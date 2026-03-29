-- CogniCap SQLite schema v2.0 — User management
PRAGMA user_version = 2;

CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT    NOT NULL UNIQUE COLLATE NOCASE,
    password_hash   TEXT    NOT NULL,
    name            TEXT    NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    email_verified  BOOLEAN NOT NULL DEFAULT FALSE,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE TABLE IF NOT EXISTS user_broker_tokens (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    broker          TEXT    NOT NULL DEFAULT 'kite',
    access_token    TEXT    NOT NULL,
    broker_user_id  TEXT,
    broker_user_name TEXT,
    broker_email    TEXT,
    linked_at       DATETIME NOT NULL DEFAULT (datetime('now')),
    expires_at      DATETIME,
    UNIQUE (user_id, broker)
);
CREATE INDEX IF NOT EXISTS idx_user_broker_tokens_user_id ON user_broker_tokens(user_id);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      TEXT    NOT NULL UNIQUE,
    expires_at      DATETIME NOT NULL,
    created_at      DATETIME NOT NULL DEFAULT (datetime('now')),
    revoked         BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash ON refresh_tokens(token_hash);
