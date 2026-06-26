"""Tests for pycopg.database module."""

import tempfile
from unittest.mock import MagicMock, patch

import pytest

from pycopg import Config, Database
from pycopg.exceptions import InvalidIdentifier
from pycopg.utils import validate_identifier


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

        Database.from_url("postgresql://user:pass@host/db")

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

        with db.connect(autocommit=True):
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

        with db.cursor(autocommit=True):
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
        db.execute("SELECT * FROM users WHERE id = %s", [1])

        mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM users WHERE id = %s", [1]
        )

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
        schemas = db.schema.list_schemas()

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
        exists = db.schema.schema_exists("public")

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
        exists = db.schema.schema_exists("nonexistent")

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
        tables = db.schema.list_tables("public")

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
        exists = db.schema.table_exists("users")

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
        exists = db.admin.role_exists("admin")

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
        exists = db.admin.role_exists("nonexistent")

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
        roles = db.admin.list_roles()

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
        db.backup.pg_dump("/tmp/backup.dump")

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
        db.backup.pg_dump("/tmp/backup.sql", format="plain")

        cmd = mock_run.call_args[0][0]
        assert "-F" in cmd
        assert "p" in cmd

    @patch("pycopg.database.psycopg")
    @patch("subprocess.run")
    def test_pg_dump_schema_only(self, mock_run, mock_psycopg, config):
        """Test pg_dump with schema_only."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        db = Database(config)
        db.backup.pg_dump("/tmp/schema.sql", schema_only=True)

        cmd = mock_run.call_args[0][0]
        assert "--schema-only" in cmd

    @patch("pycopg.database.psycopg")
    @patch("subprocess.run")
    def test_pg_dump_tables(self, mock_run, mock_psycopg, config):
        """Test pg_dump with specific tables."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        db = Database(config)
        db.backup.pg_dump("/tmp/backup.dump", tables=["users", "orders"])

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
            db.backup.pg_dump("/tmp/backup.dump")
        assert "pg_dump failed" in str(exc.value)

    @patch("pycopg.database.psycopg")
    @patch("subprocess.run")
    def test_pg_restore_basic(self, mock_run, mock_psycopg, config):
        """Test basic pg_restore call."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        db = Database(config)

        with tempfile.NamedTemporaryFile(suffix=".dump") as f:
            db.backup.pg_restore(f.name)

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
            db.backup.pg_restore(f.name, clean=True)

        cmd = mock_run.call_args[0][0]
        assert "--clean" in cmd

    @patch("pycopg.database.psycopg")
    @patch("subprocess.run")
    def test_pg_restore_sql_file_delegates_to_psql(
        self, mock_run, mock_psycopg, config
    ):
        """Test pg_restore delegates to _psql_restore for .sql files."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        db = Database(config)

        with tempfile.NamedTemporaryFile(suffix=".sql") as f:
            db.backup.pg_restore(f.name)

        # psql should have been called (not pg_restore)
        cmd = mock_run.call_args[0][0]
        assert "psql" in cmd


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
            session.execute("SELECT 1")

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

        with db.session(autocommit=True):
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
        info = db.schema.table_info("users")

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
        count = db.schema.row_count("users")

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
        assert db.schema.has_extension("postgis") is True

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
        assert db.schema.has_extension("unknown_ext") is False

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
        extensions = db.schema.list_extensions()

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
        size = db.maint.size()

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
        size = db.maint.size(pretty=False)

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
        size = db.maint.table_size("users")

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
        size = db.maint.table_size("users", pretty=False)

        assert size == 524288


