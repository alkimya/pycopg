"""Tests for pycopg.pool module."""

from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from pycopg import Config
from pycopg.pool import PooledDatabase, AsyncPooledDatabase


class TestPooledDatabase:
    """Tests for PooledDatabase class."""

    @patch("pycopg.pool.ConnectionPool")
    def test_init(self, mock_pool_class, config):
        """Test initialization creates pool."""
        db = PooledDatabase(config, min_size=5, max_size=20)

        mock_pool_class.assert_called_once()
        call_kwargs = mock_pool_class.call_args[1]
        assert call_kwargs["min_size"] == 5
        assert call_kwargs["max_size"] == 20
        assert "conninfo" in call_kwargs

    @patch("pycopg.pool.ConnectionPool")
    def test_init_custom_options(self, mock_pool_class, config):
        """Test initialization with custom pool options."""
        db = PooledDatabase(
            config,
            min_size=2,
            max_size=10,
            max_idle=600.0,
            max_lifetime=7200.0,
            timeout=60.0,
            num_workers=5,
        )

        call_kwargs = mock_pool_class.call_args[1]
        assert call_kwargs["max_idle"] == 600.0
        assert call_kwargs["max_lifetime"] == 7200.0
        assert call_kwargs["timeout"] == 60.0
        assert call_kwargs["num_workers"] == 5

    @patch("pycopg.pool.ConnectionPool")
    @patch("pycopg.pool.Config.from_env")
    def test_from_env(self, mock_from_env, mock_pool_class):
        """Test creating from environment."""
        mock_from_env.return_value = Config()

        db = PooledDatabase.from_env(min_size=3, max_size=15)

        mock_from_env.assert_called_once()
        call_kwargs = mock_pool_class.call_args[1]
        assert call_kwargs["min_size"] == 3
        assert call_kwargs["max_size"] == 15

    @patch("pycopg.pool.ConnectionPool")
    @patch("pycopg.pool.Config.from_url")
    def test_from_url(self, mock_from_url, mock_pool_class):
        """Test creating from URL."""
        mock_from_url.return_value = Config()

        db = PooledDatabase.from_url(
            "postgresql://user:pass@host/db",
            min_size=4,
            max_size=16,
        )

        mock_from_url.assert_called_once_with("postgresql://user:pass@host/db")
        call_kwargs = mock_pool_class.call_args[1]
        assert call_kwargs["min_size"] == 4
        assert call_kwargs["max_size"] == 16

    @patch("pycopg.pool.ConnectionPool")
    def test_connection_context(self, mock_pool_class, config):
        """Test connection context manager."""
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_pool_class.return_value = mock_pool

        db = PooledDatabase(config)

        with db.connection() as conn:
            assert conn == mock_conn

    @patch("pycopg.pool.ConnectionPool")
    def test_execute(self, mock_pool_class, config):
        """Test execute method."""
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("col1",), ("col2",)]
        mock_cursor.fetchall.return_value = [{"col1": 1, "col2": 2}]

        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor

        mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_pool_class.return_value = mock_pool

        db = PooledDatabase(config)
        result = db.execute("SELECT * FROM test")

        assert result == [{"col1": 1, "col2": 2}]
        mock_cursor.execute.assert_called_once_with("SELECT * FROM test", None)

    @patch("pycopg.pool.ConnectionPool")
    def test_execute_with_params(self, mock_pool_class, config):
        """Test execute with parameters."""
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",)]
        mock_cursor.fetchall.return_value = [{"id": 1}]

        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor

        mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_pool_class.return_value = mock_pool

        db = PooledDatabase(config)
        result = db.execute("SELECT * FROM test WHERE id = %s", [1])

        mock_cursor.execute.assert_called_once_with("SELECT * FROM test WHERE id = %s", [1])

    @patch("pycopg.pool.ConnectionPool")
    def test_execute_no_result(self, mock_pool_class, config):
        """Test execute with no result (INSERT/UPDATE)."""
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = None  # No result

        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor

        mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_pool_class.return_value = mock_pool

        db = PooledDatabase(config)
        result = db.execute("INSERT INTO test VALUES (1)")

        assert result == []
        mock_conn.commit.assert_called_once()

    @patch("pycopg.pool.ConnectionPool")
    def test_execute_many(self, mock_pool_class, config):
        """Test execute_many method."""
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1

        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor

        mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
        mock_pool_class.return_value = mock_pool

        db = PooledDatabase(config)
        result = db.execute_many(
            "INSERT INTO test (name) VALUES (%s)",
            [("Alice",), ("Bob",), ("Charlie",)],
        )

        assert result == 3
        assert mock_cursor.execute.call_count == 3
        mock_conn.commit.assert_called_once()

    @patch("pycopg.pool.ConnectionPool")
    def test_stats(self, mock_pool_class, config):
        """Test stats property."""
        mock_pool = MagicMock()
        mock_pool.min_size = 2
        mock_pool.max_size = 10
        mock_pool.get_stats.return_value = {
            "pool_size": 5,
            "pool_available": 3,
            "requests_waiting": 0,
            "requests_num": 100,
        }
        mock_pool_class.return_value = mock_pool

        db = PooledDatabase(config)
        stats = db.stats

        assert stats["pool_min"] == 2
        assert stats["pool_max"] == 10
        assert stats["pool_size"] == 5
        assert stats["pool_available"] == 3

    @patch("pycopg.pool.ConnectionPool")
    def test_resize(self, mock_pool_class, config):
        """Test resize method."""
        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        db = PooledDatabase(config)
        db.resize(min_size=10, max_size=50)

        mock_pool.resize.assert_called_once_with(min_size=10, max_size=50)

    @patch("pycopg.pool.ConnectionPool")
    def test_check(self, mock_pool_class, config):
        """Test check method."""
        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        db = PooledDatabase(config)
        db.check()

        mock_pool.check.assert_called_once()

    @patch("pycopg.pool.ConnectionPool")
    def test_wait(self, mock_pool_class, config):
        """Test wait method."""
        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        db = PooledDatabase(config)
        db.wait(timeout=60.0)

        mock_pool.wait.assert_called_once_with(timeout=60.0)

    @patch("pycopg.pool.ConnectionPool")
    def test_close(self, mock_pool_class, config):
        """Test close method."""
        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        db = PooledDatabase(config)
        db.close()

        mock_pool.close.assert_called_once()

    @patch("pycopg.pool.ConnectionPool")
    def test_context_manager(self, mock_pool_class, config):
        """Test context manager protocol."""
        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        with PooledDatabase(config) as db:
            assert db is not None

        mock_pool.close.assert_called_once()

    @patch("pycopg.pool.ConnectionPool")
    def test_repr(self, mock_pool_class, config):
        """Test string representation."""
        mock_pool = MagicMock()
        mock_pool.max_size = 10
        mock_pool.get_stats.return_value = {"pool_size": 5}
        mock_pool_class.return_value = mock_pool

        db = PooledDatabase(config)
        repr_str = repr(db)

        assert "PooledDatabase" in repr_str
        assert "testdb" in repr_str
        assert "5/10" in repr_str


