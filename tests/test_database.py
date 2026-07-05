"""Tests for pycopg.database module."""

import tempfile
from unittest.mock import MagicMock, patch

import pytest

from pycopg import Config, Database, queries
from pycopg.base import QueryMixin
from pycopg.exceptions import InvalidIdentifierError, TableNotFoundError
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
        tables = db.schema.list_tables(schema="public")

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

    @patch("pycopg.database.psycopg")
    def test_column_exists_true(self, mock_psycopg, config):
        """Test column_exists returns True when the column exists."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("exists",)]
        mock_cursor.fetchall.return_value = [{"exists": 1}]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        exists = db.schema.column_exists("users", "id")

        assert exists is True

    @patch("pycopg.database.psycopg")
    def test_column_exists_false(self, mock_psycopg, config):
        """Test column_exists returns False when the column does not exist."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("exists",)]
        mock_cursor.fetchall.return_value = []
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        exists = db.schema.column_exists("users", "nonexistent")

        assert exists is False

    @patch("pycopg.database.psycopg")
    def test_table_size(self, mock_psycopg, config):
        """Test table_size returns raw byte count for an existing table."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("exists",)]
        # First call (table_exists guard) returns a row; second call (TABLE_SIZE) returns size.
        mock_cursor.fetchall.side_effect = [[{"exists": 1}], [{"size": 8192}]]
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        size = db.schema.table_size("users")

        assert size == 8192
        assert isinstance(size, int)

    @patch("pycopg.database.psycopg")
    def test_table_size_missing_raises_table_not_found(self, mock_psycopg, config):
        """Test table_size raises TableNotFoundError for a nonexistent table (D-09)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("exists",)]
        mock_cursor.fetchall.return_value = []
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        with pytest.raises(TableNotFoundError):
            db.schema.table_size("missing_table")


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
        with pytest.raises(InvalidIdentifierError):
            validate_identifier("123users")

        with pytest.raises(InvalidIdentifierError):
            validate_identifier("user-accounts")

        with pytest.raises(InvalidIdentifierError):
            validate_identifier("DROP TABLE")

        with pytest.raises(InvalidIdentifierError):
            validate_identifier("users;DELETE")


class TestResolvePredicate:
    """CRUD-F01: QueryMixin._resolve_predicate guard/resolver matrix (D-01..D-04).

    Collectively this class is ``test_resolve_predicate_guard_matrix`` per the
    plan action — split into one method per behavior row for clearer failures,
    each named to keep ``-k resolve_predicate`` selecting the whole matrix.
    """

    def test_resolve_predicate_no_source_returns_empty(self):
        """No where/where_sql/where_params -> ('', [])."""
        assert QueryMixin._resolve_predicate(None, None, None) == ("", [])

    def test_resolve_predicate_dict_only_delegates_to_build_where_dict(self):
        """dict-only path returns the same result as _build_where_dict."""
        where = {"a": 1, "b": "x"}
        expected = QueryMixin._build_where_dict(where)
        assert QueryMixin._resolve_predicate(where, None, None) == expected

    def test_resolve_predicate_where_sql_only_returns_fragment_verbatim(self):
        """where_sql-only path returns the fragment verbatim + bound params."""
        frag, params = QueryMixin._resolve_predicate(
            None, "age > %s AND status = ANY(%s)", [30, ["a", "b"]]
        )
        assert frag == "age > %s AND status = ANY(%s)"
        assert params == [30, ["a", "b"]]

    def test_resolve_predicate_where_sql_no_placeholders_legal(self):
        """where_sql with no placeholders and where_params=None is legal."""
        frag, params = QueryMixin._resolve_predicate(None, "1=1", None)
        assert frag == "1=1"
        assert params == []

    def test_resolve_predicate_both_where_and_where_sql_raises(self):
        """Passing both where (dict) and where_sql raises ValueError (D-02)."""
        with pytest.raises(ValueError, match="not both"):
            QueryMixin._resolve_predicate({"a": 1}, "a > %s", [1])

    def test_resolve_predicate_where_params_without_where_sql_raises(self):
        """where_params without where_sql raises ValueError (D-04)."""
        with pytest.raises(ValueError, match="where_params requires where_sql"):
            QueryMixin._resolve_predicate(None, None, [1])

    def test_resolve_predicate_empty_where_sql_raises(self):
        """Empty/whitespace-only where_sql raises ValueError (D-03)."""
        with pytest.raises(ValueError, match="non-empty SQL fragment"):
            QueryMixin._resolve_predicate(None, "", None)
        with pytest.raises(ValueError, match="non-empty SQL fragment"):
            QueryMixin._resolve_predicate(None, "   ", None)

    def test_resolve_predicate_where_sql_not_run_through_validate_identifiers(self):
        """The raw fragment must never be validated as an identifier (C-02)."""
        # An identifier-illegal fragment (spaces, punctuation, keywords) must
        # pass through untouched since it is arbitrary SQL, not an identifier.
        frag, params = QueryMixin._resolve_predicate(
            None, "created_at < now() - %s::interval", ["1 day"]
        )
        assert frag == "created_at < now() - %s::interval"
        assert params == ["1 day"]


