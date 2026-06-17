# Roadmap: pycopg

## Milestones

- ✅ **v0.3.0 Consolidation Release** — Phases 1-7 (shipped 2026-02-11)
- ✅ **v0.3.1 Security Hotfix** — injections SQL corrigées (shipped PyPI 2026-06-06)
- ✅ **v0.4.0 Quality & Spatial Helpers** — Phases 9-15 (shipped 2026-06-14)
- ✅ **v0.5.0 ETL Pipeline Runner** — Phases 16-20 (shipped 2026-06-15)
- 🔄 **v0.6.0 Réorganisation en accessors** — Phases 21-24 (in progress)

## Phases

### v0.6.0 — Réorganisation en accessors

- [x] **Phase 21: Infrastructure & Timescale Accessor** (3 plans) - Deliver `@deprecated_alias` decorator + prove the full pattern end-to-end with the timescale accessor (6 methods) (completed 2026-06-17)
  - [x] 21-01-PLAN.md — Create `pycopg/aliases.py` (`@deprecated_alias`) + `pycopg/timescale.py` (`TimescaleAccessor`/`AsyncTimescaleAccessor`, 6 methods moved verbatim)
  - [x] 21-02-PLAN.md — Wire `db.timescale`/`async_db.timescale` lazy properties + replace the 6 flat methods with deprecated stubs + `__init__.py` exports
  - [x] 21-03-PLAN.md — Alias warn+delegate tests (D-09), `ACCESSOR_PAIRS` parity registry (D-10), migrate 27 call-sites (D-08), no-noise + coverage gate
- [ ] **Phase 22: Admin, Maint & Backup Accessors** - Replicate the proven pattern across the three smaller accessors (12 + 6 + 4 methods)
- [ ] **Phase 23: Schema Accessor & Spatial Relocation** - Migrate the largest block (~26 DDL/introspection methods) and relocate the 2 spatial-index methods to `db.spatial.*`
- [ ] **Phase 24: Exports, Docs & Release v0.6.0** - Wire `__init__.py` exports, README/Sphinx/CHANGELOG/MIGRATION, version bump, tag + PyPI publish

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

### Phase 21: Infrastructure & Timescale Accessor

**Goal**: Users calling `db.timescale.*` get a working timescale accessor, and callers still using the old flat `db.create_hypertable(...)` etc. get a `DeprecationWarning` naming the new path — the full alias + accessor pattern is established and all future phases replicate it mechanically
**Depends on**: Phase 20 (v0.5.0 shipped)
**Requirements**: REORG-01, REORG-02, REORG-03, REORG-04, TS-01
**Success Criteria** (what must be TRUE):

  1. Calling `db.timescale.create_hypertable(...)` (and all 5 other timescale methods) returns the same result as before
  2. Calling the old flat `db.create_hypertable(...)` still works AND emits a `DeprecationWarning` with a message pointing to `db.timescale.create_hypertable`
  3. `test_parity` passes with the timescale accessor registered for both sync and async surfaces
  4. A dedicated test asserts each alias both warns (with the correct message) and delegates correctly; the existing test suite runs without DeprecationWarning noise breaking any `-W error` gate; coverage stays ≥94%**Plans**: 3 plans (3 waves)

**Wave 1**

- [x] 21-01-PLAN.md — `aliases.py` decorator + `timescale.py` accessors (wave 1) — REORG-01, TS-01

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 21-02-PLAN.md — lazy properties + deprecated stubs + exports (wave 2) — REORG-02, TS-01

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 21-03-PLAN.md — alias/parity tests + 27-call-site migration + gates (wave 3) — REORG-02/03/04, TS-01

### Phase 22: Admin, Maint & Backup Accessors

