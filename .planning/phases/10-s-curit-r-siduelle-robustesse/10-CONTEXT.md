# Phase 10: Sécurité résiduelle & robustesse - Context

**Gathered:** 2026-06-08
**Status:** Ready for planning

<domain>
## Phase Boundary

Fermer les **bugs de correction résiduels** de pycopg (B1, B3, B5 + résidu B2) avec un test rouge→vert dédié pour chacun, **vérifier** que les gaps de validation d'injection et SEC-05 déjà traités par le hotfix v0.3.1 sont effectivement acquis (sans ré-implémenter), et monter le **cliquet coverage de 70 → 80** (jamais redescendant).

Couvre SEC-01 à SEC-06.

**⚠️ Constat de cadrage (scout 2026-06-08) — le périmètre textuel de ROADMAP/REQUIREMENTS est partiellement périmé.** Le hotfix v0.3.1 a fait plus que ce que l'audit pré-hotfix avait anticipé. État réel sur disque :

| Item ROADMAP/REQ | État réel | Action Phase 10 |
|---|---|---|
| Validation identifiants/intervalles (drop_index, spatial index, vacuum/analyze, valid_until, grant/revoke, CSV, compression/retention…) | **Déjà fait** — tous les `validate_*` existent dans `pycopg/utils.py` et sont appelés partout (sync + async). `tests/test_sql_injection.py` couvre **sync ET async** (28 tests). | **Auditer & cocher** comme acquis (D-01). Pas de ré-implémentation. |
| **SEC-05** — async `create_role` valide identifiants up-front | **Déjà fait** — `async create_role` valide `name` (identifier) + `valid_until` (timestamp) ; `async test_valid_until_create_role` existe. | **Vérifier & cocher** acquis (D-01). |
| **SEC-02 / B2** — `session()` masque l'exception | **Déjà corrigé** (`database.py` `try/except: raise` + `finally: _session_conn=None`). | SEC-02 satisfait. **Mais résidu distinct à corriger** (D-02). |
| **SEC-01 / B1** — `PooledDatabase.execute` commit manquant | **Bug réel** — `pool.py:152-158` : `commit()` seulement quand pas de `description` → `INSERT...RETURNING` retourne avant commit → rollback au retour pool. | **Corriger + test** (D-03). |
| **SEC-04 / B5** — `subprocess.os.environ` | **Bug réel** — 3 sites `database.py:2169, 2264, 2283`. | **Corriger + test** (D-04). |
| **SEC-03 / B3** — migrations atomiques | **Gap réel** — `migrations.py:_apply` (232-237) lance UP SQL + INSERT version dans un `cursor()` simple, sans transaction explicite. | **Corriger `_apply` ET `rollback` + test** (D-05). |

**Hors périmètre (verrouillé) :**
- **Pas de refactoring** : brancher `base.py`/`queries.py`, extraire les builders purs = Phase 12. Le comblement coverage de cette phase reste du test, pas de la restructuration.
- **Pas de parité sync/async** (méthodes manquantes côté async) = Phase 11.
- Pas de ré-implémentation des validations/tests d'injection déjà présents (acquis v0.3.1).

</domain>

<decisions>
## Implementation Decisions

### Items « déjà faits » par le hotfix v0.3.1
- **D-01 :** **Vérifier puis cocher comme acquis.** Le researcher/planner audite chaque item du critère de succès n°1 (validations identifiants/intervalles) et SEC-05 contre le code réel. Ceux déjà couverts (validation présente + test présent) sont marqués DONE **sans nouveau code**. On ne ré-implémente rien. Seul le résiduel vrai (B1, B3, B5, résidu B2) reçoit du code neuf. Si l'audit révèle un trou non couvert (méthode listée sans `validate_*` ou sans test), il est comblé.

### Résidu B2 — fuite de connexion dans session()
- **D-02 :** **Corriger le résidu commit/close.** SEC-02 (masquage) est déjà satisfait, mais dans `session()` (`database.py` ~381-394) `commit()` puis `close()` sont dans le même `try` : si `commit()` lève, `close()` est sauté → fuite de connexion. Restructurer le `finally` **sync ET async** pour garantir `close()` même si `commit()` lève, tout en propageant l'exception. Test dédié : commit qui échoue → connexion bien fermée + exception propagée + `_session_conn` remis à None.

