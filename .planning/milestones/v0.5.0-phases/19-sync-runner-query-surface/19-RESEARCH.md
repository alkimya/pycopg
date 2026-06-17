# Phase 19: Sync Runner & Query Surface — Research

**Researched:** 2026-06-15
**Domain:** pycopg ETL return/query layer — `RunResult`, `run()` upgrade, `history()`, `last_run()`, `dry_run`
**Confidence:** HIGH (all findings sourced directly from the live codebase)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `RunResult` is `@dataclass(frozen=True)` mirroring `Pipeline` (`etl.py:70`).
- **D-02:** `RunResult` carries exactly 8 fields: `run_id`, `pipeline_name`, `status`, `rows_extracted`, `rows_loaded`, `started_at`, `finished_at`, `error`. No speculative fields.
- **D-03:** `error` is `str | None` — populated from `pipeline_runs.error_message`. `error_traceback` stays DB-only. No wrapping.
- **D-04:** No `watermark` field on `RunResult` this phase. Always NULL; surfacing is v0.6.0.
- **D-05:** `run_id` is `int | None` — `None` for dry runs (no DB row), `int` for persisted runs.
- **D-06:** `history(name: str, limit: int = 100) -> list[RunResult]`. Backed by `ETL_LIST_RUNS`; newest-first (`started_at DESC`). Do not re-author the SQL.
- **D-07:** `last_run(name: str) -> RunResult | None`. Returns most recent or `None` when no runs exist. Whether it delegates to `history(name, limit=1)` or runs `ETL_GET_LAST_RUN` directly is Claude's discretion.
- **D-08:** `dry_run=True` → extract + transform, skip load, write no `pipeline_runs` row, return `RunResult(status='dry_run', rows_loaded=0, run_id=None, rows_extracted=len(df), started_at/finished_at=in-memory UTC bracket, error=None, pipeline_name=pipeline.name)`.
- **D-09:** Dry-run branch never enters the Phase 18 run-log/load bracketing. No `'running'` row can be left behind.
- **D-10:** Single mapper `_row_to_result(row: dict) -> RunResult` — module-level pure function in `etl.py` (peer of `_build_insert_sql`, `_step_label`). Maps `error_message → error`, drops `error_traceback` and `watermark`.
- **D-11:** `run()` returns by re-SELECTing the row it just wrote, by `run_id`, after `_end_run`. One source of truth, one mapper. A new `run_id`-keyed SELECT constant is likely needed (existing constants filter by `pipeline_name`).
- **D-12:** `history()` and `last_run()` build `RunResult`(s) from `pipeline_runs` rows via the same `_row_to_result` mapper.

### Claude's Discretion

- Whether `last_run` delegates to `history(name, limit=1)` or runs `ETL_GET_LAST_RUN` directly (D-07).
- The SELECT-by-`run_id` constant name and exact SQL for D-11's re-SELECT (lean toward `run_id`-keyed for correctness under concurrent runs).
- Whether `Pipeline`/`RunResult` are exported in `__init__.py` now or deferred to Phase 20.
- Field ordering inside `RunResult` and exact type hints for timestamps (`datetime`).
- Whether `status` is annotated as plain `str` or `Literal['running','success','failed','dry_run']`.

### Deferred Ideas (OUT OF SCOPE)

- `watermark` on `RunResult` — v0.6.0.
- `Literal` status type / 4th persisted status.
- Public `__init__.py` export of `Pipeline`/`RunResult`/`ETLAccessor` — Phase 20 (pull forward only if a test imports from the package root).
- `AsyncETLAccessor` parity, `TestEtlParity`, Sphinx docs, coverage ratchet, v0.5.0 release — Phase 20.
- Paging beyond `history(limit=)`.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ETL-10 | `db.etl.run(pipeline)` returns a `RunResult` carrying `run_id`, `pipeline_name`, `status`, `rows_extracted`, `rows_loaded`, `started_at`, `finished_at`, and `error`. | `RunResult` dataclass + `_row_to_result` mapper + re-SELECT after `_end_run` (D-11). Current `run()` returns bare `int run_id` at line 781. |
| ETL-11 | `db.etl.history("my_pipeline")` returns a list of `RunResult` for that pipeline, newest-first. | `ETL_LIST_RUNS` already exists (`queries.py:281`); `history()` binds `(name, limit)` to it and maps via `_row_to_result`. |
| ETL-15 | `run(pipeline, dry_run=True)` executes extract + transform but skips load and writes no run record; returns `RunResult(status='dry_run', rows_loaded=0)`. | `dry_run` branch forks before `init()`/`_start_run()` (lines 641–642); in-memory `RunResult` built per D-08. |
| ETL-17 | `db.etl.last_run("my_pipeline")` fetches the most recent `RunResult` (or `None`) — sugar over `history()`. | `ETL_GET_LAST_RUN` already exists (`queries.py:289`); or delegates to `history(name, limit=1)`. |
</phase_requirements>

---

## Summary