class TestAsyncPooledDatabase:
    """Tests for AsyncPooledDatabase class."""

    @patch("pycopg.pool.AsyncConnectionPool")
    def test_init(self, mock_pool_class, config):
        """Test initialization creates async pool."""
        db = AsyncPooledDatabase(config, min_size=5, max_size=20)

        mock_pool_class.assert_called_once()
        call_kwargs = mock_pool_class.call_args[1]
        assert call_kwargs["min_size"] == 5
        assert call_kwargs["max_size"] == 20
        assert call_kwargs["open"] is False

    @patch("pycopg.pool.AsyncConnectionPool")
    @patch("pycopg.pool.Config.from_env")
    def test_from_env(self, mock_from_env, mock_pool_class):
        """Test creating from environment."""
        mock_from_env.return_value = Config()

        db = AsyncPooledDatabase.from_env(min_size=3, max_size=15)

        mock_from_env.assert_called_once()

    @patch("pycopg.pool.AsyncConnectionPool")
    @patch("pycopg.pool.Config.from_url")
    def test_from_url(self, mock_from_url, mock_pool_class):
        """Test creating from URL."""
        mock_from_url.return_value = Config()

        db = AsyncPooledDatabase.from_url(
            "postgresql://user:pass@host/db",
            min_size=4,
            max_size=16,
        )

        mock_from_url.assert_called_once_with("postgresql://user:pass@host/db")

    @patch("pycopg.pool.AsyncConnectionPool")
    def test_stats(self, mock_pool_class, config):
        """Test stats property."""
        mock_pool = MagicMock()
        mock_pool.min_size = 2
        mock_pool.max_size = 10
        mock_pool.get_stats.return_value = {
            "pool_size": 5,
            "pool_available": 3,
            "requests_waiting": 0,
        }
        mock_pool_class.return_value = mock_pool

        db = AsyncPooledDatabase(config)
        stats = db.stats

        assert stats["pool_min"] == 2
        assert stats["pool_max"] == 10
        assert stats["pool_size"] == 5

    @patch("pycopg.pool.AsyncConnectionPool")
    def test_resize(self, mock_pool_class, config):
        """Test resize method."""
        mock_pool = MagicMock()
        mock_pool_class.return_value = mock_pool

        db = AsyncPooledDatabase(config)
        db.resize(min_size=10, max_size=50)

        mock_pool.resize.assert_called_once_with(min_size=10, max_size=50)

    @patch("pycopg.pool.AsyncConnectionPool")
    def test_repr(self, mock_pool_class, config):
        """Test string representation."""
        mock_pool = MagicMock()
        mock_pool.max_size = 10
        mock_pool.get_stats.return_value = {"pool_size": 5}
        mock_pool_class.return_value = mock_pool

        db = AsyncPooledDatabase(config)
        repr_str = repr(db)

        assert "AsyncPooledDatabase" in repr_str
        assert "testdb" in repr_str


