# pycopg — High-Level Python API for PostgreSQL/PostGIS/TimescaleDB

## What This Is

A production-ready Python library providing high-level sync and async APIs for PostgreSQL, PostGIS, and TimescaleDB. As of v0.5.0 it offers full sync/async feature parity, PostGIS spatial helpers (`db.spatial.*` / `async_db.spatial.*`), a declarative ETL pipeline runner (`db.etl.*` / `async_db.etl.*`) with run tracking and idempotent loads, numpydoc-documented APIs with an enforced docstring-coverage gate, and a uv-based contributor/CI toolchain — all under a 94% test-coverage ratchet. Published on PyPI as a standalone library and documented on ReadTheDocs.

## Core Value

Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

## Current State — v0.6.0 SHIPPED 2026-06-19

**Latest shipped:** v0.6.0 "Réorganisation en accessors" — published to PyPI (`pip install pycopg==0.6.0`; wheel + sdist live via OIDC trusted publishing, tag `v0.6.0`). All 4 phases (21–24) verified passed; Phase 24 VERIFICATION PASSED 4/4 (REORG-05); the 5 new accessors + async variants exported from `pycopg`, README/Sphinx/CHANGELOG/MIGRATION updated, version bumped in both sources, clean-venv import smoke confirmed. Gates at ship: coverage 95.64% (ratchet ≥94 held), interrogate ≥95, Sphinx `-W` clean.

**Delivered in v0.6.0:** the ~54 flat public methods on `Database`/`AsyncDatabase` regrouped under 5 lazy accessors — `db.timescale.*` (6), `db.admin.*` (11), `db.schema.*` (27), `db.maint.*` (6), `db.backup.*` (4) — plus the 2 spatial-index methods relocated to `db.spatial.*`, all with full sync/async parity (`TimescaleAccessor` … `AsyncSchemaAccessor` exported from top-level `pycopg`). 56 legacy flat names kept as `@deprecated_alias` stubs emitting `DeprecationWarning` (removal scheduled v0.7.0), documented in a prepended MIGRATION.md v0.5→v0.6 guide. Transactional core (`execute`/`session`/`to_dataframe`/…) intentionally stays flat. No new runtime power — pure reorganization.

**Previously shipped (v0.5.0):** declarative ETL pipeline runner under `db.etl.*` / `async_db.etl.*` — inspectable `Pipeline` frozen dataclass; run-tracking via `pipeline_runs` with structural autocommit isolation; three load modes (append/replace/upsert); SQL/table extract + transform chains; an 8-field `RunResult` plus `history()`/`last_run()`/`dry_run`; full sync/async parity. Zero new runtime dependencies.

**Delivered in v0.5.0:** a declarative ETL pipeline runner under `db.etl.*` / `async_db.etl.*` — inspectable `Pipeline` frozen dataclass with construction-time validation; run-tracking via `pipeline_runs` with structural autocommit isolation (run rows commit independently of the load transaction, even under `db.session()`); three load modes (append/replace/upsert) with atomic loads; SQL/table extract and single/list/None transform chains; an 8-field `RunResult` plus `history()`/`last_run()`/`dry_run`; full sync/async parity (`AsyncETLAccessor`, lazy `async_db.etl`, `asyncio.to_thread` transforms) enforced by `TestEtlParity`. Zero new runtime dependencies.

**Previously shipped (v0.4.0):** uv toolchain; residual security/robustness fixes (B1/B2/B3/B5); full sync/async parity (13 mirrored methods); wired `base.py`/`queries.py` abstractions; numpydoc docs with `interrogate ≥ 95`; `db.spatial.*` (11 helpers); coverage ratchet 70→94.

## Current Milestone: v0.6.0 Réorganisation en accessors

**Goal:** Regrouper les ~54 méthodes publiques à plat de `Database`/`AsyncDatabase` sous 5 accessors lazy (`db.timescale/admin/schema/maint/backup.*`), avec alias rétro-compatibles + `DeprecationWarning`, en gardant le cœur transactionnel à plat — sur le pattern déjà éprouvé `db.spatial.*` (v0.4.0) et `db.etl.*` (v0.5.0). Assainir avant d'étendre : ce milestone **déménage l'existant**, il n'ajoute aucun nouveau pouvoir.

**Target features:**
- `db.timescale.*` (6 méthodes — hypertables, compression, retention/compression policies)
- `db.admin.*` (12 méthodes — rôles & permissions)
- `db.schema.*` (~26 méthodes — DDL, introspection, extensions, contraintes, index ; un seul bloc)
- `db.maint.*` (6 méthodes — size, vacuum, analyze, explain)
- `db.backup.*` (4 méthodes — pg_dump/pg_restore, copy CSV)

