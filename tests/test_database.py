"""Tests for pycopg.database module."""

from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
import tempfile

import pytest

from pycopg import Database, Config


class TestDatabaseInit:
    """Tests for Database initialization."""

    @patch("pycopg.database.psycopg")
    def test_init_with_config(self, mock_psycopg, config):
        """Test initialization with Config object."""
        db = Database(config)
        assert db.config == config

    @patch("pycopg.database.psycopg")
    @patch("pycopg.database.Config.from_env")
    def test_from_env(self, mock_from_env, mock_psycopg):
        """Test creating from environment."""
        mock_from_env.return_value = Config()

        db = Database.from_env()

        mock_from_env.assert_called_once()
        assert db.config is not None

    @patch("pycopg.database.psycopg")
    @patch("pycopg.database.Config.from_url")
    def test_from_url(self, mock_from_url, mock_psycopg):
        """Test creating from URL."""
        mock_from_url.return_value = Config()

        db = Database.from_url("postgresql://user:pass@host/db")

        mock_from_url.assert_called_once_with("postgresql://user:pass@host/db")


class TestDatabaseConnection:
    """Tests for Database connection methods."""

    @patch("pycopg.database.psycopg")
    def test_connect_context(self, mock_psycopg, config):
        """Test connect context manager."""
        mock_conn = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)

        with db.connect() as conn:
            assert conn == mock_conn

        mock_conn.close.assert_called_once()

    @patch("pycopg.database.psycopg")
    def test_connect_autocommit(self, mock_psycopg, config):
        """Test connect with autocommit."""
        mock_conn = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)

        with db.connect(autocommit=True) as conn:
            pass

        # Check autocommit was passed
        call_kwargs = mock_psycopg.connect.call_args[1]
        assert call_kwargs["autocommit"] is True

    @patch("pycopg.database.psycopg")
    def test_cursor_context(self, mock_psycopg, config):
        """Test cursor context manager."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)

        with db.cursor() as cur:
            assert cur == mock_cursor

        mock_conn.commit.assert_called_once()

    @patch("pycopg.database.psycopg")
    def test_cursor_autocommit_no_commit(self, mock_psycopg, config):
        """Test cursor with autocommit doesn't commit."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)

        with db.cursor(autocommit=True) as cur:
            pass

        mock_conn.commit.assert_not_called()


class TestDatabaseExecute:
    """Tests for Database execute methods."""

    @patch("pycopg.database.psycopg")
    def test_execute_select(self, mock_psycopg, config):
        """Test execute returns results for SELECT."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [{"id": 1, "name": "Alice"}]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        result = db.execute("SELECT * FROM users")

        assert result == [{"id": 1, "name": "Alice"}]
        mock_cursor.execute.assert_called_once_with("SELECT * FROM users", None)

    @patch("pycopg.database.psycopg")
    def test_execute_with_params(self, mock_psycopg, config):
        """Test execute with parameters."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall.return_value = [{"id": 1}]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        result = db.execute("SELECT * FROM users WHERE id = %s", [1])

        mock_cursor.execute.assert_called_once_with("SELECT * FROM users WHERE id = %s", [1])

    @patch("pycopg.database.psycopg")
    def test_execute_insert(self, mock_psycopg, config):
        """Test execute for INSERT returns empty list."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = None
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        result = db.execute("INSERT INTO users (name) VALUES (%s)", ["Alice"])

        assert result == []

    @patch("pycopg.database.psycopg")
    def test_execute_many(self, mock_psycopg, config):
        """Test execute_many method."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        result = db.execute_many(
            "INSERT INTO users (name) VALUES (%s)",
            [("Alice",), ("Bob",)],
        )

        assert result == 2
        assert mock_cursor.execute.call_count == 2

    @patch("pycopg.database.psycopg")
    def test_fetch_one(self, mock_psycopg, config):
        """Test fetch_one method."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"id": 1, "name": "Alice"}
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        result = db.fetch_one("SELECT * FROM users WHERE id = %s", [1])

        assert result == {"id": 1, "name": "Alice"}

    @patch("pycopg.database.psycopg")
    def test_fetch_one_none(self, mock_psycopg, config):
        """Test fetch_one returns None when no result."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        result = db.fetch_one("SELECT * FROM users WHERE id = %s", [999])

        assert result is None

    @patch("pycopg.database.psycopg")
    def test_fetch_val(self, mock_psycopg, config):
        """Test fetch_val method."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {"count": 42}
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        result = db.fetch_val("SELECT COUNT(*) FROM users")

        assert result == 42

    @patch("pycopg.database.psycopg")
    def test_fetch_val_none(self, mock_psycopg, config):
        """Test fetch_val returns None when no result."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        result = db.fetch_val("SELECT value FROM empty_table")

        assert result is None


