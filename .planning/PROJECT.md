# pycopg — High-Level Python API for PostgreSQL/PostGIS/TimescaleDB

## What This Is

A production-ready Python library providing high-level sync and async APIs for PostgreSQL, PostGIS, and TimescaleDB. As of v0.8.0 it offers full sync/async feature parity, an accessor-organized public surface (`db.spatial/etl/timescale/admin/maint/backup/schema.*`) with a flat transactional core, PostGIS spatial helpers, a declarative ETL pipeline runner with run tracking, idempotent loads and **watermark-based incremental loading** (`Pipeline.incremental_column`), an **advanced TimescaleDB surface** (`db.timescale.*`, 15 methods — chunk & dimension management, full continuous-aggregate lifecycle, and `time_bucket`/`time_bucket_gapfill` query helpers), numpydoc-documented APIs with an enforced docstring-coverage gate, and a uv-based contributor/CI toolchain — all under a 94% test-coverage ratchet. Published on PyPI as a standalone library and documented on ReadTheDocs.

## Core Value

Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

## Current State — v0.8.0 SHIPPED 2026-06-23

**Latest shipped:** v0.8.0 "TimescaleDB avancé" — published to PyPI (`pip install pycopg==0.8.0`; wheel + sdist live via OIDC trusted publishing, tag `v0.8.0`, workflow run 28044147070). Phases 30–33 verified passed: 9 new time-series methods (chunk & dimension management ×4, continuous aggregate lifecycle ×3, query helpers ×2) on `db.timescale.*` / `async_db.timescale.*` with full sync/async parity; CHANGELOG `[0.8.0]` Added-only; all three docs surfaces updated (`docs/timescaledb.md` Advanced Chunk & Dimension Management section, `api-reference.md` 15-row table, README "15 methods"); 4 gates green at ship (coverage 95.11%, interrogate 100%, Sphinx `-W` clean, `-W error::DeprecationWarning` green); clean-venv import smoke printed 0.8.0. (Milestone roll-up into the requirements/decisions log is finalized by `/gsd-complete-milestone v0.8.0`.)

**Previously shipped:** v0.7.0 "Alias Removal + Incremental ETL" — published to PyPI (`pip install pycopg==0.7.0`; wheel + sdist live via OIDC trusted publishing, tag `v0.7.0`). All 5 phases (25–29) verified passed; the 56 deprecated flat aliases hard-removed from both classes (surface is now accessor-only), watermark-based incremental ETL wired end-to-end in sync + async, CHANGELOG `[0.7.0]` Breaking/Added + MIGRATION v0.6→v0.7 (56-name table) finalized, version bumped in both sources, clean-venv import smoke confirmed. Gates at ship: coverage 95.11% (ratchet ≥94 held), interrogate 100%, Sphinx `-W` clean, `-W error::DeprecationWarning` green (no stubs left to fire).

**Delivered in v0.7.0:**

- **Alias removal (breaking):** all 56 `@deprecated_alias` flat stubs removed from each of `Database`/`AsyncDatabase` (112 total), `pycopg/aliases.py` + 6 warn+delegate test files deleted; any removed flat name now raises plain `AttributeError`; new 114-test `test_alias_removal.py`. Closed carried-forward WR-01 (IDE signature erasure on this `py.typed` package) and IN-02 (13 stale `create_extension` error-message/guard sites). One deprecation cycle (served in v0.6.0) honored.
- **Incremental ETL (additive):** new `Pipeline.incremental_column` field (identifier-validated; `+ load_mode ∈ {append, replace}` forbidden at construction — incremental requires `upsert`). On the first run, full load + records `max(col)`; on subsequent runs, `WHERE col > last_watermark` (exclusive, `%s`-parameterized) applied to extract; high-water mark computed from the **raw** batch before transforms; advances only on success; empty batch preserves the prior watermark (never NULL). `RunResult` gains `watermark_used`/`watermark_recorded`; `history()`/`last_run()` surface them; `dry_run` previews the filter without writing a run row; typed JSONB envelope round-trips int/str/datetime with zero new deps. Full sync/async parity (ETL-INC-11). The `pipeline_runs.watermark JSONB` column reserved in v0.5.0 is now in use — no breaking migration.

**Previously shipped (v0.6.0):** the ~54 flat public methods on `Database`/`AsyncDatabase` regrouped under 5 lazy accessors — `db.timescale.*` (6), `db.admin.*` (11), `db.schema.*` (27), `db.maint.*` (6), `db.backup.*` (4) — plus the 2 spatial-index methods relocated to `db.spatial.*`, all with full sync/async parity. Shipped with backward-compatible deprecated aliases (now removed in v0.7.0). Transactional core (`execute`/`session`/`to_dataframe`/…) intentionally stays flat.

**Previously shipped (v0.5.0):** declarative ETL pipeline runner under `db.etl.*` / `async_db.etl.*` — inspectable `Pipeline` frozen dataclass; run-tracking via `pipeline_runs` with structural autocommit isolation; three load modes (append/replace/upsert); SQL/table extract + transform chains; an 8-field `RunResult` plus `history()`/`last_run()`/`dry_run`; full sync/async parity. Zero new runtime dependencies.

**Delivered in v0.5.0:** a declarative ETL pipeline runner under `db.etl.*` / `async_db.etl.*` — inspectable `Pipeline` frozen dataclass with construction-time validation; run-tracking via `pipeline_runs` with structural autocommit isolation (run rows commit independently of the load transaction, even under `db.session()`); three load modes (append/replace/upsert) with atomic loads; SQL/table extract and single/list/None transform chains; an 8-field `RunResult` plus `history()`/`last_run()`/`dry_run`; full sync/async parity (`AsyncETLAccessor`, lazy `async_db.etl`, `asyncio.to_thread` transforms) enforced by `TestEtlParity`. Zero new runtime dependencies.

**Previously shipped (v0.4.0):** uv toolchain; residual security/robustness fixes (B1/B2/B3/B5); full sync/async parity (13 mirrored methods); wired `base.py`/`queries.py` abstractions; numpydoc docs with `interrogate ≥ 95`; `db.spatial.*` (11 helpers); coverage ratchet 70→94.

