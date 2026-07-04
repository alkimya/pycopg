# Phase 52: Spatial Finish - Context

**Gathered:** 2026-07-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Complete the `db.spatial.*` accessor with 6 additive features/helpers, each following the shipped v1.0.0 spatial builder conventions. Additive-only under the frozen SemVer 1.0 API — no breaking changes, every existing default path stays byte-identical.

Delivers (SPAT-F01..F06):
- **SPAT-F01** — keyword-only `gridSize=` on `union`/`difference`/`intersection` (fixed-precision overlay)
- **SPAT-F02** — `db.spatial.length` (ST_Length)
- **SPAT-F03** — `db.spatial.envelope` (ST_Envelope)
- **SPAT-F04** — `db.spatial.point_on_surface` (ST_PointOnSurface)
- **SPAT-F05** — `db.spatial.is_valid` (ST_IsValid) + `db.spatial.is_valid_reason` (ST_IsValidReason)
- **SPAT-F06** — `overlaps`/`touches`/`crosses`/`disjoint` DE-9IM predicates

**Not in scope:** any new spatial subsystem (raster/RASTER-F01 stays in the frozen backlog); any breaking change to shipped spatial signatures; any new runtime dependency.

</domain>

<decisions>
## Implementation Decisions

### SPAT-F01 — gridSize= policy (union / difference / intersection)
- **D-01:** `gridSize` is a keyword-only `float | None = None` on all three overlay accessors AND their `build_*_sql` builders, threaded through the shared `_build_binary_geom_sql` helper. When set, it becomes the 3rd positional arg of the overlay function: `ST_Union(t.{geom}, t.{other_geom}, %s)` (likewise ST_Difference / ST_Intersection), bound as a `%s` parameter.
- **D-02:** **Pure passthrough, no client-side guard.** Do NOT validate the numeric range. In PostGIS every float is meaningful (`0` snaps to integer grid, negative disables the grid), so there is no invalid range to reject. Matches `buffer` (binds `distance`, no guard) and the D-06 SRID-mismatch passthrough precedent.
- **D-03:** **Byte-identical default path (success criterion).** When `gridSize is None`, emit the EXACT current SQL — no 3rd function argument — and return an empty params list `[]`, identical to the shipped overlay builders. A dedicated test MUST assert the `None`-path SQL string is byte-for-byte equal to the pre-change output for all three helpers.
- **D-04:** **No server-version pre-check.** `gridSize` requires PostGIS ≥ 3.1 / GEOS ≥ 3.9; on older servers PostGIS raises a native error (passthrough). Exactly the D-04 precedent used by `make_valid(method="structure")`. Document the ≥3.1/GEOS≥3.9 requirement in each docstring.

### SPAT-F04 — point_on_surface return shape
- **D-05:** Return a **geometry** point column named `point_on_surface` (`ST_PointOnSurface(t.{geom})`), supporting `into="rows"/"gdf"` — same shape as `envelope`/`buffer`/`union`, NOT the scalar x/y shape of `centroid`. Rationale: the guaranteed-inside representative point is used for labels/markers/mapping, which wants a real geometry (preserves SRID); `centroid`'s historical scalar shape is intentionally not mirrored.

