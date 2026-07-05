# API Reference

Complete API reference for all pycopg classes and methods.

## Config

Configuration for database connections.

```python
from pycopg import Config
```

### Constructor

```python
Config(
    host: str = "localhost",
    port: int = 5432,
    database: str = "postgres",
    user: str = "postgres",
    password: str = "",
    sslmode: Optional[str] = None,
    options: dict = {}
)
```

### Class Methods

| Method | Description |
|--------|-------------|
| `from_url(url)` | Create Config from PostgreSQL URL |
| `from_env(dotenv_path=None, *, load_dotenv_file=True)` | Create Config from environment variables |

#### from_env Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `dotenv_path` | `str`, `Path`, or `None` | `None` | Path to .env file |
| `load_dotenv_file` | `bool` | `True` | Whether to load .env file. Set `False` to use only existing env vars |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `dsn` | `str` | psycopg-compatible DSN string |
| `url` | `str` | SQLAlchemy-compatible URL |
| `statement_timeout` | `Optional[int]` | Statement timeout in milliseconds (None = no limit) |

### Methods

| Method | Description |
|--------|-------------|
| `connect_params()` | Return dict for psycopg.connect() |
| `with_database(name)` | Create new Config with different database |

---

## Database

Synchronous database interface.

```python
from pycopg import Database
```

### Constructor

```python
Database(config: Config)
```

### Class Methods

| Method | Description |
|--------|-------------|
| `from_url(url)` | Create from PostgreSQL URL |
| `from_env(dotenv_path=None)` | Create from environment |
| `create(name, host, port, user, password, ...)` | Create a new database and connect to it |
| `create_from_env(name, ...)` | Create database using env credentials |

### Query Methods

| Method | Parameters | Returns | Description |
|--------|------------|---------|-------------|
| `execute` | `sql, params=None, autocommit=False` | `list[dict]` | Execute SQL, return results |
| `execute_many` | `sql, params_seq` | `int` | Execute for multiple params |
| `fetch_one` | `sql, params=None` | `Optional[dict]` | Fetch single row |
| `fetch_val` | `sql, params=None` | `Any` | Fetch single value |
| `fetch_all` | `sql, params=None` | `list[dict]` | Fetch all rows as list of dicts |

### CRUD Methods (v0.9.0)

Flat helpers on `Database` for common single-table operations. All column names are validated;
values are bound as `%s`. Full sync/async parity on `AsyncDatabase`.

`delete_where`, `update_where`, `exists`, `count`, `paginate`, `paginate_page` (v1.1.0), and
`paginate_keyset` (v1.1.0) additionally accept keyword-only `where_sql: str | None = None` +
`where_params: Sequence | None = None` — a raw-SQL escape hatch for predicates the `where` dict
cannot express (e.g. `where_sql="age > %s AND status = ANY(%s)"`). `where` and `where_sql` are
mutually exclusive; the fragment is passed through **verbatim** (never identifier-validated —
the caller owns the SQL text), only `where_params` are bound as `%s`.

| Method | Parameters | Returns |
|--------|------------|---------|
| `upsert` | `table, row, conflict_columns, update_columns=None, schema="public"` | `dict \| None` |
| `delete_where` | `table, where=None, *, where_sql=None, where_params=None, schema="public"` | `int` |
| `update_where` | `table, values, where=None, *, where_sql=None, where_params=None, schema="public"` | `int` |
| `exists` | `table, where=None, *, where_sql=None, where_params=None, schema="public"` | `bool` |
| `count` | `table, *, where=None, where_sql=None, where_params=None, schema="public"` | `int` |
| `paginate` | `table, limit, *, offset=0, order_by=None, where=None, where_sql=None, where_params=None, descending=False, schema="public"` | `list[dict]` |

### Pagination (v1.1.0)

Two additional pagination methods return a typed `Page` envelope instead of a plain
`list[dict]`. `paginate()` itself is unchanged (frozen `list[dict]`).

