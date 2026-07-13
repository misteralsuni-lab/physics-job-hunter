import argparse
import logging
import os
import sys
from datetime import datetime

import httpx

from src.config import settings
from src.scrapers.tes import TESScraper
from src.scrapers.linkedin import LinkedInScraper
from src.scrapers.dipont import DipontScraper
from src.scrapers.toptutorjob import TopTutorJobScraper
from src.scrapers.teacher_horizons import TeacherHorizonsScraper
from src.scrapers.search_associates import SearchAssociatesScraper
from src.scrapers.gulftalent import GulfTalentScraper
from src.scrapers.schrole import SchroleScraper
from src.scrapers.libyan_jobs import LibyanJobsScraper
from src.storage.supabase_client import SupabaseClient
from src.scoring.llm_scorer import LLMScorer
from src.generators.cover_letter import CoverLetterGenerator
from src.agents.research_agent import ResearchAgent
from src.agents.models import StrategicBrief
from src.campaign import load_campaign
from src.notify.telegram import send_telegram_alert
from src.notify.email_sender import send_email_digest

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("job-hunter")


CORE_KEYWORDS = {"physics", "edexcel", "pearson", "igcse", "a-level"}

# Jobs mentioning these exam boards or curricula are definitively
# out-of-scope for an Edexcel/IGCSE/A-Level Physics specialist.
_EXCLUDED_EXAM_BOARDS = frozenset({
    "cambridge", "cie", "aqa", "oxford aqa", "ib",
    "international baccalaureate", "ocr",
    # US curriculum indicators — we don't teach these.
    "american curriculum", "common core", "ccss", "ngss",
    "advanced placement", "ap ", "ap,", "ap.",
    "texas essential knowledge", "teks",
})

# Jobs containing these phrases are definitively out-of-scope for a
# Physics / Maths / Science teacher.
_EXCLUSION_PHRASES = frozenset({
    "physical education",
    "pe teacher",
    "early years",
    "primary school",
    "female applicants only",
    "male applicants only",
    "female only",
    "male only",
})

# Roles that are NOT actual teaching positions — drop regardless of subject.
# Title-substring match is case-insensitive.  Each phrase was added in
# response to a specific false-positive that reached Telegram: 2026-06-29
# "Physics Technician" (Colfe's School, Greenwich) and "Lead Teacher of
# Biology" (The Oratory School) — both bypassed the hard-type specialty
# filter because the title literally contained the word "physics".
#
# All phrases are intentionally substring-matched (containment), so
# "Teaching Assistant in Physics" is caught by both
# "teaching assistant" and "in physics" — defence in depth.
_NON_TEACHER_ROLES = frozenset({
    # Original blocker set (2026-06-28)
    "teaching assistant", "cover supervisor", "wellbeing advisor",
    "wellbeing officer", "cover manager", "cover coordinator",
    "head of year", "pastoral", "teaching support", "learning support",
    "examinations officer", "senior prefect",
    # Lab / technician roles (added 2026-06-29 after the
    # "Physics Technician — Colfe's School" surprise)
    "technician", "lab technician", "science technician",
    "stem technician", "physics lab", "physics laboratory",
    # Management / non-teaching roles
    "director of", "head of department", "head of physics",
    "manager", "coordinator", "administrator",
    # Higher-ed / non-target-school roles
    "lecturer", "university", "researcher", "postdoc", "professor",
    # "TA" / stand-alone abbreviations (substring " ta " or leading "ta ")
    # Caught implicitly by "teaching assistant" mostly; "TAs" form
    # rarely appears and is not worth a long phrase.
    #
    # Note: "STEM Tutor" was considered — title contains "physics" only
    # when the broad STEM role also requires a physics specialism.  The
    # AGENTS.md "core keywords" set intentionally leaves STEM-adjacent
    # tutors in-scope (they may legitimately teach physics).  If
    # false-positives climb, add "stem tutor" / "stem instructor" here.
})


def _is_relevant(job: dict, campaign: dict | None = None) -> bool:
    title = (job.get("title") or "").lower()
    subject_list = [s.lower() for s in (job.get("subject") or [])]
    curriculum_list = [c.lower() for c in (job.get("curriculum") or [])]
    combined = f"{title} {' '.join(subject_list)} {' '.join(curriculum_list)}"

    # FIRST: reject excluded exam boards (Cambridge, CIE, AQA, IB, etc.)
    # In campaign mode the adjacent lane (Cambridge/IB) is intentionally
    # allowed through the pre-filter, so this guard is skipped.
    if campaign is None:
        for phrase in _EXCLUDED_EXAM_BOARDS:
            if phrase in combined:
                return False

    # Reject out-of-scope roles (gender restrictions, wrong subject area).
    for phrase in _EXCLUSION_PHRASES:
        if phrase in title:
            return False

    # Drop non-teacher / support roles.  These listings can carry "IGCSE,
    # A-Level" in the curriculum array and would otherwise sneak through.
    for phrase in _NON_TEACHER_ROLES:
        if phrase in title:
            return False

    # HARD REQUIREMENT: title or subject MUST mention "physics".  Without
    # this, any teacher role that includes the words "IGCSE" or "A-Level"
    # anywhere in the listing passes — that is how Geography / TA / Wellbeing
    # jobs were reaching the LLM scorer and Telegram digest.
    if "physics" not in combined:
        return False

    return True


