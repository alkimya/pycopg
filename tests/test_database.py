"""Tests for pycopg.database module."""

from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
import tempfile

import pytest

from pycopg import Database, Config
from pycopg.utils import validate_identifier
from pycopg.exceptions import InvalidIdentifier


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
        """Test execute_many method using executemany."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 2
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
        mock_cursor.executemany.assert_called_once()

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
    """Tests for identifier validation using utils.validate_identifier."""

    def test_validate_identifier_valid(self, config):
        """Test valid identifiers pass."""
        # These should not raise - using utils.validate_identifier
        validate_identifier("users")
        validate_identifier("user_accounts")
        validate_identifier("Users123")
        validate_identifier("_private")

    def test_validate_identifier_invalid(self, config):
        """Test invalid identifiers raise."""
        with pytest.raises(InvalidIdentifier):
            validate_identifier("123users")

        with pytest.raises(InvalidIdentifier):
            validate_identifier("user-accounts")

        with pytest.raises(InvalidIdentifier):
            validate_identifier("DROP TABLE")

        with pytest.raises(InvalidIdentifier):
            validate_identifier("users;DELETE")


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


class TestDatabaseSession:
    """Tests for session mode."""

    @patch("pycopg.database.psycopg")
    def test_session_context_manager(self, mock_psycopg, config):
        """Test session context manager."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall.return_value = [{"id": 1}]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)

        with db.session() as session:
            assert session.in_session is True
            result = session.execute("SELECT 1")

        assert db.in_session is False
        mock_conn.commit.assert_called()
        mock_conn.close.assert_called_once()

    @patch("pycopg.database.psycopg")
    def test_session_autocommit(self, mock_psycopg, config):
        """Test session with autocommit mode."""
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)

        with db.session(autocommit=True) as session:
            pass

        # In autocommit mode, commit should not be called
        mock_conn.commit.assert_not_called()
        mock_conn.close.assert_called_once()

    @patch("pycopg.database.psycopg")
    def test_session_nested_raises(self, mock_psycopg, config):
        """Test nested sessions raise error."""
        mock_conn = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)

        with db.session() as session:
            with pytest.raises(RuntimeError) as exc:
                with session.session():
                    pass
            assert "Already in session mode" in str(exc.value)

    @patch("pycopg.database.psycopg")
    def test_in_session_property(self, mock_psycopg, config):
        """Test in_session property."""
        db = Database(config)
        assert db.in_session is False


class TestDatabaseTableInfo:
    """Tests for table info methods."""

    @patch("pycopg.database.psycopg")
    def test_table_info(self, mock_psycopg, config):
        """Test table_info method."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("column_name",), ("data_type",)]
        mock_cursor.fetchall.return_value = [
            {"column_name": "id", "data_type": "integer"},
            {"column_name": "name", "data_type": "text"},
        ]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        info = db.table_info("users")

        assert len(info) == 2
        assert info[0]["column_name"] == "id"

    @patch("pycopg.database.psycopg")
    def test_row_count(self, mock_psycopg, config):
        """Test row_count method."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("count",)]
        mock_cursor.fetchall.return_value = [{"count": 42}]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        count = db.row_count("users")

        assert count == 42


