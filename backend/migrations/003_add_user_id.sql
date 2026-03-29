-- Migration 003: Add user_id to trades for multi-user isolation
PRAGMA user_version = 3;

ALTER TABLE trades ADD COLUMN user_id INTEGER REFERENCES users(id);
CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades(user_id);
CREATE INDEX IF NOT EXISTS idx_trades_user_status ON trades(user_id, status);
