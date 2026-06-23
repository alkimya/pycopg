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

import re
from datetime import datetime
from typing import TYPE_CHECKING

from psycopg import DatabaseError

from pycopg import queries
from pycopg.exceptions import ExtensionNotAvailable, TimescaleError
from pycopg.utils import validate_identifier, validate_identifiers, validate_interval

if TYPE_CHECKING:
    import pandas as pd

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
    elif isinstance(older_than, datetime):
        older_frag = ", older_than => %s"
        params.append(older_than)
    else:
        raise TypeError(
            "older_than must be str (interval literal) or datetime, "
            f"got {type(older_than).__name__}."
        )

    if newer_than is None:
        newer_frag = ""
    elif isinstance(newer_than, str):
        newer_frag = ", newer_than => %s::interval"
        params.append(newer_than)
    elif isinstance(newer_than, datetime):
        newer_frag = ", newer_than => %s"
        params.append(newer_than)
    else:
        raise TypeError(
            "newer_than must be str (interval literal) or datetime, "
            f"got {type(newer_than).__name__}."
        )

    return older_frag, newer_frag, params


#: Compiled regex that recognises fixed-duration interval literals such as
#: ``"7 days"``, ``"1 hour"``, ``"30 minutes"``, ``"2 weeks"``.
#: Calendar units (``month``, ``year``) are intentionally excluded — they are
#: ambiguous in seconds and are deferred to the DB (D-07).
_OFFSET_RE = re.compile(
    r"^(\d+)\s+(second|minute|hour|day|week)s?$",
    re.IGNORECASE,
)


def _check_offset_ordering(
    start_offset: str | None,
    end_offset: str | None,
) -> None:
    """Best-effort same-unit guard for continuous-aggregate policy offsets.

    Raises ``ValueError`` when ``start_offset`` and ``end_offset`` share the
    same fixed-duration unit (``second``, ``minute``, ``hour``, ``day``,
    ``week``) **and** the integer count of ``start_offset`` is less than or
    equal to that of ``end_offset``.  The start offset must cover a *longer*
    window (older data) than the end offset.

    Mixed-unit pairs (e.g. ``"1 day"`` vs ``"6 hours"``), calendar units
    (``"1 month"``, ``"1 year"``), and ``None`` offsets are silently deferred
    to the DB, which is the final authority on offset ordering (D-07).  The DB
    raises ``22023`` (``invalid_parameter_value``) on a Community build when
    ordering is violated.

    Parameters
    ----------
    start_offset : str or None
        Start offset for the policy (older boundary).  ``None`` means
        open-ended (no lower bound) — the check is skipped.
    end_offset : str or None
        End offset for the policy (newer boundary).  ``None`` means
        open-ended (no upper bound) — the check is skipped.

    Raises
    ------
    ValueError
        If both offsets share the same fixed-duration unit and
        ``start_offset`` does not cover a longer window than ``end_offset``.

    Notes
    -----
    This is a *best-effort* guard — it only covers the unambiguous same-unit
    case.  The DB is the final authority on offset ordering for calendar and
    mixed-unit intervals (D-07).  No interval-to-seconds parser is used; only
    stdlib :mod:`re` is needed (zero new dependencies).
    """
    if start_offset is None or end_offset is None:
        return  # open-ended → DB authority

    ms = _OFFSET_RE.match(start_offset.strip())
    me = _OFFSET_RE.match(end_offset.strip())

    if ms and me and ms.group(2).lower() == me.group(2).lower():
        # Both offsets share the same fixed-duration unit — compare counts.
        if int(ms.group(1)) <= int(me.group(1)):
            raise ValueError(
                f"start_offset ({start_offset!r}) must cover a longer window than "
                f"end_offset ({end_offset!r})."
            )
    # mixed-unit / month / year → defer to the DB (raises 22023 on Community builds)


#: Accepted ``into=`` values for the query helpers (D-03).  This is the
#: *inverse* of :data:`pycopg.spatial._VALID_INTO` (``("rows", "gdf")``) — the
#: timescale helpers return DataFrames or plain rows, never GeoDataFrames.
_VALID_INTO = ("df", "rows")


def _check_into(into: str, helper: str) -> None:
    """Validate the ``into=`` value for a query helper before any SQL runs.

    Parameters
    ----------
    into : str
        Requested output form — ``"df"`` (a :class:`pandas.DataFrame`) or
        ``"rows"`` (a ``list[dict]``).  ``"gdf"`` (or any other value) is
        rejected (D-03).
    helper : str
        Helper name, used only for the error message.

    Raises
    ------
    ValueError
        If ``into`` is not one of ``("df", "rows")`` — raised *before* any
        DB round-trip, which is how ``into="gdf"`` gets rejected.
    """
    if into not in _VALID_INTO:
        raise ValueError(f"{helper}(): into must be one of {_VALID_INTO}, got {into!r}")


def _to_named_binds(sql: str, params: list) -> tuple[str, dict]:
    """Convert ``%s`` placeholders to named binds for SQLAlchemy ``text()``.

    The pure builders emit psycopg-style ``%s`` placeholders with a
    positional params list, but ``to_dataframe`` wraps SQL in SQLAlchemy
    ``text()``, which requires ``:name`` binds with a dict.  This adapter
    rewrites placeholders to ``:p0``, ``:p1``, ... in order.  Local copy of
    :func:`pycopg.spatial._to_named_binds` (D-06) — kept here to avoid a
    ``timescale → spatial`` dependency on private helpers.

    Parameters
    ----------
    sql : str
        SQL containing ``%s`` placeholders.
    params : list
        Positional parameter values (one per placeholder).

    Returns
    -------
    tuple of (str, dict)
        SQL with named binds and the matching parameter dict.
    """
    parts = sql.split("%s")
    out = parts[0]
    binds: dict = {}
    for i, part in enumerate(parts[1:]):
        out += f":p{i}{part}"
        binds[f"p{i}"] = params[i]
    return out, binds


