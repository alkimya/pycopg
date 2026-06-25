"""
Core Database class - the main entry point for pycopg.

Provides high-level operations for PostgreSQL/PostGIS/TimescaleDB.
"""

from __future__ import annotations

import logging
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

from pycopg.base import (
    DatabaseBase,
    QueryMixin,
)
from pycopg.config import Config
from pycopg.exceptions import DatabaseExists, ExtensionNotAvailable
from pycopg.utils import (
    validate_identifier,
    validate_identifiers,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    import geopandas as gpd
    import pandas as pd

    from pycopg.admin import AdminAccessor
    from pycopg.backup import BackupAccessor
    from pycopg.etl import ETLAccessor
    from pycopg.maint import MaintAccessor
    from pycopg.schema import SchemaAccessor
    from pycopg.spatial import SpatialAccessor
    from pycopg.timescale import TimescaleAccessor


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
        self._timescale: TimescaleAccessor | None = None
        self._admin: AdminAccessor | None = None
        self._maint: MaintAccessor | None = None
        self._backup: BackupAccessor | None = None
        self._schema: SchemaAccessor | None = None

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

    @property
    def timescale(self) -> TimescaleAccessor:
        """Get or create the TimescaleDB accessor (lazy initialization).

        Provides access to TimescaleDB operations such as hypertable
        management, compression, and retention policies.  The accessor
        is created on first access and cached for subsequent calls.

        Returns
        -------
        TimescaleAccessor
            TimescaleDB helper namespace bound to this database.
        """
        if self._timescale is None:
            from pycopg.timescale import TimescaleAccessor

            self._timescale = TimescaleAccessor(self)
        return self._timescale

    @property
    def admin(self) -> AdminAccessor:
        """Get or create the admin accessor (lazy initialization).

        Provides access to role and permission management operations.
        The accessor is created on first access and cached for subsequent
        calls.

        Returns
        -------
        AdminAccessor
            Admin helper namespace bound to this database.
        """
        if self._admin is None:
            from pycopg.admin import AdminAccessor

            self._admin = AdminAccessor(self)
        return self._admin

    @property
    def maint(self) -> MaintAccessor:
        """Get or create the maintenance accessor (lazy initialization).

        Provides access to size, vacuum, analyze, and explain operations.
        The accessor is created on first access and cached for subsequent
        calls.

        Returns
        -------
        MaintAccessor
            Maintenance helper namespace bound to this database.
        """
        if self._maint is None:
            from pycopg.maint import MaintAccessor

            self._maint = MaintAccessor(self)
        return self._maint

    @property
    def backup(self) -> BackupAccessor:
        """Get or create the backup accessor (lazy initialization).

        Provides access to pg_dump, pg_restore, and CSV copy operations.
        The accessor is created on first access and cached for subsequent
        calls.

        Returns
        -------
        BackupAccessor
            Backup helper namespace bound to this database.
        """
        if self._backup is None:
            from pycopg.backup import BackupAccessor

            self._backup = BackupAccessor(self)
        return self._backup

    @property
    def schema(self) -> SchemaAccessor:
        """Get or create the schema accessor (lazy initialization).

        Provides access to DDL and introspection operations such as
        database, extension, schema, table, column, constraint, and index
        management.  The accessor is created on first access and cached for
        subsequent calls.

        Returns
        -------
        SchemaAccessor
            Schema helper namespace bound to this database.
        """
        if self._schema is None:
            from pycopg.schema import SchemaAccessor

            self._schema = SchemaAccessor(self)
        return self._schema

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

    def upsert(
        self,
        table: str,
        row: dict,
        conflict_columns: list[str],
        update_columns: list[str] | None = None,
        schema: str = "public",
    ) -> dict | None:
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

        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def delete_where(
        self,
        table: str,
        where: dict,
        schema: str = "public",
    ) -> int:
        """Delete rows matching the given equality conditions.

        Parameters
        ----------
        table : str
            Table name.
        where : dict
            Equality conditions as column-name to value mapping. Must be
            non-empty — use db.schema.truncate_table to affect all rows.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        int
            Number of rows deleted.

        Raises
        ------
        ValueError
            If where is empty or None (destructive guard D-04).
        """
        if not where:
            raise ValueError(
                "delete_where requires a non-empty 'where' dict. "
                "To delete all rows use db.schema.truncate_table."
            )
        validate_identifiers(table, schema)
        fragment, where_params = self._build_where_dict(where)
        sql = f"DELETE FROM {schema}.{table} WHERE {fragment}"
        with self.cursor() as cur:
            cur.execute(sql, where_params)
            return cur.rowcount

    def update_where(
        self,
        table: str,
        values: dict,
        where: dict,
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
        where : dict
            Equality conditions as column-name to value mapping. Must be
            non-empty — use execute with an explicit UPDATE statement to
            affect all rows.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        int
            Number of rows updated.

        Raises
        ------
        ValueError
            If where or values is empty or None (destructive guard D-04).
        """
        if not values:
            raise ValueError("update_where requires a non-empty 'values' dict.")
        if not where:
            raise ValueError(
                "update_where requires a non-empty 'where' dict. "
                "To update all rows use execute with an explicit SQL statement."
            )
        validate_identifiers(table, schema)
        validate_identifiers(*values.keys())
        set_clause = ", ".join(f"{col} = %s" for col in values)
        fragment, where_params = self._build_where_dict(where)
        sql = f"UPDATE {schema}.{table} SET {set_clause} WHERE {fragment}"
        params = list(values.values()) + where_params
        with self.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount

    def exists(
        self,
        table: str,
        where: dict,
        schema: str = "public",
    ) -> bool:
        """Check whether any row matching the given equality conditions exists.

        Parameters
        ----------
        table : str
            Table name.
        where : dict
            Equality conditions as column-name to value mapping. Must be
            non-empty — an existence check with no predicate is meaningless.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        bool
            ``True`` if at least one matching row exists, ``False`` otherwise.

        Raises
        ------
        ValueError
            If ``where`` is empty or falsy (guard fires before any SQL or
            cursor is opened).
        InvalidIdentifier
            If any column name or the table/schema identifier is invalid.
        """
        if not where:
            raise ValueError(
                "exists requires a non-empty `where` dict — "
                "an existence check with no predicate is meaningless."
            )
        validate_identifiers(table, schema)
        fragment, params = self._build_where_dict(where)
        sql = f"SELECT EXISTS(SELECT 1 FROM {schema}.{table} WHERE {fragment})"
        return bool(self.fetch_val(sql, params))

    def count(
        self,
        table: str,
        where: dict | None = None,
        schema: str = "public",
    ) -> int:
        """Count rows in a table, optionally filtered by equality conditions.

        Parameters
        ----------
        table : str
            Table name.
        where : dict, optional
            Equality conditions as column-name to value mapping. When ``None``
            (default), all rows are counted without a WHERE clause.
        schema : str, optional
            Schema name, by default "public".

        Returns
        -------
        int
            Number of matching (or total) rows.

        Raises
        ------
        InvalidIdentifier
            If any column name or the table/schema identifier is invalid.
        """
        validate_identifiers(table, schema)
        if where:
            fragment, params = self._build_where_dict(where)
            sql = f"SELECT COUNT(*) FROM {schema}.{table} WHERE {fragment}"
        else:
            params = []
            sql = f"SELECT COUNT(*) FROM {schema}.{table}"
        return int(self.fetch_val(sql, params))

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

    def fetch_all(self, sql: str, params: Sequence | None = None) -> list[dict]:
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
        params : Sequence, optional
            Positional query parameters (bound as ``%s``).

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
        with self.cursor() as cur:
            cur.execute(sql, params)
            if cur.description:
                return cur.fetchall()
            return []

    def paginate(
        self,
        table: str,
        limit: int,
        offset: int = 0,
        order_by: str | list[str] | None = None,
        where: dict | None = None,
        descending: bool = False,
        schema: str = "public",
    ) -> list[dict]:
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
            Equality conditions as column-name to value mapping. ``None``
            (default) returns all rows without a WHERE clause.
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
        InvalidIdentifier
            If any column name in ``order_by`` or the table/schema identifier
            is invalid.
        """
        validate_identifiers(table, schema)

        params: list = []
        where_clause = ""
        if where:
            fragment, where_params = self._build_where_dict(where)
            where_clause = f" WHERE {fragment}"
            params.extend(where_params)

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
        with self.cursor() as cur:
            cur.execute(sql, params)
            if cur.description:
                return cur.fetchall()
            return []

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
            self.schema.add_primary_key(table, primary_key, schema)

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
        if not self.schema.has_extension("postgis"):
            raise ExtensionNotAvailable(
                "PostGIS extension not installed. Run db.schema.create_extension('postgis')"
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
            self.schema.add_primary_key(table, primary_key, schema)

        if spatial_index and if_exists != "append":
            self.spatial.create_spatial_index(table, geometry_column, schema)

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
