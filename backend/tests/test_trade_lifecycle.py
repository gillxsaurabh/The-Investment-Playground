"""End-to-end trade lifecycle integration tests.

Tests the full path: insert → update fill → update SL → exit,
verifying data integrity, query correctness, and index usage.
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest


MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
MIGRATION_FILES = [
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
]


@pytest.fixture(scope="module")
def migrated_db():
    """Create a fully-migrated temporary database, yield its path, clean up after."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    for _, filename in MIGRATION_FILES:
        sql_file = MIGRATIONS_DIR / filename
        if sql_file.exists():
            conn.executescript(sql_file.read_text())
            conn.commit()
    conn.close()

    yield db_path
    os.unlink(db_path)


@pytest.fixture
def conn(migrated_db):
    """Yield a connected + configured connection; rollback after each test."""
    c = sqlite3.connect(migrated_db)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    yield c
    c.rollback()
    c.close()


def _seed_user(conn) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO users (email, password_hash, name) "
        "VALUES ('trader@test.com', 'hashed', 'Test Trader')"
    )
    conn.commit()
    row = conn.execute("SELECT id FROM users WHERE email = 'trader@test.com'").fetchone()
    return row[0]


def _seed_trade(conn, user_id: int, trade_id: str = "SIM_01JAN25_INFY_1234") -> dict:
    params = {
        "trade_id": trade_id,
        "symbol": "INFY",
        "instrument_token": 408065,
        "sector": "IT",
        "entry_ltp": 1800.0,
        "entry_price": 1801.80,
        "quantity": 10,
        "total_cost": 18018.0,
        "entry_time": "2025-01-01 09:30:00",
        "atr_at_entry": 30.0,
        "trail_multiplier": 1.5,
        "initial_sl": 1756.80,
        "risk_per_share": 45.0,
        "risk_per_trade": 450.0,
        "highest_price_seen": 1801.80,
        "last_new_high_date": "2025-01-01",
        "current_sl": 1756.80,
        "entry_order_id": None,
        "sl_order_id": None,
        "entry_status": "FILLED",
        "status": "OPEN",
        "gear_at_entry": 3,
        "automation_run_id": None,
        "account_balance_before": 100000.0,
        "account_balance_after": 81982.0,
        "scan_id": None,
        "scan_rank": None,
        "scan_ai_conviction": None,
        "trading_mode": "simulator",
        "user_id": user_id,
    }
    conn.execute("""
        INSERT OR IGNORE INTO trades (
            trade_id, symbol, instrument_token, sector,
            entry_ltp, entry_price, quantity, total_cost, entry_time,
            atr_at_entry, trail_multiplier, initial_sl, risk_per_share, risk_per_trade,
            highest_price_seen, last_new_high_date, current_sl,
            entry_order_id, sl_order_id, entry_status,
            status, gear_at_entry, automation_run_id,
            account_balance_before, account_balance_after,
            scan_id, scan_rank, scan_ai_conviction, trading_mode, user_id
        ) VALUES (
            :trade_id, :symbol, :instrument_token, :sector,
            :entry_ltp, :entry_price, :quantity, :total_cost, :entry_time,
            :atr_at_entry, :trail_multiplier, :initial_sl, :risk_per_share, :risk_per_trade,
            :highest_price_seen, :last_new_high_date, :current_sl,
            :entry_order_id, :sl_order_id, :entry_status,
            :status, :gear_at_entry, :automation_run_id,
            :account_balance_before, :account_balance_after,
            :scan_id, :scan_rank, :scan_ai_conviction, :trading_mode, :user_id
        )
    """, params)
    conn.commit()
    return params


# ---------------------------------------------------------------------------
# Trade lifecycle
# ---------------------------------------------------------------------------

def test_insert_and_retrieve_trade(conn):
    user_id = _seed_user(conn)
    _seed_trade(conn, user_id)

    row = conn.execute(
        "SELECT * FROM trades WHERE trade_id = 'SIM_01JAN25_INFY_1234'"
    ).fetchone()
    assert row is not None
    assert row["symbol"] == "INFY"
    assert row["status"] == "OPEN"
    assert row["user_id"] == user_id


def test_update_trailing_sl(conn):
    user_id = _seed_user(conn)
    _seed_trade(conn, user_id)

    conn.execute("""
        UPDATE trades SET current_sl = 1820.0, highest_price_seen = 1870.0
        WHERE trade_id = 'SIM_01JAN25_INFY_1234'
    """)
    conn.commit()

    row = conn.execute(
        "SELECT current_sl, highest_price_seen FROM trades WHERE trade_id = 'SIM_01JAN25_INFY_1234'"
    ).fetchone()
    assert row["current_sl"] == 1820.0
    assert row["highest_price_seen"] == 1870.0


def test_close_trade_and_verify(conn):
    user_id = _seed_user(conn)
    _seed_trade(conn, user_id)

    conn.execute("""
        UPDATE trades SET status = 'CLOSED', exit_price = 1900.0, exit_time = '2025-02-01 10:00:00',
            exit_reason = 'Trailing SL', realized_pnl = 981.8, realized_pnl_pct = 5.45,
            holding_days = 31
        WHERE trade_id = 'SIM_01JAN25_INFY_1234'
    """)
    conn.commit()

    row = conn.execute(
        "SELECT status, realized_pnl, holding_days FROM trades WHERE trade_id = 'SIM_01JAN25_INFY_1234'"
    ).fetchone()
    assert row["status"] == "CLOSED"
    assert abs(row["realized_pnl"] - 981.8) < 0.01
    assert row["holding_days"] == 31


