# Feature Research — pycopg v1.0.0 (Spatial v2 + API Freeze)

**Domain:** High-level Python API for PostgreSQL/PostGIS/TimescaleDB — 1.0 completion milestone
**Researched:** 2026-06-27
**Confidence:** HIGH (PostGIS function signatures from postgis.net/docs; psycopg3 transaction API from official psycopg3 docs; existing codebase patterns read directly)

---

## Context: What v1.0.0 Adds

v1.0.0 has three workstreams locked at cadrage. This research covers **only the new features** — what already exists (`db.spatial.*` 11 helpers, flat CRUD, `db.schema.*`, `db.etl.*`, `db.timescale.*`, etc.) is not re-researched.

**Builder pattern contract (all new features must follow this):**
- Module-level pure builders return `(sql: str, params: list)` — stateless, no I/O, DB-free
- Identifiers go through `validate_identifiers` before any string interpolation
- User values go through `%s` placeholders — never f-string interpolated
- Accessor methods delegate to builders, then route via `into=` or direct execute
- `AsyncSpatialAccessor` mirrors `SpatialAccessor` exactly with `async def` + `await`
- `_check_into(into, helper)` validates `into=` before any SQL runs
- `_SCALAR_HELPERS` frozenset controls which methods forbid `into="gdf"`

**Scope boundary (locked 2026-06-27):** Raster, TSDB follow-ups (TSDB-F01..04), ETL follow-ups (ETL-INC-F01..05), CRUD follow-ups (CRUD-F01..03), and schema follow-ups (INTRO-F01..02) are explicitly OUT. They become non-breaking 1.x additions after the API freeze.

---

## Workstream 1: Spatial V2 — Geometry Processing

### SPAT-V2-01 — `union` (2-geometry form)

**PostGIS signature:** `geometry ST_Union(geometry g1, geometry g2)`

**What it does:** Returns a geometry representing the point-set union of two geometries. Unlike the aggregate form, this is a scalar operation on two explicit geometry inputs from table columns.

**pycopg API shape — table-level column union:**

```python
# Select rows with each row's geometry unioned with another column (or constant)
def union(
    self,
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    other_geom: str,          # second geometry column on same table (identifier)
    into: str = "rows",
    columns: list[str] | None = None,
    where: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict] | gpd.GeoDataFrame:
```

Generated SQL: `SELECT <cols>, ST_Union(t.<geom>, t.<other_geom>) AS union_geom FROM <schema>.<table> AS t`

Both `geom` and `other_geom` are identifier-validated. Result column `union_geom` is a geometry — `into="gdf"` is valid.

**Classification:** TABLE STAKES — geometry union is one of the most fundamental spatial operations. Any spatial Python library without it is incomplete.

**Complexity:** LOW — same builder pattern as `buffer`/`transform`; two-identifier variant.

**Dependency:** Follows exact builder-pur pattern from existing spatial.py. No new infrastructure needed.

---

### SPAT-V2-02 — `simplify`

**PostGIS signatures:**
- `geometry ST_Simplify(geometry geom, float tolerance)`
- `geometry ST_Simplify(geometry geom, float tolerance, boolean preserveCollapsed)`
- `geometry ST_SimplifyPreserveTopology(geometry geom, float tolerance)`

**What it does:** Reduces the number of vertices in a geometry using the Douglas-Peucker algorithm. `ST_SimplifyPreserveTopology` is the safer variant that guarantees the result has the same topology and never produces self-intersections.

**pycopg API shape:**

```python
def simplify(
    self,
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    tolerance: float,
    preserve_topology: bool = True,  # default to safe variant
    preserve_collapsed: bool = False,  # only used when preserve_topology=False
    into: str = "rows",
    columns: list[str] | None = None,
    where: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict] | gpd.GeoDataFrame:
```

Generated SQL (when `preserve_topology=True`):
`SELECT <cols>, ST_SimplifyPreserveTopology(t.<geom>, %s) AS simplified FROM ...`

Generated SQL (when `preserve_topology=False`):
`SELECT <cols>, ST_Simplify(t.<geom>, %s, %s) AS simplified FROM ...`

`tolerance` is a `%s` param. `preserve_collapsed` is a `%s` bool param. Result column `simplified` is a geometry — `into="gdf"` is valid.

**Classification:** TABLE STAKES — simplification is essential for map rendering and data export. `preserve_topology=True` default prevents the silent production of invalid geometries that `ST_Simplify` alone can create.

**Complexity:** LOW — two SQL variants selected by a boolean flag; trivial builder.

---

### SPAT-V2-03 — `convex_hull`

**PostGIS signature:** `geometry ST_ConvexHull(geometry geomA)`

**What it does:** Computes the convex hull of a geometry — the minimum convex polygon enclosing all input vertices. Classic use cases: bounding region for a point cluster, enclosing polygon for a linestring.

**pycopg API shape:**

```python
def convex_hull(
    self,
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    into: str = "rows",
    columns: list[str] | None = None,
    where: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict] | gpd.GeoDataFrame:
```

Generated SQL: `SELECT <cols>, ST_ConvexHull(t.<geom>) AS convex_hull FROM <schema>.<table> AS t`

Result column `convex_hull` is a geometry — `into="gdf"` is valid.

**Classification:** TABLE STAKES — convex hull is a standard spatial operation found in every GIS toolkit. Its absence would be conspicuous.

**Complexity:** LOW — simplest possible builder; one identifier, no extra params.

---

### SPAT-V2-04 — `make_valid`

**PostGIS signatures:**
- `geometry ST_MakeValid(geometry input)`
- `geometry ST_MakeValid(geometry input, text params)`

**What it does:** Attempts to repair an invalid geometry without losing vertices. Common use case: sanitizing data loaded from external sources before spatial operations. The `params` string controls the repair algorithm: `"method=linework"` (default, Douglas-Peucker-style) or `"method=structure keepcollapsed=true|false"` (requires GEOS >= 3.10.0).

