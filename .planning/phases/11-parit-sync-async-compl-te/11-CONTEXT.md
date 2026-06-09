# Phase 11: Parité sync/async complète - Context

**Gathered:** 2026-06-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Restaurer la **valeur cœur du projet** : tout méthode publique de `Database` a un équivalent fonctionnel et testé dans `AsyncDatabase` (et réciproquement). **Zéro méthode divergente non documentée.** Couvre PAR-01 → PAR-09 :

- **PAR-01/02** — implémenter côté **async** les 9 méthodes aujourd'hui sync-only : `add_primary_key`, `add_foreign_key`, `add_unique_constraint`, `truncate_table`, `drop_extension`, `database_exists`, `list_databases`, `create`, `create_from_env`.
- **PAR-03** — implémenter côté **sync** les 4 méthodes aujourd'hui async-only : `insert_many`, `upsert_many`, `stream`, `notify`. (`listen` reste async-only — voir D-06.)
- **PAR-04 (C1)** — async `from_dataframe`/`from_geodataframe` appliquent réellement `primary_key` au lieu de logger un warning et l'ignorer.
- **PAR-05 (C2)** — `AsyncDatabase.close()` dispose l'engine async (n'est plus un no-op).
- **PAR-06 (C3)** — l'engine async utilise le driver `postgresql+psycopg_async://`.
- **PAR-07** — aligner signatures `create_extension(schema)`, `create_schema(owner)` et sémantique `table_info`/`list_roles` entre sync et async.
- **PAR-08** — `test_parity.py` vérifie les **champs de retour + comportement réel**, pas seulement les noms de méthodes/params.
- **PAR-09** — cliquet coverage → **90** (jamais redescendant).

**✅ Cadrage confirmé sur disque (scout 2026-06-09) — contrairement à Phase 10, le texte ROADMAP/REQUIREMENTS est exact ici.** Vérifications :

| Item | État réel sur disque | Action Phase 11 |
|---|---|---|
| PAR-01/02 (9 méthodes async) | **Toutes absentes** d'`async_database.py`, présentes dans `database.py`. | Implémenter côté async. |
| PAR-03 (4 méthodes sync) | `insert_many`/`upsert_many`/`stream`/`notify` présentes dans `async_database.py` (1652/1696/1745/2285), **absentes** de `database.py`. | Implémenter côté sync. |
| C1 (PAR-04) | async `from_dataframe` (1476) & `from_geodataframe` (1568) loggent un warning et ignorent `primary_key` (1514-1518, 1637-1641). | Appliquer réellement via le nouvel `add_primary_key` async. |
| C2 (PAR-05) | `async close()` (2298) = `pass` ; sync `close()` (database.py:2429) dispose `self._engine`. | Disposer l'engine async (voir D-05). |
| C3 (PAR-06) | async_engine (88) fait `create_async_engine(self.config.url)` → `config.url` (config.py:210) renvoie `postgresql+psycopg://` (driver **sync**). | Nouveau `Config.async_url` → `postgresql+psycopg_async://` (voir D-04). |
| PAR-07 | `create_extension` sync a `schema` / async non (706 vs 742) ; `create_schema` sync a `owner` / async non (767 vs 500) ; `table_info`/`list_roles` divergent. | Async adopte la signature sync plus riche (voir D-07). |

**Hors périmètre (verrouillé) :**
- **Pas de refactoring** (`base.py`/`queries.py`, builders purs, dédup ~48 %) = **Phase 12**. Toute écriture neuve de Phase 11 reste de l'implémentation de parité + tests, sans restructuration.
- **Pas de migration docstrings numpydoc / interrogate / exceptions réelles V2 / mypy** = **Phase 13**. Les docstrings des nouvelles méthodes suivent le style **existant** du fichier (homogénéisation au format numpydoc = Phase 13).
- **Pas de spatial helpers** = **Phase 14**.
- **Pas de nouvelles capacités** : on miroite l'API existante, on n'en ajoute pas.

</domain>

<decisions>
## Implementation Decisions

