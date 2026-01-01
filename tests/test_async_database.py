"""Tests for pycopg.async_database module."""

from contextlib import asynccontextmanager
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

import pytest

from pycopg import AsyncDatabase, Config


def create_async_cursor_mock(description=None, fetchall_result=None, fetchone_result=None, rowcount=1):
    """Helper to create a properly mocked async cursor."""
    mock_cursor = MagicMock()
    mock_cursor.description = description
    mock_cursor.rowcount = rowcount
    mock_cursor.execute = AsyncMock()
    mock_cursor.fetchall = AsyncMock(return_value=fetchall_result or [])
    mock_cursor.fetchone = AsyncMock(return_value=fetchone_result)
    return mock_cursor


def create_async_conn_mock(cursor_mock):
    """Helper to create a properly mocked async connection."""
    mock_conn = MagicMock()
    mock_conn.close = AsyncMock()
    mock_conn.commit = AsyncMock()

    @asynccontextmanager
    async def cursor_cm(*args, **kwargs):
        yield cursor_mock

    mock_conn.cursor = MagicMock(side_effect=cursor_cm)
    return mock_conn


class TestAsyncDatabaseInit:
    """Tests for AsyncDatabase initialization."""

    def test_init_with_config(self, config):
        """Test initialization with Config object."""
        db = AsyncDatabase(config)
        assert db.config == config

    @patch("pycopg.async_database.Config.from_env")
    def test_from_env(self, mock_from_env):
        """Test creating from environment."""
        mock_from_env.return_value = Config()

        db = AsyncDatabase.from_env()

        mock_from_env.assert_called_once()
        assert db.config is not None

    @patch("pycopg.async_database.Config.from_url")
    def test_from_url(self, mock_from_url):
        """Test creating from URL."""
        mock_from_url.return_value = Config()

        db = AsyncDatabase.from_url("postgresql://user:pass@host/db")

        mock_from_url.assert_called_once_with("postgresql://user:pass@host/db")

    def test_repr(self, config):
        """Test string representation."""
        db = AsyncDatabase(config)
        repr_str = repr(db)

        assert "AsyncDatabase" in repr_str
        assert "testdb" in repr_str
        assert "localhost" in repr_str


class TestAsyncDatabaseValidation:
    """Tests for identifier validation."""

    def test_validate_identifier_valid(self, config):
        """Test valid identifiers pass."""
        # These should not raise
        AsyncDatabase._validate_identifier("users")
        AsyncDatabase._validate_identifier("user_accounts")
        AsyncDatabase._validate_identifier("Users123")
        AsyncDatabase._validate_identifier("_private")

    def test_validate_identifier_invalid(self, config):
        """Test invalid identifiers raise."""
        with pytest.raises(ValueError):
            AsyncDatabase._validate_identifier("123users")

        with pytest.raises(ValueError):
            AsyncDatabase._validate_identifier("user-accounts")

        with pytest.raises(ValueError):
            AsyncDatabase._validate_identifier("DROP TABLE")


@pytest.mark.asyncio
class TestAsyncDatabaseConnection:
    """Async tests for connection methods."""

    async def test_connect_context(self, config):
        """Test connect async context manager."""
        mock_conn = MagicMock()
        mock_conn.close = AsyncMock()

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=mock_conn)

            db = AsyncDatabase(config)

            async with db.connect() as conn:
                assert conn == mock_conn

            mock_conn.close.assert_called_once()

    async def test_connect_autocommit(self, config):
        """Test connect with autocommit."""
        mock_conn = MagicMock()
        mock_conn.close = AsyncMock()

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=mock_conn)

            db = AsyncDatabase(config)

            async with db.connect(autocommit=True) as conn:
                pass

            call_kwargs = mock_class.connect.call_args[1]
            assert call_kwargs["autocommit"] is True