**Goal**: Users can access `db.admin.*`, `db.maint.*`, and `db.backup.*` with all methods working, and the 22 legacy flat names on `db.*` all warn and delegate — three accessors delivered in one phase using the pattern already validated in Phase 21
**Depends on**: Phase 21
**Requirements**: ADM-01, MNT-01, BKP-01
**Success Criteria** (what must be TRUE):

  1. Calling `db.admin.create_role(...)`, `db.maint.vacuum(...)`, `db.backup.pg_dump(...)` (and all remaining methods in those 3 accessors) returns the same results as the old flat calls
  2. Each of the 22 legacy flat names (`db.create_role`, `db.vacuum`, `db.pg_dump`, etc.) still works and emits a `DeprecationWarning` naming the new accessor path
  3. `test_parity` passes with all three new accessors registered (sync and async)
  4. Coverage stays ≥94% with alias warn+delegate tests in place

**Plans**: 3 plans
Plans:
**Wave 1**

- [x] 22-01-PLAN.md — Create admin.py/maint.py/backup.py accessor modules (move 21 method bodies verbatim, sync + async)

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 22-02-PLAN.md — Wire lazy properties + 21 @deprecated_alias stubs on Database/AsyncDatabase + __init__.py exports

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 22-03-PLAN.md — DB-free alias tests + ACCESSOR_PAIRS registry + call-site migration + gates (coverage ≥94%, -W error)

### Phase 23: Schema Accessor & Spatial Relocation

**Goal**: Users can access all ~26 DDL/introspection methods under `db.schema.*`, and the 2 spatial-index methods (`create_spatial_index`, `list_geometry_columns`) land under `db.spatial.*` — the largest accessor block is migrated and the PostGIS surface is made thematically complete
**Depends on**: Phase 22
**Requirements**: SCH-01, SCH-02
**Success Criteria** (what must be TRUE):

  1. Calling `db.schema.create_database(...)`, `db.schema.list_tables()`, `db.schema.create_index(...)` (and all ~26 schema methods) returns the same results as before
  2. Calling `db.spatial.create_spatial_index(...)` and `db.spatial.list_geometry_columns()` works; the old flat `db.create_spatial_index(...)` and `db.list_geometry_columns()` still work and emit `DeprecationWarning` pointing to `db.spatial.*`
  3. All ~28 legacy flat schema+spatial-relocation names warn and delegate; no existing caller is silently broken
  4. `test_parity` passes with the schema accessor registered (sync and async); coverage stays ≥94%

**Plans**: TBD
**UI hint**: no

### Phase 24: Exports, Docs & Release v0.6.0

**Goal**: The 5 new accessor classes are publicly importable from `pycopg`, fully documented in README and Sphinx, with a CHANGELOG entry and MIGRATION note for the deprecation cycle, and v0.6.0 is tagged and published to PyPI
**Depends on**: Phase 23
**Requirements**: REORG-05
**Success Criteria** (what must be TRUE):

  1. `from pycopg import TimescaleAccessor, AdminAccessor, SchemaAccessor, MaintAccessor, BackupAccessor` (and async variants) succeeds — all are in `__all__`
  2. The README lists the `db.X.*` accessor surfaces with their method names; Sphinx/RTD builds cleanly (`-W` green) with each accessor documented
  3. CHANGELOG has an `[Unreleased]` / `[0.6.0]` entry noting the new accessor paths and the deprecation cycle (removal in v0.7.0); MIGRATION.md instructs callers how to update from flat names
  4. `pip install pycopg==0.6.0` installs the release; `python -c "from pycopg import Database; db = Database.from_env(); print(db.timescale)"` works in a clean venv

**Plans**: TBD

## Progress

**Execution Order:** 21 → 22 → 23 → 24

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 21. Infrastructure & Timescale Accessor | v0.6.0 | 3/3 | Complete    | 2026-06-17 |
| 22. Admin, Maint & Backup Accessors | v0.6.0 | 1/3 | In Progress|  |
| 23. Schema Accessor & Spatial Relocation | v0.6.0 | 0/? | Not started | - |
| 24. Exports, Docs & Release v0.6.0 | v0.6.0 | 0/? | Not started | - |
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