@pytest.mark.asyncio
class TestAsyncPooledDatabaseAsync:
    """Async tests for AsyncPooledDatabase."""

    @patch("pycopg.pool.AsyncConnectionPool")
    async def test_open(self, mock_pool_class, config):
        """Test open method."""
        mock_pool = MagicMock()
        mock_pool.open = AsyncMock()
        mock_pool.wait = AsyncMock()
        mock_pool_class.return_value = mock_pool

        db = AsyncPooledDatabase(config)
        await db.open()

        mock_pool.open.assert_called_once()
        mock_pool.wait.assert_called_once()

    @patch("pycopg.pool.AsyncConnectionPool")
    async def test_close(self, mock_pool_class, config):
        """Test close method."""
        mock_pool = MagicMock()
        mock_pool.close = AsyncMock()
        mock_pool_class.return_value = mock_pool

        db = AsyncPooledDatabase(config)
        await db.close()

        mock_pool.close.assert_called_once()

    @patch("pycopg.pool.AsyncConnectionPool")
    async def test_check(self, mock_pool_class, config):
        """Test check method."""
        mock_pool = MagicMock()
        mock_pool.check = AsyncMock()
        mock_pool_class.return_value = mock_pool

        db = AsyncPooledDatabase(config)
        await db.check()

        mock_pool.check.assert_called_once()

    @patch("pycopg.pool.AsyncConnectionPool")
    async def test_context_manager(self, mock_pool_class, config):
        """Test async context manager."""
        mock_pool = MagicMock()
        mock_pool.open = AsyncMock()
        mock_pool.wait = AsyncMock()
        mock_pool.close = AsyncMock()
        mock_pool_class.return_value = mock_pool

        async with AsyncPooledDatabase(config) as db:
            assert db is not None

        mock_pool.open.assert_called_once()
        mock_pool.close.assert_called_once()
