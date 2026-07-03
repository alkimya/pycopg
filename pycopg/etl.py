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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from dataclasses import replace as dc_replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal, TypeAlias, cast

import pandas as pd
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from pycopg import queries
from pycopg.async_database import _async_stream_df_copy
from pycopg.database import _stream_df_copy
from pycopg.exceptions import (  # noqa: F401
    ETLError,
    ETLTargetNotFoundError,
    ETLTransformError,
)
from pycopg.logging import log_operation
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


def _validate_incremental(
    incremental_column: str | Sequence[str] | None, load_mode: str
) -> None:
    """Validate the ``incremental_column`` / ``load_mode`` combination.

    Parameters
    ----------
    incremental_column : str, sequence of str, or None
        Watermark column name (single-column), or a sequence of names for a
        composite key (ETL-INC-F03, D-09), or ``None`` for a non-incremental
        pipeline. ``None`` short-circuits — both checks are skipped (D-15).
    load_mode : str
        Load strategy. Incremental loads require ``"upsert"``;
        ``"append"`` and ``"replace"`` are forbidden (D-16).

    Raises
    ------
    ValueError
        If ``incremental_column`` is set and ``load_mode`` is ``"append"``
        or ``"replace"`` (the forbidden-combo intent error, checked first).
    InvalidIdentifierError
        If any ``incremental_column`` element is not a valid SQL identifier
        (D-15; every composite element is validated — D-10, C-04).
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
    # A bare str stays single-column; any other sequence is a composite key —
    # validate every element (D-10, C-04 injection safety).
    if isinstance(incremental_column, str):
        validate_identifiers(incremental_column)
    else:
        validate_identifiers(*incremental_column)


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
    incremental_column : str, sequence of str, or None, optional
        Watermark column(s) for incremental extraction (ETL-INC-01). ``None``
        (default) = full-load pipeline. A single ``str`` is a single-column
        watermark (byte-identical to prior behavior); a sequence of names
        declares a **composite** (multi-column) watermark key, normalized to
        a ``tuple[str, ...]`` at construction (ETL-INC-F03, D-09) and
        compared via a native Postgres row-value ``WHERE (c1, c2) > (...)``.
        Every element must be a valid SQL identifier and ``load_mode`` must
        be ``"upsert"`` — ``"append"`` and ``"replace"`` are rejected at
        construction (D-16). The column(s) are expected to hold a monotonic,
        non-decreasing watermark (an aware ``datetime`` if a timestamp);
        this contract is documented, not enforced, in this layer (D-03).
        Default ``None``.
    initial_watermark : datetime, int, str, Sequence, or None, optional
        Seed-floor value for the FIRST incremental run only (ETL-INC-F01,
        D-01). When no stored watermark exists yet, this value is used as
        the ``WHERE col > initial_watermark`` floor — turning the default
        full initial load into a bounded/seeded load. Once the first
        successful run records ``max(col)``, ``initial_watermark`` is
        never consulted again (seed-floor-only semantics, D-01) — it is
        NOT a persistent clamp and is never combined via
        ``max(initial, stored)``. Requires ``incremental_column`` to be
        set (D-02); the scalar form is checked against the same
        ``{datetime, int, str}`` allowlist as a recorded watermark
        (:func:`_encode_watermark`) — ``bool``/``float`` are rejected
        loud at construction (D-02, C-02). Incremental still requires
        ``load_mode="upsert"`` (C-01) — the idempotency that makes a
        seeded bounded first-load safe. An empty (0-row) seeded first
        batch records no watermark and re-seeds from
        ``initial_watermark`` on the next run (D-03, C-03). For a composite
        ``incremental_column`` the seed must be a same-length ``Sequence``
        of allowlisted scalars — validated per element and normalized to a
        tuple at construction (D-04). Default ``None`` (byte-identical to
        today's full-initial-load behavior).
    incremental_inclusive : bool, optional
        When ``True`` the incremental extract filter uses ``>=`` instead of
        the default exclusive ``>`` (ETL-INC-F02, D-05) — the boundary row
        (``col == watermark``) is re-read every run. Safe because
        incremental requires ``load_mode="upsert"``: the overlap replay is
        an idempotent ``ON CONFLICT`` no-op (D-08, C-01). Orthogonal to
        ``incremental_lookback``. Default ``False`` (byte-identical to the
        current exclusive SQL).
    incremental_lookback : timedelta, int, or None, optional
        Overlap window subtracted from the READ floor to re-scan
        late-arriving rows (ETL-INC-F02, D-06). The subtraction happens in
        Python before binding — e.g. floor ``100`` with lookback ``10``
        reads ``WHERE col > 90``; a ``datetime`` floor with
        ``timedelta(hours=1)`` reads ``floor - 1h``. The RECORDED
        high-water mark is always the true ``max(col)`` — lookback widens
        the read window only, it never regresses the stored watermark
        (D-07). Requires a ``datetime`` or ``int`` watermark: applying a
        lookback to a ``str``-typed watermark raises :class:`ETLError` at
        run time (D-06). Like inclusive, the overlap replay is a safe
        idempotent upsert no-op (D-08, C-01). Must be a ``timedelta`` or a
        non-``bool`` ``int`` when set. Default ``None`` (no overlap,
        byte-identical to today).
    concurrency : {"wait", "skip"} or None, optional
        Serialize concurrent runs of this pipeline via a PostgreSQL advisory
        lock keyed on the pipeline name (ETL-INC-F04, D-12). Available to ANY
        pipeline. ``"wait"`` blocks (``pg_advisory_lock``) until a peer run
        finishes, then proceeds; ``"skip"`` (``pg_try_advisory_lock``) returns
        a transient ``RunResult(status="skipped", run_id=None)`` writing no
        ``pipeline_runs`` row if the lock is already held. The lock is
        session-scoped on a dedicated connection held for the entire run span
        and released in a ``finally`` (auto-released on disconnect even on
        crash). Default ``None`` (no lock, byte-identical to today — no extra
        round-trip). ``dry_run`` bypasses the lock.

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
    ValueError
        If ``initial_watermark`` is set without ``incremental_column``
        (D-02, ETL-INC-F01).
    ETLError
        If a scalar ``initial_watermark`` is not one of the supported
        ``{datetime, int, str}`` types — e.g. ``bool`` or ``float``
        (D-02, C-02).
    ValueError
        If ``incremental_lookback`` is set to something other than a
        ``timedelta`` or a non-``bool`` ``int`` (D-05).
    ValueError
        If ``concurrency`` is not one of ``"wait"``, ``"skip"``, or ``None``
        (D-12, ETL-INC-F04).

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

    Composite (multi-column) incremental watermark — the extract filters on the
    native row-value compare ``WHERE (day, seq) > (%s, %s)`` and the recorded
    watermark is the true greatest ROW, persisted as a ``"composite"`` envelope
    ``{"type": "composite", "columns": [...], "values": [<scalar-envelope>...]}``
    (ETL-INC-F03)::

        p = Pipeline(
            name="events_by_day_seq",
            source="events",
            target="events_rollup",
            load_mode="upsert",
            conflict_columns=["day", "seq"],
            incremental_column=["day", "seq"],
            initial_watermark=(20260101, 0),  # optional composite seed floor
        )

    The ``incremental_inclusive`` / ``incremental_lookback`` overlaps re-read
    boundary/late rows every run; this is safe because incremental requires
    ``upsert`` — the replay is an idempotent ``ON CONFLICT`` no-op (D-08).
    """

    name: str
    source: str
    target: str
    load_mode: str = "append"
    conflict_columns: tuple[str, ...] = ()
    schema: str = "public"
    transform: Callable[..., Any] | list[Callable[..., Any]] | None = None
    extract_limit: int | None = None
    incremental_column: str | Sequence[str] | None = None
    initial_watermark: datetime | int | str | Sequence[Any] | None = None
    incremental_inclusive: bool = False
    incremental_lookback: timedelta | int | None = None
    concurrency: Literal["wait", "skip"] | None = None

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
        # D-01: runtime guard against untyped/dynamically-constructed callers
        # (e.g. JSON-configured pipelines) — the dataclass field annotation
        # does not enforce the type at runtime, so mypy's static view (which
        # only sees `tuple[str, ...]`) considers this branch unreachable.
        if isinstance(self.conflict_columns, str):  # type: ignore[unreachable]
            raise ValueError(
                "conflict_columns must be a sequence of column names, not a "
                f"single string; got {self.conflict_columns!r} (did you mean "
                f"[{self.conflict_columns!r}]?)"
            )
        # Normalize conflict_columns from any iterable to a tuple (D-02).
        # Frozen dataclass requires object.__setattr__ for mutation.
        # D-01: same runtime-guard rationale as the isinstance(str) check
        # above — callers may pass a list/other iterable despite the
        # `tuple[str, ...]` static annotation.
        if not isinstance(self.conflict_columns, tuple):
            object.__setattr__(  # type: ignore[unreachable]
                self, "conflict_columns", tuple(self.conflict_columns)
            )
        # Validate load_mode first (D-06).
        _validate_load_mode(self.load_mode)
        # Normalize a composite incremental_column to a tuple (ETL-INC-F03,
        # D-09) BEFORE validation. A bare str is KEPT as a single-column
        # scalar — the inverse of the conflict_columns str-reject above:
        # tuple("ts") would explode into per-char columns. Any other sequence
        # (list/tuple) becomes a tuple[str, ...] on the frozen instance.
        if self.incremental_column is not None and not isinstance(
            self.incremental_column, str
        ):
            object.__setattr__(
                self, "incremental_column", tuple(self.incremental_column)
            )
            if not self.incremental_column:
                raise ValueError(
                    "incremental_column sequence must be non-empty "
                    "(composite watermark, D-09)"
                )
        # Validate incremental_column / load_mode combo + identifier
        # (D-14/D-15/D-16/D-17) — after load_mode, before the upsert check.
        # validate_identifiers is splatted over every composite element (D-10).
        _validate_incremental(self.incremental_column, self.load_mode)
        # Validate initial_watermark (ETL-INC-F01/F03): requires
        # incremental_column to be set (D-02). For a single-column key the seed
        # must be a scalar checked against the {datetime, int, str} allowlist
        # via _encode_watermark (bool-before-int, float rejected — C-02). For a
        # composite key the seed must be a SAME-LENGTH sequence, each element
        # allowlist-checked per element (never a bulk isinstance — the bool
        # subclass trap, RESEARCH Pitfall 2), normalized to a tuple so the
        # 49-04 seed fallback yields a tuple directly (D-04).
        if self.initial_watermark is not None:
            if self.incremental_column is None:
                raise ValueError(
                    "initial_watermark requires incremental_column to be set "
                    "(D-02, ETL-INC-F01)"
                )
            if isinstance(self.incremental_column, tuple):
                # Composite key (D-04): matching-length sequence of scalars.
                if isinstance(self.initial_watermark, str) or not isinstance(
                    self.initial_watermark, (list, tuple)
                ):
                    raise ValueError(
                        "initial_watermark for a composite incremental_column "
                        f"must be a sequence of {len(self.incremental_column)} "
                        f"values, got {self.initial_watermark!r} (D-04)"
                    )
                if len(self.initial_watermark) != len(self.incremental_column):
                    raise ValueError(
                        "initial_watermark length "
                        f"{len(self.initial_watermark)} does not match composite "
                        f"incremental_column length "
                        f"{len(self.incremental_column)} (D-04)"
                    )
                for elem in self.initial_watermark:
                    _encode_watermark(elem)  # per-element allowlist (Pitfall 2)
                object.__setattr__(
                    self, "initial_watermark", tuple(self.initial_watermark)
                )
            else:
                # Single-column key: the seed must be a scalar, not a sequence.
                if isinstance(self.initial_watermark, (list, tuple)):
                    raise ValueError(
                        "initial_watermark must be a scalar for a single-column "
                        f"incremental_column, got {self.initial_watermark!r} "
                        "(D-04)"
                    )
                _encode_watermark(self.initial_watermark)  # type: ignore[arg-type]
        # Validate incremental_lookback (ETL-INC-F02, D-05): when set it must
        # be a timedelta or a plain (non-bool) int. bool is an int subclass, so
        # guard it explicitly — lookback=True would otherwise subtract 1 (the
        # same subclass trap as extract_limit/C-02). The str-watermark+lookback
        # incompatibility can only be checked once the watermark type is known,
        # so it is a RUNTIME guard in run() (D-06), not here.
        if self.incremental_lookback is not None and not isinstance(
            self.incremental_lookback, timedelta
        ):
            if isinstance(self.incremental_lookback, bool) or not isinstance(
                self.incremental_lookback, int
            ):
                raise ValueError(
                    "incremental_lookback must be a timedelta, a non-bool int, "
                    f"or None, got {self.incremental_lookback!r} (D-05)"
                )
        # Validate concurrency membership (ETL-INC-F04, D-12): available to ANY
        # pipeline; None = no lock. Modeled on _validate_load_mode.
        if self.concurrency is not None and self.concurrency not in ("wait", "skip"):
            raise ValueError(
                "concurrency must be 'wait', 'skip', or None, got "
                f"{self.concurrency!r} (D-12, ETL-INC-F04)"
            )
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
        One of ``'success'``, ``'failed'`` (persisted runs), or the transient
        values ``'dry_run'`` (D-08) and ``'skipped'`` (ETL-INC-F04, D-13) —
        both never stored: no ``pipeline_runs`` row is written and the
        ``status`` CHECK constraint is unchanged. ``'skipped'`` is returned
        when ``concurrency="skip"`` and the advisory lock is already held.
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
    watermark_used : datetime, int, str, tuple, or None
        The filter floor applied to this run — the watermark value read
        before extract, used as the ``WHERE col > wm`` bound (D-A1). A
        tuple for a composite watermark key (ETL-INC-F03). ``None`` for
        non-incremental pipelines and for stored rows surfaced by
        ``history()`` / ``last_run()`` (where the per-run input is never
        persisted).
    watermark_recorded : datetime, int, str, tuple, or None
        The new high-water mark persisted for this run — decoded from
        ``pipeline_runs.watermark`` (D-A1); a tuple for a composite
        watermark key (ETL-INC-F03).  ``None`` for non-incremental
        pipelines and when no watermark was stored (e.g. empty batch,
        failed run, or NULL in ``pipeline_runs``).
    """

    run_id: int | None
    pipeline_name: str
    status: str
    rows_extracted: int
    rows_loaded: int
    started_at: datetime
    finished_at: datetime
    error: str | None
    watermark_used: datetime | int | str | tuple[datetime | int | str, ...] | None = (
        None
    )
    watermark_recorded: (
        datetime | int | str | tuple[datetime | int | str, ...] | None
    ) = None


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


def build_truncate_sql(table: str, schema: str = "public") -> tuple[str, list[Any]]:
    """Build a TRUNCATE SQL statement for a replace-mode load target.

    Called by the Phase 18 ``replace`` load path to empty the target
    table before the bulk insert. Identifiers are validated before
    interpolation (D-13) — an invalid ``table`` or ``schema`` name raises
    ``InvalidIdentifierError`` and no SQL is produced.

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
    InvalidIdentifierError
        If ``table`` or ``schema`` is not a valid SQL identifier (D-13).
    """
    validate_identifiers(table, schema)
    return f"TRUNCATE TABLE {schema}.{table}", []


def build_init_sql() -> tuple[str, list[Any]]:
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
    rows: list[dict[str, Any]],
    schema: str = "public",
    on_conflict: str | None = None,
) -> tuple[str, list[Any]]:
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
    InvalidIdentifierError
        If ``table``, ``schema``, or any element of ``columns`` is not a
        valid SQL identifier (T-18-01, SC-6).
    """
    validate_identifiers(table, schema, *columns)

    cols_str = ", ".join(columns)
    conflict_clause = f" ON CONFLICT {on_conflict}" if on_conflict else ""

    placeholders: list[str] = []
    params: list[Any] = []
    for row in rows:
        row_placeholders = ", ".join(["%s"] * len(columns))
        placeholders.append(f"({row_placeholders})")
        params.extend(row.get(col) for col in columns)

    values_str = ", ".join(placeholders)
    sql = f"INSERT INTO {schema}.{table} ({cols_str}) VALUES {values_str}{conflict_clause}"
    return sql, params