**pycopg API shape:**

```python
def make_valid(
    self,
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    method: str | None = None,  # None = default (linework); "structure" for GEOS 3.10+
    keep_collapsed: bool | None = None,  # only for method="structure"
    into: str = "rows",
    columns: list[str] | None = None,
    where: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict] | gpd.GeoDataFrame:
```

When `method` is None: `ST_MakeValid(t.<geom>)` — no params string.
When `method="structure"`: `ST_MakeValid(t.<geom>, %s)` with params string `"method=structure keepcollapsed=true|false"` built from `keep_collapsed`.

`method` values are whitelisted: `None`, `"linework"`, `"structure"`. Invalid values raise `ValueError` before any SQL.

Result column `made_valid` is a geometry — `into="gdf"` is valid.

**Classification:** TABLE STAKES — geometry validity repair is a prerequisite for safe spatial processing pipelines. Users loading external geodata routinely need this.

**Complexity:** LOW-MEDIUM — params string construction needs a whitelist guard; two SQL variants.

---

### SPAT-V2-05 — `difference`

**PostGIS signature:** `geometry ST_Difference(geometry geomA, geometry geomB, float8 gridSize = -1)`

**What it does:** Returns the part of geometry A that does not intersect geometry B (A minus B). Order matters — result is always a subset of A.

**pycopg API shape — column-vs-column on same table:**

```python
def difference(
    self,
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    other_geom: str,           # second geometry column on same table
    into: str = "rows",
    columns: list[str] | None = None,
    where: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict] | gpd.GeoDataFrame:
```

Generated SQL: `SELECT <cols>, ST_Difference(t.<geom>, t.<other_geom>) AS difference FROM ...`

Both identifiers validated. The `gridSize` optional parameter is NOT exposed in the high-level API (it requires GEOS 3.9.0 and is an edge-case precision control — callers needing it can use raw `db.execute()`). Result column `difference` is a geometry — `into="gdf"` is valid.

**Classification:** TABLE STAKES — set difference is fundamental for polygon clipping, masking, and territory analysis.

**Complexity:** LOW — identical shape to `union` (two-column form). Can share builder structure.

---

### SPAT-V2-06 — `intersection`

**PostGIS signature:** `geometry ST_Intersection(geometry geomA, geometry geomB, float8 gridSize = -1)`

**What it does:** Returns the shared portion of two geometries. Symmetric operation (unlike `difference`).

**pycopg API shape — column-vs-column on same table:**

```python
def intersection(
    self,
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    other_geom: str,           # second geometry column on same table
    into: str = "rows",
    columns: list[str] | None = None,
    where: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict] | gpd.GeoDataFrame:
```

Generated SQL: `SELECT <cols>, ST_Intersection(t.<geom>, t.<other_geom>) AS intersection FROM ...`

Same shape as `difference`. `gridSize` NOT exposed in high-level API for same reasons. Result column `intersection` is a geometry — `into="gdf"` is valid.

**Classification:** TABLE STAKES — set intersection is the spatial equivalent of JOIN overlap; essential for overlay analysis.

**Complexity:** LOW — identical shape to `difference`.

---

## Workstream 1: Spatial V2 — Spatial Aggregates

Aggregates operate over a **set of rows** rather than row-by-row. They are intrinsically different from the processing helpers above: the output is a single geometry computed across all (or grouped) rows. The high-level API must decide:

1. **Whole-table aggregate** (no GROUP BY) — returns a single geometry.
2. **GROUP BY aggregate** — returns one geometry per group.

The existing spatial accessor has no aggregate-style methods. The pattern established by `time_bucket` in `db.timescale.*` (query helper returning DataFrame) is the closest precedent.

**Design decision for all three aggregate methods:** Return `list[dict]` or `gpd.GeoDataFrame` (via `into=`). Support optional `group_by` as an identifier-validated column list. When `group_by` is None, aggregate over all rows matching the optional `where` filter.

---

### SPAT-V2-07 — `collect_geometries` (ST_Collect aggregate)

**PostGIS signatures:**
- `geometry ST_Collect(geometry set g1field)` — aggregate form
- `geometry ST_Collect(geometry g1, geometry g2)` — 2-geometry form

**What it does:** Collects geometries into a GeometryCollection or Multi* type. Does NOT dissolve boundaries (unlike ST_Union). Faster than ST_Union when boundary dissolution is not needed.

**pycopg API shape (aggregate form — the high-value form):**

```python
def collect_geometries(
    self,
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    group_by: list[str] | None = None,  # None = whole-table aggregate
    into: str = "rows",
    where: str | None = None,
) -> list[dict] | gpd.GeoDataFrame:
```

Generated SQL (no `group_by`):
`SELECT ST_Collect(t.<geom>) AS collected FROM <schema>.<table> AS t [WHERE ...]`

Generated SQL (with `group_by`):
`SELECT <group_cols>, ST_Collect(t.<geom>) AS collected FROM <schema>.<table> AS t [WHERE ...] GROUP BY <group_cols>`

`group_by` column names are identifier-validated. Result column `collected` is a geometry — `into="gdf"` is valid. Returns a single row when `group_by` is None.

**Note on naming:** Named `collect_geometries` not `collect` to avoid collision with Python's `gc.collect()` conceptual confusion and to be explicit about what is collected. The method name clearly signals the spatial domain.

**Classification:** TABLE STAKES — geometry collection is the entry point for aggregate spatial analysis. ST_Collect is Apache PostGIS (not a premium add-on) and is universally expected.

**Complexity:** MEDIUM — first aggregate-pattern method; must handle GROUP BY identifier list correctly.

---

