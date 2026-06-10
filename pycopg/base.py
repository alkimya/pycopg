"""
Base classes and shared logic for pycopg.

Contains abstract base classes and mixins used by Database and AsyncDatabase.
"""

from __future__ import annotations

from abc import ABC
from pathlib import Path
from typing import Any

from pycopg.config import Config
from pycopg.utils import validate_identifiers, validate_timestamp


class DatabaseBase(ABC):
    """Abstract base class for Database and AsyncDatabase.

    Provides shared configuration, factory methods, and SQL query constants.
    Subclasses must implement the actual execution methods.
    """

    def __init__(self, config: Config):
        """Initialize database with configuration.

        Args:
            config: Database configuration.
        """
        self.config = config

    @classmethod
    def from_env(cls, dotenv_path: str | Path | None = None) -> DatabaseBase:
        """Create database from environment variables.

        Args:
            dotenv_path: Optional path to .env file.

        Returns:
            Database instance.
        """
        return cls(Config.from_env(dotenv_path))

    @classmethod
    def from_url(cls, url: str) -> DatabaseBase:
        """Create database from connection URL.

        Args:
            url: PostgreSQL connection URL.

        Returns:
            Database instance.
        """
        return cls(Config.from_url(url))

    def __repr__(self) -> str:
        """Return string representation of the database instance."""
        class_name = self.__class__.__name__
        return f"{class_name}({self.config.database!r} @ {self.config.host}:{self.config.port})"


