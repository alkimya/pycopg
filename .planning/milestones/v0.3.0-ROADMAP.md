# Roadmap: pycopg v0.3.0

## Overview

This roadmap delivers pycopg v0.3.0, a consolidation release that achieves full AsyncDatabase/Database feature parity, fixes all known bugs from CONCERNS.md, adds production-grade resilience with retry/backoff, and strengthens test coverage above 70%. The journey progresses from fixing critical bugs, through systematic async method implementation across three focused phases (DataFrame, Admin, Extensions), adding resilience features, comprehensive testing, and finally documentation and release. This hardens pycopg for production use before future ETL features.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Bug Fixes & Foundation** - Fix critical bugs blocking async parity work
- [x] **Phase 2: AsyncDatabase DataFrame Parity** - Complete DataFrame/GeoDataFrame async methods
- [x] **Phase 3: AsyncDatabase Admin/Backup Parity** - Complete admin, DDL, backup/restore async methods
- [x] **Phase 4: AsyncDatabase Extensions Parity** - Complete PostGIS, TimescaleDB, roles async methods
- [x] **Phase 5: Resilience & Configuration** - Add retry/backoff, timeouts, configurable batch sizes
- [x] **Phase 6: Test Coverage** - Comprehensive test infrastructure and edge case testing
- [x] **Phase 7: Documentation & Release** - Update docs, changelog, migration guide, publish v0.3.0

## Phase Details

### Phase 1: Bug Fixes & Foundation
**Goal**: Critical bugs resolved and connection lifecycle hardened, unblocking async parity work
**Depends on**: Nothing (first phase)
**Requirements**: BUG-01, BUG-02, BUG-03, BUG-04, BUG-05
**Success Criteria** (what must be TRUE):
  1. Session mode connection cleanup succeeds even if close() raises exception (no leaked connections)
  2. Session mode correctly detects implicit transactions for all TransactionStatus states
  3. Migration file parser logs skipped files at WARNING level instead of silent continue
  4. All TimescaleDB methods validate extension exists before executing operations
  5. GeoDataFrame SRID inference raises clear error on unknown CRS instead of silently defaulting to 4326
**Plans:** 2 plans

Plans:
- [x] 01-01-PLAN.md — Fix session cleanup and transaction detection (BUG-01, BUG-02)
- [x] 01-02-PLAN.md — Fix migration logging, TimescaleDB validation, SRID inference (BUG-03, BUG-04, BUG-05)

### Phase 2: AsyncDatabase DataFrame Parity
**Goal**: AsyncDatabase has full DataFrame and GeoDataFrame support matching Database
**Depends on**: Phase 1
**Requirements**: ASYNC-01, ASYNC-02, ASYNC-03, ASYNC-04
**Success Criteria** (what must be TRUE):
  1. User can call async to_dataframe() on AsyncDatabase to retrieve query results as pandas DataFrame
  2. User can call async from_dataframe() on AsyncDatabase to insert DataFrame rows to table
  3. User can call async to_geodataframe() on AsyncDatabase to retrieve spatial data as GeoDataFrame
  4. User can call async from_geodataframe() on AsyncDatabase to insert GeoDataFrame with geometries
**Plans:** 2 plans

Plans:
- [x] 02-01-PLAN.md — Implement async_engine, to_dataframe, from_dataframe, to_geodataframe, from_geodataframe on AsyncDatabase
- [x] 02-02-PLAN.md — Unit tests for all async DataFrame/GeoDataFrame methods and SRID validation

### Phase 3: AsyncDatabase Admin/Backup Parity
**Goal**: AsyncDatabase has full admin, DDL, backup/restore operations matching Database
**Depends on**: Phase 2
**Requirements**: ASYNC-05, ASYNC-06, ASYNC-07, ASYNC-08, ASYNC-09, ASYNC-10, ASYNC-11, ASYNC-12, ASYNC-13, ASYNC-14, ASYNC-24, ASYNC-25
**Success Criteria** (what must be TRUE):
  1. User can call async pg_dump() and pg_restore() for database backup/restore
  2. User can call async copy_to_csv() and copy_from_csv() for bulk data export/import
  3. User can call async create_database(), drop_database() for database lifecycle
  4. User can call async create_table(), drop_table(), create_index(), drop_index() for DDL operations
  5. User can call async vacuum(), analyze(), explain() for maintenance and query analysis
  6. User can call async table_sizes(), index_sizes(), drop_schema(), schema_exists() for stats and schema operations
**Plans:** 2 plans

Plans:
- [x] 03-01-PLAN.md — Add DDL/admin/stats async methods (drop_table, create_index, drop_index, list_indexes, list_constraints, drop_schema, table_sizes, create_database, drop_database) + tests
- [x] 03-02-PLAN.md — Add maintenance/backup/CSV async methods (vacuum, analyze, explain, pg_dump, pg_restore, copy_to_csv, copy_from_csv) + tests

