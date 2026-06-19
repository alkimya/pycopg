# pycopg — Vision des milestones futurs

> **Statut : vision / backlog de milestones.** Carte de route au-delà du milestone courant.
> Le contenu de chaque milestone se confirme à son `/gsd-new-milestone`, mais **l'ORDRE est
> validé** (utilisateur, 2026-06-15) : réorg → ETL incrémental → TimescaleDB avancé → CRUD →
> spatial v2/1.0. L'arbitrage v0.7.0↔v0.8.0 est tranché : **ETL incrémental AVANT TimescaleDB**
> (déjà à moitié préparé via la colonne watermark). Rédigé le 2026-06-15 après la clôture de v0.5.0 ;
> mis à jour le 2026-06-19 après la clôture de v0.6.0 (réorg livrée → **prochain = v0.7.0**).

## Principe directeur

**Assainir avant d'étendre.** La réorganisation (v0.6.0) vient en premier pour que tous les
ajouts futurs se posent sur une surface propre (`db.timescale.*`, `db.schema.*`, …) au lieu
d'épaissir la classe `Database` monolithique. Ensuite, **une famille de features par milestone**,
courts (4-6 phases), sur le pattern builder-pur + accessor déjà éprouvé (spatial, etl).

## Séquence recommandée

### v0.6.0 — Réorganisation en accessors  *(✅ shippé 2026-06-19)*
Regrouper l'existant sous `db.timescale/admin/schema/maint/backup.*` avec alias + DeprecationWarning.
Détail complet : voir `.planning/milestones/v0.6.0-ROADMAP.md`. Livré sur PyPI ; 56 alias dépréciés
(suppression planifiée v0.7.0).

### v0.7.0 — Suppression des alias + ETL incrémental  *(prochain à lancer)*
Deux choses qui vont bien ensemble :
- **Retirer les alias dépréciés** introduits en v0.6.0 (un cycle de dépréciation = une version).
- **ETL incrémental / CDC watermarks** : `db.etl.run()` ne recharge que le nouveau, via la colonne
  `pipeline_runs.watermark JSONB` déjà réservée en v0.5.0 (toujours NULL aujourd'hui → ajout
  additif, pas de migration cassante). Suite naturelle de v0.5.0, à moitié préparée.

### v0.8.0 — TimescaleDB avancé  *(candidat)*
Les fonctionnalités phares time-series qui manquent au socle actuel : **continuous aggregates**,
`time_bucket` / `time_bucket_gapfill`, `show_chunks` / `drop_chunks`, `add_dimension`,
`reorder_policy`. Se pose proprement dans `db.timescale.*` créé en v0.6.0.

### v0.9.0 — CRUD ergonomique + introspection enrichie  *(candidat)*
Confort utilisateur additif : `upsert` (singulier), `delete_where`, `update_where`, `exists`,
`count`, `paginate`, fetch en dict ; introspection : `primary_key()`, `foreign_keys()`,
`sequences()`, `views()`, `describe()`. Faible risque, pur confort au-dessus de l'API.

### v1.0.0 — Spatial v2 + stabilisation  *(candidat)*
Étendre `db.spatial.*` (ST_Union, ST_Simplify, ST_ConvexHull, ST_MakeValid, agrégats spatiaux,
raster ?) + figer l'API publique pour un vrai 1.0.

## Idées plus lointaines / à re-litiger
- ETL cross-DB et sources/sinks DataFrame/CSV/parquet (v0.5.0 est same-DB only).
- API deferred historique : named params (`:name`), health checks, structured logging,
  isolation level, savepoints, sync streaming, dynamic pool sizing.

## Pourquoi cet ordre (raisonnement)
Voir la discussion du 2026-06-15. En résumé : réorg d'abord (fenêtre idéale, surface propre pour
la suite) → puis on solde la dette d'alias en même temps qu'on livre l'ETL incrémental (la suite
logique de v0.5.0, déjà préparée) → puis les features par valeur décroissante / risque croissant
(TimescaleDB avancé = forte valeur time-series, CRUD = confort, spatial v2 = vers le 1.0).

---

*Vision préparée le 2026-06-15, mise à jour le 2026-06-19 (v0.6.0 shippé). Non engageante ; chaque milestone se confirme via `/gsd-new-milestone`.*
