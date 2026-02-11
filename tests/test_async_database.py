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


@pytest.mark.asyncio
class TestAsyncDatabaseGeoDataFrame:
    """Tests for async GeoDataFrame methods."""

    async def test_to_geodataframe_with_table(self, config):
        """Test to_geodataframe with table name."""
        import geopandas as gpd
        from shapely.geometry import Point

        mock_engine, mock_sync_conn = create_async_engine_mock()
        expected_gdf = gpd.GeoDataFrame(
            {"id": [1], "geometry": [Point(0, 0)]},
            crs="EPSG:4326"
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
            {"id": [1], "geometry": [Point(0, 0)]},
            crs="EPSG:4326"
        )

        db = AsyncDatabase(config)
        db._async_engine = mock_engine

        with patch("geopandas.read_postgis", return_value=expected_gdf):
            result = await db.to_geodataframe(sql="SELECT * FROM parcels WHERE area > 100")

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

        gdf = gpd.GeoDataFrame(
            {"id": [1], "geometry": [Point(0, 0)]},
            crs="EPSG:4326"
        )

        db = AsyncDatabase(config)
        db.has_extension = AsyncMock(return_value=False)

        with pytest.raises(RuntimeError, match="PostGIS extension not installed"):
            await db.from_geodataframe(gdf, "parcels")

        db.has_extension.assert_called_once_with("postgis")

    async def test_from_geodataframe_no_crs_raises(self, config):
        """Test from_geodataframe raises ValueError when GeoDataFrame has no CRS."""
        import geopandas as gpd
        from shapely.geometry import Point

        gdf = gpd.GeoDataFrame(
            {"id": [1], "geometry": [Point(0, 0)]},
            crs=None  # No CRS
        )

        db = AsyncDatabase(config)
        db.has_extension = AsyncMock(return_value=True)

        with pytest.raises(ValueError, match="GeoDataFrame has no CRS defined"):
            await db.from_geodataframe(gdf, "parcels")

    async def test_from_geodataframe_unknown_crs_raises(self, config):
        """Test from_geodataframe raises ValueError on CRS with no EPSG code."""
        import geopandas as gpd
        from shapely.geometry import Point

        gdf = gpd.GeoDataFrame(
            {"id": [1], "geometry": [Point(0, 0)]},
            crs="EPSG:4326"
        )
        # Mock CRS.to_epsg() returning None (unknown EPSG)
        with patch.object(type(gdf), 'crs', new_callable=PropertyMock) as mock_crs_prop:
            mock_crs = MagicMock()
            mock_crs.to_epsg.return_value = None
            mock_crs_prop.return_value = mock_crs

            db = AsyncDatabase(config)
            db.has_extension = AsyncMock(return_value=True)

            with pytest.raises(ValueError, match="Cannot determine EPSG code"):
                await db.from_geodataframe(gdf, "parcels")

    async def test_from_geodataframe_with_explicit_srid(self, config):
        """Test from_geodataframe with explicit srid bypasses CRS check."""
        import geopandas as gpd
        from shapely.geometry import Point

        mock_engine, mock_sync_conn = create_async_engine_mock()
        gdf = gpd.GeoDataFrame(
            {"id": [1], "geometry": [Point(0, 0)]},
            crs=None  # No CRS, but explicit srid should be fine
        )

        db = AsyncDatabase(config)
        db._async_engine = mock_engine
        db.has_extension = AsyncMock(return_value=True)

        with patch.object(gdf, "to_postgis") as mock_to_postgis:
            await db.from_geodataframe(gdf, "parcels", srid=4326)

            mock_to_postgis.assert_called_once()

    async def test_from_geodataframe_basic(self, config):
        """Test from_geodataframe writes GeoDataFrame to table."""
        import geopandas as gpd
        from shapely.geometry import Point

        mock_engine, mock_sync_conn = create_async_engine_mock()
        gdf = gpd.GeoDataFrame(
            {"id": [1], "geometry": [Point(0, 0)]},
            crs="EPSG:4326"
        )

        db = AsyncDatabase(config)
        db._async_engine = mock_engine
        db.has_extension = AsyncMock(return_value=True)

        with patch.object(gdf, "to_postgis") as mock_to_postgis:
            await db.from_geodataframe(gdf, "parcels")

            mock_to_postgis.assert_called_once()
            call_kwargs = mock_to_postgis.call_args[1]
            assert call_kwargs["name"] == "parcels"
            assert call_kwargs["schema"] == "public"


