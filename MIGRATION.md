# Migration Guide: v0.10.x → 1.0.0

This guide covers **all breaking changes** at the 1.0 boundary introduced in Phase 41
(API Homogenization). Deprecated names (`where=` parameter alias, old exception names) are
kept through **all of 1.x** and removed only in 2.0 — but they emit `DeprecationWarning`
on use, so update your code now to silence them.

## Breaking Changes

### 1. Spatial `where=` renamed to `filter=` (FREEZE-01)

**All 11 `db.spatial.*` methods** and the corresponding 11 module-level `build_*_sql`
builders rename the raw SQL filter parameter from `where=` to `filter=`.

Affected methods: `contains`, `intersects`, `dwithin`, `distance`, `nearest`, `area`,
`perimeter`, `centroid`, `buffer`, `transform`, `within`.

**Before (pycopg ≤ 0.10.x):**

```python
rows = db.spatial.contains("parks", point=(1.0, 2.0), where="area > 1000")
gdf  = db.spatial.within("cities", "geom", "regions", "geom", where="population > 50000")

# Builder functions:
from pycopg.spatial import build_contains_sql
sql = build_contains_sql("parks", point=(1.0, 2.0), where="area > 1000")
```

**After (pycopg 1.0+):**

```python
rows = db.spatial.contains("parks", point=(1.0, 2.0), filter="area > 1000")
gdf  = db.spatial.within("cities", "geom", "regions", "geom", filter="population > 50000")

# Builder functions (clean rename — no backward-compat shim on builders):
from pycopg.spatial import build_contains_sql
sql = build_contains_sql("parks", point=(1.0, 2.0), filter="area > 1000")
```

The old `where=` on **accessor methods** emits `DeprecationWarning` through 1.x and is
removed in 2.0. The old `where=` on **builder functions** (`build_*_sql`) is a **clean
break** (no shim) — passing `where=` to a builder raises `TypeError` immediately.

**Important:** The `filter=` parameter accepts a **raw SQL fragment** (a SQL WHERE clause
body authored by the caller), not a dict-equality predicate. This is a structural SQL
parameter, intentionally distinct from the CRUD `where=` dict convention.

---

### 2. Exception renames → `*Error` convention (FREEZE-02)

Four exception classes are renamed to follow the PEP 8 / N818 `*Error` convention:

| Old name (deprecated) | New canonical name |
|-----------------------|--------------------|
| `ExtensionNotAvailable` | `ExtensionNotAvailableError` |
| `TableNotFound` | `TableNotFoundError` |
| `InvalidIdentifier` | `InvalidIdentifierError` |
| `DatabaseExists` | `DatabaseExistsError` |

**Before (pycopg ≤ 0.10.x):**

```python
from pycopg.exceptions import ExtensionNotAvailable, InvalidIdentifier
from pycopg import TableNotFound, DatabaseExists

try:
    db.schema.create_extension("postgis")
except ExtensionNotAvailable:
    print("PostGIS not installed")

try:
    db.schema.create_database("mydb")
except DatabaseExists:
    print("Database already exists")
```

**After (pycopg 1.0+):**

```python
from pycopg.exceptions import ExtensionNotAvailableError, InvalidIdentifierError
from pycopg import TableNotFoundError, DatabaseExistsError

try:
    db.schema.create_extension("postgis")
except ExtensionNotAvailableError:
    print("PostGIS not installed")

try:
    db.schema.create_database("mydb")
except DatabaseExistsError:
    print("Database already exists")
```

**Backward compatibility:** `except OldName:` continues to catch the same exceptions
(the old name resolves to the identical class object). Accessing the old name at import
time emits `DeprecationWarning`. Old names are removed in 2.0.

**Note on deprecation warning timing (D-08 relaxation):** The `DeprecationWarning` fires
at **import / attribute access time** (when you write `from pycopg.exceptions import
ExtensionNotAvailable` or `pycopg.ExtensionNotAvailable`) — NOT at `except` catch time.
This is intentional (PEP 562 module `__getattr__` semantics) and is not a gap. If you see
the warning, update the import to the `*Error` canonical name.

---

### 3. Keyword-only parameter enforcement (FREEZE-03)

All optional/defaulted parameters on every public method in every accessor are now
**keyword-only**, enforced by a `*` separator in the signature. This is a **clean break**
with no deprecation alias — positional calls that worked before now raise `TypeError`.

**Before (pycopg ≤ 0.10.x) — positional calls that now raise TypeError:**

