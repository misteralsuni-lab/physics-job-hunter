import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
from postgrest.exceptions import APIError
from supabase import create_client, Client

from src.config import settings
from src.storage.dedup_store import DedupStore

log = logging.getLogger("job-hunter")


class SupabaseClient:
    def __init__(self):
        self.client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )
        self._dedup = DedupStore()
        # Whether ``job_listings.last_seen`` exists.  None = not yet known.
        # The column needs a manual ALTER TABLE (no raw-DDL path exists:
        # supabase-py has no ``query`` method, the project exposes no DDL RPC,
        # and SUPABASE_DB_URL in .env has a masked password).  Rather than
        # pay a failed request on every run to discover that, the answer is
        # probed once and remembered for the process.
        self._supports_last_seen: bool | None = None

    def close(self):
        self._dedup.close()

    @property
    def supports_last_seen(self) -> bool:
        """Whether ``job_listings.last_seen`` is present (None counts as no)."""
        return self._supports_last_seen is True

    def health_check(self) -> bool:
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                self.client.table("job_listings").select("id").limit(1).execute()
                log.info("Supabase connection healthy")
                return True
            except (httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException) as e:
                last_error = e
                if attempt < 3:
                    log.warning(
                        "Supabase health check attempt %d/3 failed (%s) — retrying",
                        attempt, e,
                    )
                    time.sleep(2 * attempt)

        log.warning("Supabase unreachable at startup: %s — using DedupStore", last_error)
        return False

    def get_seen_urls(self) -> set[str]:
        """Every URL already stored in Supabase.

        Two retries, because this single query underpins URL dedup and has
        been observed to time out transiently.  On total failure it falls
        back to the local SQLite ``seen_urls`` table — but that table holds
        only a small fraction of the corpus, so the pipeline would classify
        almost every scraped job as "new".  That degradation is now logged at
        ERROR rather than passing silently.
        """
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                result = self.client.table("job_listings").select("url").execute()
                return {row["url"] for row in result.data}
            except httpx.HTTPError as e:
                last_error = e
                if attempt < 2:
                    log.warning("get_seen_urls attempt %d failed (%s) — retrying",
                                attempt + 1, e)
                    time.sleep(2 * (attempt + 1))

        log.error(
            "get_seen_urls failed after 3 attempts (%s). Falling back to the "
            "LOCAL SQLite seen_urls table, which holds far fewer URLs than "
            "Supabase — URL dedup is degraded this run and already-known jobs "
            "may be misreported as new.", last_error,
        )
        return self._dedup.get_seen_urls()

    def upsert_jobs(self, jobs: list[dict[str, Any]]) -> int:
        """Batch upsert all jobs in a single API call.

        Every row is stamped with ``last_seen`` so the pipeline can
        distinguish "still listed on the board" from "vanished".  Callers
        should pass *every* job scraped this run, not only unseen ones —
        re-upserting an existing URL refreshes ``last_seen`` without
        disturbing ``created_at``, ``score`` or ``notified``.

        Returns the number of rows written to Supabase, or ``None`` when the
        write failed and the jobs were diverted to the local SQLite cache.
        Raises :class:`httpx.HTTPError` only if the entire batch fails.
        """
        rows = []
        now = datetime.now(timezone.utc).isoformat()
        # Skip the column once we know it is absent, so a missing migration
        # costs nothing after the first probe.
        stamp = self._supports_last_seen is not False
        for job in jobs:
            cd = job.get("closing_date")
            if cd == "" or cd is None:
                cd_val = None
            else:
                cd_val = cd
            rows.append({
                "url": job["url"],
                "title": job.get("title", ""),
                "school": job.get("school", ""),
                "country": job.get("country", ""),
                "city": job.get("city", ""),
                "curriculum": job.get("curriculum", []),
                "subject": job.get("subject", []),
                "salary_range": job.get("salary_range", ""),
                "visa_sponsorship": job.get("visa_sponsorship"),
                "housing_allowance": job.get("housing_allowance"),
                "closing_date": cd_val,
                "source": job.get("source", ""),
                "raw_json": job,
            })
            if stamp:
                rows[-1]["last_seen"] = now

        if not rows:
            return 0

        try:
            written = self._write_rows(rows, jobs)
            if stamp:
                self._supports_last_seen = True
            return written
        except APIError as e:
            # ``last_seen`` needs the ALTER TABLE from setup_supabase.sql.
            # That migration is applied by hand, so tolerate its absence
            # rather than failing the whole batch and silently routing
            # everything to the local SQLite fallback.  Remember the answer
            # so later batches do not pay for a doomed request again.
            if "last_seen" not in str(e):
                raise
            self._supports_last_seen = False
            log.info(
                "job_listings.last_seen is absent — running without it. Optional "
                "upgrade: ALTER TABLE job_listings ADD COLUMN last_seen "
                "timestamptz DEFAULT now() (scripts/setup_supabase.sql). "
                "Nothing else depends on it; the 45-day freshness gate uses "
                "created_at."
            )
            for row in rows:
                row.pop("last_seen", None)
            return self._write_rows(rows, jobs)

    def _write_rows(self, rows: list[dict[str, Any]], jobs: list[dict[str, Any]] | None = None) -> int | None:
        """Write rows. Returns the count written, or ``None`` if nothing landed.

        ``None`` matters: the previous version returned ``len(rows)`` even when
        the request failed and the jobs were diverted to the local SQLite
        cache, so ``run_pipeline`` cheerfully logged "Stored 43 new jobs in
        Supabase" for a write that never happened.
        """
        try:
            self.client.table("job_listings").upsert(
                rows,
                on_conflict="url",
                ignore_duplicates=False,
            ).execute()
            return len(rows)
        except httpx.HTTPError as e:
            log.error(
                "batch upsert FAILED for %d job(s): %s — diverted to the local "
                "SQLite cache; Supabase is NOT updated this run", len(rows), e,
            )
            if jobs is not None:
                self._dedup.cache_jobs(jobs)
            return None

    def get_unscored_jobs(self) -> list[dict[str, Any]]:
        try:
            result = self.client.table("job_listings").select("*").is_("score", "null").execute()
            return result.data
        except httpx.HTTPError as e:
            log.warning("get_unscored_jobs failed: %s — falling back to dedup", e)
            return self._dedup.get_unscored()

    def get_unscored_from_dedup(self) -> list[dict[str, Any]]:
        return self._dedup.get_unscored()

    def update_score(self, job_id: str, score: int, reasoning: str) -> None:
        try:
            self.client.table("job_listings").update(
                {"score": score, "score_reasoning": reasoning}
            ).eq("id", job_id).execute()
        except httpx.HTTPError as e:
            log.warning("update_score failed for %s: %s — falling back to dedup", job_id, e)
            self._dedup.update_score(job_id, score, reasoning)

    def get_scored_unnotified(self, min_score: int = settings.notify_score_threshold,
                              max_age_days: int | None = None) -> list[dict[str, Any]]:
        """Scored, un-notified jobs eligible for an alert.

        ``max_age_days`` gates on ``created_at`` — when the posting first
        entered our pool — not on ``last_seen``.  That distinction is the
        whole point: TES re-serves the identical URL indefinitely, so a
        ``last_seen`` gate would refresh forever and suppress nothing.
        A posting we first saw months ago and that is still being re-listed
        is a zombie listing, and ``created_at`` is the only field that
        reveals that without a date on the payload (TES carries none, and
        96% of rows have ``closing_date IS NULL``).
        """
        query = (
            self.client.table("job_listings")
            .select("*")
            .gte("score", min_score)
            .eq("notified", False)
        )
        if max_age_days is not None:
            since = datetime.now(timezone.utc) - timedelta(days=max_age_days)
            query = query.gte("created_at", since.isoformat())
        try:
            return query.execute().data
        except httpx.HTTPError as e:
            log.warning("get_scored_unnotified failed: %s — falling back to dedup", e)
            jobs = self._dedup.get_scored_unnotified(min_score=min_score)
            for job in jobs:
                job["id"] = job["url"]
            return jobs

    def mark_notified(self, ids: list[str]) -> None:
        if not ids:
            return
        try:
            self.client.table("job_listings").update({"notified": True}).in_("id", ids).execute()
        except httpx.HTTPError as e:
            log.warning("mark_notified failed: %s — falling back to dedup", e)
            self._dedup.mark_notified(ids)

    def get_recent(self, days: int = 1) -> list[dict[str, Any]]:
        try:
            since = date.today().isoformat()
            result = self.client.table("job_listings").select("*").gte("created_at", since).execute()
            return result.data
        except httpx.HTTPError as e:
            log.warning("get_recent failed: %s", e)
            return []

    def get_notified_jobs(self, since_days: int = 180) -> list[dict[str, Any]]:
        """Jobs marked notified within ``since_days`` — used to backfill the
        signature-dedup store at deploy time."""
        try:
            since = (date.today() - timedelta(days=since_days)).isoformat()
            result = (
                self.client.table("job_listings")
                .select("*")
                .eq("notified", True)
                .gte("created_at", since)
                .execute()
            )
            return result.data
        except httpx.HTTPError as e:
            log.warning("get_notified_jobs failed: %s", e)
            return []
