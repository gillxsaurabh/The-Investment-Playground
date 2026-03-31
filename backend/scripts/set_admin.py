#!/usr/bin/env python3
"""Promote a user to admin by email.

Usage:
    cd backend && ./venv/bin/python3 scripts/set_admin.py <email>
"""

import sys
from pathlib import Path

# Add backend root to path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.db import get_conn, init_db


def set_admin(email: str) -> None:
    init_db()
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT id, email, is_admin FROM users WHERE email = ?",
            (email.lower().strip(),),
        ).fetchone()
        if not row:
            print(f"Error: No user found with email '{email}'")
            sys.exit(1)
        if row["is_admin"]:
            print(f"User '{email}' is already an admin.")
            return
        conn.execute("UPDATE users SET is_admin = TRUE WHERE id = ?", (row["id"],))
        conn.commit()
        print(f"User '{email}' (id={row['id']}) promoted to admin.")
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/set_admin.py <email>")
        sys.exit(1)
    set_admin(sys.argv[1])
