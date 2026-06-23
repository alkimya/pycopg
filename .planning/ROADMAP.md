# Roadmap: pycopg

## Milestones

- ✅ **v0.3.0 Consolidation Release** — Phases 1-7 (shipped 2026-02-11)
- ✅ **v0.3.1 Security Hotfix** — injections SQL corrigées (shipped PyPI 2026-06-06)
- ✅ **v0.4.0 Quality & Spatial Helpers** — Phases 9-15 (shipped 2026-06-14)
- ✅ **v0.5.0 ETL Pipeline Runner** — Phases 16-20 (shipped 2026-06-15)
- ✅ **v0.6.0 Réorganisation en accessors** — Phases 21-24 (shipped 2026-06-19)
- ✅ **v0.7.0 Alias Removal + Incremental ETL** — Phases 25-29 (shipped 2026-06-22)
- 🔄 **v0.8.0 TimescaleDB avancé** — Phases 30-33 (in progress)

## Phases

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

### v0.8.0 TimescaleDB avancé (Phases 30-33)

- [x] **Phase 30: Chunk Management & Partitioning** - Deliver `show_chunks`, `drop_chunks`, `add_dimension`, `add_reorder_policy` on both sync and async accessors using the pure-builder pattern with no new connection seams — completed 2026-06-22
- [ ] **Phase 31: Continuous Aggregate Lifecycle** - Deliver the full `create_continuous_aggregate` + `refresh_continuous_aggregate` + `add_continuous_aggregate_policy` lifecycle on both accessors using the `connect(autocommit=True)` seam
- [ ] **Phase 32: Query Helpers & Parity Verification** - Deliver `time_bucket` and `time_bucket_gapfill` query helpers with DataFrame/rows output, plus full TS-ADV-10 sync/async parity confirmation across all 9 new methods
- [ ] **Phase 33: Release v0.8.0** - Docs, CHANGELOG, version bump, 4 quality gates, human-gated tag and PyPI publish

## Phase Details

### Phase 30: Chunk Management & Partitioning

**Goal**: Users can inspect and manage hypertable chunks, and add partitioning dimensions and a reorder policy, via `db.timescale.*` using the established pure-builder pattern

**Depends on**: Nothing (first phase of milestone; existing `TimescaleAccessor` from v0.6.0 is the base)

**Requirements**: TS-ADV-04, TS-ADV-05, TS-ADV-08, TS-ADV-09

**Success Criteria** (what must be TRUE):

1. User can call `db.timescale.show_chunks("my_hypertable")` and receive a `list[str]` of chunk names; filtering by `older_than`/`newer_than` returns only the matching subset
2. User can call `db.timescale.drop_chunks("my_hypertable", older_than="30 days")` and confirm the matching chunks are gone; calling with both bounds `None` raises `ValueError` before any DB round-trip; calling with `dry_run=True` returns the would-be-dropped list without deleting anything
3. User can call `db.timescale.add_dimension("my_hypertable", "device_id", partition_type="hash", number_partitions=4)` on a hypertable and confirm the dimension is registered (TSDB 2.28's `by_hash`/`by_range` builder works on populated hypertables too); calling with the wrong type/param combination raises `ValueError` at construction time; calling `add_dimension` for a column that is **already a dimension** (with `if_not_exists=False`) raises a clear pycopg-domain error (`TimescaleError`) — *(reshaped 2026-06-22: the legacy "non-empty hypertable raises" behavior does not exist on TSDB 2.28's builder form; see Phase 30 CONTEXT D-08)*
4. User can call `db.timescale.add_reorder_policy("my_hypertable", "my_index")` and the generated SQL is asserted by a mock unit test; on a Community-licensed build the policy job row exists in `timescaledb_information.jobs` and `CALL run_job(job_id)` completes without error, while on an Apache-licensed build (local/CI) the live test tolerates `FeatureNotSupported` — *(2026-06-22: see Phase 30 CONTEXT D-12)*
5. All four methods have async counterparts (`async_db.timescale.*`) verified by `test_accessor_parity`; coverage ratchet ≥94% holds

**Plans**: 3 plans (2 implementation waves over 3 sequential waves due to shared `timescale.py`)
**Wave 1**

- [x] 30-01-PLAN.md — Foundation: `TimescaleError` exception + `TSDB_SHOW_CHUNKS` SQL constant + new `tests/test_timescale.py` scaffold (sync/async skip-fixtures + Wave 0 stubs) [wave 1]

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 30-02-PLAN.md — `show_chunks` + `drop_chunks` (sync + async): type-driven `%s` casts, oldest-first list, both-None ValueError, capture-before-drop dry_run [wave 2] — completed 2026-06-22

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 30-03-PLAN.md — `add_dimension` + `add_reorder_policy` (sync + async): by_hash/by_range, mutual-excl ValueError, dup-dim→TimescaleError, license-tolerant reorder test, full parity + coverage gate [wave 3] — completed 2026-06-22

**UI hint**: no

### Phase 31: Continuous Aggregate Lifecycle

**Goal**: Users can create, manually refresh, and auto-schedule a continuous aggregate via `db.timescale.*`, with the `connect(autocommit=True)` seam correctly isolating CAGG DDL and refresh from any enclosing transaction

