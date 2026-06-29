---
phase: 44
slug: spatial-v2-serialization-mvt
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-29
---

# Phase 44 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `44-RESEARCH.md` § Validation Architecture (HIGH confidence — verified against live PostGIS 3.6).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7+ with pytest-asyncio |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_spatial.py tests/test_parity.py -x -q` |
| **Full suite command** | `uv run pytest` (coverage gate `--cov-fail-under=95`) |
| **Estimated runtime** | ~60–120 seconds (full suite) |

**IMPORTANT:** Integration (live PostGIS) tests require `PGDATABASE=pycopg_test2` (default `pycopg_test` is broken — TSDB catalog mismatch, see MEMORY).

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_spatial.py tests/test_parity.py -x -q`
- **After every plan wave:** Run `uv run pytest` (full suite, coverage gate)
- **Before `/gsd-verify-work`:** Full suite must be green (≥95% coverage)
- **Max feedback latency:** ~120 seconds

---

## Per-Task Verification Map

Task IDs are assigned by the planner; this map fixes the requirement → test contract each task must satisfy. (✅ = test infra exists / auto-extends; ❌ W0 = new test class/function needed in this phase.)

| Requirement | Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|------------|-----------------|-----------|-------------------|-------------|--------|
| SPAT2-10 | `as_geojson` SQL shape: options bitmask (`include_bbox`→1, `include_crs`→2, both→3); `max_decimal_digits` via `%s` | T-44-01 | Identifiers validated before SQL; precision/options are `%s` params or `int()` | unit (mock) | `uv run pytest tests/test_spatial.py -k "TestBuildGeojsonSql" -x -q` | ❌ W0 | ⬜ pending |
| SPAT2-10 | `as_geojson` injection: malicious table/geom/columns raises `InvalidIdentifierError` before SQL sent | T-44-01 | `validate_identifiers` line-1 guard | unit (mock) | `uv run pytest tests/test_spatial.py -k "geojson_invalid" -x -q` | ❌ W0 | ⬜ pending |
| SPAT2-10 | `as_geojson` live: `list[dict]` with `geojson` key (JSON string) | — | N/A | integration | `PGDATABASE=pycopg_test2 uv run pytest tests/test_spatial.py -k "as_geojson" -x -q` | ❌ W0 | ⬜ pending |
| SPAT2-10 | `as_geojson(into="gdf")` raises `ValueError` (in `_SCALAR_HELPERS`) | — | N/A | unit (mock) | `uv run pytest tests/test_spatial.py -k "geojson_gdf" -x -q` | ❌ W0 | ⬜ pending |
| SPAT2-11 | `as_text` SQL shape: one-arg (`None`) vs two-arg (`max_decimal_digits` set) conditional | T-44-01 | Identifiers validated; precision is `%s`/`int()` | unit (mock) | `uv run pytest tests/test_spatial.py -k "TestBuildTextSql" -x -q` | ❌ W0 | ⬜ pending |
| SPAT2-11 | `as_text` injection: malicious identifiers raise `InvalidIdentifierError` | T-44-01 | `validate_identifiers` line-1 guard | unit (mock) | `uv run pytest tests/test_spatial.py -k "text_invalid" -x -q` | ❌ W0 | ⬜ pending |
| SPAT2-11 | `as_text` live: `list[dict]` with `wkt` key; `into="gdf"`→`ValueError` | — | N/A | integration | `PGDATABASE=pycopg_test2 uv run pytest tests/test_spatial.py -k "as_text" -x -q` | ❌ W0 | ⬜ pending |
| SPAT2-12 | `as_mvt` SQL shape: contains `ST_Transform`, `ST_AsMVTGeom`, `ST_TileEnvelope`, `ST_AsMVT`, `q.geom_mvt IS NOT NULL`; `srid=` branch adds `ST_SetSRID`; `tile_*`/`extent`/`srid` via `int()`; `layer_name`/`feature_id` handled per D-01 | T-44-02 | No raw-geometry shortcut (criterion #2); `int()` coercion + identifier validation incl. `feature_id_column` | unit (mock) | `uv run pytest tests/test_spatial.py -k "TestBuildMvtSql" -x -q` | ❌ W0 | ⬜ pending |
| SPAT2-12 | `as_mvt` injection: malicious table/geom/columns/feature_id_column raises `InvalidIdentifierError` | T-44-02 | `validate_identifiers` covers `feature_id_column` (SQL-literal, not `%s`) | unit (mock) | `uv run pytest tests/test_spatial.py -k "mvt_invalid" -x -q` | ❌ W0 | ⬜ pending |
| SPAT2-12 | `as_mvt` live: populated tile returns `bytes` (`len>0`) that **decode** to expected feature count ≥1 (decode-don't-isinstance) | — | N/A | integration | `PGDATABASE=pycopg_test2 uv run pytest tests/test_spatial.py -k "as_mvt and feature_count" -x -q` | ❌ W0 | ⬜ pending |
| SPAT2-12 | `as_mvt` empty tile: out-of-range coords → `b""` (`isinstance(bytes)` AND zero features); always `bytes`, never `None`/`memoryview` (D-05) | — | N/A | integration | `PGDATABASE=pycopg_test2 uv run pytest tests/test_spatial.py -k "as_mvt and empty_tile" -x -q` | ❌ W0 | ⬜ pending |
| SPAT2-13 | `test_spatial_serialization_surface`: both accessors expose `as_geojson`/`as_text`/`as_mvt` | — | N/A | unit (inspection) | `uv run pytest tests/test_parity.py -k "serialization_surface" -x -q` | ❌ W0 | ⬜ pending |
| SPAT2-13 | `test_accessor_parity` passes with all 3 new methods (full spatial v2 surface P42+P43+P44) | — | N/A | unit (inspection) | `uv run pytest tests/test_parity.py -k "test_accessor_parity" -x -q` | ✅ auto-extends | ⬜ pending |
| SPAT2-13 | `test_accessor_parameter_kind_parity` passes (kw-only markers match sync/async) | — | N/A | unit (inspection) | `uv run pytest tests/test_parity.py -k "kind_parity" -x -q` | ✅ auto-extends | ⬜ pending |
| SPAT2-13 | `_HELPER_CALLS` updated with `("as_geojson", {})`, `("as_text", {})` (NOT `as_mvt` — dedicated routing test) | — | N/A | unit (routing) | `uv run pytest tests/test_spatial.py -k "TestAccessorRouting" -x -q` | ✅ auto-extends | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_spatial.py` — `TestBuildGeojsonSql`, `TestBuildTextSql`, `TestBuildMvtSql` mock classes (SQL-shape + injection)
- [ ] `tests/test_spatial.py` — live PostGIS integration tests for `as_geojson`, `as_text`, `as_mvt` (incl. MVT decode-to-feature-count + zero-feature `b""`)
- [ ] `tests/test_spatial.py` — pure-Python MVT decode helper (test-only; **no new runtime dep**) for the feature-count assertion
- [ ] `tests/test_parity.py` — `test_spatial_serialization_surface` + register full spatial v2 surface for `test_accessor_parity`
- [ ] `tests/test_spatial.py` — `_HELPER_CALLS` updated (`as_geojson`, `as_text`) + dedicated `as_mvt` routing test

*Existing test infrastructure (pytest, pytest-asyncio, fixtures, the P42/P43 two-layer pattern) covers the framework; only the new classes/functions above are needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| MVT served over HTTP at `/tiles/{z}/{x}/{y}.mvt` with `application/vnd.mapbox-vector-tile` | SPAT2-12 (docs example) | End-to-end tile serving is out of scope (library returns `bytes`; HTTP layer is the caller's) | Docs guide shows the example; not a phase acceptance gate |

*All phase acceptance behaviors have automated verification (decode-in-test proves the MVT pipeline).*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
