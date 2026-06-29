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
- 🔄 **v1.0.0 Spatial v2 + gel API** — Phases 41-47 (in progress)

## Phases

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

### ▶ v1.0.0 Spatial v2 + gel API (Phases 41-47) — in progress

- [x] **Phase 41: API Homogenization** — `where=`→`filter=` rename on all 11 existing spatial methods + DeprecationWarning aliases; 4 N818 exception renames with deprecated aliases; public API consistency pass + Stable API Contract; SemVer + deprecation policy doc (`docs/stability.md`); MIGRATION guide sections for all renamed names (completed 2026-06-28)
- [x] **Phase 42: Spatial v2 — Processing Helpers** — `union`, `simplify`, `convex_hull`, `make_valid`, `difference`, `intersection` on `SpatialAccessor` + `AsyncSpatialAccessor`; all builders use `filter=`; `validate_identifiers` first + injection tests; sync/async parity enforced by `test_accessor_parity` (completed 2026-06-29)
- [x] **Phase 43: Spatial v2 — Spatial Aggregates** — `collect_geometries`, `union_aggregate`, `extent` (GROUP BY aggregate builder shape); NULL-propagation documented and tested; `into="gdf"` box2d→geometry for `extent`; parity + injection tests (completed 2026-06-29)
- [ ] **Phase 44: Spatial v2 — Serialization + MVT** — `as_geojson`, `as_text` in `_SCALAR_HELPERS`; `as_mvt` returning `bytes` (ST_Transform→ST_AsMVTGeom→ST_AsMVT pipeline enforced); full sync/async parity + injection tests; SPAT2-13 parity acceptance finalized across spatial phases
- [ ] **Phase 45: API Completeness Gaps + Structured Logging** — `db.transaction(isolation_level=, savepoint_name=)` + `db.session(isolation_level=)` + `db.savepoint()` context manager; `%(name)s` named params documented and type-annotated; `db.health()` (latency + server_version + pool_stats); `pycopg/logging.py` + `log_operation` context manager
- [ ] **Phase 46: mypy Strict + py.typed Gate** — `strict=true` blocking in CI; 3 dev-group stubs (pandas-stubs, types-geopandas, types-shapely); `@overload` on all `into=` methods; measure error count first, fix bottom-up; zero strict errors over `pycopg/`; coverage ratchet held ≥95%
- [ ] **Phase 47: Release v1.0.0** — version bump (all sources), CHANGELOG `[1.0.0]` Breaking + Added, MIGRATION guide complete, all 5 gates green (coverage ≥95%, interrogate 100%, Sphinx `-W`, `-W error::DeprecationWarning`, `mypy --strict` exit 0), tag `v1.0.0` + human-gated OIDC PyPI publish + clean-venv smoke

## Phase Details

### Phase 41: API Homogenization

**Goal**: The public surface is consistent and homogeneous — `where=` means dict-equality everywhere, `filter=` means raw SQL fragment in spatial, exception names follow N818, and the SemVer stability contract is published

**Depends on**: Phase 40 (v0.10.0 baseline)

**Requirements**: FREEZE-01, FREEZE-02, FREEZE-03, FREEZE-04

**Success Criteria** (what must be TRUE):

1. Calling an existing spatial method with `where=` raises `DeprecationWarning` pointing to the caller's file (not `pycopg/`), and the result is identical to calling with `filter=`
2. The old exception names (`ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier`, `DatabaseExists`) raise `DeprecationWarning` when imported or caught; new `*Error` names are importable and functional at every former raise site
3. `docs/stability.md` exists, is linked from README, and documents the SemVer contract, deprecation timeline, and supported versions
4. Every public method on every accessor and the flat core has a documented positional-vs-keyword-only parameter contract (Stable API Contract)
5. MIGRATION guide has a complete section listing every renamed name (spatial `where=`→`filter=`, 4 exception renames) with before/after examples

**Plans**: 5 plans in 5 waves
Plans:
**Wave 1**

