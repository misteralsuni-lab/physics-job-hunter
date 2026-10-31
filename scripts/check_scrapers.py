#!/usr/bin/env python3
"""Run every registered scraper once and report its yield.

Read-only: nothing is written to Supabase, scored, or notified.  Useful for
answering "which boards are actually working?" without running the pipeline.

Usage:
    python3 scripts/check_scrapers.py
    python3 scripts/check_scrapers.py --only tes,linkedin
    python3 scripts/check_scrapers.py --samples 5

Exit code is 1 if an active scraper raised, 0 otherwise.  Dormant / disabled /
credential-gated scrapers returning zero are reported as such, not failures.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.main import filter_relevant_jobs  # noqa: E402
from src.scrapers.bsoteachers import BSOTeachersScraper  # noqa: E402
from src.scrapers.dipont import DipontScraper  # noqa: E402
from src.scrapers.gulftalent import GulfTalentScraper  # noqa: E402
from src.scrapers.libyan_jobs import LibyanJobsScraper  # noqa: E402
from src.scrapers.linkedin import LinkedInScraper  # noqa: E402
from src.scrapers.schrole import SchroleScraper  # noqa: E402
from src.scrapers.search_associates import SearchAssociatesScraper  # noqa: E402
from src.scrapers.seekteachers import SeekTeachersScraper  # noqa: E402
from src.scrapers.teacher_horizons import TeacherHorizonsScraper  # noqa: E402
from src.scrapers.tes import TESScraper  # noqa: E402
from src.scrapers.toptutorjob import TopTutorJobScraper  # noqa: E402

SCRAPERS = [
    TESScraper,
    LinkedInScraper,
    DipontScraper,
    TopTutorJobScraper,
    SearchAssociatesScraper,
    TeacherHorizonsScraper,
    GulfTalentScraper,
    SchroleScraper,
    LibyanJobsScraper,
    BSOTeachersScraper,
    SeekTeachersScraper,
]

STATUS_NOTES = {
    "dipont": "not a job board (marketing page)",
    "toptutorjob": "dormant (CAMOUFOX_ENABLED=0)",
    "search_associates": "dormant (no SA credentials)",
    "teacher_horizons": "dormant (no TH credentials)",
    "gulftalent": "disabled (GT_ENABLED=0)",
    "schrole": "credential-gated",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated source names to run (default: all)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=3,
        help="Sample titles to print per non-empty scraper (default: 3)",
    )
    args = parser.parse_args()
    wanted = {s.strip().lower() for s in args.only.split(",") if s.strip()}

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    selected = [c for c in SCRAPERS if not wanted or c.SOURCE_NAME in wanted]
    if not selected:
        print(f"No scrapers matched --only={args.only!r}", file=sys.stderr)
        return 2

    results = []
    all_jobs = []
    failed = False

    print(f"Running {len(selected)} scraper(s)...\n")
    for cls in selected:
        name = cls.SOURCE_NAME
        started = time.time()
        jobs: list[dict] = []
        error = ""
        try:
            with cls() as scraper:
                jobs = scraper.run()
            all_jobs.extend(jobs)
        except Exception as exc:  # noqa: BLE001 - diagnostic tool
            failed = True
            error = f"{type(exc).__name__}: {exc}"

        elapsed = time.time() - started
        results.append((name, jobs, elapsed, error))
        if error:
            print(f"{name:18s} ERROR  {error}  ({elapsed:.1f}s)")
        else:
            note = STATUS_NOTES.get(name, "")
            suffix = f"  [{note}]" if note else ""
            print(f"{name:18s} {len(jobs):4d} job(s)  ({elapsed:.1f}s){suffix}")
            for job in jobs[: args.samples]:
                print(f"                       - {job.get('title', '')[:64]}")

    relevant = filter_relevant_jobs(all_jobs, None)
    by_source = Counter(j.get("source", "?") for j in relevant)

    print("\nSummary")
    print(f"  scraped:   {len(all_jobs)}")
    print(f"  relevant:  {len(relevant)} (physics pre-filter)")
    if by_source:
        print("  relevant by source:")
        for source, count in sorted(by_source.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"    {source:18s} {count}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
