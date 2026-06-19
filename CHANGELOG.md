# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.0] - 2026-06-19

### Added

- `db.timescale.*` / `async_db.timescale.*` namespace: 6 TimescaleDB methods
  (`create_hypertable`, `enable_compression`, `add_compression_policy`,
  `add_retention_policy`, `list_hypertables`, `hypertable_info`); full sync/async parity
- `db.admin.*` / `async_db.admin.*` namespace: 11 role & permission methods
  (`create_role`, `drop_role`, `role_exists`, `list_roles`, `alter_role`, `grant_role`,
  `revoke_role`, `grant`, `revoke`, `list_role_members`, `list_role_grants`); full sync/async parity
- `db.maint.*` / `async_db.maint.*` namespace: 6 maintenance methods
  (`size`, `table_size`, `table_sizes`, `vacuum`, `analyze`, `explain`); full sync/async parity
- `db.backup.*` / `async_db.backup.*` namespace: 4 dump/restore/CSV methods
  (`pg_dump`, `pg_restore`, `copy_to_csv`, `copy_from_csv`); full sync/async parity
- `db.schema.*` / `async_db.schema.*` namespace: 27 DDL + introspection methods
  (databases 4, extensions 4, schemas 4, tables+columns 8, constraints+indexes 7); full sync/async parity
- `TimescaleAccessor`, `AsyncTimescaleAccessor`, `AdminAccessor`, `AsyncAdminAccessor`,
  `MaintAccessor`, `AsyncMaintAccessor`, `BackupAccessor`, `AsyncBackupAccessor`,
  `SchemaAccessor`, `AsyncSchemaAccessor` exported from the `pycopg` top-level namespace

### Deprecated

- All 56 legacy flat names on `db.*` / `async_db.*` (the methods moved to accessor namespaces)
  now emit `DeprecationWarning` pointing to the new accessor path (e.g.
  `db.create_hypertable` warns: "use db.timescale.create_hypertable"). Scheduled for
  removal in **v0.7.0**. See [MIGRATION.md](MIGRATION.md) for the complete flat-name →
  accessor-path table.

### Changed

- Calling the deprecated flat `db.create_spatial_index` or `db.list_geometry_columns`
  now raises `ExtensionNotAvailable` early (via the `db.spatial` PostGIS guard) when
  PostGIS is not installed, rather than a raw psycopg error. A strictly clearer failure
  mode on the deprecated path.

## [0.5.0] - 2026-06-15

### Added

- `db.etl.*` / `async_db.etl.*` namespace: ETL pipeline runner (`run`, `history`, `last_run`,
  `dry_run`) with full sync/async parity; both accessors live under a lazy-initialised property
  following the `db.spatial` pattern
- `Pipeline` frozen dataclass: `source` (SQL string or table name), `target` (table name),
  `load_mode` (`append` / `replace` / `upsert`), `conflict_columns` (upsert key), `transform`
  (None / single callable / list of callables), `extract_limit`, `schema`, `pipeline_name`
- `pipeline_runs` run-tracking table: auto-created on first `db.etl.run()` call; can also be
  created explicitly with `db.etl.init()`; stores status, row counts, timing, and error details
- `RunResult` frozen dataclass: `run_id`, `pipeline_name`, `status`, `rows_extracted`,
  `rows_loaded`, `started_at`, `finished_at`, `error`
- `ETLAccessor` and `AsyncETLAccessor` lazy accessors (sync and async) with identical public
  method surfaces (`run`, `history`, `last_run`, `init`)
- `ETLError`, `ETLTargetNotFoundError`, `ETLTransformError` exception hierarchy for typed
  ETL error handling
- `ETLAccessor`, `AsyncETLAccessor`, `RunResult`, `Pipeline` exported from the `pycopg`
  top-level namespace
- Async transform dispatch via `asyncio.to_thread` — sync transform callables do not block
  the event loop when used with `AsyncETLAccessor`
- Zero new runtime dependencies — the ETL layer is built on top of existing psycopg3 and
  pandas dependencies

## [0.4.0] - 2026-06-14

### Added

- `db.spatial.*` / `async_db.spatial.*` namespace: 11 spatial helpers (`contains`, `within`,
  `intersects`, `dwithin`, `distance`, `nearest`, `area`, `perimeter`, `centroid`, `buffer`,
  `transform`) with full sync/async parity; pure SQL builders, PostGIS guard, GeoDataFrame
  output via `into="gdf"`, four geometry input forms (`point=`, `wkt=`, `geojson=`, `ref=`)
- `SpatialAccessor` and `AsyncSpatialAccessor` exported from `pycopg` top-level
- Async methods previously missing: `add_primary_key`, `add_foreign_key`,
  `add_unique_constraint`, `truncate_table`, `drop_extension`, `database_exists`,
  `list_databases`, `create`, `create_from_env` on `AsyncDatabase`
- Sync methods previously missing: `insert_many`, `upsert_many`, `stream`, `notify`
  on `Database`
- `PooledDatabase.execute` now commits results before returning so `INSERT ... RETURNING`
  results are not rolled back on pool return
- `DatabaseExists` exception in the public exception hierarchy
- `validate_timestamp()`, `validate_privileges()`, `validate_object_type()`,
  `validate_csv_option()`, `validate_extension_name()` in `pycopg.utils`
- `interrogate` enforced in CI (docstring coverage ≥ 95%)
- mypy type checking in CI (non-blocking)
- `uv.lock` and `.python-version` for reproducible contributor environments

### Changed

- **BREAKING**: Async engine now uses `postgresql+psycopg_async://` driver URL (was
  `postgresql+psycopg://`) — fixes async query execution