class TestDatabaseSchemas:
    """Tests for schema-related methods."""

    @patch("pycopg.database.psycopg")
    def test_list_schemas(self, mock_psycopg, config):
        """Test listing schemas."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("schema_name",)]
        mock_cursor.fetchall.return_value = [
            {"schema_name": "public"},
            {"schema_name": "app"},
        ]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        schemas = db.list_schemas()

        assert schemas == ["public", "app"]

    @patch("pycopg.database.psycopg")
    def test_schema_exists_true(self, mock_psycopg, config):
        """Test schema_exists returns True."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("exists",)]
        mock_cursor.fetchall.return_value = [{"exists": 1}]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        exists = db.schema_exists("public")

        assert exists is True

    @patch("pycopg.database.psycopg")
    def test_schema_exists_false(self, mock_psycopg, config):
        """Test schema_exists returns False."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("exists",)]
        mock_cursor.fetchall.return_value = []
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        exists = db.schema_exists("nonexistent")

        assert exists is False


class TestDatabaseTables:
    """Tests for table-related methods."""

    @patch("pycopg.database.psycopg")
    def test_list_tables(self, mock_psycopg, config):
        """Test listing tables."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("table_name",)]
        mock_cursor.fetchall.return_value = [
            {"table_name": "users"},
            {"table_name": "orders"},
        ]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        tables = db.list_tables("public")

        assert tables == ["users", "orders"]

    @patch("pycopg.database.psycopg")
    def test_table_exists(self, mock_psycopg, config):
        """Test table_exists method."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("exists",)]
        mock_cursor.fetchall.return_value = [{"exists": 1}]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        exists = db.table_exists("users")

        assert exists is True


class TestDatabaseRoles:
    """Tests for role-related methods."""

    @patch("pycopg.database.psycopg")
    def test_role_exists_true(self, mock_psycopg, config):
        """Test role_exists returns True."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("exists",)]
        mock_cursor.fetchall.return_value = [{"exists": 1}]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        exists = db.role_exists("admin")

        assert exists is True

    @patch("pycopg.database.psycopg")
    def test_role_exists_false(self, mock_psycopg, config):
        """Test role_exists returns False."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("exists",)]
        mock_cursor.fetchall.return_value = []
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        exists = db.role_exists("nonexistent")

        assert exists is False

    @patch("pycopg.database.psycopg")
    def test_list_roles(self, mock_psycopg, config):
        """Test listing roles."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("name",)]
        mock_cursor.fetchall.return_value = [
            {"name": "admin", "superuser": True, "login": True},
            {"name": "appuser", "superuser": False, "login": True},
        ]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        roles = db.list_roles()

        assert len(roles) == 2


