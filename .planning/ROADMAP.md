# Roadmap: pycopg

## Milestones

- ✅ **v0.3.0 Consolidation Release** — Phases 1-7 (shipped 2026-02-11)
- ✅ **v0.3.1 Security Hotfix** — injections SQL corrigées (shipped PyPI 2026-06-06)
- ✅ **v0.4.0 Quality & Spatial Helpers** — Phases 9-15 (shipped 2026-06-14)
- ✅ **v0.5.0 ETL Pipeline Runner** — Phases 16-20 (shipped 2026-06-15)
- ✅ **v0.6.0 Réorganisation en accessors** — Phases 21-24 (shipped 2026-06-19)
- ✅ **v0.7.0 Alias Removal + Incremental ETL** — Phases 25-29 (shipped 2026-06-22)
- ✅ **v0.8.0 TimescaleDB avancé** — Phases 30-33 (shipped 2026-06-23)
- 🚧 **v0.9.0 CRUD ergonomique + introspection enrichie** — Phases 34-36 (in progress)

## Phases

<details>
<summary>🚧 v0.9.0 CRUD ergonomique + introspection enrichie (Phases 34-36) — IN PROGRESS</summary>

- [x] **Phase 34: CRUD Ergonomics** - Convenience CRUD helpers on the flat transactional core (upsert singular, delete_where, update_where, exists, count, paginate, dict-fetch) with full sync/async parity (completed 2026-06-24)
- [ ] **Phase 35: Schema Introspection** - Enriched `db.schema.*` helpers (primary_key, foreign_keys, sequences, views, describe) with full sync/async parity
- [ ] **Phase 36: Release v0.9.0** - Version bump, CHANGELOG Added-only, docs surfaces, 4 gates, human-gated OIDC publish + tag + smoke

</details>

<details>
<summary>✅ v0.8.0 TimescaleDB avancé (Phases 30-33) — SHIPPED 2026-06-23</summary>

- [x] Phase 30: Chunk Management & Partitioning (3/3 plans) — `show_chunks`, `drop_chunks` (both-None ValueError + dry_run), `add_dimension` (by_hash/by_range), `add_reorder_policy` on both accessors — completed 2026-06-22
- [x] Phase 31: Continuous Aggregate Lifecycle (3/3 plans) — `create`/`refresh` via `connect(autocommit=True)` seam + `add_continuous_aggregate_policy` — completed 2026-06-23
- [x] Phase 32: Query Helpers & Parity Verification (2/2 plans) — `time_bucket` + `time_bucket_gapfill` with `into="df"/"rows"`, 9-method sync/async parity (TS-ADV-10) — completed 2026-06-23
- [x] Phase 33: Release v0.8.0 (3/3 plans) — version bump, CHANGELOG Added, docs, 4 gates, human-gated tag + PyPI publish — completed 2026-06-23

Full details: [milestones/v0.8.0-ROADMAP.md](milestones/v0.8.0-ROADMAP.md) · Requirements: [milestones/v0.8.0-REQUIREMENTS.md](milestones/v0.8.0-REQUIREMENTS.md)

</details>

<details>
<summary>✅ v0.7.0 Alias Removal + Incremental ETL (Phases 25-29) — SHIPPED 2026-06-22</summary>

- [x] Phase 25: Alias Removal (5/5 plans) — hard-remove 56 `@deprecated_alias` stubs from both classes, delete `aliases.py`, close WR-01/IN-02 — completed 2026-06-19
- [x] Phase 26: Incremental ETL — Pure Layer (1/1 plan) — `Pipeline.incremental_column` + guards, `_build_incremental_extract_sql`, JSONB encode/decode — completed 2026-06-20
- [x] Phase 27: Incremental ETL — Run-Log Integration (1/1 plan) — `_read_watermark` + success-only `_end_run(watermark=)` + JSONB round-trip — completed 2026-06-20
- [x] Phase 28: Incremental ETL — Extract, RunResult & Async Parity (3/3 plans) — wire filter into `run()`, `RunResult.watermark_used/recorded`, `dry_run`, async 1:1 mirror, docs — completed 2026-06-21
- [x] Phase 29: Release v0.7.0 (3/3 plans) — version bump, CHANGELOG Breaking/Added, MIGRATION v0.6→v0.7, gates, tag + PyPI publish — completed 2026-06-22

Full details: [milestones/v0.7.0-ROADMAP.md](milestones/v0.7.0-ROADMAP.md) · Requirements: [milestones/v0.7.0-REQUIREMENTS.md](milestones/v0.7.0-REQUIREMENTS.md)

</details>

<details>
<summary>✅ v0.6.0 Réorganisation en accessors (Phases 21-24) — SHIPPED 2026-06-19</summary>