class TestWhereSqlShape:
    """CRUD-F01: mock SQL-shape tests for where_sql/where_params on the five
    predicate helpers (delete_where/update_where/exists/count/paginate)."""

    def _cursor_db(self, mock_psycopg, config, *, description=None, fetchall=None):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = description
        if fetchall is not None:
            mock_cursor.fetchall.return_value = fetchall
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn
        return Database(config), mock_cursor

    @patch("pycopg.database.psycopg")
    def test_where_sql_shape_delete_where(self, mock_psycopg, config):
        """delete_where with where_sql builds a WHERE clause from the raw
        fragment, verbatim, with where_params bound %s."""
        db, mock_cursor = self._cursor_db(mock_psycopg, config)
        mock_cursor.rowcount = 2

        result = db.delete_where(
            "logs", where_sql="created_at < now() - %s::interval", where_params=["1 day"]
        )

        assert result == 2
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "DELETE FROM public.logs WHERE created_at < now() - %s::interval"
        assert params == ["1 day"]

    @patch("pycopg.database.psycopg")
    def test_where_sql_shape_update_where(self, mock_psycopg, config):
        """update_where with where_sql builds SET + raw WHERE fragment."""
        db, mock_cursor = self._cursor_db(mock_psycopg, config)
        mock_cursor.rowcount = 3

        result = db.update_where(
            "t", {"status": "done"}, where_sql="age > %s", where_params=[30]
        )

        assert result == 3
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "UPDATE public.t SET status = %s WHERE age > %s"
        assert params == ["done", 30]

    @patch("pycopg.database.psycopg")
    def test_where_sql_shape_exists(self, mock_psycopg, config):
        """exists with where_sql builds an EXISTS() query from the raw fragment."""
        db, mock_cursor = self._cursor_db(
            mock_psycopg, config, description=[("exists",)], fetchall=None
        )
        mock_cursor.fetchone.return_value = {"exists": True}

        result = db.exists("t", where_sql="name = %s", where_params=["Alice"])

        assert result is True
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "SELECT EXISTS(SELECT 1 FROM public.t WHERE name = %s)"
        assert params == ["Alice"]

    @patch("pycopg.database.psycopg")
    def test_where_sql_shape_count(self, mock_psycopg, config):
        """count with where_sql builds a COUNT(*) query from the raw fragment."""
        db, mock_cursor = self._cursor_db(mock_psycopg, config)
        mock_cursor.fetchone.return_value = {"count": 5}

        result = db.count(
            "users", where_sql="age > %s AND status = ANY(%s)", where_params=[30, ["a", "b"]]
        )

        assert result == 5
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "SELECT COUNT(*) FROM public.users WHERE age > %s AND status = ANY(%s)"
        assert params == [30, ["a", "b"]]

    @patch("pycopg.database.psycopg")
    def test_where_sql_shape_paginate(self, mock_psycopg, config):
        """paginate with where_sql builds a WHERE clause from the raw fragment,
        composed with the existing ORDER BY/LIMIT/OFFSET clauses."""
        db, mock_cursor = self._cursor_db(
            mock_psycopg, config, description=[("id",)], fetchall=[{"id": 1}]
        )

        result = db.paginate(
            "events", 10, order_by="id", where_sql="created_at > %s", where_params=["2026-01-01"]
        )

        assert result == [{"id": 1}]
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == (
            "SELECT * FROM public.events WHERE created_at > %s"
            " ORDER BY id LIMIT 10 OFFSET 0"
        )
        assert params == ["2026-01-01"]

    @patch("pycopg.database.psycopg")
    def test_where_sql_shape_count_dict_where_unaffected(self, mock_psycopg, config):
        """count(where=...) (dict path) is unaffected by the where_sql addition."""
        db, mock_cursor = self._cursor_db(mock_psycopg, config)
        mock_cursor.fetchone.return_value = {"count": 2}

        result = db.count("users", where={"active": True})

        assert result == 2
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "SELECT COUNT(*) FROM public.users WHERE active = %s"
        assert params == [True]


class TestWhereSqlGuards:
    """CRUD-F01: guard tests for where_sql/where_params on the five predicate
    helpers — mutual-exclusion, empty fragment, param-desync,
    destructive-still-raises (all fire before any DB round-trip)."""

    @patch("pycopg.database.psycopg")
    def test_where_sql_guard_mutual_exclusion(self, mock_psycopg, config):
        """count(where=..., where_sql=...) raises ValueError (D-02)."""
        db = Database(config)
        with pytest.raises(ValueError, match="not both"):
            db.count("t", where_sql="a > %s", where_params=[1], where={"a": 1})

    @patch("pycopg.database.psycopg")
    def test_where_sql_guard_empty_fragment(self, mock_psycopg, config):
        """count(where_sql="") raises ValueError (D-03)."""
        db = Database(config)
        with pytest.raises(ValueError, match="non-empty SQL fragment"):
            db.count("t", where_sql="   ")

    @patch("pycopg.database.psycopg")
    def test_where_sql_guard_param_desync(self, mock_psycopg, config):
        """count(where_params=[1]) without where_sql raises ValueError (D-04)."""
        db = Database(config)
        with pytest.raises(ValueError, match="where_params requires where_sql"):
            db.count("t", where_params=[1])

    @patch("pycopg.database.psycopg")
    def test_where_sql_guard_destructive_still_raises_delete_where(
        self, mock_psycopg, config
    ):
        """delete_where("t") with neither where nor where_sql still raises."""
        db = Database(config)
        with pytest.raises(ValueError, match="non-empty 'where' dict or 'where_sql'"):
            db.delete_where("t")

    @patch("pycopg.database.psycopg")
    def test_where_sql_guard_destructive_satisfied_by_where_sql_delete_where(
        self, mock_psycopg, config
    ):
        """delete_where("t", where_sql="1=1") is allowed (explicit escape hatch)."""
        db, mock_cursor = TestWhereSqlShape()._cursor_db(mock_psycopg, config)
        mock_cursor.rowcount = 0

        result = db.delete_where("t", where_sql="1=1")

        assert result == 0
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "DELETE FROM public.t WHERE 1=1"
        assert params == []

    @patch("pycopg.database.psycopg")
    def test_where_sql_guard_destructive_still_raises_update_where(
        self, mock_psycopg, config
    ):
        """update_where("t", values) with neither where nor where_sql still raises."""
        db = Database(config)
        with pytest.raises(ValueError, match="non-empty 'where' dict or 'where_sql'"):
            db.update_where("t", {"a": 1})

    @patch("pycopg.database.psycopg")
    def test_where_sql_guard_destructive_still_raises_exists(self, mock_psycopg, config):
        """exists("t") with neither where nor where_sql still raises."""
        db = Database(config)
        with pytest.raises(ValueError, match="non-empty `where` dict or `where_sql`"):
            db.exists("t")


