---
phase: 16-pure-etl-layer
plan: "01"
subsystem: etl-foundation
tags: [etl, exceptions, sql-constants, exports]
dependency_graph:
  requires: []
  provides:
    - pycopg.exceptions.ETLError
    - pycopg.exceptions.ETLTransformError
    - pycopg.exceptions.ETLTargetNotFoundError
    - pycopg.queries.ETL_INIT_PIPELINE_RUNS
    - pycopg.queries.ETL_INSERT_RUN
    - pycopg.queries.ETL_UPDATE_RUN
    - pycopg.queries.ETL_LIST_RUNS
    - pycopg.queries.ETL_GET_LAST_RUN
  affects:
    - pycopg/__init__.py (top-level exports)
tech_stack:
  added: []
  patterns:
    - "Exception hierarchy: two-level subclassing from PycopgError (D-08)"
    - "SQL constants: SCREAMING_SNAKE_CASE triple-quoted with %s placeholders, no f-string identifier interpolation (D-12)"
    - "DDL: CREATE TABLE IF NOT EXISTS with TEXT+CHECK status (not ENUM), nullable watermark JSONB (D-14/D-15)"
key_files:
  created: []
  modified:
    - pycopg/exceptions.py
    - pycopg/queries.py
    - pycopg/__init__.py
decisions:
  - "ETLError hierarchy is two-level (ETLError → ETLTransformError / ETLTargetNotFoundError); no PipelineError wrapper per D-09"
  - "pipeline_runs uses TEXT+CHECK status not PG ENUM to avoid non-transactional ALTER TYPE in v0.6.0 per D-14"
  - "watermark JSONB is nullable; always NULL in v0.5.0 per OD-1"
  - "error_traceback TEXT column added alongside error_message (task spec); not in PATTERNS.md sketch but required by ETL_UPDATE_RUN constant"
  - "Pipeline/accessor exports deferred to Phase 20 per PATTERNS.md planner decision"
metrics:
  duration_minutes: 2
  completed_date: "2026-06-14"
  tasks_completed: 3
  files_modified: 3
---

# Phase 16 Plan 01: ETL Foundation (Exceptions + SQL Constants + Exports) Summary

**One-liner:** ETL exception hierarchy (ETLError / ETLTransformError / ETLTargetNotFoundError) plus five ETL SQL constants (`pipeline_runs` DDL + INSERT/UPDATE/LIST/GET_LAST_RUN) and top-level package exports — the pure leaf foundation for Plan 02.

## What Was Built

Three tasks completing the pure, dependency-free foundation for the ETL layer:

1. **ETL exception hierarchy** (`pycopg/exceptions.py`): Appended three classes after `DatabaseExists` matching the existing single-line-docstring + pass-body house style. `ETLError(PycopgError)` is the base; `ETLTransformError(ETLError)` and `ETLTargetNotFoundError(ETLError)` are the two specific subclasses. No `PipelineError` wrapper (D-09). Black formatting applied (blank line between docstring and `pass` body).

2. **Five ETL SQL constants** (`pycopg/queries.py`): Appended a new `# ETL QUERIES` banner section (79-char `=` rule style) with five SCREAMING_SNAKE_CASE triple-quoted constants:
   - `ETL_INIT_PIPELINE_RUNS`: Idempotent `CREATE TABLE IF NOT EXISTS pipeline_runs` with BIGSERIAL PK, TEXT+CHECK status (`'running'/'success'/'failed'`), nullable `watermark JSONB`, and `error_traceback TEXT`.
   - `ETL_INSERT_RUN`: Inserts a run row, RETURNING `run_id`.
   - `ETL_UPDATE_RUN`: Updates run at finish (status, finished_at, row counts, error fields) WHERE run_id = %s.
   - `ETL_LIST_RUNS`: Lists runs for a pipeline newest-first with LIMIT %s.
   - `ETL_GET_LAST_RUN`: Fetches the single most-recent run for a pipeline.
   All use `%s` placeholders only; no f-string/`format()` identifier interpolation (D-12).

3. **Top-level exports** (`pycopg/__init__.py`): Extended `from pycopg.exceptions import (...)` tuple with `ETLError`, `ETLTargetNotFoundError`, `ETLTransformError` (alphabetized within group) and added same three names to `__all__` under `# Exceptions`. Black formatting applied.

## Verification Results

All plan verification commands pass:

```
uv run python -c "from pycopg import ETLError, ETLTransformError, ETLTargetNotFoundError"  → ok
uv run python -c "from pycopg import queries as q; [getattr(q, n) for n in (...)]"         → ok
uv run black --check pycopg/exceptions.py pycopg/queries.py pycopg/__init__.py             → ok
```

Ruff check on modified files: `pycopg/queries.py` and `pycopg/__init__.py` pass clean. `pycopg/exceptions.py` has 4 pre-existing N818 warnings (`ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier`, `DatabaseExists` — naming style) that predate this plan; none from the new ETL classes.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | d7c3362 | feat(16-01): define ETL exception hierarchy in exceptions.py (D-08) |
| Task 2 | 261b314 | feat(16-01): add 5 ETL SQL constants to queries.py (D-10/D-12/D-14) |
| Task 3 | dda13db | feat(16-01): export ETL exception classes from top-level package |
| Style fix | 9106f72 | style(16-01): apply black formatting to exceptions.py and __init__.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Applied black formatting to exceptions.py and __init__.py**
- **Found during:** Overall verification (post-Task 3)
- **Issue:** `uv run black --check` reported two files would be reformatted — the existing style had no blank line between class docstring and `pass`, and `__init__.py` needed a blank line before `__version__`.
- **Fix:** Ran `uv run black pycopg/exceptions.py pycopg/__init__.py` to apply formatting, then committed separately as `style(16-01)`.
- **Files modified:** `pycopg/exceptions.py`, `pycopg/__init__.py`
- **Commit:** 9106f72

**2. Pre-existing ruff N818 warnings (OUT OF SCOPE — not fixed)**
- `uv run ruff check pycopg` reports 38 errors across `config.py`, `migrations.py`, `pool.py`, `utils.py`, and `exceptions.py` (pre-existing N818 naming violations on `ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier`, `DatabaseExists`).
- These are NOT introduced by this plan. Logged to `deferred-items.md` for tracking.
- The three new ETL exception classes all end with `Error` and are N818-compliant.

## Known Stubs

None. This plan contains only exception class definitions, SQL constants, and package exports — no data-flow stubs.

## Threat Flags

No new threat surface beyond the plan's own `<threat_model>`. All five SQL constants use `%s` placeholders only (T-16-01 mitigated). Status is a TEXT+CHECK literal set, not an interpolated value (T-16-02 accepted by design).

## Self-Check: PASSED

Files exist:
- pycopg/exceptions.py — FOUND (contains ETLError, ETLTransformError, ETLTargetNotFoundError)
- pycopg/queries.py — FOUND (contains all 5 ETL_* constants)
- pycopg/__init__.py — FOUND (exports all 3 ETL exception classes)

Commits exist:
- d7c3362 — FOUND
- 261b314 — FOUND
- dda13db — FOUND
- 9106f72 — FOUND