**Locked decisions (D-SCOPE-1..4, voir `.planning/v0.6.0-SCOPE.md`):**
- **D-SCOPE-1** — Transition = alias mince + `DeprecationWarning` pointant vers le nouveau chemin ; suppression des alias planifiée pour v0.7.0. Zéro rupture brutale (lib publiée sur PyPI).
- **D-SCOPE-2** — La vraie implémentation vit **dans** l'accessor ; l'ancien `db.*` devient le wrapper qui warn + délègue. Supprimer la dette en v0.7.0 = effacer un bloc d'alias.
- **D-SCOPE-3** — Les 5 accessors en **un seul milestone** (~5-6 phases ; travail mécanique répétitif validé en phase 1 puis répliqué).
- **D-SCOPE-4** — Parité sync/async obligatoire (Core Value) ; `test_parity` enregistre les 5 nouveaux accessors.

**Open questions résolues au cadrage (2026-06-17):**
- `db.schema.*` reste **un seul bloc** (DDL + introspection) — cohérent avec spatial/etl qui groupent par domaine et non par type d'opération ; un éventuel `db.meta.*` se carve plus tard (v0.9.0) sur surface propre si ça vaut le coup.
- Méthodes **DataFrame** (`to_dataframe`/`from_dataframe`/`*_geodataframe`) → restent **à plat** sur `db.*` (usage quotidien).
- `create_spatial_index` / `list_geometry_columns` → rejoignent **`db.spatial.*`** (cohérence thématique PostGIS).

**Reste à plat sur `db.*` (cœur transactionnel — ne pas déménager):** `create`, `create_from_env`, `engine`, `connect`, `cursor`, `transaction`, `session`, `in_session`, `execute`, `execute_many`, `insert_many`, `upsert_many`, `stream`, `notify`, `insert_batch`, `copy_insert`, `fetch_one`, `fetch_val`, les méthodes DataFrame, et les accessors existants (`spatial`, `etl`).

Suite prévue (voir `.planning/FUTURE-MILESTONES.md`, ordre validé) : v0.7.0 suppression des alias + ETL incrémental → v0.8.0 TimescaleDB avancé → v0.9.0 CRUD/introspection → v1.0.0 spatial v2.

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
- ✓ Declarative `Pipeline` dataclass (extract → transform → load), inspectable + construction-time validated — v0.5.0 (ETL-01)
- ✓ Pipeline runner, same-DB end-to-end (`db.etl.run`), append/replace/upsert with atomic loads + SQL/table extract + transform chains — v0.5.0 (ETL-02..06, ETL-16)
- ✓ Run tracking via `pipeline_runs` (status/counts/timing/errors), autocommit-isolated from the load transaction, auto-created or explicit `init()` — v0.5.0 (ETL-07..09, ETL-14)
- ✓ `RunResult` query surface: `run()` returns `RunResult`, `history()`, `last_run()`, `dry_run=True` — v0.5.0 (ETL-10, ETL-11, ETL-15, ETL-17)
- ✓ Full sync/async ETL parity (`AsyncETLAccessor`, lazy `db.etl`/`async_db.etl`, `asyncio.to_thread` transforms, `TestEtlParity`) — v0.5.0 (ETL-12, ETL-13)

### Active

<!-- Current scope. Building toward these. Full REQ-ID list in REQUIREMENTS.md. -->

v0.6.0 — Réorganisation en accessors (5 accessors lazy + alias dépréciés). Full REQ-ID list in REQUIREMENTS.md.

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

Shipped v0.5.0 (2026-06-15). ETL added `pycopg/etl.py` (~+800 LOC lib over v0.4.0) plus tests; milestone diff was +15,458 / −82 across 69 files.
Tech stack: Python 3.11+, psycopg 3, psycopg_pool, pandas, geopandas, tenacity, Sphinx; uv toolchain (dev + CI + build), hatchling backend. Zero new runtime deps in v0.5.0.
Test coverage: 94.26% with real PostgreSQL (`pycopg_test`); coverage ratchet at `--cov-fail-under=94`.
Docs: numpydoc, `interrogate` 100% (gate ≥95), Sphinx `-W` green, ReadTheDocs live (incl. `docs/etl.md`).

**Known tech debt:**