def _build_upsert_sql(
    table: str,
    rows: list[dict[str, Any]],
    conflict_columns: list[str] | tuple[str, ...],
    update_columns: list[str] | None = None,
    schema: str = "public",
) -> tuple[str, list[Any]]:
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
    InvalidIdentifierError
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
    column: str | Sequence[str],
    schema: str = "public",
    watermark: datetime | int | str | Sequence[Any] | None = None,
    *,
    inclusive: bool = False,
) -> tuple[str, list[Any]]:
    """Build the watermark-filtered incremental extract SQL.

    Pure builder — no ``self``, no I/O, no DB connection.  Dispatches on
    the source kind via :func:`_is_sql_source` (D-11): a SQL-string source
    is wrapped in a subquery aliased ``_pycopg_inc`` (D-06/D-07); a table
    source gets a ``WHERE`` clause appended (D-09).  Watermark values are
    ALWAYS emitted as ``%s`` placeholders appended to the params list —
    never f-string interpolated (D-10, T-26-01).  Identifiers (every
    ``column`` element, and ``source``/``schema`` for table sources) are
    validated before any interpolation (T-26-02).

    A single-``str`` ``column`` produces ``WHERE col {op} %s`` (single
    watermark param).  A composite (sequence) ``column`` produces the native
    Postgres row-value compare ``WHERE (c1, c2) {op} (%s, %s)`` with one
    bound ``%s`` per element and ``params = list(watermark)`` (ETL-INC-F03,
    D-10).

    When ``watermark is None`` (first run or no prior watermark) a full,
    unfiltered SELECT is returned with an empty params list (D-12).  The
    boundary defaults to exclusive (``>``), matching the REQUIREMENTS
    contract; ``inclusive=True`` emits ``>=`` instead (ETL-INC-F02, D-05).

    Parameters
    ----------
    source : str
        Source table name or a SQL SELECT/WITH statement string. Classified
        via :func:`_is_sql_source`.
    column : str or sequence of str
        Watermark column name (single-column) or a sequence of names for a
        composite key. Every element must be a valid SQL identifier; emitted
        bare after validation (D-10).
    schema : str, optional
        Schema for a table source, by default ``"public"``. Ignored for a
        SQL-string source. Must be a valid SQL identifier.
    watermark : optional
        High-water mark value(s), or ``None`` for a full unfiltered extract
        (D-12). A scalar for a single-column key; an ordered sequence aligned
        with ``column`` for a composite key.
    inclusive : bool, keyword-only, optional
        When ``True`` the comparison operator is ``>=`` (boundary row
        re-read); default ``False`` uses the exclusive ``>`` (ETL-INC-F02,
        D-05). The operator is a literal chosen from this bool, never
        user text — the injection surface is unchanged.

    Returns
    -------
    tuple of (str, list)
        The extract SQL string and a params list of the watermark value(s)
        (one per column element), or ``[]`` when ``watermark is None``.

    Raises
    ------
    InvalidIdentifierError
        If any ``column`` element (always) or ``source``/``schema`` (table
        source) is not a valid SQL identifier (T-26-02).
    """
    # A bare str is single-column; any other sequence is a composite key.
    # validate_identifiers is splatted over every element as line 1 (D-10).
    if isinstance(column, str):
        validate_identifiers(column)
        is_composite = False
        cols: tuple[str, ...] = (column,)
    else:
        cols = tuple(column)
        validate_identifiers(*cols)
        is_composite = True
    if watermark is None:
        if _is_sql_source(source):
            return source, []
        validate_identifiers(source, schema)
        return f"SELECT * FROM {schema}.{source}", []
    # Operator is a literal chosen from the inclusive bool — never user text.
    op = ">=" if inclusive else ">"
    if is_composite:
        # Native row-value lexicographic compare (D-10): one bound %s per
        # element; watermark is an ordered sequence aligned with cols.
        wm_seq = cast("Sequence[Any]", watermark)
        lhs = "(" + ", ".join(cols) + ")"
        placeholders = "(" + ", ".join(["%s"] * len(cols)) + ")"
        params: list[Any] = list(wm_seq)
    else:
        lhs = cols[0]
        placeholders = "%s"
        params = [watermark]
    if _is_sql_source(source):
        # Right-strip whitespace, a single trailing ';', then whitespace
        # again before wrapping (D-08 hygiene — no SQL parser).
        clean = source.rstrip().rstrip(";").rstrip()
        sql = f"SELECT * FROM ({clean}) {_PYCOPG_INC_ALIAS} WHERE {lhs} {op} {placeholders}"
        return sql, params
    validate_identifiers(source, schema)
    return (
        f"SELECT * FROM {schema}.{source} WHERE {lhs} {op} {placeholders}",
        params,
    )


