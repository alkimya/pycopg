---
phase: 42-spatial-v2-processing-helpers
plan: "03"
subsystem: spatial
tags: [spatial, postgis, parity-test, docs, stability, api-reference, coverage-gate]
dependency_graph:
  requires: [42-01, 42-02]
  provides:
    - test_spatial_v1_processing_surface
    - stability.md 6 new Stable API Contract rows
    - stability.md make_valid structure >= 3.2 note
    - api-reference.md 6 new Spatial Helpers rows (filter=)
    - README.md db.spatial.* method count 19
  affects:
    - tests/test_parity.py
    - docs/stability.md
    - docs/api-reference.md
    - README.md
tech_stack:
  added: []
  patterns: [named-frozenset-surface-test, stability-docs, filter-not-where-born-clean]
key_files:
  created: []
  modified:
    - tests/test_parity.py
    - docs/stability.md
    - docs/api-reference.md
    - README.md
decisions:
  - test_spatial_v1_processing_surface uses frozenset pattern matching test_timescale_v080_surface and test_schema_v090_surface
  - api-reference new rows use filter= (not where=) — born-clean per D-10
  - stability.md make_valid structure note covers D-04 passthrough posture
  - Pre-existing black/ruff drift fixed codebase-wide to satisfy acceptance gate
metrics:
  duration: "8 minutes"
  completed: "2026-06-29T09:27:21Z"
  tasks_completed: 3
  files_changed: 4
---

# Phase 42 Plan 03: Parity Test + Documentation Summary

**One-liner:** Named frozenset surface test `test_spatial_v1_processing_surface` guards all 6 Phase-42 processing ops on both spatial accessors; stability.md and api-reference.md document them with `filter=` and the PostGIS >=3.2 make_valid note; full suite green at 96.18%.

## What Was Built

### tests/test_parity.py

- Added `test_spatial_v1_processing_surface()` after `test_schema_v090_surface` — exact pattern mirrors `test_timescale_v080_surface` and `test_schema_v090_surface`
- `v42_surface = frozenset({"union", "difference", "intersection", "simplify", "convex_hull", "make_valid"})` — all 6 Phase-42 methods
- For each of `SpatialAccessor` / `AsyncSpatialAccessor`: builds `public` via `inspect.getmembers`, asserts `v42_surface - public` is empty
- `ACCESSOR_PAIRS` is unchanged (no edit)

### docs/stability.md

- **6 new rows** appended to the `### db.spatial.* / async_db.spatial.*` Stable API Contract table (after `list_geometry_columns`):

  | Method | Positional args | Keyword-only params |
  |--------|-----------------|---------------------|
  | `union` | `table` | `geom`, `schema`, `other_geom`, `filter`, `into`, `columns`, `order_by`, `limit` |
  | `difference` | `table` | `geom`, `schema`, `other_geom`, `filter`, `into`, `columns`, `order_by`, `limit` |
  | `intersection` | `table` | `geom`, `schema`, `other_geom`, `filter`, `into`, `columns`, `order_by`, `limit` |
  | `simplify` | `table` | `geom`, `schema`, `tolerance`, `preserve_topology`, `preserve_collapsed`, `filter`, `into`, `columns`, `order_by`, `limit` |
  | `convex_hull` | `table` | `geom`, `schema`, `filter`, `into`, `columns`, `order_by`, `limit` |
  | `make_valid` | `table` | `geom`, `schema`, `method`, `keep_collapsed`, `filter`, `into`, `columns`, `order_by`, `limit` |

- **D-04 version note** added to PostGIS floor section: `ST_MakeValid(method="structure")` requires PostGIS ≥ 3.2 / GEOS ≥ 3.10; on older servers raises a native error; pycopg does not pre-check server version; omit `method` to work on all PostGIS 3.0+ servers.

### docs/api-reference.md

