# Phase 14: Spatial helpers (Phase 8 réalisée) - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Réaliser le design validé de l'ex-Phase 8 : un namespace accesseur **`db.spatial.*` / `async_db.spatial.*`** en parité complète, sur les fondations saines des phases 10-13. Couvre SPAT-01 → SPAT-06 :

- **SPAT-01** — Les 4 points ouverts (`into=`, géométrie input, `unit=`, `where=`) sont **tranchés ci-dessous** (section décisions) → le planner doit prévoir la **MAJ de `08-DESIGN.md`** pour y refléter ces choix (critère de succès n°1 du roadmap).
- **SPAT-02** — `pycopg/spatial.py` : builders SQL **purs module-level** (pattern Phase 12 D-03) + `SpatialAccessor` (sync) + `AsyncSpatialAccessor` partageant les builders ; propriété lazy `spatial` sur `Database`/`AsyncDatabase`.
- **SPAT-03** — ~10 helpers : `contains`, `within`, `intersects`, `dwithin`, `distance`, `nearest`, `area`, `perimeter`, `centroid`, `buffer`, `transform` (catalogue = section "Common Spatial Operations" de `docs/postgis.md`).
- **SPAT-04** — Garde PostGIS via `has_extension("postgis")` → `ExtensionNotAvailable` ; identifiants via `validate_identifier(s)` ; valeurs toujours en `%s` (acquis hotfix v0.3.1 / Phase 10).
- **SPAT-05** — Parité sync/async couverte par `test_parity`.
- **SPAT-06** — Tests builders purs (sans DB) + intégration PostGIS (avec DB) ; coverage maintenu ≥ 95 (cliquet capé, jamais baissé).

**Hors périmètre (verrouillé) :** objet requête non exécuté `into="query"` (brique ETL → milestone ultérieur), query builder générique/SQLAlchemy (Out of Scope PROJECT.md), helpers TimescaleDB additionnels, doc narrative Sphinx/release (Phase 15).

**Forme déjà verrouillée par 08-DESIGN.md (ne pas rediscuter) :** helpers métier nommés (pas de builder fluide), namespace accesseur `db.spatial`, périmètre PostGIS d'abord.

</domain>

<decisions>
## Implementation Decisions

### Point ouvert 1 — Type de retour (`into=`)
- **D-01 — `into="rows"` (défaut) + `into="gdf"` en phase 1.** `rows` → `list[dict]` comme `execute`. `gdf` → réutilise `to_geodataframe` existant (sync `database.py:1498`, async `async_database.py:1964`). `into="query"` (objet requête composable) est **différé au milestone ETL** — pas de design prématuré d'une API sans consommateur.
- **D-02 — `into="gdf"` sur un helper à résultat scalaire = erreur claire.** `area`, `perimeter`, `distance`, `centroid` (ST_X/ST_Y) ne renvoient pas de géométrie → `ValueError` explicite si `into="gdf"`. `gdf` est valide uniquement sur les helpers retournant une géométrie (contains, within, intersects, dwithin, nearest, buffer, transform).
- **D-03 — Colonnes : `SELECT *` par défaut + `columns=` optionnel.** Param `columns: list[str] | None` validé par `validate_identifiers` — même pattern que `_build_select_sql` de `QueryMixin`.
- **D-04 — Pas de `db.spatial.sql(...)` public.** Les builders purs module-level sont importables pour inspecter le SQL (debug) ; une API publique dédiée recouperait `into="query"` différé.

### Point ouvert 2 — Expression géométrie en entrée
- **D-05 — Les 4 formes partout : `point=(x,y)` / `wkt="..."` / `geojson={...}` / `ref=("table","geom")`.** Mécanisme uniforme sur tous les helpers qui prennent une géométrie ; **une seule fonction interne de résolution** (testée une fois) ; tout part en `%s`. Exactement une forme à la fois (mutuellement exclusives, sinon `ValueError` — détail validation à la discrétion de Claude).
- **D-06 — Param colonne géométrie : `geom`, keyword avec défaut `"geometry"`.** Court et idiomatique dans le namespace spatial (`db.spatial.contains("parcels", point=(x,y))` fonctionne tel quel). Le défaut `"geometry"` est aligné sur la convention existante `geometry_column="geometry"` de `to_geodataframe`/`create_spatial_index`.
- **D-07 — `srid=4326` par défaut, surchargeable.** Cas GPS/WGS84 sans friction ; GeoJSON est 4326 par spec ; un mauvais défaut produit une erreur PostGIS de SRID mixte, pas un résultat silencieusement faux.
- **D-08 — `ref=` = sémantique EXISTS.** Dans les helpers mono-table, `ref=("zones","geom")` renvoie les lignes de la table interrogée qui matchent **au moins une** géométrie de la table référencée (sous-requête EXISTS). La forme de retour reste identique aux autres formes d'entrée — uniformité totale du mécanisme. (`within` bi-tables du design garde sa signature jointure dédiée.)