### SPAT-V2-08 — `union_aggregate` (ST_Union aggregate form)

**PostGIS signature:** `geometry ST_Union(geometry set g1field)` — aggregate form

**What it does:** Computes the geometric union of all rows, dissolving shared boundaries. The aggregate form dissolves all overlapping and touching geometries into a single merged polygon. Fundamentally different from the 2-geometry `union` method (SPAT-V2-01).

**pycopg API shape:**

```python
def union_aggregate(
    self,
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    group_by: list[str] | None = None,
    into: str = "rows",
    where: str | None = None,
) -> list[dict] | gpd.GeoDataFrame:
```

Generated SQL (no `group_by`):
`SELECT ST_Union(t.<geom>) AS union_geom FROM <schema>.<table> AS t [WHERE ...]`

Same shape as `collect_geometries`. Named `union_aggregate` to unambiguously distinguish from the 2-geometry `union` method. Result is a geometry — `into="gdf"` valid.

**Classification:** TABLE STAKES — dissolving geometries into a single merged polygon is the most common spatial aggregation use case (e.g., merge all parcels in a district, merge all routes in a region).

**Complexity:** MEDIUM — same infrastructure as `collect_geometries`; can share builder logic.

**Dependency:** Same aggregate builder pattern as SPAT-V2-07; implement together.

---

### SPAT-V2-09 — `extent` (ST_Extent aggregate)

**PostGIS signature:** `box2d ST_Extent(geometry set geomfield)`

**What it does:** Returns a `box2d` bounding box enclosing all geometries in the set. Commonly used to compute the spatial extent of a dataset or a group.

**Return shape consideration:** `box2d` is not a geometry — it cannot be loaded into a GeoDataFrame directly. The method should return `list[dict]` with the box2d cast to text (e.g., `ST_Extent(...)::text`) so users get the string representation like `BOX(xmin ymin, xmax ymax)`. Optionally, also accept `into="geometry"` which wraps in `ST_SetSRID(ST_Extent(...)::geometry, <srid>)` to return an actual polygon geometry for `gdf` routing.

**pycopg API shape:**

```python
def extent(
    self,
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    group_by: list[str] | None = None,
    into: str = "rows",   # "rows" returns box2d as text; "gdf" needs srid to cast to geometry
    srid: int = 4326,     # only used when into="gdf"
    where: str | None = None,
) -> list[dict] | gpd.GeoDataFrame:
```

Generated SQL (into="rows", no group_by):
`SELECT ST_Extent(t.<geom>)::text AS extent FROM <schema>.<table> AS t [WHERE ...]`

Generated SQL (into="gdf"):
`SELECT ST_SetSRID(ST_Extent(t.<geom>)::geometry, <srid>) AS extent FROM ...`

When `into="gdf"` the SRID is interpolated via `int(srid)` (injection-safe, existing pattern). When `into="rows"` the extent text is returned as a string in the `extent` key.

**Classification:** TABLE STAKES — spatial extent is a baseline inspection capability used in map initialization, tile generation, and data validation.

**Complexity:** MEDIUM — the `box2d` → geometry cast adds a branch; `into=` routing gains a third variant (rows/gdf handled differently for this helper).

---

## Workstream 1: Spatial V2 — Serialization

Serialization helpers transform geometry columns into wire formats: GeoJSON (web APIs), WKT (text interchange), and MVT (map tiles). Unlike the processing helpers, the return value is a scalar string or bytes — `into="gdf"` is explicitly invalid for all three.

---

### SPAT-V2-10 — `as_geojson` (ST_AsGeoJSON)

**PostGIS signature:** `text ST_AsGeoJSON(geometry geom, integer maxdecimaldigits=9, integer options=8)`

Options bitmask: 0=none, 1=bbox, 2=short CRS, 4=long CRS, 8=short CRS only when not EPSG:4326 (default).

**What it does:** Returns a JSON string representing the geometry in GeoJSON format. Most common serialization for web APIs.

**pycopg API shape:**

```python
def as_geojson(
    self,
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    max_decimal_digits: int = 6,  # default 6 (display-safe); PostGIS default is 9 (too precise for most uses)
    include_bbox: bool = False,   # adds options |= 1
    include_crs: bool = False,    # adds options |= 2 (short CRS)
    columns: list[str] | None = None,
    where: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict]:  # "gdf" is invalid — result is text, not geometry
```

Generated SQL:
`SELECT <cols>, ST_AsGeoJSON(t.<geom>, %s, %s) AS geojson FROM <schema>.<table> AS t`

Both `max_decimal_digits` and the computed `options` integer go through `%s`. Callers get `list[dict]` where the `geojson` key holds a JSON string. Users parse it with `json.loads()` if they need a dict.

**Note on max_decimal_digits default:** PostGIS default is 9 but 6 decimal digits is 0.1m precision — sufficient for display and API purposes while producing significantly smaller payloads. pycopg uses 6 as its default with documentation noting this choice.

**Classification:** TABLE STAKES — GeoJSON is the de facto geometry interchange format for web applications. Any spatial Python library without this is conspicuously incomplete.

**Complexity:** LOW — two `%s` params; options bitmask computed from two bool flags.

**Anti-gdf note:** `into="gdf"` is invalid — `as_geojson` returns text, not geometry. Must be added to `_SCALAR_HELPERS`.

---

### SPAT-V2-11 — `as_text` (ST_AsText)

**PostGIS signature:** `text ST_AsText(geometry geom)` / `text ST_AsText(geometry geom, integer maxdecimaldigits)`

**What it does:** Returns the Well-Known Text (WKT) representation. WKT is the standard text encoding for geometries — simpler than GeoJSON but less rich (no properties, no CRS in standard WKT).

**pycopg API shape:**

```python
def as_text(
    self,
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    max_decimal_digits: int | None = None,  # None = PostGIS default (all digits)
    columns: list[str] | None = None,
    where: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict]:  # "gdf" is invalid
```