## Current Milestone: v0.9.0 CRUD ergonomique + introspection enrichie

**Goal:** Additive convenience over the existing API, low risk — ergonomic CRUD helpers + enriched schema introspection, full sync/async parity, zero new runtime dependencies.

**Target features:**
- **CRUD ergonomics** — `upsert` (singulier), `delete_where`, `update_where`, `exists`, `count`, `paginate`, dict-fetch — convenience over the existing transactional core.
- **Introspection helpers** — `primary_key()`, `foreign_keys()`, `sequences()`, `views()`, `describe()` — enrich the existing schema-introspection surface.

**Key context:** Started 2026-06-24 via `/gsd-new-milestone`. The forward sequence (see `.planning/FUTURE-MILESTONES.md`) was locked by the user: v0.9.0 CRUD → **v1.0.0 spatial v2 + stabilisation API**. Scope decisions locked at cadrage (2026-06-24):
- **Both feature families in one milestone** — CRUD ergonomics + introspection together.
- **Placement: keep on `db.schema.*` / flat transactional core — NO `db.meta.*` carve.** The v0.6.0 open question (carve introspection into `db.meta.*`) is resolved: stay purely additive, no new accessor, no second deprecation cycle on a just-cleaned surface. The new introspection methods extend `db.schema.*`; the CRUD helpers land where their nearest analogs live (transactional core / `db.schema.*` per builder-pur convention).
- **Builder-pur + accessor pattern** (`validate_identifiers` first, user values as `%s`, pure `(sql, params)` builders, sync/async parity verified by `test_accessor_parity`) — same as spatial/etl/timescale.
- **Sync/async parity obligatoire** (Core Value), **zero new runtime dependencies**, coverage ratchet held ≥94% (baseline 95.11% since v0.7.0).

Phase numbering continues from Phase 33 (v0.9.0 starts at Phase 34).

**v1.0.0 (next) — Spatial v2 + stabilisation:** extend `db.spatial.*` (ST_Union, ST_Simplify, ST_ConvexHull, ST_MakeValid, spatial aggregates, raster?) + freeze the public API for a real 1.0.

<details>
<summary>v0.8.0 milestone goal & locked decisions (shipped 2026-06-23 — historical reference)</summary>

