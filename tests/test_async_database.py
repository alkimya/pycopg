"""Tests for pycopg.async_database module."""

import inspect
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from pycopg import AsyncDatabase, Config
from pycopg.exceptions import DatabaseExists, ExtensionNotAvailable, InvalidIdentifier
from pycopg.utils import validate_identifier


def create_async_cursor_mock(
    description=None, fetchall_result=None, fetchone_result=None, rowcount=1
):
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
            fetchall_result=[{"id": 1, "name": "Alice"}],
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
            description=[("id",)], fetchall_result=[{"id": 1}]
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
        cursor_mock = create_async_cursor_mock(fetchone_result={"count": 42})
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
            ],
        )
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            schemas = await db.schema.list_schemas()

            assert schemas == ["public", "app"]

    async def test_schema_exists_true(self, config):
        """Test schema_exists returns True."""
        cursor_mock = create_async_cursor_mock(
            description=[("exists",)], fetchall_result=[{"exists": 1}]
        )
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            exists = await db.schema.schema_exists("public")

            assert exists is True

    async def test_schema_exists_false(self, config):
        """Test schema_exists returns False."""
        cursor_mock = create_async_cursor_mock(
            description=[("exists",)], fetchall_result=[]
        )
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            exists = await db.schema.schema_exists("nonexistent")

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
            ],
        )
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            tables = await db.schema.list_tables("public")

            assert tables == ["users", "orders"]

    async def test_table_exists_true(self, config):
        """Test table_exists returns True."""
        cursor_mock = create_async_cursor_mock(
            description=[("exists",)], fetchall_result=[{"exists": 1}]
        )
        conn_mock = create_async_conn_mock(cursor_mock)

        with patch("pycopg.async_database.psycopg.AsyncConnection") as mock_class:
            mock_class.connect = AsyncMock(return_value=conn_mock)

            db = AsyncDatabase(config)
            exists = await db.schema.table_exists("users")

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
            result = await db.insert_many(
                "users",
                [
                    {"name": "Alice", "email": "alice@example.com"},
                    {"name": "Bob", "email": "bob@example.com"},
                ],
            )

            assert result == 2
            cursor_mock.execute.assert_called_once()

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
        db.execute = AsyncMock(
            return_value=[
                {"column_name": "id", "data_type": "integer"},
                {"column_name": "name", "data_type": "text"},
            ]
        )

        cols = await db.schema.list_columns("users")

        assert cols == ["id", "name"]

        # Verify call to execute
        call_args = db.execute.call_args
        assert "column_name" in call_args[0][0]
        assert call_args[0][1] == ["public", "users"]

    async def test_columns_with_types(self, config):
        """Test columns_with_types method."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(
            return_value=[
                {"column_name": "id", "data_type": "integer"},
                {"column_name": "name", "data_type": "text"},
            ]
        )

        cols = await db.schema.columns_with_types("users")

        assert cols == [("id", "integer"), ("name", "text")]


@pytest.mark.asyncio
class TestAsyncDatabaseRetry:
    """Tests for AsyncDatabase retry behavior."""

    async def test_async_connect_with_retry_has_tenacity_decorator(self, config):
        """Test _connect_with_retry has tenacity retry decorator."""
        db = AsyncDatabase(config)
        assert hasattr(db._connect_with_retry, "retry")

    @patch("pycopg.async_database.psycopg.AsyncConnection.connect")
    @patch("asyncio.sleep")  # Patch async sleep to avoid delays
    async def test_async_connect_with_retry_retries_operational_error(
        self, mock_sleep, mock_connect, config
    ):
        """Test async _connect_with_retry retries OperationalError."""
        from pycopg.async_database import OperationalError

        mock_conn = MagicMock()
        # Fail twice with OperationalError, succeed on third try
        mock_connect.side_effect = [
            OperationalError("Connection refused"),
            OperationalError("Connection refused"),
            mock_conn,
        ]

        db = AsyncDatabase(config)
        result = await db._connect_with_retry()

        assert result == mock_conn
        assert mock_connect.call_count == 3

    @patch("pycopg.async_database.psycopg.AsyncConnection.connect")
    async def test_async_connect_with_retry_does_not_retry_programming_error(
        self, mock_connect, config
    ):
        """Test async _connect_with_retry does NOT retry ProgrammingError."""
        from psycopg import ProgrammingError

        mock_connect.side_effect = ProgrammingError("Syntax error")

        db = AsyncDatabase(config)
        with pytest.raises(ProgrammingError):
            await db._connect_with_retry()

        # Should only be called once (no retry on ProgrammingError)
        assert mock_connect.call_count == 1

    @patch("pycopg.async_database.psycopg.AsyncConnection.connect")
    @patch("asyncio.sleep")
    async def test_async_connect_with_retry_reraises_after_max_attempts(
        self, mock_sleep, mock_connect, config
    ):
        """Test async _connect_with_retry reraises after 3 attempts."""
        from pycopg.async_database import OperationalError

        # Always raise OperationalError
        mock_connect.side_effect = OperationalError("Connection refused")

        db = AsyncDatabase(config)
        with pytest.raises(OperationalError):
            await db._connect_with_retry()

        # Should be called exactly 3 times (stop_after_attempt(3))
        assert mock_connect.call_count == 3

    async def test_async_insert_batch_uses_config_default(self, config):
        """Test async insert_batch uses config.default_batch_size when batch_size=None."""
        # Use inspect to verify batch_size default is None
        import inspect

        sig = inspect.signature(AsyncDatabase.insert_batch)
        param = sig.parameters["batch_size"]
        assert param.default is None


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

            # PAR-06 / C3: async engine must use the async driver URL, not the
            # sync config.url (which uses +psycopg, the sync driver).
            mock_create.assert_called_once_with(config.async_url)
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
            result = await db.to_dataframe(
                sql="SELECT * FROM users WHERE id = :id", params={"id": 1}
            )

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


@pytest.mark.asyncio
class TestAsyncDatabaseGeoDataFrame:
    """Tests for async GeoDataFrame methods."""

    async def test_to_geodataframe_with_table(self, config):
        """Test to_geodataframe with table name."""
        import geopandas as gpd
        from shapely.geometry import Point

        mock_engine, mock_sync_conn = create_async_engine_mock()
        expected_gdf = gpd.GeoDataFrame(
            {"id": [1], "geometry": [Point(0, 0)]}, crs="EPSG:4326"
        )

        db = AsyncDatabase(config)
        db._async_engine = mock_engine

        with patch("geopandas.read_postgis", return_value=expected_gdf) as mock_read:
            result = await db.to_geodataframe("parcels")

            assert isinstance(result, gpd.GeoDataFrame)
            mock_read.assert_called_once()

    async def test_to_geodataframe_with_sql(self, config):
        """Test to_geodataframe with custom SQL."""
        import geopandas as gpd
        from shapely.geometry import Point

        mock_engine, mock_sync_conn = create_async_engine_mock()
        expected_gdf = gpd.GeoDataFrame(
            {"id": [1], "geometry": [Point(0, 0)]}, crs="EPSG:4326"
        )

        db = AsyncDatabase(config)
        db._async_engine = mock_engine

        with patch("geopandas.read_postgis", return_value=expected_gdf):
            result = await db.to_geodataframe(
                sql="SELECT * FROM parcels WHERE area > 100"
            )

            assert isinstance(result, gpd.GeoDataFrame)

    async def test_to_geodataframe_both_table_and_sql_raises(self, config):
        """Test to_geodataframe raises ValueError with both table and sql."""
        db = AsyncDatabase(config)
        with pytest.raises(ValueError, match="Specify either table or sql, not both"):
            await db.to_geodataframe(table="parcels", sql="SELECT 1")

    async def test_to_geodataframe_neither_raises(self, config):
        """Test to_geodataframe raises ValueError with neither table nor sql."""
        db = AsyncDatabase(config)
        with pytest.raises(ValueError, match="Specify either table or sql"):
            await db.to_geodataframe()

    async def test_from_geodataframe_no_postgis_raises(self, config):
        """Test from_geodataframe raises RuntimeError without PostGIS."""
        import geopandas as gpd
        from shapely.geometry import Point

        from pycopg.schema import AsyncSchemaAccessor

        gdf = gpd.GeoDataFrame({"id": [1], "geometry": [Point(0, 0)]}, crs="EPSG:4326")

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=False)
        db._schema = mock_schema

        with pytest.raises(
            ExtensionNotAvailable, match="PostGIS extension not installed"
        ):
            await db.from_geodataframe(gdf, "parcels")

        mock_schema.has_extension.assert_called_once_with("postgis")

    async def test_from_geodataframe_no_crs_raises(self, config):
        """Test from_geodataframe raises ValueError when GeoDataFrame has no CRS."""
        import geopandas as gpd
        from shapely.geometry import Point

        from pycopg.schema import AsyncSchemaAccessor

        gdf = gpd.GeoDataFrame(
            {"id": [1], "geometry": [Point(0, 0)]}, crs=None  # No CRS
        )

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema

        with pytest.raises(ValueError, match="GeoDataFrame has no CRS defined"):
            await db.from_geodataframe(gdf, "parcels")

    async def test_from_geodataframe_unknown_crs_raises(self, config):
        """Test from_geodataframe raises ValueError on CRS with no EPSG code."""
        import geopandas as gpd
        from shapely.geometry import Point

        from pycopg.schema import AsyncSchemaAccessor

        gdf = gpd.GeoDataFrame({"id": [1], "geometry": [Point(0, 0)]}, crs="EPSG:4326")
        # Mock CRS.to_epsg() returning None (unknown EPSG)
        with patch.object(type(gdf), "crs", new_callable=PropertyMock) as mock_crs_prop:
            mock_crs = MagicMock()
            mock_crs.to_epsg.return_value = None
            mock_crs_prop.return_value = mock_crs

            db = AsyncDatabase(config)
            mock_schema = MagicMock(spec=AsyncSchemaAccessor)
            mock_schema.has_extension = AsyncMock(return_value=True)
            db._schema = mock_schema

            with pytest.raises(ValueError, match="Cannot determine EPSG code"):
                await db.from_geodataframe(gdf, "parcels")

    async def test_from_geodataframe_with_explicit_srid(self, config):
        """Test from_geodataframe with explicit srid bypasses CRS check."""
        import geopandas as gpd
        from shapely.geometry import Point

        from pycopg.schema import AsyncSchemaAccessor
        from pycopg.spatial import AsyncSpatialAccessor

        mock_engine, mock_sync_conn = create_async_engine_mock()
        gdf = gpd.GeoDataFrame(
            {"id": [1], "geometry": [Point(0, 0)]},
            crs=None,  # No CRS, but explicit srid should be fine
        )

        db = AsyncDatabase(config)
        db._async_engine = mock_engine
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        mock_spatial = MagicMock(spec=AsyncSpatialAccessor)
        mock_spatial.create_spatial_index = AsyncMock()
        db._spatial = mock_spatial

        with patch.object(gdf, "to_postgis") as mock_to_postgis:
            await db.from_geodataframe(gdf, "parcels", srid=4326)

            mock_to_postgis.assert_called_once()

    async def test_from_geodataframe_basic(self, config):
        """Test from_geodataframe writes GeoDataFrame to table."""
        import geopandas as gpd
        from shapely.geometry import Point

        from pycopg.schema import AsyncSchemaAccessor
        from pycopg.spatial import AsyncSpatialAccessor

        mock_engine, mock_sync_conn = create_async_engine_mock()
        gdf = gpd.GeoDataFrame({"id": [1], "geometry": [Point(0, 0)]}, crs="EPSG:4326")

        db = AsyncDatabase(config)
        db._async_engine = mock_engine
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        mock_spatial = MagicMock(spec=AsyncSpatialAccessor)
        mock_spatial.create_spatial_index = AsyncMock()
        db._spatial = mock_spatial

        with patch.object(gdf, "to_postgis") as mock_to_postgis:
            await db.from_geodataframe(gdf, "parcels")

            mock_to_postgis.assert_called_once()
            call_kwargs = mock_to_postgis.call_args[1]
            assert call_kwargs["name"] == "parcels"
            assert call_kwargs["schema"] == "public"

    async def test_from_geodataframe_with_spatial_index(self, config):
        """Test from_geodataframe creates spatial index when spatial_index=True."""
        import geopandas as gpd
        from shapely.geometry import Point

        from pycopg.schema import AsyncSchemaAccessor
        from pycopg.spatial import AsyncSpatialAccessor

        mock_engine, mock_sync_conn = create_async_engine_mock()
        gdf = gpd.GeoDataFrame({"id": [1], "geometry": [Point(0, 0)]}, crs="EPSG:4326")

        db = AsyncDatabase(config)
        db._async_engine = mock_engine
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        mock_spatial = MagicMock(spec=AsyncSpatialAccessor)
        mock_spatial.create_spatial_index = AsyncMock()
        db._spatial = mock_spatial

        with patch.object(gdf, "to_postgis") as mock_to_postgis:
            await db.from_geodataframe(gdf, "parcels", spatial_index=True)

            mock_to_postgis.assert_called_once()
            # Verify create_spatial_index was called via the spatial accessor
            mock_spatial.create_spatial_index.assert_awaited_once_with(
                "parcels", "geometry", "public"
            )


@pytest.mark.asyncio
class TestAsyncDatabaseDDL:
    """Tests for DDL operations (drop_table, create_index, etc.)."""

    async def test_drop_table_basic(self, config):
        """Test drop_table with default parameters."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.schema.drop_table("users")

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "DROP TABLE IF EXISTS public.users" in sql

    async def test_drop_table_cascade(self, config):
        """Test drop_table with cascade option."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.schema.drop_table("users", cascade=True)

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "DROP TABLE IF EXISTS public.users CASCADE" in sql

    async def test_create_index_basic(self, config):
        """Test create_index with single column."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.schema.create_index("users", "email")

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "CREATE INDEX IF NOT EXISTS" in sql
        assert "ON public.users USING btree (email)" in sql

    async def test_create_index_unique_multi_column(self, config):
        """Test create_index with unique constraint and multiple columns."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.schema.create_index("users", ["first_name", "last_name"], unique=True)

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "CREATE UNIQUE INDEX" in sql
        assert "first_name, last_name" in sql

    async def test_drop_index_basic(self, config):
        """Test drop_index with default parameters."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.schema.drop_index("idx_users_email")

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "DROP INDEX IF EXISTS public.idx_users_email" in sql

    async def test_list_indexes(self, config):
        """Test list_indexes returns index information."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(
            return_value=[
                {
                    "index_name": "idx_users_email",
                    "index_type": "btree",
                    "index_def": "CREATE INDEX...",
                },
                {
                    "index_name": "users_pkey",
                    "index_type": "btree",
                    "index_def": "CREATE UNIQUE INDEX...",
                },
            ]
        )

        indexes = await db.schema.list_indexes("users")

        assert len(indexes) == 2
        assert indexes[0]["index_name"] == "idx_users_email"
        assert indexes[1]["index_name"] == "users_pkey"

        # Verify SQL parameters
        call_args = db.execute.call_args
        assert call_args[0][1] == ["public", "users"]

    async def test_list_constraints(self, config):
        """Test list_constraints returns constraint information."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(
            return_value=[
                {
                    "constraint_name": "users_pkey",
                    "constraint_type": "p",
                    "constraint_def": "PRIMARY KEY (id)",
                },
                {
                    "constraint_name": "users_email_key",
                    "constraint_type": "u",
                    "constraint_def": "UNIQUE (email)",
                },
            ]
        )

        constraints = await db.schema.list_constraints("users")

        assert len(constraints) == 2
        assert constraints[0]["constraint_name"] == "users_pkey"
        assert constraints[1]["constraint_name"] == "users_email_key"

        # Verify SQL parameters
        call_args = db.execute.call_args
        assert call_args[0][1] == ["public", "users"]

    async def test_drop_schema_basic(self, config):
        """Test drop_schema with default parameters."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.schema.drop_schema("analytics")

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "DROP SCHEMA IF EXISTS analytics" in sql

    async def test_drop_schema_cascade(self, config):
        """Test drop_schema with cascade option."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.schema.drop_schema("analytics", cascade=True)

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "DROP SCHEMA IF EXISTS analytics CASCADE" in sql

    async def test_table_sizes(self, config):
        """Test table_sizes returns size information."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(
            return_value=[
                {
                    "table_name": "users",
                    "total_size": "128 MB",
                    "data_size": "100 MB",
                    "index_size": "28 MB",
                },
                {
                    "table_name": "logs",
                    "total_size": "64 MB",
                    "data_size": "50 MB",
                    "index_size": "14 MB",
                },
            ]
        )

        sizes = await db.maint.table_sizes("public", limit=10)

        assert len(sizes) == 2
        assert sizes[0]["table_name"] == "users"
        assert sizes[0]["total_size"] == "128 MB"

        # Verify SQL parameters
        call_args = db.execute.call_args
        assert call_args[0][1] == ["public", 10]


@pytest.mark.asyncio
class TestAsyncDatabaseAdmin:
    """Tests for database administration methods."""

    async def test_create_database(self, config):
        """Test create_database creates database with admin connection."""
        # Create mock cursor and connection
        mock_cursor = MagicMock()
        mock_cursor.execute = AsyncMock()

        @asynccontextmanager
        async def cursor_cm():
            yield mock_cursor

        mock_conn = MagicMock()
        mock_conn.cursor = MagicMock(side_effect=cursor_cm)

        @asynccontextmanager
        async def connect_cm():
            yield mock_conn

        db = AsyncDatabase(config)

        with patch("psycopg.AsyncConnection.connect", return_value=connect_cm()):
            await db.schema.create_database("testdb")

        # Verify CREATE DATABASE was called
        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        assert "CREATE DATABASE testdb" in sql
        assert "TEMPLATE template1" in sql

    async def test_create_database_with_owner(self, config):
        """Test create_database with owner parameter."""
        mock_cursor = MagicMock()
        mock_cursor.execute = AsyncMock()

        @asynccontextmanager
        async def cursor_cm():
            yield mock_cursor

        mock_conn = MagicMock()
        mock_conn.cursor = MagicMock(side_effect=cursor_cm)

        @asynccontextmanager
        async def connect_cm():
            yield mock_conn

        db = AsyncDatabase(config)

        with patch("psycopg.AsyncConnection.connect", return_value=connect_cm()):
            await db.schema.create_database("testdb", owner="appuser")

        sql = mock_cursor.execute.call_args[0][0]
        assert "OWNER appuser" in sql

    async def test_drop_database(self, config):
        """Test drop_database terminates connections and drops database."""
        mock_cursor = MagicMock()
        mock_cursor.execute = AsyncMock()

        @asynccontextmanager
        async def cursor_cm():
            yield mock_cursor

        mock_conn = MagicMock()
        mock_conn.cursor = MagicMock(side_effect=cursor_cm)

        @asynccontextmanager
        async def connect_cm():
            yield mock_conn

        db = AsyncDatabase(config)

        with patch("psycopg.AsyncConnection.connect", return_value=connect_cm()):
            await db.schema.drop_database("testdb")

        # Verify pg_terminate_backend was called first, then DROP DATABASE
        assert mock_cursor.execute.call_count == 2

        # First call should be terminate connections
        first_call = mock_cursor.execute.call_args_list[0]
        assert "pg_terminate_backend" in first_call[0][0]
        assert first_call[0][1] == ["testdb"]

        # Second call should be DROP DATABASE
        second_call = mock_cursor.execute.call_args_list[1]
        assert "DROP DATABASE IF EXISTS testdb" in second_call[0][0]

    async def test_drop_database_if_not_exists(self, config):
        """Test drop_database with if_exists=False."""
        mock_cursor = MagicMock()
        mock_cursor.execute = AsyncMock()

        @asynccontextmanager
        async def cursor_cm():
            yield mock_cursor

        mock_conn = MagicMock()
        mock_conn.cursor = MagicMock(side_effect=cursor_cm)

        @asynccontextmanager
        async def connect_cm():
            yield mock_conn

        db = AsyncDatabase(config)

        with patch("psycopg.AsyncConnection.connect", return_value=connect_cm()):
            await db.schema.drop_database("testdb", if_exists=False)

        # Check DROP DATABASE doesn't have IF EXISTS
        second_call = mock_cursor.execute.call_args_list[1]
        sql = second_call[0][0]
        assert "DROP DATABASE testdb" in sql
        assert "IF EXISTS" not in sql


@pytest.mark.asyncio
class TestAsyncDatabaseMaintenance:
    """Tests for AsyncDatabase maintenance methods."""

    async def test_vacuum_basic(self, config):
        """Test basic vacuum with analyze."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.maint.vacuum()

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "VACUUM(ANALYZE)" in sql
        assert call_args[1]["autocommit"] is True

    async def test_vacuum_full_table(self, config):
        """Test vacuum with full and specific table."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.maint.vacuum("users", full=True)

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "VACUUM(FULL, ANALYZE)" in sql
        assert "public.users" in sql
        assert call_args[1]["autocommit"] is True

    async def test_vacuum_no_analyze(self, config):
        """Test vacuum without analyze."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.maint.vacuum(analyze=False)

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "VACUUM" in sql
        assert "ANALYZE" not in sql
        assert call_args[1]["autocommit"] is True

    async def test_analyze_basic(self, config):
        """Test basic analyze."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.maint.analyze()

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "ANALYZE" in sql
        assert call_args[1]["autocommit"] is True

    async def test_analyze_table(self, config):
        """Test analyze on specific table."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.maint.analyze("users", schema="public")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "ANALYZE public.users" in sql
        assert call_args[1]["autocommit"] is True

    async def test_explain_basic(self, config):
        """Test basic explain."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(return_value=[{"QUERY PLAN": "Seq Scan on users"}])

        result = await db.maint.explain("SELECT * FROM users")

        assert result == ["Seq Scan on users"]
        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "EXPLAIN" in sql
        assert "FORMAT TEXT" in sql
        assert "SELECT * FROM users" in sql

    async def test_explain_analyze(self, config):
        """Test explain with analyze."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(
            return_value=[
                {
                    "QUERY PLAN": "Seq Scan on users (cost=0.00..10.00 rows=100 width=32)"
                },
                {"QUERY PLAN": "Planning Time: 0.1ms"},
                {"QUERY PLAN": "Execution Time: 1.2ms"},
            ]
        )

        result = await db.maint.explain("SELECT * FROM users", analyze=True)

        assert len(result) == 3
        assert "Seq Scan on users" in result[0]
        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "ANALYZE" in sql

    async def test_explain_json_format(self, config):
        """Test explain with JSON format."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(return_value=[{"QUERY PLAN": '{"Plan": {...}}'}])

        result = await db.maint.explain("SELECT * FROM users", format="json")

        assert len(result) == 1
        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "FORMAT JSON" in sql

    async def test_table_size_bytes(self, config):
        """AsyncMaintAccessor.table_size with pretty=False returns raw byte count."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(return_value=[{"size": 524288}])

        result = await db.maint.table_size("users", pretty=False)

        assert result == 524288
        db.execute.assert_called_once()


