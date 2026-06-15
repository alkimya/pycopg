---
phase: 18-load-modes-extract
plan: "02"
subsystem: etl
tags: [etl, run-body, extract, transform, load, atomic, tdd, integration]
dependency_graph:
  requires:
    - pycopg.etl._build_insert_sql
    - pycopg.etl._build_upsert_sql
    - pycopg.etl._step_label
    - pycopg.etl.build_truncate_sql
    - pycopg.database.Database.to_dataframe
    - pycopg.database.Database.from_dataframe
    - pycopg.database.Database.table_exists
    - pycopg.database.Database.session
    - pycopg.database.Database.transaction
  provides:
    - pycopg.etl.ETLAccessor.run(pipeline: Pipeline) -> int
  affects:
    - pycopg/etl.py
    - tests/test_etl_accessor.py
tech_stack:
  added: []
  patterns:
    - tdd (RED commit e3acc8b -> GREEN commit 0d6a4d4)
    - atomic-load seam (db.session + db.transaction yielded conn, never public batch methods)
    - NaN/NaT coercion (df.astype(object).where(pd.notnull(df), None) before param build)
    - run-log isolation (dedicated autocommit conn for init/_start_run/_end_run — ETL-09)
    - pure-builder dispatch (Plan 01 _build_insert_sql/_build_upsert_sql/build_truncate_sql)
key_files:
  created: []
  modified:
    - pycopg/etl.py
    - tests/test_etl_accessor.py
decisions:
  - "D-01 (corrected seam): load SQL executed directly on db.transaction()-yielded conn inside db.session(); never via insert_batch/upsert_many (which crash inside an explicit transaction)"
  - "D-02: run-log writes (init/_start_run/_end_run) stay on dedicated autocommit conns — independent of the load txn (ETL-09 non-regression)"
  - "D-03: append/upsert missing target raises ETLTargetNotFoundError; replace missing target auto-created via from_dataframe(zero-row, if_exists='replace') BEFORE opening the txn"
  - "D-05/D-06: transform chain — None no-op, single callable, list in sequence; ETLTransformError with 1-based step index + _step_label on failure"
  - "D-07/Q2: NaN/NaT coerced to None via df.astype(object).where(pd.notnull(df), None); tz-localization is caller's responsibility (matches from_dataframe)"
  - "Q5: signature changed from run(name: str) to run(pipeline: Pipeline); Phase 17 tests migrated from run('string') to run(Pipeline(...))"
metrics:
  duration: "~20 minutes"
  completed: "2026-06-15"
  tasks_completed: 1
  tasks_total: 1
  files_modified: 2
  commits: 2
---

# Phase 18 Plan 02: ETL run() Body — Extract/Transform/Load — Summary

Full `run(self, pipeline: Pipeline) -> int` body replacing the Phase 17 stub in `pycopg/etl.py`: extract delegates to `db.to_dataframe`, transform applies as None/single/list with `ETLTransformError` step naming, and all three load modes (append/replace/upsert) execute Plan 01 builders' `(sql, params)` directly on the `db.transaction()`-yielded conn inside an internal `db.session()`, making replace's TRUNCATE+INSERT atomic (SC-3 / RESEARCH Q1 corrected seam).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Add failing integration tests for run(pipeline: Pipeline) body | e3acc8b | tests/test_etl_accessor.py |
| 1 (GREEN) | Rewrite run() with extract/transform/load body; migrate Phase 17 string-arg tests | 0d6a4d4 | pycopg/etl.py, tests/test_etl_accessor.py |

## What Was Built

### `pycopg/etl.py` — rewritten `ETLAccessor.run()`

**New imports added:**
- `import traceback` — for `traceback.format_exc()` in the failed-run path
- `import pandas as pd` — for the NaN/NaT coercion idiom

**New signature:** `run(self, pipeline: Pipeline) -> int` (was `run(self, name: str = "pipeline") -> int`)

**Body sequence (mirrors RESEARCH "ETL Execution Flow (sync, corrected)"):**

1. `name = pipeline.name`; `self.init()`; `run_id = self._start_run(name)`; initialize counters.

2. Wrap steps 3-8 in `try/except Exception as exc` — on failure: `_end_run(..., "failed", ..., error_traceback=traceback.format_exc())` then `raise` (OD-2).

