---
gsd_state_version: 1.0
milestone: v0.6.0
milestone_name: — Réorganisation en accessors
status: verifying
stopped_at: Phase 24 Plan 02 complete
last_updated: "2026-06-19T12:09:27.762Z"
last_activity: 2026-06-19
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 13
  completed_plans: 13
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-17)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.
**Current focus:** Phase 24 — exports-docs-release-v0-6-0

## Current Position

Phase: 24
Plan: Not started
Status: Phase complete — ready for verification
Last activity: 2026-06-19

Progress: 0/4 phases complete [░░░░░░░░░░] 0% (9/10 plans complete)

## Performance Metrics

**Velocity (v0.5.0 reference):**

- Coverage ratchet: 94 (measured 94.26%); gate stays at --cov-fail-under=94
- interrogate: 100% (gate ≥ 95)

**By Phase (v0.6.0):**

| Phase | Plans | Complete | Status |
|-------|-------|----------|--------|
| 21. Infrastructure & Timescale Accessor | TBD | 0 | Not started |
| 22. Admin, Maint & Backup Accessors | TBD | 0 | Not started |
| 23. Schema Accessor & Spatial Relocation | 4 | 3 | Executing (Plans 01-03 done) |
| 24. Exports, Docs & Release v0.6.0 | TBD | 0 | Not started |
| Phase 23 P04 | 45m | 4 tasks | 12 files |
| Phase 24 P03 | 15min | 3 tasks | 0 files |

## Accumulated Context

### Decisions

All v0.4.0 + v0.5.0 decisions logged in PROJECT.md Key Decisions table with outcomes.

v0.6.0 locked decisions (D-SCOPE-1..4, see `.planning/v0.6.0-SCOPE.md`):

- D-SCOPE-1: transition = alias mince + `DeprecationWarning` → nouveau chemin; suppression des alias en v0.7.0 (zéro rupture brutale).
- D-SCOPE-2: la vraie implémentation vit dans l'accessor; l'ancien `db.*` devient le wrapper qui warn + délègue.
- D-SCOPE-3: les 5 accessors (`timescale`/`admin`/`schema`/`maint`/`backup`) en un seul milestone (~4 phases).
- D-SCOPE-4: parité sync/async obligatoire; `test_parity` enregistre les 5 nouveaux accessors.

Open questions tranchées au cadrage (2026-06-17): `db.schema.*` reste un seul bloc (DDL + introspection); DataFrame reste à plat sur `db.*`; `create_spatial_index`/`list_geometry_columns` → `db.spatial.*`.

- [Phase ?]: D-01 confirmed: 27 schema methods exactly in SchemaAccessor/AsyncSchemaAccessor
- [Phase ?]: Rule 1 auto-fix: etl.py + timescale.py internal deprecated flat calls rewritten to accessor paths

### Roadmap phase mapping (v0.6.0)

- Phase 21: REORG-01, REORG-02, REORG-03, REORG-04, TS-01 — infrastructure + timescale (pattern proof)
- Phase 22: ADM-01, MNT-01, BKP-01 — admin + maint + backup (small accessors)
- Phase 23: SCH-01, SCH-02 — schema (~26 methods) + spatial relocation
- Phase 24: REORG-05 — exports + docs + release v0.6.0

### Decisions

- D-07 honoured: create_spatial_index + list_geometry_columns moved verbatim into SpatialAccessor/AsyncSpatialAccessor (no builder/run conformance)
- D-05 executed atomically: all 8 call-sites in from_dataframe/from_geodataframe rewritten to accessor paths
- D-06 accepted: SpatialAccessor PostGIS guard now applies to deprecated flat path (cleaner failure mode)
- (SpatialAccessor, AsyncSpatialAccessor) added to ACCESSOR_PAIRS (was absent — CONTEXT.md correction)
- Internal deprecated calls in spatial.py fixed: SpatialAccessor.__init__ + AsyncSpatialAccessor._check_postgis now use db.schema.has_extension (Rule 1 auto-fix)
- D-04 executed: v0.5→v0.6 migration section prepended to MIGRATION.md with live-verified 56-name flat→accessor table (admin 11/schema 27/timescale 6/maint 6/backup 4/spatial 2)
- D-05 executed: CHANGELOG [0.6.0] entry written with Added/Deprecated/Changed buckets, v0.7.0 removal notice, D-06 PostGIS-guard note, and updated compare-link footer
- Criterion #1 (REORG-05) confirmed: all 10 accessor classes importable from pycopg; __init__.py untouched

### Pending Todos

None.

### Blockers/Concerns

- 2 pre-existing flaky full-suite DB tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`) — UndefinedTable fixture-isolation bug, not v0.6.0 code; use `-o addopts=""` for targeted runs.

## Session Continuity

Last session: 2026-06-19T12:02:09.338Z
Stopped at: Phase 24 Plan 02 complete
Resume file: .planning/phases/24-exports-docs-release-v0-6-0/24-02-SUMMARY.md
Next action: Execute Phase 24 Plan 03 (version bump + gates + release)

## Operator Next Steps

- Run `/gsd-execute-phase 24` Plan 03 to bump version, run release gates, build artifacts, and publish v0.6.0 to PyPI (human checkpoint required before publish).