@pytest.mark.asyncio
class TestAsyncDatabaseBackup:
    """Tests for AsyncDatabase backup/restore methods."""

    @patch("asyncio.create_subprocess_exec")
    async def test_pg_dump_basic(self, mock_subprocess, config):
        """Test basic pg_dump."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_subprocess.return_value = mock_proc

        db = AsyncDatabase(config)
        await db.backup.pg_dump("/tmp/backup.dump")

        # Verify command
        call_args = mock_subprocess.call_args
        cmd = call_args[0]
        assert cmd[0] == "pg_dump"
        assert "-h" in cmd
        assert "localhost" in cmd
        assert "-d" in cmd
        assert "testdb" in cmd
        assert "-F" in cmd
        assert "c" in cmd  # custom format
        assert "-f" in cmd
        assert "/tmp/backup.dump" in cmd

        # Verify PGPASSWORD in env
        env = call_args[1]["env"]
        assert "PGPASSWORD" in env
        assert env["PGPASSWORD"] == "testpass"

    @patch("asyncio.create_subprocess_exec")
    async def test_pg_dump_plain_format(self, mock_subprocess, config):
        """Test pg_dump with plain SQL format."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_subprocess.return_value = mock_proc

        db = AsyncDatabase(config)
        await db.backup.pg_dump("/tmp/backup.sql", format="plain", schema_only=True)

        call_args = mock_subprocess.call_args
        cmd = call_args[0]
        assert "-F" in cmd
        idx = cmd.index("-F")
        assert cmd[idx + 1] == "p"  # plain format
        assert "--schema-only" in cmd

    @patch("asyncio.create_subprocess_exec")
    async def test_pg_dump_failure(self, mock_subprocess, config):
        """Test pg_dump failure."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"pg_dump: error: database connection failed")
        )
        mock_subprocess.return_value = mock_proc

        db = AsyncDatabase(config)

        with pytest.raises(RuntimeError, match="pg_dump failed"):
            await db.backup.pg_dump("/tmp/backup.dump")

    @patch("asyncio.create_subprocess_exec")
    async def test_pg_dump_with_tables(self, mock_subprocess, config):
        """Test pg_dump with specific tables."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_subprocess.return_value = mock_proc

        db = AsyncDatabase(config)
        await db.backup.pg_dump("/tmp/backup.dump", tables=["users", "orders"])

        call_args = mock_subprocess.call_args
        cmd = call_args[0]
        assert "-t" in cmd
        assert "users" in cmd
        assert "orders" in cmd

    @patch("asyncio.create_subprocess_exec")
    async def test_pg_restore_basic(self, mock_subprocess, config):
        """Test basic pg_restore."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_subprocess.return_value = mock_proc

        db = AsyncDatabase(config)
        # Create a Path object that appears to exist and is not .sql
        with patch("pathlib.Path.exists", return_value=True):
            with patch(
                "pathlib.Path.suffix", new_callable=PropertyMock, return_value=".dump"
            ):
                await db.backup.pg_restore("/tmp/backup.dump")

        call_args = mock_subprocess.call_args
        cmd = call_args[0]
        assert cmd[0] == "pg_restore"
        assert "-d" in cmd
        assert "testdb" in cmd
        assert "/tmp/backup.dump" in cmd

    @patch("asyncio.create_subprocess_exec")
    async def test_pg_restore_clean(self, mock_subprocess, config):
        """Test pg_restore with clean option."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_subprocess.return_value = mock_proc

        db = AsyncDatabase(config)
        with patch("pathlib.Path.exists", return_value=True):
            with patch(
                "pathlib.Path.suffix", new_callable=PropertyMock, return_value=".dump"
            ):
                await db.backup.pg_restore(
                    "/tmp/backup.dump", clean=True, if_exists=True
                )

        call_args = mock_subprocess.call_args
        cmd = call_args[0]
        assert "--clean" in cmd
        assert "--if-exists" in cmd

    async def test_pg_restore_sql_file(self, config):
        """Test pg_restore delegates to _psql_restore for .sql files."""
        db = AsyncDatabase(config)
        db.backup._psql_restore = AsyncMock()

        # File with .sql suffix
        await db.backup.pg_restore("/tmp/backup.sql")

        db.backup._psql_restore.assert_called_once()

    @patch("asyncio.create_subprocess_exec")
    async def test_pg_restore_failure(self, mock_subprocess, config):
        """Test pg_restore failure."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(
            return_value=(b"", b"pg_restore: error: invalid format")
        )
        mock_subprocess.return_value = mock_proc

        db = AsyncDatabase(config)
        with patch("pathlib.Path.exists", return_value=True):
            with patch(
                "pathlib.Path.suffix", new_callable=PropertyMock, return_value=".dump"
            ):
                with pytest.raises(RuntimeError, match="pg_restore failed"):
                    await db.backup.pg_restore("/tmp/backup.dump")

    @patch("asyncio.create_subprocess_exec")
    async def test_psql_restore(self, mock_subprocess, config):
        """Test _psql_restore."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_subprocess.return_value = mock_proc

        db = AsyncDatabase(config)
        from pathlib import Path

        await db.backup._psql_restore(Path("/tmp/backup.sql"))

        call_args = mock_subprocess.call_args
        cmd = call_args[0]
        assert cmd[0] == "psql"
        assert "-f" in cmd
        assert "/tmp/backup.sql" in cmd