3. **EXTRACT:** `_is_sql_source` branches between SQL and table paths. With `extract_limit`, the LIMIT is bound as `:lim` via `to_dataframe(params={"lim": n})` (T-18-03). For table sources, `validate_identifiers(source, schema)` runs before the f-string (T-18-04). `rows_extracted = len(df)` measured after extract, before transform.

4. **TRANSFORM CHAIN:** `None` -> `[]`, single callable -> `[callable]`, list -> as-is. For each step (1-based index): `df = step(df)` inside try/except; failure raises `ETLTransformError(f"transform step {i} ('{_step_label(step)}') raised {type}: {exc}")` chained `from exc` (D-06/ETL-16).

5. **ROWS:** `df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")` — NaN/NaT -> `None` for all scalar columns (D-07/Q2). Empty DataFrame short-circuits with success/0 rows.

6. **EXISTENCE CHECK:** `self._db.table_exists(target, schema)`. append/upsert missing -> `ETLTargetNotFoundError`; replace missing -> `from_dataframe(df.head(0), ..., if_exists="replace")` BEFORE the txn (D-03).

7. **BUILD LOAD SQL:** Pure Plan 01 builders only:
   - append: `_build_insert_sql(target, columns, rows, schema)`
   - upsert: `_build_upsert_sql(target, rows, list(conflict_columns), schema=schema)`
   - replace: `build_truncate_sql(target, schema)` + `_build_insert_sql(target, columns, rows, schema)`

8. **ATOMIC LOAD SEAM:** `with self._db.session(): with self._db.transaction() as conn: with conn.cursor() as cur:` — replace executes TRUNCATE then INSERT on the SAME `cur`/`conn` (atomic SC-3); append/upsert execute just INSERT. `rows_loaded += cur.rowcount`. Never calls `insert_batch`/`upsert_many` inside this block.

9. `_end_run(run_id, "success", rows_extracted, rows_loaded)`; `return run_id`.

**ETL-09 non-regression:** `init`/`_start_run`/`_end_run` bodies unchanged — all still use `with self._db.connect(autocommit=True)`. `grep -c 'connect(autocommit=True)' pycopg/etl.py` = 6.

### `tests/test_etl_accessor.py` — Phase 18 integration tests + Phase 17 migration

**Phase 17 migration (RESEARCH Q5):** Two tests that called `db.etl.run("string")` migrated to use `Pipeline(...)`:
- `test_first_run_auto_creates` — now uses `Pipeline(name="auto", source="SELECT 1 AS id", target=tbl, load_mode="replace")`
- `test_run_writes_full_row` — now uses `Pipeline(name="demo", source="SELECT 1 AS id", target=tbl, load_mode="replace")`

**New fixtures:** `etl_table` (pre-created `(id INTEGER, val TEXT)` target), `etl_src` (pre-created source).

**`TestRunPipelineIntegration` class — 20 new integration tests:**
- Signature: accepts Pipeline, returns int run_id, derives pipeline.name
- Extract: SQL source, table source, extract_limit (bound :lim), rows_extracted recorded
- Transform: None no-op, single callable, list sequence (2+1)*3=9, ETLTransformError step naming (1-based index + fn name), failed run row committed
- Load append: inserts, doubles on re-run, missing target raises
- Load replace: latest-only on re-run, atomic rollback (SC-3), auto-create missing target
- Load upsert: no duplicates on re-run, missing target raises
- NaN->NULL coercion (D-07)
- Run-log isolation (ETL-09 non-regression)

## Verification Results

```
uv run pytest tests/test_etl.py tests/test_etl_accessor.py tests/test_sql_injection.py -x -q -o addopts=""
178 passed in 10.21s

uv run ruff check pycopg/etl.py
All checks passed!

uv run black --check pycopg/etl.py tests/test_etl_accessor.py
All done! 2 files would be left unchanged.

grep -c 'connect(autocommit=True)' pycopg/etl.py
6  (>= 3 required for ETL-09)

inspect assertions:
- 'pipeline' in sig.parameters: PASS
- 'with self._db.transaction() as conn' in src: PASS
- 'ETLTargetNotFoundError' in src: PASS
- 'ETLTransformError' in src: PASS
- 'pd.notnull' in src: PASS
- 'insert_batch' not in src: PASS
- 'upsert_many' not in src: PASS
```

## TDD Gate Compliance

RED gate: commit `e3acc8b` — `test(18-02): add failing RED tests for run(pipeline: Pipeline) body`
GREEN gate: commit `0d6a4d4` — `feat(18-02): rewrite run(pipeline: Pipeline) -> int with extract/transform/load body`
REFACTOR gate: not needed — implementation was clean on first pass.