Phase 19 is a **thin, composition-only layer** over the hardened Phase 17/18 ETL machinery. The existing `ETLAccessor.run()` in `pycopg/etl.py` (lines 579–781) already does the full extract→transform→load cycle and records `pipeline_runs` rows correctly. Its only gap is that it returns a bare `int run_id` (line 781) and accepts no `dry_run` parameter. Phase 19 adds: (1) a `RunResult` frozen dataclass, (2) a `_row_to_result` pure mapper function, (3) a `dry_run=False` parameter with a clean early branch before the run-log writes at lines 641–642, (4) a re-SELECT of the row by `run_id` after `_end_run` (D-11), (5) `history()` and `last_run()` methods that read `pipeline_runs` via already-authored SQL constants, and (6) a new `ETL_GET_RUN` constant (SELECT by `run_id`) in `queries.py`.

**No Phase 17/18 write paths change.** The `init()`/`_start_run()`/`_end_run()` calls (lines 641–642, 769–778, 780) are untouched. The atomic load block (lines 761–767) is untouched. Only the signature, the early `dry_run` fork, and the return statement change.

**Primary recommendation:** One plan is sufficient. The work is small: ~35 lines of new production code (`RunResult`, `_row_to_result`, one new query constant, three method changes). Write `RunResult` + mapper + `ETL_GET_RUN` first (DB-free, unit-testable), then upgrade `run()` + add `history()` + `last_run()`, then integration-test all four SC-*.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `RunResult` dataclass | `pycopg/etl.py` (module-level) | — | Pure value object, no I/O; lives next to `Pipeline` and the other module-level builders |
| `_row_to_result` mapper | `pycopg/etl.py` (module-level) | — | Pure function, DB-free, unit-testable; peers with `_build_insert_sql`, `_step_label` |
| `ETL_GET_RUN` constant | `pycopg/queries.py` | — | Joins the existing ETL QUERIES block; `%s`-parameterized, no identifier interpolation |
| `run()` return upgrade | `ETLAccessor` (method body) | `pycopg/queries.py` | Uses `ETL_GET_RUN`; reads via autocommit conn (or reuses the pattern from `init`/`_start_run`) |
| `dry_run` branch | `ETLAccessor.run()` (method body) | — | Early fork before line 641 (`self.init()`); builds `RunResult` in-memory |
| `history()` | `ETLAccessor` (new method) | `pycopg/queries.py` | Reads `pipeline_runs` via `ETL_LIST_RUNS`; maps rows through `_row_to_result` |
| `last_run()` | `ETLAccessor` (new method) | `pycopg/queries.py` | Reads via `ETL_GET_LAST_RUN` (or delegates to `history(name, limit=1)`); returns `RunResult | None` |

---

## Standard Stack

### Core (no new packages)

Phase 19 introduces **zero new runtime dependencies** (v0.5.0 constraint, REQUIREMENTS.md Out-of-Scope table). All imports needed are already present in `etl.py`.

| Symbol | Already Imported In | Purpose in Phase 19 |
|--------|---------------------|----------------------|
| `@dataclass(frozen=True)` | `etl.py:29` | `RunResult` definition |
| `datetime`, `UTC` | `etl.py:30` | `started_at`/`finished_at` in dry-run branch |
| `dict_row` (from `psycopg.rows`) | `etl.py:34` | Cursor row factory for re-SELECT + `history`/`last_run` reads |
| `queries` (module) | `etl.py:36` | `ETL_LIST_RUNS`, `ETL_GET_LAST_RUN`, new `ETL_GET_RUN` |

### Package Legitimacy Audit

> No new packages are installed. The `## Package Legitimacy Audit` section is not applicable — Phase 19 is a zero-dependency change.

---

## Architecture Patterns

### System Architecture Diagram

```
db.etl.run(pipeline, dry_run=False)
  │
  ├─[dry_run=True]─────────────────────────────────────────────────────────────┐
  │  Extract (to_dataframe)                                                     │
  │  Transform chain (same as normal)                                           │
  │  Build RunResult in-memory                                                  │
  │    status='dry_run', run_id=None, rows_loaded=0,                           │
  │    rows_extracted=len(df), started_at/finished_at=datetime.now(UTC)        │
  │  Return RunResult ──────────────────────────────────────────────────────────┤
  │                                                                              │
  └─[dry_run=False]────────────────────────────────────────────────────────────┐
     init() [autocommit conn → CREATE TABLE IF NOT EXISTS]                     │
     _start_run(name) → run_id [autocommit conn → INSERT RETURNING]            │
     Extract (to_dataframe)                                                     │
     Transform chain                                                            │
     Atomic load [session + transaction + conn.cursor]                          │
     _end_run(run_id, 'success'|'failed', ...) [autocommit conn → UPDATE]      │
     Re-SELECT pipeline_runs WHERE run_id = %s [autocommit conn, dict_row]    │
     _row_to_result(row) → RunResult                                           │
     Return RunResult ──────────────────────────────────────────────────────────┤
                                                                                │
db.etl.history(name, limit=100)                                                 │
  ├── SELECT * FROM pipeline_runs WHERE pipeline_name = %s                      │
  │   ORDER BY started_at DESC LIMIT %s  [ETL_LIST_RUNS, autocommit conn]      │
  ├── [_row_to_result(row) for row in rows]                                    │
  └── Return list[RunResult]                                                    │
                                                                                │
db.etl.last_run(name)                                                           │
  ├── ETL_GET_LAST_RUN  OR  history(name, limit=1)                             │
  └── Return RunResult | None                                                   │
                                                                                │
_row_to_result(row: dict) ─── pure, DB-free ──────────────────────────────────┘
  maps: run_id, pipeline_name, status, rows_extracted, rows_loaded,
        started_at, finished_at, error_message→error
  drops: error_traceback, watermark
```

