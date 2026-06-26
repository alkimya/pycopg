---
phase: 38-performance-copy
plan: "02"
subsystem: etl
tags: [performance, copy, etl, dataframe, psycopg, async-parity, seam]
dependency_graph:
  requires:
    - _stream_df_copy (pycopg/database.py) — Plan 38-01
    - _async_stream_df_copy (pycopg/async_database.py) — Plan 38-01
  provides:
    - ETL append/replace load via COPY on transaction cursor (sync + async)
  affects:
    - pycopg/etl.py (seam rewritten for append/replace; upsert unchanged)
    - pycopg/database.py (df.values -> df.to_numpy(dtype=object) bugfix)
    - pycopg/async_database.py (df.values -> df.to_numpy(dtype=object) bugfix)
    - tests/test_etl_accessor.py (TestETLCopyPath added — 4 tests)
tech_stack:
  added: []
  patterns:
    - D-02a: COPY inline on transaction cursor (never copy_insert public method)
    - D-02b: df.empty guard replaces "if not rows:" — 0 rows → success, no watermark advance
    - D-02c: upsert stays on INSERT…ON CONFLICT with list[dict] materialization
    - Rule 1: df.to_numpy(dtype=object) prevents int64→float64 upcast in COPY helpers
key_files:
  created: []
  modified:
    - pycopg/etl.py
    - pycopg/database.py
    - pycopg/async_database.py
    - tests/test_etl_accessor.py
decisions:
  - "D-02a preserved: _stream_df_copy/_async_stream_df_copy called inline on transaction cursor; copy_insert never called in seam"
  - "D-02b applied: df.empty replaces 'if not rows:'; columns from df.columns not rows[0].keys()"
  - "D-02c applied: only upsert materializes astype(object)+to_dict; append/replace stream via COPY"
  - "Rule 1 auto-fix: df.values -> df.to_numpy(dtype=object) in both COPY helpers to prevent int64 upcast when any column has NaN"
metrics:
  duration: "12m"
  completed: "2026-06-26T12:45:28Z"
  tasks_completed: 3
  files_modified: 4
requirements: [PERF-02, PERF-05]
---

# Phase 38 Plan 02: ETL COPY Seam Rewrite Summary

**One-liner:** ETL append/replace load seam rewritten to stream rows inline via COPY on the transaction cursor, eliminating full-frame astype(object)+to_dict materialization; upsert path unchanged (INSERT ON CONFLICT).

## What Was Built

### Task 1 — Module-level imports of COPY helpers in etl.py

Added two runtime (non-TYPE_CHECKING) module-level imports to `pycopg/etl.py`:

```python
from pycopg.async_database import _async_stream_df_copy
from pycopg.database import _stream_df_copy
```

These are safe: `database.py` and `async_database.py` import `etl.py` only lazily inside methods and under `TYPE_CHECKING` — no circular import at module load. Verified via `python -c "import pycopg.etl"`.

### Task 2 — Sync + async ETL load seam rewrite (D-02/D-02a/D-02b/D-02c)

**Step 3 (sync + async):** Replaced the unconditional `df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")` with:
- `if df.empty:` guard (D-02b) → success + 0 rows_loaded, no watermark advance, early return
- `columns = list(df.columns)` (was `list(rows[0].keys())`)
- `rows` materialized ONLY for `load_mode == "upsert"` (D-02c); `rows = []` for append/replace

**Step 5 (sync + async):** Build SQL only for upsert (`_build_upsert_sql`) and truncate-replace (`build_truncate_sql`). No `_build_insert_sql` call for append/replace — COPY needs no INSERT SQL.

**Step 6 (sync + async):** Inside the same `with self._db.session(): with self._db.transaction() as conn: with conn.cursor() as cur:` seam:
- `append`/`replace`: `_stream_df_copy(cur, df, ...)` / `await _async_stream_df_copy(cur, df, ...)`; `rows_loaded += cur.rowcount`
- `upsert`: `cur.execute(insert_sql, insert_params)`; `rows_loaded += cur.rowcount`
- `copy_insert()` public method NEVER called (D-02a / T-38-06)

**Rule 1 auto-fix (applied during Task 2 verification):** The existing `_stream_df_copy` / `_async_stream_df_copy` helpers (Plan 38-01) used `df.values` to extract row data. When a DataFrame has an int64 column alongside any float/NaN column, numpy's uniform-array constraint silently upcasts the int64 to float64 — causing COPY to receive `1.0` for an INTEGER column, raising `InvalidTextRepresentation`. Fixed in both helpers: `df.values` → `df.to_numpy(dtype=object)`, which forces an object array preserving per-column Python types (int stays int, Timestamp stays Timestamp).