| Method | Parameters | Returns |
|--------|------------|---------|
| `paginate_page` | `table, limit, *, offset=0, order_by=None, where=None, where_sql=None, where_params=None, with_total=False, descending=False, schema="public"` | `Page` |
| `paginate_keyset` | `table, limit, *, order_by, after=None, where=None, where_sql=None, where_params=None, with_total=False, descending=False, schema="public"` | `Page` |

`paginate_page` is the offset-pagination sibling of `paginate()`. `paginate_keyset` is stable,
index-friendly *seek* pagination via a PostgreSQL row-value comparison
(`(c1, c2) > (%s, %s)`) instead of `OFFSET` — `order_by` is mandatory (append a unique column
such as the primary key as a tiebreaker), forward-only for this release. `order_by` columns
should be `NOT NULL` — the row-value comparison follows SQL `NULL` semantics, so rows with a
`NULL` key are silently skipped by the seek predicate. Feed `Page.next_cursor` back as the next
call's `after=` to page forward, processing each page's rows before advancing the cursor:

```python
page = db.paginate_keyset("events", 50, order_by=["created_at", "id"])
while True:
    for row in page.rows:
        ...  # process
    if not page.has_next:
        break
    page = db.paginate_keyset(
        "events", 50, order_by=["created_at", "id"], after=page.next_cursor
    )
```

#### `Page` (frozen dataclass)

| Field | Type | Description |
|-------|------|--------------|
| `rows` | `list[dict]` | The page of rows, already trimmed to `limit`. |
| `total` | `int \| None` | Full filtered `COUNT(*)`; populated only when `with_total=True`, else `None`. |
| `has_next` | `bool` | Always computed cheaply via a `limit + 1` fetch-and-trim. |
| `next_cursor` | `tuple \| None` | For `paginate_keyset`, the last row's `order_by`-keyed value tuple; always `None` for `paginate_page` (offset pagination has no cursor concept). |

`Page` is exported from `pycopg` (`from pycopg import Page`), mirroring the `RunResult`
dataclass (see [etl.md](etl.md)).

### CRUD Methods (v1.2.0)

The predicate-read siblings of `delete_where`/`update_where`/`exists`/`count`, plus a
single-row `insert`. Full sync/async parity on `AsyncDatabase`.

| Method | Parameters | Returns |
|--------|------------|---------|
| `select_where` | `table, where=None, *, where_sql=None, where_params=None, columns=None, order_by=None, limit=None, offset=None, schema="public"` | `list[dict]` |
| `find` | `table, where=None, *, where_sql=None, where_params=None, columns=None, order_by=None, limit=None, offset=None, schema="public"` | `list[dict]` |
| `get` | `table, where=None, *, where_sql=None, where_params=None, columns=None, order_by=None, schema="public"` | `dict \| None` |
| `find_one` | `table, where=None, *, where_sql=None, where_params=None, columns=None, order_by=None, schema="public"` | `dict \| None` |
| `insert` | `table, row, *, schema="public", on_conflict=None` | `dict \| None` |

`select_where` reuses the `_build_select_sql` builder shared with `paginate` (so `order_by`/
`limit`/`offset` are near-free) and, like `count`, treats an empty predicate as legal — with no
`where`/`where_sql`, all rows are returned (D-03), unlike the destructive-guard helpers
(`delete_where`/`update_where`/`exists`). `find` is a real, concrete, delegating twin of
`select_where` (D-02) — not a `@deprecated_alias` or module-level alias — provided as a
shorter, familiar name for the same read.

`get`/`find_one` force a server-side `LIMIT 1` and return the first matching row (or `None`)
without raising on multiple matches (D-04); they expose `columns=`/`order_by=` but
deliberately omit `limit=`/`offset=`, since exposing them would contradict the forced
`LIMIT 1` (D-05). `find_one` is `get`'s real, concrete, delegating twin, same rule as `find`.

`insert` is the singular twin of `insert_many`/`upsert` — a single-row `RETURNING *` insert.
`on_conflict` is a raw passthrough string (e.g. `"DO NOTHING"`, `"DO UPDATE SET ..."`)
mirroring `insert_many`'s shape (D-06), not `upsert`'s conflict/update-column computation.
Returns the inserted row as a `dict`; under `on_conflict="DO NOTHING"` with a pre-existing
conflicting row, no row is returned and `insert` returns `None` (D-07).

