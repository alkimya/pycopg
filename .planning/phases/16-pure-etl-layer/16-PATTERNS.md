# Phase 16: Pure ETL Layer - Pattern Map

**Mapped:** 2026-06-14
**Files analyzed:** 5 (1 new module, 1 new test, 3 modified)
**Analogs found:** 5 / 5 (all exact / role-match)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pycopg/etl.py` (NEW) | module: dataclass + pure SQL builders | transform (pure, no I/O) | `pycopg/spatial.py` | exact (architectural template) |
| `pycopg/queries.py` (MODIFY) | config: SQL constants | transform (static SQL) | `pycopg/queries.py` itself (existing sections) | exact |
| `pycopg/exceptions.py` (MODIFY) | model: exception hierarchy | n/a | `pycopg/exceptions.py` itself (`ExtensionNotAvailable`, `TableNotFound`) | exact |
| `pycopg/__init__.py` (MODIFY) | config: export surface | n/a | `pycopg/__init__.py` itself (Spatial/Exceptions blocks) | exact |
| `tests/test_etl.py` (NEW) | test: DB-free unit tests | n/a | `tests/test_spatial.py` | exact |

> All analogs are current (the v0.4.0 spatial work is the most recently shipped module). No legacy variants exist; mirror `spatial.py` verbatim per D-13 / CONTEXT canonical refs.

---

## Pattern Assignments

### `pycopg/etl.py` (NEW — Pipeline dataclass + pure builders)

**Analog:** `pycopg/spatial.py` (THE template)

**1. Module docstring with security-invariant block** — copy the shape from `spatial.py:1-24`. The docstring MUST state: builders are stateless `(sql, params)` functions (no `self`, no I/O, no DB), shared byte-identical between sync/async accessors, fully unit-testable without a DB. Then a "Security invariants" bulleted block. Adapt to ETL:

```python
"""ETL pipeline descriptor and pure SQL builders.

This module provides the pure foundation of the (future) ``db.etl``
accessor namespace: the public ``Pipeline`` descriptor plus one
module-level SQL builder per ETL operation. Builders are stateless
functions returning ``(sql, params)`` tuples — no ``self``, no I/O,
no DB — so they are shared byte-identical between the sync and async
accessors and are fully unit-testable without a database.

Security invariants (v0.3.1, mirrored from spatial.py):

- Every identifier (table, schema, conflict columns) passes
  :func:`pycopg.utils.validate_identifiers` before any string
  interpolation.
- Every user value is emitted as a ``%s`` placeholder appended to the
  params list — never f-string interpolated.
"""
```

**2. Import block** — mirror `spatial.py:26-38` (note `from __future__ import annotations` first):

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pycopg.exceptions import ETLTargetNotFoundError, ETLTransformError  # as needed
from pycopg.utils import validate_identifiers
from pycopg import queries  # to reference ETL_INIT_PIPELINE_RUNS, etc.
```

**3. `Pipeline` frozen dataclass** (D-01/D-02/D-03/D-09/D-11). No existing dataclass analog in the lib — derive shape from CONTEXT decisions + numpydoc docstring style seen throughout `spatial.py`. Key invariants:
- `@dataclass(frozen=True)`.
- Flat fields: `name`, `source`, `target`, `load_mode` (default `"append"`), `conflict_columns: tuple[str, ...]` (default `()` — NO mutable list default on a frozen dataclass), `schema` (default `"public"`), `transform`, `extract_limit: int | None = None`.
- Validation in `__post_init__`: reject `load_mode` outside `{"append","replace","upsert"}` with `ValueError` (D-06); `upsert` without `conflict_columns` → `ValueError` (D-07). Because the dataclass is frozen, normalize a list→tuple via `object.__setattr__(self, "conflict_columns", tuple(...))`.
- `_VALID_LOAD_MODES` module constant mirrors the `_VALID_UNITS = ("m", "srid")` convention at `spatial.py:47`.

**4. ValueError validator style** — copy `_validate_unit` at `spatial.py:50-64`:

```python
_VALID_LOAD_MODES = ("append", "replace", "upsert")

def _validate_load_mode(load_mode: str) -> None:
    if load_mode not in _VALID_LOAD_MODES:
        raise ValueError(
            f"load_mode must be one of {_VALID_LOAD_MODES}, got {load_mode!r}"
        )
```