### Implémentation des méthodes manquantes (PAR-01/02/03)
- **D-01 — Miroir mécanique, à la discrétion du planner.** Les 9 méthodes async (PAR-01/02) et 4 méthodes sync (PAR-03) sont des miroirs directs de l'implémentation de l'autre côté. Le planner/exécuteur les implémente sans re-solliciter l'utilisateur, en réutilisant les patterns établis du fichier cible (sync : `cursor()`/`fetchall` ; async : `connect()`/`AsyncConnection`, `run_sync` pour pandas/geopandas). Conserver les `validate_*` déjà branchés des deux côtés (acquis Phase 10). Cohérent avec le précédent « autonomie max » (Phase 1 & 10).
- **D-02 — `create`/`create_from_env` async.** Ces deux constructeurs alternatifs sont aujourd'hui des classmethods sync-only (et listés dans `SYNC_ONLY_METHODS`). PAR-02 demande leur présence async. Le planner implémente les équivalents async (factory connexion + setup), puis **les retire de `SYNC_ONLY_METHODS`** dans `test_parity.py`.

### Tests rouge→vert & test_parity (PAR-08)
- **D-03 — Parité par intégration vraie DB, sur les paires de cette phase uniquement.** `test_parity.py` ajoute des assertions d'**intégration sur la vraie PostgreSQL de test** (deux côtés → résultats identiques) **uniquement pour les paires touchées par cette phase** : les 13 méthodes nouvellement miroitées, C1 (`primary_key` réellement appliqué), et les 4 méthodes alignées PAR-07. Les tests d'introspection existants (noms + listes de params) restent comme garde-fou plein-surface. **Ne pas** ré-asserter toute l'API (overlap inutile avec `test_database.py`/`test_async_database.py`). Le service `timescale/timescaledb-ha` du CI (Phase 9) permet ces tests d'intégration sans skip.

### C3 — driver async (PAR-06)
- **D-04 — Nouvelle propriété `Config.async_url`.** Ajouter `Config.async_url` renvoyant `postgresql+psycopg_async://...` (mêmes auth/host/port/db/sslmode que `url`). `url` (sync, `+psycopg`) reste inchangée. `AsyncDatabase.async_engine` utilise `self.config.async_url`. Avantage : explicite, testable sans DB, pas de logique de transformation dispersée dans `async_database.py`.

### C2 — close() async (PAR-05)
- **D-05 — `async close()` dispose l'engine async.** Reproduire exactement le comportement sync : si `self._async_engine is not None`, `await self._async_engine.dispose()` puis `self._async_engine = None`. None-guard + idempotence à la discrétion du planner ; `__aexit__` appelle déjà `close()`.

### Signatures (PAR-07)
- **D-06 — `listen` reste async-only (exception documentée).** Seuls `notify`/`insert_many`/`upsert_many`/`stream` reçoivent un équivalent sync (PAR-03). `listen` (qui yield un itérateur bloquant sur NOTIFY) n'a **pas** d'équivalent sync : un listener bloquant synchrone est un anti-pattern. Le conserver dans `ASYNC_ONLY_METHODS` de `test_parity.py` avec un commentaire explicite justifiant l'exception (cohérent avec la décision v0.3.0 « track known parity exceptions »).
- **D-07 — L'async adopte la signature sync, plus riche (aucun breaking change sync).** `async create_extension` gagne `schema=None` ; `async create_schema` gagne `owner=None` ; `table_info`/`list_roles` async renvoient les mêmes champs/sémantique que le sync. Le sync est l'API établie et la valeur cœur → l'async rattrape. Aucun paramètre retiré côté sync. Après alignement, retirer ces méthodes de `KNOWN_SIGNATURE_MISMATCHES` dans `test_parity.py`.

### Cliquet coverage → 90 (PAR-09)
- **D-08 — Implémentations + tests d'abord, puis comblement ciblé, puis flip de gate.** Les nouvelles méthodes et leurs tests d'intégration parité apportent une couverture substantielle. Si le total mesuré n'atteint pas 90, le planner ajoute des tests ciblés (pas de refacto — réservée Phase 12, pas de tests fragiles). Monter `--cov-fail-under` 80 → **90** dans `pyproject.toml` **seulement** une fois 90 réellement franchi (cliquet jamais redescendant).

