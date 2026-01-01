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
# Spatial query
gdf = db.to_geodataframe(
    sql="""
        SELECT * FROM parcels
        WHERE ST_Within(
            geometry,
            ST_MakeEnvelope(-122.5, 37.7, -122.3, 37.9, 4326)
        )
    """
)

# With parameters
gdf = db.to_geodataframe(
    sql="""
        SELECT * FROM parcels
        WHERE ST_DWithin(
            geometry::geography,
            ST_Point(:lon, :lat)::geography,
            :radius
        )
    """,
    params={"lon": -122.4, "lat": 37.8, "radius": 1000}
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
result = db.execute("""
    SELECT p.id, p.name
    FROM parcels p
    WHERE ST_Contains(
        p.geometry,
        ST_SetSRID(ST_Point(%s, %s), 4326)
    )
""", [-122.4, 37.8])
```

### Distance Queries

```python
# Find parcels within 1km of a point
result = db.execute("""
    SELECT id, name,
           ST_Distance(
               geometry::geography,
               ST_Point(%s, %s)::geography
           ) AS distance_meters
    FROM parcels
    WHERE ST_DWithin(
        geometry::geography,
        ST_Point(%s, %s)::geography,
        1000
    )
    ORDER BY distance_meters
""", [-122.4, 37.8, -122.4, 37.8])
```

### Intersection

```python
# Find overlapping parcels
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
# Create buffers around points
result = db.execute("""
    SELECT id, name,
           ST_Buffer(geometry::geography, 100)::geometry AS buffer_100m
    FROM locations
""")
```

### Centroid

```python
# Get centroids of polygons
result = db.execute("""
    SELECT id, name,
           ST_X(ST_Centroid(geometry)) AS lon,
           ST_Y(ST_Centroid(geometry)) AS lat
    FROM parcels
""")
```

### Area and Perimeter

```python
# Calculate area and perimeter
result = db.execute("""
    SELECT id, name,
           ST_Area(geometry::geography) AS area_sq_meters,
           ST_Perimeter(geometry::geography) AS perimeter_meters
    FROM parcels
    ORDER BY area_sq_meters DESC
    LIMIT 10
""")
```

## Coordinate Reference Systems

### Checking CRS

```python
gdf = db.to_geodataframe("parcels")
print(gdf.crs)  # EPSG:4326
```

### Transforming CRS

```python
# In database
result = db.execute("""
    SELECT id, ST_Transform(geometry, 3857) AS geometry_web_mercator
    FROM parcels
""")

# With GeoPandas
gdf = db.to_geodataframe("parcels")
gdf_3857 = gdf.to_crs(epsg=3857)
```

### Setting SRID

```python
# When creating table
db.from_geodataframe(gdf, "parcels", srid=4326)

# Update existing geometry
db.execute("""
    UPDATE parcels
    SET geometry = ST_SetSRID(geometry, 4326)
    WHERE ST_SRID(geometry) = 0
""")
```

## Example: Spatial Analysis

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
