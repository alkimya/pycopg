# Roadmap: pycopg

## Milestones

- ✅ **v0.3.0 Consolidation Release** — Phases 1-7 (shipped 2026-02-11)
- ✅ **v0.3.1 Security Hotfix** — injections SQL corrigées (shipped PyPI 2026-06-06)
- ✅ **v0.4.0 Quality & Spatial Helpers** — Phases 9-15 (shipped 2026-06-14)
- 🚧 **v0.5.0 ETL Pipeline Runner** — Phases 16-20 (in progress)

## Phases

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

### 🚧 v0.5.0 ETL Pipeline Runner (In Progress)

**Milestone Goal:** Add a declarative ETL pipeline layer (`db.etl.*` / `async_db.etl.*`) that runs
extract → transform → load flows with run tracking and safe, idempotent re-runs — built on
pycopg's existing DataFrame/spatial helpers, at full sync/async parity. Zero new runtime
dependencies. Architecture mirrors `spatial.py`.

- [x] **Phase 16: Pure ETL Layer** — Pipeline dataclass, SQL constants, pure builders; fully unit-testable with no DB (completed 2026-06-14)
- [x] **Phase 17: Run-Tracking Foundation** — `pipeline_runs` DDL + status lifecycle + separate-connection run-log writes (completed 2026-06-15)
- [x] **Phase 18: Load Modes & Extract** — extract (SQL/table), append/replace/upsert with transactional correctness, transform chain (completed 2026-06-15)
- [x] **Phase 19: Sync Runner & Query Surface** — `run()`, `RunResult`, `history()`, `last_run()`, `dry_run` (completed 2026-06-15)
- [ ] **Phase 20: Async Parity, Wiring & Release** — `AsyncETLAccessor`, lazy `db.etl` property, `TestEtlParity`, Sphinx docs, coverage gate, v0.5.0 PyPI publish

## Phase Details

### Phase 16: Pure ETL Layer

**Goal**: Users can define a `Pipeline` dataclass that is inspectable and validated at construction time — all ETL SQL constants and pure DB-free builder functions exist and are unit-testable without any database connection
**Depends on**: Phase 15
**Requirements**: ETL-01
**Success Criteria** (what must be TRUE):

  1. `Pipeline(name=..., source=..., target=..., load_mode=...)` can be instantiated and all attributes (`name`, `source`, `target`, `load_mode`, `conflict_columns`, `schema`) are readable
  2. Constructing `Pipeline(load_mode='upsert')` without `conflict_columns` raises `ValueError` at construction time, before any DB interaction
  3. All ETL SQL constants (`ETL_INIT_PIPELINE_RUNS`, `ETL_INSERT_RUN`, `ETL_UPDATE_RUN`, `ETL_LIST_RUNS`, `ETL_GET_LAST_RUN`) exist in `queries.py` and contain no f-string identifier interpolation
  4. Pure builder functions (`build_init_sql()`, `build_truncate_sql()`, etc.) are importable and return parameterized SQL strings in unit tests that require no DB fixture

**Plans**: 2 plans

  - [x] 16-01-PLAN.md — ETL exception hierarchy + 5 ETL SQL constants + exception exports (Wave 1) — completed 2026-06-14
  - [x] 16-02-PLAN.md — Pipeline frozen dataclass + build_init_sql/build_truncate_sql + DB-free tests (Wave 2) — completed 2026-06-14

### Phase 17: Run-Tracking Foundation

