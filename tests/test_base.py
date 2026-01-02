"""Tests for pycopg.base module."""

import pytest

from pycopg import Config
from pycopg.base import DatabaseBase, QueryMixin, SessionMixin
from pycopg.exceptions import InvalidIdentifier


class ConcreteDatabaseBase(DatabaseBase):
    """Concrete implementation for testing DatabaseBase."""
    pass


class TestDatabaseBase:
    """Tests for DatabaseBase class."""

    @pytest.fixture
    def config(self):
        """Create a test config."""
        return Config(
            host="localhost",
            port=5432,
            database="testdb",
            user="testuser",
            password="testpass",
        )

    def test_init_with_config(self, config):
        """Test initialization stores config."""
        db = ConcreteDatabaseBase(config)
        assert db.config == config

    def test_from_env(self, monkeypatch):
        """Test from_env class method."""
        # Use DATABASE_URL which takes precedence
        import os
        for key in list(os.environ.keys()):
            if key.startswith(("DB_", "PG", "DATABASE_")):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("DATABASE_URL", "postgresql://envuser:envpass@envhost:5432/envdb")

        db = ConcreteDatabaseBase.from_env()
        assert db.config.host == "envhost"
        assert db.config.database == "envdb"

    def test_from_url(self):
        """Test from_url class method."""
        db = ConcreteDatabaseBase.from_url("postgresql://user:pass@host:5432/dbname")
        assert db.config.host == "host"
        assert db.config.database == "dbname"
        assert db.config.user == "user"
        assert db.config.password == "pass"

    def test_repr(self, config):
        """Test string representation."""
        db = ConcreteDatabaseBase(config)
        repr_str = repr(db)
        assert "ConcreteDatabaseBase" in repr_str
        assert "testdb" in repr_str
        assert "localhost" in repr_str
        assert "5432" in repr_str


class TestQueryMixin:
    """Tests for QueryMixin class."""

    def test_build_insert_sql_basic(self):
        """Test basic INSERT SQL generation."""
        sql, cols = QueryMixin._build_insert_sql(
            "users",
            ["name", "email"],
        )
        assert "INSERT INTO public.users" in sql
        assert "name, email" in sql
        assert "%s, %s" in sql
        assert cols == "name, email"

    def test_build_insert_sql_with_schema(self):
        """Test INSERT SQL with custom schema."""
        sql, cols = QueryMixin._build_insert_sql(
            "users",
            ["name"],
            schema="app",
        )
        assert "INSERT INTO app.users" in sql

    def test_build_insert_sql_with_on_conflict(self):
        """Test INSERT SQL with ON CONFLICT clause."""
        sql, cols = QueryMixin._build_insert_sql(
            "users",
            ["id", "name"],
            on_conflict="(id) DO UPDATE SET name = EXCLUDED.name",
        )
        assert "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name" in sql

    def test_build_insert_sql_validates_identifiers(self):
        """Test that invalid identifiers are rejected."""
        with pytest.raises(InvalidIdentifier):
            QueryMixin._build_insert_sql("users;drop", ["name"])

        with pytest.raises(InvalidIdentifier):
            QueryMixin._build_insert_sql("users", ["bad;column"])

    def test_build_batch_insert_sql(self):
        """Test batch INSERT SQL generation."""
        rows = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
        ]
        sql, params = QueryMixin._build_batch_insert_sql(
            "users",
            ["name", "email"],
            rows,
        )
        assert "INSERT INTO public.users" in sql
        assert "VALUES (%s, %s), (%s, %s)" in sql
        assert params == ["Alice", "alice@example.com", "Bob", "bob@example.com"]

    def test_build_batch_insert_sql_with_on_conflict(self):
        """Test batch INSERT SQL with ON CONFLICT."""
        rows = [{"name": "Alice"}]
        sql, params = QueryMixin._build_batch_insert_sql(
            "users",
            ["name"],
            rows,
            on_conflict="DO NOTHING",
        )
        assert "ON CONFLICT DO NOTHING" in sql

    def test_build_select_sql_basic(self):
        """Test basic SELECT SQL generation."""
        sql = QueryMixin._build_select_sql("users")
        assert sql == "SELECT * FROM public.users"

    def test_build_select_sql_with_columns(self):
        """Test SELECT SQL with specific columns."""
        sql = QueryMixin._build_select_sql("users", columns=["id", "name"])
        assert "SELECT id, name FROM public.users" in sql

    def test_build_select_sql_with_where(self):
        """Test SELECT SQL with WHERE clause."""
        sql = QueryMixin._build_select_sql("users", where="active = true")
        assert "WHERE active = true" in sql

    def test_build_select_sql_with_order_by(self):
        """Test SELECT SQL with ORDER BY clause."""
        sql = QueryMixin._build_select_sql("users", order_by="name ASC")
        assert "ORDER BY name ASC" in sql

    def test_build_select_sql_with_limit_offset(self):
        """Test SELECT SQL with LIMIT and OFFSET."""
        sql = QueryMixin._build_select_sql("users", limit=10, offset=20)
        assert "LIMIT 10" in sql
        assert "OFFSET 20" in sql

    def test_build_select_sql_full(self):
        """Test SELECT SQL with all options."""
        sql = QueryMixin._build_select_sql(
            "users",
            columns=["id", "name"],
            schema="app",
            where="active = true",
            order_by="id DESC",
            limit=5,
            offset=10,
        )
        assert "SELECT id, name FROM app.users WHERE active = true ORDER BY id DESC LIMIT 5 OFFSET 10" == sql

    def test_build_select_sql_validates_identifiers(self):
        """Test that invalid identifiers are rejected."""
        with pytest.raises(InvalidIdentifier):
            QueryMixin._build_select_sql("users;drop")

        with pytest.raises(InvalidIdentifier):
            QueryMixin._build_select_sql("users", columns=["bad;col"])


class TestSessionMixin:
    """Tests for SessionMixin class."""

    def test_initial_state(self):
        """Test initial session state."""
        mixin = SessionMixin()
        assert mixin._session_connection is None
        assert mixin._in_session is False

    def test_get_session_connection_not_in_session(self):
        """Test get_session_connection when not in session."""
        mixin = SessionMixin()
        assert mixin._get_session_connection() is None

    def test_get_session_connection_in_session(self):
        """Test get_session_connection when in session."""
        mixin = SessionMixin()
        mixin._in_session = True
        mixin._session_connection = "mock_connection"
        assert mixin._get_session_connection() == "mock_connection"

    def test_is_in_session(self):
        """Test _is_in_session method."""
        mixin = SessionMixin()
        assert mixin._is_in_session() is False

        mixin._in_session = True
        assert mixin._is_in_session() is True
