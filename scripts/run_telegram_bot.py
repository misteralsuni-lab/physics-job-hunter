"""Entrypoint for the tutoring Telegram bot (inbound).

Started via ``scripts/run_telegram_bot.sh`` which is invoked by
``physics-job-hunter-bot.service``. Mirrors the pattern of
``scripts/run_scheduler.py``.
"""
import sys

sys.path.insert(0, str(__file__).rsplit("/", 2)[0])

from src.notify.telegram_inbound import _entry  # noqa: E402

if __name__ == "__main__":
    _entry()