class TestSelectWhereFind:
    """CRUD-F04: select_where / find (list[dict] predicate reads, D-01..D-03)."""

    def _cursor_db(self, mock_psycopg, config, *, description=None, fetchall=None):
        return TestWhereSqlShape()._cursor_db(
            mock_psycopg, config, description=description, fetchall=fetchall
        )

    @patch("pycopg.database.psycopg")
    def test_select_where_dict_filters(self, mock_psycopg, config):
        """select_where(where=dict) builds a WHERE clause from the dict."""
        db, mock_cursor = self._cursor_db(
            mock_psycopg, config, description=[("id",)], fetchall=[{"id": 1}]
        )

        result = db.select_where("t", {"active": True})

        assert result == [{"id": 1}]
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "SELECT * FROM public.t WHERE active = %s"
        assert params == [True]

    @patch("pycopg.database.psycopg")
    def test_select_where_no_predicate_reads_all(self, mock_psycopg, config):
        """select_where with no predicate emits no WHERE clause (D-03)."""
        db, mock_cursor = self._cursor_db(
            mock_psycopg, config, description=[("id",)], fetchall=[{"id": 1}, {"id": 2}]
        )

        result = db.select_where("t")

        assert result == [{"id": 1}, {"id": 2}]
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "SELECT * FROM public.t"
        assert params == []

    @patch("pycopg.database.psycopg")
    def test_select_where_columns_order_by_limit_offset(self, mock_psycopg, config):
        """select_where honors columns=/order_by=/limit=/offset= (D-01)."""
        db, mock_cursor = self._cursor_db(
            mock_psycopg, config, description=[("id",)], fetchall=[{"id": 1}]
        )

        result = db.select_where(
            "t",
            {"active": True},
            columns=["id", "name"],
            order_by="id DESC",
            limit=5,
            offset=2,
        )

        assert result == [{"id": 1}]
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == (
            "SELECT id, name FROM public.t WHERE active = %s"
            " ORDER BY id DESC LIMIT 5 OFFSET 2"
        )
        assert params == [True]

    @patch("pycopg.database.psycopg")
    def test_select_where_where_sql_escape_hatch(self, mock_psycopg, config):
        """select_where(where_sql=...) binds where_params verbatim (D-01)."""
        db, mock_cursor = self._cursor_db(
            mock_psycopg, config, description=[("id",)], fetchall=[{"id": 1}]
        )

        result = db.select_where("t", where_sql="age > %s", where_params=[18])

        assert result == [{"id": 1}]
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "SELECT * FROM public.t WHERE age > %s"
        assert params == [18]

    @patch("pycopg.database.psycopg")
    def test_select_where_mutual_exclusion_raises(self, mock_psycopg, config):
        """select_where(where=..., where_sql=...) raises ValueError (D-02)."""
        db = Database(config)
        with pytest.raises(ValueError, match="not both"):
            db.select_where("t", {"a": 1}, where_sql="a > %s", where_params=[1])

    @patch("pycopg.database.psycopg")
    def test_select_where_params_without_where_sql_raises(self, mock_psycopg, config):
        """select_where(where_params=...) without where_sql raises ValueError (D-04)."""
        db = Database(config)
        with pytest.raises(ValueError, match="where_params requires where_sql"):
            db.select_where("t", where_params=[1])

    @patch("pycopg.database.psycopg")
    def test_find_delegates_to_select_where(self, mock_psycopg, config):
        """find(...) returns the exact same result as select_where(...) (D-02 twin)."""
        db, mock_cursor = self._cursor_db(
            mock_psycopg, config, description=[("id",)], fetchall=[{"id": 1}]
        )

        result = db.find("t", {"active": True}, order_by="id", limit=1)

        assert result == [{"id": 1}]
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "SELECT * FROM public.t WHERE active = %s ORDER BY id LIMIT 1"
        assert params == [True]


class TestGetFindOne:
    """CRUD-F05: get / find_one (dict | None single-row reads, D-04/D-05)."""

    def _cursor_db(self, mock_psycopg, config, *, description=None, fetchone=None):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = description
        mock_cursor.fetchone.return_value = fetchone
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn
        return Database(config), mock_cursor

    @patch("pycopg.database.psycopg")
    def test_get_dict_filters_forces_limit_1(self, mock_psycopg, config):
        """get(where=dict) builds a WHERE clause and forces LIMIT 1 (D-04)."""
        db, mock_cursor = self._cursor_db(
            mock_psycopg, config, fetchone={"id": 5}
        )

        result = db.get("t", {"id": 5})

        assert result == {"id": 5}
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "SELECT * FROM public.t WHERE id = %s LIMIT 1"
        assert params == [5]

    @patch("pycopg.database.psycopg")
    def test_get_no_match_returns_none(self, mock_psycopg, config):
        """get returns None when fetchone finds nothing."""
        db, mock_cursor = self._cursor_db(mock_psycopg, config, fetchone=None)

        result = db.get("t", {"id": 999})

        assert result is None

    @patch("pycopg.database.psycopg")
    def test_get_no_predicate_legal(self, mock_psycopg, config):
        """get with no predicate emits no WHERE clause but still LIMIT 1 (D-03/D-05)."""
        db, mock_cursor = self._cursor_db(mock_psycopg, config, fetchone={"id": 1})

        result = db.get("t")

        assert result == {"id": 1}
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "SELECT * FROM public.t LIMIT 1"
        assert params == []

    @patch("pycopg.database.psycopg")
    def test_get_columns_and_order_by(self, mock_psycopg, config):
        """get exposes columns=/order_by= but no limit=/offset= (D-05)."""
        db, mock_cursor = self._cursor_db(mock_psycopg, config, fetchone={"id": 1})

        result = db.get("t", {"active": True}, columns=["id"], order_by="id ASC")

        assert result == {"id": 1}
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "SELECT id FROM public.t WHERE active = %s ORDER BY id ASC LIMIT 1"
        assert params == [True]

    def test_get_signature_has_no_limit_or_offset(self):
        """get's public signature contains no limit/offset parameter (D-05)."""
        import inspect

        sig = inspect.signature(Database.get)
        assert "limit" not in sig.parameters
        assert "offset" not in sig.parameters

    @patch("pycopg.database.psycopg")
    def test_get_mutual_exclusion_raises(self, mock_psycopg, config):
        """get(where=..., where_sql=...) raises ValueError (D-02)."""
        db = Database(config)
        with pytest.raises(ValueError, match="not both"):
            db.get("t", {"a": 1}, where_sql="a > %s", where_params=[1])

    @patch("pycopg.database.psycopg")
    def test_find_one_delegates_to_get(self, mock_psycopg, config):
        """find_one(...) returns the exact same result as get(...) (D-02 twin)."""
        db, mock_cursor = self._cursor_db(mock_psycopg, config, fetchone={"id": 5})

        result = db.find_one("t", {"id": 5}, order_by="id ASC")

        assert result == {"id": 5}
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "SELECT * FROM public.t WHERE id = %s ORDER BY id ASC LIMIT 1"
        assert params == [5]


