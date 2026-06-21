"""ETL pipeline descriptor and pure SQL builders.

This module provides the pure foundation of the (future) ``db.etl``
accessor namespace: the public ``Pipeline`` descriptor plus module-level
SQL builder functions. Builders are stateless functions returning
``(sql, params)`` tuples — no ``self``, no I/O, no DB — so they are
shared byte-identical between the sync and async accessors and are
fully unit-testable without a database.

Scope boundary: a ``Pipeline`` describes exactly one extract → transform
→ load flow (one source, one target, one pass). There are no
``depends_on``, ``schedule``, ``retry_on_failure``, or ``timeout``
fields — DAG/scheduler orchestration is out of scope for v0.5.0
(Pitfall 11).

Security invariants (v0.3.1, mirrored from spatial.py):

- Every identifier (table, schema, conflict columns) passes
  :func:`pycopg.utils.validate_identifiers` before any string
  interpolation.
- Every user value is emitted as a ``%s`` placeholder appended to the
  params list — never f-string interpolated (D-12).
"""

from __future__ import annotations

import asyncio
import traceback
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import replace as dc_replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pandas as pd
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from pycopg import queries
from pycopg.exceptions import (  # noqa: F401
    ETLError,
    ETLTargetNotFoundError,
    ETLTransformError,
)
from pycopg.utils import validate_identifiers

if TYPE_CHECKING:
    from pycopg.async_database import AsyncDatabase
    from pycopg.database import Database

#: Accepted ``load_mode=`` values (D-06).
#: ``replace`` is the public name for the truncate-load strategy; ``upsert``
#: requires ``conflict_columns`` (D-07). ``truncate`` and other values are
#: rejected at construction time.
_VALID_LOAD_MODES = ("append", "replace", "upsert")


def _validate_load_mode(load_mode: str) -> None:
    """Validate a ``load_mode=`` value.

    Parameters
    ----------
    load_mode : str
        Load strategy — must be ``"append"``, ``"replace"``, or
        ``"upsert"`` (D-06).

    Raises
    ------
    ValueError
        If ``load_mode`` is not one of the accepted values.
    """
    if load_mode not in _VALID_LOAD_MODES:
        raise ValueError(
            f"load_mode must be one of {_VALID_LOAD_MODES}, got {load_mode!r}"
        )


def _validate_incremental(incremental_column: str | None, load_mode: str) -> None:
    """Validate the ``incremental_column`` / ``load_mode`` combination.

    Parameters
    ----------
    incremental_column : str or None
        Watermark column name, or ``None`` for a non-incremental pipeline.
        ``None`` short-circuits — both checks are skipped (D-15).
    load_mode : str
        Load strategy. Incremental loads require ``"upsert"``;
        ``"append"`` and ``"replace"`` are forbidden (D-16).

    Raises
    ------
    ValueError
        If ``incremental_column`` is set and ``load_mode`` is ``"append"``
        or ``"replace"`` (the forbidden-combo intent error, checked first).
    InvalidIdentifier
        If ``incremental_column`` is not a valid SQL identifier (D-15).
    """
    # Non-incremental pipelines skip both checks (D-15 short-circuit).
    if incremental_column is None:
        return
    # Forbidden combo (intent error) is reported before the identifier
    # syntax check (D-15 order).
    if load_mode in ("append", "replace"):
        raise ValueError(
            f"incremental_column requires load_mode='upsert' (got {load_mode!r}); "
            "'append' and 'replace' are forbidden with incremental loads because "
            "upsert guarantees idempotency (ETL-INC-01)"
        )
    validate_identifiers(incremental_column)


@dataclass(frozen=True)
class Pipeline:
    """Declarative ETL pipeline descriptor.

    Describes a single extract → transform → load flow from ``source``
    to ``target``. The dataclass is frozen for idempotency safety (D-02):
    all fields are set at construction and cannot be mutated afterwards.

    ``conflict_columns`` is always stored as a ``tuple[str, ...]``
    regardless of whether a list or tuple is passed at the call site
    (D-02). The ``__post_init__`` normalizes it via ``object.__setattr__``
    so the frozen-dataclass invariant is honored.

    Parameters
    ----------
    name : str
        Human-readable pipeline identifier (used as ``pipeline_name``
        in ``pipeline_runs`` tracking rows).
    source : str
        Source table name or a SQL SELECT/WITH statement string. If the
        string contains whitespace or starts with SELECT/WITH, it is
        treated as a SQL query at extract time; otherwise as a table name
        (heuristic via ``_is_sql_source``; Phase 18 wires extraction).
        Only the string is stored here — no ``source_type`` field (D-04).
    target : str
        Target table name. Must be a plain identifier (no whitespace).
    load_mode : str, optional
        Load strategy — one of ``"append"``, ``"replace"``, or
        ``"upsert"`` (D-06). Default ``"append"``. ``"replace"`` issues a
        TRUNCATE before the insert; ``"upsert"`` performs an INSERT … ON
        CONFLICT DO UPDATE and requires ``conflict_columns`` (D-07).
    conflict_columns : tuple of str, optional
        Ordered conflict-key column names used for the ``upsert`` ON
        CONFLICT clause. Must be non-empty when ``load_mode="upsert"``
        (D-07). Accepts a list at the call site; always stored as a tuple
        (D-02). Default ``()``.
    schema : str, optional
        Schema that contains ``target``. Default ``"public"``.
    transform : callable or list of callable, optional
        Python callable (or ordered list of callables) applied to the
        extracted DataFrame/rows before the load step. Phase 18 invokes
        these in sequence. Default ``None`` (identity — no transform).
    extract_limit : int or None, optional
        Maximum number of rows to extract. ``None`` (default) = full
        materialization. Phase 18 wires this as ``LIMIT %s`` in the
        extract query. ``extract_batch_size`` streaming is deferred to
        v0.6.0. If provided, must be a positive integer (D-11).
    incremental_column : str or None, optional
        Watermark column for incremental extraction (ETL-INC-01). ``None``
        (default) = full-load pipeline. When set it must be a valid SQL
        identifier and ``load_mode`` must be ``"upsert"`` — ``"append"``
        and ``"replace"`` are rejected at construction (D-16). The column
        is expected to hold a monotonic, non-decreasing watermark (an
        aware ``datetime`` if it is a timestamp); this contract is
        documented, not enforced, in this layer (D-03). Default ``None``.

    Raises
    ------
    ValueError
        If ``load_mode`` is not one of the accepted values (D-06).
    ValueError
        If ``load_mode="upsert"`` and ``conflict_columns`` is empty (D-07).
    ValueError
        If ``extract_limit`` is a non-positive integer (D-11, Claude's
        Discretion guard — prevents silent OOM misdirection).
    ValueError
        If ``incremental_column`` is set and ``load_mode`` is not
        ``"upsert"`` (D-16, ETL-INC-01).

    Examples
    --------
    Basic append pipeline::

        p = Pipeline(name="nightly", source="raw_events", target="events")

    Upsert pipeline with conflict key::

        p = Pipeline(
            name="upsert_users",
            source="SELECT * FROM staging_users",
            target="users",
            load_mode="upsert",
            conflict_columns=["user_id"],
        )
    """

    name: str
    source: str
    target: str
    load_mode: str = "append"
    conflict_columns: tuple[str, ...] = ()
    schema: str = "public"
    transform: Callable | list[Callable] | None = None
    extract_limit: int | None = None
    incremental_column: str | None = None

    def __post_init__(self) -> None:
        """Validate and normalize fields at construction time.

        Raises
        ------
        ValueError
            If ``conflict_columns`` is passed as a bare string,
            ``load_mode`` is invalid (D-06), ``upsert`` is requested
            without ``conflict_columns`` (D-07), ``extract_limit`` is
            not a positive integer (D-11), or ``incremental_column`` is
            set with a non-``upsert`` ``load_mode`` (D-16).
        """
        # Reject a bare string before normalization: a str is iterable, so
        # tuple("user_id") would silently explode into per-character columns
        # (('u', 's', ...)) and pass the non-empty upsert check (D-07).
        if isinstance(self.conflict_columns, str):
            raise ValueError(
                "conflict_columns must be a sequence of column names, not a "
                f"single string; got {self.conflict_columns!r} (did you mean "
                f"[{self.conflict_columns!r}]?)"
            )
        # Normalize conflict_columns from any iterable to a tuple (D-02).
        # Frozen dataclass requires object.__setattr__ for mutation.
        if not isinstance(self.conflict_columns, tuple):
            object.__setattr__(self, "conflict_columns", tuple(self.conflict_columns))
        # Validate load_mode first (D-06).
        _validate_load_mode(self.load_mode)
        # Validate incremental_column / load_mode combo + identifier
        # (D-14/D-15/D-16/D-17) — after load_mode, before the upsert check.
        _validate_incremental(self.incremental_column, self.load_mode)
        # Require conflict_columns when upsert is selected (D-07).
        if self.load_mode == "upsert" and not self.conflict_columns:
            raise ValueError(
                "load_mode='upsert' requires conflict_columns to be non-empty (D-07)"
            )
        # Reject non-positive extract_limit (D-11, Claude's Discretion).
        # bool is a subclass of int, so guard against it explicitly:
        # extract_limit=True would otherwise pass and render as LIMIT 1/true.
        if self.extract_limit is not None:
            if isinstance(self.extract_limit, bool) or not isinstance(
                self.extract_limit, int
            ):
                raise ValueError(
                    "extract_limit must be a positive integer or None, got "
                    f"{self.extract_limit!r}"
                )
            if self.extract_limit <= 0:
                raise ValueError(
                    f"extract_limit must be a positive integer, got {self.extract_limit!r}"
                )