**5. Pure builder shape** (D-10: ship `build_init_sql()` + `build_truncate_sql()` only) — copy the exact body discipline of `build_within_sql` (`spatial.py:347-404`), the simplest no-geometry builder: `validate_identifiers(...)` FIRST, assemble with f-string interpolation of *validated identifiers only*, values as `%s`, return `(sql, list)`.

```python
def build_truncate_sql(table: str, schema: str = "public") -> tuple[str, list]:
    """Build TRUNCATE SQL for a replace-mode load target.

    Parameters
    ----------
    table : str
        Table to truncate.
    schema : str, optional
        Schema name, by default "public".

    Returns
    -------
    tuple of (str, list)
        SQL string and an (empty) parameter list.

    Raises
    ------
    InvalidIdentifier
        If any identifier is invalid.
    """
    validate_identifiers(table, schema)
    return f"TRUNCATE TABLE {schema}.{table}", []
```

`build_init_sql()` returns the idempotent `pipeline_runs` DDL (D-14/D-15). Since the DDL is a static `CREATE TABLE IF NOT EXISTS` with no user identifiers, the builder may simply return `(queries.ETL_INIT_PIPELINE_RUNS, [])` (optionally parameterizing schema, in which case `validate_identifiers(schema)` first). Note `spatial.py` builders that take no params still return `(sql, [])` — keep the `(sql, params)` contract uniform.

**6. numpydoc docstring blocks** — EVERY function/method/dataclass uses the Parameters / Returns / Raises numpydoc structure seen on every `spatial.py` builder (e.g. `spatial.py:202-245`). Decision tags like `(D-06)` inline in docstrings are the house style — reuse for ETL decisions.

---

### `pycopg/queries.py` (MODIFY — append ETL section)

**Analog:** the file's own existing sections (e.g. `SCHEMA QUERIES` at lines 8-22, `TIMESCALEDB QUERIES` at the tail).

**Banner style** (exact — 79-char `=` rule, blank line, constant):

```python
# =============================================================================
# ETL QUERIES
# =============================================================================

ETL_INIT_PIPELINE_RUNS = """
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        run_id BIGSERIAL PRIMARY KEY,
        pipeline_name TEXT NOT NULL,
        started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        finished_at TIMESTAMPTZ,
        status TEXT NOT NULL CHECK (status IN ('running','success','failed')),
        rows_extracted BIGINT,
        rows_loaded BIGINT,
        error_message TEXT,
        watermark JSONB
    )
"""
```

**Invariants for all 5 constants** (D-12/D-14):
- `ETL_INIT_PIPELINE_RUNS`: `CREATE TABLE IF NOT EXISTS` (idempotent, D-15); BIGSERIAL PK; `status TEXT ... CHECK (...)` NOT a PG ENUM (D-14); nullable `watermark JSONB` (D-14, always NULL in v0.5.0).
- `ETL_INSERT_RUN`, `ETL_UPDATE_RUN`, `ETL_LIST_RUNS`, `ETL_GET_LAST_RUN`: use `%s` placeholders, NO f-string identifier interpolation. Authored as constants here even though their *builders* land in phases 17-19 (D-10).
- **`%` literal escaping:** if any constant contains a literal `%` (e.g. `format('%%I.%%I', ...)` as seen in `HYPERTABLE_INFO` at the file tail), double it to `%%`. Plain ETL constants likely won't need this, but watch for `LIKE` patterns.

> Match the existing constant naming: SCREAMING_SNAKE_CASE, triple-quoted, leading newline + 4-space indented SQL body.

---

### `pycopg/exceptions.py` (MODIFY — ETL hierarchy, D-08)

**Analog:** the file's own existing subclasses `ExtensionNotAvailable` / `TableNotFound` (`exceptions.py:21-28`).

**Exact style** — single-line docstring, `pass` body, subclass the right base:

```python
class ETLError(PycopgError):
    """Base exception for ETL pipeline errors."""
    pass


class ETLTransformError(ETLError):
    """Error raised when a pipeline transform function fails."""
    pass


class ETLTargetNotFoundError(ETLError):
    """Error raised when an append-mode load target table is missing."""
    pass
```

Append after `DatabaseExists` (the current last class, `exceptions.py:41-44`). `ETLError` subclasses `PycopgError`; the two specific errors subclass `ETLError` (two-level hierarchy per D-08). Define all three NOW even though they fire in Phase 18 (single home, D-08/D-09 — no `PipelineError` wrapper).

