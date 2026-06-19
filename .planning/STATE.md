---
gsd_state_version: 1.0
milestone: v0.7.0
milestone_name: Alias Removal + Incremental ETL
status: planning
stopped_at: Roadmap created — 5 phases (25-29), 17/17 requirements mapped
last_updated: "2026-06-19T18:45:32.023Z"
last_activity: 2026-06-19 — Roadmap created for v0.7.0 (5 phases, 17 requirements mapped)
progress:
  total_phases: 5
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-19)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.
**Current focus:** Phase 25 ready to plan (Alias Removal)

## Current Position

Phase: 25 of 29 (Alias Removal)
Plan: —
Status: Ready to plan Phase 25
Last activity: 2026-06-19 — Roadmap created for v0.7.0 (5 phases, 17 requirements mapped)

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Gates (v0.6.0 baseline):**

- Coverage ratchet: ≥94% (measured 95.64% at v0.6.0 ship)
- interrogate: gate ≥95 (measured 100%)
- `-W error::DeprecationWarning`: green (will stay green after alias removal — no stubs left)

**By Phase (v0.7.0 — none complete yet):**

| Phase | Plans | Complete | Status |
|-------|-------|----------|--------|
| 25. Alias Removal | TBD | 0 | Not started |
| 26. Incremental ETL — Pure Layer | TBD | 0 | Not started |
| 27. Incremental ETL — Run-Log Integration | TBD | 0 | Not started |
| 28. Incremental ETL — Extract, RunResult & Async Parity | TBD | 0 | Not started |
| 29. Release v0.7.0 | TBD | 0 | Not started |

## Accumulated Context

### Decisions

Locked scope decisions (cadrage 2026-06-19, see PROJECT.md):

- Watermark via `incremental_column` only (no callbacks); high-water mark = `max(col)` from raw batch before transforms
- `incremental_column` + `load_mode` ∈ {append, replace} forbidden at construction (`ValueError`)
- First run (no watermark) = full load then record `max(col)`; advance only on successful load
- Empty batch: success + `rows_loaded=0` + prior watermark preserved (never write NULL)
- Alias removal = hard remove (one cycle already served in v0.6.0) + MIGRATION + Breaking CHANGELOG

Open question resolved in REQUIREMENTS.md: `append` + `incremental_column` is **forbidden** (locked).

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

Last session: 2026-06-19
Stopped at: Roadmap created — 5 phases (25-29), 17/17 requirements mapped
Resume file: None
Next action: `/gsd-plan-phase 25`
