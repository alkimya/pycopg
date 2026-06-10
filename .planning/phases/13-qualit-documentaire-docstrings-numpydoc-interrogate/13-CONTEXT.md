# Phase 13: Qualité documentaire (docstrings numpydoc + interrogate) - Context

**Gathered:** 2026-06-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Rendre la documentation de l'API **homogène et mesurée**, sans changer le comportement runtime au-delà des types d'exceptions :

- Migrer **toutes les docstrings publiques** (~174 sites, 7 modules) du format Google-style actuel (`Args:`/`Returns:`/`Example:`) vers **numpydoc** shallow (Summary / Parameters / Returns / Raises), **sans section Examples** (DOC-06).
- Ajouter `interrogate` (dev + `fail-under=95`) appliqué en CI (DOC-07).
- Activer `napoleon_numpy_docstring` dans la conf Sphinx (DOC-08).
- **V2** — lever de **vrais types d'exceptions domaine** (`ExtensionNotAvailable`, `TableNotFound`, …) au lieu de `RuntimeError`/`ValueError` génériques, **ciblé sur les erreurs métier uniquement** (DOC-09).
- **V1** — résoudre `__version__` via `importlib.metadata.version()` (DOC-10).
- Ajouter `mypy` (dev + config) **progressif/non-bloquant** (DOC-11/TY1) ; annoter `async_engine` (DOC-12/TY2).

**Hors scope :** spatial helpers (Phase 14), release/CHANGELOG/MIGRATION/RTD (Phase 15), durcissement mypy strict (milestone ultérieur), nouvelles capacités API.
</domain>

<decisions>
## Implementation Decisions

### Exceptions V2 (DOC-09)
- **D-01 — Périmètre ciblé domaine uniquement.** Convertir SEULEMENT les erreurs métier vers des types pycopg. Concrètement :
  - les ~14 `RuntimeError("... extension not installed")` (PostGIS, TimescaleDB) → **`ExtensionNotAvailable`** ;
  - les cas `"X already exists"` / `"... not found"` → type domaine (voir D-02).
  - **NE PAS toucher** : les `ValueError` de mauvais usage d'API (`"Specify either table or sql"`, `"... not both"`, `"Invalid ON DELETE action"`), les `RuntimeError("Already in session mode")` (état invalide), et les `RuntimeError("pg_dump/pg_restore/psql ... failed: ...")` (échecs subprocess). Ce sont des erreurs de programmeur ou d'outillage, pas des erreurs métier pycopg — `ValueError`/`RuntimeError` y restent corrects.
  - Rationale : c'est l'esprit littéral de DOC-09 ; un mauvais usage d'API qui lèverait un `PycopgError` brouillerait la distinction « erreur métier » vs « erreur de programmeur ».
- **D-02 — Réutiliser l'existant + 1-2 ajouts ciblés.** Mapper sur les types déjà définis dans `pycopg/exceptions.py` quand ça colle (`ExtensionNotAvailable`, `TableNotFound`). Pour `"Database '{name}' already exists"`, ajouter **un** type `DatabaseExists(PycopgError)`. **Pas de prolifération** : on n'ajoute un nouveau type que si un message domaine récurrent n'a aucun équivalent. Pas de famille symétrique exhaustive AlreadyExists/NotFound (over-engineering pour peu de sites).
- **D-03 — Breaking assumé, héritage propre.** Les types (existants et nouveaux) héritent de **`PycopgError` uniquement** (PAS de double héritage `(PycopgError, RuntimeError)`). Le changement de type est **breaking** pour qui fait `except ValueError/RuntimeError` sur ces sites — assumé et documenté dans CHANGELOG + notes MIGRATION en **Phase 15** (REL-03 existe déjà). 0.4.0 pre-1.0 = bon moment ; hiérarchie d'exceptions propre privilégiée sur la rétro-compat hybride.
- **D-04 — Non-régression tests.** Les tests existants qui asservissent ces sites via `pytest.raises(RuntimeError)` / `pytest.raises(ValueError)` **doivent être mis à jour** vers les nouveaux types dans le même plan que la conversion. À vérifier par grep `pytest.raises` sur les messages concernés avant de committer chaque conversion.

### Stratégie mypy (DOC-11 / TY1)
- **D-05 — Progressif, non-bloquant d'abord.** `mypy` ajouté en dev + **config permissive** (PAS de `--strict`). Corriger **TY2** (`async_engine` → annoté `AsyncEngine`, DOC-12) et les erreurs faciles. Job CI ajouté mais **non-bloquant** (`continue-on-error` ou baseline) pour ne pas faire exploser le scope de la phase doc sur du typing profond (sqlalchemy/psycopg dynamiques, `**kwargs`, retours `dict`). Le **durcissement mypy strict → milestone ultérieur** (noté en Deferred).

