---
gsd_state_version: 1.0
milestone: v0.7.0
milestone_name: Alias Removal + Incremental ETL
status: executing
stopped_at: Completed 28-01-PLAN.md
last_updated: "2026-06-21T17:23:49.019Z"
last_activity: 2026-06-21 -- Phase 28 execution started
progress:
  total_phases: 5
  completed_phases: 3
  total_plans: 10
  completed_plans: 8
  percent: 60
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-19)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.
**Current focus:** Phase 28 — incremental-etl-extract-runresult-async-parity

## Current Position

Phase: 28 (incremental-etl-extract-runresult-async-parity) — EXECUTING
Plan: 2 of 3
Status: Ready to execute
Last activity: 2026-06-21 -- Phase 28 execution started

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Gates (v0.6.0 baseline):**

- Coverage ratchet: ≥94% (measured 95.64% at v0.6.0 ship)
- interrogate: gate ≥95 (measured 100%)
- `-W error::DeprecationWarning`: green (will stay green after alias removal — no stubs left)

**By Phase (v0.7.0 — none complete yet):**

| Phase | Plans | Complete | Status |
|-------|-------|----------|--------|
| 25. Alias Removal | 5 | 5 | ✓ Complete |
| 26. Incremental ETL — Pure Layer | 1 | 1 | ✓ Complete |
| 27. Incremental ETL — Run-Log Integration | TBD | 0 | Not started |
| 28. Incremental ETL — Extract, RunResult & Async Parity | TBD | 0 | Not started |
| 29. Release v0.7.0 | TBD | 0 | Not started |
| Phase 25-alias-removal P01 | 2 | 2 tasks | 1 files |
| Phase 25-alias-removal P02 | 2 | 2 tasks | 1 files |
| Phase 25-alias-removal P04 | 2 | 2 tasks | 3 files |
| Phase 25-alias-removal P05 | 15min | 2 tasks | 10 files |
| Phase 26 P01 | 4min | 3 tasks | 2 files |
| Phase 27 P01 | 18min | 3 tasks | 3 files |
| Phase 28 P01 | 13min | 3 tasks | 2 files |

## Accumulated Context

### Decisions

Locked scope decisions (cadrage 2026-06-19, see PROJECT.md):

- Watermark via `incremental_column` only (no callbacks); high-water mark = `max(col)` from raw batch before transforms
- `incremental_column` + `load_mode` ∈ {append, replace} forbidden at construction (`ValueError`)
- First run (no watermark) = full load then record `max(col)`; advance only on successful load
- Empty batch: success + `rows_loaded=0` + prior watermark preserved (never write NULL)
- Alias removal = hard remove (one cycle already served in v0.6.0) + MIGRATION + Breaking CHANGELOG

Open question resolved in REQUIREMENTS.md: `append` + `incremental_column` is **forbidden** (locked).

- [Phase ?]: Dedicated ETL_UPDATE_RUN_WATERMARK constant — failed/empty paths structurally incapable of setting watermark column
- [Phase ?]: D-07 call-site coercion (int/to_pydatetime/str) at run() before _encode_watermark; encoder stays frozen
- [Phase ?]: _read_watermark exists and tested in Phase 27 but NOT yet applied as WHERE extract filter — Phase 28 (ETL-INC-03)
- [Phase ?]: WR-01/WR-02 decode hardening deferred to Phase 28 — Phase 27 data is provably well-formed
- [Phase ?]: _do_extract() shared helper as single watermark-aware extract path — prevents dry_run/real-path drift (D-A2a)
- [Phase ?]: Builder %s positional -> :wm named bind reconciliation for to_dataframe (SC-1/T-28-01)
- [Phase ?]: RunResult.watermark_used=None for stored rows (never persisted); watermark_recorded decoded from pipeline_runs.watermark (D-A1)

### Pending Todos

None.

### Blockers/Concerns

- 2 pre-existing flaky full-suite DB tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`) — fixture-isolation bug, not v0.7.0 code; use `-o addopts=""` for targeted runs.

## Deferred Items

| Category | Item | Status |
|----------|------|--------|
| nyquist | Phase 22/23/24 VALIDATION.md left `draft` | deferred from v0.6.0 — verified PASSED via VERIFICATION.md |
| tech_debt | WR-02: dead monkeypatches in `test_sql_injection.py` async fixture | housekeeping; non-blocking |
| future | ETL-INC-F01: `initial_watermark` first-run bounding | deferred to v0.8.0 |
| future | ETL-INC-F02: configurable `>` vs `>=` boundary | deferred to v0.8.0 |

## Session Continuity

Last session: 2026-06-21T17:23:49.012Z
Stopped at: Completed 28-01-PLAN.md
Resume file: None
Next action: `/gsd-plan-phase 28` — Phase 28 context gathered (ETL-INC-03/-04/-07/-08/-09/-11/-12: extract filter + RunResult watermark fields + dry_run + async parity + docs)
