---
gsd_state_version: 1.0
milestone: v0.7.0
milestone_name: Alias Removal + Incremental ETL
status: verifying
stopped_at: Completed 29-03-PLAN.md — v0.7.0 released to PyPI
last_updated: "2026-06-22T12:45:43.081Z"
last_activity: 2026-06-22 -- Phase 29 execution started
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 13
  completed_plans: 13
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-19)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.
**Current focus:** Phase 29 — release-v0-7-0

## Current Position

Phase: 29 (release-v0-7-0) — COMPLETE
Plan: 3 of 3
Status: All plans complete — v0.7.0 released to PyPI
Last activity: 2026-06-22 -- Phase 29 plan 03 complete, v0.7.0 published

Progress: [██████████] 100%

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
| 27. Incremental ETL — Run-Log Integration | 1 | 1 | ✓ Complete |
| 28. Incremental ETL — Extract, RunResult & Async Parity | 3 | 3 | ✓ Complete |
| 29. Release v0.7.0 | 3 | 1 | ◆ Executing |
| Phase 25-alias-removal P01 | 2 | 2 tasks | 1 files |
| Phase 25-alias-removal P02 | 2 | 2 tasks | 1 files |
| Phase 25-alias-removal P04 | 2 | 2 tasks | 3 files |
| Phase 25-alias-removal P05 | 15min | 2 tasks | 10 files |
| Phase 26 P01 | 4min | 3 tasks | 2 files |
| Phase 27 P01 | 18min | 3 tasks | 3 files |
| Phase 28 P01 | 13min | 3 tasks | 2 files |
| Phase 28 P02 | 26min | 3 tasks | 2 files |
| Phase 29 P01 | 92s | 3 tasks | 4 files |
| Phase 29-release-v0-7-0 P02 | 196s | 2 tasks | 1 files |

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
- [Phase 28-02]: Async _do_extract + _read_watermark as methods (matching sync); verbatim capture block not factored — WR-02 fix remains auditable in both places
- [Phase 28-02]: ETL-INC-04 guard text tested via exact string equality in async tests (not regex) — provides byte-for-byte parity proof (D-A3)
- [Phase 28-02]: ETL-INC-11 CLOSED — full sync/async incremental watermark parity achieved
- [Phase 28-03]: D-A4 honored: ## Incremental loading section added to docs/etl.md covering all 7 required points (ETL-INC-12)
- [Phase 28-03]: D-A5 honored: no reset_watermark() API — manual SQL only; initial_watermark deferred v0.8.0
- [Phase 28-03]: Sphinx -W gate clean — Phase 29 release gate passes

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

Last session: 2026-06-22T12:45:43.068Z
Stopped at: Completed 29-01-PLAN.md
Resume file: None
Next action: Phase 29 — Plan 02 (quality gates: cov/interrogate/sphinx-W/deprecation)
