# Phase 14: Spatial helpers (Phase 8 réalisée) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-12
**Phase:** 14-spatial-helpers-phase-8-r-alis-e
**Areas discussed:** Type de retour (into=), Expression géométrie en entrée, Unités (unit=), Filtres additionnels (where=)

---

## Type de retour (into=)

### Q1 — Quelles valeurs de into= en phase 1 ?

| Option | Description | Selected |
|--------|-------------|----------|
| rows + gdf | Défaut rows (list[dict] comme execute), gdf réutilise to_geodataframe existant ; query attend le milestone ETL | ✓ |
| rows + gdf + query | Inclure dès maintenant l'objet requête non exécuté | |
| rows seulement | Minimal strict, into= ajouté plus tard | |

**User's choice:** rows + gdf (recommandé)

### Q2 — into="gdf" sur les helpers scalaires (area, perimeter, distance, centroid) ?

| Option | Description | Selected |
|--------|-------------|----------|
| Erreur claire | gdf valide uniquement sur les helpers retournant une géométrie ; ailleurs ValueError explicite | ✓ |
| Inclure la géométrie source | Ajouter la colonne geom au SELECT quand into="gdf" | |
| Tu décides | Discrétion Claude | |

**User's choice:** Erreur claire (recommandé)

### Q3 — Colonnes renvoyées par les helpers de filtrage ?

| Option | Description | Selected |
|--------|-------------|----------|
| SELECT * + columns= optionnel | Défaut SELECT *, param columns=[...] validé par validate_identifiers (pattern _build_select_sql) | ✓ |
| SELECT * seulement | Toujours toutes les colonnes | |
| Tu décides | Discrétion Claude | |

**User's choice:** SELECT * + columns= optionnel (recommandé)

### Q4 — Exposer un accès public au SQL généré sans exécution (debug) ?

| Option | Description | Selected |
|--------|-------------|----------|
| Non — builders suffisent | Builders purs module-level importables ; pas d'API publique dédiée (recouperait into="query" différé) | ✓ |
| Oui, db.spatial.sql(...) | Surface publique dédiée au debug | |
| Tu décides | Discrétion Claude | |

**User's choice:** Non — builders suffisent (recommandé)

---

## Expression géométrie en entrée

### Q1 — Quelles formes d'entrée géométrie en phase 1 ?

| Option | Description | Selected |
|--------|-------------|----------|
| Les 4 | point= / wkt= / geojson= / ref= partout — une seule fonction interne de résolution | ✓ |
| point + wkt seulement | Cas courants seulement | |
| point + wkt + geojson (sans ref) | Sans comparaison entre deux tables | |

**User's choice:** Les 4 (recommandé)

### Q2 — Nom du paramètre de colonne géométrie ?

| Option | Description | Selected |
|--------|-------------|----------|
| geom, défaut "geometry" | Court, idiomatique dans le namespace spatial ; défaut aligné sur geometry_column="geometry" existant | ✓ |
| geometry_column, défaut "geometry" | Strictement cohérent avec to_geodataframe | |
| geom positionnel requis | Comme l'exemple du design | |

**User's choice:** geom, défaut "geometry" (recommandé)

### Q3 — Gestion du SRID des géométries en entrée ?

| Option | Description | Selected |
|--------|-------------|----------|
| srid=4326 par défaut | Cas GPS sans friction ; mauvais défaut → erreur PostGIS SRID mixte, pas de résultat faux silencieux | ✓ |
| srid requis | Force la conscience du CRS à chaque appel | |
| Tu décides | Discrétion Claude | |

**User's choice:** srid=4326 par défaut (recommandé)

### Q4 — Sémantique de ref= dans les helpers mono-table ?

| Option | Description | Selected |
|--------|-------------|----------|
| EXISTS — au moins une | Lignes de la table interrogée matchant au moins une géométrie référencée ; forme de retour uniforme | ✓ |
| Jointure — paires | Renvoie les paires qui matchent | |
| Tu décides | Discrétion Claude | |

**User's choice:** EXISTS — au moins une (recommandé)

---

## Unités (unit=)

### Q1 — Confirmer unit="m" par défaut (cast ::geography) ?

| Option | Description | Selected |
|--------|-------------|----------|
| Oui, "m" par défaut | Mètres partout par défaut, unit="srid" pour les unités natives | ✓ |
| "srid" par défaut | Unités natives — réintroduit le piège des degrés | |
| Pas de unit=, toujours ::geography | Un param de moins mais pénalise les données projetées | |

**User's choice:** Oui, "m" par défaut (recommandé)

### Q2 — Quels helpers exposent unit= ?

| Option | Description | Selected |
|--------|-------------|----------|
| Métriques seulement | dwithin, distance, area, perimeter, buffer | ✓ |
| Tous les helpers | Signature uniforme même quand sans effet | |
| Tu décides | Discrétion Claude | |

**User's choice:** Métriques seulement (recommandé)

---

## Filtres additionnels (where=)

### Q1 — Ajouter un where= optionnel pour combiner critère spatial + attributaire ?

| Option | Description | Selected |
|--------|-------------|----------|
| Oui, comme select() | where: str optionnel, fragment SQL brut combiné en AND — convention _build_select_sql existante | ✓ |
| Strictement spatial en phase 1 | Pas de where=, surface minimale | |
| where= + params attributaires | where="active = %s", where_params=[True] | |

**User's choice:** Oui, comme select() (recommandé)

### Q2 — Les helpers de filtrage prennent-ils aussi order_by= / limit= ?

| Option | Description | Selected |
|--------|-------------|----------|
| Oui, le trio complet | where= + order_by= + limit=, même surface que select() | ✓ |
| where= seulement | Le strict nécessaire du point ouvert n°4 | |
| Tu décides | Discrétion Claude | |

**User's choice:** Oui, le trio complet (recommandé)

---

## Claude's Discretion

- Détail KNN de `nearest` (opérateur `<->` geometry vs geography).
- Validation d'exclusivité mutuelle des formes d'entrée géométrie ; valeurs `unit=`/`into=` invalides.
- SQL exact généré par chaque builder ; signatures/ordre des fonctions builder.
- Stratégie de cache de la garde PostGIS.
- Découpage en plans/vagues, granularité des commits, forme des tests.

## Deferred Ideas

- `into="query"` (objet requête non exécuté, brique ETL) → milestone ETL ultérieur.
- `db.spatial.sql(...)` public (debug) → écarté, absorbable par `into="query"` plus tard.
- `where_params=` (paramétrage des valeurs du fragment where=) → à reconsidérer globalement (toucherait aussi select()).
- Helpers spatiaux supplémentaires (union, simplify, clustering…) → attendre un besoin réel.
