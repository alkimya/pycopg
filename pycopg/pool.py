"""
Connection Pool for pycopg.

Provides sync and async connection pools using psycopg_pool.
"""

from __future__ import annotations

import re
from contextlib import contextmanager, asynccontextmanager
from typing import TYPE_CHECKING, Any, Callable, Iterator, AsyncIterator, Optional, Sequence

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, AsyncConnectionPool

from pycopg.config import Config

if TYPE_CHECKING:
    import psycopg


class PooledDatabase:
    """Database with connection pooling.

    Uses psycopg_pool for efficient connection management.
    Ideal for web applications and services with many concurrent requests.

    Example:
        # Create pool
        db = PooledDatabase.from_env(min_size=5, max_size=20)

        # Use connections from pool
        with db.connection() as conn:
            result = conn.execute("SELECT * FROM users")

        # Or use the simplified API
        users = db.execute("SELECT * FROM users WHERE active = %s", [True])

        # Close pool when done
        db.close()
    """

    def __init__(
        self,
        config: Config,
        min_size: int = 2,
        max_size: int = 10,
        max_idle: float = 300.0,
        max_lifetime: float = 3600.0,
        timeout: float = 30.0,
        num_workers: int = 3,
        reconnect_timeout: float = 300.0,
        reconnect_failed: Optional[Callable] = None,
        check: Optional[Callable] = None,
    ):
        """Initialize connection pool.

        Args:
            config: Database configuration.
            min_size: Minimum connections to keep open.
            max_size: Maximum connections allowed.
            max_idle: Close idle connections after this many seconds.
            max_lifetime: Close connections after this many seconds.
            timeout: Wait timeout for getting a connection.
            num_workers: Background workers for pool management.
            reconnect_timeout: Time in seconds to keep retrying reconnection (default 300s).
            reconnect_failed: Callback on prolonged reconnection failure.
            check: Health check callback for connections.
        """
        self.config = config
        self._pool = ConnectionPool(
            conninfo=config.dsn,
            min_size=min_size,
            max_size=max_size,
            max_idle=max_idle,
            max_lifetime=max_lifetime,
            timeout=timeout,
            num_workers=num_workers,
            reconnect_timeout=reconnect_timeout,
            reconnect_failed=reconnect_failed,
            check=check or ConnectionPool.check_connection,
            kwargs={"row_factory": dict_row},
        )

    @classmethod
    def from_env(
        cls,
        dotenv_path: Optional[str] = None,
        min_size: int = 2,
        max_size: int = 10,
        **kwargs,
    ) -> "PooledDatabase":
        """Create PooledDatabase from environment variables.

        Args:
            dotenv_path: Optional path to .env file.
            min_size: Minimum pool size.
            max_size: Maximum pool size.
            **kwargs: Additional pool options.

        Returns:
            PooledDatabase instance.
        """
        return cls(Config.from_env(dotenv_path), min_size=min_size, max_size=max_size, **kwargs)

    @classmethod
    def from_url(
        cls,
        url: str,
        min_size: int = 2,
        max_size: int = 10,
        **kwargs,
    ) -> "PooledDatabase":
        """Create PooledDatabase from connection URL.

        Args:
            url: PostgreSQL connection URL.
            min_size: Minimum pool size.
            max_size: Maximum pool size.
            **kwargs: Additional pool options.

        Returns:
            PooledDatabase instance.
        """
        return cls(Config.from_url(url), min_size=min_size, max_size=max_size, **kwargs)

    @contextmanager
    def connection(self) -> Iterator["psycopg.Connection"]:
        """Get a connection from the pool.

        Yields:
            Connection object.

        Example:
            with db.connection() as conn:
                conn.execute("INSERT INTO users (name) VALUES (%s)", ["Alice"])
                conn.commit()
        """
        with self._pool.connection() as conn:
            yield conn

    def execute(self, sql: str, params: Optional[Sequence] = None) -> list[dict]:
        """Execute SQL and return results.

        Args:
            sql: SQL query.
            params: Query parameters.

        Returns:
            List of result rows as dicts.
        """
        with self.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                if cur.description:
                    return cur.fetchall()
                conn.commit()
                return []

    def execute_many(self, sql: str, params_seq: Sequence[Sequence]) -> int:
        """Execute SQL for multiple parameter sets.

        Args:
            sql: SQL query.
            params_seq: Sequence of parameter sequences.

        Returns:
            Total affected rows.
        """
        total = 0
        with self.connection() as conn:
            with conn.cursor() as cur:
                for params in params_seq:
                    cur.execute(sql, params)
                    total += cur.rowcount
            conn.commit()
        return total

    @property
    def stats(self) -> dict:
        """Get pool statistics.

        Returns:
            Dict with pool_size, pool_available, requests_waiting, etc.
        """
        return {
            "pool_min": self._pool.min_size,
            "pool_max": self._pool.max_size,
            "pool_size": self._pool.get_stats().get("pool_size", 0),
            "pool_available": self._pool.get_stats().get("pool_available", 0),
            "requests_waiting": self._pool.get_stats().get("requests_waiting", 0),
            "requests_num": self._pool.get_stats().get("requests_num", 0),
        }

    def resize(self, min_size: int, max_size: int) -> None:
        """Resize the pool.

        Args:
            min_size: New minimum size.
            max_size: New maximum size.
        """
        self._pool.resize(min_size=min_size, max_size=max_size)

    def check(self) -> None:
        """Check pool health and recover broken connections."""
        self._pool.check()

    def wait(self, timeout: float = 30.0) -> None:
        """Wait for pool to be ready.

        Args:
            timeout: Maximum wait time in seconds.
        """
        self._pool.wait(timeout=timeout)

    def close(self) -> None:
        """Close the pool and all connections."""
        self._pool.close()

    def __enter__(self) -> "PooledDatabase":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __repr__(self) -> str:
        stats = self._pool.get_stats()
        return (
            f"PooledDatabase({self.config.database!r}, "
            f"size={stats.get('pool_size', 0)}/{self._pool.max_size})"
        )


