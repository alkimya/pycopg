# Phase 44: Spatial v2 — Serialization + MVT - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-29
**Phase:** 44-Spatial v2 — Serialization + MVT
**Areas discussed:** MVT param surface, MVT tile coords, MVT CRS + empty tile, GeoJSON/WKT options

---

## MVT param surface (D-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Pragmatic full | tile coords + geom + schema + filter + layer_name + extent + columns= + feature_id_column. Covers real tile servers so users never drop to raw SQL; all kw-only with defaults, additive-safe but shipped now. | ✓ |
| Minimal | Only tile coords + geom + schema + filter; layer/extent fixed, no attributes/id. Matches ROADMAP example literally but geometry-only tiles. | |
| Middle | tile coords + geom + schema + filter + layer_name + columns=; drops extent + feature_id_column from 1.0. | |

**User's choice:** Pragmatic full (Rec.)
**Notes:** MVT is the milestone differentiator; the freeze is the moment to expose the common tile-server knobs. Each param is individually additive-safe, but shipping them now avoids forcing a raw-SQL fallback at 1.0.

---

## MVT tile coords (D-02)

| Option | Description | Selected |
|--------|-------------|----------|
| tile_z/x/y, req kw-only | Names tile_z/tile_x/tile_y (frozen ROADMAP/REQUIREMENTS text), Z/X/Y order (URL + ST_TileEnvelope order), required keyword-only, no positional carve-out; int() coercion. | ✓ |
| z/x/y, req kw-only | Shorter z/x/y names (research style), Z/X/Y, required kw-only. Diverges from the acceptance-criterion wording. | |
| Positional carve-out | tile coords positional after table to match the roadmap example's reading; breaks the D-09 'only table positional' freeze invariant. | |

**User's choice:** tile_z/x/y, required keyword-only (Rec.)
**Notes:** Honors the D-09 kw-only freeze with no exception, so `test_accessor_parameter_kind_parity` stays intact. Names match the frozen acceptance text; Z/X/Y matches URL `/{z}/{x}/{y}` and `ST_TileEnvelope(z, x, y)`.

---

## MVT CRS + empty tile (D-03, D-04, D-05)

**Source CRS:**

| Option | Description | Selected |
|--------|-------------|----------|
| srid override, None=trust | srid: int \| None = None. None → ST_Transform(geom, 3857) trusting stored SRID; set → wraps ST_SetSRID to rescue SRID-0 columns. int() safe. Pitfall 3's from_srid=. | ✓ |
| Trust stored SRID only | Always ST_Transform(geom, 3857), no override; document the column must carry a valid SRID. srid= addable additively in 1.x. | |

**Empty tile:**

| Option | Description | Selected |
|--------|-------------|----------|
| Always bytes, NULL→b'' | Coerce single bytea cell to bytes; NULL (empty aggregate) → b''. Guarantees -> bytes; document 'empty tile = b\"\"'; zero-feature integration test. | ✓ |
| Pass through raw | Return bytes or None as the DB yields; caller handles None. Breaks the clean -> bytes type. | |
| Raise on empty | Treat zero-feature tile as an error. Rejected — empty tiles are routine map panning. | |

**User's choice:** srid override (None=trust) + always-bytes (NULL→b'')
**Notes:** Target CRS fixed 3857; full ST_Transform→ST_AsMVTGeom→ST_AsMVT pipeline always emitted with `q.geom_mvt IS NOT NULL` filtering. ST_TileEnvelope is PostGIS ≥ 3.0 (documented, not gated — library floor is 3.0). The decode-don't-isinstance integration test is the criterion-#2 teeth.

---

## GeoJSON/WKT options (D-06, D-07, D-08)

**as_geojson options:**

| Option | Description | Selected |
|--------|-------------|----------|
| Both flags | max_decimal_digits=6 + include_bbox=False + include_crs=False composed into the options bitmask (1=bbox, 2=short CRS). | ✓ |
| Minimal | Just max_decimal_digits=6; no bbox/crs flags. Matches ROADMAP example literally. | |

**as_text precision:**

| Option | Description | Selected |
|--------|-------------|----------|
| None = full precision | max_decimal_digits: int \| None = None → one-arg ST_AsText (full precision); WKT is exact interchange/round-trip. | ✓ |
| Default to 6 | Match as_geojson for consistency; lossy by default, risks surprising round-trip users. | |

**columns= on the scalar serializers:**

| Option | Description | Selected |
|--------|-------------|----------|
| Keep columns= | Both carry columns= (validated, selected alongside the text result) like area()/centroid(); enables {id, name, geojson} without raw SQL. | ✓ |
| Drop columns= | Single text column only; forces a raw join/second query to attach an id. | |

**User's choice:** Both GeoJSON flags + as_text None (full precision) + keep columns=
**Notes:** Deliberate precision asymmetry — GeoJSON defaults to 6 (web payload), WKT to full (exact interchange). Result keys frozen: `geojson` / `wkt`. Both added to `_SCALAR_HELPERS` (into="gdf" rejected).

---

## Claude's Discretion

- `as_geojson`/`as_text` builder factoring (share or split the two near-identical scalar builders); each keeps its own injection test + frozen result key. `as_mvt` gets its own dedicated `build_mvt_sql` (no shared code — research-explicit).
- `as_mvt` bytea-extraction runner mechanics (dedicated `_run_mvt`/`_arun_mvt` vs inline; `memoryview→bytes` coercion); the D-05 always-bytes/NULL→b'' contract is the invariant.
- Options-bitmask computation for `as_geojson` (inline vs helper).
- Exact docstring wording for the SRID-0, empty-tile, PostGIS-3.0 ST_TileEnvelope, and max_decimal_digits notes (must exist; wording free).
- Plan/wave decomposition (e.g. the two scalar serializers as one plan, as_mvt as its own given HIGH complexity; docs + the SPAT2-13 full-surface parity assertion across waves).

## Deferred Ideas

- Non-3857 MVT target CRS — additive 1.x (use db.execute() for exotic tile CRSs).
- Per-geometry ST_AsMVTGeom tuning (clip/buffer) — additive 1.x.
- Other serializers (ST_AsKML/GML/SVG/EncodedPolyline) — additive 1.x.
- ST_TileEnvelope PostGIS < 3.0 runtime guard — unnecessary (floor is 3.0); documented in stability matrix.
- as_geojson returns raw JSON string (key `geojson`); callers json.loads() — a contract, not deferred work.
- Carry-forward to Phase 47: IN-02 (~22 InvalidIdentifierErrorError docstring typos), WR-01 (api-reference where= for 11 pre-1.0 helpers), P43 WR-01/WR-02 (into="gdf" integration coverage gaps).