- **6 new rows** added to the Spatial Helpers `db.spatial.*` table, using `filter=` (NOT `where=`) per D-10:
  - `union`, `difference`, `intersection` (binary — include `other_geom` param)
  - `simplify` (includes `tolerance`, `preserve_topology`, `preserve_collapsed`)
  - `convex_hull`
  - `make_valid` (includes `method`, `keep_collapsed`)
  - All return `list[dict] | GeoDataFrame`

### README.md

- `db.spatial.*` accessor row updated: count 13 → 19; example names changed to `contains`, `within`, `intersects`, `union`, `simplify`, `make_valid`

## Verification Results

| Check | Status |
|-------|--------|
| `uv run pytest tests/test_parity.py::test_spatial_v1_processing_surface -o addopts=""` | 1 passed |
| `uv run pytest tests/test_parity.py::test_accessor_parity tests/test_parity.py::test_accessor_parameter_kind_parity -o addopts=""` | 14 passed |
| `PGDATABASE=pycopg_test2 uv run pytest` (full suite) | 1567 passed, 2 skipped |
| Coverage gate (>= 95%) | 96.18% PASSED |
| `uv run ruff check pycopg tests` | clean |
| `uv run black --check pycopg tests` | clean (48 files unchanged) |
| `uv run sphinx-build -W -b html docs docs/_build/html` | La compilation a réussi (clean) |
| `-W error::DeprecationWarning` on 6 new methods | 75 passed — no DeprecationWarnings |
| New api-reference rows use `filter=` not `where=` | confirmed (6 new rows grep) |
| stability.md contains `structure` + `3.2` note | confirmed |
| README no longer says `(13 methods)` | confirmed — now `(19 methods)` |

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | 46e80c3 | test(42-03): add test_spatial_v1_processing_surface frozenset surface test |
| Task 2 | e223067 | docs(42-03): publish 6 Phase-42 processing ops in stability, api-ref, README |
| Task 3 | 44066ba | chore(42-03): apply black + ruff formatting across codebase; fix F841 noqa |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pre-existing ruff F841 unused variable in tests/test_deprecations.py**
- **Found during:** Task 3 (lint gate)
- **Issue:** An unused `db = MagicMock()` variable in `test_flat_core_kw_only_schema` (Phase 41 residue) caused `uv run ruff check pycopg tests` to fail, blocking the acceptance gate
- **Fix:** Removed the unused `db` variable; inlined `# noqa: N806` comments to survive black's multi-line parenthesized form (which placed the noqa on the closing paren, not the assignment line)
- **Files modified:** `tests/test_deprecations.py`
- **Commit:** 44066ba

**2. [Rule 3 - Blocking] Pre-existing black formatting drift across 14 files**
- **Found during:** Task 3 (format gate)
- **Issue:** `uv run black --check pycopg tests` would reformat 14 files — all pre-existing from prior phases (42-01 and 42-02 only checked `pycopg/spatial.py`, not the full codebase); the plan's acceptance criterion requires the full-codebase gate to be clean
- **Fix:** Applied `uv run black pycopg tests` — purely whitespace/formatting changes, no logic changes
- **Files modified:** `pycopg/__init__.py`, `pycopg/async_database.py`, `pycopg/database.py`, `pycopg/etl.py`, `pycopg/maint.py`, `pycopg/queries.py`, `pycopg/schema.py`, `pycopg/timescale.py`, `tests/test_async_database.py`, `tests/test_audit_37_fixes.py`, `tests/test_database.py`, `tests/test_database_integration.py`, `tests/test_postgis_errors.py`, `tests/test_sql_injection.py`
- **Commit:** 44066ba

## Known Stubs

None. All documentation rows reflect the real implemented signatures from Phase 42-01 and 42-02.

## Threat Flags

- T-42-09 mitigated: the 6 new api-reference rows use `filter=` (confirmed by grep); no `where=` on any new row — no docs-vs-code freeze contradiction.
- T-42-10 mitigated: full suite including the per-builder injection tests from 42-01/42-02 ran green; coverage ratchet 96.18% >= 95%.
- T-42-SC: No packages installed in this plan.

## Self-Check: PASSED
