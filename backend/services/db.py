"""SQLite persistence layer for CogniCap trade lifecycle tracking.

Uses PRAGMA foreign_keys = ON, WAL journal mode, and tuned PRAGMA settings
for production reliability. All connections are created via get_conn() which
sets required PRAGMAs on every new connection.

Financial writes (insert_trade, update_trade_exit, insert_account_snapshot)
capture exceptions to Sentry so silent data loss is surfaced in observability.
Non-financial writes (position_snapshots, SL updates) remain best-effort.
"""

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import sentry_sdk
    _SENTRY_AVAILABLE = True
except ImportError:
    _SENTRY_AVAILABLE = False

from config import DB_PATH

logger = logging.getLogger(__name__)


def _capture(exc: Exception) -> None:
    """Send exception to Sentry when available."""
    if _SENTRY_AVAILABLE:
        sentry_sdk.capture_exception(exc)


def get_conn() -> sqlite3.Connection:
    """Return a production-tuned WAL-mode SQLite connection."""
    conn = sqlite3.connect(str(DB_PATH), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")      # 3× faster writes; still crash-safe
    conn.execute("PRAGMA busy_timeout = 5000")        # retry for 5s on lock contention
    conn.execute("PRAGMA cache_size = -64000")        # 64 MB page cache
    conn.execute("PRAGMA journal_size_limit = 104857600")  # cap WAL at 100 MB
    return conn


@contextmanager
def managed_conn():
    """Context manager that opens, yields, commits, and closes a connection.

    Usage:
        with managed_conn() as conn:
            conn.execute(...)
    Exceptions propagate to the caller; the connection is always closed.
    """
    conn = get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


LATEST_SCHEMA_VERSION = 12


def init_db() -> None:
    """Run all pending migrations sequentially."""
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    conn = get_conn()
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]

        migrations = [
            (1,  "001_initial.sql"),
            (2,  "002_users.sql"),
            (3,  "003_add_user_id.sql"),
            (4,  "004_analysis_cache.sql"),
            (5,  "005_password_reset.sql"),
            (6,  "006_admin_and_tiers.sql"),
            (7,  "007_user_plan.sql"),
            (8,  "008_encrypt_broker_tokens.sql"),
            (9,  "009_llm_usage.sql"),
            (10, "010_schema_hardening.sql"),
            (11, "011_consolidate_state.sql"),
            (12, None),  # handled inline below — ALTER TABLE IF NOT EXISTS workaround
        ]

        for target_version, filename in migrations:
            if version >= target_version:
                continue

            if filename is None:
                # Migration 012: restore encrypted column dropped by old migration 010.
                # ALTER TABLE ADD COLUMN has no IF NOT EXISTS in SQLite, so check first.
                cols = [r[1] for r in conn.execute("PRAGMA table_info(admin_broker_tokens)").fetchall()]
                if "encrypted" not in cols:
                    conn.execute("ALTER TABLE admin_broker_tokens ADD COLUMN encrypted BOOLEAN NOT NULL DEFAULT FALSE")
                conn.execute("PRAGMA user_version = 12")
                conn.commit()
                logger.info("[DB] Migrated to schema version 12")
                version = 12
                continue

            migration_file = migrations_dir / filename
            if not migration_file.exists():
                logger.error("[DB] Migration file not found: %s", migration_file)
                return
            sql = migration_file.read_text()
            conn.executescript(sql)
            conn.commit()
            logger.info("[DB] Migrated to schema version %d", target_version)

        final_version = conn.execute("PRAGMA user_version").fetchone()[0]
        if final_version >= LATEST_SCHEMA_VERSION:
            logger.debug("[DB] Schema at version %d", final_version)
    except Exception as e:
        logger.error("[DB] Schema initialization failed: %s", e, exc_info=True)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Trade CRUD
# ---------------------------------------------------------------------------

