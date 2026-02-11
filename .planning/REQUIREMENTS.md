# Requirements: pycopg v0.3.0

**Defined:** 2026-02-11
**Core Value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

## v1 Requirements

Requirements for v0.3.0 release. Each maps to roadmap phases.

### Bug Fixes

- [ ] **BUG-01**: Session mode connection cleanup guaranteed even if close() raises exception
- [ ] **BUG-02**: Session mode implicit transaction detection fixed for all TransactionStatus states
- [ ] **BUG-03**: Migration file parser logs skipped files at WARNING level instead of silent continue
- [ ] **BUG-04**: All TimescaleDB methods validate extension exists before executing
- [ ] **BUG-05**: GeoDataFrame SRID inference raises error on unknown CRS instead of silently defaulting to 4326

### Async Parity — DataFrame

- [ ] **ASYNC-01**: AsyncDatabase has async to_dataframe() method
- [ ] **ASYNC-02**: AsyncDatabase has async from_dataframe() method
- [ ] **ASYNC-03**: AsyncDatabase has async to_geodataframe() method
- [ ] **ASYNC-04**: AsyncDatabase has async from_geodataframe() method

### Async Parity — Backup/Restore

- [ ] **ASYNC-05**: AsyncDatabase has async pg_dump() method
- [ ] **ASYNC-06**: AsyncDatabase has async pg_restore() method
- [ ] **ASYNC-07**: AsyncDatabase has async copy_to_csv() method
- [ ] **ASYNC-08**: AsyncDatabase has async copy_from_csv() method

### Async Parity — Admin/DDL

- [ ] **ASYNC-09**: AsyncDatabase has async create_database() method
- [ ] **ASYNC-10**: AsyncDatabase has async drop_database() method
- [ ] **ASYNC-11**: AsyncDatabase has async create_table() / drop_table() methods
- [ ] **ASYNC-12**: AsyncDatabase has async create_index() / drop_index() / list_indexes() methods
- [ ] **ASYNC-13**: AsyncDatabase has async list_constraints() method
- [ ] **ASYNC-14**: AsyncDatabase has async vacuum() / analyze() / explain() methods

### Async Parity — Roles/Privileges

- [ ] **ASYNC-15**: AsyncDatabase has async create_role() / drop_role() / alter_role() methods
- [ ] **ASYNC-16**: AsyncDatabase has async grant() / revoke() methods
- [ ] **ASYNC-17**: AsyncDatabase has async grant_role() / revoke_role() methods
- [ ] **ASYNC-18**: AsyncDatabase has async list_role_members() / list_role_grants() methods

### Async Parity — PostGIS

- [ ] **ASYNC-19**: AsyncDatabase has async create_spatial_index() method
- [ ] **ASYNC-20**: AsyncDatabase has async list_geometry_columns() method

### Async Parity — TimescaleDB

- [ ] **ASYNC-21**: AsyncDatabase has async create_hypertable() method
- [ ] **ASYNC-22**: AsyncDatabase has async enable_compression() / add_retention_policy() methods
- [ ] **ASYNC-23**: AsyncDatabase has async list_hypertables() method

### Async Parity — Stats/Sizes

- [ ] **ASYNC-24**: AsyncDatabase has async table_sizes() / index_sizes() methods
- [ ] **ASYNC-25**: AsyncDatabase has async drop_schema() / schema_exists() methods

### Resilience

- [ ] **RESL-01**: User can configure retry policy with exponential backoff for transient connection errors
- [ ] **RESL-02**: User can set statement_timeout in Config to prevent runaway queries
- [ ] **RESL-03**: User can configure insert batch size (default 1000)

### Test Coverage

