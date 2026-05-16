"""SQLite online backup with optional S3 off-site replication.

Uses the SQLite backup API (non-locking, safe during live traffic).
Retains the last 30 daily backups locally and uploads to S3 when
S3_BACKUP_BUCKET is set in the environment.

Can be run as a standalone script or called from APScheduler.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from config import DB_PATH, BACKUP_DIR, S3_BACKUP_BUCKET, S3_BACKUP_PREFIX

logger = logging.getLogger(__name__)

MAX_LOCAL_BACKUPS = 30


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
        logger.info("[Backup] Created: %s (%d bytes)", backup_path, backup_path.stat().st_size)
    except Exception as e:
        logger.error("[Backup] Failed to create backup: %s", e)
        return None

    # Off-site: upload to S3 if configured
    if S3_BACKUP_BUCKET:
        _upload_to_s3(backup_path, timestamp)

    # Prune old local backups
    backups = sorted(BACKUP_DIR.glob("cognicap_*.db"), reverse=True)
    for old in backups[MAX_LOCAL_BACKUPS:]:
        try:
            old.unlink()
            logger.info("[Backup] Pruned local: %s", old.name)
        except Exception as e:
            logger.warning("[Backup] Could not delete %s: %s", old.name, e)

    return str(backup_path)


def _upload_to_s3(backup_path: Path, timestamp: str) -> None:
    """Upload a backup file to S3. No-ops gracefully if boto3 is unavailable."""
    try:
        import boto3
        from config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
    except ImportError:
        logger.warning("[Backup] boto3 not installed — skipping S3 upload")
        return

    s3_key = f"{S3_BACKUP_PREFIX}/cognicap_{timestamp}.db"
    try:
        session_kwargs = {"region_name": AWS_DEFAULT_REGION}
        if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
            session_kwargs["aws_access_key_id"] = AWS_ACCESS_KEY_ID
            session_kwargs["aws_secret_access_key"] = AWS_SECRET_ACCESS_KEY

        s3 = boto3.client("s3", **session_kwargs)
        s3.upload_file(str(backup_path), S3_BACKUP_BUCKET, s3_key)
        logger.info("[Backup] Uploaded to s3://%s/%s", S3_BACKUP_BUCKET, s3_key)

        # Prune S3 objects older than 90 days
        _prune_s3_backups(s3)
    except Exception as e:
        logger.error("[Backup] S3 upload failed: %s", e)


def _prune_s3_backups(s3_client, max_keys: int = 90) -> None:
    """Delete S3 backup objects beyond the retention limit (oldest first)."""
    from config import S3_BACKUP_BUCKET, S3_BACKUP_PREFIX
    try:
        resp = s3_client.list_objects_v2(Bucket=S3_BACKUP_BUCKET, Prefix=S3_BACKUP_PREFIX + "/cognicap_")
        objects = sorted(resp.get("Contents", []), key=lambda o: o["Key"])
        to_delete = objects[:-max_keys] if len(objects) > max_keys else []
        for obj in to_delete:
            s3_client.delete_object(Bucket=S3_BACKUP_BUCKET, Key=obj["Key"])
            logger.info("[Backup] Pruned S3 object: %s", obj["Key"])
    except Exception as e:
        logger.warning("[Backup] S3 pruning failed: %s", e)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_backup()
    if result:
        print(f"Backup created: {result}")
    else:
        print("Backup failed")