@pytest.mark.asyncio
class TestAsyncDatabaseCSV:
    """Tests for AsyncDatabase CSV methods."""

    async def test_copy_to_csv_basic(self, config):
        """Test basic copy_to_csv."""
        # Create mock cursor with copy protocol
        mock_cursor = MagicMock()
        mock_cursor.execute = AsyncMock()

        @asynccontextmanager
        async def copy_cm(*args):
            # Simulate yielding data chunks
            class CopyIter:
                async def __aiter__(self):
                    yield b"id,name,email\n"
                    yield b"1,Alice,alice@example.com\n"
                    yield b"2,Bob,bob@example.com\n"

            yield CopyIter()

        mock_cursor.copy = MagicMock(side_effect=copy_cm)

        @asynccontextmanager
        async def cursor_cm():
            yield mock_cursor

        db = AsyncDatabase(config)
        db.cursor = MagicMock(side_effect=cursor_cm)
        db.execute = AsyncMock(return_value=[{"count": 2}])

        # Mock file operations
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.side_effect = lambda f, *args, **kwargs: f(*args, **kwargs)

            with patch("pathlib.Path.mkdir"):
                with patch("builtins.open", MagicMock()):
                    count = await db.backup.copy_to_csv("users", "/tmp/users.csv")

        assert count == 2
        # Verify COPY TO STDOUT SQL
        copy_call = mock_cursor.copy.call_args
        sql = copy_call[0][0]
        assert "COPY public.users TO STDOUT" in sql
        assert "FORMAT CSV" in sql

    async def test_copy_to_csv_with_columns(self, config):
        """Test copy_to_csv with specific columns."""
        mock_cursor = MagicMock()

        @asynccontextmanager
        async def copy_cm(*args):
            class CopyIter:
                async def __aiter__(self):
                    yield b"id,name\n1,Alice\n"

            yield CopyIter()

        mock_cursor.copy = MagicMock(side_effect=copy_cm)

        @asynccontextmanager
        async def cursor_cm():
            yield mock_cursor

        db = AsyncDatabase(config)
        db.cursor = MagicMock(side_effect=cursor_cm)
        db.execute = AsyncMock(return_value=[{"count": 1}])

        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.side_effect = lambda f, *args, **kwargs: f(*args, **kwargs)
            with patch("pathlib.Path.mkdir"):
                with patch("builtins.open", MagicMock()):
                    await db.backup.copy_to_csv(
                        "users", "/tmp/users.csv", columns=["id", "name"]
                    )

        copy_call = mock_cursor.copy.call_args
        sql = copy_call[0][0]
        assert "(id, name)" in sql

    async def test_copy_to_csv_validates_identifiers(self, config):
        """Test copy_to_csv validates identifiers."""
        db = AsyncDatabase(config)

        with pytest.raises(InvalidIdentifier):
            await db.backup.copy_to_csv("DROP TABLE", "/tmp/out.csv")

    async def test_copy_from_csv_basic(self, config):
        """Test basic copy_from_csv."""
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 2

        @asynccontextmanager
        async def copy_cm(*args):
            class CopyWriter:
                async def write(self, data):
                    pass

            yield CopyWriter()

        mock_cursor.copy = MagicMock(side_effect=copy_cm)

        @asynccontextmanager
        async def cursor_cm():
            yield mock_cursor

        db = AsyncDatabase(config)
        db.cursor = MagicMock(side_effect=cursor_cm)

        # Mock file operations
        csv_data = "id,name,email\n1,Alice,alice@example.com\n2,Bob,bob@example.com\n"
        mock_file = MagicMock()
        mock_file.read.side_effect = [
            csv_data,
            "",
        ]  # Return data then empty to signal EOF

        with patch("asyncio.to_thread") as mock_to_thread:
            # First call opens file, second+ calls read data
            call_count = 0

            def to_thread_side_effect(f, *args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:  # open
                    return mock_file
                elif f == mock_file.read:  # read
                    return mock_file.read(*args, **kwargs)
                else:  # close
                    return None

            mock_to_thread.side_effect = to_thread_side_effect

            count = await db.backup.copy_from_csv("users", "/tmp/users.csv")

        assert count == 2
        copy_call = mock_cursor.copy.call_args
        sql = copy_call[0][0]
        assert "COPY public.users FROM STDIN" in sql
        assert "FORMAT CSV" in sql

    async def test_copy_from_csv_with_columns(self, config):
        """Test copy_from_csv with specific columns."""
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1

        @asynccontextmanager
        async def copy_cm(*args):
            class CopyWriter:
                async def write(self, data):
                    pass

            yield CopyWriter()

        mock_cursor.copy = MagicMock(side_effect=copy_cm)

        @asynccontextmanager
        async def cursor_cm():
            yield mock_cursor

        db = AsyncDatabase(config)
        db.cursor = MagicMock(side_effect=cursor_cm)

        mock_file = MagicMock()
        mock_file.read.side_effect = ["id,name\n1,Alice\n", ""]

        with patch("asyncio.to_thread") as mock_to_thread:
            call_count = 0

            def to_thread_side_effect(f, *args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return mock_file
                elif f == mock_file.read:
                    return mock_file.read(*args, **kwargs)
                else:
                    return None

            mock_to_thread.side_effect = to_thread_side_effect

            await db.backup.copy_from_csv(
                "users", "/tmp/users.csv", columns=["id", "name"]
            )

        copy_call = mock_cursor.copy.call_args
        sql = copy_call[0][0]
        assert "(id, name)" in sql

    async def test_copy_from_csv_validates_identifiers(self, config):
        """Test copy_from_csv validates identifiers."""
        db = AsyncDatabase(config)

        with pytest.raises(InvalidIdentifier):
            await db.backup.copy_from_csv("DROP TABLE", "/tmp/in.csv")


@pytest.mark.asyncio
class TestAsyncDatabaseRoles:
    """Tests for AsyncDatabase role lifecycle methods."""

    async def test_create_role_basic(self, config):
        """Test create_role with basic login user."""
        db = AsyncDatabase(config)
        db.admin.role_exists = AsyncMock(return_value=False)
        db.execute = AsyncMock()

        await db.admin.create_role("appuser")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "CREATE ROLE appuser WITH" in sql
        assert "LOGIN" in sql
        assert call_args[1]["autocommit"] is True

    async def test_create_role_with_password(self, config):
        """Test create_role with password uses parameterized query."""
        db = AsyncDatabase(config)
        db.admin.role_exists = AsyncMock(return_value=False)

        # Mock cursor context manager
        mock_cursor = MagicMock()
        mock_cursor.execute = AsyncMock()

        @asynccontextmanager
        async def cursor_cm(autocommit=False):
            yield mock_cursor

        db.cursor = MagicMock(side_effect=cursor_cm)

        await db.admin.create_role("appuser", password="secret123")

        # Verify cursor was called with autocommit=True
        db.cursor.assert_called_once_with(autocommit=True)

        # Verify execute was called with parameterized query
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        assert "CREATE ROLE appuser WITH" in sql
        assert "PASSWORD %s" in sql
        assert params == ["secret123"]

    async def test_create_role_if_not_exists_returns_early(self, config):
        """Test create_role returns early if role exists and if_not_exists=True."""
        db = AsyncDatabase(config)
        db.admin.role_exists = AsyncMock(return_value=True)
        db.execute = AsyncMock()

        await db.admin.create_role("appuser")

        # execute should NOT be called
        db.execute.assert_not_called()

    async def test_create_role_with_options(self, config):
        """Test create_role with various role options."""
        db = AsyncDatabase(config)
        db.admin.role_exists = AsyncMock(return_value=False)
        db.execute = AsyncMock()

        await db.admin.create_role(
            "admin",
            superuser=True,
            createdb=True,
            createrole=True,
            connection_limit=10,
            replication=True,
        )

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "SUPERUSER" in sql
        assert "CREATEDB" in sql
        assert "CREATEROLE" in sql
        assert "CONNECTION LIMIT 10" in sql
        assert "REPLICATION" in sql

    async def test_create_role_with_in_roles(self, config):
        """Test create_role grants membership to specified roles."""
        db = AsyncDatabase(config)
        db.admin.role_exists = AsyncMock(return_value=False)
        db.execute = AsyncMock()
        db.admin.grant_role = AsyncMock()

        await db.admin.create_role("analyst", in_roles=["readonly", "reporting"])

        # Verify grant_role was called for each role
        assert db.admin.grant_role.call_count == 2
        db.admin.grant_role.assert_any_call("readonly", "analyst")
        db.admin.grant_role.assert_any_call("reporting", "analyst")

    async def test_create_role_nologin(self, config):
        """Test create_role with login=False creates group role."""
        db = AsyncDatabase(config)
        db.admin.role_exists = AsyncMock(return_value=False)
        db.execute = AsyncMock()

        await db.admin.create_role("readonly", login=False)

        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "NOLOGIN" in sql

    async def test_create_role_noinherit(self, config):
        """Test create_role with inherit=False."""
        db = AsyncDatabase(config)
        db.admin.role_exists = AsyncMock(return_value=False)
        db.execute = AsyncMock()

        await db.admin.create_role("noinherit_role", inherit=False)

        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "NOINHERIT" in sql

    async def test_create_role_with_valid_until(self, config):
        """Test create_role with password expiration."""
        db = AsyncDatabase(config)
        db.admin.role_exists = AsyncMock(return_value=False)
        db.execute = AsyncMock()

        await db.admin.create_role("tempuser", valid_until="2025-12-31")

        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "VALID UNTIL '2025-12-31'" in sql

    async def test_drop_role_basic(self, config):
        """Test drop_role with default IF EXISTS."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.drop_role("olduser")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "DROP ROLE IF EXISTS olduser" in sql
        assert call_args[1]["autocommit"] is True

    async def test_drop_role_no_if_exists(self, config):
        """Test drop_role without IF EXISTS clause."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.drop_role("olduser", if_exists=False)

        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "DROP ROLE olduser" in sql
        assert "IF EXISTS" not in sql

    async def test_alter_role_rename(self, config):
        """Test alter_role rename."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.alter_role("oldname", rename_to="newname")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "ALTER ROLE oldname RENAME TO newname" in sql
        assert call_args[1]["autocommit"] is True

    async def test_alter_role_with_password(self, config):
        """Test alter_role with password change uses parameterized query."""
        db = AsyncDatabase(config)

        mock_cursor = MagicMock()
        mock_cursor.execute = AsyncMock()

        @asynccontextmanager
        async def cursor_cm(autocommit=False):
            yield mock_cursor

        db.cursor = MagicMock(side_effect=cursor_cm)

        await db.admin.alter_role("appuser", password="newpassword")

        db.cursor.assert_called_once_with(autocommit=True)
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        assert "ALTER ROLE appuser WITH" in sql
        assert "PASSWORD %s" in sql
        assert params == ["newpassword"]

    async def test_alter_role_attributes(self, config):
        """Test alter_role changing boolean attributes."""
        db = AsyncDatabase(config)

        mock_cursor = MagicMock()
        mock_cursor.execute = AsyncMock()

        @asynccontextmanager
        async def cursor_cm(autocommit=False):
            yield mock_cursor

        db.cursor = MagicMock(side_effect=cursor_cm)

        await db.admin.alter_role(
            "appuser", login=False, createdb=True, superuser=False
        )

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        assert "NOLOGIN" in sql
        assert "CREATEDB" in sql
        assert "NOSUPERUSER" in sql

    async def test_alter_role_connection_limit(self, config):
        """Test alter_role changing connection limit."""
        db = AsyncDatabase(config)

        mock_cursor = MagicMock()
        mock_cursor.execute = AsyncMock()

        @asynccontextmanager
        async def cursor_cm(autocommit=False):
            yield mock_cursor

        db.cursor = MagicMock(side_effect=cursor_cm)

        await db.admin.alter_role("appuser", connection_limit=5)

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        assert "CONNECTION LIMIT 5" in sql

    async def test_alter_role_valid_until(self, config):
        """Test alter_role changing password expiration."""
        db = AsyncDatabase(config)

        mock_cursor = MagicMock()
        mock_cursor.execute = AsyncMock()

        @asynccontextmanager
        async def cursor_cm(autocommit=False):
            yield mock_cursor

        db.cursor = MagicMock(side_effect=cursor_cm)

        await db.admin.alter_role("appuser", valid_until="2026-12-31")

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        assert "VALID UNTIL '2026-12-31'" in sql

    async def test_alter_role_createrole_option(self, config):
        """Test alter_role with createrole option covers CREATEROLE/NOCREATEROLE branch."""
        db = AsyncDatabase(config)

        mock_cursor = MagicMock()
        mock_cursor.execute = AsyncMock()

        @asynccontextmanager
        async def cursor_cm(autocommit=False):
            yield mock_cursor

        db.cursor = MagicMock(side_effect=cursor_cm)

        await db.admin.alter_role("appuser", createrole=True)

        mock_cursor.execute.assert_called_once()
        sql = mock_cursor.execute.call_args[0][0]
        assert "CREATEROLE" in sql


@pytest.mark.asyncio
class TestAsyncDatabasePrivileges:
    """Tests for AsyncDatabase privilege management methods."""

    async def test_grant_table(self, config):
        """Test grant on a specific table."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.grant("SELECT", "users", "readonly")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "GRANT SELECT ON TABLE public.users TO readonly" in sql
        assert call_args[1]["autocommit"] is True

    async def test_grant_schema(self, config):
        """Test grant on schema."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.grant("USAGE", "myschema", "appuser", object_type="SCHEMA")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "GRANT USAGE ON SCHEMA myschema TO appuser" in sql

    async def test_grant_database(self, config):
        """Test grant on database."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.grant("CONNECT", "mydb", "appuser", object_type="DATABASE")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "GRANT CONNECT ON DATABASE mydb TO appuser" in sql

    async def test_grant_all_tables(self, config):
        """Test grant on all tables in schema."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.grant("SELECT", "ALL TABLES", "readonly", schema="public")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly" in sql

    async def test_grant_all_sequences(self, config):
        """Test grant on all sequences in schema."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.grant("USAGE", "ALL SEQUENCES", "appuser", schema="myschema")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "GRANT USAGE ON ALL SEQUENCES IN SCHEMA myschema TO appuser" in sql

    async def test_grant_all_functions(self, config):
        """Test grant on all functions in schema."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.grant("EXECUTE", "ALL FUNCTIONS", "appuser", schema="public")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO appuser" in sql

    async def test_grant_with_grant_option(self, config):
        """Test grant with WITH GRANT OPTION."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.grant("SELECT", "users", "admin", with_grant_option=True)

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "WITH GRANT OPTION" in sql

    async def test_grant_list_privileges(self, config):
        """Test grant with list of privileges."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.grant(["SELECT", "INSERT", "UPDATE"], "users", "appuser")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "SELECT, INSERT, UPDATE" in sql

    async def test_revoke_table(self, config):
        """Test revoke on a specific table."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.revoke("INSERT", "users", "readonly")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "REVOKE INSERT ON TABLE public.users FROM readonly" in sql
        assert call_args[1]["autocommit"] is True

    async def test_revoke_schema(self, config):
        """Test revoke on schema."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.revoke("USAGE", "myschema", "olduser", object_type="SCHEMA")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "REVOKE USAGE ON SCHEMA myschema FROM olduser" in sql

    async def test_revoke_cascade(self, config):
        """Test revoke with CASCADE option."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.revoke("ALL", "orders", "former_user", cascade=True)

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "REVOKE ALL ON TABLE public.orders FROM former_user CASCADE" in sql

    async def test_revoke_all_tables(self, config):
        """Test revoke on all tables in schema."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.revoke("DELETE", "ALL TABLES", "readonly", schema="public")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "REVOKE DELETE ON ALL TABLES IN SCHEMA public FROM readonly" in sql

    async def test_revoke_list_privileges(self, config):
        """Test revoke with list of privileges."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.revoke(["INSERT", "UPDATE", "DELETE"], "users", "readonly")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "INSERT, UPDATE, DELETE" in sql

    async def test_grant_role_basic(self, config):
        """Test grant_role basic membership."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.grant_role("readonly", "analyst")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "GRANT readonly TO analyst" in sql
        assert call_args[1]["autocommit"] is True

    async def test_grant_role_with_admin(self, config):
        """Test grant_role with admin option."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.grant_role("admin", "lead_dev", with_admin=True)

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "GRANT admin TO lead_dev WITH ADMIN OPTION" in sql

    async def test_revoke_role_basic(self, config):
        """Test revoke_role basic membership."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.revoke_role("admin", "former_admin")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "REVOKE admin FROM former_admin" in sql
        assert call_args[1]["autocommit"] is True

    async def test_revoke_database_branch(self, config):
        """Test async revoke() with DATABASE object_type emits ON DATABASE clause."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.admin.revoke("CONNECT", "mydb", "olduser", object_type="DATABASE")

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "ON DATABASE mydb" in sql


@pytest.mark.asyncio
class TestAsyncDatabaseRoleInspection:
    """Tests for AsyncDatabase role inspection methods."""

    async def test_list_role_members(self, config):
        """Test list_role_members returns member names."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(
            return_value=[{"member": "analyst"}, {"member": "viewer"}]
        )

        result = await db.admin.list_role_members("readonly")

        assert result == ["analyst", "viewer"]
        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        assert "pg_auth_members" in sql
        assert params == ["readonly"]

    async def test_list_role_members_empty(self, config):
        """Test list_role_members with no members."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(return_value=[])

        result = await db.admin.list_role_members("emptyrole")

        assert result == []

    async def test_list_role_grants(self, config):
        """Test list_role_grants returns grant info."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(
            return_value=[
                {"schema": "public", "object_name": "users", "privilege": "SELECT"},
                {"schema": "public", "object_name": "orders", "privilege": "INSERT"},
            ]
        )

        result = await db.admin.list_role_grants("appuser")

        assert len(result) == 2
        assert result[0]["schema"] == "public"
        assert result[0]["object_name"] == "users"
        assert result[0]["privilege"] == "SELECT"
        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        assert "role_table_grants" in sql
        assert params == ["appuser"]

    async def test_list_role_grants_empty(self, config):
        """Test list_role_grants with no grants."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(return_value=[])

        result = await db.admin.list_role_grants("nogrants")

        assert result == []


@pytest.mark.asyncio
class TestAsyncDatabasePostGIS:
    """Tests for async PostGIS spatial operations."""

    async def test_create_spatial_index_basic(self, config):
        """Test create_spatial_index with default parameters."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        db.execute = AsyncMock()
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema

        await db.spatial.create_spatial_index("parcels", "geom")

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "CREATE INDEX IF NOT EXISTS idx_parcels_geom_gist" in sql
        assert "ON public.parcels USING GIST (geom)" in sql

    async def test_create_spatial_index_custom_name(self, config):
        """Test create_spatial_index with custom index name."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        db.execute = AsyncMock()
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema

        await db.spatial.create_spatial_index("parcels", "geom", name="custom_idx")

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "CREATE INDEX IF NOT EXISTS custom_idx" in sql

    async def test_create_spatial_index_custom_schema(self, config):
        """Test create_spatial_index with custom schema."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        db.execute = AsyncMock()
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema

        await db.spatial.create_spatial_index("parcels", "geom", schema="geo")

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "ON geo.parcels" in sql

    async def test_list_geometry_columns_all(self, config):
        """Test list_geometry_columns without schema filter."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        db.execute = AsyncMock(
            return_value=[
                {
                    "schema": "public",
                    "table_name": "parcels",
                    "column_name": "geom",
                    "dimensions": 2,
                    "srid": 4326,
                    "geometry_type": "POLYGON",
                }
            ]
        )
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema

        result = await db.spatial.list_geometry_columns()

        assert len(result) == 1
        assert result[0]["table_name"] == "parcels"
        assert result[0]["srid"] == 4326

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "geometry_columns" in sql
        # No WHERE clause when no schema filter
        params = db.execute.call_args[0][1]
        assert params is None

    async def test_list_geometry_columns_with_schema(self, config):
        """Test list_geometry_columns with schema filter."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        db.execute = AsyncMock(return_value=[])
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema

        await db.spatial.list_geometry_columns(schema="geo")

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "WHERE f_table_schema = %s" in sql
        params = db.execute.call_args[0][1]
        assert params == ["geo"]


@pytest.mark.asyncio
class TestAsyncDatabaseTimescaleDB:
    """Tests for async TimescaleDB operations."""

    async def test_create_hypertable_basic(self, config):
        """Test create_hypertable with extension check."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock()

        await db.timescale.create_hypertable("events", "timestamp")

        mock_schema.has_extension.assert_called_once_with("timescaledb")
        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "create_hypertable" in sql
        assert "'public.events'" in sql
        assert "'timestamp'" in sql

    async def test_create_hypertable_no_extension_raises(self, config):
        """Test create_hypertable raises RuntimeError when extension missing."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=False)
        db._schema = mock_schema

        with pytest.raises(
            ExtensionNotAvailable, match="TimescaleDB extension not installed"
        ):
            await db.timescale.create_hypertable("events", "timestamp")

        mock_schema.has_extension.assert_called_once_with("timescaledb")

    async def test_create_hypertable_custom_interval(self, config):
        """Test create_hypertable with custom chunk interval."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock()

        await db.timescale.create_hypertable(
            "events", "timestamp", chunk_time_interval="1 week"
        )

        sql = db.execute.call_args[0][0]
        assert "INTERVAL '1 week'" in sql

    async def test_enable_compression_basic(self, config):
        """Test enable_compression with segment_by."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock()

        await db.timescale.enable_compression("events", segment_by="device_id")

        mock_schema.has_extension.assert_called_once_with("timescaledb")
        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "ALTER TABLE" in sql
        assert "timescaledb.compress" in sql
        assert "timescaledb.compress_segmentby" in sql

    async def test_enable_compression_with_order_by(self, config):
        """Test enable_compression with order_by."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock()

        await db.timescale.enable_compression("events", order_by=["timestamp DESC"])

        sql = db.execute.call_args[0][0]
        assert "timescaledb.compress_orderby" in sql

    async def test_enable_compression_no_extension_raises(self, config):
        """Test enable_compression raises RuntimeError when extension missing."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=False)
        db._schema = mock_schema

        with pytest.raises(
            ExtensionNotAvailable, match="TimescaleDB extension not installed"
        ):
            await db.timescale.enable_compression("events")

    async def test_add_compression_policy_basic(self, config):
        """Test add_compression_policy with default interval."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock()

        await db.timescale.add_compression_policy("events", compress_after="7 days")

        mock_schema.has_extension.assert_called_once_with("timescaledb")
        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "add_compression_policy" in sql
        assert "compress_after => INTERVAL '7 days'" in sql

    async def test_add_compression_policy_no_extension_raises(self, config):
        """Test add_compression_policy raises RuntimeError when extension missing."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=False)
        db._schema = mock_schema

        with pytest.raises(
            ExtensionNotAvailable, match="TimescaleDB extension not installed"
        ):
            await db.timescale.add_compression_policy("events")

    async def test_add_retention_policy_basic(self, config):
        """Test add_retention_policy."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock()

        await db.timescale.add_retention_policy("events", drop_after="90 days")

        mock_schema.has_extension.assert_called_once_with("timescaledb")
        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "add_retention_policy" in sql
        assert "drop_after => INTERVAL '90 days'" in sql

    async def test_add_retention_policy_no_extension_raises(self, config):
        """Test add_retention_policy raises RuntimeError when extension missing."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=False)
        db._schema = mock_schema

        with pytest.raises(
            ExtensionNotAvailable, match="TimescaleDB extension not installed"
        ):
            await db.timescale.add_retention_policy("events", drop_after="90 days")

    async def test_list_hypertables_basic(self, config):
        """Test list_hypertables returns hypertable info."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock(
            return_value=[
                {
                    "schema": "public",
                    "table_name": "events",
                    "num_dimensions": 1,
                    "num_chunks": 10,
                    "compression_enabled": True,
                }
            ]
        )

        result = await db.timescale.list_hypertables()

        assert len(result) == 1
        assert result[0]["table_name"] == "events"
        mock_schema.has_extension.assert_called_once_with("timescaledb")
        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "timescaledb_information.hypertables" in sql

    async def test_list_hypertables_no_extension_raises(self, config):
        """Test list_hypertables raises RuntimeError when extension missing."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=False)
        db._schema = mock_schema

        with pytest.raises(
            ExtensionNotAvailable, match="TimescaleDB extension not installed"
        ):
            await db.timescale.list_hypertables()

    async def test_hypertable_info_basic(self, config):
        """Test hypertable_info returns size info."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=True)
        db._schema = mock_schema
        db.execute = AsyncMock(
            return_value=[{"total_size": "100 MB", "detailed_size": "detailed info"}]
        )

        result = await db.timescale.hypertable_info("events")

        assert result["total_size"] == "100 MB"
        mock_schema.has_extension.assert_called_once_with("timescaledb")
        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "hypertable_size" in sql

    async def test_hypertable_info_no_extension_raises(self, config):
        """Test hypertable_info raises RuntimeError when extension missing."""
        from pycopg.schema import AsyncSchemaAccessor

        db = AsyncDatabase(config)
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.has_extension = AsyncMock(return_value=False)
        db._schema = mock_schema

        with pytest.raises(
            ExtensionNotAvailable, match="TimescaleDB extension not installed"
        ):
            await db.timescale.hypertable_info("events")


