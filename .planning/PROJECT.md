# pycopg — High-Level Python API for PostgreSQL/PostGIS/TimescaleDB

## What This Is

A production-ready Python library providing high-level sync and async APIs for PostgreSQL, PostGIS, and TimescaleDB. As of v0.4.0 it offers full sync/async feature parity, PostGIS spatial helpers (`db.spatial.*` / `async_db.spatial.*`), numpydoc-documented APIs with an enforced docstring-coverage gate, and a uv-based contributor/CI toolchain — all under a 94% test-coverage ratchet. Published on PyPI as a standalone library and documented on ReadTheDocs.

## Core Value

Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

## Current State — v0.4.0 SHIPPED 2026-06-14

**Latest shipped:** v0.4.0 "Quality & Spatial Helpers" — published to PyPI (`pip install pycopg==0.4.0` verified in a clean venv) and live on ReadTheDocs. All 7 phases (9–15) verified passed; milestone audit PASSED (46/46 requirements, 7/7 phases, 14/14 integration, 4/4 E2E flows). Archived: `.planning/milestones/v0.4.0-{ROADMAP,REQUIREMENTS,MILESTONE-AUDIT}.md`.

**Delivered in v0.4.0:** uv toolchain (dev + CI + build + lockfile, `pip install pycopg` kept for users); residual security/robustness fixes (B1/B2/B3/B5); full sync/async parity (13 mirrored methods, C1/C2/C3, extended `test_parity`); wired `base.py`/`queries.py` abstractions; numpydoc docs with `interrogate ≥ 95`; `db.spatial.*` / `async_db.spatial.*` (11 helpers); coverage ratchet 70→80→90→92→94.

## Current Milestone: v0.5.0 ETL Pipeline Runner

**Goal:** Add a declarative ETL pipeline layer (`db.etl.*` / `async_db.etl.*`) that runs extract → transform → load flows with run tracking and safe, idempotent re-runs — built on pycopg's existing DataFrame/spatial helpers, at full sync/async parity.

**Target features:**
- Declarative pipeline definition: extract (source query/table) → transform (Python callable over DataFrame/rows) → load (target table)
- Pipeline runner that executes a pipeline end-to-end, same-DB only (source + target in one Database)
- Idempotent loads: safe re-runs via truncate-load and/or upsert-by-key
- Run tracking: a `pipeline_runs` table recording status, row counts, timing, and errors per run
- Full sync/async parity: `db.etl.*` and `async_db.etl.*`, verified by the existing `test_parity` harness

**Key context:**
- Transform = Python callable (leans on existing pandas/geopandas integration), not SQL-only.
- Endpoints = same-DB only for v0.5.0 (cross-DB and DataFrame/file sinks deferred).
- Incremental watermarks deferred to v0.6.0 — tracked as a Future Requirement; the `pipeline_runs` table is designed so watermarks slot on additively (nothing wasted).
- Continues phase numbering from Phase 16 (v0.4.0 ended at Phase 15).
- Coverage ratchet stays at 94% baseline; new ETL code expected to hold or raise it.
- Honors Core Value: every sync ETL method has a tested async equivalent.

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
- ✓ Refactor: `Database`/`AsyncDatabase` inherit `DatabaseBase`+`QueryMixin`, ~25 inline SQL → `queries.py` constants, pure DB-free builders extracted, dead code cleaned, coverage ratchet → 92 — Phase 12 (REF-01..05)
- ✓ numpydoc docstrings + `interrogate ≥ 95` (CI gate), real exceptions (V2), `__version__` via importlib.metadata, mypy (non-blocking) — Phase 13 (DOC-06..12)
- ✓ Release v0.4.0: Sphinx spatial docs + RTD green, CHANGELOG/MIGRATION/version bump, `uv build`, Node 24 CI, tag + PyPI publish, milestone audit — Phase 15 (REL-01..06)

### Active

<!-- Current scope. Building toward these. Full REQ-ID list in REQUIREMENTS.md. -->

v0.5.0 ETL Pipeline Runner — see Current Milestone above. Full REQ-ID list (ETL-*) in REQUIREMENTS.md.

- [ ] Declarative pipeline definition (extract → transform → load)
- [ ] Pipeline runner (same-DB, end-to-end execution)
- [ ] Idempotent loads (truncate-load / upsert-by-key)
- [ ] Run tracking via `pipeline_runs` table
- [ ] Full sync/async parity for the ETL surface

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

Shipped v0.4.0 (2026-06-14) with 10,528 LOC Python (lib) + 11,228 LOC tests.
Tech stack: Python 3.11+, psycopg 3, psycopg_pool, pandas, geopandas, tenacity, Sphinx; uv toolchain (dev + CI + build), hatchling backend.
Test coverage: 94.09% with real PostgreSQL (`pycopg_test`); coverage ratchet at `--cov-fail-under=94`.
Docs: numpydoc, `interrogate` 100% (gate ≥95), Sphinx `-W` green, ReadTheDocs live.

**Known tech debt (from v0.4.0 milestone audit):**