- **2 pre-existing flaky full-suite DB tests** (`TestAsyncIntegration::test_async_transaction_fix`, `TestPostGISErrorHandling::test_create_spatial_index_name_parameter`) — `UndefinedTable` fixture-isolation bug in the spatial/integration suites, NOT ETL code; fail identically in isolation; did not affect the coverage threshold. Worth a fixture-isolation fix in a future cleanup. (See STATE.md Deferred Items.)
- Coverage-95 stretch still deferred — gate honest at 94 (measured 94.26%); remaining ~1pt is DB/IO paths structurally out of scope.
- `TableNotFound` exported in `__all__` but has no internal raise site (user-`except` only) — benign.
- `CLAUDE.md` "Version" line still reads v0.3.1 (stale) — actual shipped is v0.5.0; cosmetic doc lag.
- Nyquist: some release/tooling/doc phases `nyquist_compliant: false` by design (smoke/manual-verified).
- Database class remains monolithic — acceptable; duplication killed via base.py/queries.py wiring.

**Resolved in v0.5.0:**

- ETL pipeline runner delivered end-to-end (ETL-01..17) on top of the spatial/DataFrame helpers; `pipeline_runs` watermark column reserved for v0.6.0 incremental support.
- All of v0.3.0, v0.3.1, v0.4.0, v0.5.0 live on PyPI.

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
| v0.5.0: ETL architecture mirrors `spatial.py` (lazy accessor + pure builders) | Proven pattern; keeps monolith from growing; testable builders | ✓ Good — `ETLAccessor`/`AsyncETLAccessor` lazy under `db.etl`/`async_db.etl` |
| v0.5.0: run-log writes on a dedicated `connect(autocommit=True)`, isolated from the load txn | A failed/rolled-back load must still record a `failed` run row | ✓ Good — run rows commit on every path, incl. active `db.session()` (ETL-08/09) |
| v0.5.0: reserve a nullable `watermark JSONB` column, always NULL | Lets v0.6.0 incremental support slot on with no breaking migration | — Pending — validated additively in v0.6.0 |
| v0.5.0: same-DB only; Python-callable transforms (not SQL-only) | Scope control; leans on existing pandas/geopandas integration | ✓ Good — cross-DB/file sinks cleanly deferred |
| v0.5.0: async transforms via `asyncio.to_thread` (D-/SC-2) | Sync transform callables must not block the event loop | ✓ Good — behavioral test proves non-blocking dispatch |
| v0.5.0: PyPI publish human-gated at the irreversible step | Supply-chain publish needs maintainer sign-off | ✓ Good — executor stopped at the boundary; published after explicit approval |

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

*Last updated: 2026-06-14 — Phase 16 "Pure ETL Layer" complete (2/2 plans, verification 4/4). Pure, DB-free foundation shipped: `pycopg/etl.py` with the public `@dataclass(frozen=True) Pipeline` (8 fields, construction-time validation — upsert-needs-conflict_columns, load_mode set, bare-string/bool guards) plus `build_init_sql()`/`build_truncate_sql()` builders mirroring `spatial.py` (validate_identifiers-first, `(sql, params)` tuples); ETL exception hierarchy (`ETLError`/`ETLTransformError`/`ETLTargetNotFoundError`, D-08) in `exceptions.py` + top-level exports; 5 `ETL_*` SQL constants (idempotent `pipeline_runs` DDL, TEXT+CHECK status, nullable `watermark JSONB`, `%s`-only) in `queries.py`; 33 DB-free tests. ETL-01 validated. Code review: 0 critical, fixes applied (WR-01/02/03, IN-04). `Pipeline`/accessor wiring deferred to Phase 20.*

*Last updated: 2026-06-15 — Phase 18 "Load Modes & Extract" complete (3/3 plans, verification 6/6). The real `ETLAccessor.run(pipeline: Pipeline) -> int` body replaces the Phase 17 stub: extract (SQL/table via `to_dataframe`) → transform chain (`None`/single/list, `ETLTransformError` names the failing step via `_step_label`) → mode-dispatched load. New pure builders `_build_insert_sql` (append/replace) and `_build_upsert_sql` (ON CONFLICT DO UPDATE) join `build_truncate_sql`, all `validate_identifiers`-first with user values as `%s` only. Atomicity seam (RESEARCH Q1): load runs on the `db.transaction()` connection inside an internal `db.session()` so replace's TRUNCATE+INSERT is atomic (`replace_atomic_rollback` proven), while run-log writes stay isolated on dedicated autocommit connections. ETL-02..06 + ETL-16 validated; 186 ETL tests pass. Code review (advisory, not blocking): CR-01 latent upsert edge case (all-columns-are-conflict-columns → empty SET; untested, no in-contract impact), CR-02 `rows_loaded` from `cur.rowcount` deferred to Phase 19's `RunResult`. Next: Phase 19 (Sync Runner & Query Surface).*