**Depends on**: Phase 30 (proves the accessor extension pattern on the real DB; TimescaleDB version confirmed)

**Requirements**: TS-ADV-01, TS-ADV-02, TS-ADV-03

**Success Criteria** (what must be TRUE):

1. User can call `db.timescale.create_continuous_aggregate("metrics_hourly", select_sql)` and confirm the view exists in `timescaledb_information.continuous_aggregates`; the call succeeds even when issued after a prior `db.execute("SELECT 1")` in the same session (proving autocommit isolation); passing a `select_sql` without `time_bucket(` raises `ValueError` before any DB round-trip
2. User can call `db.timescale.refresh_continuous_aggregate("metrics_hourly")` on committed data and confirm the materialized rows appear; the call succeeds from inside a `db.session()` context (autocommit connection bypasses the session transaction)
3. User can call `db.timescale.add_continuous_aggregate_policy("metrics_hourly", start_offset="7 days", end_offset="1 hour")` and confirm the policy job row exists in `timescaledb_information.jobs`; calling with `start_offset` interval shorter than `end_offset` raises `ValueError`; `CALL run_job(job_id)` executes without error
4. All three methods have async counterparts with the correct `await` on the `has_extension` guard (no silent guard bypass); verified by `test_accessor_parity`

**Plans**: 3 plans (3 sequential waves — shared `pycopg/timescale.py` + `tests/test_timescale.py` force sequential ordering, one method end-to-end per plan)

**Wave 1**

- [x] 31-01-PLAN.md — `create_continuous_aggregate` (sync + async) via the `connect(autocommit=True)` seam: `time_bucket(` ValueError, `materialized_only`/`with_no_data` flags, mock-authoritative + license-tolerant tests [wave 1]

**Wave 2** *(blocked on Wave 1 — shared files)*

- [x] 31-02-PLAN.md — `refresh_continuous_aggregate` (sync + async) via the autocommit seam: `datetime|None`-only windows (str rejected, deliberate divergence from `drop_chunks`), both-None=full refresh, session-isolation proof [wave 2]

**Wave 3** *(blocked on Wave 2 — shared files)*

- [ ] 31-03-PLAN.md — `add_continuous_aggregate_policy` (sync + async) via plain `execute` (D-01) + `_check_offset_ordering` same-unit guard, `NULL`-for-None offsets, license-tolerant jobs/run_job test, full 3-method `test_accessor_parity` gate [wave 3]

**UI hint**: no

### Phase 32: Query Helpers & Parity Verification

**Goal**: Users can run bucketed and gap-filled time-series aggregation queries returning a DataFrame or list of dicts; full sync/async parity for all 9 new v0.8.0 methods is confirmed

**Depends on**: Phase 31 (cagg fixture provides realistic test data; full 9-method surface exists for TS-ADV-10 parity check)

**Requirements**: TS-ADV-06, TS-ADV-07, TS-ADV-10

**Success Criteria** (what must be TRUE):

1. User can call `db.timescale.time_bucket("metrics", "time", "1 hour", "avg(value)")` with `into="df"` and receive a `DataFrame` with a `bucket` column and the requested aggregate; calling with `into="rows"` returns `list[dict]`; `into="gdf"` raises `ValueError`
2. User can call `db.timescale.time_bucket_gapfill("metrics", "time", "1 hour", start, finish, "locf(avg(value))")` with Python `datetime` bound parameters (not hardcoded literals) and receive gap-filled rows including NULL-padded buckets; both `start` and `finish` are required positional arguments (no WHERE-inference path)
3. `test_accessor_parity` passes with all 9 new `TimescaleAccessor` methods mirrored on `AsyncTimescaleAccessor`; no method missing on either side; coverage ratchet ≥94% holds with all new autocommit branches covered

**Plans**: TBD

**UI hint**: no

### Phase 33: Release v0.8.0

**Goal**: v0.8.0 is published to PyPI with updated documentation covering all 9 new time-series methods, 4 quality gates green, and a clean-venv install confirmed

**Depends on**: Phase 32 (all 9 methods complete and verified at parity)

**Requirements**: REL-08

**Success Criteria** (what must be TRUE):

1. Version is bumped in both `pyproject.toml` and `docs/conf.py`; CHANGELOG has a `[0.8.0]` Added section covering the 9 new methods; `pip install pycopg==0.8.0` in a clean venv imports all 9 new methods without error
2. All 4 quality gates are green: coverage ≥94%, `interrogate` ≥95%, Sphinx `-W` clean, zero `DeprecationWarning` on import
3. `docs/timescaledb.md` (or equivalent advanced section) documents the 9 new methods; README updated to reference them; Sphinx API pages render without errors

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
| 30. Chunk Management & Partitioning | v0.8.0 | 3/3 | Complete    | 2026-06-22 |
| 31. Continuous Aggregate Lifecycle | v0.8.0 | 2/3 | In Progress|  |
| 32. Query Helpers & Parity Verification | v0.8.0 | 0/? | Not started | - |
| 33. Release v0.8.0 | v0.8.0 | 0/? | Not started | - |