### Task 3 — ETL COPY-path tests (TestETLCopyPath, 4 tests)

Added `class TestETLCopyPath` to `tests/test_etl_accessor.py`:

| Test | Purpose |
|------|---------|
| `test_etl_run_copy_path_rows_loaded_replace` | replace mode: `result.rows_loaded == 5` (exact COPY rowcount) |
| `test_etl_run_copy_path_rows_loaded_append` | append mode: `result.rows_loaded == 3` (exact COPY rowcount) |
| `test_etl_run_copy_nan_null` | NaN in float col + NaT in datetime col → SQL NULL via COPY seam |
| `test_etl_run_upsert_unchanged` | upsert still routes via INSERT ON CONFLICT, result.rows_loaded == 1 (D-02c) |

No timing assertions (D-06). All tests use UUID table names + try/finally DROP TABLE.

## Commits

| Hash | Message |
|------|---------|
| `b792b67` | feat(38-02): add module-level imports of _stream_df_copy helpers to etl.py |
| `eda69d6` | feat(38-02): rewrite ETL append/replace load seam to use COPY (D-02/D-02a/D-02b/D-02c) |
| `9b1d1d2` | test(38-02): add ETL COPY-path tests (exact rows_loaded + NaN/NaT->NULL + upsert) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] df.values upcasts int64 to float64 when any column contains NaN**

- **Found during:** Task 2 (test_nan_becomes_null failed after seam rewrite activated COPY path)
- **Issue:** `_stream_df_copy` and `_async_stream_df_copy` (Plan 38-01) used `df.values` for row extraction. When a DataFrame mixes int64 and float64 columns (e.g., a NaN in one column converts it to float64), numpy's uniform-array constraint silently upcasts the entire `df.values` matrix to float64. An integer column value of `1` became `1.0`, which PostgreSQL COPY rejects for INTEGER columns with `InvalidTextRepresentation: invalid input syntax for type integer: "1.0"`.
- **Fix:** Changed `row_values = df.values` to `row_values = df.to_numpy(dtype=object)` in both `_stream_df_copy` (database.py) and `_async_stream_df_copy` (async_database.py). `to_numpy(dtype=object)` forces an object array that preserves per-element Python/pandas types. Updated docstrings to document the reason.
- **Files modified:** `pycopg/database.py`, `pycopg/async_database.py`
- **Commit:** `eda69d6` (included in Task 2 commit)

## Test Environment Note

All real-DB tests run under `PGDATABASE=pycopg_test2` — the default `pycopg_test` DB is broken since 2026-06-24 (TSDB catalog mismatch). This is a permanent env invariant for Phase 38.

## Gate Results

| Gate | Result |
|------|--------|
| `uv run ruff check pycopg tests` | PASSED (exits 0) |
| `uv run interrogate -f 100 pycopg/etl.py pycopg/database.py pycopg/async_database.py` | PASSED (100%) |
| `tests/test_etl_accessor.py` (115 tests, real DB, PGDATABASE=pycopg_test2) | PASSED |
| `tests/test_parity.py` (real DB) | PASSED |
| `tests/test_etl_accessor.py + tests/test_parity.py` combined | PASSED (141 passed) |
| Source: `_stream_df_copy` in seam within ~10 lines of conn.cursor() | PASSED |
| Source: `await _async_stream_df_copy` in async seam | PASSED |
| Source: `copy_insert` not called in seam (comments only) | PASSED |
| Source: `if df.empty:` count >= 2 | PASSED (exactly 2) |
| Source: `astype(object)` guarded by `if pipeline.load_mode == "upsert":` | PASSED |
| `Pipeline` / `RunResult` / `db.etl.run()` signatures unchanged | PASSED |

## Known Stubs

None — all new code paths are wired and tested against real data.

## Threat Flags

No new trust boundary surfaces introduced beyond those documented in the plan's threat model (T-38-04, T-38-05, T-38-06 — all mitigated as planned).

- T-38-04 (identifier injection): identifiers validated upstream by existing ETL builders before reaching `_stream_df_copy`
- T-38-05 (value injection): values flow only through `copy.write_row(...)` — never string-interpolated
- T-38-06 (atomicity break): `copy_insert()` never called in seam; source-asserted

## Self-Check: PASSED
