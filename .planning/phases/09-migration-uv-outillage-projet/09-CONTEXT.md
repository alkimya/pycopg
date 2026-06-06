# Phase 9: Migration uv (outillage projet) - Context

**Gathered:** 2026-06-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Faire de **uv** l'outil de gestion projet (venv, dépendances, lockfile, build) pour les **contributeurs et la CI**, AVANT toutes les autres phases v0.4.0 — pour que les phases suivantes (sécu, parité, refacto, doc, spatial) tournent déjà sous le nouvel outillage.

Couvre TOOL-01 à TOOL-05 : `uv sync` pour le dev, `uv.lock` + `.python-version` commités, CI sous uv, build via `uv build` (backend hatchling conservé), doc contributeur migrée à uv.

**Hors périmètre (verrouillé) :**
- La doc **utilisateur** garde `pip install pycopg` (depuis PyPI) — seules les commandes **contributeur** passent à uv.
- Build backend reste **hatchling** (pas `uv_build` — jugé trop intrusif).
- **Aucun changement de seuil coverage** dans cette phase : la gate `--cov-fail-under` reste à **70** (le cliquet 70→80→90→95 commence en Phase 10).
- Pas de changement de code source de la lib (`pycopg/*.py`) — phase purement outillage/CI/doc.

</domain>

<decisions>
## Implementation Decisions

### Dépendances de développement (pyproject.toml)
- **D-01 :** Migrer les deps dev (pytest, pytest-cov, pytest-asyncio, black, ruff) de `[project.optional-dependencies].dev` vers **PEP 735 `[dependency-groups].dev`** — l'emplacement natif uv. C'est là que Phase 13 ajoutera `interrogate` et `mypy`.
- **D-02 :** **Suppression nette** de l'extra `[project.optional-dependencies].dev` — pas de double source de vérité, pas de rétro-compat `pip install pycopg[dev]`. C'est une lib jeune sans contributeurs externes connus ; la doc contributeur est réécrite vers `uv sync` de toute façon.
- **D-03 :** Commande contributeur cible = `uv sync --all-extras --dev` (les extras `dotenv`/`geo`/`all` couverts par `--all-extras`, le groupe dev par `--dev`).