### Recommended Project Structure

No new files. All additions are in:
```
pycopg/
├── etl.py          # RunResult dataclass (after Pipeline), _row_to_result function,
│                   # ETLAccessor.run() signature + dry_run branch + return upgrade,
│                   # ETLAccessor.history(), ETLAccessor.last_run()
└── queries.py      # ETL_GET_RUN constant (new, in ETL QUERIES block)

tests/
└── test_etl_accessor.py  # Phase 19 integration tests (new class + pure unit test)
```

---

## Exact Current Shape of `ETLAccessor.run()` (Source of Truth)

**File:** `pycopg/etl.py`, **lines 579–781** (782 total lines in file).

### Current signature (line 579):
```python
def run(self, pipeline: Pipeline) -> int:
```

### Structure of `run()` body with precise seam locations:

| Lines | Block | Phase 19 action |
|-------|-------|-----------------|
| 579 | `def run(self, pipeline: Pipeline) -> int:` | Change to `run(self, pipeline: Pipeline, dry_run: bool = False) -> RunResult:` |
| 641 | `self.init()` | **Dry-run fork point** — insert `if dry_run: ... return RunResult(...)` BEFORE this line |
| 642 | `run_id = self._start_run(name)` | Untouched (only reached when not dry_run) |
| 643–644 | `rows_extracted = 0` / `rows_loaded = 0` | Untouched |
| 646–711 | Extract block (1. EXTRACT) | Untouched |
| 678 | `rows_extracted = len(df)` | Value available for dry-run RunResult |
| 680–698 | Transform chain (2. TRANSFORM) | Untouched |
| 700–705 | NaN/NaT coercion (3. ROWS) | Untouched |
| 707–710 | Empty-DataFrame early return `return run_id` | Must be changed to `return <re-SELECT result>` |
| 712 | `columns = list(rows[0].keys())` | Untouched |
| 714–723 | Existence check (4. EXISTENCE CHECK) | Untouched |
| 725–751 | Load SQL builders (5. BUILD LOAD SQL) | Untouched |
| 761–767 | Atomic load block (6. ATOMIC LOAD) | Untouched |
| 769–778 | Exception handler → `_end_run('failed')` + `raise` | Untouched |
| 780 | `self._end_run(run_id, 'success', rows_extracted, rows_loaded)` | Untouched |
| 781 | `return run_id` | **Change to re-SELECT + `_row_to_result` + return `RunResult`** |

### The two seams Phase 19 needs:

**Seam A — dry_run fork (before line 641):**
```python
name = pipeline.name
# INSERT dry_run branch here — before any run-log write:
if dry_run:
    started_at = datetime.now(UTC)
    # ... extract + transform (same as normal path) ...
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
self.init()            # line 641 — only reached if not dry_run
run_id = self._start_run(name)  # line 642
```

**Seam B — return upgrade (line 781 + empty-DataFrame path at line 707–710):**
```python
# After _end_run at line 780 — replace "return run_id":
with self._db.connect(autocommit=True) as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(queries.ETL_GET_RUN, [run_id])
        row = cur.fetchone()
return _row_to_result(row)

# Also fix the empty-DataFrame early return at lines 707-710:
if not rows:
    self._end_run(run_id, "success", rows_extracted, 0)
    # --- was: return run_id --- now:
    with self._db.connect(autocommit=True) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(queries.ETL_GET_RUN, [run_id])
            row = cur.fetchone()
    return _row_to_result(row)
```

**Note on the exception handler (lines 769–778):** The `raise` at line 778 re-raises immediately — no `RunResult` needed on the failure path (the exception propagates to the caller, who never sees a return value).

---

## Existing Query Constants (Source of Truth)

**File:** `pycopg/queries.py`, **lines 246–295**.

### `ETL_LIST_RUNS` (lines 281–287):
```sql
SELECT *
FROM pipeline_runs
WHERE pipeline_name = %s
ORDER BY started_at DESC
LIMIT %s
```
Binds: `(pipeline_name, limit)`. Correct for `history()` — newest-first, two `%s` params.

### `ETL_GET_LAST_RUN` (lines 289–295):
```sql
SELECT *
FROM pipeline_runs
WHERE pipeline_name = %s
ORDER BY started_at DESC
LIMIT 1
```
Binds: `(pipeline_name,)`. Correct for `last_run()` — one row or empty result.

### `ETL_GET_RUN` — **DOES NOT EXIST YET, must be added:**
Neither `ETL_LIST_RUNS` nor `ETL_GET_LAST_RUN` can serve D-11 safely, because both filter by `pipeline_name`. Under Phase 17 D-06 (no concurrency guard — left-`running` row is honest), two concurrent runs of the same pipeline could interleave: `_end_run(run_id_A)` finishes just as run B also completes, and `WHERE pipeline_name = %s ORDER BY started_at DESC LIMIT 1` could return run B's row.

**Must add to `queries.py` in the ETL QUERIES block:**
```python
ETL_GET_RUN = """
    SELECT *
    FROM pipeline_runs
    WHERE run_id = %s
"""
```
Binds: `(run_id,)`. One row guaranteed (BIGSERIAL PK). No `LIMIT` needed.