def _apply_lookback(
    watermark: datetime | int | str,
    lookback: timedelta | int,
) -> datetime | int:
    """Subtract a lookback overlap from a READ floor (ETL-INC-F02, D-06).

    Pure — no I/O. Widens the read window only; the caller must NOT feed the
    result into the recorded watermark, which always stays the true
    ``max(col)`` (D-07). The subtraction happens in Python before the value is
    bound as a parameter.

    A ``datetime`` floor requires a ``timedelta`` lookback; an ``int`` floor
    requires an ``int`` lookback. A ``str``-typed floor cannot be adjusted —
    the watermark type is only known at run time, so this is a runtime
    :class:`ETLError` (D-06), not a construction guard.

    Parameters
    ----------
    watermark : datetime or int or str
        The resolved read floor (post-seed, 49-01).
    lookback : timedelta or int
        The overlap window from ``Pipeline.incremental_lookback``.

    Returns
    -------
    datetime or int
        The widened read floor (``watermark - lookback``).

    Raises
    ------
    ETLError
        If ``watermark`` is a ``str``, or the lookback type does not match the
        watermark type (D-06).
    """
    if isinstance(watermark, datetime):
        if not isinstance(lookback, timedelta):
            raise ETLError(
                "incremental_lookback for a datetime watermark must be a "
                f"timedelta, got {lookback!r} (D-06)"
            )
        return watermark - lookback
    if isinstance(watermark, int):  # bool excluded upstream; plain int floor
        if isinstance(lookback, timedelta):
            raise ETLError(
                "incremental_lookback for an int watermark must be an int, "
                f"got a timedelta {lookback!r} (D-06)"
            )
        return watermark - lookback
    raise ETLError(
        "incremental_lookback cannot be applied to a str-typed watermark "
        f"({watermark!r}); lookback requires a datetime or int watermark (D-06)"
    )


#: Watermark types that can be stored in the typed JSONB envelope (D-04).
_WATERMARK_SUPPORTED = "{datetime, int, str}"


