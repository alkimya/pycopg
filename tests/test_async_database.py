"""Tests for pycopg.async_database module."""

from contextlib import asynccontextmanager
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

import pytest

from pycopg import AsyncDatabase, Config
from pycopg.utils import validate_identifier
from pycopg.exceptions import InvalidIdentifier


def create_async_cursor_mock(description=None, fetchall_result=None, fetchone_result=None, rowcount=1):
    """Helper to create a properly mocked async cursor."""
    mock_cursor = MagicMock()
    mock_cursor.description = description
    mock_cursor.rowcount = rowcount
    mock_cursor.execute = AsyncMock()
    mock_cursor.executemany = AsyncMock()  # Add executemany for batch operations
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
        """Test execute_many method using executemany."""
        cursor_mock = create_async_cursor_mock(rowcount=2)
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            result = await db.execute_many(
                "INSERT INTO users (name) VALUES (%s)",
                [("Alice",), ("Bob",)],
            )

            assert result == 2
            cursor_mock.executemany.assert_called_once()

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
        cursor_mock = create_async_cursor_mock(rowcount=2)  # 2 rows inserted
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            result = await db.insert_many("users", [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@example.com"},
            ])

            assert result == 2
            cursor_mock.executemany.assert_called_once()

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

    async def test_close(self, config):
        """Test close method does not raise."""
        db = AsyncDatabase(config)
        await db.close()  # Should not raise

@pytest.mark.asyncio
class TestAsyncDatabaseInspection:
    """Tests for table inspection methods."""

    async def test_list_columns(self, config):
        """Test list_columns method."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(return_value=[
            {"column_name": "id", "data_type": "integer"},
            {"column_name": "name", "data_type": "text"}
        ])

        cols = await db.list_columns("users")
        
        assert cols == ["id", "name"]
        
        # Verify call to execute
        call_args = db.execute.call_args
        assert "column_name" in call_args[0][0]
        assert call_args[0][1] == ["public", "users"]

    async def test_columns_with_types(self, config):
        """Test columns_with_types method."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(return_value=[
            {"column_name": "id", "data_type": "integer"},
            {"column_name": "name", "data_type": "text"}
        ])

        cols = await db.columns_with_types("users")

        assert cols == [("id", "integer"), ("name", "text")]


def create_async_engine_mock():
    """Helper to create a mocked AsyncEngine with run_sync support."""
    mock_engine = MagicMock()
    mock_sync_conn = MagicMock()

    @asynccontextmanager
    async def connect_cm():
        mock_conn = MagicMock()

        async def run_sync(fn):
            return fn(mock_sync_conn)

        mock_conn.run_sync = AsyncMock(side_effect=run_sync)
        yield mock_conn

    mock_engine.connect = connect_cm
    return mock_engine, mock_sync_conn


class TestAsyncDatabaseEngine:
    """Tests for async_engine lazy initialization."""

    def test_async_engine_not_created_on_init(self, config):
        """Test that async_engine is not created on initialization."""
        db = AsyncDatabase(config)
        assert db._async_engine is None

    def test_async_engine_created_on_access(self, config):
        """Test that async_engine is created on first access."""
        db = AsyncDatabase(config)
        with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_create:
            mock_engine = MagicMock()
            mock_create.return_value = mock_engine

            engine = db.async_engine

            mock_create.assert_called_once_with(config.url)
            assert engine == mock_engine

    def test_async_engine_cached(self, config):
        """Test that async_engine is reused on subsequent accesses."""
        db = AsyncDatabase(config)
        with patch("sqlalchemy.ext.asyncio.create_async_engine") as mock_create:
            mock_engine = MagicMock()
            mock_create.return_value = mock_engine

            engine1 = db.async_engine
            engine2 = db.async_engine

            mock_create.assert_called_once()  # Only created once
            assert engine1 is engine2


@pytest.mark.asyncio
class TestAsyncDatabaseDataFrame:
    """Tests for async DataFrame methods."""

    async def test_to_dataframe_with_table(self, config):
        """Test to_dataframe with table name."""
        import pandas as pd

        mock_engine, mock_sync_conn = create_async_engine_mock()
        expected_df = pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]})

        db = AsyncDatabase(config)
        db._async_engine = mock_engine

        with patch("pandas.read_sql", return_value=expected_df) as mock_read:
            result = await db.to_dataframe("users")

            assert isinstance(result, pd.DataFrame)
            assert len(result) == 2
            mock_read.assert_called_once()

    async def test_to_dataframe_with_sql(self, config):
        """Test to_dataframe with custom SQL."""
        import pandas as pd

        mock_engine, mock_sync_conn = create_async_engine_mock()
        expected_df = pd.DataFrame({"id": [1]})

        db = AsyncDatabase(config)
        db._async_engine = mock_engine

        with patch("pandas.read_sql", return_value=expected_df):
            result = await db.to_dataframe(sql="SELECT * FROM users WHERE id = :id", params={"id": 1})

            assert isinstance(result, pd.DataFrame)

    async def test_to_dataframe_both_table_and_sql_raises(self, config):
        """Test to_dataframe raises ValueError with both table and sql."""
        db = AsyncDatabase(config)
        with pytest.raises(ValueError, match="Specify either table or sql, not both"):
            await db.to_dataframe(table="users", sql="SELECT 1")

    async def test_to_dataframe_neither_table_nor_sql_raises(self, config):
        """Test to_dataframe raises ValueError with neither table nor sql."""
        db = AsyncDatabase(config)
        with pytest.raises(ValueError, match="Specify either table or sql"):
            await db.to_dataframe()

    async def test_from_dataframe_basic(self, config):
        """Test from_dataframe writes DataFrame to table."""
        import pandas as pd

        mock_engine, mock_sync_conn = create_async_engine_mock()
        df = pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]})

        db = AsyncDatabase(config)
        db._async_engine = mock_engine

        # We mock df.to_sql to verify it's called correctly
        with patch.object(df, "to_sql") as mock_to_sql:
            await db.from_dataframe(df, "users")

            mock_to_sql.assert_called_once()
            call_kwargs = mock_to_sql.call_args[1]
            assert call_kwargs["name"] == "users"
            assert call_kwargs["schema"] == "public"
            assert call_kwargs["if_exists"] == "fail"

    async def test_from_dataframe_if_exists_append(self, config):
        """Test from_dataframe with if_exists='append'."""
        import pandas as pd

        mock_engine, mock_sync_conn = create_async_engine_mock()
        df = pd.DataFrame({"id": [3]})

        db = AsyncDatabase(config)
        db._async_engine = mock_engine

        with patch.object(df, "to_sql") as mock_to_sql:
            await db.from_dataframe(df, "users", if_exists="append")

            call_kwargs = mock_to_sql.call_args[1]
            assert call_kwargs["if_exists"] == "append"
