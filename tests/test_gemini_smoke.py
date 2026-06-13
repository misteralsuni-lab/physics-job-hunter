#!/usr/bin/env python3
"""
Gemini Smoke Test — run after updating GEMINI_API_KEY in .env

Validates provider resolution, round-trip JSON output, and score shape.
Exits 0 on success, 1 on failure.
"""

import os
import sys

# Ensure project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("gemini_smoke_test")

from src.scoring.llm_scorer import LLMScorer


def smoke_init() -> bool:
    """Test that LLMScorer initialises with at least one active provider."""
    scorer = LLMScorer()
    if not scorer._providers:
        log.error("❌ No active providers after validation")
        return False
    names = [p[0] for p in scorer._providers]
    log.info("✅ Active providers: %s", names)
    return True


def smoke_score() -> bool:
    """Test that a real scoring call returns the expected JSON shape."""
    scorer = LLMScorer()
    dummy_job = {
        "title": "Physics Teacher",
        "school": "Test School",
        "curriculum": "IB",
        "subject": "Physics",
        "country": "United Arab Emirates",
        "salary_range": "60,000 – 80,000 AED",
        "url": "https://example.com/job",
    }

    result = scorer.score(dummy_job)
    if result is None:
        log.error("❌ score() returned None")
        return False

    expected_keys = {"score", "reasoning", "visa_sponsorship", "housing_allowance", "curriculum_match"}
    missing = expected_keys - result.keys()
    if missing:
        log.error("❌ Missing keys in score result: %s", missing)
        return False

    score = result.get("score")
    if not isinstance(score, int) or not 0 <= score <= 100:
        log.error("❌ Invalid score value: %s (expected int 0-100)", score)
        return False

    log.info("✅ Score call succeeded — score=%d reasoning='%s'", score, result.get("reasoning", "")[:60])
    return True


def main():
    log.info("=== LLMScorer Smoke Test ===")
    ok = smoke_init() and smoke_score()
    if ok:
        log.info("✅ All smoke tests passed")
        sys.exit(0)
    else:
        log.error("🛑 Smoke test failed — check API keys and network access")
        sys.exit(1)


if __name__ == "__main__":
    main()
