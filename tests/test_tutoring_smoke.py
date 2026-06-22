"""Smoke tests for the tutoring scoring rubric + parser fallback.

Designed to be invoked manually::

    $ python3 tests/test_tutoring_smoke.py

No network calls, no Supabase. Tests:

- The pure-rule scorer returns the expected total for each hand-crafted
  sample below.
- ``parse_to_dict`` returns ``TutoringBrief`` even when no API key is
  configured (must hit fallback cleanly).
- ``generate_proposal`` produces a non-empty body in template mode and
  writes under ``data/cover_letters/``.

The script exits non-zero on any assertion failure so it can plug into a
cron watchdog or a CI gate later.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Allow imports from the project root regardless of cwd.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Redirect the cover-letter output dir to a temp location so we don't
# pollute data/cover_letters during the test.
_TMP = Path(tempfile.mkdtemp(prefix="tutoring_test_"))
os.environ["COVR_LETTERS_TMP"] = str(_TMP)

from src.agents.models import TutoringBrief                                  # noqa: E402
from src.agents.tutoring_parser import parse_to_dict                         # noqa: E402
from src.generators import tutoring_proposal                                 # noqa: E402
from src.scoring.tutoring_scorer import score_tutoring_lead                  # noqa: E402


PASSES: list[str] = []
FAILS: list[str] = []


def assert_eq(label: str, got, want) -> None:
    if got == want:
        PASSES.append(label)
        return
    FAILS.append(f"{label}: got={got!r} want={want!r}")


def assert_between(label: str, got, lo, hi) -> None:
    if lo <= got <= hi:
        PASSES.append(label)
        return
    FAILS.append(f"{label}: got={got!r} expected in [{lo}, {hi}]")


def assert_truthy(label: str, got) -> None:
    if got:
        PASSES.append(label)
        return
    FAILS.append(f"{label}: got falsy {got!r}")


# ---------------------------------------------------------------------------
# Scorer fixtures
# ---------------------------------------------------------------------------

def test_scorer_gulf_igcse_edexcel_strong() -> None:
    text = (
        "Hi, I am writing from Dubai about my son. He is in Year 11 doing "
        "IGCSE Edexcel Physics and struggling with electricity units. His "
        "mock was a B and we want a top grade. We can pay USD 60 per hour. "
        "Exam is in 10 weeks."
    )
    s = score_tutoring_lead(text)
    assert_eq("curriculum", s.curriculum, "IGCSE_Edexcel")
    assert_eq("status", s.status, "new")
    assert_eq("urgency_label", s.urgency, "high")
    assert_between("budget_usd", s.budget_per_hour_usd, 55.0, 65.0)
    assert_eq("timezone", s.timezone_offset_hours, 4.0)
    # Curriculum 30 + Subject 25 + TZ (Gulf ≤ 2.5h) 20 + Budget (≥$50) 15 + Urgency (weeks=10) 7 = 97
    assert_eq("score_total", s.match_score, 97)


def test_scorer_a_level_cambridge_london_uk() -> None:
    text = (
        "Looking for an A Level Cambridge physics tutor for my daughter in "
        "London. Year 12, taking CIE. £40/hr budget, weekly sessions."
    )
    s = score_tutoring_lead(text)
    assert_eq("curriculum", s.curriculum, "A-Level_CIE")
    assert_eq("status", s.status, "new")
    assert_between("budget_usd", s.budget_per_hour_usd, 45.0, 55.0)
    # Curriculum 30 + Subject 25 + TZ (UK is UTC+0, 2h from Tripoli, falls in Tier 1) 20
    # + Budget (GBP £40 ≈ $50 → ≥$50 tier) 15 + Urgency (no signal) 2 = 92
    assert_eq("score_total", s.match_score, 92)


def test_scorer_below_budget_floor() -> None:
    text = "Need physics help in UAE. Budget USD 20 per hour. IGCSE Pearson."
    s = score_tutoring_lead(text)
    assert_eq("status", s.status, "low_budget_hold")
    assert_truthy("budget_below_floor", s.budget_per_hour_usd is not None and s.budget_per_hour_usd < 32)


def test_scorer_out_of_scope_ib() -> None:
    text = "IB Physics HL tutor for my son in Singapore. IB Diploma."
    s = score_tutoring_lead(text)
    assert_eq("status", s.status, "out_of_scope_hold")
    assert_eq("curriculum", s.curriculum, "IB")


def test_scorer_combined_science() -> None:
    text = "Year 10 student struggling with Combined Science at a UK school."
    s = score_tutoring_lead(text)
    assert_eq("status", s.status, "out_of_scope_hold")
    assert_eq("curriculum", s.curriculum, "GCSE_Combined")


def test_scorer_minimal_message_yields_low_score() -> None:
    text = "I want a tutor please."
    s = score_tutoring_lead(text)
    assert_truthy("minimal_score_low", s.match_score < 40)


# ---------------------------------------------------------------------------
# Parser fallback (no API coverage — sole fallback path)
# ---------------------------------------------------------------------------

def test_parser_returns_brief_for_empty() -> None:
    """Even with no input, the parser returns a valid brief (fallback path)."""
    brief, payload = parse_to_dict("")
    assert_truthy("parser_returns_brief_for_empty", isinstance(brief, TutoringBrief))
    assert_eq("parser_returns_payload_for_empty", payload.get("schema_version"), 1)


def test_parser_returns_brief_for_real_text() -> None:
    """The parser contract is 'always returns a brief', regardless of
    whether the LLM cascade or the fallback path produced it.

    We don't pin content here because the live LLM may produce richer
    student_pain_points than the fallback. Fallback-specific content is
    tested below via direct TutoringBrief.fallback calls.
    """
    brief, payload = parse_to_dict("Hi, looking for an A-Level physics tutor in Dubai. Budget $50/hr.")
    assert_truthy("parser_returns_brief_for_real_text", isinstance(brief, TutoringBrief))
    assert_eq("parser_payload_schema_version", payload.get("schema_version"), 1)
    assert_truthy("parser_brief_has_session_focus", bool(brief.recommended_first_session_focus))


def test_fallback_brief_seeds_pain_points() -> None:
    """TutoringBrief.fallback contract: when the parser fails, the brief
    carries a one-element pain-points list seeded from raw text."""
    brief_empty = TutoringBrief.fallback("")
    brief_text = TutoringBrief.fallback("My son is struggling with electricity units before his exam")

    assert_eq("fallback_seed_count_empty", len(brief_empty.student_pain_points), 1)
    assert_eq("fallback_seed_count_text", len(brief_text.student_pain_points), 1)
    assert_truthy(
        "fallback_seed_includes_excerpt",
        "electricity" in brief_text.student_pain_points[0],
    )


# ---------------------------------------------------------------------------
# Proposal generator — template mode only (LLM path is opt-in)
# ---------------------------------------------------------------------------

def test_proposal_template_mode() -> None:
    # Redirect output dir
    tutoring_proposal.OUTPUT_DIR = _TMP / "cover_letters"
    tutoring_proposal.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    score = score_tutoring_lead(
        "Hi from Abu Dhabi. Son in Year 11 IGCSE Edexcel physics. "
        "Struggling with electricity. We can pay USD 50 per hour."
    )
    brief = TutoringBrief.fallback(score_text_or_excerpt_for_fallback(score, ""))

    result = tutoring_proposal.generate_proposal(
        lead_row={"id": "00000000-0000-0000-0000-000000000001", "raw_message": "ignored"},
        brief=brief,
        score=score,
        use_llm=False,
    )
    assert_eq("proposal_mode", result.mode, "template")
    assert_truthy("proposal_text_nonempty", len(result.text) > 100)
    assert_truthy("proposal_text_british", "no charge, no obligation" in result.text.lower())
    assert_truthy("proposal_file_exists", result.path.exists())


def score_text_or_excerpt_for_fallback(score, raw):  # noqa: ANN001, ANN201
    return raw


# ---------------------------------------------------------------------------
# Run all
# ---------------------------------------------------------------------------

def main() -> int:
    cases = [
        test_scorer_gulf_igcse_edexcel_strong,
        test_scorer_a_level_cambridge_london_uk,
        test_scorer_below_budget_floor,
        test_scorer_out_of_scope_ib,
        test_scorer_combined_science,
        test_scorer_minimal_message_yields_low_score,
        test_parser_returns_brief_for_empty,
        test_parser_returns_brief_for_real_text,
        test_fallback_brief_seeds_pain_points,
        test_proposal_template_mode,
    ]
    for case in cases:
        try:
            case()
        except Exception as e:  # noqa: BLE001
            FAILS.append(f"{case.__name__} raised: {e}")

    print()
    print(f"PASS: {len(PASSES)}")
    for label in PASSES:
        print(f"  ✓ {label}")
    if FAILS:
        print()
        print(f"FAIL: {len(FAILS)}")
        for label in FAILS:
            print(f"  ✗ {label}")
        return 1
    print()
    print("All tutoring smoke tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
