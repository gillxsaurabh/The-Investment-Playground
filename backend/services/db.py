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


LATEST_SCHEMA_VERSION = 13


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
            (13, "013_retrospective.sql"),
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


# ---------------------------------------------------------------------------
# Scan lifecycle (buy pipeline)
# ---------------------------------------------------------------------------

def insert_scan(scan: Dict[str, Any]) -> None:
    """Insert a new scan row (status=running). Fire-and-forget."""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO scans (
                scan_id, started_at, status,
                gear, gear_label, universe,
                min_turnover, rsi_buy_limit, adx_min, trail_multiplier,
                fundamental_check, sector_5d_tolerance, min_volume_ratio,
                vix, market_regime
            ) VALUES (
                :scan_id, :started_at, 'running',
                :gear, :gear_label, :universe,
                :min_turnover, :rsi_buy_limit, :adx_min, :trail_multiplier,
                :fundamental_check, :sector_5d_tolerance, :min_volume_ratio,
                :vix, :market_regime
            )
        """, scan)
        conn.commit()
    except Exception as e:
        logger.warning("[DB] insert_scan failed for %s: %s", scan.get("scan_id"), e)
    finally:
        conn.close()


def update_scan_completion(
    scan_id: str,
    status: str,
    total_scanned: int,
    universe_filter_passed: int,
    technical_filter_passed: int,
    fundamental_filter_passed: int,
    sector_filter_passed: int,
    final_selected: int,
    completed_at: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    """Update funnel counts and status when a scan completes or fails."""
    conn = get_conn()
    try:
        conn.execute("""
            UPDATE scans SET
                status = :status,
                completed_at = :completed_at,
                error_message = :error_message,
                total_scanned = :total_scanned,
                universe_filter_passed = :universe_filter_passed,
                technical_filter_passed = :technical_filter_passed,
                fundamental_filter_passed = :fundamental_filter_passed,
                sector_filter_passed = :sector_filter_passed,
                final_selected = :final_selected
            WHERE scan_id = :scan_id
        """, {
            "scan_id": scan_id,
            "status": status,
            "completed_at": completed_at or datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
            "error_message": error_message,
            "total_scanned": total_scanned,
            "universe_filter_passed": universe_filter_passed,
            "technical_filter_passed": technical_filter_passed,
            "fundamental_filter_passed": fundamental_filter_passed,
            "sector_filter_passed": sector_filter_passed,
            "final_selected": final_selected,
        })
        conn.commit()
    except Exception as e:
        logger.warning("[DB] update_scan_completion failed for %s: %s", scan_id, e)
    finally:
        conn.close()


def upsert_scan_candidate(scan_id: str, symbol: str, data: Dict[str, Any]) -> None:
    """Insert or update a single stock's stage data within a scan."""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO scan_candidates (scan_id, symbol, instrument_token, sector, sector_index,
                current_price, avg_volume_20d, avg_turnover_20d, volume_ratio,
                ema_200, stock_3m_return, nifty_3m_return, sector_3m_return,
                passed_universe_filter, universe_fail_reason,
                ema_20, rsi, adx, rsi_trigger,
                passed_technical_filter, technical_fail_reason,
                profit_yoy_growing, profit_qoq_growing, quarterly_profit_growth,
                roe, debt_to_equity,
                passed_fundamental_filter, fundamental_fail_reason,
                sector_5d_change, passed_sector_filter, sector_fail_reason,
                composite_score, score_technical, score_fundamental,
                score_relative_strength, score_volume_health,
                ai_conviction, why_selected, news_sentiment, news_flag, news_headlines,
                final_rank, final_rank_score, rank_reason,
                rank_factor_conviction_norm, rank_factor_composite_norm,
                rank_factor_rs_norm, rank_factor_fundamental_norm, rank_factor_sector_norm,
                reached_final_shortlist
            ) VALUES (
                :scan_id, :symbol, :instrument_token, :sector, :sector_index,
                :current_price, :avg_volume_20d, :avg_turnover_20d, :volume_ratio,
                :ema_200, :stock_3m_return, :nifty_3m_return, :sector_3m_return,
                :passed_universe_filter, :universe_fail_reason,
                :ema_20, :rsi, :adx, :rsi_trigger,
                :passed_technical_filter, :technical_fail_reason,
                :profit_yoy_growing, :profit_qoq_growing, :quarterly_profit_growth,
                :roe, :debt_to_equity,
                :passed_fundamental_filter, :fundamental_fail_reason,
                :sector_5d_change, :passed_sector_filter, :sector_fail_reason,
                :composite_score, :score_technical, :score_fundamental,
                :score_relative_strength, :score_volume_health,
                :ai_conviction, :why_selected, :news_sentiment, :news_flag, :news_headlines,
                :final_rank, :final_rank_score, :rank_reason,
                :rank_factor_conviction_norm, :rank_factor_composite_norm,
                :rank_factor_rs_norm, :rank_factor_fundamental_norm, :rank_factor_sector_norm,
                :reached_final_shortlist
            )
            ON CONFLICT(scan_id, symbol) DO UPDATE SET
                instrument_token = excluded.instrument_token,
                sector = excluded.sector,
                sector_index = excluded.sector_index,
                current_price = excluded.current_price,
                avg_volume_20d = excluded.avg_volume_20d,
                avg_turnover_20d = excluded.avg_turnover_20d,
                volume_ratio = excluded.volume_ratio,
                ema_200 = excluded.ema_200,
                stock_3m_return = excluded.stock_3m_return,
                nifty_3m_return = excluded.nifty_3m_return,
                sector_3m_return = excluded.sector_3m_return,
                passed_universe_filter = excluded.passed_universe_filter,
                universe_fail_reason = excluded.universe_fail_reason,
                ema_20 = excluded.ema_20,
                rsi = excluded.rsi,
                adx = excluded.adx,
                rsi_trigger = excluded.rsi_trigger,
                passed_technical_filter = excluded.passed_technical_filter,
                technical_fail_reason = excluded.technical_fail_reason,
                profit_yoy_growing = excluded.profit_yoy_growing,
                profit_qoq_growing = excluded.profit_qoq_growing,
                quarterly_profit_growth = excluded.quarterly_profit_growth,
                roe = excluded.roe,
                debt_to_equity = excluded.debt_to_equity,
                passed_fundamental_filter = excluded.passed_fundamental_filter,
                fundamental_fail_reason = excluded.fundamental_fail_reason,
                sector_5d_change = excluded.sector_5d_change,
                passed_sector_filter = excluded.passed_sector_filter,
                sector_fail_reason = excluded.sector_fail_reason,
                composite_score = excluded.composite_score,
                score_technical = excluded.score_technical,
                score_fundamental = excluded.score_fundamental,
                score_relative_strength = excluded.score_relative_strength,
                score_volume_health = excluded.score_volume_health,
                ai_conviction = excluded.ai_conviction,
                why_selected = excluded.why_selected,
                news_sentiment = excluded.news_sentiment,
                news_flag = excluded.news_flag,
                news_headlines = excluded.news_headlines,
                final_rank = excluded.final_rank,
                final_rank_score = excluded.final_rank_score,
                rank_reason = excluded.rank_reason,
                rank_factor_conviction_norm = excluded.rank_factor_conviction_norm,
                rank_factor_composite_norm = excluded.rank_factor_composite_norm,
                rank_factor_rs_norm = excluded.rank_factor_rs_norm,
                rank_factor_fundamental_norm = excluded.rank_factor_fundamental_norm,
                rank_factor_sector_norm = excluded.rank_factor_sector_norm,
                reached_final_shortlist = excluded.reached_final_shortlist
        """, {
            "scan_id": scan_id,
            "symbol": symbol,
            "instrument_token": data.get("instrument_token"),
            "sector": data.get("sector"),
            "sector_index": data.get("sector_index"),
            "current_price": data.get("current_price"),
            "avg_volume_20d": data.get("avg_volume_20d"),
            "avg_turnover_20d": data.get("avg_turnover_20d"),
            "volume_ratio": data.get("volume_ratio"),
            "ema_200": data.get("ema_200"),
            "stock_3m_return": data.get("stock_3m_return"),
            "nifty_3m_return": data.get("nifty_3m_return"),
            "sector_3m_return": data.get("sector_3m_return"),
            "passed_universe_filter": data.get("passed_universe_filter"),
            "universe_fail_reason": data.get("universe_fail_reason"),
            "ema_20": data.get("ema_20"),
            "rsi": data.get("rsi"),
            "adx": data.get("adx"),
            "rsi_trigger": data.get("rsi_trigger"),
            "passed_technical_filter": data.get("passed_technical_filter"),
            "technical_fail_reason": data.get("technical_fail_reason"),
            "profit_yoy_growing": data.get("profit_yoy_growing"),
            "profit_qoq_growing": data.get("profit_qoq_growing"),
            "quarterly_profit_growth": data.get("quarterly_profit_growth"),
            "roe": data.get("roe"),
            "debt_to_equity": data.get("debt_to_equity"),
            "passed_fundamental_filter": data.get("passed_fundamental_filter"),
            "fundamental_fail_reason": data.get("fundamental_fail_reason"),
            "sector_5d_change": data.get("sector_5d_change"),
            "passed_sector_filter": data.get("passed_sector_filter"),
            "sector_fail_reason": data.get("sector_fail_reason"),
            "composite_score": data.get("composite_score"),
            "score_technical": data.get("score_technical"),
            "score_fundamental": data.get("score_fundamental"),
            "score_relative_strength": data.get("score_relative_strength"),
            "score_volume_health": data.get("score_volume_health"),
            "ai_conviction": data.get("ai_conviction"),
            "why_selected": data.get("why_selected"),
            "news_sentiment": data.get("news_sentiment"),
            "news_flag": data.get("news_flag"),
            "news_headlines": data.get("news_headlines"),
            "final_rank": data.get("final_rank"),
            "final_rank_score": data.get("final_rank_score"),
            "rank_reason": data.get("rank_reason"),
            "rank_factor_conviction_norm": data.get("rank_factor_conviction_norm"),
            "rank_factor_composite_norm": data.get("rank_factor_composite_norm"),
            "rank_factor_rs_norm": data.get("rank_factor_rs_norm"),
            "rank_factor_fundamental_norm": data.get("rank_factor_fundamental_norm"),
            "rank_factor_sector_norm": data.get("rank_factor_sector_norm"),
            "reached_final_shortlist": data.get("reached_final_shortlist", False),
        })
        conn.commit()
    except Exception as e:
        logger.warning("[DB] upsert_scan_candidate failed for %s/%s: %s", scan_id, symbol, e)
    finally:
        conn.close()


def mark_final_shortlist(scan_id: str, symbols: List[str]) -> None:
    """Mark the given symbols as reached_final_shortlist=TRUE for this scan."""
    if not symbols:
        return
    conn = get_conn()
    try:
        placeholders = ",".join("?" * len(symbols))
        conn.execute(
            f"UPDATE scan_candidates SET reached_final_shortlist = TRUE "
            f"WHERE scan_id = ? AND symbol IN ({placeholders})",
            [scan_id, *symbols],
        )
        conn.commit()
    except Exception as e:
        logger.warning("[DB] mark_final_shortlist failed for %s: %s", scan_id, e)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Sell audit
# ---------------------------------------------------------------------------

def insert_sell_audit(audit: Dict[str, Any]) -> None:
    """Insert a sell audit row. Captures exceptions to Sentry."""
    import json as _json
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO sell_audits (
                audit_id, audited_at, symbol, instrument_token, sector,
                trading_mode, user_id, trade_id,
                current_price, unrealized_pnl_pct,
                rsi, adx, ema_20, ema_50, ema_200,
                stock_3m_return, nifty_3m_return, sector_5d_change,
                roe, debt_to_equity, profit_declining_quarters,
                urgency_score, urgency_level,
                urgency_reasons, sell_score_breakdown,
                ai_reasoning, news_sentiment, news_flag
            ) VALUES (
                :audit_id, :audited_at, :symbol, :instrument_token, :sector,
                :trading_mode, :user_id, :trade_id,
                :current_price, :unrealized_pnl_pct,
                :rsi, :adx, :ema_20, :ema_50, :ema_200,
                :stock_3m_return, :nifty_3m_return, :sector_5d_change,
                :roe, :debt_to_equity, :profit_declining_quarters,
                :urgency_score, :urgency_level,
                :urgency_reasons, :sell_score_breakdown,
                :ai_reasoning, :news_sentiment, :news_flag
            )
        """, {
            "audit_id": audit.get("audit_id"),
            "audited_at": audit.get("audited_at"),
            "symbol": audit.get("symbol"),
            "instrument_token": audit.get("instrument_token"),
            "sector": audit.get("sector"),
            "trading_mode": audit.get("trading_mode", "simulator"),
            "user_id": audit.get("user_id"),
            "trade_id": audit.get("trade_id"),
            "current_price": audit.get("current_price"),
            "unrealized_pnl_pct": audit.get("pnl_percentage"),
            "rsi": audit.get("rsi"),
            "adx": audit.get("adx"),
            "ema_20": audit.get("ema_20"),
            "ema_50": audit.get("ema_50"),
            "ema_200": audit.get("ema_200"),
            "stock_3m_return": audit.get("stock_3m_return"),
            "nifty_3m_return": audit.get("nifty_3m_return"),
            "sector_5d_change": audit.get("sector_5d_change"),
            "roe": audit.get("roe"),
            "debt_to_equity": audit.get("debt_to_equity"),
            "profit_declining_quarters": audit.get("profit_declining_quarters"),
            "urgency_score": audit.get("sell_urgency_score", 0),
            "urgency_level": audit.get("sell_urgency_label", "HOLD"),
            "urgency_reasons": _json.dumps(audit.get("sell_signals", [])),
            "sell_score_breakdown": _json.dumps(audit.get("sell_score_breakdown") or {}),
            "ai_reasoning": audit.get("sell_reason") or audit.get("hold_reason"),
            "news_sentiment": audit.get("news_sentiment"),
            "news_flag": audit.get("news_flag"),
        })
        conn.commit()
    except Exception as e:
        _capture(e)
        logger.warning("[DB] insert_sell_audit failed for %s: %s", audit.get("audit_id"), e)
    finally:
        conn.close()


