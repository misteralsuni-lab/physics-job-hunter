import logging
from datetime import date, datetime
from typing import Any

import httpx
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

    def close(self):
        self._dedup.close()

    def health_check(self) -> bool:
        try:
            self.client.table("job_listings").select("id").limit(1).execute()
            log.info("Supabase connection healthy")
            return True
        except (httpx.HTTPError, httpx.ConnectError, httpx.TimeoutException) as e:
            log.warning("Supabase unreachable at startup: %s — using DedupStore", e)
            return False

    def get_seen_urls(self) -> set[str]:
        try:
            result = self.client.table("job_listings").select("url").execute()
            return {row["url"] for row in result.data}
        except httpx.HTTPError as e:
            log.warning("get_seen_urls failed: %s — falling back to dedup", e)
            return self._dedup.get_seen_urls()

    def upsert_jobs(self, jobs: list[dict[str, Any]]) -> int:
        """Batch upsert all jobs in a single API call.

        Returns the number of successfully upserted jobs.
        Raises :class:`httpx.HTTPError` only if the entire batch fails.
        """
        rows = []
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

        if not rows:
            return 0

        try:
            self.client.table("job_listings").upsert(
                rows,
                on_conflict="url",
                ignore_duplicates=False,
            ).execute()
            return len(rows)
        except httpx.HTTPError as e:
            log.warning("batch upsert failed for %d jobs: %s — caching to dedup", len(rows), e)
            self._dedup.cache_jobs(jobs)
            return len(rows)

    def get_unscored_jobs(self) -> list[dict[str, Any]]:
        try:
            result = self.client.table("job_listings").select("*").is_("score", "null").execute()
            return result.data
        except httpx.HTTPError as e:
            log.warning("get_unscored_jobs failed: %s — falling back to dedup", e)
            return self._dedup.get_unscored()

    def get_unscored_from_dedup(self) -> list[dict[str, Any]]:
        return self._dedup.get_unscored()

    def update_score(self, url: str, score: int, reasoning: str) -> None:
        try:
            self.client.table("job_listings").update(
                {"score": score, "score_reasoning": reasoning}
            ).eq("url", url).execute()
        except httpx.HTTPError as e:
            log.warning("update_score failed for %s: %s — falling back to dedup", url, e)
            self._dedup.update_score(url, score, reasoning)

    def get_scored_unnotified(self, min_score: int = 80) -> list[dict[str, Any]]:
        try:
            result = self.client.table("job_listings").select("*").gte("score", min_score).eq("notified", False).execute()
            return result.data
        except httpx.HTTPError as e:
            log.warning("get_scored_unnotified failed: %s — falling back to dedup", e)
            jobs = self._dedup.get_scored_unnotified(min_score=min_score)
            for job in jobs:
                job["id"] = job["url"]
            return jobs

    def mark_notified(self, urls: list[str]) -> None:
        if not urls:
            return
        try:
            self.client.table("job_listings").update({"notified": True}).in_("url", urls).execute()
        except httpx.HTTPError as e:
            log.warning("mark_notified failed: %s — falling back to dedup", e)
            self._dedup.mark_notified(urls)

    def get_recent(self, days: int = 1) -> list[dict[str, Any]]:
        try:
            since = date.today().isoformat()
            result = self.client.table("job_listings").select("*").gte("created_at", since).execute()
            return result.data
        except httpx.HTTPError as e:
            log.warning("get_recent failed: %s", e)
            return []