```python
# Spatial — geom and schema were positional:
db.spatial.contains("parks", "geometry", "public", point=(1.0, 2.0))

# Schema — schema was positional:
db.schema.list_tables("public")
db.schema.table_exists("users", "public")
db.schema.describe("users", "public")

# Timescale — multiple params were positional:
db.timescale.create_hypertable("events", "time", "public", "7 days")
db.timescale.show_chunks("events", "30 days", None, "public")

# Admin — all optional params were positional:
db.admin.create_role("appuser", "secret", True)

# Maint — params were positional:
db.maint.vacuum("users", "public", True)
db.maint.table_size("users", "public")

# Backup — all optional params were positional:
db.backup.pg_dump("backup.dump", "custom", True)

# ETL:
db.etl.history("my_pipeline", 50)
db.etl.run(pipeline, True)

# Flat core:
db.insert_many("users", rows, "public")
db.paginate("users", 20, 40, "created_at")
db.from_dataframe(df, "users", "public", "replace")
```

**After (pycopg 1.0+) — use keyword arguments:**

```python
# Spatial:
db.spatial.contains("parks", geom="geometry", schema="public", point=(1.0, 2.0))

# Schema:
db.schema.list_tables(schema="public")
db.schema.table_exists("users", schema="public")
db.schema.describe("users", schema="public")

# Timescale:
db.timescale.create_hypertable("events", "time", schema="public", chunk_time_interval="7 days")
db.timescale.show_chunks("events", older_than="30 days", schema="public")

# Admin:
db.admin.create_role("appuser", password="secret", login=True)

# Maint:
db.maint.vacuum(table="users", schema="public", analyze=True)
db.maint.table_size("users", schema="public")

# Backup:
db.backup.pg_dump("backup.dump", format="custom", schema_only=True)

# ETL:
db.etl.history("my_pipeline", limit=50)
db.etl.run(pipeline, dry_run=True)

# Flat core:
db.insert_many("users", rows, schema="public")
db.paginate("users", 20, offset=40, order_by="created_at")
db.from_dataframe(df, "users", schema="public", if_exists="replace")
```

**Special case — `within()` 4-positional-identifier boundary (D1 decision):**

The `within()` method keeps 4 required table/column identifiers positional, but `schema=`
moves to keyword-only:

```python
# Before (schema was 5th positional):
db.spatial.within("cities", "geom", "regions", "geom", "myschema")

# After (schema is keyword-only):
db.spatial.within("cities", "geom", "regions", "geom", schema="myschema")
```

**D2/D5 carve-out — raw SQL execution primitives stay positional:**

The following methods intentionally keep their `params` (and `autocommit`) arguments
positional-with-default. The `(sql, params)` two-positional convention is established
and expected by users of the primitive I/O layer:

- `Database.execute(sql, params=None, autocommit=False)` — params and autocommit positional
- `Database.fetch_one(sql, params=None)` — params positional
- `Database.fetch_val(sql, params=None)` — params positional
- `Database.fetch_all(sql, params=None)` — params positional
- `Database.stream(sql, params=None, batch_size=1000)` — params and batch_size positional
- `db.maint.explain(sql, params=None, analyze=False, format="text")` — all positional

These are intentional, documented exceptions to the keyword-only enforcement (D-03 carve-out).
All AsyncDatabase equivalents follow the same pattern.

---

### 4. TimescaleDB `where=` renamed to `filter=` on time_bucket / time_bucket_gapfill (D3)

The `where=` parameter on `db.timescale.time_bucket()` and
`db.timescale.time_bucket_gapfill()` is renamed to `filter=`, matching the spatial
`filter=` convention for raw SQL fragments.

**Before (pycopg ≤ 0.10.x):**

```python
result = db.timescale.time_bucket(
    "events", "time", "1 hour",
    aggregates="count(*) AS cnt",
    where="device_id = 'sensor-01'",
)

result = db.timescale.time_bucket_gapfill(
    "events", "time", "1 hour",
    start="2024-01-01", finish="2024-02-01",
    aggregates="avg(value) AS avg_val",
    where="device_id = 'sensor-01'",
)
```

**After (pycopg 1.0+):**

```python
result = db.timescale.time_bucket(
    "events", "time", "1 hour",
    aggregates="count(*) AS cnt",
    filter="device_id = 'sensor-01'",
)

result = db.timescale.time_bucket_gapfill(
    "events", "time", "1 hour",
    start="2024-01-01", finish="2024-02-01",
    aggregates="avg(value) AS avg_val",
    filter="device_id = 'sensor-01'",
)
```

The old `where=` emits `DeprecationWarning` through 1.x and is removed in 2.0.
The `filter=` parameter accepts a **raw SQL fragment** (same semantics as the spatial
`filter=` — a SQL WHERE clause body, not a dict-equality predicate).

---

### 5. `mypy --strict` now blocking in CI (not a runtime break)

pycopg's own CI now fails the build if `mypy --strict` reports any error against the
`pycopg` package (previously advisory via `continue-on-error: true`). This does not change
any runtime behavior or public signature — it is listed here only for completeness against
the `[1.0.0]` CHANGELOG entry. No action is required unless you vendor pycopg's CI config.

---

## A note for type-checking consumers

