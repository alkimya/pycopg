---
phase: 44-spatial-v2-serialization-mvt
verified: 2026-06-30T08:30:00Z
status: passed
score: 19/19
overrides_applied: 0
---

# Phase 44: Spatial v2 Serialization + MVT — Verification Report

**Phase Goal:** Users can serialize PostGIS geometry columns to GeoJSON, WKT, and Mapbox Vector Tile formats directly from `db.spatial.*`
**Verified:** 2026-06-30T08:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

All must-haves drawn from Plan frontmatter across Plans 01, 02, and 03.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can call `db.spatial.as_geojson(table, geom, max_decimal_digits=6)` and get `list[dict]` rows with a `geojson` key holding a JSON string (D-06) | VERIFIED | `SpatialAccessor.as_geojson` at spatial.py:3018; live integration test `test_as_geojson_returns_geojson_string` passes under `PGDATABASE=pycopg_test2` |
| 2 | `include_bbox=True` and `include_crs=True` compose the `ST_AsGeoJSON` options bitmask (1\|2=3) passed as a `%s` param alongside `max_decimal_digits` (D-06) | VERIFIED | `build_geojson_sql` at spatial.py:849-859: `options = (1 if include_bbox else 0) | (2 if include_crs else 0); return sql, [max_decimal_digits, options]`; `TestBuildGeojsonSql` bitmask assertions pass (26/26) |
| 3 | User can call `db.spatial.as_text(table, geom)` and get `list[dict]` rows with a `wkt` key; default `max_decimal_digits=None` emits one-arg `ST_AsText`, set value emits two-arg (D-07) | VERIFIED | `build_text_sql` at spatial.py:918-926: conditional branch confirmed; live test `test_as_text_returns_wkt_string` passes |
| 4 | Both `as_geojson` and `as_text` carry `columns=/filter=/order_by=/limit=` and are in `_SCALAR_HELPERS` so `into="gdf"` raises `ValueError` (D-08) | VERIFIED | `_SCALAR_HELPERS = frozenset({"area", "perimeter", "distance", "centroid", "as_geojson", "as_text"})` at spatial.py:2086-2087; `as_mvt` is correctly absent; gdf-rejection tests pass |
| 5 | Both methods are born-clean `filter=` ONLY — no `where=` deprecated alias (D-09) | VERIFIED | AST inspection confirms no `where` in kw-only params of `as_geojson` or `as_text` on either accessor class |
| 6 | Both methods exist 1:1 on `SpatialAccessor` and `AsyncSpatialAccessor`, edited in the same change (D-10) | VERIFIED | `AsyncSpatialAccessor.as_geojson` at spatial.py:5079; `AsyncSpatialAccessor.as_text` at spatial.py:5160; AST param lists are byte-identical between sync and async |
| 7 | A malicious `table/geom/column` passed to `build_geojson_sql` or `build_text_sql` raises `InvalidIdentifierError` before any SQL is sent | VERIFIED | `validate_identifiers(table, schema, geom)` is line 1 of both builders (spatial.py:849, 915); `TestBuildGeojsonSql` and `TestBuildTextSql` injection tests assert `InvalidIdentifierError` — all 26 pass |
| 8 | User can call `db.spatial.as_mvt(table, tile_z, tile_x, tile_y)` and receive `bytes` — the pragmatic-full surface (`layer_name`, `extent`, `columns`, `feature_id_column`, `srid`, `filter`) (D-01) | VERIFIED | `SpatialAccessor.as_mvt` at spatial.py:3167; live test returns bytes; full signature confirmed |
| 9 | `tile_z/tile_x/tile_y` are required keyword-only in Z/X/Y order, coerced via `int()` and fed to `ST_TileEnvelope(z, x, y)` (D-02) | VERIFIED | AST confirms `tile_z/tile_x/tile_y` have `None` defaults (required); `build_mvt_sql` at spatial.py:1062: `z, x, y, ext = int(tile_z), int(tile_x), int(tile_y), int(extent)` |
| 10 | `build_mvt_sql` ALWAYS emits the full pipeline `ST_Transform → ST_AsMVTGeom (ST_TileEnvelope) → ST_AsMVT` in a subquery with an outer `q.geom_mvt IS NOT NULL` filter — no raw-geometry shortcut (D-03) | VERIFIED | spatial.py:1073-1085: inner SELECT → `ST_AsMVTGeom(transform, ST_TileEnvelope(z, x, y), ext) AS geom_mvt` → outer `WHERE q.geom_mvt IS NOT NULL`; all 17 `TestBuildMvtSql` SQL-shape assertions pass |
| 11 | `srid=None` emits `ST_Transform(t.geom, 3857)`; `srid` set emits `ST_Transform(ST_SetSRID(t.geom, int(srid)), 3857)` to rescue SRID-0 columns (D-04) | VERIFIED | spatial.py:1065-1068: conditional branch confirmed; `TestBuildMvtSql.test_srid_branch` passes |
| 12 | `as_mvt` always returns `bytes` via a dedicated `_run_mvt/_arun_mvt` runner: `memoryview→bytes(...)`, `None→b''`, never `None`/`memoryview` (D-05) | VERIFIED | `_run_mvt` at spatial.py:2209-2232; `_arun_mvt` at spatial.py:4244-4267; `TestMvtRouting` 9 coercion tests pass; empty-tile live test asserts `result == b""` |
| 13 | `as_mvt` is born-clean `filter=` ONLY — no `where=` alias — and is NOT in `_SCALAR_HELPERS` (D-09) | VERIFIED | AST confirms no `where` in `as_mvt`; `_SCALAR_HELPERS` does not contain `"as_mvt"` |
| 14 | `as_mvt` exists 1:1 on `SpatialAccessor` and `AsyncSpatialAccessor`, edited in the same change; the async runner uses `await self._db.execute` (D-10) | VERIFIED | `AsyncSpatialAccessor.as_mvt` at spatial.py:5234; `_arun_mvt` at 4263: `rows = await self._db.execute(sql, params)`; AST kw-only lists are identical |
| 15 | A malicious `table/geom/columns/feature_id_column` passed to `build_mvt_sql` raises `InvalidIdentifierError` before any SQL is sent | VERIFIED | spatial.py:1054-1058: three-guard sequence before any SQL assembly; `TestBuildMvtSql` injection tests for all four identifier paths pass (17/17) |
| 16 | `test_spatial_serialization_surface` asserts BOTH `SpatialAccessor` and `AsyncSpatialAccessor` expose `as_geojson/as_text/as_mvt` (SPAT2-13 surface acceptance) | VERIFIED | `test_spatial_serialization_surface` at test_parity.py:202; `frozenset({"as_geojson", "as_text", "as_mvt"})` subset-checked against both classes; test passes |
| 17 | `test_accessor_parity` and `test_accessor_parameter_kind_parity` pass over the FULL spatial v2 surface (P42 + P43 + P44) — the SPAT2-13 parity acceptance finalizes here (D-10) | VERIFIED | 16/16 SPAT2-13-relevant parity tests pass; pre-existing `test_stream_parity` failure is TimescaleDB catalog mismatch (documented in MEMORY.md, predates Phase 44) |
| 18 | All three new methods are documented with `filter=` (born-clean, no `where=`) in `docs/api-reference.md`, `docs/stability.md`, the spatial guide, and the README count is corrected 22→25 (D-09) | VERIFIED | api-reference.md:219-221 — 3 rows with `filter=`, no `where=`; stability.md:118-143 — 3 stable-tier rows + notes; spatial.md:295-356 — Serialization Helpers section + MVT tile-endpoint; README.md:89 — `(25 methods)` |
| 19 | The full test suite passes with the coverage ratchet held ≥95% | VERIFIED | `PGDATABASE=pycopg_test2 uv run pytest` — 1690 passed, 2 skipped, 96.18% coverage; gate `--cov-fail-under=95` green |

