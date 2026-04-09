"""Shared Flask extensions — importable from routes without circular imports."""

import os

from flask import g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


def get_user_or_ip() -> str:
    """Rate-limit key: per-user when authenticated, otherwise per-IP."""
    user = getattr(g, "current_user", None)
    if user and isinstance(user, dict) and "id" in user:
        return f"user:{user['id']}"
    return get_remote_address()


_redis_url = os.getenv("REDIS_URL", "")
_storage_uri = _redis_url if _redis_url else "memory://"

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per minute"],
    storage_uri=_storage_uri,
)
