import hashlib
import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger("job-hunter")

DB_PATH = Path("data/dedup.db")

# Re-post TTL.  A board re-uses the same school + title + country for a *new*
# hiring cycle (TES in particular mints a fresh job id for every re-post), so
# the signature table suppresses cross-URL re-posts — but only for this long.
# After the TTL a genuine next-round vacancy alerts again, which is the whole
# point of running the pipeline daily.
#
# The previous 180-day window was one window doing two unrelated jobs.  It
# also created a permanent deadlock: `signature_notified()` suppressed by
# signature alone, so a row that the `notified` flag still reported as False
# could never alert again, even after a failed `mark_notified`.  Suppression
# for the *same* URL is not this table's job — that is the `notified` column's,
# and `get_scored_unnotified()` already filters on it.  This table exists
# solely to collapse the same vacancy advertised under several URLs.
SIGNATURE_REPOST_TTL_DAYS = 30

_NORM_RE = re.compile(r"[^a-z0-9 ]+")


def job_signature(job: dict[str, Any]) -> str:
    """Stable md5 signature for a job: school | title | country.

    Used to detect the same vacancy posted by different boards/agencies
    under different URLs (e.g. a TES ad and a BSO ad for the same role).
    Normalisation lowercases and strips punctuation so "UAE" and
    "United Arab Emirates" converge via the country field values already
    canonicalised by the scrapers.
    """
    def norm(value: str) -> str:
        return _NORM_RE.sub(" ", (value or "").lower()).strip()

    raw = f"{norm(job.get('school', ''))}|{norm(job.get('title', ''))}|{norm(job.get('country', ''))}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


class DedupStore:
    """SQLite-backed persistent store for job dedup when Supabase is unreachable."""

    def __init__(self, db_path: str | Path = DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._init_tables()

    def _init_tables(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS seen_urls (
                url TEXT PRIMARY KEY,
                first_seen TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS job_cache (
                url TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                score INTEGER,
                notified INTEGER DEFAULT 0,
                first_seen TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS notified_signatures (
                signature TEXT PRIMARY KEY,
                first_notified TEXT NOT NULL DEFAULT (datetime('now')),
                first_url TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def get_seen_urls(self) -> set[str]:
        rows = self._conn.execute("SELECT url FROM seen_urls").fetchall()
        return {row[0] for row in rows}

    def mark_seen(self, urls: list[str]):
        self._conn.executemany(
            "INSERT OR IGNORE INTO seen_urls (url) VALUES (?)",
            [(u,) for u in urls],
        )
        self._conn.commit()

    def cache_jobs(self, jobs: list[dict[str, Any]]):
        for job in jobs:
            self._conn.execute(
                "INSERT OR REPLACE INTO job_cache (url, data) VALUES (?, ?)",
                (job["url"], json.dumps(job, default=str)),
            )
        self.mark_seen([j["url"] for j in jobs])

    def get_unscored(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT data FROM job_cache WHERE score IS NULL"
        ).fetchall()
        result = []
        for row in rows:
            job = json.loads(row[0])
            result.append(job)
        return result

    def get_scored_unnotified(self, min_score: int = 50) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT data, score FROM job_cache WHERE score >= ? AND notified = 0",
            (min_score,),
        ).fetchall()
        result = []
        for row in rows:
            job = json.loads(row[0])
            job["score"] = row[1]
            result.append(job)
        return result

    def update_score(self, url: str, score: int, reasoning: str):
        self._conn.execute(
            "UPDATE job_cache SET score = ? WHERE url = ?",
            (score, url),
        )
        self._conn.commit()

    def mark_notified(self, urls: list[str]):
        self._conn.executemany(
            "UPDATE job_cache SET notified = 1 WHERE url = ?",
            [(u,) for u in urls],
        )
        self._conn.commit()

    def signature_notified(self, signature: str,
                           window_days: int = SIGNATURE_REPOST_TTL_DAYS) -> str | None:
        """Return the first-notified URL if the signature was recorded within
        ``window_days`` (the re-post TTL); None otherwise."""
        cutoff = (datetime.now() - timedelta(days=window_days)).isoformat(timespec="seconds")
        row = self._conn.execute(
            "SELECT first_url FROM notified_signatures WHERE signature = ? AND first_notified >= ?",
            (signature, cutoff),
        ).fetchone()
        return row[0] if row else None

    def forget_signature(self, signature: str) -> bool:
        """Delete one signature so the matching vacancy can alert again.

        Used by ``--resend-muted`` to release jobs muted by the old 180-day
        window.  Returns True when a row was actually removed.
        """
        cur = self._conn.execute(
            "DELETE FROM notified_signatures WHERE signature = ?", (signature,)
        )
        self._conn.commit()
        return cur.rowcount > 0

    def record_signature(self, signature: str, url: str):
        self._conn.execute(
            "INSERT OR IGNORE INTO notified_signatures (signature, first_url) VALUES (?, ?)",
            (signature, url),
        )
        self._conn.commit()

    def record_signatures(self, jobs: list[dict[str, Any]], urls: list[str]):
        for job, url in zip(jobs, urls):
            self.record_signature(job_signature(job), url)

    def backfill_signatures(self, jobs: list[dict[str, Any]]):
        """Seed signatures from already-notified jobs (deploy-time backfill)."""
        count = 0
        for job in jobs:
            sig = job_signature(job)
            row = self._conn.execute(
                "SELECT 1 FROM notified_signatures WHERE signature = ?",
                (sig,),
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT OR IGNORE INTO notified_signatures (signature, first_url) VALUES (?, ?)",
                    (sig, job.get("url", "")),
                )
                count += 1
        self._conn.commit()
        if count:
            log.info("Backfilled %d notified signature(s)", count)

    def signature_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM notified_signatures").fetchone()
        return row[0] if row else 0

    def close(self):
        self._conn.close()