@dataclass(frozen=True)
class RunResult:
    """Immutable snapshot of a completed (or dry-run) ETL pipeline run.

    Parameters
    ----------
    run_id : int or None
        The ``pipeline_runs.run_id`` for persisted runs; ``None`` for
        dry runs (no DB row written, D-05/D-08).
    pipeline_name : str
        Pipeline identifier, from ``Pipeline.name``.
    status : str
        One of ``'success'``, ``'failed'`` (persisted runs), or
        ``'dry_run'`` (transient, never stored, D-08).
    rows_extracted : int
        Rows read from the source (after transform for dry runs).
    rows_loaded : int
        Rows written to the target; ``0`` for dry runs and failed runs.
    started_at : datetime
        UTC timestamp when the run started.
    finished_at : datetime
        UTC timestamp when the run ended.
    error : str or None
        Short error message from ``pipeline_runs.error_message``; ``None``
        on success or dry run (D-03).
    watermark_used : datetime or int or str or None
        The filter floor applied to this run — the watermark value read
        before extract, used as the ``WHERE col > wm`` bound (D-A1).
        ``None`` for non-incremental pipelines and for stored rows
        surfaced by ``history()`` / ``last_run()`` (where the per-run
        input is never persisted).
    watermark_recorded : datetime or int or str or None
        The new high-water mark persisted for this run — decoded from
        ``pipeline_runs.watermark`` (D-A1).  ``None`` for
        non-incremental pipelines and when no watermark was stored
        (e.g. empty batch, failed run, or NULL in ``pipeline_runs``).
    """

    run_id: int | None
    pipeline_name: str
    status: str
    rows_extracted: int
    rows_loaded: int
    started_at: datetime
    finished_at: datetime
    error: str | None
    watermark_used: datetime | int | str | None = None
    watermark_recorded: datetime | int | str | None = None


def _is_sql_source(source: str) -> bool:
    """Heuristically determine whether a source string is a SQL query.

    Returns ``True`` if the string looks like a SQL SELECT/WITH statement
    (D-05 heuristic). Phase 18 uses this to decide whether to run
    ``db.execute(source, ...)`` or ``SELECT * FROM {source}``.

    No validation is performed — this is a best-effort classifier only.

    Parameters
    ----------
    source : str
        Pipeline source string (table name or SQL query).

    Returns
    -------
    bool
        ``True`` if the source appears to be a SQL query; ``False`` if
        it appears to be a plain table name.
    """
    stripped = source.strip()
    if stripped.upper().startswith(("SELECT", "WITH")):
        return True
    # Presence of whitespace in a non-keyword string indicates SQL.
    return " " in stripped


def build_truncate_sql(table: str, schema: str = "public") -> tuple[str, list]:
    """Build a TRUNCATE SQL statement for a replace-mode load target.

    Called by the Phase 18 ``replace`` load path to empty the target
    table before the bulk insert. Identifiers are validated before
    interpolation (D-13) — an invalid ``table`` or ``schema`` name raises
    ``InvalidIdentifier`` and no SQL is produced.

    Parameters
    ----------
    table : str
        Table to truncate. Must be a valid SQL identifier.
    schema : str, optional
        Schema that contains the table, by default ``"public"``. Must be
        a valid SQL identifier.

    Returns
    -------
    tuple of (str, list)
        SQL string of the form ``"TRUNCATE TABLE {schema}.{table}"`` and
        an empty parameter list (no user values are interpolated — only
        the validated identifiers).

    Raises
    ------
    InvalidIdentifier
        If ``table`` or ``schema`` is not a valid SQL identifier (D-13).
    """
    validate_identifiers(table, schema)
    return f"TRUNCATE TABLE {schema}.{table}", []


def build_init_sql() -> tuple[str, list]:
    """Return the idempotent DDL for creating the ``pipeline_runs`` table.

    Returns the ``ETL_INIT_PIPELINE_RUNS`` constant from
    :mod:`pycopg.queries`. The DDL uses ``CREATE TABLE IF NOT EXISTS``
    (D-15) so it is safe to call repeatedly (lazy auto-create and explicit
    ``init()`` both use this, per OD-3 / D-15).

    The ``pipeline_runs`` schema:

    - ``run_id BIGSERIAL PRIMARY KEY`` (D-14).
    - ``status TEXT … CHECK (status IN ('running','success','failed'))``
      — **not** a PG ENUM, so no ``ALTER TYPE`` is needed in v0.6.0 (D-14).
    - ``watermark JSONB`` — nullable, always NULL in v0.5.0; reserved for
      incremental/CDC watermarks in v0.6.0 (OD-1/D-14).

    No user identifier is interpolated here — the DDL is a static
    constant, so no ``validate_identifiers`` call is required. The
    ``(sql, list)`` 2-tuple contract is kept uniform with all other
    builders.

    Returns
    -------
    tuple of (str, list)
        The ``ETL_INIT_PIPELINE_RUNS`` DDL string and an empty parameter
        list.
    """
    return queries.ETL_INIT_PIPELINE_RUNS, []


def _build_insert_sql(
    table: str,
    columns: list[str],
    rows: list[dict],
    schema: str = "public",
    on_conflict: str | None = None,
) -> tuple[str, list]:
    """Build a parameterized batch INSERT SQL statement.

    Pure builder — no ``self``, no I/O, no DB connection.  Mirrors the
    shape of :func:`build_truncate_sql`: validates identifiers first,
    then builds, and returns a ``(sql, params)`` 2-tuple.  User values
    travel only as ``%s`` placeholders appended to ``params`` — never
    f-string interpolated (T-18-02, SC-6).

    Parameters
    ----------
    table : str
        Target table name. Must be a valid SQL identifier.
    columns : list of str
        Column names. Each must be a valid SQL identifier.
    rows : list of dict
        Row dicts keyed by column name. Values are appended to ``params``
        in ``columns`` order via ``row.get(col)``.
    schema : str, optional
        Schema name, by default ``"public"``. Must be a valid SQL
        identifier.
    on_conflict : str, optional
        Raw ON CONFLICT clause body (e.g.
        ``"(id) DO UPDATE SET v = EXCLUDED.v"``), by default ``None``.
        When supplied the clause is appended as
        ``" ON CONFLICT {on_conflict}"`` after the VALUES list.  The
        caller is responsible for passing a pre-validated conflict
        clause (``_build_upsert_sql`` does this — T-18-01).

    Returns
    -------
    tuple of (str, list)
        SQL string of the form
        ``INSERT INTO {schema}.{table} ({cols}) VALUES (%s, …)[, …]``
        and a flat params list of all row values in column order.

    Raises
    ------
    InvalidIdentifier
        If ``table``, ``schema``, or any element of ``columns`` is not a
        valid SQL identifier (T-18-01, SC-6).
    """
    validate_identifiers(table, schema, *columns)

    cols_str = ", ".join(columns)
    conflict_clause = f" ON CONFLICT {on_conflict}" if on_conflict else ""

    placeholders: list[str] = []
    params: list = []
    for row in rows:
        row_placeholders = ", ".join(["%s"] * len(columns))
        placeholders.append(f"({row_placeholders})")
        params.extend(row.get(col) for col in columns)

    values_str = ", ".join(placeholders)
    sql = f"INSERT INTO {schema}.{table} ({cols_str}) VALUES {values_str}{conflict_clause}"
    return sql, params


