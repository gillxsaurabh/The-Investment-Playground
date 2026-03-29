-- Migration 004: User analysis cache (replaces analysis_storage.json)
-- Stores per-user cached stock analysis results in SQLite for
-- thread-safe concurrent access.

PRAGMA user_version = 4;

CREATE TABLE IF NOT EXISTS user_analysis_cache (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    symbol      TEXT    NOT NULL,
    analysis_json TEXT  NOT NULL,
    saved_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(user_id, symbol)
);

CREATE INDEX IF NOT EXISTS idx_analysis_cache_user_symbol
    ON user_analysis_cache(user_id, symbol);