class TestDatabaseExtensions:
    """Tests for extension-related methods."""

    @patch("pycopg.database.psycopg")
    def test_has_extension_true(self, mock_psycopg, config):
        """Test has_extension returns True when extension exists."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("exists",)]
        mock_cursor.fetchall.return_value = [{"exists": 1}]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        assert db.has_extension("postgis") is True

    @patch("pycopg.database.psycopg")
    def test_has_extension_false(self, mock_psycopg, config):
        """Test has_extension returns False when extension missing."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("exists",)]
        mock_cursor.fetchall.return_value = []
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        assert db.has_extension("unknown_ext") is False

    @patch("pycopg.database.psycopg")
    def test_list_extensions(self, mock_psycopg, config):
        """Test list_extensions method."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("extname",), ("extversion",)]
        mock_cursor.fetchall.return_value = [
            {"extname": "plpgsql", "extversion": "1.0"},
            {"extname": "postgis", "extversion": "3.1.0"},
        ]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        extensions = db.list_extensions()

        assert len(extensions) == 2
        assert extensions[0]["extname"] == "plpgsql"


class TestDatabaseSize:
    """Tests for size-related methods."""

    @patch("pycopg.database.psycopg")
    def test_size_pretty(self, mock_psycopg, config):
        """Test size method returns human-readable size."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("size",)]
        mock_cursor.fetchall.return_value = [{"size": "10 MB"}]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        size = db.size()

        assert size == "10 MB"

    @patch("pycopg.database.psycopg")
    def test_size_bytes(self, mock_psycopg, config):
        """Test size method returns bytes when pretty=False."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("size",)]
        mock_cursor.fetchall.return_value = [{"size": 1048576}]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        size = db.size(pretty=False)

        assert size == 1048576

    @patch("pycopg.database.psycopg")
    def test_table_size_pretty(self, mock_psycopg, config):
        """Test table_size method returns human-readable size."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("size",)]
        mock_cursor.fetchall.return_value = [{"size": "1 MB"}]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        size = db.table_size("users")

        assert size == "1 MB"

    @patch("pycopg.database.psycopg")
    def test_table_size_bytes(self, mock_psycopg, config):
        """Test table_size method returns bytes when pretty=False."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("size",)]
        mock_cursor.fetchall.return_value = [{"size": 524288}]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        size = db.table_size("users", pretty=False)

        assert size == 524288


class TestDatabaseInsertBatch:
    """Tests for insert_batch method."""

    @patch("pycopg.database.psycopg")
    def test_insert_batch_basic(self, mock_psycopg, config):
        """Test basic insert_batch."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 2
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        result = db.insert_batch("users", [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
        ])

        assert result == 2
        mock_cursor.execute.assert_called()

    @patch("pycopg.database.psycopg")
    def test_insert_batch_empty(self, mock_psycopg, config):
        """Test insert_batch with empty list."""
        db = Database(config)
        result = db.insert_batch("users", [])

        assert result == 0

    @patch("pycopg.database.psycopg")
    def test_insert_batch_with_conflict(self, mock_psycopg, config):
        """Test insert_batch with ON CONFLICT clause."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        result = db.insert_batch(
            "users",
            [{"id": 1, "name": "Alice Updated"}],
            on_conflict="(id) DO UPDATE SET name = EXCLUDED.name"
        )

        assert result == 1


class TestDatabaseTruncate:
    """Tests for truncate method."""

    @patch("pycopg.database.psycopg")
    def test_truncate_basic(self, mock_psycopg, config):
        """Test basic truncate."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = None
        mock_cursor.fetchall.return_value = []
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        db.truncate_table("users")

        mock_cursor.execute.assert_called()


class TestDatabaseIndexes:
    """Tests for index methods."""

    @patch("pycopg.database.psycopg")
    def test_list_indexes(self, mock_psycopg, config):
        """Test list_indexes method."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("index_name",), ("index_type",)]
        mock_cursor.fetchall.return_value = [
            {"index_name": "users_pkey", "index_type": "btree"},
            {"index_name": "users_email_idx", "index_type": "hash"},
        ]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        indexes = db.list_indexes("users")

        assert len(indexes) == 2
        assert indexes[0]["index_name"] == "users_pkey"


class TestDatabaseConstraints:
    """Tests for constraint methods."""

    @patch("pycopg.database.psycopg")
    def test_list_constraints(self, mock_psycopg, config):
        """Test list_constraints method."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("constraint_name",), ("constraint_type",)]
        mock_cursor.fetchall.return_value = [
            {"constraint_name": "users_pkey", "constraint_type": "p"},
            {"constraint_name": "users_email_key", "constraint_type": "u"},
        ]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        constraints = db.list_constraints("users")

        assert len(constraints) == 2


class TestDatabaseDropTable:
    """Tests for drop_table method."""

    @patch("pycopg.database.psycopg")
    def test_drop_table(self, mock_psycopg, config):
        """Test drop_table method."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = None
        mock_cursor.fetchall.return_value = []
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        db.drop_table("users")

        mock_cursor.execute.assert_called()
        call_args = mock_cursor.execute.call_args[0][0]
        assert "DROP TABLE" in call_args

    @patch("pycopg.database.psycopg")
    def test_drop_table_if_exists(self, mock_psycopg, config):
        """Test drop_table with if_exists."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = None
        mock_cursor.fetchall.return_value = []
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        db.drop_table("users", if_exists=True)

        call_args = mock_cursor.execute.call_args[0][0]
        assert "IF EXISTS" in call_args


class TestDatabaseCreateDropSchema:
    """Tests for schema creation/deletion methods."""

    @patch("pycopg.database.psycopg")
    def test_create_schema(self, mock_psycopg, config):
        """Test create_schema method."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = None
        mock_cursor.fetchall.return_value = []
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        db.create_schema("myschema")

        mock_cursor.execute.assert_called()
        call_args = mock_cursor.execute.call_args[0][0]
        assert "CREATE SCHEMA" in call_args

    @patch("pycopg.database.psycopg")
    def test_drop_schema(self, mock_psycopg, config):
        """Test drop_schema method."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = None
        mock_cursor.fetchall.return_value = []
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        db.drop_schema("myschema")

        mock_cursor.execute.assert_called()
        call_args = mock_cursor.execute.call_args[0][0]
        assert "DROP SCHEMA" in call_args
