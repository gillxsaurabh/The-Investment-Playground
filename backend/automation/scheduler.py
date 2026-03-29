"""APScheduler setup for the weekly Monday automation.

Schedules run_weekly_automation() to fire every Monday at 10:00 AM IST.
Running at 10 AM (not 9 AM open) avoids the volatile opening auction period
and gives price action time to settle into the day's range.
The scheduler instance is module-level so routes can query next_run_time.
"""

import logging

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from automation.weekly_trader import run_weekly_automation
from scripts.backup_db import run_backup

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

# Module-level scheduler instance (set by start_scheduler)
_scheduler: BackgroundScheduler | None = None


def start_scheduler() -> BackgroundScheduler:
    """Create and start the background scheduler. Call once at app startup."""
    global _scheduler

    scheduler = BackgroundScheduler(timezone=IST)
    scheduler.add_job(
        func=run_weekly_automation,
        trigger=CronTrigger(day_of_week="mon", hour=10, minute=0, timezone=IST),
        id="weekly_automation",
        name="Monday 10AM Stock Discovery & Trading",
        replace_existing=True,
        misfire_grace_time=300,  # 5-minute grace window if server briefly restarts
        kwargs={"dry_run": False},
    )

    # Daily DB backup at 11:30 PM IST
    scheduler.add_job(
        func=run_backup,
        trigger=CronTrigger(hour=23, minute=30, timezone=IST),
        id="daily_backup",
        name="Daily SQLite Backup 11:30PM IST",
        replace_existing=True,
        misfire_grace_time=600,
    )

    scheduler.start()
    _scheduler = scheduler

    next_run = scheduler.get_job("weekly_automation").next_run_time
    logger.info(f"[Scheduler] Started — next weekly automation run: {next_run}")
    return scheduler


def get_next_run_time() -> str | None:
    """Return ISO string of the next scheduled run time, or None if not scheduled."""
    if _scheduler is None:
        return None
    job = _scheduler.get_job("weekly_automation")
    if job and job.next_run_time:
        return job.next_run_time.isoformat()
    return None


def is_running() -> bool:
    """Return True if the scheduler is active."""
    return _scheduler is not None and _scheduler.running


def shutdown_scheduler() -> None:
    """Gracefully stop the scheduler (called on app teardown)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped")
    _scheduler = None
