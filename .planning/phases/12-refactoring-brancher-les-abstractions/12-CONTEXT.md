# Phase 12: Refactoring — brancher les abstractions - Context

**Gathered:** 2026-06-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Éliminer la duplication (~48 %) en **branchant les abstractions déjà écrites sur disque mais non utilisées** : `base.py` (`DatabaseBase`, `QueryMixin`) et `queries.py` (constantes SQL). Couvre REF-01 → REF-05 :

- **REF-01** — brancher `queries.py` : remplacer les ~25 SQL inline restants par les constantes (source unique de vérité). `queries` est déjà importé des deux côtés mais à peine utilisé (3 refs `queries.` par fichier).
- **REF-02** — adopter `base.py` : `Database(DatabaseBase, QueryMixin)` + idem async ; remonter `from_env`/`from_url`/`__repr__` au socle (supprimer les doublons concrets) ; utiliser `_build_batch_insert_sql`.
- **REF-03** — extraire des builders **purs sans état** (`_build_role_options`, `_build_pg_dump_cmd`, `_build_pg_restore_cmd`), testables sans DB → carburant coverage.
- **REF-04** — nettoyer le code mort résiduel : `import re` inutilisés, `stdout` non lu, `try/except: raise` no-op, constantes `*_SIMPLE` orphelines, commentaires « Phase 3 » périmés.
- **REF-05** — monter le cliquet coverage à **95** (`--cov-fail-under=95`) une fois réellement atteint.

**Refactor purement interne : zéro changement d'API, de signature publique, ou de forme de retour.** L'extended `test_parity` (Phase 11) + la suite complète sont le filet.

**✅ Cadrage confirmé sur disque (scout 2026-06-09) :**

