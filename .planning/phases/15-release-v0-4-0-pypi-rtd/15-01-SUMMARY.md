---
phase: 15-release-v0-4-0-pypi-rtd
plan: "01"
subsystem: docs
tags: [docs, sphinx, spatial, postgis, autodoc]
dependency_graph:
  requires: []
  provides: [spatial-docs, postgis-docs-update, autodoc-spatial]
  affects: [docs/postgis.md, docs/database.md, docs/api-autodoc.md, docs/api-reference.md, docs/spatial.md, docs/index.md]
tech_stack:
  added: []
  patterns: [MyST-markdown, Sphinx-autodoc, numpydoc]
key_files:
  created:
    - docs/spatial.md
  modified:
    - docs/postgis.md
    - docs/database.md
    - docs/api-autodoc.md
    - docs/api-reference.md
    - docs/index.md
decisions:
  - "Intersection block kept as raw execute() with added db.spatial.intersects predicate example — ST_Intersection aggregate (self-join) has no helper equivalent"
  - "ST_MakeEnvelope block kept as to_geodataframe(sql=...) with explanatory comment — no envelope-form within() helper"
  - "DML UPDATE block kept as raw execute() with comment — db.spatial.* helpers are SELECT-only"
  - "Spatial Analysis example kept as raw SQL with prose note directing readers to db.spatial.* for single-table ops"
metrics:
  duration: "342s (~5.7 min)"
  completed: "2026-06-14"
  tasks_completed: 2
  files_modified: 6
---

# Phase 15 Plan 01: Sphinx Docs — Spatial Helpers Update Summary

Replaced 7 raw `execute(...)` PostGIS examples in `docs/postgis.md` and 1 in
`docs/database.md` with `db.spatial.*` helper calls; added `pycopg.spatial` to the
Sphinx autodoc surface; created a 296-line `docs/spatial.md` narrative page covering
all 11 helpers; wired it into the index toctree; added a full `Spatial Helpers (db.spatial.*)`
section to `docs/api-reference.md`. Sphinx build `-W` and `interrogate --fail-under 95`
both exit 0.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Replace raw execute() PostGIS examples with db.spatial.* helpers | a1e0316 | docs/postgis.md, docs/database.md |
| 2 | Add autodoc, spatial.md, index toctree, api-reference section | 72890c4 | docs/api-autodoc.md, docs/spatial.md, docs/index.md, docs/api-reference.md |

## Acceptance Criteria — All Passed

- `grep -c 'db.spatial.contains' docs/postgis.md` → 1
- `grep -c 'db.spatial.dwithin' docs/postgis.md` → 3
- `grep -c 'db.spatial.distance' docs/postgis.md` → 1
- `grep -c 'db.spatial.buffer' docs/postgis.md` → 1
- `grep -c 'db.spatial.centroid' docs/postgis.md` → 1
- `grep -c 'db.spatial.area' docs/postgis.md` → 1
- `grep -c 'db.spatial.perimeter' docs/postgis.md` → 1
- `grep -c 'db.spatial.transform' docs/postgis.md` → 1
- `grep -c 'db.spatial.dwithin' docs/database.md` → 2
- `grep -c 'automodule:: pycopg.spatial' docs/api-autodoc.md` → 1
- `docs/spatial.md` exists, 296 lines (≥ 80), 24 occurrences of `db.spatial.`, contains all 6 required strings (into=, unit=, point=, wkt=, geojson=, ref=)
- `spatial` entry in docs/index.md toctree at line 16 (between postgis line 15 and timescaledb line 17)
- `docs/api-reference.md` contains heading `Spatial Helpers (db.spatial.*)`; all 11 helpers listed
- `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` exits 0
- `uv run interrogate pycopg --fail-under 95 --quiet` exits 0

## Deviations from Plan

### Auto-added improvements (Rule 2)

**1. [Rule 2 - Enhancement] Intersection section: kept raw SQL but added db.spatial.intersects example**
- **Found during:** Task 1
- **Issue:** The plan said "keep Intersection block as raw execute" but the RESEARCH §B also noted "show db.spatial.intersects for the simple predicate, note raw SQL for complex intersection area queries"
- **Fix:** Added a `db.spatial.intersects` predicate example above the existing raw-SQL aggregate block, with explanatory prose distinguishing the two use cases
- **Files modified:** docs/postgis.md

**2. [Rule 2 - Enhancement] ST_MakeEnvelope block: added clarifying comment**
- **Found during:** Task 1
- **Issue:** The plan said keep as-is; RESEARCH §B said "add a note that db.spatial.within handles the two-table JOIN form"
- **Fix:** Added a prose comment in the code block explaining ST_MakeEnvelope is not helper-covered and directing readers to `db.spatial.*` for single-table ops
- **Files modified:** docs/postgis.md

None of the deviations introduce new executable code or change signatures — documentation-only.

## Threat Flags

None. Documentation-only changes with no new attack surface. No credentials or secrets in examples; coordinate literals are illustrative.

## Known Stubs

None. All examples use realistic placeholder values (standard SF Bay Area coordinates), not hardcoded empty structures.

## Self-Check: PASSED

- docs/postgis.md: exists, contains db.spatial.* helpers for all 7 required operations
- docs/database.md: contains db.spatial.dwithin (2 occurrences)
- docs/api-autodoc.md: contains automodule:: pycopg.spatial
- docs/spatial.md: exists, 296 lines
- docs/index.md: contains "spatial" between postgis and timescaledb
- docs/api-reference.md: contains Spatial Helpers section with all 11 helpers
- Commit a1e0316: verified (Task 1)
- Commit 72890c4: verified (Task 2)
- Sphinx build: exits 0
- interrogate --fail-under 95: exits 0
