# Roadmap: pycopg

## Milestones

- ✅ **v0.3.0 Consolidation Release** — Phases 1-7 (shipped 2026-02-11)
- ✅ **v0.3.1 Security Hotfix** — injections SQL corrigées (shipped PyPI 2026-06-06)
- ✅ **v0.4.0 Quality & Spatial Helpers** — Phases 9-15 (shipped 2026-06-14)
- ✅ **v0.5.0 ETL Pipeline Runner** — Phases 16-20 (shipped 2026-06-15)
- ✅ **v0.6.0 Réorganisation en accessors** — Phases 21-24 (shipped 2026-06-19)
- ✅ **v0.7.0 Alias Removal + Incremental ETL** — Phases 25-29 (shipped 2026-06-22)
- ✅ **v0.8.0 TimescaleDB avancé** — Phases 30-33 (shipped 2026-06-23)
- ✅ **v0.9.0 CRUD ergonomique + introspection enrichie** — Phases 34-36 (shipped 2026-06-25)
- ✅ **v0.10.0 Durcissement & Performance** — Phases 37-40 (shipped 2026-06-26)
- ✅ **v1.0.0 Spatial v2 + gel API** — Phases 41-47 (shipped 2026-07-02)
- ✅ **v1.1.0 Follow-ups additifs (TimescaleDB · ETL incrémental · CRUD/introspection)** — Phases 48-51 (shipped 2026-07-04)
- 🚧 **v1.2.0 Polish & finitions additives** — Phases 52-54 (in progress)

## Phases

**Phase Numbering:**

- Integer phases (52, 53, 54): Planned milestone work
- Decimal phases (e.g. 52.1): Urgent insertions (marked with INSERTED)

### 🚧 v1.2.0 Polish & finitions additives (In Progress)

**Milestone Goal:** Second additive point release under the frozen SemVer 1.0 API — a maturity cycle (no new subsystem): close the small API ergonomics/symmetry gaps, finish the spatial tail, and settle the docs/tooling debt. Non-breaking, full sync/async parity (Core Value), zero new runtime dependencies, coverage ratchet ≥95% (baseline 96.65%), `mypy --strict` stays a blocking gate.

- [ ] **Phase 52: Spatial Finish** - Complete `db.spatial.*` with fixed-precision overlay control, remaining measurement/validity helpers, and the last four DE-9IM predicates
- [ ] **Phase 53: CRUD Symmetry + Introspection Follow-ups** - Add the missing predicate-read and single-row-insert helpers to the flat core, and the last two `db.schema.*` introspection helpers
- [ ] **Phase 54: Release v1.2.0** - Doc/tooling hygiene (deprecated-name residue, `vulture` wired into Makefile/CI), version bump, CHANGELOG, 5 gates green, tag + PyPI publish

## Phase Details

### Phase 52: Spatial Finish

**Goal**: `db.spatial.*` gains fixed-precision overlay control and completes its measurement/validity/predicate helper families, with the existing overlay default path staying byte-identical.
**Depends on**: Nothing (first phase of v1.2.0; builds on shipped `db.spatial.*` from v1.0.0/v1.1.0)
**Requirements**: SPAT-F01, SPAT-F02, SPAT-F03, SPAT-F04, SPAT-F05, SPAT-F06
**Success Criteria** (what must be TRUE):

  1. User can pass a keyword-only `gridSize=` to `union`/`difference`/`intersection` for fixed-precision overlay output, while the default `None` path produces SQL byte-identical to the shipped overlay builders
  2. User can compute the length of linear geometries via `db.spatial.length`, alongside the existing `area`/`perimeter` measurement helpers
  3. User can get the per-row bounding-box geometry via `db.spatial.envelope` and a guaranteed-inside representative point via `db.spatial.point_on_surface` (complementing `centroid`)
  4. User can check geometry validity and get the invalidity reason via `db.spatial.is_valid`/`is_valid_reason`, complementing the existing `make_valid`
  5. User can test the `overlaps`/`touches`/`crosses`/`disjoint` DE-9IM predicates via `db.spatial.*`, completing the `contains`/`intersects`/`within`/`dwithin` predicate family

**Plans**: 6 plans

