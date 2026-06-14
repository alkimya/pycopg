---
phase: 16-pure-etl-layer
plan: "02"
subsystem: etl
tags: [etl, pipeline, dataclass, builders, db-free, pure]
dependency_graph:
  requires: ["16-01"]
  provides: ["pycopg.etl.Pipeline", "pycopg.etl.build_init_sql", "pycopg.etl.build_truncate_sql"]
  affects: ["pycopg/__init__.py (Phase 20)", "pycopg/database.py (Phase 20)", "pycopg/async_database.py (Phase 20)"]
tech_stack:
  added: []
  patterns: ["frozen dataclass with __post_init__ validation", "module-level pure builders returning (sql, params)", "validate_identifiers gate before f-string interpolation", "numpydoc docstrings throughout"]
key_files:
  created:
    - pycopg/etl.py
    - tests/test_etl.py
  modified: []
decisions:
  - "Pipeline is @dataclass(frozen=True) with 8 flat fields — no nested ExtractSpec/LoadSpec (D-01)"
  - "conflict_columns normalized list→tuple in __post_init__ via object.__setattr__ (D-02)"
  - "_validate_load_mode mirrors _validate_unit from spatial.py; rejects 'truncate' and all non-public values (D-06)"
  - "extract_limit=-1/0 rejected in __post_init__ (Claude's Discretion, D-11)"
  - "_is_sql_source heuristic helper included (D-05) and unit-tested"
  - "Callable imported from collections.abc (not typing) per ruff UP035"
metrics:
  duration_minutes: 10
  completed: "2026-06-14"
  tasks_completed: 2
  files_created: 2
  tests_added: 31
---

# Phase 16 Plan 02: ETL Pipeline Dataclass + Pure Builders Summary

**One-liner:** `Pipeline` frozen dataclass with `__post_init__` validation (D-01..D-11) plus `build_init_sql()` / `build_truncate_sql()` pure builders with `validate_identifiers` gate (D-13), mirroring `spatial.py` exactly; 31 DB-free tests prove ROADMAP SC-1/SC-2/SC-4.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create pycopg/etl.py — Pipeline + pure builders | 7995558 | pycopg/etl.py (259 lines) |
| 2 | Create tests/test_etl.py — DB-free unit tests | e45f5da | tests/test_etl.py (232 lines) |

## What Was Built

### `pycopg/etl.py`

- **Module docstring** with "Security invariants" block adapted from `spatial.py` (no `self`, no I/O, no DB; every identifier passes `validate_identifiers`; every user value is `%s`; scope boundary: one extract→transform→load flow, no DAG fields).
- **`_VALID_LOAD_MODES = ("append", "replace", "upsert")`** — module constant mirroring `_VALID_UNITS`.
- **`_validate_load_mode(load_mode)`** — private validator, raises `ValueError` for values outside the set (D-06).
- **`@dataclass(frozen=True) Pipeline`** — 8 fields: `name`, `source`, `target`, `load_mode="append"`, `conflict_columns: tuple[str, ...] = ()`, `schema="public"`, `transform: Callable | list[Callable] | None = None`, `extract_limit: int | None = None` (D-01/D-02/D-03/D-11).
- **`Pipeline.__post_init__`** — normalizes `conflict_columns` list→tuple via `object.__setattr__`; calls `_validate_load_mode`; raises `ValueError` for upsert-without-conflict_columns (D-07); rejects non-positive `extract_limit` (D-11, Claude's Discretion).
- **`_is_sql_source(source)`** — D-05 heuristic helper (SELECT/WITH prefix or whitespace → SQL; else table name). Included and unit-tested.
- **`build_truncate_sql(table, schema="public")`** — calls `validate_identifiers(table, schema)` first (D-13), returns `(f"TRUNCATE TABLE {schema}.{table}", [])`.
- **`build_init_sql()`** — returns `(queries.ETL_INIT_PIPELINE_RUNS, [])`. No `validate_identifiers` call needed (static DDL with no user input). Keeps `(sql, list)` contract uniform.
- Numpydoc docstrings on all public symbols; `interrogate` reports 100% (gate ≥ 95).
- Ruff clean; Black formatted.

### `tests/test_etl.py`

31 DB-free tests organized in 4 classes:

- **`TestPipeline`** (15 tests): construction with all 8 attrs readable, defaults, upsert ValueError (SC-2/D-07), invalid load_mode ValueError (D-06), list→tuple normalization (D-02), extract_limit validation, frozen dataclass, callable/list-of-callable transform, all valid modes.
- **`TestBuilders`** (8 tests): exact SQL string `"TRUNCATE TABLE public.events"`, custom schema, `InvalidIdentifier` for bad table/schema (D-13), `build_init_sql` returns DDL constant with `IF NOT EXISTS` (D-15) and required columns.
- **`TestIsSqlSource`** (6 tests): SELECT/WITH → True, plain table → False, whitespace heuristic.
- **`TestValidateLoadMode`** (2 tests): 3 valid modes pass, invalid raises ValueError.

Zero `db.execute`, zero fixtures, zero DB connections — proves ROADMAP SC-4.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Changed Callable import from `typing` to `collections.abc`**
- **Found during:** Task 1 — ruff UP035
- **Issue:** `from typing import Callable` is deprecated in Python 3.12+ per ruff rule UP035.
- **Fix:** Changed to `from collections.abc import Callable`. The `from __future__ import annotations` annotation in the file ensures the type hint `Callable | list[Callable] | None` works correctly on Python 3.11+.
- **Files modified:** `pycopg/etl.py`
- **Commit:** 7995558

## Threat Surface Scan

The threat mitigations from the plan's threat register are implemented:

| Threat ID | File | Status |
|-----------|------|--------|
| T-16-03 | build_truncate_sql | `validate_identifiers(table, schema)` called first; `build_truncate_sql('bad-name')` test proves InvalidIdentifier is raised |
| T-16-04 | build_init_sql | Returns static `ETL_INIT_PIPELINE_RUNS` constant verbatim — no caller input interpolated |
| T-16-05 | Pipeline.conflict_columns | Stored as immutable tuple on frozen dataclass; identifier validation deferred to Phase 18 load builders |

No new security surface introduced beyond what the threat model describes.

## Success Criteria Verification

- [x] `Pipeline(name=..., source=..., target=..., load_mode=...)` instantiates; all 8 attributes readable (ROADMAP SC-1; D-01/D-03/D-11)
- [x] `Pipeline(load_mode='upsert')` without `conflict_columns` raises `ValueError` at construction (ROADMAP SC-2; D-07)
- [x] `build_init_sql()` and `build_truncate_sql()` importable, return `(sql, params)` tuples (ROADMAP SC-4; D-10)
- [x] `validate_identifiers` called before interpolation in `build_truncate_sql` (D-13)
- [x] `tests/test_etl.py` proves construction-time validation + both builders with NO DB fixture (ROADMAP SC-4)
- [x] ruff, black, interrogate (100%) pass on new files

## Self-Check: PASSED

Files exist:
- `/home/loc/workspace/pycopg/pycopg/etl.py` — FOUND
- `/home/loc/workspace/pycopg/tests/test_etl.py` — FOUND

Commits exist:
- `7995558` (Task 1) — FOUND
- `e45f5da` (Task 2) — FOUND

Test suite: 31 passed, 0 failed, 0 DB connections.