---

### `pycopg/__init__.py` (MODIFY — exports; planner decides Phase 16 vs 20)

**Analog:** the file's own Spatial + Exceptions blocks (`__init__.py:10-22`, `35-64`).

Two edit sites, both alphabetized within their import group:

1. Extend the `from pycopg.exceptions import (...)` tuple (`__init__.py:10-19`) to add `ETLError`, `ETLTargetNotFoundError`, `ETLTransformError`.
2. Add the names to `__all__` under the `# Exceptions` comment block (`__init__.py:48-56`).

If/when `Pipeline` is exported (Phase 20 wires the accessor), add `from pycopg.etl import Pipeline` and a `# ETL` group in `__all__` mirroring the `# Spatial` group at lines 45-47. **Planner decision (D, CONTEXT line 154-155):** exception exports MAY land in Phase 16; `Pipeline`/accessor exports defer to Phase 20.

---

### `tests/test_etl.py` (NEW — DB-free unit tests)

**Analog:** `tests/test_spatial.py:1-95`

The success-criterion #4 pattern (importable, unit-testable with NO DB connection). Copy structure:
- Module docstring noting "DB-free builder tests" (`test_spatial.py:1`).
- Direct imports of builders + exceptions from the module (`test_spatial.py:7-24`).
- Test classes grouping concerns: `TestPipeline` (construction + `__post_init__` ValueError cases — `pytest.raises(ValueError, match=...)`), `TestBuilders` (exact SQL string + params assertions).
- **Exact-string assertions** are the house style (`test_spatial.py:87-94`):

```python
def test_truncate_sql(self):
    sql, params = build_truncate_sql("events")
    assert sql == "TRUNCATE TABLE public.events"
    assert params == []

def test_truncate_invalid_table(self):
    with pytest.raises(InvalidIdentifier):
        build_truncate_sql("bad-name")
```

- Validation tests mirror `test_spatial.py:56-69`: bad identifier → `InvalidIdentifier`; bad `load_mode`/missing `conflict_columns` → `ValueError`. NO DB fixture, NO `db.execute`.

---

## Shared Patterns

### Identifier validation gate (THE load-bearing invariant)
**Source:** `pycopg/utils.py:76-91` (`validate_identifiers(*names)`)
**Apply to:** every ETL builder, before any interpolation (D-13).
```python
def validate_identifiers(*names: str) -> None:
    for name in names:
        if name is not None:
            validate_identifier(name)
```
Builders interpolate ONLY validated identifiers into f-strings (`{schema}.{table}`); all user values go to the `%s` params list. Mirrors every `spatial.py` builder (e.g. `spatial.py:246`, `395`, `473`).

### `(sql, params)` return contract
**Source:** all `spatial.py` builders (e.g. `build_within_sql` at `spatial.py:347-404`)
**Apply to:** `build_init_sql`, `build_truncate_sql`, and all future ETL builders. Always return a 2-tuple, params is a `list` (empty list, not `None`, when there are no values).

### Module-constant + `_validate_*` helper convention
**Source:** `spatial.py:47-64` (`_VALID_UNITS` + `_validate_unit`)
**Apply to:** `_VALID_LOAD_MODES` + `_validate_load_mode` in `etl.py`; reuse for the `__post_init__` check.

### numpydoc docstrings + inline decision tags
**Source:** every callable in `spatial.py` (Parameters / Returns / Raises) and the project numpydoc convention.
**Apply to:** every ETL function, the `Pipeline` dataclass, and its `__post_init__`.

---

## No Analog Found

| File | Role | Reason |
|------|------|--------|
| `Pipeline` dataclass (within `etl.py`) | frozen descriptor | No existing `@dataclass(frozen=True)` in the lib. `config.py` `Config` is dataclass-style but a factory, not frozen. Derive from CONTEXT D-01/D-02 + numpydoc style; the `frozen=True` / `tuple` conventions come from research `ARCHITECTURE.md` Pattern 2 (use only the frozen/tuple bits, NOT the rejected nested ExtractSpec/LoadSpec — D-01). |

---

## Metadata

**Analog search scope:** `pycopg/` (spatial.py, queries.py, exceptions.py, utils.py, __init__.py), `tests/`
**Files scanned:** 7
**Pattern extraction date:** 2026-06-14