```python
rows = db.select_where("users", {"active": True}, order_by="created_at DESC", limit=10)
user = db.get("users", {"email": "alice@example.com"})
new_row = db.insert("users", {"email": "bob@example.com", "active": True})
```

### Context Managers

| Method | Parameters | Yields | Description |
|--------|------------|--------|-------------|
| `connect` | `autocommit=False` | `Connection` | Connection context |
| `cursor` | `autocommit=False` | `Cursor` | Cursor with dict rows |

### Schema Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `list_schemas` | - | `list[str]` |
| `schema_exists` | `name` | `bool` |
| `create_schema` | `name, if_not_exists=True, owner=None` | - |
| `drop_schema` | `name, if_exists=True, cascade=False` | - |

### Table Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `list_tables` | `schema="public"` | `list[str]` |
| `table_exists` | `name, schema="public"` | `bool` |
| `table_info` | `name, schema="public"` | `list[dict]` |
| `list_columns` | `name, schema="public"` | `list[str]` |
| `columns_with_types` | `name, schema="public"` | `list[tuple[str, str]]` |
| `row_count` | `name, schema="public"` | `int` |
| `drop_table` | `name, schema="public", if_exists=True, cascade=False` | - |
| `truncate_table` | `name, schema="public", cascade=False` | - |

### Introspection Methods (v0.9.0)

Available on `db.schema.*` and `async_db.schema.*`.

| Method | Parameters | Returns |
|--------|------------|---------|
| `primary_key` | `table, schema="public"` | `dict \| None` |
| `foreign_keys` | `table, schema="public"` | `list[dict]` |
| `sequences` | `schema="public"` | `list[str]` |
| `views` | `schema="public"` | `list[str]` |
| `describe` | `table, schema="public", into="dict"\|"dataclass"\|"dataframe"` | `dict \| TableDescription \| DataFrame` |

`describe`'s `into=` selector (v1.1.0, D-11/D-12) defaults to `"dict"` — byte-identical to the
frozen v0.9.0 flat dict (C-03). `into="dataclass"` wraps the same four sub-values in a typed
`TableDescription` (no reshape); `into="dataframe"` returns the `columns` section as a
one-row-per-column `pandas.DataFrame` (nullable integer columns are promoted to `float64` with
`NaN`, a pandas dtype-inference artifact — not data loss). An unrecognized `into` value raises
`ValueError`.

#### `TableDescription` (frozen dataclass)

| Field | Type | Description |
|-------|------|--------------|
| `columns` | `list[dict]` | Exact output of `table_info`. |
| `primary_key` | `dict \| None` | Exact output of `primary_key`. |
| `foreign_keys` | `list[dict]` | Exact output of `foreign_keys`. |
| `indexes` | `list[dict]` | Exact output of `list_indexes`. |

`TableDescription` is exported from `pycopg` (`from pycopg import TableDescription`), mirroring
the `RunResult`/`Page` dataclass precedent (see [etl.md](etl.md)).

### Introspection Methods (v1.1.0)

Available on `db.schema.*` and `async_db.schema.*`. `information_schema.views`/`columns`
exclude materialized views per the SQL standard, so these two methods use dedicated
`pg_catalog` queries to close that gap (D-13/D-14). `materialized_view_columns` returns
the same 8-key shape as `table_info`; matview columns never carry NOT NULL constraints or
defaults, so `is_nullable` is always `'YES'` and `column_default` is always `None` —
faithful to what a materialized view actually is, not a bug.

| Method | Parameters | Returns |
|--------|------------|---------|
| `materialized_views` | `schema="public"` | `list[str]` |
| `materialized_view_columns` | `name, schema="public"` | `list[dict]` |

### Introspection Methods (v1.2.0)

Available on `db.schema.*` and `async_db.schema.*`.

