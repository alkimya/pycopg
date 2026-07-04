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
- 🚧 **v1.1.0 Follow-ups additifs (TimescaleDB · ETL incrémental · CRUD/introspection)** — Phases 48-51 (in progress)

## Phases

**Phase Numbering:**

- Integer phases (48, 49, 50, 51): Planned milestone work
- Decimal phases (e.g. 48.1): Urgent insertions (marked with INSERTED)

### 🚧 v1.1.0 Follow-ups additifs (In Progress)

**Milestone Goal:** First additive **1.x** point release under the frozen SemVer 1.0 API — close 13 deferred family follow-ups across three already-shipped surfaces (`db.timescale.*`, `db.etl.*`/`Pipeline`, flat core + `db.schema.*`) and fold in the pending doc/metadata patch. Non-breaking, full sync/async parity (Core Value), zero new runtime dependencies, coverage ratchet ≥95% (baseline 96.45%), `mypy --strict` stays a blocking gate at 0 errors.

- [x] **Phase 48: TimescaleDB Follow-ups** - Complete the `db.timescale.*` cagg lifecycle, custom bucket alignment, per-chunk compression, and physical-time chunk filters (completed 2026-07-03)
- [x] **Phase 49: Incremental ETL Follow-ups** - Bound the first incremental run, configurable boundary semantics, composite watermarks, and advisory-lock concurrency safety on `Pipeline` (completed 2026-07-03)
- [x] **Phase 50: CRUD + Introspection Follow-ups** - Raw-SQL escape hatch, keyset pagination with a page envelope, and richer `db.schema.*` introspection (`describe` as dataclass/DataFrame, materialized views) (completed 2026-07-04)
- [ ] **Phase 51: Release v1.1.0** - Doc/metadata patch (classifier, api-reference, CLAUDE.md), version bump, CHANGELOG, 5 gates green, tag + PyPI publish

## Phase Details

### Phase 48: TimescaleDB Follow-ups

**Goal**: Users can fully manage a continuous aggregate's lifecycle, align time buckets to a custom origin, control compression at the individual-chunk level, and filter `show_chunks` by physical time — completing the `db.timescale.*` surface opened in v0.8.0.
**Depends on**: Nothing (first phase of v1.1.0; builds on shipped v0.8.0 `db.timescale.*`)
**Requirements**: TSDB-F01, TSDB-F02, TSDB-F03, TSDB-F04
**Success Criteria** (what must be TRUE):

  1. User can drop a continuous aggregate and separately remove its refresh policy via `db.timescale.drop_continuous_aggregate(name)` / `remove_continuous_aggregate_policy(name)`, sync and async
  2. User can align `time_bucket` output to a custom origin/offset via keyword-only `origin=`/`offset=` params, sync and async
  3. User can compress or decompress a single named chunk via `db.timescale.compress_chunk(chunk)` / `decompress_chunk(chunk)`, sync and async
  4. User can filter `show_chunks` results to a physical time window via keyword-only `newer_than=`/`older_than=` bounds, sync and async**Plans**: 3 plans

**Wave 1**

- [x] 48-01-PLAN.md — F01 continuous-aggregate teardown (drop_continuous_aggregate + remove_continuous_aggregate_policy, both accessors)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 48-02-PLAN.md — F02 time_bucket custom origin/offset (keyword-only params + @overload KIND-parity, both accessors)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 48-03-PLAN.md — F03 per-chunk compress/decompress + F04 show_chunks physical-time filter verify+doc

### Phase 49: Incremental ETL Follow-ups

**Goal**: Users can precisely control the boundaries and concurrency safety of incremental `Pipeline` runs — bounding the first run, choosing inclusive/lookback semantics, tracking composite watermarks, and preventing overlapping runs of the same pipeline.
**Depends on**: Nothing (independent surface from Phase 48; builds on shipped v0.7.0 `Pipeline.incremental_column`)
**Requirements**: ETL-INC-F01, ETL-INC-F02, ETL-INC-F03, ETL-INC-F04
**Success Criteria** (what must be TRUE):

  1. User can set `Pipeline.initial_watermark` so the first incremental run is bounded/seeded instead of doing a full initial load
  2. User can configure the incremental boundary as inclusive `>=` and/or apply a lookback overlap, instead of only the fixed exclusive `>`
  3. User can define a `Pipeline` with a composite (multi-column) incremental watermark key
  4. User can run the same pipeline concurrently from two processes and have the second run safely serialize (or refuse to overlap) via a PostgreSQL advisory lock, sync and async

**Plans**: 5 plans

**Wave 1**

- [x] 49-01-PLAN.md — F01 initial_watermark seed floor (Pipeline field + construction guard + seed-floor fallback wired at all 4 run() call sites, both accessors)

**Wave 2** *(blocked on Wave 1)*

- [x] 49-02-PLAN.md — F02 boundary knobs (incremental_inclusive >= + incremental_lookback Python-subtract floor; builder inclusive op; recorded wm stays true max; str+lookback ETLError)

**Wave 3** *(blocked on Wave 2)*

- [x] 49-03-PLAN.md — F03 composite watermark, pure layer (widen incremental_column str|Sequence[str], tuple-compare builder, "composite" envelope tag, D-04 composite initial_watermark guard)

**Wave 4** *(blocked on Wave 3)*

- [x] 49-04-PLAN.md — F03 composite run() wiring (sorted max-ROW capture + per-element NaN guard, _do_extract multi-placeholder named binds, live-DB correctness, both accessors)

**Wave 5** *(blocked on Wave 4)*

