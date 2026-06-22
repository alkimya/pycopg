---
gsd_state_version: 1.0
milestone: v0.7.0
milestone_name: Alias Removal + Incremental ETL
status: Awaiting next milestone
stopped_at: Completed 29-01-PLAN.md
last_updated: "2026-06-22T13:14:47.931Z"
last_activity: 2026-06-22 — Milestone v0.7.0 completed and archived
progress:
  total_phases: 5
  completed_phases: 5
  total_plans: 13
  completed_plans: 13
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-22)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.
**Current focus:** v0.7.0 shipped + closed — planning next milestone (v0.8.0 TimescaleDB avancé). Run `/gsd-new-milestone`.

## Current Position

Phase: Milestone v0.7.0 complete
Plan: —
Status: Awaiting next milestone
Last activity: 2026-06-22 — Milestone v0.7.0 completed and archived

## Performance Metrics

**Gates (v0.7.0 ship — baseline for v0.8.0):**

- Coverage ratchet: ≥94% (measured 95.11% at v0.7.0 ship)
- interrogate: gate ≥95 (measured 100%)
- Sphinx `-W`: clean
- `-W error::DeprecationWarning`: green (no deprecated stubs left after alias removal)

**v0.7.0 phases (all complete):**

| Phase | Plans | Complete | Status |
|-------|-------|----------|--------|
| 25. Alias Removal | 5 | 5 | ✓ Complete |
| 26. Incremental ETL — Pure Layer | 1 | 1 | ✓ Complete |
| 27. Incremental ETL — Run-Log Integration | 1 | 1 | ✓ Complete |
| 28. Incremental ETL — Extract, RunResult & Async Parity | 3 | 3 | ✓ Complete |
| 29. Release v0.7.0 | 3 | 3 | ✓ Complete |

## Accumulated Context

### Decisions

v0.7.0 decisions are recorded in full in PROJECT.md → Key Decisions (alias hard-removal, incremental-column declarative watermark, upsert-only/`append`+`replace` forbidden, raw-batch `max(col)` before transforms, advance-only-on-success, typed JSONB envelope, `RunResult` watermark fields + `dry_run` preview). Cleared here on milestone close.

### Pending Todos

None — v0.7.0 closed.

### Blockers/Concerns

- 2 pre-existing flaky full-suite DB tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`) — fixture-isolation bug, not v0.7.0 code; use `-o addopts=""` for targeted runs.
- One ~2.7% flaky bound-param test surfaced during Phase 28 (orchestrator-fixed) — watch for re-flake.

## Deferred Items

| Category | Item | Status |
|----------|------|--------|
| nyquist | Phase 22/23/24 VALIDATION.md left `draft` | deferred from v0.6.0 — verified PASSED via VERIFICATION.md |
| tech_debt | WR-02: dead monkeypatches in `test_sql_injection.py` async fixture | housekeeping; non-blocking |
| tech_debt | `CLAUDE.md` "Version" line stale (reads v0.5.0; actual v0.7.0) | cosmetic doc lag, carried since v0.6.0 |
| future | ETL-INC-F01: `initial_watermark` first-run bounding | deferred to v0.8.0 |
| future | ETL-INC-F02: configurable `>` vs `>=` boundary | deferred to v0.8.0 |
| future | ETL-INC-F03: multi-column / composite watermarks | deferred to v0.8.0+ |
| future | ETL-INC-F04: advisory-lock concurrency for `append` + incremental | deferred to v0.8.0+ |
| future | ETL-INC-F05: CDC / WAL-based change capture | deferred to v0.8.0+ |

## Session Continuity

Last session: 2026-06-22 — milestone v0.7.0 completed and archived via `/gsd-complete-milestone`
Stopped at: Milestone v0.7.0 closed (ROADMAP/REQUIREMENTS archived, PROJECT.md evolved, MILESTONES.md + RETROSPECTIVE.md updated, tag v0.7.0 present)
Resume file: None
Next action: Start the next milestone — `/gsd-new-milestone` (v0.8.0 TimescaleDB avancé)

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone
