"""
Async Database class for pycopg.

Provides async/await interface for PostgreSQL operations using psycopg's async support.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import psycopg
from psycopg import AsyncConnection, AsyncCursor, OperationalError
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
    QueryMixin,
    build_pg_dump_cmd,
    build_pg_restore_cmd,
    build_role_options,
)
from pycopg.config import Config
from pycopg.exceptions import DatabaseExists, ExtensionNotAvailable
from pycopg.utils import (
    validate_csv_option,
    validate_extension_name,
    validate_identifier,
    validate_identifiers,
    validate_index_method,
    validate_interval,
    validate_object_type,
    validate_privileges,
    validate_timestamp,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import geopandas as gpd
    import pandas as pd
    from sqlalchemy.ext.asyncio import AsyncEngine

    from pycopg.spatial import AsyncSpatialAccessor


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
        DatabaseExists
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
                        raise DatabaseExists(f"Database '{name}' already exists")
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
    async def cursor(self, autocommit: bool = False) -> AsyncIterator[AsyncCursor]:
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
                    if status == TransactionStatus.INTRANS:
                        await self._session_conn.commit()
                    elif status == TransactionStatus.INERROR:
                        await self._session_conn.rollback()
                    # IDLE: no open transaction, nothing to do
                    # ACTIVE: should not occur at cursor exit
                    # UNKNOWN: connection in bad state, skip
        else:
            async with self.connect(autocommit=autocommit) as conn:
                async with conn.cursor(row_factory=dict_row) as cur:
                    yield cur
                    if not autocommit:
                        await conn.commit()

    @asynccontextmanager
    async def session(self, autocommit: bool = False) -> AsyncIterator[AsyncDatabase]:
        """Async context manager for session mode with connection reuse.

        In session mode, all operations reuse the same connection,
        significantly reducing overhead for multiple sequential operations.

        Parameters
        ----------
        autocommit : bool, optional
            Enable autocommit mode for the session, by default False.

        Yields
        ------
        AsyncDatabase
            Self (AsyncDatabase instance with active session).
        """
        if self._session_conn is not None:
            raise RuntimeError(
                "Already in session mode. Nested sessions are not supported."
            )

        self._session_conn = await psycopg.AsyncConnection.connect(
            **self.config.connect_params(), autocommit=autocommit
        )
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
    async def transaction(self) -> AsyncIterator[AsyncConnection]:
        """Async context manager for transactions.

        Automatically commits on success, rolls back on exception.
        If a session is active, reuses the session connection.

        Yields
        ------
        AsyncConnection
            psycopg AsyncConnection in a transaction.
        """
        if self._session_conn is not None:
            # Reuse existing session connection
            async with self._session_conn.transaction():
                yield self._session_conn
        else:
            # Create new connection
            async with self.connect() as conn:
                async with conn.transaction():
                    yield conn

    async def execute(
        self,
        sql: str,
        params: Sequence | None = None,
        autocommit: bool = False,
    ) -> list[dict]:
        """Execute SQL and return results as list of dicts.

        Parameters
        ----------
        sql : str
            SQL query to execute.
        params : Sequence, optional
            Query parameters.
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

    async def execute_many(self, sql: str, params_seq: Sequence[Sequence]) -> int:
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
        rows: list[dict],
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

                placeholders = []
                params = []
                for row in batch:
                    row_placeholders = ", ".join(["%s"] * len(columns))
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
        rows: list[dict],
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

    async def fetch_one(self, sql: str, params: Sequence | None = None) -> dict | None:
        """Execute SQL and return single row.

        Parameters
        ----------
        sql : str
            SQL query.
        params : Sequence, optional
            Query parameters.

        Returns
        -------
        dict or None
            Single row as dict, or None.
        """
        async with self.cursor() as cur:
            await cur.execute(sql, params)
            return await cur.fetchone()

    async def fetch_val(self, sql: str, params: Sequence | None = None) -> Any:
        """Execute SQL and return single value.

        Parameters
        ----------
        sql : str
            SQL query returning single column.
        params : Sequence, optional
            Query parameters.

        Returns
        -------
        Any
            Single value, or None.
        """
        row = await self.fetch_one(sql, params)
        if row:
            return list(row.values())[0]
        return None

    # =========================================================================
    # SCHEMAS & TABLES
    # =========================================================================

    async def list_schemas(self) -> list[str]:
        """List all schemas.

        Returns
        -------
        list of str
            List of schema names.
        """
        result = await self.execute(queries.LIST_SCHEMAS)
        return [r["schema_name"] for r in result]

    async def schema_exists(self, name: str) -> bool:
        """Check if a schema exists.

        Parameters
        ----------
        name : str
            Schema name.

        Returns
        -------
        bool
            True if schema exists.
        """
        result = await self.execute(queries.SCHEMA_EXISTS, [name])
        return len(result) > 0

    async def create_schema(
        self, name: str, if_not_exists: bool = True, owner: str | None = None
    ) -> None:
        """Create a schema.

        Parameters
        ----------
        name : str
            Schema name.
        if_not_exists : bool, optional
            Don't error if schema exists, by default True.
        owner : str, optional
            Owner role.
        """
        validate_identifier(name)
        if owner:
            validate_identifier(owner)
        if_clause = "IF NOT EXISTS " if if_not_exists else ""
        owner_clause = f" AUTHORIZATION {owner}" if owner else ""
        await self.execute(f"CREATE SCHEMA {if_clause}{name}{owner_clause}")

    async def list_tables(self, schema: str = "public") -> list[str]:
        """List tables in a schema.

        Parameters
        ----------
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of str
            List of table names.
        """
        result = await self.execute(queries.LIST_TABLES, [schema])
        return [r["table_name"] for r in result]

    async def table_exists(self, name: str, schema: str = "public") -> bool:
        """Check if a table exists.

        Parameters
        ----------
        name : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        bool
            True if table exists.
        """
        result = await self.execute(queries.TABLE_EXISTS, [schema, name])
        return len(result) > 0

    async def list_columns(self, table: str, schema: str = "public") -> list[str]:
        """Get list of column names for a table.

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of str
            List of column names in ordinal order.
        """
        result = await self.execute(queries.GET_COLUMNS, [schema, table])
        return [row["column_name"] for row in result]

    async def columns_with_types(
        self, table: str, schema: str = "public"
    ) -> list[tuple[str, str]]:
        """Get list of (column_name, data_type) tuples for a table.

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of tuple of (str, str)
            List of (name, type) tuples in ordinal order.
        """
        result = await self.execute(queries.GET_COLUMNS, [schema, table])
        return [(row["column_name"], row["data_type"]) for row in result]

    async def table_info(self, name: str, schema: str = "public") -> list[dict]:
        """Get column information for a table.

        Parameters
        ----------
        name : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of dict
            List of column info dicts with column_name, data_type, is_nullable,
            column_default, ordinal_position.
        """
        return await self.execute(queries.TABLE_INFO, [schema, name])

    async def row_count(self, name: str, schema: str = "public") -> int:
        """Get approximate row count for a table.

        Uses pg_stat for speed. For exact count, use execute("SELECT COUNT(*)...").

        Parameters
        ----------
        name : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        int
            Approximate row count.
        """
        result = await self.execute(queries.ROW_COUNT, [schema, name])
        return result[0]["count"] if result else 0

    async def drop_schema(
        self, name: str, if_exists: bool = True, cascade: bool = False
    ) -> None:
        """Drop a schema.

        Parameters
        ----------
        name : str
            Schema name.
        if_exists : bool, optional
            Don't error if schema doesn't exist, by default True.
        cascade : bool, optional
            Drop all objects in schema, by default False.
        """
        validate_identifier(name)
        if_clause = "IF EXISTS " if if_exists else ""
        cascade_clause = " CASCADE" if cascade else ""
        await self.execute(f"DROP SCHEMA {if_clause}{name}{cascade_clause}")

    async def drop_table(
        self,
        name: str,
        schema: str = "public",
        if_exists: bool = True,
        cascade: bool = False,
    ) -> None:
        """Drop a table.

        Parameters
        ----------
        name : str
            Table name.
        schema : str, optional
            Schema name, by default "public".
        if_exists : bool, optional
            Don't error if table doesn't exist, by default True.
        cascade : bool, optional
            Drop dependent objects, by default False.
        """
        validate_identifiers(name, schema)
        if_clause = "IF EXISTS " if if_exists else ""
        cascade_clause = " CASCADE" if cascade else ""
        await self.execute(f"DROP TABLE {if_clause}{schema}.{name}{cascade_clause}")

    async def truncate_table(
        self, name: str, schema: str = "public", cascade: bool = False
    ) -> None:
        """Truncate a table (delete all rows).

        Parameters
        ----------
        name : str
            Table name.
        schema : str, optional
            Schema name, by default "public".
        cascade : bool, optional
            Truncate dependent tables, by default False.
        """
        validate_identifiers(name, schema)
        cascade_clause = " CASCADE" if cascade else ""
        await self.execute(f"TRUNCATE TABLE {schema}.{name}{cascade_clause}")

    # =========================================================================
    # CONSTRAINTS & INDEXES
    # =========================================================================

    async def add_primary_key(
        self,
        table: str,
        columns: str | list[str],
        schema: str = "public",
        name: str | None = None,
    ) -> None:
        """Add primary key constraint to a table.

        Parameters
        ----------
        table : str
            Table name.
        columns : str or list of str
            Column name or list of column names.
        schema : str, optional
            Schema name, by default "public".
        name : str, optional
            Constraint name.
        """
        if isinstance(columns, str):
            columns = [columns]
        validate_identifiers(table, schema, *columns)
        if name:
            validate_identifier(name)

        cols_str = ", ".join(columns)
        constraint_name = name or f"{table}_pkey"
        await self.execute(
            f"ALTER TABLE {schema}.{table} ADD CONSTRAINT {constraint_name} PRIMARY KEY ({cols_str})"
        )

    async def add_foreign_key(
        self,
        table: str,
        columns: str | list[str],
        ref_table: str,
        ref_columns: str | list[str],
        schema: str = "public",
        ref_schema: str = "public",
        name: str | None = None,
        on_delete: str = "NO ACTION",
        on_update: str = "NO ACTION",
    ) -> None:
        """Add foreign key constraint.

        Parameters
        ----------
        table : str
            Source table name.
        columns : str or list of str
            Source column(s).
        ref_table : str
            Referenced table name.
        ref_columns : str or list of str
            Referenced column(s).
        schema : str, optional
            Source table schema, by default "public".
        ref_schema : str, optional
            Referenced table schema, by default "public".
        name : str, optional
            Constraint name.
        on_delete : str, optional
            ON DELETE action (CASCADE, SET NULL, NO ACTION, etc.), by default "NO ACTION".
        on_update : str, optional
            ON UPDATE action, by default "NO ACTION".
        """
        if isinstance(columns, str):
            columns = [columns]
        if isinstance(ref_columns, str):
            ref_columns = [ref_columns]

        # Validate all identifiers
        validate_identifiers(
            table, schema, ref_table, ref_schema, *columns, *ref_columns
        )
        if name:
            validate_identifier(name)

        # Validate ON DELETE/UPDATE actions
        valid_actions = {"NO ACTION", "RESTRICT", "CASCADE", "SET NULL", "SET DEFAULT"}
        if on_delete.upper() not in valid_actions:
            raise ValueError(
                f"Invalid ON DELETE action: {on_delete}. Must be one of: {valid_actions}"
            )
        if on_update.upper() not in valid_actions:
            raise ValueError(
                f"Invalid ON UPDATE action: {on_update}. Must be one of: {valid_actions}"
            )

        cols_str = ", ".join(columns)
        ref_cols_str = ", ".join(ref_columns)
        constraint_name = name or f"{table}_{columns[0]}_fkey"

        await self.execute(f"""
            ALTER TABLE {schema}.{table}
            ADD CONSTRAINT {constraint_name}
            FOREIGN KEY ({cols_str})
            REFERENCES {ref_schema}.{ref_table} ({ref_cols_str})
            ON DELETE {on_delete}
            ON UPDATE {on_update}
        """)

    async def add_unique_constraint(
        self,
        table: str,
        columns: str | list[str],
        schema: str = "public",
        name: str | None = None,
    ) -> None:
        """Add unique constraint.

        Parameters
        ----------
        table : str
            Table name.
        columns : str or list of str
            Column(s) to make unique.
        schema : str, optional
            Schema name, by default "public".
        name : str, optional
            Constraint name.
        """
        if isinstance(columns, str):
            columns = [columns]
        validate_identifiers(table, schema, *columns)
        if name:
            validate_identifier(name)
        cols_str = ", ".join(columns)
        constraint_name = name or f"{table}_{'_'.join(columns)}_key"
        await self.execute(
            f"ALTER TABLE {schema}.{table} ADD CONSTRAINT {constraint_name} UNIQUE ({cols_str})"
        )

    async def create_index(
        self,
        table: str,
        columns: str | list[str],
        schema: str = "public",
        name: str | None = None,
        unique: bool = False,
        method: str = "btree",
        if_not_exists: bool = True,
    ) -> None:
        """Create an index.

        Parameters
        ----------
        table : str
            Table name.
        columns : str or list of str
            Column(s) to index.
        schema : str, optional
            Schema name, by default "public".
        name : str, optional
            Index name (auto-generated if not provided).
        unique : bool, optional
            Create unique index, by default False.
        method : str, optional
            Index method (btree, hash, gist, gin, etc.), by default "btree".
        if_not_exists : bool, optional
            Don't error if index exists, by default True.
        """
        if isinstance(columns, str):
            columns = [columns]
        validate_identifiers(table, schema, *columns)
        if name:
            validate_identifier(name)
        validate_index_method(method)

        cols_str = ", ".join(columns)
        index_name = name or f"idx_{table}_{'_'.join(columns)}"
        unique_clause = "UNIQUE " if unique else ""
        if_clause = "IF NOT EXISTS " if if_not_exists else ""

        await self.execute(f"""
            CREATE {unique_clause}INDEX {if_clause}{index_name}
            ON {schema}.{table} USING {method} ({cols_str})
        """)

    async def drop_index(
        self, name: str, schema: str = "public", if_exists: bool = True
    ) -> None:
        """Drop an index.

        Parameters
        ----------
        name : str
            Index name.
        schema : str, optional
            Schema name, by default "public".
        if_exists : bool, optional
            Don't error if index doesn't exist, by default True.
        """
        validate_identifiers(schema, name)
        if_clause = "IF EXISTS " if if_exists else ""
        await self.execute(f"DROP INDEX {if_clause}{schema}.{name}")

    async def list_indexes(self, table: str, schema: str = "public") -> list[dict]:
        """List indexes on a table.

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of dict
            List of index info dicts.
        """
        return await self.execute(queries.LIST_INDEXES, [schema, table])

    async def list_constraints(self, table: str, schema: str = "public") -> list[dict]:
        """List constraints on a table.

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        list of dict
            List of constraint info dicts.
        """
        return await self.execute(queries.LIST_CONSTRAINTS, [schema, table])

    # =========================================================================
    # EXTENSIONS
    # =========================================================================

    async def has_extension(self, name: str) -> bool:
        """Check if an extension is installed.

        Parameters
        ----------
        name : str
            Extension name.

        Returns
        -------
        bool
            True if extension is installed.
        """
        result = await self.execute(queries.EXTENSION_EXISTS, [name])
        return len(result) > 0

    async def create_extension(
        self, name: str, schema: str | None = None, if_not_exists: bool = True
    ) -> None:
        """Create a PostgreSQL extension.

        Parameters
        ----------
        name : str
            Extension name (e.g., 'postgis', 'timescaledb', 'uuid-ossp').
        schema : str, optional
            Schema to install extension in.
        if_not_exists : bool, optional
            Don't error if extension exists, by default True.
        """
        validate_extension_name(name)
        if schema:
            validate_identifier(schema)
        if_clause = "IF NOT EXISTS " if if_not_exists else ""
        schema_clause = f" SCHEMA {schema}" if schema else ""
        await self.execute(
            f'CREATE EXTENSION {if_clause}"{name}"{schema_clause}', autocommit=True
        )

    async def list_extensions(self) -> list[dict]:
        """List installed extensions.

        Returns
        -------
        list of dict
            List of dicts with extname, extversion, nspname (schema).
        """
        return await self.execute(queries.LIST_EXTENSIONS)

    async def drop_extension(
        self, name: str, if_exists: bool = True, cascade: bool = False
    ) -> None:
        """Drop a PostgreSQL extension.

        Parameters
        ----------
        name : str
            Extension name.
        if_exists : bool, optional
            Don't error if extension doesn't exist, by default True.
        cascade : bool, optional
            Drop dependent objects, by default False.
        """
        validate_extension_name(name)
        if_clause = "IF EXISTS " if if_exists else ""
        cascade_clause = " CASCADE" if cascade else ""
        await self.execute(
            f'DROP EXTENSION {if_clause}"{name}"{cascade_clause}', autocommit=True
        )

    # =========================================================================
    # POSTGIS SPATIAL OPERATIONS
    # =========================================================================

    async def create_spatial_index(
        self,
        table: str,
        column: str = "geometry",
        schema: str = "public",
        name: str | None = None,
    ) -> None:
        """Create a GIST spatial index on a geometry column.

        Parameters
        ----------
        table : str
            Table name.
        column : str, optional
            Geometry column name, by default "geometry".
        schema : str, optional
            Schema name, by default "public".
        name : str, optional
            Index name (auto-generated if not provided).
        """
        validate_identifiers(table, column, schema)
        if name:
            validate_identifier(name)
        index_name = name or f"idx_{table}_{column}_gist"
        await self.execute(f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {schema}.{table} USING GIST ({column})
        """)

    async def list_geometry_columns(self, schema: str | None = None) -> list[dict]:
        """List geometry columns in the database.

        Parameters
        ----------
        schema : str, optional
            Schema filter.

        Returns
        -------
        list of dict
            List of geometry column info.
        """
        where_clause = "WHERE f_table_schema = %s" if schema else ""
        params = [schema] if schema else None
        return await self.execute(
            queries.LIST_GEOMETRY_COLUMNS.format(where_clause=where_clause),
            params,
        )

    # =========================================================================
    # TIMESCALEDB OPERATIONS
    # =========================================================================

    async def create_hypertable(
        self,
        table: str,
        time_column: str,
        schema: str = "public",
        chunk_time_interval: str = "1 day",
        if_not_exists: bool = True,
        migrate_data: bool = True,
    ) -> None:
        """Convert a table to a TimescaleDB hypertable.

        Requires TimescaleDB extension.

        Parameters
        ----------
        table : str
            Table name (must exist with time column).
        time_column : str
            Name of the timestamp column.
        schema : str, optional
            Schema name, by default "public".
        chunk_time_interval : str, optional
            Chunk time interval (e.g., '1 day', '1 week'), by default "1 day".
        if_not_exists : bool, optional
            Don't error if already a hypertable, by default True.
        migrate_data : bool, optional
            Migrate existing data to chunks, by default True.

        Raises
        ------
        ExtensionNotAvailable
            If TimescaleDB extension is not installed.
        """
        if not await self.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. Run db.create_extension('timescaledb')"
            )

        validate_identifiers(table, schema, time_column)
        validate_interval(chunk_time_interval)

        await self.execute(f"""
            SELECT create_hypertable(
                '{schema}.{table}',
                '{time_column}',
                chunk_time_interval => INTERVAL '{chunk_time_interval}',
                if_not_exists => {str(if_not_exists).upper()},
                migrate_data => {str(migrate_data).upper()}
            )
        """)

    async def enable_compression(
        self,
        table: str,
        segment_by: str | list[str] | None = None,
        order_by: str | list[str] | None = None,
        schema: str = "public",
    ) -> None:
        """Enable compression on a hypertable.

        Parameters
        ----------
        table : str
            Hypertable name.
        segment_by : str or list of str, optional
            Column(s) to segment compressed data by.
        order_by : str or list of str, optional
            Column(s) to order compressed data by.
        schema : str, optional
            Schema name, by default "public".

        Raises
        ------
        ExtensionNotAvailable
            If TimescaleDB extension is not installed.
        """
        if not await self.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.create_extension('timescaledb')"
            )

        validate_identifiers(table, schema)

        settings = ["timescaledb.compress"]
        if segment_by:
            if isinstance(segment_by, str):
                segment_by = [segment_by]
            for col in segment_by:
                # Extract column name (may have DESC/ASC suffix)
                col_name = col.split()[0]
                validate_identifier(col_name)
            settings.append(
                f"timescaledb.compress_segmentby = '{','.join(segment_by)}'"
            )
        if order_by:
            if isinstance(order_by, str):
                order_by = [order_by]
            for col in order_by:
                col_name = col.split()[0]
                validate_identifier(col_name)
            settings.append(f"timescaledb.compress_orderby = '{','.join(order_by)}'")

        await self.execute(f"ALTER TABLE {schema}.{table} SET ({', '.join(settings)})")

    async def add_compression_policy(
        self,
        table: str,
        compress_after: str = "7 days",
        schema: str = "public",
    ) -> None:
        """Add automatic compression policy to hypertable.

        Parameters
        ----------
        table : str
            Hypertable name.
        compress_after : str, optional
            Compress chunks older than this interval, by default "7 days".
        schema : str, optional
            Schema name, by default "public".

        Raises
        ------
        ExtensionNotAvailable
            If TimescaleDB extension is not installed.
        """
        validate_identifiers(table, schema)
        validate_interval(compress_after)
        if not await self.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.create_extension('timescaledb')"
            )

        await self.execute(f"""
            SELECT add_compression_policy(
                '{schema}.{table}',
                compress_after => INTERVAL '{compress_after}'
            )
        """)

    async def add_retention_policy(
        self,
        table: str,
        drop_after: str,
        schema: str = "public",
    ) -> None:
        """Add automatic data retention policy to hypertable.

        Parameters
        ----------
        table : str
            Hypertable name.
        drop_after : str
            Drop chunks older than this interval.
        schema : str, optional
            Schema name, by default "public".

        Raises
        ------
        ExtensionNotAvailable
            If TimescaleDB extension is not installed.
        """
        validate_identifiers(table, schema)
        validate_interval(drop_after)
        if not await self.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.create_extension('timescaledb')"
            )

        await self.execute(f"""
            SELECT add_retention_policy(
                '{schema}.{table}',
                drop_after => INTERVAL '{drop_after}'
            )
        """)

    async def list_hypertables(self) -> list[dict]:
        """List all hypertables.

        Returns
        -------
        list of dict
            List of hypertable info dicts.

        Raises
        ------
        ExtensionNotAvailable
            If TimescaleDB extension is not installed.
        """
        if not await self.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.create_extension('timescaledb')"
            )

        return await self.execute(queries.LIST_HYPERTABLES)

    async def hypertable_info(self, table: str, schema: str = "public") -> dict:
        """Get detailed info about a hypertable.

        Parameters
        ----------
        table : str
            Hypertable name.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        dict
            Dict with hypertable details including size info.

        Raises
        ------
        ExtensionNotAvailable
            If TimescaleDB extension is not installed.
        """
        if not await self.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.create_extension('timescaledb')"
            )

        result = await self.execute(
            # %%I in queries.HYPERTABLE_INFO is escaped so psycopg passes a
            # literal %I through to PostgreSQL's format() function.
            queries.HYPERTABLE_INFO,
            [schema, table, schema, table],
        )
        return result[0] if result else {}

    # =========================================================================
    # ROLES
    # =========================================================================

    async def role_exists(self, name: str) -> bool:
        """Check if a role exists.

        Parameters
        ----------
        name : str
            Role name.

        Returns
        -------
        bool
            True if role exists.
        """
        result = await self.execute(queries.ROLE_EXISTS, [name])
        return len(result) > 0

    async def list_roles(self, include_system: bool = False) -> list[dict]:
        """List all roles.

        Parameters
        ----------
        include_system : bool, optional
            Include system roles (pg_*), by default False.

        Returns
        -------
        list of dict
            List of role info dicts.
        """
        where_clause = "" if include_system else "WHERE rolname NOT LIKE 'pg_%'"
        return await self.execute(queries.LIST_ROLES.format(where_clause=where_clause))

    # =========================================================================
    # ROLE MANAGEMENT
    # =========================================================================

    async def create_role(
        self,
        name: str,
        password: str | None = None,
        login: bool = True,
        superuser: bool = False,
        createdb: bool = False,
        createrole: bool = False,
        inherit: bool = True,
        replication: bool = False,
        connection_limit: int = -1,
        valid_until: str | None = None,
        in_roles: list[str] | None = None,
        if_not_exists: bool = True,
    ) -> None:
        """Create a database role/user.

        Parameters
        ----------
        name : str
            Role name.
        password : str, optional
            Role password (for login roles).
        login : bool, optional
            Can log in (True = user, False = group role), by default True.
        superuser : bool, optional
            Is superuser, by default False.
        createdb : bool, optional
            Can create databases, by default False.
        createrole : bool, optional
            Can create other roles, by default False.
        inherit : bool, optional
            Inherits privileges from member roles, by default True.
        replication : bool, optional
            Can initiate streaming replication, by default False.
        connection_limit : int, optional
            Max concurrent connections (-1 = unlimited), by default -1.
        valid_until : str, optional
            Password expiration (e.g., '2025-12-31').
        in_roles : list of str, optional
            List of roles to be a member of.
        if_not_exists : bool, optional
            Don't error if role exists, by default True.
        """
        validate_identifier(name)

        # Check if exists
        if if_not_exists and await self.role_exists(name):
            return

        options = build_role_options(
            login=login,
            superuser=superuser,
            createdb=createdb,
            createrole=createrole,
            inherit=inherit,
            replication=replication,
            connection_limit=connection_limit,
            password=password,
            valid_until=valid_until,
        )
        options_str = " ".join(options)

        if password:
            async with self.cursor(autocommit=True) as cur:
                await cur.execute(f"CREATE ROLE {name} WITH {options_str}", [password])
        else:
            await self.execute(
                f"CREATE ROLE {name} WITH {options_str}", autocommit=True
            )

        # Add to roles
        if in_roles:
            for role in in_roles:
                await self.grant_role(role, name)

    async def drop_role(self, name: str, if_exists: bool = True) -> None:
        """Drop a role.

        Parameters
        ----------
        name : str
            Role name.
        if_exists : bool, optional
            Don't error if role doesn't exist, by default True.
        """
        validate_identifier(name)
        if_clause = "IF EXISTS " if if_exists else ""
        await self.execute(f"DROP ROLE {if_clause}{name}", autocommit=True)

    async def alter_role(
        self,
        name: str,
        password: str | None = None,
        login: bool | None = None,
        superuser: bool | None = None,
        createdb: bool | None = None,
        createrole: bool | None = None,
        connection_limit: int | None = None,
        valid_until: str | None = None,
        rename_to: str | None = None,
    ) -> None:
        """Alter a role's attributes.

        Parameters
        ----------
        name : str
            Role name.
        password : str, optional
            New password.
        login : bool, optional
            Enable/disable login.
        superuser : bool, optional
            Enable/disable superuser.
        createdb : bool, optional
            Enable/disable createdb.
        createrole : bool, optional
            Enable/disable createrole.
        connection_limit : int, optional
            New connection limit.
        valid_until : str, optional
            New password expiration.
        rename_to : str, optional
            Rename the role.
        """
        validate_identifier(name)

        if rename_to:
            validate_identifier(rename_to)
            await self.execute(
                f"ALTER ROLE {name} RENAME TO {rename_to}", autocommit=True
            )
            return

        options = []
        params = []

        if password is not None:
            options.append("PASSWORD %s")
            params.append(password)
        if login is not None:
            options.append("LOGIN" if login else "NOLOGIN")
        if superuser is not None:
            options.append("SUPERUSER" if superuser else "NOSUPERUSER")
        if createdb is not None:
            options.append("CREATEDB" if createdb else "NOCREATEDB")
        if createrole is not None:
            options.append("CREATEROLE" if createrole else "NOCREATEROLE")
        if connection_limit is not None:
            options.append(f"CONNECTION LIMIT {connection_limit}")
        if valid_until is not None:
            validate_timestamp(valid_until)
            options.append(f"VALID UNTIL '{valid_until}'")

        if options:
            options_str = " ".join(options)
            async with self.cursor(autocommit=True) as cur:
                await cur.execute(
                    f"ALTER ROLE {name} WITH {options_str}", params if params else None
                )

    async def grant(
        self,
        privileges: str | list[str],
        on: str,
        to: str,
        object_type: str = "TABLE",
        schema: str = "public",
        with_grant_option: bool = False,
    ) -> None:
        """Grant privileges on database objects.

        Parameters
        ----------
        privileges : str or list of str
            Privilege(s) to grant (SELECT, INSERT, UPDATE, DELETE, ALL, etc.).
        on : str
            Object name or ALL TABLES/SEQUENCES/FUNCTIONS.
        to : str
            Role receiving privileges.
        object_type : str, optional
            Type of object (TABLE, SEQUENCE, FUNCTION, SCHEMA, DATABASE),
            by default "TABLE".
        schema : str, optional
            Schema name (for tables/sequences), by default "public".
        with_grant_option : bool, optional
            Allow grantee to grant to others, by default False.
        """
        validate_identifier(to)
        validate_object_type(object_type)

        if isinstance(privileges, list):
            privileges = ", ".join(privileges)
        validate_privileges(privileges)

        grant_clause = " WITH GRANT OPTION" if with_grant_option else ""

        if object_type.upper() == "SCHEMA":
            validate_identifier(on)
            await self.execute(
                f"GRANT {privileges} ON SCHEMA {on} TO {to}{grant_clause}",
                autocommit=True,
            )
        elif object_type.upper() == "DATABASE":
            validate_identifier(on)
            await self.execute(
                f"GRANT {privileges} ON DATABASE {on} TO {to}{grant_clause}",
                autocommit=True,
            )
        elif on.upper() in ("ALL TABLES", "ALL SEQUENCES", "ALL FUNCTIONS"):
            validate_identifier(schema)
            await self.execute(
                f"GRANT {privileges} ON {on} IN SCHEMA {schema} TO {to}{grant_clause}",
                autocommit=True,
            )
        else:
            validate_identifiers(on, schema)
            await self.execute(
                f"GRANT {privileges} ON {object_type} {schema}.{on} TO {to}{grant_clause}",
                autocommit=True,
            )

    async def revoke(
        self,
        privileges: str | list[str],
        on: str,
        from_role: str,
        object_type: str = "TABLE",
        schema: str = "public",
        cascade: bool = False,
    ) -> None:
        """Revoke privileges on database objects.

        Parameters
        ----------
        privileges : str or list of str
            Privilege(s) to revoke.
        on : str
            Object name or ALL TABLES/SEQUENCES/FUNCTIONS.
        from_role : str
            Role losing privileges.
        object_type : str, optional
            Type of object, by default "TABLE".
        schema : str, optional
            Schema name, by default "public".
        cascade : bool, optional
            Revoke from dependent privileges, by default False.
        """
        validate_identifier(from_role)
        validate_object_type(object_type)

        if isinstance(privileges, list):
            privileges = ", ".join(privileges)
        validate_privileges(privileges)

        cascade_clause = " CASCADE" if cascade else ""

        if object_type.upper() == "SCHEMA":
            validate_identifier(on)
            await self.execute(
                f"REVOKE {privileges} ON SCHEMA {on} FROM {from_role}{cascade_clause}",
                autocommit=True,
            )
        elif object_type.upper() == "DATABASE":
            validate_identifier(on)
            await self.execute(
                f"REVOKE {privileges} ON DATABASE {on} FROM {from_role}{cascade_clause}",
                autocommit=True,
            )
        elif on.upper() in ("ALL TABLES", "ALL SEQUENCES", "ALL FUNCTIONS"):
            validate_identifier(schema)
            await self.execute(
                f"REVOKE {privileges} ON {on} IN SCHEMA {schema} FROM {from_role}{cascade_clause}",
                autocommit=True,
            )
        else:
            validate_identifiers(on, schema)
            await self.execute(
                f"REVOKE {privileges} ON {object_type} {schema}.{on} FROM {from_role}{cascade_clause}",
                autocommit=True,
            )

    async def grant_role(
        self, role: str, member: str, with_admin: bool = False
    ) -> None:
        """Grant role membership to another role.

        Parameters
        ----------
        role : str
            Role to grant.
        member : str
            Role receiving membership.
        with_admin : bool, optional
            Allow member to grant role to others, by default False.
        """
        validate_identifiers(role, member)
        admin_clause = " WITH ADMIN OPTION" if with_admin else ""
        await self.execute(f"GRANT {role} TO {member}{admin_clause}", autocommit=True)

    async def revoke_role(self, role: str, member: str) -> None:
        """Revoke role membership from a role.

        Parameters
        ----------
        role : str
            Role to revoke.
        member : str
            Role losing membership.
        """
        validate_identifiers(role, member)
        await self.execute(f"REVOKE {role} FROM {member}", autocommit=True)

    async def list_role_members(self, role: str) -> list[str]:
        """List members of a role.

        Parameters
        ----------
        role : str
            Role name.

        Returns
        -------
        list of str
            List of member role names.
        """
        result = await self.execute(queries.LIST_ROLE_MEMBERS, [role])
        return [r["member"] for r in result]

    async def list_role_grants(self, role: str) -> list[dict]:
        """List privileges granted to a role.

        Parameters
        ----------
        role : str
            Role name.

        Returns
        -------
        list of dict
            List of privilege info dicts.
        """
        return await self.execute(queries.LIST_ROLE_GRANTS, [role])

    # =========================================================================
    # SIZE & STATS
    # =========================================================================

    async def size(self, pretty: bool = True) -> str | int:
        """Get database size.

        Parameters
        ----------
        pretty : bool, optional
            Return human-readable size (e.g., '1.2 GB'), by default True.

        Returns
        -------
        str or int
            Database size.
        """
        if pretty:
            result = await self.execute(
                queries.DATABASE_SIZE_PRETTY,
                [self.config.database],
            )
            return result[0]["size"]
        else:
            result = await self.execute(
                queries.DATABASE_SIZE, [self.config.database]
            )
            return result[0]["size"]

    async def table_size(
        self, table: str, schema: str = "public", pretty: bool = True
    ) -> str | int:
        """Get table size including indexes.

        Parameters
        ----------
        table : str
            Table name.
        schema : str, optional
            Schema name, by default "public".
        pretty : bool, optional
            Return human-readable size, by default True.

        Returns
        -------
        str or int
            Table size.
        """
        full_name = f"{schema}.{table}"
        if pretty:
            result = await self.execute(queries.TABLE_SIZE_PRETTY, [full_name])
            return result[0]["size"]
        else:
            result = await self.execute(queries.TABLE_SIZE, [full_name])
            return result[0]["size"]

    async def table_sizes(self, schema: str = "public", limit: int = 20) -> list[dict]:
        """Get sizes of all tables in schema, sorted by size.

        Parameters
        ----------
        schema : str, optional
            Schema name, by default "public".
        limit : int, optional
            Max tables to return, by default 20.

        Returns
        -------
        list of dict
            List of table size info.
        """
        # queries.TABLE_SIZES uses %%I (psycopg-escaped) so PostgreSQL format() sees %I
        return await self.execute(queries.TABLE_SIZES, [schema, limit])

    # =========================================================================
    # DATAFRAME OPERATIONS
    # =========================================================================

    async def to_dataframe(
        self,
        table: str | None = None,
        schema: str = "public",
        sql: str | None = None,
        params: dict | None = None,
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
        params : dict, optional
            Query parameters for sql.

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

        async with self.async_engine.connect() as conn:
            return await conn.run_sync(
                lambda sync_conn: pd.read_sql(text(sql), sync_conn, params=params)
            )

    async def from_dataframe(
        self,
        df: pd.DataFrame,
        table: str,
        schema: str = "public",
        if_exists: Literal["fail", "replace", "append"] = "fail",
        primary_key: str | list[str] | None = None,
        index: bool = False,
        dtype: dict | None = None,
    ) -> None:
        """Create or append to table from pandas DataFrame.

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
            Write DataFrame index as column, by default False.
        dtype : dict, optional
            Dict of column name to SQLAlchemy types.
        """
        async with self.async_engine.connect() as conn:
            await conn.run_sync(
                lambda sync_conn: df.to_sql(
                    name=table,
                    con=sync_conn,
                    schema=schema,
                    if_exists=if_exists,
                    index=index,
                    dtype=dtype,
                )
            )

        if primary_key and if_exists != "append":
            await self.add_primary_key(table, primary_key, schema)

    async def to_geodataframe(
        self,
        table: str | None = None,
        schema: str = "public",
        sql: str | None = None,
        geometry_column: str = "geometry",
        params: dict | None = None,
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

        async with self.async_engine.connect() as conn:
            return await conn.run_sync(
                lambda sync_conn: gpd.read_postgis(
                    text(sql), sync_conn, geom_col=geometry_column, params=params
                )
            )

    async def from_geodataframe(
        self,
        gdf: gpd.GeoDataFrame,
        table: str,
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
        ExtensionNotAvailable
            If PostGIS extension is not installed.
        """
        # Ensure PostGIS is available
        if not await self.has_extension("postgis"):
            raise ExtensionNotAvailable(
                "PostGIS extension not installed. Run db.create_extension('postgis')"
            )

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
            await self.add_primary_key(table, primary_key, schema)

        if spatial_index and if_exists != "append":
            await self.create_spatial_index(table, geometry_column, schema)

    # =========================================================================
    # BATCH OPERATIONS
    # =========================================================================

    async def insert_many(
        self,
        table: str,
        rows: list[dict],
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
        sql, params = self._build_batch_insert_sql(table, columns, rows, schema, on_conflict)

        async with self.cursor() as cur:
            await cur.execute(sql, params)
            return cur.rowcount

    async def upsert_many(
        self,
        table: str,
        rows: list[dict],
        conflict_columns: list[str],
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

        return await self.insert_many(table, rows, schema, on_conflict)

    # =========================================================================
    # STREAMING
    # =========================================================================

    async def stream(
        self,
        sql: str,
        params: Sequence | None = None,
        batch_size: int = 1000,
    ) -> AsyncIterator[dict]:
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
        async with self.connect() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(sql, params)
                while True:
                    rows = await cur.fetchmany(batch_size)
                    if not rows:
                        break
                    for row in rows:
                        yield row

    # =========================================================================
    # DATABASE ADMINISTRATION
    # =========================================================================

    async def create_database(
        self, name: str, owner: str | None = None, template: str = "template1"
    ) -> None:
        """Create a new database.

        Parameters
        ----------
        name : str
            Database name.
        owner : str, optional
            Owner role.
        template : str, optional
            Template database, by default "template1".
        """
        validate_identifier(name)
        if owner:
            validate_identifier(owner)
        validate_identifier(template)
        owner_clause = f" OWNER {owner}" if owner else ""
        # Connect to postgres for database creation
        admin_config = self.config.with_database("postgres")
        async with await psycopg.AsyncConnection.connect(
            **admin_config.connect_params(), autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"CREATE DATABASE {name}{owner_clause} TEMPLATE {template}"
                )

    async def drop_database(self, name: str, if_exists: bool = True) -> None:
        """Drop a database.

        Parameters
        ----------
        name : str
            Database name.
        if_exists : bool, optional
            Don't error if database doesn't exist, by default True.
        """
        validate_identifier(name)
        if_clause = "IF EXISTS " if if_exists else ""
        admin_config = self.config.with_database("postgres")
        async with await psycopg.AsyncConnection.connect(
            **admin_config.connect_params(), autocommit=True
        ) as conn:
            async with conn.cursor() as cur:
                # Terminate existing connections
                await cur.execute(
                    """
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = %s
                    AND pid <> pg_backend_pid()
                """,
                    [name],
                )
                await cur.execute(f"DROP DATABASE {if_clause}{name}")

    async def database_exists(self, name: str) -> bool:
        """Check if a database exists.

        Parameters
        ----------
        name : str
            Database name.

        Returns
        -------
        bool
            True if database exists.
        """
        admin_config = self.config.with_database("postgres")
        async with await psycopg.AsyncConnection.connect(
            **admin_config.connect_params()
        ) as conn:
            async with conn.cursor() as cur:
                await cur.execute(queries.DATABASE_EXISTS, [name])
                return await cur.fetchone() is not None

    async def list_databases(self) -> list[str]:
        """List all databases.

        Returns
        -------
        list of str
            List of database names.
        """
        result = await self.execute(queries.LIST_DATABASES)
        return [r["datname"] for r in result]

    # =========================================================================
    # UTILITY
    # =========================================================================

    async def vacuum(
        self,
        table: str | None = None,
        schema: str = "public",
        analyze: bool = True,
        full: bool = False,
    ) -> None:
        """Vacuum database or table.

        Parameters
        ----------
        table : str, optional
            Table name (None for whole database).
        schema : str, optional
            Schema name, by default "public".
        analyze : bool, optional
            Update statistics, by default True.
        full : bool, optional
            Full vacuum (reclaims more space but locks table), by default False.
        """
        options = []
        if full:
            options.append("FULL")
        if analyze:
            options.append("ANALYZE")

        if table:
            validate_identifiers(table, schema)

        options_str = f"({', '.join(options)})" if options else ""
        table_str = f" {schema}.{table}" if table else ""

        await self.execute(f"VACUUM{options_str}{table_str}", autocommit=True)

    async def analyze(self, table: str | None = None, schema: str = "public") -> None:
        """Update table statistics for query planner.

        Parameters
        ----------
        table : str, optional
            Table name (None for whole database).
        schema : str, optional
            Schema name, by default "public".
        """
        if table:
            validate_identifiers(table, schema)
        table_str = f" {schema}.{table}" if table else ""
        await self.execute(f"ANALYZE{table_str}", autocommit=True)

    async def explain(
        self,
        sql: str,
        params: Sequence | None = None,
        analyze: bool = False,
        format: str = "text",
    ) -> list[str]:
        """Get query execution plan.

        Parameters
        ----------
        sql : str
            SQL query.
        params : Sequence, optional
            Query parameters.
        analyze : bool, optional
            Actually run the query for real stats, by default False.
        format : str, optional
            Output format (text, json, xml, yaml), by default "text".

        Returns
        -------
        list of str
            Query plan lines.
        """
        options = [f"FORMAT {format.upper()}"]
        if analyze:
            options.append("ANALYZE")

        result = await self.execute(f"EXPLAIN ({', '.join(options)}) {sql}", params)
        return [r["QUERY PLAN"] for r in result]

    # =========================================================================
    # BACKUP & RESTORE
    # =========================================================================

    async def pg_dump(
        self,
        output_file: str | Path,
        format: Literal["plain", "custom", "directory", "tar"] = "custom",
        schema_only: bool = False,
        data_only: bool = False,
        tables: list[str] | None = None,
        exclude_tables: list[str] | None = None,
        schemas: list[str] | None = None,
        compress: int = 6,
        jobs: int = 1,
    ) -> None:
        """Backup database using pg_dump.

        Parameters
        ----------
        output_file : str or Path
            Output file path.
        format : {'plain', 'custom', 'directory', 'tar'}, optional
            Dump format (plain=SQL, custom=compressed, directory=parallel, tar),
            by default "custom".
        schema_only : bool, optional
            Dump only schema, no data, by default False.
        data_only : bool, optional
            Dump only data, no schema, by default False.
        tables : list of str, optional
            Only dump these tables.
        exclude_tables : list of str, optional
            Exclude these tables.
        schemas : list of str, optional
            Only dump these schemas.
        compress : int, optional
            Compression level (0-9, for custom format), by default 6.
        jobs : int, optional
            Parallel jobs (for directory format), by default 1.
        """
        cmd = build_pg_dump_cmd(
            host=self.config.host,
            port=self.config.port,
            user=self.config.user,
            database=self.config.database,
            output_file=output_file,
            format=format,
            schema_only=schema_only,
            data_only=data_only,
            tables=tables,
            exclude_tables=exclude_tables,
            schemas=schemas,
            compress=compress,
            jobs=jobs,
        )

        # Run with password in environment
        env = {**os.environ}
        if self.config.password:
            env["PGPASSWORD"] = self.config.password

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {stderr.decode()}")

    async def pg_restore(
        self,
        input_file: str | Path,
        clean: bool = False,
        if_exists: bool = True,
        create: bool = False,
        data_only: bool = False,
        schema_only: bool = False,
        tables: list[str] | None = None,
        schemas: list[str] | None = None,
        jobs: int = 1,
        no_owner: bool = False,
        no_privileges: bool = False,
    ) -> None:
        """Restore database from pg_dump backup.

        Parameters
        ----------
        input_file : str or Path
            Backup file path.
        clean : bool, optional
            Drop objects before recreating, by default False.
        if_exists : bool, optional
            Use IF EXISTS with clean (prevents errors), by default True.
        create : bool, optional
            Create database before restoring, by default False.
        data_only : bool, optional
            Restore only data, by default False.
        schema_only : bool, optional
            Restore only schema, by default False.
        tables : list of str, optional
            Only restore these tables.
        schemas : list of str, optional
            Only restore these schemas.
        jobs : int, optional
            Parallel jobs, by default 1.
        no_owner : bool, optional
            Don't restore ownership, by default False.
        no_privileges : bool, optional
            Don't restore privileges, by default False.
        """
        input_file = Path(input_file)

        # Check if it's a plain SQL file
        if input_file.suffix == ".sql" or not input_file.exists():
            # Use psql for plain format
            await self._psql_restore(input_file)
            return

        cmd = build_pg_restore_cmd(
            host=self.config.host,
            port=self.config.port,
            user=self.config.user,
            database=self.config.database,
            input_file=input_file,
            clean=clean,
            if_exists=if_exists,
            create=create,
            data_only=data_only,
            schema_only=schema_only,
            tables=tables,
            schemas=schemas,
            jobs=jobs,
            no_owner=no_owner,
            no_privileges=no_privileges,
        )

        # Run with password in environment
        env = {**os.environ}
        if self.config.password:
            env["PGPASSWORD"] = self.config.password

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"pg_restore failed: {stderr.decode()}")

    async def _psql_restore(self, sql_file: Path) -> None:
        """Restore from plain SQL file using psql."""
        cmd = [
            "psql",
            "-h",
            self.config.host,
            "-p",
            str(self.config.port),
            "-U",
            self.config.user,
            "-d",
            self.config.database,
            "-f",
            str(sql_file),
        ]

        env = {**os.environ}
        if self.config.password:
            env["PGPASSWORD"] = self.config.password

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"psql restore failed: {stderr.decode()}")

    async def copy_to_csv(
        self,
        table: str,
        output_file: str | Path,
        schema: str = "public",
        columns: list[str] | None = None,
        delimiter: str = ",",
        header: bool = True,
        null_string: str = "",
        encoding: str = "UTF8",
    ) -> int:
        """Export table to CSV file.

        Parameters
        ----------
        table : str
            Table name.
        output_file : str or Path
            Output CSV file path.
        schema : str, optional
            Schema name, by default "public".
        columns : list of str, optional
            Specific columns to export.
        delimiter : str, optional
            Field delimiter, by default ",".
        header : bool, optional
            Include header row, by default True.
        null_string : str, optional
            String for NULL values, by default "".
        encoding : str, optional
            File encoding, by default "UTF8".

        Returns
        -------
        int
            Number of rows exported.
        """
        output_file = Path(output_file)
        validate_identifiers(table, schema)
        if columns:
            validate_identifiers(*columns)
        validate_csv_option(delimiter, "delimiter")
        validate_csv_option(null_string, "null_string")
        validate_csv_option(encoding, "encoding")

        cols = f"({', '.join(columns)})" if columns else ""

        options = [
            "FORMAT CSV",
            f"DELIMITER '{delimiter}'",
            f"NULL '{null_string}'",
            f"ENCODING '{encoding}'",
        ]
        if header:
            options.append("HEADER")

        # Create parent directory if needed
        await asyncio.to_thread(output_file.parent.mkdir, parents=True, exist_ok=True)

        async with self.cursor() as cur:
            # Open file and write data
            file_handle = await asyncio.to_thread(
                open, output_file, "w", encoding=encoding
            )
            try:
                async with cur.copy(
                    f"COPY {schema}.{table}{cols} TO STDOUT WITH ({', '.join(options)})"
                ) as copy:
                    async for data in copy:
                        # psycopg yields memoryview chunks; bytes(...) handles
                        # both memoryview and bytes before decoding to text.
                        decoded = (
                            data
                            if isinstance(data, str)
                            else bytes(data).decode(encoding)
                        )
                        await asyncio.to_thread(file_handle.write, decoded)
            finally:
                await asyncio.to_thread(file_handle.close)

            # Get row count
            result = await self.execute(
                f"SELECT COUNT(*) AS count FROM {schema}.{table}"
            )
            return result[0]["count"]

    async def copy_from_csv(
        self,
        table: str,
        input_file: str | Path,
        schema: str = "public",
        columns: list[str] | None = None,
        delimiter: str = ",",
        header: bool = True,
        null_string: str = "",
        encoding: str = "UTF8",
    ) -> int:
        """Import CSV file into table.

        Parameters
        ----------
        table : str
            Table name.
        input_file : str or Path
            Input CSV file path.
        schema : str, optional
            Schema name, by default "public".
        columns : list of str, optional
            Specific columns to import.
        delimiter : str, optional
            Field delimiter, by default ",".
        header : bool, optional
            First row is header, by default True.
        null_string : str, optional
            String representing NULL, by default "".
        encoding : str, optional
            File encoding, by default "UTF8".

        Returns
        -------
        int
            Number of rows imported.
        """
        input_file = Path(input_file)
        validate_identifiers(table, schema)
        if columns:
            validate_identifiers(*columns)
        validate_csv_option(delimiter, "delimiter")
        validate_csv_option(null_string, "null_string")
        validate_csv_option(encoding, "encoding")

        cols = f"({', '.join(columns)})" if columns else ""

        options = [
            "FORMAT CSV",
            f"DELIMITER '{delimiter}'",
            f"NULL '{null_string}'",
            f"ENCODING '{encoding}'",
        ]
        if header:
            options.append("HEADER")

        async with self.cursor() as cur:
            # Open file and read data
            file_handle = await asyncio.to_thread(
                open, input_file, "r", encoding=encoding
            )
            try:
                async with cur.copy(
                    f"COPY {schema}.{table}{cols} FROM STDIN WITH ({', '.join(options)})"
                ) as copy:
                    while True:
                        data = await asyncio.to_thread(file_handle.read, 8192)
                        if not data:
                            break
                        await copy.write(data.encode(encoding))
            finally:
                await asyncio.to_thread(file_handle.close)

            return cur.rowcount

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

    async def notify(self, channel: str, payload: str = "") -> None:
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

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the async context manager and close the connection."""
        await self.close()

