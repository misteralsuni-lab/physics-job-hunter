"""Telegram inbound bot for the tutoring branch.

Long-polling bot. Same token as the outbound Telegram notify bot — this
is a *single* bot, but with both directions wired.

Scope
-----
1. Receive parent messages forwarded by the user and insert them as
   ``tutoring_leads`` rows. The pre-existing systemd-driven tick parses,
   scores, and (when in scope) auto-proposals within ~15 minutes.

2. Accept simple reply-to-notify commands to flip the lead status:
       /paid     — mark most recent proposal as paid_first_session
       /reply    — mark most recent proposal as reply_received
       /lost     — mark most recent proposal as lost
       /paid <uuid>  /reply <uuid>  /lost <uuid>  — explicit addressing
       /help     — show command list

Authorisation
-------------
The bot only acts on messages from the chat id stored in
``settings.telegram_chat_id``. Anything from any other chat is silently
dropped. This is the primary security boundary — the same value is
already used by the outbound notify, so it must remain the user's own
chat.

Persistence
-----------
``last_proposal_per_chat`` keeps the most recent lead id proposed to each
authorised chat in process memory; cleared every process start. Anything
more durable (cross-restart) belongs in a future SQLite cache, but for
v1 the user can always reply with the full UUID.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from pathlib import Path

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx

from src.config import settings
from src.storage.tutoring_leads import TutoringLeadStorage

log = logging.getLogger("tutoring.bot")

API_BASE = "https://api.telegram.org/bot{token}"


# ---------------------------------------------------------------------------
#  In-memory state — keyed by chat id
# ---------------------------------------------------------------------------

_last_proposal_per_chat: dict[int, str] = {}


# ---------------------------------------------------------------------------
#  Refresh — query Supabase to learn which lead is the most-recent proposal.
#  This is how /paid (bare) targets the right lead without forcing the user
#  to copy UUIDs by hand.
# ---------------------------------------------------------------------------

def refresh_last_proposals(storage: TutoringLeadStorage) -> None:
    """Walk the last 30 leads and pin the most-recent ``proposal_sent`` row
    to its chat id. Called on every poll cycle so a hot-restart doesn't
    strip the mapping.
    """
    try:
        rows = storage.list_leads(statuses=["proposal_sent"], limit=30)
    except Exception as e:
        log.warning("refresh_last_proposals failed: %s", e)
        return
    if not rows:
        return
    rows.sort(key=lambda r: r.get("status_changed_at", ""), reverse=True)
    for chat_id in _authorised_chat_ids():
        most_recent = rows[0].get("id")
        if most_recent:
            _last_proposal_per_chat[chat_id] = most_recent


# ---------------------------------------------------------------------------
#  Outbound helpers (mirror src/notify/telegram.py but slimmed)
# ---------------------------------------------------------------------------

def _send(chat_id: int | str, text: str) -> bool:
    if not settings.telegram_bot_token:
        return False
    try:
        r = httpx.post(
            f"{API_BASE.format(token=settings.telegram_bot_token)}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=10.0,
        )
        if not r.is_success:
            log.warning("sendMessage non-2xx: %s", r.text[:200])
            return False
        return True
    except Exception as e:
        log.warning("sendMessage failed: %s", e)
        return False


# ---------------------------------------------------------------------------
#  Command parsing
# ---------------------------------------------------------------------------

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.I,
)


def _extract_uuid(text: str) -> str | None:
    m = _UUID_RE.search(text)
    return m.group(0).lower() if m else None


def _read_recent(chat_id: int) -> httpx.Response | None:
    """Long-poll for new updates. Returns ``None`` on transient failure."""
    if not settings.telegram_bot_token:
        return None
    try:
        params = {
            "timeout": 25,         # long-poll for 25s
            "allowed_updates": '["message"]',
        }
        # offset is set by caller via last_update_id
        return httpx.get(
            f"{API_BASE.format(token=settings.telegram_bot_token)}/getUpdates",
            params=params,
            timeout=35.0,
        )
    except httpx.TimeoutException:
        # Long-poll timeout is normal — no new messages.
        return None
    except Exception as e:
        log.warning("getUpdates failed: %s", e)
        return None


# ---------------------------------------------------------------------------
#  Command handlers
# ---------------------------------------------------------------------------

_HELP_TEXT = """*Tutoring bot* — receives parent messages and flips lead status.

*Intake:* Just forward or send a parent message. The system parses, scores, and (when in scope) drafts a proposal within ~15 minutes.

*Commands:*
- `/paid` — mark your most recent proposal as *paid first session*
- `/reply` — mark as *reply received*
- `/lost` — mark as *lost*
- `/paid <uuid>` (or `/reply`, `/lost`) — explicit lead addressing
- `/status` — show last-proposed lead id for this chat
- `/help` — show this message