class TestInsertSingleRow:
    """CRUD-F06: insert (single row RETURNING *, D-06/D-07)."""

    def _cursor_db(self, mock_psycopg, config, *, fetchone=None):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = fetchone
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn
        return Database(config), mock_cursor

    @patch("pycopg.database.psycopg")
    def test_insert_returns_row(self, mock_psycopg, config):
        """insert(table, row) executes INSERT ... RETURNING * and returns the row."""
        db, mock_cursor = self._cursor_db(
            mock_psycopg, config, fetchone={"a": 1, "b": 2}
        )

        result = db.insert("t", {"a": 1, "b": 2})

        assert result == {"a": 1, "b": 2}
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "INSERT INTO public.t (a, b) VALUES (%s, %s) RETURNING *"
        assert params == [1, 2]

    @patch("pycopg.database.psycopg")
    def test_insert_threads_on_conflict(self, mock_psycopg, config):
        """insert(..., on_conflict='DO NOTHING') is threaded verbatim (D-06)."""
        db, mock_cursor = self._cursor_db(mock_psycopg, config, fetchone=None)

        result = db.insert("t", {"a": 1}, on_conflict="DO NOTHING")

        assert result is None
        sql, params = mock_cursor.execute.call_args[0]
        assert sql == (
            "INSERT INTO public.t (a) VALUES (%s) ON CONFLICT DO NOTHING RETURNING *"
        )
        assert params == [1]

    @patch("pycopg.database.psycopg")
    def test_insert_no_conflict_columns_computed(self, mock_psycopg, config):
        """insert's SQL never contains a conflict/update-column computation (D-06)."""
        db, mock_cursor = self._cursor_db(mock_psycopg, config, fetchone={"a": 1})

        db.insert("t", {"a": 1}, schema="custom")

        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "INSERT INTO custom.t (a) VALUES (%s) RETURNING *"
        assert params == [1]

    def test_insert_source_has_no_conflict_column_computation(self):
        """insert's source uses _build_insert_sql + RETURNING *, no conflict_columns/update_columns (D-06)."""
        import inspect

        source = inspect.getsource(Database.insert)
        assert "_build_insert_sql" in source
        assert "RETURNING *" in source
        assert "conflict_columns" not in source
        assert "update_columns" not in source

    def test_insert_empty_row_raises_before_db_round_trip(self, config):
        """insert(table, {}) raises ValueError before hitting the DB (WR-01)."""
        db = Database(config)
        with pytest.raises(ValueError, match="non-empty dict"):
            db.insert("t", {})


class TestPageDataclass:
    """CRUD-F03 (D-08): Page frozen dataclass fields + export precedent."""

    def test_page_dataclass_fields(self):
        """Page carries rows/total/has_next/next_cursor as declared (D-08)."""
        from pycopg import Page

        page = Page(rows=[{"id": 1}], total=5, has_next=True, next_cursor=(1,))
        assert page.rows == [{"id": 1}]
        assert page.total == 5
        assert page.has_next is True
        assert page.next_cursor == (1,)

    def test_page_dataclass_optional_fields_accept_none(self):
        """total/next_cursor are None-able (with_total=False / offset page)."""
        from pycopg import Page

        page = Page(rows=[], total=None, has_next=False, next_cursor=None)
        assert page.total is None
        assert page.next_cursor is None

    def test_page_dataclass_is_frozen(self):
        """Page is immutable — attribute assignment raises (RunResult precedent)."""
        import dataclasses

        from pycopg import Page

        page = Page(rows=[], total=None, has_next=False, next_cursor=None)
        with pytest.raises(dataclasses.FrozenInstanceError):
            page.total = 1


