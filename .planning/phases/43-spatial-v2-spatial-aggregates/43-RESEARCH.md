# Phase 43: Spatial v2 — Spatial Aggregates — Research

**Researched:** 2026-06-29
**Domain:** PostGIS aggregate functions (ST_Collect/ST_Union aggregate/ST_Extent) on top of the existing `pycopg/spatial.py` builder-pur pattern; first GROUP-BY aggregate shape in the spatial surface
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `group_by: str | list[str] | None = None`. A bare `str` is normalized to `[str]` internally; `list[str]` handles composite grouping; `None` = whole-table aggregate (exactly one row). Every group column is run through `validate_identifiers` (line 1 with `table`/`schema`/`geom`).
- **D-02:** Drop `columns=` entirely for the aggregate methods. SQL forbids selecting non-grouped, non-aggregate columns. SELECT is exactly the group_by columns (when present) + the aggregate expression `AS <result_col>`.
- **D-03:** Clause order: `SELECT <group_cols>, <agg> AS <col> FROM <schema>.<table> AS t [WHERE <filter>] [GROUP BY <group_cols>] [ORDER BY ...] [LIMIT ...]`. GROUP BY sits between WHERE (the `filter=` fragment) and ORDER BY. `_append_tail` (~149) only does WHERE→ORDER BY→LIMIT — needs an aggregate-aware variant (extend with optional `group_by` arg or a small new helper). Precedent: `timescale.py` `_build_time_bucket_sql` (~254).
- **D-04:** Single `build_extent_sql(..., into)` branches on `into`: `"rows"` → `ST_Extent(t.{geom})::text AS extent`; `"gdf"` → `ST_SetSRID(ST_Extent(t.{geom})::geometry, {int(srid)}) AS extent`. Extent is NOT added to `_SCALAR_HELPERS`.
- **D-05:** `extent` exposes `srid: int = 4326` (keyword-only), consulted only on `into="gdf"` cast via `int(srid)`. `srid` is ignored for `into="rows"`.
- **D-06:** Per-op result column names, frozen: `collect_geometries`→`collected`, `union_aggregate`→`dissolved`, `extent`→`extent`.
- **D-07:** NULL pass-through. PostGIS aggregates skip NULL geometry inputs; a group whose inputs are all-NULL yields one row with NULL aggregate value. No `HAVING ... IS NOT NULL`. Document in docstrings + intentional-NULL fixture test.
- **D-08:** Two test layers — (a) mock/SQL-shape unit tests + per-builder injection tests; (b) live integration on PostGIS 3.6.4 / GEOS 3.13.1 with grouped + whole-table + NULL fixture.
- **D-09:** Signature: `table` positional; everything else keyword-only: `geom="geometry"`, `schema="public"`, `group_by=None`, `srid=4326` (extent only), `into="rows"`, `filter`, `order_by`, `limit`. No `columns=`. `filter=` only — NO `where=` deprecated alias.
- **D-10:** Sync/async parity non-negotiable. Edit both classes in the same change. Enforced by `test_accessor_parity` AND `test_accessor_parameter_kind_parity`.

### Claude's Discretion