class TestDatabaseValidation:
    """Tests for identifier validation."""

    def test_validate_identifier_valid(self, config):
        """Test valid identifiers pass."""
        db = Database.__new__(Database)
        db.config = config

        # These should not raise
        db._validate_identifier("users")
        db._validate_identifier("user_accounts")
        db._validate_identifier("Users123")
        db._validate_identifier("_private")

    def test_validate_identifier_invalid(self, config):
        """Test invalid identifiers raise."""
        db = Database.__new__(Database)
        db.config = config

        with pytest.raises(ValueError):
            db._validate_identifier("123users")

        with pytest.raises(ValueError):
            db._validate_identifier("user-accounts")

        with pytest.raises(ValueError):
            db._validate_identifier("DROP TABLE")

        with pytest.raises(ValueError):
            db._validate_identifier("users;DELETE")


class TestDatabaseContextManager:
    """Tests for Database context manager."""

    @patch("pycopg.database.psycopg")
    def test_context_manager(self, mock_psycopg, config):
        """Test Database as context manager."""
        mock_conn = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        with Database(config) as db:
            assert db is not None

    @patch("pycopg.database.psycopg")
    def test_repr(self, mock_psycopg, config):
        """Test string representation."""
        db = Database(config)
        repr_str = repr(db)

        assert "Database" in repr_str
        assert "testdb" in repr_str
        assert "localhost" in repr_str


class TestDatabaseBackup:
    """Tests for backup and restore methods."""

    @patch("pycopg.database.psycopg")
    @patch("subprocess.run")
    def test_pg_dump_basic(self, mock_run, mock_psycopg, config):
        """Test basic pg_dump call."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        db = Database(config)
        db.pg_dump("/tmp/backup.dump")

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "pg_dump" in cmd
        assert "-h" in cmd
        assert "localhost" in cmd

    @patch("pycopg.database.psycopg")
    @patch("subprocess.run")
    def test_pg_dump_format_plain(self, mock_run, mock_psycopg, config):
        """Test pg_dump with plain format."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        db = Database(config)
        db.pg_dump("/tmp/backup.sql", format="plain")

        cmd = mock_run.call_args[0][0]
        assert "-F" in cmd
        assert "p" in cmd

    @patch("pycopg.database.psycopg")
    @patch("subprocess.run")
    def test_pg_dump_schema_only(self, mock_run, mock_psycopg, config):
        """Test pg_dump with schema_only."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        db = Database(config)
        db.pg_dump("/tmp/schema.sql", schema_only=True)

        cmd = mock_run.call_args[0][0]
        assert "--schema-only" in cmd

    @patch("pycopg.database.psycopg")
    @patch("subprocess.run")
    def test_pg_dump_tables(self, mock_run, mock_psycopg, config):
        """Test pg_dump with specific tables."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        db = Database(config)
        db.pg_dump("/tmp/backup.dump", tables=["users", "orders"])

        cmd = mock_run.call_args[0][0]
        assert "-t" in cmd
        assert "users" in cmd
        assert "orders" in cmd

    @patch("pycopg.database.psycopg")
    @patch("subprocess.run")
    def test_pg_dump_failure(self, mock_run, mock_psycopg, config):
        """Test pg_dump failure raises."""
        mock_run.return_value = MagicMock(returncode=1, stderr="pg_dump failed")

        db = Database(config)

        with pytest.raises(RuntimeError) as exc:
            db.pg_dump("/tmp/backup.dump")
        assert "pg_dump failed" in str(exc.value)

    @patch("pycopg.database.psycopg")
    @patch("subprocess.run")
    def test_pg_restore_basic(self, mock_run, mock_psycopg, config):
        """Test basic pg_restore call."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        db = Database(config)

        with tempfile.NamedTemporaryFile(suffix=".dump") as f:
            db.pg_restore(f.name)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "pg_restore" in cmd

    @patch("pycopg.database.psycopg")
    @patch("subprocess.run")
    def test_pg_restore_clean(self, mock_run, mock_psycopg, config):
        """Test pg_restore with clean option."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        db = Database(config)

        with tempfile.NamedTemporaryFile(suffix=".dump") as f:
            db.pg_restore(f.name, clean=True)

        cmd = mock_run.call_args[0][0]
        assert "--clean" in cmd