### Claude's Discretion
Cohérent avec « autonomie max » (Phase 1 & 10). Sans re-solliciter l'utilisateur :
- Détails d'implémentation de chaque méthode miroitée (D-01) et des constructeurs async (D-02).
- Forme exacte des assertions de parité par paire (D-03) ; quelles paires précises au-delà du noyau pour atteindre 90.
- None-guard / idempotence de `close()` async (D-05).
- Stratégie de comblement coverage pour atteindre 90 proprement (D-08).
- Mise à jour des allow-lists `test_parity.py` (`SYNC_ONLY_METHODS`, `ASYNC_ONLY_METHODS`, `KNOWN_SIGNATURE_MISMATCHES`) au fil des implémentations.
- Style/contenu des docstrings des nouvelles méthodes : suivre le style **existant** du fichier (la migration numpydoc homogène = Phase 13).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Cadrage & exigences (lire en premier)
- `.planning/milestones/v0.4.0-MILESTONE.md` §« Phase 11 » + §« Conventions verrouillées » (cliquet coverage) — spec de la phase.
- `.planning/REQUIREMENTS.md` — définitions PAR-01 → PAR-09 et mapping phase.
- `.planning/ROADMAP.md` §« Phase 11 » — critères de succès (6 conditions à rendre VRAIES).
- `.planning/phases/10-s-curit-r-siduelle-robustesse/10-CONTEXT.md` — acquis Phase 10 : `validate_*` branchés partout (sync+async), gate coverage actuelle = **80**, CI sous uv avec service `timescale/timescaledb-ha` (intégration vraie DB sans skip).
- `.planning/phases/09-migration-uv-outillage-projet/09-CONTEXT.md` — outillage uv (`uv run pytest`, `uv.lock`).

### Code à modifier (état actuel sur disque, 2026-06-09)
- `pycopg/async_database.py` — ajouter PAR-01/02 (9 méthodes) ; fixer C1 (`from_dataframe` 1476, `from_geodataframe` 1568 — bloc warning 1514-1518/1637-1641) ; C2 (`close()` 2298) ; C3 (`async_engine` 86-89) ; PAR-07 (`create_extension` 742, `create_schema` 500, `table_info` 548, `list_roles` 1012).
- `pycopg/database.py` — ajouter PAR-03 (`insert_many`, `upsert_many`, `stream`, `notify`) ; références signature de vérité PAR-07 (`create_extension` 706, `create_schema` 767, `table_info` 915, `list_roles` 1849) ; `close()` 2429 = modèle pour C2 ; `engine` 256-260 = modèle pour C3.
- `pycopg/config.py` — ajouter `async_url` (modèle : `url` 197-213) pour C3 (D-04).
- `pycopg/utils.py` — `validate_*` existants à réutiliser dans les nouvelles méthodes (ne pas réécrire).

### Tests
- `tests/test_parity.py` — **fichier central de la phase.** Étendre (PAR-08, D-03) : assertions d'intégration vraie DB sur les paires de cette phase ; mettre à jour `SYNC_ONLY_METHODS` (retirer create/create_from_env + les 7 DDL/admin), `ASYNC_ONLY_METHODS` (retirer insert_many/upsert_many/stream/notify ; garder `listen` + commentaire), `KNOWN_SIGNATURE_MISMATCHES` (retirer create_schema/create_extension après alignement).
- `tests/test_database.py` / `tests/test_async_database.py` — ajouter les tests par méthode des nouvelles implémentations (forme à la discrétion du planner).
- `tests/conftest.py` — fixtures `sync_db`/`async_db` + base `pycopg_test` (vraie PostgreSQL, contrainte projet).
- `pyproject.toml` (`--cov-fail-under=80`) — à monter à **90** une fois le seuil atteint (D-08).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Implémentation de l'autre côté** : chaque méthode manquante a déjà son jumeau fonctionnel dans l'autre fichier → miroir direct (sync `add_primary_key` etc. ↔ async ; async `insert_many`/`stream`/`notify` ↔ sync).
- **`pycopg/utils.py`** : suite `validate_*` complète déjà branchée des deux côtés (acquis Phase 10) — réutiliser, ne pas réécrire.
- **`Config.url`** (config.py:197) : modèle exact pour `Config.async_url` (D-04).
- **`Database.close()`** (database.py:2429) : modèle exact pour `AsyncDatabase.close()` (D-05).
- **CI Phase 9** : service `timescale/timescaledb-ha` → tests d'intégration parité tournent sans skip.

