"""
B3 atomicity regression tests for Migrator._apply and Migrator.rollback.

Decision D-06 form choice: real-DB integration tests.
Atomicity (BEGIN/COMMIT/ROLLBACK) is only observable against a real transactional
backend — mocks cannot simulate partial DDL commits, so all tests here connect to
the real PostgreSQL service provided by the CI (timescale/timescaledb-ha, Phase 9).

RED -> GREEN proof:
  Reverting the fix in pycopg/migrations.py — replacing
      ``with self.db.transaction() as conn:``
  back to the bare
      ``with self.db.cursor() as cur:``
  in ``_apply`` makes test_apply_failure_leaves_no_partial_trace FAIL:
  the probe table created by the first statement of the UP SQL persists after
  the second statement raises, and/or the version row is present in the
  migrations table, because without an explicit transaction the two statements
  are committed independently. The same revert makes
  test_rollback_failure_leaves_version_row_intact FAIL because the DELETE on
  the version row commits independently of the failing DOWN statement, leaving
  the row absent even though the schema change was not rolled back.

These tests pass on the fixed code where both pairs of statements are wrapped
in a single explicit ``self.db.transaction()``.
"""

import uuid

import pytest

from pycopg import Database
from pycopg.migrations import Migrator
from pycopg.exceptions import MigrationError


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _unique_suffix() -> str:
    """Return a short unique suffix to avoid table-name collisions across runs."""
    return uuid.uuid4().hex[:8]


@pytest.fixture
def atomicity_migrator(db_config, temp_migrations_dir):
    """Real-DB Migrator fixture with teardown that drops any probe tables."""
    db = Database(db_config)
    migrator = Migrator(db, temp_migrations_dir)

    # Track probe table names created during the test for cleanup
    migrator._probe_tables: list[str] = []

    yield migrator

    # Teardown: drop migrations table and all probe tables
    try:
        db.execute("DROP TABLE IF EXISTS schema_migrations CASCADE")
    except Exception:
        pass

    for tbl in migrator._probe_tables:
        try:
            db.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Test A — apply failure leaves no partial trace
# ---------------------------------------------------------------------------

class TestApplyAtomicity:
    """Test A (D-05/B3): a migration whose UP SQL fails mid-course leaves no
    partial schema and no version row in the migrations table."""

    def test_apply_failure_leaves_no_partial_trace(
        self, atomicity_migrator, temp_migrations_dir
    ):
        """
        A migration whose UP section has a valid first statement followed by
        a failing second statement must leave:
          - the table created by the first statement ABSENT (rolled back)
          - no version row in schema_migrations

        Without the explicit transaction wrap in _apply (the pre-fix state),
        the CREATE TABLE commits immediately and only the second statement rolls
        back, leaving the probe table present and possibly a version row.
        """
        suffix = _unique_suffix()
        probe_table = f"atomic_probe_{suffix}"
        atomicity_migrator._probe_tables.append(probe_table)

        # Write a migration with two UP statements:
        #   1. CREATE TABLE (would succeed on its own)
        #   2. INSERT with a missing column (always fails)
        migration_file = temp_migrations_dir / "001_atomic_test.sql"
        migration_file.write_text(f"""-- UP
CREATE TABLE {probe_table} (id SERIAL PRIMARY KEY, value TEXT);
INSERT INTO {probe_table} (missing_col) VALUES (1);

-- DOWN
DROP TABLE {probe_table};
""")

        # migrate() should raise MigrationError wrapping the INSERT failure
        with pytest.raises(MigrationError):
            atomicity_migrator.migrate()

        db = atomicity_migrator.db

        # Assert: probe table must NOT exist (CREATE TABLE rolled back)
        result = db.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s",
            [probe_table]
        )
        assert len(result) == 0, (
            f"Partial trace: table '{probe_table}' was NOT rolled back. "
            "This indicates _apply is not wrapping UP SQL + INSERT in one transaction."
        )

        # Assert: no version row must exist
        # _ensure_table may or may not have been called; query safely
        version_count_rows = db.execute(
            "SELECT count(*) AS cnt FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'schema_migrations'"
        )
        migrations_table_exists = (
            version_count_rows[0]["cnt"] > 0
            if version_count_rows
            else False
        )
        if migrations_table_exists:
            rows = db.execute(
                "SELECT count(*) AS cnt FROM schema_migrations WHERE version = %s",
                [1]
            )
            count = rows[0]["cnt"] if rows else 0
            assert count == 0, (
                "Partial trace: version row version=1 persists in schema_migrations "
                "after a failed migration. _apply must be atomic."
            )


# ---------------------------------------------------------------------------
# Test B — rollback failure leaves version row intact
# ---------------------------------------------------------------------------

class TestRollbackAtomicity:
    """Test B (D-05/B3): a failed rollback (DOWN SQL fails mid-course) leaves
    the version row STILL present and the schema unchanged.

    Without the explicit transaction wrap in rollback, the DELETE on the version
    row may commit independently of the failing DOWN statement, leaving the row
    absent even though the schema change was not reversed.
    """

    def test_rollback_failure_leaves_version_row_intact(
        self, atomicity_migrator, temp_migrations_dir
    ):
        suffix = _unique_suffix()
        probe_table = f"atomic_rb_{suffix}"
        atomicity_migrator._probe_tables.append(probe_table)

        # Step 1: apply a valid migration
        migration_file = temp_migrations_dir / "001_good_migration.sql"
        migration_file.write_text(f"""-- UP
CREATE TABLE {probe_table} (id SERIAL PRIMARY KEY, value TEXT);

-- DOWN
DROP TABLE {probe_table};
""")

        applied = atomicity_migrator.migrate()
        assert len(applied) == 1, "Expected 1 migration applied"

        db = atomicity_migrator.db

        # Confirm version row exists before rollback attempt
        rows_before = db.execute(
            "SELECT count(*) AS cnt FROM schema_migrations WHERE version = %s",
            [1]
        )
        assert rows_before[0]["cnt"] == 1, "Version row should exist after apply"

        # Step 2: overwrite migration with a DOWN section that fails mid-course:
        #   first statement is valid (ALTER TABLE), second is an invalid DROP.
        migration_file.write_text(f"""-- UP
CREATE TABLE {probe_table} (id SERIAL PRIMARY KEY, value TEXT);

-- DOWN
ALTER TABLE {probe_table} ADD COLUMN temp_col TEXT;
DROP TABLE nonexistent_table_{suffix}_xyz;
""")

        # rollback() should raise MigrationError from the failing DOWN SQL
        with pytest.raises(MigrationError):
            atomicity_migrator.rollback()

        # Assert: version row must STILL exist (DELETE was rolled back)
        rows_after = db.execute(
            "SELECT count(*) AS cnt FROM schema_migrations WHERE version = %s",
            [1]
        )
        assert rows_after[0]["cnt"] == 1, (
            "Version row was deleted even though rollback failed. "
            "This indicates rollback is not wrapping DOWN SQL + DELETE in one transaction."
        )

        # Assert: schema is intact — probe table should still exist
        schema_rows = db.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = %s",
            [probe_table]
        )
        assert len(schema_rows) == 1, (
            f"Table '{probe_table}' disappeared after a failed rollback. "
            "Schema should remain unchanged when rollback fails."
        )
