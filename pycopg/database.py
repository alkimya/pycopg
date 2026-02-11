"""
Core Database class - the main entry point for pycopg.

Provides high-level operations for PostgreSQL/PostGIS/TimescaleDB.
"""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator, Literal, Optional, Sequence

import psycopg
from psycopg import OperationalError
from psycopg.rows import dict_row
from psycopg.pq import TransactionStatus
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log

from pycopg.config import Config
from pycopg.utils import validate_identifier, validate_identifiers, validate_interval, validate_index_method
from pycopg import queries

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import geopandas as gpd
    import pandas as pd


class Database:
    """High-level PostgreSQL/PostGIS/TimescaleDB interface.

    Combines psycopg (for DDL/admin) and SQLAlchemy (for DataFrame operations)
    into a simple, unified API.

    Attributes:
        config: Database connection configuration.
        engine: SQLAlchemy engine for DataFrame operations.

    Example:
        # Connect from .env
        db = Database.from_env()

        # Connect with URL
        db = Database.from_url("postgresql://user:pass@localhost/mydb")

        # Connect with explicit params
        db = Database(Config(host="localhost", database="mydb", user="admin", password="secret"))

        # Explore database
        print(db.list_schemas())
        print(db.list_tables("public"))
        print(db.table_info("users"))
        print(db.size())

        # Create tables from DataFrames
        db.from_dataframe(df, "users", primary_key="id")
        db.from_geodataframe(gdf, "parcels", spatial_index=True)

        # TimescaleDB
        db.create_hypertable("events", "timestamp")
    """

    def __init__(self, config: Config):
        """Initialize database connection.

        Args:
            config: Database configuration.
        """
        self.config = config
        self._engine: Optional[Engine] = None
        self._session_conn: Optional[psycopg.Connection] = None

    @classmethod
    def from_env(cls, dotenv_path: Optional[str | Path] = None) -> "Database":
        """Create Database from environment variables.

        Args:
            dotenv_path: Optional path to .env file.

        Returns:
            Database instance.

        Example:
            db = Database.from_env()
            db = Database.from_env("/path/to/.env")
        """
        return cls(Config.from_env(dotenv_path))

    @classmethod
    def from_url(cls, url: str) -> "Database":
        """Create Database from connection URL.

        Args:
            url: PostgreSQL connection URL.

        Returns:
            Database instance.

        Example:
            db = Database.from_url("postgresql://admin:secret@localhost:5432/mydb")
        """
        return cls(Config.from_url(url))

    @classmethod
    def create(
        cls,
        name: str,
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
        password: str = "",
        owner: Optional[str] = None,
        template: str = "template1",
        if_not_exists: bool = True,
    ) -> "Database":
        """Create a new database and return a connection to it.

        This is a convenience method that:
        1. Connects to the 'postgres' database
        2. Creates the new database
        3. Returns a Database instance connected to the new database

        Args:
            name: Name of the database to create.
            host: Database host (default: localhost).
            port: Database port (default: 5432).
            user: Database user (default: postgres).
            password: Database password.
            owner: Optional owner role for the new database.
            template: Template database (default: template1).
            if_not_exists: If True, don't error if database already exists.

        Returns:
            Database instance connected to the newly created database.

        Example:
            # Create and connect to a new database
            db = Database.create("myapp", user="admin", password="secret")

            # With owner
            db = Database.create("myapp", owner="appuser", user="admin", password="secret")

            # Safe creation (won't fail if exists)
            db = Database.create("myapp", if_not_exists=True)
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
        with psycopg.connect(**admin_config.connect_params(), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (name,)
                )
                exists = cur.fetchone() is not None

                if exists:
                    if not if_not_exists:
                        raise ValueError(f"Database '{name}' already exists")
                else:
                    # Create the database
                    owner_clause = f" OWNER {owner}" if owner else ""
                    cur.execute(f"CREATE DATABASE {name}{owner_clause} TEMPLATE {template}")

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
    def create_from_env(
        cls,
        name: str,
        owner: Optional[str] = None,
        template: str = "template1",
        if_not_exists: bool = True,
        dotenv_path: Optional[str | Path] = None,
    ) -> "Database":
        """Create a new database using connection params from environment.

        Uses PGHOST, PGPORT, PGUSER, PGPASSWORD from environment or .env file,
        then creates the database and returns a connection to it.

        Args:
            name: Name of the database to create.
            owner: Optional owner role for the new database.
            template: Template database (default: template1).
            if_not_exists: If True, don't error if database already exists.
            dotenv_path: Optional path to .env file.

        Returns:
            Database instance connected to the newly created database.

        Example:
            # Uses credentials from .env or environment
            db = Database.create_from_env("myapp")

            # With custom .env path
            db = Database.create_from_env("myapp", dotenv_path="/path/to/.env")
        """
        # Load config from env (but we'll change the database later)
        env_config = Config.from_env(dotenv_path)

        return cls.create(
            name=name,
            host=env_config.host,
            port=env_config.port,
            user=env_config.user,
            password=env_config.password,
            owner=owner,
            template=template,
            if_not_exists=if_not_exists,
        )

    @property
    def engine(self) -> Engine:
        """Get or create SQLAlchemy engine (lazy initialization)."""
        if self._engine is None:
            self._engine = create_engine(self.config.url)
        return self._engine

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(OperationalError),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    def _connect_with_retry(self, autocommit: bool = False) -> psycopg.Connection:
        """Establish connection with retry for transient failures."""
        return psycopg.connect(**self.config.connect_params(), autocommit=autocommit)

    @contextmanager
    def connect(self, autocommit: bool = False) -> Iterator[psycopg.Connection]:
        """Context manager for psycopg connection.

        Args:
            autocommit: Enable autocommit mode (required for CREATE DATABASE, etc.)

        Yields:
            psycopg Connection object.

        Example:
            with db.connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM users")
                    rows = cur.fetchall()
        """
        conn = self._connect_with_retry(autocommit=autocommit)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def cursor(self, autocommit: bool = False) -> Iterator[psycopg.Cursor]:
        """Context manager for psycopg cursor with dict rows.

        Args:
            autocommit: Enable autocommit mode.

        Yields:
            psycopg Cursor with dict_row factory.

        Example:
            with db.cursor() as cur:
                cur.execute("SELECT * FROM users WHERE id = %s", [1])
                user = cur.fetchone()  # Returns dict
        """
        # Use session connection if available
        if self._session_conn is not None:
            with self._session_conn.cursor(row_factory=dict_row) as cur:
                yield cur
                if not autocommit:
                    status = self._session_conn.info.transaction_status
                    if status == TransactionStatus.INTRANS:
                        self._session_conn.commit()
                    elif status == TransactionStatus.INERROR:
                        self._session_conn.rollback()
                    # IDLE: no open transaction, nothing to do
                    # ACTIVE: should not occur at cursor exit (mid-query)
                    # UNKNOWN: connection in bad state, skip
        else:
            with self.connect(autocommit=autocommit) as conn:
                with conn.cursor(row_factory=dict_row) as cur:
                    yield cur
                    if not autocommit:
                        conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[psycopg.Connection]:
        """Context manager for transactions.

        Automatically commits on success, rolls back on exception.
        If a session is active, reuses the session connection.

        Yields:
            psycopg Connection in a transaction.
        """
        if self._session_conn is not None:
            # Reuse existing session connection
            with self._session_conn.transaction():
                yield self._session_conn
        else:
            with self.connect() as conn:
                with conn.transaction():
                    yield conn

    @contextmanager
    def session(self, autocommit: bool = False) -> Iterator["Database"]:
        """Context manager for session mode with connection reuse.

        In session mode, all operations reuse the same connection,
        significantly reducing overhead for multiple sequential operations.

        Args:
            autocommit: Enable autocommit mode for the session.

        Yields:
            Self (Database instance with active session).

        Example:
            # Without session: each operation opens/closes a connection
            db.execute("SELECT 1")  # Open, execute, close
            db.execute("SELECT 2")  # Open, execute, close

            # With session: single connection for all operations
            with db.session() as session:
                session.execute("SELECT 1")  # Reuse connection
                session.execute("SELECT 2")  # Reuse connection
                session.insert_batch("users", rows)  # Reuse connection
                # Connection closed automatically at end

            # Useful for batch operations
            with db.session() as session:
                for table in tables:
                    session.truncate_table(table)
                    session.insert_batch(table, data[table])
        """
        if self._session_conn is not None:
            raise RuntimeError("Already in session mode. Nested sessions are not supported.")

        self._session_conn = psycopg.connect(
            **self.config.connect_params(),
            autocommit=autocommit
        )
        try:
            yield self
        finally:
            try:
                if not autocommit:
                    self._session_conn.commit()
                self._session_conn.close()
            except Exception:
                # Cleanup failure - connection may already be closed or broken.
                # Don't suppress: let the exception propagate after state reset.
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

    def execute(self, sql: str, params: Optional[Sequence] = None, autocommit: bool = False) -> list[dict]:
        """Execute SQL and return results as list of dicts.

        Args:
            sql: SQL query to execute.
            params: Query parameters.
            autocommit: Enable autocommit mode.

        Returns:
            List of result rows as dicts.

        Example:
            users = db.execute("SELECT * FROM users WHERE active = %s", [True])
            db.execute("UPDATE users SET active = %s WHERE id = %s", [False, 1])
        """
        with self.cursor(autocommit=autocommit) as cur:
            cur.execute(sql, params)
            if cur.description:
                return cur.fetchall()
            return []

    def execute_many(self, sql: str, params_seq: Sequence[Sequence]) -> int:
        """Execute SQL for multiple parameter sets.

        Uses psycopg's executemany() for better performance than sequential
        execute() calls.

        Args:
            sql: SQL query with placeholders.
            params_seq: Sequence of parameter sequences.

        Returns:
            Total number of affected rows.

        Example:
            db.execute_many(
                "INSERT INTO users (name, email) VALUES (%s, %s)",
                [("Alice", "alice@example.com"), ("Bob", "bob@example.com")]
            )
        """
        with self.cursor() as cur:
            cur.executemany(sql, params_seq)
            return cur.rowcount

    def insert_batch(
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
        For very large datasets (>10000 rows), consider using copy_insert().

        Args:
            table: Table name.
            rows: List of row dicts (all must have same keys).
            schema: Schema name.
            on_conflict: Optional ON CONFLICT clause (e.g., "DO NOTHING",
                        "(id) DO UPDATE SET name = EXCLUDED.name").
            batch_size: Max rows per INSERT statement (default from config).

        Returns:
            Total number of rows inserted.

        Example:
            db.insert_batch("users", [
                {"name": "Alice", "email": "alice@example.com"},
                {"name": "Bob", "email": "bob@example.com"},
            ])

            # With conflict handling
            db.insert_batch("users", rows, on_conflict="(email) DO NOTHING")
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
        with self.cursor() as cur:
            # Process in batches
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]

                # Build VALUES (...), (...), ...
                placeholders = []
                params = []
                for row in batch:
                    row_placeholders = ", ".join(["%s"] * len(columns))
                    placeholders.append(f"({row_placeholders})")
                    params.extend(row.get(col) for col in columns)

                values_str = ", ".join(placeholders)
                sql = f"INSERT INTO {schema}.{table} ({cols_str}) VALUES {values_str}{conflict_clause}"

                cur.execute(sql, params)
                total += cur.rowcount

        return total

    def copy_insert(
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
            columns: Optional list of column names. If not provided,
                    uses keys from first row.

        Returns:
            Number of rows inserted.

        Example:
            # Insert 100k rows efficiently
            db.copy_insert("events", events_list)
        """
        if not rows:
            return 0

        validate_identifiers(table, schema)

        if columns is None:
            columns = list(rows[0].keys())
        for col in columns:
            validate_identifier(col)

        cols_str = ", ".join(columns)

        with self.connect() as conn:
            with conn.cursor() as cur:
                with cur.copy(f"COPY {schema}.{table} ({cols_str}) FROM STDIN") as copy:
                    for row in rows:
                        copy.write_row([row.get(col) for col in columns])
            conn.commit()
            return len(rows)

    def fetch_one(self, sql: str, params: Optional[Sequence] = None) -> Optional[dict]:
        """Execute SQL and return single row.

        Args:
            sql: SQL query.
            params: Query parameters.

        Returns:
            Single row as dict, or None.

        Example:
            user = db.fetch_one("SELECT * FROM users WHERE id = %s", [1])
        """
        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def fetch_val(self, sql: str, params: Optional[Sequence] = None) -> Any:
        """Execute SQL and return single value.

        Args:
            sql: SQL query returning single column.
            params: Query parameters.

        Returns:
            Single value, or None.

        Example:
            count = db.fetch_val("SELECT COUNT(*) FROM users")
        """
        row = self.fetch_one(sql, params)
        if row:
            return list(row.values())[0]
        return None

    # =========================================================================
    # DATABASE ADMINISTRATION
    # =========================================================================

    def create_database(self, name: str, owner: Optional[str] = None, template: str = "template1") -> None:
        """Create a new database.

        Args:
            name: Database name.
            owner: Optional owner role.
            template: Template database (default: template1).

        Example:
            db.create_database("myapp")
            db.create_database("myapp", owner="appuser")
        """
        validate_identifier(name)
        if owner:
            validate_identifier(owner)
        validate_identifier(template)
        owner_clause = f" OWNER {owner}" if owner else ""
        # Connect to postgres for database creation
        admin_config = self.config.with_database("postgres")
        with psycopg.connect(**admin_config.connect_params(), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE {name}{owner_clause} TEMPLATE {template}")

    def drop_database(self, name: str, if_exists: bool = True) -> None:
        """Drop a database.

        Args:
            name: Database name.
            if_exists: Don't error if database doesn't exist.

        Example:
            db.drop_database("myapp")
        """
        validate_identifier(name)
        if_clause = "IF EXISTS " if if_exists else ""
        admin_config = self.config.with_database("postgres")
        with psycopg.connect(**admin_config.connect_params(), autocommit=True) as conn:
            with conn.cursor() as cur:
                # Terminate existing connections
                cur.execute(f"""
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = %s
                    AND pid <> pg_backend_pid()
                """, [name])
                cur.execute(f"DROP DATABASE {if_clause}{name}")

    def database_exists(self, name: str) -> bool:
        """Check if a database exists.

        Args:
            name: Database name.

        Returns:
            True if database exists.
        """
        admin_config = self.config.with_database("postgres")
        with psycopg.connect(**admin_config.connect_params()) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", [name])
                return cur.fetchone() is not None

    def list_databases(self) -> list[str]:
        """List all databases.

        Returns:
            List of database names.
        """
        result = self.execute("""
            SELECT datname FROM pg_database
            WHERE datistemplate = false
            ORDER BY datname
        """)
        return [r["datname"] for r in result]

    # =========================================================================
    # EXTENSIONS
    # =========================================================================

    def create_extension(self, name: str, schema: Optional[str] = None, if_not_exists: bool = True) -> None:
        """Create a PostgreSQL extension.

        Args:
            name: Extension name (e.g., 'postgis', 'timescaledb', 'uuid-ossp').
            schema: Optional schema to install extension in.
            if_not_exists: Don't error if extension exists.

        Example:
            db.create_extension("postgis")
            db.create_extension("uuid-ossp", schema="extensions")
            db.create_extension("timescaledb")
        """
        if_clause = "IF NOT EXISTS " if if_not_exists else ""
        schema_clause = f" SCHEMA {schema}" if schema else ""
        self.execute(f'CREATE EXTENSION {if_clause}"{name}"{schema_clause}', autocommit=True)

    def drop_extension(self, name: str, if_exists: bool = True, cascade: bool = False) -> None:
        """Drop a PostgreSQL extension.

        Args:
            name: Extension name.
            if_exists: Don't error if extension doesn't exist.
            cascade: Drop dependent objects.
        """
        if_clause = "IF EXISTS " if if_exists else ""
        cascade_clause = " CASCADE" if cascade else ""
        self.execute(f'DROP EXTENSION {if_clause}"{name}"{cascade_clause}', autocommit=True)

    def list_extensions(self) -> list[dict]:
        """List installed extensions.

        Returns:
            List of dicts with extname, extversion, nspname (schema).
        """
        return self.execute("""
            SELECT e.extname, e.extversion, n.nspname
            FROM pg_extension e
            JOIN pg_namespace n ON e.extnamespace = n.oid
            ORDER BY e.extname
        """)

    def has_extension(self, name: str) -> bool:
        """Check if an extension is installed.

        Args:
            name: Extension name.

        Returns:
            True if extension is installed.
        """
        result = self.execute("SELECT 1 FROM pg_extension WHERE extname = %s", [name])
        return len(result) > 0

    # =========================================================================
    # SCHEMAS
    # =========================================================================

    def create_schema(self, name: str, if_not_exists: bool = True, owner: Optional[str] = None) -> None:
        """Create a schema.

        Args:
            name: Schema name.
            if_not_exists: Don't error if schema exists.
            owner: Optional owner role.

        Example:
            db.create_schema("data")
            db.create_schema("app", owner="appuser")
        """
        validate_identifier(name)
        if owner:
            validate_identifier(owner)
        if_clause = "IF NOT EXISTS " if if_not_exists else ""
        owner_clause = f" AUTHORIZATION {owner}" if owner else ""
        self.execute(f"CREATE SCHEMA {if_clause}{name}{owner_clause}")

    def drop_schema(self, name: str, if_exists: bool = True, cascade: bool = False) -> None:
        """Drop a schema.

        Args:
            name: Schema name.
            if_exists: Don't error if schema doesn't exist.
            cascade: Drop all objects in schema.
        """
        validate_identifier(name)
        if_clause = "IF EXISTS " if if_exists else ""
        cascade_clause = " CASCADE" if cascade else ""
        self.execute(f"DROP SCHEMA {if_clause}{name}{cascade_clause}")

    def list_schemas(self) -> list[str]:
        """List all schemas.

        Returns:
            List of schema names.
        """
        result = self.execute("""
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name NOT LIKE 'pg_%'
            AND schema_name != 'information_schema'
            ORDER BY schema_name
        """)
        return [r["schema_name"] for r in result]

    def schema_exists(self, name: str) -> bool:
        """Check if a schema exists.

        Args:
            name: Schema name.

        Returns:
            True if schema exists.
        """
        result = self.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", [name]
        )
        return len(result) > 0

    # =========================================================================
    # TABLES
    # =========================================================================

    def list_tables(self, schema: str = "public") -> list[str]:
        """List tables in a schema.

        Args:
            schema: Schema name (default: public).

        Returns:
            List of table names.
        """
        result = self.execute("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """, [schema])
        return [r["table_name"] for r in result]

    def table_exists(self, name: str, schema: str = "public") -> bool:
        """Check if a table exists.

        Args:
            name: Table name.
            schema: Schema name.

        Returns:
            True if table exists.
        """
        result = self.execute(queries.TABLE_EXISTS, [schema, name])
        return len(result) > 0

    def list_columns(self, table: str, schema: str = "public") -> list[str]:
        """Get list of column names for a table.

        Args:
            table: Table name.
            schema: Schema name (default: "public").

        Returns:
            List of column names in ordinal order.
        """
        result = self.execute(queries.GET_COLUMNS, [schema, table])
        return [row["column_name"] for row in result]

    def columns_with_types(self, table: str, schema: str = "public") -> list[tuple[str, str]]:
        """Get list of (column_name, data_type) tuples for a table.

        Args:
            table: Table name.
            schema: Schema name (default: "public").

        Returns:
            List of (name, type) tuples in ordinal order.
        """
        result = self.execute(queries.GET_COLUMNS, [schema, table])
        return [(row["column_name"], row["data_type"]) for row in result]

    def drop_table(self, name: str, schema: str = "public", if_exists: bool = True, cascade: bool = False) -> None:
        """Drop a table.

        Args:
            name: Table name.
            schema: Schema name.
            if_exists: Don't error if table doesn't exist.
            cascade: Drop dependent objects.
        """
        validate_identifiers(name, schema)
        if_clause = "IF EXISTS " if if_exists else ""
        cascade_clause = " CASCADE" if cascade else ""
        self.execute(f"DROP TABLE {if_clause}{schema}.{name}{cascade_clause}")

    def truncate_table(self, name: str, schema: str = "public", cascade: bool = False) -> None:
        """Truncate a table (delete all rows).

        Args:
            name: Table name.
            schema: Schema name.
            cascade: Truncate dependent tables.
        """
        validate_identifiers(name, schema)
        cascade_clause = " CASCADE" if cascade else ""
        self.execute(f"TRUNCATE TABLE {schema}.{name}{cascade_clause}")

    def table_info(self, name: str, schema: str = "public") -> list[dict]:
        """Get column information for a table.

        Args:
            name: Table name.
            schema: Schema name.

        Returns:
            List of column info dicts with:
            - column_name, data_type, is_nullable, column_default, ordinal_position
        """
        return self.execute("""
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

    def row_count(self, name: str, schema: str = "public") -> int:
        """Get approximate row count for a table.

        Uses pg_stat for speed. For exact count, use execute("SELECT COUNT(*)...").

        Args:
            name: Table name.
            schema: Schema name.

        Returns:
            Approximate row count.
        """
        result = self.execute("""
            SELECT reltuples::bigint AS count
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = %s AND c.relname = %s
        """, [schema, name])
        return result[0]["count"] if result else 0

    # =========================================================================
    # CONSTRAINTS & INDEXES
    # =========================================================================

    def add_primary_key(self, table: str, columns: str | list[str], schema: str = "public", name: Optional[str] = None) -> None:
        """Add primary key constraint to a table.

        Args:
            table: Table name.
            columns: Column name or list of column names.
            schema: Schema name.
            name: Optional constraint name.

        Example:
            db.add_primary_key("users", "id")
            db.add_primary_key("order_items", ["order_id", "product_id"])
        """
        if isinstance(columns, str):
            columns = [columns]
        validate_identifiers(table, schema, *columns)
        if name:
            validate_identifier(name)

        cols_str = ", ".join(columns)
        constraint_name = name or f"{table}_pkey"
        self.execute(f"ALTER TABLE {schema}.{table} ADD CONSTRAINT {constraint_name} PRIMARY KEY ({cols_str})")

    def add_foreign_key(
        self,
        table: str,
        columns: str | list[str],
        ref_table: str,
        ref_columns: str | list[str],
        schema: str = "public",
        ref_schema: str = "public",
        name: Optional[str] = None,
        on_delete: str = "NO ACTION",
        on_update: str = "NO ACTION",
    ) -> None:
        """Add foreign key constraint.

        Args:
            table: Source table name.
            columns: Source column(s).
            ref_table: Referenced table name.
            ref_columns: Referenced column(s).
            schema: Source table schema.
            ref_schema: Referenced table schema.
            name: Optional constraint name.
            on_delete: ON DELETE action (CASCADE, SET NULL, NO ACTION, etc.)
            on_update: ON UPDATE action.

        Example:
            db.add_foreign_key("orders", "user_id", "users", "id", on_delete="CASCADE")
        """
        if isinstance(columns, str):
            columns = [columns]
        if isinstance(ref_columns, str):
            ref_columns = [ref_columns]

        # Validate all identifiers
        validate_identifiers(table, schema, ref_table, ref_schema, *columns, *ref_columns)
        if name:
            validate_identifier(name)

        # Validate ON DELETE/UPDATE actions
        valid_actions = {"NO ACTION", "RESTRICT", "CASCADE", "SET NULL", "SET DEFAULT"}
        if on_delete.upper() not in valid_actions:
            raise ValueError(f"Invalid ON DELETE action: {on_delete}. Must be one of: {valid_actions}")
        if on_update.upper() not in valid_actions:
            raise ValueError(f"Invalid ON UPDATE action: {on_update}. Must be one of: {valid_actions}")

        cols_str = ", ".join(columns)
        ref_cols_str = ", ".join(ref_columns)
        constraint_name = name or f"{table}_{columns[0]}_fkey"

        self.execute(f"""
            ALTER TABLE {schema}.{table}
            ADD CONSTRAINT {constraint_name}
            FOREIGN KEY ({cols_str})
            REFERENCES {ref_schema}.{ref_table} ({ref_cols_str})
            ON DELETE {on_delete}
            ON UPDATE {on_update}
        """)

    def add_unique_constraint(self, table: str, columns: str | list[str], schema: str = "public", name: Optional[str] = None) -> None:
        """Add unique constraint.

        Args:
            table: Table name.
            columns: Column(s) to make unique.
            schema: Schema name.
            name: Optional constraint name.

        Example:
            db.add_unique_constraint("users", "email")
            db.add_unique_constraint("products", ["category", "sku"])
        """
        if isinstance(columns, str):
            columns = [columns]
        validate_identifiers(table, schema, *columns)
        if name:
            validate_identifier(name)
        cols_str = ", ".join(columns)
        constraint_name = name or f"{table}_{'_'.join(columns)}_key"
        self.execute(f"ALTER TABLE {schema}.{table} ADD CONSTRAINT {constraint_name} UNIQUE ({cols_str})")

    def create_index(
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
            db.create_index("users", "email", unique=True)
            db.create_index("products", ["category", "price"])
            db.create_index("documents", "content", method="gin")
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

        self.execute(f"""
            CREATE {unique_clause}INDEX {if_clause}{index_name}
            ON {schema}.{table} USING {method} ({cols_str})
        """)

    def drop_index(self, name: str, schema: str = "public", if_exists: bool = True) -> None:
        """Drop an index.

        Args:
            name: Index name.
            schema: Schema name.
            if_exists: Don't error if index doesn't exist.
        """
        if_clause = "IF EXISTS " if if_exists else ""
        self.execute(f"DROP INDEX {if_clause}{schema}.{name}")

    def list_indexes(self, table: str, schema: str = "public") -> list[dict]:
        """List indexes on a table.

        Args:
            table: Table name.
            schema: Schema name.

        Returns:
            List of index info dicts.
        """
        return self.execute("""
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

    def list_constraints(self, table: str, schema: str = "public") -> list[dict]:
        """List constraints on a table.

        Args:
            table: Table name.
            schema: Schema name.

        Returns:
            List of constraint info dicts.
        """
        return self.execute("""
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
    # DATAFRAME OPERATIONS
    # =========================================================================

    def from_dataframe(
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
            index: Write DataFrame index as column.
            dtype: Optional dict of column name to SQLAlchemy types.

        Example:
            db.from_dataframe(users_df, "users", primary_key="id")
            db.from_dataframe(orders_df, "orders", if_exists="append")
        """
        df.to_sql(
            name=table,
            con=self.engine,
            schema=schema,
            if_exists=if_exists,
            index=index,
            dtype=dtype,
        )

        if primary_key and if_exists != "append":
            self.add_primary_key(table, primary_key, schema)

    def to_dataframe(
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
            users = db.to_dataframe("users")
            active = db.to_dataframe(sql="SELECT * FROM users WHERE active = :active", params={"active": True})
        """
        import pandas as pd

        if table and sql:
            raise ValueError("Specify either table or sql, not both")
        if not table and not sql:
            raise ValueError("Specify either table or sql")

        if table:
            sql = f"SELECT * FROM {schema}.{table}"

        return pd.read_sql(text(sql), self.engine, params=params)

    def from_geodataframe(
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
            spatial_index: Create GIST spatial index on geometry.
            geometry_column: Name of geometry column.
            srid: Override SRID (extracted from CRS if not specified).

        Example:
            db.from_geodataframe(parcels, "parcels", spatial_index=True)
        """
        # Ensure PostGIS is available
        if not self.has_extension("postgis"):
            raise RuntimeError("PostGIS extension not installed. Run db.create_extension('postgis')")

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

        gdf.to_postgis(
            name=table,
            con=self.engine,
            schema=schema,
            if_exists=if_exists,
            index=False,
        )

        if primary_key and if_exists != "append":
            self.add_primary_key(table, primary_key, schema)

        if spatial_index and if_exists != "append":
            self.create_spatial_index(table, geometry_column, schema)

    def to_geodataframe(
        self,
        table: Optional[str] = None,
        schema: str = "public",
        sql: Optional[str] = None,
        geometry_column: str = "geometry",
        params: Optional[dict] = None,
    ) -> "gpd.GeoDataFrame":
        """Read table or query into GeoDataFrame.

        Args:
            table: Table name.
            schema: Schema name.
            sql: SQL query.
            geometry_column: Name of geometry column.
            params: Query parameters.

        Returns:
            geopandas GeoDataFrame.

        Example:
            parcels = db.to_geodataframe("parcels", schema="geo")
        """
        import geopandas as gpd

        if table and sql:
            raise ValueError("Specify either table or sql, not both")
        if not table and not sql:
            raise ValueError("Specify either table or sql")

        if table:
            sql = f"SELECT * FROM {schema}.{table}"

        return gpd.read_postgis(text(sql), self.engine, geom_col=geometry_column, params=params)

    # =========================================================================
    # POSTGIS SPATIAL OPERATIONS
    # =========================================================================

    def create_spatial_index(self, table: str, column: str = "geometry", schema: str = "public", name: Optional[str] = None) -> None:
        """Create a GIST spatial index on a geometry column.

        Args:
            table: Table name.
            column: Geometry column name.
            schema: Schema name.
            name: Index name (auto-generated if not provided).

        Example:
            db.create_spatial_index("parcels", "geom")
        """
        index_name = name or f"idx_{table}_{column}_gist"
        self.execute(f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {schema}.{table} USING GIST ({column})
        """)

    def list_geometry_columns(self, schema: Optional[str] = None) -> list[dict]:
        """List geometry columns in the database.

        Args:
            schema: Optional schema filter.

        Returns:
            List of geometry column info.
        """
        where_clause = "WHERE f_table_schema = %s" if schema else ""
        params = [schema] if schema else None
        return self.execute(f"""
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

    def create_hypertable(
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
            db.create_hypertable("events", "created_at", chunk_time_interval="1 week")
        """
        if not self.has_extension("timescaledb"):
            raise RuntimeError("TimescaleDB extension not installed. Run db.create_extension('timescaledb')")

        validate_identifiers(table, schema, time_column)
        validate_interval(chunk_time_interval)

        self.execute(f"""
            SELECT create_hypertable(
                '{schema}.{table}',
                '{time_column}',
                chunk_time_interval => INTERVAL '{chunk_time_interval}',
                if_not_exists => {str(if_not_exists).upper()},
                migrate_data => {str(migrate_data).upper()}
            )
        """)

    def enable_compression(
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
            db.enable_compression("events", segment_by="device_id", order_by="timestamp DESC")
        """
        if not self.has_extension("timescaledb"):
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

        self.execute(f"ALTER TABLE {schema}.{table} SET ({', '.join(settings)})")

    def add_compression_policy(
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
            db.add_compression_policy("events", compress_after="30 days")
        """
        if not self.has_extension("timescaledb"):
            raise RuntimeError(
                "TimescaleDB extension not installed. "
                "Run db.create_extension('timescaledb')"
            )

        self.execute(f"""
            SELECT add_compression_policy(
                '{schema}.{table}',
                compress_after => INTERVAL '{compress_after}'
            )
        """)

    def add_retention_policy(
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
            db.add_retention_policy("logs", drop_after="90 days")
        """
        if not self.has_extension("timescaledb"):
            raise RuntimeError(
                "TimescaleDB extension not installed. "
                "Run db.create_extension('timescaledb')"
            )

        self.execute(f"""
            SELECT add_retention_policy(
                '{schema}.{table}',
                drop_after => INTERVAL '{drop_after}'
            )
        """)

    def list_hypertables(self) -> list[dict]:
        """List all hypertables.

        Returns:
            List of hypertable info dicts.
        """
        if not self.has_extension("timescaledb"):
            raise RuntimeError(
                "TimescaleDB extension not installed. "
                "Run db.create_extension('timescaledb')"
            )

        return self.execute("""
            SELECT
                hypertable_schema AS schema,
                hypertable_name AS table_name,
                num_dimensions,
                num_chunks,
                compression_enabled
            FROM timescaledb_information.hypertables
            ORDER BY hypertable_schema, hypertable_name
        """)

    def hypertable_info(self, table: str, schema: str = "public") -> dict:
        """Get detailed info about a hypertable.

        Args:
            table: Hypertable name.
            schema: Schema name.

        Returns:
            Dict with hypertable details including size info.
        """
        if not self.has_extension("timescaledb"):
            raise RuntimeError(
                "TimescaleDB extension not installed. "
                "Run db.create_extension('timescaledb')"
            )

        result = self.execute("""
            SELECT
                hypertable_size(format('%I.%I', %s, %s)) AS total_size,
                hypertable_detailed_size(format('%I.%I', %s, %s)) AS detailed_size
        """, [schema, table, schema, table])
        return result[0] if result else {}

    # =========================================================================
    # SIZE & STATS
    # =========================================================================

    def size(self, pretty: bool = True) -> str | int:
        """Get database size.

        Args:
            pretty: Return human-readable size (e.g., '1.2 GB').

        Returns:
            Database size.

        Example:
            print(db.size())  # '256 MB'
            print(db.size(pretty=False))  # 268435456
        """
        if pretty:
            result = self.execute(
                "SELECT pg_size_pretty(pg_database_size(%s)) AS size",
                [self.config.database]
            )
            return result[0]["size"]
        else:
            result = self.execute(
                "SELECT pg_database_size(%s) AS size",
                [self.config.database]
            )
            return result[0]["size"]

    def table_size(self, table: str, schema: str = "public", pretty: bool = True) -> str | int:
        """Get table size including indexes.

        Args:
            table: Table name.
            schema: Schema name.
            pretty: Return human-readable size.

        Returns:
            Table size.
        """
        full_name = f"{schema}.{table}"
        if pretty:
            result = self.execute(
                "SELECT pg_size_pretty(pg_total_relation_size(%s)) AS size",
                [full_name]
            )
            return result[0]["size"]
        else:
            result = self.execute(
                "SELECT pg_total_relation_size(%s) AS size",
                [full_name]
            )
            return result[0]["size"]

    def table_sizes(self, schema: str = "public", limit: int = 20) -> list[dict]:
        """Get sizes of all tables in schema, sorted by size.

        Args:
            schema: Schema name.
            limit: Max tables to return.

        Returns:
            List of table size info.
        """
        # Use %%I to escape the % for psycopg, format() will see %I
        return self.execute("""
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
    # UTILITY
    # =========================================================================

    def vacuum(self, table: Optional[str] = None, schema: str = "public", analyze: bool = True, full: bool = False) -> None:
        """Vacuum database or table.

        Args:
            table: Table name (None for whole database).
            schema: Schema name.
            analyze: Update statistics.
            full: Full vacuum (reclaims more space but locks table).
        """
        options = []
        if full:
            options.append("FULL")
        if analyze:
            options.append("ANALYZE")

        options_str = f"({', '.join(options)})" if options else ""
        table_str = f" {schema}.{table}" if table else ""

        self.execute(f"VACUUM{options_str}{table_str}", autocommit=True)

    def analyze(self, table: Optional[str] = None, schema: str = "public") -> None:
        """Update table statistics for query planner.

        Args:
            table: Table name (None for whole database).
            schema: Schema name.
        """
        table_str = f" {schema}.{table}" if table else ""
        self.execute(f"ANALYZE{table_str}", autocommit=True)

    def explain(self, sql: str, params: Optional[Sequence] = None, analyze: bool = False, format: str = "text") -> list[str]:
        """Get query execution plan.

        Args:
            sql: SQL query.
            params: Query parameters.
            analyze: Actually run the query for real stats.
            format: Output format (text, json, xml, yaml).

        Returns:
            Query plan lines.
        """
        options = [f"FORMAT {format.upper()}"]
        if analyze:
            options.append("ANALYZE")

        result = self.execute(f"EXPLAIN ({', '.join(options)}) {sql}", params)
        return [r["QUERY PLAN"] for r in result]

    # =========================================================================
    # ROLES & USERS
    # =========================================================================

    def create_role(
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
            db.create_role("appuser", password="secret123", login=True)

            # Create an admin user
            db.create_role("admin", password="secret", superuser=True)

            # Create a read-only group role
            db.create_role("readonly", login=False)

            # Create user in a group
            db.create_role("analyst", password="secret", in_roles=["readonly"])
        """
        validate_identifier(name)

        # Check if exists
        if if_not_exists and self.role_exists(name):
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
            with self.cursor(autocommit=True) as cur:
                cur.execute(f"CREATE ROLE {name} WITH {options_str}", [password])
        else:
            self.execute(f"CREATE ROLE {name} WITH {options_str}", autocommit=True)

        # Add to roles
        if in_roles:
            for role in in_roles:
                self.grant_role(role, name)

    def drop_role(self, name: str, if_exists: bool = True) -> None:
        """Drop a role.

        Args:
            name: Role name.
            if_exists: Don't error if role doesn't exist.

        Example:
            db.drop_role("olduser")
        """
        validate_identifier(name)
        if_clause = "IF EXISTS " if if_exists else ""
        self.execute(f"DROP ROLE {if_clause}{name}", autocommit=True)

    def role_exists(self, name: str) -> bool:
        """Check if a role exists.

        Args:
            name: Role name.

        Returns:
            True if role exists.
        """
        result = self.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [name])
        return len(result) > 0

    def list_roles(self, include_system: bool = False) -> list[dict]:
        """List all roles.

        Args:
            include_system: Include system roles (pg_*).

        Returns:
            List of role info dicts.
        """
        where_clause = "" if include_system else "WHERE rolname NOT LIKE 'pg_%'"
        return self.execute(f"""
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

    def alter_role(
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
            db.alter_role("appuser", password="newpassword")
            db.alter_role("appuser", connection_limit=10)
            db.alter_role("oldname", rename_to="newname")
        """
        validate_identifier(name)

        if rename_to:
            validate_identifier(rename_to)
            self.execute(f"ALTER ROLE {name} RENAME TO {rename_to}", autocommit=True)
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
            with self.cursor(autocommit=True) as cur:
                cur.execute(f"ALTER ROLE {name} WITH {options_str}", params if params else None)

    def grant_role(self, role: str, member: str, with_admin: bool = False) -> None:
        """Grant role membership to another role.

        Args:
            role: Role to grant.
            member: Role receiving membership.
            with_admin: Allow member to grant role to others.

        Example:
            db.grant_role("readonly", "analyst")
            db.grant_role("admin", "lead_dev", with_admin=True)
        """
        validate_identifiers(role, member)
        admin_clause = " WITH ADMIN OPTION" if with_admin else ""
        self.execute(f"GRANT {role} TO {member}{admin_clause}", autocommit=True)

    def revoke_role(self, role: str, member: str) -> None:
        """Revoke role membership from a role.

        Args:
            role: Role to revoke.
            member: Role losing membership.

        Example:
            db.revoke_role("admin", "former_admin")
        """
        validate_identifiers(role, member)
        self.execute(f"REVOKE {role} FROM {member}", autocommit=True)

    def grant(
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
            db.grant("SELECT", "users", "readonly")

            # Grant all on a table
            db.grant("ALL", "orders", "appuser")

            # Grant on all tables in schema
            db.grant("SELECT", "ALL TABLES", "readonly", schema="public")

            # Grant on schema
            db.grant("USAGE", "myschema", "appuser", object_type="SCHEMA")

            # Grant on database
            db.grant("CONNECT", "mydb", "appuser", object_type="DATABASE")
        """
        validate_identifier(to)

        if isinstance(privileges, list):
            privileges = ", ".join(privileges)

        grant_clause = " WITH GRANT OPTION" if with_grant_option else ""

        if object_type.upper() == "SCHEMA":
            validate_identifier(on)
            self.execute(f"GRANT {privileges} ON SCHEMA {on} TO {to}{grant_clause}", autocommit=True)
        elif object_type.upper() == "DATABASE":
            validate_identifier(on)
            self.execute(f"GRANT {privileges} ON DATABASE {on} TO {to}{grant_clause}", autocommit=True)
        elif on.upper() in ("ALL TABLES", "ALL SEQUENCES", "ALL FUNCTIONS"):
            validate_identifier(schema)
            self.execute(f"GRANT {privileges} ON {on} IN SCHEMA {schema} TO {to}{grant_clause}", autocommit=True)
        else:
            validate_identifiers(on, schema)
            self.execute(f"GRANT {privileges} ON {object_type} {schema}.{on} TO {to}{grant_clause}", autocommit=True)

    def revoke(
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
            db.revoke("INSERT", "users", "readonly")
            db.revoke("ALL", "orders", "former_user", cascade=True)
        """
        validate_identifier(from_role)

        if isinstance(privileges, list):
            privileges = ", ".join(privileges)

        cascade_clause = " CASCADE" if cascade else ""

        if object_type.upper() == "SCHEMA":
            validate_identifier(on)
            self.execute(f"REVOKE {privileges} ON SCHEMA {on} FROM {from_role}{cascade_clause}", autocommit=True)
        elif object_type.upper() == "DATABASE":
            validate_identifier(on)
            self.execute(f"REVOKE {privileges} ON DATABASE {on} FROM {from_role}{cascade_clause}", autocommit=True)
        elif on.upper() in ("ALL TABLES", "ALL SEQUENCES", "ALL FUNCTIONS"):
            validate_identifier(schema)
            self.execute(f"REVOKE {privileges} ON {on} IN SCHEMA {schema} FROM {from_role}{cascade_clause}", autocommit=True)
        else:
            validate_identifiers(on, schema)
            self.execute(f"REVOKE {privileges} ON {object_type} {schema}.{on} FROM {from_role}{cascade_clause}", autocommit=True)

    def list_role_members(self, role: str) -> list[str]:
        """List members of a role.

        Args:
            role: Role name.

        Returns:
            List of member role names.
        """
        result = self.execute("""
            SELECT m.rolname AS member
            FROM pg_auth_members am
            JOIN pg_roles r ON r.oid = am.roleid
            JOIN pg_roles m ON m.oid = am.member
            WHERE r.rolname = %s
            ORDER BY m.rolname
        """, [role])
        return [r["member"] for r in result]

    def list_role_grants(self, role: str) -> list[dict]:
        """List privileges granted to a role.

        Args:
            role: Role name.

        Returns:
            List of privilege info dicts.
        """
        return self.execute("""
            SELECT
                table_schema AS schema,
                table_name AS object_name,
                privilege_type AS privilege
            FROM information_schema.role_table_grants
            WHERE grantee = %s
            ORDER BY table_schema, table_name, privilege_type
        """, [role])

    # =========================================================================
    # BACKUP & RESTORE
    # =========================================================================

    def pg_dump(
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
            db.pg_dump("backup.dump")

            # SQL backup
            db.pg_dump("backup.sql", format="plain")

            # Schema only
            db.pg_dump("schema.sql", format="plain", schema_only=True)

            # Specific tables
            db.pg_dump("users.dump", tables=["users", "profiles"])

            # Parallel backup
            db.pg_dump("backup_dir", format="directory", jobs=4)
        """
        import subprocess

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
        env = {"PGPASSWORD": self.config.password} if self.config.password else {}
        result = subprocess.run(cmd, env={**subprocess.os.environ, **env}, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"pg_dump failed: {result.stderr}")

    def pg_restore(
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
            db.pg_restore("backup.dump")

            # Clean restore (drop and recreate)
            db.pg_restore("backup.dump", clean=True)

            # Restore specific tables
            db.pg_restore("backup.dump", tables=["users"])

            # Parallel restore
            db.pg_restore("backup_dir", jobs=4)
        """
        import subprocess

        input_file = Path(input_file)

        # Check if it's a plain SQL file
        if input_file.suffix == ".sql" or not input_file.exists():
            # Use psql for plain format
            self._psql_restore(input_file)
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
        env = {"PGPASSWORD": self.config.password} if self.config.password else {}
        result = subprocess.run(cmd, env={**subprocess.os.environ, **env}, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"pg_restore failed: {result.stderr}")

    def _psql_restore(self, sql_file: Path) -> None:
        """Restore from plain SQL file using psql."""
        import subprocess

        cmd = [
            "psql",
            "-h", self.config.host,
            "-p", str(self.config.port),
            "-U", self.config.user,
            "-d", self.config.database,
            "-f", str(sql_file),
        ]

        env = {"PGPASSWORD": self.config.password} if self.config.password else {}
        result = subprocess.run(cmd, env={**subprocess.os.environ, **env}, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(f"psql restore failed: {result.stderr}")

    def copy_to_csv(
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
            db.copy_to_csv("users", "users.csv")
            db.copy_to_csv("orders", "orders.csv", columns=["id", "total", "created_at"])
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

        with self.cursor() as cur:
            with open(output_file, "w", encoding=encoding) as f:
                with cur.copy(f"COPY {schema}.{table}{cols} TO STDOUT WITH ({', '.join(options)})") as copy:
                    for data in copy:
                        f.write(data.decode(encoding) if isinstance(data, bytes) else data)

            # Get row count
            cur.execute(f"SELECT COUNT(*) AS count FROM {schema}.{table}")
            return cur.fetchone()["count"]

    def copy_from_csv(
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
            db.copy_from_csv("users", "users.csv")
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

        with self.cursor() as cur:
            with open(input_file, "r", encoding=encoding) as f:
                with cur.copy(f"COPY {schema}.{table}{cols} FROM STDIN WITH ({', '.join(options)})") as copy:
                    while data := f.read(8192):
                        copy.write(data.encode(encoding))

            return cur.rowcount

    def close(self) -> None:
        """Close database connections."""
        if self._engine:
            self._engine.dispose()
            self._engine = None

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"Database({self.config.database!r} @ {self.config.host}:{self.config.port})"