- [x] Phase 21: Infrastructure & Timescale Accessor (3/3 plans) — `@deprecated_alias` decorator + timescale accessor (pattern proof) — completed 2026-06-17
- [x] Phase 22: Admin, Maint & Backup Accessors (3/3 plans) — 3 smaller accessors (11 + 6 + 4 methods) — completed 2026-06-17
- [x] Phase 23: Schema Accessor & Spatial Relocation (4/4 plans) — schema (27 methods) + 2 spatial methods → `db.spatial.*` — completed 2026-06-17
- [x] Phase 24: Exports, Docs & Release v0.6.0 (3/3 plans) — exports + README/Sphinx/CHANGELOG/MIGRATION + tag + PyPI publish — completed 2026-06-19

Full details: [milestones/v0.6.0-ROADMAP.md](milestones/v0.6.0-ROADMAP.md) · Requirements: [milestones/v0.6.0-REQUIREMENTS.md](milestones/v0.6.0-REQUIREMENTS.md) · Audit: [milestones/v0.6.0-MILESTONE-AUDIT.md](milestones/v0.6.0-MILESTONE-AUDIT.md)

</details>

<details>
<summary>✅ v0.5.0 ETL Pipeline Runner (Phases 16-20) — SHIPPED 2026-06-15</summary>

- [x] Phase 16: Pure ETL Layer — Pipeline dataclass, SQL constants, pure builders (2/2 plans) — completed 2026-06-14
- [x] Phase 17: Run-Tracking Foundation — `pipeline_runs` DDL + separate-connection run-log writes (2/2 plans) — completed 2026-06-15
- [x] Phase 18: Load Modes & Extract — extract (SQL/table), append/replace/upsert, transform chain (3/3 plans) — completed 2026-06-15
- [x] Phase 19: Sync Runner & Query Surface — `run()`, `RunResult`, `history()`, `last_run()`, `dry_run` (3/3 plans) — completed 2026-06-15
- [x] Phase 20: Async Parity, Wiring & Release — `AsyncETLAccessor`, lazy `db.etl`/`async_db.etl`, `TestEtlParity`, v0.5.0 PyPI publish (3/3 plans) — completed 2026-06-15

Full details: [milestones/v0.5.0-ROADMAP.md](milestones/v0.5.0-ROADMAP.md) · Requirements: [milestones/v0.5.0-REQUIREMENTS.md](milestones/v0.5.0-REQUIREMENTS.md)

</details>

<details>
<summary>✅ v0.4.0 Quality & Spatial Helpers (Phases 9-15) — SHIPPED 2026-06-14</summary>

- [x] Phase 9: Migration uv (outillage : dev + CI + build + lockfile) — completed 2026-06-06
- [x] Phase 10: Sécurité résiduelle & robustesse (bugs B1/B2/B3/B5) — coverage cliquet → 80 — completed 2026-06-08
- [x] Phase 11: Parité sync/async complète — coverage cliquet → 90 — completed 2026-06-09
- [x] Phase 12: Refactoring (brancher base.py + queries.py) — coverage cliquet → 92 (95 stretch deferred) — completed 2026-06-09
- [x] Phase 13: Qualité documentaire (docstrings numpydoc + interrogate ≥ 95) — completed 2026-06-10
- [x] Phase 14: Spatial helpers (`db.spatial.*`, ex-Phase 8) — coverage cliquet → 94 — completed 2026-06-12
- [x] Phase 15: Release v0.4.0 (PyPI + ReadTheDocs) — completed 2026-06-14

Full details: [milestones/v0.4.0-ROADMAP.md](milestones/v0.4.0-ROADMAP.md) · Requirements: [milestones/v0.4.0-REQUIREMENTS.md](milestones/v0.4.0-REQUIREMENTS.md) · Audit: [milestones/v0.4.0-MILESTONE-AUDIT.md](milestones/v0.4.0-MILESTONE-AUDIT.md)

</details>

<details>
<summary>✅ v0.3.0 Consolidation Release (Phases 1-7) — SHIPPED 2026-02-11</summary>

- [x] Phase 1: Bug Fixes & Foundation (2/2 plans) — completed 2026-02-11
- [x] Phase 2: AsyncDatabase DataFrame Parity (2/2 plans) — completed 2026-02-11
- [x] Phase 3: AsyncDatabase Admin/Backup Parity (2/2 plans) — completed 2026-02-11
- [x] Phase 4: AsyncDatabase Extensions Parity (2/2 plans) — completed 2026-02-11
- [x] Phase 5: Resilience & Configuration (2/2 plans) — completed 2026-02-11
- [x] Phase 6: Test Coverage (2/2 plans) — completed 2026-02-11
- [x] Phase 7: Documentation & Release (2/2 plans) — completed 2026-02-11