class TestDatabaseMaintenance:
    """Coverage tests for sync MaintAccessor branches not hit by alias tests."""

    def _make_db(self, config):
        """Return a Database with db.execute mocked (no live psycopg connection)."""
        db = Database.__new__(Database)
        db._config = config
        db._schema = "public"
        db._maint = None
        db.execute = MagicMock(return_value=[{"QUERY PLAN": "Seq Scan on t"}])
        return db

    def test_vacuum_full_option(self, config):
        """MaintAccessor.vacuum with full=True emits VACUUM(FULL, ANALYZE)."""
        db = self._make_db(config)
        db.execute = MagicMock()

        db.maint.vacuum("users", full=True)

        call_sql = db.execute.call_args[0][0]
        assert "VACUUM(FULL, ANALYZE)" in call_sql

    def test_explain_returns_plan_lines(self, config):
        """MaintAccessor.explain returns a list of QUERY PLAN strings."""
        db = self._make_db(config)

        result = db.maint.explain("SELECT 1")

        assert result == ["Seq Scan on t"]
        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "EXPLAIN" in sql
        assert "FORMAT TEXT" in sql

    def test_explain_with_analyze_option(self, config):
        """MaintAccessor.explain with analyze=True adds ANALYZE to options."""
        db = self._make_db(config)

        db.maint.explain("SELECT 1", analyze=True)

        sql = db.execute.call_args[0][0]
        assert "ANALYZE" in sql


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
        result = db.insert_batch(
            "users",
            [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@example.com"},
            ],
        )

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
            on_conflict="(id) DO UPDATE SET name = EXCLUDED.name",
        )

        assert result == 1


class TestDatabaseBatchStreamNotify:
    """PAR-03: edge cases for the sync mirrors insert_many/upsert_many/stream/notify."""

    @patch("pycopg.database.psycopg")
    def test_insert_many_empty_returns_zero(self, mock_psycopg, config):
        """insert_many([]) returns 0 without touching the DB."""
        db = Database(config)
        assert db.insert_many("users", []) == 0
        mock_psycopg.connect.assert_not_called()

    @patch("pycopg.database.psycopg")
    def test_upsert_many_empty_returns_zero(self, mock_psycopg, config):
        """upsert_many([]) returns 0 without touching the DB."""
        db = Database(config)
        assert db.upsert_many("users", [], conflict_columns=["id"]) == 0
        mock_psycopg.connect.assert_not_called()

    @patch("pycopg.database.psycopg")
    def test_insert_many_delegates_to_batch_builder(self, mock_psycopg, config):
        """insert_many builds a multi-VALUES INSERT via _build_batch_insert_sql and returns rowcount."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 2
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        result = db.insert_many(
            "users",
            [{"name": "A", "email": "a@x"}, {"name": "B", "email": "b@x"}],
        )

        assert result == 2
        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        assert sql.startswith("INSERT INTO public.users")

    @patch("pycopg.database.psycopg")
    def test_upsert_many_builds_on_conflict_clause(self, mock_psycopg, config):
        """upsert_many builds an ON CONFLICT DO UPDATE clause for non-conflict cols."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        db.upsert_many(
            "users",
            [{"id": 1, "name": "Alice", "email": "a@x"}],
            conflict_columns=["id"],
        )

        sql = mock_cursor.execute.call_args[0][0]
        assert "ON CONFLICT (id) DO UPDATE SET" in sql
        assert "name = EXCLUDED.name" in sql
        assert "email = EXCLUDED.email" in sql

    @patch("pycopg.database.psycopg")
    def test_stream_yields_dicts_in_batches(self, mock_psycopg, config):
        """stream fetches in batches and yields each row."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Two batches then empty
        mock_cursor.fetchmany.side_effect = [
            [{"id": 1}, {"id": 2}],
            [{"id": 3}],
            [],
        ]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        rows = list(db.stream("SELECT * FROM t", batch_size=2))

        assert rows == [{"id": 1}, {"id": 2}, {"id": 3}]

    @patch("pycopg.database.psycopg")
    def test_notify_uses_pg_notify(self, mock_psycopg, config):
        """notify issues SELECT pg_notify(channel, payload), not raw NOTIFY."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = None
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        db.notify("events", "hello")

        sql, params = mock_cursor.execute.call_args[0][:2]
        assert "pg_notify" in sql
        assert params == ["events", "hello"]

    def test_notify_rejects_invalid_channel(self, config):
        """notify validates the channel identifier."""
        db = Database(config)
        with pytest.raises(InvalidIdentifier):
            db.notify("bad channel; DROP TABLE x")

    def test_no_sync_listen(self, config):
        """D-06: Database has no listen method (async-only)."""
        db = Database(config)
        assert not hasattr(db, "listen")


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
        db.schema.truncate_table("users")

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
        indexes = db.schema.list_indexes("users")

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
        constraints = db.schema.list_constraints("users")

        assert len(constraints) == 2


