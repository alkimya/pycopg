---
gsd_state_version: 1.0
milestone: v0.6.0
milestone_name: Réorganisation en accessors
status: planning
last_updated: "2026-06-17T09:28:02.157Z"
last_activity: 2026-06-17
progress:
  total_phases: 0
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-17)

**Core value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.
**Current focus:** v0.6.0 — Réorganisation en accessors (defining requirements)

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-06-17 — Milestone v0.6.0 started

## Performance Metrics

**Velocity (v0.5.0 reference):**

- Coverage ratchet: 94 (measured 94.26%); gate stays at --cov-fail-under=94
- interrogate: 100% (gate ≥ 95)

**By Phase (v0.6.0 — not yet started):**

| Phase             | Plans | Total | Avg/Plan |
|-------------------|-------|-------|----------|
| (roadmap pending) | -     | -     | -        |

## Accumulated Context

### Decisions

All v0.4.0 + v0.5.0 decisions logged in PROJECT.md Key Decisions table with outcomes.

v0.6.0 locked decisions (D-SCOPE-1..4, see `.planning/v0.6.0-SCOPE.md`):

- D-SCOPE-1: transition = alias mince + `DeprecationWarning` → nouveau chemin; suppression des alias en v0.7.0 (zéro rupture brutale).
- D-SCOPE-2: la vraie implémentation vit dans l'accessor; l'ancien `db.*` devient le wrapper qui warn + délègue.
- D-SCOPE-3: les 5 accessors (`timescale`/`admin`/`schema`/`maint`/`backup`) en un seul milestone (~5-6 phases).
- D-SCOPE-4: parité sync/async obligatoire; `test_parity` enregistre les 5 nouveaux accessors.

Open questions tranchées au cadrage (2026-06-17): `db.schema.*` reste un seul bloc (DDL + introspection); DataFrame reste à plat sur `db.*`; `create_spatial_index`/`list_geometry_columns` → `db.spatial.*`.

### Pending Todos

None.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-06-17 — milestone v0.6.0 started via /gsd-new-milestone
Stopped at: PROJECT.md + STATE.md updated; defining requirements next
Resume file: None
Next action: define REQUIREMENTS.md, then spawn roadmapper

## Operator Next Steps

- Define v0.6.0 requirements, then create the roadmap (in progress via /gsd-new-milestone).