| Item | État réel sur disque | Action Phase 12 |
|---|---|---|
| REF-01 (queries.py) | `from pycopg import queries` déjà présent (database.py:30, async:29) mais seulement 3 refs `queries.` par fichier ; ~25 SQL encore inline. | Brancher les constantes restantes. |
| REF-02 (base.py) | `base.py` **totalement inutilisé** — classes en `class Database:` / `class AsyncDatabase:` nues, avec leurs propres `from_env`/`from_url`/`__repr__`. | Faire hériter `(DatabaseBase, QueryMixin)`, supprimer les fabriques dupliquées. |
| `*_SIMPLE` constants | `TABLE_INFO_SIMPLE` (queries.py:64) et `LIST_ROLES_SIMPLE` (queries.py:178) : **zéro référence** nulle part (orphelines depuis l'alignement async→sync de Phase 11/PAR-07). | Supprimer (REF-04). |
| Commentaires « Phase 3 » | async_database.py:1891, 1981 (« available in Phase 3 »). | Supprimer (REF-04). |
| Builders purs | `_build_pg_dump_cmd`/`_build_pg_restore_cmd` : logique de cmd-list inline dans pg_dump (database.py:2425+) / pg_restore (2522+), identique sync/async. `_build_role_options` : options de rôle. | Extraire en fonctions module-level dans `base.py`. |

**Hors périmètre (verrouillé) :**
- **Pas de migration docstrings numpydoc / interrogate / exceptions réelles V2 / `__version__` importlib / mypy** = **Phase 13**.
- **Pas de spatial helpers** = **Phase 14** (qui réutilisera le pattern builder-pur de cette phase).
- **Pas de nouvelles capacités, pas de changement de comportement** : on rebranche l'existant, on ne réécrit ni n'ajoute rien.
- **`SessionMixin`** (présent dans `base.py`) : **non adopté** cette phase (voir D-02).

</domain>

<decisions>
## Implementation Decisions

### REF-02 — Adoption de base.py
- **D-01 — Héritage + suppression des fabriques dupliquées.** `class Database(DatabaseBase, QueryMixin)` et idem async. **Supprimer** les `from_env`/`from_url`/`__repr__` concrets de chaque classe — ils sont hérités du socle. `cls(...)` dans les méthodes du socle retourne déjà la bonne sous-classe, donc l'annotation de type se corrige d'elle-même (plus besoin du `-> Database` explicite). **Conserver** le `__init__` propre à chaque classe : il appelle `super().__init__(config)` (qui pose `self.config`) puis pose les attributs spécifiques (`self._engine`/`self._session_conn` sync ; `self._async_engine` etc. async). Dédup maximale, source unique des docstrings sur le socle.
- **D-02 — Brancher `_build_batch_insert_sql`, ignorer `SessionMixin`.** Adopter `QueryMixin` et router la construction du batch-INSERT inline dans `insert_many`/`upsert_many` (sync **et** async) à travers `_build_batch_insert_sql` — c'est le gain REF-02 explicitement nommé dans le milestone. **Laisser `SessionMixin` HORS** des socles cette phase : le code session diverge (sync `_session_conn` vs async), l'unifier est un refactor à part non nommé dans REF-02 et CONCERNS.md flague cette zone comme fragile. `SessionMixin` → noté en Deferred.

### REF-03 — Builders purs
- **D-03 — Fonctions module-level dans `base.py`, partagées sync/async.** Les trois builders (`build_role_options`, `build_pg_dump_cmd`, `build_pg_restore_cmd`) sont des **fonctions module-level** dans `base.py` prenant des **args explicites** (host/port/user/database, format, tables…), **pas `self`**. La construction de cmd étant byte-identique sync vs async, `Database.pg_dump` et `AsyncDatabase.pg_dump` appellent **la même** fonction. Trivialement testables : `import` + appel avec des littéraux + assert sur la liste. Source unique pour le cmd identique.
- **D-04 — Le builder retourne uniquement l'argv ; env + subprocess restent dans la méthode.** `build_pg_dump_cmd`/`build_pg_restore_cmd` retournent **seulement la liste cmd** (la logique pure et branchée — format maps, flags, boucles tables — 100 % couvrable). La construction du dict env `PGPASSWORD` et le `subprocess.run` **restent dans la méthode** (la coquille I/O fine non couvrable). Split pur/impur propre ; **pas de secret à travers le builder pur**.

### REF-01 / REF-04 — Constantes SIMPLE
- **D-05 — Supprimer les `*_SIMPLE` + brancher l'async sur les constantes canoniques.** `TABLE_INFO_SIMPLE` et `LIST_ROLES_SIMPLE` ont **zéro référence** (orphelines depuis que Phase 11/PAR-07 a aligné l'async sur la forme riche du sync). Les supprimer de `queries.py` (REF-04). S'assurer que `table_info`/`list_roles` async utilisent les constantes canoniques pleines `TABLE_INFO`/`LIST_ROLES` (REF-01), produisant la forme de retour post-Phase-11. Net-safe : `test_parity` assert déjà le jeu de champs complet côté async.

### Sécurité du refactor & garde-fou
- **D-06 — Behavior-preserving ; filet = `test_parity` étendu + suite complète.** Zéro changement d'API / forme de retour / comportement — rebranchage purement interne. Le filet est l'**extended `test_parity` existant** (intégration vraie-DB sur les paires touchées + introspection plein-surface) **+ la suite pytest complète**, qui doivent rester verts en continu (lancer après chaque tranche REF-*). Nouveaux tests ajoutés **uniquement** pour les builders purs extraits (le carburant 90→95). **Pas** de tests de caractérisation neufs pour des chemins déjà couverts. Si un test parité/suite passe au rouge = **vraie régression → s'arrêter, ne pas « réparer » le test**.

### REF-05 — Cliquet coverage → 95
- **D-07 — Discipline « mesurer puis flipper » (réutilise Phase 11 D-08).** Faire atterrir builders + branchements d'abord, **mesurer** la coverage réelle, ajouter des tests ciblés sur les builders jusqu'à ce que **≥95 soit réellement franchi**, **puis** flipper `--cov-fail-under` 90→95 dans `pyproject.toml` (cliquet, **jamais geler une gate non atteinte**). REF-04 : supprimer **seulement** les items prouvés morts par grep (zéro réf) — les cibles REF-04 nommées sont toutes vérifiées ; si quelque chose paraît mort mais a une réf non-évidente, le laisser et le noter ; **pas de suppression spéculative**.

