# Phase 43: Spatial v2 — Spatial Aggregates - Context

**Gathered:** 2026-06-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can aggregate a geometry column **by group** using PostGIS aggregate
functions via `db.spatial.*` and `async_db.spatial.*` **without raw SQL**:

- `collect_geometries` (`ST_Collect` aggregate) — bundle geometries into a
  `GEOMETRYCOLLECTION` per group.
- `union_aggregate` (`ST_Union` aggregate form) — dissolve shared boundaries
  into a single merged geometry per group.
- `extent` (`ST_Extent` aggregate) — bounding box per group; **dual return**:
  box2d text for `into="rows"`, a geometry for `into="gdf"`.

This is the **first GROUP-BY aggregate shape** in the spatial surface: one row
per group when `group_by` is set, exactly one row over the whole table when
`group_by=None`. All three follow the established **column-only pure-builder**
pattern (`validate_identifiers` line 1 + injection test, `filter=` only, pure
`build_*_sql → (sql, params)`, `_run/_arun` routing, full sync/async parity).

**In scope (locked by REQUIREMENTS / ROADMAP — not re-litigated):**
- SPAT2-07, SPAT2-08, SPAT2-09 — the 3 aggregate methods on both
  `SpatialAccessor` and `AsyncSpatialAccessor`.
- Optional `group_by`; GROUP-BY identifier list validated; documented
  NULL-propagation behavior with an intentional-NULL fixture.
- `extent` dual return (box2d text vs geometry cast).
- Cross-cutting: `validate_identifiers`-first + per-builder injection test,
  `filter=` only (new builders born clean), kw-only signature (`table`
  positional), `test_accessor_parity` + `test_accessor_parameter_kind_parity`,
  zero new runtime deps, coverage ratchet ≥95%.

**Out of scope (deferred — do NOT pull in):**
- Serialization + MVT (`as_geojson`/`as_text`/`as_mvt`) → Phase 44.
- `columns=` passthrough on aggregates (illegal under GROUP BY — see D-02).
- 2-geometry `ST_Collect(g1, g2)` form — only the aggregate form is in scope
  (the pairwise ops shipped in Phase 42).
- `gridSize` precision on the union (SPAT-F01) — additive 1.x.
- Transaction control, named params, health, logging, mypy-strict — Phases 45–46.

</domain>

<decisions>
## Implementation Decisions

### group_by ergonomics (D-01, D-02)
- **D-01:** `group_by: str | list[str] | None = None`. A bare `str` (the common
  single-column case, e.g. `group_by="region"`) is **normalized to `[str]`**
  internally; a `list[str]` handles composite grouping (`["region", "zone"]`);
  `None` = whole-table aggregate (exactly one row). Every group column is run
  through `validate_identifiers` (line 1 with `table`/`schema`/`geom`). Rationale:
  the API freezes at 1.0 — add the ergonomic single-string form now; it matches
  the `db.*` ergonomic feel and still validates as a list.
- **D-02:** **Drop `columns=` entirely** for the aggregate methods. SQL forbids
  selecting non-grouped, non-aggregate columns, so the SELECT is exactly the
  group_by columns (when present) + the aggregate expression `AS <result_col>`.
  This is the cleanest frozen contract and removes a foot-gun (no
  `columns=`-that-must-also-be-in-`group_by` server-error trap).

