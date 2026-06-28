# API Stability

pycopg follows [Semantic Versioning 2.0.0](https://semver.org/).
At **1.0.0** the public API is frozen: no breaking changes will be made without a major version bump.

See [API Stability](https://pycopg.readthedocs.io/en/latest/stability.html) on ReadTheDocs for
the online version of this document.

## SemVer Contract

pycopg uses MAJOR.MINOR.PATCH versioning:

- **MAJOR** — incompatible API changes (breaking changes listed here)
- **MINOR** — new functionality added in a backward-compatible manner
- **PATCH** — backward-compatible bug fixes

### Breaking vs Non-Breaking Changes

| Change | Classification |
|--------|----------------|
| Removing a public method or parameter | BREAKING (major bump) |
| Renaming a parameter without a deprecation alias | BREAKING (major bump) |
| Adding an optional parameter with a default value | Non-breaking (minor bump) |
| Changing a parameter default value | BREAKING (major bump) |
| Changing a return type | BREAKING (major bump) |
| Changing the exception type raised by a method | BREAKING (major bump) |
| Bug fix that changes documented behaviour | Patch (noted in CHANGELOG) |

## Deprecation Policy

Deprecated names are kept for the **entirety of 1.x** and removed only in 2.0.
Every deprecated call emits `DeprecationWarning` on access or import. Update your code
before 2.0 to silence these warnings.

**Deprecated names introduced in 1.0.0:**

- Spatial `where=` parameter → use `filter=` instead (removed in 2.0)
- Exception aliases `ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier`, `DatabaseExists` → use `*Error` canonical names (removed in 2.0)
- `time_bucket` / `time_bucket_gapfill` `where=` parameter → use `filter=` instead (removed in 2.0)

**Note on deprecation warning timing (D-08):** The deprecated exception name aliases
(`ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier`, `DatabaseExists`) emit
`DeprecationWarning` at import/access time — when you write `from pycopg.exceptions import
ExtensionNotAvailable` or `pycopg.ExtensionNotAvailable`. The warning does **not** fire at
`except OldName:` catch time (this is intentional — the `except` clause receives the same class
object and catching still works). This behaviour is per Python PEP 562 module `__getattr__`
semantics and is not a gap.

## Stable API Contract

The table below documents the positional-vs-keyword-only boundary for every public method
in the pycopg 1.0 API. This is the result of the FREEZE-03 consistency audit (Phase 41, Plan 04).

**Legend:**

- **Positional** — can be passed without a keyword name (required args, or the documented
  "primitive I/O" carve-out below)
- **Keyword-only** — must be passed as `param=value`; enforced by `*` separator in the
  function signature

**D2/D5 carve-out:** The raw-SQL execution primitives — `execute`, `fetch_one`, `fetch_val`,
`fetch_all`, `stream` (both `Database` and `AsyncDatabase`) and `maint.explain` — intentionally
keep `params` (and `autocommit` on `execute`) as positional-with-default. The `(sql, params)`
two-positional convention is established and expected by users of the primitive I/O layer.

### Database / AsyncDatabase — Flat Core

| Method | Positional args | Keyword-only params |
|--------|-----------------|---------------------|
| `execute` | `sql`, `params`, `autocommit` | _(none — D2/D5 carve-out)_ |
| `execute_many` | `sql`, `params_seq` | _(none — both required)_ |
| `fetch_one` | `sql`, `params` | _(none — D2/D5 carve-out)_ |
| `fetch_val` | `sql`, `params` | _(none — D2/D5 carve-out)_ |
| `fetch_all` | `sql`, `params` | _(none — D2/D5 carve-out)_ |
| `stream` | `sql`, `params`, `batch_size` | _(none — D2/D5 carve-out)_ |
| `insert_many` | `table`, `rows` | `schema`, `on_conflict` |
| `upsert_many` | `table`, `rows`, `conflict_columns` | `update_columns`, `schema` |
| `upsert` | `table`, `row`, `conflict_columns` | `update_columns`, `schema` |
| `delete_where` | `table`, `where` | `schema` |
| `update_where` | `table`, `values`, `where` | `schema` |
| `exists` | `table`, `where` | `schema` |
| `count` | `table` | `where`, `schema` |
| `notify` | `channel` | `payload` |
| `insert_batch` | `table`, `rows` | `schema`, `on_conflict`, `batch_size` |
| `copy_insert` | `table`, `rows` | `schema`, `columns` |
| `paginate` | `table`, `limit` | `offset`, `order_by`, `where`, `descending`, `schema` |
| `from_dataframe` | `df`, `table` | `schema`, `if_exists`, `primary_key`, `index`, `dtype` |
| `to_dataframe` | _(none)_ | `table`, `schema`, `sql`, `params` |
| `from_geodataframe` | `gdf`, `table` | `schema`, `if_exists`, `primary_key`, `spatial_index`, `geometry_column`, `srid` |
| `to_geodataframe` | _(none)_ | `table`, `schema`, `sql`, `geometry_column`, `params` |

### db.spatial.* / async_db.spatial.*

| Method | Positional args | Keyword-only params |
|--------|-----------------|---------------------|
| `contains` | `table` | `geom`, `schema`, `filter`, `into`, `srid` |
| `intersects` | `table` | `geom`, `schema`, `filter`, `into`, `srid` |
| `dwithin` | `table` | `geom`, `distance`, `schema`, `filter`, `into`, `srid` |
| `distance` | `table` | `geom`, `schema`, `filter`, `into`, `srid` |
| `nearest` | `table` | `geom`, `schema`, `filter`, `into`, `limit`, `srid` |
| `area` | `table` | `geom`, `schema`, `filter`, `into` |
| `perimeter` | `table` | `geom`, `schema`, `filter`, `into` |
| `centroid` | `table` | `geom`, `schema`, `filter`, `into` |
| `buffer` | `table` | `geom`, `distance`, `schema`, `filter`, `into` |
| `transform` | `table` | `geom`, `srid`, `schema`, `filter`, `into` |
| `within` | `left_table`, `left_geom`, `right_table`, `right_geom` | `schema`, `filter`, `into` |
| `create_spatial_index` | `table` | `column`, `schema`, `name` |
| `list_geometry_columns` | _(none)_ | `schema` |

**Note on `within`:** 4 required positional identifiers (`left_table`, `left_geom`,
`right_table`, `right_geom`) stay positional. `schema=` is keyword-only (FREEZE-03 D1 clean break).

### db.schema.* / async_db.schema.*

| Method | Positional args | Keyword-only params |
|--------|-----------------|---------------------|
| `create_database` | `name` | `owner`, `template` |
| `drop_database` | `name` | `if_exists` |
| `database_exists` | `name` | _(none)_ |
| `list_databases` | _(none)_ | _(none)_ |
| `create_extension` | `name` | `schema`, `if_not_exists` |
| `drop_extension` | `name` | `if_exists`, `cascade` |
| `list_extensions` | _(none)_ | _(none)_ |
| `has_extension` | `name` | _(none)_ |
| `create_schema` | `name` | `if_not_exists`, `owner` |
| `drop_schema` | `name` | `if_exists`, `cascade` |
| `list_schemas` | _(none)_ | _(none)_ |
| `schema_exists` | `name` | _(none)_ |
| `list_tables` | _(none)_ | `schema` |
| `table_exists` | `name` | `schema` |
| `list_columns` | `table` | `schema` |
| `columns_with_types` | `table` | `schema` |
| `drop_table` | `name` | `schema`, `if_exists`, `cascade` |
| `truncate_table` | `name` | `schema`, `cascade` |
| `table_info` | `name` | `schema` |
| `row_count` | `name` | `schema` |
| `add_primary_key` | `table`, `columns` | `schema`, `name` |
| `add_foreign_key` | `table`, `columns`, `ref_table`, `ref_columns` | `schema`, `ref_schema`, `name`, `on_delete`, `on_update` |
| `add_unique_constraint` | `table`, `columns` | `schema`, `name` |
| `create_index` | `table`, `columns` | `schema`, `name`, `unique`, `method`, `if_not_exists` |
| `drop_index` | `name` | `schema`, `if_exists` |
| `list_indexes` | `table` | `schema` |
| `list_constraints` | `table` | `schema` |
| `primary_key` | `table` | `schema` |
| `foreign_keys` | `table` | `schema` |
| `sequences` | _(none)_ | `schema` |
| `views` | _(none)_ | `schema` |
| `describe` | `table` | `schema` |

### db.timescale.* / async_db.timescale.*

| Method | Positional args | Keyword-only params |
|--------|-----------------|---------------------|
| `create_hypertable` | `table`, `time_column` | `schema`, `chunk_time_interval`, `if_not_exists`, `migrate_data` |
| `enable_compression` | `table` | `segment_by`, `order_by`, `schema` |
| `add_compression_policy` | `table` | `compress_after`, `schema` |
| `add_retention_policy` | `table`, `drop_after` | `schema` |
| `list_hypertables` | _(none)_ | _(none)_ |
| `hypertable_info` | `table` | `schema` |
| `show_chunks` | `table` | `older_than`, `newer_than`, `schema` |
| `drop_chunks` | `table` | `older_than`, `newer_than`, `schema`, `dry_run` |
| `add_dimension` | `table`, `column` | `partition_type`, `number_partitions`, `chunk_interval`, `schema`, `if_not_exists` |
| `add_reorder_policy` | `table`, `index_name` | `schema`, `if_not_exists` |
| `create_continuous_aggregate` | `view_name`, `select_sql` | `schema`, `materialized_only`, `with_no_data` |
| `refresh_continuous_aggregate` | `view_name` | `window_start`, `window_end`, `schema` |
| `add_continuous_aggregate_policy` | `view_name`, `start_offset`, `end_offset` | `schedule_interval`, `schema`, `if_not_exists` |
| `time_bucket` | `table`, `time_column`, `bucket_width`, `aggregates` | `filter`, `schema`, `into` |
| `time_bucket_gapfill` | `table`, `time_column`, `bucket_width`, `start`, `finish`, `aggregates` | `filter`, `schema`, `into` |

**Note on `time_bucket` / `time_bucket_gapfill` `filter=`:** The `filter=` parameter accepts a
raw SQL fragment (structural SQL authored by the caller), not a dict-equality predicate. This
was renamed from `where=` in 1.0 (D3 decision, FREEZE-03). The old `where=` emits
`DeprecationWarning` through 1.x and is removed in 2.0.

### db.admin.* / async_db.admin.*

| Method | Positional args | Keyword-only params |
|--------|-----------------|---------------------|
| `create_role` | `name` | `password`, `login`, `superuser`, `createdb`, `createrole`, `inherit`, `replication`, `connection_limit`, `valid_until`, `in_roles`, `if_not_exists` |
| `drop_role` | `name` | `if_exists` |
| `role_exists` | `name` | _(none)_ |
| `list_roles` | _(none)_ | `include_system` |
| `alter_role` | `name` | `password`, `login`, `superuser`, `createdb`, `createrole`, `connection_limit`, `valid_until`, `rename_to` |
| `grant_role` | `role`, `member` | `with_admin` |
| `revoke_role` | `role`, `member` | _(none)_ |
| `grant` | `privileges`, `on`, `to` | `object_type`, `schema`, `with_grant_option` |
| `revoke` | `privileges`, `on`, `from_role` | `object_type`, `schema`, `cascade` |
| `list_role_members` | `role` | _(none)_ |
| `list_role_grants` | `role` | _(none)_ |

### db.maint.* / async_db.maint.*

| Method | Positional args | Keyword-only params |
|--------|-----------------|---------------------|
| `size` | _(none)_ | `pretty` |
| `table_size` | `table` | `schema`, `pretty` |
| `table_sizes` | _(none)_ | `schema`, `limit` |
| `vacuum` | _(none)_ | `table`, `schema`, `analyze`, `full` |
| `analyze` | _(none)_ | `table`, `schema` |
| `explain` | `sql`, `params`, `analyze`, `format` | _(none — D2/D5 carve-out)_ |

### db.backup.* / async_db.backup.*

| Method | Positional args | Keyword-only params |
|--------|-----------------|---------------------|
| `pg_dump` | `output_file` | `format`, `schema_only`, `data_only`, `tables`, `exclude_tables`, `schemas`, `compress`, `jobs` |
| `pg_restore` | `input_file` | `clean`, `if_exists`, `create`, `data_only`, `schema_only`, `tables`, `schemas`, `jobs`, `no_owner`, `no_privileges` |
| `copy_to_csv` | `table`, `output_file` | `schema`, `columns`, `delimiter`, `header`, `null_string`, `encoding` |
| `copy_from_csv` | `table`, `input_file` | `schema`, `columns`, `delimiter`, `header`, `null_string`, `encoding` |

### db.etl.* / async_db.etl.*

| Method | Positional args | Keyword-only params |
|--------|-----------------|---------------------|
| `init` | _(none)_ | _(none)_ |
| `history` | `name` | `limit` |
| `last_run` | `name` | _(none)_ |
| `run` | `pipeline` | `dry_run` |

## Supported Versions

Version floors are grounded in `pyproject.toml` constraints — no version is invented.

| Component | Floor | Recommended |
|-----------|-------|-------------|
| Python | 3.11 (`requires-python = ">=3.11"`) | 3.12+ |
| PostgreSQL | 13 | 16+ |
| PostGIS | 3.0 (hard floor) | 3.2+ (`ST_MakeValid method=structure` requires PostGIS 3.2, per D-02) |
| TimescaleDB | 2.0 | 2.10+ |
| psycopg | 3.1.0 (`psycopg>=3.1.0`) | latest |
| psycopg_pool | 3.2.0 (`psycopg_pool>=3.2.0`) | latest |
| pandas | 2.0.0 (`pandas>=2.0.0`) | latest |
| geopandas | 0.14.0 (`geopandas>=0.14.0`, optional `geo` extra) | latest |

**PostgreSQL floor note:** pycopg is tested against PostgreSQL 13+. Features such as
`pg_dump --jobs` require PostgreSQL 10+ (satisfied by the 13 floor).

**PostGIS floor note:** PostGIS 3.0 is the hard minimum — it provides `ST_MakeValid` and
the GeoDataFrame geometry type support used by `from_geodataframe` / `to_geodataframe`.
PostGIS 3.2+ is recommended for full `ST_MakeValid method=structure` support.

**TimescaleDB note:** TimescaleDB feature availability depends on your edition:

- Apache edition (free): `time_bucket`, chunk management, hypertables, compression, retention
- TSL (Timescale Licensed): `time_bucket_gapfill`, continuous aggregate policies, reorder policies

Some methods raise `FeatureNotSupported` on the Apache edition — see the
[TimescaleDB docs](timescaledb.md) for per-method edition requirements.

## API Stability Tiers

| API Surface | Stability | Notes |
|-------------|-----------|-------|
| `Database.*` flat core | **Stable** | Frozen at 1.0 |
| `AsyncDatabase.*` flat core | **Stable** | Full parity with sync |
| `db.spatial.*` | **Stable** | PostGIS helpers; requires `[geo]` extra |
| `db.schema.*` | **Stable** | DDL + introspection |
| `db.timescale.*` | **Stable** | TimescaleDB helpers |
| `db.etl.*` | **Stable** | ETL pipeline runner |
| `db.admin.*` | **Stable** | Role management |
| `db.maint.*` | **Stable** | Maintenance operations |
| `db.backup.*` | **Stable** | Backup/restore |
| Module-level `build_*_sql` builders | **Stable** | SQL fragment builders in `pycopg.spatial` |
| `pycopg.exceptions.*Error` | **Stable** | `ExtensionNotAvailableError`, `TableNotFoundError`, `InvalidIdentifierError`, `DatabaseExistsError` |
| `Pipeline`, `RunResult` | **Stable** | ETL data classes |
| Internal `_*` names | **Private** | No stability guarantee; may change at any time |

For migration help when upgrading from earlier versions, see [MIGRATION.md](https://github.com/alkimya/pycopg/blob/main/MIGRATION.md).