Plans:
- [ ] 52-01-PLAN.md — SPAT-F01 keyword-only `gridSize=` fixed-precision overlay (byte-identical `None` default)
- [ ] 52-02-PLAN.md — SPAT-F02 `length` + SPAT-F05 `is_valid`/`is_valid_reason` (scalar helpers, `_SCALAR_HELPERS`)
- [ ] 52-03-PLAN.md — SPAT-F03 `envelope` + SPAT-F04 `point_on_surface` (geometry helpers, `@overload` triplets)
- [ ] 52-04-PLAN.md — SPAT-F06 `overlaps` + `touches` DE-9IM predicates (into=rows/gdf)
- [ ] 52-05-PLAN.md — SPAT-F06 `crosses` + `disjoint` DE-9IM predicates (disjoint footgun + perf note)
- [ ] 52-06-PLAN.md — Docs (`spatial.md` + `api-reference.md`) + surface test + 5-gate phase closure

### Phase 53: CRUD Symmetry + Introspection Follow-ups

**Goal**: The flat transactional core gains its missing predicate-read and single-row-insert siblings, and `db.schema.*` completes its existence-check and size-introspection families.
**Depends on**: Nothing (independent surface from Phase 52; builds on shipped CRUD helpers from v0.9.0/v1.1.0 + `db.schema.*`)
**Requirements**: CRUD-F04, CRUD-F05, CRUD-F06, INTRO-F03, INTRO-F04
**Success Criteria** (what must be TRUE):

  1. User can read rows by predicate via `select_where`/`find` returning `list[dict]` — accepting both a dict-equality WHERE and a raw-SQL `where_sql`/`where_params` escape hatch through the shared `QueryMixin._resolve_predicate` guard
  2. User can read a single matching row via `get`/`find_one` returning `dict | None`, on the same predicate surface as `select_where`/`find`
  3. User can insert a single row via `insert` with `RETURNING *`, the singular twin of `insert_many`/`upsert`
  4. User can check a column's existence via `db.schema.column_exists`, completing the `table_exists`/`schema_exists`/`database_exists` family
  5. User can get a table's on-disk size via `db.schema.table_size` (`pg_total_relation_size`), complementing `row_count`

**Plans**: TBD

### Phase 54: Release v1.2.0