**Goal**: The `pipeline_runs` table schema is finalised and the separate-connection run-log write pattern is solid — so all subsequent load phases inherit correct transaction boundary behavior
**Depends on**: Phase 16
**Requirements**: ETL-07, ETL-08, ETL-09, ETL-14
**Success Criteria** (what must be TRUE):

  1. After any `run()`, a row exists in `pipeline_runs` with `run_id`, `pipeline_name`, `started_at`, `finished_at`, `status`, `rows_extracted`, `rows_loaded`, and a nullable `watermark` JSONB column (always NULL in v0.5.0)
  2. `db.etl.init()` creates the `pipeline_runs` table; calling it a second time is idempotent (no error, no duplicate table)
  3. If no explicit `init()` is called, the first `run()` auto-creates `pipeline_runs` via `CREATE TABLE IF NOT EXISTS`
  4. A run that fails during load records `status='failed'` with non-null `error_message` and `error_traceback`; the `pipeline_runs` row is committed even when the load transaction rolled back, because run-log writes use a dedicated autocommit connection separate from the load transaction

**Plans**: 2 plans (1 + 1 gap-closure)

Plans:

- [x] 17-01-PLAN.md — ETLAccessor (init/_start_run/_end_run/run stub) + lazy db.etl property + run-log tests (SC-1..SC-4) — completed 2026-06-15
- [x] 17-02-PLAN.md — gap closure: structural run-log isolation (init/_start_run/_end_run open a dedicated db.connect(autocommit=True), bypassing session-aware cursor) + session-rollback regression test (closes SC-4 session-path gap, ETL-08/ETL-09)

### Phase 18: Load Modes & Extract

**Goal**: All three load modes and both extract source types work correctly with transactional safety and SQL injection prevention via `validate_identifiers`
**Depends on**: Phase 17
**Requirements**: ETL-02, ETL-03, ETL-04, ETL-05, ETL-06, ETL-16
**Success Criteria** (what must be TRUE):

  1. `source="SELECT ..."` (SQL) and `source="table_name"` (table) both extract a DataFrame correctly, delegating to `to_dataframe`
  2. `load_mode='append'` inserts rows into an existing target; running the pipeline twice doubles the row count; a non-existent target raises `ETLTargetNotFoundError`
  3. `load_mode='replace'` with a mid-load error leaves the target with its original rows (TRUNCATE + INSERT are atomic in one transaction; a failed mid-INSERT rolls back the TRUNCATE too); if the target does not exist it is created
  4. `load_mode='upsert'` with `conflict_columns` updates existing rows and inserts new ones with no duplicates across two identical runs
  5. `transform=None` is a no-op; a single `Callable[[DataFrame], DataFrame]` is applied before load; `transform=[fn1, fn2, fn3]` applies callables in sequence; an exception in any transform step raises `ETLTransformError` and records a failed run, identifying which step failed
  6. Every load SQL builder calls `validate_identifiers` on table names and conflict columns before any string interpolation

**Plans**: 3 plans
Plans:
**Wave 1**

