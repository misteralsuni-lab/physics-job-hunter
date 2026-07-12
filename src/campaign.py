from __future__ import annotations

import json
from pathlib import Path

from src.config import settings

_CAMPAIGN_DIR = Path(__file__).resolve().parent.parent / "data"


def load_campaign() -> dict | None:
    """Return campaign config dict, or None when no campaign is active."""
    name = (settings.campaign or "").strip()
    if not name:
        return None
    path = _CAMPAIGN_DIR / f"campaign_{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
