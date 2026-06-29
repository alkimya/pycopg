# Phase 44: Spatial v2 — Serialization + MVT - Context

**Gathered:** 2026-06-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Users serialize a PostGIS geometry column to **wire formats** via `db.spatial.*`
and `async_db.spatial.*` **without raw SQL**:

- `as_geojson` (`ST_AsGeoJSON`) — GeoJSON **text** per row; scalar helper.
- `as_text` (`ST_AsText`) — WKT **text** per row; scalar helper.
- `as_mvt` (`ST_AsMVT` aggregate) — a Mapbox Vector Tile as **`bytes`**; the
  hardest spatial method (composes `ST_Transform → ST_AsMVTGeom → ST_AsMVT` in a
  subquery, returns a single bytea).

This is the **last spatial v2 phase**. The **SPAT2-13 parity acceptance**
finalizes here: `test_accessor_parity` must cover the **full spatial v2 surface**
(processing P42 + aggregates P43 + serialization P44).

`as_geojson`/`as_text` follow the established **scalar-helper** pattern (added to
`_SCALAR_HELPERS`; text result; `into="gdf"` rejected; `columns=` passthrough
like `area`/`perimeter`/`centroid`). `as_mvt` is the **one return-shape
exception** — it returns `bytes`, is **NOT** in `_SCALAR_HELPERS`, and needs its
own execution/return path (single-cell bytea extraction, not the rows/gdf `_run`).

**In scope (locked by REQUIREMENTS / ROADMAP — not re-litigated):**
- SPAT2-10 (`as_geojson`), SPAT2-11 (`as_text`), SPAT2-12 (`as_mvt`) on both
  `SpatialAccessor` and `AsyncSpatialAccessor`.
- SPAT2-13: full-parity Async equivalents; per-builder `validate_identifiers`
  first + dedicated injection test; `test_accessor_parity` covers the full
  spatial v2 surface (parity acceptance criterion satisfied here).