def insert_trade(trade: Dict[str, Any], user_id: Optional[int] = None) -> None:
    """Insert a new trade record. Captures exceptions to Sentry (financial data)."""
    atr = trade.get("atr_at_entry", 0)
    multiplier = trade.get("trail_multiplier", 1.5)
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO trades (
                trade_id, symbol, instrument_token, sector,
                entry_ltp, entry_price, quantity, total_cost, entry_time,
                atr_at_entry, trail_multiplier, initial_sl, risk_per_share, risk_per_trade,
                highest_price_seen, last_new_high_date, current_sl,
                entry_order_id, sl_order_id, entry_status,
                status, gear_at_entry, automation_run_id,
                account_balance_before, account_balance_after,
                scan_id, scan_rank, scan_ai_conviction, trading_mode,
                user_id
            ) VALUES (
                :trade_id, :symbol, :instrument_token, :sector,
                :entry_ltp, :entry_price, :quantity, :total_cost, :entry_time,
                :atr_at_entry, :trail_multiplier, :initial_sl, :risk_per_share, :risk_per_trade,
                :highest_price_seen, :last_new_high_date, :current_sl,
                :entry_order_id, :sl_order_id, :entry_status,
                :status, :gear_at_entry, :automation_run_id,
                :account_balance_before, :account_balance_after,
                :scan_id, :scan_rank, :scan_ai_conviction, :trading_mode,
                :user_id
            )
        """, {
            "trade_id": trade.get("trade_id"),
            "symbol": trade.get("symbol"),
            "instrument_token": trade.get("instrument_token"),
            "sector": trade.get("sector"),
            "entry_ltp": trade.get("entry_ltp", trade.get("entry_price")),
            "entry_price": trade.get("entry_price"),
            "quantity": trade.get("quantity"),
            "total_cost": trade.get("total_cost"),
            "entry_time": trade.get("entry_time"),
            "atr_at_entry": atr,
            "trail_multiplier": multiplier,
            "initial_sl": trade.get("initial_sl", trade.get("current_sl")),
            "risk_per_share": round(atr * multiplier, 2),
            "risk_per_trade": round(atr * multiplier * trade.get("quantity", 1), 2),
            "highest_price_seen": trade.get("highest_price_seen", trade.get("entry_price")),
            "last_new_high_date": trade.get("last_new_high_date"),
            "current_sl": trade.get("current_sl"),
            "entry_order_id": trade.get("entry_order_id"),
            "sl_order_id": trade.get("sl_order_id"),
            "entry_status": trade.get("entry_status", "FILLED"),
            "status": trade.get("status", "OPEN"),
            "gear_at_entry": trade.get("automation_gear"),
            "automation_run_id": trade.get("automation_run_id"),
            "account_balance_before": trade.get("account_balance_before"),
            "account_balance_after": trade.get("account_balance_after"),
            "scan_id": trade.get("scan_id"),
            "scan_rank": trade.get("scan_rank"),
            "scan_ai_conviction": trade.get("scan_ai_conviction"),
            "trading_mode": trade.get("trading_mode", "simulator"),
            "user_id": user_id,
        })
        conn.commit()
    except Exception as e:
        _capture(e)
        logger.warning("[DB] insert_trade failed for %s: %s", trade.get("trade_id"), e)
    finally:
        conn.close()


def update_trade_fill(
    trade_id: str,
    entry_price: float,
    quantity: int,
    entry_status: str,
    sl_order_id: Optional[str] = None,
) -> None:
    """Update trade after entry order fill confirmation."""
    conn = get_conn()
    try:
        conn.execute("""
            UPDATE trades SET entry_price = :entry_price, quantity = :quantity,
                entry_status = :entry_status, sl_order_id = :sl_order_id
            WHERE trade_id = :trade_id
        """, {
            "trade_id": trade_id,
            "entry_price": entry_price,
            "quantity": quantity,
            "entry_status": entry_status,
            "sl_order_id": sl_order_id,
        })
        conn.commit()
    except Exception as e:
        logger.warning("[DB] update_trade_fill failed for %s: %s", trade_id, e)
    finally:
        conn.close()


def update_trade_sl(
    trade_id: str,
    current_sl: float,
    highest_price_seen: float,
    sl_order_id: Optional[str] = None,
) -> None:
    """Update trailing stop and high-water mark for an open trade."""
    conn = get_conn()
    try:
        params: Dict[str, Any] = {
            "trade_id": trade_id,
            "current_sl": current_sl,
            "highest_price_seen": highest_price_seen,
        }
        sl_clause = ""
        if sl_order_id is not None:
            params["sl_order_id"] = sl_order_id
            sl_clause = ", sl_order_id = :sl_order_id"
        conn.execute(
            f"UPDATE trades SET current_sl = :current_sl,"
            f" highest_price_seen = :highest_price_seen{sl_clause}"
            f" WHERE trade_id = :trade_id",
            params,
        )
        conn.commit()
    except Exception as e:
        logger.warning("[DB] update_trade_sl failed for %s: %s", trade_id, e)
    finally:
        conn.close()


def update_trade_exit(
    trade_id: str,
    exit_price: float,
    exit_time: str,
    exit_reason: str,
    realized_pnl: float,
    realized_pnl_pct: float,
    holding_days: int,
) -> None:
    """Mark a trade as closed. Captures exceptions to Sentry (financial data)."""
    conn = get_conn()
    try:
        conn.execute("""
            UPDATE trades SET status = 'CLOSED', exit_price = :exit_price,
                exit_ltp = :exit_price, exit_time = :exit_time,
                exit_reason = :exit_reason, realized_pnl = :realized_pnl,
                realized_pnl_pct = :realized_pnl_pct, holding_days = :holding_days
            WHERE trade_id = :trade_id
        """, {
            "trade_id": trade_id,
            "exit_price": exit_price,
            "exit_time": exit_time,
            "exit_reason": exit_reason,
            "realized_pnl": realized_pnl,
            "realized_pnl_pct": realized_pnl_pct,
            "holding_days": holding_days,
        })
        conn.commit()
    except Exception as e:
        _capture(e)
        logger.warning("[DB] update_trade_exit failed for %s: %s", trade_id, e)
    finally:
        conn.close()


def get_open_trades(trading_mode: Optional[str] = None, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get all open trades, optionally filtered by trading_mode and/or user_id."""
    conn = get_conn()
    try:
        # Build parameterized query — no f-string interpolation of user values
        conditions = ["status = 'OPEN'"]
        params: List[Any] = []
        if trading_mode:
            conditions.append("trading_mode = ?")
            params.append(trading_mode)
        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)
        sql = "SELECT * FROM trades WHERE " + " AND ".join(conditions)
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.warning("[DB] get_open_trades failed: %s", e)
        return []
    finally:
        conn.close()


