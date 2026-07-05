"""
Async Database class for pycopg.

Provides async/await interface for PostgreSQL operations using psycopg's async support.
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Hashable, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from types import TracebackType
from typing import TYPE_CHECKING, Any, Literal, cast

import psycopg
from psycopg import AsyncConnection, AsyncCursor, IsolationLevel, OperationalError
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from pycopg import queries
from pycopg.base import (
    DatabaseBase,
    Params,
    QueryMixin,
    _decode_server_version,
)
from pycopg.config import Config
from pycopg.database import Page
from pycopg.exceptions import DatabaseExistsError, ExtensionNotAvailableError
from pycopg.logging import log_operation
from pycopg.utils import (
    validate_identifier,
    validate_identifiers,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import geopandas as gpd
    import pandas as pd
    from sqlalchemy.ext.asyncio import AsyncEngine

    from pycopg.admin import AsyncAdminAccessor
    from pycopg.backup import AsyncBackupAccessor
    from pycopg.etl import AsyncETLAccessor
    from pycopg.maint import AsyncMaintAccessor
    from pycopg.schema import AsyncSchemaAccessor
    from pycopg.spatial import AsyncSpatialAccessor
    from pycopg.timescale import AsyncTimescaleAccessor


async def _async_stream_df_copy(
    cur: psycopg.AsyncCursor[Any],
    df: pd.DataFrame,
    table: str,
    schema: str,
    columns: list[str],
) -> int:
    """Stream DataFrame rows into ``COPY … FROM STDIN`` on the provided async cursor.

    Async mirror of :func:`pycopg.database._stream_df_copy`.  Uses
    ``async with cur.copy(...)`` and ``await copy.write_row(...)`` for the
    psycopg AsyncCopy protocol.

    Converts NaN/NaT/pd.NA/None to SQL NULL per-value using a pre-computed
    boolean mask (``df.isna().values``).  Row values are read from
    ``df.to_numpy(dtype=object)`` (object array) which preserves
    ``pandas.Timestamp``, ``numpy.int64``, and other per-column Python types
    without a full-frame type conversion.  Using ``df.values`` instead would
    silently upcast integer columns to ``float64`` when any column in the
    DataFrame contains NaN (numpy uniform-array constraint).

    The caller is fully responsible for the connection lifecycle: this helper
    never opens a connection and never calls ``await conn.commit()``.  It DOES
    validate ``table``, ``schema`` and every column via ``validate_identifiers``
    before interpolating them into the COPY statement (builder-pur invariant),
    exactly like ``copy_insert``.  Centralising validation here guarantees every
    COPY caller — ``from_dataframe`` and the async ETL ``append``/``replace``
    seam — gets identifier validation in one place (38-REVIEW CR-01/CR-02).

    .. note::
       Do NOT call the sync ``_stream_df_copy`` from an async context — the
       sync context manager blocks the event loop.

    Parameters
    ----------
    cur : psycopg.AsyncCursor
        An open psycopg async cursor.  May be a plain cursor or a
        transaction cursor (e.g. from the async ETL seam).  Provided by
        the caller; this helper does not acquire a connection.
    df : pandas.DataFrame
        Source data.  Must already have its index promoted to columns if
        ``index=True`` was requested (i.e. pass ``df_ddl = df.reset_index()``
        before calling).
    table : str
        Target table name (already validated by the caller).
    schema : str
        Target schema name (already validated by the caller).
    columns : list of str
        Ordered list of column names that matches the DDL column order.
        Must be derived from ``df.columns`` (after any ``reset_index``).

    Returns
    -------
    int
        Number of rows written (``cur.rowcount`` read after the COPY block
        closes — reading it inside the block returns 0 or -1 on some
        psycopg versions).
    """
    if df.empty:
        return 0

    # Builder-pur: validate every identifier before it is interpolated into the
    # COPY statement (matches copy_insert). Restores the validation the old ETL
    # append/replace paths inherited from _build_insert_sql (38-REVIEW CR-01/CR-02).
    validate_identifiers(table, schema, *columns)

    cols_str = ", ".join(columns)
    null_mask = df.isna().values  # shape (n_rows, n_cols) — pre-computed once
    # to_numpy(dtype=object) forces an object array so each element retains its
    # Python / pandas type (int stays int, not float64 when mixed with NaN cols).
    # df.values would silently upcast int64 columns to float64 whenever any other
    # column contains NaN (numpy uniform-array constraint).
    row_values = df.to_numpy(dtype=object)

    async with cur.copy(f"COPY {schema}.{table} ({cols_str}) FROM STDIN") as copy:
        for i, row in enumerate(row_values):
            null_row = null_mask[i]
            await copy.write_row(
                [None if null_row[j] else row[j] for j in range(len(row))]
            )

    return cur.rowcount


class AsyncDatabase(DatabaseBase, QueryMixin):
    """Async PostgreSQL interface.

    Provides async/await versions of Database methods using psycopg's AsyncConnection.

    Attributes
    ----------
    config : Config
        Database connection configuration.
    """

    def __init__(self, config: Config):
        """Initialize async database connection.

        Parameters
        ----------
        config : Config
            Database configuration.
        """
        super().__init__(config)
        self._session_conn: AsyncConnection | None = None
        self._async_engine: AsyncEngine | None = None
        self._spatial: AsyncSpatialAccessor | None = None
        self._etl: AsyncETLAccessor | None = None
        self._timescale: AsyncTimescaleAccessor | None = None
        self._admin: AsyncAdminAccessor | None = None
        self._maint: AsyncMaintAccessor | None = None
        self._backup: AsyncBackupAccessor | None = None
        self._schema: AsyncSchemaAccessor | None = None

    @property
    def async_engine(self) -> AsyncEngine:
        """Get or create async SQLAlchemy engine (lazy initialization)."""
        if self._async_engine is None:
            from sqlalchemy.ext.asyncio import create_async_engine

            self._async_engine = create_async_engine(self.config.async_url)
        return self._async_engine

    @property
    def spatial(self) -> AsyncSpatialAccessor:
        """Get or create the async spatial accessor (lazy initialization).

        The PostGIS guard is deferred to the first helper call (an async
        check cannot run inside a property).

        Returns
        -------
        AsyncSpatialAccessor
            Async spatial helper namespace bound to this database.
        """
        if self._spatial is None:
            from pycopg.spatial import AsyncSpatialAccessor

            self._spatial = AsyncSpatialAccessor(self)
        return self._spatial

    @property
    def etl(self) -> AsyncETLAccessor:
        """Get or create the async ETL run-tracking accessor (lazy initialization).

        The accessor is created on first access and cached for subsequent
        calls.  No PostGIS or extension guard is applied — ETL run-tracking
        is core functionality, not an extension (D-08).

        Returns
        -------
        AsyncETLAccessor
            Async ETL helper namespace bound to this database.
        """
        if self._etl is None:
            from pycopg.etl import AsyncETLAccessor

            self._etl = AsyncETLAccessor(self)
        return self._etl

    @property
    def timescale(self) -> AsyncTimescaleAccessor:
        """Get or create the async TimescaleDB accessor (lazy initialization).

        Provides async access to TimescaleDB operations such as hypertable
        management, compression, and retention policies.  The accessor
        is created on first access and cached for subsequent calls.

        Returns
        -------
        AsyncTimescaleAccessor
            Async TimescaleDB helper namespace bound to this database.
        """
        if self._timescale is None:
            from pycopg.timescale import AsyncTimescaleAccessor

            self._timescale = AsyncTimescaleAccessor(self)
        return self._timescale

    @property
    def admin(self) -> AsyncAdminAccessor:
        """Get or create the async admin accessor (lazy initialization).

        Provides async access to role and permission management operations.
        The accessor is created on first access and cached for subsequent
        calls.

        Returns
        -------
        AsyncAdminAccessor
            Async admin helper namespace bound to this database.
        """
        if self._admin is None:
            from pycopg.admin import AsyncAdminAccessor

            self._admin = AsyncAdminAccessor(self)
        return self._admin

    @property
    def maint(self) -> AsyncMaintAccessor:
        """Get or create the async maintenance accessor (lazy initialization).

        Provides async access to size, vacuum, analyze, and explain operations.
        The accessor is created on first access and cached for subsequent
        calls.

        Returns
        -------
        AsyncMaintAccessor
            Async maintenance helper namespace bound to this database.
        """
        if self._maint is None:
            from pycopg.maint import AsyncMaintAccessor

            self._maint = AsyncMaintAccessor(self)
        return self._maint

    @property
    def backup(self) -> AsyncBackupAccessor:
        """Get or create the async backup accessor (lazy initialization).

        Provides async access to pg_dump, pg_restore, and CSV copy operations.
        The accessor is created on first access and cached for subsequent
        calls.

        Returns
        -------
        AsyncBackupAccessor
            Async backup helper namespace bound to this database.
        """
        if self._backup is None:
            from pycopg.backup import AsyncBackupAccessor

            self._backup = AsyncBackupAccessor(self)
        return self._backup

    @property
    def schema(self) -> AsyncSchemaAccessor:
        """Get or create the async schema accessor (lazy initialization).

        Provides async access to DDL and introspection operations such as
        database, extension, schema, table, column, constraint, and index
        management.  The accessor is created on first access and cached for
        subsequent calls.

        Returns
        -------
        AsyncSchemaAccessor
            Async schema helper namespace bound to this database.
        """
        if self._schema is None:
            from pycopg.schema import AsyncSchemaAccessor

            self._schema = AsyncSchemaAccessor(self)
        return self._schema

    @classmethod
    async def create(
        cls,
        name: str,
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
        password: str = "",
        owner: str | None = None,
        template: str = "template1",
        if_not_exists: bool = True,
    ) -> AsyncDatabase:
        """Create a new database and return a connection to it.

        This is a convenience method that:
        1. Connects to the 'postgres' database
        2. Creates the new database
        3. Returns an AsyncDatabase instance connected to the new database

        Parameters
        ----------
        name : str
            Name of the database to create.
        host : str, optional
            Database host, by default "localhost".
        port : int, optional
            Database port, by default 5432.
        user : str, optional
            Database user, by default "postgres".
        password : str, optional
            Database password.
        owner : str, optional
            Owner role for the new database.
        template : str, optional
            Template database, by default "template1".
        if_not_exists : bool, optional
            If True, don't error if database already exists, by default True.

        Returns
        -------
        AsyncDatabase
            Instance connected to the newly created database.

        Raises
        ------
        DatabaseExistsError
            If the database already exists and if_not_exists is False.
        """
        # Create config for the admin connection (to postgres database)
        admin_config = Config(
            host=host,
            port=port,
            database="postgres",
            user=user,
            password=password,
        )

        # Validate identifiers
        validate_identifier(name)
        if owner:
            validate_identifier(owner)
        validate_identifier(template)

        # Check if database exists
        async with await psycopg.AsyncConnection.connect(
            **admin_config.connect_params(), autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(queries.DATABASE_EXISTS, (name,))
                exists = await cur.fetchone() is not None

                if exists:
                    if not if_not_exists:
                        raise DatabaseExistsError(f"Database '{name}' already exists")
                else:
                    # Create the database
                    owner_clause = f" OWNER {owner}" if owner else ""
                    await cur.execute(
                        f"CREATE DATABASE {name}{owner_clause} TEMPLATE {template}"
                    )

        # Return a connection to the new database
        new_config = Config(
            host=host,
            port=port,
            database=name,
            user=user,
            password=password,
        )
        return cls(new_config)

    @classmethod
    async def create_from_env(
        cls,
        name: str,
        owner: str | None = None,
        template: str = "template1",
        if_not_exists: bool = True,
        dotenv_path: str | Path | None = None,
    ) -> AsyncDatabase:
        """Create a new database using connection params from environment.

        Uses PGHOST, PGPORT, PGUSER, PGPASSWORD from environment or .env file,
        then creates the database and returns a connection to it.

        Parameters
        ----------
        name : str
            Name of the database to create.
        owner : str, optional
            Owner role for the new database.
        template : str, optional
            Template database, by default "template1".
        if_not_exists : bool, optional
            If True, don't error if database already exists, by default True.
        dotenv_path : str or Path, optional
            Path to .env file.

        Returns
        -------
        AsyncDatabase
            Instance connected to the newly created database.
        """
        # Load config from env (but we'll change the database later)
        env_config = Config.from_env(dotenv_path)

        return await cls.create(
            name=name,
            host=env_config.host,
            port=env_config.port,
            user=env_config.user,
            password=env_config.password,
            owner=owner,
            template=template,
            if_not_exists=if_not_exists,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(OperationalError),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def _connect_with_retry(self, autocommit: bool = False) -> AsyncConnection:
        """Establish async connection with retry for transient failures."""
        return await psycopg.AsyncConnection.connect(
            **self.config.connect_params(), autocommit=autocommit
        )

    @asynccontextmanager
    async def connect(self, autocommit: bool = False) -> AsyncIterator[AsyncConnection]:
        """Async context manager for connection.

        Parameters
        ----------
        autocommit : bool, optional
            Enable autocommit mode (required for CREATE DATABASE, etc.), by default False.

        Yields
        ------
        AsyncConnection
            psycopg AsyncConnection object.
        """
        conn = await self._connect_with_retry(autocommit=autocommit)
        try:
            yield conn
        finally:
            await conn.close()

    @asynccontextmanager
    async def cursor(
        self, autocommit: bool = False
    ) -> AsyncIterator[AsyncCursor[dict[str, Any]]]:
        """Async context manager for cursor with dict rows.

        Parameters
        ----------
        autocommit : bool, optional
            Enable autocommit mode, by default False.

        Yields
        ------
        AsyncCursor
            psycopg AsyncCursor with dict_row factory.
        """
        # Use session connection if available
        if self._session_conn is not None:
            async with self._session_conn.cursor(row_factory=dict_row) as cur:
                yield cur
                if not autocommit:
                    status = self._session_conn.info.transaction_status
                    # Do NOT call commit() when inside a psycopg transaction()
                    # block (savepoint or nested transaction) — psycopg raises
                    # ProgrammingError if commit() is called inside a
                    # conn.transaction() CM. The outer CM handles commit/rollback.
                    ntx = getattr(self._session_conn, "_num_transactions", 0)
                    try:
                        in_txn_block = ntx > 0
                    except TypeError:
                        in_txn_block = (
                            False  # mock / unexpected type — behave as before
                        )
                    if status == TransactionStatus.INTRANS and not in_txn_block:
                        await self._session_conn.commit()
                    elif status == TransactionStatus.INERROR and not in_txn_block:
                        await self._session_conn.rollback()
                    # IDLE: no open transaction, nothing to do
                    # ACTIVE: should not occur at cursor exit
                    # UNKNOWN: connection in bad state, skip
                    # INTRANS + in_txn_block: savepoint/transaction CM handles it
        else:
            async with self.connect(autocommit=autocommit) as conn:
                async with conn.cursor(row_factory=dict_row) as cur:
                    yield cur
                    if not autocommit:
                        if conn.info.transaction_status == TransactionStatus.INERROR:
                            await conn.rollback()
                        else:
                            await conn.commit()

    @asynccontextmanager
    async def session(
        self,
        autocommit: bool = False,
        *,
        isolation_level: IsolationLevel | None = None,
    ) -> AsyncIterator[AsyncDatabase]:
        """Async context manager for session mode with connection reuse.

        In session mode, all operations reuse the same connection,
        significantly reducing overhead for multiple sequential operations.

        Parameters
        ----------
        autocommit : bool, optional
            Enable autocommit mode for the session, by default False.
        isolation_level : IsolationLevel or None, optional
            Transaction isolation level set on the session connection
            immediately after connecting and before any transaction opens.
            Keyword-only. When *None* (default), the server default is used.

        Yields
        ------
        AsyncDatabase
            Self (AsyncDatabase instance with active session).

        Raises
        ------
        RuntimeError
            If already inside an active session.
        """
        if self._session_conn is not None:
            raise RuntimeError(
                "Already in session mode. Nested sessions are not supported."
            )

        self._session_conn = await psycopg.AsyncConnection.connect(
            **self.config.connect_params(), autocommit=autocommit
        )
        if isolation_level is not None:
            self._session_conn.isolation_level = isolation_level
        try:
            yield self
        finally:
            try:
                if not autocommit:
                    commit_exc = None
                    try:
                        await self._session_conn.commit()
                    except Exception as e:
                        commit_exc = e
                        raise
                    finally:
                        # close() ALWAYS runs, even when commit() raises (B2 residual fix).
                        try:
                            await self._session_conn.close()
                        except Exception as close_exc:
                            if commit_exc is not None:
                                # close failure is secondary; don't mask commit failure
                                logger.warning(
                                    "session close() failed after commit() failure: %s",
                                    close_exc,
                                )
                            else:
                                raise
                else:
                    await self._session_conn.close()
            finally:
                self._session_conn = None  # ALWAYS executes

    @property
    def in_session(self) -> bool:
        """Check if currently in session mode.

        Returns
        -------
        bool
            True if in session mode, False otherwise.
        """
        return self._session_conn is not None

    @asynccontextmanager
    async def savepoint(self, *, name: str | None = None) -> AsyncIterator[None]:
        """Async nested savepoint within an active session.

        Creates a named (or auto-named) savepoint via psycopg's native
        ``conn.transaction(savepoint_name=...)`` API. Rolling back inside the
        savepoint block reverts only that block's work; the outer session
        transaction is NOT unwound (partial rollback semantics).

        Parameters
        ----------
        name : str or None, optional
            Savepoint name. When *None* (default), psycopg auto-generates a
            name. Keyword-only. The name reaches psycopg's parameterized
            savepoint API and is never string-interpolated into SQL.

        Yields
        ------
        None

        Raises
        ------
        RuntimeError
            If called outside an active ``db.session()``.
        """
        if self._session_conn is None:
            raise RuntimeError(
                "db.savepoint() requires an active db.session(). "
                "Use 'with db.session(): with db.savepoint(): ...' pattern."
            )
        async with self._session_conn.transaction(savepoint_name=name):
            yield

    async def health(self) -> dict[str, Any]:
        """Return a health-check dict for this database connection.

        Opens a fresh async connection, executes ``SELECT 1``, and measures
        the round-trip latency.  The method **never raises** — on any failure
        it returns a dict with ``connected=False`` and the exception message
        in the ``error`` key, so monitoring loops can call it unconditionally.

        Returns
        -------
        dict
            On success::

                {
                    "connected": True,
                    "latency_ms": <float>,       # round-trip in milliseconds
                    "server_version": "<str>",   # e.g. "16.1"
                }

            On failure::

                {
                    "connected": False,
                    "latency_ms": None,
                    "server_version": None,
                    "error": "<exception message>",
                }

        Notes
        -----
        The method is wrapped in ``log_operation("database.health")`` so
        monitoring probes appear in the structured log stream (D-09).
        The ``error`` string is the raw psycopg exception message — pycopg
        never appends the DSN, password, or credentials (T-45-07).

        Examples
        --------
        >>> status = await db.health()
        >>> status["connected"]
        True
        """
        with log_operation("database.health"):
            try:
                t0 = time.perf_counter()
                # Bypass _connect_with_retry so the probe fails fast (no retry
                # budget) — a down DB returns connected=False immediately rather
                # than blocking for several seconds (WR-02).
                conn = await psycopg.AsyncConnection.connect(
                    **self.config.connect_params()
                )
                try:
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT 1")
                    server_ver_int = conn.info.server_version
                finally:
                    await conn.close()
                latency_ms = round((time.perf_counter() - t0) * 1000, 2)
                return {
                    "connected": True,
                    "latency_ms": latency_ms,
                    "server_version": _decode_server_version(server_ver_int),
                }
            except Exception as exc:
                return {
                    "connected": False,
                    "latency_ms": None,
                    "server_version": None,
                    "error": str(exc),
                }

    @asynccontextmanager
    async def transaction(
        self,
        *,
        isolation_level: IsolationLevel | None = None,
        savepoint_name: str | None = None,
    ) -> AsyncIterator[AsyncConnection]:
        """Async context manager for transactions.

        Automatically commits on success, rolls back on exception.
        If a session is active, reuses the session connection.

        Parameters
        ----------
        isolation_level : IsolationLevel or None, optional
            Transaction isolation level (e.g. ``IsolationLevel.SERIALIZABLE``).
            Keyword-only. When *None* (default), the server default is used.
            Raises ``RuntimeError`` if called inside an active ``db.session()``
            (cannot change isolation mid-session — use
            ``db.session(isolation_level=...)`` instead).
        savepoint_name : str or None, optional
            Named savepoint to open via psycopg's native
            ``conn.transaction(savepoint_name=...)`` API. Keyword-only.
            When *None* (default), no savepoint is created. Inside a session,
            this creates a nested savepoint without unwinding the outer
            transaction.

        Yields
        ------
        AsyncConnection
            psycopg AsyncConnection in a transaction.

        Raises
        ------
        RuntimeError
            If ``isolation_level`` is set while inside an active
            ``db.session()``.
        """
        if self._session_conn is not None:
            # Reuse existing session connection
            if isolation_level is not None:
                raise RuntimeError(
                    "Cannot set isolation_level inside an active db.session(). "
                    "Set isolation_level on db.session(isolation_level=...) instead."
                )
            async with self._session_conn.transaction(savepoint_name=savepoint_name):
                yield self._session_conn
        else:
            # Create new connection
            async with self.connect() as conn:
                if isolation_level is not None:
                    conn.isolation_level = isolation_level
                async with conn.transaction(savepoint_name=savepoint_name):
                    yield conn

    async def execute(
        self,
        sql: str,
        params: Params = None,
        autocommit: bool = False,
    ) -> list[dict[str, Any]]:
        """Execute SQL and return results as list of dicts.

        Parameters
        ----------
        sql : str
            SQL query to execute.
        params : Params, optional
            Query parameters — either a positional sequence (``%s``
            placeholders) or a named mapping (``%(name)s`` placeholders).
            psycopg binds both forms natively without any translation.
        autocommit : bool, optional
            Enable autocommit mode, by default False.

        Returns
        -------
        list of dict
            List of result rows as dicts.
        """
        async with self.cursor(autocommit=autocommit) as cur:
            await cur.execute(sql, params)
            if cur.description:
                return await cur.fetchall()
            return []

    async def execute_many(self, sql: str, params_seq: Sequence[Sequence[Any]]) -> int:
        """Execute SQL for multiple parameter sets.

        Uses psycopg's executemany() for better performance than sequential
        execute() calls.

        Parameters
        ----------
        sql : str
            SQL query with placeholders.
        params_seq : Sequence of Sequence
            Sequence of parameter sequences.

        Returns
        -------
        int
            Total number of affected rows.
        """
        async with self.cursor() as cur:
            await cur.executemany(sql, params_seq)
            return cur.rowcount

    async def insert_batch(
        self,
        table: str,
        rows: list[dict[str, Any]],
        *,
        schema: str = "public",
        on_conflict: str | None = None,
        batch_size: int | None = None,
    ) -> int:
        """Insert multiple rows efficiently using batch VALUES.

        This method builds a single INSERT with multiple VALUES tuples,
        which is significantly faster than individual INSERT statements.
        For very large datasets (>10000 rows), consider using copy_insert().

        Parameters
        ----------
        table : str
            Table name.
        rows : list of dict
            List of row dicts (all must have same keys).
        schema : str, optional
            Schema name, by default "public".
        on_conflict : str, optional
            ON CONFLICT clause (e.g., "DO NOTHING",
            "(id) DO UPDATE SET name = EXCLUDED.name").
        batch_size : int, optional
            Max rows per INSERT statement, by default from config.

        Returns
        -------
        int
            Total number of rows inserted.
        """
        if not rows:
            return 0

        if batch_size is None:
            batch_size = self.config.default_batch_size

        validate_identifiers(table, schema)

        columns = list(rows[0].keys())
        for col in columns:
            validate_identifier(col)

        cols_str = ", ".join(columns)
        conflict_clause = f" ON CONFLICT {on_conflict}" if on_conflict else ""

        total = 0
        async with self.cursor() as cur:
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]

                row_placeholders = ", ".join(["%s"] * len(columns))
                placeholders = []
                params: list[Any] = []
                for row in batch:
                    placeholders.append(f"({row_placeholders})")
                    params.extend(row.get(col) for col in columns)

                values_str = ", ".join(placeholders)
                sql = f"INSERT INTO {schema}.{table} ({cols_str}) VALUES {values_str}{conflict_clause}"

                await cur.execute(sql, params)
                total += cur.rowcount

        return total

    async def copy_insert(
        self,
        table: str,
        rows: list[dict[str, Any]],
        *,
        schema: str = "public",
        columns: list[str] | None = None,
    ) -> int:
        """Insert rows using PostgreSQL COPY protocol.

        This is the fastest method for bulk inserts (10-100x faster than
        regular INSERT for large datasets). Best for >10000 rows.

        Note: COPY doesn't support ON CONFLICT. For upserts, use insert_batch().

        Parameters
        ----------
        table : str
            Table name.
        rows : list of dict
            List of row dicts.
        schema : str, optional
            Schema name, by default "public".
        columns : list of str, optional
            Column names. If not provided, uses keys from first row.

        Returns
        -------
        int
            Number of rows inserted.
        """
        if not rows:
            return 0

        validate_identifiers(table, schema)

        if columns is None:
            columns = list(rows[0].keys())
        for col in columns:
            validate_identifier(col)

        cols_str = ", ".join(columns)

        async with self.connect() as conn:
            async with conn.cursor() as cur:
                async with cur.copy(
                    f"COPY {schema}.{table} ({cols_str}) FROM STDIN"
                ) as copy:
                    for row in rows:
                        await copy.write_row([row.get(col) for col in columns])
            await conn.commit()
            return len(rows)

    async def fetch_one(self, sql: str, params: Params = None) -> dict[str, Any] | None:
        """Execute SQL and return single row.

        Parameters
        ----------
        sql : str
            SQL query.
        params : Params, optional
            Query parameters — either a positional sequence (``%s``
            placeholders) or a named mapping (``%(name)s`` placeholders).
            psycopg binds both forms natively without any translation.

        Returns
        -------
        dict or None
            Single row as dict, or None.
        """
        async with self.cursor() as cur:
            await cur.execute(sql, params)
            return await cur.fetchone()

    async def fetch_val(self, sql: str, params: Params = None) -> Any:
        """Execute SQL and return single value.

        Parameters
        ----------
        sql : str
            SQL query returning single column.
        params : Params, optional
            Query parameters — either a positional sequence (``%s``
            placeholders) or a named mapping (``%(name)s`` placeholders).
            psycopg binds both forms natively without any translation.

        Returns
        -------
        Any
            Single value, or None.
        """
        row = await self.fetch_one(sql, params)
        if row:
            return list(row.values())[0]
        return None

    async def fetch_all(self, sql: str, params: Params = None) -> list[dict[str, Any]]:
        """Execute SQL and return all rows as a list of dicts.

        Thin ``list[dict]`` complement to :meth:`fetch_one`. The core uses
        psycopg's ``dict_row`` row factory by default, so every row is already
        a plain ``dict`` — no extra conversion needed. Use :meth:`fetch_one`
        when you expect exactly one row; use ``fetch_all`` for arbitrary result
        sets where you need the full list at once.

        Parameters
        ----------
        sql : str
            SQL query. The caller owns the SQL string and must parameterize
            dynamic values via ``params`` (same trust model as
            :meth:`execute` / :meth:`fetch_one`).
        params : Params, optional
            Query parameters — either a positional sequence (``%s``
            placeholders) or a named mapping (``%(name)s`` placeholders).
            psycopg binds both forms natively without any translation.

        Returns
        -------
        list of dict
            All result rows as dicts (keyed by column name). Returns ``[]``
            for queries that produce no rows or no description.

        Notes
        -----
        The underlying connection uses ``dict_row`` as its row factory, so
        all fetch methods (``fetch_one``, ``fetch_all``, ``execute``) return
        ``dict`` rows by default — no ``into=`` toggle or tuples path is
        provided.
        """
        async with self.cursor() as cur:
            await cur.execute(sql, params)
            if cur.description:
                return await cur.fetchall()
            return []

    async def exists(
        self,
        table: str,
        where: dict[str, Any] | None = None,
        *,
        where_sql: str | None = None,
        where_params: Sequence[Any] | None = None,
        schema: str = "public",
    ) -> bool:
        """Check whether any row matching the given equality conditions exists.

        Parameters
        ----------
        table : str
            Table name.
        where : dict, optional
            Equality conditions as column-name to value mapping. Mutually
            exclusive with ``where_sql`` (D-02). Exactly one of ``where`` /
            ``where_sql`` must resolve to a non-empty predicate — an
            existence check with no predicate is meaningless.
        where_sql : str, optional
            Raw SQL WHERE fragment (without the ``WHERE`` keyword), for
            predicates the ``where`` dict cannot express. This is a
            documented escape hatch: the fragment is passed through
            **verbatim** and is **not** run through identifier validation —
            the caller owns the SQL text. Only ``where_params`` are treated
            as untrusted values and bound as ``%s``.
        where_params : Sequence, optional
            Positional ``%s`` parameters bound against ``where_sql``.
            Requires ``where_sql`` to be present (D-04).
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        bool
            ``True`` if at least one matching row exists, ``False`` otherwise.

        Raises
        ------
        ValueError
            If neither ``where`` nor ``where_sql`` resolves to a non-empty
            predicate (guard fires before any SQL or cursor is opened); if
            both ``where`` and ``where_sql`` are supplied (D-02); if
            ``where_params`` is supplied without ``where_sql`` (D-04); or if
            ``where_sql`` is empty/whitespace-only (D-03).
        InvalidIdentifierError
            If any column name or the table/schema identifier is invalid.
        """
        frag, pred_params = self._resolve_predicate(where, where_sql, where_params)
        if not frag:
            raise ValueError(
                "exists requires a non-empty `where` dict or `where_sql` "
                "fragment — an existence check with no predicate is "
                "meaningless."
            )
        validate_identifiers(table, schema)
        sql = f"SELECT EXISTS(SELECT 1 FROM {schema}.{table} WHERE {frag})"
        return bool(await self.fetch_val(sql, pred_params))

    async def count(
        self,
        table: str,
        *,
        where: dict[str, Any] | None = None,
        where_sql: str | None = None,
        where_params: Sequence[Any] | None = None,
        schema: str = "public",
    ) -> int:
        """Count rows in a table, optionally filtered by equality conditions.

        Parameters
        ----------
        table : str
            Table name.
        where : dict, optional
            Equality conditions as column-name to value mapping. When neither
            ``where`` nor ``where_sql`` is given, all rows are counted
            without a WHERE clause. Mutually exclusive with ``where_sql``
            (D-02).
        where_sql : str, optional
            Raw SQL WHERE fragment (without the ``WHERE`` keyword), for
            predicates the ``where`` dict cannot express (e.g.
            ``"age > %s AND status = ANY(%s)"``). This is a documented escape
            hatch: the fragment is passed through **verbatim** and is **not**
            run through identifier validation — the caller owns the SQL text.
            Only ``where_params`` are treated as untrusted values and bound
            as ``%s``.
        where_params : Sequence, optional
            Positional ``%s`` parameters bound against ``where_sql``.
            Requires ``where_sql`` to be present (D-04).
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        int
            Number of matching (or total) rows.

        Raises
        ------
        ValueError
            If both ``where`` and ``where_sql`` are supplied (D-02); if
            ``where_params`` is supplied without ``where_sql`` (D-04); or if
            ``where_sql`` is empty/whitespace-only (D-03).
        InvalidIdentifierError
            If any column name or the table/schema identifier is invalid.
        """
        validate_identifiers(table, schema)
        frag, pred_params = self._resolve_predicate(where, where_sql, where_params)
        if frag:
            sql = f"SELECT COUNT(*) FROM {schema}.{table} WHERE {frag}"
        else:
            pred_params = []
            sql = f"SELECT COUNT(*) FROM {schema}.{table}"
        return int(await self.fetch_val(sql, pred_params))

    async def select_where(
        self,
        table: str,
        where: dict[str, Any] | None = None,
        *,
        where_sql: str | None = None,
        where_params: Sequence[Any] | None = None,
        columns: list[str] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        schema: str = "public",
    ) -> list[dict[str, Any]]:
        """Select rows matching the given equality conditions.

        The predicate read sibling of :meth:`delete_where` / :meth:`update_where`
        / :meth:`exists` / :meth:`count`. Unlike those, an empty predicate is
        legal here: with no ``where``/``where_sql``, all rows are returned
        (still honoring ``order_by``/``limit``/``offset``) — reads are
        non-destructive, so there is no empty-predicate guard (D-03).

        Parameters
        ----------
        table : str
            Table name.
        where : dict, optional
            Equality conditions as column-name to value mapping. When neither
            ``where`` nor ``where_sql`` is given, all rows are returned
            without a WHERE clause (D-03). Mutually exclusive with
            ``where_sql`` (D-02).
        where_sql : str, optional
            Raw SQL WHERE fragment (without the ``WHERE`` keyword), for
            predicates the ``where`` dict cannot express (e.g.
            ``"age > %s AND status = ANY(%s)"``). This is a documented escape
            hatch: the fragment is passed through **verbatim** and is **not**
            run through identifier validation — the caller owns the SQL text.
            Only ``where_params`` are treated as untrusted values and bound
            as ``%s``.
        where_params : Sequence, optional
            Positional ``%s`` parameters bound against ``where_sql``.
            Requires ``where_sql`` to be present (D-04).
        columns : list of str, optional
            Column names to project, by default None (``SELECT *``).
        order_by : str, optional
            ``ORDER BY`` clause. Like ``where_sql``, this is a documented,
            caller-owned raw-SQL escape hatch — it is appended verbatim and
            is **not** run through identifier validation, so multi-column
            syntax such as ``"col1 DESC, col2 ASC"`` is accepted by design.
        limit : int, optional
            Maximum number of rows to return.
        offset : int, optional
            Number of rows to skip.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of dict
            Matching rows (or all rows if no predicate), as dicts.

        Raises
        ------
        ValueError
            If both ``where`` and ``where_sql`` are supplied (D-02); if
            ``where_params`` is supplied without ``where_sql`` (D-04); if
            ``where_sql`` is empty/whitespace-only (D-03); or if ``limit``
            or ``offset`` is negative (WR-02).
        InvalidIdentifierError
            If any column name or the table/schema identifier is invalid.
        """
        if limit is not None:
            limit = int(limit)
            if limit < 0:
                raise ValueError("limit must not be negative")
        if offset is not None:
            offset = int(offset)
            if offset < 0:
                raise ValueError("offset must not be negative")
        frag, pred_params = self._resolve_predicate(where, where_sql, where_params)
        sql = self._build_select_sql(
            table,
            columns,
            schema,
            where=frag or None,
            order_by=order_by,
            limit=limit,
            offset=offset,
        )
        return await self.fetch_all(sql, pred_params)

    async def find(
        self,
        table: str,
        where: dict[str, Any] | None = None,
        *,
        where_sql: str | None = None,
        where_params: Sequence[Any] | None = None,
        columns: list[str] | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        schema: str = "public",
    ) -> list[dict[str, Any]]:
        """Select rows matching the given equality conditions (alias of :meth:`select_where`).

        A real, concrete, delegating twin of :meth:`select_where` (D-02) —
        not a deprecated alias and not a module-level alias — provided as a
        shorter, familiar name for the same read. See :meth:`select_where`
        for the full parameter and behavior documentation.

        Parameters
        ----------
        table : str
            Table name.
        where : dict, optional
            Equality conditions as column-name to value mapping.
        where_sql : str, optional
            Raw SQL WHERE fragment escape hatch (see :meth:`select_where`).
        where_params : Sequence, optional
            Positional ``%s`` parameters bound against ``where_sql``.
        columns : list of str, optional
            Column names to project, by default None (``SELECT *``).
        order_by : str, optional
            ``ORDER BY`` clause (caller-owned raw-SQL escape hatch).
        limit : int, optional
            Maximum number of rows to return.
        offset : int, optional
            Number of rows to skip.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of dict
            Matching rows (or all rows if no predicate), as dicts.
        """
        return await self.select_where(
            table,
            where,
            where_sql=where_sql,
            where_params=where_params,
            columns=columns,
            order_by=order_by,
            limit=limit,
            offset=offset,
            schema=schema,
        )

    async def get(
        self,
        table: str,
        where: dict[str, Any] | None = None,
        *,
        where_sql: str | None = None,
        where_params: Sequence[Any] | None = None,
        columns: list[str] | None = None,
        order_by: str | None = None,
        schema: str = "public",
    ) -> dict[str, Any] | None:
        """Select the first row matching the given equality conditions.

        The single-row predicate read sibling of :meth:`select_where`. Forces
        a server-side ``LIMIT 1`` — never truncates in Python. On more than
        one match, the first row (per ``order_by`` if given, otherwise
        implementation-defined) is returned with **no exception raised**
        (D-04); uniqueness is the caller's responsibility (a UNIQUE
        constraint, or :meth:`exists`/:meth:`count`). Does **not** expose
        ``limit``/``offset`` — they would be contradictory with the forced
        ``LIMIT 1`` (D-05).

        Parameters
        ----------
        table : str
            Table name.
        where : dict, optional
            Equality conditions as column-name to value mapping. When
            neither ``where`` nor ``where_sql`` is given, any one row (or
            None if the table is empty) is returned. Mutually exclusive with
            ``where_sql`` (D-02).
        where_sql : str, optional
            Raw SQL WHERE fragment (without the ``WHERE`` keyword), for
            predicates the ``where`` dict cannot express. This is a
            documented escape hatch: the fragment is passed through
            **verbatim** and is **not** run through identifier validation —
            the caller owns the SQL text. Only ``where_params`` are treated
            as untrusted values and bound as ``%s``.
        where_params : Sequence, optional
            Positional ``%s`` parameters bound against ``where_sql``.
            Requires ``where_sql`` to be present (D-04).
        columns : list of str, optional
            Column names to project, by default None (``SELECT *``).
        order_by : str, optional
            ``ORDER BY`` clause, making the "first" match deterministic. Like
            ``where_sql``, this is a documented, caller-owned raw-SQL escape
            hatch — not run through identifier validation.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        dict or None
            The first matching row as a dict, or None if no row matches.

        Raises
        ------
        ValueError
            If both ``where`` and ``where_sql`` are supplied (D-02); if
            ``where_params`` is supplied without ``where_sql`` (D-04); or if
            ``where_sql`` is empty/whitespace-only (D-03).
        InvalidIdentifierError
            If any column name or the table/schema identifier is invalid.
        """
        frag, pred_params = self._resolve_predicate(where, where_sql, where_params)
        sql = self._build_select_sql(
            table,
            columns,
            schema,
            where=frag or None,
            order_by=order_by,
            limit=1,
            offset=None,
        )
        return await self.fetch_one(sql, pred_params)

    async def find_one(
        self,
        table: str,
        where: dict[str, Any] | None = None,
        *,
        where_sql: str | None = None,
        where_params: Sequence[Any] | None = None,
        columns: list[str] | None = None,
        order_by: str | None = None,
        schema: str = "public",
    ) -> dict[str, Any] | None:
        """Select the first row matching the given equality conditions (alias of :meth:`get`).

        A real, concrete, delegating twin of :meth:`get` (D-02) — not a
        deprecated alias and not a module-level alias — provided as a
        shorter, familiar name for the same single-row read. See :meth:`get`
        for the full parameter and behavior documentation.

        Parameters
        ----------
        table : str
            Table name.
        where : dict, optional
            Equality conditions as column-name to value mapping.
        where_sql : str, optional
            Raw SQL WHERE fragment escape hatch (see :meth:`get`).
        where_params : Sequence, optional
            Positional ``%s`` parameters bound against ``where_sql``.
        columns : list of str, optional
            Column names to project, by default None (``SELECT *``).
        order_by : str, optional
            ``ORDER BY`` clause, making the "first" match deterministic
            (caller-owned raw-SQL escape hatch).
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        dict or None
            The first matching row as a dict, or None if no row matches.
        """
        return await self.get(
            table,
            where,
            where_sql=where_sql,
            where_params=where_params,
            columns=columns,
            order_by=order_by,
            schema=schema,
        )

    async def paginate(
        self,
        table: str,
        limit: int,
        *,
        offset: int = 0,
        order_by: str | list[str] | None = None,
        where: dict[str, Any] | None = None,
        where_sql: str | None = None,
        where_params: Sequence[Any] | None = None,
        descending: bool = False,
        schema: str = "public",
    ) -> list[dict[str, Any]]:
        """Return a page of rows from a table.

        Parameters
        ----------
        table : str
            Table name.
        limit : int
            Maximum number of rows to return. Cast to ``int`` before use.
        offset : int, optional
            Number of rows to skip, by default 0. Cast to ``int`` before use.
        order_by : str or list of str, optional
            Column name(s) to sort by. Each name is validated via
            ``validate_identifiers`` before interpolation. Whole-clause
            direction is controlled by ``descending``.
        where : dict, optional
            Equality conditions as column-name to value mapping. When neither
            ``where`` nor ``where_sql`` is given, all rows are returned
            without a WHERE clause. Mutually exclusive with ``where_sql``
            (D-02).
        where_sql : str, optional
            Raw SQL WHERE fragment (without the ``WHERE`` keyword), for
            predicates the ``where`` dict cannot express. This is a
            documented escape hatch: the fragment is passed through
            **verbatim** and is **not** run through identifier validation —
            the caller owns the SQL text. Only ``where_params`` are treated
            as untrusted values and bound as ``%s``.
        where_params : Sequence, optional
            Positional ``%s`` parameters bound against ``where_sql``.
            Requires ``where_sql`` to be present (D-04).
        descending : bool, optional
            When ``True``, append ``DESC`` to the ORDER BY clause (applies to
            all listed columns). Per-column direction is deferred.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of dict
            Requested page as a list of row dicts. Returns ``[]`` when the
            query produces no rows.

        Raises
        ------
        ValueError
            If both ``where`` and ``where_sql`` are supplied (D-02); if
            ``where_params`` is supplied without ``where_sql`` (D-04); or if
            ``where_sql`` is empty/whitespace-only (D-03).
        InvalidIdentifierError
            If any column name in ``order_by`` or the table/schema identifier
            is invalid.
        """
        validate_identifiers(table, schema)

        params: list[Any] = []
        frag, pred_params = self._resolve_predicate(where, where_sql, where_params)
        where_clause = f" WHERE {frag}" if frag else ""
        params.extend(pred_params)

        order_clause = ""
        if order_by is not None:
            if isinstance(order_by, str):
                order_by_cols = [order_by]
            else:
                order_by_cols = list(order_by)
            if any(not isinstance(c, str) or not c for c in order_by_cols):
                raise ValueError("order_by columns must be non-empty strings")
            validate_identifiers(*order_by_cols)
            cols_str = ", ".join(order_by_cols)
            direction = " DESC" if descending else ""
            order_clause = f" ORDER BY {cols_str}{direction}"

        sql = (
            f"SELECT * FROM {schema}.{table}"
            f"{where_clause}"
            f"{order_clause}"
            f" LIMIT {int(limit)} OFFSET {int(offset)}"
        )
        async with self.cursor() as cur:
            await cur.execute(sql, params)
            if cur.description:
                return await cur.fetchall()
            return []

    async def paginate_page(
        self,
        table: str,
        limit: int,
        *,
        offset: int = 0,
        order_by: str | list[str] | None = None,
        where: dict[str, Any] | None = None,
        where_sql: str | None = None,
        where_params: Sequence[Any] | None = None,
        with_total: bool = False,
        descending: bool = False,
        schema: str = "public",
    ) -> Page:
        """Return an offset page wrapped in a :class:`Page` envelope (D-09).

        Sibling of :meth:`paginate` returning a typed :class:`Page` instead
        of a plain ``list[dict]``. :meth:`paginate` itself is left untouched
        (frozen ``list[dict]``, C-03). ``has_next`` is always computed
        cheaply via a ``limit + 1`` fetch-and-trim; ``total`` runs a
        separate ``COUNT(*)`` only when ``with_total=True`` (D-10).

        Parameters
        ----------
        table : str
            Table name.
        limit : int
            Maximum number of rows to return in the page. Cast to ``int``
            before use.
        offset : int, optional
            Number of rows to skip, by default 0. Cast to ``int`` before
            use.
        order_by : str or list of str, optional
            Column name(s) to sort by. Each name is validated via
            ``validate_identifiers`` before interpolation. Whole-clause
            direction is controlled by ``descending``.
        where : dict, optional
            Equality conditions as column-name to value mapping. Mutually
            exclusive with ``where_sql`` (D-02).
        where_sql : str, optional
            Raw SQL WHERE fragment (without the ``WHERE`` keyword), for
            predicates the ``where`` dict cannot express. Documented escape
            hatch: passed through **verbatim**, never run through identifier
            validation — the caller owns the SQL text. Only
            ``where_params`` are treated as untrusted values and bound as
            ``%s``.
        where_params : Sequence, optional
            Positional ``%s`` parameters bound against ``where_sql``.
            Requires ``where_sql`` to be present (D-04).
        with_total : bool, optional
            When ``True``, run a separate ``COUNT(*)`` (same predicate) and
            populate ``Page.total``. By default ``False`` — avoids a
            surprise ``COUNT`` on deep pages (D-10).
        descending : bool, optional
            When ``True``, append ``DESC`` to the ORDER BY clause.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        Page
            ``rows`` (trimmed to ``limit``), ``total`` (``int`` when
            ``with_total=True`` else ``None``), ``has_next``, and
            ``next_cursor`` (always ``None`` — offset pagination has no
            cursor concept).

        Raises
        ------
        ValueError
            If both ``where`` and ``where_sql`` are supplied (D-02); if
            ``where_params`` is supplied without ``where_sql`` (D-04); if
            ``where_sql`` is empty/whitespace-only (D-03); if ``order_by``
            is an empty list (WR-01); or if ``limit`` is not a positive
            integer (IN-02).
        InvalidIdentifierError
            If any column name in ``order_by`` or the table/schema
            identifier is invalid.
        """
        validate_identifiers(table, schema)

        limit = int(limit)
        if limit <= 0:
            raise ValueError("limit must be a positive integer")

        params: list[Any] = []
        frag, pred_params = self._resolve_predicate(where, where_sql, where_params)
        where_clause = f" WHERE {frag}" if frag else ""
        params.extend(pred_params)

        order_clause = ""
        if order_by is not None:
            if isinstance(order_by, str):
                order_by_cols = [order_by]
            else:
                order_by_cols = list(order_by)
            if not order_by_cols:
                raise ValueError("order_by must contain at least one column")
            if any(not isinstance(c, str) or not c for c in order_by_cols):
                raise ValueError("order_by columns must be non-empty strings")
            validate_identifiers(*order_by_cols)
            cols_str = ", ".join(order_by_cols)
            direction = " DESC" if descending else ""
            order_clause = f" ORDER BY {cols_str}{direction}"

        sql = (
            f"SELECT * FROM {schema}.{table}"
            f"{where_clause}"
            f"{order_clause}"
            f" LIMIT {limit + 1} OFFSET {int(offset)}"
        )
        async with self.cursor() as cur:
            await cur.execute(sql, params)
            rows: list[dict[str, Any]] = (
                await cur.fetchall() if cur.description else []
            )

        has_next = len(rows) > limit
        rows = rows[:limit]

        total: int | None = None
        if with_total:
            count_sql = f"SELECT COUNT(*) FROM {schema}.{table}{where_clause}"
            total = int(await self.fetch_val(count_sql, pred_params))

        return Page(rows=rows, total=total, has_next=has_next, next_cursor=None)

    async def paginate_keyset(
        self,
        table: str,
        limit: int,
        *,
        order_by: str | list[str] | None = None,
        after: Sequence[Any] | None = None,
        where: dict[str, Any] | None = None,
        where_sql: str | None = None,
        where_params: Sequence[Any] | None = None,
        with_total: bool = False,
        descending: bool = False,
        schema: str = "public",
    ) -> Page:
        """Return a keyset (seek) page wrapped in a :class:`Page` envelope (D-05).

        Stable, index-friendly deep pagination via a PostgreSQL row-value
        comparison ``(c1, c2) > (%s, %s)`` (D-07,
        :meth:`pycopg.base.QueryMixin._build_keyset_where`) instead of
        ``OFFSET``. ``order_by`` is mandatory — the caller owns a
        unique/total order (append a unique column such as the primary key
        as a tiebreaker); no hidden PK-introspection round-trip is
        performed. **Forward-only** for this release — ``before=``/backward
        paging is deferred. **Caveat (IN-01):** ``order_by`` columns should
        be ``NOT NULL`` (or the caller must guarantee no ``NULL`` values) —
        the row-value comparison follows SQL ``NULL`` semantics, so rows
        with a ``NULL`` key are silently skipped by the seek predicate.

        Parameters
        ----------
        table : str
            Table name.
        limit : int
            Maximum number of rows to return in the page. Cast to ``int``
            before use.
        order_by : str or list of str
            Column name(s) defining the seek order. **Mandatory** (D-07) —
            raises ``ValueError`` if omitted. Each name is validated via
            ``validate_identifiers`` before interpolation. Columns should be
            ``NOT NULL`` (IN-01) — see caveat above.
        after : Sequence, optional
            Cursor values, positionally keyed to ``order_by`` (D-06). Omit
            (or pass ``None``) to fetch the first page — the keyset
            fragment is skipped entirely (``ORDER BY`` + ``LIMIT`` only).
            Must have exactly ``len(order_by)`` values.
        where : dict, optional
            Equality conditions as column-name to value mapping. Mutually
            exclusive with ``where_sql`` (D-02). ANDed with the keyset
            fragment when both are present.
        where_sql : str, optional
            Raw SQL WHERE fragment (without the ``WHERE`` keyword), for
            predicates the ``where`` dict cannot express. Documented escape
            hatch: passed through **verbatim**, never run through identifier
            validation — the caller owns the SQL text. Only
            ``where_params`` are treated as untrusted values and bound as
            ``%s``.
        where_params : Sequence, optional
            Positional ``%s`` parameters bound against ``where_sql``.
            Requires ``where_sql`` to be present (D-04).
        with_total : bool, optional
            When ``True``, run a separate ``COUNT(*)`` using only the base
            predicate (``where``/``where_sql``, **not** the keyset ``after``
            fragment — the total is the full filtered set, not the
            remaining-after-cursor set) and populate ``Page.total``. By
            default ``False`` (D-10).
        descending : bool, optional
            When ``True``, flips the row-value comparison operator to ``<``
            **and** appends ``DESC`` to ``ORDER BY`` — both must agree
            (Pitfall 3). By default ``False``.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        Page
            ``rows`` (trimmed to ``limit``), ``total`` (``int`` when
            ``with_total=True`` else ``None``), ``has_next``, and
            ``next_cursor`` — the last row's ``order_by``-keyed value tuple
            (D-06), keyed to ``order_by`` columns (Pitfall 4), or ``None``
            when the page is empty.

        Raises
        ------
        ValueError
            If ``order_by`` is omitted or an empty list (D-07/WR-01); if
            ``after`` is supplied and ``len(after) != len(order_by)``; if
            both ``where`` and ``where_sql`` are supplied (D-02); if
            ``where_params`` is supplied without ``where_sql`` (D-04); if
            ``where_sql`` is empty/whitespace-only (D-03); or if ``limit``
            is not a positive integer (IN-02).
        InvalidIdentifierError
            If any column name in ``order_by`` or the table/schema
            identifier is invalid.
        """
        validate_identifiers(table, schema)

        limit = int(limit)
        if limit <= 0:
            raise ValueError("limit must be a positive integer")

        if order_by is None:
            raise ValueError(
                "paginate_keyset requires order_by (D-07) — the row-value "
                "keyset compare needs an explicit, ideally unique, sort order."
            )
        if isinstance(order_by, str):
            order_cols = [order_by]
        else:
            order_cols = list(order_by)
        if not order_cols:
            raise ValueError("order_by must contain at least one column")
        if any(not isinstance(c, str) or not c for c in order_cols):
            raise ValueError("order_by columns must be non-empty strings")
        validate_identifiers(*order_cols)

        if after is not None and len(after) != len(order_cols):
            raise ValueError(
                f"after must have exactly {len(order_cols)} value(s) matching "
                f"order_by, got {len(after)}."
            )

        params: list[Any] = []
        frag, pred_params = self._resolve_predicate(where, where_sql, where_params)

        where_parts: list[str] = []
        if after is not None:
            keyset_frag, keyset_params = self._build_keyset_where(
                order_cols, after, descending
            )
            where_parts.append(keyset_frag)
            params.extend(keyset_params)
        if frag:
            where_parts.append(frag)
            params.extend(pred_params)
        where_clause = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""

        # Every listed column must carry DESC when descending — the row-value
        # comparison flips ALL columns together (Pitfall 3); a trailing-only
        # "ORDER BY a, b DESC" would sort col a ascending and only b
        # descending, disagreeing with the (a, b) < (%s, %s) fragment above.
        if descending:
            order_terms = ", ".join(f"{c} DESC" for c in order_cols)
        else:
            order_terms = ", ".join(order_cols)
        order_clause = f" ORDER BY {order_terms}"

        sql = (
            f"SELECT * FROM {schema}.{table}"
            f"{where_clause}"
            f"{order_clause}"
            f" LIMIT {limit + 1}"
        )
        async with self.cursor() as cur:
            await cur.execute(sql, params)
            rows: list[dict[str, Any]] = (
                await cur.fetchall() if cur.description else []
            )

        has_next = len(rows) > limit
        rows = rows[:limit]
        next_cursor = tuple(rows[-1][c] for c in order_cols) if rows else None

        total: int | None = None
        if with_total:
            base_where_clause = f" WHERE {frag}" if frag else ""
            count_sql = f"SELECT COUNT(*) FROM {schema}.{table}{base_where_clause}"
            total = int(await self.fetch_val(count_sql, pred_params))

        return Page(rows=rows, total=total, has_next=has_next, next_cursor=next_cursor)

    # =========================================================================
    # DATAFRAME OPERATIONS
    # =========================================================================

    async def to_dataframe(
        self,
        table: str | None = None,
        *,
        schema: str = "public",
        sql: str | None = None,
        params: Params = None,
    ) -> pd.DataFrame:
        """Read table or query into pandas DataFrame.

        Parameters
        ----------
        table : str, optional
            Table name (mutually exclusive with sql).
        schema : str, optional
            Schema name, by default "public".
        sql : str, optional
            SQL query (mutually exclusive with table).
        params : Params, optional
            Query parameters for *sql*.  This method routes through
            SQLAlchemy ``text()`` / ``pd.read_sql``, which uses the
            ``:name`` (colon-prefix) named-parameter style — **not**
            the ``%(name)s`` style used by the psycopg-backed
            ``execute`` / ``fetch_*`` methods.  When passing a mapping,
            use ``:name`` placeholders in *sql*, e.g.
            ``"SELECT :x AS v"`` with ``params={"x": 9}``.

        Returns
        -------
        pd.DataFrame
            pandas DataFrame.
        """
        import pandas as pd
        from sqlalchemy import text

        if table and sql:
            raise ValueError("Specify either table or sql, not both")
        if not table and not sql:
            raise ValueError("Specify either table or sql")

        if table:
            validate_identifiers(table, schema)
            sql = f"SELECT * FROM {schema}.{table}"

        # sql is guaranteed non-None here: either passed directly, or just
        # built from `table` above (the earlier guard rejects both-None).
        assert sql is not None
        async with self.async_engine.connect() as conn:
            return await conn.run_sync(
                lambda sync_conn: pd.read_sql(text(sql), sync_conn, params=params)
            )

    async def from_dataframe(
        self,
        df: pd.DataFrame,
        table: str,
        *,
        schema: str = "public",
        if_exists: Literal["fail", "replace", "append"] = "fail",
        primary_key: str | list[str] | None = None,
        index: bool = False,
        dtype: dict[str, Any] | None = None,
    ) -> None:
        """Create or append to table from pandas DataFrame.

        Uses a two-phase Hybrid DDL+COPY strategy (D-01/D-04):

        1. **DDL phase** — ``df_ddl.head(0).to_sql(con=sync_conn, ...)`` creates
           or replaces the empty typed table via the async engine's
           ``run_sync`` bridge (preserving ``if_exists``, ``dtype``, and
           ``index`` semantics without re-implementing them).
        2. **COPY phase** — row data is streamed via ``psycopg AsyncCopy
           FROM STDIN`` on a separate ``async with self.connect()`` connection
           (D-03), which is committed after the COPY block closes.

        **D-04 two-phase contract for ``if_exists='replace'``:** The DDL commit
        (table dropped and recreated empty) happens before the COPY load.  If the
        COPY step fails, the table will exist but be empty.  This matches the
        pre-existing ``replace`` semantics ("drop and rebuild") and has always been
        the observable behaviour of ``from_dataframe``; it is now made explicit.

        Parameters
        ----------
        df : pd.DataFrame
            pandas DataFrame.
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".
        if_exists : {'fail', 'replace', 'append'}, optional
            What to do if table exists, by default "fail".
        primary_key : str or list of str, optional
            Column(s) to set as primary key after creation.
        index : bool, optional
            Write DataFrame index as a column, by default False.
            The index column(s) are promoted via ``reset_index()`` so they
            appear identically in both the DDL schema and the COPY stream (D-01a).
        dtype : dict, optional
            Dict of column name to SQLAlchemy types.
        """
        validate_identifiers(table, schema)

        with log_operation("database.from_dataframe", rows=len(df)):
            # D-01a: promote index columns into the frame so DDL and COPY see the same columns
            df_ddl = df.reset_index() if index else df

            # Step 1 — DDL: create/replace/append the empty typed schema via run_sync bridge
            # index=False because df_ddl already contains the index column(s) as regular columns
            # dtype is our public dict[str, Any] -> SQLAlchemy type contract; pandas-stubs'
            # to_sql() narrows the value union to concrete dtype/ExtensionDtype types that
            # don't include arbitrary Any, so cast() bridges the two (D-01 unstubbed-edge;
            # mirrors the sync Database.from_dataframe treatment).
            async with self.async_engine.connect() as conn:
                await conn.run_sync(
                    lambda sync_conn: df_ddl.head(0).to_sql(
                        name=table,
                        con=sync_conn,
                        schema=schema,
                        if_exists=if_exists,
                        index=False,
                        dtype=cast("dict[Hashable, Any] | None", dtype),
                    )
                )
            # DDL commits on the async engine (D-04: two-phase accepted for replace)

            # Step 2 — COPY: stream row data on a separate async psycopg connection (D-03)
            columns = list(
                df_ddl.columns
            )  # derived from df_ddl (not df) — must match DDL
            async with self.connect() as conn:
                async with conn.cursor() as cur:
                    await _async_stream_df_copy(cur, df_ddl, table, schema, columns)
                await conn.commit()

            # Step 3 — PK (unchanged path, post-load)
            if primary_key and if_exists != "append":
                await self.schema.add_primary_key(table, primary_key, schema=schema)

    async def to_geodataframe(
        self,
        table: str | None = None,
        *,
        schema: str = "public",
        sql: str | None = None,
        geometry_column: str = "geometry",
        params: dict[str, Any] | None = None,
    ) -> gpd.GeoDataFrame:
        """Read table or query into GeoDataFrame.

        Parameters
        ----------
        table : str, optional
            Table name (mutually exclusive with sql).
        schema : str, optional
            Schema name, by default "public".
        sql : str, optional
            SQL query (mutually exclusive with table).
        geometry_column : str, optional
            Name of geometry column, by default "geometry".
        params : dict, optional
            Query parameters.

        Returns
        -------
        gpd.GeoDataFrame
            geopandas GeoDataFrame.
        """
        import geopandas as gpd
        from sqlalchemy import text

        if table and sql:
            raise ValueError("Specify either table or sql, not both")
        if not table and not sql:
            raise ValueError("Specify either table or sql")

        if table:
            validate_identifiers(table, schema)
            sql = f"SELECT * FROM {schema}.{table}"

        # sql is guaranteed non-None here: either passed directly, or just
        # built from `table` above (the earlier guard rejects both-None).
        assert sql is not None
        # geopandas-stubs' read_postgis() overloads key on the absent `chunksize`
        # kwarg via a precise Sequence/Mapping params union that our public
        # dict[str, Any] contract can't statically satisfy — mypy cannot select
        # a variant even after narrowing `params`'s value type, so the call
        # itself is cast to its (correct, runtime-verified) return type at this
        # unstubbed-precision edge (D-01; mirrors sync Database.to_geodataframe).
        async with self.async_engine.connect() as conn:
            return cast(
                "gpd.GeoDataFrame",
                await conn.run_sync(
                    lambda sync_conn: gpd.read_postgis(  # type: ignore[call-overload]
                        text(sql), sync_conn, geom_col=geometry_column, params=params
                    )
                ),
            )

    async def from_geodataframe(
        self,
        gdf: gpd.GeoDataFrame,
        table: str,
        *,
        schema: str = "public",
        if_exists: Literal["fail", "replace", "append"] = "fail",
        primary_key: str | list[str] | None = None,
        spatial_index: bool = True,
        geometry_column: str = "geometry",
        srid: int | None = None,
    ) -> None:
        """Create or append to table from GeoDataFrame.

        Requires PostGIS extension.

        Parameters
        ----------
        gdf : gpd.GeoDataFrame
            geopandas GeoDataFrame.
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".
        if_exists : {'fail', 'replace', 'append'}, optional
            What to do if table exists, by default "fail".
        primary_key : str or list of str, optional
            Column(s) for primary key.
        spatial_index : bool, optional
            Create GIST spatial index on geometry, by default True.
        geometry_column : str, optional
            Name of geometry column, by default "geometry".
        srid : int, optional
            Override SRID (extracted from CRS if not specified).

        Raises
        ------
        ExtensionNotAvailableError
            If PostGIS extension is not installed.
        """
        # Ensure PostGIS is available
        if not await self.schema.has_extension("postgis"):
            raise ExtensionNotAvailableError(
                "PostGIS extension not installed. Run db.schema.create_extension('postgis')"
            )

        validate_identifiers(table, schema)

        with log_operation("database.from_geodataframe", rows=len(gdf)):
            # Handle SRID — fail explicitly on unknown CRS instead of silently defaulting
            if srid is None:
                if gdf.crs is None:
                    raise ValueError(
                        "GeoDataFrame has no CRS defined. "
                        "Set gdf.crs or provide explicit srid parameter."
                    )
                try:
                    srid = gdf.crs.to_epsg()
                    if srid is None:
                        raise ValueError(
                            f"Cannot determine EPSG code for CRS: {gdf.crs}. "
                            f"Provide explicit srid parameter."
                        )
                except ValueError:
                    raise
                except Exception as e:
                    raise ValueError(
                        f"Failed to infer SRID from CRS {gdf.crs}. "
                        f"Provide explicit srid parameter. Error: {e}"
                    ) from e

            async with self.async_engine.connect() as conn:
                await conn.run_sync(
                    lambda sync_conn: gdf.to_postgis(
                        name=table,
                        con=sync_conn,
                        schema=schema,
                        if_exists=if_exists,
                        index=False,
                    )
                )

            if primary_key and if_exists != "append":
                await self.schema.add_primary_key(table, primary_key, schema=schema)

            if spatial_index and if_exists != "append":
                await self.spatial.create_spatial_index(
                    table, column=geometry_column, schema=schema
                )

    # =========================================================================
    # BATCH OPERATIONS
    # =========================================================================

    async def insert_many(
        self,
        table: str,
        rows: list[dict[str, Any]],
        *,
        schema: str = "public",
        on_conflict: str | None = None,
    ) -> int:
        """Insert multiple rows efficiently.

        Parameters
        ----------
        table : str
            Table name.
        rows : list of dict
            List of row dicts.
        schema : str, optional
            Schema name, by default "public".
        on_conflict : str, optional
            ON CONFLICT clause (e.g., "DO NOTHING", "DO UPDATE SET ...").

        Returns
        -------
        int
            Number of rows inserted.
        """
        if not rows:
            return 0

        columns = list(rows[0].keys())
        sql, params = self._build_batch_insert_sql(
            table, columns, rows, schema, on_conflict
        )

        async with self.cursor() as cur:
            await cur.execute(sql, params)
            return cur.rowcount

    async def upsert_many(
        self,
        table: str,
        rows: list[dict[str, Any]],
        conflict_columns: list[str],
        *,
        update_columns: list[str] | None = None,
        schema: str = "public",
    ) -> int:
        """Upsert (insert or update) multiple rows.

        Parameters
        ----------
        table : str
            Table name.
        rows : list of dict
            List of row dicts.
        conflict_columns : list of str
            Columns that define uniqueness.
        update_columns : list of str, optional
            Columns to update on conflict (None = all except conflict).
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        int
            Number of rows affected.
        """
        if not rows:
            return 0

        columns = list(rows[0].keys())
        if update_columns is None:
            update_columns = [c for c in columns if c not in conflict_columns]

        validate_identifiers(*conflict_columns)
        validate_identifiers(*update_columns)

        conflict_str = ", ".join(conflict_columns)
        update_str = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_columns])

        on_conflict = f"({conflict_str}) DO UPDATE SET {update_str}"

        return await self.insert_many(
            table, rows, schema=schema, on_conflict=on_conflict
        )

    async def upsert(
        self,
        table: str,
        row: dict[str, Any],
        conflict_columns: list[str],
        *,
        update_columns: list[str] | None = None,
        schema: str = "public",
    ) -> dict[str, Any] | None:
        """Upsert a single row and return the affected row.

        Parameters
        ----------
        table : str
            Table name.
        row : dict
            Row data as column-name to value mapping.
        conflict_columns : list of str
            Columns that define uniqueness for the ON CONFLICT target.
        update_columns : list of str, optional
            Columns to update on conflict. Defaults to all non-conflict columns.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        dict or None
            The affected row as a dict (via ``RETURNING *``). Under DO UPDATE
            the return is structurally always a dict; None is a defensive guard
            for a future no-row path and is not reachable under the current SQL.

        Raises
        ------
        ValueError
            If ``update_columns`` resolves to an empty list — i.e. all columns
            in ``row`` are also listed in ``conflict_columns`` and no explicit
            ``update_columns`` override is given.
        """
        columns = list(row.keys())
        if update_columns is None:
            update_columns = [c for c in columns if c not in conflict_columns]
        if not update_columns:
            raise ValueError(
                "upsert: no non-conflict columns to update. Provide "
                "update_columns explicitly, or include a non-conflict column "
                "in 'row'."
            )

        validate_identifiers(*conflict_columns)
        validate_identifiers(*update_columns)

        conflict_str = ", ".join(conflict_columns)
        update_str = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_columns])
        on_conflict = f"({conflict_str}) DO UPDATE SET {update_str}"

        sql, _ = self._build_insert_sql(table, columns, schema, on_conflict)
        sql += " RETURNING *"
        params = [row[c] for c in columns]

        async with self.cursor() as cur:
            await cur.execute(sql, params)
            return await cur.fetchone()

    async def insert(
        self,
        table: str,
        row: dict[str, Any],
        *,
        schema: str = "public",
        on_conflict: str | None = None,
    ) -> dict[str, Any] | None:
        """Insert a single row and return the inserted row.

        The singular twin of :meth:`insert_many` / :meth:`upsert` — for
        inserting exactly one row without forcing a 1-element list through
        :meth:`insert_many`. Unlike :meth:`upsert`, ``on_conflict`` is a raw
        passthrough string (mirroring :meth:`insert_many`'s shape, D-06),
        not computed from a conflict/update column list.

        Parameters
        ----------
        table : str
            Table name.
        row : dict
            Row data as column-name to value mapping.
        schema : str, optional
            Schema name, by default "public".
        on_conflict : str, optional
            ON CONFLICT clause (e.g., "DO NOTHING", "DO UPDATE SET ..."),
            threaded verbatim into the INSERT statement.

        Returns
        -------
        dict or None
            The inserted row as a dict (via ``RETURNING *``). Under
            ``on_conflict="DO NOTHING"``, if a pre-existing row conflicts, no
            row is returned by ``RETURNING *`` and this method returns
            ``None`` (D-07).

        Raises
        ------
        ValueError
            If ``row`` is empty (WR-01) — an empty dict would otherwise emit
            invalid SQL (``INSERT INTO t () VALUES ()``).
        """
        if not row:
            raise ValueError("insert: 'row' must be a non-empty dict.")
        columns = list(row.keys())
        sql, _ = self._build_insert_sql(table, columns, schema, on_conflict)
        sql += " RETURNING *"
        params = [row[c] for c in columns]

        async with self.cursor() as cur:
            await cur.execute(sql, params)
            return await cur.fetchone()

    async def delete_where(
        self,
        table: str,
        where: dict[str, Any] | None = None,
        *,
        where_sql: str | None = None,
        where_params: Sequence[Any] | None = None,
        schema: str = "public",
    ) -> int:
        """Delete rows matching the given equality conditions.

        Parameters
        ----------
        table : str
            Table name.
        where : dict, optional
            Equality conditions as column-name to value mapping. Mutually
            exclusive with ``where_sql`` (D-02). Exactly one of ``where`` /
            ``where_sql`` must resolve to a non-empty predicate — use
            db.schema.truncate_table to affect all rows.
        where_sql : str, optional
            Raw SQL WHERE fragment (without the ``WHERE`` keyword), for
            predicates the ``where`` dict cannot express (e.g.
            ``"created_at < now() - %s::interval"``). This is a documented
            escape hatch: the fragment is passed through **verbatim** and is
            **not** run through identifier validation — the caller owns the
            SQL text. Only ``where_params`` are treated as untrusted values
            and bound as ``%s``.
        where_params : Sequence, optional
            Positional ``%s`` parameters bound against ``where_sql``.
            Requires ``where_sql`` to be present (D-04).
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        int
            Number of rows deleted.

        Raises
        ------
        ValueError
            If neither ``where`` nor ``where_sql`` resolves to a non-empty
            predicate (destructive guard); if both ``where`` and
            ``where_sql`` are supplied (D-02); if ``where_params`` is
            supplied without ``where_sql`` (D-04); or if ``where_sql`` is
            empty/whitespace-only (D-03).
        """
        frag, pred_params = self._resolve_predicate(where, where_sql, where_params)
        if not frag:
            raise ValueError(
                "delete_where requires a non-empty 'where' dict or 'where_sql' "
                "fragment. To delete all rows use db.schema.truncate_table."
            )
        validate_identifiers(table, schema)
        sql = f"DELETE FROM {schema}.{table} WHERE {frag}"
        async with self.cursor() as cur:
            await cur.execute(sql, pred_params)
            return cur.rowcount

    async def update_where(
        self,
        table: str,
        values: dict[str, Any],
        where: dict[str, Any] | None = None,
        *,
        where_sql: str | None = None,
        where_params: Sequence[Any] | None = None,
        schema: str = "public",
    ) -> int:
        """Update rows matching the given equality conditions.

        Parameters
        ----------
        table : str
            Table name.
        values : dict
            Column-name to new-value mapping for the SET clause. Must be
            non-empty.
        where : dict, optional
            Equality conditions as column-name to value mapping. Mutually
            exclusive with ``where_sql`` (D-02). Exactly one of ``where`` /
            ``where_sql`` must resolve to a non-empty predicate — use execute
            with an explicit UPDATE statement to affect all rows.
        where_sql : str, optional
            Raw SQL WHERE fragment (without the ``WHERE`` keyword), for
            predicates the ``where`` dict cannot express. This is a
            documented escape hatch: the fragment is passed through
            **verbatim** and is **not** run through identifier validation —
            the caller owns the SQL text. Only ``where_params`` are treated
            as untrusted values and bound as ``%s``.
        where_params : Sequence, optional
            Positional ``%s`` parameters bound against ``where_sql``.
            Requires ``where_sql`` to be present (D-04).
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        int
            Number of rows updated.

        Raises
        ------
        ValueError
            If ``values`` is empty; if neither ``where`` nor ``where_sql``
            resolves to a non-empty predicate (destructive guard); if both
            ``where`` and ``where_sql`` are supplied (D-02); if
            ``where_params`` is supplied without ``where_sql`` (D-04); or if
            ``where_sql`` is empty/whitespace-only (D-03).
        """
        if not values:
            raise ValueError("update_where requires a non-empty 'values' dict.")
        frag, pred_params = self._resolve_predicate(where, where_sql, where_params)
        if not frag:
            raise ValueError(
                "update_where requires a non-empty 'where' dict or 'where_sql' "
                "fragment. To update all rows use execute with an explicit "
                "SQL statement."
            )
        validate_identifiers(table, schema)
        validate_identifiers(*values.keys())
        set_clause = ", ".join(f"{col} = %s" for col in values)
        sql = f"UPDATE {schema}.{table} SET {set_clause} WHERE {frag}"
        params = list(values.values()) + pred_params
        async with self.cursor() as cur:
            await cur.execute(sql, params)
            return cur.rowcount

    # =========================================================================
    # STREAMING
    # =========================================================================

    async def stream(
        self,
        sql: str,
        params: Sequence[Any] | None = None,
        *,
        batch_size: int = 1000,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream query results in batches.

        Memory-efficient way to process large result sets.

        Parameters
        ----------
        sql : str
            SQL query.
        params : Sequence, optional
            Query parameters.
        batch_size : int, optional
            Rows to fetch per batch, by default 1000.

        Yields
        ------
        dict
            Row dicts.
        """
        # Use session-aware cursor() — mirrors Database.stream() parity (WR-02)
        async with self.cursor() as cur:
            await cur.execute(sql, params)
            while True:
                rows = await cur.fetchmany(batch_size)
                if not rows:
                    break
                for row in rows:
                    yield row

    # =========================================================================
    # LISTEN/NOTIFY
    # =========================================================================

    async def listen(self, channel: str) -> AsyncIterator[str]:
        """Listen for notifications on a channel.

        Parameters
        ----------
        channel : str
            Channel name.

        Yields
        ------
        str
            Notification payloads.
        """
        validate_identifier(channel)

        async with self.connect(autocommit=True) as conn:
            await conn.execute(f"LISTEN {channel}")
            async for notify in conn.notifies():
                yield notify.payload

    async def notify(self, channel: str, *, payload: str = "") -> None:
        """Send notification on a channel.

        Parameters
        ----------
        channel : str
            Channel name.
        payload : str, optional
            Notification payload (max 8000 bytes), by default "".
        """
        validate_identifier(channel)
        # NOTIFY is a utility statement and cannot bind the payload as a
        # parameter; use the pg_notify() function so the payload is safely
        # parameterized. The channel is validated above before interpolation.
        await self.execute(
            "SELECT pg_notify(%s, %s)", [channel, payload], autocommit=True
        )

    async def close(self) -> None:
        """Close database connections.

        Disposes the async SQLAlchemy engine (releasing pooled connections)
        if one was created. Per-operation connections are opened and closed
        on demand, so only the lazily-created engine needs disposal here.
        Idempotent: safe to call when no engine exists or repeatedly.
        """
        if self._async_engine is not None:
            await self._async_engine.dispose()
            self._async_engine = None

    async def __aenter__(self) -> AsyncDatabase:
        """Enter the async context manager, returning self."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager and close the connection."""
        await self.close()