def _build_upsert_sql(
    table: str,
    rows: list[dict],
    conflict_columns: list[str] | tuple[str, ...],
    update_columns: list[str] | None = None,
    schema: str = "public",
) -> tuple[str, list]:
    """Build a parameterized INSERT … ON CONFLICT … DO UPDATE SET SQL statement.

    Pure builder — delegates the INSERT body to :func:`_build_insert_sql`
    so that table/schema/column identifier validation is shared.  Validates
    ``conflict_columns`` and ``update_columns`` here before any f-string
    interpolation (T-18-01, SC-6).

    Parameters
    ----------
    table : str
        Target table name. Must be a valid SQL identifier.
    rows : list of dict
        Row dicts keyed by column name. Column order is taken from
        ``rows[0].keys()``.
    conflict_columns : list or tuple of str
        Columns that define uniqueness for the conflict target.  Each must
        be a valid SQL identifier.
    update_columns : list of str, optional
        Columns to update on conflict.  Defaults to all columns that are
        NOT in ``conflict_columns`` (same default as ``upsert_many``).
    schema : str, optional
        Schema name, by default ``"public"``.

    Returns
    -------
    tuple of (str, list)
        SQL string of the form
        ``INSERT INTO … VALUES … ON CONFLICT (cols) DO UPDATE SET col = EXCLUDED.col``
        and a flat params list.

    Raises
    ------
    InvalidIdentifier
        If any identifier in ``table``, ``schema``, ``conflict_columns``,
        ``update_columns``, or the column names derived from ``rows[0]``
        fails validation (T-18-01, SC-6).
    """
    columns = list(rows[0].keys())
    if update_columns is None:
        update_columns = [c for c in columns if c not in conflict_columns]

    validate_identifiers(*conflict_columns)
    validate_identifiers(*update_columns)

    conflict_str = ", ".join(conflict_columns)
    update_str = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_columns)
    on_conflict = f"({conflict_str}) DO UPDATE SET {update_str}"

    return _build_insert_sql(table, columns, rows, schema, on_conflict=on_conflict)


#: Reserved subquery alias for the SQL-string incremental-extract wrap (D-07).
#: Underscore-prefixed for collision safety; deterministic and greppable in logs.
_PYCOPG_INC_ALIAS = "_pycopg_inc"


def _build_incremental_extract_sql(
    source: str,
    column: str,
    schema: str = "public",
    watermark=None,
) -> tuple[str, list]:
    """Build the watermark-filtered incremental extract SQL.

    Pure builder — no ``self``, no I/O, no DB connection.  Dispatches on
    the source kind via :func:`_is_sql_source` (D-11): a SQL-string source
    is wrapped in a subquery aliased ``_pycopg_inc`` (D-06/D-07); a table
    source gets a ``WHERE`` clause appended (D-09).  The watermark value is
    ALWAYS emitted as a single ``%s`` placeholder appended to the params
    list — never f-string interpolated (D-10, T-26-01).  Identifiers
    (``column``, and ``source``/``schema`` for table sources) are validated
    before any interpolation (T-26-02).

    When ``watermark is None`` (first run or no prior watermark) a full,
    unfiltered SELECT is returned with an empty params list (D-12).  The
    boundary is exclusive (``>``), matching the REQUIREMENTS contract.

    Parameters
    ----------
    source : str
        Source table name or a SQL SELECT/WITH statement string. Classified
        via :func:`_is_sql_source`.
    column : str
        Watermark column name. Must be a valid SQL identifier; emitted bare
        after validation (D-10).
    schema : str, optional
        Schema for a table source, by default ``"public"``. Ignored for a
        SQL-string source. Must be a valid SQL identifier.
    watermark : optional
        High-water mark value, or ``None`` for a full unfiltered extract
        (D-12). When set it is the single ``%s`` parameter.

    Returns
    -------
    tuple of (str, list)
        The extract SQL string and a params list containing the watermark
        as its only element (or ``[]`` when ``watermark is None``).

    Raises
    ------
    InvalidIdentifier
        If ``column`` (always) or ``source``/``schema`` (table source) is
        not a valid SQL identifier (T-26-02).
    """
    validate_identifiers(column)
    if watermark is None:
        if _is_sql_source(source):
            return source, []
        validate_identifiers(source, schema)
        return f"SELECT * FROM {schema}.{source}", []
    if _is_sql_source(source):
        # Right-strip whitespace, a single trailing ';', then whitespace
        # again before wrapping (D-08 hygiene — no SQL parser).
        clean = source.rstrip().rstrip(";").rstrip()
        sql = f"SELECT * FROM ({clean}) {_PYCOPG_INC_ALIAS} WHERE {column} > %s"
        return sql, [watermark]
    validate_identifiers(source, schema)
    return f"SELECT * FROM {schema}.{source} WHERE {column} > %s", [watermark]


#: Watermark types that can be stored in the typed JSONB envelope (D-04).
_WATERMARK_SUPPORTED = "{datetime, int, str}"


def _encode_watermark(value) -> dict:
    """Encode a watermark scalar into a typed JSONB envelope (D-01).

    Pure builder — no ``self``, no I/O, no DB connection.  Returns a BARE
    ``dict`` of the form ``{"type": ..., "value": ...}`` (D-05); the
    ``psycopg.types.json.Jsonb`` adapter wrap is a Phase-27 write-site
    concern, not done here.  ``datetime`` is serialized via
    :meth:`datetime.isoformat` with NO UTC normalization, so the stored
    offset and microseconds are preserved verbatim (D-02).

    The supported allowlist is exactly ``{datetime, int, str}`` (D-04).
    ``bool`` is rejected *before* the ``int`` branch (it is an ``int``
    subclass — same trap guarded for ``extract_limit``).

    Parameters
    ----------
    value : datetime or int or str
        Watermark scalar to encode.

    Returns
    -------
    dict
        Typed envelope ``{"type": "datetime"|"int"|"str", "value": ...}``.

    Raises
    ------
    ETLError
        If ``value`` is not one of the supported types (e.g. ``bool``,
        ``float``, ``Decimal``); the message names the unsupported type and
        lists the supported set (D-04).
    """
    # bool is an int subclass — reject it before the int branch (D-04).
    if isinstance(value, bool):
        raise ETLError(
            f"unsupported watermark type {type(value).__name__!r}; "
            f"supported types are {_WATERMARK_SUPPORTED}"
        )
    if isinstance(value, datetime):
        return {"type": "datetime", "value": value.isoformat()}
    if isinstance(value, int):
        return {"type": "int", "value": value}
    if isinstance(value, str):
        return {"type": "str", "value": value}
    raise ETLError(
        f"unsupported watermark type {type(value).__name__!r}; "
        f"supported types are {_WATERMARK_SUPPORTED}"
    )


def _decode_watermark(envelope: dict):
    """Decode a typed JSONB envelope back to the original watermark scalar.

    Pure function — no ``self``, no I/O.  Mirrors the dict→typed
    reconstruction of :func:`_row_to_result`.  Reads the ``type`` tag and
    rebuilds the exact Python type written by :func:`_encode_watermark`;
    ``datetime`` is rebuilt via :meth:`datetime.fromisoformat`, preserving
    the offset and microseconds (D-02).

    Parameters
    ----------
    envelope : dict
        Typed envelope as returned by :func:`_encode_watermark` (the plain
        ``dict`` psycopg yields when reading a JSONB column).

    Returns
    -------
    datetime or int or str
        The reconstructed watermark scalar.
    """
    tag = envelope["type"]
    value = envelope["value"]
    if tag == "datetime":
        return datetime.fromisoformat(value)
    if tag == "int":
        return int(value)
    return str(value)