- [x] 18-01-PLAN.md — Pure (sql, params) load builders (_build_insert_sql / _build_upsert_sql) + _step_label + DB-free unit & injection tests (Wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 18-02-PLAN.md — Real run(pipeline) body: extract → transform chain → mode-dispatched atomic load (corrected txn seam) + run-log wiring (Wave 2)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 18-03-PLAN.md — Integration tests (extract, append/replace/upsert, replace_atomic_rollback, transform, NaN→NULL, ETL-09 guard) + Phase 17 caller migration (Wave 3)

### Phase 19: Sync Runner & Query Surface

**Goal**: The complete sync ETL surface (`run`, `history`, `last_run`, `dry_run`) is wired and returns correct `RunResult` objects backed by real `pipeline_runs` rows
**Depends on**: Phase 18
**Requirements**: ETL-10, ETL-11, ETL-15, ETL-17
**Success Criteria** (what must be TRUE):

  1. `db.etl.run(pipeline)` returns a `RunResult` with `run_id`, `pipeline_name`, `status`, `rows_extracted`, `rows_loaded`, `started_at`, `finished_at`, and `error`
  2. `db.etl.history("my_pipeline")` returns a list of `RunResult` objects for that pipeline ordered newest-first; running the pipeline twice yields two entries
  3. `db.etl.last_run("my_pipeline")` returns the most recent `RunResult`; returns `None` when no runs exist for that pipeline name
  4. `db.etl.run(pipeline, dry_run=True)` executes extract and transform but skips load; returns `RunResult(status='dry_run', rows_loaded=0)` and writes no row to `pipeline_runs`

**Plans**: 3 plans

Plans:

**Wave 1**

- [x] 19-01-PLAN.md — RunResult frozen dataclass + _row_to_result mapper + ETL_GET_RUN constant (pure, DB-free)

**Wave 2** *(blocked on Wave 1)*

- [x] 19-02-PLAN.md — run() -> RunResult upgrade + dry_run early fork + history()/last_run() read methods

**Wave 3** *(blocked on Wave 2)*

- [x] 19-03-PLAN.md — TestRowToResult unit + TestRunResultSurface (SC-1..SC-4) integration + existing run_id assertion migration

### Phase 20: Async Parity, Wiring & Release

**Goal**: `AsyncETLAccessor` reaches full parity with `EtlAccessor`, `db.etl` / `async_db.etl` lazy properties are wired, `TestEtlParity` enumerates the ETL surface, and pycopg v0.5.0 ships to PyPI with green Sphinx docs and a held ≥ 94% coverage gate
**Depends on**: Phase 19
**Requirements**: ETL-12, ETL-13
**Success Criteria** (what must be TRUE):

  1. `await async_db.etl.run(pipeline)`, `await async_db.etl.history(name)`, `await async_db.etl.last_run(name)`, and `await async_db.etl.run(pipeline, dry_run=True)` exist and produce results equivalent to their sync counterparts
  2. Sync transform callables are dispatched via `asyncio.to_thread` in `AsyncETLAccessor.run()` — a slow transform does not block the event loop for concurrent coroutines
  3. `db.etl` returns a lazily-created `ETLAccessor`; `async_db.etl` returns a lazily-created `AsyncETLAccessor`; both follow the `db.spatial` / `async_db.spatial` lazy-creation pattern exactly
  4. `TestEtlParity` (an extension to the existing `test_parity` harness using `inspect.getmembers`) enumerates `EtlAccessor` vs `AsyncETLAccessor` method surfaces and asserts full parity; it passes in CI
  5. `docs/etl.md` Sphinx autodoc page renders without `-W` warnings and is live on ReadTheDocs; `interrogate ≥ 95` passes on ETL docstrings; `uv run pytest --cov` on real PG measures ≥ 94% and the ratchet gate is held; CHANGELOG + MIGRATION updated; `pycopg==0.5.0` tagged and published to PyPI

**Plans**: 3 plans

Plans:

**Wave 1**

- [x] 20-01-PLAN.md — AsyncETLAccessor async mirror + lazy async_db.etl property + 4 top-level exports (ETL-12, ETL-13)

**Wave 2** *(blocked on Wave 1)*

- [x] 20-02-PLAN.md — TestEtlParity surface enumeration + behavioral async tests + docs/etl.md + toctree (ETL-12, ETL-13)

**Wave 3** *(blocked on Waves 1-2)*

- [ ] 20-03-PLAN.md — v0.5.0 release: version bump + CHANGELOG/MIGRATION + coverage/interrogate/sphinx gates + tag/publish (ETL-12, ETL-13)

## Progress

**Execution Order:** 16 → 17 → 18 → 19 → 20

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
| 16. Pure ETL Layer | v0.5.0 | 2/2 | Complete    | 2026-06-14 |
| 17. Run-Tracking Foundation | v0.5.0 | 2/2 | Complete    | 2026-06-15 |
| 18. Load Modes & Extract | v0.5.0 | 3/3 | Complete    | 2026-06-15 |
| 19. Sync Runner & Query Surface | v0.5.0 | 3/3 | Complete   | 2026-06-15 |
| 20. Async Parity, Wiring & Release | v0.5.0 | 2/3 | In Progress|  |