Anything from any chat other than the configured inbox is ignored."""


def _handle_command(
    cmd_text: str,
    chat_id: int,
    storage: TutoringLeadStorage,
) -> bool:
    """Return True if the message was a command we handled (incl. help)."""
    stripped = cmd_text.strip()
    if not stripped.startswith("/"):
        return False

    parts = stripped.split()
    head = parts[0].lower().split("@", 1)[0]   # strip optional @botname

    if head == "/help" or head == "/start":
        _send(chat_id, _HELP_TEXT)
        return True

    if head == "/status":
        recent = _last_proposal_per_chat.get(chat_id, "(none)")
        _send(chat_id, f"Last proposed lead: `{recent}`")
        return True

    if head in ("/paid", "/reply", "/lost"):
        target = {
            "/paid": "paid_first_session",
            "/reply": "reply_received",
            "/lost": "lost",
        }[head]

        # Resolve lead id: explicit UUID beats last-seen
        explicit = _extract_uuid(stripped)
        lead_id = explicit or _last_proposal_per_chat.get(chat_id)
        if not lead_id:
            _send(chat_id, f"No lead id on file — pass `{head} <uuid>` instead.")
            return True

        try:
            storage.update_status(lead_id, target)
        except Exception as e:
            log.warning("update_status failed for lead=%s: %s", lead_id, e)
            _send(chat_id, f"Could not flip status: {e}")
            return True

        _send(chat_id, f"Lead `{lead_id[:8]}` → *{target.replace('_', ' ')}*")
        return True

    # Unknown command — quietly ignore
    return False


def _handle_intake(
    raw_text: str,
    chat_id: int,
    storage: TutoringLeadStorage,
) -> None:
    """Insert a forwarded parent message as a ``tutoring_leads`` row."""
    if not raw_text or not raw_text.strip():
        return
    if len(raw_text) > 8000:
        _send(chat_id, "That message exceeds 8000 characters — please truncate before forwarding.")
        return

    try:
        lead = storage.insert_lead({
            "source": "telegram",
            "raw_message": raw_text.strip(),
        })
    except Exception as e:
        log.warning("insert_lead failed: %s", e)
        _send(chat_id, f"Could not record lead: {e}")
        return

    lead_id = lead.get("id", "?")[:8]
    _send(
        chat_id,
        f"Lead `{lead_id}` queued. Parser runs every "
        f"{int(settings.tutoring_parse_interval_min)} minutes. "
        f"Reply `/status` to see its id later.",
    )


# ---------------------------------------------------------------------------
#  Update dispatch
# ---------------------------------------------------------------------------

def _process_update(
    update: dict,
    storage: TutoringLeadStorage,
    authorised_chat_ids: set[int],
) -> None:
    message = update.get("message") or update.get("edited_message")
    if not message:
        return

    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return

    if chat_id not in authorised_chat_ids:
        # Silently ignore — never ack to unauthorised senders (avoids leaking presence)
        return

    text = message.get("text") or message.get("caption") or ""
    if not text.strip():
        return

    # Commands first
    if _handle_command(text, chat_id, storage):
        return

    # Plain text → intake
    _handle_intake(text, chat_id, storage)


# ---------------------------------------------------------------------------
#  Main loop
# ---------------------------------------------------------------------------

def _authorised_chat_ids() -> set[int]:
    """Parse authorised chat id(s) from settings. Skip if unset."""
    if not settings.telegram_chat_id:
        return set()
    raw = settings.telegram_chat_id
    out: set[int] = set()
    for token in str(raw).split(","):
        token = token.strip()
        if not token:
            continue
        try:
            out.add(int(token))
        except ValueError:
            log.warning("Could not parse telegram_chat_id token: %r", token)
    return out


def run(poll_interval: float = 2.0) -> None:
    """Long-polling loop. Runs forever; Ctrl-C to exit."""
    if not settings.telegram_bot_token:
        log.error("TELEGRAM_BOT_TOKEN is not set; bot disabled.")
        return

    authorised = _authorised_chat_ids()
    if not authorised:
        log.error(
            "TELEGRAM_CHAT_ID is not set; bot would silently drop everything. "
            "Set it in .env to enable.",
        )
        return

    storage = TutoringLeadStorage()
    log.info(
        "Tutoring bot started. Authorised chats=%s, polling every %.1fs.",
        sorted(authorised), poll_interval,
    )

    refresh_last_proposals(storage)

    offset: int | None = None
    backoff = poll_interval
    polls_since_refresh = 0
    while True:
        try:
            params: dict = {
                "timeout": 25,
                "allowed_updates": '["message"]',
            }
            if offset is not None:
                params["offset"] = offset + 1

            resp = httpx.get(
                f"{API_BASE.format(token=settings.telegram_bot_token)}/getUpdates",
                params=params,
                timeout=35.0,
            )
            if resp.status_code == 409:
                log.warning("getUpdates 409 conflict — another bot instance may be running. Backing off 30s.")
                time.sleep(30.0)
                continue

            resp.raise_for_status()
            backoff = poll_interval  # reset backoff after success

            payload = resp.json()
            if not payload.get("ok"):
                log.warning("Telegram API error: %s", payload)
                time.sleep(backoff)
                continue

            for update in payload.get("result", []):
                offset = update.get("update_id", offset)
                try:
                    _process_update(update, storage, authorised)
                except Exception:
                    log.exception("update processing crashed; continuing")

            # Refresh the last-proposal mapping every ~12 polls (≈ 30 s).
            polls_since_refresh += 1
            if polls_since_refresh >= 12:
                refresh_last_proposals(storage)
                polls_since_refresh = 0

        except httpx.TimeoutException:
            # Long-poll elapsed with no updates — normal.
            continue
        except Exception as e:
            log.warning("polling crashed; backing off: %s", e)
            time.sleep(backoff)
            backoff = min(backoff * 2, 60.0)


def _entry() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    p = argparse.ArgumentParser()
    p.add_argument("--poll", type=float, default=2.0, help="seconds between long-polls when idle")
    args = p.parse_args()
    try:
        run(poll_interval=args.poll)
    except KeyboardInterrupt:
        log.info("Bot stopped.")


if __name__ == "__main__":
    _entry()