- [ ] **TEST-01**: Test coverage exceeds 70% measured against real PostgreSQL (pycopg_test)
- [ ] **TEST-02**: Migration rollback edge cases covered (deleted files, syntax errors, first migration)
- [ ] **TEST-03**: Session mode exception scenarios covered (cleanup failures, nested sessions, disconnects)
- [ ] **TEST-04**: Pool stress scenarios covered (exhaustion, cycling, timeout, broken connections)
- [ ] **TEST-05**: Spatial operations without PostGIS tested (graceful error handling)
- [ ] **TEST-06**: Async parity test validates all Database methods have AsyncDatabase equivalent

### Documentation & Release

- [ ] **DOC-01**: README updated reflecting all 0.3.0 API changes and new features
- [ ] **DOC-02**: Sphinx documentation rebuilt with complete API reference
- [ ] **DOC-03**: CHANGELOG entry for 0.3.0 with all breaking changes listed
- [ ] **DOC-04**: Migration guide from 0.2.0 to 0.3.0 with before/after examples
- [ ] **DOC-05**: Version bumped to 0.3.0 and released on PyPI via CI

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### API Enhancements

- **API-01**: Named parameter support (:name syntax converts to %s internally)
- **API-02**: Connection health checks (validate pool connections before checkout)
- **API-03**: Comprehensive structured logging (connection lifecycle, query execution)
- **API-04**: Transaction isolation level control (SERIALIZABLE, READ COMMITTED)
- **API-05**: Savepoint support (nested transactions)
- **API-06**: Sync result streaming (async already has it)

### Architecture

- **ARCH-01**: Refactor Database into smaller classes/mixins (AdminMixin, SpatialMixin, etc.)
- **ARCH-02**: Dynamic connection pool sizing based on queue depth

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| ORM/model layer | Duplicates SQLAlchemy, maintenance nightmare |
| Query builder/fluent API | Never as good as SQLAlchemy Core |
| Schema diff/auto-migration | Complex, error-prone, out of scope |
| Multi-database support | pycopg is PostgreSQL-specific by design |
| Query result caching | Application concern, not library responsibility |
| ETL features | Explicitly next milestone after 0.3.0 |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| BUG-01 | — | Pending |
| BUG-02 | — | Pending |
| BUG-03 | — | Pending |
| BUG-04 | — | Pending |
| BUG-05 | — | Pending |
| ASYNC-01 | — | Pending |
| ASYNC-02 | — | Pending |
| ASYNC-03 | — | Pending |
| ASYNC-04 | — | Pending |
| ASYNC-05 | — | Pending |
| ASYNC-06 | — | Pending |
| ASYNC-07 | — | Pending |
| ASYNC-08 | — | Pending |
| ASYNC-09 | — | Pending |
| ASYNC-10 | — | Pending |
| ASYNC-11 | — | Pending |
| ASYNC-12 | — | Pending |
| ASYNC-13 | — | Pending |
| ASYNC-14 | — | Pending |
| ASYNC-15 | — | Pending |
| ASYNC-16 | — | Pending |
| ASYNC-17 | — | Pending |
| ASYNC-18 | — | Pending |
| ASYNC-19 | — | Pending |
| ASYNC-20 | — | Pending |
| ASYNC-21 | — | Pending |
| ASYNC-22 | — | Pending |
| ASYNC-23 | — | Pending |
| ASYNC-24 | — | Pending |
| ASYNC-25 | — | Pending |
| RESL-01 | — | Pending |
| RESL-02 | — | Pending |
| RESL-03 | — | Pending |
| TEST-01 | — | Pending |
| TEST-02 | — | Pending |
| TEST-03 | — | Pending |
| TEST-04 | — | Pending |
| TEST-05 | — | Pending |
| TEST-06 | — | Pending |
| DOC-01 | — | Pending |
| DOC-02 | — | Pending |
| DOC-03 | — | Pending |
| DOC-04 | — | Pending |
| DOC-05 | — | Pending |

**Coverage:**
- v1 requirements: 44 total
- Mapped to phases: 0
- Unmapped: 44

---
*Requirements defined: 2026-02-11*
*Last updated: 2026-02-11 after initial definition*