### SPAT-F06 — DE-9IM predicate family
- **D-06:** `overlaps`/`touches`/`crosses` mirror `build_intersects_sql` / `intersects` **mechanically** — symmetric predicates, same 4 input forms (point/wkt/geojson/ref), same EXISTS subquery for `ref=`, **and the same `into="rows"/"gdf"` overload triplet as the shipped `intersects`/`contains`/`dwithin`** — a row-filter returning `list[dict]` for `into="rows"` (default) or a GeoDataFrame of the matching rows (table `geometry` column) for `into="gdf"`. Just swap the ST_* function name (ST_Overlaps / ST_Touches / ST_Crosses). **[Amended 2026-07-04 during plan-phase, per user decision: the original "(no `into=`)" parenthetical was a factual error — the live sibling predicates `intersects`/`contains`/`dwithin` already ship `into=` support (`tests/test_spatial.py` `_GDF_CALLS`), so "mirror `intersects` mechanically" REQUIRES the `into=` overloads. See 52-RESEARCH.md Pitfall 1.]**
- **D-07:** `disjoint` uses the **same uniform pattern** — supports all 4 input forms including `ref=` via EXISTS, **and the same `into="rows"/"gdf"` overloads per the amended D-06**. The docstring MUST document the footgun: `ref=` means "EXISTS a ref row disjoint from t" (near-always true), NOT "disjoint from all". This keeps the predicate family mechanically uniform (faithful to SPAT-F06 = the pairwise DE-9IM predicate). Rejected: omitting `ref=` for disjoint (breaks parity) and special-casing it as `NOT EXISTS(intersects)` (invents set-semantics not asked for).
- **D-08:** `disjoint`'s docstring MUST add a performance note: `ST_Disjoint` cannot use spatial indexes — point users to `NOT ST_Intersects` (or the `filter=` escape hatch) for large indexed tables.

### SPAT-F02 / F03 / F05 — output conventions
- **D-09:** **Bare operation-name AS labels** (become dict keys / gdf geometry column): `length`, `envelope`, `point_on_surface`, `is_valid`, `is_valid_reason`. Matches the majority convention (`difference`/`intersection`/`area`/`made_valid`); `union_geom` stays the lone historical exception — do NOT add a `_geom` suffix to new geometry columns.
- **D-10:** `length` **mirrors area/perimeter** — identical signature with `unit="m"` default (`::geography` cast → meters) or `unit="srid"` (raw), reusing `_validate_unit` (D-09 of the original spatial design). Scalar result → rows-only. Document that `ST_Length` returns 0 for non-linear geometries (polygons/points).
- **D-11:** `envelope` (ST_Envelope) returns a **geometry** column `envelope` → `into="rows"/"gdf"` (like the other geometry-returning helpers).
- **D-12:** `is_valid` (ST_IsValid) returns a **boolean** scalar column `is_valid` → rows-only (`_check_into` rejects `into="gdf"`). `is_valid_reason` (ST_IsValidReason) returns a **text** scalar column `is_valid_reason` → rows-only.