### Docstrings numpydoc (DOC-06 / DOC-08)
- **D-06 — Format verrouillé (décision user 2026-06-06).** numpydoc **shallow** : Summary + Parameters + Returns + Raises pertinents. **AUCUNE section Examples** (les exemples vivent dans la doc narrative Sphinx, Phase 15). `napoleon` est déjà actif dans `docs/conf.py` → il suffit d'ajouter `napoleon_numpy_docstring = True` (et désactiver/garder `napoleon_google_docstring` selon ce que le researcher confirme pour éviter le double-parsing).
- **D-07 — Découpage par module, plusieurs plans.** Grouper la migration par module pour des commits atomiques et des diffs reviewables : `database.py` (~72 docstrings) et `async_database.py` (~64) chacun leur plan ; le reste (`base.py`, `config.py`, `utils.py`, `migrations.py`, `pool.py` ; ~38 au total) groupé. **Le planner décide du nombre exact de plans / vagues.** Pas de big-bang (diff de 174 docstrings non-reviewable, échec interrogate en fin = tout reprendre).
- **D-08 — Double garde-fou non-régression.** La migration est validée par : (1) `interrogate ≥ 95` (couverture docstrings) **ET** (2) le **build Sphinx passe sans warning** numpydoc/napoleon (détecte une section Parameters mal formée, un paramètre non documenté, un nom de param qui ne matche pas la signature, etc.). interrogate seul ne valide PAS la *forme* numpydoc — d'où le build Sphinx en complément. **Pas** de `pydocstyle`/ruff-`D` cette phase (trop de violations à trier sur l'existant, scope++).

### Version (DOC-10 / V1)
- **D-09 — `importlib.metadata`.** Remplacer le `__version__ = "0.3.1"` hardcodé dans `pycopg/__init__.py:63` par `importlib.metadata.version("pycopg")` (avec fallback `PackageNotFoundError` pour les installs editable/source non packagées). Source unique de vérité = la version du package installé, alignée avec `pyproject.toml`. Mécanique, pas de gray area.

### Claude's Discretion
- Nombre exact de plans pour la migration docstrings (le planner orchestre les vagues selon D-07).
- Détail de la config mypy permissive (quels flags exacts : `ignore_missing_imports`, `disallow_untyped_defs=false`, per-module overrides) — researcher/planner décident dans l'esprit de D-05.
- Mécanisme CI précis pour rendre mypy non-bloquant (continue-on-error vs job séparé vs baseline `mypy --install-types`).
- Choix de garder ou retirer `napoleon_google_docstring` une fois la migration faite (le researcher confirme s'il y a un risque de double-parsing pendant la transition).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Spec de la phase
- `.planning/REQUIREMENTS.md` §"Documentation Quality (Phase 13)" (lignes 49-57) — définitions DOC-06, DOC-07, DOC-08, DOC-09, DOC-10, DOC-11, DOC-12 ; mapping phase (lignes 144-145).
- `.planning/ROADMAP.md` §"Phase 13: Qualité documentaire" — Goal + 6 critères de succès.
- `.planning/REQUIREMENTS.md` §"Out of Scope" ligne 111 — « Docstring Examples sections : numpydoc kept shallow by decision; examples live in Sphinx narrative docs » (verrouille D-06).

### Conventions verrouillées (décisions user 2026-06-06)
- `.planning/milestones/v0.4.0-MILESTONE.md` — conventions verrouillées : numpydoc shallow sans Examples, cliquet coverage 70→80→90→95 (capé 95), interrogate ≥95 en CI.
- `.planning/PROJECT.md` — décisions clés v0.4.0 (cliquet coverage, doc quality).

### Code & outillage existants
- `pycopg/exceptions.py` — hiérarchie actuelle (`PycopgError`, `ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier`, `ConnectionError`, `ConfigurationError`, `MigrationError`) ; point d'ajout de `DatabaseExists` (D-02).
- `pycopg/__init__.py:63` — `__version__` hardcodé à remplacer (D-09).
- `pycopg/async_database.py:91` — propriété `async_engine` sans annotation de retour (TY2/D-05).
- `docs/conf.py` lignes 21-27 — `extensions` incluant déjà `sphinx.ext.napoleon` ; point d'ajout `napoleon_numpy_docstring` (D-06).
- `pyproject.toml` §`dev` (ligne 63) + `[tool.*]` — point d'ajout des deps `interrogate`/`mypy` et de leurs configs ; `--cov-fail-under=92` déjà en place.
- `.github/workflows/tests.yml` — point d'ajout des jobs `interrogate` / `mypy` (aucun pour l'instant).
- `.planning/codebase/CONVENTIONS.md` §"Comments" / "JSDoc/TSDoc" — atteste le style **Google actuel** (`Args/Returns/Example`) → la cible numpydoc ; type hints PEP 484 / union `str | Path` déjà la norme.