### Phase 4: AsyncDatabase Extensions Parity
**Goal**: AsyncDatabase has full PostGIS, TimescaleDB, and role management support matching Database
**Depends on**: Phase 3
**Requirements**: ASYNC-15, ASYNC-16, ASYNC-17, ASYNC-18, ASYNC-19, ASYNC-20, ASYNC-21, ASYNC-22, ASYNC-23
**Success Criteria** (what must be TRUE):
  1. User can call async create_role(), drop_role(), alter_role() for role lifecycle
  2. User can call async grant(), revoke(), grant_role(), revoke_role() for privilege management
  3. User can call async list_role_members(), list_role_grants() for role inspection
  4. User can call async create_spatial_index(), list_geometry_columns() for PostGIS operations
  5. User can call async create_hypertable(), enable_compression(), add_retention_policy(), list_hypertables() for TimescaleDB operations
**Plans:** 2 plans

Plans:
- [x] 04-01-PLAN.md — Add async role management, privilege, and inspection methods + tests
- [x] 04-02-PLAN.md — Add async PostGIS and TimescaleDB methods + update from_geodataframe spatial index + tests

### Phase 5: Resilience & Configuration
**Goal**: Production-grade error handling with retry/backoff and configurable operation parameters
**Depends on**: Phase 4
**Requirements**: RESL-01, RESL-02, RESL-03
**Success Criteria** (what must be TRUE):
  1. User can configure retry policy with exponential backoff that handles transient connection errors
  2. User can set statement_timeout in Config to prevent runaway queries
  3. User can configure insert batch size (default remains 1000 but is configurable)
  4. Transient network errors trigger automatic retry with backoff instead of immediate failure
**Plans:** 2 plans

Plans:
- [x] 05-01-PLAN.md — Add tenacity retry/backoff, statement_timeout, batch size config, pool reconnection params
- [x] 05-02-PLAN.md — Tests for retry behavior, statement_timeout, batch size defaults, pool reconnection params

### Phase 6: Test Coverage
**Goal**: Test coverage exceeds 70% with real PostgreSQL and all edge cases covered
**Depends on**: Phase 5
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04, TEST-05, TEST-06
**Success Criteria** (what must be TRUE):
  1. pytest reports test coverage exceeds 70% measured against real PostgreSQL (pycopg_test database)
  2. Migration rollback edge cases pass tests (deleted files, syntax errors, first migration)
  3. Session mode exception scenarios pass tests (cleanup failures, nested sessions, disconnects)
  4. Pool stress scenarios pass tests (exhaustion, cycling, timeout, broken connections)
  5. Spatial operations without PostGIS extension raise graceful errors with helpful messages
  6. Automated async parity test validates all Database public methods have AsyncDatabase equivalent
**Plans:** 2 plans

Plans:
- [x] 06-01-PLAN.md — Coverage infrastructure, Config/Base coverage, Database integration tests, async parity verification (TEST-01, TEST-06)
- [x] 06-02-PLAN.md — Migration rollback edge cases, session exceptions, pool stress, PostGIS error handling (TEST-02, TEST-03, TEST-04, TEST-05)

### Phase 7: Documentation & Release
**Goal**: Documentation updated, migration guide published, v0.3.0 released on PyPI
**Depends on**: Phase 6
**Requirements**: DOC-01, DOC-02, DOC-03, DOC-04, DOC-05
**Success Criteria** (what must be TRUE):
  1. README.md reflects all 0.3.0 API changes and new resilience features
  2. Sphinx documentation rebuilt with complete API reference for all async methods
  3. CHANGELOG.md contains 0.3.0 entry with all breaking changes clearly listed
  4. Migration guide exists showing before/after examples for breaking changes from 0.2.0 to 0.3.0
  5. Version bumped to 0.3.0 in pyproject.toml and package published on PyPI via CI workflow
**Plans:** 2 plans

Plans:
- [ ] 07-01-PLAN.md — Create CHANGELOG.md, MIGRATION.md, and update README.md with v0.3.0 features (DOC-01, DOC-03, DOC-04)
- [ ] 07-02-PLAN.md — Update Sphinx docs, version bump to 0.3.0, rebuild HTML, verify release readiness (DOC-02, DOC-05)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Bug Fixes & Foundation | 2/2 | ✓ Complete | 2026-02-11 |
| 2. AsyncDatabase DataFrame Parity | 2/2 | ✓ Complete | 2026-02-11 |
| 3. AsyncDatabase Admin/Backup Parity | 2/2 | ✓ Complete | 2026-02-11 |
| 4. AsyncDatabase Extensions Parity | 2/2 | ✓ Complete | 2026-02-11 |
| 5. Resilience & Configuration | 2/2 | ✓ Complete | 2026-02-11 |
| 6. Test Coverage | 2/2 | ✓ Complete | 2026-02-11 |
| 7. Documentation & Release | 2/2 | ✓ Complete | 2026-02-11 |
