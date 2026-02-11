# pycopg v0.3.0 — Consolidation Release

## What This Is

A consolidation release of pycopg, the high-level Python API for PostgreSQL/PostGIS/TimescaleDB. Version 0.3.0 fixes all known tech debt and bugs from CONCERNS.md, achieves full AsyncDatabase feature parity with Database, brings test coverage above 70% with real PostgreSQL, adds retry/backoff for transient errors, and ships with updated documentation. This is a hardening release before future ETL features.

## Core Value

Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

## Requirements

### Validated

<!-- Shipped and confirmed valuable. -->

- ✓ Sync Database class with full PostgreSQL operations (DDL, DML, schema, admin) — existing v0.2.0
- ✓ Async Database class with core operations (execute, insert, select, transactions) — existing v0.2.0
- ✓ Connection pooling (sync + async) via psycopg_pool — existing v0.2.0
- ✓ Config dataclass with from_env/from_url/from_params factory methods — existing v0.2.0
- ✓ Migration system with versioned SQL files (up/down) — existing v0.2.0
- ✓ DataFrame integration (to_dataframe, from_dataframe) in sync Database — existing v0.2.0
- ✓ PostGIS/GeoDataFrame support in sync Database — existing v0.2.0
- ✓ TimescaleDB hypertable/compression support in sync Database — existing v0.2.0
- ✓ SQL identifier validation and injection prevention — existing v0.2.0
- ✓ Custom exception hierarchy — existing v0.2.0
- ✓ Sphinx documentation with ReadTheDocs — existing v0.2.0
- ✓ GitHub Actions CI for PyPI publish — existing v0.2.0

### Active

<!-- Current scope. Building toward these. -->

- [ ] Full AsyncDatabase feature parity (DataFrame, backup, admin, spatial, timescale methods)
- [ ] Fix session mode transaction handling bug (implicit transaction detection)
- [ ] Fix migration file parsing silent error swallowing
- [ ] Fix TimescaleDB methods missing extension pre-checks
- [ ] Fix GeoDataFrame silent SRID defaulting
- [ ] Fix session mode connection leak on cleanup exception
- [ ] Add retry/backoff policy for transient connection errors
- [ ] Add statement_timeout support in Config
- [ ] Configurable insert batch size (currently hardcoded 1000)
- [ ] Test coverage >70% with real PostgreSQL
- [ ] Test migration rollback edge cases (deleted files, syntax errors, first migration)
- [ ] Test session mode exception scenarios (cleanup failures, nested sessions, disconnects)
- [ ] Test pool stress scenarios (exhaustion, cycling, timeout, broken connections)
- [ ] Test spatial operations without PostGIS (graceful errors)
- [ ] Updated README reflecting all 0.3.0 API changes
- [ ] Updated Sphinx documentation rebuilt with new API
- [ ] CHANGELOG entry for 0.3.0 with breaking changes
- [ ] Migration guide for 0.2.0 → 0.3.0 breaking changes
- [ ] Release v0.3.0 on PyPI via existing CI workflow

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

- Refactor Database into smaller classes/mixins — keep monolith for now, restructure in future version
- Query result caching — premature optimization, defer to post-ETL
- Named parameters (:name syntax) — nice-to-have, not blocking ETL
- Computed/virtual column support — advanced schema feature, defer
- Dynamic pool sizing — current fixed sizing is acceptable
- Query result streaming — defer to ETL phase
- SQLAlchemy as optional dependency — would require significant refactoring
- ETL features — explicitly next milestone after 0.3.0

## Context

pycopg v0.2.0 is functional but has significant async gaps and known bugs documented in `.planning/codebase/CONCERNS.md`. The codebase has been mapped (`.planning/codebase/`) and the issues are well-understood. This consolidation pass will make the library production-ready before adding ETL capabilities.

**Key technical context:**
- Database class is 2300 lines — monolithic but we're not restructuring now
- AsyncDatabase has ~40% of Database's methods — needs full parity
- Current test coverage is below target — tests exist but don't cover edge cases
- Breaking changes are acceptable for 0.3.0 — clean API over backwards compat
- Tests must use real PostgreSQL (not mocks)
- CI workflow for PyPI publish already exists

## Constraints

- **Tech stack**: Python 3.11+, psycopg 3, no new dependencies beyond what's in pyproject.toml
- **Independence**: pycopg is a standalone PyPI library — no Solaris/MarketStream dependencies
- **Test infra**: Real PostgreSQL required for tests (Docker or local)
- **Breaking changes**: Allowed, but must be documented in CHANGELOG and migration guide

## Key Decisions

<!-- Decisions that constrain future work. Add throughout project lifecycle. -->

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Full async parity over partial | Users expect same API surface in both sync and async | — Pending |
| Breaking changes allowed | Clean API more valuable than backwards compat at v0.3.0 | — Pending |
| Keep monolithic Database class | Restructuring is high risk/effort, not needed for consolidation | — Pending |
| Real PostgreSQL for tests | Mock-based tests don't catch real driver/DB interaction bugs | — Pending |
| Retry/backoff as only new feature | Scope control — consolidation release, not feature release | — Pending |

---
*Last updated: 2026-02-11 after initialization*