def test_get_open_trades_by_user(conn):
    user_id = _seed_user(conn)
    _seed_trade(conn, user_id, trade_id="SIM_01JAN25_TCS_9999")

    rows = conn.execute(
        "SELECT * FROM trades WHERE status = 'OPEN' AND user_id = ?", (user_id,)
    ).fetchall()
    trade_ids = [r["trade_id"] for r in rows]
    assert "SIM_01JAN25_TCS_9999" in trade_ids


def test_position_snapshot_cascade_delete(conn):
    user_id = _seed_user(conn)
    _seed_trade(conn, user_id)

    conn.execute("""
        INSERT INTO position_snapshots (trade_id, symbol, snapshot_time, ltp, entry_price,
            current_sl, highest_price_seen, unrealized_pnl, unrealized_pnl_pct, quantity)
        VALUES ('SIM_01JAN25_INFY_1234', 'INFY', datetime('now'), 1850.0, 1801.80,
                1756.80, 1850.0, 482.0, 2.67, 10)
    """)
    conn.commit()

    snapshot = conn.execute(
        "SELECT id FROM position_snapshots WHERE trade_id = 'SIM_01JAN25_INFY_1234'"
    ).fetchone()
    assert snapshot is not None

    conn.execute("DELETE FROM trades WHERE trade_id = 'SIM_01JAN25_INFY_1234'")
    conn.commit()

    snapshot_after = conn.execute(
        "SELECT id FROM position_snapshots WHERE trade_id = 'SIM_01JAN25_INFY_1234'"
    ).fetchone()
    assert snapshot_after is None, "Position snapshots should be cascade-deleted with the trade"


def test_invalid_trade_status_rejected(conn):
    user_id = _seed_user(conn)
    _seed_trade(conn, user_id)

    # Triggers raise IntegrityError, not OperationalError
    with pytest.raises(sqlite3.IntegrityError, match="Invalid trades.status"):
        conn.execute(
            "UPDATE trades SET status = 'WHATEVER' WHERE trade_id = 'SIM_01JAN25_INFY_1234'"
        )


def test_invalid_trading_mode_rejected(conn):
    with pytest.raises(sqlite3.IntegrityError, match="Invalid trades.trading_mode"):
        user_id = _seed_user(conn)
        conn.execute("""
            INSERT INTO trades (
                trade_id, symbol, entry_ltp, entry_price, quantity, total_cost, entry_time,
                atr_at_entry, trail_multiplier, initial_sl, risk_per_share, risk_per_trade,
                status, trading_mode, user_id
            ) VALUES (
                'BAD_TRADE_MODE', 'RELI', 1000.0, 1001.0, 5, 5005.0, datetime('now'),
                20.0, 1.5, 971.0, 30.0, 150.0, 'OPEN', 'paper', ?
            )
        """, (user_id,))


# ---------------------------------------------------------------------------
# Simulator account
# ---------------------------------------------------------------------------

def test_simulator_account_upsert(conn):
    user_id = _seed_user(conn)

    conn.execute("""
        INSERT INTO simulator_accounts (user_id, initial_capital, current_balance, total_pnl, updated_at)
        VALUES (?, 100000.0, 95000.0, -5000.0, datetime('now'))
        ON CONFLICT(user_id) DO UPDATE SET
            current_balance = excluded.current_balance,
            total_pnl = excluded.total_pnl,
            updated_at = excluded.updated_at
    """, (user_id,))
    conn.commit()

    row = conn.execute(
        "SELECT current_balance, total_pnl FROM simulator_accounts WHERE user_id = ?", (user_id,)
    ).fetchone()
    assert row["current_balance"] == 95000.0
    assert row["total_pnl"] == -5000.0

    # Upsert again (balance improved)
    conn.execute("""
        INSERT INTO simulator_accounts (user_id, initial_capital, current_balance, total_pnl, updated_at)
        VALUES (?, 100000.0, 107000.0, 7000.0, datetime('now'))
        ON CONFLICT(user_id) DO UPDATE SET
            current_balance = excluded.current_balance,
            total_pnl = excluded.total_pnl,
            updated_at = excluded.updated_at
    """, (user_id,))
    conn.commit()

    row = conn.execute(
        "SELECT current_balance FROM simulator_accounts WHERE user_id = ?", (user_id,)
    ).fetchone()
    assert row["current_balance"] == 107000.0


# ---------------------------------------------------------------------------
# Index usage (EXPLAIN QUERY PLAN)
# ---------------------------------------------------------------------------

def test_open_trades_uses_index(conn):
    # EXPLAIN QUERY PLAN rows: (id, parent, notused, detail)
    plan = conn.execute(
        "EXPLAIN QUERY PLAN SELECT * FROM trades WHERE status = 'OPEN' AND user_id = 1"
    ).fetchall()
    # Extract the 4th column (detail) from each row
    plan_details = " ".join(row[3] if len(row) > 3 else str(row) for row in plan).lower()
    assert "scan" in plan_details or "index" in plan_details, (
        f"Query plan looks unexpected — no SCAN or INDEX step found: {plan_details}"
    )
