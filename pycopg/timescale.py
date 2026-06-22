"""TimescaleDB accessor classes for db.timescale.* / async_db.timescale.*.

This module provides :class:`TimescaleAccessor` and
:class:`AsyncTimescaleAccessor` — the real implementation of the 6
TimescaleDB helper methods, moved verbatim from ``Database`` /
``AsyncDatabase`` as part of the v0.6.0 accessor reorganisation (D-06).

Both classes are exposed on the parent database via a lazy-cached
``timescale`` property added in plan 02.  The flat ``db.*`` names remain
as thin deprecated aliases (see :mod:`pycopg.aliases`) until v0.7.0.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from pycopg import queries
from pycopg.exceptions import ExtensionNotAvailable
from pycopg.utils import validate_identifier, validate_identifiers, validate_interval

if TYPE_CHECKING:
    from pycopg.async_database import AsyncDatabase
    from pycopg.database import Database


def _build_chunk_bound_fragments(
    older_than: str | datetime | None,
    newer_than: str | datetime | None,
) -> tuple[str, str, list]:
    """Build SQL bound fragments and params list for show_chunks / drop_chunks.

    Parameters
    ----------
    older_than : str or datetime or None
        Chunks older than this bound.  A ``str`` is treated as a
        PostgreSQL interval literal; a :class:`datetime` as an absolute
        timestamptz cutoff; ``None`` omits the argument.
    newer_than : str or datetime or None
        Chunks newer than this bound.  Same type rules as ``older_than``.

    Returns
    -------
    older_frag : str
        SQL fragment for the ``older_than`` argument (empty string if None).
    newer_frag : str
        SQL fragment for the ``newer_than`` argument (empty string if None).
    params : list
        Bound parameter values, in older-then-newer order (D-02 footgun guard).
    """
    params: list = []
    if older_than is None:
        older_frag = ""
    elif isinstance(older_than, str):
        older_frag = ", older_than => %s::interval"
        params.append(older_than)
    else:
        older_frag = ", older_than => %s"
        params.append(older_than)

    if newer_than is None:
        newer_frag = ""
    elif isinstance(newer_than, str):
        newer_frag = ", newer_than => %s::interval"
        params.append(newer_than)
    else:
        newer_frag = ", newer_than => %s"
        params.append(newer_than)

    return older_frag, newer_frag, params


class TimescaleAccessor:
    """TimescaleDB helper namespace exposed as ``db.timescale``.

    Methods are moved verbatim from ``Database``.  The extension guard
    (``has_extension("timescaledb")``) is checked inside each method,
    not at construction, consistent with the ETL accessor pattern.
    """

    def __init__(self, db: Database) -> None:
        """Store the parent database reference.

        Parameters
        ----------
        db : Database
            Parent database instance.  Stored as ``self._db``; no
            extension check is performed at construction time.
        """
        self._db = db

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
        if not self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. Run db.schema.create_extension('timescaledb')"
            )

        validate_identifiers(table, schema, time_column)
        validate_interval(chunk_time_interval)

        self._db.execute(f"""
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
        if not self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
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

        self._db.execute(f"ALTER TABLE {schema}.{table} SET ({', '.join(settings)})")

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
        if not self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        self._db.execute(f"""
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
        if not self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        self._db.execute(f"""
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
        if not self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        return self._db.execute(queries.LIST_HYPERTABLES)

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
        if not self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        result = self._db.execute(
            # %%I in queries.HYPERTABLE_INFO is escaped so psycopg passes a
            # literal %I through to PostgreSQL's format() function.
            queries.HYPERTABLE_INFO,
            [schema, table, schema, table],
        )
        return result[0] if result else {}

    def show_chunks(
        self,
        table: str,
        older_than: str | datetime | None = None,
        newer_than: str | datetime | None = None,
        schema: str = "public",
    ) -> list[str]:
        """List chunks for a hypertable, sorted oldest-first by range start.

        Parameters
        ----------
        table : str
            Hypertable name.
        older_than : str or datetime or None, optional
            Return only chunks whose time range ends before this bound.
            A ``str`` is treated as a PostgreSQL interval literal (e.g.
            ``"30 days"``); a :class:`datetime` as an absolute timestamptz
            cutoff.  ``None`` (default) imposes no upper-age filter.
        newer_than : str or datetime or None, optional
            Return only chunks whose time range starts after this bound.
            Same type rules as ``older_than``.  ``None`` (default) imposes
            no lower-age filter.
        schema : str, optional
            Schema name, by default ``"public"``.

        Returns
        -------
        list of str
            Fully-qualified chunk names (e.g.
            ``_timescaledb_internal._hyper_1_2_chunk``), sorted
            oldest-first by ``range_start``.  Never sorted lexicographically
            — use the DB-supplied order so ``_hyper_N_10`` sorts after
            ``_hyper_N_9``.

        Raises
        ------
        ExtensionNotAvailable
            If TimescaleDB extension is not installed.
        """
        if not self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        validate_identifiers(table, schema)

        older_frag, newer_frag, params = _build_chunk_bound_fragments(
            older_than, newer_than
        )
        sql = queries.TSDB_SHOW_CHUNKS.format(
            schema=schema,
            table=table,
            older_arg=older_frag,
            newer_arg=newer_frag,
        )
        rows = self._db.execute(sql, params)
        return [r["chunk_name"] for r in rows]

    def drop_chunks(
        self,
        table: str,
        older_than: str | datetime | None = None,
        newer_than: str | datetime | None = None,
        schema: str = "public",
        dry_run: bool = False,
    ) -> list[str]:
        """Drop chunks from a hypertable matching the given bounds.

        Uses a capture-before-drop pattern: the matching chunk list is
        retrieved first (while chunks still exist), then the drop is issued.
        The returned list is always in oldest-first order, identical in shape
        to :meth:`show_chunks`.

        Parameters
        ----------
        table : str
            Hypertable name.
        older_than : str or datetime or None, optional
            Drop only chunks whose time range ends before this bound.
            A ``str`` is treated as a PostgreSQL interval literal (e.g.
            ``"30 days"``); a :class:`datetime` as an absolute timestamptz
            cutoff.
        newer_than : str or datetime or None, optional
            Drop only chunks whose time range starts after this bound.
            Same type rules as ``older_than``.
        schema : str, optional
            Schema name, by default ``"public"``.
        dry_run : bool, optional
            If ``True``, return the would-be-dropped chunk list without
            actually dropping anything.  By default ``False``.

        Returns
        -------
        list of str
            Fully-qualified chunk names that were (or would be) dropped,
            sorted oldest-first by ``range_start``.

        Raises
        ------
        ValueError
            If both ``older_than`` and ``newer_than`` are ``None`` — this
            guard fires *before* any DB round-trip to prevent an accidental
            full-table wipe.
        ExtensionNotAvailable
            If TimescaleDB extension is not installed.

        Notes
        -----
        **DESTRUCTIVE / IRREVERSIBLE.**  Dropped chunks cannot be recovered
        unless you have a backup.  Always call with ``dry_run=True`` first to
        inspect which chunks will be removed.
        """
        if older_than is None and newer_than is None:
            raise ValueError(
                "drop_chunks requires at least one of older_than or newer_than. "
                "Passing both as None would drop ALL chunks — use show_chunks() "
                "to inspect first, or pass an explicit bound."
            )

        if not self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        validate_identifiers(table, schema)

        older_frag, newer_frag, params = _build_chunk_bound_fragments(
            older_than, newer_than
        )

        # Capture the ordered preview list BEFORE dropping (rows vanish post-drop;
        # drop_chunks() SRF returns text not regclass so the JOIN would fail).
        capture_sql = queries.TSDB_SHOW_CHUNKS.format(
            schema=schema,
            table=table,
            older_arg=older_frag,
            newer_arg=newer_frag,
        )
        captured = self._db.execute(capture_sql, params)
        chunk_list = [r["chunk_name"] for r in captured]

        if dry_run:
            return chunk_list

        drop_sql = queries.TSDB_DROP_CHUNKS.format(
            schema=schema,
            table=table,
            older_arg=older_frag,
            newer_arg=newer_frag,
        )
        self._db.execute(drop_sql, params)
        return chunk_list


class AsyncTimescaleAccessor:
    """Async TimescaleDB helper namespace exposed as ``async_db.timescale``.

    Mirrors :class:`TimescaleAccessor` exactly with ``await`` calls.
    """

    def __init__(self, db: AsyncDatabase) -> None:
        """Store the parent async database reference.

        Parameters
        ----------
        db : AsyncDatabase
            Parent async database instance.  Stored as ``self._db``; no
            extension check is performed at construction time.
        """
        self._db = db

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
        if not await self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. Run db.schema.create_extension('timescaledb')"
            )

        validate_identifiers(table, schema, time_column)
        validate_interval(chunk_time_interval)

        await self._db.execute(f"""
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
        if not await self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
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

        await self._db.execute(
            f"ALTER TABLE {schema}.{table} SET ({', '.join(settings)})"
        )

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
        if not await self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        await self._db.execute(f"""
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
        if not await self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        await self._db.execute(f"""
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
        if not await self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        return await self._db.execute(queries.LIST_HYPERTABLES)

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
        if not await self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        result = await self._db.execute(
            # %%I in queries.HYPERTABLE_INFO is escaped so psycopg passes a
            # literal %I through to PostgreSQL's format() function.
            queries.HYPERTABLE_INFO,
            [schema, table, schema, table],
        )
        return result[0] if result else {}

    async def show_chunks(
        self,
        table: str,
        older_than: str | datetime | None = None,
        newer_than: str | datetime | None = None,
        schema: str = "public",
    ) -> list[str]:
        """List chunks for a hypertable, sorted oldest-first by range start.

        Parameters
        ----------
        table : str
            Hypertable name.
        older_than : str or datetime or None, optional
            Return only chunks whose time range ends before this bound.
            A ``str`` is treated as a PostgreSQL interval literal (e.g.
            ``"30 days"``); a :class:`datetime` as an absolute timestamptz
            cutoff.  ``None`` (default) imposes no upper-age filter.
        newer_than : str or datetime or None, optional
            Return only chunks whose time range starts after this bound.
            Same type rules as ``older_than``.  ``None`` (default) imposes
            no lower-age filter.
        schema : str, optional
            Schema name, by default ``"public"``.

        Returns
        -------
        list of str
            Fully-qualified chunk names (e.g.
            ``_timescaledb_internal._hyper_1_2_chunk``), sorted
            oldest-first by ``range_start``.  Never sorted lexicographically
            — use the DB-supplied order so ``_hyper_N_10`` sorts after
            ``_hyper_N_9``.

        Raises
        ------
        ExtensionNotAvailable
            If TimescaleDB extension is not installed.
        """
        if not await self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        validate_identifiers(table, schema)

        older_frag, newer_frag, params = _build_chunk_bound_fragments(
            older_than, newer_than
        )
        sql = queries.TSDB_SHOW_CHUNKS.format(
            schema=schema,
            table=table,
            older_arg=older_frag,
            newer_arg=newer_frag,
        )
        rows = await self._db.execute(sql, params)
        return [r["chunk_name"] for r in rows]

    async def drop_chunks(
        self,
        table: str,
        older_than: str | datetime | None = None,
        newer_than: str | datetime | None = None,
        schema: str = "public",
        dry_run: bool = False,
    ) -> list[str]:
        """Drop chunks from a hypertable matching the given bounds.

        Uses a capture-before-drop pattern: the matching chunk list is
        retrieved first (while chunks still exist), then the drop is issued.
        The returned list is always in oldest-first order, identical in shape
        to :meth:`show_chunks`.

        Parameters
        ----------
        table : str
            Hypertable name.
        older_than : str or datetime or None, optional
            Drop only chunks whose time range ends before this bound.
            A ``str`` is treated as a PostgreSQL interval literal (e.g.
            ``"30 days"``); a :class:`datetime` as an absolute timestamptz
            cutoff.
        newer_than : str or datetime or None, optional
            Drop only chunks whose time range starts after this bound.
            Same type rules as ``older_than``.
        schema : str, optional
            Schema name, by default ``"public"``.
        dry_run : bool, optional
            If ``True``, return the would-be-dropped chunk list without
            actually dropping anything.  By default ``False``.

        Returns
        -------
        list of str
            Fully-qualified chunk names that were (or would be) dropped,
            sorted oldest-first by ``range_start``.

        Raises
        ------
        ValueError
            If both ``older_than`` and ``newer_than`` are ``None`` — this
            guard fires *before* any DB round-trip to prevent an accidental
            full-table wipe.
        ExtensionNotAvailable
            If TimescaleDB extension is not installed.

        Notes
        -----
        **DESTRUCTIVE / IRREVERSIBLE.**  Dropped chunks cannot be recovered
        unless you have a backup.  Always call with ``dry_run=True`` first to
        inspect which chunks will be removed.
        """
        if older_than is None and newer_than is None:
            raise ValueError(
                "drop_chunks requires at least one of older_than or newer_than. "
                "Passing both as None would drop ALL chunks — use show_chunks() "
                "to inspect first, or pass an explicit bound."
            )

        if not await self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        validate_identifiers(table, schema)

        older_frag, newer_frag, params = _build_chunk_bound_fragments(
            older_than, newer_than
        )

        # Capture the ordered preview list BEFORE dropping (rows vanish post-drop;
        # drop_chunks() SRF returns text not regclass so the JOIN would fail).
        capture_sql = queries.TSDB_SHOW_CHUNKS.format(
            schema=schema,
            table=table,
            older_arg=older_frag,
            newer_arg=newer_frag,
        )
        captured = await self._db.execute(capture_sql, params)
        chunk_list = [r["chunk_name"] for r in captured]

        if dry_run:
            return chunk_list

        drop_sql = queries.TSDB_DROP_CHUNKS.format(
            schema=schema,
            table=table,
            older_arg=older_frag,
            newer_arg=newer_frag,
        )
        await self._db.execute(drop_sql, params)
        return chunk_list