### `pipeline_runs` column list (from `ETL_INIT_PIPELINE_RUNS`, lines 249–262):
```
run_id           BIGSERIAL PRIMARY KEY
pipeline_name    TEXT NOT NULL
started_at       TIMESTAMPTZ NOT NULL DEFAULT now()
finished_at      TIMESTAMPTZ
status           TEXT NOT NULL CHECK (status IN ('running','success','failed'))
rows_extracted   BIGINT
rows_loaded      BIGINT
error_message    TEXT
error_traceback  TEXT
watermark        JSONB
```

**`_row_to_result` column-to-field mapping:**
| `pipeline_runs` column | `RunResult` field | Notes |
|------------------------|-------------------|-------|
| `run_id` | `run_id` | `int` from BIGSERIAL |
| `pipeline_name` | `pipeline_name` | `str` |
| `status` | `status` | `str`: `'running'`/`'success'`/`'failed'` |
| `rows_extracted` | `rows_extracted` | `int` (BIGINT → Python int) |
| `rows_loaded` | `rows_loaded` | `int` (BIGINT → Python int) |
| `started_at` | `started_at` | `datetime` (TIMESTAMPTZ → tz-aware datetime) |
| `finished_at` | `finished_at` | `datetime` |
| `error_message` | `error` | Rename; `None` on success |
| `error_traceback` | *(dropped)* | Not on `RunResult` (D-03) |
| `watermark` | *(dropped)* | Not on `RunResult` (D-04) |

**psycopg type coercions:** psycopg3 automatically coerces `TIMESTAMPTZ` to `datetime` with `tzinfo=UTC`. The `dict_row` factory returns a plain `dict` so `row['started_at']` is already a tz-aware `datetime` — no manual conversion needed. `BIGINT` becomes Python `int`. `TEXT` becomes `str` or `None`.

---

## `dict_row` Pattern Already in `etl.py`

The `dict_row` cursor pattern is used in three places already:

- `init()` — line 491: `with conn.cursor(row_factory=dict_row) as cur:`
- `_start_run()` — line 515: `with conn.cursor(row_factory=dict_row) as cur:`
- `_end_run()` — line 565: `with conn.cursor(row_factory=dict_row) as cur:`

Import already at line 34: `from psycopg.rows import dict_row`

**The pattern `history()` and `last_run()` should follow:**
```python
def history(self, name: str, limit: int = 100) -> list[RunResult]:
    with self._db.connect(autocommit=True) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(queries.ETL_LIST_RUNS, [name, limit])
            rows = cur.fetchall()
    return [_row_to_result(row) for row in rows]

def last_run(self, name: str) -> RunResult | None:
    with self._db.connect(autocommit=True) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(queries.ETL_GET_LAST_RUN, [name])
            row = cur.fetchone()
    return _row_to_result(row) if row is not None else None
```

The re-SELECT in `run()` (D-11) uses the identical pattern with `ETL_GET_RUN`.

---

## Module-Level Pure-Builder Precedent

Current module-level functions in `etl.py` (in order of definition):

| Lines | Function | DB-free? |
|-------|----------|----------|
| 50–67 | `_validate_load_mode(load_mode)` | Yes |
| 202–226 | `_is_sql_source(source)` | Yes |
| 229–258 | `build_truncate_sql(table, schema)` | Yes |
| 261–288 | `build_init_sql()` | Yes |
| 291–353 | `_build_insert_sql(table, columns, rows, schema, on_conflict)` | Yes |
| 356–411 | `_build_upsert_sql(table, rows, conflict_columns, update_columns, schema)` | Yes |
| 414–440 | `_step_label(fn)` | Yes |
| 443–782 | `class ETLAccessor` | (class) |

**`_row_to_result` joins as a peer pure function, placed after `_step_label` and before `class ETLAccessor`.** `RunResult` dataclass should be placed right after `Pipeline` (line 70) since it is the other public value object.

**`RunResult` frozen-dataclass idiom (mirrors `Pipeline` at lines 70–199):**
```python
@dataclass(frozen=True)
class RunResult:
    """Immutable snapshot of a completed (or dry-run) ETL pipeline run."""
    run_id: int | None
    pipeline_name: str
    status: str
    rows_extracted: int
    rows_loaded: int
    started_at: datetime
    finished_at: datetime
    error: str | None
```
No `__post_init__` needed (D-02 says no validation on `RunResult`). The `datetime` type hint is already imported at line 30 (`from datetime import UTC, datetime`). `int | None` uses the same `from __future__ import annotations` style already at line 25.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Timestamp coercion from DB | Manual `datetime.fromisoformat()` parsing | `dict_row` + psycopg3 native coercion | psycopg3 automatically converts `TIMESTAMPTZ` to tz-aware `datetime` |
| Pipeline name filtering in history | Manual Python-side filter after fetching all rows | `ETL_LIST_RUNS` WHERE clause | The constant already filters by `pipeline_name` at the DB level |
| re-SELECT via `pipeline_name` | `ETL_GET_LAST_RUN` for D-11 | New `ETL_GET_RUN` keyed on `run_id` | `pipeline_name`-keyed SELECT is unsafe under concurrent runs (D-11 rationale) |
| DB-backed dry-run record | Insert then immediately delete | No row at all (D-08) | `dry_run` is never persisted; build `RunResult` in-memory only |