Generated SQL (no max_decimal_digits): `SELECT <cols>, ST_AsText(t.<geom>) AS wkt FROM ...`
Generated SQL (with max_decimal_digits): `SELECT <cols>, ST_AsText(t.<geom>, %s) AS wkt FROM ...`

Result key is `wkt`. Must be added to `_SCALAR_HELPERS`.

**Classification:** TABLE STAKES — WKT is the universal geometry text format used in debugging, data export, and interoperability with other spatial tools.

**Complexity:** LOW — one optional `%s` param; trivial builder.

---

### SPAT-V2-12 — `as_mvt` (ST_AsMVT)

**PostGIS signatures (aggregate function):**
```
bytea ST_AsMVT(anyelement set row)
bytea ST_AsMVT(anyelement row, text name)
bytea ST_AsMVT(anyelement row, text name, integer extent)
bytea ST_AsMVT(anyelement row, text name, integer extent, text geom_name)
bytea ST_AsMVT(anyelement row, text name, integer extent, text geom_name, text feature_id_name)
```

**What it does:** Aggregate function returning a binary Mapbox Vector Tile representation of a set of rows. The input rows must already contain a geometry column in the tile's coordinate system (usually EPSG:3857 for web tiles). ST_AsMVT is an aggregate — it consumes all rows from a subquery that provides tile-space geometry (typically via ST_AsMVTGeom).

**Design challenge:** ST_AsMVT is fundamentally different from all other spatial helpers:
- It is an aggregate (consumes a full rowset)
- It requires the geometry to already be in tile coordinates (ST_AsMVTGeom preprocessing)
- It returns `bytea` (bytes), not rows
- The SQL shape is `SELECT ST_AsMVT(q.*, %s, %s, %s) FROM (<subquery>) AS q`

**pycopg API shape:**

```python
def as_mvt(
    self,
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    layer_name: str = "default",
    extent: int = 4096,
    tile_x: int,       # tile X coordinate (required)
    tile_y: int,       # tile Y coordinate (required)
    tile_z: int,       # tile zoom level (required)
    columns: list[str] | None = None,  # attribute columns to include
    where: str | None = None,
    feature_id_column: str | None = None,
) -> bytes:
```

Generated SQL (conceptually):
```sql
SELECT ST_AsMVT(q.*, %s, %s, 'geom_mvt', %s)
FROM (
    SELECT <columns>, ST_AsMVTGeom(
        ST_Transform(t.<geom>, 3857),
        ST_TileEnvelope(%s, %s, %s),
        %s
    ) AS geom_mvt
    FROM <schema>.<table> AS t
    [WHERE ...]
) AS q
WHERE q.geom_mvt IS NOT NULL
```

Params: `[layer_name, extent, feature_id_column, tile_z, tile_x, tile_y, extent]`

`tile_x`, `tile_y`, `tile_z` are coerced through `int()` (injection-safe). `layer_name` is a `%s` param. `feature_id_column` is identifier-validated if provided.

**Return shape:** `bytes` — the raw MVT binary blob. Callers serve this directly as `application/vnd.mapbox-vector-tile` HTTP response content.

**Classification:** DIFFERENTIATOR — MVT generation is a significant capability for map tile servers. Most PostGIS users write complex raw SQL for this. A high-level `as_mvt()` removes ~15 lines of boilerplate for each tile endpoint. However, it requires understanding of tile coordinate systems and is not universally needed.

**Complexity:** HIGH — most complex spatial helper. Requires composing `ST_AsMVTGeom` + `ST_TileEnvelope` + `ST_Transform` + `ST_AsMVT` aggregate in a subquery. The SQL structure is significantly more complex than all other builders. Must handle NULL geometry filtering.

**Dependency:** `into=` routing does not apply (returns `bytes`, not rows/gdf). Must NOT be added to `_SCALAR_HELPERS` — needs its own return type handling in the accessor.

---

## Workstream 2: API Completeness

### API-01 — Transaction Isolation Level Control

**psycopg3 API:** `connection.isolation_level` property accepts `psycopg.IsolationLevel` enum (READ_UNCOMMITTED=1, READ_COMMITTED=2, REPEATABLE_READ=3, SERIALIZABLE=4) or `None` (server default). Also available as `connection.set_isolation_level()` method. Can only be set before a transaction starts.

**What is missing:** The existing `db.transaction()` context manager does not accept an `isolation_level` parameter. Users who need SERIALIZABLE isolation for critical financial operations must manually set it on raw psycopg connections.

**pycopg high-level API shape:**

```python
# Extend db.transaction() to accept isolation_level
@contextmanager
def transaction(
    self,
    isolation_level: str | None = None,  # "read_committed", "repeatable_read", "serializable", None
) -> Iterator[psycopg.Connection]:
```

The `isolation_level` string is mapped to the `psycopg.IsolationLevel` enum inside the implementation. Using a string (not the enum directly) keeps the public API stable if psycopg3's enum changes. A whitelist of valid strings raises `ValueError` for invalid values before any DB round-trip.

Internally: `conn.isolation_level = psycopg.IsolationLevel[level.upper().replace("-", "_")]`

**Classification:** TABLE STAKES — any serious production application needs isolation level control. Without it, users must bypass the high-level API entirely for SERIALIZABLE transactions.

**Complexity:** LOW — adding one optional parameter to an existing context manager; enum lookup + validation.

**Dependency:** Needs both `Database.transaction()` and `AsyncDatabase.transaction()` updated (parity requirement).

---

### API-02 — Savepoints / Nested Transactions

**psycopg3 API:** `connection.transaction(savepoint_name=None, force_rollback=False)` — nested calls create SAVEPOINTs. The `savepoint_name` parameter names the savepoint; if `None`, one is auto-chosen. Exceptions inside a nested transaction block roll back only to the savepoint, not the whole outer transaction.