def get_trade(trade_id: str) -> Optional[Dict[str, Any]]:
    """Get a single trade by trade_id."""
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM trades WHERE trade_id = ?", (trade_id,)).fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.warning("[DB] get_trade failed for %s: %s", trade_id, e)
        return None
    finally:
        conn.close()


def get_pending_entry_trades() -> List[Dict[str, Any]]:
    """Get trades with PENDING entry status (for recovery on server restart)."""
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM trades WHERE entry_status = 'PENDING' AND status = 'OPEN'"
        ).fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.warning("[DB] get_pending_entry_trades failed: %s", e)
        return []
    finally:
        conn.close()


def insert_position_snapshot(snapshot: Dict[str, Any]) -> None:
    """Record a position price snapshot (best-effort, no Sentry capture)."""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO position_snapshots (
                trade_id, symbol, snapshot_time, ltp, entry_price,
                current_sl, highest_price_seen, unrealized_pnl,
                unrealized_pnl_pct, quantity
            ) VALUES (
                :trade_id, :symbol, :snapshot_time, :ltp, :entry_price,
                :current_sl, :highest_price_seen, :unrealized_pnl,
                :unrealized_pnl_pct, :quantity
            )
        """, snapshot)
        conn.commit()
    except Exception as e:
        logger.warning("[DB] insert_position_snapshot failed: %s", e)
    finally:
        conn.close()


def insert_account_snapshot(snapshot: Dict[str, Any]) -> None:
    """Record an account state snapshot. Captures exceptions to Sentry (financial data)."""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO account_snapshots (
                snapshot_time, event_type, trade_id,
                initial_capital, current_balance, total_realized_pnl,
                open_position_cost, unrealized_pnl, net_equity,
                total_trades, winning_trades, losing_trades
            ) VALUES (
                :snapshot_time, :event_type, :trade_id,
                :initial_capital, :current_balance, :total_realized_pnl,
                :open_position_cost, :unrealized_pnl, :net_equity,
                :total_trades, :winning_trades, :losing_trades
            )
        """, snapshot)
        conn.commit()
    except Exception as e:
        _capture(e)
        logger.warning("[DB] insert_account_snapshot failed: %s", e)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Simulator account state (replaces simulator_data_*.json as primary store)
# ---------------------------------------------------------------------------

def upsert_simulator_account(user_id: int, account: Dict[str, Any]) -> None:
    """Write current simulator account state for a user (upsert)."""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO simulator_accounts (
                user_id, initial_capital, current_balance, total_pnl, updated_at
            ) VALUES (:user_id, :initial_capital, :current_balance, :total_pnl, :updated_at)
            ON CONFLICT(user_id) DO UPDATE SET
                initial_capital = excluded.initial_capital,
                current_balance = excluded.current_balance,
                total_pnl       = excluded.total_pnl,
                updated_at      = excluded.updated_at
        """, {
            "user_id": user_id,
            "initial_capital": account.get("initial_capital"),
            "current_balance": account.get("current_balance"),
            "total_pnl": account.get("total_pnl", 0.0),
            "updated_at": datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
        })
        conn.commit()
    except Exception as e:
        _capture(e)
        logger.warning("[DB] upsert_simulator_account failed for user %s: %s", user_id, e)
    finally:
        conn.close()


def get_simulator_account(user_id: int) -> Optional[Dict[str, Any]]:
    """Return the simulator account row for a user, or None if not found."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM simulator_accounts WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.warning("[DB] get_simulator_account failed for user %s: %s", user_id, e)
        return None
    finally:
        conn.close()