### Claude's Discretion
Cohérent avec « autonomie max » (Phase 1, 10, 11). Sans re-solliciter l'utilisateur :
- L'ordre exact des tranches REF-* et leur granularité de commit.
- Quelles ~25 chaînes SQL inline précises brancher et la constante canonique cible pour chacune (REF-01).
- La signature exacte / l'ordre des args des fonctions builder (D-03).
- La forme précise des tests builder DB-free et lesquels écrire pour atteindre 95 (D-04/D-07).
- Le détail du `__init__` post-`super().__init__()` de chaque classe (D-01).
- Quels `import re` / branches `try/except: raise` / `stdout` non lus précis sont supprimables après vérif grep (D-07/REF-04).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Cadrage & exigences (lire en premier)
- `.planning/milestones/v0.4.0-MILESTONE.md` §« Phase 12 — Refactoring » + §« Conventions verrouillées » (cliquet coverage) — spec de la phase.
- `.planning/REQUIREMENTS.md` — définitions REF-01 → REF-05 (lignes 43-47) et mapping phase (139-143).
- `.planning/ROADMAP.md` §« Phase 12 » — 5 critères de succès (R1/R3/R4/code mort/gate 95).
- `.planning/PROJECT.md` — décision clé « v0.4.0: refactor by wiring existing base.py/queries.py » ; cliquet coverage 70→80→90→95 capé à 95.

### Acquis des phases précédentes (filet & contraintes)
- `.planning/phases/11-parit-sync-async-compl-te/11-CONTEXT.md` — Phase 11 a **explicitement reporté tout refactoring à Phase 12** (base.py/queries.py, builders purs, dédup ~48 %) ; alignement async→sync (PAR-07/D-07) qui rend les `*_SIMPLE` orphelines ; `test_parity` étendu = filet de cette phase ; gate coverage actuelle = **90** (mesurée 91.62%).
- `.planning/phases/10-s-curit-r-siduelle-robustesse/10-CONTEXT.md` — `validate_*` branchés partout (à **conserver** dans tout SQL rebranché) ; gestion subprocess/PGPASSWORD sensible.
- `.planning/phases/09-migration-uv-outillage-projet/09-CONTEXT.md` — outillage uv (`uv run pytest`, `uv.lock`, `--cov-fail-under` dans pyproject.toml).

### Maps codebase (contexte refactor)
- `.planning/codebase/CONCERNS.md` — flague la zone session/transaction comme fragile (justifie D-02 SessionMixin différé) ; subprocess PGPASSWORD (justifie D-04).
- `.planning/codebase/CONVENTIONS.md`, `.planning/codebase/STRUCTURE.md` — conventions/structure existantes.

