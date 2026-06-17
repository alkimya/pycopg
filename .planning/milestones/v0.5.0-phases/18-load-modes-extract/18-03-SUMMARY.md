---
phase: 18-load-modes-extract
plan: "03"
subsystem: etl
tags: [etl, integration-tests, behavioral-gate, atomicity, tdd]
dependency_graph:
  requires:
    - pycopg.etl.ETLAccessor.run(pipeline: Pipeline) -> int
    - pycopg.etl._build_insert_sql
    - pycopg.etl._build_upsert_sql
    - pycopg.etl.build_truncate_sql
  provides:
    - tests/test_etl_accessor.py::TestRunPipelineIntegration (slug-named integration tests)
  affects:
    - tests/test_etl_accessor.py
tech_stack:
  added: []
  patterns:
    - slug-named integration tests (VALIDATION.md per-task verification map)
    - scratch-table isolation (uuid.uuid4().hex[:8] + DROP TABLE IF EXISTS … CASCADE)
    - atomicity probe (NOT NULL constraint violation forces mid-INSERT failure)
key_files:
  created: []
  modified:
    - tests/test_etl_accessor.py
decisions:
  - "Slug-named tests added alongside existing Wave-2 tests rather than renaming — preserves Wave-2 test IDs while satisfying VALIDATION.md -k resolution requirements"
  - "test_replace_atomic_rollback already existed from Wave 2 (crown-jewel test); no duplication needed"
  - "numpy imported locally inside test_nan_to_null (not module-level) to keep import surface minimal"
metrics:
  duration: "~10 minutes"
  completed: "2026-06-15"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 1
  commits: 1
---

# Phase 18 Plan 03: Integration-Test Behavioral Gate + Phase 17 Caller Migration — Summary

Eight slug-named integration test methods added to `TestRunPipelineIntegration` in `tests/test_etl_accessor.py`, providing VALIDATION.md `-k` slug resolution for all Phase 18 ETL behavioral requirements. The Phase 17 string-arg caller migration (Task 1) was already completed by Wave 2 (commit 0d6a4d4); acceptance criteria confirmed. All 41 etl_accessor tests pass against real `pycopg_test`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Migrate Phase 17 string-arg run() callers to run(Pipeline(...)) | 0d6a4d4 (Wave 2) | tests/test_etl_accessor.py |
| 2 | Integration tests — extract, append/replace/upsert, transform, NaN→NULL, ETL-09 | 664b1d7 | tests/test_etl_accessor.py |

## What Was Built

### Task 1 — Phase 17 Caller Migration (verified, Wave 2)

Both `test_first_run_auto_creates` and `test_run_writes_full_row` already use `Pipeline(...)` (committed 0d6a4d4). Acceptance criteria confirmed:

- `grep -c 'db\.etl\.run("' tests/test_etl_accessor.py` = 0
- `test_run_writes_full_row` asserts `pipeline_name == "demo"` and `watermark is None`
- Both tests pass under `-k "first_run_auto_creates or run_writes_full_row"`

### Task 2 — Slug-Named Integration Tests (commit 664b1d7)

Eight new methods added to `TestRunPipelineIntegration` matching VALIDATION.md slugs exactly, so all plan acceptance criteria `-k` commands resolve:

**`test_extract_table_limit`**: Seeds 4-row source, runs `Pipeline(extract_limit=2, source=<table>)`, asserts exactly 2 target rows and `rows_extracted == 2` in `pipeline_runs`.

**`test_transform_error_failed_run`**: `bad_transform` raises `ValueError`; asserts `ETLTransformError` propagates and `pipeline_runs` row has `status='failed'` with non-null `error_message`.

**`test_append_double_count`**: Runs append pipeline twice; asserts target row count doubles to 2 (ETL-04 idempotency).

**`test_replace_latest_only`**: Runs replace with rows `id=10` then `id=20`; asserts only `id=20` remains (ETL-05).

**`test_replace_creates_missing`**: Runs replace against non-existent target; asserts target is auto-created and holds the extracted row (D-03).

**`test_upsert_no_duplicates`**: Pre-seeds target `(1, 'old'), (2, 'keep')`; upserts `(1, 'updated')`; asserts 2 rows total, `id=1` updated to `'updated'`, `id=2` untouched (ETL-06).

**`test_nan_to_null`**: Injects `np.nan` into `val` column via transform; asserts `rows[0]["val"] is None` in target (D-07/Q2).

**`test_run_level_failed_load_rolls_back_but_run_committed`**: Seeds target with baseline `(1, 'base')`, adds NOT NULL constraint, runs replace pipeline whose transform injects a NULL-val row; asserts (a) target retains `id=1` (TRUNCATE+INSERT atomic), (b) `pipeline_runs` has `status='failed'` (ETL-09 run()-level isolation).