class TestAsyncDatabaseConstraintsIntegration:
    """PAR-01: async mirrors of sync constraint/admin DDL, against the real DB."""

    @staticmethod
    def _tname():
        import uuid

        return f"test_async_{uuid.uuid4().hex[:8]}"

    async def test_add_primary_key_applies_constraint(self, db_config):
        """add_primary_key adds a real PK visible in the constraint catalog."""
        db = AsyncDatabase(db_config)
        t = self._tname()
        try:
            await db.execute(
                f'CREATE TABLE "{t}" (id INTEGER, name TEXT)', autocommit=True
            )
            await db.schema.add_primary_key(t, "id")
            rows = await db.execute(
                "SELECT 1 FROM information_schema.table_constraints "
                "WHERE table_name = %s AND constraint_type = 'PRIMARY KEY'",
                [t],
            )
            assert len(rows) == 1
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    async def test_add_primary_key_signature_matches_sync(self, db_config):
        """add_primary_key signature params match the sync twin."""
        import inspect

        from pycopg.schema import AsyncSchemaAccessor, SchemaAccessor

        async_params = list(
            inspect.signature(AsyncSchemaAccessor.add_primary_key).parameters
        )
        sync_params = list(inspect.signature(SchemaAccessor.add_primary_key).parameters)
        assert (
            async_params
            == sync_params
            == ["self", "table", "columns", "schema", "name"]
        )

    async def test_add_unique_constraint_rejects_duplicate(self, db_config):
        """add_unique_constraint enforces uniqueness (duplicate insert raises)."""
        db = AsyncDatabase(db_config)
        t = self._tname()
        try:
            await db.execute(
                f'CREATE TABLE "{t}" (id INTEGER, email TEXT)', autocommit=True
            )
            await db.schema.add_unique_constraint(t, "email")
            await db.execute(
                f'INSERT INTO "{t}" VALUES (1, %s)', ["a@x.com"], autocommit=True
            )
            with pytest.raises(Exception):
                await db.execute(
                    f'INSERT INTO "{t}" VALUES (2, %s)', ["a@x.com"], autocommit=True
                )
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    async def test_add_foreign_key_cascades_on_delete(self, db_config):
        """add_foreign_key creates an FK that cascades deletes."""
        db = AsyncDatabase(db_config)
        parent = self._tname()
        child = self._tname()
        try:
            await db.execute(
                f'CREATE TABLE "{parent}" (id INTEGER PRIMARY KEY)', autocommit=True
            )
            await db.execute(
                f'CREATE TABLE "{child}" (id INTEGER PRIMARY KEY, parent_id INTEGER)',
                autocommit=True,
            )
            await db.schema.add_foreign_key(
                child, "parent_id", parent, "id", on_delete="CASCADE"
            )
            await db.execute(f'INSERT INTO "{parent}" VALUES (1)', autocommit=True)
            await db.execute(f'INSERT INTO "{child}" VALUES (10, 1)', autocommit=True)
            await db.execute(f'DELETE FROM "{parent}" WHERE id = 1', autocommit=True)
            rows = await db.execute(f'SELECT * FROM "{child}"')
            assert rows == []
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{child}" CASCADE', autocommit=True)
            await db.execute(
                f'DROP TABLE IF EXISTS "{parent}" CASCADE', autocommit=True
            )

    async def test_add_foreign_key_invalid_action_raises_before_sql(self, db_config):
        """add_foreign_key with a bad on_delete raises ValueError and runs no SQL."""
        db = AsyncDatabase(db_config)
        with pytest.raises(ValueError, match="Invalid ON DELETE"):
            await db.schema.add_foreign_key(
                "orders", "user_id", "users", "id", on_delete="BOGUS"
            )

    async def test_truncate_table_removes_all_rows(self, db_config):
        """truncate_table leaves 0 rows on a populated table."""
        db = AsyncDatabase(db_config)
        t = self._tname()
        try:
            await db.execute(f'CREATE TABLE "{t}" (id INTEGER)', autocommit=True)
            await db.execute(f'INSERT INTO "{t}" VALUES (1), (2), (3)', autocommit=True)
            await db.schema.truncate_table(t)
            rows = await db.execute(f'SELECT COUNT(*) AS n FROM "{t}"')
            assert rows[0]["n"] == 0
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)