def _encode_watermark(value: datetime | int | str) -> dict[str, Any]:
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


def _encode_composite_watermark(
    columns: Sequence[str], values: Sequence[Any]
) -> dict[str, Any]:
    """Encode a composite (multi-column) watermark into a typed envelope (D-11).

    Pure — no I/O. Reuses the frozen per-scalar :func:`_encode_watermark`
    element-wise so the bool-before-int / float-reject allowlist holds PER
    ELEMENT (never a bulk ``isinstance`` — RESEARCH Pitfall 2, C-02). The shape
    is ``{"type": "composite", "columns": [...], "values": [<scalar-envelope>...]}``,
    additive to the three frozen scalar tags so single-column rows are
    untouched (zero migration, C-02).

    Parameters
    ----------
    columns : sequence of str
        The composite watermark column names (order-significant).
    values : sequence
        The per-column watermark scalars, aligned with ``columns``.

    Returns
    -------
    dict
        The composite envelope.

    Raises
    ------
    ETLError
        If any element is not an allowlisted scalar (per-element, D-11).
    """
    return {
        "type": "composite",
        "columns": list(columns),
        "values": [_encode_watermark(v) for v in values],
    }


def _decode_watermark(
    envelope: dict[str, Any],
) -> datetime | int | str | tuple[datetime | int | str, ...]:
    """Decode a typed JSONB envelope back to the original watermark value.

    Pure function — no ``self``, no I/O.  Mirrors the dict→typed
    reconstruction of :func:`_row_to_result`.  Reads the ``type`` tag and
    rebuilds the exact Python type written by :func:`_encode_watermark`;
    ``datetime`` is rebuilt via :meth:`datetime.fromisoformat`, preserving
    the offset and microseconds (D-02).  A ``"composite"`` envelope
    (ETL-INC-F03, D-11) is decoded element-wise back to a tuple of scalars,
    reusing this same decoder per element; the three scalar tags are
    unchanged so single-column rows decode exactly as before (zero
    migration, C-02).

    Parameters
    ----------
    envelope : dict
        Typed envelope as returned by :func:`_encode_watermark` /
        :func:`_encode_composite_watermark` (the plain ``dict`` psycopg
        yields when reading a JSONB column).

    Returns
    -------
    datetime or int or str or tuple
        The reconstructed watermark scalar, or a tuple of scalars for a
        composite envelope.
    """
    tag = envelope["type"]
    if tag == "composite":
        return tuple(_decode_scalar_watermark(v) for v in envelope["values"])
    return _decode_scalar_watermark(envelope)


def _decode_scalar_watermark(envelope: dict[str, Any]) -> datetime | int | str:
    """Decode a single scalar watermark envelope (the three frozen tags)."""
    tag = envelope["type"]
    value = envelope["value"]
    if tag == "datetime":
        return datetime.fromisoformat(value)
    if tag == "int":
        return int(value)
    if tag == "str":
        return str(value)
    raise ETLError(
        f"Unknown watermark type tag {tag!r} in envelope {envelope!r}. "
        "Watermark envelope may be corrupted; supported tags are: "
        "'datetime', 'int', 'str', 'composite'."
    )


#: A composite (multi-column) watermark value — a tuple of scalars aligned
#: with a composite ``incremental_column`` (ETL-INC-F03).
CompositeWatermark: TypeAlias = tuple["datetime | int | str", ...]


def _encode_watermark_value(
    col: str | Sequence[str] | None,
    value: datetime | int | str | CompositeWatermark,
) -> dict[str, Any]:
    """Encode a captured watermark for persistence — scalar or composite.

    Dispatches on the column shape: a single ``str`` (or ``None``) column
    encodes a scalar via :func:`_encode_watermark`; a composite (sequence)
    column encodes the tuple via :func:`_encode_composite_watermark`. The
    resulting envelope is persisted opaquely by ``_end_run`` (D-11).
    """
    if isinstance(col, str) or col is None:
        return _encode_watermark(cast("datetime | int | str", value))
    return _encode_composite_watermark(col, cast("Sequence[Any]", value))


def _coerce_watermark_scalar(m: Any, col_label: str) -> datetime | int | str | None:
    """Coerce one pandas/numpy max value to a plain watermark scalar.

    Shared by the single-column and composite (per-element) capture paths.
    Returns ``None`` when the value is ``NaN``/``NaT`` (record nothing this
    run — C-03). The ``pd.isna`` check precedes the float check because ``NaN``
    is itself a float (WR-02). A genuine float dtype raises :class:`ETLError`
    (no defined watermark semantics — ``int()`` would silently truncate; D-06).
    """
    if pd.isna(m):
        return None
    if isinstance(m, pd.Timestamp):
        return m.to_pydatetime()  # plain datetime, offset preserved
    if isinstance(m, str):
        return str(m)  # normalize numpy.str_ → str
    if pd.api.types.is_float(m):
        raise ETLError(
            f"incremental_column {col_label!r} has float dtype; float "
            f"watermarks are not supported (cast to INTEGER or TIMESTAMP). "
            f"Supported types are {_WATERMARK_SUPPORTED}"
        )
    return int(m)  # numpy.int64 → plain int


def _capture_watermark(
    df: pd.DataFrame,
    col: str | Sequence[str] | None,
) -> datetime | int | str | CompositeWatermark | None:
    """Capture the recorded high-water mark from a RAW extract batch.

    Single-column (``str``): ``max(col)``. Composite (sequence): the true
    greatest ROW — sort by the key columns and take the last row's tuple, NOT
    per-column maxes (D-10; per-column maxes fabricate a row no data has —
    RESEARCH Pitfall 3). A ``NaN``/``NaT`` in ANY captured element voids the
    whole watermark for this run (record nothing, the prior watermark is
    preserved — RESEARCH Pitfall 4 / C-03).

    Returns ``None`` for a non-incremental pipeline (``col is None``) or an
    empty batch. Raises :class:`ETLError` if any key column is missing from
    the batch (D-06) or has float dtype.
    """
    if col is None:
        return None
    cols = [col] if isinstance(col, str) else list(col)
    missing = [c for c in cols if c not in df.columns]
    if missing:
        # Single-column keeps the scalar repr byte-identical (D-A3); composite
        # reports the list of missing key columns.
        label: str | list[str] = col if isinstance(col, str) else missing
        raise ETLError(
            f"incremental_column {label!r} not found in extracted batch "
            f"columns {list(df.columns)} (ETL-INC-04)"  # D-06 — not a bare KeyError
        )
    if not len(df):  # guard: max()/iloc on an empty frame
        return None
    if isinstance(col, str):
        return _coerce_watermark_scalar(df[col].max(), col)
    # Composite: the greatest ROW under lexicographic key order — matches the
    # native Postgres row-value compare (c1, c2) > (w1, w2) (D-10). Read each
    # element from its OWN sorted column (`sorted_df[c].iloc[-1]`), never from a
    # cross-column row Series: extracting a whole row promotes mixed int/float
    # columns to a common dtype, which would falsely trip the float-reject on an
    # int key when a sibling column is float.
    sorted_df = df.sort_values(cols)
    captured: list[datetime | int | str] = []
    for c in cols:
        scalar = _coerce_watermark_scalar(sorted_df[c].iloc[-1], c)
        if scalar is None:  # any NaN element → void the whole tuple (Pitfall 4)
            return None
        captured.append(scalar)
    return tuple(captured)


