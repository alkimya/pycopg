---
gsd_state_version: 1.0
milestone: v0.6.0
milestone_name: — Réorganisation en accessors
status: executing
stopped_at: Phase 23 Plan 02 complete
last_updated: "2026-06-17T22:30:00Z"
last_activity: 2026-06-17 -- Phase 23 Plan 02 executed (SchemaAccessor wired into Database/AsyncDatabase)
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 10
  completed_plans: 8
  percent: 60
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-17)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.
**Current focus:** Phase 23 — schema-accessor-spatial-relocation

## Current Position

Phase: 23 (schema-accessor-spatial-relocation) — EXECUTING
Plan: 3 of 4
Status: Executing Phase 23 (Plans 01-02 complete)
Last activity: 2026-06-17 -- Phase 23 Plan 02 executed (SchemaAccessor wired into Database/AsyncDatabase)

Progress: 0/4 phases complete [░░░░░░░░░░] 0% (8/10 plans complete)

## Performance Metrics

**Velocity (v0.5.0 reference):**

- Coverage ratchet: 94 (measured 94.26%); gate stays at --cov-fail-under=94
- interrogate: 100% (gate ≥ 95)

**By Phase (v0.6.0):**

| Phase | Plans | Complete | Status |
|-------|-------|----------|--------|
| 21. Infrastructure & Timescale Accessor | TBD | 0 | Not started |
| 22. Admin, Maint & Backup Accessors | TBD | 0 | Not started |
| 23. Schema Accessor & Spatial Relocation | 4 | 2 | Executing (Plans 01-02 done) |
| 24. Exports, Docs & Release v0.6.0 | TBD | 0 | Not started |

## Accumulated Context

### Decisions

All v0.4.0 + v0.5.0 decisions logged in PROJECT.md Key Decisions table with outcomes.

v0.6.0 locked decisions (D-SCOPE-1..4, see `.planning/v0.6.0-SCOPE.md`):

- D-SCOPE-1: transition = alias mince + `DeprecationWarning` → nouveau chemin; suppression des alias en v0.7.0 (zéro rupture brutale).
- D-SCOPE-2: la vraie implémentation vit dans l'accessor; l'ancien `db.*` devient le wrapper qui warn + délègue.
- D-SCOPE-3: les 5 accessors (`timescale`/`admin`/`schema`/`maint`/`backup`) en un seul milestone (~4 phases).
- D-SCOPE-4: parité sync/async obligatoire; `test_parity` enregistre les 5 nouveaux accessors.

Open questions tranchées au cadrage (2026-06-17): `db.schema.*` reste un seul bloc (DDL + introspection); DataFrame reste à plat sur `db.*`; `create_spatial_index`/`list_geometry_columns` → `db.spatial.*`.

### Roadmap phase mapping (v0.6.0)

- Phase 21: REORG-01, REORG-02, REORG-03, REORG-04, TS-01 — infrastructure + timescale (pattern proof)
- Phase 22: ADM-01, MNT-01, BKP-01 — admin + maint + backup (small accessors)
- Phase 23: SCH-01, SCH-02 — schema (~26 methods) + spatial relocation
- Phase 24: REORG-05 — exports + docs + release v0.6.0

### Pending Todos

None.

### Blockers/Concerns

- 2 pre-existing flaky full-suite DB tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`) — UndefinedTable fixture-isolation bug, not v0.6.0 code; use `-o addopts=""` for targeted runs.

## Session Continuity

Last session: 2026-06-17T22:30:00Z
Stopped at: Phase 23 Plan 02 complete
Resume file: .planning/phases/23-schema-accessor-spatial-relocation/23-02-SUMMARY.md
Next action: Execute Phase 23 Plan 03

## Operator Next Steps

- Run `/gsd-execute-phase 23` Plan 03 to add schema alias tests, migrate call-sites (D-05), and complete the schema track.