**Key insight:** The DB machinery (Phase 17/18) is correct and complete. Phase 19's job is to read back what the DB stored, not to re-compute values. The single mapper `_row_to_result` is the anti-drift guarantee.

---

## Common Pitfalls

### Pitfall 1: Dry-run branch placed AFTER `_start_run`
**What goes wrong:** A `'running'` row is written to `pipeline_runs` and never `_end_run`'d. The row is committed (autocommit), permanently stuck as `status='running'`.
**Why it happens:** Misreading the D-09 contract — the dry-run branch must fork BEFORE `self.init()` at line 641, not after.
**How to avoid:** The fork is the very first action after `name = pipeline.name` (line 640). The pattern is:
```python
name = pipeline.name
if dry_run:
    ... # extract + transform only
    return RunResult(...)
self.init()         # ← only reached if not dry_run
run_id = ...
```
**Warning signs:** Test for SC-4 ("writes no row to `pipeline_runs`") fails — row count > 0 after a dry run.

### Pitfall 2: Forgetting the empty-DataFrame early return path
**What goes wrong:** The `run()` method has an early return at lines 707–710 for the `not rows` case. If this is not updated to return a `RunResult`, the return type is inconsistent (`int` on the empty-df path, `RunResult` otherwise).
**How to avoid:** Search for ALL `return run_id` occurrences in `run()` and update every one. There are exactly two: line 710 (empty-df path) and line 781 (normal success path).
**Warning signs:** `mypy` type error on the `int | RunResult` inconsistency; integration test with empty source returns wrong type.

### Pitfall 3: Using `ETL_GET_LAST_RUN` for the D-11 re-SELECT
**What goes wrong:** `WHERE pipeline_name = %s ORDER BY started_at DESC LIMIT 1` returns the WRONG row if two concurrent runs of the same pipeline finish in close succession.
**Why it happens:** Both the D-11 rationale and Phase 17 D-06 (no concurrency guard, left-`running` row is honest) accept concurrent runs. The re-SELECT must be keyed on the specific `run_id` returned by `_start_run`.
**How to avoid:** Add `ETL_GET_RUN = "SELECT * FROM pipeline_runs WHERE run_id = %s"` and use it.

### Pitfall 4: `_row_to_result` accessing wrong key names
**What goes wrong:** `dict_row` returns the actual column names from `pipeline_runs`. The mapper must use exactly the column names from `ETL_INIT_PIPELINE_RUNS`. Typos like `row['error']` (instead of `row['error_message']`) produce `KeyError` at runtime.
**How to avoid:** The rename is `error_message → error` (field rename, not column rename). Always use `row['error_message']` inside `_row_to_result`, not `row['error']`.

### Pitfall 5: Using `SELECT *` → field-order dependency
**What goes wrong:** `SELECT *` returns columns in table-definition order. If `pipeline_runs` schema changes (unlikely, but possible), the mapping breaks silently.
**Why it's acceptable here:** `dict_row` returns a dict keyed by column name, so order is irrelevant. `SELECT *` is safe with `dict_row`.

### Pitfall 6: `history()` opening a load-path connection vs. a clean read connection
**What goes wrong:** `history()` and `last_run()` are read-only queries. Using `self._db.execute()` (session-aware) could join an active session transaction and see uncommitted data.
**How to avoid:** Follow the same dedicated-autocommit-connection pattern as `init()`/`_start_run()`/`_end_run()` — `with self._db.connect(autocommit=True) as conn: ...`. This is already the established pattern in `etl.py`.

---

## Code Examples

### `RunResult` definition
```python
# Source: etl.py — after Pipeline class, before _is_sql_source (place ~line 202)
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
        ``'dry_run'`` (transient, never stored, D-07).
    rows_extracted : int
        Rows read from the source (after transform for dry runs).
    rows_loaded : int
        Rows written to the target; 0 for dry runs and failed runs.
    started_at : datetime
        UTC timestamp when the run started.
    finished_at : datetime
        UTC timestamp when the run ended.
    error : str or None
        Short error message from ``pipeline_runs.error_message``; ``None``
        on success or dry run (D-03).
    """
    run_id: int | None
    pipeline_name: str
    status: str
    rows_extracted: int
    rows_loaded: int
    started_at: datetime
    finished_at: datetime
    error: str | None
```

### `_row_to_result` mapper
```python
# Source: etl.py — after _step_label, before class ETLAccessor
def _row_to_result(row: dict) -> RunResult:
    """Map a ``dict_row`` from ``pipeline_runs`` to a :class:`RunResult`.

    Pure function — no I/O, no ``self``. Maps ``error_message → error``
    and drops ``error_traceback`` and ``watermark`` (D-10).

    Parameters
    ----------
    row : dict
        A row from ``pipeline_runs`` fetched with the ``dict_row`` factory.

    Returns
    -------
    RunResult
        Immutable snapshot of the run.
    """
    return RunResult(
        run_id=row["run_id"],
        pipeline_name=row["pipeline_name"],
        status=row["status"],
        rows_extracted=row["rows_extracted"],
        rows_loaded=row["rows_loaded"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        error=row["error_message"],
    )
```

