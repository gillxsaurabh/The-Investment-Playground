"""Migration ladder tests.

Verifies that every migration (001–011) can be applied sequentially
to a fresh database, producing the expected schema version and tables.
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

MIGRATION_FILES = [
    (1,  "001_initial.sql"),
    (2,  "002_users.sql"),
    (3,  "003_add_user_id.sql"),
    (4,  "004_analysis_cache.sql"),
    (5,  "005_password_reset.sql"),
    (6,  "006_admin_and_tiers.sql"),
    (7,  "007_user_plan.sql"),
    (8,  "008_encrypt_broker_tokens.sql"),
    (9,  "009_llm_usage.sql"),
    (10, "010_schema_hardening.sql"),
    (11, "011_consolidate_state.sql"),
]

# Tables that must exist at the given version (cumulative)
TABLES_AT_VERSION = {
    1: {"scans", "scan_candidates", "stock_analyses", "trades", "position_snapshots", "account_snapshots"},
    2: {"users", "user_broker_tokens", "refresh_tokens"},
    4: {"user_analysis_cache"},
    5: {"password_reset_tokens"},
    6: {"admin_broker_tokens", "user_llm_keys"},
    9: {"llm_usage"},
    11: {"simulator_accounts"},
}


@pytest.fixture
def fresh_db():
    """Yield a path to a fresh temporary SQLite database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    os.unlink(db_path)


def _get_tables(conn: sqlite3.Connection) -> set:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def _apply_migration(conn: sqlite3.Connection, sql_file: Path) -> None:
    sql = sql_file.read_text()
    conn.executescript(sql)
    conn.commit()


# ALTER TABLE ADD COLUMN migrations are inherently non-idempotent in SQLite —
# applying them twice will raise "duplicate column name". These are tested
# only for correct first-time application via test_full_migration_ladder.
_NON_IDEMPOTENT = {3, 6, 7, 8}


@pytest.mark.parametrize("target_version,filename", MIGRATION_FILES)
def test_each_migration_is_idempotent(fresh_db, target_version, filename):
    """Applying a migration twice should not raise an error (IF NOT EXISTS guards).

    Skipped for ALTER TABLE migrations that are non-idempotent by design.
    """
    if target_version in _NON_IDEMPOTENT:
        pytest.skip(f"Migration {target_version} uses ALTER TABLE — not idempotent by design")

    sql_file = MIGRATIONS_DIR / filename
    if not sql_file.exists():
        pytest.skip(f"Migration file not found: {filename}")

    conn = sqlite3.connect(fresh_db)
    conn.execute("PRAGMA foreign_keys = ON")

    # Apply all preceding migrations first
    for prev_version, prev_file in MIGRATION_FILES:
        if prev_version >= target_version:
            break
        prev_sql = MIGRATIONS_DIR / prev_file
        if prev_sql.exists():
            conn.executescript(prev_sql.read_text())
            conn.commit()

    # Apply the target migration twice — should not fail
    _apply_migration(conn, sql_file)
    _apply_migration(conn, sql_file)
    conn.close()


def test_full_migration_ladder(fresh_db):
    """Applying all migrations in order produces the correct final schema version and tables."""
    conn = sqlite3.connect(fresh_db)
    conn.execute("PRAGMA foreign_keys = ON")

    expected_tables: set = set()

    for target_version, filename in MIGRATION_FILES:
        sql_file = MIGRATIONS_DIR / filename
        if not sql_file.exists():
            pytest.skip(f"Migration file not found: {filename}")

        _apply_migration(conn, sql_file)

        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == target_version, (
            f"Expected user_version={target_version} after {filename}, got {version}"
        )

        if target_version in TABLES_AT_VERSION:
            expected_tables |= TABLES_AT_VERSION[target_version]
            tables = _get_tables(conn)
            missing = expected_tables - tables
            assert not missing, (
                f"After migration {target_version}, missing tables: {missing}"
            )

    # Final version check
    final_version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert final_version == 11

    # Foreign key validation — should return no violations
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    assert not violations, f"Foreign key violations after migrations: {violations}"

    conn.close()


def test_migration_validates_enum_triggers(fresh_db):
    """The status triggers from migration 010 should reject invalid values."""
    conn = sqlite3.connect(fresh_db)
    conn.execute("PRAGMA foreign_keys = ON")

    for _, filename in MIGRATION_FILES:
        sql_file = MIGRATIONS_DIR / filename
        if sql_file.exists():
            conn.executescript(sql_file.read_text())
            conn.commit()

    # Valid scan status should succeed
    conn.execute(
        "INSERT INTO scans (scan_id, started_at, gear, gear_label, universe, "
        "min_turnover, rsi_buy_limit, adx_min, trail_multiplier, fundamental_check, "
        "sector_5d_tolerance, min_volume_ratio) "
        "VALUES ('test_scan_1', datetime('now'), 3, 'Balanced', 'nifty100', "
        "1000000, 30, 20, 1.5, 'standard', -0.5, 0.7)"
    )
    conn.commit()

    # Invalid scan status should raise IntegrityError (trigger-based enforcement)
    with pytest.raises(sqlite3.IntegrityError, match="Invalid scans.status"):
        conn.execute(
            "UPDATE scans SET status = 'invalid_status' WHERE scan_id = 'test_scan_1'"
        )

    conn.close()