class TestAsyncDatabaseAdminIntegration:
    """PAR-02: async drop_extension/database_exists/list_databases + create constructors."""

    async def test_database_exists_true_and_false(self, db_config):
        """database_exists returns True for an existing DB and False otherwise."""
        db = AsyncDatabase(db_config)
        assert await db.schema.database_exists("pycopg_test") is True
        assert await db.schema.database_exists("definitely_absent_xyz") is False

    async def test_list_databases_includes_test_db(self, db_config):
        """list_databases returns non-template database names including pycopg_test."""
        db = AsyncDatabase(db_config)
        names = await db.schema.list_databases()
        assert isinstance(names, list)
        assert "pycopg_test" in names

    async def test_drop_extension_if_exists_is_safe(self, db_config):
        """drop_extension with if_exists=True does not raise when absent."""
        db = AsyncDatabase(db_config)
        # pg_trgm is a commonly available, droppable extension; ensure idempotent path
        await db.schema.create_extension("pg_trgm", if_not_exists=True)
        await db.schema.drop_extension("pg_trgm", if_exists=True)
        # Dropping again with if_exists=True must not raise
        await db.schema.drop_extension("pg_trgm", if_exists=True)
        # Restore for other tests that may assume it
        await db.schema.create_extension("pg_trgm", if_not_exists=True)

    def test_create_is_classmethod(self):
        """create / create_from_env are classmethods (D-02)."""
        assert isinstance(inspect.getattr_static(AsyncDatabase, "create"), classmethod)
        assert isinstance(
            inspect.getattr_static(AsyncDatabase, "create_from_env"), classmethod
        )

    async def test_create_from_env_delegates_to_create(self):
        """create_from_env loads env Config then delegates to create with its fields."""
        env_cfg = Config(
            host="envhost",
            port=5433,
            database="postgres",
            user="envuser",
            password="envpass",
        )
        with (
            patch(
                "pycopg.async_database.Config.from_env", return_value=env_cfg
            ) as mock_from_env,
            patch.object(
                AsyncDatabase, "create", new=AsyncMock(return_value="sentinel")
            ) as mock_create,
        ):
            result = await AsyncDatabase.create_from_env("newdb")

        mock_from_env.assert_called_once()
        mock_create.assert_awaited_once_with(
            name="newdb",
            host="envhost",
            port=5433,
            user="envuser",
            password="envpass",
            owner=None,
            template="template1",
            if_not_exists=True,
        )
        assert result == "sentinel"

    def test_create_signature_matches_sync(self):
        """AsyncDatabase.create accepts the same params as Database.create."""
        from pycopg import Database

        async_params = list(inspect.signature(AsyncDatabase.create).parameters)
        sync_params = list(inspect.signature(Database.create).parameters)
        assert async_params == sync_params

    async def test_create_returns_connected_database(self, db_config):
        """create makes a new DB and returns an AsyncDatabase connected to it."""
        target = "pycopg_tmp_create_xyz"
        admin = AsyncDatabase(db_config)
        # Ensure clean slate
        await admin.schema.drop_database(target, if_exists=True)
        try:
            new_db = await AsyncDatabase.create(
                target,
                host=db_config.host,
                port=db_config.port,
                user=db_config.user,
                password=db_config.password,
                if_not_exists=True,
            )
            assert isinstance(new_db, AsyncDatabase)
            assert new_db.config.database == target
            result = await new_db.execute("SELECT current_database() AS db")
            assert result[0]["db"] == target
            # if_not_exists=True on an existing DB must not raise
            await AsyncDatabase.create(
                target,
                host=db_config.host,
                port=db_config.port,
                user=db_config.user,
                password=db_config.password,
                if_not_exists=True,
            )
        finally:
            await admin.schema.drop_database(target, if_exists=True)

    async def test_create_raises_when_exists_and_not_if_not_exists(self, db_config):
        """create(if_not_exists=False) on an existing DB raises ValueError."""
        with pytest.raises(DatabaseExists, match="already exists"):
            await AsyncDatabase.create(
                "pycopg_test",
                host=db_config.host,
                port=db_config.port,
                user=db_config.user,
                password=db_config.password,
                if_not_exists=False,
            )