### `ETL_GET_RUN` constant
```python
# Source: queries.py — add in ETL QUERIES block after ETL_GET_LAST_RUN
ETL_GET_RUN = """
    SELECT *
    FROM pipeline_runs
    WHERE run_id = %s
"""
```

---

## State of the Art

| Old Approach | Current Approach | Impact on Phase 19 |
|--------------|------------------|--------------------|
| `run() -> int` (bare run_id, Phase 17–18 stub) | `run() -> RunResult` | The only caller contract change — all existing tests that check `isinstance(run_id, int)` must be updated |
| No query surface (Phase 17–18) | `history()` + `last_run()` | New methods; no conflict with existing code |
| No `dry_run` (Phase 17–18) | `dry_run=True` short-circuits before run-log | `dry_run` was always deferred; no existing code to update |

**Deprecated / changed:**

- `test_run_accepts_pipeline_object` in `tests/test_etl_accessor.py` (line 451–459): currently asserts `isinstance(run_id, int)`. Must be updated to assert `isinstance(result, RunResult)`.
- `test_run_derives_pipeline_name_from_pipeline` (lines 461–475): re-reads from `pipeline_runs` by `run_id` — still valid but the `run_id` is now `result.run_id`.
- `test_run_writes_full_row` in `TestETLAccessorIntegration` (lines 231–257): asserts `isinstance(run_id, int)` at line 243. Must be updated.
- `test_first_run_auto_creates` (lines 207–229): calls `db.etl.run(p)` without capturing the return — no change needed.
- `test_rows_extracted_recorded` (lines 526–541): captures `run_id = db.etl.run(p)` — must become `result = db.etl.run(p)`, then `result.run_id` for the SELECT.
- Any test that does `run_id = db.etl.run(p)` and passes it as a raw int to `db.execute("... WHERE run_id = %s", [run_id])` — must use `result.run_id` instead.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | (None) | — | — |

**All claims in this research were verified directly from the live source files.** No training-data assumptions were made.

---

## Open Questions

1. **Empty-DataFrame path (lines 707–710) — helper or inline?**
   - What we know: There are two places that return from `run()` on the success path: the empty-df early exit (line 710) and the normal path (line 781). Both must now return `RunResult` from a re-SELECT.
   - What's unclear: Whether to extract a small `_fetch_run_result(run_id)` helper to avoid duplicating the re-SELECT block, or keep it inline twice.
   - Recommendation: Extract a private `_fetch_run_result(self, run_id: int) -> RunResult` helper. Keeps both return sites DRY and makes the pattern explicit.

