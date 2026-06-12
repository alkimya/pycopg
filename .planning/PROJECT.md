# pycopg — High-Level Python API for PostgreSQL/PostGIS/TimescaleDB

## What This Is

A production-ready Python library providing high-level sync and async APIs for PostgreSQL, PostGIS, and TimescaleDB. Version 0.3.0 achieved full AsyncDatabase/Database feature parity with 30+ async methods, production resilience (retry/backoff, timeouts), and 72.76% test coverage. Published on PyPI as a standalone library.

## Core Value

Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

## Current Milestone: v0.4.0 Quality & Spatial Helpers

**Goal:** Make pycopg cleanly publishable — first sanitize (security, parity, debt, tests, docs), then add spatial helpers on healthy foundations, and ship (PyPI + ReadTheDocs).

**Target features:**
- uv as the project-management tool (dev + CI + build + lockfile), keeping `pip install pycopg` for end users
- Close residual SQL-injection / robustness bugs left after the v0.3.1 hotfix (B1/B2/B3/B5)
- Restore full sync/async parity (10+ divergent methods) with an extended `test_parity`
- Wire up the already-existing abstractions (`base.py`, `queries.py`) to kill ~48% duplication
- numpydoc docstrings (shallow, no Examples) measured by `interrogate ≥ 95%`
- `db.spatial.*` / `async_db.spatial.*` helpers in parity (the realized Phase 8 design)
- Release v0.4.0 on PyPI with up-to-date Sphinx docs and a green RTD build

**Key context:** Scoped from the 2026-06-06 out-of-GSD audit (`.planning/AUDIT-2026-06-06.md`) + Phase 8 spatial design. Locked conventions: uv tooling, numpydoc docstrings, coverage ratchet 70→80→90→95 (never decreasing, capped at 95). The refactor previously deferred to a "future version" is now in scope. Full plan: `.planning/milestones/v0.4.0-MILESTONE.md`.

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
- ✓ uv project tooling: dev + CI + build + `uv.lock` + `.python-version` (hatchling kept) — Phase 9 (TOOL-*)
- ✓ Residual SQL-injection / robustness bugs B1/B2/B3/B5 + async validation closed — Phase 10 (SEC-*)
- ✓ Full sync/async parity: 13 mirrored methods, C1/C2/C3 fixes, extended `test_parity`, coverage ratchet → 90 — Phase 11 (PAR-*)
- ✓ Doc API homogène : docstrings numpydoc shallow (sans Examples), interrogate 100% (gate ≥95 en CI), garde Sphinx `-W` avec Google parsing OFF, exceptions domaine (`ExtensionNotAvailable`/`DatabaseExists`), `__version__` via importlib.metadata, mypy non-bloquant — Phase 13 (DOC-06..12)
- ✓ `db.spatial.*` / `async_db.spatial.*` : 11 helpers (builders SQL purs partagés + accesseurs lazy), garde PostGIS, `into="rows"/"gdf"`, 4 points ouverts tranchés (D-01..D-12 → 08-DESIGN.md), parité test_parity, coverage cliquet 92→94 — Phase 14 (SPAT-01..06)

### Active

<!-- Current scope. Building toward these. Full REQ-ID list in REQUIREMENTS.md. -->

- [ ] Refactor: wire up `queries.py` + `base.py`, extract pure stateless builders, dead-code cleanup — v0.4.0 (REF-*)
- [ ] numpydoc docstrings + `interrogate ≥ 95`, real exceptions (V2), `__version__` via importlib, mypy — v0.4.0 (DOC-*)
- [ ] Release v0.4.0: Sphinx docs, CHANGELOG, `uv build`, PyPI publish, RTD live — v0.4.0 (REL-*)

### Out of Scope

<!-- Explicit boundaries. Includes reasoning to prevent re-adding. -->

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

**Now in scope for v0.4.0 (was deferred):**
- ARCH-01: Refactor Database into shared base/mixins — done by wiring up existing `base.py`/`queries.py` (REF-*)

**Still deferred to a future milestone (v2 requirements):**
- API-01: Named parameter support (:name syntax)
- API-02: Connection health checks
- API-03: Structured logging
- API-04: Transaction isolation level control
- API-05: Savepoint support (nested transactions)
- API-06: Sync result streaming
- ARCH-02: Dynamic connection pool sizing
- ETL features (the spatial helpers are its building blocks, but the ETL layer itself is a later milestone)

## Constraints

- **Tech stack**: Python 3.11+, psycopg 3, tenacity added in v0.3.0
- **Project tooling (v0.4.0+)**: uv manages venv/deps/lockfile/build for contributors + CI; build backend stays hatchling. End-user docs keep `pip install pycopg`.
- **Independence**: pycopg is a standalone PyPI library — no Solaris/MarketStream dependencies
- **Test infra**: Real PostgreSQL required for tests (Docker or local)
- **Coverage ratchet (v0.4.0)**: `--cov-fail-under` only goes up per phase (70→80→90→95), never down; 100% is a per-method goal, not a hard gate
- **Docstrings (v0.4.0)**: numpydoc format, shallow (Summary/Parameters/Returns/Raises), no Examples; `interrogate ≥ 95` enforced in CI
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
| v0.4.0: security hotfix as isolated v0.3.1 release first | Low-risk mechanical fix, ship before the larger milestone | ✓ Good — shipped to PyPI 2026-06-06 |
| v0.4.0: uv as project manager, migrated in Phase 9 first | Every later phase runs under the new tooling; lockfile + reproducible CI | — Pending |
| v0.4.0: keep hatchling build backend (not uv_build) | uv_build too intrusive; hatchling is uv-compatible and already wired to trusted publishing | — Pending |
| v0.4.0: refactor by wiring existing base.py/queries.py | Abstractions already written but unbranched (~48% dup); wire, don't rewrite | — Pending |
| v0.4.0: coverage ratchet 70→80→90→95, capped at 95 | Forces steady test growth without blocking on hard-to-mock I/O | — Pending |
| v0.4.0: numpydoc docstrings, no Examples, interrogate ≥ 95 | Homogeneous measurable API docs; napoleon already active | — Pending |
| v0.4.0: refactor lifted from Out of Scope | PROJECT.md deferred it to a "future version" — this is that version | — Pending |
| v0.4.0 (P11): async catches up to richer sync signatures, never the reverse (D-07) | Sync is the established core-value API; align by enriching async | ✓ Good — 0 sync breaking changes, signatures match |
| v0.4.0 (P11): `listen` stays async-only by design (D-06) | A blocking synchronous NOTIFY listener is an anti-pattern | ✓ Good — sole documented async-only method in `test_parity` |
| v0.4.0 (P11): measure coverage before raising the ratchet gate (D-08) | Never freeze an unmet threshold | ✓ Good — measured 91.61% then flipped 80→90 |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-12 — Phase 14 complete (spatial helpers : `db.spatial.*`/`async_db.spatial.*` en parité, 11 helpers, builders purs 100% couverts, garde PostGIS, D-01..D-12 actés dans 08-DESIGN.md, gate coverage 92→94 ; SPAT-01..06 validés, vérification 11/11).*