def _reconcile_watermark_binds(
    sql: str, params_list: list[Any]
) -> tuple[str, dict[str, Any]]:
    """Map the builder's positional ``%s`` watermark placeholders to named binds.

    ``to_dataframe`` uses SQLAlchemy ``text()`` named parameters. A
    single-column extract keeps the historical ``:wm`` bind (byte-identical);
    a composite extract maps each ``%s`` in order to a distinct ``:wm{i}``
    bind so the ``(c1, c2) > (:wm0, :wm1)`` row-value compare is fully
    parameterized (never interpolated).

    :func:`_build_incremental_extract_sql` always APPENDS its placeholders at
    the tail (the ``WHERE`` clause it adds), so only the LAST
    ``len(params_list)`` ``%s`` are the watermark binds. Substituting those
    from the right leaves any literal ``%s`` inside a user SQL source (e.g. a
    ``LIKE '%s%'`` predicate) untouched (WR-01).
    """
    n = len(params_list)
    if n == 0:
        return sql, {}
    # Locate the last n "%s" occurrences — the builder's trailing placeholders.
    positions: list[int] = []
    search_end = len(sql)
    while len(positions) < n:
        idx = sql.rfind("%s", 0, search_end)
        if idx == -1:
            break
        positions.append(idx)
        search_end = idx
    if len(positions) < n:  # defensive — the builder guarantees n placeholders
        raise ETLError(
            f"expected {n} watermark placeholder(s) in the extract SQL, "
            f"found {len(positions)}"
        )
    positions.reverse()  # left-to-right → placeholder i binds :wm{i}
    names = ["wm"] if n == 1 else [f"wm{i}" for i in range(n)]
    # Replace right-to-left so earlier positions stay valid as lengths change.
    for i in range(n - 1, -1, -1):
        pos = positions[i]
        sql = sql[:pos] + ":" + names[i] + sql[pos + 2 :]
    return sql, dict(zip(names, params_list))


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
    name: str | None = getattr(fn, "__name__", None)
    if name and name != "<lambda>":
        return name
    return repr(fn)