2. **`last_run` — direct query or delegate to `history`?**
   - What we know: Both `ETL_GET_LAST_RUN` and `history(name, limit=1)` produce an equivalent result. `ETL_GET_LAST_RUN` is marginally cheaper (one fewer Python list allocation). `history(name, limit=1)` is shorter to write.
   - What's unclear: No strong technical reason to prefer one.
   - Recommendation: Use `ETL_GET_LAST_RUN` directly (Claude's discretion — dedicated constant, slightly cleaner, avoids the `[0]` index-or-empty idiom).

3. **Updating existing test assertions for `run() -> RunResult`:**
   - What we know: `test_run_accepts_pipeline_object` (line 459) asserts `isinstance(run_id, int)` — will fail after the return-type change. `test_run_writes_full_row` (line 243) captures `run_id = db.etl.run(p)`.
   - What's unclear: How many tests in `test_etl_accessor.py` need updating.
   - Recommendation: The planner should include a task to audit and update all `db.etl.run()` callers in the test file. A grep for `run_id = db.etl.run` and `isinstance(run_id, int)` finds all sites.

---

## Environment Availability

Step 2.6: All ETL tests run against the live `pycopg_test` PostgreSQL database with the `dict_row` pattern and psycopg3 — all available and used in Phase 17/18 tests. No new external dependencies. SKIPPED beyond that.

---

## Validation Architecture

`workflow.nyquist_validation` key is absent from `.planning/config.json` → treated as **enabled**.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (configured in `pyproject.toml`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_etl_accessor.py tests/test_etl.py -x -q -o addopts=""` |
| Full suite command | `uv run pytest` (coverage gate: `--cov-fail-under=94`) |

**Known caveat:** Three pre-existing full-suite DB tests are flaky in the local env. For targeted ETL runs always use `-o addopts=""` to strip the coverage/HTML flags from the invocation.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ETL-10 (SC-1) | `run()` returns `RunResult` with all 8 fields | integration | `uv run pytest tests/test_etl_accessor.py -k "test_run_returns_run_result" -x -o addopts=""` | ❌ Wave 0 |
| ETL-11 (SC-2) | `history()` newest-first, two runs → two entries | integration | `uv run pytest tests/test_etl_accessor.py -k "test_history" -x -o addopts=""` | ❌ Wave 0 |
| ETL-17 (SC-3) | `last_run()` returns most-recent or `None` | integration | `uv run pytest tests/test_etl_accessor.py -k "test_last_run" -x -o addopts=""` | ❌ Wave 0 |
| ETL-15 (SC-4) | `dry_run=True` skips load, no row, correct RunResult | integration | `uv run pytest tests/test_etl_accessor.py -k "test_dry_run" -x -o addopts=""` | ❌ Wave 0 |
| D-10 | `_row_to_result` maps columns correctly (pure, no DB) | unit | `uv run pytest tests/test_etl.py -k "test_row_to_result" -x -o addopts=""` | ❌ Wave 0 |
| D-11 regression | `run()` re-SELECT returns DB-consistent values (not Python-side computed) | integration | covered by SC-1 test + `status == 'success'` assertion | ❌ Wave 0 |
| Phase 17 non-regression | run-log isolation not broken (no regression) | integration | `uv run pytest tests/test_etl_accessor.py::TestETLAccessorIntegration -x -o addopts=""` | ✅ exists |
| Phase 18 non-regression | load paths untouched | integration | `uv run pytest tests/test_etl_accessor.py::TestRunPipelineIntegration -x -o addopts=""` | ✅ exists |
| Existing test fixes | `isinstance(run_id, int)` → `isinstance(result, RunResult)` | integration | full `TestRunPipelineIntegration` suite | ✅ exists (needs edit) |

### Detailed New Tests Required (Wave 0 Gaps)

**In `tests/test_etl.py` (DB-free unit tests):**

```python
class TestRowToResult:
    """Unit tests for _row_to_result — pure function, no DB."""

    def _sample_row(self, **overrides):
        """Return a minimal valid pipeline_runs dict_row."""
        from datetime import timezone
        base = {
            "run_id": 7,
            "pipeline_name": "test_pipeline",
            "status": "success",
            "rows_extracted": 10,
            "rows_loaded": 10,
            "started_at": datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            "finished_at": datetime(2026, 1, 1, 0, 0, 5, tzinfo=timezone.utc),
            "error_message": None,
            "error_traceback": None,
            "watermark": None,
        }
        base.update(overrides)
        return base

    def test_maps_all_8_fields(self):
        row = self._sample_row()
        result = _row_to_result(row)
        assert result.run_id == 7
        assert result.pipeline_name == "test_pipeline"
        assert result.status == "success"
        assert result.rows_extracted == 10
        assert result.rows_loaded == 10
        assert result.started_at is not None
        assert result.finished_at is not None
        assert result.error is None

    def test_error_message_mapped_to_error_field(self):
        row = self._sample_row(error_message="something failed", status="failed")
        result = _row_to_result(row)
        assert result.error == "something failed"

    def test_error_traceback_not_on_result(self):
        row = self._sample_row(error_traceback="Traceback ...")
        result = _row_to_result(row)
        assert not hasattr(result, "error_traceback")

    def test_watermark_not_on_result(self):
        row = self._sample_row(watermark={"cursor": "2026-01-01"})
        result = _row_to_result(row)
        assert not hasattr(result, "watermark")

    def test_result_is_frozen(self):
        row = self._sample_row()
        result = _row_to_result(row)
        with pytest.raises(Exception):
            result.status = "changed"
```

**In `tests/test_etl_accessor.py` (DB integration, new class `TestRunResultSurface`):**

```python
class TestRunResultSurface:
    """SC-1..SC-4: run/history/last_run/dry_run return RunResult objects."""

    # SC-1: run() returns RunResult with all 8 fields
    def test_run_returns_run_result(self, db, cleanup_pipeline_runs, etl_table): ...
    def test_run_result_fields_match_pipeline_runs_row(self, db, cleanup_pipeline_runs, etl_table): ...

    # SC-2: history() newest-first, two entries for two runs
    def test_history_returns_list(self, db, cleanup_pipeline_runs, etl_table): ...
    def test_history_newest_first(self, db, cleanup_pipeline_runs, etl_table): ...
    def test_history_two_runs_two_entries(self, db, cleanup_pipeline_runs, etl_table): ...
    def test_history_default_limit(self, db, cleanup_pipeline_runs, etl_table): ...
    def test_history_unknown_pipeline_returns_empty_list(self, db, cleanup_pipeline_runs): ...

    # SC-3: last_run() most-recent or None
    def test_last_run_returns_most_recent(self, db, cleanup_pipeline_runs, etl_table): ...
    def test_last_run_returns_none_when_no_runs(self, db, cleanup_pipeline_runs): ...
    def test_last_run_is_not_second_run(self, db, cleanup_pipeline_runs, etl_table): ...

    # SC-4: dry_run=True — no row written, correct RunResult fields
    def test_dry_run_returns_run_result(self, db, cleanup_pipeline_runs, etl_table): ...
    def test_dry_run_status_is_dry_run(self, db, cleanup_pipeline_runs, etl_table): ...
    def test_dry_run_run_id_is_none(self, db, cleanup_pipeline_runs, etl_table): ...
    def test_dry_run_rows_loaded_is_zero(self, db, cleanup_pipeline_runs, etl_table): ...
    def test_dry_run_writes_no_pipeline_runs_row(self, db, cleanup_pipeline_runs, etl_table): ...
    def test_dry_run_rows_extracted_reflects_actual_extract(self, db, cleanup_pipeline_runs, etl_table): ...
    def test_dry_run_target_table_unchanged(self, db, cleanup_pipeline_runs, etl_table): ...

    # Inherited invariant: Phase 17 run-log isolation not broken
    # (existing TestETLAccessorIntegration::test_failed_run_commits_inside_session
    # must still pass — no new test needed, just don't break it)
```

**Existing tests to update (not new, but required for Phase 19):**

- `TestRunPipelineIntegration::test_run_accepts_pipeline_object` (line 451–459): change `isinstance(run_id, int)` → `isinstance(result, RunResult)` and add import.
- `TestRunPipelineIntegration::test_run_derives_pipeline_name_from_pipeline` (lines 461–475): change `run_id = db.etl.run(p)` → `result = db.etl.run(p); run_id = result.run_id`.
- `TestETLAccessorIntegration::test_run_writes_full_row` (lines 231–257): change `run_id = db.etl.run(p)` → `result = db.etl.run(p); run_id = result.run_id`.
- `TestETLAccessorIntegration::test_first_run_auto_creates` (lines 207–229): no capture of return value — no change needed.
- `TestRunPipelineIntegration::test_rows_extracted_recorded` (lines 526–541): change `run_id = db.etl.run(p)` → `result = db.etl.run(p); run_id = result.run_id`.
- All other tests in `TestRunPipelineIntegration` that use `run_id = db.etl.run(p)` as a raw int: audit the full class for any `run_id = db.etl.run(...)` assignment.

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_etl_accessor.py tests/test_etl.py -x -q -o addopts=""`
- **Per wave merge:** Same (this phase fits in one wave)
- **Phase gate:** `uv run pytest` (full suite, coverage ≥ 94) before `/gsd-verify-work`

### Wave 0 Gaps (test infrastructure that must exist before implementation)

- [ ] `_row_to_result` import in `tests/test_etl.py` — add to the `from pycopg.etl import (...)` block
- [ ] `RunResult` import in `tests/test_etl_accessor.py` — add to `from pycopg.etl import ETLAccessor, Pipeline, RunResult`
- [ ] `TestRowToResult` class in `tests/test_etl.py` (pure unit tests — no DB fixture needed)
- [ ] `TestRunResultSurface` class skeleton in `tests/test_etl_accessor.py`

---

## Security Domain

`security_enforcement` is absent from `.planning/config.json` → **enabled**.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes (limited) | `pipeline_name` bound as `%s` param; `run_id` is an `int` from Python, not user-supplied text — no injection surface |
| V6 Cryptography | no | — |

### Threat Analysis for Phase 19

Phase 19 adds **read-only** queries only (`SELECT * FROM pipeline_runs WHERE ...`). All parameters are bound via `%s` placeholders — no identifier interpolation. The `pipeline_name` parameter in `history(name)` / `last_run(name)` is user-supplied text, but it travels only as a `%s` value, not as an identifier in the SQL string. No new injection surface is introduced.

The `run_id` used in `ETL_GET_RUN` originates from `cur.fetchone()["run_id"]` in `_start_run()` — a DB-issued integer, not user-controlled. No validation needed beyond the psycopg integer type.

---

## Sources

### Primary (HIGH confidence — verified from live source files)

- `pycopg/etl.py` lines 1–782 — full `run()` body, all module-level functions, imports
- `pycopg/queries.py` lines 246–295 — ETL QUERIES block: `ETL_INIT_PIPELINE_RUNS`, `ETL_INSERT_RUN`, `ETL_UPDATE_RUN`, `ETL_LIST_RUNS`, `ETL_GET_LAST_RUN`
- `tests/test_etl_accessor.py` lines 1–1060 — all existing integration and unit tests
- `tests/test_etl.py` lines 1–418 — all existing DB-free unit tests
- `tests/conftest.py` — fixture definitions (`db_config`, `db`, `cleanup_pipeline_runs`)
- `pycopg/__init__.py` — current exports (no `Pipeline`, no `RunResult`, 3 ETL exceptions)
- `pyproject.toml` `[tool.pytest.ini_options]` — coverage gate 94, `addopts` pattern

### Secondary (MEDIUM confidence — context documents)

- `.planning/phases/19-sync-runner-query-surface/19-CONTEXT.md` — D-01..D-12 locked decisions
- `.planning/phases/18-load-modes-extract/18-CONTEXT.md` — Phase 18 boundary and what `run()` returns
- `.planning/phases/17-run-tracking-foundation/17-CONTEXT.md` — run-log isolation contract
- `.planning/REQUIREMENTS.md` — ETL-10, ETL-11, ETL-15, ETL-17 requirement text

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — zero new packages; all imports verified present in `etl.py`
- Architecture: HIGH — both seams verified against real line numbers in the live source
- Pitfalls: HIGH — all grounded in actual code structure, not speculation
- Test map: HIGH — based on reading the real test file and counting existing `run_id = db.etl.run()` call sites

**Research date:** 2026-06-15
**Valid until:** 2026-07-15 (stable codebase; `etl.py` won't change between now and Phase 19 planning)

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 19 |
|-----------|-------------------|
| `uv run pytest tests/ -x -q` for quick runs | Use `-o addopts=""` for targeted ETL runs to avoid coverage HTML noise |
| `uv run pytest` for full suite with coverage gate | Gate stays at 94 this phase |
| `uv run ruff check pycopg tests` | `RunResult`, `_row_to_result`, new methods must pass ruff; `Callable` from `collections.abc` per UP035 (already imported at line 28) |
| `uv run black pycopg tests` | Format before committing |
| No deps on Solaris/MarketStream/Kala | Phase 19 adds zero imports — compliant |
| Venv independent: `uv sync --all-extras --dev` | No change to `pyproject.toml` dependencies |
