---
gsd_state_version: 1.0
milestone: v0.6.0
milestone_name: — Réorganisation en accessors
status: Awaiting next milestone
stopped_at: Phase 24 Plan 02 complete
last_updated: "2026-06-19T14:06:15.837Z"
last_activity: 2026-06-19 — Milestone v0.6.0 completed and archived
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
**Current focus:** Planning next milestone (v0.7.0 — alias removal / ALIAS-RM-01)

## Current Position

Phase: Milestone v0.6.0 complete
Plan: —
Status: Awaiting next milestone
Last activity: 2026-06-19 — Milestone v0.6.0 completed and archived

## Performance Metrics

**Velocity (v0.5.0 reference):**

- Coverage ratchet: 94 (measured 94.26%); gate stays at --cov-fail-under=94
- interrogate: 100% (gate ≥ 95)

**By Phase (v0.6.0 — all complete):**

| Phase | Plans | Complete | Status |
|-------|-------|----------|--------|
| 21. Infrastructure & Timescale Accessor | 3 | 3 | Complete |
| 22. Admin, Maint & Backup Accessors | 3 | 3 | Complete |
| 23. Schema Accessor & Spatial Relocation | 4 | 4 | Complete |
| 24. Exports, Docs & Release v0.6.0 | 3 | 3 | Complete |

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

## Deferred Items

Items acknowledged and deferred at milestone close on 2026-06-19:

| Category | Item | Status |
|----------|------|--------|
| nyquist | Phase 22 VALIDATION.md left `draft` / `nyquist_compliant: false` | deferred — verified PASSED via VERIFICATION.md; optional `/gsd-validate-phase 22` |
| nyquist | Phase 23 VALIDATION.md left `draft` / `nyquist_compliant: false` | deferred — verified PASSED via VERIFICATION.md; optional `/gsd-validate-phase 23` |
| nyquist | Phase 24 VALIDATION.md left `draft` / `nyquist_compliant: false` | deferred — verified PASSED via VERIFICATION.md; optional `/gsd-validate-phase 24` |
| tech_debt | WR-01: deprecated `*args/**kwargs` alias stubs erase IDE signatures | accepted milestone-wide; self-resolves at v0.7.0 alias removal (ALIAS-RM-01) |
| tech_debt | IN-02: `ExtensionNotAvailable` message may still name flat `db.create_extension(...)` | cosmetic; resolves at v0.7.0 |
| tech_debt | WR-02: dead `has_extension`/`role_exists` monkeypatches in `test_sql_injection.py` async fixture | housekeeping; tests pass 92/92 |

## Session Continuity

Last session: 2026-06-19T12:02:09.338Z
Stopped at: Phase 24 Plan 02 complete
Resume file: .planning/phases/24-exports-docs-release-v0-6-0/24-02-SUMMARY.md
Next action: Execute Phase 24 Plan 03 (version bump + gates + release)

## Operator Next Steps

- Start the next milestone with /gsd-new-milestone