- [x] 41-01-PLAN.md — Wave-0 `-W error::DeprecationWarning` gate (post third-party discovery) + `tests/test_deprecations.py` scaffold

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 41-02-PLAN.md — FREEZE-02: 4 `*Error` renames + PEP 562 `__getattr__` aliases (atomic w/ `__init__.py`) + all internal raise sites + N818 suppression removed

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 41-03-PLAN.md — FREEZE-01: spatial `where=`→`filter=` clean builder rename + per-accessor shim (22 methods, sync/async parity, stacklevel D-09)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 41-04-PLAN.md — FREEZE-03: consistency audit table + USER REVIEW GATE (D-05) + kw-only `*` enforcement across 7 accessors + flat core

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 41-05-PLAN.md — FREEZE-04: `docs/stability.md` (SemVer + support matrix + Stable API Contract) + toctree/README links + MIGRATION `v0.10.x → 1.0.0` section

---

### Phase 42: Spatial v2 — Processing Helpers

**Goal**: Users can perform the 6 core pairwise and unary geometry processing operations on PostGIS tables without writing raw SQL

**Depends on**: Phase 41 (homogenization — `filter=` available from day one)

**Requirements**: SPAT2-01, SPAT2-02, SPAT2-03, SPAT2-04, SPAT2-05, SPAT2-06

**Success Criteria** (what must be TRUE):

1. User can call `db.spatial.union(table, geom, other_geom)`, `db.spatial.difference(...)`, and `db.spatial.intersection(...)` to get pairwise geometry results without raw SQL; both sync and async variants return identical shape
2. User can call `db.spatial.simplify(table, geom, tolerance)` (ST_SimplifyPreserveTopology default — no NULL collapse) and `db.spatial.convex_hull(table, geom)` to get derived geometry columns
3. User can repair invalid geometries via `db.spatial.make_valid(table, geom, method=None)` with a whitelist-enforced `method` parameter; `method="structure"` is documented as requiring PostGIS ≥ 3.2
4. Passing a malicious identifier (e.g., `table="users; DROP TABLE users"`) to any new builder raises `InvalidIdentifierError` before any SQL is sent to the server (dedicated injection test per builder)
5. Every new method has a working `AsyncSpatialAccessor` equivalent with identical signature, confirmed by `test_accessor_parity`

**Plans**: 3 plans in 3 waves

Plans:

**Wave 1**

- [x] 42-01-PLAN.md — Binary trio: `union`/`difference`/`intersection` (shared `_build_binary_geom_sql` + 3 builders + 6 accessor methods + SQL-shape/injection/mixed-SRID/live tests) — SPAT2-01/05/06

**Wave 2** *(blocked on Wave 1; shared spatial.py/test_spatial.py)*

- [x] 42-02-PLAN.md — Unary trio: `simplify`/`convex_hull`/`make_valid` (3 builders w/ method whitelist + ValueError guards + `%s` params string + 6 accessor methods + SQL-shape/ValueError/injection/bowtie/tiny-polygon/structure live tests) — SPAT2-02/03/04

**Wave 3** *(blocked on Wave 2; docs + surface gate)*

- [x] 42-03-PLAN.md — `test_spatial_v1_processing_surface` parity-surface test + docs (stability.md 6 rows + structure>=3.2 note, api-reference.md filter= rows, README count) + full-suite/coverage gate — SPAT2-01..06

**UI hint**: no

---

### Phase 43: Spatial v2 — Spatial Aggregates

**Goal**: Users can aggregate geometry columns by group using PostGIS aggregate functions without writing raw SQL

**Depends on**: Phase 42 (processing builder pattern established)

**Requirements**: SPAT2-07, SPAT2-08, SPAT2-09

**Success Criteria** (what must be TRUE):

1. User can call `db.spatial.collect_geometries(table, geom, group_by=None)` and `db.spatial.union_aggregate(table, geom, group_by=None)` to get geometry collections and dissolved boundaries; optional `group_by` returns one row per group
2. User can call `db.spatial.extent(table, geom, group_by=None)` to get the bounding box; `into="rows"` returns box2d text, `into="gdf"` returns geometry; behavior with optional `group_by` is consistent
3. NULL geometry rows propagate predictably (documented NULL-propagation behavior; fixture with intentional NULL geometry rows is tested)
4. Passing a malicious identifier to any aggregate builder raises `InvalidIdentifierError` before any SQL is sent (dedicated injection test per builder)
5. Every new aggregate method has a working `AsyncSpatialAccessor` equivalent confirmed by `test_accessor_parity`

