"""APScheduler setup for the weekly Monday automation.

Schedules run_weekly_automation() to fire every Monday at 10:00 AM IST.
Running at 10 AM (not 9 AM open) avoids the volatile opening auction period
and gives price action time to settle into the day's range.
The scheduler instance is module-level so routes can query next_run_time.
"""

import logging
from datetime import date

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from automation.weekly_trader import run_weekly_automation
from automation.nse_holidays import is_trading_day
from scripts.backup_db import run_backup
from config import STATE_DIR

logger = logging.getLogger(__name__)

IST = pytz.timezone("Asia/Kolkata")

# Lock files — one per scheduled job so they don't block each other
_AUTOMATION_LOCK = STATE_DIR / ".weekly_automation.lock"
_BACKUP_LOCK = STATE_DIR / ".daily_backup.lock"
_RETROSPECTIVE_LOCK = STATE_DIR / ".monthly_retrospective.lock"

# Module-level scheduler instance (set by start_scheduler)
_scheduler: BackgroundScheduler | None = None


def _guarded_weekly_automation(**kwargs) -> None:
    """Run weekly automation only on trading days and only if no other instance is running.

    Holiday check is intentionally lightweight (no heavy imports) so it runs before
    acquiring the lock. The lock ensures only one Gunicorn worker / server instance
    executes the job when multiple processes share the same STATE_DIR.
    """
    try:
        from filelock import FileLock, Timeout
    except ImportError:
        logger.warning("[Scheduler] filelock not installed — running without distributed lock")
        run_weekly_automation(**kwargs)
        return

    today = date.today()
    if not is_trading_day(today):
        logger.info("[Scheduler] %s is not a trading day — skipping weekly automation", today)
        return

    lock = FileLock(str(_AUTOMATION_LOCK), timeout=0)
    try:
        with lock:
            logger.info("[Scheduler] Lock acquired — running weekly automation")
            run_weekly_automation(**kwargs)
    except Timeout:
        logger.info("[Scheduler] Weekly automation lock held by another instance — skipping this run")


def _guarded_backup() -> None:
    """Run daily backup only if no other instance is currently running the backup."""
    try:
        from filelock import FileLock, Timeout
    except ImportError:
        run_backup()
        return

    lock = FileLock(str(_BACKUP_LOCK), timeout=0)
    try:
        with lock:
            run_backup()
    except Timeout:
        logger.info("[Scheduler] Daily backup lock held by another instance — skipping")


def _guarded_daily_close() -> None:
    """Write a daily_close account snapshot for all active simulator users."""
    try:
        from services.db import get_open_trades, insert_account_snapshot, get_simulator_account
        from datetime import datetime as _dt
        now_str = _dt.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        # Get distinct user_ids with open simulator trades
        open_trades = get_open_trades(trading_mode="simulator")
        seen_users: set = set()
        for trade in open_trades:
            uid = trade.get("user_id")
            if uid and uid not in seen_users:
                seen_users.add(uid)
                acct = get_simulator_account(uid)
                if acct:
                    open_cost = sum(
                        t.get("total_cost", 0) for t in open_trades
                        if t.get("user_id") == uid
                    )
                    insert_account_snapshot({
                        "snapshot_time": now_str,
                        "event_type": "daily_close",
                        "trade_id": None,
                        "initial_capital": acct.get("initial_capital", 0),
                        "current_balance": acct.get("current_balance", 0),
                        "total_realized_pnl": acct.get("total_pnl", 0),
                        "open_position_cost": open_cost,
                        "unrealized_pnl": 0.0,
                        "net_equity": acct.get("current_balance", 0) + open_cost,
                        "total_trades": 0,
                        "winning_trades": 0,
                        "losing_trades": 0,
                    })
        logger.info("[Scheduler] Daily close snapshot written for %d users", len(seen_users))
    except Exception as e:
        logger.warning("[Scheduler] Daily close snapshot failed: %s", e)


def _guarded_monthly_retrospective() -> None:
    """Run monthly retrospective pipeline for simulator mode (locked, single-instance)."""
    try:
        from filelock import FileLock, Timeout
    except ImportError:
        _run_monthly_retrospective()
        return

    lock = FileLock(str(_RETROSPECTIVE_LOCK), timeout=0)
    try:
        with lock:
            logger.info("[Scheduler] Lock acquired — running monthly retrospective")
            _run_monthly_retrospective()
    except Timeout:
        logger.info("[Scheduler] Monthly retrospective lock held by another instance — skipping")


def _run_monthly_retrospective() -> None:
    try:
        from agents.retrospective.pipeline import run_retrospective
        logger.info("[Scheduler] Starting monthly retrospective (simulator)")
        run_retrospective(trading_mode="simulator", lookback_days=90, triggered_by="monthly_cron")
        logger.info("[Scheduler] Monthly retrospective complete")
    except Exception as e:
        logger.error("[Scheduler] Monthly retrospective failed: %s", e, exc_info=True)


def start_scheduler() -> BackgroundScheduler:
    """Create and start the background scheduler. Call once at app startup."""
    global _scheduler

    scheduler = BackgroundScheduler(timezone=IST)
    scheduler.add_job(
        func=_guarded_weekly_automation,
        trigger=CronTrigger(day_of_week="mon", hour=10, minute=0, timezone=IST),
        id="weekly_automation",
        name="Monday 10AM Stock Discovery & Trading",
        replace_existing=True,
        misfire_grace_time=300,  # 5-minute grace window if server briefly restarts
        kwargs={"dry_run": False},
    )

    # Daily DB backup at 11:30 PM IST
    scheduler.add_job(
        func=_guarded_backup,
        trigger=CronTrigger(hour=23, minute=30, timezone=IST),
        id="daily_backup",
        name="Daily SQLite Backup 11:30PM IST",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Daily close snapshot at 11:55 PM IST
    scheduler.add_job(
        func=_guarded_daily_close,
        trigger=CronTrigger(hour=23, minute=55, timezone=IST),
        id="daily_close_snapshot",
        name="Daily Close Account Snapshot 11:55PM IST",
        replace_existing=True,
        misfire_grace_time=300,
    )

    # Monthly retrospective on 1st of month at 9:00 AM IST
    scheduler.add_job(
        func=_guarded_monthly_retrospective,
        trigger=CronTrigger(day=1, hour=9, minute=0, timezone=IST),
        id="monthly_retrospective",
        name="Monthly Retrospective Analysis 1st 9AM IST",
        replace_existing=True,
        misfire_grace_time=3600,
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