| Method | Parameters | Returns |
|--------|------------|---------|
| `column_exists` | `table, column, schema="public"` | `bool` |
| `table_size` | `name, schema="public"` | `int` |

`column_exists` mirrors `table_exists` mechanically (D-08): `table`/`column`/`schema` are
bound as `%s` values against `information_schema.columns`, never interpolated as SQL
identifiers.

`table_size` returns the raw `pg_total_relation_size` byte count (heap + indexes + TOAST) —
no pretty formatting. It checks `table_exists` first and raises `TableNotFoundError` on a
missing table rather than leaking a raw psycopg `UndefinedTable` or silently returning `0`
(D-09). This is a different accessor with different semantics than `db.maint.table_size`
(see "Size/Stats Methods" below), which returns a human-readable/pretty size
(`pretty=True` by default) with no existence guard — the two are intentionally not
deduplicated.

### Extension Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `list_extensions` | - | `list[dict]` |
| `has_extension` | `name` | `bool` |
| `create_extension` | `name, schema=None, if_not_exists=True` | - |
| `drop_extension` | `name, if_exists=True, cascade=False` | - |

### Index Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `create_index` | `table, columns, schema="public", name=None, unique=False, method="btree", if_not_exists=True` | - |
| `drop_index` | `name, schema="public", if_exists=True` | - |
| `list_indexes` | `table, schema="public"` | `list[dict]` |

### Constraint Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `add_primary_key` | `table, columns, schema="public", name=None` | - |
| `add_foreign_key` | `table, columns, ref_table, ref_columns, ...` | - |
| `add_unique_constraint` | `table, columns, schema="public", name=None` | - |
| `list_constraints` | `table, schema="public"` | `list[dict]` |

### DataFrame Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `from_dataframe` | `df, table, schema="public", if_exists="fail", primary_key=None, ...` | - |
| `to_dataframe` | `table=None, schema="public", sql=None, params=None` | `DataFrame` |
| `from_geodataframe` | `gdf, table, schema="public", ...` | - |
| `to_geodataframe` | `table=None, schema="public", sql=None, geometry_column="geometry", ...` | `GeoDataFrame` |

### PostGIS Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `create_spatial_index` | `table, column="geometry", schema="public", name=None` | - |
| `list_geometry_columns` | `schema=None` | `list[dict]` |

### Spatial Helpers (db.spatial.*)

Accessed via `db.spatial.<method>(...)`. The accessor is initialized lazily on first
access and raises `ExtensionNotAvailableError` if PostGIS is not installed. All helpers accept
one of four geometry input forms: `point=(x, y)`, `wkt="..."`, `geojson={...}`,
`ref=(table, col)`. The `into=` parameter controls output: `"rows"` returns
`list[dict]` (default); `"gdf"` returns a `GeoDataFrame`. Scalar helpers (`area`,
`perimeter`, `distance`, `centroid`, `length`, `is_valid`, `is_valid_reason`) only
support `into="rows"`.

