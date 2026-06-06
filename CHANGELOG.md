# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/alkimya/pycopg/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/alkimya/pycopg/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/alkimya/pycopg/releases/tag/v0.2.0