**Score:** 19/19 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/spatial.py` | `build_geojson_sql`, `build_text_sql`, `build_mvt_sql` builders; `as_geojson/as_text/as_mvt` on both accessors; `_run_mvt`/`_arun_mvt` runners; `_SCALAR_HELPERS` updated | VERIFIED | All symbols present at expected line numbers; substantive implementations with full docstrings, real DB calls |
| `tests/test_spatial.py` | `TestBuildGeojsonSql`, `TestBuildTextSql`, `TestBuildMvtSql`, `TestMvtRouting` classes; `_read_varint`/`_count_mvt_features` helpers; `_HELPER_CALLS` entries; live integration tests | VERIFIED | All classes confirmed at lines 1882, 1958, 2026, 2186; decoders at 49/65; integration tests at 1484-1609 |
| `tests/test_parity.py` | `test_spatial_serialization_surface` function | VERIFIED | Present at line 202; frozenset guard for all 3 P44 methods on both accessors |
| `docs/api-reference.md` | 3 new rows for `as_geojson/as_text/as_mvt` with `filter=` signatures | VERIFIED | Lines 219-221; `as_mvt` return documented as `bytes`; no `where=` |
| `docs/stability.md` | 3 stable-tier rows + PostGIS-3.0 `ST_AsMVT` note + GeoJSON-6-digits / empty-tile notes | VERIFIED | Lines 118-143; all notes present |
| `docs/spatial.md` | `as_mvt` tile-endpoint example with `application/vnd.mapbox-vector-tile` | VERIFIED | Lines 328-356; example present with correct content-type |
| `README.md` | Count `22→25`; `as_geojson/as_text/as_mvt` in example list | VERIFIED | Line 89 reads `(25 methods)` with all three methods listed |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `SpatialAccessor.as_geojson` | `build_geojson_sql` | `sql, params = build_geojson_sql(...)` then `self._run(sql, params, into, geom)` | WIRED | spatial.py:3082-3094 — call and result use confirmed |
| `build_geojson_sql / build_text_sql` | `validate_identifiers` | line-1 identifier guard | WIRED | spatial.py:849 (`build_geojson_sql`), 915 (`build_text_sql`) — first statement of both |
| `SpatialAccessor.as_mvt` | `build_mvt_sql + _run_mvt` | `sql, params = build_mvt_sql(...); return self._run_mvt(sql, params)` | WIRED | spatial.py:3250-3264 — both calls confirmed |
| `build_mvt_sql` | `validate_identifiers` | line-1 guard covering `table/schema/geom` + `columns` + `feature_id_column` | WIRED | spatial.py:1054-1058 — three-stage guard sequence |
| `_run_mvt` | `self._db.execute` | `rows[0]["mvt"]` single bytea cell, `memoryview→bytes / None→b""` | WIRED | spatial.py:2228-2232 — execute call and coercion confirmed |
| `AsyncSpatialAccessor.as_geojson` | `build_geojson_sql` | `await self._check_postgis()` + same pattern | WIRED | spatial.py:5144-5158 |
| `AsyncSpatialAccessor.as_mvt` | `build_mvt_sql + _arun_mvt` | `return await self._arun_mvt(sql, params)` | WIRED | spatial.py:5308-5322 |
| `test_spatial_serialization_surface` | `SpatialAccessor / AsyncSpatialAccessor` | `inspect.getmembers` frozenset subset check | WIRED | test_parity.py:229-236 — both classes inspected |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `SpatialAccessor.as_geojson` | rows from `_run` | `self._db.execute(sql, params)` via `ST_AsGeoJSON` | Yes — live PostGIS query; integration test asserts `json.loads(row["geojson"])` yields dict with `"type"` | FLOWING |
| `SpatialAccessor.as_text` | rows from `_run` | `self._db.execute(sql, params)` via `ST_AsText` | Yes — live PostGIS query; integration test asserts `wkt.startswith("POINT")` | FLOWING |
| `SpatialAccessor.as_mvt` | bytes from `_run_mvt` | `rows[0]["mvt"]` from `self._db.execute` via `ST_AsMVT` | Yes — live PostGIS query; integration test decodes tile to `_count_mvt_features >= 1` | FLOWING |
| `AsyncSpatialAccessor.as_geojson` | rows from `_run` | `await self._db.execute` | Yes — async live integration test at test_spatial.py:1513 passes | FLOWING |
| `AsyncSpatialAccessor.as_mvt` | bytes from `_arun_mvt` | `await self._db.execute` | Yes — async live integration test at test_spatial.py:1590 passes; decoded to `>= 1 feature` | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Builder mock + injection tests green | `uv run pytest tests/test_spatial.py -k "TestBuildGeojsonSql or TestBuildTextSql" -x -q -o addopts=""` | 26 passed | PASS |
| MVT SQL-shape + injection tests green | `uv run pytest tests/test_spatial.py -k "TestBuildMvtSql" -x -q -o addopts=""` | 17 passed | PASS |
| MVT bytes-coercion routing tests green | `uv run pytest tests/test_spatial.py -k "TestMvtRouting" -x -q -o addopts=""` | 9 passed | PASS |
| Accessor routing covers `as_geojson/as_text` sync+async | `uv run pytest tests/test_spatial.py -k "TestAccessorRouting" -x -q -o addopts=""` | 77 passed | PASS |
| SPAT2-13 parity + surface guard | `uv run pytest tests/test_parity.py -k "serialization_surface or kind_parity or test_accessor_parity" -x -q -o addopts=""` | 16 passed | PASS |
| Live GeoJSON/WKT integration | `PGDATABASE=pycopg_test2 uv run pytest tests/test_spatial.py -k "as_geojson or as_text" -x -q -o addopts=""` | 11 passed | PASS |
| Live MVT decode-to-feature-count + empty-tile | `PGDATABASE=pycopg_test2 uv run pytest tests/test_spatial.py -k "as_mvt and (feature_count or empty_tile)" -x -q -o addopts=""` | 3 passed | PASS |
| Lint clean | `uv run ruff check pycopg tests` | All checks passed | PASS |
| Format clean | `uv run black --check pycopg tests` | 48 files unchanged | PASS |
| Full suite + coverage gate | `PGDATABASE=pycopg_test2 uv run pytest` | 1690 passed, 2 skipped, 96.18% (gate ≥95%) | PASS |

---

### Probe Execution

Step 7c: SKIPPED — no `scripts/*/tests/probe-*.sh` conventional probes and the phase plans declare none. Behavioral spot-checks above serve as the equivalent runtime verification.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| SPAT2-10 | 44-01 | GeoJSON serialization via `db.spatial.as_geojson` | SATISFIED | `build_geojson_sql` + `SpatialAccessor.as_geojson` + `AsyncSpatialAccessor.as_geojson` implemented; live test returns rows with parseable `geojson` key |
| SPAT2-11 | 44-01 | WKT serialization via `db.spatial.as_text` | SATISFIED | `build_text_sql` + both accessor `as_text` methods; live test returns rows with `wkt` key starting with `POINT` |
| SPAT2-12 | 44-02 | MVT generation via `db.spatial.as_mvt` returning `bytes` | SATISFIED | `build_mvt_sql` + `_run_mvt/_arun_mvt` + both accessor `as_mvt` methods; live decode proves `>= 1 feature`; empty tile returns `b""` |
| SPAT2-13 | 44-03 | Async parity + injection guards on all new builders | SATISFIED | `test_spatial_serialization_surface` + `test_accessor_parity` + `test_accessor_parameter_kind_parity` all pass; `validate_identifiers` is line 1 of all three builders with dedicated injection tests |

**Note on SPAT2-13 traceability table drift:** The REQUIREMENTS.md traceability table at line 136 shows `SPAT2-13 | Phase 44 | Pending` while the inline checkbox at line 40 shows `[x]`. This is the documented recurring REQUIREMENTS.md drift pattern (see MEMORY.md "Recurring GSD tooling taxes"). The implementation is fully complete and verified. The table cell needs a hand-update to `Complete`. This is informational only — not a gap.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | No TBD/FIXME/XXX/placeholder/stub patterns found in any Phase 44 modified file | — | — |

No debt-marker anti-patterns found in `pycopg/spatial.py`, `tests/test_spatial.py`, `tests/test_parity.py`, or the four docs/README surfaces.

---

### Human Verification Required

None. All must-haves are verifiable programmatically. All tests pass, all artifacts are substantive and wired, and all data flows are confirmed with live PostGIS execution.

---

## Gaps Summary

No gaps. All 19 must-haves verified. The REQUIREMENTS.md traceability table status for SPAT2-13 (`Pending` vs `[x]` inline) is a cosmetic documentation drift, not a functional gap — the implementation is complete.

---

_Verified: 2026-06-30T08:30:00Z_
_Verifier: Claude (gsd-verifier)_
