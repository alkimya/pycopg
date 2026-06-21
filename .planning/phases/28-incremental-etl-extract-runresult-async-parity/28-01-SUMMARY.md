---
phase: 28-incremental-etl-extract-runresult-async-parity
plan: 01
subsystem: database
tags: [postgresql, pandas, etl, watermark, incremental, timescaledb]

# Dependency graph
requires:
  - phase: 27-incremental-etl-run-log-integration
    provides: "_read_watermark + _end_run(watermark=) sync primitives; capture block with pd.isna-before-is_float guard"
  - phase: 26-incremental-etl-pure-layer
    provides: "_build_incremental_extract_sql builder (built-but-unwired until this plan)"
provides:
  - "RunResult.watermark_used and watermark_recorded fields (D-A1)"
  - "ETLAccessor._do_extract() shared watermark-aware extract helper"
  - "_row_to_result maps pipeline_runs.watermark -> watermark_recorded (NULL guard)"
  - "Sync run() reads prior watermark, applies WHERE col > :wm filtered extract (ETL-INC-03)"
  - "Sync incremental dry_run: filters identically, reports both watermark fields, writes no row (ETL-INC-09)"
  - "58 passing sync integration tests covering all 5 requirements (ETL-INC-03/04/07/08/09)"
affects:
  - "28-02: async parity plan uses exact same RunResult fields and mirrors _do_extract pattern"
  - "28-03: docs plan documents watermark_used/watermark_recorded fields introduced here"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "_do_extract shared helper: single extract path for both dry_run and real path (D-A2a)"
    - "Positional %s -> named :wm bind reconciliation for to_dataframe (SQLAlchemy text() compat)"
    - "dc_replace (dataclasses.replace) to inject per-run watermark_used on fetched RunResult"
    - "NULL->decode guard in _row_to_result: None when stored NULL, _decode_watermark otherwise"

key-files:
  created: []
  modified:
    - "pycopg/etl.py"
    - "tests/test_etl_accessor.py"

key-decisions:
  - "D-A1 honored: watermark_used = None for stored rows (per-run input never persisted); watermark_recorded = decoded pipeline_runs.watermark"
  - "D-A2a: factored _do_extract() shared helper — dry_run fork and real path both call it identically (no drift)"
  - "Builder %s positional param converted to :wm named bind before to_dataframe (SC-1 / T-28-01)"
  - "dc_replace used to inject watermark_used on success path (fetched row never stores it)"
  - "Non-incremental pipelines: both fields None at all surfaces (run/history/last_run/dry_run)"

patterns-established:
  - "Watermark reconciliation: _build_incremental_extract_sql returns %s; caller converts to :wm named bind for to_dataframe"
  - "LIMIT+watermark composition: wrap filtered SQL as SELECT * FROM (...) _etl_lim LIMIT :lim subquery"
  - "Dry-run watermark capture: same guard block as real path (pd.isna before is_float, WR-02 ordering preserved)"

requirements-completed: [ETL-INC-03, ETL-INC-04, ETL-INC-07, ETL-INC-08, ETL-INC-09]

# Metrics
duration: 13min
completed: 2026-06-21
---

# Phase 28 Plan 01: Sync incremental ETL extract wired end-to-end with RunResult watermark fields and filtered dry_run

**Watermark filter loop closed sync-side: `_read_watermark` + `_build_incremental_extract_sql` + `_end_run(watermark=)` finally connected via shared `_do_extract()` helper; `RunResult` gains `watermark_used`/`watermark_recorded`; incremental `dry_run` applies identical filter and reports both fields without writing a run row**

## Performance

- **Duration:** ~13 min
- **Started:** 2026-06-21T17:08:00Z
- **Completed:** 2026-06-21T17:21:20Z
- **Tasks:** 3 completed
- **Files modified:** 2

## Accomplishments