@pytest.mark.asyncio
class TestAsyncDatabaseDDL:
    """Tests for DDL operations (drop_table, create_index, etc.)."""

    async def test_drop_table_basic(self, config):
        """Test drop_table with default parameters."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.drop_table("users")

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "DROP TABLE IF EXISTS public.users" in sql

    async def test_drop_table_cascade(self, config):
        """Test drop_table with cascade option."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.drop_table("users", cascade=True)

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "DROP TABLE IF EXISTS public.users CASCADE" in sql

    async def test_create_index_basic(self, config):
        """Test create_index with single column."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.create_index("users", "email")

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "CREATE INDEX IF NOT EXISTS" in sql
        assert "ON public.users USING btree (email)" in sql

    async def test_create_index_unique_multi_column(self, config):
        """Test create_index with unique constraint and multiple columns."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.create_index("users", ["first_name", "last_name"], unique=True)

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "CREATE UNIQUE INDEX" in sql
        assert "first_name, last_name" in sql

    async def test_drop_index_basic(self, config):
        """Test drop_index with default parameters."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.drop_index("idx_users_email")

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "DROP INDEX IF EXISTS public.idx_users_email" in sql

    async def test_list_indexes(self, config):
        """Test list_indexes returns index information."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(return_value=[
            {"index_name": "idx_users_email", "index_type": "btree", "index_def": "CREATE INDEX..."},
            {"index_name": "users_pkey", "index_type": "btree", "index_def": "CREATE UNIQUE INDEX..."}
        ])

        indexes = await db.list_indexes("users")

        assert len(indexes) == 2
        assert indexes[0]["index_name"] == "idx_users_email"
        assert indexes[1]["index_name"] == "users_pkey"

        # Verify SQL parameters
        call_args = db.execute.call_args
        assert call_args[0][1] == ["public", "users"]

    async def test_list_constraints(self, config):
        """Test list_constraints returns constraint information."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(return_value=[
            {"constraint_name": "users_pkey", "constraint_type": "p", "constraint_def": "PRIMARY KEY (id)"},
            {"constraint_name": "users_email_key", "constraint_type": "u", "constraint_def": "UNIQUE (email)"}
        ])

        constraints = await db.list_constraints("users")

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

        await db.drop_schema("analytics")

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "DROP SCHEMA IF EXISTS analytics" in sql

    async def test_drop_schema_cascade(self, config):
        """Test drop_schema with cascade option."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.drop_schema("analytics", cascade=True)

        db.execute.assert_called_once()
        sql = db.execute.call_args[0][0]
        assert "DROP SCHEMA IF EXISTS analytics CASCADE" in sql

    async def test_table_sizes(self, config):
        """Test table_sizes returns size information."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(return_value=[
            {
                "table_name": "users",
                "total_size": "128 MB",
                "data_size": "100 MB",
                "index_size": "28 MB"
            },
            {
                "table_name": "logs",
                "total_size": "64 MB",
                "data_size": "50 MB",
                "index_size": "14 MB"
            }
        ])

        sizes = await db.table_sizes("public", limit=10)

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
            await db.create_database("testdb")

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
            await db.create_database("testdb", owner="appuser")

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
            await db.drop_database("testdb")

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
            await db.drop_database("testdb", if_exists=False)

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

        await db.vacuum()

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "VACUUM(ANALYZE)" in sql
        assert call_args[1]["autocommit"] is True

    async def test_vacuum_full_table(self, config):
        """Test vacuum with full and specific table."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.vacuum("users", full=True)

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

        await db.vacuum(analyze=False)

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

        await db.analyze()

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "ANALYZE" in sql
        assert call_args[1]["autocommit"] is True

    async def test_analyze_table(self, config):
        """Test analyze on specific table."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.analyze("users", schema="public")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "ANALYZE public.users" in sql
        assert call_args[1]["autocommit"] is True

    async def test_explain_basic(self, config):
        """Test basic explain."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(return_value=[{"QUERY PLAN": "Seq Scan on users"}])

        result = await db.explain("SELECT * FROM users")

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
        db.execute = AsyncMock(return_value=[
            {"QUERY PLAN": "Seq Scan on users (cost=0.00..10.00 rows=100 width=32)"},
            {"QUERY PLAN": "Planning Time: 0.1ms"},
            {"QUERY PLAN": "Execution Time: 1.2ms"}
        ])

        result = await db.explain("SELECT * FROM users", analyze=True)

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

        result = await db.explain("SELECT * FROM users", format="json")

        assert len(result) == 1
        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "FORMAT JSON" in sql


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
        await db.pg_dump("/tmp/backup.dump")

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
        await db.pg_dump("/tmp/backup.sql", format="plain", schema_only=True)

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
        mock_proc.communicate = AsyncMock(return_value=(b"", b"pg_dump: error: database connection failed"))
        mock_subprocess.return_value = mock_proc

        db = AsyncDatabase(config)

        with pytest.raises(RuntimeError, match="pg_dump failed"):
            await db.pg_dump("/tmp/backup.dump")

    @patch("asyncio.create_subprocess_exec")
    async def test_pg_dump_with_tables(self, mock_subprocess, config):
        """Test pg_dump with specific tables."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_subprocess.return_value = mock_proc

        db = AsyncDatabase(config)
        await db.pg_dump("/tmp/backup.dump", tables=["users", "orders"])

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
            with patch("pathlib.Path.suffix", new_callable=PropertyMock, return_value=".dump"):
                await db.pg_restore("/tmp/backup.dump")

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
            with patch("pathlib.Path.suffix", new_callable=PropertyMock, return_value=".dump"):
                await db.pg_restore("/tmp/backup.dump", clean=True, if_exists=True)

        call_args = mock_subprocess.call_args
        cmd = call_args[0]
        assert "--clean" in cmd
        assert "--if-exists" in cmd

    async def test_pg_restore_sql_file(self, config):
        """Test pg_restore delegates to _psql_restore for .sql files."""
        db = AsyncDatabase(config)
        db._psql_restore = AsyncMock()

        # File with .sql suffix
        await db.pg_restore("/tmp/backup.sql")

        db._psql_restore.assert_called_once()

    @patch("asyncio.create_subprocess_exec")
    async def test_pg_restore_failure(self, mock_subprocess, config):
        """Test pg_restore failure."""
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"pg_restore: error: invalid format"))
        mock_subprocess.return_value = mock_proc

        db = AsyncDatabase(config)
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.suffix", new_callable=PropertyMock, return_value=".dump"):
                with pytest.raises(RuntimeError, match="pg_restore failed"):
                    await db.pg_restore("/tmp/backup.dump")

    @patch("asyncio.create_subprocess_exec")
    async def test_psql_restore(self, mock_subprocess, config):
        """Test _psql_restore."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_subprocess.return_value = mock_proc

        db = AsyncDatabase(config)
        from pathlib import Path
        await db._psql_restore(Path("/tmp/backup.sql"))

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
                    count = await db.copy_to_csv("users", "/tmp/users.csv")

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
                    await db.copy_to_csv("users", "/tmp/users.csv", columns=["id", "name"])

        copy_call = mock_cursor.copy.call_args
        sql = copy_call[0][0]
        assert "(id, name)" in sql

    async def test_copy_to_csv_validates_identifiers(self, config):
        """Test copy_to_csv validates identifiers."""
        db = AsyncDatabase(config)

        with pytest.raises(InvalidIdentifier):
            await db.copy_to_csv("DROP TABLE", "/tmp/out.csv")

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
        mock_file.read.side_effect = [csv_data, ""]  # Return data then empty to signal EOF

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

            count = await db.copy_from_csv("users", "/tmp/users.csv")

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

            await db.copy_from_csv("users", "/tmp/users.csv", columns=["id", "name"])

        copy_call = mock_cursor.copy.call_args
        sql = copy_call[0][0]
        assert "(id, name)" in sql

    async def test_copy_from_csv_validates_identifiers(self, config):
        """Test copy_from_csv validates identifiers."""
        db = AsyncDatabase(config)

        with pytest.raises(InvalidIdentifier):
            await db.copy_from_csv("DROP TABLE", "/tmp/in.csv")