### Bugs de correction résiduels (corriger + test rouge→vert chacun)
- **D-03 — B1 :** `PooledDatabase.execute` (`pool.py:152-158`) doit committer même quand `cur.description` est présent (cas `INSERT...RETURNING`) **avant** de retourner les lignes et de rendre la connexion au pool. Vérifier aussi le pendant async (`pool.py:341`). Test : persistance prouvée après retour pool.
- **D-04 — B5 :** Remplacer `subprocess.os.environ` par `os.environ` aux 3 sites (`database.py:2169, 2264, 2283`). Le côté async utilise déjà `os.environ` correctement. Test : l'environnement subprocess est construit sans `AttributeError` / avec le bon merge.
- **D-05 — B3 :** `_apply` (et `rollback`) des migrations s'exécutent dans une **transaction atomique explicite** (REQUIREMENTS SEC-03, critère n°2) : UP SQL + INSERT version atomiques ; rollback DOWN + DELETE version atomiques. Test : migration dont le SQL échoue à mi-course → aucune trace partielle (ni schéma ni ligne de version).

### Tests des correctifs (B1/B2/B3/B5 — pas des injections SQL)
- **D-06 :** **Forme à la discrétion du planner.** Le planner choisit par bug la forme la plus adaptée (intégration vraie DB vs mock ciblé) au moment du plan et documente le choix. Le CI dispose déjà du service `timescale/timescaledb-ha` (Phase 9), donc l'intégration vraie DB est disponible sans skip. Chaque correctif a **son** test, en mode rouge→vert (le test échoue sur le code buggé, passe après fix) — critère de succès n°3.

### Cliquet coverage → 80
- **D-07 :** **Tests des correctifs d'abord, puis comblement ciblé.** Écrire d'abord les tests rouge→vert des bugs. Si le total n'atteint pas 80, le planner identifie les modules les plus faciles/critiques à couvrir (`pool.py`, `migrations.py`, `session()` de `database.py`/`async_database.py`) et y ajoute des tests ciblés. **Pas de refacto** (réservée Phase 12) ni de tests fragiles. Monter `--cov-fail-under` de 70 → **80** dans `pyproject.toml` une fois le seuil réellement atteint (cliquet jamais redescendant).

### Claude's Discretion
Cohérent avec le précédent « autonomie max » de Phase 1. Sans re-solliciter l'utilisateur :
- Forme exacte des tests par bug (D-06).
- Stratégie de comblement coverage pour atteindre 80 proprement (D-07).
- Types/messages d'exception et structuration précise des correctifs.
- Détails de la restructuration `try/finally` de `session()` (D-02).
- Périmètre exact de l'audit « déjà fait » (D-01) — quels appels grep, quel niveau de preuve par item.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Cadrage & exigences (lire en premier)
- `.planning/milestones/v0.4.0-MILESTONE.md` §4 (Phase 10) + §2 (Conventions verrouillées) + §6 (Risques) — spec de la phase (note explicite : v0.3.1 a déjà corrigé les 8 injections + ajouté `tests/test_sql_injection.py`), convention cliquet coverage.
- `.planning/REQUIREMENTS.md` §« Security — residual (Phase 10) » — définitions SEC-01 à SEC-06 et mapping.
- `.planning/AUDIT-2026-06-06.md` — source d'audit du milestone (B1/B2/B3/B5 d'origine, contexte dette sécu).
- `.planning/phases/09-migration-uv-outillage-projet/09-CONTEXT.md` — acquis Phase 9 : CI sous uv avec service `timescale/timescaledb-ha` (PostGIS + TimescaleDB) → tests d'intégration vraie DB disponibles sans skip ; gate coverage actuelle reste 70 jusqu'à cette phase.

### Code à corriger (état actuel sur disque, 2026-06-08)
- `pycopg/pool.py:142-177` (sync `execute`/`execute_many`) + `pycopg/pool.py:341-359` (async) — **B1** : commit avant retour quand `description` présent.
- `pycopg/database.py:2169, 2264, 2283` — **B5** : `subprocess.os.environ` → `os.environ` (le merge `{**subprocess.os.environ, **env}` est le bug).
- `pycopg/migrations.py:220-237` (`_apply`) + `migrations.py:239+` (`rollback`) — **B3** : transaction atomique explicite.
- `pycopg/database.py` `session()` (~381-394) + pendant async `async_database.py` — **résidu B2** : commit/close dans try séparés.
- `pycopg/utils.py:15-260` — helpers de validation (`validate_identifier(s)`, `validate_interval`, `validate_timestamp`, `validate_privileges`, `validate_object_type`, `validate_csv_option`, `validate_index_method`, `quote_literal`) — **déjà existants**, base de l'audit D-01.

