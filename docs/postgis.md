# PostGIS Support

pycopg provides first-class support for PostGIS spatial operations with GeoPandas integration.

## Prerequisites

1. PostGIS extension installed on your PostgreSQL server
2. GeoPandas installed: `pip install pycopg[geo]`

## Setup

```python
from pycopg import Database

db = Database.from_env()

# Enable PostGIS extension
db.create_extension("postgis")

# Verify installation
if db.has_extension("postgis"):
    print("PostGIS is ready")
```

## Creating Spatial Tables

### From GeoDataFrame

```python
import geopandas as gpd

# Load spatial data
gdf = gpd.read_file("parcels.geojson")

# Create table with spatial index
db.from_geodataframe(
    gdf,
    "parcels",
    primary_key="id",
    spatial_index=True
)
```

### Options

```python
db.from_geodataframe(
    gdf,
    "parcels",
    schema="geo",            # Target schema
    if_exists="replace",     # 'fail', 'replace', 'append'
    primary_key="id",        # Set primary key
    spatial_index=True,      # Create GIST spatial index
    geometry_column="geom",  # Geometry column name
    srid=4326,               # Override SRID
)
```

## Reading Spatial Data

### Full Table

```python
gdf = db.to_geodataframe("parcels")
print(gdf.crs)  # EPSG:4326
print(gdf.geometry.head())
```

### With SQL Query

```python
# Envelope filter — ST_MakeEnvelope is not covered by a db.spatial.* helper;
# use to_geodataframe(sql=...) directly for bounding-box queries.
gdf = db.to_geodataframe(
    sql="""
        SELECT * FROM parcels
        WHERE ST_Within(
            geometry,
            ST_MakeEnvelope(-122.5, 37.7, -122.3, 37.9, 4326)
        )
    """
)

# Distance filter — db.spatial.dwithin with into="gdf" for GeoDataFrame output
gdf = db.spatial.dwithin(
    "parcels",
    point=(-122.4, 37.8),
    distance=1000,
    into="gdf",
)
```

## Spatial Indexes

### Create GIST Index

```python
# Create spatial index
db.create_spatial_index("parcels", "geometry")

# With custom name
db.create_spatial_index("parcels", "geometry", name="idx_parcels_geom")

# On specific schema
db.create_spatial_index("parcels", "geometry", schema="geo")
```

### Using Regular Index API

```python
# GIST index for geometry
db.create_index("parcels", "geometry", method="gist")

# GIN index for JSONB properties
db.create_index("parcels", "properties", method="gin")
```

## Listing Geometry Columns

```python
# All geometry columns
columns = db.list_geometry_columns()
# [
#     {
#         'schema': 'public',
#         'table_name': 'parcels',
#         'column_name': 'geometry',
#         'dimensions': 2,
#         'srid': 4326,
#         'geometry_type': 'POLYGON'
#     },
#     ...
# ]

# Filter by schema
columns = db.list_geometry_columns(schema="geo")
```

## Common Spatial Operations

### Point in Polygon

```python
result = db.spatial.contains(
    "parcels",
    geom="geometry",
    point=(-122.4, 37.8),
    srid=4326,
    columns=["id", "name"],
)
```

### Distance Queries

The `db.spatial` namespace provides two helpers for distance-based queries: one
to filter rows within a radius (`dwithin`) and one to compute the distance to
each row (`distance`). Use them separately or in combination.

```python
# Filter: rows within 1 km of a point
rows = db.spatial.dwithin(
    "parcels",
    geom="geometry",
    point=(-122.4, 37.8),
    distance=1000,
    unit="m",
)

# Compute distance column with ordering
rows = db.spatial.distance(
    "parcels",
    geom="geometry",
    point=(-122.4, 37.8),
    unit="m",
    columns=["id", "name"],
    order_by="distance",
)
```

### Intersection

For simple intersection predicates (does this row's geometry intersect a given point or
geometry?), use `db.spatial.intersects`. For complex aggregate queries computing the
overlap area between rows (a self-join or cross-join), raw SQL remains the right tool.