- **Builder factoring:** `collect_geometries` and `union_aggregate` share the same aggregate-builder shape — encouraged to share `_build_agg_geom_sql(agg_func, result_col, ...)` (mirrors Phase 42's `_build_binary_geom_sql`); `extent` is its own builder.
- **Aggregate-tail mechanism (D-03):** extend `_append_tail` with an optional `group_by` arg vs a new small helper — planner's call.
- Group-column `t.` alias qualification — consistency-preferred but free.
- Exact docstring wording for NULL/box2d/SRID notes.
- Plan/wave decomposition.

### Deferred Ideas (OUT OF SCOPE)

- Serialization + MVT (`as_geojson`/`as_text`/`as_mvt`) → Phase 44.
- `columns=` passthrough on aggregates (illegal under GROUP BY — D-02).
- 2-geometry `ST_Collect(g1, g2)` form.
- `gridSize` precision on union (SPAT-F01) — additive 1.x.
- Transaction control, named params, health, logging, mypy-strict — Phases 45–46.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SPAT2-07 | User can collect geometries into a collection via `db.spatial.collect_geometries(table, geom, group_by=None, ...)` (ST_Collect) | `_build_agg_geom_sql("ST_Collect", "collected", ...)` pattern; `group_by` normalized to list; result col `collected` |
| SPAT2-08 | User can dissolve geometries into a single boundary via `db.spatial.union_aggregate(table, geom, group_by=None, ...)` (ST_Union aggregate) | Same `_build_agg_geom_sql("ST_Union", "dissolved", ...)` pattern; result col `dissolved` distinct from Phase 42's pairwise `union_geom` |
| SPAT2-09 | User can compute the bounding extent of a geometry column via `db.spatial.extent(table, geom, group_by=None, ...)` (ST_Extent; box2d text for `into="rows"`, geometry cast for `into="gdf"`) | Dedicated `build_extent_sql(..., into)` branches on `into`; `srid=4326` kw-only; result col `extent` |
</phase_requirements>

---

## Summary

Phase 43 adds 3 aggregate methods (`collect_geometries`, `union_aggregate`, `extent`) to both `SpatialAccessor` and `AsyncSpatialAccessor` — 6 method bodies total, plus 2-3 module-level builders. All locked decisions (D-01..D-10) are drawn from the Phase 42/41 precedents. The only genuinely new piece of infrastructure is the aggregate-tail mechanism (D-03): a variant of `_append_tail` that inserts GROUP BY between WHERE and ORDER BY.

The PostGIS aggregate functions involved (`ST_Collect`, `ST_Union` aggregate form, `ST_Extent`) are all **Apache PostGIS** — no TimescaleDB or premium license gates. They exist since PostGIS 2.x, comfortably within the PostGIS 3.0 floor. The `ST_Extent` → `::geometry` cast and `ST_SetSRID(...)` wrapping for the GDF path is the only non-trivial SQL difference from `collect_geometries`/`union_aggregate`.

The key architectural fact: aggregate builders emit no `%s` parameters (all identifiers are validated and interpolated; `group_by` columns are identifier-validated and interpolated; SRID is via `int(srid)`). Empty `params = []` is the normal return.

**Primary recommendation:** Share a `_build_agg_geom_sql(agg_func, result_col, ...)` internal helper for `collect_geometries` and `union_aggregate` (mirrors `_build_binary_geom_sql` from Phase 42). `extent` gets its own `build_extent_sql` because the `into`-dependent SQL branch is intrinsic. For the GROUP-BY tail, extend `_append_tail` with an optional `group_by: list[str] | None = None` arg inserted after WHERE — minimal footprint, keeps the pattern centralized.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Aggregate SQL builder (ST_Collect/ST_Union/ST_Extent) | Module-level pure functions in `pycopg/spatial.py` | — | Stateless, no I/O; shared byte-identical between sync/async accessors |
| GROUP-BY tail insertion | `_append_tail` (extended) or new `_append_agg_tail` in `pycopg/spatial.py` | — | D-03: must sit after WHERE, before ORDER BY |
| Identifier validation + injection guard | `validate_identifiers` in `utils.py` (line 1 of every builder) | — | Applied to `table`/`schema`/`geom` + every `group_by` column |
| `group_by` normalization (str → [str]) | Module-level helper or inline in each builder | — | D-01: bare str normalized before validation loop |
| `into=` routing and PostGIS guard | `SpatialAccessor` / `AsyncSpatialAccessor` methods | — | Thin accessor delegates to builder then `_run`/`_arun` |
| `extent` `into=` branch | `build_extent_sql(... into=)` — builder sees `into` (D-04 exception) | — | box2d→geometry cast is intrinsic SQL shape difference |
| SRID injection-safe interpolation | `int(srid)` in `build_extent_sql` f-string | — | Established pattern from `build_point_geom`/`build_transform_sql` (~120/123/126) |
| Result delivery (rows/GDF) | `_run` (sync) / `_arun` (async) unchanged | `_to_named_binds` for GDF path | Existing machinery; no changes needed |
| Tests | `tests/test_spatial.py` | `tests/test_parity.py` | SQL-shape + injection + routing + parity + live integration |
| Docs | `docs/stability.md` (new stable-tier rows) | `docs/api-reference.md`, README spatial count | 3 new method rows per accessor |

---

## Standard Stack

No new packages — this phase is pure code. [VERIFIED: CONTEXT.md + REQUIREMENTS.md cross-cutting criterion "zero new runtime deps"]

### Core (unchanged)
| Library | Version Floor | Purpose | Status |
|---------|--------------|---------|--------|
| psycopg | ≥ 3.1.0 | DB driver | In project |
| geopandas | ≥ 0.14.0 | GeoDataFrame for `into="gdf"` | In project |
| PostGIS server | ≥ 3.0 (hard) / ≥ 3.2 (rec) | `ST_Collect`, `ST_Union(agg)`, `ST_Extent` | CI: 3.6.4 |

### PostGIS Functions (all Apache PostGIS, no TSL gate) [ASSUMED — from training + milestone research docs]

| Function | PostGIS Version | Notes |
|----------|----------------|-------|
| `ST_Collect(geometry set)` | 1.4+ (aggregate form) | No boundary dissolve; faster than ST_Union |
| `ST_Union(geometry set)` | 1.0+ (aggregate form) | Dissolves boundaries; more expensive |
| `ST_Extent(geometry set)` | 1.0+ | Returns `box2d`, NOT a geometry |
| `ST_SetSRID(geometry, srid)` | all | Cast `box2d::geometry` to a real polygon with SRID |

## Package Legitimacy Audit

> No new packages installed in this phase. Section is not applicable.

**Packages removed due to slopcheck:** none (no new packages)
**Packages flagged as suspicious:** none

---

## Architecture Patterns

### System Architecture Diagram

```
User call: db.spatial.collect_geometries("zones", group_by="region", into="rows")
              |
              v
  SpatialAccessor.collect_geometries(table, *, geom, schema, group_by, into, filter, order_by, limit)
      1. Normalize group_by: str → [str]   (D-01)
      2. _check_into(into, "collect_geometries")  (NOT in _SCALAR_HELPERS)
      3. build_collect_geometries_sql(table, ...) → (sql, [])
              |
              +→ validate_identifiers(table, schema, geom)  ← LINE 1
              +→ validate_identifiers(*group_by_list)       ← LINE 2 (if group_by)
              +→ assemble SELECT:
                   group_by=None: "SELECT ST_Collect(t.geometry) AS collected FROM ..."
                   group_by=["r"]: "SELECT t.r, ST_Collect(t.geometry) AS collected FROM ... GROUP BY t.r"
              +→ _append_tail(sql, filter, order_by, limit, has_where=False, group_by=group_cols_str)
      4. return _run(sql, [], into, geometry_column="collected")
              |
       into="rows" → db.execute(sql, []) → list[dict]
       into="gdf"  → _to_named_binds(sql, []) → db.to_geodataframe(sql, {}, geometry_column="collected")


User call: db.spatial.extent("zones", group_by="region", into="gdf", srid=4326)
              |
              v
  SpatialAccessor.extent(table, *, geom, schema, group_by, srid, into, filter, order_by, limit)
      1. Normalize group_by
      2. _check_into(into, "extent")  (NOT in _SCALAR_HELPERS; "gdf" is valid via cast)
      3. build_extent_sql(table, ..., into=into) → (sql, [])
              |
              into="rows": "SELECT [t.r,] ST_Extent(t.geometry)::text AS extent FROM ..."
              into="gdf":  "SELECT [t.r,] ST_SetSRID(ST_Extent(t.geometry)::geometry, 4326) AS extent FROM ..."
              +→ _append_tail(..., group_by=group_cols_str)
      4. return _run(sql, [], into, geometry_column="extent")
```

### Recommended Project Structure

No new directories. All changes in:

```
pycopg/
└── spatial.py           # 3 new builders + _append_tail extension + 6 new accessor methods
tests/
└── test_spatial.py      # new TestAggregateBuilders + injection tests + routing ext + integration
tests/
└── test_parity.py       # new test_spatial_aggregates_surface frozenset test
docs/
└── stability.md         # 3 new stable-tier rows per accessor
```

### Pattern 1: Shared Aggregate Builder (`_build_agg_geom_sql`)

**What:** Internal helper backing `build_collect_geometries_sql` and `build_union_aggregate_sql`. Mirrors `_build_binary_geom_sql` from Phase 42.

**When to use:** Any aggregate where the SQL shape is `SELECT [group_cols,] AGG_FUNC(t.geom) AS alias FROM schema.table AS t [WHERE] [GROUP BY] [ORDER BY] [LIMIT]` with no `%s` params.

```python
# Source: codebase pattern from _build_binary_geom_sql (spatial.py ~957)
def _build_agg_geom_sql(
    agg_func: str,
    result_col: str,
    table: str,
    geom: str,
    schema: str,
    *,
    group_by: list[str] | None,
    filter: str | None,
    order_by: str | None,
    limit: int | None,
) -> tuple[str, list]:
    """Build SQL for a single-column geometry aggregate."""
    validate_identifiers(table, schema, geom)  # LINE 1 — security invariant
    if group_by:
        validate_identifiers(*group_by)
    group_cols = [f"t.{col}" for col in group_by] if group_by else []
    select_prefix = ", ".join(group_cols + [f"{agg_func}(t.{geom}) AS {result_col}"])
    sql = f"SELECT {select_prefix} FROM {schema}.{table} AS t"
    group_by_str = ", ".join(group_cols) if group_cols else None
    sql = _append_tail(sql, filter, order_by, limit, has_where=False, group_by=group_by_str)
    return sql, []
```

### Pattern 2: Aggregate-Aware `_append_tail` Extension (D-03)

**What:** Extend `_append_tail` with an optional `group_by: str | None = None` argument inserted after WHERE, before ORDER BY.

**When to use:** All 3 aggregate builders; does NOT affect any existing builder caller (default `None` preserves existing behavior).

```python
# Source: codebase — current _append_tail at spatial.py ~149; GROUP BY precedent in timescale.py ~260
def _append_tail(
    sql: str,
    filter: str | None,
    order_by: str | None,
    limit: int | None,
    has_where: bool,
    group_by: str | None = None,   # NEW — aggregate GROUP BY clause body
) -> str:
    if filter:
        sql += f" AND ({filter})" if has_where else f" WHERE {filter}"
    if group_by:
        sql += f" GROUP BY {group_by}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return sql
```

**Important:** The new `group_by` parameter must be the pre-assembled column expression string (e.g., `"t.region"` or `"t.region, t.zone"`), already validated by `validate_identifiers` at the builder level. `_append_tail` does NOT call `validate_identifiers` — that is the builder's responsibility (line 1).

### Pattern 3: `build_extent_sql` — Builder Sees `into=` (D-04 exception)

**What:** `extent` is the one builder where the SQL shape depends on `into`. The `::text` vs `ST_SetSRID(::geometry, srid)` cast cannot be resolved in `_run` — it changes the column type.

```python
# Source: D-04 decision + int(srid) pattern at spatial.py ~120/123/126
def build_extent_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    group_by: list[str] | None = None,
    srid: int = 4326,
    into: str = "rows",
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    validate_identifiers(table, schema, geom)  # LINE 1
    if group_by:
        validate_identifiers(*group_by)
    group_cols = [f"t.{col}" for col in group_by] if group_by else []
    if into == "gdf":
        agg_expr = f"ST_SetSRID(ST_Extent(t.{geom})::geometry, {int(srid)}) AS extent"
    else:
        agg_expr = f"ST_Extent(t.{geom})::text AS extent"
    select_prefix = ", ".join(group_cols + [agg_expr]) if group_cols else agg_expr
    sql = f"SELECT {select_prefix} FROM {schema}.{table} AS t"
    group_by_str = ", ".join(group_cols) if group_cols else None
    sql = _append_tail(sql, filter, order_by, limit, has_where=False, group_by=group_by_str)
    return sql, []
```

Note: `build_extent_sql` receives `into` only to select the SQL branch. The accessor still calls `_check_into` before the builder — `build_extent_sql` does NOT call `_check_into` internally (keep concerns separated).

### Pattern 4: Accessor Method Shape (D-09, D-10)

```python
# Source: Phase 42 build_convex_hull + accessor convention (spatial.py ~2395/2430)
def collect_geometries(
    self,
    table: str,
    *,
    geom: str = "geometry",
    schema: str = "public",
    group_by: str | list[str] | None = None,
    into: str = "rows",
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict] | gpd.GeoDataFrame:
    # Normalize group_by (D-01)
    if isinstance(group_by, str):
        group_by = [group_by]
    _check_into(into, "collect_geometries")
    sql, params = build_collect_geometries_sql(
        table, geom=geom, schema=schema, group_by=group_by,
        filter=filter, order_by=order_by, limit=limit,
    )
    return self._run(sql, params, into, "collected")
```

Async mirror is byte-identical except: `async def` + `await self._run(...)`.

### Anti-Patterns to Avoid

- **`where=` alias on new methods:** New builders are born clean — no `where=` shim. The deprecation shim is only for the 11 pre-1.0 spatial methods.
- **`columns=` parameter on aggregates:** Illegal under GROUP BY; no footgun trap.
- **Interpolating `group_by` without `validate_identifiers`:** Every group column must pass `validate_identifiers` before being f-string-interpolated. This is the Pitfall 1 failure mode.
- **Adding `extent` to `_SCALAR_HELPERS`:** D-04 explicitly forbids this — `into="gdf"` IS valid for extent (via the geometry cast).
- **Calling `int(srid)` in the accessor instead of the builder:** The `int(srid)` cast belongs in `build_extent_sql` where the f-string interpolation happens, following the `build_point_geom` convention.
- **Two builders for `extent`:** D-04 explicitly prefers one builder + one branch (DRY).
- **Edit sync class, defer async:** D-10 requires editing both classes in the same commit.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Identifier injection guard | Custom regex / quoting | `validate_identifiers` from `utils.py` | Proven, covers all edge cases, consistent |
| Named-bind conversion for GDF path | Custom `%s` replacer | `_to_named_binds(sql, params)` in spatial.py | Already exists, tested |
| `into=` validation | Inline if/else | `_check_into(into, helper_name)` | Raises consistent ValueError message |
| GDF routing | Direct `to_geodataframe` call | `_run(sql, params, into, geometry_column)` / `_arun(...)` | Handles both paths uniformly |
| SRID injection safety | Quoted string | `int(srid)` cast in f-string | Established pattern lines ~120/123/126 |

**Key insight:** All the machinery to implement these methods exists. The work is assembling the GROUP BY aggregate SQL shape and wiring it through the established pipeline — no new infrastructure beyond the aggregate tail and `_build_agg_geom_sql`.

---

## Common Pitfalls

### Pitfall 1: `validate_identifiers` Missing on `group_by` Columns
**What goes wrong:** Builder validates `table`/`schema`/`geom` (inherited from template) but forgets to validate `group_by` column names. A malicious `group_by="region; DROP TABLE users; --"` passes the table/geom check and is interpolated directly into SQL.
**Why it happens:** `group_by` is a new argument not in the Phase 42 template. Easy to copy the template header and miss the new validation loop.
**How to avoid:** The builder injection test MUST test malicious `group_by` values specifically. The test is the safety net: `build_collect_geometries_sql("t", group_by="bad; DROP TABLE") → InvalidIdentifierError`.
**Warning signs:** A builder test that only tests malicious `table` but not malicious `group_by`.

### Pitfall 2: `_append_tail` Signature Change Breaks Existing Callers
**What goes wrong:** Extending `_append_tail` with a positional `group_by` arg breaks the 20+ existing call sites.
**How to avoid:** The new `group_by` parameter MUST be keyword-only with `None` default. Because Python functions don't have a `*` forced kw-only point naturally, write: `def _append_tail(sql, filter, order_by, limit, has_where, *, group_by=None)` — or keep it positional with a default but document the position carefully. The safe approach: add as a keyword-only arg at the end.
**Warning signs:** Any existing `_append_tail(sql, f, o, l, hw)` call breaking at runtime.

### Pitfall 3: `extent` Added to `_SCALAR_HELPERS` By Analogy to Phase 42 `area`/`perimeter`
**What goes wrong:** Reviewer or implementer looks at `area`/`perimeter` in `_SCALAR_HELPERS` and incorrectly adds `extent` there too, blocking `into="gdf"` with the scalar guard.
**How to avoid:** D-04 explicitly states "extent NOT in `_SCALAR_HELPERS`". The GDF path is valid because the builder casts `box2d::geometry`. The accessor test must assert `into="gdf"` does NOT raise.
**Warning signs:** `extent` appears in the `_SCALAR_HELPERS = frozenset({...})` definition.

### Pitfall 4: NULL All-Group Returns Zero Rows (Wrong — Should Return One Row with NULL)
**What goes wrong:** A HAVING clause is added to filter NULL aggregate results. This is explicitly forbidden (D-07). An all-NULL group should return one row with `{"collected": None}`, not zero rows.
**How to avoid:** The SQL must not contain `HAVING`. The intentional-NULL fixture test verifies the NULL row IS present in results. Docstring must say "NULL geometries are skipped per SQL aggregate semantics; an all-NULL group yields a row with NULL aggregate value."
**Warning signs:** SQL contains `HAVING ... IS NOT NULL`.

### Pitfall 5: `group_by=[]` (Empty List) vs `group_by=None`
**What goes wrong:** User passes `group_by=[]`. Without a guard, the builder generates `GROUP BY ` (empty string after GROUP BY) — syntax error at the database.
**How to avoid:** Normalize: if `group_by` is an empty list, treat as `None` (whole-table aggregate). Or raise `ValueError("group_by cannot be an empty list; use None for whole-table aggregate")`. Either is fine — document the choice.
**Warning signs:** `GROUP BY ` in generated SQL with no columns after it.

### Pitfall 6: KIND Parity Drift — `group_by` or `srid` Positional in Async
**What goes wrong:** The sync method has `group_by` as keyword-only (after `*`), but the async mirror accidentally has it as positional (common copy-paste error when `*` boundary is missing).
**How to avoid:** `test_accessor_parameter_kind_parity` catches this — it compares `inspect.Parameter.kind` for every parameter. The test will fail immediately if `group_by` kind differs between sync and async.
**Warning signs:** `test_accessor_parameter_kind_parity` fails after adding the new methods.

---

## Code Examples

### Generated SQL — Verified Shapes

#### `collect_geometries` whole-table
```sql
SELECT ST_Collect(t.geometry) AS collected FROM public.zones AS t
```

#### `collect_geometries` with `group_by="region"`
```sql
SELECT t.region, ST_Collect(t.geometry) AS collected FROM public.zones AS t GROUP BY t.region
```

#### `collect_geometries` with `group_by="region"` + `filter` + `order_by` + `limit`
```sql
SELECT t.region, ST_Collect(t.geometry) AS collected FROM public.zones AS t WHERE active = true GROUP BY t.region ORDER BY t.region LIMIT 10
```

#### `union_aggregate` with `group_by=["region", "zone"]`
```sql
SELECT t.region, t.zone, ST_Union(t.geometry) AS dissolved FROM public.zones AS t GROUP BY t.region, t.zone
```

#### `extent` with `into="rows"`, `group_by=None`
```sql
SELECT ST_Extent(t.geometry)::text AS extent FROM public.zones AS t
```

#### `extent` with `into="gdf"`, `group_by="region"`, `srid=4326`
```sql
SELECT t.region, ST_SetSRID(ST_Extent(t.geometry)::geometry, 4326) AS extent FROM public.zones AS t GROUP BY t.region
```

These are derived from the locked decisions (D-03, D-04, D-06). The clause order GROUP BY→ORDER BY→LIMIT mirrors `_build_time_bucket_sql` in `timescale.py` line ~260.

### Injection Test Pattern (per-builder, matches Phase 42 convention)

```python
# Source: test_spatial.py ~497-505 (union injection tests)
def test_collect_geometries_invalid_table(self):
    """collect_geometries validates the table identifier."""
    with pytest.raises(InvalidIdentifierError):
        build_collect_geometries_sql("bad-name", group_by=None)

def test_collect_geometries_invalid_geom(self):
    """collect_geometries validates the geom identifier."""
    with pytest.raises(InvalidIdentifierError):
        build_collect_geometries_sql("zones", geom="bad; DROP TABLE")

def test_collect_geometries_invalid_group_by(self):
    """collect_geometries validates group_by columns (Pitfall 1)."""
    with pytest.raises(InvalidIdentifierError):
        build_collect_geometries_sql("zones", group_by=["region; DROP TABLE users; --"])
```

### Integration Fixture — NULL Geometry Rows (D-07)

```python
# Pattern: _make_points in TestIntegration; adapt for aggregates
def _make_grouped_with_nulls(self, db, t):
    """Create a table with grouped geometries including intentional NULL rows."""
    db.execute(
        f'CREATE TABLE "{t}" (id INT, region TEXT, geometry geometry(Point, 4326))',
        autocommit=True,
    )
    db.execute(
        f'INSERT INTO "{t}" VALUES '
        "(1, 'north', ST_GeomFromText('POINT(0 1)', 4326)), "
        "(2, 'north', NULL), "                          # intentional NULL geometry
        "(3, 'south', ST_GeomFromText('POINT(0 -1)', 4326))",
        autocommit=True,
    )

def test_collect_geometries_null_rows_pass_through(self, sdb):
    """collect_geometries with NULL geometry rows: group still has 1 row; NULL skipped."""
    t = _uniq("spat_agg_null")
    try:
        self._make_grouped_with_nulls(sdb, t)
        rows = sdb.spatial.collect_geometries(t, group_by="region", order_by="region")
        # Both groups present; 'north' aggregate is over 1 non-NULL row (D-07)
        assert len(rows) == 2
        regions = [r["region"] for r in rows]
        assert "north" in regions and "south" in regions
        for row in rows:
            assert "collected" in row
    finally:
        sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

def test_collect_geometries_all_null_group(self, sdb):
    """All-NULL group returns one row with NULL aggregate (D-07, no HAVING)."""
    t = _uniq("spat_agg_allnull")
    try:
        db.execute(
            f'CREATE TABLE "{t}" (region TEXT, geometry geometry(Point, 4326))',
            autocommit=True,
        )
        sdb.execute(
            f"INSERT INTO \"{t}\" VALUES ('x', NULL)",
            autocommit=True,
        )
        rows = sdb.spatial.collect_geometries(t, group_by="region")
        assert len(rows) == 1
        assert rows[0]["collected"] is None  # NULL aggregate, not zero rows
    finally:
        sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Row-by-row geometry assembly in Python | PostGIS server-side aggregate (ST_Collect) | PostGIS 1.4 | All aggregation in DB — no client-side geometry construction |
| `GROUP BY` added manually in raw SQL | `group_by=` kw-only parameter | Phase 43 (this phase) | First GROUP-BY aggregate shape in pycopg spatial surface |
| `where=` raw SQL fragment on spatial methods | `filter=` on new builders (born clean) | Phase 41 freeze | No migration shim for new Phase 43 builders |

**Deprecated/outdated:**
- `ST_Extent` returning `box2d` directly: the GDF path requires the `::geometry` + `ST_SetSRID` cast, not native `box2d` — `box2d` is a text-serializable PostgreSQL type but not a geometry PostGIS type.

---

## Open Questions

1. **`group_by=[]` empty list handling**
   - What we know: the builder will try `validate_identifiers()` with no args (no-op) and then produce `GROUP BY ` (empty), which is a PostgreSQL syntax error.
   - What's unclear: whether to silently treat `[]` as `None` (whole-table aggregate) or raise `ValueError`.
   - Recommendation: raise `ValueError("group_by cannot be an empty list; pass None for a whole-table aggregate")` — explicit is better than silent.

2. **`t.` alias on GROUP BY columns vs bare column names**
   - What we know: `GROUP BY t.region` and `GROUP BY region` are both valid PostgreSQL when the table is aliased `AS t`. The SELECT list already uses `t.region`.
   - What's unclear: whether `GROUP BY t.region` (alias-qualified) or `GROUP BY region` (unqualified) is safer for column name conflicts.
   - Recommendation: Use `t.` qualification in GROUP BY to match the SELECT list — consistency and no ambiguity risk (Claude's Discretion per D-03).

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostGIS | ST_Collect/ST_Union/ST_Extent | ✓ | 3.6.4 (CI timescale/timescaledb-ha:pg17) | Skip live tests |
| GEOS | PostGIS geometry engine | ✓ | 3.13.1 (from Phase 42 CONTEXT.md) | N/A (bundled) |
| psycopg | DB driver | ✓ | ≥ 3.1.0 (from pyproject.toml) | None needed |
| geopandas | `into="gdf"` path | ✓ | ≥ 0.14.0 | N/A |

**Missing dependencies with no fallback:** None — all required dependencies available.

ST_Collect, ST_Union (aggregate), and ST_Extent are all Apache PostGIS, available since PostGIS 1.x, well within the project's 3.0 hard floor. No version gate needed.

---

## Validation Architecture

> Nyquist validation is ENABLED (no `workflow.nyquist_validation: false` in `.planning/config.json`).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (verified: `pyproject.toml` `[tool.pytest.ini_options]`) |
| Config | `pyproject.toml` `[tool.pytest.ini_options]` + conftest.py |
| Quick run | `uv run pytest tests/test_spatial.py -x -q` |
| Full suite | `uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SPAT2-07 | `build_collect_geometries_sql` emits `ST_Collect(t.geom) AS collected` with no GROUP BY when `group_by=None` | unit (SQL-shape) | `uv run pytest tests/test_spatial.py::TestAggregateBuilders::test_collect_geometries_whole_table -x` | ❌ Wave 0 |
| SPAT2-07 | `build_collect_geometries_sql` emits `SELECT t.region, ST_Collect(...) AS collected ... GROUP BY t.region` when `group_by="region"` | unit (SQL-shape) | `uv run pytest tests/test_spatial.py::TestAggregateBuilders::test_collect_geometries_with_group_by -x` | ❌ Wave 0 |
| SPAT2-07 | `build_collect_geometries_sql` with `filter=`/`order_by=`/`limit=`: GROUP BY is between WHERE and ORDER BY | unit (SQL-shape) | `uv run pytest tests/test_spatial.py::TestAggregateBuilders::test_collect_geometries_tail_clauses -x` | ❌ Wave 0 |
| SPAT2-07 | `build_collect_geometries_sql` raises `InvalidIdentifierError` on malicious `table` | injection | `uv run pytest tests/test_spatial.py::TestAggregateBuilders::test_collect_geometries_invalid_table -x` | ❌ Wave 0 |
| SPAT2-07 | `build_collect_geometries_sql` raises `InvalidIdentifierError` on malicious `geom` | injection | `uv run pytest tests/test_spatial.py::TestAggregateBuilders::test_collect_geometries_invalid_geom -x` | ❌ Wave 0 |
| SPAT2-07 | `build_collect_geometries_sql` raises `InvalidIdentifierError` on malicious `group_by` column | injection | `uv run pytest tests/test_spatial.py::TestAggregateBuilders::test_collect_geometries_invalid_group_by -x` | ❌ Wave 0 |
| SPAT2-07 | Live: whole-table collect returns 1 row with `collected` geometry | integration | `uv run pytest tests/test_spatial.py::TestIntegration::test_collect_geometries_whole_table -x` | ❌ Wave 0 |
| SPAT2-07 | Live: grouped collect returns one row per group | integration | `uv run pytest tests/test_spatial.py::TestIntegration::test_collect_geometries_grouped -x` | ❌ Wave 0 |
| SPAT2-07 | Live: NULL geometry rows — all-NULL group yields row with NULL `collected` (D-07, no HAVING) | integration | `uv run pytest tests/test_spatial.py::TestIntegration::test_collect_geometries_all_null_group -x` | ❌ Wave 0 |
| SPAT2-07 | Live: mixed-NULL group — NULL rows skipped, non-NULL aggregated (D-07) | integration | `uv run pytest tests/test_spatial.py::TestIntegration::test_collect_geometries_null_rows_pass_through -x` | ❌ Wave 0 |
| SPAT2-08 | `build_union_aggregate_sql` emits `ST_Union(t.geom) AS dissolved` (not `dissolved_geom`) | unit (SQL-shape) | `uv run pytest tests/test_spatial.py::TestAggregateBuilders::test_union_aggregate_whole_table -x` | ❌ Wave 0 |
| SPAT2-08 | `build_union_aggregate_sql` with `group_by` emits correct GROUP BY placement | unit (SQL-shape) | `uv run pytest tests/test_spatial.py::TestAggregateBuilders::test_union_aggregate_with_group_by -x` | ❌ Wave 0 |
| SPAT2-08 | `build_union_aggregate_sql` raises `InvalidIdentifierError` on malicious `table`, `geom`, `group_by` | injection | `uv run pytest tests/test_spatial.py::TestAggregateBuilders::test_union_aggregate_invalid_* -x` | ❌ Wave 0 |
| SPAT2-08 | Live: whole-table union_aggregate returns 1 dissolved geometry | integration | `uv run pytest tests/test_spatial.py::TestIntegration::test_union_aggregate_whole_table -x` | ❌ Wave 0 |
| SPAT2-08 | Live: grouped union_aggregate; NULL rows pass-through (D-07) | integration | `uv run pytest tests/test_spatial.py::TestIntegration::test_union_aggregate_null_rows -x` | ❌ Wave 0 |
| SPAT2-09 | `build_extent_sql(into="rows")` emits `ST_Extent(t.geom)::text AS extent` | unit (SQL-shape) | `uv run pytest tests/test_spatial.py::TestAggregateBuilders::test_extent_rows_branch -x` | ❌ Wave 0 |
| SPAT2-09 | `build_extent_sql(into="gdf")` emits `ST_SetSRID(ST_Extent(t.geom)::geometry, 4326) AS extent` | unit (SQL-shape) | `uv run pytest tests/test_spatial.py::TestAggregateBuilders::test_extent_gdf_branch -x` | ❌ Wave 0 |
| SPAT2-09 | `build_extent_sql(into="gdf", srid=3857)` uses `int(srid)` — custom SRID in cast | unit (SQL-shape) | `uv run pytest tests/test_spatial.py::TestAggregateBuilders::test_extent_custom_srid -x` | ❌ Wave 0 |
| SPAT2-09 | `build_extent_sql` with GROUP BY: group cols in SELECT + GROUP BY after WHERE | unit (SQL-shape) | `uv run pytest tests/test_spatial.py::TestAggregateBuilders::test_extent_with_group_by -x` | ❌ Wave 0 |
| SPAT2-09 | `build_extent_sql` raises `InvalidIdentifierError` on malicious `table`, `geom`, `group_by` | injection | `uv run pytest tests/test_spatial.py::TestAggregateBuilders::test_extent_invalid_* -x` | ❌ Wave 0 |
| SPAT2-09 | `extent` with `into="gdf"` does NOT raise (extent NOT in `_SCALAR_HELPERS`) | unit | `uv run pytest tests/test_spatial.py::TestAggregateBuilders::test_extent_gdf_not_rejected -x` | ❌ Wave 0 |
| SPAT2-09 | Live: extent `into="rows"` returns box2d text string | integration | `uv run pytest tests/test_spatial.py::TestIntegration::test_extent_rows_returns_box2d_text -x` | ❌ Wave 0 |
| SPAT2-09 | Live: extent `into="gdf"` returns GeoDataFrame with geometry column `extent` | integration | `uv run pytest tests/test_spatial.py::TestIntegration::test_extent_gdf_returns_geodataframe -x` | ❌ Wave 0 |
| SPAT2-09 | Live: grouped extent returns one row per group | integration | `uv run pytest tests/test_spatial.py::TestIntegration::test_extent_grouped -x` | ❌ Wave 0 |
| SPAT2-09 | Live: all-NULL group extent returns NULL (not empty box2d), D-07 | integration | `uv run pytest tests/test_spatial.py::TestIntegration::test_extent_null_group -x` | ❌ Wave 0 |
| D-10 parity | 3 new methods present on AsyncSpatialAccessor | parity | `uv run pytest tests/test_parity.py::test_accessor_parity -x` | ✅ (auto-extends) |
| D-10 kind | `group_by`/`srid` keyword-only boundary identical on sync/async | parity | `uv run pytest tests/test_parity.py::test_accessor_parameter_kind_parity -x` | ✅ (auto-extends) |
| SPAT2-07/08/09 surface | `collect_geometries`, `union_aggregate`, `extent` on both accessor classes | surface | `uv run pytest tests/test_parity.py::test_spatial_aggregates_surface -x` | ❌ Wave 0 |
| routing | 3 new aggregate methods route into="rows" through db.execute | routing | `uv run pytest tests/test_spatial.py::TestAccessorRouting -x` (after _HELPER_CALLS extended) | ❌ Wave 0 (list extension) |
| routing | `collect_geometries`/`union_aggregate`/`extent` (gdf) routes with correct geometry_column | routing | `uv run pytest tests/test_spatial.py::TestAccessorRouting -x` (after _GDF_CALLS extended) | ❌ Wave 0 (list extension) |

### Test Layers and Their Roles (D-08)

**Layer (a) — Mock/SQL-shape authoritative unit tests (no DB required):**

Each test asserts the exact SQL string shape. Assertions to include:
1. SQL contains correct PostGIS aggregate function (`ST_Collect`, `ST_Union`, `ST_Extent`)
2. Result column alias matches D-06 name (`AS collected`, `AS dissolved`, `AS extent`)
3. GROUP BY is present and appears AFTER WHERE and BEFORE ORDER BY
4. `filter=`/`order_by=`/`limit=` tail correctly appended
5. `into="gdf"` branch produces `ST_SetSRID(ST_Extent(...)::geometry, ...)` not `::text`
6. `int(srid)` custom value appears in SQL
7. `%s` count == `len(params)` (should both be 0 for aggregate builders)

**Layer (b) — Live integration tests:**

Real PostGIS tests using the `sdb` fixture in `TestIntegration`. Cover:
- All 3 aggregates: whole-table (group_by=None) and grouped (group_by="region")
- NULL geometry fixture: rows with intentional NULL geometry — verify NULL aggregate, not missing row
- `extent` `into="rows"` returns string like `"BOX(0 0, 1 1)"`
- `extent` `into="gdf"` returns GeoDataFrame with `geometry.name == "extent"`
- `collect_geometries`/`union_aggregate` with `into="gdf"` returns GeoDataFrame with correct geometry column name

### Mock Recording Pattern for Routing Tests

Extend `_HELPER_CALLS` and `_GDF_CALLS` in `TestAccessorRouting`:

```python
# Add to _HELPER_CALLS:
("collect_geometries", {}),                               # SPAT2-07
("union_aggregate", {}),                                  # SPAT2-08
("extent", {}),                                           # SPAT2-09

# Add to _GDF_CALLS (geom column = D-06 name):
("collect_geometries", {}, "collected"),                  # SPAT2-07
("union_aggregate", {}, "dissolved"),                     # SPAT2-08
("extent", {"into": "gdf"}, "extent"),                    # SPAT2-09
```

Note: `extent` needs `into="gdf"` explicitly in `_GDF_CALLS` because the builder must know `into` to generate the geometry branch. The `_RecordingSyncDb.execute` mock records the call, so `into="rows"` also works for the rows-path routing test.

### Aggregates Surface Test (pattern: `test_spatial_v1_processing_surface` in test_parity.py)

Add to `test_parity.py`:

```python
def test_spatial_aggregates_surface():
    """Assert both spatial accessors expose the 3 Phase 43 aggregate methods."""
    v43_surface = frozenset({
        "collect_geometries",
        "union_aggregate",
        "extent",
    })
    for cls in (SpatialAccessor, AsyncSpatialAccessor):
        public = {name for name, _ in inspect.getmembers(cls) if not name.startswith("_")}
        missing = v43_surface - public
        assert not missing, f"{cls.__name__} is missing Phase 43 method(s): {sorted(missing)}"
```

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_spatial.py -x -q` (SQL-shape + injection + routing; ~5 seconds)
- **Per wave merge:** `uv run pytest` (full suite including parity + integration; ~30-60 seconds)
- **Phase gate:** Full suite green + coverage ≥95% before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_spatial.py` — new `TestAggregateBuilders` class for 3 builders (SQL-shape + GROUP BY placement + extent branches)
- [ ] `tests/test_spatial.py` — injection tests: 3 builders × (malicious `table`, `geom`, `group_by`) = 9 tests
- [ ] `tests/test_spatial.py` — live integration: whole-table + grouped + NULL fixture per aggregate
- [ ] `tests/test_spatial.py` — `_HELPER_CALLS` and `_GDF_CALLS` extended with 3 new entries each
- [ ] `tests/test_parity.py` — `test_spatial_aggregates_surface` frozenset test

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on Phase 43 |
|-----------|-------------------|
| `pycopg` is an independent library — no Solaris/MarketStream deps | No new deps; PostGIS is a DB-side dependency, not a Python runtime dep |
| `pycopg/venv/` — own venv, `uv sync --all-extras --dev` | All test runs via `uv run pytest` |
| Coverage ratchet ≥95% | New code must be covered; 3 builders + 6 accessor methods + NULL fixture paths must all have tests |
| `uv run ruff check` + `uv run black` | Standard formatting/lint; no special impact on aggregate builder code |
| `uv run pytest tests/ -x -q` for quick runs | Use this during wave-by-wave development |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ST_Collect`, `ST_Union` (aggregate), `ST_Extent` available since PostGIS 2.x, within the 3.0 hard floor | Standard Stack | Low — these are foundational PostGIS functions; verified indirectly via milestone research docs |
| A2 | `ST_SetSRID(ST_Extent(...)::geometry, srid)` produces a valid polygon geometry GeoPandas can load | Code Examples | Low — standard PostGIS pattern; would surface in live integration test |
| A3 | All-NULL group for `ST_Extent` returns NULL (not empty box2d), same as `ST_Collect`/`ST_Union` | Common Pitfalls | Medium — the intentional-NULL integration test verifies this live |
| A4 | `t.` alias qualification in GROUP BY columns is valid PostgreSQL (i.e., `GROUP BY t.region` where table is `AS t`) | Code Examples | Low — standard SQL; verified via `_build_time_bucket_sql` precedent which uses column-only `GROUP BY bucket` |

**Verified claims in this research:** All architectural claims, builder patterns, `_append_tail` signature, accessor shape, test patterns, parity guard behavior — verified by direct codebase inspection. [VERIFIED: codebase]

---

## Sources

### Primary (HIGH confidence)
- `pycopg/spatial.py` (4506 lines, inspected directly) — `_append_tail` ~149, `_build_binary_geom_sql` ~957, Phase 42 builders ~983-1438, `_SCALAR_HELPERS`/`_VALID_INTO`/`_check_into` ~1443-1477, `_to_named_binds` ~1480, `SpatialAccessor._run` ~1536, `AsyncSpatialAccessor._arun` ~3016, `int(srid)` pattern ~120-126
- `pycopg/timescale.py` — `_build_time_bucket_sql` ~252: GROUP BY precedent (`WHERE ... GROUP BY bucket ORDER BY bucket`)
- `tests/test_spatial.py` (1433 lines) — injection test conventions ~497-505, `_HELPER_CALLS`/`_GDF_CALLS` ~1228-1261, `TestAccessorRouting` ~1264, `TestIntegration` ~814
- `tests/test_parity.py` — `test_accessor_parity` ~36, `test_accessor_parameter_kind_parity` ~362, `test_spatial_v1_processing_surface` ~135
- `.planning/phases/43-spatial-v2-spatial-aggregates/43-CONTEXT.md` — D-01..D-10 locked decisions (authoritative)
- `.planning/REQUIREMENTS.md` — SPAT2-07/08/09 + cross-cutting acceptance criteria
- `.planning/research/FEATURES.md` §"Workstream 1: Spatial V2 — Spatial Aggregates" ~249-370 (CAVEAT: `group_by: list[str]` and `where=` are pre-Phase-41 — use `str | list[str]` per D-01, `filter=` per D-09)
- `.planning/research/PITFALLS.md` — Pitfall 1 (validate_identifiers), Pitfall 5 (aggregate NULL), Pitfall 11 (parity drift)
- `.planning/phases/42-spatial-v2-processing-helpers/42-RESEARCH.md` — validation architecture template, Phase 42 pattern

### Secondary (MEDIUM confidence)
- `.planning/research/SUMMARY.md` §"Architecture Approach" — GROUP-BY aggregate builder shape rationale

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; PostGIS functions from existing milestone research
- Architecture: HIGH — direct codebase inspection; all patterns verified against spatial.py
- Pitfalls: HIGH — derived from pycopg's own history + D-07 explicit NULL decision
- Test map: HIGH — direct extension of Phase 42 test pattern, verified against test_spatial.py

**Research date:** 2026-06-29
**Valid until:** 2026-07-30 (stable; PostGIS aggregate APIs do not change)