class AsyncPooledDatabase:
    """Async database with connection pooling.

    Uses psycopg_pool.AsyncConnectionPool for async applications.

    Example:
        # Create pool
        db = AsyncPooledDatabase.from_env(min_size=5, max_size=20)

        # Wait for pool to be ready
        await db.open()

        # Use connections
        async with db.connection() as conn:
            await conn.execute("SELECT * FROM users")

        # Or use simplified API
        users = await db.execute("SELECT * FROM users")

        # Close when done
        await db.close()
    """

    def __init__(
        self,
        config: Config,
        min_size: int = 2,
        max_size: int = 10,
        max_idle: float = 300.0,
        max_lifetime: float = 3600.0,
        timeout: float = 30.0,
        num_workers: int = 3,
        reconnect_timeout: float = 300.0,
        reconnect_failed: Optional[Callable] = None,
        check: Optional[Callable] = None,
    ):
        """Initialize async connection pool.

        Args:
            config: Database configuration.
            min_size: Minimum connections to keep open.
            max_size: Maximum connections allowed.
            max_idle: Close idle connections after this many seconds.
            max_lifetime: Close connections after this many seconds.
            timeout: Wait timeout for getting a connection.
            num_workers: Background workers for pool management.
            reconnect_timeout: Time in seconds to keep retrying reconnection (default 300s).
            reconnect_failed: Callback on prolonged reconnection failure.
            check: Health check callback for connections.
        """
        self.config = config
        self._pool = AsyncConnectionPool(
            conninfo=config.dsn,
            min_size=min_size,
            max_size=max_size,
            max_idle=max_idle,
            max_lifetime=max_lifetime,
            timeout=timeout,
            num_workers=num_workers,
            reconnect_timeout=reconnect_timeout,
            reconnect_failed=reconnect_failed,
            check=check or AsyncConnectionPool.check_connection,
            kwargs={"row_factory": dict_row},
            open=False,  # Don't open immediately, use open() method
        )

    @classmethod
    def from_env(
        cls,
        dotenv_path: Optional[str] = None,
        min_size: int = 2,
        max_size: int = 10,
        **kwargs,
    ) -> "AsyncPooledDatabase":
        """Create AsyncPooledDatabase from environment variables."""
        return cls(Config.from_env(dotenv_path), min_size=min_size, max_size=max_size, **kwargs)

    @classmethod
    def from_url(
        cls,
        url: str,
        min_size: int = 2,
        max_size: int = 10,
        **kwargs,
    ) -> "AsyncPooledDatabase":
        """Create AsyncPooledDatabase from connection URL."""
        return cls(Config.from_url(url), min_size=min_size, max_size=max_size, **kwargs)

    async def open(self) -> None:
        """Open the pool and wait for it to be ready."""
        await self._pool.open()
        await self._pool.wait()

    @asynccontextmanager
    async def connection(self) -> AsyncIterator["psycopg.AsyncConnection"]:
        """Get a connection from the pool.

        Yields:
            AsyncConnection object.

        Example:
            async with db.connection() as conn:
                await conn.execute("INSERT INTO users (name) VALUES (%s)", ["Alice"])
        """
        async with self._pool.connection() as conn:
            yield conn

    async def execute(self, sql: str, params: Optional[Sequence] = None) -> list[dict]:
        """Execute SQL and return results.

        Args:
            sql: SQL query.
            params: Query parameters.

        Returns:
            List of result rows as dicts.
        """
        async with self.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                if cur.description:
                    return await cur.fetchall()
                await conn.commit()
                return []

    async def execute_many(self, sql: str, params_seq: Sequence[Sequence]) -> int:
        """Execute SQL for multiple parameter sets."""
        total = 0
        async with self.connection() as conn:
            async with conn.cursor() as cur:
                for params in params_seq:
                    await cur.execute(sql, params)
                    total += cur.rowcount
            await conn.commit()
        return total

    async def fetch_one(self, sql: str, params: Optional[Sequence] = None) -> Optional[dict]:
        """Fetch single row."""
        async with self.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                return await cur.fetchone()

    async def fetch_val(self, sql: str, params: Optional[Sequence] = None) -> Any:
        """Fetch single value."""
        row = await self.fetch_one(sql, params)
        if row:
            return list(row.values())[0]
        return None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator["psycopg.AsyncConnection"]:
        """Context manager for transactions.

        Commits on success, rolls back on exception.

        Example:
            async with db.transaction() as conn:
                await conn.execute("INSERT INTO users (name) VALUES (%s)", ["Alice"])
                await conn.execute("UPDATE stats SET count = count + 1")
        """
        async with self.connection() as conn:
            async with conn.transaction():
                yield conn

    @property
    def stats(self) -> dict:
        """Get pool statistics."""
        return {
            "pool_min": self._pool.min_size,
            "pool_max": self._pool.max_size,
            "pool_size": self._pool.get_stats().get("pool_size", 0),
            "pool_available": self._pool.get_stats().get("pool_available", 0),
            "requests_waiting": self._pool.get_stats().get("requests_waiting", 0),
        }

    def resize(self, min_size: int, max_size: int) -> None:
        """Resize the pool."""
        self._pool.resize(min_size=min_size, max_size=max_size)

    async def check(self) -> None:
        """Check pool health."""
        await self._pool.check()

    async def close(self) -> None:
        """Close the pool."""
        await self._pool.close()

    async def __aenter__(self) -> "AsyncPooledDatabase":
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    def __repr__(self) -> str:
        stats = self._pool.get_stats()
        return (
            f"AsyncPooledDatabase({self.config.database!r}, "
            f"size={stats.get('pool_size', 0)}/{self._pool.max_size})"
        )
