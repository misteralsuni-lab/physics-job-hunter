import logging
import re
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from typing import Any

import httpx

from src.config import settings

log = logging.getLogger("job-hunter")

API_BASE = "https://api.telegram.org/bot{token}"


# HTML entity escaping for Telegram's parse_mode=HTML.
# Escapes &, <, >, " so values are safe in both element text and inside
# attributes (e.g. the url interpolated into <a href="...">).
_HTMLESC_RE = re.compile(r'[&<>"]')


def _esc(text: str) -> str:
    """Escape &, <, >, " for safe interpolation into Telegram HTML."""
    return _HTMLESC_RE.sub(
        lambda m: {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[m.group()],
        text,
    )


def _send_message(chat_id: str, text: str) -> bool:
    """Send an HTML text message. Returns True on success."""
    try:
        resp = httpx.post(
            f"{API_BASE.format(token=settings.telegram_bot_token)}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        log.warning("Telegram sendMessage failed: %s", exc)
        return False


def _send_document(chat_id: str, file_path: str, caption: str) -> bool:
    """Send a local file as a document with an optional caption. Returns True on success."""
    path = Path(file_path)
    if not path.is_file():
        log.warning("Cover letter file not found: %s", file_path)
        return False

    try:
        resp = httpx.post(
            f"{API_BASE.format(token=settings.telegram_bot_token)}/sendDocument",
            data={
                "chat_id": chat_id,
                "caption": caption,
                "parse_mode": "HTML",
            },
            files={"document": (path.name, path.read_bytes(), "text/markdown")},
            timeout=30,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        log.warning("Telegram sendDocument failed: %s", exc)
        return False


def send_telegram_alert(
    jobs: list[dict[str, Any]],
    cover_letter_paths: dict[str, str] | None = None,
) -> int:
    """Send Telegram alerts for high-scoring jobs.

    Parameters
    ----------
    jobs:
        List of job dicts with at least ``title``, ``school``, ``url``, etc.
    cover_letter_paths:
        Mapping of job URL → absolute path to a generated cover letter file.
        When present, the file is sent as a document attachment after the
        alert message.

    Returns
    -------
    Number of alerts successfully sent.
    """
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return 0

    chat_id = settings.telegram_chat_id
    paths = cover_letter_paths or {}
    sent = 0

    for job in jobs:
        score = job.get("score", 0)
        title = job.get("title", "Unknown")
        school = job.get("school", "Unknown")
        country = job.get("country", "Unknown")
        url = job.get("url", "")
        salary = job.get("salary_range", "")
        curriculum = ", ".join(job.get("curriculum", []))

        has_cover = url in paths
        reasoning = job.get("scoring_reasoning", "") or job.get("reasoning", "")
        message = (
            f"🎯 <b>{_esc(title)}</b>\n"
            f"🏫 {_esc(school)}\n"
            f"🌍 {_esc(country)}\n"
            f"📚 {_esc(curriculum)}\n"
            f"💰 {_esc(salary)}\n"
            f"⭐ Score: {score}/100\n"
            + (f"💡 {_esc(reasoning)}\n" if reasoning else "")
            + f'<a href="{_esc(url)}">Apply</a>'
        )

        if has_cover:
            message += "\n📄 <i>Cover letter attached below.</i>"

        ok = _send_message(chat_id, message)
        if ok:
            sent += 1

        # Send the cover letter document if one exists
        if has_cover:
            caption = (
                f"📄 Cover Letter — {_esc(title)}\n"
                f"🏫 {_esc(school)}  ·  ⭐ {score}/100"
                + (f"\n💡 {_esc(reasoning)}" if reasoning else "")
            )
            _send_document(chat_id, paths[url], caption)

    return sent


def send_campaign_digest(
    prospects: list[dict[str, Any]],
    email_paths: dict[str, str] | None = None,
) -> int:
    """Send a Telegram digest for the campaign's top-10 prospects.

    Sends one summary message listing each prospect (school, location, score,
    tier, Category-F flag) followed by the generated outreach-email documents
    as attachments. Returns the number of messages sent.

    Parameters
    ----------
    prospects:
        Ordered list of top prospects (dicts with ``school_name``,
        ``location``, ``campaign_score``, ``tier``, ``category_f``,
        ``normalized_key`` / ``outreach_email_path``).
    email_paths:
        Mapping of ``normalized_key`` → absolute path of the generated email
        file. When present, each file is attached after the summary.
    """
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return 0

    chat_id = settings.telegram_chat_id
    email_paths = email_paths or {}
    sent = 0

    lines = ["📋 <b>Campaign Prospect Digest — Top 10</b>\n"]
    for i, p in enumerate(prospects, 1):
        name = p.get("school_name", "Unknown")
        loc = p.get("location", "")
        score = p.get("campaign_score", 0)
        tier = p.get("tier", "")
        catf = " 🔥CatF" if p.get("category_f") else ""
        lines.append(
            f"{i}. <b>{_esc(name)}</b> — {_esc(loc)} · {score}/100 · {_esc(tier)}{catf}"
        )

    if _send_message(chat_id, "\n".join(lines)):
        sent += 1

    for p in prospects:
        key = p.get("normalized_key") or p.get("school_name", "")
        path = email_paths.get(key) or p.get("outreach_email_path")
        if path:
            _send_document(chat_id, path, f"📧 {_esc(p.get('school_name', ''))}")

    return sent


if __name__ == "__main__":
    test_job = {
        "title": "Physics Teacher",
        "school": "Brighton College Dubai",
        "country": "Dubai",
        "salary_range": "AED 15,000 - 20,000",
        "curriculum": ["IGCSE", "A-Level"],
        "score": 85,
        "url": "https://www.tes.com/jobs/vacancy/test-123",
    }
    n = send_telegram_alert([test_job])
    print(f"Sent {n} message(s)")

    test_paths = {test_job["url"]: "C:\\path\\to\\cover_letter.md"}
    n2 = send_telegram_alert([test_job], cover_letter_paths=test_paths)
    print(f"Sent {n2} message(s) with cover letter")