- [x] 49-05-PLAN.md — F04 advisory-lock concurrency (ETL_ADVISORY_* constants, concurrency field, session-scoped lock acquire/finally-release, 'skip'->'skipped' transient RunResult, live two-connection integration)

### Phase 50: CRUD + Introspection Follow-ups

**Goal**: Users get richer, more production-ready query ergonomics on the flat transactional core and deeper structural visibility via `db.schema.*` — an escape hatch for conditions the dict-WHERE form can't express, stable deep pagination, and materialized-view introspection.
**Depends on**: Nothing (independent surface from Phases 48-49; builds on shipped v0.9.0 CRUD helpers + `db.schema.*`)
**Requirements**: CRUD-F01, CRUD-F02, CRUD-F03, INTRO-F01, INTRO-F02
**Success Criteria** (what must be TRUE):

  1. User can pass a raw-SQL WHERE fragment with bound params as an escape hatch to `delete_where`/`update_where`/`count`/`exists`/`paginate` for conditions the dict form can't express, sync and async
  2. User can paginate by keyset/cursor (seek method) for stable, index-friendly deep pagination, sync and async
  3. User can retrieve a page envelope carrying `total` count and `has_next` alongside the rows
  4. User can get `db.schema.describe()` output as a structured dataclass and/or DataFrame, not only a plain dict
  5. User can introspect materialized views and their columns via `db.schema.materialized_views()` plus per-view column introspection, sync and async

**Plans**: 4 plans

**Wave 1**

- [x] 50-01-PLAN.md — CRUD-F01 raw-SQL WHERE escape hatch (`where_sql`/`where_params` on delete_where/update_where/exists/count/paginate, both classes; `_resolve_predicate` guard)

**Wave 2** *(blocked on Wave 1)*

- [x] 50-02-PLAN.md — CRUD-F02 + CRUD-F03 pagination family (`Page` envelope + `paginate_page` offset→Page + `paginate_keyset` seek→Page, both classes; `_build_keyset_where`)

**Wave 3** *(blocked on Wave 2 — shared test-suite files)*

- [x] 50-03-PLAN.md — INTRO-F02 materialized-view introspection (`materialized_views` + `materialized_view_columns`, both accessors; dedicated pg_catalog queries)

**Wave 4** *(blocked on Wave 3 — shared schema.py + spine files)*

- [x] 50-04-PLAN.md — INTRO-F01 structured describe (`describe(into="dict"|"dataclass"|"dataframe")` + `TableDescription`, both accessors; @overload set)

### Phase 51: Release v1.1.0

**Goal**: pycopg v1.1.0 is published to PyPI with correct, stable-1.x package metadata and documentation, all quality gates green.
**Depends on**: Phase 48, Phase 49, Phase 50 (release packages all prior phases' work; DOC-13's api-reference `*Error` fix must land before the `-W error::DeprecationWarning` release gate runs)
**Requirements**: DOC-13, REL-12
**Success Criteria** (what must be TRUE):

  1. `pyproject.toml` classifier reads `Development Status :: 5 - Production/Stable` and `docs/api-reference.md` uses only the `*Error` exception names (no deprecated-name imports), and `CLAUDE.md` Version line reflects v1.1.0
  2. `pip install pycopg==1.1.0` installs the new surface from PyPI with `__version__ == "1.1.0"` confirmed via clean-venv smoke
  3. CHANGELOG `[1.1.0]` is code-exact against Phases 48-50 — `Added` entries plus exactly one `Fixed` entry for the WR-01 `time_bucket` origin/offset guard-order fix folded into this phase (D-05)
  4. All 5 release gates are green: coverage ≥95%, interrogate 100%, Sphinx `-W`, `-W error::DeprecationWarning`, `mypy --strict` 0 errors

**Plans**: 3 plans

**Wave 1**

- [x] 51-01-PLAN.md — DOC-13 corrections (D-02 classifier, D-03 api-reference *Error names, D-04 CLAUDE.md version) + WR-01 guard hoist (D-05, sync+async + regression test)

**Wave 2** *(blocked on Wave 1 — D-03 must land before the DeprecationWarning gate)*

- [x] 51-02-PLAN.md — version bump (D-01, pyproject/conf.py/uv.lock) + code-exact CHANGELOG [1.1.0] (D-06) + run all 5 release gates (D-08)

**Wave 3** *(blocked on Wave 2 — green gates precede tag)*

- [x] 51-03-PLAN.md — annotated tag v1.1.0 + human-gated GitHub Release → OIDC publish (D-07) + clean-venv smoke

## Progress

**Execution Order:**
Phases execute in numeric order: 48 → 49 → 50 → 51

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 48. TimescaleDB Follow-ups | v1.1.0 | 3/3 | Complete    | 2026-07-03 |
| 49. Incremental ETL Follow-ups | v1.1.0 | 5/5 | Complete   | 2026-07-03 |
| 50. CRUD + Introspection Follow-ups | v1.1.0 | 4/4 | Complete    | 2026-07-03 |
| 51. Release v1.1.0 | v1.1.0 | 3/3 | Complete   | 2026-07-04 |

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
| 48. TimescaleDB Follow-ups | v1.1.0 | 0/3 | Planned | - |
| 49. Incremental ETL Follow-ups | v1.1.0 | 0/5 | Planned | - |
| 50. CRUD + Introspection Follow-ups | v1.1.0 | 0/4 | Planned | - |
| 51. Release v1.1.0 | v1.1.0 | 0/3 | Planned | - |