**What is missing:** The existing `db.transaction()` cannot be nested — calling it inside another `db.transaction()` reuses the outer connection but does not create a SAVEPOINT, so a failure in the inner block rolls back the entire outer transaction. Users need explicit savepoint naming for partial-rollback patterns.

**pycopg high-level API shape:**

```python
@contextmanager
def savepoint(
    self,
    name: str | None = None,        # savepoint name; auto-chosen if None
) -> Iterator[None]:
```

A separate `db.savepoint()` context manager is cleaner than overloading `db.transaction()`. Usage:

```python
with db.transaction():
    db.execute("INSERT INTO orders ...")
    with db.savepoint("after_order"):
        db.execute("INSERT INTO payments ...")
        # if this fails, only payments rolls back
```

Internally calls `conn.transaction(savepoint_name=name)` when inside a session. If called outside a session (no active connection), raises `RuntimeError` — savepoints require an enclosing transaction.

**Classification:** TABLE STAKES — savepoints are essential for partial-rollback patterns in multi-step workflows (e.g., try to insert, fall back on conflict without rolling back the parent transaction).

**Complexity:** MEDIUM — requires detecting whether a session connection is active; needs both sync and async variants; error message for misuse needs to be clear.

**Dependency:** Requires `db.session()` / `db.transaction()` — must guard against misuse outside a session.

---

### API-03 — Named Parameters (`:name` style)

**psycopg3 parameter style:** psycopg3 uses `%(name)s` for named parameters in `cursor.execute()`, not `:name`. The SQLAlchemy `text()` layer (used in `to_geodataframe`) already uses `:name` style. There is no native `:name` psycopg3 syntax — pycopg would need to translate.

**What is missing:** The current `db.execute(sql, params)` requires positional `%s` placeholders and a list/sequence. Users who want named params must translate manually or use raw psycopg3 with `%(name)s` dicts.

**pycopg high-level API shape (option 1 — recommended):**

Support `%(name)s` dict-style directly in `db.execute()`:

```python
# Already works in psycopg3 — just accept dict params
db.execute(
    "SELECT * FROM orders WHERE user_id = %(uid)s AND status = %(status)s",
    {"uid": 42, "status": "open"}
)
```

This requires zero new code — psycopg3's `cursor.execute()` already accepts both `Sequence` and `Mapping`. The enhancement is:
1. Document this explicitly (currently undocumented)
2. Ensure `execute_many`, `fetch_one`, `fetch_all` also accept dict params
3. Add a type annotation update: `params: Sequence | Mapping | None = None`

**Classification:** TABLE STAKES — named parameters are fundamental developer ergonomics. However, this is largely a documentation gap, not a missing implementation. The complexity is LOW (type annotation + docs + tests) rather than HIGH (full parser).

**Anti-feature note on `:name` translation:** Building a `:name` → `%(name)s` translator would be a medium-complexity parser that handles edge cases (colons in strings, type casts like `::text`). This is an anti-feature. Use `%(name)s` style instead — it is native to psycopg3 and unambiguous.

**Complexity:** LOW — type annotation update + explicit test coverage + documentation. No implementation changes needed.

---

### API-04 — Connection / Pool Health Checks

**psycopg_pool API:**
- `ConnectionPool.check()` — tests each connection; broken ones are replaced. Also available as `AsyncConnectionPool.check()` (async).
- `ConnectionPool.get_stats()` — returns a dict of pool metrics (request counts, queue depth, connection counts).
- `ConnectionPool.wait(timeout=30.0)` — blocks until pool is ready.

**What is missing:** pycopg does not expose pool health check or stats methods. Users cannot programmatically verify connection health or gather metrics for monitoring.

**pycopg high-level API shape — flat methods on `Database`:**

```python
def health_check(self) -> dict:
    """Check connection health and return pool stats.

    Returns
    -------
    dict
        Keys: pool_available (bool), pool_stats (dict from get_stats()),
        single_conn_ok (bool).
    """

def pool_stats(self) -> dict:
    """Return raw pool statistics dict from psycopg_pool.get_stats()."""
```

The `health_check()` method:
1. If a pool is configured: calls `pool.check()` (verifies connections), then `pool.get_stats()`
2. If no pool (direct connection): attempts a `SELECT 1` on a fresh connection
3. Returns a structured dict with `pool_available`, `pool_stats`, `single_conn_ok` keys

**Classification:** TABLE STAKES — health check endpoints are required by every production deployment (Kubernetes liveness/readiness probes, monitoring dashboards). A library without health check support forces users to bolt on raw psycopg3 code.

**Complexity:** MEDIUM — must handle both pool and non-pool configurations; needs async parity.

---

### API-05 — Structured Logging

**Current state:** The codebase has `logger = logging.getLogger(__name__)` in `database.py` with a single `logger.warning(...)` call for the session close failure path. There is no structured event logging for normal operations.

**What structured logging means for pycopg:** Emitting machine-readable log records for:
- Connection events (pool checkout, connection failure, retry)
- Long-running queries (queries exceeding a configurable threshold)
- Transaction lifecycle (begin, commit, rollback with duration)
- ETL run lifecycle (start, success, failure with row counts)

**pycopg high-level API shape:** Use the existing `logging.getLogger(__name__)` infrastructure — no new logging library dependency. Add `logging.DEBUG`-level records at key execution points:

```python
# In execute():
logger.debug("execute sql=%.200s params_count=%d", sql, len(params or []))

# In transaction():
logger.debug("transaction begin isolation=%s", isolation_level)
logger.debug("transaction commit duration_ms=%.1f", elapsed * 1000)

# In ETL run():
logger.info("etl pipeline=%s mode=%s rows=%d duration_ms=%.1f", ...)
```