### Point ouvert 3 — Unités (`unit=`)
- **D-09 — `unit="m"` par défaut (cast `::geography`, mètres) ; `unit="srid"` pour les unités natives.** Évite le piège « distance en degrés » sur colonnes 4326 ; `"srid"` sert les données déjà projetées (ex. Lambert-93) et les calculs natifs plus rapides.
- **D-10 — `unit=` exposé sur les helpers métriques seulement :** `dwithin`, `distance`, `area`, `perimeter`, `buffer`. Les prédicats booléens (contains, within, intersects), `nearest` (ordre KNN), `centroid` et `transform` ne l'exposent pas — un `unit=` ignoré suggérerait un comportement inexistant.

### Point ouvert 4 — Filtres additionnels (`where=`)
- **D-11 — `where=` optionnel, convention `select()` existante.** `where: str | None` = fragment SQL brut (sans mot-clé WHERE) combiné en `AND (...spatial...) AND (where)` — exactement la convention de `_build_select_sql` (`base.py:159`). Zéro nouveau concept ; sans ça, toute requête réelle (spatial + attributaire) retombe sur `execute()`.
- **D-12 — Trio complet `where=` + `order_by=` + `limit=`** sur les helpers de filtrage — même surface que `select()`, coût quasi nul car le builder suit le même schéma.

### Claude's Discretion
Cohérent avec « autonomie max » des phases précédentes. Sans re-solliciter l'utilisateur :
- Détail KNN de `nearest` (opérateur `<->` geometry vs geography) — choisir la forme correcte/performante.
- Détail de la validation d'exclusivité mutuelle des formes d'entrée géométrie (D-05) et des valeurs `unit=`/`into=` invalides.
- SQL exact généré par chaque builder (formes `ST_*`, casts, sous-requête EXISTS) et signatures/ordre exact des fonctions builder.
- Stratégie de cache de la garde PostGIS (vérif à la première utilisation, pattern `from_geodataframe`).
- Découpage en plans/vagues et granularité des commits.
- Forme des tests builders DB-free et des tests d'intégration PostGIS (fixtures, tables temporaires).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Design source (lire en premier)
- `.planning/phases/08-spatial-helpers/08-DESIGN.md` — design complet validé : surface d'API (§3, tableau des ~10 helpers + SQL généré), sécurité (§4), organisation fichiers (§6), lien ETL (§7), plan d'implémentation (§8). **À METTRE À JOUR avec les décisions D-01..D-12 (exigé par SPAT-01 / critère de succès n°1).**

### Cadrage & exigences
- `.planning/REQUIREMENTS.md` — définitions SPAT-01 → SPAT-06 (lignes 61-66) et mapping phase (151-156).
- `.planning/ROADMAP.md` §"Phase 14" — Goal + 5 critères de succès.
- `.planning/milestones/v0.4.0-MILESTONE.md` — cadrage milestone + conventions verrouillées (cliquet coverage capé 95, numpydoc shallow).
- `.planning/PROJECT.md` — Out of Scope (query builder/ORM/SQLAlchemy exclus → helpers nommés uniquement) ; ETL = milestone ultérieur ; core value parité sync/async.

### Acquis des phases précédentes (patterns & contraintes)
- `.planning/phases/12-refactoring-brancher-les-abstractions/12-CONTEXT.md` — pattern builder-pur module-level partagé sync/async (D-03/D-04 phase 12) que `spatial.py` doit réutiliser ; discipline cliquet « mesurer puis flipper ».
- `.planning/phases/13-qualit-documentaire-docstrings-numpydoc-interrogate/13-CONTEXT.md` — docstrings numpydoc shallow (sans Examples) obligatoires sur tout nouveau code public ; interrogate ≥ 95 en CI ; garde Sphinx `-W` ; exceptions domaine (`ExtensionNotAvailable`).
- `.planning/phases/10-s-curit-r-siduelle-robustesse/10-CONTEXT.md` — validation identifiants/`%s` non négociable dans tout SQL généré.

