"""
Connection Pool for pycopg.

Provides sync and async connection pools using psycopg_pool.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator, Callable, Iterator, Sequence
from contextlib import asynccontextmanager, contextmanager
from types import TracebackType
from typing import TYPE_CHECKING, Any

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool, ConnectionPool

from pycopg.base import Params, _decode_server_version
from pycopg.config import Config
from pycopg.logging import log_operation

if TYPE_CHECKING:
    import psycopg


class PooledDatabase:
    """Database with connection pooling.

    Uses psycopg_pool for efficient connection management.
    Ideal for web applications and services with many concurrent requests.
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
        reconnect_failed: Callable[..., Any] | None = None,
        check: Callable[..., Any] | None = None,
    ):
        """Initialize connection pool.

        Parameters
        ----------
        config : Config
            Database configuration.
        min_size : int, optional
            Minimum connections to keep open, by default 2.
        max_size : int, optional
            Maximum connections allowed, by default 10.
        max_idle : float, optional
            Close idle connections after this many seconds, by default 300.0.
        max_lifetime : float, optional
            Close connections after this many seconds, by default 3600.0.
        timeout : float, optional
            Wait timeout for getting a connection, by default 30.0.
        num_workers : int, optional
            Background workers for pool management, by default 3.
        reconnect_timeout : float, optional
            Time in seconds to keep retrying reconnection, by default 300.0.
        reconnect_failed : callable, optional
            Callback on prolonged reconnection failure.
        check : callable, optional
            Health check callback for connections.
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
            open=True,
        )

    @classmethod
    def from_env(
        cls,
        dotenv_path: str | None = None,
        min_size: int = 2,
        max_size: int = 10,
        **kwargs: Any,
    ) -> PooledDatabase:
        """Create PooledDatabase from environment variables.

        Parameters
        ----------
        dotenv_path : str, optional
            Path to .env file.
        min_size : int, optional
            Minimum pool size, by default 2.
        max_size : int, optional
            Maximum pool size, by default 10.
        **kwargs
            Additional pool options.

        Returns
        -------
        PooledDatabase
            PooledDatabase instance.
        """
        return cls(
            Config.from_env(dotenv_path), min_size=min_size, max_size=max_size, **kwargs
        )

    @classmethod
    def from_url(
        cls,
        url: str,
        min_size: int = 2,
        max_size: int = 10,
        **kwargs: Any,
    ) -> PooledDatabase:
        """Create PooledDatabase from connection URL.

        Parameters
        ----------
        url : str
            PostgreSQL connection URL.
        min_size : int, optional
            Minimum pool size, by default 2.
        max_size : int, optional
            Maximum pool size, by default 10.
        **kwargs
            Additional pool options.

        Returns
        -------
        PooledDatabase
            PooledDatabase instance.
        """
        return cls(Config.from_url(url), min_size=min_size, max_size=max_size, **kwargs)

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        """Get a connection from the pool.

        Yields
        ------
        psycopg.Connection
            Connection object.
        """
        with self._pool.connection() as conn:
            yield conn

    def execute(self, sql: str, params: Params = None) -> list[dict[str, Any]]:
        """Execute SQL and return results.

        Parameters
        ----------
        sql : str
            SQL query.
        params : Params, optional
            Query parameters.

        Returns
        -------
        list of dict
            List of result rows as dicts.
        """
        with self.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(sql, params)
                rows = cur.fetchall() if cur.description else []
                conn.commit()
                return rows

    def execute_many(self, sql: str, params_seq: Sequence[Sequence[Any]]) -> int:
        """Execute SQL for multiple parameter sets.

        Parameters
        ----------
        sql : str
            SQL query.
        params_seq : sequence of sequences
            Sequence of parameter sequences.

        Returns
        -------
        int
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
    def stats(self) -> dict[str, Any]:
        """Get pool statistics.

        Returns
        -------
        dict
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

    def health(self) -> dict[str, Any]:
        """Return a health-check dict for this pooled database connection.

        Acquires a connection from the pool, executes ``SELECT 1``, and
        measures the round-trip latency.  The method **never raises** — on
        any failure it returns a dict with ``connected=False`` and the
        exception message in the ``error`` key.  The ``pool_stats`` key
        provides a snapshot of pool metrics sourced from :attr:`stats`.

        Returns
        -------
        dict
            On success::

                {
                    "connected": True,
                    "latency_ms": <float>,
                    "server_version": "<str>",
                    "pool_stats": <dict>,
                }

            On failure::

                {
                    "connected": False,
                    "latency_ms": None,
                    "server_version": None,
                    "error": "<exception message>",
                    "pool_stats": None,
                }

        Notes
        -----
        Wrapped in ``log_operation("database.health")`` (D-09).  The
        ``error`` string is the raw psycopg exception message — credentials
        are never appended (T-45-07).

        Examples
        --------
        >>> status = pool_db.health()
        >>> status["connected"]
        True
        >>> "pool_stats" in status
        True
        """
        with log_operation("database.health"):
            try:
                t0 = time.perf_counter()
                with self.connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT 1")
                    server_ver_int = conn.info.server_version
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                return {
                    "connected": True,
                    "latency_ms": latency_ms,
                    "server_version": _decode_server_version(server_ver_int),
                    "pool_stats": self.stats,
                }
            except Exception as exc:
                return {
                    "connected": False,
                    "latency_ms": None,
                    "server_version": None,
                    "error": str(exc),
                    "pool_stats": None,
                }

    def resize(self, min_size: int, max_size: int) -> None:
        """Resize the pool.

        Parameters
        ----------
        min_size : int
            New minimum size.
        max_size : int
            New maximum size.
        """
        self._pool.resize(min_size=min_size, max_size=max_size)

    def check(self) -> None:
        """Check pool health and recover broken connections."""
        self._pool.check()

    def wait(self, timeout: float = 30.0) -> None:
        """Wait for pool to be ready.

        Parameters
        ----------
        timeout : float, optional
            Maximum wait time in seconds, by default 30.0.
        """
        self._pool.wait(timeout=timeout)

    def close(self) -> None:
        """Close the pool and all connections."""
        self._pool.close()

    def __enter__(self) -> PooledDatabase:
        """Enter the context manager, returning self."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the context manager and close the pool."""
        self.close()

    def __repr__(self) -> str:
        """Return string representation of the PooledDatabase instance."""
        stats = self._pool.get_stats()
        return (
            f"PooledDatabase({self.config.database!r}, "
            f"size={stats.get('pool_size', 0)}/{self._pool.max_size})"
        )


