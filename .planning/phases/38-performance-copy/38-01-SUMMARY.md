---
phase: 38-performance-copy
plan: "01"
subsystem: database
tags: [performance, copy, dataframe, psycopg, async-parity]
dependency_graph:
  requires: []
  provides:
    - _stream_df_copy (pycopg/database.py) — module-level sync COPY helper
    - _async_stream_df_copy (pycopg/async_database.py) — module-level async COPY helper
    - from_dataframe Hybrid DDL+COPY rewrite (sync + async)
  affects:
    - pycopg/database.py (from_dataframe rewritten, _stream_df_copy added)
    - pycopg/async_database.py (from_dataframe rewritten, _async_stream_df_copy added)
    - tests/test_database_integration.py (TestFromDataframeCopy added)
    - tests/test_async_database.py (TestAsyncFromDataframeCopy added; 4 mock tests updated)
tech_stack:
  added: []
  patterns:
    - Hybrid DDL+COPY (D-01): df.head(0).to_sql for schema, COPY for rows
    - Module-level COPY helpers parameterized by caller-provided cursor (D-02a reuse by Plan 02)
    - df.isna().values null-mask (no full-frame astype(object) copy)
    - D-03: separate self.connect() for from_dataframe COPY (not session-aware)
key_files:
  created: []
  modified:
    - pycopg/database.py
    - pycopg/async_database.py
    - tests/test_database_integration.py
    - tests/test_async_database.py
decisions:
  - "D-01 Hybrid confirmed: head(0).to_sql creates schema, _stream_df_copy streams rows"
  - "D-01a reset_index() guarded by if index; columns derived from df_ddl not df"
  - "D-03 separate psycopg connection for COPY in from_dataframe (not session-aware)"
  - "D-04 two-phase replace contract documented in both from_dataframe docstrings"
  - "Rule 1: 4 existing async mock tests fixed to also mock db.connect() for COPY phase"
metrics:
  duration: "11m 20s"
  completed: "2026-06-26T12:31:51Z"
  tasks_completed: 3
  files_modified: 4
requirements: [PERF-01, PERF-05]
---

# Phase 38 Plan 01: COPY Helpers + from_dataframe Hybrid DDL+COPY Summary

**One-liner:** Two module-level COPY streaming helpers (`_stream_df_copy` / `_async_stream_df_copy`) plus `from_dataframe` (sync + async) rewritten to Hybrid DDL+COPY, routing row data through psycopg COPY instead of `df.to_sql`.

## What Was Built

### Task 1 — `_stream_df_copy` + `_async_stream_df_copy` helpers

Two module-level private functions added:

**`_stream_df_copy(cur, df, table, schema, columns) -> int`** in `pycopg/database.py`:
- Takes a caller-provided psycopg cursor; no connection opened, no commit, no identifier validation
- NaN/NaT/pd.NA/None → SQL NULL via `df.isna().values` boolean mask + `df.values` object array
- Returns `cur.rowcount` after the `with cur.copy(...)` block closes (Pitfall 4 timing)
- Designed for reuse by Plan 02 ETL seam (D-02a)

**`async def _async_stream_df_copy(cur, df, table, schema, columns) -> int`** in `pycopg/async_database.py`:
- Async mirror: `async with cur.copy(...) as copy: await copy.write_row(...)`
- Same null-mask mechanism and caller-owns-connection contract

Both are importable at module level:
```python
from pycopg.database import _stream_df_copy
from pycopg.async_database import _async_stream_df_copy
```

### Task 2 — `from_dataframe` (sync + async) rewritten to Hybrid DDL+COPY

Both `Database.from_dataframe` and `AsyncDatabase.from_dataframe` now follow the D-01/D-04 two-phase pattern:

1. **DDL phase**: `df_ddl.head(0).to_sql(name=table, con=engine, ..., index=False)` creates or replaces the empty typed schema (preserves `if_exists`, `dtype`, `index` semantics via pandas/SQLAlchemy)
2. **COPY phase**: `_stream_df_copy` / `_async_stream_df_copy` called on a separate `self.connect()` psycopg connection (D-03); `conn.commit()` after

Key details:
- D-01a: `df_ddl = df.reset_index() if index else df`; `columns = list(df_ddl.columns)` (not `df.columns`) to avoid column drift
- D-04 documented in both docstrings: for `if_exists='replace'`, DDL commits before COPY; COPY failure leaves table replaced-but-empty
- Method signatures unchanged (non-breaking)
- `validate_identifiers(table, schema)` remains the first statement (builder-pur invariant)

