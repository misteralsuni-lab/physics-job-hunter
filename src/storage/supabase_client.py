from datetime import date, datetime
from typing import Any

from supabase import create_client, Client

from src.config import settings


class SupabaseClient:
    def __init__(self):
        self.client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )

    def get_seen_urls(self) -> set[str]:
        result = self.client.table("job_listings").select("url").execute()
        return {row["url"] for row in result.data}

    def upsert_job(self, job: dict[str, Any]) -> None:
        self.client.table("job_listings").upsert(
            {
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
                "closing_date": job.get("closing_date"),
                "source": job.get("source", ""),
                "raw_json": job,
            },
            on_conflict="url",
        ).execute()

    def upsert_jobs(self, jobs: list[dict[str, Any]]) -> int:
        count = 0
        for job in jobs:
            self.upsert_job(job)
            count += 1
        return count

    def get_unscored_jobs(self) -> list[dict[str, Any]]:
        result = self.client.table("job_listings").select("*").is_("score", "null").execute()
        return result.data

    def update_score(self, job_id: str, score: int, reasoning: str) -> None:
        self.client.table("job_listings").update(
            {"score": score, "score_reasoning": reasoning}
        ).eq("id", job_id).execute()

    def get_scored_unnotified(self, min_score: int = 80) -> list[dict[str, Any]]:
        result = self.client.table("job_listings").select("*").gte("score", min_score).eq("notified", False).execute()
        return result.data

    def mark_notified(self, job_ids: list[str]) -> None:
        self.client.table("job_listings").update({"notified": True}).in_("id", job_ids).execute()

    def get_recent(self, days: int = 1) -> list[dict[str, Any]]:
        since = date.today().isoformat()
        result = self.client.table("job_listings").select("*").gte("created_at", since).execute()
        return result.data