@pytest.mark.asyncio
class TestAsyncDatabaseExecute:
    """Async tests for execute methods."""

    async def test_execute_select(self, config):
        """Test execute returns results for SELECT."""
        cursor_mock = create_async_cursor_mock(
            description=[("id",), ("name",)],
            fetchall_result=[{"id": 1, "name": "Alice"}]
        )
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            result = await db.execute("SELECT * FROM users")

            assert result == [{"id": 1, "name": "Alice"}]

    async def test_execute_with_params(self, config):
        """Test execute with parameters."""
        cursor_mock = create_async_cursor_mock(
            description=[("id",)],
            fetchall_result=[{"id": 1}]
        )
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            result = await db.execute("SELECT * FROM users WHERE id = %s", [1])

            cursor_mock.execute.assert_called_once()
            call_args = cursor_mock.execute.call_args[0]
            assert call_args[0] == "SELECT * FROM users WHERE id = %s"
            assert call_args[1] == [1]

    async def test_execute_insert(self, config):
        """Test execute for INSERT returns empty list."""
        cursor_mock = create_async_cursor_mock(description=None)
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            result = await db.execute("INSERT INTO users (name) VALUES (%s)", ["Alice"])

            assert result == []

    async def test_execute_many(self, config):
        """Test execute_many method."""
        cursor_mock = create_async_cursor_mock(rowcount=1)
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            result = await db.execute_many(
                "INSERT INTO users (name) VALUES (%s)",
                [("Alice",), ("Bob",)],
            )

            assert result == 2
            assert cursor_mock.execute.call_count == 2

    async def test_fetch_one(self, config):
        """Test fetch_one method."""
        cursor_mock = create_async_cursor_mock(
            fetchone_result={"id": 1, "name": "Alice"}
        )
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            result = await db.fetch_one("SELECT * FROM users WHERE id = %s", [1])

            assert result == {"id": 1, "name": "Alice"}

    async def test_fetch_one_none(self, config):
        """Test fetch_one returns None when no result."""
        cursor_mock = create_async_cursor_mock(fetchone_result=None)
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            result = await db.fetch_one("SELECT * FROM users WHERE id = %s", [999])

            assert result is None

    async def test_fetch_val(self, config):
        """Test fetch_val method."""
        cursor_mock = create_async_cursor_mock(
            fetchone_result={"count": 42}
        )
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            result = await db.fetch_val("SELECT COUNT(*) FROM users")

            assert result == 42

    async def test_fetch_val_none(self, config):
        """Test fetch_val returns None when no result."""
        cursor_mock = create_async_cursor_mock(fetchone_result=None)
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            result = await db.fetch_val("SELECT value FROM empty_table")

            assert result is None


@pytest.mark.asyncio
class TestAsyncDatabaseSchemas:
    """Async tests for schema methods."""

    async def test_list_schemas(self, config):
        """Test listing schemas."""
        cursor_mock = create_async_cursor_mock(
            description=[("schema_name",)],
            fetchall_result=[
                {"schema_name": "public"},
                {"schema_name": "app"},
            ]
        )
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            schemas = await db.list_schemas()

            assert schemas == ["public", "app"]

    async def test_schema_exists_true(self, config):
        """Test schema_exists returns True."""
        cursor_mock = create_async_cursor_mock(
            description=[("exists",)],
            fetchall_result=[{"exists": 1}]
        )
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            exists = await db.schema_exists("public")

            assert exists is True

    async def test_schema_exists_false(self, config):
        """Test schema_exists returns False."""
        cursor_mock = create_async_cursor_mock(
            description=[("exists",)],
            fetchall_result=[]
        )
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            exists = await db.schema_exists("nonexistent")

            assert exists is False


@pytest.mark.asyncio
class TestAsyncDatabaseTables:
    """Async tests for table methods."""

    async def test_list_tables(self, config):
        """Test listing tables."""
        cursor_mock = create_async_cursor_mock(
            description=[("table_name",)],
            fetchall_result=[
                {"table_name": "users"},
                {"table_name": "orders"},
            ]
        )
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            tables = await db.list_tables("public")

            assert tables == ["users", "orders"]

    async def test_table_exists_true(self, config):
        """Test table_exists returns True."""
        cursor_mock = create_async_cursor_mock(
            description=[("exists",)],
            fetchall_result=[{"exists": 1}]
        )
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            exists = await db.table_exists("users")

            assert exists is True


@pytest.mark.asyncio
class TestAsyncDatabaseBatch:
    """Async tests for batch operations."""

    async def test_insert_many(self, config):
        """Test insert_many method."""
        cursor_mock = create_async_cursor_mock(rowcount=1)
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            result = await db.insert_many("users", [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@example.com"},
            ])

            assert result == 2

    async def test_insert_many_empty(self, config):
        """Test insert_many with empty list."""
        db = AsyncDatabase(config)
        result = await db.insert_many("users", [])

        assert result == 0

    async def test_upsert_many(self, config):
        """Test upsert_many method."""
        cursor_mock = create_async_cursor_mock(rowcount=1)
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            result = await db.upsert_many(
                "users",
                [{"id": 1, "name": "Alice Updated"}],
                conflict_columns=["id"],
                update_columns=["name"],
            )

            assert result == 1


@pytest.mark.asyncio
class TestAsyncDatabaseContextManager:
    """Async tests for context manager."""

    async def test_async_context_manager(self, config):
        """Test async context manager."""
        async with AsyncDatabase(config) as db:
            assert db is not None
            assert db.config == config

    async def test_close_no_pool(self, config):
        """Test close when no pool exists."""
        db = AsyncDatabase(config)
        assert db._pool is None
        await db.close()  # Should not raise
        assert db._pool is None
