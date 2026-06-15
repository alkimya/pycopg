"""
Core Database class - the main entry point for pycopg.

Provides high-level operations for PostgreSQL/PostGIS/TimescaleDB.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

import psycopg
from psycopg import OperationalError
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
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

    from pycopg.etl import ETLAccessor
    from pycopg.spatial import SpatialAccessor


class Database(DatabaseBase, QueryMixin):
    """High-level PostgreSQL/PostGIS/TimescaleDB interface.

    Combines psycopg (for DDL/admin) and SQLAlchemy (for DataFrame operations)
    into a simple, unified API.

    Attributes
    ----------
    config : Config
        Database connection configuration.
    """

    def __init__(self, config: Config):
        """Initialize database connection.

        Parameters
        ----------
        config : Config
            Database configuration.
        """
        super().__init__(config)
        self._engine: Engine | None = None
        self._session_conn: psycopg.Connection | None = None
        self._spatial: SpatialAccessor | None = None
        self._etl: ETLAccessor | None = None

    @classmethod
    def create(
        cls,
        name: str,
        host: str = "localhost",
        port: int = 5432,
        user: str = "postgres",
        password: str = "",
        owner: str | None = None,
        template: str = "template1",
        if_not_exists: bool = True,
    ) -> Database:
        """Create a new database and return a connection to it.

        This is a convenience method that:
        1. Connects to the 'postgres' database
        2. Creates the new database
        3. Returns a Database instance connected to the new database

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
        Database
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
        with psycopg.connect(**admin_config.connect_params(), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,))
                exists = cur.fetchone() is not None

                if exists:
                    if not if_not_exists:
                        raise DatabaseExists(f"Database '{name}' already exists")
                else:
                    # Create the database
                    owner_clause = f" OWNER {owner}" if owner else ""
                    cur.execute(
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
    def create_from_env(
        cls,
        name: str,
        owner: str | None = None,
        template: str = "template1",
        if_not_exists: bool = True,
        dotenv_path: str | Path | None = None,
    ) -> Database:
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
        Database
            Instance connected to the newly created database.
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

    @property
    def spatial(self) -> SpatialAccessor:
        """Get or create the spatial helper accessor (lazy initialization).

        First access verifies PostGIS availability (the accessor guards
        at construction).

        Returns
        -------
        SpatialAccessor
            Spatial helper namespace bound to this database.

        Raises
        ------
        ExtensionNotAvailable
            If the PostGIS extension is not installed.
        """
        if self._spatial is None:
            from pycopg.spatial import SpatialAccessor

            self._spatial = SpatialAccessor(self)
        return self._spatial

    @property
    def etl(self) -> ETLAccessor:
        """Get or create the ETL run-tracking accessor (lazy initialization).

        The accessor hosts ``init()``, ``_start_run()``, ``_end_run()``,
        and ``run()`` — the run-log primitives for the v0.5.0 ETL layer.
        All run-log writes use a dedicated autocommit connection fully
        independent of any load transaction (D-01/D-02, ETL-07).

        Returns
        -------
        ETLAccessor
            ETL run-tracking namespace bound to this database.
        """
        if self._etl is None:
            from pycopg.etl import ETLAccessor

            self._etl = ETLAccessor(self)
        return self._etl

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

        Parameters
        ----------
        autocommit : bool, optional
            Enable autocommit mode (required for CREATE DATABASE, etc.), by default False.

        Yields
        ------
        psycopg.Connection
            psycopg Connection object.
        """
        conn = self._connect_with_retry(autocommit=autocommit)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def cursor(self, autocommit: bool = False) -> Iterator[psycopg.Cursor]:
        """Context manager for psycopg cursor with dict rows.

        Parameters
        ----------
        autocommit : bool, optional
            Enable autocommit mode, by default False.

        Yields
        ------
        psycopg.Cursor
            psycopg Cursor with dict_row factory.
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

        Yields
        ------
        psycopg.Connection
            Connection in a transaction.
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
    def session(self, autocommit: bool = False) -> Iterator[Database]:
        """Context manager for session mode with connection reuse.

        In session mode, all operations reuse the same connection,
        significantly reducing overhead for multiple sequential operations.

        Parameters
        ----------
        autocommit : bool, optional
            Enable autocommit mode for the session, by default False.

        Yields
        ------
        Database
            Self (Database instance with active session).
        """
        if self._session_conn is not None:
            raise RuntimeError(
                "Already in session mode. Nested sessions are not supported."
            )

        self._session_conn = psycopg.connect(
            **self.config.connect_params(), autocommit=autocommit
        )
        try:
            yield self
        finally:
            try:
                if not autocommit:
                    commit_exc = None
                    try:
                        self._session_conn.commit()
                    except Exception as e:
                        commit_exc = e
                        raise
                    finally:
                        # close() ALWAYS runs, even when commit() raises (B2 residual fix).
                        try:
                            self._session_conn.close()
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
                    self._session_conn.close()
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

    def execute(
        self, sql: str, params: Sequence | None = None, autocommit: bool = False
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
        with self.cursor(autocommit=autocommit) as cur:
            cur.execute(sql, params)
            if cur.description:
                return cur.fetchall()
            return []

    def execute_many(self, sql: str, params_seq: Sequence[Sequence]) -> int:
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
        with self.cursor() as cur:
            cur.executemany(sql, params_seq)
            return cur.rowcount

    def insert_many(
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
        sql, params = self._build_batch_insert_sql(
            table, columns, rows, schema, on_conflict
        )

        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount

    def upsert_many(
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

        return self.insert_many(table, rows, schema, on_conflict)

    def stream(
        self,
        sql: str,
        params: Sequence | None = None,
        batch_size: int = 1000,
    ) -> Iterator[dict]:
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
        with self.cursor() as cur:
            cur.execute(sql, params)
            while True:
                rows = cur.fetchmany(batch_size)
                if not rows:
                    break
                yield from rows

    def notify(self, channel: str, payload: str = "") -> None:
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
        self.execute("SELECT pg_notify(%s, %s)", [channel, payload], autocommit=True)

    def insert_batch(
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
        with self.cursor() as cur:
            # Process in batches
            for i in range(0, len(rows), batch_size):
                batch = rows[i : i + batch_size]

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

        with self.connect() as conn:
            with conn.cursor() as cur:
                with cur.copy(f"COPY {schema}.{table} ({cols_str}) FROM STDIN") as copy:
                    for row in rows:
                        copy.write_row([row.get(col) for col in columns])
            conn.commit()
            return len(rows)

    def fetch_one(self, sql: str, params: Sequence | None = None) -> dict | None:
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
        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def fetch_val(self, sql: str, params: Sequence | None = None) -> Any:
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
        row = self.fetch_one(sql, params)
        if row:
            return list(row.values())[0]
        return None

    # =========================================================================
    # DATABASE ADMINISTRATION
    # =========================================================================

    def create_database(
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
        with psycopg.connect(**admin_config.connect_params(), autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(f"CREATE DATABASE {name}{owner_clause} TEMPLATE {template}")

    def drop_database(self, name: str, if_exists: bool = True) -> None:
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
        with psycopg.connect(**admin_config.connect_params(), autocommit=True) as conn:
            with conn.cursor() as cur:
                # Terminate existing connections
                cur.execute(
                    """
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = %s
                    AND pid <> pg_backend_pid()
                """,
                    [name],
                )
                cur.execute(f"DROP DATABASE {if_clause}{name}")

    def database_exists(self, name: str) -> bool:
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
        with psycopg.connect(**admin_config.connect_params()) as conn:
            with conn.cursor() as cur:
                cur.execute(queries.DATABASE_EXISTS, [name])
                return cur.fetchone() is not None

    def list_databases(self) -> list[str]:
        """List all databases.

        Returns
        -------
        list of str
            List of database names.
        """
        result = self.execute(queries.LIST_DATABASES)
        return [r["datname"] for r in result]

    # =========================================================================
    # EXTENSIONS
    # =========================================================================

    def create_extension(
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
        self.execute(
            f'CREATE EXTENSION {if_clause}"{name}"{schema_clause}', autocommit=True
        )

    def drop_extension(
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
        self.execute(
            f'DROP EXTENSION {if_clause}"{name}"{cascade_clause}', autocommit=True
        )

    def list_extensions(self) -> list[dict]:
        """List installed extensions.

        Returns
        -------
        list of dict
            List of dicts with extname, extversion, nspname (schema).
        """
        return self.execute(queries.LIST_EXTENSIONS)

    def has_extension(self, name: str) -> bool:
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
        result = self.execute(queries.EXTENSION_EXISTS, [name])
        return len(result) > 0

    # =========================================================================
    # SCHEMAS
    # =========================================================================

    def create_schema(
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
        self.execute(f"CREATE SCHEMA {if_clause}{name}{owner_clause}")

    def drop_schema(
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
        self.execute(f"DROP SCHEMA {if_clause}{name}{cascade_clause}")

    def list_schemas(self) -> list[str]:
        """List all schemas.

        Returns
        -------
        list of str
            List of schema names.
        """
        result = self.execute(queries.LIST_SCHEMAS)
        return [r["schema_name"] for r in result]

    def schema_exists(self, name: str) -> bool:
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
        result = self.execute(queries.SCHEMA_EXISTS, [name])
        return len(result) > 0

    # =========================================================================
    # TABLES
    # =========================================================================

    def list_tables(self, schema: str = "public") -> list[str]:
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
        result = self.execute(queries.LIST_TABLES, [schema])
        return [r["table_name"] for r in result]

    def table_exists(self, name: str, schema: str = "public") -> bool:
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
        result = self.execute(queries.TABLE_EXISTS, [schema, name])
        return len(result) > 0

    def list_columns(self, table: str, schema: str = "public") -> list[str]:
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
        result = self.execute(queries.GET_COLUMNS, [schema, table])
        return [row["column_name"] for row in result]

    def columns_with_types(
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
        result = self.execute(queries.GET_COLUMNS, [schema, table])
        return [(row["column_name"], row["data_type"]) for row in result]

    def drop_table(
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
        self.execute(f"DROP TABLE {if_clause}{schema}.{name}{cascade_clause}")

    def truncate_table(
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
        self.execute(f"TRUNCATE TABLE {schema}.{name}{cascade_clause}")

    def table_info(self, name: str, schema: str = "public") -> list[dict]:
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
        return self.execute(queries.TABLE_INFO, [schema, name])

    def row_count(self, name: str, schema: str = "public") -> int:
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
        result = self.execute(queries.ROW_COUNT, [schema, name])
        return result[0]["count"] if result else 0

    # =========================================================================
    # CONSTRAINTS & INDEXES
    # =========================================================================

    def add_primary_key(
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
        self.execute(
            f"ALTER TABLE {schema}.{table} ADD CONSTRAINT {constraint_name} PRIMARY KEY ({cols_str})"
        )

    def add_foreign_key(
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

        self.execute(f"""
            ALTER TABLE {schema}.{table}
            ADD CONSTRAINT {constraint_name}
            FOREIGN KEY ({cols_str})
            REFERENCES {ref_schema}.{ref_table} ({ref_cols_str})
            ON DELETE {on_delete}
            ON UPDATE {on_update}
        """)

    def add_unique_constraint(
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
        self.execute(
            f"ALTER TABLE {schema}.{table} ADD CONSTRAINT {constraint_name} UNIQUE ({cols_str})"
        )

    def create_index(
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

        self.execute(f"""
            CREATE {unique_clause}INDEX {if_clause}{index_name}
            ON {schema}.{table} USING {method} ({cols_str})
        """)

    def drop_index(
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
        self.execute(f"DROP INDEX {if_clause}{schema}.{name}")

    def list_indexes(self, table: str, schema: str = "public") -> list[dict]:
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
        return self.execute(queries.LIST_INDEXES, [schema, table])

    def list_constraints(self, table: str, schema: str = "public") -> list[dict]:
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
        return self.execute(queries.LIST_CONSTRAINTS, [schema, table])

    # =========================================================================
    # DATAFRAME OPERATIONS
    # =========================================================================

    def from_dataframe(
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

        if table and sql:
            raise ValueError("Specify either table or sql, not both")
        if not table and not sql:
            raise ValueError("Specify either table or sql")

        if table:
            validate_identifiers(table, schema)
            sql = f"SELECT * FROM {schema}.{table}"

        return pd.read_sql(text(sql), self.engine, params=params)

    def from_geodataframe(
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
        if not self.has_extension("postgis"):
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

        if table and sql:
            raise ValueError("Specify either table or sql, not both")
        if not table and not sql:
            raise ValueError("Specify either table or sql")

        if table:
            validate_identifiers(table, schema)
            sql = f"SELECT * FROM {schema}.{table}"

        return gpd.read_postgis(
            text(sql), self.engine, geom_col=geometry_column, params=params
        )

    # =========================================================================
    # POSTGIS SPATIAL OPERATIONS
    # =========================================================================

    def create_spatial_index(
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
        self.execute(f"""
            CREATE INDEX IF NOT EXISTS {index_name}
            ON {schema}.{table} USING GIST ({column})
        """)

    def list_geometry_columns(self, schema: str | None = None) -> list[dict]:
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
        return self.execute(
            queries.LIST_GEOMETRY_COLUMNS.format(where_clause=where_clause),
            params,
        )

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
        if not self.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. Run db.create_extension('timescaledb')"
            )

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
        if not self.has_extension("timescaledb"):
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

        self.execute(f"ALTER TABLE {schema}.{table} SET ({', '.join(settings)})")

    def add_compression_policy(
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
        if not self.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
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
        if not self.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
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

        Returns
        -------
        list of dict
            List of hypertable info dicts.

        Raises
        ------
        ExtensionNotAvailable
            If TimescaleDB extension is not installed.
        """
        if not self.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.create_extension('timescaledb')"
            )

        return self.execute(queries.LIST_HYPERTABLES)

    def hypertable_info(self, table: str, schema: str = "public") -> dict:
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
        if not self.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.create_extension('timescaledb')"
            )

        result = self.execute(
            # %%I in queries.HYPERTABLE_INFO is escaped so psycopg passes a
            # literal %I through to PostgreSQL's format() function.
            queries.HYPERTABLE_INFO,
            [schema, table, schema, table],
        )
        return result[0] if result else {}

    # =========================================================================
    # SIZE & STATS
    # =========================================================================

    def size(self, pretty: bool = True) -> str | int:
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
            result = self.execute(
                queries.DATABASE_SIZE_PRETTY,
                [self.config.database],
            )
            return result[0]["size"]
        else:
            result = self.execute(queries.DATABASE_SIZE, [self.config.database])
            return result[0]["size"]

    def table_size(
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
            result = self.execute(queries.TABLE_SIZE_PRETTY, [full_name])
            return result[0]["size"]
        else:
            result = self.execute(queries.TABLE_SIZE, [full_name])
            return result[0]["size"]

    def table_sizes(self, schema: str = "public", limit: int = 20) -> list[dict]:
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
        return self.execute(queries.TABLE_SIZES, [schema, limit])

    # =========================================================================
    # UTILITY
    # =========================================================================

    def vacuum(
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

        self.execute(f"VACUUM{options_str}{table_str}", autocommit=True)

    def analyze(self, table: str | None = None, schema: str = "public") -> None:
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
        self.execute(f"ANALYZE{table_str}", autocommit=True)

    def explain(
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

        result = self.execute(f"EXPLAIN ({', '.join(options)}) {sql}", params)
        return [r["QUERY PLAN"] for r in result]

    # =========================================================================
    # ROLES & USERS
    # =========================================================================

    def create_role(
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
        if if_not_exists and self.role_exists(name):
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

        Parameters
        ----------
        name : str
            Role name.
        if_exists : bool, optional
            Don't error if role doesn't exist, by default True.
        """
        validate_identifier(name)
        if_clause = "IF EXISTS " if if_exists else ""
        self.execute(f"DROP ROLE {if_clause}{name}", autocommit=True)

    def role_exists(self, name: str) -> bool:
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
        result = self.execute(queries.ROLE_EXISTS, [name])
        return len(result) > 0

    def list_roles(self, include_system: bool = False) -> list[dict]:
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
        return self.execute(queries.LIST_ROLES.format(where_clause=where_clause))

    def alter_role(
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
            validate_timestamp(valid_until)
            options.append(f"VALID UNTIL '{valid_until}'")

        if options:
            options_str = " ".join(options)
            with self.cursor(autocommit=True) as cur:
                cur.execute(
                    f"ALTER ROLE {name} WITH {options_str}", params if params else None
                )

    def grant_role(self, role: str, member: str, with_admin: bool = False) -> None:
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
        self.execute(f"GRANT {role} TO {member}{admin_clause}", autocommit=True)

    def revoke_role(self, role: str, member: str) -> None:
        """Revoke role membership from a role.

        Parameters
        ----------
        role : str
            Role to revoke.
        member : str
            Role losing membership.
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
            self.execute(
                f"GRANT {privileges} ON SCHEMA {on} TO {to}{grant_clause}",
                autocommit=True,
            )
        elif object_type.upper() == "DATABASE":
            validate_identifier(on)
            self.execute(
                f"GRANT {privileges} ON DATABASE {on} TO {to}{grant_clause}",
                autocommit=True,
            )
        elif on.upper() in ("ALL TABLES", "ALL SEQUENCES", "ALL FUNCTIONS"):
            validate_identifier(schema)
            self.execute(
                f"GRANT {privileges} ON {on} IN SCHEMA {schema} TO {to}{grant_clause}",
                autocommit=True,
            )
        else:
            validate_identifiers(on, schema)
            self.execute(
                f"GRANT {privileges} ON {object_type} {schema}.{on} TO {to}{grant_clause}",
                autocommit=True,
            )

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
            self.execute(
                f"REVOKE {privileges} ON SCHEMA {on} FROM {from_role}{cascade_clause}",
                autocommit=True,
            )
        elif object_type.upper() == "DATABASE":
            validate_identifier(on)
            self.execute(
                f"REVOKE {privileges} ON DATABASE {on} FROM {from_role}{cascade_clause}",
                autocommit=True,
            )
        elif on.upper() in ("ALL TABLES", "ALL SEQUENCES", "ALL FUNCTIONS"):
            validate_identifier(schema)
            self.execute(
                f"REVOKE {privileges} ON {on} IN SCHEMA {schema} FROM {from_role}{cascade_clause}",
                autocommit=True,
            )
        else:
            validate_identifiers(on, schema)
            self.execute(
                f"REVOKE {privileges} ON {object_type} {schema}.{on} FROM {from_role}{cascade_clause}",
                autocommit=True,
            )

    def list_role_members(self, role: str) -> list[str]:
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
        result = self.execute(queries.LIST_ROLE_MEMBERS, [role])
        return [r["member"] for r in result]

    def list_role_grants(self, role: str) -> list[dict]:
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
        return self.execute(queries.LIST_ROLE_GRANTS, [role])

    # =========================================================================
    # BACKUP & RESTORE
    # =========================================================================

    def pg_dump(
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
        import subprocess

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
        env = {"PGPASSWORD": self.config.password} if self.config.password else {}
        result = subprocess.run(
            cmd, env={**os.environ, **env}, capture_output=True, text=True
        )

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
        import subprocess

        input_file = Path(input_file)

        # Check if it's a plain SQL file
        if input_file.suffix == ".sql" or not input_file.exists():
            # Use psql for plain format
            self._psql_restore(input_file)
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
        env = {"PGPASSWORD": self.config.password} if self.config.password else {}
        result = subprocess.run(
            cmd, env={**os.environ, **env}, capture_output=True, text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"pg_restore failed: {result.stderr}")

    def _psql_restore(self, sql_file: Path) -> None:
        """Restore from plain SQL file using psql."""
        import subprocess

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

        env = {"PGPASSWORD": self.config.password} if self.config.password else {}
        result = subprocess.run(
            cmd, env={**os.environ, **env}, capture_output=True, text=True
        )

        if result.returncode != 0:
            raise RuntimeError(f"psql restore failed: {result.stderr}")

    def copy_to_csv(
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

        with self.cursor() as cur:
            with open(output_file, "w", encoding=encoding) as f:
                with cur.copy(
                    f"COPY {schema}.{table}{cols} TO STDOUT WITH ({', '.join(options)})"
                ) as copy:
                    for data in copy:
                        # psycopg yields memoryview chunks; bytes(...) handles
                        # both memoryview and bytes before decoding to text.
                        if isinstance(data, str):
                            f.write(data)
                        else:
                            f.write(bytes(data).decode(encoding))

            # Get row count
            cur.execute(f"SELECT COUNT(*) AS count FROM {schema}.{table}")
            return cur.fetchone()["count"]

    def copy_from_csv(
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

        with self.cursor() as cur:
            with open(input_file, encoding=encoding) as f:
                with cur.copy(
                    f"COPY {schema}.{table}{cols} FROM STDIN WITH ({', '.join(options)})"
                ) as copy:
                    while data := f.read(8192):
                        copy.write(data.encode(encoding))

            return cur.rowcount

    def close(self) -> None:
        """Close database connections."""
        if self._engine:
            self._engine.dispose()
            self._engine = None

    def __enter__(self) -> Database:
        """Enter the context manager, returning self."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit the context manager and close the connection."""
        self.close()
