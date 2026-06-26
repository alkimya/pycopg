# Requirements: pycopg v0.10.0 — Durcissement & Performance

**Defined:** 2026-06-25
**Core Value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

> **Milestone framing.** Durcissement interne **avant** le gel 1.0 : assainir la dette, débusquer le nouveau par outillage, monter la couverture, et optimiser les chemins de volume par COPY sous garde-fou de benchmarks. **Non-cassant** (aucun changement d'API public cassant), parité sync/async maintenue, **zéro nouvelle dépendance runtime** (benchmarks en dev-group). Issu du split de la cible v1.0.0 d'origine — voir `.planning/FUTURE-MILESTONES.md`. v1.0.0 (spatial v2 + gel API) suit.

## v1 Requirements

Requirements for the v0.10.0 release. Each maps to exactly one roadmap phase.

### Dette technique (DEBT)

- [x] **DEBT-01**: Les tests flaky par isolation de fixture (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`, le ~2.7% bound-param) passent de façon déterministe en suite complète (`uv run pytest`), sans `-o addopts=""` ni ordre particulier.
- [x] **DEBT-02**: Les 4 erreurs ruff résiduelles (N818/W291/F841/E722) sont corrigées — `uv run ruff check pycopg tests` retourne 0 erreur.
- [x] **DEBT-03**: Les warnings advisory recensés v0.8-0.9 sont soldés ou explicitement clos avec justification : WR-01 garde `time_bucket(` insensible à la casse, WR-03 INTERVAL-literal-vs-`%s`, `%`/`%s` dans le SQL structurel fourni par l'appelant, IN-03 helper `chunk_seq` fragile, et les advisory v0.9 (`test_sequences_async` assertion sur le nom de séquence, `upsert` docstring section `Raises`, duplications `import uuid`/helpers ad-hoc dans les tests async).
- [x] **DEBT-04**: Le code mort de test est retiré — monkeypatches morts du fixture async de `test_sql_injection.py` (WR-02) supprimés.
- [x] **DEBT-05**: `TableNotFound` est cohérent — soit doté d'un site de raise interne réel, soit retiré de `__all__` ; l'incohérence « exportée mais jamais levée » est résolue et documentée.

### Audit outillé (AUDIT)

- [x] **AUDIT-01**: Une passe `gsd-code-review`/audit sur l'ensemble de `pycopg/` produit un rapport classé par sévérité ; chaque finding HIGH/MEDIUM est corrigé ou explicitement déféré avec justification consignée.
- [x] **AUDIT-02**: Un scan de code mort (vulture/coverage) sur `pycopg/` identifie le code non-atteint ; le code mort confirmé est retiré et les faux positifs sont documentés (allowlist).

### Couverture (COV)

- [x] **COV-01**: Le cliquet de couverture passe de 94 à 95% (`--cov-fail-under=95` dans la config pytest), mesuré ≥95% et tenu vert en CI.

### Nyquist (NYQ)

- [x] **NYQ-01**: Les VALIDATION.md des phases 22-24 (restés `draft`/`nyquist_compliant: false`) sont signés-off (`nyquist_compliant: true`, PASSED) ou explicitement clos avec justification — la dette de sign-off Nyquist est soldée.

### Performance (PERF)

- [x] **PERF-01**: `from_dataframe` (sync + async) route les inserts via le protocole COPY au lieu de `df.to_sql(con=engine)`, en préservant le contrat observable (`if_exists` fail/replace/append, `index`, `primary_key`) ; un test démontre le gain de débit sur un volume représentatif.
- [x] **PERF-02**: Le chemin de load ETL (`append`/`replace`) route via COPY et évite la matérialisation `astype(object)` + `to_dict(orient="records")` inutile sur gros frames, sans changer le contrat de `db.etl.run()` (statut/compte/parité).
- [x] **PERF-03**: `insert_batch` hoiste le placeholder de ligne invariant hors de la boucle par ligne (micro-optimisation) ; comportement strictement inchangé, couvert par un test de non-régression.
- [x] **PERF-04**: Une suite de benchmarks reproductible (dev-group, sans nouvelle dépendance runtime) mesure les chemins d'insertion (`insert_batch`, `copy_insert`, `from_dataframe`, ETL load) et sert de garde-fou anti-régression ; protocole documenté (comment lancer, comment lire).
- [x] **PERF-05**: Tout changement de chemin d'insertion (PERF-01/PERF-02) conserve la parité sync/async — vérifiée par les tests de parité existants (`test_parity`/`test_accessor_parity`) et un test de comportement async dédié.

### Release (REL)

- [x] **REL-10**: v0.10.0 publié sur PyPI via OIDC trusted publishing — version bumpée (`pyproject.toml` canonique + `uv.lock` + `docs/conf.py` ; `__version__` reste dynamique via `importlib.metadata`), CHANGELOG `[0.10.0]` (durcissement + perf, gains COPY documentés), 4 gates verts (couverture ≥95%, interrogate 100%, Sphinx `-W`, `-W error::DeprecationWarning`), tag `v0.10.0` + smoke clean-venv confirmant `__version__ == "0.10.0"`.

## v2 Requirements

Deferred to a future release. Tracked but not in this roadmap.

### Performance (PERF, futur)

- **PERF-F01**: COPY binaire (vs textuel) pour `from_dataframe`/copy_insert si le profilage le justifie.
- **PERF-F02**: Vectorisation numpy explicite de la sérialisation de valeurs sur très gros frames (au-delà du gain COPY).
- **PERF-F03**: Dimensionnement dynamique du pool (ARCH-02) — déjà hors scope historique.

### Reporté à v1.0.0 (milestone suivant)

- **Spatial v2** : traitement géométrique (`ST_Union`/`ST_Simplify`/`ST_ConvexHull`/`ST_MakeValid`/`ST_Difference`/`ST_Intersection`), agrégats spatiaux (`ST_Union(agg)`/`ST_Collect`/`ST_Extent`), sérialisation (`ST_AsGeoJSON`/`ST_AsText`/`ST_AsMVT`) ; raster reporté post-1.0.
- **Stabilisation API** : SemVer + politique de dépréciation + gel d'API ; revue de cohérence/homogénéisation ; mypy strict bloquant + typage `py.typed` complété ; items API (named params `:name`, health checks, isolation level + savepoints, structured logging).

## Out of Scope

Explicitly excluded for v0.10.0. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Tout nouvel ajout de surface spatiale | Reporté à v1.0.0 (milestone suivant) — v0.10.0 ne touche pas à la surface publique |
| Gel d'API / politique SemVer | Objet du v1.0.0 ; prématuré tant que durcissement + perf ne sont pas faits |
| mypy strict bloquant | Reporté à v1.0.0 (stabilisation) — hors du durcissement minimal |
| Raster (postgis_raster) | Lourd (GDAL, nouvelle extension) — reporté post-1.0 |
| Réécriture COPY en binaire | Optimisation supplémentaire non requise pour le gain principal (PERF-F01) |
| Nouvelle dépendance runtime | Contrainte projet : benchmarks et outillage d'audit en dev-group uniquement |
| Changement d'API public cassant | Durcissement interne par définition — toute évolution de signature reste additive/compatible |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DEBT-01 | Phase 37 | Complete |
| DEBT-02 | Phase 37 | Complete |
| DEBT-03 | Phase 37 | Partial (D-03a done P04; D-03b deferred P05) |
| DEBT-04 | Phase 37 | Complete |
| DEBT-05 | Phase 37 | Complete |
| AUDIT-01 | Phase 37 | Complete |
| AUDIT-02 | Phase 37 | Complete |
| NYQ-01 | Phase 37 | Complete |
| PERF-01 | Phase 38 | Complete |
| PERF-02 | Phase 38 | Complete |
| PERF-03 | Phase 38 | Complete |
| PERF-05 | Phase 38 | Complete |
| COV-01 | Phase 39 | Complete |
| PERF-04 | Phase 39 | Complete |
| REL-10 | Phase 40 | Complete |

**Coverage:**

- v1 requirements: 15 total
- Mapped to phases: 15 (roadmap complete)
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-25*
*Last updated: 2026-06-25 — traceability filled (roadmap v0.10.0, Phases 37-40)*