**Goal:** Livrer les fonctionnalités phares time-series qui manquent au socle actuel, posées proprement dans le `db.timescale.*` créé en v0.6.0 (qui n'avait que hypertable/compression/rétention) : **continuous aggregates** (cycle complet create + refresh manuel + policy auto-refresh), `time_bucket` / `time_bucket_gapfill` (helpers de requête), `show_chunks` / `drop_chunks`, `add_dimension`, `reorder_policy`. Sur le pattern builder-pur + accessor déjà éprouvé (spatial, etl, timescale-basics), parité sync/async obligatoire (Core Value), cible TimescaleDB 2.x. Phases 30–33.

**Locked scope decisions (cadrage 2026-06-22):**
- **Cible TimescaleDB 2.x uniquement** — continuous aggregates matérialisées modernes, signatures `add_*_policy` actuelles ; 2.x documenté comme plancher (matche l'env de test local).
- **Pattern builder-pur + accessor** — comme spatial/etl/timescale-basics : `validate_identifiers` d'abord, valeurs utilisateur en `%s`, builders purs `(sql, params)`, accessor lazy, parité sync/async vérifiée par `test_accessor_parity` (Core Value).
- **continuous aggregates = cycle complet** — `create_continuous_aggregate` + `refresh_continuous_aggregate` (manuel) + `add_continuous_aggregate_policy` (auto-refresh) livrés ensemble.
- **`time_bucket`/`time_bucket_gapfill` = helpers de requête**, pas du DDL/management : builders SQL purs renvoyant DataFrame/rows (et non `db.execute()` brut).
- **Fence : TimescaleDB-only** — les follow-ups ETL incrémental (`initial_watermark` F01, F02–F05) restent reportés à un milestone ETL ultérieur (une famille de features par milestone).
- **Zéro nouvelle dépendance runtime** ; cliquet de couverture maintenu ≥94% (baseline 95.11% depuis v0.7.0).

**Material correction during execution:** D-08 was REVERSED at Phase 32 plan time — `time_bucket` is Apache-free (live tests assert REAL output) but `time_bucket_gapfill`/`locf`/`interpolate` and the full continuous-aggregate surface are Community/TSL-only (raise `FeatureNotSupported` under the local Apache 2.28 license), so those live tests use a license-tolerant `try/except FeatureNotSupported` with the mock SQL-shape test as authoritative.

</details>

<details>
<summary>v0.7.0 milestone goal & locked decisions (shipped 2026-06-22 — historical reference)</summary>

**Goal:** Solder la dette de dépréciation de v0.6.0 (retirer les 56 alias plats — ALIAS-RM-01) et livrer l'ETL incrémental (watermarks CDC — ETL-INC-01), via la colonne `pipeline_runs.watermark JSONB` réservée en v0.5.0 (ajout additif, pas de migration cassante).

**Locked scope decisions (cadrage 2026-06-19):**

- Watermark déclaratif via `incremental_column` (pas de callback) ; high-water mark = `max(col)` du batch extrait **avant transforms** ; opérateur `>` exclusif.
- Sources SQL-string : wrap subquery + WHERE (`SELECT * FROM (<sql>) sub WHERE col > %s`, la colonne watermark doit figurer dans le SELECT) ; watermark toujours passé en `%s`.
- Premier run = full load puis record `max(col)` ; avance uniquement sur succès ; batch vide préserve le watermark (jamais NULL).
- Incrémental requiert `load_mode="upsert"` ; `append` **et** `replace` interdits à la construction (`ValueError`).
- Suppression d'alias = hard remove (un cycle de dépréciation déjà servi en v0.6.0) + MIGRATION v0.6→v0.7 + note Breaking au CHANGELOG.
- `initial_watermark` (borne du premier run) reporté en v0.8.0 ; zéro nouvelle dépendance runtime.

</details>

<details>
<summary>v0.6.0 milestone goal & locked decisions (shipped — historical reference)</summary>

**Goal:** Regrouper les ~54 méthodes publiques à plat de `Database`/`AsyncDatabase` sous 5 accessors lazy (`db.timescale/admin/schema/maint/backup.*`), avec alias rétro-compatibles + `DeprecationWarning`, en gardant le cœur transactionnel à plat — sur le pattern déjà éprouvé `db.spatial.*` (v0.4.0) et `db.etl.*` (v0.5.0). Assainir avant d'étendre : ce milestone **déménage l'existant**, il n'ajoute aucun nouveau pouvoir.

**Locked decisions (D-SCOPE-1..4, voir `.planning/milestones/v0.6.0-ROADMAP.md`):**
- **D-SCOPE-1** — Transition = alias mince + `DeprecationWarning` pointant vers le nouveau chemin ; suppression des alias planifiée pour v0.7.0. Zéro rupture brutale (lib publiée sur PyPI).
- **D-SCOPE-2** — La vraie implémentation vit **dans** l'accessor ; l'ancien `db.*` devient le wrapper qui warn + délègue. Supprimer la dette en v0.7.0 = effacer un bloc d'alias.
- **D-SCOPE-3** — Les 5 accessors en **un seul milestone** (travail mécanique répétitif validé en phase 1 puis répliqué).
- **D-SCOPE-4** — Parité sync/async obligatoire (Core Value) ; `test_parity` enregistre les 5 nouveaux accessors.

**Open questions résolues au cadrage (2026-06-17):** `db.schema.*` reste un seul bloc (DDL + introspection) ; méthodes DataFrame restent à plat sur `db.*` ; `create_spatial_index`/`list_geometry_columns` → `db.spatial.*`.

**Reste à plat sur `db.*` (cœur transactionnel — non déménagé):** `create`, `create_from_env`, `engine`, `connect`, `cursor`, `transaction`, `session`, `in_session`, `execute`, `execute_many`, `insert_many`, `upsert_many`, `stream`, `notify`, `insert_batch`, `copy_insert`, `fetch_one`, `fetch_val`, les méthodes DataFrame, et les accessors existants (`spatial`, `etl`).

</details>

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
- ✓ `@deprecated_alias` decorator (sync + async) — uniform `DeprecationWarning` + correct `stacklevel`, delegates to accessor; the single shared mechanism for the whole deprecation cycle — v0.6.0 (REORG-01)
- ✓ 5 lazy accessors carved from the monolith: `db.timescale.*` (6), `db.admin.*` (11), `db.maint.*` (6), `db.backup.*` (4), `db.schema.*` (27) — bodies moved verbatim, validators preserved, full sync/async parity — v0.6.0 (TS-01, ADM-01, MNT-01, BKP-01, SCH-01)
- ✓ `create_spatial_index` / `list_geometry_columns` relocated to `db.spatial.*` for PostGIS thematic coherence — v0.6.0 (SCH-02)
- ✓ 56 backward-compatible flat aliases on each of `Database`/`AsyncDatabase` (warn + delegate, removal scheduled v0.7.0); internal call-sites rewritten through accessors; zero breaking change — v0.6.0 (REORG-02)
- ✓ `test_parity` registers all 5 new accessors (7-pair `ACCESSOR_PAIRS`); coverage ratchet held ≥94% (95.64%) with per-alias warn+delegate tests + green `-W error` gate — v0.6.0 (REORG-03, REORG-04)
- ✓ Accessor classes exported in `__all__`; README + Sphinx document `db.X.*`; CHANGELOG `[0.6.0]` + 56-row MIGRATION guide note the deprecation cycle — v0.6.0 (REORG-05)
- ✓ 56 deprecated flat aliases hard-removed from `Database`/`AsyncDatabase` (112 stubs); `aliases.py` deleted; removed names raise plain `AttributeError`; `test_parity`/`ACCESSOR_PAIRS` green — v0.7.0 (ALIAS-RM-01, ALIAS-RM-02)
- ✓ MIGRATION v0.6→v0.7 section with 1:1 flat→accessor table for all 56 names; CHANGELOG `[0.7.0]` Breaking entry — v0.7.0 (ALIAS-RM-03)
- ✓ Carried-forward debt closed by removal: WR-01 (IDE signature erasure on `py.typed` package) + IN-02 (stale flat-name error messages/guards) — v0.7.0 (ALIAS-RM-04)
- ✓ `Pipeline.incremental_column` (identifier-validated; `+ append/replace` forbidden at construction — incremental requires `upsert`) — v0.7.0 (ETL-INC-01)
- ✓ First-run full load records `max(col)`; subsequent runs apply `WHERE col > last_watermark` (exclusive, `%s`-parameterized; SQL sources subquery-wrapped) — v0.7.0 (ETL-INC-02, ETL-INC-03)
- ✓ High-water mark computed from the raw batch before transforms; missing watermark column raises a clear `ETL*` error (not bare `KeyError`) — v0.7.0 (ETL-INC-04)
- ✓ Empty batch records `success`/`rows_loaded=0` and preserves the prior watermark (never NULL); watermark read from last successful run, persisted only on success; failed run does not advance — v0.7.0 (ETL-INC-05, ETL-INC-06)
- ✓ `RunResult.watermark_used`/`watermark_recorded` (None for non-incremental); `history()`/`last_run()` surface them; `dry_run` previews the filter without writing a run row — v0.7.0 (ETL-INC-07, ETL-INC-08, ETL-INC-09)
- ✓ Typed JSONB envelope round-trips timestamp/integer/text watermarks without drift, zero new runtime deps — v0.7.0 (ETL-INC-10)
- ✓ Full sync/async incremental parity (`AsyncETLAccessor` mirrors the surface, covered by `test_accessor_parity`); `docs/etl.md` incremental section + backfill/reset workflow documented — v0.7.0 (ETL-INC-11, ETL-INC-12)
- ✓ v0.7.0 released to PyPI via OIDC: version bumped (2 sources), gates green (cov 95.11%, interrogate 100%, Sphinx `-W`, `-W error::DeprecationWarning`), tagged, clean-venv smoke confirmed — v0.7.0 (REL-07)
- ✓ Chunk inspection/management: `show_chunks` (list[str], oldest-first, `older_than`/`newer_than` filters) + `drop_chunks` (both-None `ValueError` before any DB round-trip, capture-before-drop `dry_run`, DESTRUCTIVE docstring) on both accessors — v0.8.0 (TS-ADV-04, TS-ADV-05)
- ✓ Partitioning & reorder: `add_dimension` (TSDB 2.x `by_hash`/`by_range` form, construction-time mutual-exclusivity `ValueError`, dup-dimension → `TimescaleError`) + `add_reorder_policy` (mock-authoritative SQL, Apache-license-tolerant live test) on both accessors — v0.8.0 (TS-ADV-08, TS-ADV-09)
- ✓ Continuous aggregate lifecycle: `create_continuous_aggregate` + `refresh_continuous_aggregate` via the `connect(autocommit=True)` seam (bypasses an enclosing `db.session()`) + `add_continuous_aggregate_policy` (plain execute, `_check_offset_ordering` guard), all sync + async — v0.8.0 (TS-ADV-01, TS-ADV-02, TS-ADV-03)
- ✓ Time-series query helpers: `time_bucket` (Apache-free, REAL live output) + `time_bucket_gapfill` (required positional `start`/`finish`, double-bound, TSL-only) with `into="df"/"rows"` routing via local `_to_named_binds`/`_check_into` — v0.8.0 (TS-ADV-06, TS-ADV-07)
- ✓ Full sync/async parity for all 9 new methods (`AsyncTimescaleAccessor` mirrors every method, `await`ed extension guard) enforced by `test_accessor_parity` + explicit 9-name surface assertion — v0.8.0 (TS-ADV-10)
- ✓ v0.8.0 released to PyPI via OIDC: version bumped (2 sources), CHANGELOG `[0.8.0]` Added-only, all 3 docs surfaces updated (timescaledb.md Advanced section + api-reference 15-row table + README "15 methods"), 4 gates green (cov 95.11%, interrogate 100%, Sphinx `-W`, `-W error::DeprecationWarning`), tagged, clean-venv smoke confirmed — v0.8.0 (REL-08)

### Active

<!-- Current scope. Building toward these. Full REQ-ID list in REQUIREMENTS.md. -->

**v0.9.0 "CRUD ergonomique + introspection enrichie"** — additive convenience over the existing API, full sync/async parity, low risk. Full REQ-ID list in `.planning/REQUIREMENTS.md`.

- **CRUD ergonomics:** `upsert` (singulier), `delete_where`, `update_where`, `exists`, `count`, `paginate`, dict-fetch.
- **Introspection helpers:** `primary_key()`, `foreign_keys()`, `sequences()`, `views()`, `describe()` — extend `db.schema.*` (no `db.meta.*` carve).

Then **v1.0.0 "Spatial v2 + stabilisation"**.

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

Shipped v0.8.0 (2026-06-23). Purely additive on `pycopg/timescale.py`: 9 new time-series methods (sync + async) grow the `db.timescale.*` surface from 6 to 15 — `show_chunks`/`drop_chunks`/`add_dimension`/`add_reorder_policy` (chunk & dimension management), `create_continuous_aggregate`/`refresh_continuous_aggregate`/`add_continuous_aggregate_policy` (cagg lifecycle via the `connect(autocommit=True)` seam), and `time_bucket`/`time_bucket_gapfill` (query helpers, `into="df"/"rows"`). New milestone-wide `TimescaleError(PycopgError)` in `exceptions.py`; new `TSDB_SHOW_CHUNKS`/`TSDB_DROP_CHUNKS` SQL constants in `queries.py`; new `tests/test_timescale.py` (sync `ts_db` + `async_ts_db` skip-fixtures, two-layer mock + live coverage). Community/TSL-only operations (caggs, gapfill, reorder) tested mock-authoritative + Apache-license-tolerant live. No breaking change, no migration. Zero new runtime dependencies.
Tech stack: Python 3.11+, psycopg 3, psycopg_pool, pandas, geopandas, tenacity, Sphinx; uv toolchain (dev + CI + build), hatchling backend.
Codebase: ~15,112 LOC lib (`pycopg/`).
Test coverage: 95.11% with real PostgreSQL (`pycopg_test` + a TimescaleDB-enabled `ts_db` fixture); coverage ratchet at `--cov-fail-under=94`.
Docs: numpydoc, `interrogate` 100% (gate ≥95), Sphinx `-W` green, ReadTheDocs live; `docs/timescaledb.md` rewritten to first-class `db.timescale.*` calls + Advanced Chunk & Dimension Management section; `api-reference.md` 15-row timescale table; `docs/etl.md` incremental-loading section. CHANGELOG `[0.8.0]` Added-only (no MIGRATION — purely additive).

**Known tech debt:**

- **2 pre-existing flaky full-suite DB tests** (`TestAsyncIntegration::test_async_transaction_fix`, `TestPostGISErrorHandling::test_create_spatial_index_name_parameter`) — `UndefinedTable` fixture-isolation bug in the spatial/integration suites, NOT ETL code; fail identically in isolation; did not affect the coverage threshold. Worth a fixture-isolation fix in a future cleanup. (See STATE.md Deferred Items.)
- New (v0.7.0): one ~2.7% flaky bound-param test surfaced during Phase 28 (orchestrator-fixed); watch for re-flake. (See RETROSPECTIVE.md.)
- Coverage-95 stretch still deferred — gate honest at 94 (measured 95.11% at v0.8.0 ship); remaining headroom is DB/IO paths structurally out of scope.
- `TableNotFound` exported in `__all__` but has no internal raise site (user-`except` only) — benign.
- `CLAUDE.md` "Version" line still reads v0.5.0 (stale) — actual shipped is v0.8.0; cosmetic doc lag (carried since v0.6.0).
- Stale `pycopg.aliases` Sphinx cross-reference in accessor docstrings (IN-01/IN-02 carry-forward, cosmetic — `aliases.py` was deleted in v0.7.0).
- v0.8.0 code-review warnings deferred (advisory, not blocking): WR-01 case-sensitive `time_bucket(` cagg guard; WR-03 INTERVAL-literal-vs-`%s`; `%`/`%s` in caller-supplied structural `aggregates`/`where` breaks the rows/named-bind path (caller-error UX, not injection); IN-03 fragile `chunk_seq` helper.
- Nyquist: phases 22–24 VALIDATION.md left `draft`/`nyquist_compliant: false` (verified PASSED via VERIFICATION.md; missing formal sign-off, not a coverage gap — see STATE.md Deferred Items).
- Database class is organized under accessors (`spatial`/`etl`/`timescale`/`admin`/`maint`/`backup`/`schema`) with the transactional core kept flat by design; the public surface is accessor-only (no flat aliases).

**Resolved in v0.8.0:**

- TimescaleDB advanced surface delivered end-to-end at full sync/async parity (TS-ADV-01..10): chunk & dimension management, full continuous-aggregate lifecycle via the `connect(autocommit=True)` seam, and `time_bucket`/`time_bucket_gapfill` query helpers — `db.timescale.*` grows 6 → 15 methods. Purely additive, no migration.
- License reality mapped: `time_bucket` + basic chunk ops are Apache-free; caggs, gapfill, and reorder policies are Community/TSL-only — documented in `docs/timescaledb.md`, tested mock-authoritative + Apache-tolerant live.
- All of v0.3.0, v0.3.1, v0.4.0, v0.5.0, v0.6.0, v0.7.0, v0.8.0 live on PyPI.

**Resolved in v0.7.0:**

- The 56 deprecated flat aliases removed (one deprecation cycle served in v0.6.0); public surface is accessor-only (ALIAS-RM-01..04). Closed WR-01 (IDE signature erasure) and IN-02 (stale flat-name error messages) — both carried forward from v0.6.0.
- Watermark-based incremental ETL delivered end-to-end at full sync/async parity (ETL-INC-01..12); the v0.5.0-reserved `watermark JSONB` column wired with no breaking migration.

**Still deferred to a future milestone:**

- TimescaleDB follow-ups (out of v0.8.0 surface): `drop_continuous_aggregate`/`remove_continuous_aggregate_policy` lifecycle removal (TSDB-F01), `time_bucket` `origin`/`offset` alignment (TSDB-F02), `compress_chunk`/`decompress_chunk` per-chunk control (TSDB-F03), `show_chunks` physical-time filters (TSDB-F04).
- ETL incremental follow-ups: `initial_watermark` first-run bound (ETL-INC-F01), configurable `>=`/lookback boundary (ETL-INC-F02), multi-column watermarks (ETL-INC-F03), advisory-lock concurrency (ETL-INC-F04), CDC/WAL change capture (ETL-INC-F05).
- v0.9.0 (next candidate): CRUD ergonomique + introspection enrichie. v1.0.0: spatial v2 + API stabilisation.
- API-01: Named parameter support (:name syntax)
- API-02: Connection health checks
- API-03: Structured logging
- API-04: Transaction isolation level control
- API-05: Savepoint support (nested transactions)
- API-06: Sync result streaming
- ARCH-02: Dynamic connection pool sizing
- ETL cross-DB transfer and DataFrame/CSV/parquet source/sink — deferred; ETL is same-DB only

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
| v0.5.0: same-DB only; Python-callable transforms (not SQL-only) | Scope control; leans on existing pandas/geopandas integration | ✓ Good — cross-DB/file sinks cleanly deferred |
| v0.5.0: async transforms via `asyncio.to_thread` (D-/SC-2) | Sync transform callables must not block the event loop | ✓ Good — behavioral test proves non-blocking dispatch |
| v0.5.0: PyPI publish human-gated at the irreversible step | Supply-chain publish needs maintainer sign-off | ✓ Good — executor stopped at the boundary; published after explicit approval |
| v0.6.0: transition via thin deprecated alias + `DeprecationWarning`, not a hard break (D-SCOPE-1) | Published PyPI lib; zero brutal breakage; clean API still the core value | ✓ Good — 56 aliases warn+delegate, removal scheduled v0.7.0, no caller broken |
| v0.6.0: real logic lives in the accessor; old `db.*` becomes the wrapper (D-SCOPE-2) | Makes v0.7.0 alias removal a single-block deletion with no logic touched | ✓ Good — `@deprecated_alias` decorator centralizes warn+delegate; bodies moved verbatim |
| v0.6.0: all 5 accessors in one milestone (D-SCOPE-3) | Mechanical repetitive work — validate the pattern at Phase 21, replicate Phases 22-24 | ✓ Good — pattern proved once, replicated cleanly across admin/maint/backup/schema |
| v0.6.0: sync/async parity enforced for every accessor (D-SCOPE-4) | Core value; a method moved on one side but not the other would break parity | ✓ Good — 7-pair `ACCESSOR_PAIRS`, `test_accessor_parity` green both directions |
| v0.6.0: `db.schema.*` kept as one block, not split into `db.meta.*` | Group by domain (like spatial/etl), not by operation type; carve later on clean surface | ✓ Good — single 27-method accessor; `db.meta.*` carve reconsidered at v0.9.0 |
| v0.6.0: DataFrame methods + transactional core stay flat on `db.*` | Daily-use / core API; accessors are for thematic method families | ✓ Good — `execute`/`session`/`to_dataframe`/… unchanged |
| v0.6.0: `create_spatial_index`/`list_geometry_columns` → `db.spatial.*`, not `db.schema.*` | Thematic PostGIS coherence over DDL grouping | ✓ Good — relocated verbatim; PostGIS guard now also covers the deprecated flat path (D-06) |
| v0.6.0: deprecated stubs use `(*args, **kwargs)` signatures (WR-01) | Single uniform decorator beats 56 hand-copied signature wrappers | ✓ Resolved — aliases removed in v0.7.0; IDE signature erasure gone, surface is accessor-only with full type info |
| v0.7.0: hard-remove the 56 aliases (no second deprecation cycle) | One deprecation cycle = one version; cycle already served in v0.6.0; real logic lives in accessors (D-SCOPE-2 → one-block deletion) | ✓ Good — `aliases.py` deleted, removed names raise plain `AttributeError`, MIGRATION + Breaking CHANGELOG shipped, no caller silently broken |
| v0.7.0: incremental ETL declarative via `Pipeline.incremental_column` (no callbacks) | Inspectable, mirrors the frozen-dataclass `Pipeline` design; derives the filter + high-water mark from one field | ✓ Good — field validated at construction, `WHERE col > %s` derived, `max(col)` recorded |
| v0.7.0: incremental requires `upsert`; `append` AND `replace` forbidden at construction | Non-unique watermark columns silently drop boundary rows under `append`; `replace` truncates the whole target — only `upsert` is idempotent | ✓ Good — `ValueError` at construction for both forbidden combos, tested both sides |
| v0.7.0: high-water mark = `max(col)` from the RAW batch before transforms; advance only on success; empty batch preserves prior watermark | Watermark must reflect what was actually extracted from source, independent of transform reshaping; never regress or write NULL | ✓ Good — invariants proven on live DB (first-run/empty/failed paths) |
| v0.7.0: typed JSONB envelope for the watermark (`_encode`/`_decode`), zero new deps | `pipeline_runs.watermark JSONB` (reserved v0.5.0) must round-trip int/str/datetime without tz/precision drift | ✓ Good — reserved column now in use, no breaking migration, round-trip verified for all 3 types |
| v0.7.0: `RunResult.watermark_used/recorded` (None for non-incremental) + incremental `dry_run` preview | Surface the filter floor + new high-water mark for inspection without writing a run row | ✓ Good — both fields on `RunResult`/`history()`/`last_run()`; `dry_run` previews without persisting |
| v0.5.0: reserve a nullable `watermark JSONB` column, always NULL | Lets incremental support slot on with no breaking migration | ✓ Good — incremental ETL shipped v0.7.0 (ETL-INC-*) using exactly this column; no breaking migration needed |
| v0.8.0: target TimescaleDB 2.x only; the v0.6.0 `db.timescale.*` accessor is the base, extended via the same builder-pur pattern | One feature family per milestone on a clean accessor; no new connection seams except where DDL requires it | ✓ Good — 9 methods added on both accessors, `test_accessor_parity` green, zero new deps |
| v0.8.0: cagg `create`/`refresh` run on a dedicated `connect(autocommit=True)` connection; policy uses plain `execute` (D-01) | CAGG DDL + refresh cannot run inside a transaction block; the auto-refresh policy can | ✓ Good — autocommit seam proven to bypass an enclosing `db.session()`; 3 prior policy methods matched |
| v0.8.0: `drop_chunks` raises `ValueError` when both bounds are None, before any DB round-trip; `dry_run` captures-before-drop | A destructive op with no bounds would wipe the whole hypertable; preview must not delete | ✓ Good — guard fires pre-flight, `dry_run` previews via `show_chunks` |
| v0.8.0: `add_dimension` uses the TSDB 2.x `by_hash`/`by_range` builder form with construction-time mutual-exclusivity `ValueError`; dup-dimension → `TimescaleError` | 2.28's builder form replaced the legacy positional API; the "non-empty hypertable raises" behavior no longer exists (D-08 reshaped) | ✓ Good — validated against live TSDB 2.28; 13 regression tests |
| v0.8.0: query helpers use a LOCAL `_to_named_binds`/`_check_into` (not imported from spatial); `into ∈ {df, rows}` (gdf rejected) | Avoid a timescale→spatial import coupling; gdf is meaningless for time-series rows | ✓ Good — local copies, `into="gdf"` raises before any DB call |
| v0.8.0: D-08 REVERSED at plan time — `time_bucket` Apache-free (REAL live tests) but `gapfill`/caggs/reorder Community/TSL-only | Live verification against local Apache 2.28 contradicted the CONTEXT assumption; tests must not assert features the license lacks | ✓ Good — split verdict: mock-authoritative + license-tolerant `try/except FeatureNotSupported` live |

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

*Last updated: 2026-06-19 — milestone v0.6.0 "Réorganisation en accessors" CLOSED via `/gsd-complete-milestone`. Full PROJECT.md evolution review: "What This Is" → v0.6.0 (already done at phase close); all 11 v0.6.0 requirements (REORG-01..05, TS/ADM/MNT/BKP/SCH-01, SCH-02) moved to Validated; Active emptied; "Current Milestone" reframed as "Next Milestone Goals" (v0.7.0 alias removal + ETL incremental → v0.8.0 TSDB avancé → v0.9.0 CRUD → v1.0.0 spatial v2), v0.6.0 goal/decisions collapsed to historical reference; Context refreshed (95.64% coverage, 5 new accessor modules ~3,800 LOC, WR-01 tech debt recorded); 8 v0.6.0 Key Decisions outcomes added (D-SCOPE-1..4 + 4 scoping calls). ROADMAP collapsed + REQUIREMENTS/audit archived to `milestones/v0.6.0-*`. Milestone audit passed (11/11 reqs, integration clean). Next: `/gsd-new-milestone`.*

*Last updated: 2026-06-19 — milestone v0.7.0 "Alias Removal + Incremental ETL" started via `/gsd-new-milestone`. Goal: solder la dette de dépréciation v0.6.0 (hard-remove des 56 alias plats — ALIAS-RM-01) + livrer l'ETL incrémental (watermarks CDC via `pipeline_runs.watermark JSONB` réservée en v0.5.0 — ETL-INC-01). Scope locked au cadrage : watermark déclaratif via `incremental_column` (pas de callback), high-water mark = `max(col)` du batch, sources SQL enveloppées (subquery + WHERE), premier run = full load puis record, incrémental réservé à `load_mode` ∈ {append, upsert} (`replace` interdit), suppression d'alias = hard remove + MIGRATION v0.6→v0.7 + note Breaking. Active set au scope v0.7.0. Phase numbering continues from Phase 25. Suite validée (FUTURE-MILESTONES) : v0.8.0 TSDB avancé → v0.9.0 CRUD → v1.0.0 spatial v2.*

*Last updated: 2026-06-17 — Phase 21 "Infrastructure & Timescale Accessor" complete (3/3 plans, verification PASSED 4/4). Le pattern alias+accessor est désormais établi de bout en bout et prouvé : `pycopg/aliases.py` (`@deprecated_alias` — `stacklevel=2`, branche `iscoroutinefunction`, sans eval/exec, réutilisé tel quel par les Phases 22-24) + `pycopg/timescale.py` (`TimescaleAccessor`/`AsyncTimescaleAccessor`, 6 méthodes déplacées verbatim avec `self.`→`self._db.`). `db.timescale.*` / `async_db.timescale.*` câblés en propriétés lazy (cache `_timescale`, miroir de `_spatial`/`_etl`) ; les 6 méthodes plates sync + 6 async sont des stubs `@deprecated_alias` qui warn + délèguent (zéro breaking change). Registre data-driven `ACCESSOR_PAIRS` + `test_accessor_parity` (sync↔async), `test_timescale_aliases.py` (warn+delegate par alias), 27 call-sites migrés. Gates : suite complète 994 passants (2 échecs DB pré-existants connus), `-W error::DeprecationWarning` vert (295), coverage 94.46% (ratchet ≥94 tenu). Revue de code : 0 critique, 4 warnings advisory (notamment WR-01 : signatures `(*args, **kwargs)` dégradant le typage statique sur ce package `py.typed` ; WR-02 : README/docs documentent encore l'API plate dépréciée). REORG-01/02/03/04 + TS-01 validés. Next : Phase 22 (Admin, Maint & Backup accessors).*

*Last updated: 2026-06-22 — milestone v0.8.0 "TimescaleDB avancé" started via `/gsd-new-milestone`. Goal: livrer les features time-series phares manquantes sous `db.timescale.*` (qui n'a aujourd'hui que hypertable/compression/rétention) — continuous aggregates (cycle complet create+refresh+policy), `time_bucket`/`time_bucket_gapfill` (helpers de requête, builders SQL purs), `show_chunks`/`drop_chunks`, `add_dimension`, `reorder_policy`. Scope locked au cadrage (2026-06-22) : cible TimescaleDB 2.x uniquement, pattern builder-pur + accessor lazy (validate_identifiers + `%s`), parité sync/async obligatoire, continuous aggregates en cycle complet, time_bucket = helpers de requête (pas DDL), fence TimescaleDB-only (ETL follow-ups F01-F05 reportés à un milestone ETL ultérieur), zéro nouvelle dépendance. Active set au scope v0.8.0. Phase numbering continues from Phase 29 (v0.8.0 démarre à la Phase 30). Suite validée (FUTURE-MILESTONES) : v0.9.0 CRUD → v1.0.0 spatial v2.*

*Last updated: 2026-06-22 — milestone v0.7.0 "Alias Removal + Incremental ETL" CLOSED via `/gsd-complete-milestone`. Full PROJECT.md evolution review: "What This Is" → v0.7.0 (incremental ETL + accessor-only surface); Current State → v0.7.0 SHIPPED, v0.6.0 demoted to "Previously shipped"; all 17 v0.7.0 requirements (ALIAS-RM-01..04, ETL-INC-01..12, REL-07) moved to Validated; Active emptied; "Current Milestone" reframed as "Next Milestone Goals" (v0.8.0 TimescaleDB avancé → v0.9.0 CRUD → v1.0.0 spatial v2), v0.7.0 goal/decisions collapsed to historical reference; Context refreshed (95.11% coverage, ~13,327 lib + ~15,690 test LOC, WR-01/IN-02 resolved by removal, incremental follow-ups F01-F05 deferred); 8 v0.7.0 Key Decisions outcomes added + WR-01 flipped ⚠️→✓ Resolved + watermark-JSONB Pending→✓ Good. ROADMAP collapsed + REQUIREMENTS archived to `milestones/v0.7.0-*`. Pre-flight: open-artifact audit clean, 17/17 requirements complete. Next: `/gsd-new-milestone` (v0.8.0).*

*Last updated: 2026-06-22 — Phase 30 "Chunk Management & Partitioning" complete (3/3 plans, verification PASSED 5/5). Four new methods on both `TimescaleAccessor` and `AsyncTimescaleAccessor` via the established pure-builder pattern (no new connection seams): `show_chunks`/`drop_chunks` (TS-ADV-04/05) and `add_dimension`/`add_reorder_policy` (TS-ADV-08/09). New milestone-wide `TimescaleError(PycopgError)` in `exceptions.py` (D-09, reused Phases 31-32); `TSDB_SHOW_CHUNKS`/`TSDB_DROP_CHUNKS` SQL constants in `queries.py` (literal `%%I.%%I` regclass JOIN + `range_start ASC`); new `tests/test_timescale.py` (sync `ts_db` + `async_ts_db` skip-fixtures). Key behaviors: `drop_chunks` both-None `ValueError` fires before any DB round-trip (D-03) + capture-before-drop `dry_run`; `add_dimension` uses TSDB 2.28 `by_hash`/`by_range` form (D-06) with construction-time mutual-exclusivity `ValueError` (D-07) and the RESHAPED D-08 (wrap the duplicate-dimension DB error as `TimescaleError`, only with `if_not_exists=False` — the legacy "non-empty hypertable raises" behavior does not exist on 2.28); `add_reorder_policy` mock-authoritative + live FeatureNotSupported tolerance under Apache license (D-12). Ran sequential-on-main (3 single-plan waves, strict dep chain, no worktrees). Code review: 0 critical, 4 warnings — WR-01 (narrowed `add_dimension` `except Exception`→`except DatabaseError` so non-DB errors propagate), WR-03 (`number_partitions` positive-int validation), WR-04 (reject non-str/non-datetime chunk bounds on the destructive path) fixed in 1325f29 with 13 regression tests; deferred IN-01 (stale `pycopg.aliases` docstring drift — recurring), IN-03 (fragile `chunk_seq` helper). Gates: full suite 1239 passed, `test_accessor_parity` 7/7, coverage 94.98% (ratchet ≥94 held); 2 pre-existing flaky DB tests unrelated to this phase. TS-ADV-04/05/08/09 validated; TS-ADV-10 full-9-method parity remains Phase 32. Next: `/gsd-discuss-phase 31` (Continuous Aggregate Lifecycle).*

*Last updated: 2026-06-23 — milestone v0.8.0 "TimescaleDB avancé" CLOSED via `/gsd-complete-milestone`. Full PROJECT.md evolution review: "What This Is" → v0.8.0 (advanced TimescaleDB surface, `db.timescale.*` 6→15 methods); Current State → v0.8.0 SHIPPED (done at Phase 33 close); all 11 v0.8.0 requirements (TS-ADV-01..10, REL-08) moved to Validated; Active emptied (next = v0.9.0 CRUD candidate); "Current Milestone" reframed as "Next Milestone Goals" (v0.9.0 CRUD → v1.0.0 spatial v2), v0.8.0 goal/decisions collapsed to historical reference (incl. the D-08 license reversal); Context refreshed (~15,112 lib LOC, 95.11% coverage, TSDB-F01..04 + ETL-INC-F01..05 deferred, v0.8.0 review warnings recorded as cosmetic/advisory debt); 7 v0.8.0 Key Decisions outcomes added. ROADMAP collapsed + REQUIREMENTS archived to `milestones/v0.8.0-*`. Pre-flight: open-artifact audit clean, 11/11 requirements complete. Tag `v0.8.0` already created at Phase 33 (PyPI publish). Next: `/gsd-new-milestone` (v0.9.0).*

*Last updated: 2026-06-24 — milestone v0.9.0 "CRUD ergonomique + introspection enrichie" started via `/gsd-new-milestone`. Goal: convenience additif sur l'API existante (faible risque) — helpers CRUD ergonomiques (`upsert` singulier, `delete_where`, `update_where`, `exists`, `count`, `paginate`, dict-fetch) + introspection enrichie (`primary_key()`, `foreign_keys()`, `sequences()`, `views()`, `describe()`). Scope locked au cadrage (2026-06-24) : les DEUX familles de features dans ce milestone ; placement = tout reste sur `db.schema.*` / cœur transactionnel à plat — PAS de carve `db.meta.*` (la question ouverte de v0.6.0 est tranchée : purement additif, pas de nouveau cycle de dépréciation sur une surface fraîchement assainie) ; pattern builder-pur + accessor (`validate_identifiers` d'abord, valeurs user en `%s`, parité `test_accessor_parity`) ; parité sync/async obligatoire (Core Value) ; zéro nouvelle dépendance runtime ; cliquet de couverture tenu ≥94% (baseline 95.11%). Active set au scope v0.9.0. Phase numbering continues from Phase 33 (v0.9.0 démarre à la Phase 34). Suite validée (FUTURE-MILESTONES) : v1.0.0 spatial v2 + stabilisation API.*

*Last updated: 2026-06-23 — Phase 32 "Query Helpers & Parity Verification" complete (2/2 plans, verification PASSED 8/8) — LAST v0.8.0 feature phase. The two read-only query helpers `time_bucket` (TS-ADV-06) and `time_bucket_gapfill` (TS-ADV-07) ship on both `TimescaleAccessor` and `AsyncTimescaleAccessor` via the established pure-builder + lazy-accessor pattern: module-level `_build_time_bucket_sql` / `_build_time_bucket_gapfill_sql` (validate_identifiers-first, fixed `AS bucket` alias D-01, `GROUP BY bucket ORDER BY bucket`), a LOCAL `_to_named_binds` (`%s`→`:pN`, D-06 — not imported from spatial) and a timescale-local `_check_into` (`_VALID_INTO = ("df","rows")`, the INVERSE of spatial's set, D-03), and sync+async `_run` dispatchers routing `into="df"` through `to_dataframe(sql=named, params=dict)` and `into="rows"` through `execute`. Key behaviors: `into="gdf"` raises `ValueError` before any DB call (guard runs first); `time_bucket_gapfill` takes REQUIRED positional `start`/`finish` (no WHERE-inference) bound TWICE — params `[bucket_width, start, finish, start, finish]`, 5 `%s` (D-10); async methods correctly `await self._db.schema.has_extension(...)` (the recurring Phase-23/30/31 missing-`await` regression did NOT recur). MATERIAL milestone correction: D-08 was REVERSED at plan time via live verification — `time_bucket` is Apache-free (live tests assert REAL output) but `time_bucket_gapfill`/`locf`/`interpolate` raise `FeatureNotSupported` under the local Apache 2.28.0 license (TSL-only, EXACTLY like Phase-31 caggs), so the gapfill live test uses the Phase-31 license-tolerant `try/except FeatureNotSupported` with the mock SQL-shape test as authoritative. TS-ADV-10 full 9-method sync/async parity confirmed via the existing `test_accessor_parity` (no `ACCESSOR_PAIRS` change) plus a new explicit 9-name `test_timescale_v080_surface` set-membership assertion. Ran sequential-on-main (2 single-plan waves, strict dep chain, no worktrees). Code review: 0 critical, 1 warning (WR-01 — literal `%`/`%s` in caller-supplied structural `aggregates`/`where` breaks the rows/named-bind path; inherited from the spatial `_to_named_binds` precedent, caller-error UX not injection — deferred, advisory), 4 info. Gates: full suite 1288 passed, coverage 95.11% (ratchet ≥94 held); the 2 pre-existing flaky DB tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`) fail in files Phase 32 never touched — not regressions. TS-ADV-06/07/10 validated; all 11 v0.8.0 feature requirements now complete. Next: `/gsd-discuss-phase 33` (Release v0.8.0 — REL-08, the LAST phase).*