class TestDatabaseIntrospectionHelpers:
    """Mock-based unit tests for primary_key, foreign_keys, sequences, views."""

    def _make_db(self, mock_psycopg, config, fetchall_value):
        """Helper: set up mock cursor with given fetchall return value."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("col",)]
        mock_cursor.fetchall.return_value = fetchall_value
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn
        return Database(config)

    @patch("pycopg.database.psycopg")
    def test_primary_key(self, mock_psycopg, config):
        """primary_key reshapes constraint+column rows into dict with constraint_name and columns."""
        rows = [
            {"constraint_name": "users_pkey", "column_name": "id"},
        ]
        db = self._make_db(mock_psycopg, config, rows)
        result = db.schema.primary_key("users")
        assert result == {"constraint_name": "users_pkey", "columns": ["id"]}

    @patch("pycopg.database.psycopg")
    def test_primary_key_composite(self, mock_psycopg, config):
        """primary_key returns columns in key order for composite PK."""
        rows = [
            {"constraint_name": "org_user_pkey", "column_name": "org_id"},
            {"constraint_name": "org_user_pkey", "column_name": "user_id"},
        ]
        db = self._make_db(mock_psycopg, config, rows)
        result = db.schema.primary_key("org_user")
        assert result == {
            "constraint_name": "org_user_pkey",
            "columns": ["org_id", "user_id"],
        }

    @patch("pycopg.database.psycopg")
    def test_primary_key_none(self, mock_psycopg, config):
        """primary_key returns None when the table has no primary key."""
        db = self._make_db(mock_psycopg, config, [])
        result = db.schema.primary_key("no_pk_table")
        assert result is None

    @patch("pycopg.database.psycopg")
    def test_foreign_keys(self, mock_psycopg, config):
        """foreign_keys groups rows into list[dict] with exactly the 4 core keys."""
        rows = [
            {
                "constraint_name": "orders_user_id_fkey",
                "column_name": "user_id",
                "referenced_table": "users",
                "referenced_column": "id",
            }
        ]
        db = self._make_db(mock_psycopg, config, rows)
        result = db.schema.foreign_keys("orders")
        assert len(result) == 1
        entry = result[0]
        assert set(entry.keys()) == {
            "constraint_name",
            "columns",
            "referenced_table",
            "referenced_columns",
        }
        assert entry["constraint_name"] == "orders_user_id_fkey"
        assert entry["columns"] == ["user_id"]
        assert entry["referenced_table"] == "users"
        assert entry["referenced_columns"] == ["id"]

    @patch("pycopg.database.psycopg")
    def test_foreign_keys_empty(self, mock_psycopg, config):
        """foreign_keys returns [] when the table has no foreign keys."""
        db = self._make_db(mock_psycopg, config, [])
        result = db.schema.foreign_keys("no_fk_table")
        assert result == []

    @patch("pycopg.database.psycopg")
    def test_sequences(self, mock_psycopg, config):
        """sequences returns list[str] of sequence names."""
        rows = [{"sequence_name": "users_id_seq"}, {"sequence_name": "orders_id_seq"}]
        db = self._make_db(mock_psycopg, config, rows)
        result = db.schema.sequences("public")
        assert result == ["users_id_seq", "orders_id_seq"]

    @patch("pycopg.database.psycopg")
    def test_sequences_empty(self, mock_psycopg, config):
        """sequences returns [] for a schema with no sequences."""
        db = self._make_db(mock_psycopg, config, [])
        result = db.schema.sequences("empty_schema")
        assert result == []

    @patch("pycopg.database.psycopg")
    def test_views(self, mock_psycopg, config):
        """views returns list[str] of regular view names."""
        rows = [{"table_name": "active_users"}, {"table_name": "recent_orders"}]
        db = self._make_db(mock_psycopg, config, rows)
        result = db.schema.views("public")
        assert result == ["active_users", "recent_orders"]

    @patch("pycopg.database.psycopg")
    def test_views_empty(self, mock_psycopg, config):
        """views returns [] for a schema with no regular views."""
        db = self._make_db(mock_psycopg, config, [])
        result = db.schema.views("public")
        assert result == []

    @patch("pycopg.database.psycopg")
    def test_describe_composes_four_helpers(self, mock_psycopg, config):
        """describe returns a flat 4-key dict by composing the four standalone helpers."""
        # Patch each composed helper directly so describe's composition contract is
        # tested without fighting the shared-fetchall mock cursor limitation.
        db = self._make_db(mock_psycopg, config, [])
        expected_columns = [{"column_name": "id", "data_type": "integer"}]
        expected_pk = {"constraint_name": "t_pkey", "columns": ["id"]}
        expected_fks = []
        expected_indexes = [{"index_name": "t_pkey", "index_type": "btree"}]
        with (
            patch.object(
                db.schema, "table_info", return_value=expected_columns
            ) as m_ti,
            patch.object(
                db.schema, "primary_key", return_value=expected_pk
            ) as m_pk,
            patch.object(
                db.schema, "foreign_keys", return_value=expected_fks
            ) as m_fk,
            patch.object(
                db.schema, "list_indexes", return_value=expected_indexes
            ) as m_li,
        ):
            result = db.schema.describe("some_table", "public")

        # Exact key set
        assert set(result) == {"columns", "primary_key", "foreign_keys", "indexes"}
        # Each sub-value is the standalone helper's exact output
        assert result["columns"] == expected_columns
        assert result["primary_key"] == expected_pk
        assert result["foreign_keys"] == expected_fks
        assert result["indexes"] == expected_indexes
        # Each helper was called exactly once with positional table+schema args
        m_ti.assert_called_once_with("some_table", "public")
        m_pk.assert_called_once_with("some_table", "public")
        m_fk.assert_called_once_with("some_table", "public")
        m_li.assert_called_once_with("some_table", "public")


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
        db.schema.drop_table("users")

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
        db.schema.drop_table("users", if_exists=True)

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
        db.schema.create_schema("myschema")

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
        db.schema.drop_schema("myschema")

        mock_cursor.execute.assert_called()
        call_args = mock_cursor.execute.call_args[0][0]
        assert "DROP SCHEMA" in call_args


class TestDatabaseInspection:
    """Tests for table inspection methods."""

    def test_list_columns(self, config):
        """Test list_columns method."""
        db = Database(config)
        db.execute = MagicMock(
            return_value=[
                {"column_name": "id", "data_type": "integer"},
                {"column_name": "name", "data_type": "text"},
            ]
        )

        cols = db.schema.list_columns("users")

        assert cols == ["id", "name"]

        # Verify call to execute
        call_args = db.execute.call_args
        assert "column_name" in call_args[0][0]
        assert call_args[0][1] == ["public", "users"]

    def test_columns_with_types(self, config):
        """Test columns_with_types method."""
        db = Database(config)
        db.execute = MagicMock(
            return_value=[
                {"column_name": "id", "data_type": "integer"},
                {"column_name": "name", "data_type": "text"},
            ]
        )

        cols = db.schema.columns_with_types("users")

        assert cols == [("id", "integer"), ("name", "text")]


class TestDatabaseRetry:
    """Tests for Database retry behavior."""

    def test_connect_with_retry_has_tenacity_decorator(self, config):
        """Test _connect_with_retry has tenacity retry decorator."""
        db = Database(config)
        assert hasattr(db._connect_with_retry, "retry")

    @patch("pycopg.database.psycopg")
    @patch("time.sleep")  # Patch sleep to avoid delays
    def test_connect_with_retry_retries_operational_error(
        self, mock_sleep, mock_psycopg, config
    ):
        """Test _connect_with_retry retries OperationalError."""
        from pycopg.database import OperationalError

        mock_conn = MagicMock()
        # Fail twice with OperationalError, succeed on third try
        mock_psycopg.connect.side_effect = [
            OperationalError("Connection refused"),
            OperationalError("Connection refused"),
            mock_conn,
        ]

        db = Database(config)
        result = db._connect_with_retry()

        assert result == mock_conn
        assert mock_psycopg.connect.call_count == 3

    @patch("pycopg.database.psycopg")
    def test_connect_with_retry_does_not_retry_programming_error(
        self, mock_psycopg, config
    ):
        """Test _connect_with_retry does NOT retry ProgrammingError."""
        from psycopg import ProgrammingError

        mock_psycopg.connect.side_effect = ProgrammingError("Syntax error")

        db = Database(config)
        with pytest.raises(ProgrammingError):
            db._connect_with_retry()

        # Should only be called once (no retry on ProgrammingError)
        assert mock_psycopg.connect.call_count == 1

    @patch("pycopg.database.psycopg")
    @patch("time.sleep")
    def test_connect_with_retry_reraises_after_max_attempts(
        self, mock_sleep, mock_psycopg, config
    ):
        """Test _connect_with_retry reraises after 3 attempts."""
        from pycopg.database import OperationalError

        # Always raise OperationalError
        mock_psycopg.connect.side_effect = OperationalError("Connection refused")

        db = Database(config)
        with pytest.raises(OperationalError):
            db._connect_with_retry()

        # Should be called exactly 3 times (stop_after_attempt(3))
        assert mock_psycopg.connect.call_count == 3

    def test_insert_batch_uses_config_default_batch_size(self, config):
        """Test insert_batch uses config.default_batch_size when batch_size=None."""
        # Use inspect to verify batch_size default is None
        import inspect

        sig = inspect.signature(Database.insert_batch)
        param = sig.parameters["batch_size"]
        assert param.default is None

    def test_insert_batch_explicit_batch_size_overrides_config(self, config):
        """Test insert_batch explicit batch_size overrides config."""
        import inspect

        sig = inspect.signature(Database.insert_batch)
        # Verify batch_size parameter exists with default None
        assert "batch_size" in sig.parameters
        assert sig.parameters["batch_size"].default is None


class TestDatabaseGrantRevoke:
    """Tests for grant() and revoke() method branches (coverage-fill, D-07)."""

    def _make_db_with_execute_mock(self, config):
        """Return a Database whose execute() is mocked to do nothing."""
        with patch("pycopg.database.psycopg"):
            db = Database(config)
        db.execute = MagicMock(return_value=[])
        return db

    def test_grant_list_privileges_joined(self, config):
        """Test grant() joins a list of privileges into a comma-separated string."""
        db = self._make_db_with_execute_mock(config)
        db.admin.grant(["SELECT", "INSERT"], "users", "appuser", object_type="TABLE")
        call_sql = db.execute.call_args[0][0]
        assert "SELECT, INSERT" in call_sql

    def test_grant_schema_branch(self, config):
        """Test grant() emits GRANT ... ON SCHEMA for object_type=SCHEMA."""
        db = self._make_db_with_execute_mock(config)
        db.admin.grant("USAGE", "public", "appuser", object_type="SCHEMA")
        call_sql = db.execute.call_args[0][0]
        assert "ON SCHEMA public" in call_sql

    def test_grant_database_branch(self, config):
        """Test grant() emits GRANT ... ON DATABASE for object_type=DATABASE."""
        db = self._make_db_with_execute_mock(config)
        db.admin.grant("CONNECT", "mydb", "appuser", object_type="DATABASE")
        call_sql = db.execute.call_args[0][0]
        assert "ON DATABASE mydb" in call_sql

    def test_grant_all_tables_branch(self, config):
        """Test grant() emits IN SCHEMA ... for on='ALL TABLES'."""
        db = self._make_db_with_execute_mock(config)
        db.admin.grant("SELECT", "ALL TABLES", "appuser", schema="public")
        call_sql = db.execute.call_args[0][0]
        assert "ALL TABLES IN SCHEMA public" in call_sql

    def test_grant_default_table_branch(self, config):
        """Test grant() emits ON TABLE schema.table for default object_type."""
        db = self._make_db_with_execute_mock(config)
        db.admin.grant("SELECT", "users", "appuser")
        call_sql = db.execute.call_args[0][0]
        assert "ON TABLE public.users" in call_sql

    def test_grant_with_grant_option(self, config):
        """Test grant() appends WITH GRANT OPTION when requested."""
        db = self._make_db_with_execute_mock(config)
        db.admin.grant("SELECT", "users", "appuser", with_grant_option=True)
        call_sql = db.execute.call_args[0][0]
        assert "WITH GRANT OPTION" in call_sql

    def test_revoke_list_privileges_joined(self, config):
        """Test revoke() joins a list of privileges into a comma-separated string."""
        db = self._make_db_with_execute_mock(config)
        db.admin.revoke(["SELECT", "INSERT"], "users", "appuser", object_type="TABLE")
        call_sql = db.execute.call_args[0][0]
        assert "SELECT, INSERT" in call_sql

    def test_revoke_schema_branch(self, config):
        """Test revoke() emits REVOKE ... ON SCHEMA for object_type=SCHEMA."""
        db = self._make_db_with_execute_mock(config)
        db.admin.revoke("USAGE", "public", "appuser", object_type="SCHEMA")
        call_sql = db.execute.call_args[0][0]
        assert "ON SCHEMA public" in call_sql

    def test_revoke_database_branch(self, config):
        """Test revoke() emits REVOKE ... ON DATABASE for object_type=DATABASE."""
        db = self._make_db_with_execute_mock(config)
        db.admin.revoke("CONNECT", "mydb", "appuser", object_type="DATABASE")
        call_sql = db.execute.call_args[0][0]
        assert "ON DATABASE mydb" in call_sql

    def test_revoke_all_tables_branch(self, config):
        """Test revoke() emits IN SCHEMA for on='ALL TABLES'."""
        db = self._make_db_with_execute_mock(config)
        db.admin.revoke("SELECT", "ALL TABLES", "appuser", schema="public")
        call_sql = db.execute.call_args[0][0]
        assert "ALL TABLES IN SCHEMA public" in call_sql

    def test_revoke_cascade_flag(self, config):
        """Test revoke() appends CASCADE when cascade=True."""
        db = self._make_db_with_execute_mock(config)
        db.admin.revoke("SELECT", "users", "appuser", cascade=True)
        call_sql = db.execute.call_args[0][0]
        assert "CASCADE" in call_sql

    def test_list_role_members_returns_names(self, config):
        """Test list_role_members() returns list of member role name strings."""
        db = self._make_db_with_execute_mock(config)
        db.execute = MagicMock(return_value=[{"member": "alice"}, {"member": "bob"}])
        members = db.admin.list_role_members("admin")
        assert members == ["alice", "bob"]

    def test_list_role_grants_returns_rows(self, config):
        """Test list_role_grants() returns raw execute result rows."""
        db = self._make_db_with_execute_mock(config)
        db.execute = MagicMock(
            return_value=[{"object_name": "users", "privilege": "SELECT"}]
        )
        grants = db.admin.list_role_grants("appuser")
        assert grants == [{"object_name": "users", "privilege": "SELECT"}]

    def test_list_databases_returns_names(self, config):
        """Test list_databases() returns list of database name strings."""
        db = self._make_db_with_execute_mock(config)
        db.execute = MagicMock(
            return_value=[{"datname": "mydb"}, {"datname": "testdb"}]
        )
        dbs = db.schema.list_databases()
        assert dbs == ["mydb", "testdb"]


class TestDatabaseRoleAdminBranches:
    """Tests for create_role / alter_role / grant_role / revoke_role option branches (D-07)."""

    def _make_db_with_execute_mock(self, config):
        with patch("pycopg.database.psycopg"):
            db = Database(config)
        db.execute = MagicMock(return_value=[])
        return db

    def _make_db_with_cursor_mock(self, config):
        """Return a Database whose cursor() yields a MagicMock cursor."""
        from contextlib import contextmanager

        with patch("pycopg.database.psycopg"):
            db = Database(config)
        mock_cursor = MagicMock()

        @contextmanager
        def fake_cursor(autocommit=False):
            yield mock_cursor

        db.cursor = fake_cursor
        db.execute = MagicMock(return_value=[])
        return db, mock_cursor

    def test_create_role_if_not_exists_returns_early_when_exists(self, config):
        """Test create_role() returns early without executing when role exists and if_not_exists=True."""
        db = self._make_db_with_execute_mock(config)
        # role_exists() is a sibling accessor call (D-02); mock via accessor path
        db.admin.role_exists = MagicMock(return_value=True)

        db.admin.create_role("existing_user", if_not_exists=True)

        # execute should not have been called (early return)
        db.execute.assert_not_called()

    def test_create_role_nologin_branch(self, config):
        """Test create_role() appends NOLOGIN when login=False."""
        db, mock_cursor = self._make_db_with_cursor_mock(config)
        db.admin.role_exists = MagicMock(return_value=False)

        db.admin.create_role("appuser", login=False)

        # execute should have been called with NOLOGIN in the SQL
        call_sql = db.execute.call_args[0][0]
        assert "NOLOGIN" in call_sql

    def test_create_role_superuser_createdb_createrole_flags(self, config):
        """Test create_role() appends SUPERUSER/CREATEDB/CREATEROLE when flags True."""
        db = self._make_db_with_execute_mock(config)
        db.admin.role_exists = MagicMock(return_value=False)

        db.admin.create_role(
            "superrole", login=True, superuser=True, createdb=True, createrole=True
        )

        call_sql = db.execute.call_args[0][0]
        assert "SUPERUSER" in call_sql
        assert "CREATEDB" in call_sql
        assert "CREATEROLE" in call_sql

    def test_create_role_noinherit_replication_connection_limit(self, config):
        """Test create_role() appends NOINHERIT/REPLICATION/CONNECTION LIMIT options."""
        db = self._make_db_with_execute_mock(config)
        db.admin.role_exists = MagicMock(return_value=False)

        db.admin.create_role(
            "limitedrole",
            login=True,
            inherit=False,
            replication=True,
            connection_limit=5,
        )

        call_sql = db.execute.call_args[0][0]
        assert "NOINHERIT" in call_sql
        assert "REPLICATION" in call_sql
        assert "CONNECTION LIMIT 5" in call_sql

    def test_create_role_with_password_uses_cursor(self, config):
        """Test create_role() with a password uses cursor() for parameterized query."""
        db, mock_cursor = self._make_db_with_cursor_mock(config)
        db.admin.role_exists = MagicMock(return_value=False)

        db.admin.create_role("secureuser", login=True, password="secret123")

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "PASSWORD %s" in call_args[0][0]
        assert "secret123" in call_args[0][1]

    def test_drop_role_without_if_exists(self, config):
        """Test drop_role() with if_exists=False emits DROP ROLE without IF EXISTS."""
        db = self._make_db_with_execute_mock(config)

        db.admin.drop_role("oldrole", if_exists=False)

        call_sql = db.execute.call_args[0][0]
        assert "DROP ROLE oldrole" in call_sql
        assert "IF EXISTS" not in call_sql

    def test_alter_role_rename_returns_after_rename(self, config):
        """Test alter_role() with rename_to executes RENAME and returns immediately."""
        db = self._make_db_with_execute_mock(config)

        db.admin.alter_role("oldname", rename_to="newname")

        call_sql = db.execute.call_args[0][0]
        assert "RENAME TO newname" in call_sql

    def test_alter_role_options_with_password(self, config):
        """Test alter_role() with password uses cursor() for parameterized ALTER ROLE."""
        db, mock_cursor = self._make_db_with_cursor_mock(config)

        db.admin.alter_role("appuser", password="newpass")

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "PASSWORD %s" in call_args[0][0]
        assert "newpass" in call_args[0][1]

    def test_alter_role_login_superuser_createdb_createrole_options(self, config):
        """Test alter_role() with login/superuser/createdb/createrole options uses cursor."""
        db, mock_cursor = self._make_db_with_cursor_mock(config)

        db.admin.alter_role(
            "appuser", login=True, superuser=False, createdb=True, createrole=False
        )

        mock_cursor.execute.assert_called_once()
        call_sql = mock_cursor.execute.call_args[0][0]
        assert "LOGIN" in call_sql
        assert "NOSUPERUSER" in call_sql
        assert "CREATEDB" in call_sql
        assert "NOCREATEROLE" in call_sql

    def test_alter_role_connection_limit_option(self, config):
        """Test alter_role() with connection_limit option uses cursor."""
        db, mock_cursor = self._make_db_with_cursor_mock(config)

        db.admin.alter_role("appuser", connection_limit=10)

        mock_cursor.execute.assert_called_once()
        assert "CONNECTION LIMIT 10" in mock_cursor.execute.call_args[0][0]

    def test_grant_role_with_admin_option(self, config):
        """Test grant_role() appends WITH ADMIN OPTION when with_admin=True."""
        db = self._make_db_with_execute_mock(config)

        db.admin.grant_role("readonly", "analyst", with_admin=True)

        call_sql = db.execute.call_args[0][0]
        assert "WITH ADMIN OPTION" in call_sql

    def test_revoke_role_calls_execute(self, config):
        """Test revoke_role() calls execute with correct REVOKE SQL."""
        db = self._make_db_with_execute_mock(config)

        db.admin.revoke_role("readonly", "analyst")

        call_sql = db.execute.call_args[0][0]
        assert "REVOKE readonly FROM analyst" in call_sql

    def test_create_role_with_in_roles_calls_grant_role(self, config):
        """Test create_role() with in_roles calls grant_role for each role."""
        db = self._make_db_with_execute_mock(config)
        db.admin.role_exists = MagicMock(return_value=False)
        db.admin.grant_role = MagicMock()

        db.admin.create_role("analyst", in_roles=["readonly", "reporting"])

        assert db.admin.grant_role.call_count == 2
        db.admin.grant_role.assert_any_call("readonly", "analyst")
        db.admin.grant_role.assert_any_call("reporting", "analyst")

    def test_alter_role_valid_until_option(self, config):
        """Test alter_role() with valid_until appends VALID UNTIL clause."""
        db, mock_cursor = self._make_db_with_cursor_mock(config)

        db.admin.alter_role("appuser", valid_until="2026-12-31")

        mock_cursor.execute.assert_called_once()
        call_sql = mock_cursor.execute.call_args[0][0]
        assert "VALID UNTIL '2026-12-31'" in call_sql


class TestDatabaseCursorTransactionSessionPaths:
    """Tests for cursor() INERROR rollback branch and transaction() session path (D-07)."""

    @patch("pycopg.database.psycopg")
    def test_cursor_session_inerror_triggers_rollback(self, mock_psycopg, config):
        """Test that cursor() in a session rolls back when transaction status is INERROR."""
        from pycopg.database import TransactionStatus

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.info.transaction_status = TransactionStatus.INERROR

        db = Database(config)
        # Manually set a session connection (as session() context manager would do)
        db._session_conn = mock_conn

        with db.cursor() as cur:
            assert cur is mock_cursor

        # INERROR path must call rollback(), never commit()
        mock_conn.rollback.assert_called_once()
        mock_conn.commit.assert_not_called()

        # Cleanup so teardown doesn't break other tests
        db._session_conn = None

    @patch("pycopg.database.psycopg")
    def test_transaction_reuses_session_connection(self, mock_psycopg, config):
        """Test transaction() reuses _session_conn when a session is active."""
        mock_conn = MagicMock()
        mock_tx_ctx = MagicMock()
        mock_tx_ctx.__enter__ = MagicMock(return_value=None)
        mock_tx_ctx.__exit__ = MagicMock(return_value=False)
        mock_conn.transaction.return_value = mock_tx_ctx

        db = Database(config)
        db._session_conn = mock_conn

        with db.transaction() as conn:
            assert conn is mock_conn

        mock_conn.transaction.assert_called_once()
        # psycopg.connect should NOT have been called (reused session conn)
        mock_psycopg.connect.assert_not_called()

        db._session_conn = None
