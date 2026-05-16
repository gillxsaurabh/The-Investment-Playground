-- Migration 012: Restore encrypted column to admin_broker_tokens
-- Migration 010 recreated the table without the encrypted column that was
-- added in migration 008, breaking set_admin_broker_token() inserts.

ALTER TABLE admin_broker_tokens ADD COLUMN encrypted BOOLEAN NOT NULL DEFAULT FALSE;

PRAGMA user_version = 12;