- **BREAKING**: `AsyncDatabase.close()` now disposes the SQLAlchemy async engine
  (was a no-op) — connections are properly released
- **BREAKING**: Custom exception types now raised instead of `RuntimeError`/`ValueError`
  for domain errors: `ExtensionNotAvailable` (was RuntimeError), `TableNotFound` (was
  RuntimeError), `DatabaseExists` (was RuntimeError) — see MIGRATION.md
- `create_extension(schema=...)` and `create_schema(owner=...)` signatures aligned
  between sync and async (parameters added to async)
- `table_info` and `list_roles` semantics aligned sync/async
- All docstrings migrated to numpydoc format (Summary/Parameters/Returns/Raises)
- Dev tooling migrated to `uv` (`uv sync`, `uv run`, `uv build`); `pip install pycopg`
  for end users unchanged
- CI test and publish workflows use `uv` for dependency management and build

### Fixed

- `session()` context manager no longer masks the original exception when commit/close
  fails in the finally block
- Migration `_apply` and `rollback` now run inside an explicit atomic transaction
  (fixes partial-apply on error)
- Subprocess helpers use `os.environ` correctly (was `subprocess.os.environ`)
- Async `create_role` validates identifiers before executing (closes residual injection gap)
- Async `from_dataframe`/`from_geodataframe` now correctly apply `primary_key` (was silently
  ignoring it)
- `__version__` resolved via `importlib.metadata` (was stuck at `0.1.0`)

### Security

- Identifier validation extended to all remaining unvalidated parameters (see v0.3.1 for the
  initial hotfix; this release closes the residual gaps in `create_role` async path)

## [0.3.1] - 2026-06-06

### Security

- Fix SQL injection in methods that interpolated identifiers without validation:
  `drop_index()`, `create_spatial_index()`, `vacuum()`, `analyze()`,
  `create_extension()` (name and schema), `to_dataframe()`/`to_geodataframe()`
  (table form), and async `insert_many()`/`upsert_many()` (column names). All now
  validate identifiers via `validate_identifier(s)` before building SQL.
- Fix SQL injection via unvalidated interval arguments in `add_compression_policy()`
  and `add_retention_policy()` — both now call `validate_interval()`.
- Fix SQL injection via `valid_until` in `create_role()`/`alter_role()` — now
  validated with the new `validate_timestamp()`.
- Restrict `grant()`/`revoke()` `privileges` and `object_type` to a whitelist via
  the new `validate_privileges()` and `validate_object_type()`.
- Validate CSV `delimiter`/`null_string`/`encoding` options in `copy_to_csv()`/
  `copy_from_csv()` via the new `validate_csv_option()`.
- All fixes applied identically to sync `Database` and async `AsyncDatabase` (parity).

### Added

- New validation helpers in `pycopg.utils`: `validate_timestamp()`,
  `validate_privileges()`, `validate_object_type()`, `validate_csv_option()`,
  `validate_extension_name()` (allows hyphenated names such as `uuid-ossp`).
- `tests/test_sql_injection.py`: regression tests asserting malicious input is
  rejected before reaching the database (sync and async).

### Fixed

- `__version__` was stuck at `0.1.0`; now reflects the package version (`0.3.1`).

## [0.3.0] - 2026-02-11

### Added

- Full AsyncDatabase parity: async to_dataframe(), from_dataframe(), to_geodataframe(), from_geodataframe()
- Async admin methods: create_table(), drop_table(), create_index(), drop_index(), list_indexes(), list_constraints(), drop_schema(), table_sizes()
- Async maintenance methods: vacuum(), analyze(), explain()
- Async backup methods: pg_dump(), pg_restore(), copy_to_csv(), copy_from_csv()
- Async database lifecycle: create_database(), drop_database()
- Async role management: create_role(), drop_role(), alter_role(), grant(), revoke(), grant_role(), revoke_role(), list_role_members(), list_role_grants()
- Async PostGIS methods: create_spatial_index(), list_geometry_columns()
- Async TimescaleDB methods: create_hypertable(), enable_compression(), add_compression_policy(), add_retention_policy(), list_hypertables(), hypertable_info()
- Retry/backoff with tenacity for transient connection errors (3 attempts, exponential backoff 1-10s)
- Configurable statement_timeout in Config for query timeout protection
- Configurable batch_size for insert operations (default 1000)
- Pool reconnection timeout configuration (reconnect_timeout parameter)
- schema_exists() on AsyncDatabase

### Changed

- **BREAKING:** from_geodataframe() raises ValueError on unknown CRS instead of silently defaulting to SRID 4326

### Fixed

- Session cleanup succeeds even if close() raises exception (prevents connection leaks)
- Session mode correctly detects implicit transactions for all TransactionStatus states
- Migration file parser logs skipped files at WARNING level instead of silent continue
- All TimescaleDB methods validate extension exists before executing operations
- GeoDataFrame SRID inference raises clear error on unknown CRS with actionable message

### Improved

- Test coverage increased from ~50% to 72.76% with real PostgreSQL integration tests
- Async parity verified via automated test (all Database public methods have AsyncDatabase equivalents)
- Pool connection cycling and reconnection handling improved
- Error messages for PostGIS operations without extension installed

## [0.2.0] - 2026-01-15

Initial release with sync/async Database, connection pooling, migrations, PostGIS, TimescaleDB support.

[Unreleased]: https://github.com/alkimya/pycopg/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/alkimya/pycopg/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/alkimya/pycopg/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/alkimya/pycopg/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/alkimya/pycopg/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/alkimya/pycopg/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/alkimya/pycopg/releases/tag/v0.2.0