**Classification:** DIFFERENTIATOR (not TABLE STAKES) — structured logging is valuable but not blocking. Users can add their own logging around `db.execute()` calls. However, instrumenting the library itself is significantly more useful because it covers internals (retry attempts, pool events) that users cannot observe from outside.

**Complexity:** LOW-MEDIUM — adding `logger.debug/info` calls at the right points in `database.py`, `etl.py`, and the pool wrapper. No new dependencies. Main complexity is deciding which events to log at which level without producing noise.

**Note:** Structured logging with explicit `extra={}` dicts for machine-readable records (as opposed to format-string messages) is a DIFFERENTIATOR-tier enhancement, not table stakes. Start with format-string logging at DEBUG level; structured extras can be a 1.x enhancement.

---

## Workstream 3: API Freeze

### FREEZE-01 — Consistency / Homogenization Pass

**What this means:** An aggressive review of the entire public surface for inconsistencies in:
- Parameter naming (e.g., `time_column` vs `column` vs `col`)
- Parameter ordering across similar methods
- Return shapes for analogous methods
- Error message formats

**Known inconsistencies identified from codebase reading:**
- `db.spatial.*` uses `into="rows"/"gdf"` but `db.timescale.*` query helpers use `into="df"/"rows"` — the value `"df"` vs `"gdf"` is inconsistent for the GeoDataFrame case (timescale returns DataFrame, spatial returns GeoDataFrame, so technically different types, but the param value naming is confusing).
- `db.schema.*` uses `schema="public"` but some methods have `schema: str | None = None` (optional vs required-with-default).
- The `where=` parameter in spatial accepts raw SQL fragments; `where=` in CRUD methods accepts a dict — same name, different semantics.

**API shape:** This is not a new method — it is a review phase that produces breaking renames served through the existing `@deprecated_alias` + DeprecationWarning + MIGRATION cycle (same mechanism as v0.6→v0.7 alias removal).

**Classification:** TABLE STAKES — an incoherent API surface at 1.0 becomes permanent technical debt under SemVer. This is the last opportunity to fix naming before the freeze.

**Complexity:** MEDIUM — requires systematic review; breaking changes need migration table.

---

### FREEZE-02 — SemVer Policy + Deprecation Policy Document

**What this means:** A formal written policy (in docs, not just CHANGELOG entries) specifying:
- What constitutes a breaking change in pycopg (removal of public method, parameter rename, return type change, exception class change)
- Deprecation cycle: minimum one minor version warning before removal
- Version guarantees: patch = bug fix, minor = additive non-breaking, major = breaking changes
- How to deprecate: `DeprecationWarning` via `@deprecated_alias` + stacklevel=3, MIGRATION section in CHANGELOG

**Form:** A `docs/stability.md` page published to ReadTheDocs, referenced from README.

**Classification:** TABLE STAKES — without a written policy, users cannot rely on API stability. A 1.0 version tag without a stability guarantee is meaningless.

**Complexity:** LOW — primarily documentation; the enforcement mechanism (DeprecationWarning) already exists.

---

### FREEZE-03 — mypy Strict Mode Blocking

**Current state:** mypy is configured in `pyproject.toml` with `disallow_untyped_defs = false` and `check_untyped_defs = true`. It runs in CI but is `continue-on-error` (non-blocking). Several `ignore_missing_imports = true` overrides are used for psycopg, geopandas, geoalchemy2, shapely, tenacity, sqlalchemy.

**What strict mode enables:** `--strict` adds: `disallow_any_generics`, `disallow_subclassing_any`, `disallow_untyped_calls`, `disallow_untyped_defs`, `disallow_incomplete_defs`, `disallow_untyped_decorators`, `warn_redundant_casts`, `warn_unused_ignores`.

**Migration path:** The `ignore_missing_imports` overrides for third-party libraries without stubs are acceptable under strict mode — they are explicitly scoped. The main cost is annotating all function signatures (adding return types and param types to all currently-untyped functions).

**Classification:** TABLE STAKES — `py.typed` exists but mypy is non-blocking. A library advertising `py.typed` that doesn't pass its own type checker is misleading. Making mypy strict + blocking is the correct 1.0 commitment.

**Complexity:** HIGH — requires annotating all untyped functions in the codebase; fixing all mypy strict errors; some complex return types (Union types, generic types) may require significant annotation work.

**Dependency:** Must be done after the homogenization pass (FREEZE-01) to avoid re-annotating renamed methods.

---

### FREEZE-04 — py.typed Completeness Verification

**Current state:** `pycopg/py.typed` exists (marker file). This means pycopg is typed. However, completeness (all modules annotated) has not been systematically verified.

**What this means:** Run mypy in strict mode over the full package and confirm zero errors. This is the verification step for FREEZE-03 — once mypy strict passes, py.typed completeness is confirmed.

**Classification:** TABLE STAKES — pairs with FREEZE-03. The marker file without strict-mode compliance is misleading to type-checker users.

**Complexity:** LOW (as a distinct deliverable — the work is in FREEZE-03; this is the gate check).

---

## Feature Dependencies