**Plans**: 3 plans in 3 waves

Plans:

**Wave 1**

- [x] 43-01-PLAN.md — `_append_tail` GROUP-BY extension + shared `_build_agg_geom_sql` + `collect_geometries`/`union_aggregate` (2 builders + 4 accessor methods, sync+async) + SQL-shape/injection/routing tests in `TestAggregateBuilders` — SPAT2-07/08

**Wave 2** *(blocked on Wave 1; shared spatial.py/test_spatial.py)*

- [x] 43-02-PLAN.md — `extent` dual-branch builder (box2d `::text` for rows, `ST_SetSRID(...::geometry, int(srid))` for gdf, D-04) + `srid=4326` kw-only + sync+async `extent` + branch/srid/group_by/injection tests — SPAT2-09

**Wave 3** *(blocked on Waves 1-2; live integration + docs + surface gate)*

- [x] 43-03-PLAN.md — live PostGIS integration (whole-table + grouped + intentional-NULL D-07 fixture, extent box2d/gdf) + `test_spatial_aggregates_surface` + docs (stability.md 3 rows + extent srid note, api-reference.md filter= rows, README 19→22) + full-suite/coverage gate — SPAT2-07/08/09

**UI hint**: no

---

### Phase 44: Spatial v2 — Serialization + MVT

**Goal**: Users can serialize PostGIS geometry columns to GeoJSON, WKT, and Mapbox Vector Tile formats directly from `db.spatial.*`

**Depends on**: Phase 43 (spatial builder surface established; SPAT2-13 parity acceptance finalizes here)

**Requirements**: SPAT2-10, SPAT2-11, SPAT2-12, SPAT2-13

**Success Criteria** (what must be TRUE):

1. User can call `db.spatial.as_geojson(table, geom, max_decimal_digits=6)` and `db.spatial.as_text(table, geom)` to get text-column results without raw SQL; both are in `_SCALAR_HELPERS`
2. User can call `db.spatial.as_mvt(table, geom, tile_z, tile_x, tile_y)` and receive `bytes`; the generated SQL always contains the ST_Transform→ST_AsMVTGeom→ST_AsMVT pipeline (no raw-geometry shortcut); the returned bytes decode to a valid MVT with the expected feature count
3. Passing a malicious identifier to `as_geojson`, `as_text`, or `as_mvt` raises `InvalidIdentifierError` before any SQL is sent (dedicated injection test per builder)
4. Every serialization method has a working `AsyncSpatialAccessor` equivalent with identical signature confirmed by `test_accessor_parity`; `test_accessor_parity` covers the full spatial v2 surface (SPAT2-13 parity acceptance criterion satisfied)

**Plans**: TBD

**UI hint**: no

---

### Phase 45: API Completeness Gaps + Structured Logging

**Goal**: Users can control transaction isolation and savepoints, pass named query parameters, probe connection health, and enable structured logging — all without new runtime dependencies

**Depends on**: Phase 44 (spatial v2 complete; this is purely additive to the flat core)

**Requirements**: TXN-01, TXN-02, PARAM-01, HEALTH-01, LOG-01

**Success Criteria** (what must be TRUE):

1. User can call `db.transaction(isolation_level=IsolationLevel.SERIALIZABLE)` and `db.session(isolation_level=...)` to set the isolation level; both sync and async variants accept the psycopg3 `IsolationLevel` enum
2. User can use `db.savepoint(name=None)` as a context manager to create a named savepoint and selectively rollback to it without rolling back the outer transaction
3. User can pass a `dict` of named parameters (e.g., `{"id": 1}`) using `%(name)s` placeholders to `db.execute`, `db.fetch_one`, `db.fetch_val`, `db.fetch_all`, and `db.to_dataframe`; the type annotations and docstring examples document this usage
4. User can call `db.health()` (sync) or `await db.health()` (async) and receive a dict with `connected`, `latency_ms`, and `server_version`; pooled instances include pool stats
5. User can enable pycopg structured logging by configuring stdlib `logging`; calling `get_logger()` from `pycopg.logging` returns the library logger; `log_operation` context manager records operation name and duration via `extra={}` fields; zero new runtime dependencies

