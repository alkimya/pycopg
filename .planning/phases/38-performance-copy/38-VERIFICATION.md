---
phase: 38-performance-copy
verified: 2026-06-26T14:00:00Z
status: passed
score: 4/4
overrides_applied: 0
---

# Phase 38: Performance COPY — Verification Report

**Phase Goal:** Les chemins d'insertion à volume (`from_dataframe`, ETL load, `insert_batch`) sont optimisés via COPY et micro-opts, avec parité sync/async maintenue.
**Verified:** 2026-06-26T14:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `db.from_dataframe()` and `async_db.from_dataframe()` route via psycopg COPY (not `df.to_sql` data path), preserving `if_exists`/`index`/`primary_key` contract — test verifies observable behavior | VERIFIED | `_stream_df_copy` called at `database.py:1346`; `_async_stream_df_copy` called at `async_database.py:1122`. `validate_identifiers(table, schema)` is first statement in both. `TestFromDataframeCopy` (5 tests) + `TestAsyncFromDataframeCopy` (1 test) pass. to_sql spy confirms data rows go through COPY, DDL head(0) only. |
| 2 | ETL load path (`append`/`replace`) routes via COPY without `astype(object)+to_dict` materialization; `db.etl.run()` returns the same status/count as before | VERIFIED | `_stream_df_copy` / `await _async_stream_df_copy` called inline on the transaction cursor at `etl.py:1426` and `etl.py:2105`. `astype(object)` guarded by `if pipeline.load_mode == "upsert":` at lines 1369/2046. `copy_insert` never called in seam (only in comments). `TestETLCopyPath` (4 tests) pass. |
| 3 | `insert_batch` hoists `row_placeholders` out of the per-row loop — byte-exact identical behavior, covered by non-regression test | VERIFIED | `row_placeholders = ", ".join(["%s"] * len(columns))` at `database.py:1054` (before `for row in batch:` at 1057) and `async_database.py:705` (before 708). `test_insert_batch_placeholder_hoist_regression` exists and passes. |
| 4 | Existing parity tests (`test_parity`/`test_accessor_parity`) stay green after all routing changes — no sync/async parity regression | VERIFIED | 26/26 tests in `tests/test_parity.py` pass under `PGDATABASE=pycopg_test2`. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/database.py` | `_stream_df_copy` module-level helper + `from_dataframe` Hybrid DDL+COPY | VERIFIED | `def _stream_df_copy` at line 55; `validate_identifiers(table, schema, *columns)` at line 111; `df.isna().values` null mask; `df.to_numpy(dtype=object)` type-fidelity fix applied |
| `pycopg/async_database.py` | `_async_stream_df_copy` module-level async helper + async `from_dataframe` rewritten | VERIFIED | `async def _async_stream_df_copy` at line 55; same validation + null mask + type-fidelity fix |
| `pycopg/etl.py` | sync + async ETL seam rewritten for append/replace via COPY helpers | VERIFIED | Module-level imports at lines 40-41; `df.empty` guards (count=2); COPY inline on transaction cursor; upsert unchanged |
| `tests/test_database_integration.py` | `TestFromDataframeCopy` (5 tests) | VERIFIED | Class present at line 337 with: `test_from_dataframe_copy_path`, `test_from_dataframe_replace`, `test_from_dataframe_append`, `test_from_dataframe_index_true`, `test_from_dataframe_nan_null` |
| `tests/test_async_database.py` | `TestAsyncFromDataframeCopy` + `TestAsyncStreamDfCopyValidation` | VERIFIED | `TestAsyncFromDataframeCopy` at line 3436 (1 test); `TestAsyncStreamDfCopyValidation` at line 3469 (2 tests for CR-01/CR-02) |
| `tests/test_database.py` | `TestStreamDfCopyValidation` + `test_insert_batch_placeholder_hoist_regression` | VERIFIED | `TestStreamDfCopyValidation` at line 1829 (2 tests); `test_insert_batch_placeholder_hoist_regression` at line 906 |
| `tests/test_etl_accessor.py` | `TestETLCopyPath` (4 tests: exact rows_loaded + NaN/NaT + upsert unchanged) | VERIFIED | Class at line 3002 with: `test_etl_run_copy_path_rows_loaded_replace`, `test_etl_run_copy_path_rows_loaded_append`, `test_etl_run_copy_nan_null`, `test_etl_run_upsert_unchanged` |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `database.py from_dataframe` | `_stream_df_copy` | `self.connect()` cursor passed to helper | WIRED | `_stream_df_copy(cur, df_ddl, table, schema, columns)` at line 1346, inside `with self.connect() as conn: with conn.cursor() as cur:` |
| `async_database.py from_dataframe` | `_async_stream_df_copy` | `async self.connect()` cursor passed to helper | WIRED | `await _async_stream_df_copy(cur, df_ddl, table, schema, columns)` at line 1122 |
| `from_dataframe` (both) | `validate_identifiers` | first call before any COPY SQL | WIRED | `validate_identifiers(table, schema)` at `database.py:1325` and `async_database.py:1098` — first statement in both methods |
| `_stream_df_copy` | `validate_identifiers` | inside helper before COPY SQL string (CR-01/CR-02 fix) | WIRED | `validate_identifiers(table, schema, *columns)` at `database.py:111` — after `if df.empty:` guard, before `COPY {schema}.{table}` string |
| `_async_stream_df_copy` | `validate_identifiers` | inside async helper (CR-01/CR-02 fix) | WIRED | `validate_identifiers(table, schema, *columns)` at `async_database.py:119` |
| `etl.py sync seam` | `_stream_df_copy` | inline on transaction cursor | WIRED | `rows_loaded += _stream_df_copy(cur, df, pipeline.target, pipeline.schema, columns)` at `etl.py:1426-1428`, inside `with self._db.transaction() as conn: with conn.cursor() as cur:` |
| `etl.py async seam` | `_async_stream_df_copy` | `await` inline on async transaction cursor | WIRED | `rows_loaded += await _async_stream_df_copy(cur, df, pipeline.target, pipeline.schema, columns)` at `etl.py:2105-2107` |
| `etl.py` | `pycopg.database._stream_df_copy` / `pycopg.async_database._async_stream_df_copy` | module-level runtime imports (no circular import) | WIRED | `from pycopg.database import _stream_df_copy` at `etl.py:41`, `from pycopg.async_database import _async_stream_df_copy` at `etl.py:40`; circular-import check passes |
| `database.py insert_batch` | `row_placeholders` | computed before `for row in batch:` | WIRED | Line 1054 before loop at 1057; indentation confirms it is inside the outer batch loop but not inside the per-row loop |
| `async_database.py insert_batch` | `row_placeholders` | same hoist | WIRED | Line 705 before loop at 708 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `_stream_df_copy` | `row_values` (DataFrame rows) | `df.to_numpy(dtype=object)` — object array preserving per-column types | Yes — iterates actual rows, writes via `copy.write_row(...)` | FLOWING |
| `_async_stream_df_copy` | `row_values` | Same `df.to_numpy(dtype=object)` mechanism | Yes | FLOWING |
| ETL seam `rows_loaded` | `_stream_df_copy(...)` return value | `cur.rowcount` after COPY block closes (WR-02 fix: helper return consumed via `+=`) | Yes — exact count asserted by `TestETLCopyPath` | FLOWING |
| `from_dataframe` DDL path | `df_ddl.head(0)` | `df.reset_index() if index else df` — always derived from caller DataFrame | Yes — typed empty schema created before COPY | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `_stream_df_copy` importable + correct sync kind | `uv run python -c "from pycopg.database import _stream_df_copy; import inspect; assert not inspect.iscoroutinefunction(_stream_df_copy)"` | exit 0, confirmed sync | PASS |
| `_async_stream_df_copy` importable + correct async kind | `uv run python -c "from pycopg.async_database import _async_stream_df_copy; import inspect; assert inspect.iscoroutinefunction(_async_stream_df_copy)"` | exit 0, confirmed coroutine | PASS |
| No circular import in `pycopg.etl` | `uv run python -c "import pycopg.etl"` | exit 0, no import error | PASS |
| `TestStreamDfCopyValidation` (CR-01/CR-02 fix) | `uv run pytest tests/test_database.py::TestStreamDfCopyValidation tests/test_async_database.py::TestAsyncStreamDfCopyValidation -q -o addopts=""` | 4 passed | PASS |
| `insert_batch` hoist non-regression | `uv run pytest tests/test_database.py -k "insert_batch_placeholder_hoist" -q -o addopts=""` | 1 passed | PASS |
| `TestFromDataframeCopy` (5 real-DB tests) | `PGDATABASE=pycopg_test2 uv run pytest tests/test_database_integration.py::TestFromDataframeCopy -q -o addopts=""` | 5 passed | PASS |
| `TestAsyncFromDataframeCopy` (real-DB) | `PGDATABASE=pycopg_test2 uv run pytest tests/test_async_database.py::TestAsyncFromDataframeCopy -q -o addopts=""` | 1 passed | PASS |
| `TestETLCopyPath` (4 real-DB tests) | `PGDATABASE=pycopg_test2 uv run pytest tests/test_etl_accessor.py::TestETLCopyPath -q -o addopts=""` | 4 passed | PASS |
| Parity tests green | `PGDATABASE=pycopg_test2 uv run pytest tests/test_parity.py -q -o addopts=""` | 26 passed | PASS |

### Probe Execution

No probe scripts declared in PLAN.md or found at conventional `scripts/*/tests/probe-*.sh` paths. Step 7c: SKIPPED (no probe scripts for this phase).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PERF-01 | 38-01-PLAN.md | `from_dataframe` (sync+async) routes via COPY, preserving contract | SATISFIED | `_stream_df_copy`/`_async_stream_df_copy` wired in both `from_dataframe` methods; `TestFromDataframeCopy` spy test proves to_sql called once on head(0) only |
| PERF-02 | 38-02-PLAN.md | ETL append/replace via COPY, no astype(object)+to_dict | SATISFIED | Seam rewritten; astype(object) guarded to upsert-only branch; `TestETLCopyPath` asserts exact `rows_loaded` |
| PERF-03 | 38-03-PLAN.md | `insert_batch` hoists invariant `row_placeholders` — byte-exact, non-regression test | SATISFIED | Hoist confirmed at database.py:1054 and async_database.py:705; `test_insert_batch_placeholder_hoist_regression` passes |
| PERF-05 | 38-01/02/03-PLAN.md | Sync/async parity maintained — parity tests green + async behavioral test | SATISFIED | 26/26 parity tests pass; `TestAsyncFromDataframeCopy` passes; async ETL seam mirrors sync exactly |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No TBD/FIXME/XXX markers found in any modified file | — | — |
| — | — | No stub implementations (return null/empty) on new code paths | — | — |
| — | — | `astype(object)` present in etl.py but correctly guarded under `upsert` branch only | INFO | Not a stub — intentional data preparation for INSERT ON CONFLICT path |

### 38-REVIEW CR-01/CR-02 Fix Verification (Absolute Phase Constraint)

The code review found two BLOCKERs: `_stream_df_copy` and `_async_stream_df_copy` built COPY SQL with unvalidated identifiers. Fixed in commit 863e894. Verification evidence:

- `validate_identifiers(table, schema, *columns)` present at `database.py:111` inside `_stream_df_copy`, after the `if df.empty:` guard, before the `COPY {schema}.{table}` string is formed.
- `validate_identifiers(table, schema, *columns)` present at `async_database.py:119` inside `_async_stream_df_copy`, same placement.
- `TestStreamDfCopyValidation` (test_database.py:1829) — 2 tests asserting `InvalidIdentifier` raised before `cur.copy` is called.
- `TestAsyncStreamDfCopyValidation` (test_async_database.py:3469) — 2 async tests asserting same.
- All 4 validation tests pass (confirmed by spot-check run).
- Docstrings in both helpers updated to document the internal validation (IN-01 fix).
- WR-02 fix confirmed: ETL seam consumes helper return value (`rows_loaded += _stream_df_copy(...)`) at etl.py:1426 and 2105 — no dead-return issue.

### Human Verification Required

None — all truths are programmatically verifiable and confirmed.

### Gaps Summary

No gaps. All 4 roadmap success criteria are verified against actual codebase code, all key links are wired, all required tests exist and pass against real DB (PGDATABASE=pycopg_test2), and the code review BLOCKERs (CR-01/CR-02) are confirmed fixed in commit 863e894.

---

_Verified: 2026-06-26T14:00:00Z_
_Verifier: Claude (gsd-verifier)_
