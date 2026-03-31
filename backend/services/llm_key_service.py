"""Per-user LLM API key storage with Fernet encryption.

Keys are encrypted before storage and decrypted on retrieval.
The encryption key is derived from JWT_SECRET (or LLM_KEY_ENCRYPTION_SECRET
if separately configured).

Never return raw keys in API responses — only provider names.
"""

import base64
import hashlib
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Supported providers
VALID_PROVIDERS = {"gemini", "anthropic", "openai"}


def _get_cipher():
    """Build a Fernet cipher from the configured secret."""
    from cryptography.fernet import Fernet
    secret = os.getenv("LLM_KEY_ENCRYPTION_SECRET") or os.getenv("JWT_SECRET", "")
    if not secret:
        raise RuntimeError("JWT_SECRET or LLM_KEY_ENCRYPTION_SECRET must be set")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def store_llm_key(user_id: int, provider: str, api_key: str) -> None:
    """Encrypt and upsert a user's LLM API key."""
    from services.db import get_conn
    cipher = _get_cipher()
    encrypted = cipher.encrypt(api_key.encode()).decode()
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO user_llm_keys (user_id, provider, encrypted_key, updated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT (user_id, provider)
               DO UPDATE SET encrypted_key = excluded.encrypted_key,
                             updated_at = datetime('now')""",
            (user_id, provider, encrypted),
        )
        conn.commit()
        logger.info("[LLMKey] Stored %s key for user %s", provider, user_id)
    finally:
        conn.close()


def get_llm_key(user_id: int, provider: str) -> Optional[str]:
    """Retrieve and decrypt a user's LLM API key. Returns None if not set."""
    from services.db import get_conn
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT encrypted_key FROM user_llm_keys WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        ).fetchone()
        if not row:
            return None
        cipher = _get_cipher()
        return cipher.decrypt(row["encrypted_key"].encode()).decode()
    except Exception as e:
        logger.warning("[LLMKey] Failed to decrypt %s key for user %s: %s", provider, user_id, e)
        return None
    finally:
        conn.close()


def delete_llm_key(user_id: int, provider: str) -> bool:
    """Remove a user's LLM API key. Returns True if a row was deleted."""
    from services.db import get_conn
    conn = get_conn()
    try:
        cursor = conn.execute(
            "DELETE FROM user_llm_keys WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_user_llm_providers(user_id: int) -> list:
    """Return list of providers for which the user has stored keys."""
    from services.db import get_conn
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT provider FROM user_llm_keys WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        return [row["provider"] for row in rows]
    finally:
        conn.close()


def validate_llm_key(provider: str, api_key: str) -> bool:
    """Test a key with a minimal API call. Returns True if valid."""
    try:
        if provider == "gemini":
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel("gemini-2.0-flash")
            model.generate_content("ping", generation_config={"max_output_tokens": 1})
            return True
        elif provider == "anthropic":
            from anthropic import Anthropic
            client = Anthropic(api_key=api_key)
            client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        elif provider == "openai":
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            client.models.list()
            return True
    except Exception as e:
        logger.info("[LLMKey] Validation failed for %s: %s", provider, str(e)[:100])
    return False
