"""SQLite persistence layer for CogniCap trade lifecycle tracking.

Uses PRAGMA foreign_keys = ON and WAL journal mode for concurrent read perf.
All writes are fire-and-forget (log warnings on failure) so they never break
the primary JSON-backed simulator behavior.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import DB_PATH

logger = logging.getLogger(__name__)


def get_conn() -> sqlite3.Connection:
    """Return a WAL-mode, foreign-key-enabled SQLite connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


LATEST_SCHEMA_VERSION = 9


def init_db() -> None:
    """Run all pending migrations sequentially."""
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    conn = get_conn()
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]

        migrations = [
            (1, "001_initial.sql"),
            (2, "002_users.sql"),
            (3, "003_add_user_id.sql"),
            (4, "004_analysis_cache.sql"),
            (5, "005_password_reset.sql"),
            (6, "006_admin_and_tiers.sql"),
            (7, "007_user_plan.sql"),
            (8, "008_encrypt_broker_tokens.sql"),
            (9, "009_llm_usage.sql"),
        ]

        for target_version, filename in migrations:
            if version >= target_version:
                continue
            migration_file = migrations_dir / filename
            if not migration_file.exists():
                logger.error(f"[DB] Migration file not found: {migration_file}")
                return
            sql = migration_file.read_text()
            conn.executescript(sql)
            conn.commit()
            logger.info(f"[DB] Migrated to schema version {target_version}")

        final_version = conn.execute("PRAGMA user_version").fetchone()[0]
        if final_version >= LATEST_SCHEMA_VERSION:
            logger.debug(f"[DB] Schema at version {final_version}")
    except Exception as e:
        logger.error(f"[DB] Schema initialization failed: {e}", exc_info=True)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Trade CRUD
# ---------------------------------------------------------------------------

def insert_trade(trade: Dict[str, Any], user_id: Optional[int] = None) -> None:
    """Insert a new trade record."""
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
        logger.warning(f"[DB] insert_trade failed for {trade.get('trade_id')}: {e}")
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
        logger.warning(f"[DB] update_trade_fill failed for {trade_id}: {e}")
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
        conn.execute(f"""
            UPDATE trades SET current_sl = :current_sl,
                highest_price_seen = :highest_price_seen{sl_clause}
            WHERE trade_id = :trade_id
        """, params)
        conn.commit()
    except Exception as e:
        logger.warning(f"[DB] update_trade_sl failed for {trade_id}: {e}")
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
    """Mark a trade as closed with exit details."""
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
        logger.warning(f"[DB] update_trade_exit failed for {trade_id}: {e}")
    finally:
        conn.close()


def get_open_trades(trading_mode: Optional[str] = None, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get all open trades, optionally filtered by trading_mode and/or user_id."""
    conn = get_conn()
    try:
        conditions = ["status = 'OPEN'"]
        params: List[Any] = []
        if trading_mode:
            conditions.append("trading_mode = ?")
            params.append(trading_mode)
        if user_id is not None:
            conditions.append("user_id = ?")
            params.append(user_id)
        where = " AND ".join(conditions)
        rows = conn.execute(f"SELECT * FROM trades WHERE {where}", params).fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.warning(f"[DB] get_open_trades failed: {e}")
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
        logger.warning(f"[DB] get_trade failed for {trade_id}: {e}")
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
        logger.warning(f"[DB] get_pending_entry_trades failed: {e}")
        return []
    finally:
        conn.close()


def insert_position_snapshot(snapshot: Dict[str, Any]) -> None:
    """Record a position price snapshot."""
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
        logger.warning(f"[DB] insert_position_snapshot failed: {e}")
    finally:
        conn.close()


def insert_account_snapshot(snapshot: Dict[str, Any]) -> None:
    """Record an account state snapshot."""
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
        logger.warning(f"[DB] insert_account_snapshot failed: {e}")
    finally:
        conn.close()
