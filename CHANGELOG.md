# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.10.1] - 2026-06-27

### Fixed

- `refresh_continuous_aggregate` (sync and async) no longer fails with
  `psycopg.errors.IndeterminateDatatype` on a full refresh (the default — both
  `window_start` and `window_end` `None`) against a Community/TSL TimescaleDB.
  Absent window bounds are now rendered as the SQL literal `NULL` rather than
  untyped bind parameters, which TimescaleDB's `"any"`-typed window arguments
  could not type-infer under psycopg's extended protocol. Present `datetime`
  bounds are still passed as typed parameters. The bug was present since the
  continuous-aggregate API shipped in v0.8.0 and was masked on Apache-licensed
  builds (which raise `FeatureNotSupported` before parameter binding).

## [0.10.0] - 2026-06-26

### Changed

- `from_dataframe` (sync and async) now streams rows via the psycopg COPY
  protocol using a Hybrid DDL+COPY approach (`df.head(0).to_sql` for schema
  creation, then COPY for row streaming), yielding higher-throughput bulk
  insertion for large DataFrames. The `if_exists`, `index`, `primary_key`,
  and `dtype` contract is preserved. See `benchmarks/` and
  `benchmarks/README.md` for a reproducible, on-demand comparison of
  all four insertion paths.
- The ETL `append` and `replace` load paths now stream rows inline via COPY
  on the transaction cursor, eliminating the intermediate
  `astype(object) + to_dict(orient="records")` materialization. The `upsert`
  path continues to use `INSERT … ON CONFLICT DO UPDATE` (unchanged).
- `insert_batch` hoists the invariant row-placeholder string out of the
  per-row loop (byte-exact SQL and parameter order preserved).
- Test coverage ratchet raised from 94% to 95% (`--cov-fail-under=95`);
  measured at 95.74%.

### Fixed

- **Audit BLOCKERs (5 security/correctness fixes):** `explain()` format
  argument is now validated against a whitelist (`text`, `json`, `xml`,
  `yaml`) before EXPLAIN SQL is constructed; `validate_identifiers` is now
  called before `df.to_sql()` in `from_dataframe` and before `gdf.to_postgis()`
  in `from_geodataframe` (sync and async); `pg_dump` and `pg_restore`
  CLI argument expansion now rejects values starting with `-` or containing
  control characters (flag-injection guard); `pg_restore` now raises
  `FileNotFoundError` for missing non-`.sql` input files instead of misrouting
  them to psql.
- Three previously-flaky tests (`test_async_transaction_fix`,
  `test_create_spatial_index_name_parameter`, and the watermark bound-param
  test) now pass deterministically under `pytest-randomly` via fixture-isolation
  fixes (UUID table names, connection teardown in `finally`, pool-state reset).
- Residual ruff errors (`N818` suppressed via per-file-ignore on
  `pycopg/exceptions.py`, `W291`, `F841`, `E722`) resolved; `ruff check
  pycopg tests` now exits 0.
- `TableNotFound` now has a real raise site in `truncate_table` (sync and
  async): it is raised when the target table does not exist, resolving the
  exported-but-never-raised inconsistency.
- Advisory code-review warnings from v0.8.0 and v0.9.0 closed or justified
  in-milestone (connection-limit integer guard, async `stream()` session
  parity, libpq option sanitization, `TimescaleError` export, watermark
  decoder unknown-tag branch).

## [0.9.0] - 2026-06-25

### Added

**CRUD ergonomics (7 new methods on `db.*` / `async_db.*`, flat on `Database`/`AsyncDatabase`):**

- `upsert(self, table, row, conflict_columns, update_columns=None, schema="public") -> dict | None` — upsert
  a single row via `INSERT ... ON CONFLICT DO UPDATE` and return the affected row (or `None` if no row was
  returned). Column names are validated via `validate_identifiers`; values bound as `%s`.
- `delete_where(self, table, where, schema="public") -> int` — delete rows matching the given equality
  conditions; returns the number of rows deleted. `where` must be a non-empty dict (destructive guard —
  use `db.schema.truncate_table` to affect all rows).