@pytest.mark.asyncio
class TestAsyncDatabaseRoles:
    """Tests for AsyncDatabase role lifecycle methods."""

    async def test_create_role_basic(self, config):
        """Test create_role with basic login user."""
        db = AsyncDatabase(config)
        db.role_exists = AsyncMock(return_value=False)
        db.execute = AsyncMock()

        await db.create_role("appuser")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "CREATE ROLE appuser WITH" in sql
        assert "LOGIN" in sql
        assert call_args[1]["autocommit"] is True

    async def test_create_role_with_password(self, config):
        """Test create_role with password uses parameterized query."""
        db = AsyncDatabase(config)
        db.role_exists = AsyncMock(return_value=False)

        # Mock cursor context manager
        mock_cursor = MagicMock()
        mock_cursor.execute = AsyncMock()

        @asynccontextmanager
        async def cursor_cm(autocommit=False):
            yield mock_cursor

        db.cursor = MagicMock(side_effect=cursor_cm)

        await db.create_role("appuser", password="secret123")

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
        db.role_exists = AsyncMock(return_value=True)
        db.execute = AsyncMock()

        await db.create_role("appuser")

        # execute should NOT be called
        db.execute.assert_not_called()

    async def test_create_role_with_options(self, config):
        """Test create_role with various role options."""
        db = AsyncDatabase(config)
        db.role_exists = AsyncMock(return_value=False)
        db.execute = AsyncMock()

        await db.create_role(
            "admin",
            superuser=True,
            createdb=True,
            createrole=True,
            connection_limit=10,
            replication=True
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
        db.role_exists = AsyncMock(return_value=False)
        db.execute = AsyncMock()
        db.grant_role = AsyncMock()

        await db.create_role("analyst", in_roles=["readonly", "reporting"])

        # Verify grant_role was called for each role
        assert db.grant_role.call_count == 2
        db.grant_role.assert_any_call("readonly", "analyst")
        db.grant_role.assert_any_call("reporting", "analyst")

    async def test_create_role_nologin(self, config):
        """Test create_role with login=False creates group role."""
        db = AsyncDatabase(config)
        db.role_exists = AsyncMock(return_value=False)
        db.execute = AsyncMock()

        await db.create_role("readonly", login=False)

        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "NOLOGIN" in sql

    async def test_create_role_noinherit(self, config):
        """Test create_role with inherit=False."""
        db = AsyncDatabase(config)
        db.role_exists = AsyncMock(return_value=False)
        db.execute = AsyncMock()

        await db.create_role("noinherit_role", inherit=False)

        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "NOINHERIT" in sql

    async def test_create_role_with_valid_until(self, config):
        """Test create_role with password expiration."""
        db = AsyncDatabase(config)
        db.role_exists = AsyncMock(return_value=False)
        db.execute = AsyncMock()

        await db.create_role("tempuser", valid_until="2025-12-31")

        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "VALID UNTIL '2025-12-31'" in sql

    async def test_drop_role_basic(self, config):
        """Test drop_role with default IF EXISTS."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.drop_role("olduser")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "DROP ROLE IF EXISTS olduser" in sql
        assert call_args[1]["autocommit"] is True

    async def test_drop_role_no_if_exists(self, config):
        """Test drop_role without IF EXISTS clause."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.drop_role("olduser", if_exists=False)

        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "DROP ROLE olduser" in sql
        assert "IF EXISTS" not in sql

    async def test_alter_role_rename(self, config):
        """Test alter_role rename."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.alter_role("oldname", rename_to="newname")

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

        await db.alter_role("appuser", password="newpassword")

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

        await db.alter_role("appuser", login=False, createdb=True, superuser=False)

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

        await db.alter_role("appuser", connection_limit=5)

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

        await db.alter_role("appuser", valid_until="2026-12-31")

        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        assert "VALID UNTIL '2026-12-31'" in sql


@pytest.mark.asyncio
class TestAsyncDatabasePrivileges:
    """Tests for AsyncDatabase privilege management methods."""

    async def test_grant_table(self, config):
        """Test grant on a specific table."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.grant("SELECT", "users", "readonly")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "GRANT SELECT ON TABLE public.users TO readonly" in sql
        assert call_args[1]["autocommit"] is True

    async def test_grant_schema(self, config):
        """Test grant on schema."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.grant("USAGE", "myschema", "appuser", object_type="SCHEMA")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "GRANT USAGE ON SCHEMA myschema TO appuser" in sql

    async def test_grant_database(self, config):
        """Test grant on database."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.grant("CONNECT", "mydb", "appuser", object_type="DATABASE")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "GRANT CONNECT ON DATABASE mydb TO appuser" in sql

    async def test_grant_all_tables(self, config):
        """Test grant on all tables in schema."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.grant("SELECT", "ALL TABLES", "readonly", schema="public")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly" in sql

    async def test_grant_all_sequences(self, config):
        """Test grant on all sequences in schema."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.grant("USAGE", "ALL SEQUENCES", "appuser", schema="myschema")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "GRANT USAGE ON ALL SEQUENCES IN SCHEMA myschema TO appuser" in sql

    async def test_grant_all_functions(self, config):
        """Test grant on all functions in schema."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.grant("EXECUTE", "ALL FUNCTIONS", "appuser", schema="public")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO appuser" in sql

    async def test_grant_with_grant_option(self, config):
        """Test grant with WITH GRANT OPTION."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.grant("SELECT", "users", "admin", with_grant_option=True)

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "WITH GRANT OPTION" in sql

    async def test_grant_list_privileges(self, config):
        """Test grant with list of privileges."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.grant(["SELECT", "INSERT", "UPDATE"], "users", "appuser")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "SELECT, INSERT, UPDATE" in sql

    async def test_revoke_table(self, config):
        """Test revoke on a specific table."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.revoke("INSERT", "users", "readonly")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "REVOKE INSERT ON TABLE public.users FROM readonly" in sql
        assert call_args[1]["autocommit"] is True

    async def test_revoke_schema(self, config):
        """Test revoke on schema."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.revoke("USAGE", "myschema", "olduser", object_type="SCHEMA")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "REVOKE USAGE ON SCHEMA myschema FROM olduser" in sql

    async def test_revoke_cascade(self, config):
        """Test revoke with CASCADE option."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.revoke("ALL", "orders", "former_user", cascade=True)

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "REVOKE ALL ON TABLE public.orders FROM former_user CASCADE" in sql

    async def test_revoke_all_tables(self, config):
        """Test revoke on all tables in schema."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.revoke("DELETE", "ALL TABLES", "readonly", schema="public")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "REVOKE DELETE ON ALL TABLES IN SCHEMA public FROM readonly" in sql

    async def test_revoke_list_privileges(self, config):
        """Test revoke with list of privileges."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.revoke(["INSERT", "UPDATE", "DELETE"], "users", "readonly")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "INSERT, UPDATE, DELETE" in sql

    async def test_grant_role_basic(self, config):
        """Test grant_role basic membership."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.grant_role("readonly", "analyst")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "GRANT readonly TO analyst" in sql
        assert call_args[1]["autocommit"] is True

    async def test_grant_role_with_admin(self, config):
        """Test grant_role with admin option."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.grant_role("admin", "lead_dev", with_admin=True)

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "GRANT admin TO lead_dev WITH ADMIN OPTION" in sql

    async def test_revoke_role_basic(self, config):
        """Test revoke_role basic membership."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock()

        await db.revoke_role("admin", "former_admin")

        db.execute.assert_called_once()
        call_args = db.execute.call_args
        sql = call_args[0][0]
        assert "REVOKE admin FROM former_admin" in sql
        assert call_args[1]["autocommit"] is True


@pytest.mark.asyncio
class TestAsyncDatabaseRoleInspection:
    """Tests for AsyncDatabase role inspection methods."""

    async def test_list_role_members(self, config):
        """Test list_role_members returns member names."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(return_value=[
            {"member": "analyst"},
            {"member": "viewer"}
        ])

        result = await db.list_role_members("readonly")

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

        result = await db.list_role_members("emptyrole")

        assert result == []

    async def test_list_role_grants(self, config):
        """Test list_role_grants returns grant info."""
        db = AsyncDatabase(config)
        db.execute = AsyncMock(return_value=[
            {"schema": "public", "object_name": "users", "privilege": "SELECT"},
            {"schema": "public", "object_name": "orders", "privilege": "INSERT"}
        ])

        result = await db.list_role_grants("appuser")

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

        result = await db.list_role_grants("nogrants")

        assert result == []
