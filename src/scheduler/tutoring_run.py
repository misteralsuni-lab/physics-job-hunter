"""Tick that drains new leads through the parser + scorer + generator.

Run cadence: every ``settings.tutoring_parse_interval_min`` minutes via
the existing systemd unit (see ``scripts/...service`` and
``src/scheduler/daily_run.py`` for the schedule pattern).

v1 behaviour intentionally conservative:

1. Take up to N pending leads where N = BATCH_SIZE = 25.
2. For each, score via :func:`score_tutoring_lead` (heuristic, no LLM).
3. If ``status`` resolves to ``new`` AND ``match_score >= threshold``:
     - generate proposal (template mode by default)
     - persist proposal_text + status='proposal_sent' on the row
     - emit a Telegram notify (when configured)
4. If status is ``low_budget_hold`` / ``out_of_scope_hold``:
     - persist the score fields only; leave status; no Telegram notify.

The LLM parser path (Heather reasoning inside TutoringBrief) is wired
but disabled until next stage. Today, every lead gets a
``TutoringBrief.fallback`` brief; once the parser ships we substitute.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from src.agents.tutoring_parser import parse_to_dict
from src.config import settings
from src.generators.tutoring_proposal import generate_proposal
from src.scoring.tutoring_scorer import score_tutoring_lead
from src.storage.tutoring_leads import TutoringLeadStorage

log = logging.getLogger("tutoring.tick")


BATCH_SIZE = 25


def _emit_telegram_notify(lead_id: str, raw_message: str, score_breakdown: dict[str, int],
                          match_score: int, proposal_text: str) -> None:
    """Best-effort Telegram notify. Silent on missing config — pipeline
    must not crash if the bot credentials aren't set."""
    bot = settings.telegram_bot_token
    chat = settings.telegram_chat_id
    if not bot or not chat:
        log.info("Telegram not configured; skipping notify for lead=%s", lead_id)
        return
    try:
        import httpx  # local import — keeps startup light when notify is off
        excerpt = raw_message.replace("\n", " ")[:160]
        bd = "; ".join(f"{k}={v}" for k, v in score_breakdown.items())
        body = (
            f"*Tutoring lead ready* (id={lead_id})\n"
            f"Score {match_score}/100 — {bd}\n"
            f'"{excerpt}"\n\n'
            f"----\n{proposal_text}"
        )
        httpx.post(
            f"https://api.telegram.org/bot{bot}/sendMessage",
            params={"chat_id": chat, "text": body, "parse_mode": "Markdown"},
            timeout=10.0,
        )
    except Exception as e:
        log.warning("Telegram notify failed for lead=%s: %s", lead_id, e)


def run_once() -> dict[str, int]:
    """Drain the parse queue once. Returns a small summary dict."""
    summary = {"scanned": 0, "scored_hold": 0, "proposals_written": 0, "skipped": 0}
    try:
        storage = TutoringLeadStorage()
        if not storage.health_check():
            log.warning("tutoring_leads unreachable; skipping tick")
            return summary

        pending = storage.get_pending_parses(limit=BATCH_SIZE)
        summary["scanned"] = len(pending)
        if not pending:
            log.info("No new tutoring leads to process")
            return summary

        threshold = settings.tutoring_proposal_score_threshold

        for row in pending:
            lead_id = row["id"]
            raw = row.get("raw_message", "")
            try:
                score = score_tutoring_lead(raw)
            except Exception:
                log.exception("scorer crashed on lead=%s; leaving for retry", lead_id)
                summary["skipped"] += 1
                continue

            # Persist the parsed score fields + status plus the brief.
            brief, brief_dict = parse_to_dict(raw)
            update: dict[str, Any] = {
                "curriculum": score.curriculum,
                "timezone_offset_hours": score.timezone_offset_hours,
                "budget_per_hour_usd": score.budget_per_hour_usd,
                "urgency": score.urgency,
                "match_score": score.match_score,
                "status": score.status,
                "tutoring_brief_json": brief_dict,
            }
            storage.save_parse(lead_id, update)

            if score.status in ("low_budget_hold", "out_of_scope_hold"):
                summary["scored_hold"] += 1
                log.info(
                    "lead=%s → %s (score=%s, breakdown=%s)",
                    lead_id, score.status, score.match_score, score.score_breakdown,
                )
                continue

            if score.match_score < threshold:
                summary["scored_hold"] += 1
                log.info(
                    "lead=%s → below threshold (%s < %s); staying 'new'",
                    lead_id, score.match_score, threshold,
                )
                continue

            # Auto-proposal path
            result = generate_proposal(
                lead_row={"id": lead_id, "raw_message": raw},
                brief=brief,
                score=score,
                use_llm=False,
            )
            storage.save_proposal(
                lead_id=lead_id,
                proposal_text=result.text,
                proposed_rate_usd=score.proposed_rate_usd,
            )
            _emit_telegram_notify(
                lead_id=lead_id,
                raw_message=raw,
                score_breakdown=score.score_breakdown,
                match_score=score.match_score,
                proposal_text=result.text,
            )
            summary["proposals_written"] += 1
            log.info(
                "lead=%s → proposal_sent (score=%s, mode=%s, file=%s)",
                lead_id, score.match_score, result.mode, result.path,
            )

    except Exception:
        log.error("tutoring tick crashed:\n%s", traceback.format_exc())

    return summary


if __name__ == "__main__":   # pragma: no cover
    logging.basicConfig(level=logging.INFO)
    print(run_once())
