"""Maintenance & size accessor classes for db.maint.* / async_db.maint.*.

This module provides :class:`MaintAccessor` and
:class:`AsyncMaintAccessor` — the real implementation of the 6
maintenance and size helper methods, moved verbatim from ``Database`` /
``AsyncDatabase`` as part of the v0.6.0 accessor reorganisation (D-06).

Both classes are exposed on the parent database via a lazy-cached
``maint`` property.  The flat ``db.*`` maintenance names were removed in
v0.7.0.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pycopg import queries
from pycopg.utils import validate_identifiers

if TYPE_CHECKING:
    from pycopg.async_database import AsyncDatabase
    from pycopg.database import Database


class MaintAccessor:
    """Maintenance helper namespace exposed as ``db.maint``.

    Methods are moved verbatim from ``Database``.  Size queries and
    maintenance operations (VACUUM, ANALYZE, EXPLAIN) are accessible
    via this accessor.
    """

    def __init__(self, db: Database) -> None:
        """Store the parent database reference.

        Parameters
        ----------
        db : Database
            Parent database instance.  Stored as ``self._db``; no
            connection check is performed at construction time.
        """
        self._db = db

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
            result = self._db.execute(
                queries.DATABASE_SIZE_PRETTY,
                [self._db.config.database],
            )
            return result[0]["size"]
        else:
            result = self._db.execute(queries.DATABASE_SIZE, [self._db.config.database])
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
            result = self._db.execute(queries.TABLE_SIZE_PRETTY, [full_name])
            return result[0]["size"]
        else:
            result = self._db.execute(queries.TABLE_SIZE, [full_name])
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
        return self._db.execute(queries.TABLE_SIZES, [schema, limit])

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

        self._db.execute(f"VACUUM{options_str}{table_str}", autocommit=True)

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
        self._db.execute(f"ANALYZE{table_str}", autocommit=True)

    def explain(
        self,
        sql: str,
        params=None,
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

        result = self._db.execute(f"EXPLAIN ({', '.join(options)}) {sql}", params)
        return [r["QUERY PLAN"] for r in result]


class AsyncMaintAccessor:
    """Async maintenance helper namespace exposed as ``async_db.maint``.

    Mirrors :class:`MaintAccessor` exactly with ``await`` calls.
    """

    def __init__(self, db: AsyncDatabase) -> None:
        """Store the parent async database reference.

        Parameters
        ----------
        db : AsyncDatabase
            Parent async database instance.  Stored as ``self._db``; no
            connection check is performed at construction time.
        """
        self._db = db

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
            result = await self._db.execute(
                queries.DATABASE_SIZE_PRETTY,
                [self._db.config.database],
            )
            return result[0]["size"]
        else:
            result = await self._db.execute(
                queries.DATABASE_SIZE, [self._db.config.database]
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
            result = await self._db.execute(queries.TABLE_SIZE_PRETTY, [full_name])
            return result[0]["size"]
        else:
            result = await self._db.execute(queries.TABLE_SIZE, [full_name])
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
        return await self._db.execute(queries.TABLE_SIZES, [schema, limit])

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

        await self._db.execute(f"VACUUM{options_str}{table_str}", autocommit=True)

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
        await self._db.execute(f"ANALYZE{table_str}", autocommit=True)

    async def explain(
        self,
        sql: str,
        params=None,
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

        result = await self._db.execute(f"EXPLAIN ({', '.join(options)}) {sql}", params)
        return [r["QUERY PLAN"] for r in result]
