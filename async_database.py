"""
Async Database class for pycopg.

Provides async/await interface for PostgreSQL operations using psycopg's async support.
"""

from __future__ import annotations

import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator, Optional, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg import AsyncConnection, AsyncCursor

from pycopg.config import Config

if TYPE_CHECKING:
    from psycopg_pool import AsyncConnectionPool


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
        self._pool: Optional[AsyncConnectionPool] = None

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
        conn = await psycopg.AsyncConnection.connect(
            **self.config.connect_params(),
            autocommit=autocommit,
        )
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
        async with self.connect(autocommit=autocommit) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                yield cur
                if not autocommit:
                    await conn.commit()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncConnection]:
        """Async context manager for transactions.

        Automatically commits on success, rolls back on exception.

        Yields:
            AsyncConnection in a transaction.

        Example:
            async with db.transaction() as conn:
                await conn.execute("INSERT INTO users (name) VALUES (%s)", ["Alice"])
                await conn.execute("UPDATE stats SET count = count + 1")
                # Commits automatically if no exception
        """
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
        total = 0
        async with self.cursor() as cur:
            for params in params_seq:
                await cur.execute(sql, params)
                total += cur.rowcount
        return total

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
        self._validate_identifier(name)
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
        result = await self.execute("""
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = %s AND table_name = %s
        """, [schema, name])
        return len(result) > 0

    async def table_info(self, name: str, schema: str = "public") -> list[dict]:
        """Get column information for a table."""
        return await self.execute("""
            SELECT
                column_name,
                data_type,
                is_nullable,
                column_default,
                ordinal_position
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
                rolcanlogin AS login
            FROM pg_roles
            {where_clause}
            ORDER BY rolname
        """)

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

        self._validate_identifier(table)
        self._validate_identifier(schema)

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
        self._validate_identifier(channel)

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
        self._validate_identifier(channel)
        await self.execute(f"NOTIFY {channel}, %s", [payload], autocommit=True)

    # =========================================================================
    # UTILITY
    # =========================================================================

    @staticmethod
    def _validate_identifier(name: str) -> None:
        """Validate SQL identifier to prevent injection."""
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
            raise ValueError(f"Invalid identifier: {name}")

    async def close(self) -> None:
        """Close database connections."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def __aenter__(self) -> "AsyncDatabase":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    def __repr__(self) -> str:
        return f"AsyncDatabase({self.config.database!r} @ {self.config.host}:{self.config.port})"