Full details: [milestones/v0.3.0-ROADMAP.md](milestones/v0.3.0-ROADMAP.md)

</details>

## Phase Details

### Phase 34: CRUD Ergonomics

**Goal**: Users can call ergonomic single-row and predicate-driven CRUD helpers on `Database` and `AsyncDatabase` next to their existing batch analogs, with full sync/async parity
**Depends on**: Nothing new (additive over existing transactional core)
**Requirements**: CRUD-01, CRUD-02, CRUD-03, CRUD-04, CRUD-05, CRUD-06, CRUD-07, CRUD-08
**Success Criteria** (what must be TRUE):

  1. User can call `db.upsert(table, row, conflict_columns)` to upsert a single row and receive the affected/returned row back
  2. User can call `db.delete_where(table, where={...})` and receive the count of deleted rows; columns are identifier-validated, values bound as `%s`
  3. User can call `db.update_where(table, values={...}, where={...})` to update rows matching AND-ed equality conditions and receive the count of updated rows
  4. User can call `db.exists(table, where={...})` and `db.count(table, where=None|{...})` to check/count rows without fetching result sets
  5. User can call `db.paginate(table, limit, offset, order_by, where)` to retrieve a specific page of rows, and `db.fetch_as_dicts(sql)` (or equivalent) to get results as `list[dict]` instead of tuples
  6. Every new CRUD method is callable identically on `AsyncDatabase`, and `test_accessor_parity` enumerates and verifies each pair**Plans**: 3 plans

**Wave 1**

