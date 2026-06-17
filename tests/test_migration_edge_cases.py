"""
Migration rollback edge case tests (TEST-02).

All tests use real PostgreSQL and test edge cases in migration rollback:
- Deleted DOWN sections
- Deleted migration files
- SQL syntax errors in DOWN sections
- Empty rollback (no migrations applied)
- Multi-step rollback
"""

import pytest

from pycopg import Database
from pycopg.exceptions import MigrationError
from pycopg.migrations import Migrator


@pytest.fixture
def migrator(db_config, temp_migrations_dir):
    """Create a Migrator with real PostgreSQL and temp migrations dir.

    Ensures cleanup of migration table and test tables after each test.
    """
    db = Database(db_config)
    migrator = Migrator(db, temp_migrations_dir)

    yield migrator

    # Cleanup: drop migration table and any test tables
    try:
        db.execute("DROP TABLE IF EXISTS schema_migrations CASCADE")
        # Drop common test tables
        db.execute("DROP TABLE IF EXISTS test_rollback_del_down CASCADE")
        db.execute("DROP TABLE IF EXISTS test_rollback_del_file CASCADE")
        db.execute("DROP TABLE IF EXISTS test_rollback_syntax CASCADE")
        db.execute("DROP TABLE IF EXISTS test_multi_step_1 CASCADE")
        db.execute("DROP TABLE IF EXISTS test_multi_step_2 CASCADE")
        db.execute("DROP TABLE IF EXISTS test_multi_step_3 CASCADE")
    except Exception:
        pass  # Ignore cleanup errors


class TestMigrationRollbackEdgeCases:
    """Test migration rollback edge cases using real PostgreSQL."""

    def test_rollback_with_deleted_down_section(self, migrator, temp_migrations_dir):
        """Test rollback fails gracefully when DOWN section is deleted from migration file."""
        # Create migration with UP and DOWN
        migration_file = temp_migrations_dir / "001_test_rollback.sql"
        migration_file.write_text("""-- UP
CREATE TABLE test_rollback_del_down (
    id SERIAL PRIMARY KEY,
    name TEXT
);

-- DOWN
DROP TABLE test_rollback_del_down;
""")

        # Apply migration
        applied = migrator.migrate()
        assert len(applied) == 1

        # Verify table exists
        result = migrator.db.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = 'test_rollback_del_down'"
        )
        assert len(result) == 1

        # Rewrite file without DOWN section
        migration_file.write_text("""-- UP
CREATE TABLE test_rollback_del_down (
    id SERIAL PRIMARY KEY,
    name TEXT
);
""")

        # Attempt rollback - should fail with helpful error
        with pytest.raises(MigrationError) as exc_info:
            migrator.rollback()

        assert "No DOWN section" in str(exc_info.value)

        # Cleanup manually
        migrator.db.execute("DROP TABLE IF EXISTS test_rollback_del_down CASCADE")

    def test_rollback_with_deleted_migration_file(self, migrator, temp_migrations_dir):
        """Test rollback fails gracefully when migration file is deleted."""
        # Create and apply migration
        migration_file = temp_migrations_dir / "002_test_deleted_file.sql"
        migration_file.write_text("""-- UP
CREATE TABLE test_rollback_del_file (
    id SERIAL PRIMARY KEY
);

-- DOWN
DROP TABLE test_rollback_del_file;
""")

        applied = migrator.migrate()
        assert len(applied) == 1

        # Delete the migration file
        migration_file.unlink()

        # Attempt rollback - should fail with helpful error
        with pytest.raises(MigrationError) as exc_info:
            migrator.rollback()

        assert "not found" in str(exc_info.value).lower()

        # Cleanup manually
        migrator.db.execute("DROP TABLE IF EXISTS test_rollback_del_file CASCADE")

    def test_rollback_with_syntax_error_in_down(self, migrator, temp_migrations_dir):
        """Test rollback propagates SQL syntax error with context."""
        # Create migration with valid UP but invalid DOWN
        migration_file = temp_migrations_dir / "003_test_syntax_error.sql"
        migration_file.write_text("""-- UP
CREATE TABLE test_rollback_syntax (
    id SERIAL PRIMARY KEY
);

-- DOWN
DROP TABEL test_rollback_syntax;
""")  # Typo: TABEL instead of TABLE

        # Apply migration
        applied = migrator.migrate()
        assert len(applied) == 1

        # Attempt rollback - should fail with SQL error wrapped in MigrationError
        with pytest.raises(MigrationError) as exc_info:
            migrator.rollback()

        # Error should mention the migration and contain SQL context
        error_msg = str(exc_info.value).lower()
        assert "003_test_syntax_error" in error_msg or "rollback" in error_msg

        # Cleanup manually
        migrator.db.execute("DROP TABLE IF EXISTS test_rollback_syntax CASCADE")

    def test_rollback_when_no_migrations_applied(self, migrator, temp_migrations_dir):
        """Test rollback returns empty list gracefully when no migrations applied."""
        # Don't apply any migrations

        # Attempt rollback - should return empty list, not raise
        result = migrator.rollback()

        assert result == []
        assert isinstance(result, list)

    def test_rollback_multiple_steps(self, migrator, temp_migrations_dir):
        """Test rolling back multiple migrations with steps parameter."""
        # Create 3 migrations
        migrations = [
            (
                "001_first.sql",
                """-- UP
CREATE TABLE test_multi_step_1 (id SERIAL PRIMARY KEY);

-- DOWN
DROP TABLE test_multi_step_1;
""",
            ),
            (
                "002_second.sql",
                """-- UP
CREATE TABLE test_multi_step_2 (id SERIAL PRIMARY KEY);

-- DOWN
DROP TABLE test_multi_step_2;
""",
            ),
            (
                "003_third.sql",
                """-- UP
CREATE TABLE test_multi_step_3 (id SERIAL PRIMARY KEY);

-- DOWN
DROP TABLE test_multi_step_3;
""",
            ),
        ]

        for filename, content in migrations:
            (temp_migrations_dir / filename).write_text(content)

        # Apply all 3 migrations
        applied = migrator.migrate()
        assert len(applied) == 3

        # Verify all 3 applied
        applied_migrations = migrator.applied()
        assert len(applied_migrations) == 3

        # Rollback 2 steps
        rolled_back = migrator.rollback(steps=2)
        assert len(rolled_back) == 2

        # Verify only 1 migration remains
        remaining = migrator.applied()
        assert len(remaining) == 1
        assert remaining[0]["version"] == 1

        # Cleanup remaining
        migrator.rollback(steps=1)
