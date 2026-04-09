"""Redis L2 cache with graceful fallback.

If Redis is not configured or is down every operation silently returns
None / False — callers must handle None as a cache miss.

Cache key scheme:
    ohlcv:{instrument_token}:{YYYY-MM-DD}    TTL 86400 (24h)  — DataFrame (pickle)
    screener:{symbol}                         TTL 21600 (6h)   — JSON dict
    llm:{pipeline}:{sha256(prompt)[:16]}:{YYYY-MM-DD}
                                              TTL 86400 (24h)  — raw LLM string

Usage:
    from services.cache_service import cache_get, cache_set

    raw = cache_get(key)                # returns bytes or None
    cache_set(key, value, ttl=86400)    # value is bytes
    cache_delete(key)
"""

import hashlib
import logging
import pickle
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)

_client = None
_init_done = False


def _get_client():
    """Lazy Redis client initialisation. Returns None if Redis is not configured."""
    global _client, _init_done
    if _init_done:
        return _client
    _init_done = True
    try:
        from config import REDIS_URL
        if not REDIS_URL:
            return None
        import redis
        _client = redis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=2)
        _client.ping()
        logger.info("[Cache] Redis connected at %s", REDIS_URL)
    except Exception as exc:
        logger.warning("[Cache] Redis unavailable — running without L2 cache: %s", exc)
        _client = None
    return _client


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def cache_get(key: str) -> Optional[bytes]:
    """Return raw bytes from Redis, or None on miss / error."""
    r = _get_client()
    if r is None:
        return None
    try:
        return r.get(key)
    except Exception as exc:
        logger.debug("[Cache] GET failed for %s: %s", key, exc)
        return None


def cache_set(key: str, value: bytes, ttl: int = 86400) -> bool:
    """Store bytes in Redis. Returns True on success, False otherwise."""
    r = _get_client()
    if r is None:
        return False
    try:
        r.setex(key, ttl, value)
        return True
    except Exception as exc:
        logger.debug("[Cache] SET failed for %s: %s", key, exc)
        return False


def cache_delete(key: str) -> bool:
    """Delete a key from Redis."""
    r = _get_client()
    if r is None:
        return False
    try:
        r.delete(key)
        return True
    except Exception as exc:
        logger.debug("[Cache] DEL failed for %s: %s", key, exc)
        return False


# ---------------------------------------------------------------------------
# Typed helpers
# ---------------------------------------------------------------------------

def ohlcv_cache_key(instrument_token: int) -> str:
    return f"ohlcv:{instrument_token}:{date.today().isoformat()}"


def screener_cache_key(symbol: str) -> str:
    return f"screener:{symbol}"


def llm_cache_key(pipeline: str, prompt: str) -> str:
    digest = hashlib.sha256(prompt.encode()).hexdigest()[:16]
    return f"llm:{pipeline}:{digest}:{date.today().isoformat()}"


def get_dataframe(key: str):
    """Return a cached DataFrame (unpickled) or None."""
    raw = cache_get(key)
    if raw is None:
        return None
    try:
        return pickle.loads(raw)
    except Exception:
        return None


def set_dataframe(key: str, df, ttl: int = 86400) -> bool:
    """Pickle a DataFrame and store it in Redis."""
    try:
        return cache_set(key, pickle.dumps(df), ttl=ttl)
    except Exception:
        return False