class AsyncPooledDatabase:
    """Async database with connection pooling.

    Uses psycopg_pool.AsyncConnectionPool for async applications.
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
        reconnect_failed: Callable[..., Any] | None = None,
        check: Callable[..., Any] | None = None,
    ):
        """Initialize async connection pool.

        Parameters
        ----------
        config : Config
            Database configuration.
        min_size : int, optional
            Minimum connections to keep open, by default 2.
        max_size : int, optional
            Maximum connections allowed, by default 10.
        max_idle : float, optional
            Close idle connections after this many seconds, by default 300.0.
        max_lifetime : float, optional
            Close connections after this many seconds, by default 3600.0.
        timeout : float, optional
            Wait timeout for getting a connection, by default 30.0.
        num_workers : int, optional
            Background workers for pool management, by default 3.
        reconnect_timeout : float, optional
            Time in seconds to keep retrying reconnection, by default 300.0.
        reconnect_failed : callable, optional
            Callback on prolonged reconnection failure.
        check : callable, optional
            Health check callback for connections.
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
        dotenv_path: str | None = None,
        min_size: int = 2,
        max_size: int = 10,
        **kwargs: Any,
    ) -> AsyncPooledDatabase:
        """Create AsyncPooledDatabase from environment variables."""
        return cls(
            Config.from_env(dotenv_path), min_size=min_size, max_size=max_size, **kwargs
        )

    @classmethod
    def from_url(
        cls,
        url: str,
        min_size: int = 2,
        max_size: int = 10,
        **kwargs: Any,
    ) -> AsyncPooledDatabase:
        """Create AsyncPooledDatabase from connection URL."""
        return cls(Config.from_url(url), min_size=min_size, max_size=max_size, **kwargs)

    async def open(self) -> None:
        """Open the pool and wait for it to be ready."""
        await self._pool.open()
        await self._pool.wait()

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[psycopg.AsyncConnection]:
        """Get a connection from the pool.

        Yields
        ------
        psycopg.AsyncConnection
            AsyncConnection object.
        """
        async with self._pool.connection() as conn:
            yield conn

    async def execute(self, sql: str, params: Params = None) -> list[dict[str, Any]]:
        """Execute SQL and return results.

        Parameters
        ----------
        sql : str
            SQL query.
        params : Params, optional
            Query parameters.

        Returns
        -------
        list of dict
            List of result rows as dicts.
        """
        async with self.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall() if cur.description else []
                await conn.commit()
                return rows

    async def execute_many(self, sql: str, params_seq: Sequence[Sequence[Any]]) -> int:
        """Execute SQL for multiple parameter sets."""
        total = 0
        async with self.connection() as conn:
            async with conn.cursor() as cur:
                for params in params_seq:
                    await cur.execute(sql, params)
                    total += cur.rowcount
                await conn.commit()
        return total

    async def fetch_one(self, sql: str, params: Params = None) -> dict[str, Any] | None:
        """Fetch single row."""
        async with self.connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                return await cur.fetchone()

    async def fetch_val(self, sql: str, params: Params = None) -> Any:
        """Fetch single value."""
        row = await self.fetch_one(sql, params)
        if row:
            return list(row.values())[0]
        return None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[psycopg.AsyncConnection]:
        """Context manager for transactions.

        Commits on success, rolls back on exception.
        """
        async with self.connection() as conn:
            async with conn.transaction():
                yield conn

    @property
    def stats(self) -> dict[str, Any]:
        """Get pool statistics."""
        return {
            "pool_min": self._pool.min_size,
            "pool_max": self._pool.max_size,
            "pool_size": self._pool.get_stats().get("pool_size", 0),
            "pool_available": self._pool.get_stats().get("pool_available", 0),
            "requests_waiting": self._pool.get_stats().get("requests_waiting", 0),
        }

    async def health(self) -> dict[str, Any]:
        """Return a health-check dict for this async pooled database connection.

        Acquires a connection from the pool, executes ``SELECT 1``, and
        measures the round-trip latency.  The method **never raises** — on
        any failure it returns a dict with ``connected=False`` and the
        exception message in the ``error`` key.  The ``pool_stats`` key
        provides a snapshot of pool metrics sourced from :attr:`stats`.

        Returns
        -------
        dict
            On success::

                {
                    "connected": True,
                    "latency_ms": <float>,
                    "server_version": "<str>",
                    "pool_stats": <dict>,
                }

            On failure::

                {
                    "connected": False,
                    "latency_ms": None,
                    "server_version": None,
                    "error": "<exception message>",
                    "pool_stats": None,
                }

        Notes
        -----
        Wrapped in ``log_operation("database.health")`` (D-09).  The
        ``error`` string is the raw psycopg exception message — credentials
        are never appended (T-45-07).

        Examples
        --------
        >>> status = await async_pool_db.health()
        >>> status["connected"]
        True
        >>> "pool_stats" in status
        True
        """
        with log_operation("database.health"):
            try:
                t0 = time.perf_counter()
                async with self.connection() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT 1")
                    server_ver_int = conn.info.server_version
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                return {
                    "connected": True,
                    "latency_ms": latency_ms,
                    "server_version": _decode_server_version(server_ver_int),
                    "pool_stats": self.stats,
                }
            except Exception as exc:
                return {
                    "connected": False,
                    "latency_ms": None,
                    "server_version": None,
                    "error": str(exc),
                    "pool_stats": None,
                }

    async def resize(self, min_size: int, max_size: int) -> None:
        """Resize the pool."""
        await self._pool.resize(min_size=min_size, max_size=max_size)

    async def check(self) -> None:
        """Check pool health."""
        await self._pool.check()

    async def close(self) -> None:
        """Close the pool."""
        await self._pool.close()

    async def __aenter__(self) -> AsyncPooledDatabase:
        """Enter the async context manager, opening the pool and returning self."""
        await self.open()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager and close the pool."""
        await self.close()

    def __repr__(self) -> str:
        """Return string representation of the AsyncPooledDatabase instance."""
        stats = self._pool.get_stats()
        return (
            f"AsyncPooledDatabase({self.config.database!r}, "
            f"size={stats.get('pool_size', 0)}/{self._pool.max_size})"
        )