class TestAsyncDatabaseCorrectnessFixes:
    """Plan 05: C1 (primary_key applied), C2 (close disposes engine), PAR-07 signatures."""

    async def test_from_dataframe_applies_primary_key(self, config):
        """C1: from_dataframe with primary_key calls schema.add_primary_key (not a warning)."""
        import pandas as pd

        from pycopg.schema import AsyncSchemaAccessor

        mock_engine, _ = create_async_engine_mock()
        df = pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]})

        db = AsyncDatabase(config)
        db._async_engine = mock_engine
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.add_primary_key = AsyncMock()
        db._schema = mock_schema

        with patch.object(df, "to_sql"):
            await db.from_dataframe(df, "users", primary_key="id")

        mock_schema.add_primary_key.assert_awaited_once_with("users", "id", "public")

    async def test_from_dataframe_append_skips_primary_key(self, config):
        """C1: with if_exists='append', primary_key is NOT applied (matches sync guard)."""
        import pandas as pd

        from pycopg.schema import AsyncSchemaAccessor

        mock_engine, _ = create_async_engine_mock()
        df = pd.DataFrame({"id": [3]})

        db = AsyncDatabase(config)
        db._async_engine = mock_engine
        mock_schema = MagicMock(spec=AsyncSchemaAccessor)
        mock_schema.add_primary_key = AsyncMock()
        db._schema = mock_schema

        with patch.object(df, "to_sql"):
            await db.from_dataframe(df, "users", primary_key="id", if_exists="append")

        mock_schema.add_primary_key.assert_not_called()

    async def test_from_dataframe_real_db_applies_pk(self, db_config):
        """C1 integration: real from_dataframe with primary_key produces a PK constraint."""
        import pandas as pd

        db = AsyncDatabase(db_config)
        import uuid

        t = f"test_c1_{uuid.uuid4().hex[:8]}"
        df = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]})
        try:
            await db.from_dataframe(df, t, primary_key="id")
            rows = await db.execute(
                "SELECT 1 FROM information_schema.table_constraints "
                "WHERE table_name = %s AND constraint_type = 'PRIMARY KEY'",
                [t],
            )
            assert len(rows) == 1
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    async def test_close_disposes_engine(self, config):
        """C2: close() disposes the async engine and resets the reference."""
        mock_engine = MagicMock()
        mock_engine.dispose = AsyncMock()

        db = AsyncDatabase(config)
        db._async_engine = mock_engine

        await db.close()

        mock_engine.dispose.assert_awaited_once()
        assert db._async_engine is None

    async def test_close_no_engine_is_noop(self, config):
        """C2: close() with no engine created does not raise and is idempotent."""
        db = AsyncDatabase(config)
        assert db._async_engine is None
        await db.close()
        await db.close()
        assert db._async_engine is None

    async def test_create_extension_schema_clause(self, config):
        """PAR-07: create_extension(schema=...) emits a SCHEMA clause."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()
        await db.schema.create_extension("pg_trgm", schema="public")
        sql = db.execute.call_args[0][0]
        assert "SCHEMA public" in sql

    async def test_create_schema_owner_clause(self, config):
        """PAR-07: create_schema(owner=...) emits an AUTHORIZATION clause."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()
        await db.schema.create_schema("app", owner="appuser")
        sql = db.execute.call_args[0][0]
        assert "AUTHORIZATION appuser" in sql

    def test_create_extension_signature_matches_sync(self):
        """PAR-07/D-07: async create_extension signature matches the richer sync one."""
        from pycopg.schema import AsyncSchemaAccessor, SchemaAccessor

        a = list(inspect.signature(AsyncSchemaAccessor.create_extension).parameters)
        s = list(inspect.signature(SchemaAccessor.create_extension).parameters)
        assert a == s == ["self", "name", "schema", "if_not_exists"]

    def test_create_schema_signature_matches_sync(self):
        """PAR-07/D-07: async create_schema signature matches the richer sync one."""
        from pycopg.schema import AsyncSchemaAccessor, SchemaAccessor

        a = list(inspect.signature(AsyncSchemaAccessor.create_schema).parameters)
        s = list(inspect.signature(SchemaAccessor.create_schema).parameters)
        assert a == s == ["self", "name", "if_not_exists", "owner"]

    async def test_table_info_fields_match_sync(self, db_config):
        """PAR-07: async/sync table_info return the same dict keys."""
        import uuid

        from pycopg import Database

        t = f"test_ti_{uuid.uuid4().hex[:8]}"
        adb = AsyncDatabase(db_config)
        sdb = Database(db_config)
        try:
            await adb.execute(
                f'CREATE TABLE "{t}" (id INTEGER, name TEXT)', autocommit=True
            )
            a_info = await adb.schema.table_info(t)
            s_info = sdb.schema.table_info(t)
            assert {*a_info[0].keys()} == {*s_info[0].keys()}
        finally:
            await adb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    async def test_list_roles_fields_match_sync(self, db_config):
        """PAR-07: async/sync list_roles return the same dict keys."""
        from pycopg import Database

        adb = AsyncDatabase(db_config)
        sdb = Database(db_config)
        a_roles = await adb.admin.list_roles()
        s_roles = sdb.admin.list_roles()
        if a_roles and s_roles:
            assert {*a_roles[0].keys()} == {*s_roles[0].keys()}


