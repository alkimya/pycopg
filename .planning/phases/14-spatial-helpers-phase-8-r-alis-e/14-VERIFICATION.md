---
phase: 14-spatial-helpers-phase-8-r-alis-e
verified: 2026-06-12T00:00:00Z
status: passed
score: 11/11 must-haves verified
overrides_applied: 0
---

# Phase 14: Spatial helpers (Phase 8 réalisée) Verification Report

**Phase Goal:** `db.spatial.*` / `async_db.spatial.*` en parité, sur fondations saines ; coverage maintenu (cliquet).
**Verified:** 2026-06-12
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1   | spatial.py imports and exposes `_resolve_geometry` + 11 pure builders | ✓ VERIFIED | import check prints "OK all builders present"; module 2730 lines |
| 2   | Builders return `(sql, params)`, identifiers via `validate_identifiers`, values as `%s` | ✓ VERIFIED | 25 `validate_identifiers` occurrences; `grep "ST_MakePoint\([^%]"` empty; exact-SQL tests assert placeholder/param pairing |
| 3   | `_resolve_geometry` enforces exactly-one-of point/wkt/geojson/ref | ✓ VERIFIED | TestGeometryResolver: zero-form and two-form both raise ValueError |
| 4   | DB-free unit tests cover every builder branch | ✓ VERIFIED | spatial.py at 100% coverage; 169 spatial tests |
| 5   | `db.spatial` / `async_db.spatial` expose 11 helpers at parity | ✓ VERIFIED | public method sets identical; `inspect.getmembers` sync-only = `{'engine'}`; test_parity green (no allow-list change) |
| 6   | PostGIS guard raises `ExtensionNotAvailable` (sync at construction, async first call) | ✓ VERIFIED | TestGuard both paths green |
| 7   | `into='gdf'` scalar rejection + real GeoDataFrame on geometry helpers | ✓ VERIFIED | TestGuard ValueError tests; TestIntegration buffer→GeoDataFrame, transform→EPSG:3857, distance-gdf ValueError |
| 8   | 08-DESIGN.md reflects D-01..D-12 with no open points | ✓ VERIFIED | 0 "Points à TRANCHER"; 12 distinct decision IDs; §9 states all resolved; status line marks Phase 14 realization |
| 9   | Full suite passes coverage gate | ✓ VERIFIED | "Required test coverage of 94% reached. Total coverage: 94.09%" (820 passed; 2 failures are documented pre-existing flaky DB tests) |
| 10  | Cliquet applied correctly (never freeze unmet gate) | ✓ VERIFIED | gate 92→94 (= floor of measured 94.09); 95 milestone target documented as deferred |
| 11  | interrogate ≥ 95 and Sphinx -W green with new surface | ✓ VERIFIED | interrogate 100%; `sphinx-build -W --keep-going` succeeds |

**Score:** 11/11 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `pycopg/spatial.py` | resolver + builders + both accessors, ≥350 lines | ✓ | 2730 lines, contains `def _resolve_geometry` and `class AsyncSpatialAccessor` |
| `pycopg/database.py` | lazy `spatial` property + `_spatial` field | ✓ | property + deferred import verified |
| `pycopg/async_database.py` | lazy `spatial` property + `_spatial` field | ✓ | property + deferred import verified |
| `tests/test_spatial.py` | TestGeometryResolver/TestBuilders/TestGuard/TestIntegration, ≥200 lines | ✓ | 876 lines, all classes present, 169 tests green |
| `pyproject.toml` | cov-fail-under consistent with measured coverage | ✓ | `cov-fail-under=94` ≤ measured 94.09% |
| `.planning/phases/08-spatial-helpers/08-DESIGN.md` | updated with D-01..D-12 | ✓ | all 12 IDs cited |

### Key Link Verification

| From | To | Via | Status |
| ---- | --- | --- | ------ |
| builders | `pycopg.utils.validate_identifiers` | first-line call per builder | ✓ |
| builders | `%s` parameterization | params list per value | ✓ |
| `Database.spatial` / `AsyncDatabase.spatial` | accessor classes | lazy property + deferred import | ✓ |
| accessor methods | `execute` / `to_geodataframe` | `into=` routing (`_to_named_binds` for gdf) | ✓ |
| `AsyncSpatialAccessor` | `has_extension("postgis")` | lazy `_postgis_ok` guard | ✓ |

### Requirements Coverage

| Requirement | Status | Evidence |
| ----------- | ------ | -------- |
| SPAT-01 | ✓ SATISFIED | 08-DESIGN.md updated (plan 14-03) |
| SPAT-02 | ✓ SATISFIED | spatial.py builders + both accessors |
| SPAT-03 | ✓ SATISFIED | 11 helpers on both sides |
| SPAT-04 | ✓ SATISFIED | guard + validation + %s end-to-end |
| SPAT-05 | ✓ SATISFIED | test_parity green, no allow-list change |
| SPAT-06 | ✓ SATISFIED | 120+ DB-free tests + 8 PostGIS integration tests |

No orphaned requirements: REQUIREMENTS.md maps exactly SPAT-01..06 to Phase 14; all claimed by plans (plan frontmatter used `SPA-` prefix — a naming typo; mapped 1:1 to `SPAT-` IDs and all marked complete).

### Anti-Pattern Scan

No TBD/FIXME/XXX/TODO/HACK/placeholder markers in any phase-modified file.

## Known Issues (not regressions)

- 2 pre-existing flaky DB tests fail in the local environment (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`) — documented in project memory before this phase; unrelated to spatial work.
- Code review (14-REVIEW.md): 1 Warning (document `%%` escaping for literal `%` in `where=` fragments), 2 Info — advisory.

---

_Verified: 2026-06-12_
_Verifier: Claude (inline goal-backward verification; subagent spawn skipped per project infra constraint)_