def _campaign_text(job: dict) -> str:
    return " ".join(str(job.get(k, "")) for k in
                    ("title", "school", "country", "location", "description", "subject", "curriculum")).lower()


def _derive_curriculum(text: str, precedence: list[str]) -> str:
    found = []
    if "edexcel" in text or "pearson" in text:
        found.append("Edexcel")
    if "cambridge" in text or " cie" in text or text.startswith("cie ") or "cie," in text:
        found.append("Cambridge")
    import re
    if re.search(r"\bib\b", text) or "international baccalaureate" in text:
        found.append("IB")
    for cur in precedence:
        if cur in found:
            return cur
    return "Other"


def _derive_region(text: str, location_components: dict) -> str:
    if "dresden" in text:
        return "Dresden"
    if "germany" in text or " berlin" in text or "leipzig" in text or "paderborn" in text or "munich" in text:
        return "Germany"
    if "czech" in text or "prague" in text:
        return "Czechia"
    if any(w in text for w in ("poland", "warsaw", "hungary", "budapest", "austria", "vienna", "slovakia", "bratislava")):
        return "CentralEurope"
    return "Other"


def tag_campaign(job: dict, campaign: dict) -> dict | None:
    """Tag a surviving job with campaign curriculum/region/lane/score.

    Returns the mutated job, or None when the job falls in the disabled
    curriculum_adjacent lane (so the caller can drop it).
    """
    text = _campaign_text(job)
    precedence = campaign.get("curriculum_precedence", ["Edexcel", "Cambridge", "IB", "Other"])
    curriculum = _derive_curriculum(text, precedence)
    region = _derive_region(text, campaign["scoring"]["location"]["components"])
    lane = "edexcel_only" if curriculum == "Edexcel" else "curriculum_adjacent"

    if lane == "curriculum_adjacent" and not campaign.get("secondary_lane_enabled", False):
        return None

    cm = 0.0
    comps = campaign["scoring"]["curriculum_match"]["components"]
    # Subject credit is awarded on the SUBJECTS offered (physics/maths at
    # A-Level / IGCSE), independent of the exam board. The board only decides
    # whether the full (Edexcel) credit applies or the 0.6x adjacency boost
    # (Cambridge / IB). This is what lets a Cambridge Physics+Maths school
    # earn real curriculum_match credit instead of only the strong_stem point.
    has_al = "a-level" in text or "a level" in text
    has_ig = "igcse" in text
    has_phys = "physics" in text
    has_math = "maths" in text or "math" in text
    if has_al:
        if has_phys:
            cm += comps.get("pearson_edexcel_a_level_physics", 0)
        if has_math:
            cm += comps.get("pearson_edexcel_a_level_maths", 0)
    if has_ig:
        if has_phys:
            cm += comps.get("pearson_edexcel_igcse_physics", 0)
        if has_math:
            cm += comps.get("pearson_edexcel_igcse_maths", 0)
    if has_phys or has_math or "science" in text or "stem" in text:
        cm += comps.get("strong_stem", 0)
    if lane == "curriculum_adjacent":
        cm *= campaign.get("lane", {}).get("adjacency_boost", 0.6)

    subject = 0
    sm = campaign["scoring"]["subject_match"]
    has_physics = "physics" in text
    has_maths = "maths" in text or "math" in text
    if has_physics and has_maths:
        subject = sm.get("physics_and_maths", 0)
    elif has_physics:
        subject = sm.get("physics_vacancy", 0)
    elif has_maths:
        subject = sm.get("maths_vacancy", 0)

    school = (job.get("school") or "").lower()
    whitelist = {s["name"].lower(): s for s in campaign.get("target_schools", [])}
    match = next((v for k, v in whitelist.items() if k and k in school), None)
    if match:
        visa = match.get("visa", 0)
        career = match.get("career", 0)
        competition = match.get("competition", 0)
    else:
        visa = campaign["scoring"]["visa"].get("unknown", 5)
        career = 0
        competition = 0

    loc = campaign["scoring"]["location"]["components"].get(
        {"Dresden": "dresden_region", "Germany": "germany", "Czechia": "czechia", "CentralEurope": "central_europe"}.get(region, ""), 0)

    total = cm + subject + visa + loc + career + competition
    total = int(min(100, round(total)))

    tagged = dict(job)
    tagged["curriculum"] = curriculum
    tagged["region"] = region
    tagged["lane"] = lane
    tagged["campaign_score"] = total
    return tagged


def filter_relevant_jobs(jobs: list[dict], campaign: dict | None = None) -> list[dict]:
    before = len(jobs)
    kept = [j for j in jobs if _is_relevant(j, campaign)]
    if campaign is not None:
        tagged = []
        for j in kept:
            t = tag_campaign(j, campaign)
            if t is not None:
                tagged.append(t)
        kept = tagged
    dropped = before - len(kept)
    if dropped:
        log.info("Heuristic pre-filter: dropped %d deviant job(s), keeping %d", dropped, len(kept))
    return kept


