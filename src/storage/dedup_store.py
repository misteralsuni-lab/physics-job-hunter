import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

log = logging.getLogger("job-hunter")

DB_PATH = Path("data/dedup.db")


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

    def close(self):
        self._conn.close()
