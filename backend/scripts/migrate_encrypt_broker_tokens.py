#!/usr/bin/env python3
"""One-time migration script: encrypt existing plaintext broker tokens.

Run ONCE after deploying migration 008 and setting BROKER_TOKEN_ENCRYPTION_SECRET:

    cd backend
    BROKER_TOKEN_ENCRYPTION_SECRET=<secret> ./venv/bin/python3 scripts/migrate_encrypt_broker_tokens.py

The script is idempotent: rows already marked encrypted=TRUE are skipped.
"""

import sys
from pathlib import Path

# Ensure backend is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.db import get_conn
from services.broker_key_service import encrypt_broker_token, is_encryption_enabled


def migrate():
    if not is_encryption_enabled():
        print("ERROR: BROKER_TOKEN_ENCRYPTION_SECRET is not set. Aborting.")
        sys.exit(1)

    conn = get_conn()
    try:
        # --- user_broker_tokens ---
        rows = conn.execute(
            "SELECT id, access_token FROM user_broker_tokens WHERE encrypted = FALSE"
        ).fetchall()
        print(f"Found {len(rows)} unencrypted user broker token(s)")
        for row in rows:
            encrypted = encrypt_broker_token(row["access_token"])
            conn.execute(
                "UPDATE user_broker_tokens SET access_token = ?, encrypted = TRUE WHERE id = ?",
                (encrypted, row["id"]),
            )
        conn.commit()
        print(f"  Encrypted {len(rows)} user broker token(s)")

        # --- admin_broker_tokens ---
        admin_rows = conn.execute(
            "SELECT id, access_token FROM admin_broker_tokens WHERE encrypted = FALSE"
        ).fetchall()
        print(f"Found {len(admin_rows)} unencrypted admin broker token(s)")
        for row in admin_rows:
            encrypted = encrypt_broker_token(row["access_token"])
            conn.execute(
                "UPDATE admin_broker_tokens SET access_token = ?, encrypted = TRUE WHERE id = ?",
                (encrypted, row["id"]),
            )
        conn.commit()
        print(f"  Encrypted {len(admin_rows)} admin broker token(s)")

        print("Migration complete.")
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