**Goal**: Documentation prose is current, dead-code scanning is enforced automatically, and pycopg 1.2.0 is published to PyPI.
**Depends on**: Phase 52, Phase 53 (release packages all prior phases' work)
**Requirements**: DOC-14, TOOL-01, REL-13
**Success Criteria** (what must be TRUE):

  1. `docs/spatial.md` and `docs/api-reference.md` reference only current `*Error` exception names (the intentional deprecated-alias mentions in `docs/stability.md` are left as-is)
  2. Developer can run `make deadcode` locally and CI runs the same `vulture` dead-code scan on every push, using the existing `vulture_whitelist.py`
  3. `pip install pycopg==1.2.0` installs the new surface from PyPI with `__version__ == "1.2.0"` confirmed via clean-venv smoke, all 5 release gates green (coverage ≥95%, interrogate 100%, Sphinx `-W`, `-W error::DeprecationWarning`, `mypy --strict` 0/18), and a code-exact `[1.2.0]` CHANGELOG entry

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 52 → 53 → 54

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 52. Spatial Finish | v1.2.0 | 0/6 | Planned | - |
| 53. CRUD Symmetry + Introspection Follow-ups | v1.2.0 | TBD | Not started | - |
| 54. Release v1.2.0 | v1.2.0 | TBD | Not started | - |

<details>
<summary>✅ v1.1.0 Follow-ups additifs (Phases 48-51) — SHIPPED 2026-07-04</summary>

- [x] Phase 48: TimescaleDB Follow-ups (3/3 plans) — cagg teardown (`drop_continuous_aggregate`/`remove_continuous_aggregate_policy`), `time_bucket` origin/offset alignment, per-chunk `compress_chunk`/`decompress_chunk`, `show_chunks` physical-time filter — completed 2026-07-03
- [x] Phase 49: Incremental ETL Follow-ups (5/5 plans) — `Pipeline.initial_watermark` seed, `incremental_inclusive`/`incremental_lookback` boundary config, composite multi-column watermarks (row-value compare + `"composite"` envelope), advisory-lock `concurrency="wait"|"skip"` — completed 2026-07-03
- [x] Phase 50: CRUD + Introspection Follow-ups (4/4 plans) — raw-SQL `where_sql`/`where_params` escape hatch on 5 helpers, `Page` envelope + `paginate_page`/`paginate_keyset` seek pagination, `materialized_views`/`materialized_view_columns`, `describe(into=dict|dataclass|dataframe)` + `TableDescription` — completed 2026-07-04
- [x] Phase 51: Release v1.1.0 (3/3 plans) — classifier 5-Production/Stable + api-reference `*Error` + CLAUDE.md version, code-exact CHANGELOG `[1.1.0]` (Added + one Fixed WR-01), 5 gates green, tag `v1.1.0` + human-gated OIDC PyPI publish + clean-venv smoke — completed 2026-07-04

Full details: [milestones/v1.1.0-ROADMAP.md](milestones/v1.1.0-ROADMAP.md) · Requirements: [milestones/v1.1.0-REQUIREMENTS.md](milestones/v1.1.0-REQUIREMENTS.md) · Audit: [milestones/v1.1.0-MILESTONE-AUDIT.md](milestones/v1.1.0-MILESTONE-AUDIT.md)

</details>

<details>
<summary>✅ v1.0.0 Spatial v2 + gel API (Phases 41-47) — SHIPPED 2026-07-02</summary>

- [x] Phase 41: API Homogenization (5/5 plans) — spatial `where=`→`filter=` + deprecation shim on 22 methods, 4 N818 exception renames (`*Error`) with PEP 562 aliases, kw-only `*` freeze across 7 accessors + flat core, `docs/stability.md` + MIGRATION v0.10.x→1.0.0 — completed 2026-06-28
- [x] Phase 42: Spatial v2 — Processing Helpers (3/3 plans) — `union`/`difference`/`intersection` + `simplify`/`convex_hull`/`make_valid` on both accessors, `validate_identifiers`-first + injection tests — completed 2026-06-29
- [x] Phase 43: Spatial v2 — Spatial Aggregates (3/3 plans) — `collect_geometries`/`union_aggregate`/`extent` GROUP-BY aggregates, dual `into=` extent branch (box2d/geometry), NULL-propagation documented — completed 2026-06-29
- [x] Phase 44: Spatial v2 — Serialization + MVT (3/3 plans) — `as_geojson`/`as_text` + `as_mvt`→`bytes` (enforced ST_Transform→ST_AsMVTGeom→ST_AsMVT); `db.spatial.*` 13→25; SPAT2-13 parity finalized — completed 2026-06-30
- [x] Phase 45: API Completeness Gaps + Structured Logging (4/4 plans) — transaction `isolation_level=`/`savepoint()`, named dict `Params`, never-raises `health()` ×4 classes, `pycopg/logging.py` — completed 2026-06-30
- [x] Phase 46: mypy Strict + py.typed Gate (7/7 plans) — package 356→0 strict errors, ~108 `@overload` stubs, truthful `py.typed`, CI mypy flipped blocking; fixed 2 latent bugs (`AsyncPooledDatabase.resize()` await) — completed 2026-07-02
- [x] Phase 47: Release v1.0.0 (3/3 plans) — version bump (3 sources), CHANGELOG `[1.0.0]` Breaking+Added, 5 gates green, tag `v1.0.0` + human-gated OIDC PyPI publish + clean-venv smoke — completed 2026-07-02

Full details: [milestones/v1.0.0-ROADMAP.md](milestones/v1.0.0-ROADMAP.md) · Requirements: [milestones/v1.0.0-REQUIREMENTS.md](milestones/v1.0.0-REQUIREMENTS.md) · Audit: [milestones/v1.0.0-MILESTONE-AUDIT.md](milestones/v1.0.0-MILESTONE-AUDIT.md)

</details>

<details>
<summary>✅ v0.10.0 Durcissement & Performance (Phases 37-40) — SHIPPED 2026-06-26</summary>

- [x] Phase 37: Dette & Audit (5/5 plans) — flaky-test fixture isolation, ruff `[tool.ruff.lint]` + 0 errors, `TableNotFound` raise site in `truncate_table`, vulture dead-code scan + allowlist, AUDIT-01 review (5 BLOCKERS fixed in-phase), Nyquist sign-off 22-24 — completed 2026-06-26
- [x] Phase 38: Performance COPY (3/3 plans) — `from_dataframe` (sync+async) Hybrid DDL+COPY via `_stream_df_copy`/`_async_stream_df_copy`, ETL load seam via COPY, `insert_batch` placeholder hoist, sync/async parity (CR-01/CR-02 `validate_identifiers` BLOCKER fixed in-phase) — completed 2026-06-26
- [x] Phase 39: Couverture & Benchmarks (2/2 plans) — coverage ratchet 94→95% (measured 96.32%, 6 justified pragmas), stdlib `benchmarks/` 4-path runner + `make bench` + regression protocol — completed 2026-06-26
- [x] Phase 40: Release v0.10.0 (2/2 plans) — version bump (3 sources), Keep-a-Changelog `[0.10.0]` (Changed+Fixed), 4 gates green, tag `v0.10.0` + human-gated OIDC PyPI publish + clean-venv smoke — completed 2026-06-26

Full details: [milestones/v0.10.0-ROADMAP.md](milestones/v0.10.0-ROADMAP.md) · Requirements: [milestones/v0.10.0-REQUIREMENTS.md](milestones/v0.10.0-REQUIREMENTS.md) · Audit: [milestones/v0.10.0-MILESTONE-AUDIT.md](milestones/v0.10.0-MILESTONE-AUDIT.md)

</details>

<details>
<summary>✅ v0.9.0 CRUD ergonomique + introspection enrichie (Phases 34-36) — SHIPPED 2026-06-25</summary>

- [x] Phase 34: CRUD Ergonomics (3/3 plans) — `upsert` (RETURNING *), `delete_where`, `update_where`, `exists`, `count`, `paginate`, `fetch_all` (dict-fetch) on both classes via shared `_build_where_dict` builder — completed 2026-06-24
- [x] Phase 35: Schema Introspection (2/2 plans) — `db.schema.primary_key`/`foreign_keys`/`sequences`/`views` (pg_catalog/information_schema) + `describe` composition helper on both accessors — completed 2026-06-25
- [x] Phase 36: Release v0.9.0 (2/2 plans) — version bump, CHANGELOG [0.9.0] Added-only (12 methods), docs surfaces, 4 gates green, human-gated OIDC PyPI publish + tag + clean-venv smoke — completed 2026-06-25

Full details: [milestones/v0.9.0-ROADMAP.md](milestones/v0.9.0-ROADMAP.md) · Requirements: [milestones/v0.9.0-REQUIREMENTS.md](milestones/v0.9.0-REQUIREMENTS.md) · Audit: [milestones/v0.9.0-MILESTONE-AUDIT.md](milestones/v0.9.0-MILESTONE-AUDIT.md)

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

## Full Progress Table (All Milestones)

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
| 34. CRUD Ergonomics | v0.9.0 | 3/3 | Complete | 2026-06-24 |
| 35. Schema Introspection | v0.9.0 | 2/2 | Complete | 2026-06-25 |
| 36. Release v0.9.0 | v0.9.0 | 2/2 | Complete | 2026-06-25 |
| 37. Dette & Audit | v0.10.0 | 5/5 | Complete | 2026-06-26 |
| 38. Performance COPY | v0.10.0 | 3/3 | Complete | 2026-06-26 |
| 39. Couverture & Benchmarks | v0.10.0 | 2/2 | Complete | 2026-06-26 |
| 40. Release v0.10.0 | v0.10.0 | 2/2 | Complete | 2026-06-26 |
| 41. API Homogenization | v1.0.0 | 5/5 | Complete    | 2026-06-28 |
| 42. Spatial v2 — Processing Helpers | v1.0.0 | 3/3 | Complete    | 2026-06-29 |
| 43. Spatial v2 — Spatial Aggregates | v1.0.0 | 3/3 | Complete    | 2026-06-29 |
| 44. Spatial v2 — Serialization + MVT | v1.0.0 | 3/3 | Complete    | 2026-06-30 |
| 45. API Completeness Gaps + Structured Logging | v1.0.0 | 4/4 | Complete    | 2026-06-30 |
| 46. mypy Strict + py.typed Gate | v1.0.0 | 7/7 | Complete    | 2026-07-02 |
| 47. Release v1.0.0 | v1.0.0 | 3/3 | Complete    | 2026-07-02 |
| 48. TimescaleDB Follow-ups | v1.1.0 | 3/3 | Complete | 2026-07-03 |
| 49. Incremental ETL Follow-ups | v1.1.0 | 5/5 | Complete | 2026-07-03 |
| 50. CRUD + Introspection Follow-ups | v1.1.0 | 4/4 | Complete | 2026-07-04 |
| 51. Release v1.1.0 | v1.1.0 | 3/3 | Complete | 2026-07-04 |
| 52. Spatial Finish | v1.2.0 | 0/6 | Planned | - |
| 53. CRUD Symmetry + Introspection Follow-ups | v1.2.0 | TBD | Not started | - |
| 54. Release v1.2.0 | v1.2.0 | TBD | Not started | - |