def _step_label(fn: object) -> str:
    """Return a human-readable label for a transform step function.

    Used by the ``run()`` transform chain to name the failing step in an
    :class:`~pycopg.exceptions.ETLTransformError` message (D-06).

    Returns ``fn.__name__`` for named functions.  Falls back to
    ``repr(fn)`` for lambdas (whose ``__name__`` is the string
    ``"<lambda>"``, which is truthy but not useful) and for
    ``functools.partial`` objects (which have no ``__name__`` attribute
    at all).

    Parameters
    ----------
    fn : callable
        The transform step whose label is needed.

    Returns
    -------
    str
        ``fn.__name__`` when it is a non-empty string other than
        ``"<lambda>"``; ``repr(fn)`` otherwise.
    """
    name = getattr(fn, "__name__", None)
    if name and name != "<lambda>":
        return name
    return repr(fn)


def _row_to_result(row: dict) -> RunResult:
    """Map a ``dict_row`` from ``pipeline_runs`` to a :class:`RunResult`.

    Pure function — no I/O, no ``self``.  Maps ``error_message -> error``
    and drops ``error_traceback`` (D-10).  Maps ``watermark`` ->
    ``watermark_recorded`` via a NULL guard: when the stored column is
    ``NULL`` sets ``watermark_recorded=None``; otherwise decodes via the
    frozen :func:`_decode_watermark` helper.  ``watermark_used`` is always
    ``None`` for stored rows — it is a per-run input that is never
    persisted (D-A1).

    Parameters
    ----------
    row : dict
        A row from ``pipeline_runs`` fetched with the ``dict_row`` factory.

    Returns
    -------
    RunResult
        Immutable snapshot of the run.
    """
    wm_recorded = (
        None if row["watermark"] is None else _decode_watermark(row["watermark"])
    )
    return RunResult(
        run_id=row["run_id"],
        pipeline_name=row["pipeline_name"],
        status=row["status"],
        rows_extracted=row["rows_extracted"],
        rows_loaded=row["rows_loaded"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        error=row["error_message"],
        watermark_used=None,
        watermark_recorded=wm_recorded,
    )


class ETLAccessor:
    """Sync ETL helper namespace exposed as ``db.etl``.

    Hosts the run-tracking I/O primitives: idempotent table creation
    (``init``), run-log insertion (``_start_run``), and run-log update
    (``_end_run``). All run-log writes use a fresh short-lived autocommit
    connection per write — independent of any load transaction — so a
    failed run row commits even when the load transaction rolls back
    (D-04/D-05, ETL-08/ETL-09).

    No PostGIS extension guard and no ``schema`` argument (D-08).  The
    ``pipeline_runs`` table is unqualified and resolves via the
    connection's ``search_path``.

    Parameters
    ----------
    db : Database
        Parent database instance.
    """

    def __init__(self, db: Database) -> None:
        """Store the parent database reference (D-02).

        Parameters
        ----------
        db : Database
            Parent database instance. Stored as ``self._db``; no
            extension check is performed (ETL run-tracking is core, not
            an extension — D-08).
        """
        self._db = db

    def init(self) -> None:
        """Create the ``pipeline_runs`` table if it does not exist.

        Executes the ``ETL_INIT_PIPELINE_RUNS`` DDL on a **dedicated**
        autocommit connection opened directly via
        ``db.connect(autocommit=True)`` (D-04).  This bypasses the
        session-aware ``Database.cursor()`` entirely — the DDL commits on
        its own connection whether or not a ``db.session()`` is active.
        Safe to call repeatedly — ``CREATE TABLE IF NOT EXISTS`` makes it
        idempotent (D-10/D-15, ETL-14).

        Returns
        -------
        None
        """
        with self._db.connect(autocommit=True) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(queries.ETL_INIT_PIPELINE_RUNS)

    def _start_run(self, name: str) -> int:
        """Insert a ``'running'`` row into ``pipeline_runs`` and return its id.

        Opens a **dedicated** autocommit connection directly via
        ``db.connect(autocommit=True)`` (D-04), bypassing the
        session-aware ``Database.cursor()``.  The INSERT commits on its own
        connection whether or not a ``db.session()`` is active, so the
        run-log write is independent of the load transaction (D-05).

        Parameters
        ----------
        name : str
            Pipeline name stored as ``pipeline_name`` in the run row.

        Returns
        -------
        int
            The ``run_id`` of the newly inserted row (from
            ``RETURNING run_id``).
        """
        with self._db.connect(autocommit=True) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    queries.ETL_INSERT_RUN,
                    [name, "running", datetime.now(UTC)],
                )
                return cur.fetchone()["run_id"]

    def _end_run(
        self,
        run_id: int,
        status: str,
        rows_extracted: int,
        rows_loaded: int,
        error_message: str | None = None,
        error_traceback: str | None = None,
        watermark: dict | None = None,
    ) -> None:
        """Update a ``pipeline_runs`` row with final status and metrics.

        Opens a **dedicated** autocommit connection directly via
        ``db.connect(autocommit=True)`` (D-04), bypassing the
        session-aware ``Database.cursor()``.  The UPDATE commits on its
        own connection whether or not a ``db.session()`` is active,
        ensuring a ``status='failed'`` row is committed even when the
        load transaction rolled back (D-05/ETL-08/ETL-09).

        Use the literal ``'failed'`` status string for failures — the
        CHECK constraint only accepts ``'running'``, ``'success'``, and
        ``'failed'`` (D-07).

        When *watermark* is not ``None`` the dedicated
        :data:`~pycopg.queries.ETL_UPDATE_RUN_WATERMARK` constant is
        used and the already-encoded envelope dict is bound via
        :class:`psycopg.types.json.Jsonb` at the write site (D-05).
        The failed and empty-batch callers pass no *watermark*, so the
        ``watermark`` column stays ``NULL`` (no-advance-on-failure /
        empty-batch-preserves invariants — ETL-INC-05/06).

        Parameters
        ----------
        run_id : int
            The ``run_id`` returned by :meth:`_start_run`.
        status : str
            Final run status: ``'success'`` or ``'failed'``.
        rows_extracted : int
            Number of rows read from the source.
        rows_loaded : int
            Number of rows written to the target.
        error_message : str or None, optional
            Short error description, by default ``None``.
        error_traceback : str or None, optional
            Full traceback string (e.g. from ``traceback.format_exc()``),
            by default ``None``.
        watermark : dict or None, optional
            Already-encoded watermark envelope dict (output of
            :func:`_encode_watermark`), by default ``None``.  When
            provided the ``watermark`` JSONB column is updated via
            :data:`~pycopg.queries.ETL_UPDATE_RUN_WATERMARK`; when
            ``None`` the existing :data:`~pycopg.queries.ETL_UPDATE_RUN`
            is used and the column stays ``NULL`` (ETL-INC-06).

        Returns
        -------
        None
        """
        with self._db.connect(autocommit=True) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if watermark is None:
                    cur.execute(
                        queries.ETL_UPDATE_RUN,
                        [
                            status,
                            datetime.now(UTC),
                            rows_extracted,
                            rows_loaded,
                            error_message,
                            error_traceback,
                            run_id,
                        ],
                    )
                else:
                    cur.execute(
                        queries.ETL_UPDATE_RUN_WATERMARK,
                        [
                            status,
                            datetime.now(UTC),
                            rows_extracted,
                            rows_loaded,
                            error_message,
                            error_traceback,
                            Jsonb(watermark),
                            run_id,
                        ],
                    )

    def _fetch_run_result(self, run_id: int) -> RunResult:
        """Re-SELECT the ``pipeline_runs`` row for *run_id* and return a ``RunResult``.

        Uses a dedicated autocommit connection with the ``dict_row`` factory
        so the returned snapshot reflects what the DB actually stored (D-11).

        Parameters
        ----------
        run_id : int
            The ``run_id`` of the row to fetch.

        Returns
        -------
        RunResult
            Immutable snapshot of the completed run.
        """
        with self._db.connect(autocommit=True) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(queries.ETL_GET_RUN, [run_id])
                row = cur.fetchone()
        return _row_to_result(row)

    def history(self, name: str, limit: int = 100) -> list[RunResult]:
        """Return the run history for a pipeline, newest-first.

        Reads ``pipeline_runs`` via :data:`~pycopg.queries.ETL_LIST_RUNS`
        on a dedicated autocommit connection (Pitfall 6 — read-only, not
        inside a session transaction).  Results are ordered by
        ``started_at DESC`` (newest first) and capped at *limit* rows
        (D-06/ETL-11).

        Parameters
        ----------
        name : str
            Pipeline name to query (bound as a ``%s`` parameter — no
            identifier interpolation).
        limit : int, optional
            Maximum number of rows to return, by default 100.

        Returns
        -------
        list[RunResult]
            Immutable snapshots of the matching runs, newest-first.
            Empty list when no runs exist for *name*.
        """
        with self._db.connect(autocommit=True) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(queries.ETL_LIST_RUNS, [name, limit])
                rows = cur.fetchall()
        return [_row_to_result(row) for row in rows]

    def last_run(self, name: str) -> RunResult | None:
        """Return the most recent run for a pipeline, or ``None``.

        Reads one row from ``pipeline_runs`` via
        :data:`~pycopg.queries.ETL_GET_LAST_RUN` on a dedicated autocommit
        connection (Pitfall 6).  Returns ``None`` when no runs exist for
        *name* (SC-3/D-07/ETL-17).

        Parameters
        ----------
        name : str
            Pipeline name to query (bound as a ``%s`` parameter — no
            identifier interpolation).

        Returns
        -------
        RunResult or None
            Immutable snapshot of the most recent run, or ``None`` when no
            runs exist for *name*.
        """
        with self._db.connect(autocommit=True) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(queries.ETL_GET_LAST_RUN, [name])
                row = cur.fetchone()
        return _row_to_result(row) if row is not None else None

    def _read_watermark(self, name: str) -> datetime | int | str | None:
        """Return the last successful, non-NULL watermark for a pipeline, or None.

        Reads one row from ``pipeline_runs`` via
        :data:`~pycopg.queries.ETL_GET_LAST_WATERMARK` on a dedicated
        autocommit connection with the ``dict_row`` factory (mirrors the
        :meth:`last_run` autocommit pattern).  The ``status = 'success'
        AND watermark IS NOT NULL`` predicate (D-03) means failed runs and
        empty-batch successes are automatically skipped — the prior
        successful watermark is returned with no copy-forward write.

        The ``watermark`` JSONB column yields a plain Python ``dict`` which
        is passed straight to the frozen :func:`_decode_watermark` helper
        to reconstruct the typed scalar.

        **Phase 27 note:** this method exists and is tested here but is NOT
        yet applied as an extract filter — the ``WHERE col > last_watermark``
        wiring is Phase 28 (ETL-INC-03).

        Parameters
        ----------
        name : str
            Pipeline name to query (bound as a ``%s`` parameter — no
            identifier interpolation).

        Returns
        -------
        datetime or int or str or None
            The decoded last successful, non-NULL watermark scalar, or
            ``None`` when no qualifying success row exists (first run or
            never-succeeded-with-watermark — D-04).
        """
        with self._db.connect(autocommit=True) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(queries.ETL_GET_LAST_WATERMARK, [name])
                row = cur.fetchone()
        if row is None or row["watermark"] is None:
            return None
        return _decode_watermark(row["watermark"])

    def _do_extract(
        self,
        pipeline: Pipeline,
        watermark,
    ) -> pd.DataFrame:
        """Run the watermark-filtered extract step for *pipeline*.

        Single shared extract path used by both the ``dry_run`` fork and the
        real run path — prevents the two forks from drifting in their filter
        logic (D-A2a).

        When ``pipeline.incremental_column`` is set, reads the watermark
        floor and applies ``WHERE col > :wm`` via
        :func:`_build_incremental_extract_sql`; the watermark value is
        always a named bound parameter (never f-string interpolated —
        SC-1 / T-28-01).  When ``watermark is None`` the builder returns a
        full unfiltered SELECT (first run, D-12).

        When ``pipeline.incremental_column`` is ``None``, falls back to the
        existing non-incremental extract behaviour.

        ``extract_limit`` is applied as a LIMIT subquery wrapping the
        filtered SQL so the watermark bind remains a named parameter.

        Parameters
        ----------
        pipeline : Pipeline
            The pipeline descriptor.
        watermark : datetime or int or str or None
            The filter floor returned by :meth:`_read_watermark`, or
            ``None`` for a non-incremental pipeline or first run.

        Returns
        -------
        pd.DataFrame
            The extracted batch.
        """
        if pipeline.incremental_column is not None:
            # Incremental path: build filtered SQL with bound watermark param.
            # The builder emits %s positional; reconcile to :wm named bind
            # for to_dataframe (which uses SQLAlchemy text() + named params).
            sql, _params = _build_incremental_extract_sql(
                pipeline.source,
                pipeline.incremental_column,
                pipeline.schema,
                watermark=watermark,
            )
            if _params:
                # Replace the single positional %s with a named :wm bind
                sql = sql.replace("%s", ":wm", 1)
                params: dict = {"wm": _params[0]}
            else:
                params = {}
            if pipeline.extract_limit is not None:
                # Wrap as subquery so LIMIT applies to the filtered result
                # and the :wm bind is still valid in the inner query
                sql = f"SELECT * FROM ({sql}) _etl_lim LIMIT :lim"
                params["lim"] = pipeline.extract_limit
            return self._db.to_dataframe(sql=sql, params=params or None)

        # Non-incremental path — unchanged from original extract block
        if _is_sql_source(pipeline.source):
            if pipeline.extract_limit is not None:
                return self._db.to_dataframe(
                    sql=(
                        f"SELECT * FROM ({pipeline.source}) AS _etl_sub" f" LIMIT :lim"
                    ),
                    params={"lim": pipeline.extract_limit},
                )
            return self._db.to_dataframe(sql=pipeline.source)
        else:
            validate_identifiers(pipeline.source, pipeline.schema)
            if pipeline.extract_limit is not None:
                return self._db.to_dataframe(
                    sql=(
                        f"SELECT * FROM {pipeline.schema}.{pipeline.source}"
                        f" LIMIT :lim"
                    ),
                    params={"lim": pipeline.extract_limit},
                )
            return self._db.to_dataframe(
                table=pipeline.source,
                schema=pipeline.schema,
            )

    def run(self, pipeline: Pipeline, dry_run: bool = False) -> RunResult:
        """Execute a full extract → transform → load pipeline run.

        Auto-creates ``pipeline_runs`` if absent, inserts a ``'running'``
        row, executes the pipeline, and records the final status.

        When *dry_run* is ``True`` the extract and transform steps are
        executed but no load is performed and no ``pipeline_runs`` row is
        written.  The returned :class:`RunResult` has
        ``status='dry_run'``, ``rows_loaded=0``, and ``run_id=None``
        (D-08/D-09/ETL-15).

        The run-log writes (``init``/``_start_run``/``_end_run``) stay on
        their own dedicated autocommit connections — independent of the load
        transaction — so a ``'failed'`` row is committed even when the load
        transaction rolls back (ETL-09 isolation invariant).

        The load executes the SQL produced by the Plan 01 builders directly
        on the connection yielded by ``db.transaction()`` (opened inside an
        internal ``db.session()``), making the replace TRUNCATE+INSERT
        atomic (SC-3 / RESEARCH Q1 corrected seam).

        **Extract:** delegates to :meth:`~pycopg.database.Database.to_dataframe`
        for both SQL and table sources.  When ``pipeline.extract_limit`` is
        set, the LIMIT value is sent as a bound ``:lim`` parameter — never
        f-string-interpolated (T-18-03).

        **Transform:** ``transform=None`` is a no-op; a single callable is
        applied once; a list is applied in sequence, each step receiving the
        prior step's DataFrame.  A failing step raises
        :exc:`~pycopg.exceptions.ETLTransformError` whose message names the
        step by its **1-based** index and label (``fn.__name__`` for named
        functions, ``repr(fn)`` for lambdas/``functools.partial``).

        **NaN/NaT coercion:** all ``NaN``/``NaT`` cells in the
        post-transform DataFrame are replaced with ``None`` (SQL ``NULL``)
        before building the INSERT params.  The conversion uses
        ``df.astype(object).where(pd.notnull(df), None)`` (RESEARCH Q2).
        Timezone-localization of naive ``datetime64`` columns is **not**
        performed — that is the caller's responsibility, matching the
        existing :meth:`~pycopg.database.Database.from_dataframe` behaviour.
        This conversion only covers scalar-valued columns; list/array cells
        are out of scope for v0.5.0.

        Parameters
        ----------
        pipeline : Pipeline
            Fully specified pipeline descriptor.
        dry_run : bool, optional
            When ``True``, run extract + transform only — skip the load,
            write no ``pipeline_runs`` row, and return a transient
            :class:`RunResult` with ``status='dry_run'`` and
            ``run_id=None``.  By default ``False``.

        Returns
        -------
        RunResult
            Immutable snapshot of the completed (or dry-run) run.

        Raises
        ------
        ETLTargetNotFoundError
            If ``load_mode`` is ``'append'`` or ``'upsert'`` and the target
            table does not exist (D-03).
        ETLTransformError
            If a transform step raises — the message includes the 1-based
            step index and the step label (D-06 / ETL-16).
        Exception
            Any other exception from the extract, existence-check, or load
            steps is re-raised after the failed run row is committed
            (OD-2).
        """
        name = pipeline.name

        # ------------------------------------------------------------------
        # DRY-RUN EARLY FORK (D-08/D-09/ETL-15)
        # Forks before init/start_run — writes no pipeline_runs row.
        # ------------------------------------------------------------------
        if dry_run:
            started_at = datetime.now(UTC)
            rows_extracted = 0

            # Read prior watermark (None on first run or non-incremental) — D-A2
            dry_wm = (
                self._read_watermark(name)
                if pipeline.incremental_column is not None
                else None
            )

            # Shared filtered extract (D-A2a) — same path as real run
            df = self._do_extract(pipeline, dry_wm)
            rows_extracted = len(df)

            # Capture would-be watermark from RAW filtered batch (D-A2)
            dry_raw_watermark = None
            dry_col = pipeline.incremental_column
            if dry_col is not None:
                if dry_col not in df.columns:
                    raise ETLError(
                        f"incremental_column {dry_col!r} not found in extracted batch "
                        f"columns {list(df.columns)} (ETL-INC-04)"
                    )
                if len(df):
                    m = df[dry_col].max()
                    if pd.isna(m):  # must precede is_float — NaN is a float (WR-02)
                        dry_raw_watermark = None
                    elif isinstance(m, pd.Timestamp):
                        dry_raw_watermark = m.to_pydatetime()
                    elif isinstance(m, str):
                        dry_raw_watermark = str(m)
                    elif pd.api.types.is_float(m):
                        raise ETLError(
                            f"incremental_column {dry_col!r} has float dtype; float "
                            f"watermarks are not supported (cast to INTEGER or "
                            f"TIMESTAMP). Supported types are {_WATERMARK_SUPPORTED}"
                        )
                    else:
                        dry_raw_watermark = int(m)

            # Transform chain (same as normal path)
            transform = pipeline.transform
            if transform is None:
                steps: list = []
            elif callable(transform):
                steps = [transform]
            else:
                steps = list(transform)

            for i, step in enumerate(steps, start=1):
                try:
                    df = step(df)
                except Exception as exc:
                    raise ETLTransformError(
                        f"transform step {i} ('{_step_label(step)}')"
                        f" raised {type(exc).__name__}: {exc}"
                    ) from exc

            rows_extracted = len(df)
            finished_at = datetime.now(UTC)
            return RunResult(
                run_id=None,
                pipeline_name=name,
                status="dry_run",
                rows_extracted=rows_extracted,
                rows_loaded=0,
                started_at=started_at,
                finished_at=finished_at,
                error=None,
                watermark_used=dry_wm,
                watermark_recorded=dry_raw_watermark,
            )

        self.init()
        run_id = self._start_run(name)
        rows_extracted = 0
        rows_loaded = 0

        # Read prior watermark before extract (None on first run or non-incremental)
        wm = (
            self._read_watermark(name)
            if pipeline.incremental_column is not None
            else None
        )

        try:
            # ------------------------------------------------------------------
            # 1. EXTRACT (shared filtered path — D-A2a)
            # ------------------------------------------------------------------
            df = self._do_extract(pipeline, wm)

            rows_extracted = len(df)

            # ------------------------------------------------------------------
            # 1b. INCREMENTAL WATERMARK CAPTURE (D-02 / D-06 / D-07 / ETL-INC-02)
            # Capture max(col) from the RAW batch BEFORE the transform chain
            # (D-02: transforms may rename/drop the column).  Only when
            # pipeline.incremental_column is set.  Coerce pandas/numpy scalars
            # to plain Python types so _encode_watermark's strict allowlist is
            # satisfied (D-07 resolved by call-site coercion — do NOT reopen
            # _encode_watermark).
            # ------------------------------------------------------------------
            raw_watermark = None
            col = pipeline.incremental_column
            if col is not None:
                if col not in df.columns:
                    raise ETLError(
                        f"incremental_column {col!r} not found in extracted batch "
                        f"columns {list(df.columns)} (ETL-INC-04)"
                    )  # D-06 — clear ETLError, not a bare KeyError
                if len(df):  # guard: max() on empty df is NaN
                    m = df[col].max()
                    if pd.isna(m):
                        # All values NULL (NaN/NaT) — record no watermark for
                        # this run, same as the empty-batch path; the prior
                        # successful watermark is preserved.  Must precede the
                        # is_float branch below: NaN is itself a float.
                        raw_watermark = None
                    elif isinstance(m, pd.Timestamp):
                        raw_watermark = (
                            m.to_pydatetime()
                        )  # plain datetime, offset preserved
                    elif isinstance(m, str):
                        raw_watermark = str(m)  # normalize numpy.str_ → str
                    elif pd.api.types.is_float(m):
                        # float/Decimal columns have no defined watermark
                        # semantics — int() would silently truncate (99.99 → 99)
                        # and regress the watermark.  Fail loud (D-06 contract).
                        raise ETLError(
                            f"incremental_column {col!r} has float dtype; float "
                            f"watermarks are not supported (cast to INTEGER or "
                            f"TIMESTAMP). Supported types are {_WATERMARK_SUPPORTED}"
                        )
                    else:
                        raw_watermark = int(m)  # numpy.int64 → plain int

            # ------------------------------------------------------------------
            # 2. TRANSFORM CHAIN (D-05 / D-06 / ETL-16)
            # ------------------------------------------------------------------
            transform = pipeline.transform
            if transform is None:
                steps: list = []
            elif callable(transform):
                steps = [transform]
            else:
                steps = list(transform)

            for i, step in enumerate(steps, start=1):
                try:
                    df = step(df)
                except Exception as exc:
                    raise ETLTransformError(
                        f"transform step {i} ('{_step_label(step)}')"
                        f" raised {type(exc).__name__}: {exc}"
                    ) from exc

            # ------------------------------------------------------------------
            # 3. ROWS: NaN/NaT → None (RESEARCH Q2 / D-07)
            # ------------------------------------------------------------------
            rows = (
                df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")
            )

            # No rows to load (empty extract, or transforms dropped every row):
            # record success with 0 rows_loaded and NO watermark — even if a
            # raw_watermark was captured above, a no-load run must not advance
            # the watermark.  The prior successful watermark is preserved by
            # ETL_GET_LAST_WATERMARK's `watermark IS NOT NULL` predicate.
            if not rows:
                self._end_run(run_id, "success", rows_extracted, 0)
                return self._fetch_run_result(run_id)

            columns = list(rows[0].keys())

            # ------------------------------------------------------------------
            # 4. EXISTENCE CHECK (D-03)
            # ------------------------------------------------------------------
            exists = self._db.schema.table_exists(pipeline.target, pipeline.schema)

            if pipeline.load_mode in ("append", "upsert") and not exists:
                raise ETLTargetNotFoundError(
                    f"{pipeline.load_mode} target"
                    f" {pipeline.schema}.{pipeline.target} does not exist"
                )

            if pipeline.load_mode == "replace" and not exists:
                # Create empty typed table before the load txn (D-03 / D-03a)
                self._db.from_dataframe(
                    df.head(0),
                    pipeline.target,
                    pipeline.schema,
                    if_exists="replace",
                )

            # ------------------------------------------------------------------
            # 5. BUILD LOAD SQL (Plan 01 pure builders — never the public batch methods)
            # ------------------------------------------------------------------
            if pipeline.load_mode == "append":
                insert_sql, insert_params = _build_insert_sql(
                    pipeline.target, columns, rows, pipeline.schema
                )
            elif pipeline.load_mode == "upsert":
                insert_sql, insert_params = _build_upsert_sql(
                    pipeline.target,
                    rows,
                    list(pipeline.conflict_columns),
                    schema=pipeline.schema,
                )
            else:  # replace
                truncate_sql, _ = build_truncate_sql(pipeline.target, pipeline.schema)
                insert_sql, insert_params = _build_insert_sql(
                    pipeline.target, columns, rows, pipeline.schema
                )

            # ------------------------------------------------------------------
            # 6. ATOMIC LOAD — the seam (RESEARCH Q1 / SC-3)
            #    Execute (sql, params) directly on the txn-yielded conn.
            #    Never call the public batch-write methods inside this block
            #    (those acquire self.cursor() which commits at exit — crashes
            #    or breaks atomicity inside an explicit transaction).
            # ------------------------------------------------------------------
            with self._db.session():
                with self._db.transaction() as conn:
                    with conn.cursor() as cur:
                        if pipeline.load_mode == "replace":
                            cur.execute(truncate_sql)
                        cur.execute(insert_sql, insert_params)
                        rows_loaded += cur.rowcount

        except Exception as exc:
            self._end_run(
                run_id,
                "failed",
                rows_extracted,
                0,
                error_message=str(exc),
                error_traceback=traceback.format_exc(),
            )
            raise

        wm_env = _encode_watermark(raw_watermark) if raw_watermark is not None else None
        self._end_run(run_id, "success", rows_extracted, rows_loaded, watermark=wm_env)
        # Fetch the stored result (watermark_recorded comes via _row_to_result),
        # then inject watermark_used (per-run input, never stored — D-A1).
        result = self._fetch_run_result(run_id)
        if wm is not None or pipeline.incremental_column is not None:
            result = dc_replace(result, watermark_used=wm)
        return result


