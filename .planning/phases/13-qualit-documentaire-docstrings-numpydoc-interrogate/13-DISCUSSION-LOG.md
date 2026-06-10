# Phase 13: Qualité documentaire (docstrings numpydoc + interrogate) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-10
**Phase:** 13-qualit-documentaire-docstrings-numpydoc-interrogate
**Areas discussed:** Périmètre exceptions (V2), Compat / breaking changes, Stratégie gate mypy (TY1), Lot docstrings & non-régression

---

## Périmètre exceptions (V2) — scope de conversion

| Option | Description | Selected |
|--------|-------------|----------|
| Ciblé domaine seulement | Convertir uniquement les erreurs métier (extensions → ExtensionNotAvailable, exists/not-found → type domaine) ; laisser les ValueError de mauvais usage d'API et les RuntimeError subprocess | ✓ |
| Tout RuntimeError/ValueError | Convertir les ~42 raises, y compris validation d'argument et échecs subprocess | |
| Minimal — extensions seules | Ne convertir que les 'extension not installed' → ExtensionNotAvailable | |

**User's choice:** Ciblé domaine seulement
**Notes:** Diagnostic codebase : ~14 `RuntimeError("... extension not installed")` (PostGIS/TimescaleDB), `ValueError("Database already exists")` côté domaine ; à laisser : `"Specify either table or sql"`, `"Invalid ON DELETE action"`, `"Already in session mode"`, `"pg_dump/pg_restore/psql failed"` (erreurs de programmeur / subprocess). → D-01.

---

## Périmètre exceptions (V2) — nouveaux types

| Option | Description | Selected |
|--------|-------------|----------|
| Réutiliser l'existant + 1-2 ajouts ciblés | Mapper sur ExtensionNotAvailable/TableNotFound existants ; ajouter un seul DatabaseExists(PycopgError) ; pas de prolifération | ✓ |
| Famille complète AlreadyExists/NotFound | Créer DatabaseExists, DatabaseNotFound, SchemaExists, RoleExists… symétriques | |
| Pas de nouveau type | Se limiter aux types existants, laisser le reste en ValueError | |

**User's choice:** Réutiliser l'existant + 1-2 ajouts ciblés
**Notes:** N'ajouter un type que pour un message domaine récurrent sans équivalent. → D-02.

---

## Compat / breaking changes

| Option | Description | Selected |
|--------|-------------|----------|
| Breaking assumé + doc MIGRATION | Nouveaux types héritent de PycopgError seul ; breaking documenté en CHANGELOG/MIGRATION (Phase 15) ; 0.4.0 pre-1.0 = bon moment | ✓ |
| Double héritage non-breaking | `(PycopgError, RuntimeError)` pour ne pas casser `except RuntimeError/ValueError` | |
| Décider au planning | Laisser planner/researcher trancher selon ce que catch la suite de tests | |

**User's choice:** Breaking assumé + doc MIGRATION
**Notes:** Hiérarchie propre privilégiée. Implique de mettre à jour les `pytest.raises(RuntimeError/ValueError)` existants vers les nouveaux types dans le même plan que la conversion. → D-03, D-04.

---

## Stratégie gate mypy (TY1)

| Option | Description | Selected |
|--------|-------------|----------|
| Progressif, non-bloquant d'abord | mypy dev + config permissive (pas de --strict), corriger TY2 + faciles, job CI non-bloquant ; durcissement → milestone ultérieur | ✓ |
| Strict bloquant d'emblée | mypy --strict sur tout pycopg/, CI bloquant | |
| Ciblé modules sûrs | mypy bloquant limité aux modules bien typés, database/async_database exclus | |

**User's choice:** Progressif, non-bloquant d'abord
**Notes:** Évite de transformer la phase doc en chantier typing (sqlalchemy/psycopg dynamiques). TY2 = annoter `async_engine -> AsyncEngine`. → D-05.

---

## Lot docstrings — découpage

| Option | Description | Selected |
|--------|-------------|----------|
| Par module, plusieurs plans | database.py (~72) et async_database.py (~64) chacun son plan, reste (~38) groupé ; planner décide du nombre | ✓ |
| Un seul gros plan | Tout migrer en un plan (diff énorme, review difficile) | |
| Laisser le planner décider | Ne pas verrouiller le découpage | |

**User's choice:** Par module, plusieurs plans
**Notes:** Commits atomiques par module, diffs reviewables, interrogate vérifie au fur et à mesure. → D-07.

---

## Lot docstrings — garde-fou non-régression

| Option | Description | Selected |
|--------|-------------|----------|
| interrogate ≥95 + Sphinx build sans warning | Double garde-fou : couverture docstrings ET forme numpydoc validée par le build Sphinx | ✓ |
| interrogate ≥95 seul | Couverture seulement ; ne valide pas la forme numpydoc | |
| Ajouter pydocstyle/ruff-D | Validation numérique du style en plus (scope++, bruit sur l'existant) | |

**User's choice:** interrogate ≥95 + Sphinx build sans warning
**Notes:** interrogate ne valide pas la *forme* numpydoc → le build Sphinx warning-free attrape les sections Parameters mal formées / params non documentés. → D-08.

---

## Claude's Discretion

- Nombre exact de plans pour la migration docstrings (orchestration des vagues par le planner, esprit D-07).
- Détail de la config mypy permissive (flags exacts, per-module overrides) dans l'esprit D-05.
- Mécanisme CI précis pour mypy non-bloquant (continue-on-error / job séparé / baseline).
- Garder ou retirer `napoleon_google_docstring` après migration (risque double-parsing à confirmer par le researcher).

## Deferred Ideas

- Durcissement mypy strict (job bloquant sur tout pycopg/) → milestone ultérieur.
- Famille symétrique d'exceptions (DatabaseNotFound, SchemaExists, RoleExists…) → seulement si besoin réel.
- pydocstyle / ruff `D` → écarté cette phase.
- CHANGELOG / notes MIGRATION du breaking exceptions → Phase 15 (REL-03).
- Remplacer `print()` par logging → hors scope, API-03 v2.
