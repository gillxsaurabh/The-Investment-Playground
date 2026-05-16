-- Migration 011: Consolidate simulator account state into SQLite
-- Creates simulator_accounts as the canonical store for per-user paper-trading
-- balances, replacing the primary role of simulator_data_{user_id}.json.
-- JSON files are kept as a write-through cache for backwards compatibility
-- but are no longer the source of truth for balance/P&L.

PRAGMA user_version = 11;

-- Per-user paper trading account (balance, P&L summary)
-- One row per user; upserted on every save via INSERT OR REPLACE.
CREATE TABLE IF NOT EXISTS simulator_accounts (
    user_id         INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    initial_capital REAL    NOT NULL DEFAULT 100000.0,
    current_balance REAL    NOT NULL DEFAULT 100000.0,
    total_pnl       REAL    NOT NULL DEFAULT 0.0,
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Prune position_snapshots older than 30 days for closed trades.
-- This is a one-time cleanup; ongoing pruning is handled by the application.
DELETE FROM position_snapshots
WHERE trade_id IN (
    SELECT trade_id FROM trades WHERE status = 'CLOSED'
)
AND snapshot_time < datetime('now', '-30 days');
