# Phase 52: Spatial Finish - Research

**Researched:** 2026-07-04
**Domain:** PostGIS SQL builder extension (pycopg `db.spatial.*` accessor, additive-only, frozen SemVer 1.0)
**Confidence:** HIGH

## Summary

Phase 52 adds 6 additive features (SPAT-F01..F06, 9 new/changed public methods) to `pycopg/spatial.py`. The phase is spec-complete in `52-CONTEXT.md` — this research's job was to verify D-01..D-12's cited line anchors against the live file and catch implementation landmines before planning. All cited anchors verified accurate (`pycopg/spatial.py` is 7726 lines; anchors drift by 0 lines from CONTEXT.md's estimates). No new dependency is required — every new helper is a thin SQL-builder wrapping an already-available PostGIS function; `psycopg`/`geopandas` already handle execution.

**One material landmine was found and must be resolved before planning locks task shape:** CONTEXT.md D-06 states the new DE-9IM predicates (`overlaps`/`touches`/`crosses`) "mirror `build_intersects_sql`/`intersects` mechanically" but then adds "(no `into=`)" — this parenthetical contradicts the live code. `contains`, `intersects`, `dwithin`, and `within` **all** support `into="rows"|"gdf"` today (three-way `@overload` triplet, present in `_GDF_CALLS` test fixture at `tests/test_spatial.py:1692-1708`), because their SELECT already carries the full row including the geometry column. If the new predicates mirror `intersects` "mechanically" as instructed, they inherit `into=`/`@overload` too — the "(no into=)" clause appears to be a drafting slip in CONTEXT.md, not an intentional API-shape decision. See Common Pitfalls #1 for the full analysis and a recommended resolution the planner should adopt (or explicitly override with a documented reason).

Everything else in D-01..D-12 is confirmed accurate against the live source: the byte-identical D-03 invariant for `gridSize=None` is *already* covered word-for-word by three existing tests (`test_union_emits_st_union` / `test_difference_emits_st_difference` / `test_intersection_emits_st_intersection`), the `_SCALAR_HELPERS` frozenset needs 3 new entries (`length`, `is_valid`, `is_valid_reason`), and the local test server (PostGIS 3.6.4 / GEOS 3.13.1) comfortably exceeds the gridSize ≥3.1/≥3.9 requirement, so a live positive-path test for gridSize is possible here (not just a passthrough/mock test).

**Primary recommendation:** Follow the shipped `build_*_sql` + accessor + `@overload` + async-mirror template exactly as CONTEXT.md's "Reusable Assets" section describes, EXCEPT resolve the into=/gdf question for SPAT-F06 predicates before writing tasks (recommend: include `into=`/`@overload`/gdf support on all 4, matching `contains`/`intersects`/`dwithin`, and update the surface/routing test fixtures accordingly).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Fixed-precision overlay (`gridSize=`) | API / Backend (pycopg SQL builder) | Database (PostGIS/GEOS executes the snap) | pycopg's job is parameter threading + validation-free passthrough; PostGIS/GEOS does the actual grid snapping |
| Length/envelope/point_on_surface measurement | API / Backend (pycopg SQL builder) | Database (PostGIS computes ST_* result) | Same pure-builder pattern as existing `area`/`perimeter`/`centroid` |
| Validity check (`is_valid`/`is_valid_reason`) | API / Backend (pycopg SQL builder) | Database (PostGIS validity engine) | Scalar boolean/text result, no client-side geometry parsing |
| DE-9IM predicates (overlaps/touches/crosses/disjoint) | API / Backend (pycopg SQL builder) | Database (PostGIS spatial predicate + optional GiST index) | pycopg emits the WHERE-clause condition; PostGIS/GiST decides index usage (disjoint cannot use the index — see Pitfall 4) |
| GeoDataFrame conversion (`into="gdf"`) | API / Backend (`_run`/`_to_named_binds`) | Client (geopandas consumes result) | Existing `_run` dispatcher already owns this; no new tier work needed |

No browser, frontend-server, or CDN tier involvement — this is a pure backend library change.

## Standard Stack

No new libraries. This phase is 100% additive SQL-builder code reusing the existing stack:

| Library | Version (installed) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg | (already a pycopg dependency, unchanged) | Executes `%s`-parameterized SQL | Already used by every existing spatial helper |
| geopandas (`pycopg[geo]` extra) | (already optional dep, unchanged) | `into="gdf"` conversion | Already used by every existing geometry-returning helper via `Database.to_geodataframe` |
| PostGIS | 3.6.4 confirmed live on local test server `pycopg_test3` [VERIFIED: `SELECT postgis_full_version()`] | Provides ST_Length/ST_Envelope/ST_PointOnSurface/ST_IsValid/ST_IsValidReason/ST_Overlaps/ST_Touches/ST_Crosses/ST_Disjoint and the 3-arg gridSize overlay forms | Native SQL functions — no Python-side geometry library needed |
| GEOS (bundled in PostGIS) | 3.13.1 confirmed live [VERIFIED] | Required ≥3.9 for gridSize (D-04) | Far exceeds requirement; gridSize is live-testable on this server |

### Alternatives Considered

None — CONTEXT.md's decisions (D-01..D-12) already lock the exact PostGIS functions and no alternative library or approach was in scope to evaluate. This is purely an extension of the existing hand-rolled-SQL-builder pattern (which is itself the project's established, intentional "don't hand-roll a query builder library" architecture — see `Don't Hand-Roll` below for why that's still correct here).

**Installation:** None required. `pyproject.toml` dependencies (checked, line 37+) are unchanged by this phase; `uv.lock` must show zero diff after implementation (`git diff --stat uv.lock` should be empty — verified clean at research time).

**Version verification:**
```
$ psql -tAc "SELECT postgis_full_version();"
POSTGIS="3.6.4 94d984b" [EXTENSION] PGSQL="180" GEOS="3.13.1-CAPI-1.19.2" ...
```
[VERIFIED: live `pycopg_test3` database, 2026-07-04]

## Package Legitimacy Audit

**Not applicable — this phase installs zero external packages.** All 6 features (SPAT-F01..F06) are implemented as pure SQL-string builders calling already-available native PostGIS functions (`ST_Union`/`ST_Difference`/`ST_Intersection` 3-arg forms, `ST_Length`, `ST_Envelope`, `ST_PointOnSurface`, `ST_IsValid`, `ST_IsValidReason`, `ST_Overlaps`, `ST_Touches`, `ST_Crosses`, `ST_Disjoint`). No new Python dependency, no new PostgreSQL extension. `git status`/`git diff --stat` on `pyproject.toml` and `uv.lock` were confirmed clean at research time (no prior-phase drift carried in) — the planner/executor must keep it that way; any edit to either file for this phase is a signal something has gone wrong.

## Architecture Patterns

### System Architecture Diagram

```
Caller code
   │
   │  db.spatial.length(table, unit="m")
   ▼
SpatialAccessor.length()                 (pycopg/spatial.py, sync accessor, ~2159+)
   │  1. resolve where= -> filter= deprecation shim (SKIPPED for new methods — born clean)
   │  2. _check_into(into, "length")      -> validates into=, rejects gdf if scalar
   ▼
build_length_sql()                       (module-level pure builder, no self/no I/O)
   │  1. validate_identifiers(table, schema, geom)   <- LINE 1, security invariant
   │  2. _validate_unit(unit)                        <- whitelist guard
   │  3. assemble f-string SQL w/ %s placeholders for user values
   ▼
returns (sql: str, params: list[Any])
   │
   ▼
SpatialAccessor._run(sql, params, into, geom)
   │  into == "rows" -> self._db.execute(sql, params)         -> list[dict]
   │  into == "gdf"  -> _to_named_binds() -> self._db.to_geodataframe(...) -> GeoDataFrame
   ▼
Caller receives list[dict] or GeoDataFrame

AsyncSpatialAccessor mirrors this chain 1:1 (await self._db.execute(...) / await self._db.to_geodataframe(...)),
sharing the SAME module-level build_*_sql() functions (no duplication of SQL logic).
```

### Recommended Project Structure

No new files or directories. All work lands in the two existing locations:

```
pycopg/
├── spatial.py           # ALL 9 new/changed methods land here (both accessor classes)
docs/
├── spatial.md           # user-facing docs — add sections for the 6 new helpers
├── api-reference.md     # API surface reference — add the 6 new helpers
tests/
├── test_spatial.py      # ALL new tests land here (TestBuilders, TestAccessorRouting,
│                         #   TestGuard, TestIntegration sections already exist — extend them)
├── test_parity.py        # extend ACCESSOR_PAIRS (already covers SpatialAccessor — no
                          #   change needed there) + optionally add a named
                          #   `test_spatial_finish_surface` frozenset test (SPAT2-13 precedent)
```

### Pattern 1: gridSize threading through `_build_binary_geom_sql` (SPAT-F01)

**What:** `_build_binary_geom_sql` (line 1278) is the single funnel for `build_union_sql`/`build_difference_sql`/`build_intersection_sql`. Today it takes NO grid_size parameter and NEVER emits a `%s` placeholder — the op_func literal (e.g. `"ST_Union"`) is inserted directly: `f"{op_func}(t.{geom}, t.{other_geom}) AS {result_col}"`, returning `params=[]` unconditionally.

**When to use:** Add `grid_size: float | None = None` as a new keyword-only parameter on `_build_binary_geom_sql` AND on all three public `build_union_sql`/`build_difference_sql`/`build_intersection_sql` wrappers (which currently just forward fixed args to the shared helper — see line 1356-1367 for the exact forwarding shape to extend).

**Example (verified against live source, `pycopg/spatial.py:1278-1301`):**
```python
# CURRENT (verified, no gridSize):
def _build_binary_geom_sql(
    op_func: str,
    result_col: str,
    table: str,
    geom: str,
    schema: str,
    *,
    other_geom: str,
    columns: list[str] | None,
    filter: str | None,
    order_by: str | None,
    limit: int | None,
) -> tuple[str, list[Any]]:
    """Build SQL for a pairwise (binary, 2-column) geometry operation."""
    validate_identifiers(table, schema, geom, other_geom)
    if columns:
        validate_identifiers(*columns)
    sql = (
        f"SELECT {_cols_str(columns)}, "
        f"{op_func}(t.{geom}, t.{other_geom}) AS {result_col} "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []

# RECOMMENDED SHAPE (D-01/D-02/D-03 compliant):
def _build_binary_geom_sql(
    op_func: str,
    result_col: str,
    table: str,
    geom: str,
    schema: str,
    *,
    other_geom: str,
    grid_size: float | None = None,
    columns: list[str] | None,
    filter: str | None,
    order_by: str | None,
    limit: int | None,
) -> tuple[str, list[Any]]:
    validate_identifiers(table, schema, geom, other_geom)
    if columns:
        validate_identifiers(*columns)
    if grid_size is None:
        expr = f"{op_func}(t.{geom}, t.{other_geom})"
        params: list[Any] = []
    else:
        expr = f"{op_func}(t.{geom}, t.{other_geom}, %s)"
        params = [grid_size]
    sql = (
        f"SELECT {_cols_str(columns)}, {expr} AS {result_col} "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, params
```
This preserves D-03 byte-for-byte: when `grid_size is None`, the emitted SQL string and empty `params=[]` are IDENTICAL to today's output — the three existing exact-string tests (`test_union_emits_st_union` line 554, `test_difference_emits_st_difference` line 588, `test_intersection_emits_st_intersection` line 622 in `tests/test_spatial.py`) already assert this string byte-for-byte and will continue to pass unmodified as the D-03 regression guard. **No new "byte-identical" test file/fixture is needed — these three existing tests already are it.**

### Pattern 2: Scalar single-column measurement helper (SPAT-F02 `length`)

**What:** Mirror `build_area_sql`/`build_perimeter_sql` (lines 666/728) exactly — same signature shape (`table, geom, schema, *, unit="m", columns, filter, order_by, limit`), same `_validate_unit` + `::geography` cast idiom, same `has_where=False` tail.

**Example (verified against live `build_perimeter_sql`, lines 728-788 — `length` is a mechanical copy with `ST_Perimeter`→`ST_Length` and alias `perimeter`→`length`):**
```python
def build_length_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    unit: str = "m",
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list[Any]]:
    validate_identifiers(table, schema, geom)
    if columns:
        validate_identifiers(*columns)
    _validate_unit(unit)
    cast = "::geography" if unit == "m" else ""
    sql = (
        f"SELECT {_cols_str(columns)}, ST_Length(t.{geom}{cast}) AS length "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []
```
Accessor: mirror `perimeter` accessor (line 3148) exactly — no `@overload` (scalar, rows-only, `cast("list[dict[str, Any]]", ...)` pattern), **and add `"length"` to `_SCALAR_HELPERS`** (line 2091) so `_check_into` correctly rejects `into="gdf"`.

### Pattern 3: Geometry-returning helper, no required extra kwarg (SPAT-F03 `envelope`)

**What:** Mirror `build_convex_hull_sql` (line 1596) — no extra parameters beyond the base shape, single geometry output column, valid for `into="gdf"`.
```python
def build_envelope_sql(
    table: str, geom: str = "geometry", schema: str = "public", *,
    columns: list[str] | None = None, filter: str | None = None,
    order_by: str | None = None, limit: int | None = None,
) -> tuple[str, list[Any]]:
    validate_identifiers(table, schema, geom)
    if columns:
        validate_identifiers(*columns)
    sql = (
        f"SELECT {_cols_str(columns)}, ST_Envelope(t.{geom}) AS envelope "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []
```
Accessor: mirror `convex_hull` accessor (line 4272) — full `@overload` triplet (`Literal["rows"]`/`Literal["gdf"]`/`str`), no `where=` shim (born-clean, D-10 of the original freeze). Same shape applies to `point_on_surface` (SPAT-F04, `ST_PointOnSurface`, alias `point_on_surface` per D-09) — it is a geometry column (D-05), NOT the scalar x/y shape `centroid` uses.

### Pattern 4: Scalar validity helpers (SPAT-F05 `is_valid`/`is_valid_reason`)

**What:** Mirror `build_make_valid_sql`'s validated-table/no-extra-guard-needed shape, but scalar output like `area`/`centroid`. `is_valid` returns boolean, `is_valid_reason` returns text — both rows-only.
```python
def build_is_valid_sql(
    table: str, geom: str = "geometry", schema: str = "public", *,
    columns: list[str] | None = None, filter: str | None = None,
    order_by: str | None = None, limit: int | None = None,
) -> tuple[str, list[Any]]:
    validate_identifiers(table, schema, geom)
    if columns:
        validate_identifiers(*columns)
    sql = (
        f"SELECT {_cols_str(columns)}, ST_IsValid(t.{geom}) AS is_valid "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []
# build_is_valid_reason_sql is identical with ST_IsValidReason / alias is_valid_reason
```
Add BOTH `"is_valid"` and `"is_valid_reason"` to `_SCALAR_HELPERS` (line 2091).

### Pattern 5: DE-9IM predicates (SPAT-F06 `overlaps`/`touches`/`crosses`/`disjoint`)

**What:** Mirror `build_intersects_sql` (line 287) mechanically — same 4 input forms via `_resolve_geometry`, same `_REF_SENTINEL` EXISTS handling, same tail. Only the ST_* function name changes.
```python
def build_overlaps_sql(
    table: str, geom: str = "geometry", schema: str = "public", *,
    point: tuple[float, float] | None = None, wkt: str | None = None,
    geojson: dict[str, Any] | None = None, ref: tuple[str, str] | None = None,
    srid: int = 4326, columns: list[str] | None = None,
    filter: str | None = None, order_by: str | None = None, limit: int | None = None,
) -> tuple[str, list[Any]]:
    validate_identifiers(table, schema, geom)
    if columns:
        validate_identifiers(*columns)
    fragment, frag_params = _resolve_geometry(point=point, wkt=wkt, geojson=geojson, ref=ref, srid=srid)
    params: list[Any] = []
    if fragment == _REF_SENTINEL:
        ref_table, ref_col = frag_params
        cond = f"EXISTS (SELECT 1 FROM {ref_table} AS _ref WHERE ST_Overlaps(_ref.{ref_col}, t.{geom}))"
    else:
        cond = f"ST_Overlaps(t.{geom}, {fragment})"
        params.extend(frag_params)
    sql = f"SELECT {_cols_str(columns)} FROM {schema}.{table} AS t WHERE {cond}"
    sql = _append_tail(sql, filter, order_by, limit, has_where=True)
    return sql, params
# build_touches_sql / build_crosses_sql / build_disjoint_sql: identical, swap ST_Overlaps
# for ST_Touches / ST_Crosses / ST_Disjoint respectively.
```
**Landmine (see Pitfall 1):** the CONTEXT.md instruction to omit `into=` contradicts "mirror intersects mechanically" — `intersects` HAS `into=`/`@overload`/gdf support live today. Resolve before task-writing; the code example above deliberately omits `into=` per the CONTEXT.md text, but the planner should treat this as an open decision, not settled fact (see Pitfall 1 for the full argument to include it).

### Anti-Patterns to Avoid

- **Adding `where=` deprecated-alias shims to new methods:** every post-1.0 helper (`union`/`difference`/`intersection`/`convex_hull`/`make_valid`) is explicitly "born clean" — no `where=` parameter, no `DeprecationWarning` shim. Only pre-1.0 helpers (`contains`/`intersects`/`area`/`perimeter`/`centroid`/`dwithin`) carry the shim. All 9 new methods in this phase MUST be born-clean (no `where=`).
- **Client-side range validation on `gridSize`:** D-02 explicitly forbids this — every float is meaningful to PostGIS (0 = integer snap, negative = disable). Do not add a `ValueError` guard.
- **Forgetting to add new scalar helpers to `_SCALAR_HELPERS`:** if `length`/`is_valid`/`is_valid_reason` are omitted from the frozenset at line 2091, `into="gdf"` will not raise the expected `ValueError` — it will instead fail deep inside `_to_named_binds`/`to_geodataframe` with a confusing geopandas error about a missing geometry column, defeating the "fail fast with a clear message" contract every other scalar helper honors.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Fixed-precision geometry snapping | A Python-side coordinate-rounding pass on returned geometries | PostGIS native `gridSize` 3rd arg (GEOS ≥3.9) | GEOS's snap-rounding overlay is numerically robust (handles near-coincident vertices correctly); a Python post-process on already-computed float geometries cannot achieve the same robustness guarantee and would silently produce different topology than the SQL-side approach |
| Geometry validity checking/repair | Regex/heuristic WKT inspection, or a client-side geometry library validity check | `ST_IsValid`/`ST_IsValidReason` (PostGIS/GEOS OGC-compliant validity engine) | GEOS's validity model (OGC Simple Features) covers self-intersection, ring orientation, and dimensional collapse cases that are extremely error-prone to reimplement client-side |
| DE-9IM spatial predicates | Custom bounding-box or centroid-distance heuristics for overlaps/touches/crosses/disjoint | Native `ST_Overlaps`/`ST_Touches`/`ST_Crosses`/`ST_Disjoint` | DE-9IM matrix semantics (boundary/interior/exterior intersection patterns) are precisely defined by the OGC spec and implemented correctly only inside GEOS |

**Key insight:** this project's entire spatial subsystem is already "don't hand-roll a query builder — hand-write the minimal SQL builder function" (see module docstring, line 1-24) — this phase simply extends that established, correct pattern to 6 more PostGIS functions. There is no new domain of hand-rolling risk introduced.

## Common Pitfalls

### Pitfall 1: CONTEXT.md D-06 "(no into=)" contradicts the live `intersects` shape — RESOLVE BEFORE PLANNING

**What goes wrong:** If the planner takes D-06's parenthetical literally and builds `overlaps`/`touches`/`crosses`/`disjoint` WITHOUT `into=`/`@overload`, the new predicates will have a narrower API than their sibling `contains`/`intersects`/`dwithin` (which all support `into="gdf"` today), breaking the "complete the predicate family" framing of SPAT-F06 itself (its own requirement text says "completing the `contains`/`intersects`/`within`/`dwithin` predicate family" — a family where 3 of 4 existing members support gdf).

**Why it happens:** CONTEXT.md's D-06 text says two things that don't agree: "mirror `build_intersects_sql`/`intersects` **mechanically**" (implies full parity, including `into=`) immediately followed by "(no `into=`)" (implies a narrower shape). Verified against live source: `intersects` accessor (line 2520-2666) has a full 3-overload `@overload` triplet + `into: str = "rows"` + `_check_into(into, "intersects")` + `self._run(sql, params, into, geom)` — identical structure to `union`/`buffer`/`transform`. `tests/test_spatial.py` confirms this at the fixture level: `_GDF_CALLS` (line 1692) includes `("contains", ...)`, `("intersects", ...)`, `("dwithin", ...)` all mapped to `"geometry"` as their gdf geometry column.

**How to avoid:** The planner/discuss-phase should explicitly decide (and document the decision, since it deviates from what CONTEXT.md literally says) whether the 4 new predicates get `into=`/`@overload`/gdf support. Recommendation based on the evidence: **include it** — matching `contains`/`intersects`/`dwithin` exactly is the more defensible reading of "mirror mechanically," is what the SPAT-F06 requirement text implies ("completing the...family"), and avoids a permanent asymmetry in the accessor surface (`contains`/`intersects`/`dwithin` support gdf, `overlaps`/`touches`/`crosses`/`disjoint` silently wouldn't, with no principled reason for the split). If the planner instead follows CONTEXT.md literally ("no into="), that is an available, valid choice — but it should be a documented decision line in the phase's plan/decisions doc, not something inherited silently from a CONTEXT.md contradiction.

**Warning signs:** If planning proceeds without addressing this, expect a `code-review` finding at execution time (the project's `gsd-code-fixer`/reviewer step has repeatedly caught exactly this class of "new code should mirror an existing sibling but doesn't" gap in prior phases — see STATE.md Phase 41 CR-01 and Phase 44-03 SPAT2-13 lessons).

### Pitfall 2: `_SCALAR_HELPERS` frozenset must gain 3 new entries, or `into="gdf"` fails with a confusing error instead of a clear one

**What goes wrong:** `length`, `is_valid`, `is_valid_reason` are all scalar-result helpers (no geometry column). If they are NOT added to `_SCALAR_HELPERS` (line 2091-2093), calling `db.spatial.length("t", into="gdf")` will not raise the expected `ValueError: into='gdf' is invalid for length(): it returns a scalar, not a geometry` — instead `_run` will attempt `_to_named_binds` + `to_geodataframe(geometry_column="geometry")` against a result set that has no geometry column matching that name, producing a much less clear geopandas-level error deep in the call stack.

**Why it happens:** `_check_into`'s scalar rejection is opt-in via an explicit frozenset (not inferred from the builder's return columns) — a new scalar helper that forgets to register itself silently loses this fail-fast guard.

**How to avoid:** Explicitly add all 3 new scalar helper names to `_SCALAR_HELPERS` in the same commit/task that adds their builders. A dedicated test (mirroring `test_sync_scalar_helper_rejects_gdf`, `tests/test_spatial.py:862`) should assert this for each of the 3.

**Warning signs:** A missing/incomplete `_SCALAR_HELPERS` update produces GREEN builder-level tests (SQL string assertions pass fine) but a LATE failure only surfaced by a live-DB `into="gdf"` integration test — if that integration test is skipped or under-specified, this gap ships silently.

### Pitfall 3: `envelope`/`point_on_surface` result columns collide with existing `columns=` selections named the same

**What goes wrong:** Not a bug in pycopg, but a footgun for callers: if a table already has a column literally named `envelope` or `point_on_surface` and the caller passes `columns=["envelope"]` alongside the helper call, the SELECT list will contain a duplicate `envelope` alias (once from `columns=`, once from the computed `AS envelope`), causing a PostgreSQL "column reference ambiguous" or duplicate-column-name error depending on context. This is the SAME pre-existing risk `union_geom`/`difference`/`intersection`/`buffer`/`made_valid` already carry — not new, but worth a one-line docstring note (mirroring existing helpers' silence on this) rather than a defensive check (none of the existing helpers guard against this either, so adding one here would be an inconsistent, un-requested scope increase).

**How to avoid:** No code change needed — just don't introduce a defensive check that the existing 10 geometry-returning helpers don't have (consistency > defensiveness here, per the project's established pattern).

### Pitfall 4: `ST_Disjoint` never uses a spatial index — document this explicitly (D-08 already anticipates this)

**What goes wrong:** A caller filtering a large indexed table with `db.spatial.disjoint(...)` will get a full sequential scan even if a GiST index exists on the geometry column, because `ST_Disjoint` is defined as "not intersecting" and PostGIS's spatial index only accelerates bounding-box-overlap-style predicates.

**Why it happens:** [CITED: postgis.net/docs/ST_Disjoint.html] "This function call does not use indexes... A negated ST_Intersects predicate can be used as a more performant alternative that uses indexes: `ST_Disjoint(A,B) = NOT ST_Intersects(A,B)`." — official PostGIS documentation confirms this exactly as D-08 anticipated.

**How to avoid:** D-08 already mandates this be documented in the `disjoint` docstring/`docs/spatial.md` — this research confirms the claim is accurate and should be cited verbatim (not paraphrased) since it's an authoritative, precise statement.

### Pitfall 5: `disjoint(ref=...)` EXISTS semantics footgun is real and matches production PostGIS EXISTS-subquery behavior

**What goes wrong:** `disjoint(ref=("zones", "geom"))` builds `EXISTS (SELECT 1 FROM zones AS _ref WHERE ST_Disjoint(_ref.geom, t.geometry))` — this is true if **ANY** row in `zones` is disjoint from the current row's geometry, which for any reasonably sparse/scattered `zones` table is almost always true (a geometry only needs to be disjoint from ONE other row to satisfy EXISTS). This is very likely NOT what a caller intends when they think "give me rows disjoint from the zones table" (which would require disjoint from ALL rows — a `NOT EXISTS(...intersects...)` shape, not `EXISTS(...disjoint...)`).

**Why it happens:** This is the SAME EXISTS-quantifier pattern already used by `contains`/`intersects`/`dwithin`'s `ref=` form, applied mechanically to `disjoint`. For `contains`/`intersects` the "EXISTS a row satisfying the predicate" semantic is usually the intended meaning (any zone that intersects). For `disjoint`, the DE-9IM-inverse relationship makes the EXISTS-quantified version nearly a no-op/always-true footgun in practice.

**How to avoid:** D-07 already mandates a docstring warning covering exactly this. Confirmed as accurate and necessary — this is a genuine, non-hypothetical footgun, not overcaution. No code change is needed beyond the documented warning (the CONTEXT.md decision to keep it mechanically uniform rather than special-case `disjoint(ref=...)` into `NOT EXISTS(...)` is reasonable — special-casing would silently change what "the pairwise predicate family" means for one member only).

## Code Examples

### D-03 byte-identical regression coverage (already exists — verify it stays green, don't duplicate it)

```python
# tests/test_spatial.py:554 — EXISTING test, unmodified by this phase, is the
# D-03 regression guard for build_union_sql's None-path:
def test_union_emits_st_union(self):
    """union emits ST_Union with union_geom alias and empty params."""
    sql, params = build_union_sql("parcels", other_geom="geom2")
    assert sql == (
        "SELECT *, ST_Union(t.geometry, t.geom2) AS union_geom "
        "FROM public.parcels AS t"
    )
    assert params == []
# Identical existing tests for difference (line 588) and intersection (line 622).
# After adding gridSize=, these three tests MUST continue to pass byte-for-byte
# with ZERO changes to their assertions — that IS the D-03 acceptance criterion.
```

### New gridSize-set test (needed, does not exist yet)

```python
def test_union_grid_size_appends_third_arg(self):
    """union(gridSize=...) adds a 3rd ST_Union arg bound as %s (SPAT-F01/D-01)."""
    sql, params = build_union_sql("parcels", other_geom="geom2", grid_size=0.001)
    assert sql == (
        "SELECT *, ST_Union(t.geometry, t.geom2, %s) AS union_geom "
        "FROM public.parcels AS t"
    )
    assert params == [0.001]
```

### `_HELPER_CALLS`/`_GDF_CALLS` fixture extension needed for routing tests

```python
# tests/test_spatial.py:1667-1708 — the planner MUST add entries here for the
# 9 new methods, e.g.:
_HELPER_CALLS = [
    # ...existing entries...
    ("length", {}),
    ("envelope", {}),
    ("point_on_surface", {}),
    ("is_valid", {}),
    ("is_valid_reason", {}),
    ("overlaps", {"point": (1, 2)}),
    ("touches", {"point": (1, 2)}),
    ("crosses", {"point": (1, 2)}),
    ("disjoint", {"point": (1, 2)}),
]
# _GDF_CALLS gets envelope/point_on_surface (geometry columns) and — PENDING
# Pitfall 1's resolution — possibly overlaps/touches/crosses/disjoint too.
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| ST_Union/ST_Difference/ST_Intersection 2-arg only | 3-arg form with `gridSize` for fixed-precision snap-rounding overlay | PostGIS 3.1.0 / GEOS ≥3.9.0 [CITED: postgis.net/docs/ST_Union.html] | Enables robust overlay on near-coincident vertices; opt-in via 3rd positional arg, fully backward compatible with the 2-arg form |

**Deprecated/outdated:** None relevant — all 9 target functions (`ST_Length`, `ST_Envelope`, `ST_PointOnSurface`, `ST_IsValid`, `ST_IsValidReason`, `ST_Overlaps`, `ST_Touches`, `ST_Crosses`, `ST_Disjoint`) are long-stable, non-deprecated PostGIS core functions available since early PostGIS 1.x/2.x releases — no version gating needed for any of them except `gridSize` (D-04, already covered).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `overlaps`/`touches`/`crosses`/`disjoint` should include `into=`/`@overload`/gdf support (research's recommendation, not CONTEXT.md's literal text) | Common Pitfalls #1 / Pattern 5 | If the planner adopts this recommendation without an explicit user/planner decision record, it silently overrides a CONTEXT.md decision (D-06) — must be logged as a resolved discrepancy, not silently changed |

No other claims in this research are `[ASSUMED]` — the PostGIS function behaviors (gridSize version gate, ST_Disjoint index behavior, ST_Length polygon=0 behavior) were confirmed via official PostGIS documentation (`postgis.net`), and all `pycopg/spatial.py` line-anchor claims were confirmed by direct `Read` against the live file at research time.

## Open Questions (RESOLVED)

1. **Should the 4 new DE-9IM predicates support `into="gdf"`? — RESOLVED 2026-07-04 (plan-phase, user decision): YES, full into=rows/gdf mirror. See CONTEXT.md amended D-06/D-07; implemented by plans 52-04/52-05.**
   - What we know: `contains`/`intersects`/`dwithin` (siblings in the "predicate family" per SPAT-F06's own wording) all support it today; CONTEXT.md D-06 said "no into=" but also "mirror mechanically."
   - Resolution: the "(no into=)" text was a factual error — the live siblings already ship `into=`, so "mirror mechanically" REQUIRES the overloads. User confirmed the full-mirror shape; CONTEXT.md D-06/D-07 amended accordingly.

2. **Does `disjoint` need a `_SCALAR_HELPERS`-style special exclusion given its non-indexable nature?**
   - What we know: `disjoint` is a row-filter predicate (like `intersects`), not a scalar-column helper — it does NOT belong in `_SCALAR_HELPERS` regardless of the into= decision above (that frozenset governs geometry-vs-scalar shape, not index performance).
   - What's unclear: nothing — this is just a clarification to prevent a planner from conflating "can't use an index" (a performance note, D-08) with "is a scalar helper" (a return-shape category, unrelated).
   - Recommendation: no action needed beyond the D-08 docstring note; do not add `disjoint` to `_SCALAR_HELPERS`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | All DB-backed tests | ✓ | 18.4 (Debian) [VERIFIED] | — |
| PostGIS | All 6 SPAT-F01..F06 features | ✓ | 3.6.4 [VERIFIED] | — |
| GEOS | `gridSize` (needs ≥3.9) | ✓ | 3.13.1-CAPI-1.19.2 [VERIFIED] — far exceeds requirement | — |
| Test database `pycopg_test3` | All live-DB spatial integration tests | ✓ | postgis 3.6.4, timescaledb 2.28.2, pg_trgm 1.6 extensions installed [VERIFIED] | `PGDATABASE=pycopg_test3` required — default `pycopg_test`/`pycopg_test2` are known-broken (TimescaleDB `.so` drift, per project memory) |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** None — environment is fully sufficient for this phase, including a LIVE positive-path test for `gridSize` (server exceeds the version gate, unlike a typical "passthrough, can't verify" scenario).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (+ pytest-asyncio for async accessor tests, already configured) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (line 95-97): `testpaths=["tests"]`, `addopts="-v --cov=pycopg --cov-report=term-missing --cov-report=html --cov-fail-under=95"` |
| Quick run command | `PGDATABASE=pycopg_test3 uv run pytest tests/test_spatial.py -x -q` |
| Full suite command | `PGDATABASE=pycopg_test3 uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SPAT-F01 | `gridSize=None` keeps overlay SQL byte-identical | unit (pure SQL string) | `pytest tests/test_spatial.py -k "test_union_emits_st_union or test_difference_emits_st_difference or test_intersection_emits_st_intersection" -x` | ✅ exists (regression guard, verify unchanged) |
| SPAT-F01 | `gridSize=<float>` emits 3rd `%s` arg | unit (pure SQL string) | `pytest tests/test_spatial.py -k "grid_size" -x` | ❌ Wave 0 — new test |
| SPAT-F01 | `gridSize` live behavior on server ≥3.1/≥3.9 | DB integration | `PGDATABASE=pycopg_test3 pytest tests/test_spatial.py -k "grid_size and Integration" -x` | ❌ Wave 0 — new test (server supports it, see Environment Availability) |
| SPAT-F02 | `length` returns ST_Length scalar, unit=m/srid | unit + DB integration | `pytest tests/test_spatial.py -k "length" -x` | ❌ Wave 0 — new test |
| SPAT-F02 | `length` returns 0 for non-linear (polygon) geometry | DB integration (documents the pitfall) | `PGDATABASE=pycopg_test3 pytest tests/test_spatial.py -k "length_polygon" -x` | ❌ Wave 0 — new test |
| SPAT-F03 | `envelope` returns geometry, valid for into=gdf | unit + gdf routing | `pytest tests/test_spatial.py -k "envelope" -x` | ❌ Wave 0 — new test |
| SPAT-F04 | `point_on_surface` returns geometry (NOT scalar x/y) | unit + gdf routing | `pytest tests/test_spatial.py -k "point_on_surface" -x` | ❌ Wave 0 — new test |
| SPAT-F05 | `is_valid`/`is_valid_reason` scalar, rows-only, `_SCALAR_HELPERS` gdf-rejection | unit + guard test | `pytest tests/test_spatial.py -k "is_valid" -x` | ❌ Wave 0 — new test |
| SPAT-F06 | `overlaps`/`touches`/`crosses`/`disjoint` — 4 input forms + EXISTS ref= | unit (pure SQL string, mirrors `TestBuilders` contains/intersects sections) | `pytest tests/test_spatial.py -k "overlaps or touches or crosses or disjoint" -x` | ❌ Wave 0 — new test |
| SPAT-F06 | injection tests per new predicate builder (standing bar) | unit | `pytest tests/test_spatial.py -k "invalid_table or invalid_column" -x` (extend existing parametrized pattern) | ❌ Wave 0 — new test |
| Standing bar | sync/async parity for all 9 new methods | parity (generic, auto-extends) | `pytest tests/test_parity.py -x` | ✅ exists (`test_accessor_parity`/`test_accessor_parameter_kind_parity` are name-generic — no per-phase edit needed) |
| Standing bar | mypy --strict clean incl. new `@overload` stubs | static | `uv run mypy pycopg` | ✅ exists (blocking gate) |
| Standing bar | coverage ≥95% | coverage | `uv run pytest` (fails under 95 automatically per addopts) | ✅ exists |
| Standing bar | interrogate 100% (numpydoc docstrings) | static | `uv run interrogate pycopg` (or configured Makefile target) | ✅ exists |
| Standing bar | Sphinx `-W` clean | doc build | `uv run sphinx-build -W docs docs/_build` (check exact Makefile target) | ✅ exists |

### Sampling Rate

- **Per task commit:** `PGDATABASE=pycopg_test3 uv run pytest tests/test_spatial.py -x -q`
- **Per wave merge:** `PGDATABASE=pycopg_test3 uv run pytest` (full suite, coverage gate enforced)
- **Phase gate:** Full suite green + mypy --strict + interrogate 100 + Sphinx -W before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] New builder-level SQL-string tests for all 9 new/changed methods in `tests/test_spatial.py::TestBuilders` (mirror the existing `contains`/`intersects`/`union`/`area`/`perimeter`/`make_valid` sections' exact-string-assertion style)
- [ ] Extend `_HELPER_CALLS` (line 1667) and (pending Pitfall 1 resolution) `_GDF_CALLS` (line 1692) fixtures with the 9 new method entries so `TestAccessorRouting`'s parametrized sync/async rows+gdf tests auto-cover them
- [ ] Extend `TestGuard`'s `@pytest.mark.parametrize("helper", ["area", "perimeter", "distance", "centroid"])` scalar-gdf-rejection test (line 862) to include `"length"`, `"is_valid"`, `"is_valid_reason"`
- [ ] New `TestIntegration` live-DB tests for: gridSize positive-path proof (server supports it), `length` polygon=0 behavior proof, `disjoint` EXISTS-quantifier footgun proof (documents the behavior with a live assertion, doesn't just describe it)
- [ ] Injection tests per new builder (standing bar requirement) — extend the existing `test_*_invalid_table`/`test_*_invalid_column` pattern (e.g. lines 576-584, 610-618, 644-651) for each of the 9 new/changed builders
- [ ] Optional: a named `test_spatial_finish_surface` frozenset test in `tests/test_parity.py` (SPAT2-13 precedent, line 291) asserting all 9 new method names exist on both accessor classes — not strictly required (the generic `test_accessor_parity` already catches drift) but matches established phase-closure convention for prior spatial phases

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A — library-internal SQL builder, no auth surface |
| V3 Session Management | no | N/A |
| V4 Access Control | no | N/A — pycopg does not implement row-level authorization; that's the consuming application's responsibility (unchanged by this phase) |
| V5 Input Validation | yes | `validate_identifiers` (line 1 of every builder, `pycopg/utils.py`) for all table/schema/column identifiers; `%s`-bound psycopg parameters for all user-supplied values (coordinates, WKT, GeoJSON, gridSize float, unit string after whitelist check) |
| V6 Cryptography | no | N/A — no cryptographic operation in this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via table/schema/geometry-column names | Tampering | `validate_identifiers()` called as the FIRST statement in every new `build_*_sql` function (matches all 20+ existing builders) — a dedicated injection test per new builder asserts `InvalidIdentifierError` on a malicious identifier (e.g. `"bad-name; DROP TABLE"`) |
| SQL injection via user-supplied geometry values (WKT/GeoJSON/coordinates/gridSize) | Tampering | All such values are `%s`-bound psycopg parameters, never f-string-interpolated — `_resolve_geometry` (line 69) already enforces this for the 4 D-05 input forms reused by SPAT-F06's predicates; gridSize is bound the same way (Pattern 1 above) |
| `filter=`/`order_by=` raw-SQL fragment injection | Tampering | Explicitly accepted, pre-existing, documented limitation (module docstring line 21-23: "values inside it are the caller's responsibility, T-14-04 accepted limitation") — unchanged by this phase, no new risk introduced since all 9 new helpers reuse the existing `_append_tail` tail-clause assembly unchanged |
| `method=`/`unit=`-style string parameters silently becoming injectable if a new one is added without a whitelist | Tampering | This phase adds no new open-ended string parameter of this shape — `length` reuses the existing whitelisted `_validate_unit` (`"m"`/`"srid"` only); no analogous "method=" parameter is introduced for any of the 6 features |

## Sources

### Primary (HIGH confidence)
- `pycopg/spatial.py` (local file, read directly, lines 1-170, 180-600, 640-800, 1060-1500, 1650-1780, 2090-2350, 2390-2440, 2520-2670, 3067-3150, 3229-3310, 3814-3934) — all CONTEXT.md line anchors verified accurate against this live source
- `tests/test_spatial.py` (local file, read directly, lines 167-260, 552-660, 1667-1800, 1802-1900, 849-980) — existing test conventions (`TestBuilders`, `_HELPER_CALLS`/`_GDF_CALLS`, `TestGuard`, `TestIntegration`) confirmed
- `tests/test_parity.py` (local file, read directly, lines 1-330) — parity/surface-test conventions confirmed
- `tests/conftest.py` (local file, read directly, lines 1-30) — `db_config` fixture confirms `PGDATABASE` env override
- `docs/spatial.md` (local file, read directly, lines 1-80) — user-facing doc conventions confirmed (into= table, geometry input forms table)
- Live database query `SELECT postgis_full_version()` on `pycopg_test3` — PostGIS 3.6.4 / GEOS 3.13.1 confirmed installed [VERIFIED]
- [ST_Union — postgis.net](https://postgis.net/docs/ST_Union.html) — gridSize signature, PostGIS 3.1.0/GEOS≥3.9.0 requirement confirmed
- [ST_Disjoint — postgis.net](https://postgis.net/docs/ST_Disjoint.html) — "does not use indexes" + `NOT ST_Intersects` alternative confirmed verbatim
- [ST_Length — postgis.net](https://postgis.net/docs/ST_Length.html) — "For areal geometries 0 is returned" confirmed

### Secondary (MEDIUM confidence)
- None used — all critical claims were verifiable directly against local source or official PostGIS docs.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies, all functions confirmed live on the test server
- Architecture: HIGH — every pattern verified against live `pycopg/spatial.py` source, not training-data recall
- Pitfalls: HIGH — the D-06 into=/gdf contradiction was found by direct code comparison (not speculation); ST_Disjoint index behavior and ST_Length polygon=0 behavior confirmed via official PostGIS docs

**Research date:** 2026-07-04
**Valid until:** 2026-08-03 (30 days — stable domain, PostGIS/pycopg internal APIs change slowly; re-verify line anchors if `pycopg/spatial.py` is touched by another phase first)

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SPAT-F01 | Keyword-only `gridSize=` on `union`/`difference`/`intersection`; default `None` byte-identical | Pattern 1 (exact code shape) + confirmation that D-03's byte-identical test already exists (3 tests, unmodified) + live server exceeds version gate (Environment Availability) |
| SPAT-F02 | `db.spatial.length` (ST_Length) | Pattern 2 (mechanical copy of `build_perimeter_sql`) + Pitfall re: 0-for-polygon behavior confirmed via official docs |
| SPAT-F03 | `db.spatial.envelope` (ST_Envelope) | Pattern 3 (mechanical copy of `build_convex_hull_sql`) |
| SPAT-F04 | `db.spatial.point_on_surface` (ST_PointOnSurface) | Pattern 3 (same shape as envelope — geometry column, NOT centroid's scalar x/y shape) |
| SPAT-F05 | `db.spatial.is_valid` + `is_valid_reason` | Pattern 4 (scalar helpers, `_SCALAR_HELPERS` frozenset update required — Pitfall 2) |
| SPAT-F06 | `overlaps`/`touches`/`crosses`/`disjoint` DE-9IM predicates | Pattern 5 (mechanical copy of `build_intersects_sql`) + Pitfall 1 (into=/gdf open question, MUST be resolved before task-writing) + Pitfall 4/5 (ST_Disjoint index + EXISTS-quantifier footguns, both confirmed accurate) |
</phase_requirements>

## RESEARCH COMPLETE