### Code à modifier (état sur disque, 2026-06-09)
- `pycopg/base.py` (194 l) — `DatabaseBase` (from_env/from_url/__repr__/__init__), `QueryMixin` (_build_insert_sql / _build_batch_insert_sql / _build_select_sql), `SessionMixin` (non adopté). Y **ajouter** les 3 fonctions builder module-level (D-03).
- `pycopg/queries.py` (269 l) — constantes SQL ; **supprimer** `TABLE_INFO_SIMPLE` (64), `LIST_ROLES_SIMPLE` (178) (D-05).
- `pycopg/database.py` (~2733 l) — `class Database:` (51) → hériter ; `from_env` (96), `from_url` (112), `__repr__` (2731) à supprimer (D-01) ; cmd inline `pg_dump` (2425+) / `pg_restore` (2522+) → builder (D-03/D-04) ; ~25 SQL inline → constantes (REF-01).
- `pycopg/async_database.py` (~2790 l) — `class AsyncDatabase:` (50) → hériter ; `from_env` (93), `from_url` (105), `__repr__` (2784) à supprimer (D-01) ; `table_info`/`list_roles` → constantes canoniques (D-05) ; commentaires « Phase 3 » (1891, 1981) à supprimer (REF-04) ; cmd inline pg_dump (2344+) → builder partagé.
- `pycopg/utils.py` — `validate_*` existants à conserver dans tout SQL rebranché (ne pas réécrire).
- `tests/test_parity.py` — filet principal (D-06) ; ne pas affaiblir.
- `pyproject.toml` — `--cov-fail-under` 90→95 **après** mesure (D-07).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `base.py::DatabaseBase` — `from_env`/`from_url`/`__repr__`/`__init__(config)` déjà écrits, inutilisés → cible REF-02 (D-01).
- `base.py::QueryMixin` — `_build_insert_sql`, `_build_batch_insert_sql`, `_build_select_sql` (staticmethods purs avec `validate_identifiers`) → home des builders existants ; `_build_batch_insert_sql` à brancher dans insert_many/upsert_many (D-02).
- `queries.py` — déjà importé des deux côtés ; ~25 constantes SQL prêtes, beaucoup non encore référencées (REF-01).
- `utils.py::validate_identifier(s)` — déjà appelé dans les builders QueryMixin ; à préserver.

### Established Patterns
- Style sync : `cursor()`/`fetchall` ; style async : `connect()`/`AsyncConnection`, `run_sync` pour pandas/geopandas (acquis Phase 11) — à respecter, ne pas restructurer.
- Construction de cmd subprocess identique sync/async (pg_dump/pg_restore) → candidat parfait au builder partagé module-level (D-03).
- Cliquet coverage « mesurer puis flipper » (Phase 11 D-08) → réutilisé en D-07.
- « Track known parity exceptions » + `test_parity` plein-surface = filet de refactor (D-06).

### Integration Points
- MRO : `class Database(DatabaseBase, QueryMixin)` — `__init__` concret appelle `super().__init__(config)` puis pose engines ; aucune autre base actuelle, pas de conflit MRO.
- `__init__.py` exporte `Database`/`AsyncDatabase` — l'héritage ne change pas la surface exportée.
- pg_dump/pg_restore (sync + async) consomment le builder partagé ; env+subprocess restent côté méthode (D-04).

</code_context>

<specifics>
## Specific Ideas

- Builders = **fonctions module-level dans base.py** (pas staticmethods, pas free funcs ailleurs) — choix explicite pour la testabilité DB-free maximale (D-03).
- Builder pg_dump/pg_restore retourne **l'argv liste seule** ; le `PGPASSWORD` ne transite jamais par le builder pur (D-04).
- Suppression de `from_env`/`from_url`/`__repr__` concrets (pas seulement « inherit en plus ») — collapse complet sur le socle (D-01).

</specifics>

<deferred>
## Deferred Ideas

- **Adoption de `SessionMixin`** — unifier le code session-mode (sync `_session_conn` vs async) sur le `SessionMixin` du socle. Hors REF-02, zone flaguée fragile par CONCERNS.md. Refactor session à part — candidat futur, pas cette phase. (D-02)
- **Migration docstrings numpydoc / interrogate ≥95 / exceptions réelles V2 / `__version__` importlib / mypy** → **Phase 13** (les docstrings remontées sur le socle en D-01 suivent le style existant, homogénéisation numpydoc = Phase 13).
- **Spatial helpers `db.spatial.*`** → **Phase 14** (réutilise le pattern builder-pur établi ici).
- **Sweep agressif de code mort au-delà des cibles REF-04 nommées** → écarté cette phase (D-07 : suppression seulement des items grep-vérifiés-morts, pas spéculative).

</deferred>

---

*Phase: 12-refactoring-brancher-les-abstractions*
*Context gathered: 2026-06-09*
