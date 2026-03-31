"""Admin broker token management.

Stores and retrieves the global admin Kite access token used for
market data requests when users don't have their own broker linked.
"""

import logging
import time
from typing import Optional

from services.db import get_conn

logger = logging.getLogger(__name__)

# In-memory cache to avoid repeated DB reads
_cache: dict = {"token": None, "fetched_at": 0}
_CACHE_TTL = 60  # seconds


def get_admin_broker_token(broker: str = "kite") -> Optional[str]:
    """Fetch the currently active admin broker token. Cached for 60s."""
    now = time.time()
    if _cache["token"] and (now - _cache["fetched_at"]) < _CACHE_TTL:
        return _cache["token"]

    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT access_token FROM admin_broker_tokens "
            "WHERE broker = ? AND is_active = TRUE "
            "ORDER BY created_at DESC LIMIT 1",
            (broker,),
        ).fetchone()
        token = row["access_token"] if row else None
        _cache["token"] = token
        _cache["fetched_at"] = now
        return token
    finally:
        conn.close()


def set_admin_broker_token(
    user_id: int,
    access_token: str,
    broker: str = "kite",
) -> None:
    """Deactivate previous admin tokens and store a new one."""
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE admin_broker_tokens SET is_active = FALSE WHERE broker = ?",
            (broker,),
        )
        conn.execute(
            "INSERT INTO admin_broker_tokens (broker, access_token, set_by_user_id) "
            "VALUES (?, ?, ?)",
            (broker, access_token, user_id),
        )
        conn.commit()
        # Invalidate cache
        _cache["token"] = access_token
        _cache["fetched_at"] = time.time()
        logger.info("[AdminToken] New admin broker token set by user %s", user_id)
    finally:
        conn.close()


def is_admin_token_valid(broker: str = "kite") -> bool:
    """Test whether the current admin broker token is valid."""
    token = get_admin_broker_token(broker)
    if not token:
        return False
    try:
        from broker import get_broker
        b = get_broker(token)
        b.profile()
        return True
    except Exception:
        return False
