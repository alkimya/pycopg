# Requirements: pycopg v0.8.0 — TimescaleDB avancé

**Defined:** 2026-06-22
**Core Value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

## v1 Requirements

Requirements for milestone v0.8.0. Each maps to exactly one roadmap phase. All methods live on
both `TimescaleAccessor` (sync) and `AsyncTimescaleAccessor` (async) under `db.timescale.*` /
`async_db.timescale.*`, following the established pure-builder + `validate_identifiers` + `%s`-params

+ lazy-accessor + sync/async-parity contract. Target baseline: **TimescaleDB 2.x**. Zero new runtime

dependencies. Coverage ratchet held ≥94% (baseline 95.11%).

### Chunk Management & Partitioning

+ [ ] **TS-ADV-04**: User can list a hypertable's chunks via `db.timescale.show_chunks(table, older_than=None, newer_than=None, schema="public")`, returning `list[str]` of chunk names
+ [ ] **TS-ADV-05**: User can drop chunks via `db.timescale.drop_chunks(table, older_than=None, newer_than=None, schema="public", dry_run=False)`, returning the dropped chunk names; **safety: raises `ValueError` when both bounds are None** (prevents full-table wipe); **`dry_run=True` previews via `show_chunks` without deleting**; docstring marks the operation DESTRUCTIVE/IRREVERSIBLE
+ [x] **TS-ADV-08**: User can add a partitioning dimension via `db.timescale.add_dimension(table, column, partition_type="hash", number_partitions=None, chunk_interval=None, schema="public", if_not_exists=True)` using the TimescaleDB 2.x `by_hash`/`by_range` form; construction-time `ValueError` enforces the hash↔number_partitions / range↔chunk_interval mutual-exclusivity
+ [x] **TS-ADV-09**: User can add a chunk-reorder background policy via `db.timescale.add_reorder_policy(table, index_name, schema="public", if_not_exists=True)`

### Continuous Aggregates (full lifecycle)

+ [ ] **TS-ADV-01**: User can create a continuous aggregate via `db.timescale.create_continuous_aggregate(view_name, select_sql, schema="public", materialized_only=True, with_no_data=False)`; **must run on a dedicated `connect(autocommit=True)` connection** (cannot execute inside a transaction block); `materialized_only` defaults to `True` (matches TSDB 2.13+ behavior)
+ [ ] **TS-ADV-02**: User can manually refresh a continuous aggregate via `db.timescale.refresh_continuous_aggregate(view_name, window_start=None, window_end=None, schema="public")` (`CALL`-based; both bounds None = full refresh); **must run on a dedicated `connect(autocommit=True)` connection**
+ [ ] **TS-ADV-03**: User can add an auto-refresh policy via `db.timescale.add_continuous_aggregate_policy(view_name, start_offset, end_offset, schedule_interval="1 hour", schema="public", if_not_exists=True)`

### Query Helpers

+ [x] **TS-ADV-06**: User can run a bucketed aggregation query via `db.timescale.time_bucket(table, time_column, bucket_width, aggregates, where=None, schema="public", into="df")`, returning a `DataFrame` (or `list[dict]` when `into="rows"`); `bucket_width` and `where` values parameterized as `%s`, identifiers validated, `aggregates` documented as structural SQL (not from untrusted input)
+ [x] **TS-ADV-07**: User can run a gap-filled bucketed query via `db.timescale.time_bucket_gapfill(table, time_column, bucket_width, start, finish, aggregates, where=None, schema="public", into="df")`, returning a `DataFrame`/`list[dict]`; **`start` and `finish` are required** (passed as explicit function arguments, not WHERE inference — `%s` planner-inference is structurally broken); `locf()`/`interpolate()` supplied inside the `aggregates` fragments

### Parity, Docs & Release

+ [x] **TS-ADV-10**: Full sync/async parity for all 9 new methods — `AsyncTimescaleAccessor` mirrors every method (async guard correctly `await`ed); enforced by `test_accessor_parity` over the existing `(TimescaleAccessor, AsyncTimescaleAccessor)` `ACCESSOR_PAIRS` entry
+ [ ] **REL-08**: Release v0.8.0 — README + Sphinx API docs cover the 9 new methods + an `docs/` time-series advanced section; CHANGELOG `[0.8.0]` Added entry; version bumped in both sources; 4 gates green (coverage ≥94, interrogate ≥95, Sphinx `-W`, no DeprecationWarnings); human-gated tag `v0.8.0` + OIDC publish + clean-venv install smoke

## Future Requirements

Deferred to a future release. Tracked but not in the current roadmap.

### TimescaleDB (deferred — out of this milestone's surface)

+ **TSDB-F01**: `drop_continuous_aggregate` / `remove_continuous_aggregate_policy` lifecycle removal (raw SQL works; low value)
+ **TSDB-F02**: `time_bucket` `origin`/`offset` alignment params (edge case)
+ **TSDB-F03**: `compress_chunk` / `decompress_chunk` manual per-chunk control (advanced operational)
+ **TSDB-F04**: `show_chunks` `created_before`/`created_after` physical-time filters (rarely needed)

### Incremental ETL follow-ups (deferred to a later ETL milestone — one feature family per milestone)

+ **ETL-INC-F01**: `initial_watermark` first-run bounding
+ **ETL-INC-F02**: configurable `>` vs `>=` boundary / lookback window
+ **ETL-INC-F03**: multi-column / composite watermarks
+ **ETL-INC-F04**: advisory-lock concurrency for `append` + incremental
+ **ETL-INC-F05**: CDC / WAL-based change capture

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
| ------- | ------ |
| `locf()` / `interpolate()` as first-class Python methods | Only valid inside a `time_bucket_gapfill` GROUP BY context; standalone wrappers would mislead. Supplied as SQL fragments in `aggregates`. |
| cagg waterfall chaining (cagg-on-cagg) as a dedicated API | User writes `FROM schema.lower_cagg` in `select_sql`; no extra surface needed. |
| Multi-database / cross-DB time-series | pycopg is single-PostgreSQL by design. |
| Query builder / fluent time-series API | `time_bucket`/`gapfill` are structured helpers, not a builder; pycopg is a wrapper, never a query builder. |
| TimescaleDB 1.x compatibility shims | Target is 2.x only; 1.x APIs (pre-materialized caggs, positional `add_dimension`) explicitly not supported. |
| ETL incremental follow-ups (F01–F05) in v0.8.0 | One feature family per milestone; v0.8.0 is TimescaleDB-only. Deferred to a later ETL milestone. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
| ----------- | ----- | ------ |
| TS-ADV-04 | Phase 30 | Complete |
| TS-ADV-05 | Phase 30 | Complete |
| TS-ADV-08 | Phase 30 | Complete |
| TS-ADV-09 | Phase 30 | Complete |
| TS-ADV-01 | Phase 31 | Complete |
| TS-ADV-02 | Phase 31 | Complete |
| TS-ADV-03 | Phase 31 | Complete |
| TS-ADV-06 | Phase 32 | Complete |
| TS-ADV-07 | Phase 32 | Complete |
| TS-ADV-10 | Phase 32 | Complete |
| REL-08 | Phase 33 | Pending |

**Coverage:**

+ v1 requirements: 11 total
+ Mapped to phases: 11
+ Unmapped: 0 ✓

---
*Requirements defined: 2026-06-22*
*Last updated: 2026-06-22 — Phase 30 complete; TS-ADV-04/05/08/09 marked complete*