*Last updated: 2026-06-15 — Phase 20 complete + milestone v0.5.0 "ETL Pipeline Runner" SHIPPED via `/gsd-complete-milestone`. Phase 20 delivered `AsyncETLAccessor` (async mirror, `asyncio.to_thread` transforms), lazy `async_db.etl`, `TestEtlParity`, `docs/etl.md`, and the v0.5.0 release (tag + PyPI via OIDC, human-gated publish); VERIFICATION PASSED 5/5. Full PROJECT.md evolution review: "What This Is" → v0.5.0; Current State + Next Milestone Goals (v0.6.0 ETL watermarks candidate); all 17 ETL requirements moved to Validated; Active emptied; Context refreshed (94.26% coverage, 2 known-flaky tests as tech debt); v0.5.0 Key Decisions outcomes recorded. ROADMAP collapsed + REQUIREMENTS archived to `milestones/v0.5.0-*`.*

*Last updated: 2026-06-19 — Phase 24 complete + milestone v0.6.0 "Réorganisation en accessors" SHIPPED. Phase 24 (final, REORG-05) delivered the docs+release work on top of Phases 21–23's accessor migration: the 5 accessor classes + async variants exported from top-level `pycopg`; README "Accessor Namespaces" overview + accessor-path rewrites; 5 `automodule` blocks; the 4 per-topic prose pages on accessor paths with v0.7.0 deprecation notices; CHANGELOG `[0.6.0]` (Added/Deprecated/Changed) + prepended MIGRATION v0.5→v0.6 guide (56-name table, 1:1 with `@deprecated_alias` stubs); version bumped in pyproject.toml + docs/conf.py; v0.6.0 tagged + published to PyPI via OIDC (human-gated); clean-venv import smoke confirmed. VERIFICATION PASSED 4/4; code review clean (docs/release phase, no source logic). Current State → v0.6.0. Open: PROJECT.md "Requirements" not yet collapsed + ROADMAP/REQUIREMENTS not yet archived → run `/gsd-complete-milestone v0.6.0`.*

*Last updated: 2026-06-17 — milestone v0.6.0 "Réorganisation en accessors" started via `/gsd-new-milestone`. Goal: regrouper les ~54 méthodes publiques à plat de `Database`/`AsyncDatabase` sous 5 accessors lazy (`db.timescale/admin/schema/maint/backup.*`) avec alias dépréciés (D-SCOPE-1..4 verrouillés en discussion, voir `.planning/v0.6.0-SCOPE.md`). 3 questions ouvertes du scope tranchées au cadrage : `db.schema.*` reste un seul bloc, DataFrame reste à plat, spatial-index → `db.spatial.*`. Cœur transactionnel reste à plat. Active set to the réorg scope. Phase numbering continues from Phase 21. Suite validée (FUTURE-MILESTONES) : v0.7.0 alias removal + ETL incrémental → v0.8.0 TSDB avancé → v0.9.0 CRUD → v1.0.0 spatial v2.*

*Last updated: 2026-06-17 — Phase 21 "Infrastructure & Timescale Accessor" complete (3/3 plans, verification PASSED 4/4). Le pattern alias+accessor est désormais établi de bout en bout et prouvé : `pycopg/aliases.py` (`@deprecated_alias` — `stacklevel=2`, branche `iscoroutinefunction`, sans eval/exec, réutilisé tel quel par les Phases 22-24) + `pycopg/timescale.py` (`TimescaleAccessor`/`AsyncTimescaleAccessor`, 6 méthodes déplacées verbatim avec `self.`→`self._db.`). `db.timescale.*` / `async_db.timescale.*` câblés en propriétés lazy (cache `_timescale`, miroir de `_spatial`/`_etl`) ; les 6 méthodes plates sync + 6 async sont des stubs `@deprecated_alias` qui warn + délèguent (zéro breaking change). Registre data-driven `ACCESSOR_PAIRS` + `test_accessor_parity` (sync↔async), `test_timescale_aliases.py` (warn+delegate par alias), 27 call-sites migrés. Gates : suite complète 994 passants (2 échecs DB pré-existants connus), `-W error::DeprecationWarning` vert (295), coverage 94.46% (ratchet ≥94 tenu). Revue de code : 0 critique, 4 warnings advisory (notamment WR-01 : signatures `(*args, **kwargs)` dégradant le typage statique sur ce package `py.typed` ; WR-02 : README/docs documentent encore l'API plate dépréciée). REORG-01/02/03/04 + TS-01 validés. Next : Phase 22 (Admin, Maint & Backup accessors).*