- Coverage-95 stretch deferred — gate honest at 94 (measured 94.09%); remaining ~1pt is DB/IO paths (subprocess, engine.dispose) structurally out of scope. REF-01..05 satisfied regardless.
- `TableNotFound` exported in `__all__` but has no internal raise site (user-`except` only) — benign.
- `docs/conf.py` sets `release = '0.4.0'` but no explicit `version =` short-version line (cosmetic; RTD green).
- Nyquist: phases 10 & 12 lack VALIDATION.md; 9/13/15 `nyquist_compliant: false` (release/tooling/doc phases smoke/manual-verified by design).
- Database class remains monolithic (~2300 lines) — acceptable; duplication killed via base.py/queries.py wiring.

**Resolved this milestone:**

- ARCH-01 (refactor Database into shared base/mixins) — done by wiring up existing `base.py`/`queries.py` (REF-*).
- v0.3.0 tag + PyPI publication (carried in earlier; v0.3.0, v0.3.1, v0.4.0 all live on PyPI).

**Now in scope (v0.5.0):**

- ETL pipeline runner (the spatial/DataFrame helpers are its building blocks) — see Current Milestone.

**Still deferred to a future milestone:**
- API-01: Named parameter support (:name syntax)
- API-02: Connection health checks
- API-03: Structured logging
- API-04: Transaction isolation level control
- API-05: Savepoint support (nested transactions)
- API-06: Sync result streaming
- ARCH-02: Dynamic connection pool sizing
- ETL incremental/CDC watermarks — deferred to v0.6.0; v0.5.0's `pipeline_runs` table is designed so watermarks slot on additively
- ETL cross-DB transfer and DataFrame/CSV/parquet source/sink — deferred; v0.5.0 is same-DB only

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
| v0.4.0: uv as project manager, migrated in Phase 9 first | Every later phase runs under the new tooling; lockfile + reproducible CI | ✓ Good — uv.lock + .python-version committed; CI/build run under uv (Phase 9) |
| v0.4.0: keep hatchling build backend (not uv_build) | uv_build too intrusive; hatchling is uv-compatible and already wired to trusted publishing | ✓ Good — `uv build` delegates to hatchling; OIDC publish unchanged |
| v0.4.0: refactor by wiring existing base.py/queries.py | Abstractions already written but unbranched (~48% dup); wire, don't rewrite | ✓ Good — both classes inherit base; ~25 SQL strings → queries.py (Phase 12) |
| v0.4.0: coverage ratchet 70→80→90→95, capped at 95 | Forces steady test growth without blocking on hard-to-mock I/O | ⚠️ Revisit — landed at 94 (measured); 95 stretch deferred (DB/IO paths out of scope, D-07) |
| v0.4.0: numpydoc docstrings, no Examples, interrogate ≥ 95 | Homogeneous measurable API docs; napoleon already active | ✓ Good — interrogate 100%, Sphinx -W green, Google parsing off (Phase 13) |
| v0.4.0: refactor lifted from Out of Scope | PROJECT.md deferred it to a "future version" — this is that version | ✓ Good — ARCH-01 delivered via base.py/queries.py wiring |
| v0.4.0 (P14): geometry resolver enforces exactly-one-of point/wkt/geojson/ref (D-05) | One unambiguous geometry input path per spatial helper | ✓ Good — resolver + 11 builders, spatial.py 100% covered |
| v0.4.0 (P15): release human-gated (RTD + tag + PyPI publish) | Irreversible supply-chain steps need maintainer confirmation | ✓ Good — clean-venv install verified, RTD green, milestone audit passed |
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

*Last updated: 2026-06-14 — Phase 15 complete + milestone v0.4.0 SHIPPED. Released to PyPI (wheel+sdist via OIDC trusted publishing, tag `v0.4.0`, clean-venv install verified) and ReadTheDocs (green build, Spatial Helpers page live). REL-01..06 satisfied: Sphinx spatial docs + `docs/spatial.md`, version bump 0.4.0, CHANGELOG/MIGRATION, Node 24 CI actions, RTD green, PyPI publish, milestone audit passed (6/6 plans, verification 6/6).*

*Last updated: 2026-06-14 — milestone v0.4.0 closed via `/gsd-complete-milestone`. Full PROJECT.md evolution review: "What This Is" → v0.4.0; Current State + Next Milestone Goals sections; REF/DOC/REL/SPAT requirements moved to Validated; Active emptied; Context refreshed (10,528 lib LOC + 11,228 test LOC, 94.09% coverage); v0.4.0 Key Decisions outcomes recorded. ROADMAP/REQUIREMENTS archived to `milestones/v0.4.0-*`.*

*Last updated: 2026-06-14 — milestone v0.5.0 "ETL Pipeline Runner" started via `/gsd-new-milestone`. Goal: declarative `db.etl.*`/`async_db.etl.*` extract→transform→load layer (Python-callable transforms, same-DB, idempotent loads, `pipeline_runs` tracking) at full sync/async parity. Active requirements set to ETL scope; ETL removed from deferred list; incremental watermarks + cross-DB/file sinks deferred (v0.6.0). Phase numbering continues from Phase 16.*