class AsyncETLAccessor:
    """Async ETL helper namespace exposed as ``async_db.etl``.

    Async mirror of :class:`ETLAccessor` — every method is ``async def``
    and every database call uses ``await``.  All run-log writes
    (``init``, ``_start_run``, ``_end_run``, ``_fetch_run_result``) use a
    fresh short-lived **autocommit** connection per write via
    ``async with self._db.connect(autocommit=True)``.  This isolates the
    run-log from any load transaction so a ``'failed'`` row is committed
    even when the load transaction rolls back (D-04/D-05, ETL-08/ETL-09).

    Transform steps are dispatched via :func:`asyncio.to_thread` so that
    slow sync callables do not block the event loop (SC-2).

    No PostGIS extension guard and no ``schema`` argument (D-08).  The
    ``pipeline_runs`` table resolves via the connection's ``search_path``.

    Parameters
    ----------
    db : AsyncDatabase
        Parent async database instance.
    """

    def __init__(self, db: AsyncDatabase) -> None:
        """Store the parent async database reference (D-02).

        Parameters
        ----------
        db : AsyncDatabase
            Parent async database instance.  Stored as ``self._db``; no
            extension check is performed (ETL run-tracking is core, not an
            extension — D-08).
        """
        self._db = db

    async def init(self) -> None:
        """Create the ``pipeline_runs`` table if it does not exist.

        Executes the ``ETL_INIT_PIPELINE_RUNS`` DDL on a **dedicated**
        autocommit connection opened via
        ``async with self._db.connect(autocommit=True)`` (D-04).  Safe to
        call repeatedly — ``CREATE TABLE IF NOT EXISTS`` makes it idempotent
        (D-10/D-15, ETL-14).

        Returns
        -------
        None
        """
        async with self._db.connect(autocommit=True) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(queries.ETL_INIT_PIPELINE_RUNS)

    async def _start_run(self, name: str) -> int:
        """Insert a ``'running'`` row into ``pipeline_runs`` and return its id.

        Opens a **dedicated** autocommit connection via
        ``async with self._db.connect(autocommit=True)`` (D-04).  The
        INSERT commits on its own connection whether or not a session or
        load transaction is active (D-05).

        Parameters
        ----------
        name : str
            Pipeline name stored as ``pipeline_name`` in the run row.

        Returns
        -------
        int
            The ``run_id`` of the newly inserted row.
        """
        async with self._db.connect(autocommit=True) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    queries.ETL_INSERT_RUN,
                    [name, "running", datetime.now(UTC)],
                )
                return (await cur.fetchone())["run_id"]

    async def _end_run(
        self,
        run_id: int,
        status: str,
        rows_extracted: int,
        rows_loaded: int,
        error_message: str | None = None,
        error_traceback: str | None = None,
    ) -> None:
        """Update a ``pipeline_runs`` row with final status and metrics.

        Opens a **dedicated** autocommit connection via
        ``async with self._db.connect(autocommit=True)`` (D-04), ensuring
        the UPDATE commits even when the load transaction rolled back
        (D-05/ETL-08/ETL-09).

        Parameters
        ----------
        run_id : int
            The ``run_id`` returned by :meth:`_start_run`.
        status : str
            Final run status: ``'success'`` or ``'failed'``.
        rows_extracted : int
            Number of rows read from the source.
        rows_loaded : int
            Number of rows written to the target.
        error_message : str or None, optional
            Short error description, by default ``None``.
        error_traceback : str or None, optional
            Full traceback string, by default ``None``.

        Returns
        -------
        None
        """
        async with self._db.connect(autocommit=True) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    queries.ETL_UPDATE_RUN,
                    [
                        status,
                        datetime.now(UTC),
                        rows_extracted,
                        rows_loaded,
                        error_message,
                        error_traceback,
                        run_id,
                    ],
                )

    async def _fetch_run_result(self, run_id: int) -> RunResult:
        """Re-SELECT the ``pipeline_runs`` row for *run_id* and return a ``RunResult``.

        Uses a dedicated autocommit connection with the ``dict_row`` factory
        so the returned snapshot reflects what the DB actually stored (D-11).

        Parameters
        ----------
        run_id : int
            The ``run_id`` of the row to fetch.

        Returns
        -------
        RunResult
            Immutable snapshot of the completed run.
        """
        async with self._db.connect(autocommit=True) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(queries.ETL_GET_RUN, [run_id])
                row = await cur.fetchone()
        return _row_to_result(row)

    async def history(self, name: str, limit: int = 100) -> list[RunResult]:
        """Return the run history for a pipeline, newest-first.

        Reads ``pipeline_runs`` via :data:`~pycopg.queries.ETL_LIST_RUNS`
        on a dedicated autocommit connection.  Results are ordered by
        ``started_at DESC`` (newest first) and capped at *limit* rows
        (D-06/ETL-11).

        Parameters
        ----------
        name : str
            Pipeline name to query.
        limit : int, optional
            Maximum number of rows to return, by default 100.

        Returns
        -------
        list[RunResult]
            Immutable snapshots of the matching runs, newest-first.
            Empty list when no runs exist for *name*.
        """
        async with self._db.connect(autocommit=True) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(queries.ETL_LIST_RUNS, [name, limit])
                rows = await cur.fetchall()
        return [_row_to_result(row) for row in rows]

    async def last_run(self, name: str) -> RunResult | None:
        """Return the most recent run for a pipeline, or ``None``.

        Reads one row from ``pipeline_runs`` via
        :data:`~pycopg.queries.ETL_GET_LAST_RUN` on a dedicated autocommit
        connection.  Returns ``None`` when no runs exist for *name*
        (SC-3/D-07/ETL-17).

        Parameters
        ----------
        name : str
            Pipeline name to query.

        Returns
        -------
        RunResult or None
            Immutable snapshot of the most recent run, or ``None`` when no
            runs exist for *name*.
        """
        async with self._db.connect(autocommit=True) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(queries.ETL_GET_LAST_RUN, [name])
                row = await cur.fetchone()
        return _row_to_result(row) if row is not None else None

    async def run(self, pipeline: Pipeline, dry_run: bool = False) -> RunResult:
        """Execute a full async extract → transform → load pipeline run.

        Async mirror of :meth:`ETLAccessor.run`.  All DB calls use
        ``await``; transform steps are dispatched via
        :func:`asyncio.to_thread` so slow sync callables do not block the
        event loop (SC-2).

        Auto-creates ``pipeline_runs`` if absent, inserts a ``'running'``
        row, executes the pipeline, and records the final status.

        When *dry_run* is ``True`` the extract and transform steps are
        executed but no load is performed and no ``pipeline_runs`` row is
        written.  The returned :class:`RunResult` has
        ``status='dry_run'``, ``rows_loaded=0``, and ``run_id=None``
        (D-08/D-09/ETL-15).

        **Extract:** delegates to
        :meth:`~pycopg.async_database.AsyncDatabase.to_dataframe`.

        **Transform:** ``transform=None`` is a no-op; a single callable is
        applied once; a list is applied in sequence.  Each step is
        dispatched via ``await asyncio.to_thread(step, df)`` (SC-2, Pitfall
        2 — pass callable + arg separately, not ``step(df)``).  A failing
        step raises :exc:`~pycopg.exceptions.ETLTransformError`.

        **NaN/NaT coercion:** all ``NaN``/``NaT`` cells are replaced with
        ``None`` before building the INSERT params (RESEARCH Q2).

        Parameters
        ----------
        pipeline : Pipeline
            Fully specified pipeline descriptor.
        dry_run : bool, optional
            When ``True``, run extract + transform only — skip the load,
            write no ``pipeline_runs`` row, and return a transient
            :class:`RunResult` with ``status='dry_run'`` and
            ``run_id=None``.  By default ``False``.

        Returns
        -------
        RunResult
            Immutable snapshot of the completed (or dry-run) run.

        Raises
        ------
        ETLTargetNotFoundError
            If ``load_mode`` is ``'append'`` or ``'upsert'`` and the target
            table does not exist (D-03).
        ETLTransformError
            If a transform step raises — the message includes the 1-based
            step index and the step label (D-06 / ETL-16).
        Exception
            Any other exception from the extract, existence-check, or load
            steps is re-raised after the failed run row is committed (OD-2).
        """
        name = pipeline.name

        # ------------------------------------------------------------------
        # DRY-RUN EARLY FORK (D-08/D-09/ETL-15)
        # Forks before init/start_run — writes no pipeline_runs row.
        # ------------------------------------------------------------------
        if dry_run:
            started_at = datetime.now(UTC)
            rows_extracted = 0

            # Extract (same as normal path)
            if _is_sql_source(pipeline.source):
                if pipeline.extract_limit is not None:
                    df = await self._db.to_dataframe(
                        sql=(
                            f"SELECT * FROM ({pipeline.source}) AS _etl_sub"
                            f" LIMIT :lim"
                        ),
                        params={"lim": pipeline.extract_limit},
                    )
                else:
                    df = await self._db.to_dataframe(sql=pipeline.source)
            else:
                validate_identifiers(pipeline.source, pipeline.schema)
                if pipeline.extract_limit is not None:
                    df = await self._db.to_dataframe(
                        sql=(
                            f"SELECT * FROM {pipeline.schema}.{pipeline.source}"
                            f" LIMIT :lim"
                        ),
                        params={"lim": pipeline.extract_limit},
                    )
                else:
                    df = await self._db.to_dataframe(
                        table=pipeline.source,
                        schema=pipeline.schema,
                    )

            rows_extracted = len(df)

            # Transform chain (same as normal path, but dispatched via to_thread — SC-2)
            transform = pipeline.transform
            if transform is None:
                steps: list = []
            elif callable(transform):
                steps = [transform]
            else:
                steps = list(transform)

            for i, step in enumerate(steps, start=1):
                try:
                    df = await asyncio.to_thread(step, df)
                except Exception as exc:
                    raise ETLTransformError(
                        f"transform step {i} ('{_step_label(step)}')"
                        f" raised {type(exc).__name__}: {exc}"
                    ) from exc

            rows_extracted = len(df)
            finished_at = datetime.now(UTC)
            return RunResult(
                run_id=None,
                pipeline_name=name,
                status="dry_run",
                rows_extracted=rows_extracted,
                rows_loaded=0,
                started_at=started_at,
                finished_at=finished_at,
                error=None,
            )

        await self.init()
        run_id = await self._start_run(name)
        rows_extracted = 0
        rows_loaded = 0

        try:
            # ------------------------------------------------------------------
            # 1. EXTRACT
            # ------------------------------------------------------------------
            if _is_sql_source(pipeline.source):
                if pipeline.extract_limit is not None:
                    df = await self._db.to_dataframe(
                        sql=(
                            f"SELECT * FROM ({pipeline.source}) AS _etl_sub"
                            f" LIMIT :lim"
                        ),
                        params={"lim": pipeline.extract_limit},
                    )
                else:
                    df = await self._db.to_dataframe(sql=pipeline.source)
            else:
                # table source — validate identifiers before interpolation (T-18-04)
                validate_identifiers(pipeline.source, pipeline.schema)
                if pipeline.extract_limit is not None:
                    df = await self._db.to_dataframe(
                        sql=(
                            f"SELECT * FROM {pipeline.schema}.{pipeline.source}"
                            f" LIMIT :lim"
                        ),
                        params={"lim": pipeline.extract_limit},
                    )
                else:
                    df = await self._db.to_dataframe(
                        table=pipeline.source,
                        schema=pipeline.schema,
                    )

            rows_extracted = len(df)

            # ------------------------------------------------------------------
            # 2. TRANSFORM CHAIN (D-05 / D-06 / ETL-16)
            #    Each step dispatched via asyncio.to_thread (SC-2).
            # ------------------------------------------------------------------
            transform = pipeline.transform
            if transform is None:
                steps: list = []
            elif callable(transform):
                steps = [transform]
            else:
                steps = list(transform)

            for i, step in enumerate(steps, start=1):
                try:
                    df = await asyncio.to_thread(step, df)
                except Exception as exc:
                    raise ETLTransformError(
                        f"transform step {i} ('{_step_label(step)}')"
                        f" raised {type(exc).__name__}: {exc}"
                    ) from exc

            # ------------------------------------------------------------------
            # 3. ROWS: NaN/NaT → None (RESEARCH Q2 / D-07)
            # ------------------------------------------------------------------
            rows = (
                df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")
            )

            # Empty DataFrame: no load needed; record success with 0 rows_loaded
            if not rows:
                await self._end_run(run_id, "success", rows_extracted, 0)
                return await self._fetch_run_result(run_id)

            columns = list(rows[0].keys())

            # ------------------------------------------------------------------
            # 4. EXISTENCE CHECK (D-03)
            # ------------------------------------------------------------------
            exists = await self._db.schema.table_exists(
                pipeline.target, pipeline.schema
            )

            if pipeline.load_mode in ("append", "upsert") and not exists:
                raise ETLTargetNotFoundError(
                    f"{pipeline.load_mode} target"
                    f" {pipeline.schema}.{pipeline.target} does not exist"
                )

            if pipeline.load_mode == "replace" and not exists:
                # Create empty typed table before the load txn (D-03 / D-03a)
                await self._db.from_dataframe(
                    df.head(0),
                    pipeline.target,
                    pipeline.schema,
                    if_exists="replace",
                )

            # ------------------------------------------------------------------
            # 5. BUILD LOAD SQL (Plan 01 pure builders — never the public batch methods)
            # ------------------------------------------------------------------
            if pipeline.load_mode == "append":
                insert_sql, insert_params = _build_insert_sql(
                    pipeline.target, columns, rows, pipeline.schema
                )
            elif pipeline.load_mode == "upsert":
                insert_sql, insert_params = _build_upsert_sql(
                    pipeline.target,
                    rows,
                    list(pipeline.conflict_columns),
                    schema=pipeline.schema,
                )
            else:  # replace
                truncate_sql, _ = build_truncate_sql(pipeline.target, pipeline.schema)
                insert_sql, insert_params = _build_insert_sql(
                    pipeline.target, columns, rows, pipeline.schema
                )

            # ------------------------------------------------------------------
            # 6. ATOMIC LOAD — async seam (RESEARCH §7 / SC-3)
            #    Execute (sql, params) directly on the txn-yielded conn.
            # ------------------------------------------------------------------
            async with self._db.session():
                async with self._db.transaction() as conn:
                    async with conn.cursor() as cur:
                        if pipeline.load_mode == "replace":
                            await cur.execute(truncate_sql)
                        await cur.execute(insert_sql, insert_params)
                        rows_loaded += cur.rowcount

        except Exception as exc:
            await self._end_run(
                run_id,
                "failed",
                rows_extracted,
                0,
                error_message=str(exc),
                error_traceback=traceback.format_exc(),
            )
            raise

        await self._end_run(run_id, "success", rows_extracted, rows_loaded)
        return await self._fetch_run_result(run_id)
