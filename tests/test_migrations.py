"""Tests for pycopg.migrations module."""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pycopg.migrations import Migration, Migrator
from pycopg.exceptions import MigrationError


class TestMigration:
    """Tests for Migration class."""

    def test_parse_filename_basic(self, temp_migrations_dir):
        """Test parsing basic migration filename."""
        path = temp_migrations_dir / "001_create_users.sql"
        path.write_text("CREATE TABLE users (id INT);")

        migration = Migration(path)
        assert migration.version == 1
        assert migration.name == "create_users"
        assert migration.filename == "001_create_users.sql"

    def test_parse_filename_four_digits(self, temp_migrations_dir):
        """Test parsing 4-digit version."""
        path = temp_migrations_dir / "0001_init.sql"
        path.write_text("SELECT 1;")

        migration = Migration(path)
        assert migration.version == 1
        assert migration.name == "init"

    def test_parse_filename_large_version(self, temp_migrations_dir):
        """Test parsing large version number."""
        path = temp_migrations_dir / "999_final.sql"
        path.write_text("SELECT 1;")

        migration = Migration(path)
        assert migration.version == 999
        assert migration.name == "final"

    def test_parse_filename_underscores_in_name(self, temp_migrations_dir):
        """Test parsing name with underscores."""
        path = temp_migrations_dir / "005_add_user_email_index.sql"
        path.write_text("SELECT 1;")

        migration = Migration(path)
        assert migration.version == 5
        assert migration.name == "add_user_email_index"

    def test_parse_filename_invalid_no_underscore(self, temp_migrations_dir):
        """Test invalid filename without underscore."""
        path = temp_migrations_dir / "001createusers.sql"
        path.write_text("SELECT 1;")

        with pytest.raises(MigrationError) as exc:
            Migration(path)
        assert "Invalid migration filename" in str(exc.value)

    def test_parse_filename_invalid_no_number(self, temp_migrations_dir):
        """Test invalid filename without version number."""
        path = temp_migrations_dir / "create_users.sql"
        path.write_text("SELECT 1;")

        with pytest.raises(MigrationError) as exc:
            Migration(path)
        assert "Invalid migration filename" in str(exc.value)

    def test_parse_filename_invalid_extension(self, temp_migrations_dir):
        """Test invalid filename with wrong extension."""
        path = temp_migrations_dir / "001_create_users.txt"
        path.write_text("SELECT 1;")

        with pytest.raises(MigrationError) as exc:
            Migration(path)
        assert "Invalid migration filename" in str(exc.value)

    def test_sql_property(self, temp_migrations_dir):
        """Test reading SQL content."""
        path = temp_migrations_dir / "001_test.sql"
        sql_content = "CREATE TABLE test (id SERIAL PRIMARY KEY);"
        path.write_text(sql_content)

        migration = Migration(path)
        assert migration.sql == sql_content

    def test_repr(self, temp_migrations_dir):
        """Test string representation."""
        path = temp_migrations_dir / "042_add_index.sql"
        path.write_text("SELECT 1;")

        migration = Migration(path)
        assert repr(migration) == "Migration(042_add_index)"