The `replace_atomic_rollback` (crown-jewel) test already existed from Wave 2 — no duplication.

## Verification Results

```
uv run pytest tests/test_etl_accessor.py -k "first_run_auto_creates or run_writes_full_row" -x -q -o addopts=""
2 passed, 39 deselected in 1.06s

uv run pytest tests/test_etl_accessor.py -k replace_atomic_rollback -x -q -o addopts=""
1 passed, 40 deselected in 0.70s

uv run pytest tests/test_etl_accessor.py -k "extract_sql or extract_table_limit" -x -q -o addopts=""
2 passed, 39 deselected in 1.22s

uv run pytest tests/test_etl_accessor.py -k "append_double_count or append_missing_target" -x -q -o addopts=""
2 passed, 39 deselected in 1.04s

uv run pytest tests/test_etl_accessor.py -k "replace_latest_only or replace_creates_missing" -x -q -o addopts=""
2 passed, 39 deselected in 1.05s

uv run pytest tests/test_etl_accessor.py -k "upsert_no_duplicates or upsert_missing_target" -x -q -o addopts=""
2 passed, 39 deselected in 0.89s

uv run pytest tests/test_etl_accessor.py -k "transform_single or transform_error_failed_run" -x -q -o addopts=""
2 passed, 39 deselected in 0.94s

uv run pytest tests/test_etl_accessor.py -k nan_to_null -x -q -o addopts=""
1 passed, 40 deselected in 0.64s

uv run pytest tests/test_etl_accessor.py -k "extract or append or replace or upsert or transform or nan_to_null or run_level_failed" -x -q -o addopts=""
26 passed, 15 deselected in 10.23s

uv run pytest tests/test_etl.py tests/test_etl_accessor.py tests/test_sql_injection.py -x -q -o addopts=""
186 passed in 13.51s

uv run ruff check tests/test_etl_accessor.py pycopg/etl.py
All checks passed!

uv run black --check tests/test_etl_accessor.py
All done! 1 file would be left unchanged.

grep -c 'db\.etl\.run("' tests/test_etl_accessor.py
0

grep -c 'replace_atomic_rollback' tests/test_etl_accessor.py
1

grep -c 'ETLTargetNotFoundError' tests/test_etl_accessor.py
5

grep -c 'ETLTransformError' tests/test_etl_accessor.py
8
```

## Decisions Made

1. **Slug-naming approach:** Added new test methods with VALIDATION.md slug names alongside the existing Wave-2 named tests rather than renaming them. This avoids breaking prior-wave test IDs while ensuring all `-k` slug commands in the acceptance criteria resolve.

2. **NOT NULL constraint as atomicity failure trigger:** `test_replace_atomic_rollback` and `test_run_level_failed_load_rolls_back_but_run_committed` both use an `ALTER TABLE … SET NOT NULL` + transform-injected NULL to force a constraint violation mid-INSERT. This is the most realistic failure mechanism — no mocking needed, and it distinguishes the atomic seam (TRUNCATE+INSERT in same txn) from a broken seam (TRUNCATE committed separately).

3. **numpy local import:** `import numpy as np` placed inside `test_nan_to_null` rather than module-level — keeps import surface minimal; numpy is available as a project dependency.

## Deviations from Plan

### Context

**1. [Rule 1 - Bug] Task 1 and most Task 2 behaviors already implemented by Wave 2**
- **Found during:** Reading `tests/test_etl_accessor.py` at execution start
- **Issue:** Wave 2 (18-02, commit 0d6a4d4) pre-implemented Phase 17 caller migration and 20 integration tests in `TestRunPipelineIntegration`. However the test names did not match the VALIDATION.md slug names required by Plan 03's acceptance criteria `-k` commands.
- **Fix:** Confirmed Task 1 acceptance criteria already met (verified). Added 8 slug-named test methods for Task 2 to satisfy all VALIDATION.md `-k` slug resolution requirements. Did not re-implement behaviors already proven by Wave 2 tests.
- **Files modified:** `tests/test_etl_accessor.py`
- **Commit:** 664b1d7

## Known Stubs

None. All behavioral claims are proven by integration tests against real `pycopg_test`.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. All tests use scratch tables with `uuid.uuid4().hex[:8]` names dropped in cleanup — T-18-07 mitigated. No new packages installed — T-18-SC accepted.

## Self-Check: PASSED

- tests/test_etl_accessor.py: FOUND (contains `replace_atomic_rollback`, `ETLTargetNotFoundError`, `ETLTransformError`, `test_nan_to_null`, `test_run_level_failed_load_rolls_back_but_run_committed`)
- Commit 664b1d7: FOUND
- All 41 etl_accessor tests pass: VERIFIED
- All VALIDATION.md `-k` slug commands exit 0: VERIFIED
- ruff + black clean on modified files: VERIFIED