### Established Patterns
- **Sync I/O** : `with self.cursor(...) as cur` / `fetchall()` (database.py:440) ; **async I/O** : `async with self.connect() as conn` / `dict_row` / `fetchmany` (async stream 1768) — modèles pour les miroirs.
- **pandas/geopandas en async** : pattern `run_sync` (décision v0.3.0) — pertinent si une méthode miroitée touche un DataFrame.
- **`create_database` async** se reconnecte sur `postgres` via `config.with_database("postgres")` + `autocommit=True` — modèle pour les constructeurs `create`/`create_from_env` async (D-02).
- **Allow-lists `test_parity.py`** : `SYNC_ONLY_METHODS` / `ASYNC_ONLY_METHODS` / `KNOWN_SIGNATURE_MISMATCHES` sont la mémoire des exceptions de parité — les tenir à jour fait partie du livrable.

### Integration Points
- `pyproject.toml` `--cov-fail-under` ← 80→90 (une ligne, D-08).
- `test_parity.py` ← cœur de la vérification PAR-08, consommé par le job CI `tests.yml` (Phase 9).
- Aucun nouveau module sauf `Config.async_url` (propriété, pas de fichier) ; tout le reste = éditions ciblées dans `database.py`, `async_database.py`, `config.py`, `test_parity.py`.

</code_context>

<specifics>
## Specific Ideas

- **C3 explicite** : le bug est que `create_async_engine` reçoit un driver **sync** (`+psycopg`). `Config.async_url` doit renvoyer `+psycopg_async` ; vérifier qu'un test (sans DB) asserte la chaîne produite.
- **C1 dépend de PAR-01** : l'`add_primary_key` async (PAR-01) doit exister AVANT que C1 puisse l'appeler dans `from_dataframe`/`from_geodataframe`. Ordre de plan : PAR-01 → C1.
- **`listen` async-only assumé** : décision explicite (D-06), pas un oubli — documenté dans `ASYNC_ONLY_METHODS`.
- **Cliquet réellement atteint** : monter la gate à 90 seulement quand le coverage mesuré franchit 90 — ne pas geler un seuil non atteint.
- **Aucun breaking change sync** (D-07) : l'alignement de signature se fait toujours en enrichissant l'async, jamais en appauvrissant le sync.

</specifics>

<deferred>
## Deferred Ideas

- **Refactoring (`base.py`/`queries.py`, builders purs, dédup ~48 %)** — Phase 12. Le code neuf de Phase 11 reste de l'implémentation de parité, sans restructuration.
- **Docstrings numpydoc homogènes + interrogate ≥ 95 + exceptions réelles V2 + mypy** — Phase 13. Les nouvelles méthodes suivent le style docstring existant en attendant.
- **Spatial helpers (`db.spatial.*`)** — Phase 14 (4 points ouverts à trancher en début de phase).
- **`listen` sync bloquant** — écarté par design (D-06), pas reporté : un listener synchrone bloquant est un anti-pattern.
- **Concerns robustesse plus larges** (statement_timeout par requête, pool adaptatif, streaming avec backpressure, SRID inference) — backlog / futures milestones, hors parité.

None — discussion stayed within phase scope (the items above are pre-existing phase boundaries, not scope creep raised during discussion).

</deferred>

---

*Phase: 11-parit-sync-async-compl-te*
*Context gathered: 2026-06-09*
