-- Add explicit plan selection to users
-- Plan is separate from derived tier: user picks their intent,
-- system enforces the requirements.
ALTER TABLE users ADD COLUMN plan TEXT NOT NULL DEFAULT 'general';

-- Migrate existing users: broker → ideal, broker+llm → rockstar
UPDATE users
SET plan = CASE
    WHEN id IN (
        SELECT DISTINCT u.id FROM users u
        JOIN user_broker_tokens ubt ON ubt.user_id = u.id
        JOIN user_llm_keys ulk ON ulk.user_id = u.id
    ) THEN 'rockstar'
    WHEN id IN (
        SELECT DISTINCT user_id FROM user_broker_tokens
    ) THEN 'ideal'
    ELSE 'general'
END;

PRAGMA user_version = 7;
