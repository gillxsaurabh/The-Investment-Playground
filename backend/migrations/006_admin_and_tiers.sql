-- Migration 006: Admin broker tokens, per-user LLM keys, user tier flags
-- Supports API decoupling & user tier architecture

-- Global admin broker token for market data requests
CREATE TABLE IF NOT EXISTS admin_broker_tokens (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    broker          TEXT    NOT NULL DEFAULT 'kite',
    access_token    TEXT    NOT NULL,
    set_by_user_id  INTEGER NOT NULL REFERENCES users(id),
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    expires_at      DATETIME,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_admin_broker_active ON admin_broker_tokens(broker, is_active);

-- Per-user LLM API keys (encrypted via Fernet)
CREATE TABLE IF NOT EXISTS user_llm_keys (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider        TEXT    NOT NULL,
    encrypted_key   TEXT    NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, provider)
);
CREATE INDEX IF NOT EXISTS idx_user_llm_keys_user ON user_llm_keys(user_id);

-- Admin flag and onboarding tracking on users table
ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE;

-- Existing users with linked brokers skip onboarding
UPDATE users SET onboarding_completed = TRUE
WHERE id IN (SELECT user_id FROM user_broker_tokens);

PRAGMA user_version = 6;
