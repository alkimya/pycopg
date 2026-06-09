# Roadmap: pycopg

## Milestones

- ✅ **v0.3.0 Consolidation Release** — Phases 1-7 (shipped 2026-02-11)
- ✅ **v0.3.1 Security Hotfix** — injections SQL corrigées (shipped PyPI 2026-06-06)
- 🔵 **v0.4.0 Quality & Spatial Helpers** — Phases 9-15 — *validé 2026-06-06, prêt à exécuter*

## Phases

### 🔵 v0.4.0 Quality & Spatial Helpers (Phases 9-15) — EN COURS

Détails : [milestones/v0.4.0-MILESTONE.md](milestones/v0.4.0-MILESTONE.md) · Exigences : [REQUIREMENTS.md](REQUIREMENTS.md) (46 mappées, 0 non couverte) · Audit source : [AUDIT-2026-06-06.md](AUDIT-2026-06-06.md)

- [x] Phase 9: Migration uv (outillage : dev + CI + build + lockfile) — COMPLETE 2026-06-06
- [x] Phase 10: Sécurité résiduelle & robustesse (bugs B1/B2/B3/B5) — coverage cliquet → 80 (completed 2026-06-08)
- [ ] Phase 11: Parité sync/async complète — coverage cliquet → 90
- [ ] Phase 12: Refactoring (brancher base.py + queries.py) — coverage cliquet → 95
- [ ] Phase 13: Qualité documentaire (docstrings numpydoc + interrogate ≥ 95)
- [ ] Phase 14: Spatial helpers (`db.spatial.*`, ex-Phase 8) — trancher 4 points ouverts en début de phase
- [ ] Phase 15: Release v0.4.0 (PyPI + ReadTheDocs)

## Phase Details

> Synchronisé depuis [milestones/v0.4.0-MILESTONE.md](milestones/v0.4.0-MILESTONE.md) (source de vérité du cadrage). Détails complets et risques : voir le document milestone.

### Phase 9: Migration uv (outillage projet)

**Goal**: Faire de `uv` l'outil de gestion projet (dev + CI + build), AVANT tout le reste — toutes les phases suivantes tournent sous le nouvel outillage.
**Depends on**: Nothing (première phase du milestone v0.4.0)
**Requirements**: TOOL-01, TOOL-02, TOOL-03, TOOL-04, TOOL-05
**Success Criteria** (what must be TRUE):

  1. `uv sync --all-extras --dev` provisionne l'environnement dev (pyproject configuré pour uv)
  2. `uv.lock` et `.python-version` sont commités pour des environnements reproductibles
  3. Le workflow CI de tests tourne sous uv et passe (remplace le flux `venv`/`pip` classique)
  4. Le workflow CI de publish build via `uv build` (wheel + sdist), backend hatchling conservé, trusted publishing PyPI conservé
  5. Les commandes contributeur (CLAUDE.md, Makefile, Development/CONTRIBUTING) utilisent uv ; la doc utilisateur garde `pip install pycopg`

### Phase 10: Sécurité résiduelle & robustesse

**Goal**: Fermer toute injection restante + bugs de correction ; cliquet coverage → 80.
**Depends on**: Phase 9
**Requirements**: SEC-01, SEC-02, SEC-03, SEC-04, SEC-05, SEC-06
**Success Criteria** (what must be TRUE):

  1. Identifiants/intervalles validés partout où il en manque (compression/retention policies, spatial index, vacuum/analyze, drop_index, dataframes, insert/upsert_many, valid_until, create_extension schema, grant/revoke whitelist, options CSV)
  2. Bugs corrigés : B1 (`PooledDatabase.execute` commit), B2 (`session()` exception masquée), B3 (migrations atomiques), B5 (`subprocess.os.environ`)
  3. Chaque correctif a son test d'injection dédié (rouge → vert)
  4. Gate coverage globale montée à 80 (cliquet, jamais redescendante)

**Plans:** 5/5 plans complete
Plans:
**Wave 1**

- [x] 10-01-PLAN.md — B1 fix (PooledDatabase.execute commit, sync+async) + D-01 audit (SEC-05/validations acquired)
- [x] 10-02-PLAN.md — B3 fix (atomic _apply + rollback) + red→green migration-atomicity test
- [x] 10-03-PLAN.md — B5 fix (subprocess.os.environ → os.environ, 3 sites) + red→green env test

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 10-04-PLAN.md — B2 residual fix (session() close-on-commit-failure, sync+async) + red→green leak test

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 10-05-PLAN.md — [BLOCKING] coverage ratchet 70→80 (targeted fill, then gate flip)

### Phase 11: Parité sync/async complète

