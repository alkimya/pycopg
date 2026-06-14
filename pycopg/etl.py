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

from collections.abc import Callable
from dataclasses import dataclass

from pycopg import queries
from pycopg.exceptions import ETLTargetNotFoundError, ETLTransformError  # noqa: F401
from pycopg.utils import validate_identifiers

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

    Raises
    ------
    ValueError
        If ``load_mode`` is not one of the accepted values (D-06).
    ValueError
        If ``load_mode="upsert"`` and ``conflict_columns`` is empty (D-07).
    ValueError
        If ``extract_limit`` is a non-positive integer (D-11, Claude's
        Discretion guard — prevents silent OOM misdirection).

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

    def __post_init__(self) -> None:
        """Validate and normalize fields at construction time.

        Raises
        ------
        ValueError
            If ``conflict_columns`` is passed as a bare string,
            ``load_mode`` is invalid (D-06), ``upsert`` is requested
            without ``conflict_columns`` (D-07), or ``extract_limit`` is
            not a positive integer (D-11).
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
