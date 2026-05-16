-- Migration 010: Schema hardening
-- Adds CHECK constraints, fixes ON DELETE behaviour, and fills missing indexes.
-- SQLite does not support adding CHECK constraints or altering FKs via ALTER TABLE,
-- so we use trigger-based enforcement where the column already exists, and
-- recreate tables only where structurally required (none needed here — we use
-- triggers + new tables for constraint enforcement going forward).

PRAGMA user_version = 10;

-- -----------------------------------------------------------------------
-- 1. Triggers for enum validation on existing tables
--    (Equivalent to CHECK constraints on columns that can't be altered)
-- -----------------------------------------------------------------------

-- scans.status: running | completed | failed | cancelled
CREATE TRIGGER IF NOT EXISTS trg_scans_status_insert
BEFORE INSERT ON scans
WHEN NEW.status NOT IN ('running', 'completed', 'failed', 'cancelled')
BEGIN
    SELECT RAISE(ABORT, 'Invalid scans.status value');
END;

CREATE TRIGGER IF NOT EXISTS trg_scans_status_update
BEFORE UPDATE OF status ON scans
WHEN NEW.status NOT IN ('running', 'completed', 'failed', 'cancelled')
BEGIN
    SELECT RAISE(ABORT, 'Invalid scans.status value');
END;

-- trades.status: OPEN | CLOSED
CREATE TRIGGER IF NOT EXISTS trg_trades_status_insert
BEFORE INSERT ON trades
WHEN NEW.status NOT IN ('OPEN', 'CLOSED')
BEGIN
    SELECT RAISE(ABORT, 'Invalid trades.status value');
END;

CREATE TRIGGER IF NOT EXISTS trg_trades_status_update
BEFORE UPDATE OF status ON trades
WHEN NEW.status NOT IN ('OPEN', 'CLOSED')
BEGIN
    SELECT RAISE(ABORT, 'Invalid trades.status value');
END;

-- trades.entry_status: PENDING | FILLED | FAILED
CREATE TRIGGER IF NOT EXISTS trg_trades_entry_status_insert
BEFORE INSERT ON trades
WHEN NEW.entry_status IS NOT NULL
    AND NEW.entry_status NOT IN ('PENDING', 'FILLED', 'FAILED')
BEGIN
    SELECT RAISE(ABORT, 'Invalid trades.entry_status value');
END;

-- trades.trading_mode: simulator | live
CREATE TRIGGER IF NOT EXISTS trg_trades_trading_mode_insert
BEFORE INSERT ON trades
WHEN NEW.trading_mode IS NOT NULL
    AND NEW.trading_mode NOT IN ('simulator', 'live')
BEGIN
    SELECT RAISE(ABORT, 'Invalid trades.trading_mode value');
END;

-- scan_candidates score range enforcement
CREATE TRIGGER IF NOT EXISTS trg_scan_candidates_ai_conviction
BEFORE INSERT ON scan_candidates
WHEN NEW.ai_conviction IS NOT NULL
    AND (NEW.ai_conviction < 1 OR NEW.ai_conviction > 10)
BEGIN
    SELECT RAISE(ABORT, 'ai_conviction must be between 1 and 10');
END;

CREATE TRIGGER IF NOT EXISTS trg_scan_candidates_composite_score
BEFORE INSERT ON scan_candidates
WHEN NEW.composite_score IS NOT NULL
    AND (NEW.composite_score < 0 OR NEW.composite_score > 100)
BEGIN
    SELECT RAISE(ABORT, 'composite_score must be between 0 and 100');
END;

CREATE TRIGGER IF NOT EXISTS trg_scan_candidates_news_sentiment
BEFORE INSERT ON scan_candidates
WHEN NEW.news_sentiment IS NOT NULL
    AND (NEW.news_sentiment < 1 OR NEW.news_sentiment > 5)
BEGIN
    SELECT RAISE(ABORT, 'news_sentiment must be between 1 and 5');
END;

-- -----------------------------------------------------------------------
-- 2. ON DELETE CASCADE for password_reset_tokens and admin_broker_tokens
--    SQLite requires recreating the table to change FK behaviour.
-- -----------------------------------------------------------------------

-- password_reset_tokens: missing ON DELETE CASCADE → users
CREATE TABLE IF NOT EXISTS password_reset_tokens_v2 (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT    NOT NULL UNIQUE,
    expires_at  TEXT    NOT NULL,
    used        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

INSERT OR IGNORE INTO password_reset_tokens_v2
    SELECT id, user_id, token_hash, expires_at, used, created_at
    FROM password_reset_tokens;

DROP TABLE password_reset_tokens;
ALTER TABLE password_reset_tokens_v2 RENAME TO password_reset_tokens;

CREATE INDEX IF NOT EXISTS idx_password_reset_user
    ON password_reset_tokens(user_id);

-- admin_broker_tokens: missing ON DELETE CASCADE → users
CREATE TABLE IF NOT EXISTS admin_broker_tokens_v2 (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    broker          TEXT    NOT NULL DEFAULT 'kite',
    access_token    TEXT    NOT NULL,
    set_by_user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    expires_at      DATETIME,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    encrypted       BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT OR IGNORE INTO admin_broker_tokens_v2
    SELECT id, broker, access_token, set_by_user_id, created_at, expires_at, is_active,
           COALESCE(encrypted, FALSE)
    FROM admin_broker_tokens;

DROP TABLE admin_broker_tokens;
ALTER TABLE admin_broker_tokens_v2 RENAME TO admin_broker_tokens;

CREATE INDEX IF NOT EXISTS idx_admin_broker_active ON admin_broker_tokens(broker, is_active);

-- -----------------------------------------------------------------------
-- 3. Missing indexes
-- -----------------------------------------------------------------------

-- Partial index for open trades per user (most common query pattern)
CREATE INDEX IF NOT EXISTS idx_trades_open_by_user
    ON trades(user_id)
    WHERE status = 'OPEN';

-- scan_candidates: solo reached_final_shortlist filter
CREATE INDEX IF NOT EXISTS idx_scan_candidates_shortlist_solo
    ON scan_candidates(reached_final_shortlist);

-- account_snapshots: query by trade_id
CREATE INDEX IF NOT EXISTS idx_account_snapshots_trade_id
    ON account_snapshots(trade_id);
