import logging
import traceback

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger  # type: ignore[import-not-found]  # depends on installed apscheduler version

from src.config import settings
from src.main import run_pipeline
from src.scheduler.tutoring_run import run_once as tutoring_run_once

log = logging.getLogger("scheduler")


def _wrapped_run() -> None:
    """Wrap run_pipeline so a single crash doesn't kill the scheduler."""
    try:
        run_pipeline()
    except Exception:
        log.error("Pipeline crashed:\n%s", traceback.format_exc())


def _wrapped_tutoring_tick() -> None:
    """Wrap the tutoring tick so a single crash doesn't kill the scheduler."""
    try:
        summary = tutoring_run_once()
        log.info("tutoring tick summary: %s", summary)
    except Exception:
        log.error("Tutoring tick crashed:\n%s", traceback.format_exc())


def start() -> None:
    scheduler = BlockingScheduler()
    times = [t.strip() for t in settings.schedule_time.split(",")]
    for i, time in enumerate(times):
        hour, minute = time.split(":")
        scheduler.add_job(
            _wrapped_run,
            CronTrigger(hour=int(hour), minute=int(minute)),
            id=f"daily_job_hunt_{i}",
            name=f"Physics Job Pipeline ({time})",
            replace_existing=True,
        )
    log.info("Scheduler set for %s daily", ", ".join(times))

    interval_min = max(1, int(settings.tutoring_parse_interval_min))
    scheduler.add_job(
        _wrapped_tutoring_tick,
        IntervalTrigger(minutes=interval_min),
        id="tutoring_tick",
        name=f"Tutoring tick (every {interval_min}m)",
        replace_existing=True,
        next_run_time=None,   # do not fire at scheduler startup; wait one full interval
    )
    log.info("Tutoring tick registered for every %s minutes", interval_min)

    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("Shutting down scheduler")
        scheduler.shutdown()