def link_exit_audit(trade_id: str, audit_id: str) -> None:
    """Record which sell audit prompted a trade exit."""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE trades SET exit_audit_id = ? WHERE trade_id = ?",
            (audit_id, trade_id),
        )
        conn.commit()
    except Exception as e:
        logger.warning("[DB] link_exit_audit failed for %s: %s", trade_id, e)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Stock analyses (on-demand deep analysis)
# ---------------------------------------------------------------------------

def insert_stock_analysis(analysis: Dict[str, Any]) -> None:
    """Persist a completed on-demand stock analysis."""
    conn = get_conn()
    try:
        conn.execute("""
            INSERT INTO stock_analyses (
                symbol, analyzed_at, triggered_by, overall_score,
                recency_score, recency_stock_return, recency_nifty_return,
                recency_outperformance, recency_detail,
                trend_score, trend_adx, trend_ema_20, trend_ema_50,
                trend_strength, trend_direction, stats_explanation,
                fundamental_score, fund_roe, fund_debt_to_equity, fund_sales_growth,
                fundamental_summary, fundamental_explanation,
                news_score, news_explanation
            ) VALUES (
                :symbol, :analyzed_at, :triggered_by, :overall_score,
                :recency_score, :recency_stock_return, :recency_nifty_return,
                :recency_outperformance, :recency_detail,
                :trend_score, :trend_adx, :trend_ema_20, :trend_ema_50,
                :trend_strength, :trend_direction, :stats_explanation,
                :fundamental_score, :fund_roe, :fund_debt_to_equity, :fund_sales_growth,
                :fundamental_summary, :fundamental_explanation,
                :news_score, :news_explanation
            )
        """, {
            "symbol": analysis.get("symbol"),
            "analyzed_at": analysis.get("analyzed_at", datetime.utcnow().isoformat(sep=" ", timespec="seconds")),
            "triggered_by": analysis.get("triggered_by", "user"),
            "overall_score": analysis.get("overall_score"),
            "recency_score": analysis.get("recency_score"),
            "recency_stock_return": analysis.get("recency_stock_return"),
            "recency_nifty_return": analysis.get("recency_nifty_return"),
            "recency_outperformance": analysis.get("recency_outperformance"),
            "recency_detail": analysis.get("recency_detail"),
            "trend_score": analysis.get("trend_score"),
            "trend_adx": analysis.get("trend_adx"),
            "trend_ema_20": analysis.get("trend_ema_20"),
            "trend_ema_50": analysis.get("trend_ema_50"),
            "trend_strength": analysis.get("trend_strength"),
            "trend_direction": analysis.get("trend_direction"),
            "stats_explanation": analysis.get("stats_explanation"),
            "fundamental_score": analysis.get("fundamental_score"),
            "fund_roe": analysis.get("fund_roe"),
            "fund_debt_to_equity": analysis.get("fund_debt_to_equity"),
            "fund_sales_growth": analysis.get("fund_sales_growth"),
            "fundamental_summary": analysis.get("fundamental_summary"),
            "fundamental_explanation": analysis.get("fundamental_explanation"),
            "news_score": analysis.get("news_score"),
            "news_explanation": analysis.get("news_explanation"),
        })
        conn.commit()
    except Exception as e:
        logger.warning("[DB] insert_stock_analysis failed for %s: %s", analysis.get("symbol"), e)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Retrospective reports
