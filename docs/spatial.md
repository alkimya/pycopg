# Spatial Helpers

pycopg provides a `db.spatial.*` (and `async_db.spatial.*`) accessor namespace with 11
spatial helpers built on PostGIS. Each helper is a pure SQL builder that returns
parameterized queries — no string interpolation of user values.

## Access Pattern

The accessor is exposed as a property on `Database` and `AsyncDatabase`:

```python
from pycopg import Database

db = Database.from_env()

# Sync: db.spatial is initialized lazily on first access
rows = db.spatial.contains("parcels", geom="geometry", point=(-122.4, 37.8))
```

```python
from pycopg import AsyncDatabase

async_db = AsyncDatabase.from_env()

# Async: async_db.spatial mirrors the sync API with awaited methods
rows = await async_db.spatial.contains("parcels", geom="geometry", point=(-122.4, 37.8))
```

The accessor verifies that PostGIS is installed on first access. If the extension is
absent, `ExtensionNotAvailableError` is raised before any query runs.

## Output: the `into=` Parameter

All helpers accept an `into=` keyword argument controlling the return type:

| `into=` value | Return type | Notes |
|---------------|-------------|-------|
| `"rows"` (default) | `list[dict]` | One dict per row |
| `"gdf"` | `GeoDataFrame` | Requires `pip install pycopg[geo]` |

```python
# list of dicts (default)
rows = db.spatial.dwithin("parcels", point=(-122.4, 37.8), distance=500)

# GeoDataFrame
gdf = db.spatial.dwithin("parcels", point=(-122.4, 37.8), distance=500, into="gdf")
```

Scalar helpers (`area`, `perimeter`, `distance`, `centroid`, `length`, `is_valid`,
`is_valid_reason`) only support `into="rows"`; passing `into="gdf"` raises `ValueError`
because their result columns are not geometry.

## Geometry Input Forms

Every helper that takes a reference geometry accepts exactly one of four forms:

| Parameter | Type | Example |
|-----------|------|---------|
| `point=(x, y)` | `tuple[float, float]` | `point=(-122.4, 37.8)` |
| `wkt="..."` | `str` | `wkt="POINT(-122.4 37.8)"` |
| `geojson={...}` | `dict` | `geojson={"type": "Point", "coordinates": [-122.4, 37.8]}` |
| `ref=(table, col)` | `tuple[str, str]` | `ref=("zones", "geometry")` |

Exactly one must be supplied; providing two or none raises `ValueError`. The `srid=`
keyword sets the SRID for `point=`, `wkt=`, and `geojson=` forms (default `4326`).

```python
# point form
rows = db.spatial.contains("parcels", geom="geometry", point=(-122.4, 37.8), srid=4326)

# WKT form
rows = db.spatial.intersects(
    "parcels",
    geom="geometry",
    wkt="POLYGON((-122.5 37.7, -122.3 37.7, -122.3 37.9, -122.5 37.9, -122.5 37.7))",
)

# GeoJSON form
rows = db.spatial.dwithin(
    "parcels",
    geom="geometry",
    geojson={"type": "Point", "coordinates": [-122.4, 37.8]},
    distance=1000,
)

# ref form — uses EXISTS subquery against another table's geometry column
rows = db.spatial.contains("parcels", geom="geometry", ref=("zones", "boundary"))
```

## Distance Units: the `unit=` Parameter

Helpers that deal with distances or areas accept `unit=`:

| `unit=` value | Behaviour |
|---------------|-----------|
| `"m"` (default) | Distances in metres, areas in m², via `::geography` cast |
| `"srid"` | Native units of the geometry's SRID (degrees for EPSG:4326) |

```python
# Metres (default)
rows = db.spatial.dwithin("parcels", geom="geometry", point=(-122.4, 37.8), distance=1000, unit="m")

# Native SRID units
rows = db.spatial.area("parcels", geom="geometry", unit="srid")
```

## Helper Reference

### contains

Selects rows whose geometry contains the input geometry (ST_Contains).

