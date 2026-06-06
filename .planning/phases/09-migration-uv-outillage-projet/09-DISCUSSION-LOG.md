# Phase 9: Migration uv (outillage projet) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-06
**Phase:** 9-migration-uv-outillage-projet
**Areas discussed:** Emplacement des deps dev, CI de tests (création), Surface doc contributeur, Étendue migration publish.yml

> Note préalable : le parser GSD ne détectait aucune phase v0.4.0 (ROADMAP.md n'avait que la checklist, pas les sections `### Phase N:` détaillées requises). Avec l'accord de l'utilisateur, un bloc `## Phase Details` synchronisé depuis `v0.4.0-MILESTONE.md` a été ajouté à ROADMAP.md (commit `5d0a363`), débloquant `init.phase-op` pour les phases 9–15.

---

## Emplacement des deps dev

| Option | Description | Selected |
|--------|-------------|----------|
| Migrer vers [dependency-groups] | PEP 735 `[dependency-groups].dev`, emplacement natif uv ; `uv sync --dev` | ✓ |
| Garder optional-dependencies.dev | Zéro changement pyproject, mais `dev` reste un extra utilisateur-installable (sémantiquement bancal) | |
| Tu décides | Claude tranche (par défaut : migrer) | |

**User's choice:** Migrer vers [dependency-groups]
**Notes:** C'est là que Phase 13 ajoutera interrogate + mypy.

| Option | Description | Selected |
|--------|-------------|----------|
| Suppression nette | Retirer `[project.optional-dependencies].dev`, pas de rétro-compat ; doc contributeur réécrite vers uv sync | ✓ |
| Garder aussi l'extra (dual) | Dupliquer dans les deux endroits (double source de vérité, anti-pattern) | |
| Tu décides | Par défaut suppression nette | |

**User's choice:** Suppression nette
**Notes:** `pip install pycopg[dev]` n'est pas une API publique documentée — cassure invisible pour les utilisateurs.

---

## CI de tests (création)

| Option | Description | Selected |
|--------|-------------|----------|
| Créer tests.yml complet | `uv sync` + service Postgres + `uv run pytest` avec gate `--cov-fail-under=70` | ✓ |
| tests.yml minimal | Un seul Python, Postgres simple sans PostGIS/Timescale | |
| Reporter le CI tests | Phase 9 = build/publish seulement ; TOOL-03 réinterprété comme flux local | |

**User's choice:** Créer tests.yml complet
**Notes:** Aucun workflow de tests n'existe aujourd'hui (seul publish.yml). Donne le filet de sécurité pour les phases 10-14 (parité, refacto).

| Option | Description | Selected |
|--------|-------------|----------|
| timescaledb-ha (PostGIS+TS) | `timescale/timescaledb-ha` — PostGIS ET TimescaleDB en une image, tous les tests sans skip | ✓ |
| postgis/postgis | PostGIS oui, mais pas TimescaleDB (tests Timescale skippés) | |
| Tu décides | Par défaut timescaledb-ha | |

**User's choice:** timescaledb-ha (PostGIS+TS)
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| Matrice 3.11 / 3.12 / 3.13 | Les 3 versions des classifiers, interpréteurs via `uv python install` | ✓ |
| Python 3.12 uniquement | Un seul job (RTD/publish), plus rapide mais incomplet | |
| Tu décides | Par défaut matrice 3 versions | |

**User's choice:** Matrice 3.11 / 3.12 / 3.13
**Notes:** —

---

## Surface doc contributeur

| Option | Description | Selected |
|--------|-------------|----------|
| CLAUDE.md + README Dev + Makefile | Fix CLAUDE.md + section Development README + Makefile (cibles uv) ; pas de CONTRIBUTING.md | ✓ |
| CLAUDE.md + README Dev seulement | Sans Makefile | |
| Tout : + CONTRIBUTING.md | + CONTRIBUTING.md dédié (surface maximale) | |

**User's choice:** CLAUDE.md + README Dev + Makefile
**Notes:** Makefile et CONTRIBUTING.md n'existaient pas sur disque.

| Option | Description | Selected |
|--------|-------------|----------|
| Abandonner venv/, doc .venv | Doc ne référence plus que `uv sync`/`.venv` ; venv/ local non supprimé (gitignoré) | ✓ |
| Supprimer venv/ + doc .venv | Idem + étape explicite de suppression de l'ancien venv/ | |
| Tu décides | Par défaut abandonner la référence sans toucher au répertoire local | |

**User's choice:** Abandonner venv/, doc .venv
**Notes:** —

---

## Étendue migration publish.yml

| Option | Description | Selected |
|--------|-------------|----------|
| astral-sh/setup-uv + uv build | `astral-sh/setup-uv@v6` + `uv build` ; job publish inchangé (trusted publishing) | ✓ |
| Garder setup-python + uv build | setup-python conservé, build via `pip install uv && uv build` (incohérent) | |
| Tu décides | Par défaut setup-uv + uv build | |

**User's choice:** astral-sh/setup-uv + uv build
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| Respecter le report (Phase 15) | Actions récentes pour le code neuf seulement ; pas de bump dédié sur l'existant | ✓ |
| Bumper Node maintenant | Avancer le bump Node 20→24 de Phase 15 | |
| Tu décides | Par défaut respecter le report | |

**User's choice:** Respecter le report (Phase 15)
**Notes:** Évite le scope creep ; le bump est explicitement planifié en Phase 15.

---

## Claude's Discretion

L'utilisateur accorde une autonomie élevée (précédent Phase 1). À ma discrétion :
- Génération initiale et contenu de `uv.lock` (`uv lock`).
- Valeur de `.python-version` (défaut 3.12 pour matcher RTD/publish).
- Section `[tool.uv]` éventuelle dans pyproject.
- Cibles et formulation exactes du `Makefile`.
- Formulation précise des commandes uv dans CLAUDE.md / README.
- Configuration détaillée du service Postgres dans tests.yml (healthcheck, env PG*, création `pycopg_test`, extensions postgis/timescaledb).
- Versions de tags d'actions GitHub pour le code neuf.

## Deferred Ideas

- Bump des actions GitHub Node 20→24 sur les workflows existants — planifié Phase 15 (release).