```
SPAT-V2-01 union (2-geom)
    └──same builder pattern as──> existing build_buffer_sql, build_transform_sql

SPAT-V2-02 simplify
    └──independent; two SQL variants (ST_Simplify / ST_SimplifyPreserveTopology)

SPAT-V2-03 convex_hull
    └──simplest builder; no deps

SPAT-V2-04 make_valid
    └──independent; params string needs whitelist guard

SPAT-V2-05 difference
    └──same shape as SPAT-V2-01 (two-column, same table)

SPAT-V2-06 intersection
    └──same shape as SPAT-V2-05; can share builder function

SPAT-V2-07 collect_geometries (ST_Collect agg)
    └──first aggregate method; establishes GROUP BY builder pattern
    └──enables──> SPAT-V2-08, SPAT-V2-09 (same aggregate infrastructure)

SPAT-V2-08 union_aggregate (ST_Union agg)
    └──requires──> SPAT-V2-07 aggregate builder pattern established

SPAT-V2-09 extent (ST_Extent agg)
    └──requires──> SPAT-V2-07 aggregate builder pattern
    └──has extra branch: into="gdf" needs ST_SetSRID cast

SPAT-V2-10 as_geojson
    └──independent; must be added to _SCALAR_HELPERS

SPAT-V2-11 as_text
    └──independent; must be added to _SCALAR_HELPERS

SPAT-V2-12 as_mvt
    └──most complex; needs subquery wrapping with ST_AsMVTGeom + ST_TileEnvelope
    └──returns bytes, NOT routed through _run() / into= machinery

API-01 isolation_level
    └──extends existing db.transaction()

API-02 savepoints
    └──requires db.session() to be active (guard: RuntimeError if outside session)

API-03 named params
    └──documentation + type annotation only; no code change

API-04 health_check
    └──wraps psycopg_pool.check() / get_stats()

API-05 structured logging
    └──extends existing logger in database.py, etl.py

FREEZE-01 homogenization
    └──must precede──> FREEZE-03 mypy strict (avoid re-annotating renamed methods)

FREEZE-03 mypy strict
    └──must precede──> FREEZE-04 py.typed verification (strict is the work; verification is the gate)
```

### Dependency Notes

- **Processing helpers (SPAT-V2-01..06):** All independent of each other; best phased as two sub-groups: (01 union, 05 difference, 06 intersection) share the two-column builder shape and should go together; (02 simplify, 03 convex_hull, 04 make_valid) are each independent but logically form a "geometry repair/analysis" group.
- **Aggregate helpers (SPAT-V2-07..09):** SPAT-V2-07 must come first as it establishes the GROUP BY aggregate builder pattern. SPAT-V2-08 and SPAT-V2-09 can follow in the same phase.
- **Serialization helpers (SPAT-V2-10..12):** SPAT-V2-10 and SPAT-V2-11 are simple and go together. SPAT-V2-12 (`as_mvt`) is the hardest spatial feature and should be its own phase or sub-task.
- **`as_mvt` isolation:** ST_AsMVT is the only method that returns `bytes` and that composes two PostGIS functions in a subquery. It should NOT share implementation code with other builders — its complexity warrants a dedicated builder function.

---

## Anti-Features

| Anti-Feature | Why Requested | Why Problematic | Alternative |
|--------------|---------------|-----------------|-------------|
| **`:name` parameter style translation** | Familiar from other ORMs | Building a `:name` → `%(name)s` translator introduces a parser that fails on edge cases (colons in strings, PostgreSQL `::text` casts, etc.) | Document `%(name)s` dict style — it's native to psycopg3 and unambiguous |
| **`gridSize` parameter in `difference`/`intersection`** | Advanced precision control | Requires GEOS 3.9.0+; edge case; exposing it in the high-level API bloats signatures for 99% of users who never need it | `db.execute("SELECT ST_Difference(a, b, %s)", [grid_size])` |
| **`ST_Union` array form** | Convenient for pre-loaded lists | Adds a third Union variant; the two-column and aggregate forms cover all table-query use cases | Build array literal in raw `db.execute()` |
| **`ST_AsMVT` with row-level preprocessing control** | Tile server flexibility | Exposing all ST_AsMVTGeom parameters (clip, extent per-geom) makes the API near-SQL complexity; the defaults (clip=true, extent=4096) cover standard tile servers | Use `db.execute()` for non-standard tile configurations |
| **Global `logging.basicConfig()` call** | Easy to add | Side effect on user's logging configuration — never acceptable in a library | Only `logging.getLogger(__name__)`; never `basicConfig()` |
| **Raster support (ST_Union for rasters, etc.)** | PostGIS handles rasters too | Raster API surface is large and distinct from geometry; 1.0 scope is locked; adding it would require a new accessor or major spatial.py expansion | Explicitly deferred to post-1.0 (`db.raster.*` in 1.x) |
| **`db.spatial.aggregate_by_sql()`** | Generic aggregate escape hatch | Defeats the purpose of the high-level API; each aggregate method provides validated, injection-safe SQL | Named aggregate methods (SPAT-V2-07..09) cover the main cases |
| **mypy strict with `warn_unused_ignores` before stubs exist** | Maximal strictness | `ignore_missing_imports` for geopandas/shapely is necessary until stubs are published; `warn_unused_ignores` would fire when those stubs are added | Keep `warn_unused_ignores = false` until third-party stubs stabilize |

---

## MVP Definition (v1.0.0)

### Must Ship (Table Stakes — block 1.0 if absent)

**Spatial V2:**
- SPAT-V2-01 `union` (2-geom form) — fundamental
- SPAT-V2-02 `simplify` — fundamental, safe topology default
- SPAT-V2-03 `convex_hull` — trivial but expected
- SPAT-V2-04 `make_valid` — essential for production data pipelines
- SPAT-V2-05 `difference` — set algebra, fundamental
- SPAT-V2-06 `intersection` — set algebra, fundamental
- SPAT-V2-07 `collect_geometries` (ST_Collect aggregate) — most common aggregate use case
- SPAT-V2-08 `union_aggregate` (ST_Union aggregate) — most important aggregate operation
- SPAT-V2-09 `extent` (ST_Extent aggregate) — universal spatial inspection
- SPAT-V2-10 `as_geojson` — universal web API serialization
- SPAT-V2-11 `as_text` — universal WKT serialization

**API Completeness:**
- API-01 transaction isolation level
- API-02 savepoints
- API-03 named params (documentation + type annotation)
- API-04 health check

