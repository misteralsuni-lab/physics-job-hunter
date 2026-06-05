import sys
from pathlib import Path
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from typing import Any
import httpx

from src.config import settings


def send_telegram_alert(jobs: list[dict[str, Any]]) -> int:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return 0

    sent = 0
    for job in jobs:
        score = job.get("score", 0)
        title = job.get("title", "Unknown")
        school = job.get("school", "Unknown")
        country = job.get("country", "Unknown")
        url = job.get("url", "")
        salary = job.get("salary_range", "")
        curriculum = ", ".join(job.get("curriculum", []))

        message = (
            f"🎯 *{title}*\n"
            f"🏫 {school}\n"
            f"🌍 {country}\n"
            f"📚 {curriculum}\n"
            f"💰 {salary}\n"
            f"⭐ Score: {score}/100\n"
            f"[Apply]({url})"
        )

        try:
            httpx.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": message,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            sent += 1
        except Exception:
            pass

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
