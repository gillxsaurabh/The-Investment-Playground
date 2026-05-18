-- Migration 014: Widen trades.entry_status trigger for live trading
-- Adds PARTIAL, REJECTED, CANCELLED, TIMEOUT to the allowed set.
-- Drops and recreates both insert and update triggers.

PRAGMA user_version = 14;

DROP TRIGGER IF EXISTS trg_trades_entry_status_insert;
DROP TRIGGER IF EXISTS trg_trades_entry_status_update;

CREATE TRIGGER IF NOT EXISTS trg_trades_entry_status_insert
BEFORE INSERT ON trades
WHEN NEW.entry_status IS NOT NULL
    AND NEW.entry_status NOT IN ('PENDING', 'FILLED', 'PARTIAL', 'FAILED', 'REJECTED', 'CANCELLED', 'TIMEOUT', 'EXIT_PENDING')
BEGIN
    SELECT RAISE(ABORT, 'Invalid trades.entry_status value');
END;

CREATE TRIGGER IF NOT EXISTS trg_trades_entry_status_update
BEFORE UPDATE OF entry_status ON trades
WHEN NEW.entry_status IS NOT NULL
    AND NEW.entry_status NOT IN ('PENDING', 'FILLED', 'PARTIAL', 'FAILED', 'REJECTED', 'CANCELLED', 'TIMEOUT', 'EXIT_PENDING')
BEGIN
    SELECT RAISE(ABORT, 'Invalid trades.entry_status value');
END;
