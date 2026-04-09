-- Migration 009: LLM usage tracking table

CREATE TABLE IF NOT EXISTS llm_usage (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    pipeline   TEXT    NOT NULL DEFAULT 'unknown',
    provider   TEXT    NOT NULL DEFAULT 'unknown',
    model      TEXT    NOT NULL DEFAULT 'unknown',
    input_tokens  INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd   REAL    NOT NULL DEFAULT 0.0,
    created_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_user_id    ON llm_usage(user_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_created_at ON llm_usage(created_at);
CREATE INDEX IF NOT EXISTS idx_llm_usage_pipeline   ON llm_usage(pipeline);

PRAGMA user_version = 9;