| Method | Key Parameters | Returns |
|--------|----------------|---------|
| `contains` | `table, geom="geometry", point=, wkt=, geojson=, ref=, srid=4326, into="rows", columns=, filter=, order_by=, limit=` | `list[dict] \| GeoDataFrame` |
| `within` | `left_table, left_geom, right_table, right_geom, schema="public", into="rows", columns=, filter=, order_by=, limit=` | `list[dict] \| GeoDataFrame` |
| `intersects` | `table, geom="geometry", point=, wkt=, geojson=, ref=, srid=4326, into="rows", columns=, filter=, order_by=, limit=` | `list[dict] \| GeoDataFrame` |
| `dwithin` | `table, geom="geometry", point=, wkt=, geojson=, ref=, srid=4326, distance=, unit="m", into="rows", columns=, filter=, order_by=, limit=` | `list[dict] \| GeoDataFrame` |
| `distance` | `table, geom="geometry", point=, wkt=, geojson=, srid=4326, unit="m", into="rows", columns=, filter=, order_by=, limit=` | `list[dict]` |
| `nearest` | `table, geom="geometry", point=, wkt=, geojson=, srid=4326, k=5, into="rows", columns=, filter=` | `list[dict] \| GeoDataFrame` |
| `area` | `table, geom="geometry", unit="m", into="rows", columns=, filter=, order_by=, limit=` | `list[dict]` |
| `perimeter` | `table, geom="geometry", unit="m", into="rows", columns=, filter=, order_by=, limit=` | `list[dict]` |
| `centroid` | `table, geom="geometry", into="rows", columns=, filter=, order_by=, limit=` | `list[dict]` |
| `buffer` | `table, geom="geometry", distance=, unit="m", into="rows", columns=, filter=, order_by=, limit=` | `list[dict] \| GeoDataFrame` |
| `transform` | `table, geom="geometry", to_srid=, into="rows", columns=, filter=, order_by=, limit=` | `list[dict] \| GeoDataFrame` |
| `union` | `table, *, geom="geometry", schema="public", other_geom, grid_size=None, filter=None, into="rows", columns=None, order_by=None, limit=None` | `list[dict] \| GeoDataFrame` |
| `difference` | `table, *, geom="geometry", schema="public", other_geom, grid_size=None, filter=None, into="rows", columns=None, order_by=None, limit=None` | `list[dict] \| GeoDataFrame` |
| `intersection` | `table, *, geom="geometry", schema="public", other_geom, grid_size=None, filter=None, into="rows", columns=None, order_by=None, limit=None` | `list[dict] \| GeoDataFrame` |
| `simplify` | `table, *, geom="geometry", schema="public", tolerance, preserve_topology=True, preserve_collapsed=False, filter=None, into="rows", columns=None, order_by=None, limit=None` | `list[dict] \| GeoDataFrame` |
| `convex_hull` | `table, *, geom="geometry", schema="public", filter=None, into="rows", columns=None, order_by=None, limit=None` | `list[dict] \| GeoDataFrame` |
| `make_valid` | `table, *, geom="geometry", schema="public", method=None, keep_collapsed=None, filter=None, into="rows", columns=None, order_by=None, limit=None` | `list[dict] \| GeoDataFrame` |
| `collect_geometries` | `table, *, geom="geometry", schema="public", group_by=None, filter=None, into="rows", order_by=None, limit=None` | `list[dict] \| GeoDataFrame` |
| `union_aggregate` | `table, *, geom="geometry", schema="public", group_by=None, filter=None, into="rows", order_by=None, limit=None` | `list[dict] \| GeoDataFrame` |
| `extent` | `table, *, geom="geometry", schema="public", group_by=None, srid=4326, filter=None, into="rows", order_by=None, limit=None` | `list[dict] \| GeoDataFrame` |
| `as_geojson` | `table, *, geom="geometry", schema="public", max_decimal_digits=6, include_bbox=False, include_crs=False, into="rows", columns=None, filter=None, order_by=None, limit=None` | `list[dict]` |
| `as_text` | `table, *, geom="geometry", schema="public", max_decimal_digits=None, into="rows", columns=None, filter=None, order_by=None, limit=None` | `list[dict]` |
| `as_mvt` | `table, *, geom="geometry", schema="public", tile_z, tile_x, tile_y, layer_name="default", extent=4096, columns=None, feature_id_column=None, srid=None, filter=None` | `bytes` |
| `length` | `table, *, geom="geometry", schema="public", unit="m", into="rows", columns=None, filter=None, order_by=None, limit=None` | `list[dict]` |
| `is_valid` | `table, *, geom="geometry", schema="public", into="rows", columns=None, filter=None, order_by=None, limit=None` | `list[dict]` |
| `is_valid_reason` | `table, *, geom="geometry", schema="public", into="rows", columns=None, filter=None, order_by=None, limit=None` | `list[dict]` |
| `envelope` | `table, *, geom="geometry", schema="public", into="rows", columns=None, filter=None, order_by=None, limit=None` | `list[dict] \| GeoDataFrame` |
| `point_on_surface` | `table, *, geom="geometry", schema="public", into="rows", columns=None, filter=None, order_by=None, limit=None` | `list[dict] \| GeoDataFrame` |
| `overlaps` | `table, geom="geometry", schema="public", point=, wkt=, geojson=, ref=, srid=4326, into="rows", columns=, filter=, order_by=, limit=` | `list[dict] \| GeoDataFrame` |
| `touches` | `table, geom="geometry", schema="public", point=, wkt=, geojson=, ref=, srid=4326, into="rows", columns=, filter=, order_by=, limit=` | `list[dict] \| GeoDataFrame` |
| `crosses` | `table, geom="geometry", schema="public", point=, wkt=, geojson=, ref=, srid=4326, into="rows", columns=, filter=, order_by=, limit=` | `list[dict] \| GeoDataFrame` |
| `disjoint` | `table, geom="geometry", schema="public", point=, wkt=, geojson=, ref=, srid=4326, into="rows", columns=, filter=, order_by=, limit=` | `list[dict] \| GeoDataFrame` |