# ---------------------------------------------------------------------------

def insert_retrospective_report(report: Dict[str, Any]) -> None:
    """Persist a completed retrospective report."""
    import json as _json
    conn = get_conn()
    try:
        conn.execute("""
            INSERT OR IGNORE INTO retrospective_reports (
                report_id, generated_at, trading_mode,
                period_start, period_end, lookback_days,
                trades_analyzed, winners, losers, win_rate_pct, total_pnl, avg_pnl_pct,
                cohort_aggregates, winner_patterns, loser_patterns,
                filter_audit, sl_calibration, conviction_cal, sell_audit_cal,
                claude_findings, claude_recommendations,
                triggered_by, user_id
            ) VALUES (
                :report_id, :generated_at, :trading_mode,
                :period_start, :period_end, :lookback_days,
                :trades_analyzed, :winners, :losers, :win_rate_pct, :total_pnl, :avg_pnl_pct,
                :cohort_aggregates, :winner_patterns, :loser_patterns,
                :filter_audit, :sl_calibration, :conviction_cal, :sell_audit_cal,
                :claude_findings, :claude_recommendations,
                :triggered_by, :user_id
            )
        """, {
            "report_id": report.get("report_id"),
            "generated_at": report.get("generated_at"),
            "trading_mode": report.get("trading_mode", "simulator"),
            "period_start": report.get("period_start"),
            "period_end": report.get("period_end"),
            "lookback_days": report.get("lookback_days", 90),
            "trades_analyzed": report.get("trades_analyzed", 0),
            "winners": report.get("winners", 0),
            "losers": report.get("losers", 0),
            "win_rate_pct": report.get("win_rate_pct"),
            "total_pnl": report.get("total_pnl"),
            "avg_pnl_pct": report.get("avg_pnl_pct"),
            "cohort_aggregates": _json.dumps(report.get("cohort_aggregates") or {}),
            "winner_patterns": _json.dumps(report.get("winner_patterns") or {}),
            "loser_patterns": _json.dumps(report.get("loser_patterns") or {}),
            "filter_audit": _json.dumps(report.get("filter_audit") or {}),
            "sl_calibration": _json.dumps(report.get("sl_calibration") or {}),
            "conviction_cal": _json.dumps(report.get("conviction_cal") or {}),
            "sell_audit_cal": _json.dumps(report.get("sell_audit_cal") or {}),
            "claude_findings": report.get("claude_findings"),
            "claude_recommendations": _json.dumps(report.get("claude_recommendations") or []),
            "triggered_by": report.get("triggered_by", "manual"),
            "user_id": report.get("user_id"),
        })
        conn.commit()
    except Exception as e:
        _capture(e)
        logger.warning("[DB] insert_retrospective_report failed for %s: %s", report.get("report_id"), e)
    finally:
        conn.close()