- Added `RunResult.watermark_used` / `watermark_recorded` with `= None` defaults and numpydoc entries; updated `_row_to_result` to map stored `watermark` column via NULL guard (closes ETL-INC-07/08)
- Factored `ETLAccessor._do_extract()` — single watermark-aware extract path for both the `dry_run` fork and the real run path, reconciling builder's `%s` positional param to `:wm` named bind for `to_dataframe` (SC-1); `extract_limit` composes as a subquery LIMIT (ETL-INC-03)
- Wired incremental `dry_run`: reads prior watermark, applies same filter as real run, captures `max(col)` of filtered batch (preserving `pd.isna`-before-`is_float` ordering from WR-02), sets both `RunResult` fields, writes no `pipeline_runs` row (ETL-INC-09)
- 58 passing sync integration tests in `TestRunResultSurface` covering all 5 requirements: second-run filtering, bound-param safety, RunResult field surfacing, history/last_run surfacing, incremental dry_run (empty+non-empty), and tz-aware offset preservation on second-run filter

## Task Commits

1. **Task 1: Add RunResult watermark fields + map in _row_to_result** - `b6d7d09` (feat, TDD RED+GREEN)
2. **Task 2: Wire filtered extract into sync run() + incremental dry_run** - `5908047` (feat, TDD RED+GREEN)
3. **Task 3: Sync integration tests — 7 behaviors** - `570bbab` (test)

## Files Created/Modified

- `/home/loc/workspace/pycopg/pycopg/etl.py` — RunResult dataclass (2 new fields), `_row_to_result` NULL guard, `_do_extract()` helper method, dry-run fork and real-path extract blocks replaced, `wm` read before extract, `dc_replace` on success return
- `/home/loc/workspace/pycopg/tests/test_etl_accessor.py` — 11 new tests in `TestRunResultSurface` (4 for Task 1 TDD, 7 for Tasks 2+3 integration coverage)

## Decisions Made

- `_do_extract()` as a method on `ETLAccessor` (vs inline mirror in both forks): avoids drift and follows existing method-level factoring style in the class
- `dc_replace(result, watermark_used=wm)` on the real-path return: cleanest way to inject the per-run input value (not stored in DB) onto an already-fetched frozen RunResult
- The dry-run watermark capture block mirrors the real-path guard block verbatim (including `pd.isna` before `is_float`) rather than calling a shared helper — keeps the Phase-27 WR-02 fix visible and auditable in both places
- Non-incremental pipeline: `wm = None` and `_do_extract` falls through to the existing non-incremental extract branch unchanged

## Deviations from Plan

None - plan executed exactly as written. The param-style reconciliation (`%s` to `:wm`) was called out explicitly in the plan as the critical integration risk; it was handled as specified.

## Issues Encountered

- `ruff` detected unsorted import after adding `replace as dc_replace` to the `from dataclasses import` line — auto-fixed with `ruff --fix` in same task before commit.
- `black` reformatted `etl.py` once after Task 1 (Python 3.15 target-version warning is pre-existing, non-blocking).

## Next Phase Readiness

- Plan 02 (async parity) can now mirror `_do_extract` and the dry-run watermark capture block verbatim (with `async with` / `await` mechanical diffs only)
- The `AsyncETLAccessor._end_run` still needs `watermark=` param (Plan 02 work)
- `test_accessor_parity` remains green — structural surface parity is automatic once Plan 02 adds async `_read_watermark`

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. All watermark values flow as bound params (`:wm` named bind via SQLAlchemy `text()`) — T-28-01 mitigated. Identifiers validated by `_build_incremental_extract_sql` before any interpolation — T-28-02 maintained.

## Self-Check: PASSED

- `pycopg/etl.py` exists with `watermark_used` and `watermark_recorded` fields: confirmed
- `tests/test_etl_accessor.py` exists with `test_incremental_tz_aware_offset_preserved_second_run`: confirmed
- Commits `b6d7d09`, `5908047`, `570bbab` exist in git log: confirmed
- All 58 RunResultSurface+watermark+incremental tests pass: confirmed
- `test_accessor_parity` 7/7 green: confirmed
- `interrogate pycopg` 100%: confirmed

---
*Phase: 28-incremental-etl-extract-runresult-async-parity*
*Completed: 2026-06-21*