**Goal**: Restaurer la valeur cœur du projet — 0 méthode divergente non documentée ; cliquet coverage → 90.
**Depends on**: Phase 10
**Requirements**: PAR-01, PAR-02, PAR-03, PAR-04, PAR-05, PAR-06, PAR-07, PAR-08, PAR-09
**Success Criteria** (what must be TRUE):

  1. AsyncDatabase implémente add_primary_key, add_foreign_key, add_unique_constraint, truncate_table, drop_extension, database_exists, list_databases, create/create_from_env
  2. Database implémente insert_many, upsert_many, stream, notify
  3. C1/C2/C3 corrigés (primary_key appliqué async, `close()` dispose l'engine, driver `postgresql+psycopg_async`)
  4. Signatures alignées : create_extension(schema), create_schema(owner), sémantique table_info/list_roles
  5. `test_parity.py` étendu aux champs de retour + comportement réel (intégration vraie DB, D-03)
  6. Gate coverage montée à 90 (cliquet)

**Plans:** 7 plansPlans:
**Wave 1**

- [x] 11-01-PLAN.md — Config.async_url + async_engine rewire (C3/PAR-06)
- [x] 11-02-PLAN.md — sync insert_many/upsert_many/stream/notify (PAR-03)

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 11-03-PLAN.md — async add_primary_key/add_foreign_key/add_unique_constraint/truncate_table (PAR-01)

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 11-04-PLAN.md — async drop_extension/database_exists/list_databases/create/create_from_env (PAR-02)

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 11-05-PLAN.md — C1 primary_key applied + C2 close() dispose + signature alignment (PAR-04/05/07)

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 11-06-PLAN.md — test_parity integration assertions + allow-lists + per-method tests (PAR-08)

**Wave 6** *(blocked on Wave 5 completion)*

- [ ] 11-07-PLAN.md — coverage gap-fill + ratchet flip 80→90 (PAR-09)

### Phase 12: Refactoring — brancher les abstractions

**Goal**: Éliminer la duplication en branchant `base.py` & `queries.py` existants ; cliquet coverage → 95.
**Depends on**: Phase 11
**Requirements**: REF-01, REF-02, REF-03, REF-04, REF-05
**Success Criteria** (what must be TRUE):

  1. R1 — `queries.py` branché : ~25 SQL inline remplacés par les constantes (source unique de vérité)
  2. R3 — `base.py` adopté : `Database(DatabaseBase, QueryMixin)` + idem async ; from_env/from_url/__repr__ remontés ; `_build_batch_insert_sql` utilisé
  3. R4 — builders purs sans état extraits (`_build_role_options`, `_build_pg_dump_cmd`, `_build_pg_restore_cmd`), testables sans DB
  4. Code mort résiduel nettoyé (imports `re`, `stdout` non lu, `try/except: raise`, constantes `*_SIMPLE`)
  5. Gate coverage montée à 95 (cliquet)

### Phase 13: Qualité documentaire (docstrings numpydoc + interrogate)

**Goal**: Doc API homogène et mesurée — numpydoc peu profond sans Examples, interrogate ≥ 95 en CI.
**Depends on**: Phase 12
**Requirements**: DOC-01, DOC-02, DOC-03, DOC-04, DOC-05, DOC-06, DOC-07
**Success Criteria** (what must be TRUE):

  1. Docstrings publiques migrées au format numpydoc (Summary + Parameters + Returns + Raises pertinents, sans Examples)
  2. `interrogate` ajouté (dev + config `fail-under=95`) + job CI vert
  3. `napoleon_numpy_docstring` activé dans la conf Sphinx
  4. V2 — exceptions réelles levées (ExtensionNotAvailable/TableNotFound/etc.) au lieu de RuntimeError/ValueError
  5. V1 — `__version__` fixé via `importlib.metadata`
  6. mypy ajouté (dev + config, TY1) ; `async_engine` annoté (TY2)

### Phase 14: Spatial helpers (Phase 8 réalisée)

**Goal**: `db.spatial.*` / `async_db.spatial.*` en parité, sur fondations saines ; coverage maintenu 95.
**Depends on**: Phase 12 (réutilise le pattern builder-pur) ; peut chevaucher Phase 13
**Requirements**: SPA-01, SPA-02, SPA-03, SPA-04, SPA-05, SPA-06
**Success Criteria** (what must be TRUE):

  1. Les 4 points ouverts (`into=`, géométrie input, `unit=`, `where=`) sont tranchés en début de phase → MAJ 08-DESIGN.md
  2. `pycopg/spatial.py` : builders SQL purs + `SpatialAccessor` / `AsyncSpatialAccessor`
  3. ~10 helpers : contains, within, intersects, dwithin, distance, nearest, area, perimeter, centroid, buffer, transform
  4. Garde PostGIS (`has_extension`) + validation identifiants/valeurs `%s` (acquis hotfix v0.3.1 / Phase 10)
  5. `test_parity` couvre l'accessor des 2 côtés ; tests builders (sans DB) + intégration PostGIS

### Phase 15: Release v0.4.0 (PyPI + RTD)

**Goal**: Livrer v0.4.0 sur PyPI + ReadTheDocs.
**Depends on**: Phase 14
**Requirements**: REL-01, REL-02, REL-03, REL-04, REL-05, REL-06
**Success Criteria** (what must be TRUE):

  1. Doc Sphinx à jour : exemples `execute(...)` PostGIS remplacés par les helpers ; api-reference régénérée
  2. Build RTD vert (`.readthedocs.yaml`)
  3. CHANGELOG v0.4.0 ; version bumpée partout ; MIGRATION notes si breaking
  4. Wheel publié sur PyPI via `uv build` + GitHub release → auto-publish ; tag créé
  5. Actions GitHub bumpées Node 20 → Node 24
  6. Audit milestone (gsd-audit-milestone) passé avant archivage

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
| 9. Migration uv (outillage) | v0.4.0 | 4/4 | Complete    | 2026-06-06 |
| 10. Sécurité résiduelle & robustesse | v0.4.0 | 5/5 | Complete    | 2026-06-08 |
| 11. Parité sync/async complète | v0.4.0 | 6/7 | In Progress|  |
| 12. Refactoring (base.py + queries.py) | v0.4.0 | 0/? | Pending (5 req) | — |
| 13. Qualité documentaire (numpydoc + interrogate) | v0.4.0 | 0/? | Pending (7 req) | — |
| 14. Spatial helpers (db.spatial.*) | v0.4.0 | 0/? | Pending (6 req) | — |
| 15. Release v0.4.0 (PyPI + RTD) | v0.4.0 | 0/? | Pending (6 req) | — |