### TimescaleDB Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `create_hypertable` | `table, time_column, schema="public", chunk_time_interval="1 day", ...` | - |
| `enable_compression` | `table, segment_by=None, order_by=None, schema="public"` | - |
| `add_compression_policy` | `table, compress_after="7 days", schema="public"` | - |
| `add_retention_policy` | `table, drop_after, schema="public"` | - |
| `list_hypertables` | - | `list[dict]` |
| `hypertable_info` | `table, schema="public"` | `dict` |
| `show_chunks` | `table, older_than=None, newer_than=None, schema="public"` | `list[str]` |
| `drop_chunks` | `table, older_than=None, newer_than=None, schema="public", dry_run=False` | `list[str]` |
| `add_dimension` | `table, column, partition_type="hash", number_partitions=None, chunk_interval=None, schema="public", if_not_exists=True` | `-` |
| `add_reorder_policy` | `table, index_name, schema="public", if_not_exists=True` | `-` |
| `create_continuous_aggregate` | `view_name, select_sql, schema="public", materialized_only=True, with_no_data=False` | `-` |
| `refresh_continuous_aggregate` | `view_name, window_start=None, window_end=None, schema="public"` | `-` |
| `add_continuous_aggregate_policy` | `view_name, start_offset, end_offset, schedule_interval="1 hour", schema="public", if_not_exists=True` | `-` |
| `time_bucket` | `table, time_column, bucket_width, aggregates, filter=None, schema="public", into="df"` | `DataFrame \| list[dict]` |
| `time_bucket_gapfill` | `table, time_column, bucket_width, start, finish, aggregates, filter=None, schema="public", into="df"` | `DataFrame \| list[dict]` |

### Role Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `create_role` | `name, password=None, login=True, superuser=False, ...` | - |
| `drop_role` | `name, if_exists=True` | - |
| `role_exists` | `name` | `bool` |
| `list_roles` | `include_system=False` | `list[dict]` |
| `alter_role` | `name, password=None, login=None, ...` | - |
| `grant_role` | `role, member, with_admin=False` | - |
| `revoke_role` | `role, member` | - |
| `grant` | `privileges, on, to, object_type="TABLE", schema="public", ...` | - |
| `revoke` | `privileges, on, from_role, object_type="TABLE", schema="public", ...` | - |
| `list_role_members` | `role` | `list[str]` |
| `list_role_grants` | `role` | `list[dict]` |

### Backup Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `pg_dump` | `output_file, format="custom", schema_only=False, ...` | - |
| `pg_restore` | `input_file, clean=False, if_exists=True, ...` | - |
| `copy_to_csv` | `table, output_file, schema="public", ...` | `int` |
| `copy_from_csv` | `table, input_file, schema="public", ...` | `int` |

### Database Admin Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `create_database` | `name, owner=None, template="template1"` | - |
| `drop_database` | `name, if_exists=True` | - |
| `database_exists` | `name` | `bool` |
| `list_databases` | - | `list[str]` |

### Size/Stats Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `size` | `pretty=True` | `str` or `int` |
| `table_size` | `table, schema="public", pretty=True` | `str` or `int` |
| `table_sizes` | `schema="public", limit=20` | `list[dict]` |

