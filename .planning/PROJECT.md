# pycopg — High-Level Python API for PostgreSQL/PostGIS/TimescaleDB

## What This Is

A production-ready Python library providing high-level sync and async APIs for PostgreSQL, PostGIS, and TimescaleDB. Version 0.3.0 achieved full AsyncDatabase/Database feature parity with 30+ async methods, production resilience (retry/backoff, timeouts), and 72.76% test coverage. Published on PyPI as a standalone library.

## Core Value

Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ Sync Database class with full PostgreSQL operations (DDL, DML, schema, admin) — v0.2.0
- ✓ Async Database class with core operations (execute, insert, select, transactions) — v0.2.0
- ✓ Connection pooling (sync + async) via psycopg_pool — v0.2.0
- ✓ Config dataclass with from_env/from_url/from_params factory methods — v0.2.0
- ✓ Migration system with versioned SQL files (up/down) — v0.2.0
- ✓ DataFrame integration (to_dataframe, from_dataframe) in sync Database — v0.2.0
- ✓ PostGIS/GeoDataFrame support in sync Database — v0.2.0
- ✓ TimescaleDB hypertable/compression support in sync Database — v0.2.0
- ✓ SQL identifier validation and injection prevention — v0.2.0
- ✓ Custom exception hierarchy — v0.2.0
- ✓ Sphinx documentation with ReadTheDocs — v0.2.0
- ✓ GitHub Actions CI for PyPI publish — v0.2.0
- ✓ Session mode connection cleanup guaranteed even if close() raises — v0.3.0
- ✓ Session mode implicit transaction detection for all TransactionStatus states — v0.3.0
- ✓ Migration file parser logs skipped files at WARNING level — v0.3.0
- ✓ TimescaleDB methods validate extension exists before executing — v0.3.0
- ✓ GeoDataFrame SRID inference raises error on unknown CRS (breaking change) — v0.3.0
- ✓ Full AsyncDatabase feature parity: DataFrame, Admin, Backup, Roles, PostGIS, TimescaleDB — v0.3.0
- ✓ Retry/backoff policy with tenacity for transient connection errors — v0.3.0
- ✓ statement_timeout support in Config — v0.3.0
- ✓ Configurable insert batch size (default 1000) — v0.3.0
- ✓ Test coverage >70% with real PostgreSQL (achieved 72.76%) — v0.3.0
- ✓ Edge case testing: migration rollback, session exceptions, pool stress, PostGIS errors — v0.3.0
- ✓ Automated async parity verification test — v0.3.0
- ✓ CHANGELOG, MIGRATION guide, updated README, rebuilt Sphinx docs — v0.3.0

### Active

<!-- Current scope. Building toward these. -->

(No active requirements — next milestone not yet defined)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Refactor Database into smaller classes/mixins — keep monolith for now, restructure in future version
- Query result caching — premature optimization, defer to post-ETL
- Named parameters (:name syntax) — nice-to-have, not blocking ETL
- Computed/virtual column support — advanced schema feature, defer
- Dynamic pool sizing — current fixed sizing is acceptable
- SQLAlchemy as optional dependency — would require significant refactoring
- ORM/model layer — duplicates SQLAlchemy, maintenance nightmare
- Query builder/fluent API — never as good as SQLAlchemy Core
- Schema diff/auto-migration — complex, error-prone, out of scope
- Multi-database support — pycopg is PostgreSQL-specific by design

## Context

Shipped v0.3.0 with 13,648 LOC Python across 15 source files.
Tech stack: Python 3.11+, psycopg 3, psycopg_pool, pandas, geopandas, tenacity, Sphinx.
Test coverage: 72.76% with real PostgreSQL (pycopg_test database).
Breaking change: `from_geodataframe` raises ValueError on unknown CRS instead of silently defaulting to SRID 4326.

**Known tech debt (from audit):**
- Git tag v0.3.0 not yet created (user action)
- PyPI publication not completed (requires tag push to trigger CI)
- Database class remains monolithic (~2300 lines) — acceptable for now

**Deferred to future milestone (v2 requirements from REQUIREMENTS.md):**
- API-01: Named parameter support (:name syntax)
- API-02: Connection health checks
- API-03: Structured logging
- API-04: Transaction isolation level control
- API-05: Savepoint support (nested transactions)
- API-06: Sync result streaming
- ARCH-01: Refactor Database into mixins
- ARCH-02: Dynamic connection pool sizing
- ETL features (explicitly next milestone)

## Constraints

- **Tech stack**: Python 3.11+, psycopg 3, tenacity added in v0.3.0
- **Independence**: pycopg is a standalone PyPI library — no Solaris/MarketStream dependencies
- **Test infra**: Real PostgreSQL required for tests (Docker or local)
- **Breaking changes**: Must be documented in CHANGELOG and migration guide

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Full async parity over partial | Users expect same API surface in both sync and async | ✓ Good — 30+ methods added, parity verified by automated test |
| Breaking changes allowed | Clean API more valuable than backwards compat at v0.3.0 | ✓ Good — SRID validation breaking change is cleaner, documented in MIGRATION.md |
| Keep monolithic Database class | Restructuring is high risk/effort, not needed for consolidation | ✓ Good — monolith works, parity achieved without refactor |
| Real PostgreSQL for tests | Mock-based tests don't catch real driver/DB interaction bugs | ✓ Good — caught real issues, coverage 23% → 72.76% |
| Retry/backoff as only new feature | Scope control — consolidation release, not feature release | ✓ Good — tenacity integration clean, no scope creep |
| Use run_sync for pandas/geopandas in async | Sync libraries in async context, thread pool delegation | ✓ Good — clean pattern, no blocking |
| Retry only on OperationalError | Connection failures retry, logic errors don't | ✓ Good — correct granularity |
| 3 attempts with 1-10s exponential backoff | Balance reliability vs latency | ✓ Good — configurable defaults |
| Track known parity exceptions | Some methods intentionally sync-only or async-only | ✓ Good — documented in parity test |
| Keep a Changelog 1.1.0 format | Industry standard, structured, parseable | ✓ Good — clean CHANGELOG.md |

---
*Last updated: 2026-02-11 after v0.3.0 milestone*
