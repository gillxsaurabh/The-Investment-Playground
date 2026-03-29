"""Authentication service — JWT tokens, password hashing, user CRUD.

Pure business logic, no Flask dependencies.
"""

import hashlib
import logging
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import bcrypt
import jwt

from config import JWT_SECRET, JWT_ACCESS_EXPIRY_MINUTES, JWT_REFRESH_EXPIRY_DAYS
from services.db import get_conn

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

def create_access_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=JWT_ACCESS_EXPIRY_MINUTES),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def create_refresh_token(user_id: int) -> Tuple[str, str]:
    """Create a refresh token. Returns (raw_token, token_hash)."""
    raw_token = secrets.token_urlsafe(48)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    return raw_token, token_hash


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        if payload.get("type") != "access":
            return None
        # Convert sub back to int
        payload["sub"] = int(payload["sub"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ---------------------------------------------------------------------------
# User CRUD
# ---------------------------------------------------------------------------

def create_user(email: str, password: str, name: str) -> Dict[str, Any]:
    """Register a new user. Raises ValueError if email taken."""
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO users (email, password_hash, name) VALUES (?, ?, ?)",
            (email.lower().strip(), hash_password(password), name.strip()),
        )
        conn.commit()
        user_id = conn.execute(
            "SELECT id FROM users WHERE email = ?", (email.lower().strip(),)
        ).fetchone()["id"]
        return {"id": user_id, "email": email.lower().strip(), "name": name.strip()}
    except sqlite3.IntegrityError:
        raise ValueError("Email already registered")
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Verify email + password. Returns user dict or None."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, email, password_hash, name, is_active FROM users WHERE email = ?",
            (email.lower().strip(),),
        ).fetchone()
        if not row:
            return None
        if not row["is_active"]:
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        return {"id": row["id"], "email": row["email"], "name": row["name"]}
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, email, name, created_at, email_verified, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Password management
# ---------------------------------------------------------------------------

def change_password(user_id: int, current_password: str, new_password: str) -> bool:
    """Change a user's password. Verifies the current password first.

    Revokes all refresh tokens so existing sessions are invalidated.
    Returns True on success, raises ValueError on failure.
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not row:
            raise ValueError("User not found")
        if not verify_password(current_password, row["password_hash"]):
            raise ValueError("Current password is incorrect")
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(new_password), user_id),
        )
        conn.commit()
    finally:
        conn.close()

    revoke_all_user_tokens(user_id)
    return True


def create_password_reset_token(email: str) -> Optional[str]:
    """Create a time-limited password reset token.

    Returns the raw token (to be sent to user), or None if the email
    doesn't exist. Always returns in constant time to prevent enumeration.
    """
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE email = ? AND is_active = 1",
            (email.lower().strip(),),
        ).fetchone()
        if not row:
            return None

        raw_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        expires_at = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

        conn.execute(
            "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
            (row["id"], token_hash, expires_at),
        )
        conn.commit()
        return raw_token
    finally:
        conn.close()


def validate_reset_token(raw_token: str) -> Optional[int]:
    """Validate a password reset token. Returns user_id or None."""
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT user_id, expires_at, used FROM password_reset_tokens WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        if not row or row["used"]:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            return None
        return row["user_id"]
    finally:
        conn.close()


def reset_password(raw_token: str, new_password: str) -> bool:
    """Reset a user's password using a valid reset token.

    Marks the token as used and revokes all refresh tokens.
    Returns True on success, raises ValueError on failure.
    """
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    user_id = validate_reset_token(raw_token)
    if user_id is None:
        raise ValueError("Invalid or expired reset token")

    conn = get_conn()
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(new_password), user_id),
        )
        conn.execute(
            "UPDATE password_reset_tokens SET used = 1 WHERE token_hash = ?",
            (token_hash,),
        )
        conn.commit()
    finally:
        conn.close()

    revoke_all_user_tokens(user_id)
    return True


# ---------------------------------------------------------------------------
# Refresh token persistence
# ---------------------------------------------------------------------------

def store_refresh_token(user_id: int, token_hash: str) -> None:
    expires_at = datetime.now(timezone.utc) + timedelta(days=JWT_REFRESH_EXPIRY_DAYS)
    conn = get_conn()
    try:
        conn.execute(
            "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
            (user_id, token_hash, expires_at.isoformat()),
        )
        conn.commit()
    finally:
        conn.close()


def validate_refresh_token(raw_token: str) -> Optional[int]:
    """Validate a refresh token. Returns user_id or None."""
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT user_id, expires_at, revoked FROM refresh_tokens WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()
        if not row or row["revoked"]:
            return None
        expires_at = datetime.fromisoformat(row["expires_at"])
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires_at:
            return None
        return row["user_id"]
    finally:
        conn.close()


def revoke_refresh_token(raw_token: str) -> None:
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE refresh_tokens SET revoked = TRUE WHERE token_hash = ?",
            (token_hash,),
        )
        conn.commit()
    finally:
        conn.close()


def revoke_all_user_tokens(user_id: int) -> None:
    conn = get_conn()
    try:
        conn.execute(
            "UPDATE refresh_tokens SET revoked = TRUE WHERE user_id = ?",
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Broker token management
# ---------------------------------------------------------------------------

def link_broker_token(
    user_id: int,
    access_token: str,
    broker: str = "kite",
    broker_user_id: str = None,
    broker_user_name: str = None,
    broker_email: str = None,
) -> None:
    """Store or update a user's broker access token."""
    conn = get_conn()
    try:
        conn.execute(
            """INSERT INTO user_broker_tokens
                (user_id, broker, access_token, broker_user_id, broker_user_name, broker_email)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, broker)
            DO UPDATE SET
                access_token = excluded.access_token,
                broker_user_id = excluded.broker_user_id,
                broker_user_name = excluded.broker_user_name,
                broker_email = excluded.broker_email,
                linked_at = datetime('now')
            """,
            (user_id, broker, access_token, broker_user_id, broker_user_name, broker_email),
        )
        conn.commit()
    finally:
        conn.close()


def get_broker_token(user_id: int, broker: str = "kite") -> Optional[str]:
    """Get the stored broker access token for a user."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT access_token FROM user_broker_tokens WHERE user_id = ? AND broker = ?",
            (user_id, broker),
        ).fetchone()
        return row["access_token"] if row else None
    finally:
        conn.close()


def get_broker_info(user_id: int, broker: str = "kite") -> Optional[Dict[str, Any]]:
    """Get full broker link info for a user."""
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM user_broker_tokens WHERE user_id = ? AND broker = ?",
            (user_id, broker),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
