# Roadmap: pycopg

## Milestones

- ✅ **v0.3.0 Consolidation Release** — Phases 1-7 (shipped 2026-02-11)
- ✅ **v0.3.1 Security Hotfix** — injections SQL corrigées (shipped PyPI 2026-06-06)
- ✅ **v0.4.0 Quality & Spatial Helpers** — Phases 9-15 (shipped 2026-06-14)
- ✅ **v0.5.0 ETL Pipeline Runner** — Phases 16-20 (shipped 2026-06-15)
- ✅ **v0.6.0 Réorganisation en accessors** — Phases 21-24 (shipped 2026-06-19)
- 🚧 **v0.7.0 Alias Removal + Incremental ETL** — Phases 25-29 (in progress)

## Phases

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

### 🚧 v0.7.0 Alias Removal + Incremental ETL (In Progress)

**Milestone Goal:** Hard-remove 56 deprecated flat aliases (one deprecation cycle already served in v0.6.0) and deliver watermark-based incremental ETL via `Pipeline.incremental_column`, wiring the `pipeline_runs.watermark JSONB` column that has been reserved since v0.5.0.

- [ ] **Phase 25: Alias Removal** — Hard-remove 56 `@deprecated_alias` stubs from `Database`/`AsyncDatabase`, update tests and docs, close carried-forward WR-01/IN-02 debt
- [ ] **Phase 26: Incremental ETL — Pure Layer** — `Pipeline.incremental_column` field with construction-time guards, pure SQL builders for watermark filtering, encode/decode functions
- [ ] **Phase 27: Incremental ETL — Run-Log Integration** — `_read_watermark` helper, success-only `_end_run(watermark=)` path, JSONB round-trip verification, no-advance-on-failure invariant
- [ ] **Phase 28: Incremental ETL — Extract, RunResult & Async Parity** — wire incremental filter into `run()` extract, `RunResult.watermark_used/recorded`, `dry_run` support, `AsyncETLAccessor` mirror, `TestEtlParity`, incremental docs
- [ ] **Phase 29: Release v0.7.0** — CHANGELOG finalized, MIGRATION v0.6→v0.7 complete, version bump, Sphinx `-W` clean, gates, tag + PyPI publish

## Phase Details

### Phase 25: Alias Removal

**Goal**: The v0.6.0 deprecated flat API surface is permanently removed; callers that haven't migrated get a clear `AttributeError`; carried-forward WR-01 (IDE signature erasure) and IN-02 (stale error messages) are closed
**Depends on**: Phase 24 (v0.6.0 shipped)
**Requirements**: ALIAS-RM-01, ALIAS-RM-02, ALIAS-RM-03, ALIAS-RM-04
**Success Criteria** (what must be TRUE):

  1. The 112 `@deprecated_alias` stubs (56 on `Database` + 56 on `AsyncDatabase`) are gone; the public surface is accessor-only
  2. Calling any removed flat name on a live `Database` or `AsyncDatabase` instance raises `AttributeError` with no warning, no delegation
  3. All per-alias warn+delegate tests are removed; `test_parity` and `ACCESSOR_PAIRS` still pass green; `-W error::DeprecationWarning` gate is clean because there are no stubs left to fire it
  4. MIGRATION.md has a `v0.6→v0.7` section with a 1:1 flat→accessor replacement table covering all 56 names; CHANGELOG `[0.7.0]` has a `Breaking` entry pointing to it
  5. IDE autocomplete on a `py.typed`-declared `Database` shows only accessor-namespaced methods (no `*args/**kwargs` stubs); error messages in `ExtensionNotAvailable` reference accessor paths**Plans**: 5 plans (2 waves)

**Wave 1**