pycopg 1.0 ships a complete [`py.typed`](https://peps.python.org/pep-0561/) marker and the
whole package passes `mypy --strict` with zero errors. If your own project runs `mypy` (or
another type checker that honors inline package types) against code that calls pycopg, you
no longer need `ignore_missing_imports` for the `pycopg` module — inline types, including
`@overload` variants for every polymorphic `into=` method, are picked up automatically.

## Upgrade Checklist

- [ ] Update `db.spatial.*` calls: replace `where=` with `filter=`
- [ ] Update `build_*_sql` builder calls: replace `where=` with `filter=` (no shim — TypeError if you don't)
- [ ] Update `db.timescale.time_bucket()` and `time_bucket_gapfill()` calls: replace `where=` with `filter=`
- [ ] Update exception imports: `from pycopg.exceptions import ExtensionNotAvailableError` etc.
- [ ] Update `except OldExceptionName:` blocks to use `*Error` canonical names (optional — old names still work through 1.x)
- [ ] Update positional calls to use keyword arguments for all optional/defaulted params
- [ ] Verify that `db.execute(sql, params)`, `db.fetch_all(sql, params)`, `db.stream(sql, params)` — these stay positional, no change needed
- [ ] Run test suite with `-W error::DeprecationWarning` to catch remaining deprecated usage:
  `uv run pytest -W error::DeprecationWarning`
- [ ] Optional: if you type-check your own code with `mypy`, drop any `ignore_missing_imports`
  override for `pycopg` — it now ships complete inline types (`py.typed`)

## Getting Help

- See [API Stability](https://pycopg.readthedocs.io/en/latest/stability.html) for the full
  Stable API Contract table (positional vs keyword-only for every method)
- Review [CHANGELOG.md](CHANGELOG.md) for the full list of changes
- Open an issue on [GitHub](https://github.com/alkimya/pycopg/issues) with your use case

---

# Migration Guide: v0.6.0 → v0.7.0

This guide helps you upgrade from pycopg 0.6.0 to 0.7.0. Version 0.7.0 permanently
removes the 56 flat method names that were deprecated in v0.6.0. Calling any removed
flat name now raises `AttributeError` immediately — there is no warning and no delegation.

## Breaking Changes: Flat API Names Removed

All 56 flat methods on `Database` and `AsyncDatabase` that emitted `DeprecationWarning`
in v0.6.0 are **permanently removed** in v0.7.0. They now raise `AttributeError`.

**Before (v0.6.0) — emitted DeprecationWarning; now raises AttributeError:**
```python
db.create_hypertable("events", "time")   # AttributeError in v0.7.0
db.create_role("appuser", login=True)    # AttributeError in v0.7.0
db.list_tables()                         # AttributeError in v0.7.0
```

**After (v0.7.0) — use the accessor path:**
```python
db.timescale.create_hypertable("events", "time")
db.admin.create_role("appuser", login=True)
db.schema.list_tables()
```

## Complete Flat-Name → Accessor-Path Removal Table

All 56 flat names removed in v0.7.0 and their accessor replacements.
Use this table to find the correct path for each removed name.

| Flat name (removed in v0.7.0) | Accessor path (use this) |
| ----------------------------- | ------------------------ |
| `db.add_compression_policy` | `db.timescale.add_compression_policy` |
| `db.add_retention_policy` | `db.timescale.add_retention_policy` |
| `db.create_hypertable` | `db.timescale.create_hypertable` |
| `db.enable_compression` | `db.timescale.enable_compression` |
| `db.hypertable_info` | `db.timescale.hypertable_info` |
| `db.list_hypertables` | `db.timescale.list_hypertables` |
| `db.alter_role` | `db.admin.alter_role` |
| `db.create_role` | `db.admin.create_role` |
| `db.drop_role` | `db.admin.drop_role` |
| `db.grant` | `db.admin.grant` |
| `db.grant_role` | `db.admin.grant_role` |
| `db.list_role_grants` | `db.admin.list_role_grants` |
| `db.list_role_members` | `db.admin.list_role_members` |
| `db.list_roles` | `db.admin.list_roles` |
| `db.revoke` | `db.admin.revoke` |
| `db.revoke_role` | `db.admin.revoke_role` |
| `db.role_exists` | `db.admin.role_exists` |
| `db.copy_from_csv` | `db.backup.copy_from_csv` |
| `db.copy_to_csv` | `db.backup.copy_to_csv` |
| `db.pg_dump` | `db.backup.pg_dump` |
| `db.pg_restore` | `db.backup.pg_restore` |
| `db.analyze` | `db.maint.analyze` |
| `db.explain` | `db.maint.explain` |
| `db.size` | `db.maint.size` |
| `db.table_size` | `db.maint.table_size` |
| `db.table_sizes` | `db.maint.table_sizes` |
| `db.vacuum` | `db.maint.vacuum` |
| `db.add_foreign_key` | `db.schema.add_foreign_key` |
| `db.add_primary_key` | `db.schema.add_primary_key` |
| `db.add_unique_constraint` | `db.schema.add_unique_constraint` |
| `db.columns_with_types` | `db.schema.columns_with_types` |
| `db.create_database` | `db.schema.create_database` |
| `db.create_extension` | `db.schema.create_extension` |
| `db.create_index` | `db.schema.create_index` |
| `db.create_schema` | `db.schema.create_schema` |
| `db.database_exists` | `db.schema.database_exists` |
| `db.drop_database` | `db.schema.drop_database` |
| `db.drop_extension` | `db.schema.drop_extension` |
| `db.drop_index` | `db.schema.drop_index` |
| `db.drop_schema` | `db.schema.drop_schema` |
| `db.drop_table` | `db.schema.drop_table` |
| `db.has_extension` | `db.schema.has_extension` |
| `db.list_columns` | `db.schema.list_columns` |
| `db.list_constraints` | `db.schema.list_constraints` |
| `db.list_databases` | `db.schema.list_databases` |
| `db.list_extensions` | `db.schema.list_extensions` |
| `db.list_indexes` | `db.schema.list_indexes` |
| `db.list_schemas` | `db.schema.list_schemas` |
| `db.list_tables` | `db.schema.list_tables` |
| `db.row_count` | `db.schema.row_count` |
| `db.schema_exists` | `db.schema.schema_exists` |
| `db.table_exists` | `db.schema.table_exists` |
| `db.table_info` | `db.schema.table_info` |
| `db.truncate_table` | `db.schema.truncate_table` |
| `db.create_spatial_index` | `db.spatial.create_spatial_index` |
| `db.list_geometry_columns` | `db.spatial.list_geometry_columns` |

**Total: 56 removed names** (timescale 6 / admin 11 / backup 4 / maint 6 / schema 27 / spatial 2).
All `async_db.*` flat names are identical (same 56, same accessor paths with `async_db` prefix).

## Upgrade Checklist

- [ ] Search codebase for any of the 56 removed flat names and replace with accessor paths
- [ ] If you call `db.create_extension(...)` or `db.list_tables(...)` anywhere, update now
- [ ] Run your test suite with `python -W error::AttributeError` to catch any missed calls
- [ ] Run `uv run pytest tests/ -x -q -o addopts=""` to verify compatibility

## New in v0.7.0: Incremental ETL

v0.7.0 adds optional watermark-based incremental loading to the ETL pipeline runner. It is
**additive and non-breaking**: existing pipelines are unaffected. The `pipeline_runs.watermark`
column was already reserved in v0.5.0 — no schema migration is required.

To opt in, set `incremental_column` on a `Pipeline` and use `load_mode="upsert"`:

```python
Pipeline(
    source="events",
    target="events_copy",
    load_mode="upsert",
    conflict_columns=["id"],
    incremental_column="created_at",
)
```

See [docs/etl.md](docs/etl.md) for the full incremental loading guide, including worked
examples, watermark-column requirements, and backfill/reset instructions.

## Getting Help

If you encounter issues during migration:

1. Check that you're using a supported Python version (3.11+)
2. Review the [CHANGELOG.md](CHANGELOG.md) for the full list of changes
3. Open an issue on [GitHub](https://github.com/alkimya/pycopg/issues) with your use case

---

# Migration Guide: v0.5.0 → v0.6.0

This guide helps you upgrade from pycopg 0.5.0 to 0.6.0. Version 0.6.0 introduces
accessor namespaces (`db.timescale.*`, `db.admin.*`, `db.schema.*`, `db.maint.*`,
`db.backup.*`) for all non-transactional operations. The flat names are deprecated and
will be **removed in v0.7.0**.

## Deprecation: Flat Method Names → Accessor Paths

All 56 methods that moved to accessor namespaces now emit `DeprecationWarning` when called
via the old flat name. They continue to work in v0.6.0 — update your code before v0.7.0.

### Before (v0.5.0) / After (v0.6.0)

**Timescale:**
```python
# Before
db.create_hypertable("events", "time")
await async_db.enable_compression("events", segment_by="device_id")

# After
db.timescale.create_hypertable("events", "time")
await async_db.timescale.enable_compression("events", segment_by="device_id")
```

**Admin:**
```python
# Before
db.create_role("appuser", password="secret", login=True)
db.grant("SELECT", "users", "readonly")

# After
db.admin.create_role("appuser", password="secret", login=True)
db.admin.grant("SELECT", "users", "readonly")
```

**Schema:**
```python
# Before
db.list_schemas()
db.create_index("users", "email", unique=True)

# After
db.schema.list_schemas()
db.schema.create_index("users", "email", unique=True)
```

**Maint:**
```python
# Before
db.vacuum("users", analyze=True)
db.size()

# After
db.maint.vacuum("users", analyze=True)
db.maint.size()
```

**Backup:**
```python
# Before
db.pg_dump("backup.dump")
db.copy_to_csv("users", "users.csv")

# After
db.backup.pg_dump("backup.dump")
db.backup.copy_to_csv("users", "users.csv")
```

**Spatial (relocated in v0.6.0):**
```python
# Before
db.create_spatial_index("parcels", "geometry")

# After
db.spatial.create_spatial_index("parcels", "geometry")
# Note: the deprecated flat path now raises ExtensionNotAvailable early when
# PostGIS is absent (stricter than the raw psycopg error it raised before).
```

## Complete Flat-Name → Accessor-Path Table

Generated from live source (`grep '@deprecated_alias' pycopg/database.py`). Do not use
the SCOPE doc counts — use this table.

**Regeneration command** (verify against live source before publishing):

```bash
grep '@deprecated_alias' pycopg/database.py \
  | sed 's/.*@deprecated_alias("\(.*\)")/\1/' \
  | sort
```

| Flat name (deprecated) | Accessor path (use this) |
| ---------------------- | ------------------------ |
| `db.add_compression_policy` | `db.timescale.add_compression_policy` |
| `db.add_retention_policy` | `db.timescale.add_retention_policy` |
| `db.create_hypertable` | `db.timescale.create_hypertable` |
| `db.enable_compression` | `db.timescale.enable_compression` |
| `db.hypertable_info` | `db.timescale.hypertable_info` |
| `db.list_hypertables` | `db.timescale.list_hypertables` |
| `db.alter_role` | `db.admin.alter_role` |
| `db.create_role` | `db.admin.create_role` |
| `db.drop_role` | `db.admin.drop_role` |
| `db.grant` | `db.admin.grant` |
| `db.grant_role` | `db.admin.grant_role` |
| `db.list_role_grants` | `db.admin.list_role_grants` |
| `db.list_role_members` | `db.admin.list_role_members` |
| `db.list_roles` | `db.admin.list_roles` |
| `db.revoke` | `db.admin.revoke` |
| `db.revoke_role` | `db.admin.revoke_role` |
| `db.role_exists` | `db.admin.role_exists` |
| `db.copy_from_csv` | `db.backup.copy_from_csv` |
| `db.copy_to_csv` | `db.backup.copy_to_csv` |
| `db.pg_dump` | `db.backup.pg_dump` |
| `db.pg_restore` | `db.backup.pg_restore` |
| `db.analyze` | `db.maint.analyze` |
| `db.explain` | `db.maint.explain` |
| `db.size` | `db.maint.size` |
| `db.table_size` | `db.maint.table_size` |
| `db.table_sizes` | `db.maint.table_sizes` |
| `db.vacuum` | `db.maint.vacuum` |
| `db.add_foreign_key` | `db.schema.add_foreign_key` |
| `db.add_primary_key` | `db.schema.add_primary_key` |
| `db.add_unique_constraint` | `db.schema.add_unique_constraint` |
| `db.columns_with_types` | `db.schema.columns_with_types` |
| `db.create_database` | `db.schema.create_database` |
| `db.create_extension` | `db.schema.create_extension` |
| `db.create_index` | `db.schema.create_index` |
| `db.create_schema` | `db.schema.create_schema` |
| `db.database_exists` | `db.schema.database_exists` |
| `db.drop_database` | `db.schema.drop_database` |
| `db.drop_extension` | `db.schema.drop_extension` |
| `db.drop_index` | `db.schema.drop_index` |
| `db.drop_schema` | `db.schema.drop_schema` |
| `db.drop_table` | `db.schema.drop_table` |
| `db.has_extension` | `db.schema.has_extension` |
| `db.list_columns` | `db.schema.list_columns` |
| `db.list_constraints` | `db.schema.list_constraints` |
| `db.list_databases` | `db.schema.list_databases` |
| `db.list_extensions` | `db.schema.list_extensions` |
| `db.list_indexes` | `db.schema.list_indexes` |
| `db.list_schemas` | `db.schema.list_schemas` |
| `db.list_tables` | `db.schema.list_tables` |
| `db.row_count` | `db.schema.row_count` |
| `db.schema_exists` | `db.schema.schema_exists` |
| `db.table_exists` | `db.schema.table_exists` |
| `db.table_info` | `db.schema.table_info` |
| `db.truncate_table` | `db.schema.truncate_table` |
| `db.create_spatial_index` | `db.spatial.create_spatial_index` |
| `db.list_geometry_columns` | `db.spatial.list_geometry_columns` |

**Total: 56 deprecated names** (timescale 6 / admin 11 / backup 4 / maint 6 / schema 27 / spatial 2).
All `async_db.*` flat names are identical (same 56, same accessor paths with `async_db` prefix).

## Upgrade Checklist

- [ ] Search codebase for deprecated flat names (see table above) and update to accessor paths
- [ ] Update any `import` statements if you imported deprecated names directly
- [ ] Run test suite: `uv run pytest tests/ -x -q -o addopts=""`
- [ ] Verify no `DeprecationWarning` in your test output

## Getting Help

If you encounter issues during migration:

1. Check that you're using a supported Python version (3.11+)
2. Review the [CHANGELOG.md](CHANGELOG.md) for the full list of changes
3. Open an issue on [GitHub](https://github.com/alkimya/pycopg/issues) with your use case

---

# Migration Guide: v0.2.0 to v0.3.0

This guide helps you upgrade from pycopg 0.2.0 to 0.3.0. Version 0.3.0 is a consolidation release that achieves full async/sync parity, adds resilience features, and includes one breaking change.

## Breaking Changes

### 1. GeoDataFrame CRS Validation (from_geodataframe)

**What changed:** `from_geodataframe()` now raises `ValueError` on unknown CRS instead of silently defaulting to SRID 4326.

**Why:** Silent defaults hide configuration errors and can lead to data corruption. Explicit errors ensure you always know which coordinate system your spatial data is using.

**Who is affected:** Anyone using `from_geodataframe()` with GeoDataFrames that have unknown or missing CRS. If you're already using standard EPSG codes like "EPSG:4326", your code will continue to work unchanged.

**Before (0.2.0):**
```python
import geopandas as gpd
from pycopg import Database

gdf = gpd.read_file("parcels.geojson")  # Unknown or missing CRS
db = Database.from_env()

# Silently defaulted to SRID 4326 - potential data corruption
db.from_geodataframe(gdf, "parcels")
```

**After (0.3.0):**
```python
import geopandas as gpd
from pycopg import Database

gdf = gpd.read_file("parcels.geojson")
db = Database.from_env()

# Now raises: ValueError("GeoDataFrame CRS could not be converted to SRID...")
# db.from_geodataframe(gdf, "parcels")  # This will raise an error

# FIX 1: Explicitly set the CRS if you know what it should be
gdf = gdf.set_crs("EPSG:4326")
db.from_geodataframe(gdf, "parcels")  # Works

# FIX 2: Or specify SRID directly
db.from_geodataframe(gdf, "parcels", srid=4326)  # Works
```

**Impact:** Low - only affects GeoDataFrames with unknown or missing CRS. Standard EPSG CRS codes like "EPSG:4326", "EPSG:3857", etc., continue to work automatically.

## New Features

### Full Async Parity

**What's new:** AsyncDatabase now has complete feature parity with Database. Every public method available in Database is now available in AsyncDatabase.

**DataFrame Operations:**
```python
from pycopg import AsyncDatabase

db = AsyncDatabase.from_env()

# Read table to DataFrame
df = await db.to_dataframe("users")
df = await db.to_dataframe(sql="SELECT * FROM users WHERE age > :min", params={"min": 18})

# Insert from DataFrame
import pandas as pd
df = pd.DataFrame({"name": ["Alice", "Bob"], "age": [30, 25]})
await db.from_dataframe(df, "users_backup", primary_key="id")

# Spatial data
gdf = await db.to_geodataframe("parcels")
await db.from_geodataframe(gdf, "parcels_copy", spatial_index=True)
```

**Admin Operations:**
```python
# Maintenance
await db.vacuum("users", analyze=True)
await db.analyze("orders")

# Query analysis
plan = await db.explain("SELECT * FROM users WHERE email = %s", ["test@example.com"])

# Indexes
await db.create_index("users", "email", unique=True)
await db.drop_index("idx_users_email")

# Tables
await db.create_table("logs", {"id": "SERIAL PRIMARY KEY", "message": "TEXT"})
await db.drop_table("temp_data")
```

**Backup Operations:**
```python
# Full backup
await db.pg_dump("backup.dump")
await db.pg_dump("backup.sql", format="plain")

# Restore
await db.pg_restore("backup.dump")

# CSV export/import
await db.copy_to_csv("users", "users.csv")
await db.copy_from_csv("users", "users.csv")
```

**Role Management:**
```python
# Create roles
await db.create_role("analyst", password="secret", login=True)
await db.create_role("readonly", login=False)

# Grant/revoke privileges
await db.grant("SELECT", "users", "readonly")
await db.grant("ALL", "orders", "analyst")
await db.revoke("INSERT", "users", "readonly")

# Role membership
await db.grant_role("readonly", "analyst")
await db.list_role_grants("analyst")
```

**PostGIS Operations:**
```python
# Spatial indexes
await db.create_spatial_index("parcels", "geometry")

# List geometry columns
columns = await db.list_geometry_columns()
```

**TimescaleDB Operations:**
```python
# Create hypertables
await db.create_hypertable("events", "timestamp", chunk_time_interval="1 week")

# Compression
await db.enable_compression("events", segment_by="device_id", order_by="timestamp DESC")
await db.add_compression_policy("events", compress_after="30 days")

# Retention
await db.add_retention_policy("logs", drop_after="90 days")

# List hypertables
tables = await db.list_hypertables()
info = await db.hypertable_info("events")
```

### Retry/Backoff for Resilience

**What's new:** Automatic retry with exponential backoff for transient connection errors. No configuration needed - it just works.

**How it works:**
```python
from pycopg import Database, AsyncDatabase

# Retry automatically enabled on connect()
db = Database.from_env()
# On connection failure: retries 3 times with exponential backoff (1-10s)

# Same for async
db = AsyncDatabase.from_env()
# Automatically retries on OperationalError (connection failures)
```

**Details:**
- 3 retry attempts (initial attempt + 2 retries)
- Exponential backoff: wait 1s, then 2.7s, then 7.4s
- Only retries on `OperationalError` (transient connection failures)
- Does not retry on `ProgrammingError` (SQL syntax errors, etc.)
- Applies to `Database.connect()` and `AsyncDatabase.connect()` only
- Connection pools already have built-in reconnection handling

### Statement Timeout

**What's new:** Configurable query timeout to prevent runaway queries from consuming resources.

**Basic usage:**
```python
from pycopg import Database, Config

config = Config.from_env()
config.statement_timeout = 30000  # 30 seconds (in milliseconds)
db = Database(config)

# Queries exceeding 30s will be cancelled automatically
# db.execute("SELECT pg_sleep(60)")  # Raises exception after 30s
```

**With URL:**
```python
db = Database.from_url(
    "postgresql://user:pass@localhost:5432/mydb",
    statement_timeout=30000
)
```

**Recommended values:**
- Web API endpoints: 5000-10000ms (5-10s)
- Background jobs: 60000-300000ms (1-5 minutes)
- Data warehousing: 600000+ (10+ minutes)

### Configurable Batch Size

**What's new:** Control the batch size for insert operations to optimize memory usage and performance.

**Usage:**
```python
from pycopg import Database

db = Database.from_env()

# Default batch size is 1000
db.insert_batch("users", large_dataset)

# For memory-constrained environments or very large rows
db.insert_batch("users", large_dataset, batch_size=500)

# For small rows and high performance
db.insert_batch("users", large_dataset, batch_size=5000)
```

**When to adjust:**
- Large rows (many columns, JSONB, TEXT): decrease to 100-500
- Small rows (few columns, simple types): increase to 2000-5000
- Memory errors: decrease batch size
- Performance tuning: benchmark different values

## Upgrade Checklist

- [ ] Review breaking changes above
- [ ] Update `from_geodataframe()` calls to handle CRS explicitly if needed
- [ ] Test that GeoDataFrames have valid CRS before insertion
- [ ] Optional: Configure `statement_timeout` for query protection
- [ ] Optional: Explore new async DataFrame/admin/backup methods if using AsyncDatabase
- [ ] Optional: Adjust `batch_size` if experiencing memory issues or want performance tuning
- [ ] Run test suite to verify compatibility

## Getting Help

If you encounter issues during migration:

1. Check that you're using a supported Python version (3.11+)
2. Review the [CHANGELOG.md](CHANGELOG.md) for full list of changes
3. Open an issue on [GitHub](https://github.com/alkimya/pycopg/issues) with your use case

---

# Migration Guide: v0.3.x to v0.4.0

This guide helps you upgrade from pycopg 0.3.x to 0.4.0. Version 0.4.0 adds spatial helpers,
full sync/async parity, and custom exception types. There are three breaking changes.

## Breaking Changes

### 1. AsyncDatabase engine URL (psycopg_async driver)

**Affected users:** Anyone inspecting or passing through `AsyncDatabase._async_engine` URLs.

**What changed:** The async engine now uses the `postgresql+psycopg_async://` URL scheme (was
`postgresql+psycopg://`). This is the correct driver for async psycopg v3.

**Impact:** Low. Only affects code that reads or logs `async_engine.url`. The API
(`execute`, `connect`, etc.) is unchanged — you do not need to update connection strings
passed to `AsyncDatabase.from_env()` or `AsyncDatabase.from_url()`.

### 2. AsyncDatabase.close() now disposes the engine

**What changed:** `close()` now calls `await engine.dispose()`. Previously it was a no-op.

**Impact:** Any code that called `close()` and then attempted to use the same
`AsyncDatabase` instance again will now fail — the engine is disposed. This was already
incorrect behavior: `close()` semantics have always implied the object should not be
used afterward. Treat this as a bug fix rather than a behavior change.

### 3. Custom exception types replace RuntimeError/ValueError

**What changed:** Several methods now raise domain-specific exceptions instead of
`RuntimeError` or `ValueError`:

| Method | Old exception | New exception |
|--------|---------------|---------------|
| `create_extension()` when extension is missing | `RuntimeError` | `ExtensionNotAvailable` |
| `create_database()` when database already exists | `RuntimeError` | `DatabaseExists` |
| Other extension-requiring methods | `RuntimeError` | `ExtensionNotAvailable` |

**Migration:** Update `except` clauses:

```python
# Before (0.3.x)
try:
    db.create_extension("postgis")
except RuntimeError:
    pass

# After (0.4.0)
from pycopg import ExtensionNotAvailable
try:
    db.create_extension("postgis")
except ExtensionNotAvailable:
    pass
```

```python
# Before (0.3.x)
try:
    db.create_database("mydb")
except RuntimeError:
    pass

# After (0.4.0)
from pycopg import DatabaseExists
try:
    db.create_database("mydb")
except DatabaseExists:
    pass
```

**Impact:** Medium. Code with broad `except Exception` or `except PycopgError` catch-all
clauses is unaffected. Only explicit `except RuntimeError` or `except ValueError` blocks
that catch database-domain errors need updating.

## Upgrade Checklist

- [ ] Review breaking changes above
- [ ] Search codebase for `except RuntimeError` near `create_extension` / `create_database`
  calls and update to `except ExtensionNotAvailable` / `except DatabaseExists`
- [ ] Import new exception types: `from pycopg import ExtensionNotAvailable, DatabaseExists`
- [ ] If you inspect `async_engine.url` anywhere, update expected URL scheme to
  `postgresql+psycopg_async://`
- [ ] Run test suite to verify compatibility

## New in 0.4.0

- `db.spatial.*` / `async_db.spatial.*`: 11 spatial helpers (contains, within, intersects,
  dwithin, distance, nearest, area, perimeter, centroid, buffer, transform)
- Full sync/async API parity (all public methods now available on both `Database` and `AsyncDatabase`)
- `PooledDatabase.execute` commits results before returning (fixes `INSERT ... RETURNING`)

## Getting Help

If you encounter issues during migration:

1. Check that you're using a supported Python version (3.11+)
2. Review the [CHANGELOG.md](CHANGELOG.md) for the full list of changes
3. Open an issue on [GitHub](https://github.com/alkimya/pycopg/issues) with your use case

---

# Migration Guide: v0.4.x to v0.5.0

This guide covers upgrading from pycopg 0.4.x to 0.5.0. Version 0.5.0 is a purely additive
release — there are **no breaking changes**. Existing code continues to work without modification.

## Breaking Changes

None. All changes in 0.5.0 are new additive features.

## New Features

### ETL Pipeline Runner (`db.etl.*` / `async_db.etl.*`)

Version 0.5.0 adds a full ETL pipeline runner with run tracking, accessible via the new
`db.etl` and `async_db.etl` lazy properties.

**Define a pipeline:**
```python
from pycopg import Database, Pipeline

db = Database.from_env()

pipeline = Pipeline(
    source="SELECT id, name, value FROM staging_data",
    target="analytics_results",
    load_mode="upsert",
    conflict_columns=["id"],
)
```

**Run the pipeline:**
```python
from pycopg import RunResult

result = db.etl.run(pipeline)
print(result.status)          # "success"
print(result.rows_extracted)  # rows read from source
print(result.rows_loaded)     # rows written to target
```

**Query run history:**
```python
# Last 100 runs for a pipeline (newest first)
runs = db.etl.history("my_pipeline")

# Most recent run only
last = db.etl.last_run("my_pipeline")
```

**Dry run (no data written):**
```python
result = db.etl.run(pipeline, dry_run=True)
print(result.status)    # "dry_run"
print(result.run_id)    # None (not recorded)
```

**Async usage (full parity):**
```python
from pycopg import AsyncDatabase

async_db = AsyncDatabase.from_env()
result = await async_db.etl.run(pipeline)
runs   = await async_db.etl.history("my_pipeline")
last   = await async_db.etl.last_run("my_pipeline")
```

**Transform callables:**
```python
import pandas as pd

def clean(df: pd.DataFrame) -> pd.DataFrame:
    return df.dropna()

pipeline = Pipeline(
    source="staging_data",
    target="clean_data",
    load_mode="replace",
    transform=clean,       # single callable, or a list of callables
)
```

Async transforms dispatch sync callables via `asyncio.to_thread` — no event-loop blocking.

**New top-level exports:**
```python
from pycopg import (
    ETLAccessor,
    AsyncETLAccessor,
    Pipeline,
    RunResult,
    ETLError,
    ETLTargetNotFoundError,
    ETLTransformError,
)
```

**Run-tracking table (`pipeline_runs`):** Created automatically on the first `run()` call.
You can also create it explicitly before the first run:
```python
db.etl.init()
```

## Upgrade Checklist

- [ ] No breaking changes — no action required for existing code
- [ ] Optional: explore the new `db.etl.*` / `async_db.etl.*` ETL namespace
- [ ] Optional: import `Pipeline`, `RunResult` from `pycopg` top-level if using ETL features
- [ ] Run test suite to verify compatibility: `uv run pytest tests/ -x -q`

## Getting Help

If you encounter issues during migration:

1. Check that you're using a supported Python version (3.11+)
2. Review the [CHANGELOG.md](CHANGELOG.md) for the full list of changes
3. Open an issue on [GitHub](https://github.com/alkimya/pycopg/issues) with your use case
