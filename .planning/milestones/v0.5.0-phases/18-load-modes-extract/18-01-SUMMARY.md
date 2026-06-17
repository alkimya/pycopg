---
phase: 18-load-modes-extract
plan: "01"
subsystem: etl
tags: [etl, sql-builders, security, tdd, pure-functions]
dependency_graph:
  requires: []
  provides:
    - pycopg.etl._build_insert_sql
    - pycopg.etl._build_upsert_sql
    - pycopg.etl._step_label
  affects:
    - pycopg/etl.py
    - tests/test_etl.py
    - tests/test_sql_injection.py
tech_stack:
  added: []
  patterns:
    - pure-builder (validate-then-build, (sql, params) 2-tuple, no self, no I/O)
    - identifier-injection guard (validate_identifiers before any f-string)
    - step-label naming helper (__name__ with repr() fallback for lambdas/partials)
key_files:
  created: []
  modified:
    - pycopg/etl.py
    - tests/test_etl.py
    - tests/test_sql_injection.py
decisions:
  - "D-04 (RESEARCH Q1): load SQL built by pure _build_insert_sql/_build_upsert_sql in etl.py rather than the public insert_batch/upsert_many methods (unusable inside db.transaction())"
  - "D-06: _step_label returns __name__ for named functions, repr() fallback for lambdas and functools.partial"
  - "SC-6 (ETL-16): validate_identifiers called on every identifier before any f-string interpolation in both new builders"
metrics:
  duration: "~15 minutes"
  completed: "2026-06-15"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
  commits: 2
---

# Phase 18 Plan 01: Pure SQL Builders for ETL Load Modes — Summary

Three pure, DB-free helper functions added to `pycopg/etl.py`: `_build_insert_sql` (multi-VALUES INSERT with SC-6 identifier validation), `_build_upsert_sql` (ON CONFLICT DO UPDATE delegating to `_build_insert_sql`), and `_step_label` (transform step naming with `__name__`/`repr()` fallback). Locked by 28 DB-free unit tests and 25 EVIL_IDENTIFIERS injection regression cases.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Author _build_insert_sql, _build_upsert_sql, _step_label pure helpers in etl.py | 6ba6f17 | pycopg/etl.py |
| 2 | DB-free unit tests for builders + _step_label + transform step-index; ETL injection regression cases | 62a9199 | tests/test_etl.py, tests/test_sql_injection.py |

## What Was Built

### Task 1: Three pure helpers in `pycopg/etl.py`

Added immediately before `class ETLAccessor`, mirroring the `build_truncate_sql` pure-builder shape:

**`_build_insert_sql(table, columns, rows, schema="public", on_conflict=None) -> tuple[str, list]`**
- Ports `base.py:_build_batch_insert_sql` logic verbatim into etl.py
- Calls `validate_identifiers(table, schema, *columns)` before any f-string
- Builds a multi-VALUES INSERT: `INSERT INTO {schema}.{table} ({cols}) VALUES (%s, ...)[, ...]`
- User values go only to `params` as `%s` placeholders — never interpolated (T-18-02)
- Appends `ON CONFLICT {on_conflict}` when supplied

**`_build_upsert_sql(table, rows, conflict_columns, update_columns=None, schema="public") -> tuple[str, list]`**
- Derives `columns` from `rows[0].keys()`; defaults `update_columns` to all non-conflict columns
- Calls `validate_identifiers(*conflict_columns)` and `validate_identifiers(*update_columns)` (T-18-01, SC-6)
- Builds the ON CONFLICT clause then delegates to `_build_insert_sql` for the INSERT body
- Accepts `conflict_columns` as any sequence of str (Pipeline stores tuples)

**`_step_label(fn) -> str`**
- Returns `fn.__name__` for named functions
- Falls back to `repr(fn)` for lambdas (whose `__name__` is `"<lambda>"`, truthy but unhelpful) and `functools.partial` objects (no `__name__` attribute)
- Documents the `repr()` fallback in numpydoc docstring (D-06)

