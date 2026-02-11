"""
Async Database class for pycopg.

Provides async/await interface for PostgreSQL operations using psycopg's async support.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator, Literal, Optional, Sequence

import psycopg
from psycopg import OperationalError
from psycopg.rows import dict_row
from psycopg import AsyncConnection, AsyncCursor
from psycopg.pq import TransactionStatus
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

from pycopg.config import Config
from pycopg.utils import validate_identifier, validate_identifiers, validate_index_method, validate_interval
from pycopg import queries

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import geopandas as gpd
    import pandas as pd


class AsyncDatabase:
    """Async PostgreSQL interface.

    Provides async/await versions of Database methods using psycopg's AsyncConnection.

    Example:
        # Connect
        db = AsyncDatabase.from_env()

        # Execute queries
        users = await db.execute("SELECT * FROM users WHERE active = %s", [True])

        # With context manager
        async with db.cursor() as cur:
            await cur.execute("SELECT * FROM users")
            users = await cur.fetchall()

        # Transactions
        async with db.transaction() as conn:
            await conn.execute("INSERT INTO users (name) VALUES (%s)", ["Alice"])
            await conn.execute("INSERT INTO logs (action) VALUES (%s)", ["user_created"])
    """

    def __init__(self, config: Config):
        """Initialize async database connection.

        Args:
            config: Database configuration.
        """
        self.config = config
        self._session_conn: Optional[AsyncConnection] = None
        self._async_engine = None

    @property
    def async_engine(self):
        """Get or create async SQLAlchemy engine (lazy initialization)."""
        if self._async_engine is None:
            from sqlalchemy.ext.asyncio import create_async_engine
            self._async_engine = create_async_engine(self.config.url)
        return self._async_engine

    @classmethod
    def from_env(cls, dotenv_path: Optional[str | Path] = None) -> "AsyncDatabase":
        """Create AsyncDatabase from environment variables.

        Args:
            dotenv_path: Optional path to .env file.

        Returns:
            AsyncDatabase instance.
        """
        return cls(Config.from_env(dotenv_path))

    @classmethod
    def from_url(cls, url: str) -> "AsyncDatabase":
        """Create AsyncDatabase from connection URL.

        Args:
            url: PostgreSQL connection URL.

        Returns:
            AsyncDatabase instance.
        """
        return cls(Config.from_url(url))

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

        Args:
            autocommit: Enable autocommit mode.

        Yields:
            AsyncConnection object.

        Example:
            async with db.connect() as conn:
                result = await conn.execute("SELECT 1")
        """
        conn = await self._connect_with_retry(autocommit=autocommit)
        try:
            yield conn
        finally:
            await conn.close()

    @asynccontextmanager
    async def cursor(self, autocommit: bool = False) -> AsyncIterator[AsyncCursor]:
        """Async context manager for cursor with dict rows.

        Args:
            autocommit: Enable autocommit mode.

        Yields:
            AsyncCursor with dict_row factory.

        Example:
            async with db.cursor() as cur:
                await cur.execute("SELECT * FROM users WHERE id = %s", [1])
                user = await cur.fetchone()  # Returns dict
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
    async def session(self, autocommit: bool = False) -> AsyncIterator["AsyncDatabase"]:
        """Async context manager for session mode with connection reuse.

        In session mode, all operations reuse the same connection,
        significantly reducing overhead for multiple sequential operations.

        Args:
            autocommit: Enable autocommit mode for the session.

        Yields:
            Self (AsyncDatabase instance with active session).

        Example:
            # Without session: each operation opens/closes a connection
            await db.execute("SELECT 1")  # Open, execute, close
            await db.execute("SELECT 2")  # Open, execute, close

            # With session: single connection for all operations
            async with db.session() as session:
                await session.execute("SELECT 1")  # Reuse connection
                await session.execute("SELECT 2")  # Reuse connection
                await session.insert_batch("users", rows)  # Reuse connection
                # Connection closed automatically at end

            # Useful for batch operations
            async with db.session() as session:
                for table in tables:
                    await session.execute(f"TRUNCATE {table}")
                    await session.insert_batch(table, data[table])
        """
        if self._session_conn is not None:
            raise RuntimeError("Already in session mode. Nested sessions are not supported.")

        self._session_conn = await psycopg.AsyncConnection.connect(
            **self.config.connect_params(),
            autocommit=autocommit
        )
        try:
            yield self
        finally:
            try:
                if not autocommit:
                    await self._session_conn.commit()
                await self._session_conn.close()
            except Exception:
                raise
            finally:
                self._session_conn = None  # ALWAYS executes

    @property
    def in_session(self) -> bool:
        """Check if currently in session mode.

        Returns:
            True if in session mode, False otherwise.
        """
        return self._session_conn is not None

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncConnection]:
        """Async context manager for transactions.

        Automatically commits on success, rolls back on exception.
        If a session is active, reuses the session connection.

        Yields:
            AsyncConnection in a transaction.

        Example:
            async with db.transaction() as conn:
                await conn.execute("INSERT INTO users (name) VALUES (%s)", ["Alice"])
                await conn.execute("UPDATE stats SET count = count + 1")
                # Commits automatically if no exception
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
        params: Optional[Sequence] = None,
        autocommit: bool = False,
    ) -> list[dict]:
        """Execute SQL and return results as list of dicts.

        Args:
            sql: SQL query to execute.
            params: Query parameters.
            autocommit: Enable autocommit mode.

        Returns:
            List of result rows as dicts.

        Example:
            users = await db.execute("SELECT * FROM users WHERE active = %s", [True])
            await db.execute("UPDATE users SET active = %s WHERE id = %s", [False, 1])
        """
        async with self.cursor(autocommit=autocommit) as cur:
            await cur.execute(sql, params)
            if cur.description:
                return await cur.fetchall()
            return []

    async def execute_many(self, sql: str, params_seq: Sequence[Sequence]) -> int:
        """Execute SQL for multiple parameter sets.

        Uses psycopg's executemany() for better performance.

        Args:
            sql: SQL query with placeholders.
            params_seq: Sequence of parameter sequences.

        Returns:
            Total number of affected rows.

        Example:
            await db.execute_many(
                "INSERT INTO users (name, email) VALUES (%s, %s)",
                [("Alice", "alice@example.com"), ("Bob", "bob@example.com")]
            )
        """
        async with self.cursor() as cur:
            await cur.executemany(sql, params_seq)
            return cur.rowcount

    async def insert_batch(
        self,
        table: str,
        rows: list[dict],
        schema: str = "public",
        on_conflict: Optional[str] = None,
        batch_size: Optional[int] = None,
    ) -> int:
        """Insert multiple rows efficiently using batch VALUES.

        This method builds a single INSERT with multiple VALUES tuples,
        which is significantly faster than individual INSERT statements.

        Args:
            table: Table name.
            rows: List of row dicts (all must have same keys).
            schema: Schema name.
            on_conflict: Optional ON CONFLICT clause.
            batch_size: Max rows per INSERT statement (default from config).

        Returns:
            Total number of rows inserted.

        Example:
            await db.insert_batch("users", [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@example.com"},
            ])
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
                batch = rows[i:i + batch_size]

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
        columns: Optional[list[str]] = None,
    ) -> int:
        """Insert rows using PostgreSQL COPY protocol.

        This is the fastest method for bulk inserts (10-100x faster than
        regular INSERT for large datasets). Best for >10000 rows.

        Note: COPY doesn't support ON CONFLICT. For upserts, use insert_batch().

        Args:
            table: Table name.
            rows: List of row dicts.
            schema: Schema name.
            columns: Optional list of column names.

        Returns:
            Number of rows inserted.

        Example:
            await db.copy_insert("events", events_list)
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
                async with cur.copy(f"COPY {schema}.{table} ({cols_str}) FROM STDIN") as copy:
                    for row in rows:
                        await copy.write_row([row.get(col) for col in columns])
            await conn.commit()
            return len(rows)

    async def fetch_one(self, sql: str, params: Optional[Sequence] = None) -> Optional[dict]:
        """Execute SQL and return single row.

        Args:
            sql: SQL query.
            params: Query parameters.

        Returns:
            Single row as dict, or None.

        Example:
            user = await db.fetch_one("SELECT * FROM users WHERE id = %s", [1])
        """
        async with self.cursor() as cur:
            await cur.execute(sql, params)
            return await cur.fetchone()

    async def fetch_val(self, sql: str, params: Optional[Sequence] = None) -> Any:
        """Execute SQL and return single value.

        Args:
            sql: SQL query returning single column.
            params: Query parameters.

        Returns:
            Single value, or None.

        Example:
            count = await db.fetch_val("SELECT COUNT(*) FROM users")
        """
        row = await self.fetch_one(sql, params)
        if row:
            return list(row.values())[0]
        return None

    # =========================================================================
    # SCHEMAS & TABLES
    # =========================================================================

    async def list_schemas(self) -> list[str]:
        """List all schemas."""
        result = await self.execute("""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT LIKE 'pg_%'
            AND schema_name != 'information_schema'
            ORDER BY schema_name
        """)
        return [r["schema_name"] for r in result]

    async def schema_exists(self, name: str) -> bool:
        """Check if a schema exists."""
        result = await self.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", [name]
        )
        return len(result) > 0

    async def create_schema(self, name: str, if_not_exists: bool = True) -> None:
        """Create a schema."""
        validate_identifier(name)
        if_clause = "IF NOT EXISTS " if if_not_exists else ""
        await self.execute(f"CREATE SCHEMA {if_clause}{name}")

    async def list_tables(self, schema: str = "public") -> list[str]:
        """List tables in a schema."""
        result = await self.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """, [schema])
        return [r["table_name"] for r in result]

    async def table_exists(self, name: str, schema: str = "public") -> bool:
        """Check if a table exists."""
        result = await self.execute(queries.TABLE_EXISTS, [schema, name])
        return len(result) > 0

    async def list_columns(self, table: str, schema: str = "public") -> list[str]:
        """Get list of column names for a table.

        Args:
            table: Table name.
            schema: Schema name (default: "public").

        Returns:
            List of column names in ordinal order.
        """
        result = await self.execute(queries.GET_COLUMNS, [schema, table])
        return [row["column_name"] for row in result]

    async def columns_with_types(self, table: str, schema: str = "public") -> list[tuple[str, str]]:
        """Get list of (column_name, data_type) tuples for a table.

        Args:
            table: Table name.
            schema: Schema name (default: "public").

        Returns:
            List of (name, type) tuples in ordinal order.
        """
        result = await self.execute(queries.GET_COLUMNS, [schema, table])
        return [(row["column_name"], row["data_type"]) for row in result]

    async def table_info(self, name: str, schema: str = "public") -> list[dict]:
        """Get column information for a table.

        Args:
            name: Table name.
            schema: Schema name.

        Returns:
            List of column info dicts with:
            - column_name, data_type, is_nullable, column_default, ordinal_position
        """
        return await self.execute("""
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default,
                ordinal_position,
                character_maximum_length,
                numeric_precision,
                numeric_scale
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
        """, [schema, name])

    async def row_count(self, name: str, schema: str = "public") -> int:
        """Get approximate row count for a table."""
        result = await self.execute("""
            SELECT reltuples::bigint AS count
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s AND c.relname = %s
        """, [schema, name])
        return result[0]["count"] if result else 0

    async def drop_schema(self, name: str, if_exists: bool = True, cascade: bool = False) -> None:
        """Drop a schema.

        Args:
            name: Schema name.
            if_exists: Don't error if schema doesn't exist.
            cascade: Drop all objects in schema.

        Example:
            await db.drop_schema("analytics")
            await db.drop_schema("old_data", cascade=True)
        """
        validate_identifier(name)
        if_clause = "IF EXISTS " if if_exists else ""
        cascade_clause = " CASCADE" if cascade else ""
        await self.execute(f"DROP SCHEMA {if_clause}{name}{cascade_clause}")

    async def drop_table(self, name: str, schema: str = "public", if_exists: bool = True, cascade: bool = False) -> None:
        """Drop a table.

        Args:
            name: Table name.
            schema: Schema name.
            if_exists: Don't error if table doesn't exist.
            cascade: Drop dependent objects.

        Example:
            await db.drop_table("old_users")
            await db.drop_table("logs", cascade=True)
        """
        validate_identifiers(name, schema)
        if_clause = "IF EXISTS " if if_exists else ""
        cascade_clause = " CASCADE" if cascade else ""
        await self.execute(f"DROP TABLE {if_clause}{schema}.{name}{cascade_clause}")

    async def create_index(
        self,
        table: str,
        columns: str | list[str],
        schema: str = "public",
        name: Optional[str] = None,
        unique: bool = False,
        method: str = "btree",
        if_not_exists: bool = True,
    ) -> None:
        """Create an index.

        Args:
            table: Table name.
            columns: Column(s) to index.
            schema: Schema name.
            name: Index name (auto-generated if not provided).
            unique: Create unique index.
            method: Index method (btree, hash, gist, gin, etc.)
            if_not_exists: Don't error if index exists.

        Example:
            await db.create_index("users", "email", unique=True)
            await db.create_index("products", ["category", "price"])
            await db.create_index("documents", "content", method="gin")
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

    async def drop_index(self, name: str, schema: str = "public", if_exists: bool = True) -> None:
        """Drop an index.

        Args:
            name: Index name.
            schema: Schema name.
            if_exists: Don't error if index doesn't exist.

        Example:
            await db.drop_index("idx_users_email")
        """
        if_clause = "IF EXISTS " if if_exists else ""
        await self.execute(f"DROP INDEX {if_clause}{schema}.{name}")

    async def list_indexes(self, table: str, schema: str = "public") -> list[dict]:
        """List indexes on a table.

        Args:
            table: Table name.
            schema: Schema name.

        Returns:
            List of index info dicts.

        Example:
            indexes = await db.list_indexes("users")
            for idx in indexes:
                print(f"{idx['index_name']}: {idx['index_type']}")
        """
        return await self.execute("""
            SELECT
                i.relname AS index_name,
                am.amname AS index_type,
                pg_get_indexdef(i.oid) AS index_def
            FROM pg_index idx
            JOIN pg_class t ON t.oid = idx.indrelid
            JOIN pg_class i ON i.oid = idx.indexrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            JOIN pg_am am ON am.oid = i.relam
            WHERE n.nspname = %s AND t.relname = %s
            ORDER BY i.relname
        """, [schema, table])

    async def list_constraints(self, table: str, schema: str = "public") -> list[dict]:
        """List constraints on a table.

        Args:
            table: Table name.
            schema: Schema name.

        Returns:
            List of constraint info dicts.

        Example:
            constraints = await db.list_constraints("users")
            for c in constraints:
                print(f"{c['constraint_name']}: {c['constraint_type']}")
        """
        return await self.execute("""
            SELECT
                c.conname AS constraint_name,
                c.contype AS constraint_type,
                pg_get_constraintdef(c.oid) AS constraint_def
            FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = %s AND t.relname = %s
            ORDER BY c.conname
        """, [schema, table])

    # =========================================================================
    # EXTENSIONS
    # =========================================================================

    async def has_extension(self, name: str) -> bool:
        """Check if an extension is installed."""
        result = await self.execute("SELECT 1 FROM pg_extension WHERE extname = %s", [name])
        return len(result) > 0

    async def create_extension(self, name: str, if_not_exists: bool = True) -> None:
        """Create a PostgreSQL extension."""
        if_clause = "IF NOT EXISTS " if if_not_exists else ""
        await self.execute(f'CREATE EXTENSION {if_clause}"{name}"', autocommit=True)

    async def list_extensions(self) -> list[dict]:
        """List installed extensions."""
        return await self.execute("""
            SELECT e.extname, e.extversion, n.nspname
            FROM pg_extension e
            JOIN pg_namespace n ON e.extnamespace = n.oid
            ORDER BY e.extname
        """)

    # =========================================================================
    # POSTGIS SPATIAL OPERATIONS
    # =========================================================================

    async def create_spatial_index(self, table: str, column: str = "geometry", schema: str = "public", name: Optional[str] = None) -> None:
        """Create a GIST spatial index on a geometry column.

        Args:
            table: Table name.
            column: Geometry column name.
            schema: Schema name.
            name: Index name (auto-generated if not provided).

        Example:
            await db.create_spatial_index("parcels", "geom")
        """
        index_name = name or f"idx_{table}_{column}_gist"
        await self.execute(f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {schema}.{table} USING GIST ({column})
        """)

    async def list_geometry_columns(self, schema: Optional[str] = None) -> list[dict]:
        """List geometry columns in the database.

        Args:
            schema: Optional schema filter.

        Returns:
            List of geometry column info.
        """
        where_clause = "WHERE f_table_schema = %s" if schema else ""
        params = [schema] if schema else None
        return await self.execute(f"""
            SELECT
                f_table_schema AS schema,
                f_table_name AS table_name,
                f_geometry_column AS column_name,
                coord_dimension AS dimensions,
                srid,
                type AS geometry_type
            FROM geometry_columns
            {where_clause}
            ORDER BY f_table_schema, f_table_name
        """, params)

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

        Args:
            table: Table name (must exist with time column).
            time_column: Name of the timestamp column.
            schema: Schema name.
            chunk_time_interval: Chunk time interval (e.g., '1 day', '1 week').
            if_not_exists: Don't error if already a hypertable.
            migrate_data: Migrate existing data to chunks.

        Example:
            await db.create_hypertable("events", "created_at", chunk_time_interval="1 week")
        """
        if not await self.has_extension("timescaledb"):
            raise RuntimeError("TimescaleDB extension not installed. Run db.create_extension('timescaledb')")

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
        segment_by: Optional[str | list[str]] = None,
        order_by: Optional[str | list[str]] = None,
        schema: str = "public",
    ) -> None:
        """Enable compression on a hypertable.

        Args:
            table: Hypertable name.
            segment_by: Column(s) to segment compressed data by.
            order_by: Column(s) to order compressed data by.
            schema: Schema name.

        Example:
            await db.enable_compression("events", segment_by="device_id", order_by="timestamp DESC")
        """
        if not await self.has_extension("timescaledb"):
            raise RuntimeError(
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
            settings.append(f"timescaledb.compress_segmentby = '{','.join(segment_by)}'")
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

        Args:
            table: Hypertable name.
            compress_after: Compress chunks older than this interval.
            schema: Schema name.

        Example:
            await db.add_compression_policy("events", compress_after="30 days")
        """
        if not await self.has_extension("timescaledb"):
            raise RuntimeError(
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

        Args:
            table: Hypertable name.
            drop_after: Drop chunks older than this interval.
            schema: Schema name.

        Example:
            await db.add_retention_policy("logs", drop_after="90 days")
        """
        if not await self.has_extension("timescaledb"):
            raise RuntimeError(
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

        Returns:
            List of hypertable info dicts.
        """
        if not await self.has_extension("timescaledb"):
            raise RuntimeError(
                "TimescaleDB extension not installed. "
                "Run db.create_extension('timescaledb')"
            )

        return await self.execute("""
            SELECT
                hypertable_schema AS schema,
                hypertable_name AS table_name,
                num_dimensions,
                num_chunks,
                compression_enabled
            FROM timescaledb_information.hypertables
            ORDER BY hypertable_schema, hypertable_name
        """)

    async def hypertable_info(self, table: str, schema: str = "public") -> dict:
        """Get detailed info about a hypertable.

        Args:
            table: Hypertable name.
            schema: Schema name.

        Returns:
            Dict with hypertable details including size info.
        """
        if not await self.has_extension("timescaledb"):
            raise RuntimeError(
                "TimescaleDB extension not installed. "
                "Run db.create_extension('timescaledb')"
            )

        result = await self.execute("""
            SELECT
                hypertable_size(format('%I.%I', %s, %s)) AS total_size,
                hypertable_detailed_size(format('%I.%I', %s, %s)) AS detailed_size
        """, [schema, table, schema, table])
        return result[0] if result else {}

    # =========================================================================
    # ROLES
    # =========================================================================

    async def role_exists(self, name: str) -> bool:
        """Check if a role exists."""
        result = await self.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [name])
        return len(result) > 0

    async def list_roles(self, include_system: bool = False) -> list[dict]:
        """List all roles."""
        where_clause = "" if include_system else "WHERE rolname NOT LIKE 'pg_%'"
        return await self.execute(f"""
            SELECT
                rolname AS name,
                rolsuper AS superuser,
                rolcreaterole AS createrole,
                rolcreatedb AS createdb,
                rolcanlogin AS login,
                rolreplication AS replication,
                rolconnlimit AS connection_limit,
                rolvaliduntil AS valid_until
            FROM pg_roles
            {where_clause}
            ORDER BY rolname
        """)

    # =========================================================================
    # ROLE MANAGEMENT
    # =========================================================================

    async def create_role(
        self,
        name: str,
        password: Optional[str] = None,
        login: bool = True,
        superuser: bool = False,
        createdb: bool = False,
        createrole: bool = False,
        inherit: bool = True,
        replication: bool = False,
        connection_limit: int = -1,
        valid_until: Optional[str] = None,
        in_roles: Optional[list[str]] = None,
        if_not_exists: bool = True,
    ) -> None:
        """Create a database role/user.

        Args:
            name: Role name.
            password: Role password (for login roles).
            login: Can log in (True = user, False = group role).
            superuser: Is superuser.
            createdb: Can create databases.
            createrole: Can create other roles.
            inherit: Inherits privileges from member roles.
            replication: Can initiate streaming replication.
            connection_limit: Max concurrent connections (-1 = unlimited).
            valid_until: Password expiration (e.g., '2025-12-31').
            in_roles: List of roles to be a member of.
            if_not_exists: Don't error if role exists.

        Example:
            # Create a regular user
            await db.create_role("appuser", password="secret123", login=True)

            # Create an admin user
            await db.create_role("admin", password="secret", superuser=True)

            # Create a read-only group role
            await db.create_role("readonly", login=False)

            # Create user in a group
            await db.create_role("analyst", password="secret", in_roles=["readonly"])
        """
        validate_identifier(name)

        # Check if exists
        if if_not_exists and await self.role_exists(name):
            return

        options = []
        if login:
            options.append("LOGIN")
        else:
            options.append("NOLOGIN")

        if superuser:
            options.append("SUPERUSER")
        if createdb:
            options.append("CREATEDB")
        if createrole:
            options.append("CREATEROLE")
        if not inherit:
            options.append("NOINHERIT")
        if replication:
            options.append("REPLICATION")
        if connection_limit != -1:
            options.append(f"CONNECTION LIMIT {connection_limit}")
        if password:
            # Use parameterized query for password
            options.append(f"PASSWORD %s")
        if valid_until:
            options.append(f"VALID UNTIL '{valid_until}'")

        options_str = " ".join(options)

        if password:
            async with self.cursor(autocommit=True) as cur:
                await cur.execute(f"CREATE ROLE {name} WITH {options_str}", [password])
        else:
            await self.execute(f"CREATE ROLE {name} WITH {options_str}", autocommit=True)

        # Add to roles
        if in_roles:
            for role in in_roles:
                await self.grant_role(role, name)

    async def drop_role(self, name: str, if_exists: bool = True) -> None:
        """Drop a role.

        Args:
            name: Role name.
            if_exists: Don't error if role doesn't exist.

        Example:
            await db.drop_role("olduser")
        """
        validate_identifier(name)
        if_clause = "IF EXISTS " if if_exists else ""
        await self.execute(f"DROP ROLE {if_clause}{name}", autocommit=True)

    async def alter_role(
        self,
        name: str,
        password: Optional[str] = None,
        login: Optional[bool] = None,
        superuser: Optional[bool] = None,
        createdb: Optional[bool] = None,
        createrole: Optional[bool] = None,
        connection_limit: Optional[int] = None,
        valid_until: Optional[str] = None,
        rename_to: Optional[str] = None,
    ) -> None:
        """Alter a role's attributes.

        Args:
            name: Role name.
            password: New password.
            login: Enable/disable login.
            superuser: Enable/disable superuser.
            createdb: Enable/disable createdb.
            createrole: Enable/disable createrole.
            connection_limit: New connection limit.
            valid_until: New password expiration.
            rename_to: Rename the role.

        Example:
            await db.alter_role("appuser", password="newpassword")
            await db.alter_role("appuser", connection_limit=10)
            await db.alter_role("oldname", rename_to="newname")
        """
        validate_identifier(name)

        if rename_to:
            validate_identifier(rename_to)
            await self.execute(f"ALTER ROLE {name} RENAME TO {rename_to}", autocommit=True)
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
            options.append(f"VALID UNTIL '{valid_until}'")

        if options:
            options_str = " ".join(options)
            async with self.cursor(autocommit=True) as cur:
                await cur.execute(f"ALTER ROLE {name} WITH {options_str}", params if params else None)

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

        Args:
            privileges: Privilege(s) to grant (SELECT, INSERT, UPDATE, DELETE, ALL, etc.)
            on: Object name or ALL TABLES/SEQUENCES/FUNCTIONS.
            to: Role receiving privileges.
            object_type: Type of object (TABLE, SEQUENCE, FUNCTION, SCHEMA, DATABASE).
            schema: Schema name (for tables/sequences).
            with_grant_option: Allow grantee to grant to others.

        Example:
            # Grant SELECT on a table
            await db.grant("SELECT", "users", "readonly")

            # Grant all on a table
            await db.grant("ALL", "orders", "appuser")

            # Grant on all tables in schema
            await db.grant("SELECT", "ALL TABLES", "readonly", schema="public")

            # Grant on schema
            await db.grant("USAGE", "myschema", "appuser", object_type="SCHEMA")

            # Grant on database
            await db.grant("CONNECT", "mydb", "appuser", object_type="DATABASE")
        """
        validate_identifier(to)

        if isinstance(privileges, list):
            privileges = ", ".join(privileges)

        grant_clause = " WITH GRANT OPTION" if with_grant_option else ""

        if object_type.upper() == "SCHEMA":
            validate_identifier(on)
            await self.execute(f"GRANT {privileges} ON SCHEMA {on} TO {to}{grant_clause}", autocommit=True)
        elif object_type.upper() == "DATABASE":
            validate_identifier(on)
            await self.execute(f"GRANT {privileges} ON DATABASE {on} TO {to}{grant_clause}", autocommit=True)
        elif on.upper() in ("ALL TABLES", "ALL SEQUENCES", "ALL FUNCTIONS"):
            validate_identifier(schema)
            await self.execute(f"GRANT {privileges} ON {on} IN SCHEMA {schema} TO {to}{grant_clause}", autocommit=True)
        else:
            validate_identifiers(on, schema)
            await self.execute(f"GRANT {privileges} ON {object_type} {schema}.{on} TO {to}{grant_clause}", autocommit=True)

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

        Args:
            privileges: Privilege(s) to revoke.
            on: Object name or ALL TABLES/SEQUENCES/FUNCTIONS.
            from_role: Role losing privileges.
            object_type: Type of object.
            schema: Schema name.
            cascade: Revoke from dependent privileges.

        Example:
            await db.revoke("INSERT", "users", "readonly")
            await db.revoke("ALL", "orders", "former_user", cascade=True)
        """
        validate_identifier(from_role)

        if isinstance(privileges, list):
            privileges = ", ".join(privileges)

        cascade_clause = " CASCADE" if cascade else ""

        if object_type.upper() == "SCHEMA":
            validate_identifier(on)
            await self.execute(f"REVOKE {privileges} ON SCHEMA {on} FROM {from_role}{cascade_clause}", autocommit=True)
        elif object_type.upper() == "DATABASE":
            validate_identifier(on)
            await self.execute(f"REVOKE {privileges} ON DATABASE {on} FROM {from_role}{cascade_clause}", autocommit=True)
        elif on.upper() in ("ALL TABLES", "ALL SEQUENCES", "ALL FUNCTIONS"):
            validate_identifier(schema)
            await self.execute(f"REVOKE {privileges} ON {on} IN SCHEMA {schema} FROM {from_role}{cascade_clause}", autocommit=True)
        else:
            validate_identifiers(on, schema)
            await self.execute(f"REVOKE {privileges} ON {object_type} {schema}.{on} FROM {from_role}{cascade_clause}", autocommit=True)

    async def grant_role(self, role: str, member: str, with_admin: bool = False) -> None:
        """Grant role membership to another role.

        Args:
            role: Role to grant.
            member: Role receiving membership.
            with_admin: Allow member to grant role to others.

        Example:
            await db.grant_role("readonly", "analyst")
            await db.grant_role("admin", "lead_dev", with_admin=True)
        """
        validate_identifiers(role, member)
        admin_clause = " WITH ADMIN OPTION" if with_admin else ""
        await self.execute(f"GRANT {role} TO {member}{admin_clause}", autocommit=True)

    async def revoke_role(self, role: str, member: str) -> None:
        """Revoke role membership from a role.

        Args:
            role: Role to revoke.
            member: Role losing membership.

        Example:
            await db.revoke_role("admin", "former_admin")
        """
        validate_identifiers(role, member)
        await self.execute(f"REVOKE {role} FROM {member}", autocommit=True)

    async def list_role_members(self, role: str) -> list[str]:
        """List members of a role.

        Args:
            role: Role name.

        Returns:
            List of member role names.
        """
        result = await self.execute("""
            SELECT m.rolname AS member
            FROM pg_auth_members am
            JOIN pg_roles r ON r.oid = am.roleid
            JOIN pg_roles m ON m.oid = am.member
            WHERE r.rolname = %s
            ORDER BY m.rolname
        """, [role])
        return [r["member"] for r in result]

    async def list_role_grants(self, role: str) -> list[dict]:
        """List privileges granted to a role.

        Args:
            role: Role name.

        Returns:
            List of privilege info dicts.
        """
        return await self.execute("""
            SELECT
                table_schema AS schema,
                table_name AS object_name,
                privilege_type AS privilege
            FROM information_schema.role_table_grants
            WHERE grantee = %s
            ORDER BY table_schema, table_name, privilege_type
        """, [role])

    # =========================================================================
    # SIZE & STATS
    # =========================================================================

    async def size(self, pretty: bool = True) -> str | int:
        """Get database size."""
        if pretty:
            result = await self.execute(
                "SELECT pg_size_pretty(pg_database_size(%s)) AS size",
                [self.config.database]
            )
            return result[0]["size"]
        else:
            result = await self.execute(
                "SELECT pg_database_size(%s) AS size",
                [self.config.database]
            )
            return result[0]["size"]

    async def table_size(self, table: str, schema: str = "public", pretty: bool = True) -> str | int:
        """Get table size including indexes."""
        full_name = f"{schema}.{table}"
        if pretty:
            result = await self.execute(
                "SELECT pg_size_pretty(pg_total_relation_size(%s)) AS size",
                [full_name]
            )
            return result[0]["size"]
        else:
            result = await self.execute(
                "SELECT pg_total_relation_size(%s) AS size",
                [full_name]
            )
            return result[0]["size"]

    async def table_sizes(self, schema: str = "public", limit: int = 20) -> list[dict]:
        """Get sizes of all tables in schema, sorted by size.

        Args:
            schema: Schema name.
            limit: Max tables to return.

        Returns:
            List of table size info with total_size, data_size, index_size columns.

        Example:
            sizes = await db.table_sizes("public", limit=10)
            for s in sizes:
                print(f"{s['table_name']}: {s['total_size']}")
        """
        # Use %%I to escape the % for psycopg, format() will see %I
        return await self.execute("""
            SELECT
                t.tablename AS table_name,
                pg_size_pretty(pg_total_relation_size(format('%%I.%%I', t.schemaname, t.tablename))) AS total_size,
                pg_size_pretty(pg_relation_size(format('%%I.%%I', t.schemaname, t.tablename))) AS data_size,
                pg_size_pretty(pg_indexes_size(format('%%I.%%I', t.schemaname, t.tablename))) AS index_size
            FROM pg_tables t
            WHERE t.schemaname = %s
            ORDER BY pg_total_relation_size(format('%%I.%%I', t.schemaname, t.tablename)) DESC
            LIMIT %s
        """, [schema, limit])

    # =========================================================================
    # DATAFRAME OPERATIONS
    # =========================================================================

    async def to_dataframe(
        self,
        table: Optional[str] = None,
        schema: str = "public",
        sql: Optional[str] = None,
        params: Optional[dict] = None,
    ) -> "pd.DataFrame":
        """Read table or query into pandas DataFrame.

        Args:
            table: Table name (mutually exclusive with sql).
            schema: Schema name.
            sql: SQL query (mutually exclusive with table).
            params: Query parameters for sql.

        Returns:
            pandas DataFrame.

        Example:
            users = await db.to_dataframe("users")
            active = await db.to_dataframe(
                sql="SELECT * FROM users WHERE active = :active",
                params={"active": True}
            )
        """
        import pandas as pd
        from sqlalchemy import text

        if table and sql:
            raise ValueError("Specify either table or sql, not both")
        if not table and not sql:
            raise ValueError("Specify either table or sql")

        if table:
            sql = f"SELECT * FROM {schema}.{table}"

        async with self.async_engine.connect() as conn:
            return await conn.run_sync(
                lambda sync_conn: pd.read_sql(text(sql), sync_conn, params=params)
            )

    async def from_dataframe(
        self,
        df: "pd.DataFrame",
        table: str,
        schema: str = "public",
        if_exists: Literal["fail", "replace", "append"] = "fail",
        primary_key: Optional[str | list[str]] = None,
        index: bool = False,
        dtype: Optional[dict] = None,
    ) -> None:
        """Create or append to table from pandas DataFrame.

        Args:
            df: pandas DataFrame.
            table: Table name.
            schema: Schema name.
            if_exists: What to do if table exists ('fail', 'replace', 'append').
            primary_key: Column(s) to set as primary key after creation.
                Note: Requires add_primary_key (available in Phase 3).
            index: Write DataFrame index as column.
            dtype: Optional dict of column name to SQLAlchemy types.

        Example:
            await db.from_dataframe(users_df, "users")
            await db.from_dataframe(orders_df, "orders", if_exists="append")
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
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                "primary_key parameter ignored — add_primary_key not yet available in AsyncDatabase. "
                "Use db.execute('ALTER TABLE ...') manually or wait for Phase 3."
            )

    async def to_geodataframe(
        self,
        table: Optional[str] = None,
        schema: str = "public",
        sql: Optional[str] = None,
        geometry_column: str = "geometry",
        params: Optional[dict] = None,
    ) -> "gpd.GeoDataFrame":
        """Read table or query into GeoDataFrame.

        Args:
            table: Table name (mutually exclusive with sql).
            schema: Schema name.
            sql: SQL query (mutually exclusive with table).
            geometry_column: Name of geometry column.
            params: Query parameters.

        Returns:
            geopandas GeoDataFrame.

        Example:
            parcels = await db.to_geodataframe("parcels", schema="geo")
            custom = await db.to_geodataframe(
                sql="SELECT * FROM parcels WHERE area > :min_area",
                params={"min_area": 1000}
            )
        """
        import geopandas as gpd
        from sqlalchemy import text

        if table and sql:
            raise ValueError("Specify either table or sql, not both")
        if not table and not sql:
            raise ValueError("Specify either table or sql")

        if table:
            sql = f"SELECT * FROM {schema}.{table}"

        async with self.async_engine.connect() as conn:
            return await conn.run_sync(
                lambda sync_conn: gpd.read_postgis(
                    text(sql), sync_conn, geom_col=geometry_column, params=params
                )
            )

    async def from_geodataframe(
        self,
        gdf: "gpd.GeoDataFrame",
        table: str,
        schema: str = "public",
        if_exists: Literal["fail", "replace", "append"] = "fail",
        primary_key: Optional[str | list[str]] = None,
        spatial_index: bool = True,
        geometry_column: str = "geometry",
        srid: Optional[int] = None,
    ) -> None:
        """Create or append to table from GeoDataFrame.

        Requires PostGIS extension.

        Args:
            gdf: geopandas GeoDataFrame.
            table: Table name.
            schema: Schema name.
            if_exists: What to do if table exists.
            primary_key: Column(s) for primary key.
                Note: Requires add_primary_key (available in Phase 3).
            spatial_index: Create GIST spatial index on geometry.
                Note: Requires create_spatial_index (available in Phase 4).
            geometry_column: Name of geometry column.
            srid: Override SRID (extracted from CRS if not specified).

        Example:
            await db.from_geodataframe(parcels, "parcels")
        """
        # Ensure PostGIS is available
        if not await self.has_extension("postgis"):
            raise RuntimeError(
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
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                "primary_key parameter ignored — add_primary_key not yet available in AsyncDatabase. "
                "Use db.execute('ALTER TABLE ...') manually or wait for Phase 3."
            )

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
        on_conflict: Optional[str] = None,
    ) -> int:
        """Insert multiple rows efficiently.

        Args:
            table: Table name.
            rows: List of row dicts.
            schema: Schema name.
            on_conflict: ON CONFLICT clause (e.g., "DO NOTHING", "DO UPDATE SET ...").

        Returns:
            Number of rows inserted.

        Example:
            await db.insert_many("users", [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@example.com"},
            ])

            await db.insert_many("users", rows, on_conflict="(email) DO NOTHING")
        """
        if not rows:
            return 0

        validate_identifiers(table, schema)

        columns = list(rows[0].keys())
        placeholders = ", ".join(["%s"] * len(columns))
        cols_str = ", ".join(columns)

        conflict_clause = f" ON CONFLICT {on_conflict}" if on_conflict else ""

        sql = f"INSERT INTO {schema}.{table} ({cols_str}) VALUES ({placeholders}){conflict_clause}"

        params_seq = [[row.get(col) for col in columns] for row in rows]

        return await self.execute_many(sql, params_seq)

    async def upsert_many(
        self,
        table: str,
        rows: list[dict],
        conflict_columns: list[str],
        update_columns: Optional[list[str]] = None,
        schema: str = "public",
    ) -> int:
        """Upsert (insert or update) multiple rows.

        Args:
            table: Table name.
            rows: List of row dicts.
            conflict_columns: Columns that define uniqueness.
            update_columns: Columns to update on conflict (None = all except conflict).
            schema: Schema name.

        Returns:
            Number of rows affected.

        Example:
            await db.upsert_many(
                "users",
                [{"id": 1, "name": "Alice", "email": "alice@new.com"}],
                conflict_columns=["id"],
                update_columns=["name", "email"]
            )
        """
        if not rows:
            return 0

        columns = list(rows[0].keys())
        if update_columns is None:
            update_columns = [c for c in columns if c not in conflict_columns]

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
        params: Optional[Sequence] = None,
        batch_size: int = 1000,
    ) -> AsyncIterator[dict]:
        """Stream query results in batches.

        Memory-efficient way to process large result sets.

        Args:
            sql: SQL query.
            params: Query parameters.
            batch_size: Rows to fetch per batch.

        Yields:
            Row dicts.

        Example:
            async for row in db.stream("SELECT * FROM large_table"):
                process(row)
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

    async def create_database(self, name: str, owner: Optional[str] = None, template: str = "template1") -> None:
        """Create a new database.

        Args:
            name: Database name.
            owner: Optional owner role.
            template: Template database (default: template1).

        Example:
            await db.create_database("myapp")
            await db.create_database("myapp", owner="appuser")
        """
        validate_identifier(name)
        if owner:
            validate_identifier(owner)
        validate_identifier(template)
        owner_clause = f" OWNER {owner}" if owner else ""
        # Connect to postgres for database creation
        admin_config = self.config.with_database("postgres")
        async with await psycopg.AsyncConnection.connect(**admin_config.connect_params(), autocommit=True) as conn:
            async with conn.cursor() as cur:
                await cur.execute(f"CREATE DATABASE {name}{owner_clause} TEMPLATE {template}")

    async def drop_database(self, name: str, if_exists: bool = True) -> None:
        """Drop a database.

        Args:
            name: Database name.
            if_exists: Don't error if database doesn't exist.

        Example:
            await db.drop_database("myapp")
        """
        validate_identifier(name)
        if_clause = "IF EXISTS " if if_exists else ""
        admin_config = self.config.with_database("postgres")
        async with await psycopg.AsyncConnection.connect(**admin_config.connect_params(), autocommit=True) as conn:
            async with conn.cursor() as cur:
                # Terminate existing connections
                await cur.execute(f"""
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = %s
                    AND pid <> pg_backend_pid()
                """, [name])
                await cur.execute(f"DROP DATABASE {if_clause}{name}")

    # =========================================================================
    # UTILITY
    # =========================================================================

    async def vacuum(self, table: Optional[str] = None, schema: str = "public", analyze: bool = True, full: bool = False) -> None:
        """Vacuum database or table.

        Args:
            table: Table name (None for whole database).
            schema: Schema name.
            analyze: Update statistics.
            full: Full vacuum (reclaims more space but locks table).

        Example:
            await db.vacuum()
            await db.vacuum("users", full=True)
        """
        options = []
        if full:
            options.append("FULL")
        if analyze:
            options.append("ANALYZE")

        options_str = f"({', '.join(options)})" if options else ""
        table_str = f" {schema}.{table}" if table else ""

        await self.execute(f"VACUUM{options_str}{table_str}", autocommit=True)

    async def analyze(self, table: Optional[str] = None, schema: str = "public") -> None:
        """Update table statistics for query planner.

        Args:
            table: Table name (None for whole database).
            schema: Schema name.

        Example:
            await db.analyze()
            await db.analyze("users")
        """
        table_str = f" {schema}.{table}" if table else ""
        await self.execute(f"ANALYZE{table_str}", autocommit=True)

    async def explain(self, sql: str, params: Optional[Sequence] = None, analyze: bool = False, format: str = "text") -> list[str]:
        """Get query execution plan.

        Args:
            sql: SQL query.
            params: Query parameters.
            analyze: Actually run the query for real stats.
            format: Output format (text, json, xml, yaml).

        Returns:
            Query plan lines.

        Example:
            plan = await db.explain("SELECT * FROM users WHERE id = 1")
            print("\\n".join(plan))
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
        tables: Optional[list[str]] = None,
        exclude_tables: Optional[list[str]] = None,
        schemas: Optional[list[str]] = None,
        compress: int = 6,
        jobs: int = 1,
    ) -> None:
        """Backup database using pg_dump.

        Args:
            output_file: Output file path.
            format: Dump format (plain=SQL, custom=compressed, directory=parallel, tar).
            schema_only: Dump only schema, no data.
            data_only: Dump only data, no schema.
            tables: Only dump these tables.
            exclude_tables: Exclude these tables.
            schemas: Only dump these schemas.
            compress: Compression level (0-9, for custom format).
            jobs: Parallel jobs (for directory format).

        Example:
            # Full backup in custom format
            await db.pg_dump("backup.dump")

            # SQL backup
            await db.pg_dump("backup.sql", format="plain")

            # Schema only
            await db.pg_dump("schema.sql", format="plain", schema_only=True)

            # Specific tables
            await db.pg_dump("users.dump", tables=["users", "profiles"])

            # Parallel backup
            await db.pg_dump("backup_dir", format="directory", jobs=4)
        """
        output_file = Path(output_file)
        cmd = ["pg_dump"]

        # Connection params
        cmd.extend(["-h", self.config.host])
        cmd.extend(["-p", str(self.config.port)])
        cmd.extend(["-U", self.config.user])
        cmd.extend(["-d", self.config.database])

        # Format
        format_map = {"plain": "p", "custom": "c", "directory": "d", "tar": "t"}
        cmd.extend(["-F", format_map[format]])

        # Options
        if schema_only:
            cmd.append("--schema-only")
        if data_only:
            cmd.append("--data-only")
        if compress and format == "custom":
            cmd.extend(["-Z", str(compress)])
        if jobs > 1 and format == "directory":
            cmd.extend(["-j", str(jobs)])

        # Tables
        if tables:
            for table in tables:
                cmd.extend(["-t", table])
        if exclude_tables:
            for table in exclude_tables:
                cmd.extend(["-T", table])
        if schemas:
            for schema in schemas:
                cmd.extend(["-n", schema])

        # Output
        cmd.extend(["-f", str(output_file)])

        # Run with password in environment
        env = {**os.environ}
        if self.config.password:
            env["PGPASSWORD"] = self.config.password

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await proc.communicate()

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
        tables: Optional[list[str]] = None,
        schemas: Optional[list[str]] = None,
        jobs: int = 1,
        no_owner: bool = False,
        no_privileges: bool = False,
    ) -> None:
        """Restore database from pg_dump backup.

        Args:
            input_file: Backup file path.
            clean: Drop objects before recreating.
            if_exists: Use IF EXISTS with clean (prevents errors).
            create: Create database before restoring.
            data_only: Restore only data.
            schema_only: Restore only schema.
            tables: Only restore these tables.
            schemas: Only restore these schemas.
            jobs: Parallel jobs.
            no_owner: Don't restore ownership.
            no_privileges: Don't restore privileges.

        Example:
            # Full restore
            await db.pg_restore("backup.dump")

            # Clean restore (drop and recreate)
            await db.pg_restore("backup.dump", clean=True)

            # Restore specific tables
            await db.pg_restore("backup.dump", tables=["users"])

            # Parallel restore
            await db.pg_restore("backup_dir", jobs=4)
        """
        input_file = Path(input_file)

        # Check if it's a plain SQL file
        if input_file.suffix == ".sql" or not input_file.exists():
            # Use psql for plain format
            await self._psql_restore(input_file)
            return

        cmd = ["pg_restore"]

        # Connection params
        cmd.extend(["-h", self.config.host])
        cmd.extend(["-p", str(self.config.port)])
        cmd.extend(["-U", self.config.user])
        cmd.extend(["-d", self.config.database])

        # Options
        if clean:
            cmd.append("--clean")
        if if_exists:
            cmd.append("--if-exists")
        if create:
            cmd.append("--create")
        if data_only:
            cmd.append("--data-only")
        if schema_only:
            cmd.append("--schema-only")
        if jobs > 1:
            cmd.extend(["-j", str(jobs)])
        if no_owner:
            cmd.append("--no-owner")
        if no_privileges:
            cmd.append("--no-privileges")

        # Tables/Schemas
        if tables:
            for table in tables:
                cmd.extend(["-t", table])
        if schemas:
            for schema in schemas:
                cmd.extend(["-n", schema])

        cmd.append(str(input_file))

        # Run with password in environment
        env = {**os.environ}
        if self.config.password:
            env["PGPASSWORD"] = self.config.password

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"pg_restore failed: {stderr.decode()}")

    async def _psql_restore(self, sql_file: Path) -> None:
        """Restore from plain SQL file using psql."""
        cmd = [
            "psql",
            "-h", self.config.host,
            "-p", str(self.config.port),
            "-U", self.config.user,
            "-d", self.config.database,
            "-f", str(sql_file),
        ]

        env = {**os.environ}
        if self.config.password:
            env["PGPASSWORD"] = self.config.password

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"psql restore failed: {stderr.decode()}")

    async def copy_to_csv(
        self,
        table: str,
        output_file: str | Path,
        schema: str = "public",
        columns: Optional[list[str]] = None,
        delimiter: str = ",",
        header: bool = True,
        null_string: str = "",
        encoding: str = "UTF8",
    ) -> int:
        """Export table to CSV file.

        Args:
            table: Table name.
            output_file: Output CSV file path.
            schema: Schema name.
            columns: Specific columns to export.
            delimiter: Field delimiter.
            header: Include header row.
            null_string: String for NULL values.
            encoding: File encoding.

        Returns:
            Number of rows exported.

        Example:
            count = await db.copy_to_csv("users", "users.csv")
            await db.copy_to_csv("orders", "orders.csv", columns=["id", "total", "created_at"])
        """
        output_file = Path(output_file)
        validate_identifiers(table, schema)
        if columns:
            validate_identifiers(*columns)

        cols = f"({', '.join(columns)})" if columns else ""

        options = [
            f"FORMAT CSV",
            f"DELIMITER '{delimiter}'",
            f"NULL '{null_string}'",
            f"ENCODING '{encoding}'",
        ]
        if header:
            options.append("HEADER")

        # Create parent directory if needed
        await asyncio.to_thread(output_file.parent.mkdir, parents=True, exist_ok=True)

        try:
            async with self.cursor() as cur:
                # Open file and write data
                file_handle = await asyncio.to_thread(open, output_file, "w", encoding=encoding)
                try:
                    async with cur.copy(f"COPY {schema}.{table}{cols} TO STDOUT WITH ({', '.join(options)})") as copy:
                        async for data in copy:
                            decoded = data.decode(encoding) if isinstance(data, bytes) else data
                            await asyncio.to_thread(file_handle.write, decoded)
                finally:
                    await asyncio.to_thread(file_handle.close)

                # Get row count
                result = await self.execute(f"SELECT COUNT(*) AS count FROM {schema}.{table}")
                return result[0]["count"]
        except Exception:
            raise

    async def copy_from_csv(
        self,
        table: str,
        input_file: str | Path,
        schema: str = "public",
        columns: Optional[list[str]] = None,
        delimiter: str = ",",
        header: bool = True,
        null_string: str = "",
        encoding: str = "UTF8",
    ) -> int:
        """Import CSV file into table.

        Args:
            table: Table name.
            input_file: Input CSV file path.
            schema: Schema name.
            columns: Specific columns to import.
            delimiter: Field delimiter.
            header: First row is header.
            null_string: String representing NULL.
            encoding: File encoding.

        Returns:
            Number of rows imported.

        Example:
            count = await db.copy_from_csv("users", "users.csv")
        """
        input_file = Path(input_file)
        validate_identifiers(table, schema)
        if columns:
            validate_identifiers(*columns)

        cols = f"({', '.join(columns)})" if columns else ""

        options = [
            f"FORMAT CSV",
            f"DELIMITER '{delimiter}'",
            f"NULL '{null_string}'",
            f"ENCODING '{encoding}'",
        ]
        if header:
            options.append("HEADER")

        async with self.cursor() as cur:
            # Open file and read data
            file_handle = await asyncio.to_thread(open, input_file, "r", encoding=encoding)
            try:
                async with cur.copy(f"COPY {schema}.{table}{cols} FROM STDIN WITH ({', '.join(options)})") as copy:
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

        Args:
            channel: Channel name.

        Yields:
            Notification payloads.

        Example:
            async for payload in db.listen("events"):
                event = json.loads(payload)
                handle_event(event)
        """
        validate_identifier(channel)

        async with self.connect(autocommit=True) as conn:
            await conn.execute(f"LISTEN {channel}")
            async for notify in conn.notifies():
                yield notify.payload

    async def notify(self, channel: str, payload: str = "") -> None:
        """Send notification on a channel.

        Args:
            channel: Channel name.
            payload: Notification payload (max 8000 bytes).

        Example:
            await db.notify("events", json.dumps({"type": "user_created", "id": 1}))
        """
        validate_identifier(channel)
        await self.execute(f"NOTIFY {channel}, %s", [payload], autocommit=True)

    async def close(self) -> None:
        """Close database connections.

        Note: AsyncDatabase creates connections on-demand and closes them
        after each operation. This method exists for API consistency with
        the context manager protocol.
        """
        pass

    async def __aenter__(self) -> "AsyncDatabase":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    def __repr__(self) -> str:
        return f"AsyncDatabase({self.config.database!r} @ {self.config.host}:{self.config.port})"