class TestAsyncDatabaseCoverageFill:
    """PAR-09 coverage: async copy_insert/size/csv/timescale lifecycle on the real DB."""

    @staticmethod
    def _t():
        import uuid

        return f"test_acov_{uuid.uuid4().hex[:8]}"

    async def test_copy_insert(self, db_config):
        """async copy_insert bulk-loads via COPY."""
        db = AsyncDatabase(db_config)
        t = self._t()
        try:
            await db.execute(
                f'CREATE TABLE "{t}" (id INTEGER, name TEXT)', autocommit=True
            )
            count = await db.copy_insert(
                t, [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
            )
            assert count == 2
            rows = await db.execute(f'SELECT COUNT(*) AS n FROM "{t}"')
            assert rows[0]["n"] == 2
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    async def test_size_table_size_row_count(self, db_config):
        """async size/table_size/row_count return values."""
        db = AsyncDatabase(db_config)
        t = self._t()
        try:
            await db.execute(f'CREATE TABLE "{t}" (id INTEGER)', autocommit=True)
            await db.insert_many(t, [{"id": i} for i in range(3)])
            assert isinstance(await db.maint.size(pretty=True), str)
            assert isinstance(await db.maint.size(pretty=False), int)
            assert await db.maint.table_size(t) is not None
            assert isinstance(await db.schema.row_count(t), int)
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    async def test_copy_to_and_from_csv(self, db_config, tmp_path):
        """async copy_to_csv exports; copy_from_csv re-imports."""
        db = AsyncDatabase(db_config)
        src = self._t()
        dst = self._t()
        try:
            await db.execute(
                f'CREATE TABLE "{src}" (id INTEGER, name TEXT)', autocommit=True
            )
            await db.insert_many(src, [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}])
            csv_path = tmp_path / "async_out.csv"
            exported = await db.backup.copy_to_csv(src, str(csv_path))
            assert exported == 2
            assert csv_path.exists()
            await db.execute(
                f'CREATE TABLE "{dst}" (id INTEGER, name TEXT)', autocommit=True
            )
            await db.backup.copy_from_csv(dst, str(csv_path))
            rows = await db.execute(f'SELECT id, name FROM "{dst}" ORDER BY id')
            assert rows == [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{src}" CASCADE', autocommit=True)
            await db.execute(f'DROP TABLE IF EXISTS "{dst}" CASCADE', autocommit=True)

    async def test_hypertable_lifecycle(self, db_config):
        """async create_hypertable -> hypertable_info -> list_hypertables."""
        db = AsyncDatabase(db_config)
        if not await db.schema.has_extension("timescaledb"):
            try:
                await db.schema.create_extension("timescaledb", if_not_exists=True)
            except Exception:
                pytest.skip("TimescaleDB not available")
        if not await db.schema.has_extension("timescaledb"):
            pytest.skip("TimescaleDB not available")

        t = self._t()
        try:
            await db.execute(
                f'CREATE TABLE "{t}" (ts TIMESTAMPTZ NOT NULL, v DOUBLE PRECISION)',
                autocommit=True,
            )
            await db.timescale.create_hypertable(t, "ts", chunk_time_interval="1 day")
            info = await db.timescale.hypertable_info(t)
            assert "total_size" in info
            hts = await db.timescale.list_hypertables()
            assert any(h["table_name"] == t for h in hts)
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    # NOTE: async from_geodataframe/to_geodataframe are intentionally NOT exercised
    # here. geopandas (a sync-only library) reaches for a raw DBAPI cursor context
    # manager that SQLAlchemy's async psycopg adapter does not expose under
    # run_sync, so to_postgis raises TypeError in this environment. Async GIS
    # DataFrame integration is out of Phase 11 scope (PAR parity covers the
    # constraint/admin/batch surface); the sync GeoDataFrame round-trip is
    # covered in test_database_integration.py::TestDatabaseGeoCoverage.


@pytest.mark.asyncio
class TestAsyncDatabaseCRUDErgonomics:
    """34-02: upsert / delete_where / update_where async live-DB tests."""

    def _t(self):
        import uuid

        return f"test_crud_{uuid.uuid4().hex[:8]}"

    async def test_upsert_async(self, db_config):
        """async upsert inserts a row and returns full row dict, then updates it."""
        import uuid

        db = AsyncDatabase(db_config)
        t = f"test_upsert_{uuid.uuid4().hex[:8]}"
        try:
            await db.execute(
                f'CREATE TABLE "{t}" (id INTEGER PRIMARY KEY, name TEXT, email TEXT)',
                autocommit=True,
            )
            # Insert path
            row = await db.upsert(t, {"id": 1, "name": "Alice", "email": "a@x.com"}, ["id"])
            assert isinstance(row, dict)
            assert row["id"] == 1
            assert row["name"] == "Alice"

            # Update path
            row2 = await db.upsert(t, {"id": 1, "name": "Alice", "email": "new@x.com"}, ["id"])
            assert isinstance(row2, dict)
            assert row2["email"] == "new@x.com"
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    async def test_delete_where_async(self, db_config):
        """async delete_where deletes matching rows and returns the count."""
        import uuid

        db = AsyncDatabase(db_config)
        t = f"test_delw_{uuid.uuid4().hex[:8]}"
        try:
            await db.execute(
                f'CREATE TABLE "{t}" (id INTEGER PRIMARY KEY, name TEXT)',
                autocommit=True,
            )
            await db.insert_many(
                t,
                [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
            )
            count = await db.delete_where(t, {"id": 1})
            assert count == 1
            remaining = await db.execute(f'SELECT id FROM "{t}" ORDER BY id')
            assert [r["id"] for r in remaining] == [2]
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    async def test_delete_where_empty_raises_async(self, db_config):
        """async delete_where with empty where raises ValueError before any DB call."""
        db = AsyncDatabase(db_config)
        with pytest.raises(ValueError):
            await db.delete_where("any_table", {})


@pytest.mark.asyncio
class TestAsyncDatabaseReadHelpers:
    """34-03: exists / count / paginate / fetch_all async live-DB tests."""

    def _t(self, prefix="crud"):
        import uuid

        return f"test_{prefix}_{uuid.uuid4().hex[:8]}"

    async def test_exists_async(self, db_config):
        """async exists returns True for a present row and False for an absent one."""
        db = AsyncDatabase(db_config)
        t = self._t("exists")
        try:
            await db.execute(
                f'CREATE TABLE "{t}" (id INTEGER PRIMARY KEY, name TEXT)',
                autocommit=True,
            )
            await db.insert_many(t, [{"id": 1, "name": "Alice"}])

            assert await db.exists(t, {"id": 1}) is True
            assert await db.exists(t, {"id": 999}) is False
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    async def test_exists_empty_where_raises_async(self, db_config):
        """async exists with empty where raises ValueError before any DB call."""
        db = AsyncDatabase(db_config)
        with pytest.raises(ValueError):
            await db.exists("any_table", {})

    async def test_count_async(self, db_config):
        """async count returns total (where=None) and filtered count."""
        db = AsyncDatabase(db_config)
        t = self._t("count")
        try:
            await db.execute(
                f'CREATE TABLE "{t}" (id INTEGER PRIMARY KEY, active BOOLEAN)',
                autocommit=True,
            )
            await db.insert_many(
                t,
                [
                    {"id": 1, "active": True},
                    {"id": 2, "active": False},
                    {"id": 3, "active": True},
                ],
            )

            assert await db.count(t) == 3
            assert await db.count(t, {"active": True}) == 2
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    async def test_paginate_async(self, db_config):
        """async paginate returns the correct page slice in order."""
        db = AsyncDatabase(db_config)
        t = self._t("pag")
        try:
            await db.execute(
                f'CREATE TABLE "{t}" (id INTEGER PRIMARY KEY, name TEXT)',
                autocommit=True,
            )
            await db.insert_many(
                t,
                [
                    {"id": 1, "name": "Alice"},
                    {"id": 2, "name": "Bob"},
                    {"id": 3, "name": "Carol"},
                ],
            )

            page = await db.paginate(t, limit=2, offset=0, order_by="id")
            assert len(page) == 2
            assert [r["id"] for r in page] == [1, 2]

            page2 = await db.paginate(t, limit=2, offset=2, order_by="id")
            assert len(page2) == 1
            assert page2[0]["id"] == 3
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    async def test_fetch_all_async(self, db_config):
        """async fetch_all returns list[dict]; empty result returns []."""
        db = AsyncDatabase(db_config)
        t = self._t("fall")
        try:
            await db.execute(
                f'CREATE TABLE "{t}" (id INTEGER PRIMARY KEY, name TEXT)',
                autocommit=True,
            )
            await db.insert_many(t, [{"id": 1, "name": "Alice"}])

            rows = await db.fetch_all(f'SELECT id, name FROM "{t}" ORDER BY id')
            assert isinstance(rows, list)
            assert len(rows) == 1
            assert isinstance(rows[0], dict)
            assert rows[0]["id"] == 1

            empty = await db.fetch_all(
                f'SELECT id FROM "{t}" WHERE id = 9999'
            )
            assert empty == []
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)


@pytest.mark.asyncio
class TestAsyncSchemaIntrospection:
    """35-01/35-02: async schema introspection — primary_key / foreign_keys / sequences / views / describe."""

    def _t(self, prefix="intr"):
        import uuid

        return f"test_{prefix}_{uuid.uuid4().hex[:8]}"

    async def test_primary_key_async(self, db_config):
        """async primary_key returns constraint_name + columns for a table with a PK."""
        db = AsyncDatabase(db_config)
        t = self._t("pk")
        try:
            await db.execute(
                f'CREATE TABLE "{t}" (id INTEGER PRIMARY KEY, name TEXT)',
                autocommit=True,
            )
            result = await db.schema.primary_key(t)
            assert result is not None
            assert "constraint_name" in result
            assert result["columns"] == ["id"]
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    async def test_primary_key_none_async(self, db_config):
        """async primary_key returns None for a table with no PK."""
        db = AsyncDatabase(db_config)
        t = self._t("npk")
        try:
            await db.execute(
                f'CREATE TABLE "{t}" (id INTEGER, name TEXT)',
                autocommit=True,
            )
            result = await db.schema.primary_key(t)
            assert result is None
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    async def test_foreign_keys_async(self, db_config):
        """async foreign_keys returns FK constraints with referenced table info."""
        db = AsyncDatabase(db_config)
        parent = self._t("fkp")
        child = self._t("fkc")
        try:
            await db.execute(
                f'CREATE TABLE "{parent}" (id INTEGER PRIMARY KEY)',
                autocommit=True,
            )
            await db.execute(
                f'CREATE TABLE "{child}" (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES "{parent}"(id))',
                autocommit=True,
            )
            fks = await db.schema.foreign_keys(child)
            assert isinstance(fks, list)
            assert len(fks) == 1
            assert fks[0]["referenced_table"] == parent
            assert fks[0]["columns"] == ["parent_id"]
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{child}" CASCADE', autocommit=True)
            await db.execute(f'DROP TABLE IF EXISTS "{parent}" CASCADE', autocommit=True)

    async def test_sequences_async(self, db_config):
        """async sequences returns sequence names in the schema."""
        db = AsyncDatabase(db_config)
        t = self._t("seq")
        try:
            await db.execute(
                f'CREATE TABLE "{t}" (id SERIAL PRIMARY KEY)',
                autocommit=True,
            )
            seqs = await db.schema.sequences("public")
            assert isinstance(seqs, list)
            assert len(seqs) >= 1
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    async def test_views_async(self, db_config):
        """async views returns regular view names; excludes materialized views."""
        db = AsyncDatabase(db_config)
        view_name = self._t("vw")
        t = self._t("vwt")
        try:
            await db.execute(
                f'CREATE TABLE "{t}" (id INTEGER PRIMARY KEY)',
                autocommit=True,
            )
            await db.execute(
                f'CREATE VIEW "{view_name}" AS SELECT id FROM "{t}"',
                autocommit=True,
            )
            views = await db.schema.views("public")
            assert isinstance(views, list)
            assert view_name in views
        finally:
            await db.execute(f'DROP VIEW IF EXISTS "{view_name}"', autocommit=True)
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    async def test_describe_async(self, db_config):
        """async describe returns a dict with columns/primary_key/foreign_keys/indexes keys."""
        db = AsyncDatabase(db_config)
        t = self._t("desc")
        try:
            await db.execute(
                f'CREATE TABLE "{t}" (id INTEGER PRIMARY KEY, name TEXT)',
                autocommit=True,
            )
            result = await db.schema.describe(t)
            assert set(result.keys()) == {"columns", "primary_key", "foreign_keys", "indexes"}
            assert isinstance(result["columns"], list)
            assert result["primary_key"] is not None
            assert result["primary_key"]["columns"] == ["id"]
            assert result["foreign_keys"] == []
        finally:
            await db.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)