def _build_time_bucket_sql(
    table: str,
    time_column: str,
    bucket_width: str,
    aggregates: str,
    where: str | None = None,
    schema: str = "public",
) -> tuple[str, list]:
    """Build a ``time_bucket`` bucketed-aggregation SELECT (D-01, D-05).

    Identifiers (``table``, ``time_column``, ``schema``) are validated and
    interpolated; only ``bucket_width`` is bound as a ``%s`` parameter.  The
    bucket expression always carries the fixed ``AS bucket`` alias so the
    output column is deterministically named ``bucket`` (D-01).

    Parameters
    ----------
    table : str
        Hypertable name.
    time_column : str
        Timestamp column to bucket on.
    bucket_width : str
        Bucket interval (e.g. ``"1 hour"``), bound as ``%s``.
    aggregates : str
        Caller-supplied structural SQL aggregate list (e.g. ``"avg(v)"``);
        documented as structural SQL, not untrusted input (D-04).
    where : str or None, optional
        Optional structural-SQL WHERE fragment (without the ``WHERE``
        keyword).  ``None`` (default) omits the clause.
    schema : str, optional
        Schema name, by default ``"public"``.

    Returns
    -------
    tuple of (str, list)
        SQL string with ``%s`` placeholders and the positional params list
        ``[bucket_width]``.
    """
    validate_identifiers(table, schema, time_column)

    sql = (
        f"SELECT time_bucket(%s, {time_column}) AS bucket, {aggregates} "
        f"FROM {schema}.{table}"
    )
    if where is not None:
        sql += f" WHERE {where}"
    sql += " GROUP BY bucket ORDER BY bucket"

    return sql, [bucket_width]


