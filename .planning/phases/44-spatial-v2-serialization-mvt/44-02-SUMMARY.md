---
phase: 44-spatial-v2-serialization-mvt
plan: 02
subsystem: database
tags: [postgis, spatial, mvt, mapbox-vector-tile, sql-builder, serialization, pycopg]

# Dependency graph
requires:
  - phase: 44-01
    provides: "scalar serializer pattern (build_geojson_sql/build_text_sql), _SCALAR_HELPERS pattern, builder conventions"
  - phase: 43-spatial-v2-spatial-aggregates
    provides: "build_extent_sql int(srid) precedent, _append_tail group_by pattern"
  - phase: 42-spatial-v2-processing-helpers
    provides: "builder-pur pattern, injection-test template, KIND-parity guard"
  - phase: 41-api-homogenization
    provides: "filter= born-clean convention, D-09 kw-only, validate_identifiers line-1 rule"
provides:
  - "build_mvt_sql module-level builder (ST_Transform→ST_AsMVTGeom→ST_AsMVT pipeline, AS mvt alias)"
  - "SpatialAccessor._run_mvt (dedicated bytea runner: memoryview→bytes, None→b\"\")"
  - "AsyncSpatialAccessor._arun_mvt (async mirror via await self._db.execute)"
  - "SpatialAccessor.as_mvt (born-clean filter=, tile_z/x/y REQUIRED kw-only, returns bytes)"
  - "AsyncSpatialAccessor.as_mvt (parity: identical * boundary + await _check_postgis)"
  - "_read_varint + _count_mvt_features (dependency-free pure-Python MVT protobuf decoder, test-only)"
  - "TestBuildMvtSql (17 SQL-shape + injection tests)"
  - "TestMvtRouting (9 mock routing + coercion tests)"
  - "Live integration: test_as_mvt_decodes_to_feature_count + test_as_mvt_empty_tile_returns_empty_bytes + async mirror"
affects:
  - "44-03 (parity test will cover as_mvt alongside as_geojson/as_text)"
  - "test_parity.py serialization surface test (plan 03)"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dedicated MVT subquery builder: validate_identifiers line-1 + columns + feature_id_column validation; int()-coerced tile coords; AS mvt alias; inner-WHERE filter (NOT _append_tail); params=[layer_name, ext] only"
    - "Dedicated bytea runner (_run_mvt/_arun_mvt): rows[0]['mvt'], memoryview→bytes, None→b'' (D-05)"
    - "D-04 SRID rescue: srid=None→ST_Transform(t.geom, 3857); srid set→ST_Transform(ST_SetSRID(t.geom, {int(srid)}), 3857)"
    - "Pure-Python MVT protobuf decoder for test assertions (verified vs PostGIS 3.6): _read_varint + _count_mvt_features"
    - "D-09 born-clean: no into= / no _check_into / NOT in _SCALAR_HELPERS / NOT in _HELPER_CALLS"
    - "D-10 KIND-parity: identical * boundary on sync and async as_mvt"

key-files:
  created: []
  modified:
    - "pycopg/spatial.py"
    - "tests/test_spatial.py"

key-decisions:
  - "D-03 enforced: build_mvt_sql ALWAYS emits full ST_Transform→ST_AsMVTGeom→ST_AsMVT pipeline; q.geom_mvt IS NOT NULL outer filter; no raw-geometry shortcut"
  - "D-04: srid=None trusts stored SRID; srid=<int> injects ST_SetSRID rescue before transform"
  - "D-05: _run_mvt/_arun_mvt always return bytes (memoryview coerced, None→b\"\"); runner reads rows[0]['mvt'] via AS mvt alias"
  - "D-09: as_mvt born-clean filter= only; NOT in _SCALAR_HELPERS or _HELPER_CALLS; no where= alias"
  - "D-10: sync+async edited in same change; identical * boundary proven by existing test_accessor_parameter_kind_parity"
  - "Pitfall 5 avoided: AS mvt alias in build_mvt_sql makes rows[0]['mvt'] reliable (not fragile st_asmvt auto-name)"
  - "Criterion #2 implemented: live test decodes MVT bytes with _count_mvt_features to assert >= 1 feature (isinstance alone rejected)"

