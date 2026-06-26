# Phase 38: Performance COPY - Context

**Gathered:** 2026-06-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Optimiser les **chemins d'insertion à volume** de pycopg via le protocole COPY de PostgreSQL, en gardant le contrat observable et la parité sync/async intacts. Trois cibles :

1. **`from_dataframe`** (sync + async) — router le **chargement des données** via COPY au lieu de `df.to_sql(con=engine)`, tout en préservant `if_exists` (fail/replace/append), `index`, `primary_key` (et `dtype` — voir D-01).
2. **Chemin de load ETL** (`append`/`replace` uniquement) — router via COPY **sur le curseur de la transaction (le seam)** sans matérialiser `astype(object)` + `to_dict(orient="records")` sur les gros frames ; **`upsert` reste sur `INSERT … ON CONFLICT`** (COPY ne supporte pas `ON CONFLICT`).
3. **`insert_batch`** (sync + async) — micro-opt : hoister le placeholder de ligne invariant hors de la boucle par ligne, comportement byte-exact.

**Contraintes absolues (carried forward du milestone v0.10.0) :**
- **Non-cassant** — aucun changement de signature ou de nom d'API publique. Tout changement de chemin d'insertion reste additif/compatible.
- **Zéro nouvelle dépendance runtime** — la suite de benchmarks (PERF-04) ira en dev-group, **en Phase 39**.
- **Parité sync/async obligatoire** (Core Value) — chaque changement miroité dans `AsyncDatabase`/`AsyncETLAccessor`, vérifié par `test_parity`/`test_accessor_parity` + un test de comportement async dédié (PERF-05).
- **Builder-pur** intact — `validate_identifiers` d'abord, valeurs utilisateur jamais interpolées.

**Explicitement hors de cette phase (mappé ailleurs dans v0.10.0) :**
- **COV-01** (cliquet couverture 94→95) → **Phase 39** (le cliquet reste à **94** ici ; ne PAS toucher `--cov-fail-under` dans `pyproject.toml`).
- **PERF-04** (suite de benchmarks reproductible + protocole documenté + mesure de débit sur volume représentatif ~100k lignes) → **Phase 39**.
- **REL-10** (release) → **Phase 40**.
- **COPY binaire** (PERF-F01) — reporté v2 ; COPY **textuel** (défaut psycopg) en Phase 38.
- **Vectorisation numpy explicite** (PERF-F02) — reporté v2 ; le levier ici est l'**I/O COPY**, pas la vectorisation.

</domain>

<decisions>
## Implementation Decisions