def _row_to_result(row: dict[str, Any]) -> RunResult:
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
                row = cur.fetchone()
                # INSERT ... RETURNING always yields exactly one row.
                assert row is not None
                return int(row["run_id"])

    def _end_run(
        self,
        run_id: int,
        status: str,
        rows_extracted: int,
        rows_loaded: int,
        error_message: str | None = None,
        error_traceback: str | None = None,
        watermark: dict[str, Any] | None = None,
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
        # The row was just written by _start_run/_end_run under this run_id.
        assert row is not None
        return _row_to_result(row)

    def history(self, name: str, *, limit: int = 100) -> list[RunResult]:
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

    def _read_watermark(
        self, name: str
    ) -> datetime | int | str | CompositeWatermark | None:
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
        watermark: datetime | int | str | CompositeWatermark | None,
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
            # Incremental path: build filtered SQL with bound watermark param(s).
            # The builder emits positional %s; reconcile to named :wm / :wm{i}
            # binds for to_dataframe (SQLAlchemy text() + named params). A
            # composite key emits multiple %s → one distinct named bind each.
            sql, _params = _build_incremental_extract_sql(
                pipeline.source,
                pipeline.incremental_column,
                pipeline.schema,
                watermark=watermark,
                inclusive=pipeline.incremental_inclusive,
            )
            sql, params = _reconcile_watermark_binds(sql, _params)
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

    def run(self, pipeline: Pipeline, *, dry_run: bool = False) -> RunResult:
        """Execute a pipeline run, optionally under an advisory concurrency lock.

        Thin wrapper around :meth:`_run_impl` (the extract → transform → load
        body). When ``pipeline.concurrency`` is ``None`` (default) or
        ``dry_run`` is set, delegates directly — byte-identical to the
        pre-F04 behavior with no extra round-trip.

        Otherwise a session-scoped PostgreSQL advisory lock keyed on the
        pipeline name (via ``hashtextextended``) is acquired on a DEDICATED
        autocommit connection held for the entire run span (ETL-INC-F04,
        D-14): ``"wait"`` blocks until a peer run releases the lock, then
        proceeds; ``"skip"`` returns a transient
        ``RunResult(status="skipped", run_id=None)`` writing no
        ``pipeline_runs`` row when the lock is already held (D-13). The lock
        is released in a ``finally`` and the connection is closed — closing
        auto-releases the lock even on crash.

        See :meth:`_run_impl` for the full extract/transform/load semantics.

        Parameters
        ----------
        pipeline : Pipeline
            Fully specified pipeline descriptor.
        dry_run : bool, optional
            When ``True``, run extract + transform only and bypass the lock.
            By default ``False``.

        Returns
        -------
        RunResult
            Immutable snapshot of the completed, dry-run, or skipped run.
        """
        if pipeline.concurrency is None or dry_run:
            return self._run_impl(pipeline, dry_run=dry_run)
        # Session-scoped advisory lock on a DEDICATED connection (D-14) — a
        # third connection, independent of the run-log and load-txn connections
        # (Pitfall 1): it must span from before _read_watermark through _end_run.
        with self._db.connect(autocommit=True) as lock_conn:
            if pipeline.concurrency == "skip":
                with lock_conn.cursor() as cur:
                    cur.execute(queries.ETL_ADVISORY_TRY_LOCK, [pipeline.name])
                    row = cur.fetchone()
                if not (row and row[0]):  # lock already held → transient skip (D-13)
                    now = datetime.now(UTC)
                    return RunResult(
                        run_id=None,
                        pipeline_name=pipeline.name,
                        status="skipped",
                        rows_extracted=0,
                        rows_loaded=0,
                        started_at=now,
                        finished_at=now,
                        error=None,
                    )
            else:  # "wait" → block until the peer releases
                with lock_conn.cursor() as cur:
                    cur.execute(queries.ETL_ADVISORY_LOCK, [pipeline.name])
            try:
                return self._run_impl(pipeline, dry_run=dry_run)
            finally:
                # Explicit release for the normal path; the `with` close below
                # auto-releases even if this fails (crash-safety, D-14).
                try:
                    with lock_conn.cursor() as cur:
                        cur.execute(queries.ETL_ADVISORY_UNLOCK, [pipeline.name])
                except Exception:  # pragma: no cover - defensive
                    pass

    def _run_impl(self, pipeline: Pipeline, *, dry_run: bool = False) -> RunResult:
        """Execute a full extract → transform → load pipeline run (lock-unaware).

        The run body behind :meth:`run`. Auto-creates ``pipeline_runs`` if
        absent, inserts a ``'running'`` row, executes the pipeline, and
        records the final status.

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

        with log_operation("etl.run"):
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
                # Seed-floor fallback (D-01): first-run seed, explicit is-None.
                if pipeline.incremental_column is not None and dry_wm is None:
                    dry_wm = cast(
                        "datetime | int | str | CompositeWatermark | None",
                        pipeline.initial_watermark,
                    )

                # Shared filtered extract (D-A2a) — same path as real run.
                # Lookback widens the READ floor here too so the dry-run
                # previews the same overlap window (D-06/D-07).
                dry_read_floor: datetime | int | str | CompositeWatermark | None = (
                    dry_wm
                )
                if pipeline.incremental_lookback is not None and dry_wm is not None:
                    if isinstance(dry_wm, tuple):
                        raise ETLError(
                            "incremental_lookback is not supported for a composite "
                            "watermark key (ETL-INC-F03); apply a lookback only to a "
                            "single-column watermark"
                        )
                    dry_read_floor = _apply_lookback(
                        dry_wm, pipeline.incremental_lookback
                    )
                df = self._do_extract(pipeline, dry_read_floor)
                rows_extracted = len(df)

                # Capture would-be watermark from RAW filtered batch (D-A2).
                # Composite → the greatest sorted ROW (D-10); scalar → max(col);
                # any NaN element voids the watermark for this run (Pitfall 4).
                dry_raw_watermark: (
                    datetime | int | str | CompositeWatermark | None
                ) = _capture_watermark(df, pipeline.incremental_column)

                # Transform chain (same as normal path)
                transform = pipeline.transform
                steps: list[Any]
                if transform is None:
                    steps = []
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
                    watermark_used=dry_read_floor,
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
            # Seed-floor fallback (D-01 / C-04): on the FIRST run (no stored
            # watermark) fall back to Pipeline.initial_watermark. Explicit
            # is-None — 0 is a valid floor (RESEARCH §F01), never a falsy check.
            # Consulted ONLY here; once a run records max(col) it is ignored.
            # Composite (Sequence) seeding is wired in 49-04 — F01 is scalar-only,
            # so the cast documents the narrowed scalar contract.
            if pipeline.incremental_column is not None and wm is None:
                wm = cast(
                    "datetime | int | str | CompositeWatermark | None",
                    pipeline.initial_watermark,
                )

            try:
                # ------------------------------------------------------------------
                # 1. EXTRACT (shared filtered path — D-A2a)
                # Lookback (D-06/D-07): widen the READ floor only — the recorded
                # watermark below stays the true max(col). A str-typed floor
                # cannot be adjusted → _apply_lookback raises ETLError at run
                # time. Overlap replay is a safe idempotent upsert no-op (D-08,
                # C-01): incremental requires upsert, so re-read rows ON CONFLICT.
                # ------------------------------------------------------------------
                read_floor: datetime | int | str | CompositeWatermark | None = wm
                if pipeline.incremental_lookback is not None and wm is not None:
                    if isinstance(wm, tuple):
                        raise ETLError(
                            "incremental_lookback is not supported for a composite "
                            "watermark key (ETL-INC-F03); apply a lookback only to a "
                            "single-column watermark"
                        )
                    read_floor = _apply_lookback(wm, pipeline.incremental_lookback)
                df = self._do_extract(pipeline, read_floor)

                rows_extracted = len(df)

                # ------------------------------------------------------------------
                # 1b. INCREMENTAL WATERMARK CAPTURE (D-02 / D-06 / D-07 / ETL-INC-02)
                # Capture the recorded high-water mark from the RAW batch BEFORE
                # the transform chain (D-02: transforms may rename/drop columns).
                # Single-column → max(col); composite → the greatest sorted ROW
                # (D-10, NOT per-column maxes); any NaN element voids the
                # watermark for this run (Pitfall 4 / C-03). Coercion to plain
                # Python types keeps _encode_watermark's allowlist satisfied.
                # ------------------------------------------------------------------
                raw_watermark: datetime | int | str | CompositeWatermark | None = (
                    _capture_watermark(df, pipeline.incremental_column)
                )

                # ------------------------------------------------------------------
                # 2. TRANSFORM CHAIN (D-05 / D-06 / ETL-16)
                # ------------------------------------------------------------------
                transform = pipeline.transform
                if transform is None:
                    steps = []
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
                # 3. ROWS: early-exit on empty + derive columns (D-02b / D-02c)
                # ------------------------------------------------------------------
                # No rows to load (empty extract, or transforms dropped every row):
                # record success with 0 rows_loaded and NO watermark — even if a
                # raw_watermark was captured above, a no-load run must not advance
                # the watermark.  The prior successful watermark is preserved by
                # ETL_GET_LAST_WATERMARK's `watermark IS NOT NULL` predicate.
                if df.empty:
                    self._end_run(run_id, "success", rows_extracted, 0)
                    return self._fetch_run_result(run_id)

                columns = list(df.columns)

                # Materialize rows as list[dict] only for upsert (INSERT … ON CONFLICT).
                # append/replace stream directly via COPY — no full-frame astype(object)
                # materialization needed (D-02 / D-02c / PERF-02).
                rows: list[dict[str, Any]]
                if pipeline.load_mode == "upsert":
                    # pandas types to_dict(orient="records") keys as Hashable;
                    # DataFrame columns are always str here (extracted via
                    # to_dataframe/SQL), so the runtime shape is dict[str, Any].
                    records = (
                        df.astype(object)
                        .where(pd.notnull(df), None)
                        .to_dict(orient="records")
                    )
                    rows = cast("list[dict[str, Any]]", records)
                else:
                    rows = []  # unused for append/replace COPY path

                # ------------------------------------------------------------------
                # 4. EXISTENCE CHECK (D-03)
                # ------------------------------------------------------------------
                exists = self._db.schema.table_exists(
                    pipeline.target, schema=pipeline.schema
                )

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
                        schema=pipeline.schema,
                        if_exists="replace",
                    )

                # ------------------------------------------------------------------
                # 5. BUILD LOAD SQL (pure builders — upsert only; COPY needs no INSERT SQL)
                # ------------------------------------------------------------------
                if pipeline.load_mode == "upsert":
                    insert_sql, insert_params = _build_upsert_sql(
                        pipeline.target,
                        rows,
                        list(pipeline.conflict_columns),
                        schema=pipeline.schema,
                    )
                elif pipeline.load_mode == "replace":
                    truncate_sql, _ = build_truncate_sql(
                        pipeline.target, pipeline.schema
                    )

                # append: no SQL builder — rows stream via COPY below

                # ------------------------------------------------------------------
                # 6. ATOMIC LOAD — the seam (RESEARCH Q1 / SC-3 / D-02a)
                #    append/replace: COPY inline on the transaction cursor.
                #    upsert: INSERT … ON CONFLICT via execute() (D-02c).
                #    Never call copy_insert() here — it opens its own connection +
                #    commit, breaking run-log atomicity (D-02a / T-38-06).
                # ------------------------------------------------------------------
                with self._db.session():
                    with self._db.transaction() as conn:
                        with conn.cursor() as cur:
                            if pipeline.load_mode == "replace":
                                cur.execute(truncate_sql)
                            if pipeline.load_mode in ("append", "replace"):
                                rows_loaded += _stream_df_copy(
                                    cur, df, pipeline.target, pipeline.schema, columns
                                )
                            else:  # upsert
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

            wm_env = (
                _encode_watermark_value(pipeline.incremental_column, raw_watermark)
                if raw_watermark is not None
                else None
            )
            self._end_run(
                run_id, "success", rows_extracted, rows_loaded, watermark=wm_env
            )
            # Fetch the stored result (watermark_recorded comes via _row_to_result),
            # then inject watermark_used (per-run input, never stored — D-A1).
            result = self._fetch_run_result(run_id)
            if wm is not None or pipeline.incremental_column is not None:
                result = dc_replace(result, watermark_used=read_floor)
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
                row = await cur.fetchone()
                # INSERT ... RETURNING always yields exactly one row.
                assert row is not None
                return int(row["run_id"])

    async def _end_run(
        self,
        run_id: int,
        status: str,
        rows_extracted: int,
        rows_loaded: int,
        error_message: str | None = None,
        error_traceback: str | None = None,
        watermark: dict[str, Any] | None = None,
    ) -> None:
        """Update a ``pipeline_runs`` row with final status and metrics.

        Opens a **dedicated** autocommit connection via
        ``async with self._db.connect(autocommit=True)`` (D-04), ensuring
        the UPDATE commits even when the load transaction rolled back
        (D-05/ETL-08/ETL-09).

        When *watermark* is not ``None`` the dedicated
        :data:`~pycopg.queries.ETL_UPDATE_RUN_WATERMARK` constant is used
        and the already-encoded envelope dict is bound via
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
            Full traceback string, by default ``None``.
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
        async with self._db.connect(autocommit=True) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                if watermark is None:
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
                else:
                    await cur.execute(
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
        # The row was just written by _start_run/_end_run under this run_id.
        assert row is not None
        return _row_to_result(row)

    async def history(self, name: str, *, limit: int = 100) -> list[RunResult]:
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

    async def _read_watermark(
        self, name: str
    ) -> datetime | int | str | CompositeWatermark | None:
        """Return the last successful, non-NULL watermark for a pipeline, or None.

        Reads one row from ``pipeline_runs`` via
        :data:`~pycopg.queries.ETL_GET_LAST_WATERMARK` on a dedicated
        autocommit connection with the ``dict_row`` factory (mirrors the
        :meth:`last_run` autocommit pattern).  The ``status = 'success'
        AND watermark IS NOT NULL`` predicate means failed runs and
        empty-batch successes are automatically skipped — the prior
        successful watermark is returned with no copy-forward write.

        The ``watermark`` JSONB column yields a plain Python ``dict`` which
        is passed straight to the frozen :func:`_decode_watermark` helper
        to reconstruct the typed scalar.

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
            never-succeeded-with-watermark).
        """
        async with self._db.connect(autocommit=True) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(queries.ETL_GET_LAST_WATERMARK, [name])
                row = await cur.fetchone()
        if row is None or row["watermark"] is None:
            return None
        return _decode_watermark(row["watermark"])

    async def _do_extract(
        self,
        pipeline: Pipeline,
        watermark: datetime | int | str | CompositeWatermark | None,
    ) -> pd.DataFrame:
        """Run the watermark-filtered async extract step for *pipeline*.

        Single shared extract path used by both the ``dry_run`` fork and the
        real run path — prevents the two forks from drifting in their filter
        logic (D-A2a).  Async mirror of :meth:`ETLAccessor._do_extract`.

        When ``pipeline.incremental_column`` is set, reads the watermark
        floor and applies ``WHERE col > :wm`` via
        :func:`_build_incremental_extract_sql`; the watermark value is
        always a named bound parameter (never f-string interpolated —
        SC-1 / T-28-A1).  When ``watermark is None`` the builder returns a
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
            # Incremental path: build filtered SQL with bound watermark param(s).
            # The builder emits positional %s; reconcile to named :wm / :wm{i}
            # binds for to_dataframe (SQLAlchemy text() + named params). A
            # composite key emits multiple %s → one distinct named bind each.
            sql, _params = _build_incremental_extract_sql(
                pipeline.source,
                pipeline.incremental_column,
                pipeline.schema,
                watermark=watermark,
                inclusive=pipeline.incremental_inclusive,
            )
            sql, params = _reconcile_watermark_binds(sql, _params)
            if pipeline.extract_limit is not None:
                # Wrap as subquery so LIMIT applies to the filtered result
                # and the :wm bind is still valid in the inner query
                sql = f"SELECT * FROM ({sql}) _etl_lim LIMIT :lim"
                params["lim"] = pipeline.extract_limit
            return await self._db.to_dataframe(sql=sql, params=params or None)

        # Non-incremental path — unchanged from original extract block
        if _is_sql_source(pipeline.source):
            if pipeline.extract_limit is not None:
                return await self._db.to_dataframe(
                    sql=(
                        f"SELECT * FROM ({pipeline.source}) AS _etl_sub" f" LIMIT :lim"
                    ),
                    params={"lim": pipeline.extract_limit},
                )
            return await self._db.to_dataframe(sql=pipeline.source)
        else:
            validate_identifiers(pipeline.source, pipeline.schema)
            if pipeline.extract_limit is not None:
                return await self._db.to_dataframe(
                    sql=(
                        f"SELECT * FROM {pipeline.schema}.{pipeline.source}"
                        f" LIMIT :lim"
                    ),
                    params={"lim": pipeline.extract_limit},
                )
            return await self._db.to_dataframe(
                table=pipeline.source,
                schema=pipeline.schema,
            )

    async def run(self, pipeline: Pipeline, *, dry_run: bool = False) -> RunResult:
        """Execute a pipeline run, optionally under an advisory concurrency lock.

        Async mirror of :meth:`ETLAccessor.run`. Thin wrapper around
        :meth:`_run_impl`: when ``pipeline.concurrency`` is ``None`` (default)
        or ``dry_run`` is set, delegates directly (byte-identical, no extra
        round-trip). Otherwise a session-scoped advisory lock keyed on the
        pipeline name is acquired on a dedicated ``await``ed autocommit
        connection held for the whole run span (ETL-INC-F04, D-14): ``"wait"``
        blocks then proceeds; ``"skip"`` returns a transient
        ``RunResult(status="skipped", run_id=None)`` writing no
        ``pipeline_runs`` row when the lock is held (D-13). Released in a
        ``finally``; the connection close auto-releases even on crash.

        Parameters
        ----------
        pipeline : Pipeline
            Fully specified pipeline descriptor.
        dry_run : bool, optional
            When ``True``, run extract + transform only and bypass the lock.

        Returns
        -------
        RunResult
            Immutable snapshot of the completed, dry-run, or skipped run.
        """
        if pipeline.concurrency is None or dry_run:
            return await self._run_impl(pipeline, dry_run=dry_run)
        async with self._db.connect(autocommit=True) as lock_conn:
            if pipeline.concurrency == "skip":
                async with lock_conn.cursor() as cur:
                    await cur.execute(queries.ETL_ADVISORY_TRY_LOCK, [pipeline.name])
                    row = await cur.fetchone()
                if not (row and row[0]):  # lock already held → transient skip (D-13)
                    now = datetime.now(UTC)
                    return RunResult(
                        run_id=None,
                        pipeline_name=pipeline.name,
                        status="skipped",
                        rows_extracted=0,
                        rows_loaded=0,
                        started_at=now,
                        finished_at=now,
                        error=None,
                    )
            else:  # "wait" → block until the peer releases
                async with lock_conn.cursor() as cur:
                    await cur.execute(queries.ETL_ADVISORY_LOCK, [pipeline.name])
            try:
                return await self._run_impl(pipeline, dry_run=dry_run)
            finally:
                try:
                    async with lock_conn.cursor() as cur:
                        await cur.execute(
                            queries.ETL_ADVISORY_UNLOCK, [pipeline.name]
                        )
                except Exception:  # pragma: no cover - defensive
                    pass

    async def _run_impl(
        self, pipeline: Pipeline, *, dry_run: bool = False
    ) -> RunResult:
        """Execute a full async extract → transform → load run (lock-unaware).

        Async mirror of :meth:`ETLAccessor._run_impl`.  All DB calls use
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

        **Extract:** delegates to :meth:`_do_extract` (watermark-filtered
        shared path — D-A2a) which in turn calls
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

        with log_operation("etl.run"):
            # ------------------------------------------------------------------
            # DRY-RUN EARLY FORK (D-08/D-09/ETL-15)
            # Forks before init/start_run — writes no pipeline_runs row.
            # ------------------------------------------------------------------
            if dry_run:
                started_at = datetime.now(UTC)
                rows_extracted = 0

                # Read prior watermark (None on first run or non-incremental) — D-A2
                dry_wm = (
                    await self._read_watermark(name)
                    if pipeline.incremental_column is not None
                    else None
                )
                # Seed-floor fallback (D-01): first-run seed, explicit is-None.
                if pipeline.incremental_column is not None and dry_wm is None:
                    dry_wm = cast(
                        "datetime | int | str | CompositeWatermark | None",
                        pipeline.initial_watermark,
                    )

                # Shared filtered extract (D-A2a) — same path as real run.
                # Lookback widens the READ floor here too so the dry-run
                # previews the same overlap window (D-06/D-07).
                dry_read_floor: datetime | int | str | CompositeWatermark | None = (
                    dry_wm
                )
                if pipeline.incremental_lookback is not None and dry_wm is not None:
                    if isinstance(dry_wm, tuple):
                        raise ETLError(
                            "incremental_lookback is not supported for a composite "
                            "watermark key (ETL-INC-F03); apply a lookback only to a "
                            "single-column watermark"
                        )
                    dry_read_floor = _apply_lookback(
                        dry_wm, pipeline.incremental_lookback
                    )
                df = await self._do_extract(pipeline, dry_read_floor)
                rows_extracted = len(df)

                # Capture would-be watermark from RAW filtered batch (D-A2).
                # Composite → the greatest sorted ROW (D-10); scalar → max(col);
                # any NaN element voids the watermark for this run (Pitfall 4).
                dry_raw_watermark: (
                    datetime | int | str | CompositeWatermark | None
                ) = _capture_watermark(df, pipeline.incremental_column)

                # Transform chain (same as normal path, but dispatched via to_thread — SC-2)
                transform = pipeline.transform
                steps: list[Any]
                if transform is None:
                    steps = []
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
                    watermark_used=dry_read_floor,
                    watermark_recorded=dry_raw_watermark,
                )

            await self.init()
            run_id = await self._start_run(name)
            rows_extracted = 0
            rows_loaded = 0

            # Read prior watermark before extract (None on first run or non-incremental)
            wm = (
                await self._read_watermark(name)
                if pipeline.incremental_column is not None
                else None
            )
            # Seed-floor fallback (D-01 / C-04): on the FIRST run (no stored
            # watermark) fall back to Pipeline.initial_watermark. Explicit
            # is-None — 0 is a valid floor (RESEARCH §F01), never a falsy check.
            # Consulted ONLY here; once a run records max(col) it is ignored.
            # Composite (Sequence) seeding is wired in 49-04 — F01 is scalar-only,
            # so the cast documents the narrowed scalar contract.
            if pipeline.incremental_column is not None and wm is None:
                wm = cast(
                    "datetime | int | str | CompositeWatermark | None",
                    pipeline.initial_watermark,
                )

            try:
                # ------------------------------------------------------------------
                # 1. EXTRACT (shared filtered path — D-A2a)
                # Lookback (D-06/D-07): widen the READ floor only — the recorded
                # watermark below stays the true max(col). A str-typed floor
                # cannot be adjusted → _apply_lookback raises ETLError at run
                # time. Overlap replay is a safe idempotent upsert no-op (D-08,
                # C-01): incremental requires upsert, so re-read rows ON CONFLICT.
                # ------------------------------------------------------------------
                read_floor: datetime | int | str | CompositeWatermark | None = wm
                if pipeline.incremental_lookback is not None and wm is not None:
                    if isinstance(wm, tuple):
                        raise ETLError(
                            "incremental_lookback is not supported for a composite "
                            "watermark key (ETL-INC-F03); apply a lookback only to a "
                            "single-column watermark"
                        )
                    read_floor = _apply_lookback(wm, pipeline.incremental_lookback)
                df = await self._do_extract(pipeline, read_floor)

                rows_extracted = len(df)

                # ------------------------------------------------------------------
                # 1b. INCREMENTAL WATERMARK CAPTURE (D-02 / D-06 / D-07 / ETL-INC-02)
                # Capture the recorded high-water mark from the RAW batch BEFORE
                # the transform chain (D-02: transforms may rename/drop columns).
                # Single-column → max(col); composite → the greatest sorted ROW
                # (D-10, NOT per-column maxes); any NaN element voids the
                # watermark for this run (Pitfall 4 / C-03). Coercion to plain
                # Python types keeps _encode_watermark's allowlist satisfied.
                # ------------------------------------------------------------------
                raw_watermark: datetime | int | str | CompositeWatermark | None = (
                    _capture_watermark(df, pipeline.incremental_column)
                )

                # ------------------------------------------------------------------
                # 2. TRANSFORM CHAIN (D-05 / D-06 / ETL-16)
                #    Each step dispatched via asyncio.to_thread (SC-2).
                # ------------------------------------------------------------------
                transform = pipeline.transform
                if transform is None:
                    steps = []
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
                # 3. ROWS: early-exit on empty + derive columns (D-02b / D-02c)
                # ------------------------------------------------------------------
                # No rows to load (empty extract, or transforms dropped every row):
                # record success with 0 rows_loaded and NO watermark — even if a
                # raw_watermark was captured above, a no-load run must not advance
                # the watermark.  The prior successful watermark is preserved by
                # ETL_GET_LAST_WATERMARK's `watermark IS NOT NULL` predicate.
                if df.empty:
                    await self._end_run(run_id, "success", rows_extracted, 0)
                    return await self._fetch_run_result(run_id)

                columns = list(df.columns)

                # Materialize rows as list[dict] only for upsert (INSERT … ON CONFLICT).
                # append/replace stream directly via COPY — no full-frame astype(object)
                # materialization needed (D-02 / D-02c / PERF-02).
                rows: list[dict[str, Any]]
                if pipeline.load_mode == "upsert":
                    # pandas types to_dict(orient="records") keys as Hashable;
                    # DataFrame columns are always str here (extracted via
                    # to_dataframe/SQL), so the runtime shape is dict[str, Any].
                    records = (
                        df.astype(object)
                        .where(pd.notnull(df), None)
                        .to_dict(orient="records")
                    )
                    rows = cast("list[dict[str, Any]]", records)
                else:
                    rows = []  # unused for append/replace COPY path

                # ------------------------------------------------------------------
                # 4. EXISTENCE CHECK (D-03)
                # ------------------------------------------------------------------
                exists = await self._db.schema.table_exists(
                    pipeline.target, schema=pipeline.schema
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
                        schema=pipeline.schema,
                        if_exists="replace",
                    )

                # ------------------------------------------------------------------
                # 5. BUILD LOAD SQL (pure builders — upsert only; COPY needs no INSERT SQL)
                # ------------------------------------------------------------------
                if pipeline.load_mode == "upsert":
                    insert_sql, insert_params = _build_upsert_sql(
                        pipeline.target,
                        rows,
                        list(pipeline.conflict_columns),
                        schema=pipeline.schema,
                    )
                elif pipeline.load_mode == "replace":
                    truncate_sql, _ = build_truncate_sql(
                        pipeline.target, pipeline.schema
                    )

                # append: no SQL builder — rows stream via COPY below

                # ------------------------------------------------------------------
                # 6. ATOMIC LOAD — async seam (RESEARCH §7 / SC-3 / D-02a)
                #    append/replace: COPY inline on the transaction cursor.
                #    upsert: INSERT … ON CONFLICT via execute() (D-02c).
                #    Never call copy_insert() here — it opens its own connection +
                #    commit, breaking run-log atomicity (D-02a / T-38-06).
                # ------------------------------------------------------------------
                async with self._db.session():
                    async with self._db.transaction() as conn:
                        async with conn.cursor() as cur:
                            if pipeline.load_mode == "replace":
                                await cur.execute(truncate_sql)
                            if pipeline.load_mode in ("append", "replace"):
                                rows_loaded += await _async_stream_df_copy(
                                    cur, df, pipeline.target, pipeline.schema, columns
                                )
                            else:  # upsert
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

            wm_env = (
                _encode_watermark_value(pipeline.incremental_column, raw_watermark)
                if raw_watermark is not None
                else None
            )
            await self._end_run(
                run_id, "success", rows_extracted, rows_loaded, watermark=wm_env
            )
            # Fetch the stored result (watermark_recorded comes via _row_to_result),
            # then inject watermark_used (per-run input, never stored — D-A1).
            result = await self._fetch_run_result(run_id)
            if wm is not None or pipeline.incremental_column is not None:
                result = dc_replace(result, watermark_used=read_floor)
            return result