patterns-established:
  - "MVT tile endpoint recipe: build_mvt_sql + _run_mvt = complete /tiles/{z}/{x}/{y}.mvt handler without raw SQL"
  - "Pure-Python MVT decoder as test helper (no new runtime dep): _read_varint + _count_mvt_features (15 lines)"
  - "zoom=0 tile (covers entire world) as reliable integration test tile for any SRID-4326 point"
  - "zoom=20 x=0 y=0 (far-off tile) as reliable empty-tile fixture (POINT(0 0) is far from date-line/north-pole)"

requirements-completed: [SPAT2-12]

# Metrics
duration: 7min
completed: 2026-06-30
---

# Phase 44 Plan 02: MVT Tile Builder Summary

**build_mvt_sql dedicated subquery builder with enforced ST_Transform→ST_AsMVTGeom→ST_AsMVT pipeline, dedicated bytea runners, as_mvt on both accessors (born-clean filter=, bytes return, never None/memoryview), and live decode-to-feature-count integration proof**

## Performance

- **Duration:** 7 min
- **Started:** 2026-06-30T06:51:19Z
- **Completed:** 2026-06-30T06:58:XX Z
- **Tasks:** 3
- **Files modified:** 2

## Accomplishments

- `build_mvt_sql` module-level builder: `validate_identifiers` line-1 guard covering `table`/`schema`/`geom` + `columns` entries + `feature_id_column` (T-44-02); `int()` coercion for `tile_z/x/y/extent/srid` (T-44-02b); enforced `ST_Transform → ST_AsMVTGeom(ST_TileEnvelope(z,x,y), ext) → ST_AsMVT` pipeline (D-03); `AS mvt` alias (Pitfall 5); inner-subquery `WHERE filter` (NOT `_append_tail`); `params = [layer_name, ext]` exactly two
- `SpatialAccessor._run_mvt` + `AsyncSpatialAccessor._arun_mvt`: dedicated bytea runners reading `rows[0]["mvt"]`, coercing `memoryview→bytes(...)`, mapping `None→b""` (D-05 contract)
- `SpatialAccessor.as_mvt` + `AsyncSpatialAccessor.as_mvt`: born-clean (D-09) — no `into=`, no `_check_into`, not in `_SCALAR_HELPERS`, not in `_HELPER_CALLS`; `tile_z/tile_x/tile_y` REQUIRED keyword-only; identical `*` boundary on sync and async (KIND parity, D-10)
- `srid=` D-04 rescue branch: `srid=None` → `ST_Transform(t.geom, 3857)`; `srid=<int>` → `ST_Transform(ST_SetSRID(t.geom, {int(srid)}), 3857)`
- `_read_varint` + `_count_mvt_features`: dependency-free pure-Python MVT protobuf decoder (test-only; no `uv add`); module-level self-check `assert _count_mvt_features(b"") == 0`
- `TestBuildMvtSql`: 17 SQL-shape + injection tests (table/geom/columns/feature_id_column injection; ST_Transform/ST_AsMVTGeom/ST_TileEnvelope literal coords/ST_AsMVT/q.geom_mvt IS NOT NULL/AS mvt assertions; srid branch; params=2 invariant; feature_id_column literal not param)
- `TestMvtRouting`: 9 mock routing tests (bytes pass-through, memoryview coercion, None→b"", %s count == len(params)) for both sync and async — via `_MvtSyncDb`/`_MvtAsyncDb` mock classes
- Live integration tests: `test_as_mvt_decodes_to_feature_count` (zoom=0 world tile, `_count_mvt_features(result) >= 1`); `test_as_mvt_empty_tile_returns_empty_bytes` (zoom=20 far-off, `result == b""`); `test_async_as_mvt_decodes_to_feature_count` (async mirror, D-10 proof)

## Task Commits

1. **Task 1: build_mvt_sql builder + SQL-shape/injection tests** - `4c75ff1` (feat)
2. **Task 2: _run_mvt/_arun_mvt runners + as_mvt on both accessors + mock routing tests** - `355ee24` (feat)
3. **Task 3: pure-Python MVT decoder + live integration tests** - `13398d6` (feat)