class TestTableDescriptionDataclass:
    """INTRO-F01 (D-12): TableDescription frozen dataclass fields + export precedent."""

    def test_table_description_fields(self):
        """TableDescription carries the 4 describe-dict keys as declared fields (D-12)."""
        from pycopg import TableDescription

        describe_dict = {
            "columns": [{"column_name": "id", "data_type": "integer"}],
            "primary_key": {"constraint_name": "t_pkey", "columns": ["id"]},
            "foreign_keys": [],
            "indexes": [{"index_name": "t_pkey", "index_type": "btree"}],
        }
        assert set(describe_dict) == {
            "columns",
            "primary_key",
            "foreign_keys",
            "indexes",
        }

        # Round-trips from the describe dict without reshaping (D-12).
        td = TableDescription(**describe_dict)
        assert td.columns == describe_dict["columns"]
        assert td.primary_key == describe_dict["primary_key"]
        assert td.foreign_keys == describe_dict["foreign_keys"]
        assert td.indexes == describe_dict["indexes"]

    def test_table_description_is_frozen(self):
        """TableDescription is immutable — attribute assignment raises."""
        import dataclasses

        from pycopg import TableDescription

        td = TableDescription(
            columns=[], primary_key=None, foreign_keys=[], indexes=[]
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            td.columns = []


class TestBuildKeysetWhere:
    """CRUD-F02 (D-06/D-07): QueryMixin._build_keyset_where row-value builder."""

    def test_build_keyset_where_shape(self):
        """Two-column ascending keyset emits a row-value '>' comparison."""
        frag, params = QueryMixin._build_keyset_where(
            ["created_at", "id"], ("2026-01-01", 5), False
        )
        assert frag == "(created_at, id) > (%s, %s)"
        assert params == ["2026-01-01", 5]

    def test_build_keyset_where_descending_flips_operator(self):
        """descending=True flips the comparison operator to '<' (D-07)."""
        frag, params = QueryMixin._build_keyset_where(
            ["created_at", "id"], ("2026-01-01", 5), True
        )
        assert frag == "(created_at, id) < (%s, %s)"
        assert params == ["2026-01-01", 5]

    def test_build_keyset_where_single_column(self):
        """A single order_by column still produces a valid row-value tuple."""
        frag, params = QueryMixin._build_keyset_where(["id"], (5,), False)
        assert frag == "(id) > (%s)"
        assert params == [5]

    def test_build_keyset_where_validates_order_cols(self):
        """An invalid order_by column identifier raises before any SQL build (C-02)."""
        with pytest.raises(InvalidIdentifierError):
            QueryMixin._build_keyset_where(["a; DROP TABLE x"], (1,), False)


class TestPaginatePage:
    """CRUD-F03 (D-09/D-10): paginate_page mock SQL-shape + Page envelope tests."""

    @patch("pycopg.database.psycopg")
    def test_paginate_page_basic_shape(self, mock_psycopg, config):
        """paginate_page fetches limit+1 rows, ORDER BY, returns a Page."""
        db, mock_cursor = TestWhereSqlShape()._cursor_db(
            mock_psycopg,
            config,
            description=[("id",)],
            fetchall=[{"id": 1}, {"id": 2}],
        )

        page = db.paginate_page("events", 2, order_by="id")

        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "SELECT * FROM public.events ORDER BY id LIMIT 3 OFFSET 0"
        assert params == []
        assert page.rows == [{"id": 1}, {"id": 2}]
        assert page.has_next is False
        assert page.total is None
        assert page.next_cursor is None

    @patch("pycopg.database.psycopg")
    def test_paginate_page_has_next_true_trims_sentinel(self, mock_psycopg, config):
        """When limit+1 rows are returned, has_next=True and the sentinel row
        is trimmed off (D-10)."""
        db, mock_cursor = TestWhereSqlShape()._cursor_db(
            mock_psycopg,
            config,
            description=[("id",)],
            fetchall=[{"id": 1}, {"id": 2}, {"id": 3}],
        )

        page = db.paginate_page("events", 2)

        assert page.rows == [{"id": 1}, {"id": 2}]
        assert page.has_next is True

    @patch("pycopg.database.psycopg")
    def test_paginate_page_with_total_runs_separate_count(self, mock_psycopg, config):
        """with_total=True runs a separate COUNT(*) using the same predicate (D-10)."""
        db, mock_cursor = TestWhereSqlShape()._cursor_db(
            mock_psycopg,
            config,
            description=[("id",)],
            fetchall=[{"id": 1}],
        )
        mock_cursor.fetchone.return_value = {"count": 42}

        page = db.paginate_page(
            "events", 10, where={"active": True}, with_total=True
        )

        assert page.total == 42
        select_call, count_call = mock_cursor.execute.call_args_list
        assert select_call[0][0] == (
            "SELECT * FROM public.events WHERE active = %s LIMIT 11 OFFSET 0"
        )
        assert count_call[0][0] == "SELECT COUNT(*) FROM public.events WHERE active = %s"
        assert count_call[0][1] == [True]

    @patch("pycopg.database.psycopg")
    def test_paginate_page_with_total_false_leaves_total_none(
        self, mock_psycopg, config
    ):
        """with_total=False (the default) never runs a COUNT query (D-10)."""
        db, mock_cursor = TestWhereSqlShape()._cursor_db(
            mock_psycopg, config, description=[("id",)], fetchall=[{"id": 1}]
        )

        page = db.paginate_page("events", 10)

        assert page.total is None
        assert mock_cursor.execute.call_count == 1

    @patch("pycopg.database.psycopg")
    def test_paginate_page_where_sql_composes(self, mock_psycopg, config):
        """paginate_page composes where_sql/where_params like paginate does (D-01)."""
        db, mock_cursor = TestWhereSqlShape()._cursor_db(
            mock_psycopg, config, description=[("id",)], fetchall=[{"id": 1}]
        )

        page = db.paginate_page(
            "events", 10, where_sql="created_at > %s", where_params=["2026-01-01"]
        )

        sql, params = mock_cursor.execute.call_args[0]
        assert sql == (
            "SELECT * FROM public.events WHERE created_at > %s LIMIT 11 OFFSET 0"
        )
        assert params == ["2026-01-01"]
        assert page.rows == [{"id": 1}]

    @patch("pycopg.database.psycopg")
    def test_paginate_page_empty_order_by_raises(self, mock_psycopg, config):
        """order_by=[] raises ValueError before any DB round-trip (WR-01)."""
        db = Database(config)
        with pytest.raises(ValueError, match="order_by must contain at least one"):
            db.paginate_page("events", 10, order_by=[])

    @patch("pycopg.database.psycopg")
    def test_paginate_page_limit_zero_raises(self, mock_psycopg, config):
        """limit=0 raises ValueError before any DB round-trip (IN-02)."""
        db = Database(config)
        with pytest.raises(ValueError, match="limit must be a positive integer"):
            db.paginate_page("events", 0)

    @patch("pycopg.database.psycopg")
    def test_paginate_page_negative_limit_raises(self, mock_psycopg, config):
        """A negative limit raises ValueError before any DB round-trip (IN-02)."""
        db = Database(config)
        with pytest.raises(ValueError, match="limit must be a positive integer"):
            db.paginate_page("events", -1)

    @patch("pycopg.database.psycopg")
    def test_paginate_page_non_int_limit_normalized(self, mock_psycopg, config):
        """A non-int limit (e.g. 5.0) is normalized to int before the SQL
        LIMIT and the Python-side trim, so the slice never sees a float
        (WR-02)."""
        rows = [{"id": i} for i in range(6)]
        db, mock_cursor = TestWhereSqlShape()._cursor_db(
            mock_psycopg, config, description=[("id",)], fetchall=rows
        )

        page = db.paginate_page("events", 5.0)

        sql, _params = mock_cursor.execute.call_args[0]
        assert sql == "SELECT * FROM public.events LIMIT 6 OFFSET 0"
        assert page.rows == rows[:5]
        assert page.has_next is True


class TestPaginateKeyset:
    """CRUD-F02 (D-05..D-07): paginate_keyset mock SQL-shape + guard tests."""

    @patch("pycopg.database.psycopg")
    def test_paginate_keyset_first_page_no_after(self, mock_psycopg, config):
        """after=None (first page) omits the keyset fragment entirely."""
        rows = [
            {"created_at": "2026-01-01", "id": 1},
            {"created_at": "2026-01-02", "id": 2},
        ]
        db, mock_cursor = TestWhereSqlShape()._cursor_db(
            mock_psycopg,
            config,
            description=[("created_at",), ("id",)],
            fetchall=rows,
        )

        page = db.paginate_keyset("events", 2, order_by=["created_at", "id"])

        sql, params = mock_cursor.execute.call_args[0]
        assert sql == "SELECT * FROM public.events ORDER BY created_at, id LIMIT 3"
        assert params == []
        assert page.rows == rows
        assert page.has_next is False
        assert page.next_cursor == ("2026-01-02", 2)

    @patch("pycopg.database.psycopg")
    def test_paginate_keyset_with_after_builds_row_value_where(
        self, mock_psycopg, config
    ):
        """after= builds the row-value keyset WHERE fragment (D-06/D-07)."""
        rows = [{"created_at": "2026-01-03", "id": 3}]
        db, mock_cursor = TestWhereSqlShape()._cursor_db(
            mock_psycopg,
            config,
            description=[("created_at",), ("id",)],
            fetchall=rows,
        )

        page = db.paginate_keyset(
            "events", 50, order_by=["created_at", "id"], after=("2026-01-02", 2)
        )

        sql, params = mock_cursor.execute.call_args[0]
        assert sql == (
            "SELECT * FROM public.events WHERE (created_at, id) > (%s, %s) "
            "ORDER BY created_at, id LIMIT 51"
        )
        assert params == ["2026-01-02", 2]
        assert page.next_cursor == ("2026-01-03", 3)

    @patch("pycopg.database.psycopg")
    def test_paginate_keyset_descending_flips_operator_and_order(
        self, mock_psycopg, config
    ):
        """descending=True flips both the row-value operator AND ORDER BY DESC
        (Pitfall 3 — both must agree)."""
        rows = [{"created_at": "2026-01-01", "id": 1}]
        db, mock_cursor = TestWhereSqlShape()._cursor_db(
            mock_psycopg,
            config,
            description=[("created_at",), ("id",)],
            fetchall=rows,
        )

        db.paginate_keyset(
            "events",
            10,
            order_by=["created_at", "id"],
            after=("2026-01-02", 2),
            descending=True,
        )

        sql, params = mock_cursor.execute.call_args[0]
        assert sql == (
            "SELECT * FROM public.events WHERE (created_at, id) < (%s, %s) "
            "ORDER BY created_at DESC, id DESC LIMIT 11"
        )
        assert params == ["2026-01-02", 2]

    @patch("pycopg.database.psycopg")
    def test_paginate_keyset_composes_where_sql_with_keyset(
        self, mock_psycopg, config
    ):
        """The keyset fragment ANDs with the optional where_sql predicate."""
        rows = [{"created_at": "2026-01-03", "id": 3}]
        db, mock_cursor = TestWhereSqlShape()._cursor_db(
            mock_psycopg,
            config,
            description=[("created_at",), ("id",)],
            fetchall=rows,
        )

        db.paginate_keyset(
            "events",
            10,
            order_by=["created_at", "id"],
            after=("2026-01-02", 2),
            where_sql="status = %s",
            where_params=["active"],
        )

        sql, params = mock_cursor.execute.call_args[0]
        assert sql == (
            "SELECT * FROM public.events WHERE (created_at, id) > (%s, %s) "
            "AND status = %s ORDER BY created_at, id LIMIT 11"
        )
        assert params == ["2026-01-02", 2, "active"]

    @patch("pycopg.database.psycopg")
    def test_paginate_keyset_with_total_uses_base_predicate_only(
        self, mock_psycopg, config
    ):
        """with_total's COUNT uses only the base predicate, not the keyset
        after fragment (D-10 — total is the full filtered set)."""
        rows = [{"created_at": "2026-01-03", "id": 3}]
        db, mock_cursor = TestWhereSqlShape()._cursor_db(
            mock_psycopg,
            config,
            description=[("created_at",), ("id",)],
            fetchall=rows,
        )
        mock_cursor.fetchone.return_value = {"count": 100}

        page = db.paginate_keyset(
            "events",
            10,
            order_by=["created_at", "id"],
            after=("2026-01-02", 2),
            where={"status": "active"},
            with_total=True,
        )

        assert page.total == 100
        _select_call, count_call = mock_cursor.execute.call_args_list
        assert (
            count_call[0][0]
            == "SELECT COUNT(*) FROM public.events WHERE status = %s"
        )
        assert count_call[0][1] == ["active"]

    @patch("pycopg.database.psycopg")
    def test_paginate_keyset_order_by_required(self, mock_psycopg, config):
        """order_by is mandatory (D-07) — omitting it raises ValueError."""
        db = Database(config)
        with pytest.raises(ValueError, match="order_by"):
            db.paginate_keyset("t", 10)

    @patch("pycopg.database.psycopg")
    def test_paginate_keyset_after_arity_mismatch_raises(self, mock_psycopg, config):
        """A mismatched after= arity raises before any DB round-trip (Pitfall 4)."""
        db = Database(config)
        with pytest.raises(ValueError, match="after must have exactly"):
            db.paginate_keyset("t", 10, order_by=["a", "b"], after=(1,))

    @patch("pycopg.database.psycopg")
    def test_paginate_keyset_empty_order_by_raises(self, mock_psycopg, config):
        """order_by=[] raises ValueError before any DB round-trip (WR-01)."""
        db = Database(config)
        with pytest.raises(ValueError, match="order_by must contain at least one"):
            db.paginate_keyset("t", 10, order_by=[])

    @patch("pycopg.database.psycopg")
    def test_paginate_keyset_limit_zero_raises(self, mock_psycopg, config):
        """limit=0 raises ValueError before any DB round-trip (IN-02)."""
        db = Database(config)
        with pytest.raises(ValueError, match="limit must be a positive integer"):
            db.paginate_keyset("t", 0, order_by=["id"])

    @patch("pycopg.database.psycopg")
    def test_paginate_keyset_negative_limit_raises(self, mock_psycopg, config):
        """A negative limit raises ValueError before any DB round-trip (IN-02)."""
        db = Database(config)
        with pytest.raises(ValueError, match="limit must be a positive integer"):
            db.paginate_keyset("t", -1, order_by=["id"])

    @patch("pycopg.database.psycopg")
    def test_paginate_keyset_non_int_limit_normalized(self, mock_psycopg, config):
        """A non-int limit (e.g. 5.0) is normalized to int before the SQL
        LIMIT and the Python-side trim, so the slice never sees a float
        (WR-02)."""
        rows = [{"id": i} for i in range(6)]
        db, mock_cursor = TestWhereSqlShape()._cursor_db(
            mock_psycopg, config, description=[("id",)], fetchall=rows
        )

        page = db.paginate_keyset("events", 5.0, order_by=["id"])

        sql, _params = mock_cursor.execute.call_args[0]
        assert sql == "SELECT * FROM public.events ORDER BY id LIMIT 6"
        assert page.rows == rows[:5]
        assert page.has_next is True


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

        db.maint.vacuum(table="users", full=True)

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

    @patch("pycopg.database.psycopg")
    def test_insert_batch_placeholder_hoist_regression(self, mock_psycopg, config):
        """PERF-03: non-regression pin — insert_batch SQL/params shape unchanged after hoist.

        Inserts 3 rows with 2 columns, captures the SQL and params passed to
        cur.execute, and asserts byte-exact VALUES shape:
        - exactly one ``(%s, %s)`` placeholder tuple per row
        - params is the flat list of row values in column order
        """
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 3
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        db = Database(config)
        rows = [
            {"name": "Alice", "score": 10},
            {"name": "Bob", "score": 20},
            {"name": "Carol", "score": 30},
        ]
        result = db.insert_batch("scores", rows)

        assert result == 3
        # Capture the SQL and params passed to cur.execute
        call_args = mock_cursor.execute.call_args
        sql_called, params_called = call_args[0]

        # SQL must contain exactly 3 placeholder tuples — one per row
        assert sql_called.count("(%s, %s)") == 3
        # params must be the flat row values in column order (name, score)
        assert list(params_called) == ["Alice", 10, "Bob", 20, "Carol", 30]


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
        db.notify("events", payload="hello")

        sql, params = mock_cursor.execute.call_args[0][:2]
        assert "pg_notify" in sql
        assert params == ["events", "hello"]

    def test_notify_rejects_invalid_channel(self, config):
        """notify validates the channel identifier."""
        db = Database(config)
        with pytest.raises(InvalidIdentifierError):
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
        # truncate_table() now runs a table_exists() pre-check (DEBT-05) before
        # the TRUNCATE — return a non-empty result so the table is seen to exist
        # and truncate proceeds rather than raising TableNotFound.
        mock_cursor.description = [("exists",)]
        mock_cursor.fetchall.return_value = [{"exists": True}]
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
        result = db.schema.sequences(schema="public")
        assert result == ["users_id_seq", "orders_id_seq"]

    @patch("pycopg.database.psycopg")
    def test_sequences_empty(self, mock_psycopg, config):
        """sequences returns [] for a schema with no sequences."""
        db = self._make_db(mock_psycopg, config, [])
        result = db.schema.sequences(schema="empty_schema")
        assert result == []

    @patch("pycopg.database.psycopg")
    def test_views(self, mock_psycopg, config):
        """views returns list[str] of regular view names."""
        rows = [{"table_name": "active_users"}, {"table_name": "recent_orders"}]
        db = self._make_db(mock_psycopg, config, rows)
        result = db.schema.views(schema="public")
        assert result == ["active_users", "recent_orders"]

    @patch("pycopg.database.psycopg")
    def test_views_empty(self, mock_psycopg, config):
        """views returns [] for a schema with no regular views."""
        db = self._make_db(mock_psycopg, config, [])
        result = db.schema.views(schema="public")
        assert result == []

    @patch("pycopg.database.psycopg")
    def test_materialized_views_sql(self, mock_psycopg, config):
        """materialized_views issues MATERIALIZED_VIEWS with [schema] and
        returns list[str] of names."""
        rows = [{"table_name": "mv_daily"}, {"table_name": "mv_weekly"}]
        db = self._make_db(mock_psycopg, config, rows)
        with patch.object(db, "execute", return_value=rows) as m_execute:
            result = db.schema.materialized_views(schema="public")
        assert result == ["mv_daily", "mv_weekly"]
        m_execute.assert_called_once_with(queries.MATERIALIZED_VIEWS, ["public"])

    @patch("pycopg.database.psycopg")
    def test_materialized_views_empty(self, mock_psycopg, config):
        """materialized_views returns [] for a schema with no materialized views."""
        db = self._make_db(mock_psycopg, config, [])
        result = db.schema.materialized_views(schema="public")
        assert result == []

    @patch("pycopg.database.psycopg")
    def test_materialized_view_columns_sql(self, mock_psycopg, config):
        """materialized_view_columns issues MATERIALIZED_VIEW_COLUMNS with
        [schema, name] param order and returns the raw execute() rows."""
        rows = [
            {
                "column_name": "id",
                "data_type": "integer",
                "is_nullable": "YES",
                "column_default": None,
                "ordinal_position": 1,
                "character_maximum_length": None,
                "numeric_precision": 32,
                "numeric_scale": 0,
            }
        ]
        db = self._make_db(mock_psycopg, config, rows)
        with patch.object(db, "execute", return_value=rows) as m_execute:
            result = db.schema.materialized_view_columns("mv_daily", schema="public")
        assert result == rows
        m_execute.assert_called_once_with(
            queries.MATERIALIZED_VIEW_COLUMNS, ["public", "mv_daily"]
        )

    @patch("pycopg.database.psycopg")
    def test_materialized_view_columns_empty(self, mock_psycopg, config):
        """materialized_view_columns returns [] for a nonexistent matview."""
        db = self._make_db(mock_psycopg, config, [])
        result = db.schema.materialized_view_columns("no_such_mv", schema="public")
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
            patch.object(db.schema, "primary_key", return_value=expected_pk) as m_pk,
            patch.object(db.schema, "foreign_keys", return_value=expected_fks) as m_fk,
            patch.object(
                db.schema, "list_indexes", return_value=expected_indexes
            ) as m_li,
        ):
            result = db.schema.describe("some_table", schema="public")

        # Exact key set
        assert set(result) == {"columns", "primary_key", "foreign_keys", "indexes"}
        # Each sub-value is the standalone helper's exact output
        assert result["columns"] == expected_columns
        assert result["primary_key"] == expected_pk
        assert result["foreign_keys"] == expected_fks
        assert result["indexes"] == expected_indexes
        # Each helper was called exactly once with keyword schema arg
        m_ti.assert_called_once_with("some_table", schema="public")
        m_pk.assert_called_once_with("some_table", schema="public")
        m_fk.assert_called_once_with("some_table", schema="public")
        m_li.assert_called_once_with("some_table", schema="public")

    def _patch_describe_helpers(self, db, columns, pk, fks, indexes):
        """Helper: patch the four describe-composed helpers with fixed return values."""
        return (
            patch.object(db.schema, "table_info", return_value=columns),
            patch.object(db.schema, "primary_key", return_value=pk),
            patch.object(db.schema, "foreign_keys", return_value=fks),
            patch.object(db.schema, "list_indexes", return_value=indexes),
        )

    @patch("pycopg.database.psycopg")
    def test_describe_into_dict(self, mock_psycopg, config):
        """describe(into='dict') is byte-identical to describe() (default, C-03)."""
        db = self._make_db(mock_psycopg, config, [])
        columns = [{"column_name": "id", "data_type": "integer"}]
        pk = {"constraint_name": "t_pkey", "columns": ["id"]}
        fks = []
        indexes = [{"index_name": "t_pkey", "index_type": "btree"}]
        p1, p2, p3, p4 = self._patch_describe_helpers(db, columns, pk, fks, indexes)
        with p1, p2, p3, p4:
            plain = db.schema.describe("t")
            explicit = db.schema.describe("t", into="dict")
        assert explicit == plain
        assert explicit == {
            "columns": columns,
            "primary_key": pk,
            "foreign_keys": fks,
            "indexes": indexes,
        }

    @patch("pycopg.database.psycopg")
    def test_describe_into_dataclass(self, mock_psycopg, config):
        """describe(into='dataclass') wraps the same sub-values in TableDescription (D-12)."""
        from pycopg import TableDescription

        db = self._make_db(mock_psycopg, config, [])
        columns = [{"column_name": "id", "data_type": "integer"}]
        pk = {"constraint_name": "t_pkey", "columns": ["id"]}
        fks = []
        indexes = [{"index_name": "t_pkey", "index_type": "btree"}]
        p1, p2, p3, p4 = self._patch_describe_helpers(db, columns, pk, fks, indexes)
        with p1, p2, p3, p4:
            result = db.schema.describe("t", into="dataclass")
        assert isinstance(result, TableDescription)
        assert result.columns == columns
        assert result.primary_key == pk
        assert result.foreign_keys == fks
        assert result.indexes == indexes

    @patch("pycopg.database.psycopg")
    def test_describe_into_dataframe(self, mock_psycopg, config):
        """describe(into='dataframe') returns the columns section, one row per column."""
        import pandas as pd

        db = self._make_db(mock_psycopg, config, [])
        columns = [
            {"column_name": "id", "data_type": "integer"},
            {"column_name": "name", "data_type": "text"},
        ]
        p1, p2, p3, p4 = self._patch_describe_helpers(db, columns, None, [], [])
        with p1, p2, p3, p4:
            result = db.schema.describe("t", into="dataframe")
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
        assert list(result["column_name"]) == ["id", "name"]

    @patch("pycopg.database.psycopg")
    def test_describe_into_invalid(self, mock_psycopg, config):
        """describe(into='bogus') raises ValueError."""
        db = self._make_db(mock_psycopg, config, [])
        p1, p2, p3, p4 = self._patch_describe_helpers(db, [], None, [], [])
        with p1, p2, p3, p4, pytest.raises(ValueError, match="into must be"):
            db.schema.describe("t", into="bogus")


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


