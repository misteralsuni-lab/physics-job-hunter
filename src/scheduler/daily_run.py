import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import settings
from src.main import run_pipeline

log = logging.getLogger("scheduler")


def start():
    scheduler = BlockingScheduler()
    times = [t.strip() for t in settings.schedule_time.split(",")]
    for i, time in enumerate(times):
        hour, minute = time.split(":")
        scheduler.add_job(
            run_pipeline,
            CronTrigger(hour=int(hour), minute=int(minute)),
            id=f"daily_job_hunt_{i}",
            name=f"Physics Job Pipeline ({time})",
            replace_existing=True,
        )
    log.info("Scheduler set for %s daily", ", ".join(times))

    try:
        scheduler.start()
    except KeyboardInterrupt:
        log.info("Shutting down scheduler")
        scheduler.shutdown()