- `update_where(self, table, values, where, schema="public") -> int` — update rows matching the equality
  conditions in `where` using the column-value mapping in `values`; returns the number of rows updated.
  Both `values` and `where` must be non-empty dicts (destructive guard).
- `exists(self, table, where, schema="public") -> bool` — return `True` if at least one row matches the
  equality conditions; `False` otherwise. `where` must be non-empty (an existence check with no predicate
  is meaningless).
- `count(self, table, where=None, schema="public") -> int` — count rows in a table, optionally filtered
  by equality conditions. When `where` is `None`, all rows are counted without a WHERE clause.
- `fetch_all(self, sql, params=None) -> list[dict]` — execute SQL and return all rows as a list of dicts.
  Thin complement to `fetch_one`; uses the connection's `dict_row` row factory so every row is already a
  plain dict.
- `paginate(self, table, limit, offset=0, order_by=None, where=None, descending=False, schema="public") -> list[dict]` —
  return a page of rows from a table. `order_by` accepts a column name or list of column names (each
  validated via `validate_identifiers`); `descending=True` adds `DESC` to the ORDER BY clause.

**Schema introspection (5 new methods on `db.schema.*` / `async_db.schema.*`):**

- `primary_key(self, table, schema="public") -> dict | None` — return a dict describing the primary key
  constraint (`constraint_name`, `columns`) for the given table, or `None` if no primary key exists.
- `foreign_keys(self, table, schema="public") -> list[dict]` — return a list of dicts, one per foreign key
  constraint, each containing `constraint_name`, `columns`, `ref_table`, and `ref_columns`.
- `sequences(self, schema="public") -> list[str]` — return a list of sequence names owned by the given
  schema, sorted alphabetically.
- `views(self, schema="public") -> list[str]` — return a list of view names in the given schema, sorted
  alphabetically. Includes both regular and materialized views.
- `describe(self, table, schema="public") -> dict` — compose `table_info`, `primary_key`, `foreign_keys`,
  and `list_indexes` into a single flat dict with keys `columns`, `primary_key`, `foreign_keys`, and
  `indexes`. No new SQL — anti-drift guarantee (D-04).

All 12 methods have full sync/async parity on `AsyncDatabase` and `AsyncSchemaAccessor`. Zero new runtime
dependencies.

## [0.8.0] - 2026-06-23

### Added

**Chunk & dimension management** (4 new methods on `db.timescale.*` and `async_db.timescale.*`):

- `db.timescale.show_chunks(table, older_than=None, newer_than=None)` — list fully-qualified
  chunk names for a hypertable, sorted oldest-first by range start.
- `db.timescale.drop_chunks(table, older_than=None, newer_than=None, dry_run=False)` — drop
  chunks matching the given time bounds. `dry_run=True` returns the list that *would* be dropped
  without removing any data. Raises `ValueError` when both bounds are `None` (DESTRUCTIVE/IRREVERSIBLE
  safety guard). Passing only one bound is valid.
- `db.timescale.add_dimension(table, column, partition_type="hash", number_partitions=None,
  chunk_interval=None, if_not_exists=True)` — add a space partition (`by_hash`) or time partition
  (`by_range`) using the TimescaleDB 2.x `add_dimension` builder form; `partition_type` selects the
  builder (`hash`↔`number_partitions`, `range`↔`chunk_interval`). Raises `TimescaleError` on
  duplicate-dimension conflicts when `if_not_exists=False`.
- `db.timescale.add_reorder_policy(table, index_name, if_not_exists=True)` — register a
  background reorder policy for a hypertable chunk index. Requires a Community/TSL-licensed
  TimescaleDB build; raises `FeatureNotSupported` on Apache-licensed builds.

**Continuous aggregate lifecycle** (3 new methods):

- `db.timescale.create_continuous_aggregate(view_name, select_sql, materialized_only=True,
  with_no_data=False)` — create a continuous aggregate view. `select_sql` must contain
  `time_bucket(` (heuristic guard; raises `ValueError` otherwise). Uses a dedicated
  `autocommit=True` connection to satisfy TimescaleDB's transaction-block restriction.
  Requires Community/TSL build; raises `FeatureNotSupported` on Apache.