class QueryMixin:
    """Mixin providing common query building utilities.

    Used by both sync and async database classes for consistent
    SQL generation and validation.
    """

    @staticmethod
    def _build_insert_sql(
        table: str,
        columns: list[str],
        schema: str = "public",
        on_conflict: str | None = None,
    ) -> tuple[str, str]:
        """Build INSERT SQL template.

        Args:
            table: Table name.
            columns: Column names.
            schema: Schema name.
            on_conflict: Optional ON CONFLICT clause.

        Returns:
            Tuple of (sql_template, columns_str).
        """
        validate_identifiers(table, schema, *columns)

        cols_str = ", ".join(columns)
        placeholders = ", ".join(["%s"] * len(columns))
        conflict_clause = f" ON CONFLICT {on_conflict}" if on_conflict else ""

        sql = f"INSERT INTO {schema}.{table} ({cols_str}) VALUES ({placeholders}){conflict_clause}"
        return sql, cols_str

    @staticmethod
    def _build_batch_insert_sql(
        table: str,
        columns: list[str],
        rows: list[dict],
        schema: str = "public",
        on_conflict: str | None = None,
    ) -> tuple[str, list]:
        """Build batch INSERT SQL with multiple VALUES.

        Args:
            table: Table name.
            columns: Column names.
            rows: List of row dicts.
            schema: Schema name.
            on_conflict: Optional ON CONFLICT clause.

        Returns:
            Tuple of (sql, params).
        """
        validate_identifiers(table, schema, *columns)

        cols_str = ", ".join(columns)
        conflict_clause = f" ON CONFLICT {on_conflict}" if on_conflict else ""

        placeholders = []
        params = []
        for row in rows:
            row_placeholders = ", ".join(["%s"] * len(columns))
            placeholders.append(f"({row_placeholders})")
            params.extend(row.get(col) for col in columns)

        values_str = ", ".join(placeholders)
        sql = f"INSERT INTO {schema}.{table} ({cols_str}) VALUES {values_str}{conflict_clause}"

        return sql, params

    @staticmethod
    def _build_select_sql(
        table: str,
        columns: list[str] | None = None,
        schema: str = "public",
        where: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> str:
        """Build SELECT SQL.

        Args:
            table: Table name.
            columns: Column names (None = *).
            schema: Schema name.
            where: Optional WHERE clause (without WHERE keyword).
            order_by: Optional ORDER BY clause.
            limit: Optional LIMIT.
            offset: Optional OFFSET.

        Returns:
            SQL string.
        """
        validate_identifiers(table, schema)
        if columns:
            validate_identifiers(*columns)

        cols_str = ", ".join(columns) if columns else "*"
        sql = f"SELECT {cols_str} FROM {schema}.{table}"

        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        if offset is not None:
            sql += f" OFFSET {int(offset)}"

        return sql


class SessionMixin:
    """Mixin providing session/connection reuse capabilities.

    Allows keeping a connection open for multiple operations,
    reducing connection overhead for batch operations.
    """

    _session_connection: Any = None
    _in_session: bool = False

    def _get_session_connection(self):
        """Get the current session connection if in session mode."""
        if self._in_session and self._session_connection is not None:
            return self._session_connection
        return None

    def _is_in_session(self) -> bool:
        """Check if currently in session mode."""
        return self._in_session


def build_pg_dump_cmd(
    host: str,
    port: int,
    user: str,
    database: str,
    output_file,
    format: str = "custom",
    schema_only: bool = False,
    data_only: bool = False,
    tables: list | None = None,
    exclude_tables: list | None = None,
    schemas: list | None = None,
    compress: int = 6,
    jobs: int = 1,
) -> list:
    """Build a pg_dump command argv list.

    Constructs the argument list for invoking pg_dump. Pure function: no
    I/O, no environment access, no secrets. The caller runs the command
    and manages credentials via environment variables.

    Args:
        host: Database host.
        port: Database port.
        user: Database user.
        database: Database name.
        output_file: Output file path (str or Path).
        format: Dump format — 'plain', 'custom', 'directory', or 'tar'.
        schema_only: Dump only schema, no data.
        data_only: Dump only data, no schema.
        tables: Only dump these tables.
        exclude_tables: Exclude these tables.
        schemas: Only dump these schemas.
        compress: Compression level (0-9, for custom format).
        jobs: Parallel jobs (for directory format).

    Returns:
        List of strings (argv) suitable for passing to a process runner.
    """
    output_file = Path(output_file)
    cmd = ["pg_dump"]

    # Connection params
    cmd.extend(["-h", host])
    cmd.extend(["-p", str(port)])
    cmd.extend(["-U", user])
    cmd.extend(["-d", database])

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

    return cmd


def build_pg_restore_cmd(
    host: str,
    port: int,
    user: str,
    database: str,
    input_file,
    clean: bool = False,
    if_exists: bool = True,
    create: bool = False,
    data_only: bool = False,
    schema_only: bool = False,
    tables: list | None = None,
    schemas: list | None = None,
    jobs: int = 1,
    no_owner: bool = False,
    no_privileges: bool = False,
) -> list:
    """Build a pg_restore command argv list.

    Constructs the argument list for invoking pg_restore. Pure function: no
    I/O, no environment access, no secrets. The caller runs the command
    and manages credentials via environment variables.

    The .sql / non-existent file early-return branch (which delegates to
    _psql_restore) is the caller's responsibility; this builder assumes a
    binary-format input file.

    Args:
        host: Database host.
        port: Database port.
        user: Database user.
        database: Database name.
        input_file: Backup file path (str or Path).
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

    Returns:
        List of strings (argv) suitable for passing to a process runner.
    """
    cmd = ["pg_restore"]

    # Connection params
    cmd.extend(["-h", host])
    cmd.extend(["-p", str(port)])
    cmd.extend(["-U", user])
    cmd.extend(["-d", database])

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

    cmd.append(str(Path(input_file)))

    return cmd


def build_role_options(
    login: bool = True,
    superuser: bool = False,
    createdb: bool = False,
    createrole: bool = False,
    inherit: bool = True,
    replication: bool = False,
    connection_limit: int = -1,
    password=None,
    valid_until: str | None = None,
) -> list:
    """Build the options list for a CREATE ROLE statement.

    Constructs the SQL option tokens for CREATE ROLE … WITH <options>.
    The password VALUE is never stored in or returned from this builder
    (D-04); when password is truthy the literal placeholder "PASSWORD %s"
    is appended so the caller can bind the actual secret via a parameterized
    execute call.

    Args:
        login: Can log in (True = user, False = group role).
        superuser: Is superuser.
        createdb: Can create databases.
        createrole: Can create other roles.
        inherit: Inherits privileges from member roles.
        replication: Can initiate streaming replication.
        connection_limit: Max concurrent connections (-1 = unlimited).
        password: Truthiness flag only — when truthy, appends "PASSWORD %s"
            placeholder. The actual secret must be bound by the caller.
        valid_until: Password expiration (e.g. '2025-12-31'). Validated
            against the timestamp whitelist before use.

    Returns:
        List of SQL option token strings.
    """
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
        # Append placeholder only; caller binds the actual secret value
        options.append("PASSWORD %s")
    if valid_until:
        validate_timestamp(valid_until)
        options.append(f"VALID UNTIL '{valid_until}'")

    return options
