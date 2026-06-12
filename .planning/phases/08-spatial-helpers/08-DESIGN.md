# Phase 8: Spatial Helpers — Design

**Status:** Design validé et réalisé en Phase 14 (D-01..D-12)
**Date:** 2026-05-29 (mis à jour 2026-06-12)
**Domain:** PostGIS spatial query abstraction
**Author:** discussion Loc + Claude (audit "haut niveau / ETL")

> **Réalisation :** ce document capture toute la discussion d'audit. Le cadre,
> les 2 choix structurants et les 4 points de détail sont tous tranchés — voir
> la section "Points tranchés (D-01..D-12)" ; les résolutions complètes sont
> dans `14-CONTEXT.md` (Phase 14). Implémenté dans `pycopg/spatial.py`.

---

## 1. Objectif

Rendre pycopg plus "haut niveau" en **abstrayant le SQL** pour les opérations
courantes, en commençant par **PostGIS / spatial**. But final à plus long
terme : un outil ETL où l'on écrit le moins de SQL possible.

Aujourd'hui, côté lecture/requêtage, l'API se résume à `execute(sql, params)`,
`fetch_one`, `fetch_val`, `to_dataframe`. Pour PostGIS il n'existe **aucune**
fonction `ST_*` : tout passe par du SQL brut dans `execute()`.