class TestMigrator:
    """Tests for Migrator class."""

    def test_init_valid_directory(self, sample_migrations):
        """Test initialization with valid directory."""
        db = MagicMock()
        migrator = Migrator(db, sample_migrations)
        assert migrator.migrations_dir == sample_migrations
        assert migrator.table == "schema_migrations"

    def test_init_custom_table(self, sample_migrations):
        """Test initialization with custom table name."""
        db = MagicMock()
        migrator = Migrator(db, sample_migrations, table="my_migrations")
        assert migrator.table == "my_migrations"

    def test_init_invalid_directory(self):
        """Test initialization with non-existent directory."""
        db = MagicMock()
        with pytest.raises(MigrationError) as exc:
            Migrator(db, "/nonexistent/path")
        assert "not found" in str(exc.value)

    def test_ensure_table(self, sample_migrations):
        """Test migrations table creation."""
        db = MagicMock()
        db.execute = MagicMock(return_value=[])

        migrator = Migrator(db, sample_migrations)
        migrator._ensure_table()

        db.execute.assert_called()
        call_args = db.execute.call_args[0][0]
        assert "CREATE TABLE IF NOT EXISTS" in call_args
        assert "schema_migrations" in call_args

    def test_get_migrations(self, sample_migrations):
        """Test getting all migration files."""
        db = MagicMock()
        migrator = Migrator(db, sample_migrations)

        migrations = migrator._get_migrations()
        assert len(migrations) == 3
        assert migrations[0].version == 1
        assert migrations[1].version == 2
        assert migrations[2].version == 3

    def test_get_migrations_sorted(self, temp_migrations_dir):
        """Test migrations are sorted by version."""
        # Create out of order
        (temp_migrations_dir / "003_third.sql").write_text("SELECT 3;")
        (temp_migrations_dir / "001_first.sql").write_text("SELECT 1;")
        (temp_migrations_dir / "002_second.sql").write_text("SELECT 2;")

        db = MagicMock()
        migrator = Migrator(db, temp_migrations_dir)

        migrations = migrator._get_migrations()
        versions = [m.version for m in migrations]
        assert versions == [1, 2, 3]

    def test_get_migrations_skips_invalid(self, temp_migrations_dir):
        """Test invalid files are skipped."""
        (temp_migrations_dir / "001_valid.sql").write_text("SELECT 1;")
        (temp_migrations_dir / "invalid.sql").write_text("SELECT 2;")
        (temp_migrations_dir / "002_also_valid.sql").write_text("SELECT 3;")

        db = MagicMock()
        migrator = Migrator(db, temp_migrations_dir)

        migrations = migrator._get_migrations()
        assert len(migrations) == 2

    def test_pending_all_pending(self, sample_migrations):
        """Test all migrations are pending when none applied."""
        db = MagicMock()
        db.execute = MagicMock(return_value=[])

        migrator = Migrator(db, sample_migrations)
        pending = migrator.pending()

        assert len(pending) == 3

    def test_pending_some_applied(self, sample_migrations):
        """Test pending excludes applied migrations."""
        db = MagicMock()
        db.execute = MagicMock(return_value=[{"version": 1}, {"version": 2}])

        migrator = Migrator(db, sample_migrations)
        pending = migrator.pending()

        assert len(pending) == 1
        assert pending[0].version == 3

    def test_pending_all_applied(self, sample_migrations):
        """Test no pending when all applied."""
        db = MagicMock()
        db.execute = MagicMock(return_value=[
            {"version": 1},
            {"version": 2},
            {"version": 3},
        ])

        migrator = Migrator(db, sample_migrations)
        pending = migrator.pending()

        assert len(pending) == 0

    def test_applied(self, sample_migrations):
        """Test getting applied migrations."""
        db = MagicMock()
        db.execute = MagicMock(return_value=[
            {"version": 1, "name": "create_users", "applied_at": "2024-01-01"},
            {"version": 2, "name": "add_email", "applied_at": "2024-01-02"},
        ])

        migrator = Migrator(db, sample_migrations)
        applied = migrator.applied()

        assert len(applied) == 2
        assert applied[0]["version"] == 1

    def test_migrate_all(self, sample_migrations):
        """Test migrating all pending."""
        db = MagicMock()
        cursor_mock = MagicMock()
        cursor_mock.__enter__ = MagicMock(return_value=cursor_mock)
        cursor_mock.__exit__ = MagicMock(return_value=False)

        db.execute = MagicMock(return_value=[])
        db.cursor = MagicMock(return_value=cursor_mock)

        migrator = Migrator(db, sample_migrations)
        applied = migrator.migrate()

        assert len(applied) == 3
        assert cursor_mock.execute.call_count == 6  # 3 migrations + 3 inserts

    def test_migrate_to_target(self, sample_migrations):
        """Test migrating to specific version."""
        db = MagicMock()
        cursor_mock = MagicMock()
        cursor_mock.__enter__ = MagicMock(return_value=cursor_mock)
        cursor_mock.__exit__ = MagicMock(return_value=False)

        db.execute = MagicMock(return_value=[])
        db.cursor = MagicMock(return_value=cursor_mock)

        migrator = Migrator(db, sample_migrations)
        applied = migrator.migrate(target=2)

        assert len(applied) == 2
        assert applied[0].version == 1
        assert applied[1].version == 2

    def test_migrate_none_pending(self, sample_migrations):
        """Test migrating when nothing pending."""
        db = MagicMock()
        db.execute = MagicMock(return_value=[
            {"version": 1},
            {"version": 2},
            {"version": 3},
        ])

        migrator = Migrator(db, sample_migrations)
        applied = migrator.migrate()

        assert len(applied) == 0

    def test_migrate_failure(self, sample_migrations):
        """Test migration failure raises MigrationError."""
        db = MagicMock()
        cursor_mock = MagicMock()
        cursor_mock.__enter__ = MagicMock(return_value=cursor_mock)
        cursor_mock.__exit__ = MagicMock(return_value=False)
        cursor_mock.execute = MagicMock(side_effect=Exception("SQL error"))

        db.execute = MagicMock(return_value=[])
        db.cursor = MagicMock(return_value=cursor_mock)

        migrator = Migrator(db, sample_migrations)

        with pytest.raises(MigrationError) as exc:
            migrator.migrate()
        assert "001_create_users failed" in str(exc.value)

    def test_extract_section_up(self, sample_migrations):
        """Test extracting UP section."""
        db = MagicMock()
        migrator = Migrator(db, sample_migrations)

        sql = """-- UP
CREATE TABLE test;

-- DOWN
DROP TABLE test;
"""
        up_sql = migrator._extract_section(sql, "UP")
        assert up_sql == "CREATE TABLE test;"

    def test_extract_section_down(self, sample_migrations):
        """Test extracting DOWN section."""
        db = MagicMock()
        migrator = Migrator(db, sample_migrations)

        sql = """-- UP
CREATE TABLE test;

-- DOWN
DROP TABLE test;
"""
        down_sql = migrator._extract_section(sql, "DOWN")
        assert down_sql == "DROP TABLE test;"

    def test_extract_section_case_insensitive(self, sample_migrations):
        """Test section extraction is case insensitive."""
        db = MagicMock()
        migrator = Migrator(db, sample_migrations)

        sql = """-- up
CREATE TABLE test;

-- down
DROP TABLE test;
"""
        up_sql = migrator._extract_section(sql, "UP")
        assert up_sql == "CREATE TABLE test;"

    def test_extract_section_not_found(self, sample_migrations):
        """Test extracting non-existent section."""
        db = MagicMock()
        migrator = Migrator(db, sample_migrations)

        sql = "CREATE TABLE test;"
        result = migrator._extract_section(sql, "DOWN")
        assert result is None

    def test_rollback_single(self, sample_migrations):
        """Test rolling back single migration."""
        db = MagicMock()
        cursor_mock = MagicMock()
        cursor_mock.__enter__ = MagicMock(return_value=cursor_mock)
        cursor_mock.__exit__ = MagicMock(return_value=False)

        # Return applied migrations
        db.execute = MagicMock(side_effect=[
            [],  # _ensure_table
            [{"version": 1, "name": "create_users", "applied_at": "2024-01-01"}],  # applied()
        ])
        db.cursor = MagicMock(return_value=cursor_mock)

        migrator = Migrator(db, sample_migrations)
        rolled_back = migrator.rollback()

        assert len(rolled_back) == 1
        assert rolled_back[0]["version"] == 1

    def test_rollback_multiple(self, sample_migrations):
        """Test rolling back multiple migrations."""
        db = MagicMock()
        cursor_mock = MagicMock()
        cursor_mock.__enter__ = MagicMock(return_value=cursor_mock)
        cursor_mock.__exit__ = MagicMock(return_value=False)

        db.execute = MagicMock(side_effect=[
            [],  # _ensure_table
            [
                {"version": 1, "name": "create_users", "applied_at": "2024-01-01"},
                {"version": 2, "name": "add_email", "applied_at": "2024-01-02"},
                {"version": 3, "name": "create_orders", "applied_at": "2024-01-03"},
            ],
        ])
        db.cursor = MagicMock(return_value=cursor_mock)

        migrator = Migrator(db, sample_migrations)
        rolled_back = migrator.rollback(steps=2)

        assert len(rolled_back) == 2
        # Should be in reverse order (3, 2)
        assert rolled_back[0]["version"] == 3
        assert rolled_back[1]["version"] == 2

    def test_rollback_none_applied(self, sample_migrations):
        """Test rollback when nothing applied."""
        db = MagicMock()
        db.execute = MagicMock(return_value=[])

        migrator = Migrator(db, sample_migrations)
        rolled_back = migrator.rollback()

        assert len(rolled_back) == 0

    def test_rollback_no_down_section(self, temp_migrations_dir):
        """Test rollback fails without DOWN section."""
        (temp_migrations_dir / "001_no_down.sql").write_text("CREATE TABLE test;")

        db = MagicMock()
        db.execute = MagicMock(side_effect=[
            [],  # _ensure_table
            [{"version": 1, "name": "no_down", "applied_at": "2024-01-01"}],
        ])

        migrator = Migrator(db, temp_migrations_dir)

        with pytest.raises(MigrationError) as exc:
            migrator.rollback()
        assert "No DOWN section" in str(exc.value)

    def test_status(self, sample_migrations):
        """Test getting migration status."""
        db = MagicMock()
        db.execute = MagicMock(side_effect=[
            [],  # _ensure_table for applied()
            [{"version": 1, "name": "create_users", "applied_at": "2024-01-01"}],  # applied()
            [],  # _ensure_table for pending()
            [{"version": 1}],  # _get_applied for pending()
        ])

        migrator = Migrator(db, sample_migrations)
        status = migrator.status()

        assert status["applied_count"] == 1
        assert status["pending_count"] == 2
        assert len(status["applied"]) == 1
        assert len(status["pending"]) == 2

    def test_create_migration(self, temp_migrations_dir):
        """Test creating new migration file."""
        db = MagicMock()
        migrator = Migrator(db, temp_migrations_dir)

        path = migrator.create("add_users_table")

        assert path.exists()
        assert path.name == "001_add_users_table.sql"
        content = path.read_text()
        assert "-- UP" in content
        assert "-- DOWN" in content
        assert "add_users_table" in content

    def test_create_migration_increments_version(self, sample_migrations):
        """Test new migration gets next version."""
        db = MagicMock()
        migrator = Migrator(db, sample_migrations)

        path = migrator.create("new_migration")

        assert path.name == "004_new_migration.sql"

    def test_create_migration_sanitizes_name(self, temp_migrations_dir):
        """Test migration name is sanitized."""
        db = MagicMock()
        migrator = Migrator(db, temp_migrations_dir)

        path = migrator.create("Add Users Table!")

        assert path.name == "001_add_users_table_.sql"

    def test_repr(self, sample_migrations):
        """Test string representation."""
        db = MagicMock()
        db.execute = MagicMock(return_value=[{"version": 1}])

        migrator = Migrator(db, sample_migrations)
        repr_str = repr(migrator)

        assert "Migrator" in repr_str
        assert "applied=" in repr_str
        assert "pending=" in repr_str
