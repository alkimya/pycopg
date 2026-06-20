---
phase: 26-incremental-etl-pure-layer
plan: 01
subsystem: etl
tags: [etl, incremental, watermark, jsonb, sql-builder, pure-functions, tdd]

# Dependency graph
requires:
  - phase: 19-etl-sync-runner
    provides: "Pipeline frozen dataclass, _validate_load_mode, _is_sql_source, the (sql, list) pure-builder convention, _row_to_result"
  - phase: 20-etl-async-parity
    provides: "watermark JSONB column reserved in pipeline_runs (queries.ETL_INIT_PIPELINE_RUNS)"
provides:
  - "Pipeline.incremental_column field (validated at construction; requires load_mode='upsert')"
  - "_validate_incremental(column, load_mode) module-level validator"
  - "_build_incremental_extract_sql(source, column, schema, watermark) pure watermark-filter SQL builder"
  - "_encode_watermark / _decode_watermark typed-JSONB-envelope serializers ({datetime, int, str})"
affects: [27-incremental-etl-run-log, 28-incremental-etl-wiring]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Typed JSONB envelope {type, value} for lossless scalar round-trip with zero new deps (stdlib isoformat/fromisoformat)"
    - "Watermark-filter SQL builder dispatches source-kind via existing _is_sql_source; subquery-wrap (_pycopg_inc) vs WHERE-append"
    - "Module-level validator owns combo-then-identifier order, wired into __post_init__ in a fixed sequence"

key-files:
  created: []
  modified:
    - "pycopg/etl.py"
    - "tests/test_etl.py"

key-decisions:
  - "Used the existing base ETLError (exceptions.py:54) for the unsupported-watermark-type raise — no new subclass warranted (planner discretion, D-04)"
  - "Reserved subquery alias kept as the module constant _PYCOPG_INC_ALIAS = '_pycopg_inc' (D-07)"
  - "_encode_watermark returns a BARE dict — the Jsonb adapter wrap is deferred to Phase 27 (D-05)"
  - "datetime serialized via isoformat() with NO UTC normalization, preserving offset + microseconds (D-02)"

patterns-established:
  - "Pattern 1: typed JSONB envelope (encode→bare dict, decode→exact Python type via a 'type' tag)"
  - "Pattern 2: bool-before-int allowlist guard reused from the extract_limit precedent for the watermark serializer (D-04)"

requirements-completed: [ETL-INC-01]

# Metrics
duration: 4min
completed: 2026-06-20
---

# Phase 26 Plan 01: Incremental ETL — Pure Layer Summary

**DB-free incremental-ETL foundation in pycopg/etl.py: a validated `Pipeline.incremental_column` field, the `_build_incremental_extract_sql` watermark-filter builder (subquery-wrap or WHERE-append, watermark always a `%s` param), and the typed-JSONB-envelope `_encode_watermark`/`_decode_watermark` serializers — 5 new symbols, 34 co-located unit tests, zero new deps.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-06-20T11:21:32Z
- **Completed:** 2026-06-20T11:25:26Z
- **Tasks:** 3 (all TDD)
- **Files modified:** 2 (`pycopg/etl.py`, `tests/test_etl.py`)

## Accomplishments
- `Pipeline.incremental_column: str | None` field validated at construction — requires `load_mode='upsert'`, rejects `append`/`replace` with a `ValueError` that cites ETL-INC-01, and rejects bad identifiers with `InvalidIdentifier` (D-14..D-17).
- `_build_incremental_extract_sql` pure builder: dispatches on `_is_sql_source` (D-11); SQL-string source wraps as `SELECT * FROM (<clean>) _pycopg_inc WHERE col > %s` (D-06/D-07/D-08), table source appends `WHERE col > %s` (D-09); `watermark=None` returns a full unfiltered SELECT with `[]` params (D-12); the watermark always travels as the single `%s` param, never interpolated (D-10, T-26-01).
- `_encode_watermark`/`_decode_watermark` typed JSONB envelope: `{datetime, int, str}` allowlist with `bool` rejected before the `int` branch (D-04); `datetime` round-trips losslessly with offset + microseconds preserved (D-02); encode returns a bare dict, not a `Jsonb` (D-05).
- 34 new DB-free tests added (full `test_etl.py` suite: 58 → 92 passing); `interrogate pycopg` = 100%.

## Task Commits

Each task was committed atomically following the TDD RED → GREEN gate:

1. **Task 1: incremental_column field + _validate_incremental + __post_init__ wiring**
   - `a004fc7` (test — RED)
   - `7953d65` (feat — GREEN)
2. **Task 2: _build_incremental_extract_sql pure watermark-filter builder**
   - `6378bc8` (test — RED)
   - `a078862` (feat — GREEN)
3. **Task 3: _encode_watermark / _decode_watermark typed-JSONB-envelope helpers**
   - `e531ed6` (test — RED)
   - `a751e8a` (feat — GREEN)

No REFACTOR commits were needed — the GREEN implementations were already clean (ruff + black on the two changed files).

## Files Created/Modified
- `pycopg/etl.py` — added `incremental_column` field + docstring entry, `_validate_incremental`, `_build_incremental_extract_sql`, `_encode_watermark`, `_decode_watermark`, the `_PYCOPG_INC_ALIAS` and `_WATERMARK_SUPPORTED` constants, and the `ETLError` import; wired `_validate_incremental` into `__post_init__` (after `_validate_load_mode`, before the upsert check).
- `tests/test_etl.py` — added field cases to `TestPipeline`, plus the `TestValidateIncremental`, `TestBuildIncrementalExtractSql`, and `TestEncodeDecodeWatermark` classes; extended the `from pycopg.etl import (...)` tuple and the `from pycopg.exceptions import ...` line.
- `.planning/phases/26-incremental-etl-pure-layer/deferred-items.md` — logged pre-existing out-of-scope lint/format debt.

## Decisions Made
- Used the existing base `ETLError` for the unsupported-type raise (planner discretion D-04); added `ETLError` to the existing `from pycopg.exceptions import ...` line in `etl.py` (it was not previously imported there).
- Kept the reserved subquery alias as a module constant `_PYCOPG_INC_ALIAS = "_pycopg_inc"` rather than inlining the literal (both were acceptable per D-08).
- Single-line f-string for the subquery-wrap SQL (D-08 formatting discretion) — chosen to keep black clean.

## Deviations from Plan

None — plan executed exactly as written. No deviation rules (1–4) were triggered; no architectural changes, no missing-functionality additions, no blocking issues.

## Issues Encountered

- **Whole-tree ruff/black gate noise:** the plan's phase-level verification ran `uv run ruff check pycopg tests` and `uv run black --check pycopg tests` across the entire tree, which reports failures that **pre-date this plan** and live in files this plan did not touch (`pycopg/exceptions.py` N818, several `tests/*` F841/E722/W291, and the untouched async `table_exists` line in `etl.py` that black would re-wrap). Per the executor SCOPE BOUNDARY rule these were **not** fixed. Resolution: ran ruff + black scoped to the two changed files (`pycopg/etl.py`, `tests/test_etl.py`) — both clean for the new code; the only residual `etl.py` black hunk is the pre-existing async line. Pre-existing debt is logged in `deferred-items.md`. `interrogate pycopg` = 100% (≥95 gate met).

## Known Stubs

None — every new symbol is fully implemented and unit-tested. The intentionally-unwired nature of this layer (no `run()` wiring, no `pipeline_runs` reads/writes, no `Jsonb` wrap, no async mirror, no docs) is the deliberate Phase-26 boundary, with those consumers explicitly scheduled for Phases 27/28 — not stubs.

## User Setup Required

None — no external service configuration required. This is a pure, DB-free code layer.

## Next Phase Readiness
- Phase 27 (run-log read/write) can now consume `_encode_watermark`/`_decode_watermark` and wrap the bare dict in `Jsonb` at the write-site, and read the last watermark from `pipeline_runs`.
- Phase 28 (extract wiring) can call `_build_incremental_extract_sql` from the `run()` extract path and compute `max(incremental_column)` after the batch (ETL-INC-04), plus add the async mirror, `RunResult.watermark_*` fields, and incremental docs.
- No blockers. The `watermark JSONB` column in `queries.py` remains untouched and ready as the round-trip target.

## Self-Check: PASSED

- All 6 task commits verified present (`a004fc7`, `7953d65`, `6378bc8`, `a078862`, `e531ed6`, `a751e8a`).
- `26-01-SUMMARY.md` created at `.planning/phases/26-incremental-etl-pure-layer/`.
- Both modified files (`pycopg/etl.py`, `tests/test_etl.py`) exist on disk.
- All 5 new symbols present in `pycopg/etl.py`; `git diff` vs base shows only the 2 intended source files changed.

---
*Phase: 26-incremental-etl-pure-layer*
*Completed: 2026-06-20*