### DDL & dtype — `from_dataframe` (PERF-01)
- **D-01 (Hybrid : `to_sql` pour le DDL + COPY pour les données) :** Garder `df.head(0).to_sql(name=table, con=..., schema=schema, if_exists=if_exists, index=index, dtype=dtype)` pour **créer/remplacer la table vide typée** (gère fail/replace/append, `dtype`, `index` gratuitement), puis **streamer les lignes via COPY**. Réutilise **exactement** le pattern déjà présent au [etl.py:1381](pycopg/etl.py#L1381) (chemin ETL replace). Risque minimal ; le contrat `dtype`/`index`/`if_exists`/`primary_key` est préservé **sans réimplémentation**. **Rejeté :** full-COPY avec inférence de types maison (réimplémenter le mapping de types + `dtype` + sémantique `if_exists` = risque élevé, touche le contrat observable). **Note :** `dtype` n'est pas listé dans le contrat préservé de PERF-01 mais le hybrid le conserve de toute façon — ne pas le casser.
- **D-01a (détails mécaniques — researcher/planner confirme) :** `index=True` exige `df.reset_index()` pour que la/les colonne(s) d'index figurent dans le flux COPY (le DDL `head(0).to_sql(index=True)` crée déjà ces colonnes au schéma). `append` vers une table absente continue de créer la table via l'appel DDL `head(0)` (préserve le comportement pandas actuel). `primary_key` post-load via `self.schema.add_primary_key(...)` inchangé (déjà `if_exists != "append"`).

### ETL materialization & seam (PERF-02)
- **D-02 (Streamer les lignes dans COPY, sans copie full-frame) :** Alimenter `cur.copy(...).write_row(...)` **sur le curseur de la transaction (le seam)** au lieu de construire `df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")` ([etl.py:1354](pycopg/etl.py#L1354) sync / [etl.py:2023](pycopg/etl.py#L2023) async). Le NaN/NaT → None se fait **par valeur / via un masque plus léger** plutôt que par un `astype(object)` full-frame. **Le researcher choisit le mécanisme exact de normalisation des nulls** qui préserve la fidélité de type sous COPY (text format). **Rejeté :** garder la construction de lignes en ne changeant que `_build_insert_sql`→COPY (laisse l'essentiel du coût de matérialisation en place — trop faible face à PERF-02).
- **D-02a (préserver le seam — verrou architectural, pas un choix) :** Le COPY tourne **inline** dans `with self._db.session(): with self._db.transaction() as conn: with conn.cursor() as cur:` ([etl.py:1415](pycopg/etl.py#L1415)). **Ne JAMAIS** appeler la méthode publique `copy_insert` ici (elle ouvre sa propre connexion + commit → casse l'atomicité + l'isolation du run-log). Mirror identique dans l'async ETL.
- **D-02b (correctness — researcher préserve) :** La détection « vide » passe de `if not rows:` à `df.empty`/`len(df)` ; les colonnes passent de `rows[0].keys()` à `df.columns`. Le comportement exact « 0 lignes → success, `rows_loaded=0`, **pas d'avance de watermark** » reste identique. `rows_loaded += cur.rowcount` après COPY fonctionne toujours (psycopg pose `cur.rowcount` au nombre de lignes copiées). Le calcul du watermark (sur le **batch brut avant transforms**) est déjà séparé en amont — ne pas y toucher.
- **D-02c (portée stricte) :** **Seuls `append` et `replace`** routent via COPY. **`upsert` reste sur `INSERT … ON CONFLICT`** via `_build_upsert_sql` (COPY ne supporte pas `ON CONFLICT`).

### Connection & atomicity — `from_dataframe`
- **D-03 (Propre connexion — préserve le comportement actuel) :** Le COPY de `from_dataframe` acquiert `self.connect()` (sync) / `async with self.connect()` (async), **exactement comme `copy_insert`**. `from_dataframe` utilise aujourd'hui `df.to_sql(con=self.engine)` — une connexion **du pool SQLAlchemy**, donc il **ne participe déjà pas** à un `db.session()`/`db.transaction()` pycopg actif. Router via `self.connect()` **conserve cette même isolation** → **zéro régression de comportement, non-cassant**. **Rejeté :** rendre `from_dataframe` session-aware = changement de comportement + tire en avant le finding **37-REVIEW WR-03** (`copy_insert` session bypass), explicitement **reporté à v1.0.0**.
- **D-04 (Accepter + documenter le deux-temps) :** Pour `if_exists="replace"`, le DDL (`to_sql`) **commit sur l'engine**, puis le COPY charge sur une connexion psycopg séparée. Si le COPY échoue, la table est **remplacée-mais-vide**. C'est accepté : `replace` signifie déjà « détruire et reconstruire », et `from_dataframe` n'a jamais été atomique au travers de la frontière engine de façon visible par l'appelant. **Documenter** ce contrat (DDL commit avant le load ; échec COPY ⇒ table existe mais vide). **Rejeté :** DDL+COPY atomiques dans une seule transaction psycopg (bridging cross-driver, plus de code et de risque — hors esprit du milestone).

### insert_batch micro-opt (PERF-03)
- **D-05 (verrouillé par l'exigence — pas un point gris) :** Hoister `row_placeholders = ", ".join(["%s"] * len(columns))` **hors de la boucle par ligne** ([database.py:983](pycopg/database.py#L983), invariant à travers les lignes), miroir async ([async_database.py:568](pycopg/async_database.py#L568)). **Comportement strictement byte-exact** — couvert par un test de non-régression. Aucune décision additionnelle requise.

### Verification scope (Phase 38 vs Phase 39)
- **D-06 (Comportement + assert-COPY-utilisé en Phase 38 ; débit → Phase 39) :** Les tests Phase 38 vérifient (a) le **contrat préservé** (`if_exists`/`index`/`primary_key` pour `from_dataframe` ; statut/compte/parité pour `db.etl.run()`) et (b) que **COPY est réellement le chemin emprunté** (spy/mock que `cur.copy` est invoqué et que `to_sql` n'est **pas** utilisé pour l'écriture des données). La **mesure de débit** sur volume représentatif (~100k lignes) appartient à la **suite de benchmarks reproductible de Phase 39 (PERF-04)**. Résout la tension de formulation ROADMAP (« comportement observable ») vs REQUIREMENTS PERF-01 (« gain de débit ») et **évite les assertions basées sur le timing** (flakiness — la Phase 37 vient justement de dé-flaker la suite). **Rejeté :** test de débit timing-based en Phase 38.

### Claude's Discretion
- **Mécanisme exact de normalisation NaN/NaT → None** sous COPY (D-02) — researcher tranche, en préservant la fidélité de type. Lean : masque/itération léger, pas `astype(object)` full-frame.
- **Forme du helper COPY partagé** (D-01/D-02) — un helper privé COPY-streaming paramétré par curseur, réutilisable par `from_dataframe` (sur sa propre connexion) **et** par le seam ETL (sur le curseur de transaction), serait conforme au DRY + builder-pur. Le **planner** décide d'extraire ou non ce helper vs implémentations locales ; contrainte : il doit pouvoir opérer sur un curseur fourni (pour respecter le seam) sans ouvrir sa propre connexion.
- **Site exact du spy/assert-COPY-used** (D-06) — researcher/planner choisit (mock de `cur.copy`, ou assertion d'absence d'appel `to_sql` data).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Périmètre & exigences
- `.planning/REQUIREMENTS.md` — PERF-01, PERF-02, PERF-03, PERF-05 (le périmètre exact de Phase 38) + la table **Out of Scope** (non-cassant, zéro dep runtime, pas de COPY binaire, pas de vectorisation numpy) ; PERF-04 + COV-01 = **Phase 39**.
- `.planning/ROADMAP.md` §"Phase 38: Performance COPY" — goal + **4 critères de succès** (la source d'autorité du « DONE »). Note la formulation « un test vérifie le comportement observable » (vs PERF-01 « gain de débit ») → tranchée par **D-06**.
- `.planning/PROJECT.md` §"Current Milestone: v0.10.0" + §"Known tech debt" — contexte du levier COPY (I/O 10-50×, éviter `astype(object)`/`to_dict`) ; **37-REVIEW WR-03** (`copy_insert` session bypass, reporté v1.0.0) pertinent pour **D-03**.
- `.planning/STATE.md` §Blockers/Concerns — **note `PGDATABASE=pycopg_test2`** (le défaut `pycopg_test` est cassé depuis 2026-06-24) ; 3 env-failures PostGIS connus (non régressions).

### Sites de code (cibles)
- `pycopg/database.py` — `from_dataframe` ([L1204](pycopg/database.py#L1204), `df.to_sql` à [L1234](pycopg/database.py#L1234)) ; `insert_batch` ([L925](pycopg/database.py#L925), placeholder invariant à [L983](pycopg/database.py#L983)) ; `copy_insert` ([L995](pycopg/database.py#L995)) — **patron COPY de référence** (`cur.copy(f"COPY {schema}.{table} ({cols_str}) FROM STDIN")` + `write_row`).
- `pycopg/async_database.py` — `from_dataframe` async ([L967](pycopg/async_database.py#L967), `run_sync`+`to_sql` à [L997](pycopg/async_database.py#L997)) ; `insert_batch` async ([L568](pycopg/async_database.py#L568)) ; `copy_insert` async ([L636](pycopg/async_database.py#L636), `async with cur.copy(...)`).
- `pycopg/etl.py` — **chemin de load sync** : matérialisation à [L1354](pycopg/etl.py#L1354), création table vide replace à [L1381](pycopg/etl.py#L1381) (**le précédent `head(0).to_sql`**), build SQL à [L1391](pycopg/etl.py#L1391), **le seam atomique** à [L1415](pycopg/etl.py#L1415) ; **chemin async** miroir : matérialisation à [L2023](pycopg/etl.py#L2023). `_build_insert_sql`/`_build_upsert_sql` = builders purs à ne pas court-circuiter.

### Cartes de codebase
- `.planning/codebase/CONVENTIONS.md`, `TESTING.md` — patterns (builder-pur, parité, fixtures DB réelles, cliquet couverture à 94 — **tenu à 94 en Phase 38**).
- `.planning/phases/37-dette-audit/37-DECISIONS.md` — §2 disposition de **37-REVIEW WR-03** (`copy_insert` session bypass déféré v1.0.0) — cohérence avec **D-03**.
- ⚠ `.planning/codebase/CONCERNS.md` daté 2026-02-11, largement périmé — lire avec prudence.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`copy_insert` (sync + async)** — patron COPY déjà en place (`cur.copy("COPY … FROM STDIN") as copy` + `copy.write_row([row.get(col) for col in columns])`). Source de vérité pour la mécanique COPY de `from_dataframe`/ETL.
- **`df.head(0).to_sql(if_exists="replace")` au [etl.py:1381](pycopg/etl.py#L1381)** — précédent in-repo exact pour le DDL Hybrid (D-01). À répliquer pour `from_dataframe`.
- **Le seam ETL** `with session(): with transaction() as conn: with conn.cursor() as cur:` ([etl.py:1415](pycopg/etl.py#L1415)) — point d'insertion du COPY ETL (D-02a). Le commentaire de code y interdit déjà explicitement les méthodes batch publiques.
- **Builders purs** `_build_insert_sql` / `_build_upsert_sql` ([etl.py:1391](pycopg/etl.py#L1391)) — `upsert` continue de les utiliser (D-02c) ; `append`/`replace` passent à COPY.

### Established Patterns
- **Builder-pur + `validate_identifiers` d'abord** — tout chemin COPY valide table/schema/colonnes avant exécution (déjà fait dans `copy_insert`/`insert_batch`).
- **Parité sync/async** vérifiée par `test_parity`/`test_accessor_parity` — chaque changement de routage doit rester symétrique ; un test de comportement async dédié (PERF-05).
- **Cliquet de couverture à 94** (`--cov-fail-under=94`) — **tenu à 94 ici** ; montée à 95 = Phase 39.
- **Tests DB réels** sur `pycopg_test2` (le défaut `pycopg_test` est cassé) — pour valider le comportement observable COPY.

### Integration Points
- `from_dataframe` → DDL via `self.engine`/`async_engine` (SQLAlchemy, hors session pycopg) **puis** COPY via `self.connect()` (psycopg) — deux connexions distinctes, D-03/D-04.
- ETL load → COPY **inline sur le curseur de transaction** (jamais via `copy_insert`) — D-02a.
- Helper COPY-streaming partagé éventuel paramétré par curseur — choix planner (Claude's Discretion).

</code_context>

<specifics>
## Specific Ideas

- **Tension non-cassant ↔ perf** : le levier est l'**I/O COPY**, pas la vectorisation numpy ni le COPY binaire (tous deux reportés v2). Le contrat public ne bouge pas.
- **`dtype` conservé « gratuitement »** par le Hybrid bien qu'absent de la liste de contrat préservé de PERF-01 — ne pas le casser.
- **Pas de test de timing en Phase 38** — assertion « COPY réellement utilisé » + contrat préservé ; le débit chiffré est la suite de benchmarks Phase 39 (PERF-04). Évite de ré-introduire la flakiness que la Phase 37 vient de solder.
- **Atomicité `replace` deux-temps acceptée et documentée** — DDL commit avant load ; échec COPY ⇒ table vide.

</specifics>

<deferred>
## Deferred Ideas

- **PERF-04** (suite de benchmarks reproductible, protocole documenté, mesure ~100k lignes) → **Phase 39**.
- **COV-01** (cliquet couverture 94→95) → **Phase 39** (ne PAS toucher `--cov-fail-under` ici).
- **REL-10** (release v0.10.0) → **Phase 40**.
- **COPY binaire** (PERF-F01) et **vectorisation numpy explicite** (PERF-F02) → **v2** (REQUIREMENTS §v2).
- **`from_dataframe` session-aware** / durcissement **WR-03** (`copy_insert` session bypass) → **v1.0.0** (gel d'API, déjà déféré en Phase 37).
- **DDL+COPY atomiques en une transaction** pour `from_dataframe replace` → écarté pour ce milestone (D-04) ; reconsidérable si une exigence d'intégrité émerge.

</deferred>

---

*Phase: 38-performance-copy*
*Context gathered: 2026-06-26*
