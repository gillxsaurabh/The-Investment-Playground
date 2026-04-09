-- Migration 008: Add encrypted flag to broker token tables
-- The actual token encryption is performed by scripts/migrate_encrypt_broker_tokens.py
-- This migration only adds the tracking column; run the Python script after upgrading.

ALTER TABLE user_broker_tokens
    ADD COLUMN encrypted BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE admin_broker_tokens
    ADD COLUMN encrypted BOOLEAN NOT NULL DEFAULT FALSE;

PRAGMA user_version = 8;