### Acquis des phases précédentes (filet & contraintes)
- `.planning/phases/12-refactoring-brancher-les-abstractions/12-CONTEXT.md` — Phase 12 a explicitement reporté à Phase 13 : numpydoc / interrogate / exceptions réelles V2 / `__version__` importlib / mypy. Socle `DatabaseBase`/`QueryMixin` = source unique des docstrings héritées (migrer une fois sur le socle profite aux deux classes). Discipline cliquet « mesurer puis flipper, jamais geler une gate non atteinte » (D-07 phase 12) — applicable si interrogate/coverage bougent.
- `.planning/phases/10-s-curit-r-siduelle-robustesse/10-CONTEXT.md` — gestion subprocess/PGPASSWORD ; les `RuntimeError("pg_dump failed")` viennent de cette zone (conservés en RuntimeError par D-01).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `pycopg/exceptions.py` : hiérarchie `PycopgError` complète déjà en place — `ExtensionNotAvailable` et `TableNotFound` existent et couvrent la majorité des conversions V2 (D-01/D-02). Seul `DatabaseExists` est à ajouter.
- `sphinx.ext.napoleon` déjà chargé dans `docs/conf.py` — la migration numpydoc se réduit à un flag `napoleon_numpy_docstring = True` côté Sphinx, pas un changement d'extension (D-06).
- Socle `base.py` (`DatabaseBase`, `QueryMixin`, Phase 12) : les docstrings des méthodes hissées y sont définies une seule fois → migrer le socle bénéficie à `Database` ET `AsyncDatabase` (réduit le volume réel sous les 174 bruts).

### Established Patterns
- Style docstring actuel = **Google** (`Args:`/`Returns:`/`Example:`) sur ~174 sites (database 72, async_database 64, utils 10, base 9, pool 9, migrations 7, config 3). Cible numpydoc shallow.
- Type hints PEP 484 modernes déjà partout (`str | Path`, `Optional[T]`, `list[dict]`) — bon terrain pour mypy progressif (D-05) ; `engine` est déjà annoté `-> Engine` (database.py:231), `async_engine` est l'asymétrie à corriger (TY2).
- Exceptions : ~22 `RuntimeError` + ~20 `ValueError` dans database/async_database ; **seul un sous-ensemble métier** est converti (D-01).

### Integration Points
- `pyproject.toml` : nouvelles deps dev (`interrogate`, `mypy`) + sections `[tool.interrogate]` / `[tool.mypy]`.
- `.github/workflows/tests.yml` : nouveaux steps/jobs interrogate (bloquant ≥95) + mypy (non-bloquant, D-05).
- `docs/conf.py` : flag napoleon + le build Sphinx devient un garde-fou de non-régression (D-08) — vérifier qu'il tourne déjà en CI ou l'ajouter.
- `pycopg/__init__.py` : `__version__` (D-09) — attention à ne pas casser l'export `__all__` qui inclut `"__version__"`.

</code_context>

<specifics>
## Specific Ideas

- Les messages d'exception existants sont à **préserver** lors de la conversion de type (ne changer que la classe levée, pas le texte) pour limiter le diff et garder les messages d'aide utilisateur (ex: `"PostGIS extension not installed. Run db.create_extension('postgis')"`).
- Garde-fou Sphinx (D-08) : le build doit être **warning-free** spécifiquement sur les warnings numpydoc/napoleon ; un `-W` (warnings-as-errors) ciblé est une option à évaluer par le researcher.

</specifics>

<deferred>
## Deferred Ideas

- **Durcissement mypy strict** (`--strict`, job bloquant sur tout `pycopg/`) → milestone ultérieur. Cette phase pose seulement les fondations non-bloquantes (D-05).
- **Famille symétrique d'exceptions** (DatabaseNotFound, SchemaExists, RoleExists, …) → seulement si un besoin réel émerge ; D-02 limite aux ajouts prouvés nécessaires.
- **pydocstyle / ruff règles `D`** (validation numérique du style docstring) → écarté cette phase (trop de bruit sur l'existant) ; reconsidérable post-migration.
- **CHANGELOG / notes MIGRATION du breaking exceptions** → **Phase 15** (REL-03), pas ici.
- **Remplacer les `print()` par du logging** (noté dans CONVENTIONS.md §Logging) → hors scope, API-03 v2.

[Aucune dérive de scope pendant la discussion — toutes les pistes hors-phase sont capturées ci-dessus.]

</deferred>

---

*Phase: 13-qualit-documentaire-docstrings-numpydoc-interrogate*
*Context gathered: 2026-06-10*
