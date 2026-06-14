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
absent, `ExtensionNotAvailable` is raised before any query runs.

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

Scalar helpers (`area`, `perimeter`, `distance`, `centroid`) only support `into="rows"`;
passing `into="gdf"` raises `ValueError` because their result columns are not geometry.

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

## Security

All identifier arguments (table, schema, geometry column, `columns=` entries, `ref=`
table/column) pass through `validate_identifiers` before any SQL is assembled. User
values (coordinates, WKT, GeoJSON, distances, `k`, `to_srid`) are always emitted as
`%s` placeholders. The only directly interpolated value is `srid`, which is coerced
to `int` before interpolation.