```python
rows = db.spatial.contains(
    "parcels",
    geom="geometry",
    point=(-122.4, 37.8),
    srid=4326,
    columns=["id", "name"],
)
```

### within

Selects rows from `left_table` whose geometry is within the geometry of `right_table`
(two-table ST_Within join).

```python
rows = db.spatial.within(
    left_table="buildings",
    left_geom="geometry",
    right_table="zones",
    right_geom="boundary",
    columns=["id", "name"],
)
```

### intersects

Selects rows whose geometry intersects the input geometry (ST_Intersects predicate).

```python
rows = db.spatial.intersects(
    "parcels",
    geom="geometry",
    wkt="POLYGON((-122.5 37.7, -122.3 37.7, -122.3 37.9, -122.5 37.9, -122.5 37.7))",
    into="gdf",
)
```

### dwithin

Selects rows within a given distance of the input geometry (ST_DWithin filter).

```python
rows = db.spatial.dwithin(
    "parcels",
    geom="geometry",
    point=(-122.4, 37.8),
    distance=1000,
    unit="m",
    columns=["id", "name"],
)
```

### distance

Selects rows with a computed `distance` column (scalar result; `into="gdf"` forbidden).

```python
rows = db.spatial.distance(
    "parcels",
    geom="geometry",
    point=(-122.4, 37.8),
    unit="m",
    columns=["id", "name"],
    order_by="distance",
    limit=20,
)
# Each row has a "distance" key with the computed distance.
```

### nearest

Selects the k nearest rows to the input geometry using PostGIS KNN ordering.

```python
rows = db.spatial.nearest(
    "parcels",
    geom="geometry",
    point=(-122.4, 37.8),
    k=10,
    columns=["id", "name"],
)
```

### area

Selects rows with a computed `area` column (scalar result; `into="gdf"` forbidden).

```python
rows = db.spatial.area(
    "parcels",
    geom="geometry",
    unit="m",
    columns=["id", "name"],
    order_by="area",
    limit=10,
)
# Each row has an "area" key with the computed area in square metres.
```

### perimeter

Selects rows with a computed `perimeter` column (scalar result; `into="gdf"` forbidden).

```python
rows = db.spatial.perimeter(
    "parcels",
    geom="geometry",
    unit="m",
    columns=["id", "name"],
)
# Each row has a "perimeter" key with the computed perimeter in metres.
```

### centroid

Selects rows with computed centroid coordinates (scalar result; `into="gdf"` forbidden).
Result columns are `centroid_x` and `centroid_y` (not `lon`/`lat`).

```python
rows = db.spatial.centroid(
    "parcels",
    geom="geometry",
    columns=["id", "name"],
)
# Each row has "centroid_x" and "centroid_y" keys.
```

### buffer

Selects rows with a `buffer` geometry column (valid for `into="gdf"`).

```python
rows = db.spatial.buffer(
    "locations",
    geom="geometry",
    distance=100,
    unit="m",
    columns=["id", "name"],
    into="gdf",
)
# Result GeoDataFrame has a "buffer" geometry column.
```

### transform

Selects rows with their geometry transformed to another SRID, as a
`geometry_transformed` column (valid for `into="gdf"`).

```python
rows = db.spatial.transform(
    "parcels",
    geom="geometry",
    to_srid=3857,
    into="gdf",
)
# Result GeoDataFrame has a "geometry_transformed" geometry column.
```

### Fixed-Precision Overlays: `grid_size=`

The overlay helpers `union`, `difference`, and `intersection` accept a keyword-only
`grid_size` parameter (`float | None`, default `None`) for fixed-precision (snap-rounding)
overlay computation:

```python
rows = db.spatial.union(
    "parcels",
    geom="geometry",
    other_geom="geometry_b",
    grid_size=0.001,
)
```

