import argparse
import logging
import sys
from datetime import datetime

import httpx

from src.config import settings
from src.scrapers.tes import TESScraper
from src.scrapers.linkedin import LinkedInScraper
from src.scrapers.teacher_horizons import TeacherHorizonsScraper
from src.scrapers.search_associates import SearchAssociatesScraper
from src.scrapers.schrole import SchroleScraper
from src.scrapers.libyan_jobs import LibyanJobsScraper
from src.storage.supabase_client import SupabaseClient
from src.scoring.llm_scorer import LLMScorer
from src.generators.cover_letter import CoverLetterGenerator
from src.notify.telegram import send_telegram_alert
from src.notify.email_sender import send_email_digest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("job-hunter")


CORE_KEYWORDS = {"physics", "maths", "mathematics", "science", "stem",
                  "edexcel", "igcse", "a-level", "biology", "chemistry"}


def _is_relevant(job: dict) -> bool:
    title = (job.get("title") or "").lower()
    for kw in CORE_KEYWORDS:
        if kw in title:
            return True
    for s in (job.get("subject") or []):
        if s.lower() in CORE_KEYWORDS or any(kw in s.lower() for kw in CORE_KEYWORDS):
            return True
    return False


def filter_relevant_jobs(jobs: list[dict]) -> list[dict]:
    before = len(jobs)
    kept = [j for j in jobs if _is_relevant(j)]
    dropped = before - len(kept)
    if dropped:
        log.info("Heuristic pre-filter: dropped %d deviant job(s), keeping %d", dropped, len(kept))
    return kept


def run_scrapers() -> list[dict]:
    scrapers = [TESScraper(), LinkedInScraper(), SearchAssociatesScraper(), SchroleScraper(), LibyanJobsScraper()]
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


def score_jobs_in_memory(jobs: list[dict], scorer: LLMScorer) -> list[dict]:
    unscored = [j for j in jobs if j.get("score") is None]
    if not unscored:
        return jobs
    log.info("Scoring %d jobs in memory (batch)...", len(unscored))
    try:
        results = scorer.batch_score(unscored)
        for job, result in zip(unscored, results):
            job["score"] = result.get("score", 0)
            job["scoring_reasoning"] = result.get("reasoning", "")
        log.info("  → %d jobs scored in memory", len(unscored))
    except Exception as e:
        log.error("  ✗ Batch scoring failed: %s — falling back to individual", e)
        for job in unscored:
            try:
                result = scorer.score(job)
                job["score"] = result.get("score", 0)
                job["scoring_reasoning"] = result.get("reasoning", "")
            except Exception as e2:
                log.error("  ✗ Failed to score job %s: %s", job.get("title"), e2)
    return jobs


def _job_key(job: dict) -> str:
    return str(job.get("id") or job.get("url", ""))


def score_jobs_from_db(db: SupabaseClient, scorer: LLMScorer) -> int:
    unscored = db.get_unscored_jobs()
    if not unscored:
        return 0
    log.info("Scoring %d jobs from DB (batch)...", len(unscored))
    scored = 0
    try:
        results = scorer.batch_score(unscored)
        for job, result in zip(unscored, results):
            db.update_score(_job_key(job), result.get("score", 0), result.get("reasoning", ""))
            scored += 1
    except Exception as e:
        log.error("  ✗ Batch scoring from DB failed: %s — falling back to individual", e)
        for job in unscored:
            try:
                result = scorer.score(job)
                db.update_score(_job_key(job), result["score"], result["reasoning"])
                scored += 1
            except Exception as e2:
                log.error("  ✗ Failed to score job %s: %s", _job_key(job), e2)
    log.info("  → %d jobs scored from DB", scored)
    return scored


def send_notifications(jobs: list[dict], db: SupabaseClient | None = None) -> None:
    top_jobs = [j for j in jobs if j.get("score", 0) >= settings.notify_score_threshold]
    if not top_jobs:
        log.info("No top-scoring jobs to notify")
        return

    # Generate bespoke cover letters for every top-scoring job
    log.info("Generating cover letters for %d top-scoring jobs...", len(top_jobs))
    generator = CoverLetterGenerator()
    cover_letter_paths: dict[str, str] = {}
    for job in top_jobs:
        try:
            path = generator.generate(job)
            if path:
                cover_letter_paths[job["url"]] = path
        except Exception as e:
            log.error("  ✗ Cover letter generation failed for %s: %s", job.get("title", "?"), e)

    tg = send_telegram_alert(top_jobs, cover_letter_paths)
    log.info("Telegram: %d alerts sent", tg)

    email_ok = send_email_digest(top_jobs)
    log.info("Email digest: %s", "sent" if email_ok else "skipped")

    if db is not None:
        db.mark_notified([_job_key(j) for j in top_jobs])


def run_pipeline(force_notify: bool = False) -> dict:
    start = datetime.now()
    log.info("=" * 50)
    log.info("Physics Job Hunter — Pipeline Start")
    log.info("=" * 50)

    jobs = run_scrapers()
    jobs = filter_relevant_jobs(jobs)
    count = 0
    scored = 0

    db_available = False
    try:
        db = SupabaseClient()
        if not db.health_check():
            log.info("Supabase unhealthy — DedupStore fallback for entire pipeline")
            raise httpx.HTTPError("health check failed")

        scorer = LLMScorer()

        existing = db.get_seen_urls()
        new_jobs = [j for j in jobs if j["url"] not in existing]

        if not new_jobs:
            log.info("No new jobs found")
        else:
            count = db.upsert_jobs(new_jobs)
            log.info("Stored %d new jobs in Supabase", count)

        db_scored = score_jobs_from_db(db, scorer)
        scored += db_scored

        if force_notify:
            all_scored = db.client.table("job_listings").select("*").gte("score", settings.notify_score_threshold).execute().data
            if all_scored:
                log.info("Force-notify: sending notifications for %d jobs", len(all_scored))
                send_notifications(all_scored)
            else:
                log.info("Force-notify: no jobs scored >= %d", settings.notify_score_threshold)
        else:
            db_jobs = db.get_scored_unnotified(min_score=settings.notify_score_threshold)
            send_notifications(db_jobs, db)

        db_available = True

    except httpx.HTTPError as e:
        log.error("Supabase unreachable — continuing with in-memory scoring: %s", e)

    if not db_available and jobs:
        log.info("Falling back to in-memory scoring for %d jobs...", len(jobs))
        scorer = LLMScorer()
        scored_jobs = score_jobs_in_memory(jobs, scorer)
        scored = len([j for j in scored_jobs if j.get("score") is not None])
        send_notifications(scored_jobs)

    elapsed = (datetime.now() - start).total_seconds()
    log.info("Pipeline complete in %.1fs — %d new, %d scored", elapsed, count, scored)
    return {"new": count, "scored": scored, "elapsed": elapsed}


def main():
    parser = argparse.ArgumentParser(description="Physics Job Hunter Pipeline")
    parser.add_argument("--force-notify", action="store_true", help="Notify all scored jobs ≥80, ignoring 'notified' flag")
    args = parser.parse_args()

    result = run_pipeline(force_notify=args.force_notify)
    print(f"Done. {result['new']} new jobs, {result['scored']} scored in {result['elapsed']:.1f}s")
    sys.exit(0)


if __name__ == "__main__":
    main()