- [x] 34-01-PLAN.md — Shared `_build_where_dict` pure builder (validated dict→`%s` WHERE fragment) in base.py + unit tests [Wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 34-02-PLAN.md — Write helpers: `upsert` (RETURNING *), `delete_where`, `update_where` (empty-where guard, rowcount) on both classes + live-DB tests [Wave 2]

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 34-03-PLAN.md — Read helpers: `exists`, `count`, `paginate`, `fetch_all` (dict-fetch) on both classes + live-DB tests [Wave 3]

**UI hint**: no

### Phase 35: Schema Introspection

**Goal**: Users can call enriched read-only introspection helpers on `db.schema.*` to retrieve primary keys, foreign keys, sequences, views, and a consolidated table description, with full sync/async parity
**Depends on**: Phase 34 (same milestone; can execute independently but follows naturally)
**Requirements**: INTRO-01, INTRO-02, INTRO-03, INTRO-04, INTRO-05, INTRO-06
**Success Criteria** (what must be TRUE):

  1. User can call `db.schema.primary_key(table, schema="public")` and receive the list of primary-key column name(s) for the table
  2. User can call `db.schema.foreign_keys(table, schema="public")` and receive a list of entries each naming the local column(s), referenced table, and referenced column(s)
  3. User can call `db.schema.sequences(schema="public")` and receive a list of sequences defined in that schema, and `db.schema.views(schema="public")` and receive a list of view names
  4. User can call `db.schema.describe(table, schema="public")` and receive a consolidated description containing columns+types, primary key, foreign keys, and indexes — the all-in-one introspection helper
  5. Every new introspection method is callable identically on `async_db.schema.*` (`AsyncSchemaAccessor`), and `test_accessor_parity` enumerates and verifies each pair

**Plans**: 2 plans

**Wave 1**

- [x] 35-01-introspection-helpers-PLAN.md — pg_catalog `primary_key`/`foreign_keys` + `information_schema` `sequences`/`views` on both accessors (4 SQL constants, 8 methods, mock+live tests) [Wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 35-02-describe-consolidation-PLAN.md — `describe()` composition helper (one flat dict over table_info/primary_key/foreign_keys/list_indexes) on both accessors + composition-equality/missing-table tests + optional v090 named-surface test [Wave 2]

**UI hint**: no

### Phase 36: Release v0.9.0

**Goal**: v0.9.0 is published to PyPI with all quality gates green, documentation updated, and a clean-venv smoke confirming the new surface is importable and functional
**Depends on**: Phase 34, Phase 35
**Requirements**: REL-09
**Success Criteria** (what must be TRUE):

  1. Version is bumped to 0.9.0 in the single canonical source (`pyproject.toml`); `__version__` is derived dynamically via `importlib.metadata.version("pycopg")` and updates automatically — do NOT hardcode it (see 36-CONTEXT D-36-01). CHANGELOG `[0.9.0]` Added-only entry covers all new CRUD and introspection methods
  2. All 4 quality gates pass: coverage ratchet ≥94%, interrogate ≥95, Sphinx `-W` clean, `-W error::DeprecationWarning` green
  3. Docs surfaces updated: README method counts reflect new helpers, `api-reference.md` rows added, `docs/*.md` pages cover the new methods with numpydoc-consistent shallow docstrings
  4. Tag `v0.9.0` pushed and PyPI wheel+sdist published via OIDC trusted publishing (human-gated at the irreversible publish step); clean-venv `pip install pycopg==0.9.0` smoke prints 0.9.0

**Plans**: TBD
**UI hint**: no

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Bug Fixes & Foundation | v0.3.0 | 2/2 | Complete | 2026-02-11 |
| 2. AsyncDatabase DataFrame Parity | v0.3.0 | 2/2 | Complete | 2026-02-11 |
| 3. AsyncDatabase Admin/Backup Parity | v0.3.0 | 2/2 | Complete | 2026-02-11 |
| 4. AsyncDatabase Extensions Parity | v0.3.0 | 2/2 | Complete | 2026-02-11 |
| 5. Resilience & Configuration | v0.3.0 | 2/2 | Complete | 2026-02-11 |
| 6. Test Coverage | v0.3.0 | 2/2 | Complete | 2026-02-11 |
| 7. Documentation & Release | v0.3.0 | 2/2 | Complete | 2026-02-11 |
| — Security Hotfix v0.3.1 | v0.3.1 | — | Shipped | 2026-06-06 |
| 9. Migration uv (outillage) | v0.4.0 | 4/4 | Complete | 2026-06-06 |
| 10. Sécurité résiduelle & robustesse | v0.4.0 | 5/5 | Complete | 2026-06-08 |
| 11. Parité sync/async complète | v0.4.0 | 7/7 | Complete | 2026-06-09 |
| 12. Refactoring (base.py + queries.py) | v0.4.0 | 4/4 | Complete | 2026-06-09 |
| 13. Qualité documentaire (numpydoc + interrogate) | v0.4.0 | 6/6 | Complete | 2026-06-10 |
| 14. Spatial helpers (db.spatial.*) | v0.4.0 | 4/4 | Complete | 2026-06-12 |
| 15. Release v0.4.0 (PyPI + RTD) | v0.4.0 | 6/6 | Complete | 2026-06-14 |
| 16. Pure ETL Layer | v0.5.0 | 2/2 | Complete | 2026-06-14 |
| 17. Run-Tracking Foundation | v0.5.0 | 2/2 | Complete | 2026-06-15 |
| 18. Load Modes & Extract | v0.5.0 | 3/3 | Complete | 2026-06-15 |
| 19. Sync Runner & Query Surface | v0.5.0 | 3/3 | Complete | 2026-06-15 |
| 20. Async Parity, Wiring & Release | v0.5.0 | 3/3 | Complete | 2026-06-15 |
| 21. Infrastructure & Timescale Accessor | v0.6.0 | 3/3 | Complete | 2026-06-17 |
| 22. Admin, Maint & Backup Accessors | v0.6.0 | 3/3 | Complete | 2026-06-17 |
| 23. Schema Accessor & Spatial Relocation | v0.6.0 | 4/4 | Complete | 2026-06-17 |
| 24. Exports, Docs & Release v0.6.0 | v0.6.0 | 3/3 | Complete | 2026-06-19 |
| 25. Alias Removal | v0.7.0 | 5/5 | Complete | 2026-06-19 |
| 26. Incremental ETL — Pure Layer | v0.7.0 | 1/1 | Complete | 2026-06-20 |
| 27. Incremental ETL — Run-Log Integration | v0.7.0 | 1/1 | Complete | 2026-06-20 |
| 28. Incremental ETL — Extract, RunResult & Async Parity | v0.7.0 | 3/3 | Complete | 2026-06-21 |
| 29. Release v0.7.0 | v0.7.0 | 3/3 | Complete | 2026-06-22 |
| 30. Chunk Management & Partitioning | v0.8.0 | 3/3 | Complete | 2026-06-22 |
| 31. Continuous Aggregate Lifecycle | v0.8.0 | 3/3 | Complete | 2026-06-23 |
| 32. Query Helpers & Parity Verification | v0.8.0 | 2/2 | Complete | 2026-06-23 |
| 33. Release v0.8.0 | v0.8.0 | 3/3 | Complete | 2026-06-23 |
| 34. CRUD Ergonomics | v0.9.0 | 3/3 | Complete    | 2026-06-24 |
| 35. Schema Introspection | v0.9.0 | 2/2 | Complete   | 2026-06-25 |
| 36. Release v0.9.0 | v0.9.0 | 0/TBD | Not started | - |
