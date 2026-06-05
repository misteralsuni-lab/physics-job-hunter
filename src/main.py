import logging
import sys
from datetime import datetime

import httpx

from src.config import settings
from src.scrapers.tes import TESScraper
from src.scrapers.linkedin import LinkedInScraper
from src.storage.supabase_client import SupabaseClient
from src.scoring.llm_scorer import LLMScorer
from src.notify.telegram import send_telegram_alert
from src.notify.email_sender import send_email_digest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("job-hunter")


def run_scrapers() -> list[dict]:
    scrapers = [TESScraper(), LinkedInScraper()]
    all_jobs = []
    for scraper in scrapers:
        try:
            log.info("Running %s scraper...", scraper.SOURCE_NAME)
            jobs = scraper.run()
            all_jobs.extend(jobs)
            log.info("  → %d jobs from %s", len(jobs), scraper.SOURCE_NAME)
        except Exception as e:
            log.error("  ✗ %s failed: %s", scraper.SOURCE_NAME, e)
    return all_jobs


def score_jobs(db: SupabaseClient, scorer: LLMScorer) -> int:
    unscored = db.get_unscored_jobs()
    log.info("Scoring %d jobs...", len(unscored))
    scored = 0
    for job in unscored:
        try:
            result = scorer.score(job)
            db.update_score(job["id"], result["score"], result["reasoning"])
            scored += 1
        except Exception as e:
            log.error("  ✗ Failed to score job %s: %s", job.get("id"), e)
    log.info("  → %d jobs scored", scored)
    return scored


def send_notifications(db: SupabaseClient) -> None:
    top_jobs = db.get_scored_unnotified(min_score=80)
    if not top_jobs:
        log.info("No top-scoring jobs to notify")
        return

    tg = send_telegram_alert(top_jobs)
    log.info("Telegram: %d alerts sent", tg)

    email_ok = send_email_digest(top_jobs)
    log.info("Email digest: %s", "sent" if email_ok else "skipped")

    db.mark_notified([j["id"] for j in top_jobs])


def run_pipeline() -> dict:
    start = datetime.now()
    log.info("=" * 50)
    log.info("Physics Job Hunter — Pipeline Start")
    log.info("=" * 50)

    jobs = run_scrapers()
    count = 0
    scored = 0

    try:
        db = SupabaseClient()
        scorer = LLMScorer()

        existing = db.get_seen_urls()
        new_jobs = [j for j in jobs if j["url"] not in existing]

        if not new_jobs:
            log.info("No new jobs found")
        else:
            count = db.upsert_jobs(new_jobs)
            log.info("Stored %d new jobs in Supabase", count)

        scored = score_jobs(db, scorer)
        send_notifications(db)

    except httpx.HTTPError as e:
        log.error("Supabase unreachable — pipeline continuing without persistence: %s", e)

    elapsed = (datetime.now() - start).total_seconds()
    log.info("Pipeline complete in %.1fs — %d new, %d scored", elapsed, count, scored)
    return {"new": count, "scored": scored, "elapsed": elapsed}


def main():
    result = run_pipeline()
    print(f"Done. {result['new']} new jobs, {result['scored']} scored in {result['elapsed']:.1f}s")
    sys.exit(0)


if __name__ == "__main__":
    main()