- The enforced MVT pipeline `ST_Transform → ST_AsMVTGeom → ST_AsMVT` (no
  raw-geometry shortcut; criterion #2).
- Cross-cutting: `validate_identifiers` line 1 + injection test, **born-clean
  `filter=` only** (NO `where=` alias — these are new 1.0 methods), kw-only
  signature (`table` positional), `test_accessor_parity` +
  `test_accessor_parameter_kind_parity`, zero new runtime deps, coverage ratchet
  ≥95%, two-layer tests (SQL-shape mock + live PostGIS).

**Out of scope (deferred — do NOT pull in):**
- API completeness gaps + structured logging (transaction/savepoint controls,
  `%(name)s` named-param docs, `db.health()`, `pycopg/logging.py`) → Phase 45.
- mypy-strict + `py.typed` gate, `@overload` on `into=` methods → Phase 46.
- Release v1.0.0 (version bump, CHANGELOG, MIGRATION, tag, publish) → Phase 47.
- Non-3857 MVT target CRS, per-geometry `ST_AsMVTGeom` clip/buffer tuning, KML/
  GML/SVG serializers, raster — additive 1.x (see Deferred).

</domain>

<decisions>
## Implementation Decisions

### `as_mvt` parameter surface — frozen at 1.0 (D-01)
- **D-01:** **Pragmatic-full surface.** `as_mvt` exposes the knobs a real
  `/tiles/{z}/{x}/{y}.mvt` endpoint needs so callers never fall back to raw SQL
  (MVT is the milestone *differentiator*). Signature shape:
  ```python
  def as_mvt(
      self,
      table: str,
      *,
      geom: str = "geometry",
      schema: str = "public",
      tile_z: int,                       # required (D-02)
      tile_x: int,                       # required (D-02)
      tile_y: int,                       # required (D-02)
      layer_name: str = "default",       # ST_AsMVT 2nd arg (%s param)
      extent: int = 4096,                # tile extent; int() coercion
      columns: list[str] | None = None,  # feature-attribute columns
      feature_id_column: str | None = None,  # ST_AsMVT feature_id_name
      srid: int | None = None,           # source-CRS override (D-04)
      filter: str | None = None,         # pre-aggregate WHERE
  ) -> bytes:
  ```
  Rationale: each new kw-only param with a default is additive-safe, but shipping
  the common ones now (named layer, feature attributes, picking id, extent)
  avoids forcing raw SQL at the freeze. `layer_name` is a `%s` bind;
  `extent`/`tile_*`/`srid` go through `int()` (injection-safe); `columns` and
  `feature_id_column` are identifier-validated (line-1 guard).

### `as_mvt` tile coordinates (D-02)
- **D-02:** Names **`tile_z`, `tile_x`, `tile_y`** (matches the frozen ROADMAP /
  REQUIREMENTS acceptance text), **Z/X/Y order** (matches URL `/{z}/{x}/{y}` and
  `ST_TileEnvelope(z, x, y)` arg order), **required keyword-only** (no defaults).
  Honors the D-09 kw-only freeze with **no positional carve-out** — `table`
  remains the only positional arg, so `test_accessor_parameter_kind_parity` stays
  intact. Call reads `db.spatial.as_mvt("roads", tile_z=12, tile_x=2048,
  tile_y=1361)`. All three coerced via `int()` and fed to `ST_TileEnvelope`.

### `as_mvt` source CRS + pipeline (D-03, D-04)
- **D-03:** **Target CRS is always 3857.** The builder ALWAYS emits the full
  pipeline — `ST_AsMVT(q.*, layer_name, extent, 'geom_mvt'[, feature_id]) FROM (
  SELECT <columns>, ST_AsMVTGeom(ST_Transform(<src>, 3857),
  ST_TileEnvelope(tile_z, tile_x, tile_y), extent) AS geom_mvt FROM
  <schema>.<table> AS t [WHERE <filter>]) AS q WHERE q.geom_mvt IS NOT NULL`. No
  raw-geometry shortcut (criterion #2). The inner `WHERE q.geom_mvt IS NOT NULL`
  drops geometries that clip away. `ST_TileEnvelope` is **PostGIS ≥ 3.0** — add a
  version note in the docstring / stability matrix (the library floor is already
  3.0, so no runtime gate needed beyond documenting it; see PITFALLS Pitfall 3
  step 4 if a guard is later wanted).
- **D-04:** **`srid: int | None = None` source override.** `None` (default) →
  `ST_Transform(t.{geom}, 3857)` trusting the column's stored SRID. When set →
  `ST_Transform(ST_SetSRID(t.{geom}, {int(srid)}), 3857)` to rescue **SRID-0 /
  untagged** columns (the common footgun — PITFALLS Pitfall 3 / Pitfall 2). The
  override is the `from_srid=` the research recommended, named `srid` for
  consistency with the rest of the spatial surface. `int(srid)` = injection-safe.
  Document the SRID-0 failure mode in the docstring.

### `as_mvt` empty-tile contract + return path (D-05)
- **D-05:** **Always returns `bytes`.** The accessor extracts the single bytea
  cell from the 1-row result and coerces: a `memoryview`/`bytes` value →
  `bytes(...)`; a NULL/`None` (empty aggregate over zero post-clip rows) →
  **`b""`**. Guarantees the `-> bytes` contract so a tile endpoint can always
  serve the result (empty tile = empty/204 response) with no `None` check.
  Document "empty tile = `b''`". `as_mvt` does **NOT** use the rows/gdf `_run`;
  it needs a small dedicated runner (sync + async) that runs the SQL via
  `self._db.execute`, reads `rows[0]` first column, and applies the coercion.
  A **zero-feature integration test** asserts `isinstance(result, bytes)` AND
  decodes a populated tile to the expected feature count (criterion #2 — an
  `isinstance(bytes)`-only test does NOT prove the pipeline; decode it).

### `as_geojson` options (D-06)
- **D-06:** `max_decimal_digits: int = 6` (display-safe ~0.1m, smaller payloads
  than PostGIS default 9) **plus** `include_bbox: bool = False` and
  `include_crs: bool = False`. The two flags compose the `ST_AsGeoJSON` **options
  bitmask** (`1` = bbox, `2` = short CRS) into one computed integer passed via
  `%s` alongside `max_decimal_digits`. Generated SQL: `SELECT <cols>,
  ST_AsGeoJSON(t.{geom}, %s, %s) AS geojson FROM ...`. Result key **`geojson`**
  (a JSON string; users `json.loads()` if they need a dict).

### `as_text` precision (D-07)
- **D-07:** `max_decimal_digits: int | None = None`. `None` (default) emits the
  **one-arg** `ST_AsText(t.{geom})` (full precision — WKT is debugging / exact
  interchange / round-trip, so no silent truncation). When set → the **two-arg**
  `ST_AsText(t.{geom}, %s)`. Result key **`wkt`**. (Deliberately asymmetric with
  `as_geojson`'s default-6, which is web-payload oriented.)

### `columns=` on the scalar serializers (D-08)
- **D-08:** **Keep `columns=`** on `as_geojson` and `as_text` (validated
  identifiers, selected alongside the text column — exactly like `area`/
  `perimeter`/`centroid`). Enables the common API shape `SELECT id, name,
  ST_AsGeoJSON(geom) AS geojson` → `{id, name, geojson}` rows without raw SQL.
  Both also carry born-clean `filter=`/`order_by=`/`limit=`. Both added to
  `_SCALAR_HELPERS` so `into="gdf"` raises `ValueError` (text, not geometry).

### Signature & parity (D-09, D-10) — carried forward from Phase 41/42/43
- **D-09:** Per Phase 41/43 D-09/D-03 — `table` **positional**; everything else
  **keyword-only**. New methods carry **`filter=` only — NO `where=` deprecated
  alias** (the shim is solely a migration aid for the 11 pre-1.0 spatial methods;
  born clean for the Phase-46 mypy-strict / `@overload` pass and the
  `-W error::DeprecationWarning` gate).
- **D-10:** Sync/async parity is non-negotiable — every method mirrored 1:1 on
  `AsyncSpatialAccessor` (`async def` + `await`), edited in the **same change** as
  the sync class. Enforced by `test_accessor_parity` **and**
  `test_accessor_parameter_kind_parity` (identical keyword-only markers on both
  classes — the Phase-41 KIND-parity guard that code-review caught last time).
  `as_mvt`'s async runner uses `await self._db.execute(...)`.

### Claude's Discretion
- **`as_geojson`/`as_text` builder factoring:** both are single-column scalar
  builders nearly identical to `build_area_sql`/`build_perimeter_sql` — share or
  not as the planner sees fit; each MUST keep its own injection test + frozen
  result key (`geojson` / `wkt`). `as_mvt` gets its **own dedicated builder**
  (`build_mvt_sql`) — research is explicit it should NOT share code (subquery
  shape + bytea return are unique).
- **`as_mvt` bytea-extraction runner:** exact mechanics of reading the single
  cell + `memoryview→bytes` coercion (a small `_run_mvt`/`_arun_mvt` helper vs
  inline) — planner's call; the D-05 contract (always `bytes`, NULL→`b""`) is the
  invariant.
- **Options-bitmask computation** for `as_geojson` (`1` if bbox, `+2` if crs) —
  inline vs helper; the two-flag → one-int mapping is the only requirement.
- Exact docstring wording for the SRID-0, empty-tile, PostGIS-3.0-`ST_TileEnvelope`,
  and `max_decimal_digits` notes (must exist; wording free).
- Plan/wave decomposition (e.g. the two simple scalar serializers as one plan,
  `as_mvt` as its own plan given its HIGH complexity; docs + the SPAT2-13
  full-surface parity assertion across the waves).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope & requirements
- `.planning/REQUIREMENTS.md` §"Spatial v2 — Serialization" (SPAT2-10, SPAT2-11,
  SPAT2-12) + **SPAT2-13** (the milestone-wide cross-cutting acceptance:
  full-parity Async equivalents, `validate_identifiers` first + injection test,
  `test_accessor_parity`) — the locked requirements this phase satisfies and
  finalizes.
- `.planning/ROADMAP.md` "Phase 44: Spatial v2 — Serialization + MVT" — goal + 4
  success criteria (note criterion #2 enforces the MVT pipeline + decode-to-valid;
  criterion #4 = SPAT2-13 full-surface parity acceptance).

### Research (HIGH confidence, this milestone)
- `.planning/research/FEATURES.md` §"Workstream 1: Spatial V2 — Serialization"
  (SPAT-V2-10..12, ~line 373) — API shapes, PostGIS signatures, the
  `ST_AsGeoJSON` options bitmask, the full `as_mvt` subquery SQL (~line 494), the
  param list, and the `_SCALAR_HELPERS` membership notes.
  **CAVEAT:** code blocks there were written 2026-06-27 (before Phase 41 + this
  discussion) — they show `where=` and tile coords as positional `x, y, z`. Use
  **`filter=`** (D-09), **`tile_z/tile_x/tile_y` required kw-only Z/X/Y** (D-02),
  and the D-01 surface (add `srid`, keep `feature_id_column`); otherwise
  authoritative on the SQL shapes.
- `.planning/research/PITFALLS.md` — **Pitfall 3** (ST_AsMVT needs EPSG:3857 +
  ST_AsMVTGeom clip; ST_TileEnvelope is PostGIS 3.0+; decode-don't-isinstance
  test → D-03/D-04/D-05), **Pitfall 2** (SRID mismatch / SRID-0 → D-04 override),
  Pitfall 1 (validate_identifiers dropped in builder additions), Pitfall 11
  (sync/async parity drift → D-10). Also the "Looks Done But Isn't" checklist.
- `.planning/research/SUMMARY.md` — §"Architecture Approach" (no new accessors;
  no `_resolve_geometry`); §sequencing note that `as_mvt` is the hardest and
  should be its own plan (~line 825).

### Source to modify (templates to copy)
- `pycopg/spatial.py`:
  - `build_area_sql` (~662) / `build_perimeter_sql` (~724) — the scalar
    single-column builder template (`validate` → `SELECT {_cols_str(columns)},
    <ST_*(...)> AS <key> FROM {schema}.{table} AS t` → `_append_tail` → return
    `(sql, [])`) to copy for `as_geojson`/`as_text`. Note their `%s` param-list
    use (area passes `[]`; geojson/text pass `[max_decimal_digits, options]` etc).
  - `_SCALAR_HELPERS` (1784) — add `"as_geojson"` and `"as_text"` (NOT `as_mvt`).
  - `_VALID_INTO` (1788), `_check_into` (1796) — the `into="gdf"`-on-scalar guard.
  - `_append_tail` (~149) — the WHERE→ORDER BY→LIMIT tail (the `has_where`
    threading; `as_mvt`'s `filter` lands in the inner subquery, not the tail).
  - `_run` sync (1877) / `_arun` async (3639) — the rows/gdf router. `as_mvt`
    needs a NEW sibling runner (`_run_mvt`/`_arun_mvt`) per D-05; the scalar
    serializers reuse `_run` with `into` forced to `"rows"` semantics.
  - scalar accessor methods `area` (2455) / `perimeter` (2534) / `centroid`
    (2613) and async `area` (4234) / `perimeter` (4316) / `centroid` (4398) —
    the method-wiring template (NOTE: these pre-1.0 methods still carry the
    `where=` shim — the NEW methods must NOT; born clean per D-09).
  - `int(srid)` interpolation precedent (~120/123/126, and P43
    `build_extent_sql` ~1770) — the injection-safe int cast reused by `as_mvt`
    `tile_*`/`extent`/`srid` (D-02/D-04).
- `pycopg/database.py` `execute` (~594) / `pycopg/async_database.py` `execute`
  (~602) — return `list[dict]`; `as_mvt` reads `rows[0][<first col>]` for the
  bytea cell (D-05).
- `pycopg/utils.py` `validate_identifiers` — the line-1 guard (table/schema/geom
  + `columns` + `feature_id_column`).
- `pycopg/exceptions.py` `InvalidIdentifierError` — the injection-test target.
  **NOTE (IN-02 carry-forward):** docstrings in spatial.py contain ~22
  `InvalidIdentifierErrorError` double-suffix typos (P41 rename artifact) — do
  NOT propagate the typo into the new methods' `Raises` sections; write
  `InvalidIdentifierError`.

### Conventions & contracts inherited
- `.planning/phases/43-spatial-v2-spatial-aggregates/43-CONTEXT.md` — D-08
  (two-layer tests), D-09/D-10 (born-clean `filter=`, parity + KIND-parity),
  result-column-naming + `int(srid)` precedents. Reused wholesale.
- `.planning/phases/42-spatial-v2-processing-helpers/42-CONTEXT.md` — D-07 (NULL
  pass-through), builder mechanics, the `test_spatial_v1_processing_surface`
  parity-surface test (template for a `test_spatial_serialization_surface` + the
  SPAT2-13 full-surface assertion).
- `.planning/phases/41-api-homogenization/41-CONTEXT.md` — D-03 (kw-only
  contract), D-09 (stacklevel), `-W error::DeprecationWarning` gate, KIND-parity
  guard origin.
- `docs/stability.md` — support matrix (PostGIS floor 3.0 hard / 3.2
  recommended). 3 new rows land here. `ST_AsGeoJSON`/`ST_AsText` are baseline
  PostGIS; `ST_AsMVT`/`ST_AsMVTGeom`/`ST_TileEnvelope` are **PostGIS ≥ 3.0**
  (document, not gate — floor is 3.0).
- `tests/test_spatial.py` — existing injection-test + `test_accessor_parity` +
  `test_accessor_parameter_kind_parity` conventions to extend; the
  `test_spatial_aggregates_surface` (P43) / `test_spatial_v1_processing_surface`
  (P42) surface tests are the template — the SPAT2-13 assertion must register the
  FULL spatial v2 surface (P42 + P43 + P44).
- `.planning/codebase/CONVENTIONS.md`, `.planning/codebase/ARCHITECTURE.md` —
  builder-pur + lazy accessor pattern.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `build_area_sql` / `build_perimeter_sql` — near-exact templates for
  `build_geojson_sql` / `build_text_sql` (single scalar column + `columns=`
  passthrough + `_append_tail`); differ only in the `ST_*` call and the `%s`
  param list (geojson: `[max_decimal_digits, options]`; text: `[]` or
  `[max_decimal_digits]`).
- `_check_into` + `_VALID_INTO` + `_SCALAR_HELPERS` — the scalar `into="gdf"`
  rejection path; add `as_geojson`/`as_text` to the frozenset.
- `build_extent_sql` (P43, ~1770) + `int(srid)` precedent — the injection-safe
  integer-interpolation pattern reused by `as_mvt` `tile_*`/`extent`/`srid`.
- `_run` (rows/gdf) — reused by the two scalar serializers (rows only). `as_mvt`
  needs a NEW dedicated runner (bytea single-cell → `bytes`, NULL→`b""`).
- `validate_identifiers` — line-1 guard; for `as_mvt` it covers
  `table`/`schema`/`geom` + `columns` + `feature_id_column`.

### Established Patterns
- Pure module-level `build_*_sql` (DB-free, returns `(sql, params)`) + thin
  accessor that validates `into=` then delegates; `SpatialAccessor` /
  `AsyncSpatialAccessor` mirrored 1:1, edited in one change.
- Scalar helpers select the computed column with a frozen `AS <key>` name
  (`geojson`, `wkt`) and pass `geom` as `geometry_column` (unused on the
  rows-only path).
- `as_mvt` breaks the rows/gdf return mold — a third return shape (`bytes`)
  with its own runner; the only spatial method whose builder also receives
  `tile_*`/`extent`/`srid`/`layer_name`/`feature_id_column`.
- Coverage ratchet ≥95% (baseline ~96% post-P43); `# pragma: no cover` only with
  em-dash justification.

### Integration Points
- `SpatialAccessor` (+3 methods) and `AsyncSpatialAccessor` (+3 methods) — edit
  both in one change; mirror the `as_mvt` async runner too.
- `tests/test_spatial.py` — SQL-shape mock tests (geojson options bitmask;
  as_text one-arg vs two-arg; **as_mvt full pipeline** asserting `ST_Transform` +
  `ST_AsMVTGeom` + `ST_TileEnvelope` + `ST_AsMVT` + the `q.geom_mvt IS NOT NULL`
  filter + the `ST_SetSRID` branch when `srid` is set); per-builder injection
  tests (malicious `table`/`geom`/`columns`/`feature_id_column`); live PostGIS
  integration (geojson/wkt rows; **as_mvt decode to expected feature count** +
  the zero-feature `b""` case); parity + KIND-parity; a
  `test_spatial_serialization_surface` + the **SPAT2-13 full-spatial-v2-surface**
  parity assertion.
- Docs: `docs/api-reference.md` spatial rows (3 new, `filter=`), the spatial
  guide page (MVT example serving `application/vnd.mapbox-vector-tile`), README
  spatial method count (22→25), and `docs/stability.md` (3 stable-tier rows +
  the PostGIS-3.0 `ST_TileEnvelope`/`ST_AsMVT` note + the GeoJSON-6-digits note).

</code_context>

<specifics>
## Specific Ideas

- Milestone framing "un maximum de fonctions sans SQL brut" + the SemVer freeze
  at 1.0 → `as_mvt` ships the **pragmatic-full** surface (D-01: `layer_name`,
  `extent`, attribute `columns=`, `feature_id_column`, `srid` override) now,
  because MVT is the differentiator and falling back to raw SQL for a tile
  endpoint defeats the milestone's purpose.
- `as_text` defaults to **full precision** (`None`) while `as_geojson` defaults
  to **6 digits** — deliberate asymmetry: WKT is for exact interchange/round-trip
  (truncation = silent data loss), GeoJSON is for web payloads (smaller is
  better).
- The MVT decode-don't-`isinstance` test is the criterion-#2 teeth: a test that
  only checks `isinstance(result, bytes)` would pass even if the pipeline emitted
  raw-CRS garbage — the integration test MUST decode to the expected feature
  count.
- `as_mvt` is the one method whose builder sees `tile_*`/`extent`/`srid`/
  `layer_name`/`feature_id_column` AND whose return is `bytes` — it warrants its
  own builder + own runner, not the shared scalar/`_run` machinery.

</specifics>

<deferred>
## Deferred Ideas

- **Non-3857 target CRS for MVT** — web tiles are universally EPSG:3857; a
  configurable target is YAGNI and would complicate the frozen signature. Use
  `db.execute()` for exotic tile CRSs. Additive 1.x if ever requested.
- **Per-geometry `ST_AsMVTGeom` tuning** (clip on/off, per-geom buffer) — the
  defaults (clip=true, extent=`extent`) cover standard tile servers; exposing
  them approaches raw-SQL complexity (FEATURES.md "rejected" table). Additive 1.x.
- **Other serializers** (`ST_AsKML`, `ST_AsGML`, `ST_AsSVG`, `ST_AsEncodedPolyline`)
  — not requested; GeoJSON/WKT/MVT cover the dominant web/interchange/tile cases.
  Additive 1.x.
- **`ST_TileEnvelope` PostGIS < 3.0 runtime guard** — the library floor is
  already PostGIS 3.0, so a try/except `UndefinedFunction` guard is unnecessary;
  documented in the stability matrix instead (PITFALLS Pitfall 3 step 4 if a
  hard guard is later wanted).
- **`json` auto-parse for `as_geojson`** — returns the raw JSON **string** (key
  `geojson`); callers `json.loads()` if they need a dict. Auto-parsing would
  surprise the streaming/HTTP-passthrough use case. Not deferred work, a contract.

### Carry-forward to Phase 47 (release) — open across spatial v2
- **IN-02:** ~22 `InvalidIdentifierErrorError` double-suffix docstring typos in
  `spatial.py` (P41 rename artifact) — clean up at release; do NOT propagate into
  the new P44 methods.
- **WR-01:** `docs/api-reference.md` still shows deprecated `where=` for the 11
  pre-1.0 spatial helpers — reconcile at release.
- **P43 WR-01/WR-02:** no live `into="gdf"` integration test for
  collect/union; all-NULL `extent(into="gdf")` uncovered — fold into the release
  audit's integration sweep.

</deferred>

---

*Phase: 44-Spatial v2 — Serialization + MVT*
*Context gathered: 2026-06-29*