- `db.timescale.refresh_continuous_aggregate(view_name, window_start=None, window_end=None)` —
  manually refresh a continuous aggregate over the specified window. `window_start` and
  `window_end` must be `datetime` objects or `None`; raises `ValueError` when both are supplied
  but `window_start >= window_end`. Requires Community/TSL build.
- `db.timescale.add_continuous_aggregate_policy(view_name, start_offset, end_offset,
  schedule_interval="1 hour", if_not_exists=True)` — register a background refresh policy for a
  continuous aggregate. Uses plain `execute` (no autocommit seam). Requires Community/TSL build.

**Query helpers** (2 new methods):

- `db.timescale.time_bucket(table, time_column, bucket_width, aggregates, where=None,
  into="df")` — time-bucket aggregation query helper; returns a `pandas.DataFrame` (default
  `into="df"`) or a `list[dict]` (`into="rows"`). `aggregates` is required structural SQL
  (the projected bucket columns/aggregate expressions); any other `into` value raises `ValueError`.
- `db.timescale.time_bucket_gapfill(table, time_column, bucket_width, start, finish, aggregates,
  where=None, into="df")` — gap-filling time-bucket query; `start` and `finish` are required
  positional `datetime` arguments (TSDB planner hook requires them explicitly). Returns a
  `pandas.DataFrame` (default) or `list[dict]`. Requires Community/TSL build; raises
  `FeatureNotSupported` on Apache.

All 9 methods have full sync/async parity on `AsyncTimescaleAccessor`. Zero new runtime
dependencies. For usage examples and the license note for Community/TSL-gated methods, see the
[TimescaleDB advanced guide](docs/timescaledb.md).

## [0.7.0] - 2026-06-22

### Breaking

All 56 flat method names on `Database` and `AsyncDatabase` that were deprecated in v0.6.0
are permanently removed. Calling any removed flat name (e.g. `db.create_hypertable`,
`db.list_tables`, `db.vacuum`) now raises `AttributeError` with no warning and no delegation.

**Migration:** Replace each flat call with its accessor-namespaced equivalent.
See [MIGRATION.md](MIGRATION.md#migration-guide-v060--v070) for the complete flat-name →
accessor-path table covering all 56 removed names
(timescale 6 / admin 11 / backup 4 / maint 6 / schema 27 / spatial 2).

### Added

- **Incremental ETL via watermark-based loading** — `Pipeline` now accepts an optional
  `incremental_column` field. When set, `load_mode` must be `"upsert"` (append and replace
  are rejected at construction with `ValueError`). Each run extracts only rows where
  `incremental_column > <last watermark>`, using `max(incremental_column)` from the raw
  extracted batch (before transforms) as the new high-water mark.
- First run (no prior watermark) performs a full load then records `max(incremental_column)`.
  Failed loads do not advance the watermark; empty batches preserve it unchanged.
- Watermark persisted as a typed JSONB envelope in the already-reserved
  `pipeline_runs.watermark` column — zero new runtime dependencies.
- `RunResult.watermark_used` and `RunResult.watermark_recorded` fields surface the prior and
  new watermarks for each run (also visible via `history()` and `last_run()`).
- `dry_run=True` previews the incremental filter and the new `max(incremental_column)` without
  writing a run row or advancing the watermark.
- Full sync/async parity: `ETLAccessor` and `AsyncETLAccessor` implement identical incremental
  behaviour.

See [docs/etl.md](docs/etl.md) for the full incremental loading guide including worked
examples, watermark-column requirements, and backfill/reset instructions.

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

[Unreleased]: https://github.com/alkimya/pycopg/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/alkimya/pycopg/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/alkimya/pycopg/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/alkimya/pycopg/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/alkimya/pycopg/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/alkimya/pycopg/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/alkimya/pycopg/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/alkimya/pycopg/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/alkimya/pycopg/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/alkimya/pycopg/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/alkimya/pycopg/releases/tag/v0.2.0
