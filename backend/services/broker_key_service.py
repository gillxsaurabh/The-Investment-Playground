"""Broker access token encryption at rest.

Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
The cipher key is derived from BROKER_TOKEN_ENCRYPTION_SECRET.

Unlike the LLM key service, there is NO fallback to JWT_SECRET — broker tokens
authorise real-money trades and must always have their own dedicated secret.
If BROKER_TOKEN_ENCRYPTION_SECRET is not configured the service returns tokens
unencrypted (with a warning) so the app still boots in development; production
startup will be blocked by config.py:validate_config().
"""

import base64
import hashlib
import logging
import os

logger = logging.getLogger(__name__)

# Sentinel so we only warn once per process
_warned_no_secret: bool = False


def _get_broker_cipher():
    """Build a Fernet cipher from BROKER_TOKEN_ENCRYPTION_SECRET."""
    from cryptography.fernet import Fernet
    from config import BROKER_TOKEN_ENCRYPTION_SECRET

    if not BROKER_TOKEN_ENCRYPTION_SECRET:
        return None  # encryption disabled — warn at call site

    key = base64.urlsafe_b64encode(
        hashlib.sha256(BROKER_TOKEN_ENCRYPTION_SECRET.encode()).digest()
    )
    return Fernet(key)


def encrypt_broker_token(plaintext: str) -> str:
    """Encrypt a broker access token.  Returns ciphertext string.

    If BROKER_TOKEN_ENCRYPTION_SECRET is not configured, returns the plaintext
    unchanged (development mode) and logs a one-time warning.
    """
    global _warned_no_secret
    cipher = _get_broker_cipher()
    if cipher is None:
        if not _warned_no_secret:
            logger.warning(
                "[BrokerKey] BROKER_TOKEN_ENCRYPTION_SECRET not set — "
                "storing broker token in plaintext. Set this variable before production."
            )
            _warned_no_secret = True
        return plaintext
    return cipher.encrypt(plaintext.encode()).decode()


def decrypt_broker_token(ciphertext: str) -> str:
    """Decrypt a broker access token.  Returns plaintext string.

    Falls back to returning the value unchanged if:
      - BROKER_TOKEN_ENCRYPTION_SECRET is not configured (dev mode)
      - Decryption fails (e.g. key rotation) — logs a warning and returns empty string
    """
    cipher = _get_broker_cipher()
    if cipher is None:
        # Secret not set → token was stored in plaintext, return as-is
        return ciphertext
    try:
        return cipher.decrypt(ciphertext.encode()).decode()
    except Exception as e:
        logger.warning("[BrokerKey] Token decryption failed (key mismatch or corruption): %s", e)
        return ""


def is_encryption_enabled() -> bool:
    """Return True if BROKER_TOKEN_ENCRYPTION_SECRET is configured."""
    from config import BROKER_TOKEN_ENCRYPTION_SECRET
    return bool(BROKER_TOKEN_ENCRYPTION_SECRET)