def run_scrapers() -> list[dict]:
    scrapers = [TESScraper(), LinkedInScraper(), DipontScraper(),
                TopTutorJobScraper(),
                SearchAssociatesScraper(), TeacherHorizonsScraper(),
                GulfTalentScraper(),
                SchroleScraper(), LibyanJobsScraper()]
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


def send_notifications(jobs: list[dict], db: SupabaseClient | None = None, campaign: dict | None = None) -> None:
    top_jobs = [j for j in jobs if j.get("score", 0) >= settings.notify_score_threshold]
    if not top_jobs:
        log.info("No top-scoring jobs to notify")
        return

    # In campaign mode, only research jobs in lanes the campaign allows.
    if campaign is not None:
        secondary = campaign.get("secondary_lane_enabled", False)
        research_candidates = [
            j for j in top_jobs
            if j.get("score", 0) >= settings.research_score_threshold
            and (j.get("lane") == "edexcel_only"
                 or (j.get("lane") == "curriculum_adjacent" and secondary))
        ]
    else:
        research_candidates = [j for j in top_jobs if j.get("score", 0) >= settings.research_score_threshold]

    if research_candidates:
        log.info("Running strategic research for %d high-scoring job(s)...", len(research_candidates))
        agent = ResearchAgent(campaign=campaign)
        for job in research_candidates:
            try:
                brief = agent.research(
                    school_name=job.get("school", ""),
                    location=job.get("location", "") or job.get("city", "") or job.get("country", ""),
                    job_description=job.get("description", ""),
                    campaign=campaign,
                )
                job["research_brief"] = brief.model_dump()
                log.info("  ✓ Research brief produced for %s at %s", job.get("title", "?"), job.get("school", "?"))
            except Exception as e:
                log.error("  ✗ Research agent failed for %s: %s", job.get("title", "?"), e)
                job["research_brief"] = StrategicBrief.fallback(job.get("school", "the school")).model_dump()

    # Generate bespoke cover letters for every top-scoring job
    log.info("Generating cover letters for %d top-scoring jobs...", len(top_jobs))
    generator = CoverLetterGenerator()
    cover_letter_paths: dict[str, str] = {}
    for job in top_jobs:
        try:
            path = generator.generate(job, campaign=campaign)
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

    campaign = load_campaign()
    jobs = run_scrapers()
    jobs = filter_relevant_jobs(jobs, campaign)
    count = 0
    scored = 0

    db_available = False
    try:
        db = SupabaseClient()
        if not db.health_check():
            log.info("Supabase unhealthy — DedupStore fallback for entire pipeline")
            raise httpx.HTTPError("health check failed")

        scorer = LLMScorer(campaign=campaign)

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
                send_notifications(all_scored, db, campaign=campaign)
            else:
                log.info("Force-notify: no jobs scored >= %d", settings.notify_score_threshold)
        else:
            db_jobs = db.get_scored_unnotified(min_score=settings.notify_score_threshold)
            send_notifications(db_jobs, db, campaign=campaign)

        db_available = True

    except httpx.HTTPError as e:
        log.error("Supabase unreachable — continuing with in-memory scoring: %s", e)

    if not db_available and jobs:
        log.info("Falling back to in-memory scoring for %d jobs...", len(jobs))
        scorer = LLMScorer(campaign=campaign)
        scored_jobs = score_jobs_in_memory(jobs, scorer)
        scored = len([j for j in scored_jobs if j.get("score") is not None])
        send_notifications(scored_jobs, campaign=campaign)

    elapsed = (datetime.now() - start).total_seconds()
    log.info("Pipeline complete in %.1fs — %d new, %d scored", elapsed, count, scored)
    return {"new": count, "scored": scored, "elapsed": elapsed}


def main():
    parser = argparse.ArgumentParser(description="Physics Job Hunter Pipeline")
    parser.add_argument("--force-notify", action="store_true", help="Notify all scored jobs ≥80, ignoring 'notified' flag")
    parser.add_argument("--campaign-run", action="store_true",
                        help="Run the proactive discovery campaign (CAMPAIGN env must be set) instead of the reactive pipeline.")
    parser.add_argument("--campaign-id", default=None,
                        help="Campaign id for --campaign-run (overrides CAMPAIGN env if set).")
    args = parser.parse_args()

    if args.campaign_run:
        from src.campaign_runner import run_campaign
        force = os.getenv("FORCE", "").strip() == "1"
        campaign_id = args.campaign_id or (settings.campaign or "").strip() or None
        result = run_campaign(campaign_id=campaign_id, force=force)
        print(f"Campaign done. {result['discovered']} discovered, "
              f"{result['top10']} top-10 researched in {result['elapsed']:.1f}s")
        sys.exit(0)

    result = run_pipeline(force_notify=args.force_notify)
    print(f"Done. {result['new']} new jobs, {result['scored']} scored in {result['elapsed']:.1f}s")
    sys.exit(0)


if __name__ == "__main__":
    main()