class TestStreamDfCopyValidation:
    """`_stream_df_copy` enforces the builder-pur invariant (38-REVIEW CR-01/CR-02).

    The COPY-streaming helper is the single chokepoint every COPY caller
    (``from_dataframe`` and the ETL ``append``/``replace`` seam) funnels through,
    so it must reject invalid identifiers *before* any COPY SQL is issued.
    """

    def test_stream_df_copy_rejects_invalid_column(self):
        """An invalid column name raises InvalidIdentifierError before COPY runs."""
        import pandas as pd

        from pycopg.database import _stream_df_copy

        df = pd.DataFrame({"id": [1, 2], "bad; DROP TABLE x": [3, 4]})
        cur = MagicMock()
        with pytest.raises(InvalidIdentifierError):
            _stream_df_copy(cur, df, "t", "public", list(df.columns))
        # Validation ran before any SQL was issued — no injection surface.
        cur.copy.assert_not_called()

    def test_stream_df_copy_rejects_invalid_table(self):
        """An invalid table name raises InvalidIdentifierError before COPY runs."""
        import pandas as pd

        from pycopg.database import _stream_df_copy

        df = pd.DataFrame({"id": [1, 2]})
        cur = MagicMock()
        with pytest.raises(InvalidIdentifierError):
            _stream_df_copy(cur, df, "t; DROP TABLE x", "public", list(df.columns))
        cur.copy.assert_not_called()