When set, `grid_size` becomes the 3rd argument of the underlying PostGIS overlay
function (`ST_Union(a, b, grid_size)`, likewise `ST_Difference`/`ST_Intersection`) and is
bound as a `%s` parameter (pure passthrough — no client-side range validation, since
every float, including `0` and negative values, is meaningful to PostGIS). **Requires
PostGIS >= 3.1 / GEOS >= 3.9**; on older servers PostGIS raises a native error. The
default `grid_size=None` path emits the exact pre-existing 2-argument SQL — byte-identical
to versions of pycopg without this parameter.

### length

Selects rows with a computed `length` column (scalar result; `into="gdf"` forbidden).
Mirrors `area`/`perimeter` — same `unit=` parameter.

```python
rows = db.spatial.length(
    "roads",
    geom="geometry",
    unit="m",
    columns=["id", "name"],
)
# Each row has a "length" key with the computed length in metres.
```

`ST_Length` returns `0` for non-linear geometries (polygons, points) — it only measures
the length of `LINESTRING`/`MULTILINESTRING` geometries.

### is_valid

Selects rows with a computed boolean `is_valid` column (scalar result; `into="gdf"`
forbidden).

```python
rows = db.spatial.is_valid("parcels", geom="geometry", columns=["id"])
# Each row has an "is_valid" key (True/False) per OGC validity rules.
```

### is_valid_reason

Selects rows with a computed text `is_valid_reason` column describing why a geometry is
invalid (scalar result; `into="gdf"` forbidden). Complements `make_valid` — use
`is_valid`/`is_valid_reason` to diagnose, `make_valid` to repair.

```python
rows = db.spatial.is_valid_reason("parcels", geom="geometry", columns=["id"])
# Each row has an "is_valid_reason" key, e.g. "Self-intersection at ...".
```

### envelope

Selects rows with an `envelope` geometry column — the per-row minimum bounding
rectangle (valid for `into="gdf"`).

```python
rows = db.spatial.envelope(
    "parcels",
    geom="geometry",
    into="gdf",
)
# Result GeoDataFrame has an "envelope" geometry column.
```

### point_on_surface

Selects rows with a `point_on_surface` geometry column — a guaranteed-inside
representative point (valid for `into="gdf"`), suited for map labels/markers. Unlike
`centroid` (which returns scalar `centroid_x`/`centroid_y` coordinates and is never
guaranteed to lie inside a concave geometry), `point_on_surface` returns a real geometry
column and always lies on the surface of the input geometry.

```python
rows = db.spatial.point_on_surface(
    "parcels",
    geom="geometry",
    into="gdf",
)
# Result GeoDataFrame has a "point_on_surface" geometry column, guaranteed
# to lie inside/on each polygon (unlike centroid, which can fall outside
# a concave shape).
```

### overlaps / touches / crosses / disjoint

Four DE-9IM predicates completing the `contains`/`intersects`/`within`/`dwithin`
predicate family. Each mechanically mirrors `intersects`: same four geometry input
forms (`point=`/`wkt=`/`geojson=`/`ref=`), same `ref=` EXISTS-subquery handling, same
`into="rows"/"gdf"` support (row-filter predicates — `into="gdf"` uses the table's own
geometry column, not a computed column).

```python
# overlaps — ST_Overlaps
rows = db.spatial.overlaps("parcels", geom="geometry", point=(-122.4, 37.8))

# touches — ST_Touches
rows = db.spatial.touches("parcels", geom="geometry", ref=("zones", "boundary"))

# crosses — ST_Crosses
rows = db.spatial.crosses(
    "roads", geom="geometry",
    wkt="LINESTRING(-122.5 37.7, -122.3 37.9)",
)

# disjoint — ST_Disjoint
rows = db.spatial.disjoint("parcels", geom="geometry", point=(-122.4, 37.8))
```

**`disjoint` footgun:** the `ref=` form means "EXISTS a ref row disjoint from t" — true
as soon as **any** row in the reference table is disjoint from the current row (near-
always true for a sparse reference table). It does **not** mean "disjoint from all"
reference rows. This is the same uniform EXISTS quantifier used by every other
predicate's `ref=` form (kept mechanically consistent rather than special-cased), so
read the result semantics carefully when using `ref=` with `disjoint`.