### Claude's Discretion
- Exact `@overload` stub shapes, docstring numpydoc wording, injection-test structure, and `_run` wiring are standard pattern-following — planner/executor follow the shipped `build_*_sql` + accessor + async-mirror template. No user decision needed.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope
- `.planning/REQUIREMENTS.md` — SPAT-F01..F06 definitions + the standing bar (parity, `validate_identifiers`-first, zero new deps, cov ≥95%, `mypy --strict`, interrogate 100%, Sphinx `-W`). Out-of-scope table (raster, breaking changes) prevents scope creep.
- `.planning/ROADMAP.md` §"Phase 52: Spatial Finish" — goal + 5 success criteria (byte-identical overlay default is criterion #1).

### Live pattern source (the shipped code to mirror — the design doc `08-DESIGN.md` is archived, so the code IS the spec)
- `pycopg/spatial.py` — the single file to edit. Both accessors live here: `SpatialAccessor` (sync, ~line 2159) and `AsyncSpatialAccessor` (mirror, ~line 4949). Edit BOTH.
  - Overlay builders to extend for gridSize: `_build_binary_geom_sql` (~1278), `build_union_sql`/`build_difference_sql`/`build_intersection_sql` (~1304/1370/1436) + accessor methods `union`/`difference`/`intersection` (~3814+).
  - Predicate pattern for SPAT-F06: `build_contains_sql`/`build_intersects_sql` (~207/287) + `_resolve_geometry` (~69, 4 input forms) + `_REF_SENTINEL` EXISTS handling + `contains`/`intersects` accessors (~2240/2520).
  - Measurement pattern for SPAT-F02: `build_area_sql`/`build_perimeter_sql` (~666/728) + `_validate_unit` (~52) + `area`/`perimeter` accessors (~3067/3148).
  - Geometry-scalar pattern for SPAT-F03/F04: `build_centroid_sql` (~1094, scalar x/y — the shape we DON'T follow for point_on_surface) and `build_buffer_sql`/`build_transform_sql` (~1151/1219, geometry-returning — the shape we DO follow).
  - Validity/guard pattern for SPAT-F05: `build_make_valid_sql` (~1650, the `made_valid` geometry helper) — is_valid/is_valid_reason are its scalar siblings.
  - Shared helpers: `_cols_str` (~137), `_append_tail` (~153), `_check_into` (~2105), `_to_named_binds` (~2130), `_run`/`_run_mvt` (~2186/2214).
- `tests/test_parity.py` — enforces sync/async accessor parity (`test_accessor_parity` / `test_accessor_parameter_kind_parity`); new methods MUST appear in both classes with identical kw-only signatures.

### Docs to update (helper reference)
- `docs/spatial.md` — user-facing spatial helper docs; the 6 new helpers get documented here.
- `docs/api-reference.md` — API reference surface.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_build_binary_geom_sql` — single funnel for all three overlay builders; add an optional `grid_size: float | None = None` param here once and all three inherit it. Emits the `%s` + returns `[grid_size]` only when set, `[]` when `None`.
- `_resolve_geometry` (4 input forms + `_REF_SENTINEL`) — reuse verbatim for all 4 new SPAT-F06 predicates.
- `_validate_unit` + `::geography` cast idiom — reuse for `length` (SPAT-F02).
- `_check_into` — enforces "geometry helpers allow gdf, scalar helpers rows-only". Applies as: envelope/point_on_surface → rows+gdf; length/is_valid/is_valid_reason → rows-only.
- `@overload` stub template (union has 3 overloads: `Literal["rows"]` → list[dict], `Literal["gdf"]` → GeoDataFrame, `str` → union) — copy for each new geometry-returning helper.

### Established Patterns
- Every helper = pure `build_*_sql()` (identifier-validated, `validate_identifiers` on line 1) + sync accessor method + async mirror + `@overload` stubs. User values bound as `%s`; identifiers f-string-interpolated only after `validate_identifiers`.
- Predicates are WHERE-clause row filters returning `list[dict]` (no `into=`); measurement/geometry helpers add a computed SELECT column.
- New 1.0-era methods are "born clean": kw-only after `table`, NO `where=` deprecated alias (D-10 of the freeze) — unlike the pre-1.0 helpers that carry a `where=`→`filter=` shim.
- Standing security requirement: a dedicated injection test per new helper asserting `validate_identifiers` rejects malicious `table`/`schema`/`geom`/`columns`.

### Integration Points
- Both `SpatialAccessor` and `AsyncSpatialAccessor` in `pycopg/spatial.py` must gain each new method (parity gate).
- `mypy --strict` (blocking gate) requires `@overload` stubs on any method whose return type varies with `into=`.
- Coverage ratchet ≥95% (baseline 96.65%) — new helpers need tests; interrogate 100% requires numpydoc docstrings.

</code_context>

<specifics>
## Specific Ideas

- gridSize byte-identical guarantee (D-03) is the single most testable invariant of the phase — a snapshot/equality assertion on the `None`-path SQL for all three overlay builders is the right verification.
- PostGIS function reference for the new helpers: ST_Union/ST_Difference/ST_Intersection (3-arg gridSize form, ≥3.1), ST_Length, ST_Envelope, ST_PointOnSurface, ST_IsValid, ST_IsValidReason, ST_Overlaps, ST_Touches, ST_Crosses, ST_Disjoint.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (Raster/RASTER-F01 and CDC/ETL-INC-F05 remain in the frozen backlog per the milestone decision; not re-litigated here.)

</deferred>

---

*Phase: 52-spatial-finish*
*Context gathered: 2026-07-04*