def _build_time_bucket_gapfill_sql(
    table: str,
    time_column: str,
    bucket_width: str,
    start: datetime,
    finish: datetime,
    aggregates: str,
    where: str | None = None,
    schema: str = "public",
) -> tuple[str, list]:
    """Build a ``time_bucket_gapfill`` gap-filled SELECT (D-01, D-05, D-10).

    Identifiers (``table``, ``time_column``, ``schema``) are validated and
    interpolated; ``bucket_width``, ``start`` and ``finish`` are bound as
    ``%s``.  ``start`` and ``finish`` are bound **twice** — once as the
    explicit gapfill bound args and once in the ``WHERE`` range (``>=`` lower /
    ``<`` upper) — so the params order is
    ``[bucket_width, start, finish, start, finish]`` (D-10).  The bucket
    expression always carries the fixed ``AS bucket`` alias (D-01).

    No semantic guards are applied (no Python ``start < finish`` check, no
    ``locf(``-presence heuristic) — the DB is the authority (D-09).

    Parameters
    ----------
    table : str
        Hypertable name.
    time_column : str
        Timestamp column to bucket on.
    bucket_width : str
        Bucket interval (e.g. ``"1 hour"``), bound as ``%s``.
    start : datetime
        Lower (inclusive) bound of the gap-filled range, bound as ``%s``.
    finish : datetime
        Upper (exclusive) bound of the gap-filled range, bound as ``%s``.
    aggregates : str
        Caller-supplied structural SQL aggregate list, optionally including
        ``locf(...)`` / ``interpolate(...)`` (D-04).
    where : str or None, optional
        Optional structural-SQL WHERE fragment ANDed onto the time range.
        ``None`` (default) omits it.
    schema : str, optional
        Schema name, by default ``"public"``.

    Returns
    -------
    tuple of (str, list)
        SQL string with five ``%s`` placeholders and the positional params
        list ``[bucket_width, start, finish, start, finish]``.
    """
    validate_identifiers(table, schema, time_column)

    sql = (
        f"SELECT time_bucket_gapfill(%s, {time_column}, %s, %s) AS bucket, "
        f"{aggregates} FROM {schema}.{table} "
        f"WHERE {time_column} >= %s AND {time_column} < %s"
    )
    if where is not None:
        sql += f" AND ({where})"
    sql += " GROUP BY bucket ORDER BY bucket"

    return sql, [bucket_width, start, finish, start, finish]


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

    def add_dimension(
        self,
        table: str,
        column: str,
        partition_type: str = "hash",
        number_partitions: int | None = None,
        chunk_interval: str | None = None,
        schema: str = "public",
        if_not_exists: bool = True,
    ) -> None:
        """Add a partitioning dimension to a hypertable.

        Uses the modern TimescaleDB 2.13+ ``by_hash`` / ``by_range`` builder
        form (TSDB 2.28 verified).  Validates mutual exclusivity of
        ``number_partitions`` and ``chunk_interval`` at construction time —
        before any DB round-trip (D-07).

        Parameters
        ----------
        table : str
            Hypertable name.
        column : str
            Column to partition by.
        partition_type : str, optional
            ``"hash"`` (space-partitioning) or ``"range"`` (time/value
            partitioning), by default ``"hash"``.
        number_partitions : int or None, optional
            Number of hash partitions.  Required when
            ``partition_type="hash"``; forbidden for ``"range"``.
        chunk_interval : str or None, optional
            Chunk interval for the new dimension (e.g. ``"7 days"``).
            Required when ``partition_type="range"``; forbidden for
            ``"hash"``.
        schema : str, optional
            Schema name, by default ``"public"``.
        if_not_exists : bool, optional
            If ``True`` (default), a duplicate dimension is silently
            ignored (TSDB emits a NOTICE).  If ``False``, a duplicate
            dimension raises :exc:`TimescaleError`.

        Raises
        ------
        ValueError
            If ``partition_type`` is neither ``"hash"`` nor ``"range"``,
            or if the ``number_partitions`` / ``chunk_interval`` mutual
            exclusivity constraint is violated — raised *before* any DB
            round-trip.
        ExtensionNotAvailable
            If TimescaleDB extension is not installed.
        TimescaleError
            Wraps any database-level failure of ``add_dimension`` — most
            notably the duplicate-dimension error (SQLSTATE TS160) raised
            when ``if_not_exists=False`` and the column is already a
            dimension, but also other DB errors such as the table not being
            a hypertable.  Non-database errors (e.g. :exc:`ValueError`)
            propagate unchanged.
        """
        # D-07: construction-time mutual-exclusivity ValueError — before any
        # DB round-trip.
        if partition_type == "hash":
            if number_partitions is None:
                raise ValueError(
                    "partition_type='hash' requires number_partitions to be set."
                )
            if chunk_interval is not None:
                raise ValueError(
                    "partition_type='hash' does not accept chunk_interval. "
                    "Use number_partitions instead."
                )
            # bool is a subclass of int — reject it and non-positive values
            # before they reach by_hash() as a silently-wrong partition count.
            if isinstance(number_partitions, bool) or not isinstance(
                number_partitions, int
            ):
                raise ValueError(
                    "number_partitions must be a positive int, got "
                    f"{type(number_partitions).__name__}."
                )
            if number_partitions < 1:
                raise ValueError(
                    f"number_partitions must be >= 1, got {number_partitions}."
                )
        elif partition_type == "range":
            if chunk_interval is None:
                raise ValueError(
                    "partition_type='range' requires chunk_interval to be set."
                )
            if number_partitions is not None:
                raise ValueError(
                    "partition_type='range' does not accept number_partitions. "
                    "Use chunk_interval instead."
                )
        else:
            raise ValueError(
                f"partition_type must be 'hash' or 'range', got {partition_type!r}."
            )

        if not self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        validate_identifiers(table, schema)
        validate_identifier(column)

        if partition_type == "hash":
            dim = f"by_hash('{column}', {int(number_partitions)})"
        else:  # range
            validate_interval(chunk_interval)
            dim = f"by_range('{column}', INTERVAL '{chunk_interval}')"

        ne = ", if_not_exists => true" if if_not_exists else ""
        sql = f"SELECT add_dimension('{schema}.{table}', {dim}{ne})"

        # D-08 reshape: wrap any database-level failure of add_dimension as
        # TimescaleError.  The motivating case is the duplicate-dimension error
        # (SQLSTATE TS160) raised when if_not_exists=False; with if_not_exists
        # True, TSDB emits a NOTICE and returns normally.  We catch only
        # DatabaseError (not bare Exception) so ValueError, cancellation, and
        # non-DB programming errors propagate unchanged.
        try:
            self._db.execute(sql)
        except DatabaseError as exc:
            raise TimescaleError(
                f"add_dimension failed for column '{column}' on "
                f"'{schema}.{table}': {exc}"
            ) from exc

    def add_reorder_policy(
        self,
        table: str,
        index_name: str,
        schema: str = "public",
        if_not_exists: bool = True,
    ) -> None:
        """Add an automatic reorder policy to a hypertable.

        Registers a background job that periodically reorders chunks by the
        given index (Community license feature).  On Apache-licensed builds,
        psycopg raises ``FeatureNotSupported`` — the caller must tolerate it.

        Parameters
        ----------
        table : str
            Hypertable name.
        index_name : str
            Name of the index to reorder by.
        schema : str, optional
            Schema name, by default ``"public"``.
        if_not_exists : bool, optional
            If ``True`` (default), silently skip if a reorder policy already
            exists for this hypertable.

        Raises
        ------
        ExtensionNotAvailable
            If TimescaleDB extension is not installed.
        psycopg.errors.FeatureNotSupported
            If the local TimescaleDB runs under the Apache license (Community
            feature not available).  Callers should catch this and tolerate it
            on non-Community builds (see D-12).
        """
        if not self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        validate_identifiers(table, schema, index_name)

        ne = ", if_not_exists => true" if if_not_exists else ""
        self._db.execute(
            f"SELECT add_reorder_policy('{schema}.{table}', '{index_name}'{ne}) AS job_id"
        )

    def create_continuous_aggregate(
        self,
        view_name: str,
        select_sql: str,
        schema: str = "public",
        materialized_only: bool = True,
        with_no_data: bool = False,
    ) -> None:
        """Create a TimescaleDB continuous aggregate materialized view.

        Runs on a dedicated ``connect(autocommit=True)`` connection (D-02)
        because TimescaleDB's internal multi-transaction materialization
        cannot execute inside a transaction block.  The license error
        (``FeatureNotSupported`` / ``0A000``) propagates to the caller — no
        swallow (D-09).

        .. note::
            ``select_sql`` is structural SQL authored by the caller and is
            **not** safe for untrusted user input (the same contract as the
            ``aggregates`` argument in the Phase-32 query helpers).

        Parameters
        ----------
        view_name : str
            Name of the continuous-aggregate view to create.
        select_sql : str
            The ``SELECT`` statement for the continuous aggregate.  Must
            contain a ``time_bucket(...)`` grouping — a ``ValueError`` is
            raised before any DB round-trip if this substring is absent (D-04).
        schema : str, optional
            Schema for the view, by default ``"public"``.
        materialized_only : bool, optional
            If ``True`` (default), sets
            ``timescaledb.materialized_only=true``, returning only
            materialised data on queries.  Set to ``False`` to also include
            real-time data beyond the materialisation horizon.
        with_no_data : bool, optional
            If ``True``, creates the view with ``WITH NO DATA`` (skips
            initial materialisation).  Default ``False`` (materialises on
            creation).

        Raises
        ------
        ValueError
            If ``select_sql`` does not contain ``time_bucket(`` — a cagg
            select without a ``time_bucket`` grouping is almost always a
            user error.
        ExtensionNotAvailable
            If the TimescaleDB extension is not installed.
        psycopg.errors.FeatureNotSupported
            If the local TimescaleDB runs under the Apache license (Community
            feature not available).  Callers should catch and tolerate it on
            non-Community builds (see D-09).
        """
        validate_identifiers(view_name, schema)

        if "time_bucket(" not in select_sql:
            raise ValueError(
                "select_sql must contain a time_bucket(...) grouping. "
                "A continuous aggregate without time_bucket is almost certainly a user error."
            )

        if not self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        mo = "true" if materialized_only else "false"
        data = "NO DATA" if with_no_data else "DATA"
        sql = (
            f"CREATE MATERIALIZED VIEW {schema}.{view_name}\n"
            f"WITH (timescaledb.continuous, timescaledb.materialized_only={mo})\n"
            f"AS {select_sql}\n"
            f"WITH {data}"
        )

        with self._db.connect(autocommit=True) as conn:
            conn.execute(sql)

    def refresh_continuous_aggregate(
        self,
        view_name: str,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        schema: str = "public",
    ) -> None:
        """Refresh a TimescaleDB continuous aggregate over an optional time window.

        Runs on a dedicated ``connect(autocommit=True)`` connection (D-02)
        because TimescaleDB's refresh procedure issues multiple internal
        transactions (one per batch on TSDB 2.28+) and cannot execute inside
        a transaction block.  The license error (``FeatureNotSupported`` /
        ``0A000``) propagates to the caller — no swallow (D-09).

        Window bounds are **absolute timestamps** (``datetime`` or ``None``).
        Both ``None`` → full refresh across the entire cagg range (D-06).
        One side ``None`` → open-ended on that side.  Relative interval
        strings (``"7 days"`` etc.) are deliberately rejected — unlike
        :meth:`TimescaleAccessor.drop_chunks`, a refresh window is an
        absolute materialisation range (D-05).

        Parameters
        ----------
        view_name : str
            Name of the continuous-aggregate view to refresh.
        window_start : datetime or None, optional
            Start of the materialisation window (inclusive).  ``None``
            means no lower bound (full refresh from the beginning).
        window_end : datetime or None, optional
            End of the materialisation window (exclusive).  ``None``
            means no upper bound (full refresh to the end).
        schema : str, optional
            Schema for the view, by default ``"public"``.

        Raises
        ------
        ValueError
            If ``window_start`` or ``window_end`` is not a
            :class:`datetime` or ``None``.  Relative interval strings are
            not accepted as refresh window bounds.
        ExtensionNotAvailable
            If the TimescaleDB extension is not installed.
        psycopg.errors.FeatureNotSupported
            If the local TimescaleDB runs under the Apache license (Community
            feature not available).  Callers should catch and tolerate it on
            non-Community builds (see D-09).
        """
        validate_identifiers(view_name, schema)

        for bound in (window_start, window_end):
            if bound is not None and not isinstance(bound, datetime):
                raise ValueError(
                    "refresh window bounds must be datetime or None (absolute timestamps); "
                    f"got {type(bound).__name__}. "
                    "Relative interval strings are not accepted — "
                    "a refresh window is an absolute materialisation range."
                )

        if not self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        sql = f"CALL refresh_continuous_aggregate('{schema}.{view_name}', %s, %s)"

        with self._db.connect(autocommit=True) as conn:
            conn.execute(sql, [window_start, window_end])

    def add_continuous_aggregate_policy(
        self,
        view_name: str,
        start_offset: str | None,
        end_offset: str | None,
        schedule_interval: str = "1 hour",
        schema: str = "public",
        if_not_exists: bool = True,
    ) -> None:
        """Register an auto-refresh policy on a continuous aggregate.

        Schedules a background job that periodically calls
        ``refresh_continuous_aggregate`` on the given view.  Uses a plain
        ``self._db.execute`` call (D-01 — transaction-safe, like
        ``add_reorder_policy`` / ``add_compression_policy`` /
        ``add_retention_policy``; NOT the autocommit seam).

        On Apache-licensed TimescaleDB builds, the underlying
        ``add_continuous_aggregate_policy`` function raises
        ``FeatureNotSupported`` (SQLSTATE ``0A000``) — the license error
        propagates to the caller without swallowing (D-09).

        Parameters
        ----------
        view_name : str
            Name of the continuous-aggregate view to register the policy on.
        start_offset : str or None
            Start offset for the policy refresh window (older boundary), e.g.
            ``"7 days"``.  ``None`` means open-ended (no lower bound).
        end_offset : str or None
            End offset for the policy refresh window (newer boundary), e.g.
            ``"1 hour"``.  ``None`` means open-ended (no upper bound).
        schedule_interval : str, optional
            How often the policy job runs, by default ``"1 hour"``.
        schema : str, optional
            Schema for the view, by default ``"public"``.
        if_not_exists : bool, optional
            If ``True`` (default), silently skip if a policy already exists
            for this view.  If ``False``, the DB raises an error on duplicate.

        Raises
        ------
        ValueError
            If ``start_offset`` and ``end_offset`` share the same
            fixed-duration unit (``second``, ``minute``, ``hour``, ``day``,
            ``week``) and ``start_offset`` does not cover a longer window than
            ``end_offset`` — raised *before* any DB round-trip (D-07).
        ExtensionNotAvailable
            If TimescaleDB extension is not installed.
        psycopg.errors.FeatureNotSupported
            If the local TimescaleDB runs under the Apache license (Community
            feature not available).  Callers should catch and tolerate it on
            non-Community builds (D-09).
        """
        validate_identifiers(view_name, schema)

        if start_offset is not None:
            validate_interval(start_offset)
        if end_offset is not None:
            validate_interval(end_offset)

        _check_offset_ordering(start_offset, end_offset)

        validate_interval(schedule_interval)

        if not self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        ne = ", if_not_exists => true" if if_not_exists else ""

        start_frag = "NULL" if start_offset is None else f"INTERVAL '{start_offset}'"
        end_frag = "NULL" if end_offset is None else f"INTERVAL '{end_offset}'"

        self._db.execute(
            f"SELECT add_continuous_aggregate_policy("
            f"'{schema}.{view_name}', "
            f"start_offset => {start_frag}, "
            f"end_offset => {end_frag}, "
            f"schedule_interval => INTERVAL '{schedule_interval}'"
            f"{ne}) AS job_id"
        )

    def _run(self, sql: str, params: list, into: str) -> pd.DataFrame | list[dict]:
        """Execute a built query helper SELECT, routing on ``into=`` (D-02, D-06).

        Parameters
        ----------
        sql : str
            SQL from a pure builder, with ``%s`` placeholders.
        params : list
            Positional parameters for the SQL.
        into : str
            Output form, already validated by :func:`_check_into` — ``"df"``
            returns a :class:`pandas.DataFrame` (via the named-bind
            ``to_dataframe`` path); ``"rows"`` returns a ``list[dict]`` (via
            positional ``execute``).

        Returns
        -------
        pandas.DataFrame or list of dict
            Query results in the requested form.
        """
        if into == "df":
            named_sql, binds = _to_named_binds(sql, params)
            return self._db.to_dataframe(sql=named_sql, params=binds)
        return self._db.execute(sql, params)

    def time_bucket(
        self,
        table: str,
        time_column: str,
        bucket_width: str,
        aggregates: str,
        where: str | None = None,
        schema: str = "public",
        into: str = "df",
    ) -> pd.DataFrame | list[dict]:
        """Run a ``time_bucket`` bucketed aggregation (TS-ADV-06).

        Buckets ``time_column`` into fixed ``bucket_width`` intervals and
        applies the caller-supplied ``aggregates``.  The first output column
        is deterministically named ``bucket`` (D-01).

        Parameters
        ----------
        table : str
            Hypertable name.
        time_column : str
            Timestamp column to bucket on.
        bucket_width : str
            Bucket interval (e.g. ``"1 hour"``), bound as ``%s``.
        aggregates : str
            Caller-supplied **structural SQL** aggregate list (e.g.
            ``"avg(value), max(value)"``).  Documented as structural SQL — not
            untrusted end-user input — the same posture as the spatial
            accessor (D-04).
        where : str or None, optional
            Optional structural-SQL ``WHERE`` fragment (without the ``WHERE``
            keyword).  ``None`` (default) omits the clause.
        schema : str, optional
            Schema name, by default ``"public"``.
        into : str, optional
            Output form — ``"df"`` (default) returns a
            :class:`pandas.DataFrame`; ``"rows"`` returns a ``list[dict]``.
            Any other value (e.g. ``"gdf"``) raises :class:`ValueError`
            *before* any DB round-trip (D-03).

        Returns
        -------
        pandas.DataFrame or list of dict
            Bucketed aggregation results in the requested form.

        Raises
        ------
        ValueError
            If ``into`` is not ``"df"`` or ``"rows"`` — raised before any DB
            call (D-03).
        ExtensionNotAvailable
            If the TimescaleDB extension is not installed.
        """
        _check_into(into, "time_bucket")
        if not self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. Run db.schema.create_extension('timescaledb')"
            )
        sql, params = _build_time_bucket_sql(
            table, time_column, bucket_width, aggregates, where=where, schema=schema
        )
        return self._run(sql, params, into)

    def time_bucket_gapfill(
        self,
        table: str,
        time_column: str,
        bucket_width: str,
        start: datetime,
        finish: datetime,
        aggregates: str,
        where: str | None = None,
        schema: str = "public",
        into: str = "df",
    ) -> pd.DataFrame | list[dict]:
        """Run a gap-filled ``time_bucket_gapfill`` aggregation (TS-ADV-07).

        Like :meth:`time_bucket` but NULL-pads missing buckets across the
        explicit ``[start, finish)`` range, enabling ``locf()`` /
        ``interpolate()`` inside ``aggregates``.  ``start`` and ``finish`` are
        **required** absolute bounds — gapfill cannot infer them from a
        ``WHERE`` predicate (TS-ADV-07) — and are bound twice (gapfill args +
        WHERE range, D-10).  The first output column is named ``bucket``.

        No Python ``start < finish`` guard is applied; the DB is the authority
        (D-09).  On Apache-licensed builds ``time_bucket_gapfill`` raises
        :class:`psycopg.errors.FeatureNotSupported` (a license gate, not a
        syntax error).

        Parameters
        ----------
        table : str
            Hypertable name.
        time_column : str
            Timestamp column to bucket on.
        bucket_width : str
            Bucket interval (e.g. ``"1 hour"``), bound as ``%s``.
        start : datetime
            Lower (inclusive) bound of the gap-filled range, bound as ``%s``.
        finish : datetime
            Upper (exclusive) bound of the gap-filled range, bound as ``%s``.
        aggregates : str
            Caller-supplied **structural SQL** aggregate list, optionally
            including ``locf(...)`` / ``interpolate(...)`` (D-04).
        where : str or None, optional
            Optional structural-SQL ``WHERE`` fragment ANDed onto the time
            range.  ``None`` (default) omits it.
        schema : str, optional
            Schema name, by default ``"public"``.
        into : str, optional
            Output form — ``"df"`` (default) or ``"rows"``; any other value
            (e.g. ``"gdf"``) raises :class:`ValueError` before any DB call
            (D-03).

        Returns
        -------
        pandas.DataFrame or list of dict
            Gap-filled bucketed results in the requested form.

        Raises
        ------
        ValueError
            If ``into`` is not ``"df"`` or ``"rows"`` — raised before any DB
            call (D-03).
        ExtensionNotAvailable
            If the TimescaleDB extension is not installed.
        psycopg.errors.FeatureNotSupported
            If the local TimescaleDB runs under the Apache license (gapfill is
            a Community/TSL feature).
        """
        _check_into(into, "time_bucket_gapfill")
        if not self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. Run db.schema.create_extension('timescaledb')"
            )
        sql, params = _build_time_bucket_gapfill_sql(
            table,
            time_column,
            bucket_width,
            start,
            finish,
            aggregates,
            where=where,
            schema=schema,
        )
        return self._run(sql, params, into)


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

    async def add_dimension(
        self,
        table: str,
        column: str,
        partition_type: str = "hash",
        number_partitions: int | None = None,
        chunk_interval: str | None = None,
        schema: str = "public",
        if_not_exists: bool = True,
    ) -> None:
        """Add a partitioning dimension to a hypertable.

        Async mirror of :meth:`TimescaleAccessor.add_dimension`.

        Parameters
        ----------
        table : str
            Hypertable name.
        column : str
            Column to partition by.
        partition_type : str, optional
            ``"hash"`` (space-partitioning) or ``"range"`` (time/value
            partitioning), by default ``"hash"``.
        number_partitions : int or None, optional
            Number of hash partitions.  Required when
            ``partition_type="hash"``; forbidden for ``"range"``.
        chunk_interval : str or None, optional
            Chunk interval for the new dimension (e.g. ``"7 days"``).
            Required when ``partition_type="range"``; forbidden for
            ``"hash"``.
        schema : str, optional
            Schema name, by default ``"public"``.
        if_not_exists : bool, optional
            If ``True`` (default), a duplicate dimension is silently
            ignored.  If ``False``, a duplicate dimension raises
            :exc:`TimescaleError`.

        Raises
        ------
        ValueError
            If ``partition_type`` is invalid or mutual-exclusivity is
            violated — raised *before* any DB round-trip (D-07).
        ExtensionNotAvailable
            If TimescaleDB extension is not installed.
        TimescaleError
            Wraps any database-level failure of ``add_dimension`` — most
            notably the duplicate-dimension error (SQLSTATE TS160) raised
            when ``if_not_exists=False``.  Non-database errors (e.g.
            :exc:`ValueError`) propagate unchanged.
        """
        # D-07: construction-time mutual-exclusivity ValueError — before any
        # DB round-trip (plain Python, no await).
        if partition_type == "hash":
            if number_partitions is None:
                raise ValueError(
                    "partition_type='hash' requires number_partitions to be set."
                )
            if chunk_interval is not None:
                raise ValueError(
                    "partition_type='hash' does not accept chunk_interval. "
                    "Use number_partitions instead."
                )
            # bool is a subclass of int — reject it and non-positive values
            # before they reach by_hash() as a silently-wrong partition count.
            if isinstance(number_partitions, bool) or not isinstance(
                number_partitions, int
            ):
                raise ValueError(
                    "number_partitions must be a positive int, got "
                    f"{type(number_partitions).__name__}."
                )
            if number_partitions < 1:
                raise ValueError(
                    f"number_partitions must be >= 1, got {number_partitions}."
                )
        elif partition_type == "range":
            if chunk_interval is None:
                raise ValueError(
                    "partition_type='range' requires chunk_interval to be set."
                )
            if number_partitions is not None:
                raise ValueError(
                    "partition_type='range' does not accept number_partitions. "
                    "Use chunk_interval instead."
                )
        else:
            raise ValueError(
                f"partition_type must be 'hash' or 'range', got {partition_type!r}."
            )

        if not await self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        validate_identifiers(table, schema)
        validate_identifier(column)

        if partition_type == "hash":
            dim = f"by_hash('{column}', {int(number_partitions)})"
        else:  # range
            validate_interval(chunk_interval)
            dim = f"by_range('{column}', INTERVAL '{chunk_interval}')"

        ne = ", if_not_exists => true" if if_not_exists else ""
        sql = f"SELECT add_dimension('{schema}.{table}', {dim}{ne})"

        # D-08 reshape: wrap any database-level failure as TimescaleError (the
        # motivating case is the duplicate-dimension error when
        # if_not_exists=False).  Catch only DatabaseError so non-DB errors
        # propagate unchanged.
        try:
            await self._db.execute(sql)
        except DatabaseError as exc:
            raise TimescaleError(
                f"add_dimension failed for column '{column}' on "
                f"'{schema}.{table}': {exc}"
            ) from exc

    async def add_reorder_policy(
        self,
        table: str,
        index_name: str,
        schema: str = "public",
        if_not_exists: bool = True,
    ) -> None:
        """Add an automatic reorder policy to a hypertable.

        Async mirror of :meth:`TimescaleAccessor.add_reorder_policy`.

        Parameters
        ----------
        table : str
            Hypertable name.
        index_name : str
            Name of the index to reorder by.
        schema : str, optional
            Schema name, by default ``"public"``.
        if_not_exists : bool, optional
            If ``True`` (default), silently skip if a reorder policy already
            exists for this hypertable.

        Raises
        ------
        ExtensionNotAvailable
            If TimescaleDB extension is not installed.
        psycopg.errors.FeatureNotSupported
            If the local TimescaleDB runs under the Apache license (Community
            feature not available).  Callers should catch and tolerate it on
            non-Community builds (D-12).
        """
        if not await self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        validate_identifiers(table, schema, index_name)

        ne = ", if_not_exists => true" if if_not_exists else ""
        await self._db.execute(
            f"SELECT add_reorder_policy('{schema}.{table}', '{index_name}'{ne}) AS job_id"
        )

    async def create_continuous_aggregate(
        self,
        view_name: str,
        select_sql: str,
        schema: str = "public",
        materialized_only: bool = True,
        with_no_data: bool = False,
    ) -> None:
        """Create a TimescaleDB continuous aggregate materialized view.

        Async mirror of :meth:`TimescaleAccessor.create_continuous_aggregate`.
        Runs on a dedicated ``async with self._db.connect(autocommit=True)``
        connection (D-02).  The license error (``FeatureNotSupported`` /
        ``0A000``) propagates to the caller — no swallow (D-09).

        .. note::
            ``select_sql`` is structural SQL authored by the caller and is
            **not** safe for untrusted user input.

        Parameters
        ----------
        view_name : str
            Name of the continuous-aggregate view to create.
        select_sql : str
            The ``SELECT`` statement for the continuous aggregate.  Must
            contain a ``time_bucket(...)`` grouping — a ``ValueError`` is
            raised before any DB round-trip if this substring is absent (D-04).
        schema : str, optional
            Schema for the view, by default ``"public"``.
        materialized_only : bool, optional
            If ``True`` (default), sets
            ``timescaledb.materialized_only=true``.  Set to ``False`` to also
            include real-time data beyond the materialisation horizon.
        with_no_data : bool, optional
            If ``True``, creates with ``WITH NO DATA``.  Default ``False``
            (materialises on creation).

        Raises
        ------
        ValueError
            If ``select_sql`` does not contain ``time_bucket(`` — a cagg
            select without a ``time_bucket`` grouping is almost always a
            user error.
        ExtensionNotAvailable
            If the TimescaleDB extension is not installed.
        psycopg.errors.FeatureNotSupported
            If the local TimescaleDB runs under the Apache license (Community
            feature not available).  Callers should catch and tolerate it on
            non-Community builds (see D-09).
        """
        validate_identifiers(view_name, schema)

        if "time_bucket(" not in select_sql:
            raise ValueError(
                "select_sql must contain a time_bucket(...) grouping. "
                "A continuous aggregate without time_bucket is almost certainly a user error."
            )

        if not await self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        mo = "true" if materialized_only else "false"
        data = "NO DATA" if with_no_data else "DATA"
        sql = (
            f"CREATE MATERIALIZED VIEW {schema}.{view_name}\n"
            f"WITH (timescaledb.continuous, timescaledb.materialized_only={mo})\n"
            f"AS {select_sql}\n"
            f"WITH {data}"
        )

        async with self._db.connect(autocommit=True) as conn:
            await conn.execute(sql)

    async def refresh_continuous_aggregate(
        self,
        view_name: str,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        schema: str = "public",
    ) -> None:
        """Refresh a TimescaleDB continuous aggregate over an optional time window.

        Async mirror of :meth:`TimescaleAccessor.refresh_continuous_aggregate`.
        Runs on a dedicated ``async with self._db.connect(autocommit=True)``
        connection (D-02).  The license error (``FeatureNotSupported`` /
        ``0A000``) propagates to the caller — no swallow (D-09).

        Parameters
        ----------
        view_name : str
            Name of the continuous-aggregate view to refresh.
        window_start : datetime or None, optional
            Start of the materialisation window (inclusive).  ``None``
            means no lower bound (full refresh from the beginning).
        window_end : datetime or None, optional
            End of the materialisation window (exclusive).  ``None``
            means no upper bound (full refresh to the end).
        schema : str, optional
            Schema for the view, by default ``"public"``.

        Raises
        ------
        ValueError
            If ``window_start`` or ``window_end`` is not a
            :class:`datetime` or ``None``.  Relative interval strings are
            not accepted as refresh window bounds.
        ExtensionNotAvailable
            If the TimescaleDB extension is not installed.
        psycopg.errors.FeatureNotSupported
            If the local TimescaleDB runs under the Apache license (Community
            feature not available).  Callers should catch and tolerate it on
            non-Community builds (see D-09).
        """
        validate_identifiers(view_name, schema)

        for bound in (window_start, window_end):
            if bound is not None and not isinstance(bound, datetime):
                raise ValueError(
                    "refresh window bounds must be datetime or None (absolute timestamps); "
                    f"got {type(bound).__name__}. "
                    "Relative interval strings are not accepted — "
                    "a refresh window is an absolute materialisation range."
                )

        if not await self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        sql = f"CALL refresh_continuous_aggregate('{schema}.{view_name}', %s, %s)"

        async with self._db.connect(autocommit=True) as conn:
            await conn.execute(sql, [window_start, window_end])

    async def add_continuous_aggregate_policy(
        self,
        view_name: str,
        start_offset: str | None,
        end_offset: str | None,
        schedule_interval: str = "1 hour",
        schema: str = "public",
        if_not_exists: bool = True,
    ) -> None:
        """Register an auto-refresh policy on a continuous aggregate.

        Async mirror of
        :meth:`TimescaleAccessor.add_continuous_aggregate_policy`.
        Uses a plain ``await self._db.execute`` call (D-01 — transaction-safe;
        NOT the autocommit seam).

        Parameters
        ----------
        view_name : str
            Name of the continuous-aggregate view to register the policy on.
        start_offset : str or None
            Start offset for the policy refresh window (older boundary), e.g.
            ``"7 days"``.  ``None`` means open-ended (no lower bound).
        end_offset : str or None
            End offset for the policy refresh window (newer boundary), e.g.
            ``"1 hour"``.  ``None`` means open-ended (no upper bound).
        schedule_interval : str, optional
            How often the policy job runs, by default ``"1 hour"``.
        schema : str, optional
            Schema for the view, by default ``"public"``.
        if_not_exists : bool, optional
            If ``True`` (default), silently skip if a policy already exists
            for this view.  If ``False``, the DB raises an error on duplicate.

        Raises
        ------
        ValueError
            If ``start_offset`` and ``end_offset`` share the same
            fixed-duration unit and ``start_offset`` does not cover a longer
            window than ``end_offset`` — raised *before* any DB round-trip
            (D-07).
        ExtensionNotAvailable
            If TimescaleDB extension is not installed.
        psycopg.errors.FeatureNotSupported
            If the local TimescaleDB runs under the Apache license (Community
            feature not available).  Callers should catch and tolerate it on
            non-Community builds (D-09).
        """
        validate_identifiers(view_name, schema)

        if start_offset is not None:
            validate_interval(start_offset)
        if end_offset is not None:
            validate_interval(end_offset)

        _check_offset_ordering(start_offset, end_offset)

        validate_interval(schedule_interval)

        if not await self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. "
                "Run db.schema.create_extension('timescaledb')"
            )

        ne = ", if_not_exists => true" if if_not_exists else ""

        start_frag = "NULL" if start_offset is None else f"INTERVAL '{start_offset}'"
        end_frag = "NULL" if end_offset is None else f"INTERVAL '{end_offset}'"

        await self._db.execute(
            f"SELECT add_continuous_aggregate_policy("
            f"'{schema}.{view_name}', "
            f"start_offset => {start_frag}, "
            f"end_offset => {end_frag}, "
            f"schedule_interval => INTERVAL '{schedule_interval}'"
            f"{ne}) AS job_id"
        )

    async def _run(
        self, sql: str, params: list, into: str
    ) -> pd.DataFrame | list[dict]:
        """Execute a built query helper SELECT asynchronously (D-07).

        Exact awaited mirror of :meth:`TimescaleAccessor._run`.

        Parameters
        ----------
        sql : str
            SQL from a pure builder, with ``%s`` placeholders.
        params : list
            Positional parameters for the SQL.
        into : str
            Output form, already validated by :func:`_check_into` — ``"df"``
            returns a :class:`pandas.DataFrame` (via the awaited named-bind
            ``to_dataframe`` path); ``"rows"`` returns a ``list[dict]`` (via
            awaited positional ``execute``).

        Returns
        -------
        pandas.DataFrame or list of dict
            Query results in the requested form.
        """
        if into == "df":
            named_sql, binds = _to_named_binds(sql, params)
            return await self._db.to_dataframe(sql=named_sql, params=binds)
        return await self._db.execute(sql, params)

    async def time_bucket(
        self,
        table: str,
        time_column: str,
        bucket_width: str,
        aggregates: str,
        where: str | None = None,
        schema: str = "public",
        into: str = "df",
    ) -> pd.DataFrame | list[dict]:
        """Run a ``time_bucket`` bucketed aggregation (TS-ADV-06, TS-ADV-10).

        Async mirror of :meth:`TimescaleAccessor.time_bucket` — buckets
        ``time_column`` into fixed ``bucket_width`` intervals and applies the
        caller-supplied ``aggregates``.  The first output column is
        deterministically named ``bucket`` (D-01).

        Parameters
        ----------
        table : str
            Hypertable name.
        time_column : str
            Timestamp column to bucket on.
        bucket_width : str
            Bucket interval (e.g. ``"1 hour"``), bound as ``%s``.
        aggregates : str
            Caller-supplied **structural SQL** aggregate list (e.g.
            ``"avg(value), max(value)"``).  Documented as structural SQL — not
            untrusted end-user input (D-04).
        where : str or None, optional
            Optional structural-SQL ``WHERE`` fragment (without the ``WHERE``
            keyword).  ``None`` (default) omits the clause.
        schema : str, optional
            Schema name, by default ``"public"``.
        into : str, optional
            Output form — ``"df"`` (default) returns a
            :class:`pandas.DataFrame`; ``"rows"`` returns a ``list[dict]``.
            Any other value (e.g. ``"gdf"``) raises :class:`ValueError`
            *before* any DB round-trip (D-03).

        Returns
        -------
        pandas.DataFrame or list of dict
            Bucketed aggregation results in the requested form.

        Raises
        ------
        ValueError
            If ``into`` is not ``"df"`` or ``"rows"`` — raised before any DB
            call (D-03).
        ExtensionNotAvailable
            If the TimescaleDB extension is not installed.
        """
        _check_into(into, "time_bucket")
        if not await self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. Run db.schema.create_extension('timescaledb')"
            )
        sql, params = _build_time_bucket_sql(
            table, time_column, bucket_width, aggregates, where=where, schema=schema
        )
        return await self._run(sql, params, into)

    async def time_bucket_gapfill(
        self,
        table: str,
        time_column: str,
        bucket_width: str,
        start: datetime,
        finish: datetime,
        aggregates: str,
        where: str | None = None,
        schema: str = "public",
        into: str = "df",
    ) -> pd.DataFrame | list[dict]:
        """Run a gap-filled ``time_bucket_gapfill`` aggregation (TS-ADV-07/10).

        Async mirror of :meth:`TimescaleAccessor.time_bucket_gapfill` — NULL-pads
        missing buckets across the explicit ``[start, finish)`` range.  ``start``
        and ``finish`` are **required** absolute bounds (TS-ADV-07) and are bound
        twice (gapfill args + WHERE range, D-10).  No Python ``start < finish``
        guard is applied (D-09).  On Apache-licensed builds the underlying
        function raises :class:`psycopg.errors.FeatureNotSupported` (a license
        gate, not a syntax error).

        Parameters
        ----------
        table : str
            Hypertable name.
        time_column : str
            Timestamp column to bucket on.
        bucket_width : str
            Bucket interval (e.g. ``"1 hour"``), bound as ``%s``.
        start : datetime
            Lower (inclusive) bound of the gap-filled range, bound as ``%s``.
        finish : datetime
            Upper (exclusive) bound of the gap-filled range, bound as ``%s``.
        aggregates : str
            Caller-supplied **structural SQL** aggregate list, optionally
            including ``locf(...)`` / ``interpolate(...)`` (D-04).
        where : str or None, optional
            Optional structural-SQL ``WHERE`` fragment ANDed onto the time
            range.  ``None`` (default) omits it.
        schema : str, optional
            Schema name, by default ``"public"``.
        into : str, optional
            Output form — ``"df"`` (default) or ``"rows"``; any other value
            (e.g. ``"gdf"``) raises :class:`ValueError` before any DB call
            (D-03).

        Returns
        -------
        pandas.DataFrame or list of dict
            Gap-filled bucketed results in the requested form.

        Raises
        ------
        ValueError
            If ``into`` is not ``"df"`` or ``"rows"`` — raised before any DB
            call (D-03).
        ExtensionNotAvailable
            If the TimescaleDB extension is not installed.
        psycopg.errors.FeatureNotSupported
            If the local TimescaleDB runs under the Apache license (gapfill is
            a Community/TSL feature).
        """
        _check_into(into, "time_bucket_gapfill")
        if not await self._db.schema.has_extension("timescaledb"):
            raise ExtensionNotAvailable(
                "TimescaleDB extension not installed. Run db.schema.create_extension('timescaledb')"
            )
        sql, params = _build_time_bucket_gapfill_sql(
            table,
            time_column,
            bucket_width,
            start,
            finish,
            aggregates,
            where=where,
            schema=schema,
        )
        return await self._run(sql, params, into)
