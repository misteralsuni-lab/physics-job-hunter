from datetime import date
from typing import Any
import logging
import smtplib
from email.mime.text import MIMEText

import httpx

from src.config import settings

log = logging.getLogger("job-hunter")


def _build_digest_html(jobs: list[dict[str, Any]]) -> str:
    rows = "".join(
        f"""
        <tr>
            <td><a href="{j.get("url", "#")}">{j.get("title", "Unknown")}</a></td>
            <td>{j.get("school", "")}</td>
            <td>{j.get("country", "")}</td>
            <td>{", ".join(j.get("curriculum", []))}</td>
            <td>{j.get("salary_range", "")}</td>
            <td><strong>{j.get("score", "N/A")}</strong></td>
            <td><em>{j.get("scoring_reasoning", "") or j.get("reasoning", "") or ""}</em></td>
        </tr>
        """
        for j in jobs
    )

    return f"""
    <html>
    <body style="font-family: Arial; background: #111; color: #eee; padding: 20px;">
        <h2>📋 Physics Job Digest — {date.today()}</h2>
        <table border="1" cellpadding="8" style="border-collapse: collapse; width: 100%;">
            <thead style="background: #333;">
                <tr>
                    <th>Title</th><th>School</th><th>Country</th><th>Curriculum</th><th>Salary</th><th>Score</th><th>Reasoning</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
    </body>
    </html>
    """


def send_email_digest(jobs: list[dict[str, Any]]) -> bool:
    if not jobs:
        return False

    html = _build_digest_html(jobs)
    subject = f"Physics Job Digest — {date.today()} ({len(jobs)} new)"

    if settings.email_provider == "resend":
        return _send_via_resend(subject, html)
    elif settings.email_provider == "smtp":
        return _send_via_smtp(subject, html)
    return False


def _send_via_resend(subject: str, html: str) -> bool:
    if not settings.resend_api_key or not settings.email_to:
        return False
    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={
                "from": settings.email_from or "job-hunter@yourdomain.com",
                "to": [settings.email_to],
                "subject": subject,
                "html": html,
            },
            timeout=15,
        )
        if resp.is_success:
            return True
        log.warning("Resend send failed: HTTP %s — %s", resp.status_code, resp.text)
        return False
    except Exception as e:
        log.warning("Resend send raised: %s", e)
        return False


def _send_via_smtp(subject: str, html: str) -> bool:
    if not all([settings.smtp_host, settings.smtp_user, settings.smtp_password, settings.email_to]):
        return False
    try:
        msg = MIMEText(html, "html")
        msg["Subject"] = subject
        msg["From"] = settings.email_from or settings.smtp_user
        msg["To"] = settings.email_to

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
        return True
    except Exception:
        return False