## Files Created/Modified

- `/home/loc/workspace/pycopg/pycopg/spatial.py` - Added `build_mvt_sql` builder; `SpatialAccessor._run_mvt`; `SpatialAccessor.as_mvt`; `AsyncSpatialAccessor._arun_mvt`; `AsyncSpatialAccessor.as_mvt`
- `/home/loc/workspace/pycopg/tests/test_spatial.py` - Added `build_mvt_sql` import; `_read_varint` + `_count_mvt_features` helpers + self-check; `_MvtSyncDb` + `_MvtAsyncDb` mock classes; `TestBuildMvtSql` (17 tests); `TestMvtRouting` (9 tests); live integration tests on `TestIntegration`

## Decisions Made

- **D-03 enforced pipeline:** `build_mvt_sql` always emits `ST_Transform → ST_AsMVTGeom → ST_AsMVT`; the `q.geom_mvt IS NOT NULL` outer filter is structural; no raw-geometry shortcut allowed.
- **AS mvt alias:** Using `AS mvt` in the outer SELECT makes `rows[0]["mvt"]` reliable and immune to PostGIS auto-naming changes (Pitfall 5 avoided).
- **inner-WHERE for filter=:** `filter` is appended to the inner subquery as `WHERE {filter}`, not through `_append_tail` — the outer query has a fixed `WHERE q.geom_mvt IS NOT NULL`.
- **feature_id_column as literal identifier:** PostGIS requires the column name in the query text (not a `%s` bind); validated via `validate_identifiers` then interpolated directly; document PostGIS integer-type requirement.
- **Dedicated mock DB classes:** `_MvtSyncDb`/`_MvtAsyncDb` with configurable `mvt_value` are cleaner than patching `_RecordingSyncDb` (which returns `[{"ok":1}]`).
- **zoom=0 / zoom=20 tile strategy:** zoom=0 (one tile covering the full world) is the simplest way to guarantee a SRID-4326 point is inside a tile; zoom=20 x=0 y=0 is reliably far from POINT(0 0).

## Deviations from Plan

None — plan executed exactly as written. TDD cycle followed (RED confirmed via ImportError for Task 1, AttributeError for Task 2; GREEN confirmed by test pass). `_MvtSyncDb`/`_MvtAsyncDb` classes were added (plan implied but didn't explicitly name them) — this is an implementation detail within the task scope, not a deviation.

## Issues Encountered

None.

## Threat Surface Scan

All threats in the plan's `<threat_model>` are mitigated:
- T-44-02: `validate_identifiers(table, schema, geom)` is line 1 of `build_mvt_sql`; `columns` and `feature_id_column` also validated before interpolation. `TestBuildMvtSql` has injection tests for all four identifier paths.
- T-44-02b: `tile_z`/`tile_x`/`tile_y`/`extent`/`srid` coerced via `int()` before SQL assembly; non-integer raises `ValueError`/`TypeError`. No caller string reaches SQL text.
- T-44-02c: `filter=` raw fragment is accepted risk (documented escape hatch, consistent with full spatial surface).
- T-44-02d: Denial of service accepted (PostGIS handles bounds; `int()` prevents non-numeric abuse).

No new security-relevant surface beyond what the plan's threat model covers.

## Known Stubs

None — `as_mvt` makes real PostGIS calls in integration tests and decodes the result to feature count.

## Next Phase Readiness

- `build_mvt_sql`, `_run_mvt`/`_arun_mvt`, `as_mvt` on both accessors are stable, injection-tested, and live-integration-proven.
- `_count_mvt_features` decoder is available for any future MVT test that needs structural verification.
- `_SCALAR_HELPERS` correctly excludes `as_mvt` (returns bytes, not rows/gdf).
- All plan verification commands pass: SQL-shape/injection (17), mock routing (9), live decode (3), lint/format clean.

---
*Phase: 44-spatial-v2-serialization-mvt*
*Completed: 2026-06-30*

## Self-Check: PASSED
