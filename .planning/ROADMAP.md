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
- 🚧 **v0.10.0 Durcissement & Performance** — Phases 37-40 (in progress)

## Phases

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

### 🚧 v0.10.0 Durcissement & Performance (In Progress)

**Milestone Goal:** Assainir et optimiser le socle avant le gel 1.0 — solder la dette technique, passer une passe outillée d'audit et de code mort, monter la couverture à 95%, et router les volumes par COPY sous garde-fou de benchmarks. Non-cassant, zéro nouvelle dépendance runtime.

- [ ] **Phase 37: Dette & Audit** - Corriger la dette accumulée (flaky tests, ruff, warnings advisory, code mort, TableNotFound) + passe d'audit outillée + sign-off Nyquist 22-24
- [ ] **Phase 38: Performance COPY** - Router `from_dataframe` + ETL load via COPY, micro-opt `insert_batch`, parité sync/async vérifiée
- [ ] **Phase 39: Couverture & Benchmarks** - Lever le cliquet de couverture à 95%, écrire la suite de benchmarks garde-fou
- [ ] **Phase 40: Release v0.10.0** - Bump version, CHANGELOG, 4 gates verts, tag + PyPI OIDC publish + smoke

## Phase Details

### Phase 37: Dette & Audit
**Goal**: La base de code est propre et auditée — dette technique connue soldée, passe outillée terminée, Nyquist en règle
**Depends on**: Nothing (first phase of v0.10.0)
**Requirements**: DEBT-01, DEBT-02, DEBT-03, DEBT-04, DEBT-05, AUDIT-01, AUDIT-02, NYQ-01
**Success Criteria** (what must be TRUE):
  1. `uv run pytest` en suite complète passe de façon déterministe — les trois tests flaky (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`, bound-param ~2.7%) ne failent plus par isolation de fixture
  2. `uv run ruff check pycopg tests` retourne exactement 0 erreur (N818/W291/F841/E722 corrigées)
  3. Chaque warning advisory v0.8-0.9 (WR-01, WR-03, %/`%s` structurel, IN-03 `chunk_seq`, advisory v0.9) est soit corrigé dans le code, soit clos avec une justification consignée dans un fichier de décision
  4. `TableNotFound` a soit un site de raise interne réel, soit est retiré de `__all__` — l'incohérence est résolue et documentée
  5. Les VALIDATION.md des phases 22-24 sont à `nyquist_compliant: true` (PASSED) ; un rapport d'audit classé HIGH/MEDIUM/LOW existe pour `pycopg/`, chaque finding HIGH/MEDIUM ayant une disposition ; une allowlist vulture documente les faux positifs de code mort
**Plans**: TBD

### Phase 38: Performance COPY
**Goal**: Les chemins d'insertion à volume (`from_dataframe`, ETL load, `insert_batch`) sont optimisés via COPY et micro-opts, avec parité sync/async maintenue
**Depends on**: Phase 37
**Requirements**: PERF-01, PERF-02, PERF-03, PERF-05
**Success Criteria** (what must be TRUE):
  1. `db.from_dataframe()` et `async_db.from_dataframe()` routent via le protocole COPY (`psycopg` COPY) au lieu de `df.to_sql(con=engine)`, en préservant le contrat `if_exists`/`index`/`primary_key` — un test vérifie le comportement observable
  2. Le chemin de load ETL (`append`/`replace`) route via COPY sans matérialiser `astype(object)` + `to_dict(orient="records")` sur les gros DataFrames — `db.etl.run()` retourne le même statut/compte qu'avant
  3. `insert_batch` hoiste le placeholder de ligne invariant hors de la boucle — comportement byte-exact identique, couvert par un test de non-régression
  4. Les tests de parité existants (`test_parity`/`test_accessor_parity`) restent verts après tous les changements de routage — aucune régression de parité sync/async
**Plans**: TBD
**UI hint**: no

### Phase 39: Couverture & Benchmarks
**Goal**: Le cliquet de couverture est tenu à 95% et une suite de benchmarks reproductible documente les gains COPY
**Depends on**: Phase 38
**Requirements**: COV-01, PERF-04
**Success Criteria** (what must be TRUE):
  1. `uv run pytest` mesure ≥95% de couverture et `--cov-fail-under=95` est vert en CI (le fichier de config pytest reflète le nouveau seuil)
  2. Une suite de benchmarks (dev-group, sans nouvelle dépendance runtime) mesure les chemins `insert_batch`, `copy_insert`, `from_dataframe`, ETL load sur un volume représentatif (ex. 100k lignes) et produit des résultats comparatifs lisibles
  3. Le protocole de benchmark est documenté (comment lancer, comment lire les résultats, comment interpréter une régression)
**Plans**: TBD

### Phase 40: Release v0.10.0
**Goal**: v0.10.0 est publié sur PyPI avec tous les gates verts et le CHANGELOG documentant les gains de durcissement et de performance
**Depends on**: Phase 39
**Requirements**: REL-10
**Success Criteria** (what must be TRUE):
  1. La version est bumpée dans les deux sources canoniques (`pyproject.toml` + `docs/conf.py`) ; `__version__` reste dynamique via `importlib.metadata` et retourne `"0.10.0"` après install propre
  2. CHANGELOG `[0.10.0]` documente le durcissement (dette soldée, audit, couverture 95%) et la performance (gains COPY mesurés)
  3. Les 4 gates sont verts : couverture ≥95%, interrogate 100%, Sphinx `-W` clean, `-W error::DeprecationWarning` green
  4. Le tag `v0.10.0` est créé, la wheel + sdist sont publiées sur PyPI via OIDC trusted publishing, et un smoke clean-venv confirme `__version__ == "0.10.0"`
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
| 37. Dette & Audit | v0.10.0 | 0/TBD | Not started | - |
| 38. Performance COPY | v0.10.0 | 0/TBD | Not started | - |
| 39. Couverture & Benchmarks | v0.10.0 | 0/TBD | Not started | - |
| 40. Release v0.10.0 | v0.10.0 | 0/TBD | Not started | - |
