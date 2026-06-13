import logging
import sys
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from typing import Any

import httpx

from src.config import settings

log = logging.getLogger("job-hunter")

API_BASE = "https://api.telegram.org/bot{token}"


def _send_message(chat_id: str, text: str) -> bool:
    """Send a Markdown text message. Returns True on success."""
    try:
        resp = httpx.post(
            f"{API_BASE.format(token=settings.telegram_bot_token)}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        log.debug("Telegram sendMessage failed: %s", exc)
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
                "parse_mode": "Markdown",
            },
            files={"document": (path.name, path.read_bytes(), "text/markdown")},
            timeout=30,
        )
        resp.raise_for_status()
        return True
    except Exception as exc:
        log.debug("Telegram sendDocument failed: %s", exc)
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
            f"🎯 *{title}*\n"
            f"🏫 {school}\n"
            f"🌍 {country}\n"
            f"📚 {curriculum}\n"
            f"💰 {salary}\n"
            f"⭐ Score: {score}/100\n"
            + (f"💡 {reasoning}\n" if reasoning else "")
            + f"[Apply]({url})"
        )

        if has_cover:
            message += "\n📄 _Cover letter attached below._"

        ok = _send_message(chat_id, message)
        if ok:
            sent += 1

        # Send the cover letter document if one exists
        if has_cover:
            caption = (
                f"📄 Cover Letter — {title}\n"
                f"🏫 {school}  ·  ⭐ {score}/100"
                + (f"\n💡 {reasoning}" if reasoning else "")
            )
            _send_document(chat_id, paths[url], caption)

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

    # Test with a cover letter attachment
    test_paths = {test_job["url"]: "C:\\path\\to\\cover_letter.md"}
    n2 = send_telegram_alert([test_job], cover_letter_paths=test_paths)
    print(f"Sent {n2} message(s) with cover letter")