def list_retrospective_reports(
    trading_mode: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """List retrospective reports, most recent first."""
    conn = get_conn()
    try:
        if trading_mode:
            rows = conn.execute(
                "SELECT * FROM retrospective_reports WHERE trading_mode = ? "
                "ORDER BY generated_at DESC LIMIT ?",
                (trading_mode, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM retrospective_reports ORDER BY generated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[DB] list_retrospective_reports failed: %s", e)
        return []
    finally:
        conn.close()


def get_retrospective_report(report_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a single retrospective report by ID."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM retrospective_reports WHERE report_id = ?", (report_id,)
        ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        logger.warning("[DB] get_retrospective_report failed for %s: %s", report_id, e)
        return None
    finally:
        conn.close()


def get_closed_trades_for_retrospective(
    trading_mode: str,
    period_start: str,
    period_end: str,
) -> List[Dict[str, Any]]:
    """Fetch all closed trades in window with joined scan_candidates and sell_audit data."""
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT
                t.*,
                sc.passed_universe_filter, sc.universe_fail_reason,
                sc.passed_technical_filter, sc.technical_fail_reason,
                sc.passed_fundamental_filter, sc.fundamental_fail_reason,
                sc.passed_sector_filter, sc.sector_fail_reason,
                sc.composite_score AS sc_composite_score,
                sc.score_technical, sc.score_fundamental,
                sc.score_relative_strength, sc.score_volume_health,
                sc.ai_conviction AS sc_ai_conviction,
                sc.why_selected, sc.news_flag AS sc_news_flag,
                sc.final_rank AS sc_final_rank,
                sc.final_rank_score AS sc_final_rank_score,
                sc.rank_reason,
                sa.urgency_score AS exit_urgency_score,
                sa.urgency_level AS exit_urgency_level,
                sa.urgency_reasons AS exit_urgency_reasons,
                sa.ai_reasoning AS exit_ai_reasoning
            FROM trades t
            LEFT JOIN scan_candidates sc
                ON t.scan_id = sc.scan_id AND t.symbol = sc.symbol
            LEFT JOIN sell_audits sa
                ON t.exit_audit_id = sa.audit_id
            WHERE t.status = 'CLOSED'
              AND t.trading_mode = ?
              AND t.exit_time BETWEEN ? AND ?
            ORDER BY t.exit_time ASC
        """, (trading_mode, period_start, period_end)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[DB] get_closed_trades_for_retrospective failed: %s", e)
        return []
    finally:
        conn.close()


def get_scan_rejection_stats(
    period_start: str,
    period_end: str,
) -> List[Dict[str, Any]]:
    """Get rejection counts per stage across all scans in the window."""
    conn = get_conn()
    try:
        rows = conn.execute("""
            SELECT
                sc.universe_fail_reason,
                sc.technical_fail_reason,
                sc.fundamental_fail_reason,
                sc.sector_fail_reason,
                sc.passed_universe_filter,
                sc.passed_technical_filter,
                sc.passed_fundamental_filter,
                sc.passed_sector_filter,
                sc.reached_final_shortlist,
                s.gear_label,
                s.started_at
            FROM scan_candidates sc
            JOIN scans s ON sc.scan_id = s.scan_id
            WHERE s.started_at BETWEEN ? AND ?
        """, (period_start, period_end)).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning("[DB] get_scan_rejection_stats failed: %s", e)
        return []
    finally:
        conn.close()
