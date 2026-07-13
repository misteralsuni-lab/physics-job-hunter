"""Campaign orchestrator — wires the proactive-discovery pieces into a runnable pipeline.

Steps wired (see ``docs/campaign_handoff.md``):
  DiscoveryAgent → ProspectsStore → ResearchAgent (top 10) →
  CoverLetterGenerator (speculative) → CampaignReporter → Telegram digest.

Run via::

    CAMPAIGN=pe_central_europe python3 -m src.campaign_runner
    CAMPAIGN=pe_central_europe FORCE=1 python3 -m src.campaign_runner   # re-discover
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agents.discovery_agent import DiscoveryAgent
from src.agents.models import StrategicBrief
from src.agents.research_agent import ResearchAgent
from src.campaign import load_campaign
from src.config import settings
from src.generators.campaign_reporter import CampaignReporter
from src.generators.cover_letter import CoverLetterGenerator
from src.storage.prospects_store import ProspectsStore

log = logging.getLogger("job-hunter")


def _load_campaign_by_id(campaign_id: str) -> dict | None:
    from src.campaign import _CAMPAIGN_DIR

    path = _CAMPAIGN_DIR / f"campaign_{campaign_id}.json"
    if not path.exists():
        return None
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _email_out_dir(campaign: dict) -> str:
    out = campaign.get("output", {})
    base = out.get("base_dir", "data/campaign_pe_central_europe")
    emails = out.get("emails_dir", "emails")
    return str(Path(base) / emails)


def run_campaign(campaign_id: str | None = None, force: bool = False) -> dict:
    """Run a proactive discovery campaign end-to-end.

    Args:
        campaign_id: Optional id to load when ``CAMPAIGN`` env is not set.
        force: Re-run discovery ignoring in-memory dedup by ``normalized_key``.

    Returns:
        A summary dict with ``discovered`` and ``top10`` counts.
    """
    start = datetime.now()
    log.info("=" * 50)
    log.info("Physics Job Hunter — Campaign Run Start")
    log.info("=" * 50)

    campaign = load_campaign() or (_load_campaign_by_id(campaign_id) if campaign_id else None)
    if campaign is None:
        raise SystemExit(
            "No campaign configured. Set CAMPAIGN=pe_central_europe or pass --campaign-id."
        )

    # 1. Discover real target schools (radial web-search, verified).
    agent = DiscoveryAgent(campaign)
    prospects = agent.discover(force=force)
    if not prospects:
        log.warning("Discovery returned 0 prospects — nothing to persist or report.")
        return {"discovered": 0, "top10": 0, "elapsed": 0.0}

    # 2. Persist all discovered prospects.
    store = ProspectsStore()
    store.upsert_prospects(prospects)

    # 3. Pull the top 10 (Category-F first, then score desc) for deep research.
    top10 = store.get_top(campaign["id"], n=10)

    # 4. Deep-research + speculative outreach email for the top 10.
    researcher = ResearchAgent(campaign=campaign)
    generator = CoverLetterGenerator()
    out_dir = _email_out_dir(campaign)
    email_paths: dict[str, str] = {}

    for p in top10:
        desc = (
            f"Offerings: {p.get('pearson_offerings')}; "
            f"Location: {p.get('location')}; "
            f"Evidence: {p.get('evidence_urls')}"
        )
        try:
            brief = researcher.research(
                p["school_name"], p.get("location", ""), desc, campaign=campaign
            )
            p["research_brief"] = brief.model_dump()
        except Exception as exc:
            log.error("Research failed for %s: %s — using fallback brief",
                      p.get("school_name"), exc)
            p["research_brief"] = StrategicBrief.fallback(p["school_name"]).model_dump()

        try:
            path = generator.generate(p, speculative=True, out_dir=out_dir)
        except Exception as exc:
            log.error("Speculative email failed for %s: %s", p.get("school_name"), exc)
            path = None
        if path:
            p["outreach_email_path"] = path
            email_paths[p["normalized_key"]] = path

    # 5. Persist enriched top 10 (brief + email path).
    store.upsert_prospects(top10)

    # 6. Merge enrichment back into the full prospect list for reporting.
    merged: dict[str, dict[str, Any]] = {p["normalized_key"]: p for p in prospects}
    for t in top10:
        merged[t["normalized_key"]] = t
    all_for_report = list(merged.values())

    reporter = CampaignReporter(campaign)
    reporter.write_prospect_briefs(all_for_report)
    reporter.render_strategy_report(all_for_report, top10)
    reporter.send_digest(top10, email_paths)

    store.close()

    elapsed = (datetime.now() - start).total_seconds()
    log.info("Campaign run complete in %.1fs — %d discovered, %d top-10 researched",
             elapsed, len(prospects), len(top10))
    return {"discovered": len(prospects), "top10": len(top10), "elapsed": elapsed}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Physics Job Hunter — Campaign Runner")
    parser.add_argument("--campaign-id", default=None,
                        help="Campaign id to run (overrides CAMPAIGN env if set).")
    parser.add_argument("--force", action="store_true",
                        help="Re-run discovery ignoring dedup by normalized_key.")
    args = parser.parse_args(argv)

    force = args.force or (os.getenv("FORCE", "").strip() == "1")
    campaign_id = args.campaign_id or (settings.campaign or "").strip() or None

    result = run_campaign(campaign_id=campaign_id, force=force)
    print(f"Campaign done. {result['discovered']} discovered, "
          f"{result['top10']} top-10 researched in {result['elapsed']:.1f}s")
    sys.exit(0)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")
    main()