**Plans**: TBD

---

### Phase 46: mypy Strict + py.typed Gate

**Goal**: `mypy --strict` over `pycopg/` exits 0 and is a blocking CI gate — the type surface is frozen and complete

**Depends on**: Phase 45 (all method signatures and renamed types are final)

**Requirements**: FREEZE-05

**Success Criteria** (what must be TRUE):

1. `uv run mypy --strict pycopg/` exits with code 0 (zero errors); CI runs it as a blocking check (no `continue-on-error`); measure error count first before fixing bottom-up (utils.py → exceptions.py → base.py → spatial.py)
2. `@overload` stubs are present on all `into="rows"/"gdf"` accessor methods so that callers can infer the return type from the literal argument
3. The 3 dev-group stubs (`pandas-stubs`, `types-geopandas`, `types-shapely`) are added to `[dependency-groups]` in `pyproject.toml` and used only by mypy (zero runtime installation)
4. `py.typed` marker is present and complete — the package is a valid PEP 561 typed package with no `ignore_missing_imports` gaps from pycopg's own code (only external stubs may require overrides)
5. Coverage ratchet remains at ≥95% (no regression from annotation work)

**Plans**: TBD

---

### Phase 47: Release v1.0.0

**Goal**: pycopg 1.0.0 is live on PyPI — a complete, stable, frozen public API for PostgreSQL/PostGIS/TimescaleDB

**Depends on**: Phase 46 (all gates including mypy strict must be green)

**Requirements**: REL-11

**Success Criteria** (what must be TRUE):

1. `pip install pycopg==1.0.0` in a clean venv imports successfully and `pycopg.__version__ == "1.0.0"`
2. All 5 gates pass: coverage ≥95%, interrogate 100%, Sphinx `-W` clean, `-W error::DeprecationWarning` clean, `mypy --strict` exit 0
3. CHANGELOG `[1.0.0]` has a Breaking section (homogenization renames) and an Added section (spatial v2 methods + API gap methods)
4. MIGRATION guide is complete with before/after code for every breaking rename introduced in Phase 41
5. Tag `v1.0.0` exists on the correct commit; GitHub Release is published; annotated tag is pushed to origin

**Plans**: TBD

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
| 34. CRUD Ergonomics | v0.9.0 | 3/3 | Complete | 2026-06-24 |
| 35. Schema Introspection | v0.9.0 | 2/2 | Complete | 2026-06-25 |
| 36. Release v0.9.0 | v0.9.0 | 2/2 | Complete | 2026-06-25 |
| 37. Dette & Audit | v0.10.0 | 5/5 | Complete | 2026-06-26 |
| 38. Performance COPY | v0.10.0 | 3/3 | Complete | 2026-06-26 |
| 39. Couverture & Benchmarks | v0.10.0 | 2/2 | Complete | 2026-06-26 |
| 40. Release v0.10.0 | v0.10.0 | 2/2 | Complete | 2026-06-26 |
| 41. API Homogenization | v1.0.0 | 5/5 | Complete    | 2026-06-28 |
| 42. Spatial v2 — Processing Helpers | v1.0.0 | 3/3 | Complete    | 2026-06-29 |
| 43. Spatial v2 — Spatial Aggregates | v1.0.0 | 3/3 | Complete   | 2026-06-29 |
| 44. Spatial v2 — Serialization + MVT | v1.0.0 | 0/? | Not started | - |
| 45. API Completeness Gaps + Structured Logging | v1.0.0 | 0/? | Not started | - |
| 46. mypy Strict + py.typed Gate | v1.0.0 | 0/? | Not started | - |
| 47. Release v1.0.0 | v1.0.0 | 0/? | Not started | - |