### Task 2: DB-free tests (TDD)

**`tests/test_etl.py` — `TestEtlBuilders` class (28 new tests):**
- `_build_insert_sql`: single/multi-row SQL shape, params count (N*M), `on_conflict` passthrough, custom schema, invalid table/column/schema rejection
- `_build_upsert_sql`: default vs explicit `update_columns`, multiple conflict columns, tuple conflict_columns, invalid conflict_column rejection, delegation to `_build_insert_sql`
- `_step_label`: named function, lambda `repr` fallback, `functools.partial` `repr` fallback
- `test_transform_chain_step_index`: locks D-06 message contract — `transform step {i} ('{label}') raised {type}: {exc}`

**`tests/test_sql_injection.py` — `TestEtlIdentifierInjection` class (25 new parametrized tests):**
- `_build_insert_sql`: rejects EVIL_IDENTIFIERS as table, schema, or column
- `_build_upsert_sql`: rejects EVIL_IDENTIFIERS as conflict_column or table
- Pure builder calls — no DB, no mock needed

## Verification Results

```
uv run pytest tests/test_etl.py tests/test_sql_injection.py -x -q -o addopts=""
145 passed in 0.21s

uv run ruff check pycopg/etl.py tests/test_etl.py tests/test_sql_injection.py
All checks passed!

uv run black --check pycopg/etl.py tests/test_etl.py tests/test_sql_injection.py
3 files would be left unchanged.
```

## Decisions Made

1. **D-04 (RESEARCH Q1 correction):** Load SQL built by new pure `_build_insert_sql`/`_build_upsert_sql` in `etl.py` — NOT by calling the public `insert_batch`/`upsert_many` methods (which crash inside `db.transaction()` due to `ProgrammingError: Explicit commit() forbidden`). The pure builders supply `(sql, params)` tuples that Plan 02's `run()` executes directly on the txn-yielded `conn`.

2. **_step_label lambda special-case:** The plan specified `getattr(fn, "__name__", None) or repr(fn)` but a lambda's `__name__` is `"<lambda>"` (truthy), so the simple `or` expression would return the unhelpful string. Added explicit `name != "<lambda>"` guard so lambdas always get `repr(fn)`. This matches the plan's action text describing the lambda repr fallback.

3. **validate_identifiers call count:** 4 calls in etl.py after this plan (build_truncate_sql has 1; `_build_insert_sql` adds 1; `_build_upsert_sql` adds 2 for conflict and update columns). SC-6 satisfied.

## Deviations from Plan

None — plan executed exactly as written. The only additional implementation detail was the `name != "<lambda>"` guard in `_step_label` to make lambda labels actually useful (plan described the lambda `repr` fallback; implementation just handled the truthy-but-unhelpful `"<lambda>"` string explicitly, matching the plan's stated behavior).

## Known Stubs

None. All three helpers are fully implemented and return correct `(sql, params)` tuples.

## Threat Surface Scan

No new network endpoints, auth paths, or file access patterns introduced. Both builders are pure functions with no I/O. The threat model from the plan is fully implemented:

- T-18-01 (Tampering via identifiers): mitigated by `validate_identifiers` before interpolation in both builders, regression-tested against `EVIL_IDENTIFIERS` (25 cases).
- T-18-02 (Tampering via row values): mitigated by `%s` placeholders only — verified by placeholder/param-shape unit tests.

## Self-Check: PASSED

- pycopg/etl.py: FOUND (contains `_build_insert_sql`, `_build_upsert_sql`, `_step_label`)
- tests/test_etl.py: FOUND (contains `_build_upsert_sql`, `_step_label`)
- tests/test_sql_injection.py: FOUND (contains `_build_insert_sql`, `EVIL_IDENTIFIERS`)
- Commit 6ba6f17: FOUND
- Commit 62a9199: FOUND
