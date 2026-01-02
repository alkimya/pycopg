"""
Base classes and shared logic for pycopg.

Contains abstract base classes and mixins used by Database and AsyncDatabase.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional, Sequence, Union

from pycopg.config import Config
from pycopg.utils import validate_identifier, validate_identifiers
from pycopg import queries


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
    def from_env(cls, dotenv_path: Optional[Union[str, Path]] = None) -> "DatabaseBase":
        """Create database from environment variables.

        Args:
            dotenv_path: Optional path to .env file.

        Returns:
            Database instance.
        """
        return cls(Config.from_env(dotenv_path))

    @classmethod
    def from_url(cls, url: str) -> "DatabaseBase":
        """Create database from connection URL.

        Args:
            url: PostgreSQL connection URL.

        Returns:
            Database instance.
        """
        return cls(Config.from_url(url))

    def __repr__(self) -> str:
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
        on_conflict: Optional[str] = None,
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
        on_conflict: Optional[str] = None,
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
        columns: Optional[list[str]] = None,
        schema: str = "public",
        where: Optional[str] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
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