## Decisions Made

1. **Corrected atomicity seam (RESEARCH Q1, D-02 correction):** Public `insert_batch`/`upsert_many` are forbidden inside the load txn (they call `self.cursor()` which commits at exit, breaking atomicity or crashing with `ProgrammingError: Explicit commit() forbidden`). The seam opens `db.session()` internally, runs the load in `db.transaction()`, and executes `(sql, params)` directly on the yielded `conn` via `conn.cursor()`. This is the exact working pattern from `tests/test_etl_accessor.py:344-348`.

2. **Run-log isolation preserved (ETL-09):** `init`/`_start_run`/`_end_run` bodies left completely unchanged — all use dedicated `db.connect(autocommit=True)` connections independent of the load session/txn. A failed load still commits the failed run row.

3. **Phase 17 test migration (RESEARCH Q5):** The signature change from `run(name: str)` to `run(pipeline: Pipeline)` broke two Phase 17 tests. Migrated them inline as a deviation (Rule 1 — blocking issue from contract change) to `Pipeline(..., load_mode="replace")` patterns that don't need a pre-existing target table.

4. **`truncate_sql` comment references removed from run():** The docstring referenced `insert_batch`/`upsert_many` by name. Replaced with generic "public batch-write methods" to satisfy the acceptance criterion (`inspect.getsource(run)` must not contain those strings).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Phase 17 tests broken by signature change**
- **Found during:** Task 1 (GREEN — implementing the new signature)
- **Issue:** `test_first_run_auto_creates` and `test_run_writes_full_row` called `db.etl.run("auto")` / `db.etl.run("demo")` with string arguments; the new `run(pipeline: Pipeline)` signature would pass the string as `pipeline.name`, raising `AttributeError: 'str' object has no attribute 'name'`.
- **Fix:** Updated both tests to pass `Pipeline(name=..., source="SELECT 1 AS id", target=tbl, load_mode="replace")`. The auto-create replace mode was chosen so tests don't need a pre-existing target (matches test intent: test the run-log infrastructure, not the load behavior).
- **Files modified:** `tests/test_etl_accessor.py` lines 207-241
- **Commit:** 0d6a4d4

**2. [Rule 2 - Missing] Comment text contained forbidden strings**
- **Found during:** Task 1 verification (inspect assertions)
- **Issue:** Comments inside `run()` body contained the strings `insert_batch` and `upsert_many`, which the acceptance criterion required to be absent from `inspect.getsource(ETLAccessor.run)`.
- **Fix:** Replaced specific method names with the generic phrase "public batch-write methods" / "never the public batch methods" in the two comment lines.
- **Files modified:** `pycopg/etl.py`
- **Commit:** 0d6a4d4

## Known Stubs

None. `run(pipeline)` is fully implemented: extract, transform chain, NaN coercion, existence check, and all three load modes (append/replace/upsert) are wired. The implementation matches the plan's body sequence exactly.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes at trust boundaries beyond what the threat model documents. All mitigations implemented:

| Flag | File | Status |
|------|------|--------|
| T-18-03: extract_limit | pycopg/etl.py | Mitigated — bound as `:lim` param via `to_dataframe(params={"lim": n})`, never f-string |
| T-18-04: table source name | pycopg/etl.py | Mitigated — `validate_identifiers(source, schema)` before f-string in table path |
| T-18-05: target/conflict_columns | pycopg/etl.py | Mitigated — routed through Plan 01 builders which call `validate_identifiers` first |
| T-18-06: error_message/error_traceback | pycopg/etl.py | Accepted — internal run-tracking in user's own DB |

## Self-Check: PASSED

- pycopg/etl.py: FOUND — contains `run(self, pipeline: Pipeline)`, `_build_insert_sql`, `_build_upsert_sql`, `build_truncate_sql`, `_step_label`
- tests/test_etl_accessor.py: FOUND — contains `TestRunPipelineIntegration`, `Pipeline`, `ETLTargetNotFoundError`, `ETLTransformError`
- Commit e3acc8b (RED): FOUND
- Commit 0d6a4d4 (GREEN): FOUND
- All 178 ETL tests pass: VERIFIED
- `connect(autocommit=True)` count >= 3: VERIFIED (6)
- inspect assertions all pass: VERIFIED
- ruff + black clean: VERIFIED