- [x] 25-01-PLAN.md — Remove 56 @deprecated_alias stubs + import + IN-02 PostGIS string in database.py (wave 1)
- [ ] 25-02-PLAN.md — Remove 56 @deprecated_alias stubs + import + IN-02 PostGIS string in async_database.py (wave 1)
- [ ] 25-04-PLAN.md — IN-02 guard strings in spatial.py + timescale.py + test_sql_injection.py comment (wave 1)
- [ ] 25-05-PLAN.md — MIGRATION v0.6→v0.7 + CHANGELOG [0.7.0] Breaking + docs/*.md flat-name examples (wave 1)

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 25-03-PLAN.md — Delete aliases.py + 6 alias test files; add test_alias_removal.py (AttributeError + WR-01 proof) (wave 2)

### Phase 26: Incremental ETL — Pure Layer

**Goal**: The pure foundation of incremental ETL exists and is DB-free unit-testable — `Pipeline` accepts and validates `incremental_column`, pure SQL builders produce correct WHERE-clause SQL and subquery wraps, and the encode/decode functions for the JSONB watermark envelope are verified for all supported types
**Depends on**: Phase 25
**Requirements**: ETL-INC-01
**Success Criteria** (what must be TRUE):

  1. `Pipeline(incremental_column="updated_at", load_mode="upsert", ...)` constructs without error; the field is identifier-validated at construction time
  2. `Pipeline(incremental_column="col", load_mode="append", ...)` and `Pipeline(incremental_column="col", load_mode="replace", ...)` both raise `ValueError` at construction (forbidden combinations)
  3. Pure builder functions produce correct SQL: a SQL-string source is wrapped as `SELECT * FROM (<sql>) <alias> WHERE col > %s`; a table source gets `WHERE col > %s` appended; the watermark value is always a `%s` parameter, never interpolated
  4. `_encode_watermark` / `_decode_watermark` round-trip correctly for `datetime` (with tz), `int`, and `str` values without type drift — verified by DB-free unit tests

**Plans**: TBD

### Phase 27: Incremental ETL — Run-Log Integration

**Goal**: The run-log layer correctly reads the last successful watermark and persists a new one only on the success path; the no-advance-on-failure and empty-batch-preserves-watermark invariants are proven in integration tests
**Depends on**: Phase 26
**Requirements**: ETL-INC-02, ETL-INC-05, ETL-INC-06, ETL-INC-10
**Success Criteria** (what must be TRUE):

  1. On the first run of an incremental pipeline (no prior success row in `pipeline_runs`), `db.etl.run()` performs a full load and the resulting `pipeline_runs` row has a non-NULL `watermark` JSONB value equal to the max of the incremental column
  2. On a failed load, the `pipeline_runs` row for that run has `status='failed'` and `watermark IS NULL`; a subsequent run re-reads the prior successful watermark (if any) and re-extracts from that boundary, not from the failed run's
  3. On a run that extracts an empty batch, `pipeline_runs` records `status='success'`, `rows_loaded=0`, and the prior successful watermark is preserved unchanged (no NULL written)
  4. Watermark values for timestamp, integer, and text columns survive a full round-trip through `pipeline_runs.watermark JSONB` without type drift (typed envelope via `Jsonb()`)

**Plans**: TBD

### Phase 28: Incremental ETL — Extract, RunResult & Async Parity

**Goal**: The full incremental ETL loop is wired end-to-end in `run()` and its async mirror; `RunResult` exposes watermark fields; `dry_run` works incrementally; `TestEtlParity` covers the incremental surface; and the incremental feature is documented for users
**Depends on**: Phase 27
**Requirements**: ETL-INC-03, ETL-INC-04, ETL-INC-07, ETL-INC-08, ETL-INC-09, ETL-INC-11, ETL-INC-12
**Success Criteria** (what must be TRUE):

  1. `db.etl.run(pipeline)` on a pipeline with `incremental_column` applies `WHERE col > last_watermark` to the extract; the watermark value reaches the DB as a `%s` parameter (confirmed by checking the SQL or a parameterized-query spy), never by string interpolation
  2. If the transform chain drops the incremental column, `run()` raises a clear `ETLError` subclass (not a bare `KeyError`) identifying the missing column
  3. `RunResult` from `db.etl.run(pipeline)` has `watermark_used` set to the filter floor applied this run and `watermark_recorded` set to the new high-water mark persisted; both are `None` for non-incremental pipelines; `history()` and `last_run()` surface the same fields from stored rows
  4. `db.etl.run(pipeline, dry_run=True)` on an incremental pipeline reads the last watermark and computes `watermark_used` and `watermark_recorded` without writing any `pipeline_runs` row
  5. `async_db.etl.run(pipeline)` mirrors the full incremental surface; `TestEtlParity` passes with incremental methods included; `docs/etl.md` has an incremental section describing watermark-column requirements, the upsert requirement, and the backfill/reset workflow

**UI hint**: no
**Plans**: TBD

### Phase 29: Release v0.7.0

**Goal**: v0.7.0 is published to PyPI with all quality gates green, a complete CHANGELOG Breaking/Added section, and a MIGRATION v0.6→v0.7 guide that enables callers to upgrade safely
**Depends on**: Phase 28
**Requirements**: REL-07
**Success Criteria** (what must be TRUE):

  1. Version is bumped to `0.7.0` in both `pyproject.toml` and `docs/conf.py`; the package is tagged `v0.7.0` and published to PyPI via OIDC; `pip install pycopg==0.7.0` in a clean venv imports successfully
  2. All quality gates pass: coverage ≥ 94%, `interrogate ≥ 95%`, Sphinx `-W` clean, `-W error::DeprecationWarning` green (no stubs left to fire)
  3. CHANGELOG `[0.7.0]` contains a `Breaking` entry (alias removal, with pointer to MIGRATION) and an `Added` entry (incremental ETL); MIGRATION v0.6→v0.7 is complete with the 56-name flat→accessor table and incremental usage notes

**Plans**: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 25. Alias Removal | v0.7.0 | 1/5 | In Progress|  |
| 26. Incremental ETL — Pure Layer | v0.7.0 | 0/TBD | Not started | - |
| 27. Incremental ETL — Run-Log Integration | v0.7.0 | 0/TBD | Not started | - |
| 28. Incremental ETL — Extract, RunResult & Async Parity | v0.7.0 | 0/TBD | Not started | - |
| 29. Release v0.7.0 | v0.7.0 | 0/TBD | Not started | - |
| 21. Infrastructure & Timescale Accessor | v0.6.0 | 3/3 | Complete    | 2026-06-17 |
| 22. Admin, Maint & Backup Accessors | v0.6.0 | 3/3 | Complete    | 2026-06-17 |
| 23. Schema Accessor & Spatial Relocation | v0.6.0 | 4/4 | Complete    | 2026-06-17 |
| 24. Exports, Docs & Release v0.6.0 | v0.6.0 | 3/3 | Complete    | 2026-06-19 |
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
