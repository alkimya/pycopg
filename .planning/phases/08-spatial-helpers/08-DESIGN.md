# Phase 8: Spatial Helpers — Design

**Status:** Design validated, ready to implement (no code written yet)
**Date:** 2026-05-29
**Domain:** PostGIS spatial query abstraction
**Author:** discussion Loc + Claude (audit "haut niveau / ETL")

> **Reprise dans VS Code :** ce document capture toute la discussion d'audit.
> Le cadre et les 2 choix structurants sont validés. Reste à trancher 4 points
> de détail (section "Points à trancher"), puis implémenter.

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

| Méthode | SQL généré (schéma) | Couvre (doc) |
|---------|---------------------|--------------|
| `contains(table, geom, *, point=/wkt=/geojson=/ref=, srid)` | `ST_Contains(geom, <geom_in>)` | Point in Polygon |
| `within(left_t, left_g, right_t, right_g, ...)` | jointure `ST_Within(a.g, b.g)` | Spatial join |
| `intersects(...)` | `ST_Intersects(...)` | Intersection |
| `dwithin(table, geom, point, meters)` | `ST_DWithin(geom::geography, <pt>::geography, %s)` | Distance Queries |
| `distance(table, geom, point, *, unit="m")` | colonne `ST_Distance(...)` + `ORDER BY` | Distance |
| `nearest(table, geom, point, k=5)` | KNN `ORDER BY geom <-> <pt> LIMIT k` | (manquant, demandé) |
| `area(table, geom)` | `ST_Area(geom::geography)` | Area and Perimeter |
| `perimeter(table, geom)` | `ST_Perimeter(geom::geography)` | Area and Perimeter |
| `centroid(table, geom)` | `ST_X/ST_Y(ST_Centroid(geom))` | Centroid |
| `buffer(table, geom, meters)` | `ST_Buffer(geom::geography, %s)::geometry` | Buffer |
| `transform(table, geom, to_srid)` | `ST_Transform(geom, %s)` | Transforming CRS |

~10 fonctions = couverture complète de la section "Common Spatial Operations".

## 4. Sécurité (non négociable)

- **Identifiants** (table, colonne, schéma) → `validate_identifier(s)` du module
  `utils.py` existant. Jamais interpolés sans validation.
- **Valeurs** (coordonnées, SRID, distances, WKT, GeoJSON) → toujours `%s`
  paramétrés. Zéro f-string sur une valeur utilisateur.
- `db.spatial` vérifie `has_extension("postgis")` à la première utilisation,
  message d'erreur clair sinon (réutiliser le pattern de `from_geodataframe`).

## 5. Points à TRANCHER (défauts proposés)

1. **Type de retour** — paramètre `into=`:
   - `into="rows"` (défaut) → `list[dict]`, comme `execute`.
   - `into="gdf"` → réutilise `to_geodataframe`.
   - (futur ETL) `into="query"` → objet requête non exécuté = brique ETL.

2. **Expression d'une géométrie en entrée** — mécanisme uniforme partout :
   - `point=(x, y)`
   - `wkt="POLYGON((...))"`
   - `geojson={...}`
   - `ref=("autre_table", "geom")` pour comparer deux tables.
   Tout part en `%s`.

3. **Géographie vs géométrie** — `unit=`:
   - `unit="m"` (défaut) → cast `::geography`, distances en mètres.
   - `unit="srid"` → unités natives du SRID.
   Évite le piège "distance en degrés".

4. **Filtres additionnels** — faut-il un `where=`/`extra` optionnel pour
   combiner critère spatial + attributaire (ex: `contains(...) AND active`),
   ou rester strictement spatial en phase 1 ?

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

- Les 4 points de la section 5.
- Nom exact des paramètres (`geom` vs `column`, `point` vs `coords`).
- Faut-il un `db.spatial.sql(...)` qui retourne le SQL sans l'exécuter (debug) ?