**`disjoint` performance note:** `ST_Disjoint` does not use indexes ("This function call
does not use indexes" — postgis.net). For large indexed tables, prefer a negated
`NOT ST_Intersects` predicate instead — e.g. via the `filter=` escape hatch — for an
indexable, more performant equivalent.

## Async Usage

All 11 helpers are available on `async_db.spatial` with the same signatures — prefix the
call with `await`:

```python
from pycopg import AsyncDatabase

async_db = AsyncDatabase.from_env()

rows = await async_db.spatial.contains(
    "parcels", geom="geometry", point=(-122.4, 37.8), columns=["id", "name"]
)

gdf = await async_db.spatial.dwithin(
    "parcels", geom="geometry", point=(-122.4, 37.8), distance=1000, into="gdf"
)
```

## Serialization Helpers (Phase 44 / v1.0)

Three serialization helpers on `db.spatial.*` convert stored geometries to portable
formats. All use born-clean `filter=` (no deprecated `where=`).

### as_geojson

Returns rows with a ``geojson`` key containing the geometry as a GeoJSON string.
`max_decimal_digits=6` by default (web-payload precision). Set `include_bbox=True`
or `include_crs=True` to embed bounding-box / CRS metadata in each GeoJSON object.
`into="gdf"` is forbidden (raises ``ValueError``) because the result is already a
string, not a geometry column.

```python
rows = db.spatial.as_geojson(
    "parcels",
    geom="geometry",
    columns=["id", "name"],
    max_decimal_digits=6,
)
# Each row: {"id": 1, "name": "Lot A", "geojson": '{"type":"Polygon",...}'}
```

### as_text

Returns rows with a ``wkt`` key containing the geometry as a WKT string.
`max_decimal_digits=None` by default (full precision, no silent truncation).
`into="gdf"` is forbidden. Setting `max_decimal_digits=` emits the two-arg
`ST_AsText(geom, ndigits)` form, which requires PostGIS >= 3.1; the default
(`None`, full precision, one-arg form) works on all PostGIS 3.0+ servers.

```python
rows = db.spatial.as_text(
    "parcels",
    geom="geometry",
    columns=["id"],
)
# Each row: {"id": 1, "wkt": "POLYGON((0 0,1 0,1 1,0 1,0 0))"}
```

### as_mvt

Returns a Mapbox Vector Tile as raw ``bytes``. Uses the
``ST_Transform → ST_AsMVTGeom(ST_TileEnvelope(z, x, y)) → ST_AsMVT`` pipeline.
An empty tile (no features inside the requested tile envelope) returns ``b""``.
Requires PostGIS ≥ 3.0 (the pycopg floor). `tile_z`, `tile_x`, `tile_y` are
required keyword arguments.

```python
# Tile endpoint shape: serve /tiles/{z}/{x}/{y}.mvt
tile_bytes = db.spatial.as_mvt(
    "roads",
    geom="geometry",
    tile_z=14,
    tile_x=8192,
    tile_y=5464,
    layer_name="roads",
    columns=["id", "name", "highway"],
)

# In a web framework (e.g. FastAPI):
# from fastapi import Response
# return Response(content=tile_bytes, media_type="application/vnd.mapbox-vector-tile")
```

If the stored geometry has an unknown SRID, rescue it with `srid=`:

```python
tile_bytes = db.spatial.as_mvt(
    "parcels",
    geom="geometry",
    tile_z=14,
    tile_x=8192,
    tile_y=5464,
    srid=4326,  # inject ST_SetSRID before ST_Transform
)
```

## Security

All identifier arguments (table, schema, geometry column, `columns=` entries, `ref=`
table/column) pass through `validate_identifiers` before any SQL is assembled. User
values (coordinates, WKT, GeoJSON, distances, `k`, `to_srid`) are always emitted as
`%s` placeholders. The only directly interpolated value is `srid`, which is coerced
to `int` before interpolation.