### GROUP-BY clause placement (D-03)
- **D-03:** The clause order is `SELECT <group_cols>, <agg> AS <col> FROM
  <schema>.<table> AS t [WHERE <filter>] [GROUP BY <group_cols>] [ORDER BY ...]
  [LIMIT ...]`. GROUP BY MUST sit **between** `WHERE` (the `filter=` fragment)
  and `ORDER BY`. `_append_tail` (spatial.py ~149) only does WHERE→ORDER BY→LIMIT,
  so the planner needs an **aggregate-aware tail** — either extend `_append_tail`
  with an optional `group_by` arg inserted after WHERE, or a small new helper.
  Precedent: `pycopg/timescale.py` `_build_time_bucket_sql` (~254) does
  `... [WHERE ...] GROUP BY bucket ORDER BY bucket`. `filter`/`order_by`/`limit`
  remain on the signature and stay meaningful (filter pre-aggregate; ORDER BY /
  LIMIT = top-N groups). Group columns qualified with the `t.` alias for
  consistency is acceptable (Claude's discretion).

### extent dual return (D-04, D-05)
- **D-04:** **Single `build_extent_sql(..., into)`** that branches on `into`
  (this method is the one exception to the "builder never sees `into`" rule):
  - `into="rows"` → `SELECT [<group_cols>,] ST_Extent(t.{geom})::text AS extent
    FROM ...` — returns the box2d string (`BOX(xmin ymin, xmax ymax)`).
  - `into="gdf"` → `SELECT [<group_cols>,] ST_SetSRID(ST_Extent(t.{geom})::geometry,
    {int(srid)}) AS extent FROM ...` — a real polygon geometry GeoPandas can load.
  - `extent` is **NOT** added to `_SCALAR_HELPERS` (`into="gdf"` is valid via the
    cast). Prefer one builder + one branch over two builder functions (DRY).
- **D-05:** `extent` exposes **`srid: int = 4326`** (keyword-only), consulted
  only on the `into="gdf"` cast and interpolated via `int(srid)` (injection-safe,
  the existing `build_point_geom`/`build_transform_sql` convention — `box2d` has
  no SRID, so one must be supplied; 4326 is the library-wide default). `srid` is
  ignored for `into="rows"`.

### Result column names — frozen at 1.0 (D-06)
- **D-06:** Per-op descriptive names, frozen as BOTH the `list[dict]` key AND the
  `into="gdf"` `geometry_column` (the 4th arg to `_run/_arun`):
  - `collect_geometries` → `collected`
  - `union_aggregate` → `dissolved` (the GIS term for ST_Union-aggregate; avoids
    reusing Phase 42's pairwise `union` → `union_geom`, keeping the two unions
    semantically distinct)
  - `extent` → `extent`

### NULL / empty-aggregate posture (D-07)
- **D-07:** **Pass-through.** PostGIS aggregates skip NULL geometry inputs; a
  group (or whole table) whose inputs are all-NULL or empty yields **one row with
  a NULL aggregate value**. Return it unchanged: `into="rows"` →
  `{"collected": None, ...}`; `into="gdf"` → a row with None/missing geometry. No
  `HAVING ... IS NOT NULL` filter (would hide empty groups and surprisingly turn
  the whole-table case into zero rows). Consistent with Phase 42 D-07. **Document
  the behavior** in each method docstring and add a **fixture with intentional
  NULL-geometry rows** asserting the documented output — this satisfies SPAT2-07/
  08/09 criterion 3.

### Test strategy (D-08) — carried forward from Phase 42 D-08
- **D-08:** Two layers — (a) **mock/SQL-shape authoritative** unit tests asserting
  the generated SQL (correct `ST_*` aggregate, `AS <result_col>`, GROUP-BY
  placement after WHERE / before ORDER BY, the `::text` vs `ST_SetSRID(...::geometry,
  {srid})` extent branch, `filter`/`order_by`/`limit` tail) + a **per-builder
  injection test** (malicious `table`/`geom`/`group_by` identifier →
  `InvalidIdentifierError` before any SQL is sent); (b) **live integration** on
  local PostGIS 3.6.4 / GEOS 3.13.1 with grouped + whole-table cases and the
  intentional-NULL fixture (D-07).

### Signature & parity (D-09, D-10) — carried forward from Phase 41/42, restated
- **D-09:** Signature shape per Phase 41 D-03 — `table` **positional**; everything
  else **keyword-only**: `geom="geometry"`, `schema="public"`, `group_by=None`,
  `srid=4326` (extent only), `into="rows"`, `filter`, `order_by`, `limit`. **No
  `columns=`** (D-02). The new methods carry **`filter=` only — NO `where=`
  deprecated alias** (the shim is solely a migration aid for the 11 pre-1.0
  spatial methods; new builders born clean for the Phase-46 mypy-strict /
  `@overload` pass and the `-W error::DeprecationWarning` gate).
- **D-10:** Sync/async parity is non-negotiable — every method mirrored 1:1 on
  `AsyncSpatialAccessor` (`async def` + `await self._run(...)`), edited in the
  **same change** as the sync class. Enforced by `test_accessor_parity` **and**
  `test_accessor_parameter_kind_parity` (the keyword-only markers must be
  identical on both classes — the Phase-41 KIND-parity guard).

### Claude's Discretion
- **Builder factoring:** `collect_geometries` and `union_aggregate` share the same
  aggregate-builder shape — encouraged to share `_build_agg_geom_sql(agg_func,
  result_col, ...)` (mirrors Phase 42's `_build_binary_geom_sql`); `extent` is its
  own builder (dual SQL, D-04). Each method MUST keep its own injection test +
  frozen result column.
- **Aggregate-tail mechanism (D-03):** extend `_append_tail` with an optional
  `group_by` arg vs a new small helper — planner's call.
- Group-column `t.` alias qualification — consistency-preferred but free.
- Exact docstring wording for the NULL/box2d/SRID notes (must exist; wording free).
- Plan/wave decomposition (e.g. the two share-a-builder aggregates as one plan,
  `extent` as another; or all three + docs across the waves).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope & requirements
- `.planning/REQUIREMENTS.md` §"Spatial v2 — Spatial Aggregates" (SPAT2-07..09)
  + the line-10 "Cross-cutting acceptance criteria for every new builder/method"
  note (`validate_identifiers` first + injection test + `test_accessor_parity`
  parity + zero new runtime deps) — the locked requirements this phase satisfies.
- `.planning/ROADMAP.md` "Phase 43: Spatial v2 — Spatial Aggregates" — goal + 5
  success criteria.

### Research (HIGH confidence, this milestone)
- `.planning/research/FEATURES.md` §"Workstream 1: Spatial V2 — Spatial Aggregates"
  (SPAT-V2-07..09, ~line 249) — API shapes, PostGIS signatures, generated-SQL
  proposals (whole-table vs GROUP BY), the box2d→geometry cast for `extent`, and
  the `collect_geometries`/`union_aggregate` naming rationale.
  **CAVEAT:** code blocks there show `group_by: list[str]` and `where=` (written
  2026-06-27, before Phase 41 + this discussion) — use `group_by: str | list[str]`
  (D-01) and `filter=` (D-09); otherwise authoritative.
- `.planning/research/PITFALLS.md` — Pitfall 1 (validate_identifiers dropped in
  builder additions), Pitfall 4 (NULL/degenerate geometry → D-07), Pitfall 11
  (sync/async parity drift → D-10). Also the "Looks Done But Isn't" checklist.
- `.planning/research/SUMMARY.md` — §"Architecture Approach" (no new accessors;
  no `_resolve_geometry`); aggregate-shape rationale.

### Source to modify (templates to copy)
- `pycopg/spatial.py`:
  - `_append_tail` (~149) — the `filter`/`order_by`/`limit` tail; needs the
    GROUP-BY-aware variant (D-03).
  - `_build_binary_geom_sql` (~959) + `build_union_sql`/`build_simplify_sql`/
    `build_convex_hull_sql` (Phase 42 builders, ~1268/1322/1434) — the
    derived-geometry-column builder templates (validate first → `SELECT ...,
    <expr> AS <name> FROM {schema}.{table} AS t` → tail → return `(sql, params)`).
  - `_SCALAR_HELPERS` (1443), `_VALID_INTO` (1447), `_check_into` (1455),
    `_to_named_binds` (1480).
  - `_run` sync (1536) / `_arun` async (3016) — derived col passed as
    `geometry_column`; `int(srid)` interpolation precedent at ~120/123/126.
  - `SpatialAccessor` class (~1509) / `AsyncSpatialAccessor` class (~2090+) —
    where the 3×2 new methods land.
- `pycopg/timescale.py` `_build_time_bucket_sql` (~254) — the GROUP-BY precedent
  (`... [WHERE] GROUP BY ... ORDER BY ...`).
- `pycopg/utils.py` — `validate_identifiers` (the line-1 guard).
- `pycopg/exceptions.py` — `InvalidIdentifierError` (the injection-test target).

### Conventions & contracts inherited
- `.planning/phases/42-spatial-v2-processing-helpers/42-CONTEXT.md` — D-01
  (result-column-naming precedent), D-07 (NULL pass-through), D-08 (two-layer
  tests), D-10/D-11/D-12 (born-clean `filter=`, parity, builder mechanics). This
  phase reuses all of them.
- `.planning/phases/41-api-homogenization/41-CONTEXT.md` — D-03 (kw-only contract),
  D-09 (stacklevel), `-W error::DeprecationWarning` gate, KIND-parity guard.
- `docs/stability.md` — support matrix (PostGIS floor 3.0 hard / 3.2 recommended);
  the 3 new methods' stable-tier rows land here. `ST_Collect`/`ST_Union`(agg)/
  `ST_Extent` are all Apache PostGIS (no version gate beyond the floor).
- `tests/test_spatial.py` — existing injection-test + `test_accessor_parity` +
  `test_accessor_parameter_kind_parity` conventions to extend; the
  `test_spatial_v1_processing_surface` parity-surface test (Phase 42) is the
  template for a `test_spatial_aggregates_surface` assertion.
- `.planning/codebase/CONVENTIONS.md`, `.planning/codebase/ARCHITECTURE.md` —
  builder-pur + lazy accessor pattern.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_build_binary_geom_sql` (Phase 42) — exact template for a shared multi-method
  aggregate builder (`_build_agg_geom_sql(agg_func, result_col, ...)`) backing
  `collect_geometries` + `union_aggregate`.
- `build_simplify_sql`/`build_convex_hull_sql` — single-column derived-geometry
  builder shape (validate → `SELECT {_cols_str}, <expr> AS <name> FROM ... AS t`
  → tail → `(sql, params)`); aggregates drop the `_cols_str(columns)` part (D-02).
- `_build_time_bucket_sql` (timescale.py) — the GROUP-BY-after-WHERE precedent.
- `_check_into` + `_VALID_INTO` — validate `into=` before SQL; do **not** add
  `collect_geometries`/`union_aggregate`/`extent` to `_SCALAR_HELPERS` (all yield
  geometry / gdf-valid, `extent` via the D-04 cast).
- `_run` / `_arun` — `into="gdf"` path uses `_to_named_binds` +
  `to_geodataframe(geometry_column=…)`; pass each method's frozen result column
  (D-06) as `geometry_column`.
- `int(srid)` interpolation (spatial.py ~120/123/126) — the injection-safe SRID
  cast pattern reused by `extent`'s gdf branch (D-05).
- `validate_identifiers` — identifier guard; called line 1 with
  `table`/`schema`/`geom` + every `group_by` column.

### Established Patterns
- Pure module-level `build_*_sql` (DB-free, returns `(sql, params)`) + thin
  accessor that delegates; `SpatialAccessor` / `AsyncSpatialAccessor` 1:1.
- Derived-geometry helpers pass the **derived** column name (not `geom`) as
  `geometry_column`. The aggregates follow this with their D-06 names.
- Coverage ratchet ≥95% (baseline ~96% post-Phase-42); `# pragma: no cover` only
  with em-dash justification.

### Integration Points
- `SpatialAccessor` (+3 methods) and `AsyncSpatialAccessor` (+3 methods) — edit
  both in one change.
- `tests/test_spatial.py` — add SQL-shape (incl. GROUP-BY placement + extent
  dual-branch), per-builder injection (incl. malicious `group_by`),
  live-integration (grouped + whole-table + intentional-NULL fixture), and parity
  coverage; `test_accessor_parity` + `test_accessor_parameter_kind_parity` +
  a `test_spatial_aggregates_surface` register the 3 new methods.
- Docs: `docs/api-reference.md` spatial rows, the spatial guide page, README
  spatial method count, and `docs/stability.md` stable-tier rows.

</code_context>

<specifics>
## Specific Ideas

- Milestone framing "un maximum de fonctions sans SQL brut" + the SemVer freeze
  at 1.0 → expose the ergonomic `group_by="region"` single-string form now (D-01)
  rather than defer to a 1.x additive change, since the signature freezes here.
- `union_aggregate` → `dissolved` (not `union_geom`) deliberately distinguishes
  the dissolve-all-boundaries aggregate from Phase 42's pairwise `union`.
- `extent` is the one method whose builder sees `into=` — the box2d-vs-geometry
  return is intrinsic to `ST_Extent` and can't be routed purely in `_run`.

</specifics>

<deferred>
## Deferred Ideas

- **Serialization + MVT** (`as_geojson`/`as_text`/`as_mvt`) → Phase 44 (already
  scheduled, not a deferral).
- **`gridSize` precision** on `union_aggregate` (SPAT-F01, GEOS ≥ 3.9) — out of
  the high-level API; additive 1.x.
- **2-geometry `ST_Collect(g1, g2)` form** — only the aggregate form is in scope;
  the pairwise geometry ops shipped in Phase 42.
- **`HAVING`-style group filtering** on the aggregate result — not requested;
  callers needing it use raw `db.execute()`. The `filter=` (pre-aggregate WHERE)
  + `order_by`/`limit` knobs cover the common cases.

</deferred>

---

*Phase: 43-Spatial v2 — Spatial Aggregates*
*Context gathered: 2026-06-29*