### Task 3 — Tests

**`TestFromDataframeCopy`** in `tests/test_database_integration.py` (5 tests, PERF-01):
- `test_from_dataframe_copy_path`: D-06 spy — `pd.DataFrame.to_sql` called once on head(0); data present via COPY
- `test_from_dataframe_replace`: `if_exists='replace'` drops and recreates; only new rows remain
- `test_from_dataframe_append`: `if_exists='append'` adds rows; union count correct
- `test_from_dataframe_index_true`: index column appears in DB and values round-trip (D-01a)
- `test_from_dataframe_nan_null`: NaN in float column → SQL NULL; NaT in datetime column → SQL NULL

**`TestAsyncFromDataframeCopy`** in `tests/test_async_database.py` (1 test, PERF-05):
- `test_from_dataframe_copy_path`: async behavioral spy; data present via async COPY; `to_sql` called once on head(0)

## Commits

| Hash | Message |
|------|---------|
| `d753829` | feat(38-01): add _stream_df_copy + _async_stream_df_copy private helpers |
| `113bd3b` | feat(38-01): rewrite from_dataframe (sync + async) to Hybrid DDL+COPY |
| `045eda9` | test(38-01): add TestFromDataframeCopy (5 tests) + async COPY behavioral test |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 4 existing async mock tests broke after COPY phase added**

- **Found during:** Task 3
- **Issue:** `test_from_dataframe_basic`, `test_from_dataframe_if_exists_append`, `test_from_dataframe_applies_primary_key`, `test_from_dataframe_append_skips_primary_key` all mock `df.to_sql` (instance-level) but the new `from_dataframe` now also calls `self.connect()` for COPY. Two additional problems: (a) `patch.object(df, "to_sql")` patches the df instance but not the `head(0)` return (new DataFrame), so it never fires; (b) `self.connect()` tries a real connection against `testdb/testuser` credentials which fail
- **Fix:** Added COPY-phase mock (asynccontextmanager yielding mock cursor with mock copy context manager) to all 4 tests; replaced `patch.object(df, "to_sql")` with `patch("pandas.DataFrame.to_sql")` (class-level) so `head(0).to_sql(...)` is intercepted
- **Files modified:** `tests/test_async_database.py`
- **Commit:** `045eda9`

## Test Environment Note

All real-DB tests run under `PGDATABASE=pycopg_test2` — the default `pycopg_test` DB is broken since 2026-06-24 (TSDB catalog mismatch). This is a permanent env invariant for Phase 38.

## Helper Signatures for Plan 02 (ETL seam import)

```python
# Sync helper — importable from pycopg.database
def _stream_df_copy(
    cur,           # psycopg.Cursor (caller-provided, may be transaction cursor)
    df: pd.DataFrame,
    table: str,
    schema: str,
    columns: list[str],
) -> int: ...     # returns cur.rowcount after COPY block closes

# Async helper — importable from pycopg.async_database
async def _async_stream_df_copy(
    cur,           # psycopg.AsyncCursor (caller-provided)
    df: pd.DataFrame,
    table: str,
    schema: str,
    columns: list[str],
) -> int: ...     # returns cur.rowcount after COPY block closes
```

## Gate Results

| Gate | Result |
|------|--------|
| `uv run ruff check pycopg tests` | PASSED (exits 0) |
| `uv run interrogate -f 100 pycopg/database.py pycopg/async_database.py` | PASSED (100%) |
| Coverage (`--cov-fail-under=94`) | PASSED (94.24%) |
| `TestFromDataframeCopy` (5 tests, real DB) | PASSED |
| `TestAsyncFromDataframeCopy` (1 test, real DB) | PASSED |
| `test_parity.py` + `test_database_integration.py` | PASSED (114+1 skip) |
| Full suite | PASSED (1393 passed, 3 pre-existing PostGIS env failures, 11 skip) |

## Known Stubs

None — all new code paths are wired and tested against real data.

## Threat Flags

No new trust boundary surfaces introduced. Threat mitigations from PLAN.md threat register:
- T-38-01 (identifier injection): `validate_identifiers` is the first statement in both `from_dataframe` methods — verified by source assertion
- T-38-02 (value injection): values flow only through `write_row` — never string-interpolated into COPY SQL
- T-38-03 (replace atomicity): documented in both docstrings as D-04

## Self-Check: PASSED