### CI de tests (création — n'existe pas aujourd'hui)
- **D-04 :** **Créer** `.github/workflows/tests.yml` (aucun workflow de tests n'existe — seul `publish.yml` est présent). TOOL-03 (« le CI de tests tourne sous uv et passe ») est satisfait par création, pas par remplacement.
- **D-05 :** Service Postgres = image **`timescale/timescaledb-ha`** (PostGIS **ET** TimescaleDB dans une seule image) → tous les tests existants (spatial + hypertable) tournent en CI **sans skip**.
- **D-06 :** Matrice Python **3.11 / 3.12 / 3.13** (les 3 versions des classifiers / `requires-python>=3.11`), interpréteurs installés via `uv python install`.
- **D-07 :** Le job lance `uv sync` puis `uv run pytest` ; la gate coverage reste celle de `pyproject.toml` (`--cov-fail-under=70`).

### Doc contributeur (TOOL-05)
- **D-08 :** Artefacts = **CLAUDE.md + section « Development » du README + `Makefile`**. Pas de `CONTRIBUTING.md` séparé (README suffit pour une lib de cette taille). Makefile/CONTRIBUTING n'existaient pas sur disque.
- **D-09 :** Corriger `CLAUDE.md` : chemin périmé `solaris/pycopg` → `/home/loc/workspace/pycopg` ; remplacer `pip install -e ".[all,dev]"` + activation `venv/` par les commandes `uv` ; bump de la mention version (0.2.0 périmée).
- **D-10 :** `Makefile` avec cibles uv (p. ex. `install`, `test`, `lint`, `format`, `build`) — wrappers fins autour des commandes uv.
- **D-11 :** README : ajouter une section **Development** (commandes uv contributeur) ; la section **Installation** existante garde `pip install pycopg` (utilisateur).
- **D-12 :** La doc ne référence plus que `uv sync` / `.venv/` ; l'ancien `venv/` classique local n'est **pas** supprimé de force par la phase (gitignoré, local au dev). `.gitignore` couvre déjà `venv/` et `.venv/`.

### Migration publish.yml (TOOL-04)
- **D-13 :** Remplacer `setup-python@v5` + `pip install build` + `python -m build` par **`astral-sh/setup-uv@v6`** + **`uv build`** (produit wheel + sdist). uv gère l'interpréteur.
- **D-14 :** Le job `publish` reste **inchangé** : `pypa/gh-action-pypi-publish@release/v1` + trusted publishing PyPI (OIDC) **conservés** (verrouillé). Vérifier que `uv build` produit toujours un wheel + sdist valides (idéalement via un run `workflow_dispatch` avant de dépendre d'un tag — voir risque milestone).
- **D-15 :** **Bump des actions GitHub Node 20→24 différé à Phase 15** (release) — conforme au plan milestone. Phase 9 utilise des versions d'actions récentes pour le **code neuf** (setup-uv@v6, checkout@v4 dans tests.yml) mais ne fait **pas** de passe de bump dédiée sur l'existant.

### Claude's Discretion
L'utilisateur accorde une autonomie élevée sur les détails d'implémentation (précédent Phase 1 « autonomie max »). À ma discrétion, sans re-solliciter :
- Génération initiale de `uv.lock` (`uv lock`) et son contenu exact.
- Valeur de `.python-version` (défaut **3.12** pour matcher RTD/publish, sauf raison contraire).
- Section `[tool.uv]` éventuelle dans pyproject (sources, settings) si utile.
- Cibles et formulation exactes du `Makefile`.
- Formulation précise des commandes uv dans CLAUDE.md / README.
- Détails de configuration du service Postgres dans tests.yml (healthcheck, env PG*, création de `pycopg_test`, activation des extensions postgis/timescaledb).
- Versions de tags d'actions GitHub pour le code neuf.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Cadrage & exigences (lire en premier)
- `.planning/milestones/v0.4.0-MILESTONE.md` §4 (Phase 9) + §2 (Conventions verrouillées) + §6 (Risques) — spec de la phase, conventions uv/hatchling, risque migration CI publish.
- `.planning/REQUIREMENTS.md` §« Tooling — uv (Phase 9) » — définitions TOOL-01 à TOOL-05 et mapping.
- `.planning/AUDIT-2026-06-06.md` — source d'audit du milestone (contexte tooling/dette).

### Fichiers outillage à modifier (état actuel sur disque)
- `pyproject.toml` — backend hatchling, version 0.3.1, `[project.optional-dependencies]` (dotenv/geo/timescale/all/dev), `[tool.ruff]`, `[tool.pytest.ini_options]` (`--cov-fail-under=70`), `[tool.coverage.*]`. **Pas** de `[dependency-groups]` ni `[tool.uv]` actuellement.
- `.github/workflows/publish.yml` — workflow publish actuel (setup-python 3.12 + `pip install build` + `python -m build` + `pypa/gh-action-pypi-publish`). **Seul workflow présent** — il n'y a PAS de workflow de tests à migrer ; il faut le créer.
- `CLAUDE.md` (racine repo) — instructions contributeur avec **chemin périmé** `solaris/pycopg`, `pip install -e`, version 0.2.0 obsolète.
- `README.md` — section « Installation » (utilisateur, garde `pip install`) ; pas de section « Development » à ce jour.
- `.readthedocs.yaml` — build RTD (Python 3.12) ; **non modifié** en Phase 9 mais réf utile (cohérence version Python).
- `tests/conftest.py` — les tests exigent un vrai PostgreSQL (`pycopg_test`, env `PGHOST`/`PGUSER`/`PGPASSWORD`/`PGPORT`) ; dimensionne le service Postgres du CI.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`pyproject.toml` comme source unique** : déjà bien structuré (hatchling, extras, ruff, pytest, coverage). La migration uv s'y branche par ajout de `[dependency-groups]` (+ éventuel `[tool.uv]`) sans réécriture.
- **`publish.yml` existant** : structure build→publish déjà correcte (artifact upload, trusted publishing OIDC). Seul l'étage build change (uv build) ; le pattern reste.
- **`tests/conftest.py`** : fixtures basées sur env PG* + base `pycopg_test` → mappe directement sur un `services.postgres` GitHub Actions avec ces variables d'environnement.

### Established Patterns
- **Python supporté** : classifiers 3.11/3.12/3.13, `requires-python>=3.11` → la matrice CI doit refléter ces 3 versions (D-06).
- **Tests = vrai PostgreSQL** (contrainte projet, pas de mock DB) → le CI a impérativement besoin d'un service Postgres avec PostGIS + TimescaleDB (D-05).
- **`venv/` et `.venv/` déjà gitignorés** → migrer vers `.venv` (uv) ne touche pas `.gitignore`.

### Integration Points
- `pyproject.toml` `[dependency-groups]` ← nouvelle cible des deps dev (D-01) ; consommé par `uv sync --dev` (dev local + jobs CI).
- `.github/workflows/tests.yml` (NOUVEAU) ← `uv sync` + service Postgres + `uv run pytest` ; point d'ancrage du filet CI pour les phases 10-14.
- `.github/workflows/publish.yml` ← `astral-sh/setup-uv` + `uv build` (D-13) ; doit rester compatible avec le trusted publishing existant.
- `uv.lock` + `.python-version` (NOUVEAUX, commités) ← reproductibilité dev + CI (TOOL-02).

</code_context>

<specifics>
## Specific Ideas

- Image CI explicitement souhaitée : **`timescale/timescaledb-ha`** (couvre PostGIS + TimescaleDB en une image).
- Action build explicitement souhaitée : **`astral-sh/setup-uv`** (+ `uv build`).
- Convention de doc : commandes **utilisateur** = `pip install pycopg` ; commandes **contributeur** = `uv` — frontière nette à maintenir dans README/CLAUDE.md.

</specifics>

<deferred>
## Deferred Ideas

- **Bump des actions GitHub Node 20→24** sur les workflows existants — planifié **Phase 15** (release) ; pas dans Phase 9 (D-15).

</deferred>

---

*Phase: 09-migration-uv-outillage-projet*
*Context gathered: 2026-06-06*