**Freeze:**
- FREEZE-01 homogenization pass
- FREEZE-02 SemVer/deprecation policy doc
- FREEZE-03 mypy strict blocking
- FREEZE-04 py.typed verification

### Should Ship (Differentiators — high value, reasonable scope)

- SPAT-V2-12 `as_mvt` — complex but high-value for tile servers
- API-05 structured logging — low-cost DX improvement

### Explicitly Deferred to 1.x

- Raster support (ST_Union for rasters, ST_Band, etc.)
- `gridSize` precision parameters on overlay functions
- TSDB-F, ETL-INC-F, CRUD-F, INTRO-F follow-ups (all locked out per cadrage)
- Cross-DB ETL sources/sinks
- Dynamic pool sizing API

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority | Classification |
|---------|------------|---------------------|----------|----------------|
| SPAT-V2-01 `union` (2-geom) | HIGH | LOW | P1 | Table stakes |
| SPAT-V2-02 `simplify` | HIGH | LOW | P1 | Table stakes |
| SPAT-V2-03 `convex_hull` | MEDIUM | LOW | P1 | Table stakes |
| SPAT-V2-04 `make_valid` | HIGH | LOW | P1 | Table stakes |
| SPAT-V2-05 `difference` | HIGH | LOW | P1 | Table stakes |
| SPAT-V2-06 `intersection` | HIGH | LOW | P1 | Table stakes |
| SPAT-V2-07 `collect_geometries` | HIGH | MEDIUM | P1 | Table stakes |
| SPAT-V2-08 `union_aggregate` | HIGH | MEDIUM | P1 | Table stakes |
| SPAT-V2-09 `extent` | HIGH | MEDIUM | P1 | Table stakes |
| SPAT-V2-10 `as_geojson` | HIGH | LOW | P1 | Table stakes |
| SPAT-V2-11 `as_text` | MEDIUM | LOW | P1 | Table stakes |
| SPAT-V2-12 `as_mvt` | MEDIUM | HIGH | P2 | Differentiator |
| API-01 isolation level | HIGH | LOW | P1 | Table stakes |
| API-02 savepoints | HIGH | MEDIUM | P1 | Table stakes |
| API-03 named params | MEDIUM | LOW | P1 | Table stakes |
| API-04 health check | HIGH | MEDIUM | P1 | Table stakes |
| API-05 structured logging | MEDIUM | LOW | P2 | Differentiator |
| FREEZE-01 homogenization | HIGH | MEDIUM | P1 | Table stakes |
| FREEZE-02 SemVer policy doc | HIGH | LOW | P1 | Table stakes |
| FREEZE-03 mypy strict | HIGH | HIGH | P1 | Table stakes |
| FREEZE-04 py.typed verify | LOW | LOW | P1 | Table stakes |

**Priority key:**
- P1: Must have for milestone to be coherent as a "1.0 release"
- P2: Strong value-add, include when scope allows

---

## Sources

- [PostGIS ST_Union](https://postgis.net/docs/ST_Union.html) — 2-geom and aggregate forms, gridSize parameter
- [PostGIS ST_Simplify](https://postgis.net/docs/ST_Simplify.html) — tolerance, preserveCollapsed parameters
- [PostGIS ST_SimplifyPreserveTopology](https://postgis.net/docs/ST_SimplifyPreserveTopology.html) — topology-safe variant
- [PostGIS ST_MakeValid](https://postgis.net/docs/ST_MakeValid.html) — method= and keepcollapsed= params string
- [PostGIS ST_Difference](https://postgis.net/docs/ST_Difference.html) — geomA, geomB, gridSize signatures
- [PostGIS ST_Intersection](https://postgis.net/docs/ST_Intersection.html) — geometry and geography overloads
- [PostGIS ST_Collect](https://postgis.net/docs/ST_Collect.html) — aggregate and 2-geom forms
- [PostGIS ST_Extent](https://postgis.net/docs/ST_Extent.html) — box2d aggregate return type
- [PostGIS ST_AsGeoJSON](https://postgis.net/docs/ST_AsGeoJSON.html) — maxdecimaldigits, options bitmask
- [PostGIS ST_AsMVT](https://postgis.net/docs/ST_AsMVT.html) — aggregate bytea return, all 5 overloads
- [psycopg3 transaction management](https://www.psycopg.org/psycopg3/docs/basic/transactions.html) — isolation levels, nested transactions/savepoints
- [psycopg3 top-level objects](https://access.crunchydata.com/documentation/psycopg3/3.1.9/api/objects.html) — IsolationLevel enum values
- [psycopg_pool API](https://doc.rockdata.net/psycopg/api/pool/) — check(), get_stats(), wait() methods
- [psycopg3 parameter passing](https://www.psycopg.org/psycopg3/docs/basic/params.html) — %(name)s dict style
- [mypy strict mode configuration](https://mypy.readthedocs.io/en/stable/config_file.html) — strict flag details
- pycopg codebase: `pycopg/spatial.py` — existing builder pattern, _SCALAR_HELPERS, _check_into, _to_named_binds, SpatialAccessor, AsyncSpatialAccessor (read directly)
- pycopg codebase: `pycopg/base.py` — QueryMixin, SessionMixin, DatabaseBase (read directly)
- pycopg codebase: `pycopg/database.py` — transaction(), session(), in_session, isolation level absence confirmed
- pycopg project: `.planning/PROJECT.md` — locked scope decisions, v1.0.0 cadrage

---

*Feature landscape for: pycopg v1.0.0 Spatial v2 + API Freeze*
*Researched: 2026-06-27*
*Confidence: HIGH — PostGIS function signatures verified from postgis.net/docs official pages;
psycopg3 transaction API confirmed from official docs; existing codebase patterns read directly
from source; locked scope boundary from PROJECT.md cadrage decision.*