### Maintenance Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `vacuum` | `table=None, schema="public", analyze=True, full=False` | - |
| `analyze` | `table=None, schema="public"` | - |
| `explain` | `sql, params=None, analyze=False, format="text"` | `list[str]` |

---

## AsyncDatabase

Asynchronous database interface with full parity to Database.

```python
from pycopg import AsyncDatabase
```

> **Full Async Parity (v0.3.0):** AsyncDatabase provides all the same methods as Database with async/await. All methods listed in the Database section above (query, schema, table, DataFrame, PostGIS, TimescaleDB, role, backup, admin, maintenance, and size methods) are available asynchronously.

### Async-Only Methods

These methods are only available on AsyncDatabase and have no sync equivalent:

| Method | Parameters | Returns |
|--------|------------|---------|
| `stream` | `sql, params=None, batch_size=1000` | `AsyncIterator[dict]` |
| `insert_many` | `table, rows, schema="public", on_conflict=None` | `int` |
| `upsert_many` | `table, rows, conflict_columns, update_columns=None, ...` | `int` |
| `listen` | `channel` | `AsyncIterator[str]` |
| `notify` | `channel, payload=""` | - |

### Async Context Managers

| Method | Parameters | Yields |
|--------|------------|--------|
| `connect` | `autocommit=False` | `AsyncConnection` |
| `cursor` | `autocommit=False` | `AsyncCursor` |
| `transaction` | - | `AsyncConnection` |

---

## PooledDatabase

Synchronous connection pool.

```python
from pycopg import PooledDatabase
```

### Constructor

```python
PooledDatabase(
    config: Config,
    min_size: int = 2,
    max_size: int = 10,
    max_idle: float = 300.0,
    max_lifetime: float = 3600.0,
    timeout: float = 30.0,
    num_workers: int = 3,
)
```

### Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `connection` | - | `ContextManager[Connection]` |
| `execute` | `sql, params=None` | `list[dict]` |
| `execute_many` | `sql, params_seq` | `int` |
| `resize` | `min_size, max_size` | - |
| `check` | - | - |
| `wait` | `timeout=30.0` | - |
| `close` | - | - |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `stats` | `dict` | Pool statistics |

---

## AsyncPooledDatabase

Asynchronous connection pool.

```python
from pycopg import AsyncPooledDatabase
```

### Constructor

Same as PooledDatabase.

### Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `open` | - | `Coroutine` |
| `connection` | - | `AsyncContextManager[AsyncConnection]` |
| `execute` | `sql, params=None` | `Coroutine[list[dict]]` |
| `execute_many` | `sql, params_seq` | `Coroutine[int]` |
| `fetch_one` | `sql, params=None` | `Coroutine[Optional[dict]]` |
| `fetch_val` | `sql, params=None` | `Coroutine[Any]` |
| `transaction` | - | `AsyncContextManager[AsyncConnection]` |
| `resize` | `min_size, max_size` | - |
| `check` | - | `Coroutine` |
| `close` | - | `Coroutine` |

---

## Migrator

SQL migration manager.

```python
from pycopg import Migrator
```

### Constructor

```python
Migrator(
    db: Database,
    migrations_dir: Union[str, Path],
    table: str = "schema_migrations",
)
```

### Methods

| Method | Parameters | Returns |
|--------|------------|---------|
| `status` | - | `dict` |
| `pending` | - | `list[Migration]` |
| `applied` | - | `list[dict]` |
| `migrate` | `target=None` | `list[Migration]` |
| `rollback` | `steps=1` | `list[dict]` |
| `create` | `name` | `Path` |

---

## Exceptions

```python
from pycopg import (
    PycopgError,                # Base exception
    ConnectionError,            # Connection failed
    ConfigurationError,         # Bad config
    ExtensionNotAvailableError, # Missing extension
    TableNotFoundError,         # Table doesn't exist
    InvalidIdentifierError,     # SQL injection attempt
    MigrationError,             # Migration failed
)
```