### Tests (état actuel)
- `tests/test_sql_injection.py` — **28 tests sync + async déjà présents** (drop_index, spatial, vacuum, analyze, create_extension, valid_until, compression/retention, grant/revoke, CSV, insert_many/upsert_many). Base de l'audit D-01 ; **étendre** avec les tests des correctifs B1/B2/B3/B5 (nouveau fichier dédié ou sections nouvelles, au choix du planner).
- `tests/test_pool.py`, `tests/test_migrations.py`, `tests/test_database.py` — cibles probables du comblement coverage ciblé (D-07).
- `pyproject.toml:88` (`--cov-fail-under=70`) — à monter à **80** une fois le seuil atteint.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`pycopg/utils.py`** : suite complète de `validate_*` déjà branchée partout (sync + async). L'audit D-01 s'appuie dessus — aucune nouvelle fonction de validation attendue, sauf trou avéré.
- **`tests/test_sql_injection.py`** : pattern de test d'injection établi (`pytest.raises(InvalidIdentifier)`, fixtures `sync_db`/`async_db` mockées, `evil` parametrize). Réutilisable pour étendre si un trou de validation est trouvé.
- **CI Phase 9** : service `timescale/timescaledb-ha` → tests d'intégration B1/B3 contre une vraie DB tournent en CI sans skip.

### Established Patterns
- **session() sync ET async** déjà gèrent `TransactionStatus` (INTRANS→commit, INERROR→rollback, IDLE/ACTIVE/UNKNOWN→skip) dans `cursor()`. Le correctif B2 ne touche pas cette logique, seulement le `try/finally` de fermeture de `session()`.
- **subprocess** : le côté async (`async_database.py:1958, 2061, 2088`) utilise déjà `{**os.environ}` correctement → modèle de référence pour le fix B5 sync.
- **Tests = vrai PostgreSQL** (contrainte projet, conftest base `pycopg_test` + env PG*) pour l'intégration ; mocks possibles pour subprocess/commit (B5/B2).

### Integration Points
- `pyproject.toml` `--cov-fail-under` ← monté 70→80 (D-07), une seule ligne.
- Tests des correctifs ← `tests/test_sql_injection.py` (extension) ou nouveau fichier ; consommés par le job CI `tests.yml` (Phase 9).
- Aucun nouveau module ; tous les correctifs sont des éditions ciblées dans `pool.py`, `database.py`, `async_database.py`, `migrations.py`.

</code_context>

<specifics>
## Specific Ideas

- **B3 explicite :** `_apply` ET `rollback` atomiques (pas seulement `_apply`) — verrouillé à la discrétion, conforme critère n°2 + SEC-03.
- **Rouge→vert obligatoire :** chaque test de correctif doit démontrer l'échec sur le code buggé puis le succès après fix (pas seulement un test vert post-fix).
- **Cliquet réellement atteint :** monter la gate à 80 seulement quand le coverage mesuré franchit 80 — ne pas baisser la barre ni geler un seuil non atteint.

</specifics>

<deferred>
## Deferred Ideas

- **Refactoring (`base.py`/`queries.py`, builders purs)** — Phase 12. Le comblement coverage de Phase 10 reste du test pur, sans restructuration.
- **Parité sync/async (méthodes async manquantes : DataFrame, backup, role/privilege complets)** — Phase 11.
- **Concerns robustesse plus larges** repérés au scout mais hors SEC-01..06 (statement_timeout, retry/backoff, streaming résultats, pool adaptatif, SRID inference silencieuse) — backlog / futures phases, non ouverts ici.
- **Logging des fichiers de migration ignorés silencieusement** (`migrations.py` `_get_migrations`) — amélioration distincte de B3, non requise par SEC-03 → backlog.

</deferred>

---

*Phase: 10-s-curit-r-siduelle-robustesse*
*Context gathered: 2026-06-08*
