"""SQLite online backup — safe to run while the application is serving requests.

Uses the SQLite backup API (non-locking) to create timestamped copies.
Retains the last 7 daily backups and deletes older ones.

Can be run as a standalone script or called from APScheduler.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from config import DB_PATH

logger = logging.getLogger(__name__)

BACKUP_DIR = Path(DB_PATH).parent.parent / "backups"
MAX_BACKUPS = 7


def run_backup() -> str | None:
    """Create a timestamped backup of the SQLite database.

    Returns the backup file path on success, or None on failure.
    """
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"cognicap_{timestamp}.db"

    try:
        src = sqlite3.connect(str(DB_PATH))
        dst = sqlite3.connect(str(backup_path))
        src.backup(dst)
        dst.close()
        src.close()
        logger.info("[Backup] Created: %s", backup_path)
    except Exception as e:
        logger.error("[Backup] Failed: %s", e)
        return None

    # Prune old backups
    backups = sorted(BACKUP_DIR.glob("cognicap_*.db"), reverse=True)
    for old in backups[MAX_BACKUPS:]:
        try:
            old.unlink()
            logger.info("[Backup] Pruned: %s", old.name)
        except Exception as e:
            logger.warning("[Backup] Could not delete %s: %s", old.name, e)

    return str(backup_path)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_backup()
    if result:
        print(f"Backup created: {result}")
    else:
        print("Backup failed")