```python
# Simple predicate: does this parcel intersect a given WKT polygon?
rows = db.spatial.intersects(
    "parcels",
    geom="geometry",
    wkt="POLYGON((-122.5 37.7, -122.3 37.7, -122.3 37.9, -122.5 37.9, -122.5 37.7))",
)

# Complex aggregate: pairwise overlap area (no helper — raw execute)
result = db.execute("""
    SELECT a.id AS id_a, b.id AS id_b,
           ST_Area(ST_Intersection(a.geometry, b.geometry)) AS overlap_area
    FROM parcels a, parcels b
    WHERE a.id < b.id
      AND ST_Intersects(a.geometry, b.geometry)
""")
```

### Buffer

```python
# Create 100 m buffers around point geometries
result = db.spatial.buffer(
    "locations",
    geom="geometry",
    distance=100,
    unit="m",
    columns=["id", "name"],
)
# Result rows include a "buffer" geometry column.
```

### Centroid

```python
# Get centroid coordinates for each parcel
result = db.spatial.centroid(
    "parcels",
    geom="geometry",
    columns=["id", "name"],
)
# Result rows include "centroid_x" and "centroid_y" (not "lon"/"lat").
```

### Area and Perimeter

The helpers compute area and perimeter separately. Each returns a scalar result
column (`"area"` or `"perimeter"`); `into="gdf"` is not supported for these helpers.

```python
# Top 10 parcels by area (sq metres)
result = db.spatial.area(
    "parcels",
    geom="geometry",
    unit="m",
    columns=["id", "name"],
    order_by="area",
    limit=10,
)

# Perimeter in metres
result = db.spatial.perimeter(
    "parcels",
    geom="geometry",
    unit="m",
    columns=["id", "name"],
)
```

## Coordinate Reference Systems

### Checking CRS

```python
gdf = db.to_geodataframe("parcels")
print(gdf.crs)  # EPSG:4326
```

### Transforming CRS

```python
# In database (result column is named "geometry_transformed")
result = db.spatial.transform(
    "parcels",
    geom="geometry",
    to_srid=3857,
)

# With GeoPandas (client-side reproject)
gdf = db.to_geodataframe("parcels")
gdf_3857 = gdf.to_crs(epsg=3857)
```

### Setting SRID

```python
# When creating table
db.from_geodataframe(gdf, "parcels", srid=4326)

# Update existing geometry — DML UPDATE is not covered by db.spatial.* helpers
# (helpers are SELECT-only); use db.execute() directly for mutations.
db.execute("""
    UPDATE parcels
    SET geometry = ST_SetSRID(geometry, 4326)
    WHERE ST_SRID(geometry) = 0
""")
```

## Example: Spatial Analysis

For complex multi-table spatial queries (spatial joins, `SUM(ST_Area(...))` aggregates),
use `db.to_geodataframe(sql=...)` or `db.execute()` directly. The `db.spatial.*` helpers
cover single-table operations; raw SQL remains the right tool for complex aggregates.

```python
import geopandas as gpd
from pycopg import Database

db = Database.from_env()

# Ensure PostGIS is available
if not db.has_extension("postgis"):
    db.create_extension("postgis")

# Load and store data
parcels = gpd.read_file("parcels.geojson")
db.from_geodataframe(parcels, "parcels", primary_key="id", spatial_index=True)

buildings = gpd.read_file("buildings.geojson")
db.from_geodataframe(buildings, "buildings", primary_key="id", spatial_index=True)

# Spatial join: buildings within parcels
result = db.to_geodataframe(sql="""
    SELECT b.*, p.parcel_id, p.owner
    FROM buildings b
    JOIN parcels p ON ST_Within(b.geometry, p.geometry)
""")

# Aggregate: total building area per parcel
stats = db.execute("""
    SELECT
        p.id AS parcel_id,
        p.owner,
        COUNT(b.id) AS building_count,
        SUM(ST_Area(b.geometry::geography)) AS total_building_area,
        ST_Area(p.geometry::geography) AS parcel_area
    FROM parcels p
    LEFT JOIN buildings b ON ST_Within(b.geometry, p.geometry)
    GROUP BY p.id, p.owner, p.geometry
    ORDER BY building_count DESC
""")

# Cleanup
db.close()
```