### Doc utilisateur (catalogue des helpers)
- `docs/postgis.md` §"Common Spatial Operations" — le catalogue exact des opérations que les ~10 helpers couvrent (la MAJ des exemples eux-mêmes = Phase 15/REL-01).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `pycopg/base.py` — `QueryMixin._build_select_sql` (l.159) : pattern `columns`/`where`/`order_by`/`limit` à imiter (D-03/D-11/D-12) ; les 3 builders module-level de Phase 12 (`build_pg_dump_cmd`…) = modèle structurel pour les builders spatiaux.
- `pycopg/utils.py` — `validate_identifier(s)` (l.47/76) pour table/schema/geom/columns ; tout le reste en `%s`.
- `pycopg/database.py:1498` / `pycopg/async_database.py:1964` — `to_geodataframe(table|sql, geometry_column=...)` : la cible de délégation de `into="gdf"` (la variante `sql=` + `params=` accepte directement le SQL des builders).
- `pycopg/database.py:854` / `pycopg/async_database.py:1055` — `has_extension` pour la garde PostGIS.
- `pycopg/exceptions.py` — `ExtensionNotAvailable` (messages existants type `"PostGIS extension not installed. Run db.create_extension('postgis')"` à imiter).

### Established Patterns
- Accesseur lazy : propriété `spatial` sur `Database`/`AsyncDatabase` instanciant l'accesseur à la première utilisation (pattern type `_engine` lazy existant).
- Builders purs = fonctions module-level avec args explicites, jamais `self`, partagées byte-identique sync/async (Phase 12 D-03) → seul `execute`/`await execute` diffère entre `SpatialAccessor` et `AsyncSpatialAccessor`.
- Async : `run_sync` pour geopandas (acquis Phase 11) — `into="gdf"` async délègue au `to_geodataframe` async existant qui gère déjà ça.
- numpydoc shallow (Summary/Parameters/Returns/Raises, pas d'Examples) sur toute la nouvelle surface publique (Phase 13) ; interrogate ≥ 95 et Sphinx `-W` doivent rester verts.
- Convention `geometry_column="geometry"` existante → le défaut `geom="geometry"` s'y aligne (D-06).

### Integration Points
- `pycopg/database.py` / `pycopg/async_database.py` : propriété lazy `spatial` (+ import de `spatial.py`).
- `pycopg/__init__.py` : exporter les accesseurs si pertinent (a minima les types pour la doc API).
- `tests/test_parity.py` : l'introspection plein-surface doit couvrir `SpatialAccessor` vs `AsyncSpatialAccessor` (SPAT-05) — vérifier que l'accesseur n'échappe pas au scan de parité existant.
- `tests/test_spatial.py` (nouveau) : builders sans DB + intégration PostGIS (la DB locale `pycopg_test` a PostGIS installé ; 3 tests full-suite flaky pré-existants connus — utiliser `-o addopts=""` pour les runs ciblés).
- `pyproject.toml` : `--cov-fail-under=95` déjà en place — le nouveau code doit maintenir la gate (builders purs = carburant coverage).
- `docs/api-reference.md` / Sphinx : la nouvelle API doit apparaître dans la référence (la doc narrative complète = Phase 15).

</code_context>

<specifics>
## Specific Ideas

- Exemple cible canonique (08-DESIGN.md §1) : `db.spatial.contains("parcels", point=(-122.4, 37.8))` remplace le bloc `execute("SELECT ... WHERE ST_Contains(...)")` — avec D-06/D-07, le cas courant ne nécessite ni `geom=` ni `srid=`.
- La résolution géométrie (D-05) est **une seule fonction interne** retournant (fragment SQL, params) — testée exhaustivement une fois, consommée par tous les builders.
- `buffer` retourne `ST_Buffer(geom::geography, %s)::geometry` (cast retour en geometry, design §3) — compatible `into="gdf"`.

</specifics>

<deferred>
## Deferred Ideas

- **`into="query"` (objet requête non exécuté, composable)** → brique de la couche ETL, **milestone ultérieur** (PROJECT.md le liste explicitement en deferred). Les builders purs de cette phase en seront la fondation — rien à jeter.
- **`db.spatial.sql(...)` public (debug)** → écarté (D-04) ; reconsidérable si le besoin émerge, probablement absorbé par `into="query"` à l'ETL.
- **`where_params=` (paramétrage des valeurs du fragment `where=`)** → écarté en phase 1 au profit de la convention `select()` existante ; à reconsidérer si le besoin de valeurs dynamiques sûres dans `where=` se présente (toucherait aussi `select()`).
- **Helpers spatiaux supplémentaires** (union, simplify, clustering…) → hors catalogue phase 1 ; attendre un besoin réel.

</deferred>

---

*Phase: 14-spatial-helpers-phase-8-r-alis-e*
*Context gathered: 2026-06-12*