Exemple actuel (ce qu'on veut supprimer) :
```python
db.execute("""
    SELECT p.id, p.name FROM parcels p
    WHERE ST_Contains(p.geometry, ST_SetSRID(ST_Point(%s, %s), 4326))
""", [-122.4, 37.8])
```

Cible :
```python
db.spatial.contains("parcels", "geometry", point=(-122.4, 37.8), srid=4326)
```

## 2. Décisions structurantes (VALIDÉES)

| Décision | Choix retenu | Raison |
|----------|--------------|--------|
| Forme d'API | **Helpers métier nommés** (pas de query builder générique, pas de SQLAlchemy) | Aligné avec `PROJECT.md` "Out of Scope" (query builder/ORM/SQLAlchemy exclus) et avec le style existant (`db.grant`, `db.create_index`…) |
| Périmètre de départ | **PostGIS / spatial d'abord** | C'est le trou le plus net de l'API et l'exemple concret de l'utilisateur |
| Organisation | **Namespace accesseur `db.spatial.*`** | Évite de gonfler `Database` (~2300 lignes monolithiques) ; pattern type `df.str` / `df.dt` |

### Cohérence avec PROJECT.md
- `PROJECT.md` liste "Query builder/fluent API" et "ORM" en **Out of Scope** →
  on respecte : ce sont des **fonctions nommées**, pas un builder.
- `PROJECT.md` liste "ETL features (explicitly next milestone)" en **Deferred** →
  ces helpers en sont les **briques de base**.
- **Core value du projet** : parité sync/async obligatoire. L'accesseur doit
  exister en `db.spatial` ET `async_db.spatial`, vérifié par `test_parity.py`.

## 3. Surface d'API (Phase 1 — PostGIS)

Source d'inspiration : la section "Common Spatial Operations" de `docs/postgis.md`
est déjà le catalogue exact des helpers à offrir.

Signature commune (défauts D-06/D-07, paramètres D-01/D-03/D-11/D-12) :
`geom="geometry"`, `srid=4326`, `into="rows"` (ou `"gdf"`), `columns=None`,
`where=None`, `order_by=None`, `limit=None`. `unit="m"` (ou `"srid"`) sur les
helpers métriques uniquement (D-10).

| Méthode | SQL généré (schéma) | Couvre (doc) |
|---------|---------------------|--------------|
| `contains(table, geom="geometry", *, point=/wkt=/geojson=/ref=, srid=4326, into=, columns=, where=, order_by=, limit=)` | `ST_Contains(t.geom, <geom_in>)` ; `ref=` → EXISTS (D-08) | Point in Polygon |
| `within(left_t, left_g, right_t, right_g, ...)` | jointure `ST_Within(a.g, b.g)` (signature dédiée conservée, D-08) | Spatial join |
| `intersects(...)` | `ST_Intersects(...)` (même signature que `contains`) | Intersection |
| `dwithin(table, geom="geometry", *, <geom_in>, distance, unit="m", ...)` | `ST_DWithin(geom::geography, <g>::geography, %s)` (`unit="srid"` sans cast) | Distance Queries |
| `distance(table, geom="geometry", *, <geom_in>, unit="m", ...)` | colonne `ST_Distance(...) AS distance` + `order_by=` | Distance |
| `nearest(table, geom="geometry", *, <geom_in>, k=5, ...)` | KNN `ORDER BY geom::geography <-> <g>::geography LIMIT %s` | (manquant, demandé) |
| `area(table, geom="geometry", *, unit="m", ...)` | `ST_Area(geom::geography) AS area` | Area and Perimeter |
| `perimeter(table, geom="geometry", *, unit="m", ...)` | `ST_Perimeter(geom::geography) AS perimeter` | Area and Perimeter |
| `centroid(table, geom="geometry", ...)` | `ST_X/ST_Y(ST_Centroid(geom))` (scalaire → `into="gdf"` interdit, D-02) | Centroid |
| `buffer(table, geom="geometry", *, distance, unit="m", ...)` | `ST_Buffer(geom::geography, %s)::geometry AS buffer` | Buffer |
| `transform(table, geom="geometry", *, to_srid, ...)` | `ST_Transform(geom, %s) AS geometry_transformed` | Transforming CRS |

~11 fonctions = couverture complète de la section "Common Spatial Operations".
Avec les défauts D-06/D-07, le cas courant s'écrit
`db.spatial.contains("parcels", point=(-122.4, 37.8))` — ni `geom=` ni `srid=`.

## 4. Sécurité (non négociable)

- **Identifiants** (table, colonne, schéma) → `validate_identifier(s)` du module
  `utils.py` existant. Jamais interpolés sans validation.
- **Valeurs** (coordonnées, SRID, distances, WKT, GeoJSON) → toujours `%s`
  paramétrés. Zéro f-string sur une valeur utilisateur.
- `db.spatial` vérifie `has_extension("postgis")` à la première utilisation,
  message d'erreur clair sinon (réutiliser le pattern de `from_geodataframe`).

## 5. Points tranchés (D-01..D-12)

Les 4 points ouverts sont résolus en Phase 14 — décisions complètes dans
`.planning/phases/14-spatial-helpers-phase-8-r-alis-e/14-CONTEXT.md`.

1. **Type de retour** — paramètre `into=` (**TRANCHÉ**) :
   - **D-01** — `into="rows"` (défaut) → `list[dict]` comme `execute` ;
     `into="gdf"` → délègue au `to_geodataframe` existant. `into="query"`
     (objet requête non exécuté) **différé au milestone ETL**.
   - **D-02** — `into="gdf"` sur un helper à résultat scalaire (`area`,
     `perimeter`, `distance`, `centroid`) lève un `ValueError` explicite ;
     valide uniquement sur les helpers retournant une géométrie.
   - **D-03** — `SELECT *` par défaut + `columns: list[str] | None` validé
     par `validate_identifiers` (pattern `_build_select_sql`).
   - **D-04** — pas de `db.spatial.sql(...)` public ; les builders purs
     module-level restent importables pour inspecter le SQL (debug).

2. **Expression d'une géométrie en entrée** (**TRANCHÉ**) :
   - **D-05** — les 4 formes partout : `point=(x, y)` / `wkt="..."` /
     `geojson={...}` / `ref=("table", "geom")`, mutuellement exclusives
     (sinon `ValueError`), une seule fonction interne de résolution, tout
     en `%s`.
   - **D-06** — paramètre colonne géométrie : `geom`, keyword avec défaut
     `"geometry"` (aligné sur `geometry_column="geometry"` existant).
   - **D-07** — `srid=4326` par défaut, surchargeable.
   - **D-08** — `ref=` = sémantique EXISTS (lignes de la table interrogée
     matchant au moins une géométrie de la table référencée) ; `within`
     bi-tables garde sa signature jointure dédiée.

3. **Géographie vs géométrie** — `unit=` (**TRANCHÉ**) :
   - **D-09** — `unit="m"` par défaut (cast `::geography`, mètres) ;
     `unit="srid"` pour les unités natives du SRID.
   - **D-10** — `unit=` exposé sur les helpers métriques seulement :
     `dwithin`, `distance`, `area`, `perimeter`, `buffer`. Pas sur les
     prédicats booléens, `nearest`, `centroid`, `transform`.

4. **Filtres additionnels** (**TRANCHÉ**) :
   - **D-11** — `where: str | None` optionnel = fragment SQL brut (sans
     mot-clé WHERE) combiné `AND (...spatial...) AND (where)` — convention
     `_build_select_sql` existante (`where_params=` différé).
   - **D-12** — trio complet `where=` + `order_by=` + `limit=` sur les
     helpers de filtrage — même surface que `select()`.

## 6. Organisation fichiers (proposée)

- `pycopg/spatial.py`
  - Builders SQL **purs** (fonctions/staticmethods) → testables sans DB.
  - `SpatialAccessor` (sync) + `AsyncSpatialAccessor` partageant les builders.
    Seul l'`execute`/`await execute` diffère (pattern type `QueryMixin` de `base.py`).
- `pycopg/database.py` / `async_database.py`
  - propriété **lazy** `spatial` → instancie l'accesseur, garde PostGIS.
- `tests/test_spatial.py`
  - tests des builders SQL (sans DB) + intégration PostGIS (avec DB).
  - `test_parity.py` couvre automatiquement la présence de l'accesseur des 2 côtés.

## 7. Lien avec l'ETL (vision finale)

Le retour `into="query"` (point 5.1) = objet requête composable → future base des
pipelines `source → transform spatial → sink`. Rien à jeter : les helpers de
phase 1 deviennent les transforms de la couche ETL (milestone ultérieur).

## 8. Plan d'implémentation (à faire dans VS Code)

1. `pycopg/spatial.py` : builders SQL purs + `SpatialAccessor` sync.
2. Propriété `db.spatial` lazy + garde PostGIS dans `Database`.
3. `AsyncSpatialAccessor` + `async_db.spatial` (parité).
4. `tests/test_spatial.py` (builders sans DB + intégration PostGIS).
5. Mettre à jour `docs/postgis.md` : remplacer les exemples `execute(...)` par
   les helpers ; ajouter l'API au `docs/api-reference.md`.
6. Vérifier `test_parity.py` au vert.
7. README : section PostGIS haut niveau.

## 9. Décisions encore ouvertes

Aucune. Toutes les décisions ont été tranchées en Phase 14 (D-01..D-12,
voir `14-CONTEXT.md`) :

- Les 4 points de la section 5 → résolus (section 5 ci-dessus).
- Nom des paramètres → `geom` (défaut `"geometry"`, D-06) et `point=` (D-05).
- `db.spatial.sql(...)` public → écarté (D-04) ; les builders purs
  module-level de `pycopg/spatial.py` couvrent le besoin de debug.
