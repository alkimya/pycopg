# Requirements: pycopg — v0.6.0 Réorganisation en accessors

**Defined:** 2026-06-17
**Core Value:** Every public method in Database must have a working, tested equivalent in AsyncDatabase — full sync/async parity with consistent, clean API.

> **Nature du milestone :** refactor interne pur — ce milestone **déménage l'existant** sous
> des accessors lazy avec alias rétro-compatibles, il **n'ajoute aucun nouveau pouvoir**. Pattern
> déjà éprouvé : `db.spatial.*` (v0.4.0) et `db.etl.*` (v0.5.0). Décisions D-SCOPE-1..4 verrouillées
> en discussion (voir `.planning/v0.6.0-SCOPE.md`). Questions ouvertes tranchées au cadrage
> (2026-06-17) : `db.schema.*` reste un seul bloc ; DataFrame reste à plat ; `create_spatial_index`/
> `list_geometry_columns` → `db.spatial.*`.

## v1 Requirements

Requirements for the v0.6.0 release. Each maps to exactly one roadmap phase.

### Infrastructure (REORG)

Mécanisme transverse partagé par tous les accessors. À livrer en premier (la phase 1 valide le
pattern, les phases suivantes le répliquent).

- [ ] **REORG-01**: A `@deprecated_alias("db.<accessor>.<method>")` decorator emits a uniform `DeprecationWarning` (message pointing to the new path, correct `stacklevel`) and delegates to the accessor; sync and async variants exist.
- [ ] **REORG-02**: Each migrated method keeps a working flat alias on `db.*` / `async_db.*` that warns and delegates — zero breaking change for existing callers (D-SCOPE-1/D-SCOPE-2).
- [ ] **REORG-03**: `test_parity` registers the 5 new accessors and verifies sync ↔ async surface parity for every moved method (D-SCOPE-4).
- [ ] **REORG-04**: Coverage ratchet held at ≥94% — every alias has a test asserting it both warns and delegates correctly; existing tests' `DeprecationWarning` noise is filtered (no `-W error` breakage).
- [ ] **REORG-05**: New accessor classes are exported in `__init__.py` `__all__` (mirroring `SpatialAccessor`/`ETLAccessor`); README + Sphinx document the `db.X.*` surface; CHANGELOG + MIGRATION note the deprecation cycle (removal in v0.7.0).

### Timescale accessor (TS)

- [ ] **TS-01**: `db.timescale.*` / `async_db.timescale.*` exposes the 6 TimescaleDB methods (`create_hypertable`, `enable_compression`, `add_compression_policy`, `add_retention_policy`, `list_hypertables`, `hypertable_info`); the flat `db.*` names remain as deprecated aliases.

### Admin accessor (ADM)

- [ ] **ADM-01**: `db.admin.*` / `async_db.admin.*` exposes the 12 role & permission methods (`create_role`, `drop_role`, `role_exists`, `list_roles`, `alter_role`, `grant_role`, `revoke_role`, `grant`, `revoke`, `list_role_members`, `list_role_grants`); the flat `db.*` names remain as deprecated aliases.

### Schema accessor (SCH)

- [ ] **SCH-01**: `db.schema.*` / `async_db.schema.*` exposes the ~26 DDL + introspection methods as a single block — bases (`create_database`/`drop_database`/`database_exists`/`list_databases`), extensions (`create_extension`/`drop_extension`/`list_extensions`/`has_extension`), schemas (`create_schema`/`drop_schema`/`list_schemas`/`schema_exists`), tables/columns (`list_tables`/`table_exists`/`list_columns`/`columns_with_types`/`drop_table`/`truncate_table`/`table_info`/`row_count`), constraints/index (`add_primary_key`/`add_foreign_key`/`add_unique_constraint`/`create_index`/`drop_index`/`list_indexes`/`list_constraints`); the flat `db.*` names remain as deprecated aliases.
- [ ] **SCH-02**: `create_spatial_index` and `list_geometry_columns` are relocated to **`db.spatial.*`** / `async_db.spatial.*` (thematic PostGIS coherence, not `db.schema.*`); the flat `db.*` names remain as deprecated aliases.

### Maint accessor (MNT)

- [ ] **MNT-01**: `db.maint.*` / `async_db.maint.*` exposes the 6 maintenance/size methods (`size`, `table_size`, `table_sizes`, `vacuum`, `analyze`, `explain`); the flat `db.*` names remain as deprecated aliases.

### Backup accessor (BKP)

- [ ] **BKP-01**: `db.backup.*` / `async_db.backup.*` exposes the 4 dump/restore/CSV methods (`pg_dump`, `pg_restore`, `copy_to_csv`, `copy_from_csv`); the flat `db.*` names remain as deprecated aliases.

## v2 Requirements

Deferred to future releases (ordre validé, voir `.planning/FUTURE-MILESTONES.md`). Tracked but not in the v0.6.0 roadmap.

### Alias removal (v0.7.0)

- **ALIAS-RM-01**: Remove the deprecated flat aliases introduced in v0.6.0 (one deprecation cycle = one version). Trivial because the real logic lives in the accessors (D-SCOPE-2).

### ETL incremental (v0.7.0)

- **ETL-INC-01**: `db.etl.run()` reloads only new rows via the reserved nullable `pipeline_runs.watermark JSONB` column (additive, no breaking migration).

### Advanced TimescaleDB (v0.8.0)

- **TS-ADV-01**: Continuous aggregates, `time_bucket`/`time_bucket_gapfill`, `show_chunks`/`drop_chunks`, `add_dimension`, `reorder_policy` — land cleanly under the `db.timescale.*` created in v0.6.0.

### CRUD & enriched introspection (v0.9.0)

- **CRUD-01**: Ergonomic CRUD (`upsert`, `delete_where`, `update_where`, `exists`, `count`, `paginate`, dict fetch) + introspection (`primary_key()`, `foreign_keys()`, `sequences()`, `views()`, `describe()`); natural moment to carve a `db.meta.*` from `db.schema.*` if it earns its keep.

## Out of Scope

Explicitly excluded for v0.6.0. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Tout nouveau helper (CRUD, TimescaleDB avancé, spatial v2, introspection enrichie) | Ce milestone déménage l'existant, il n'ajoute aucun pouvoir. Les nouveaux helpers viendront sur la surface propre (v0.8.0+). |
| Suppression des alias dépréciés | Planifiée pour v0.7.0 — un cycle de dépréciation = une version. |
| Déménager les méthodes DataFrame (`to_dataframe`/`from_dataframe`/`*_geodataframe`) | Usage quotidien — restent à plat sur `db.*` (penchant confirmé au cadrage). |
| Déménager le cœur transactionnel (`execute`, `transaction`, `session`, `insert_many`, `stream`, `notify`, `fetch_*`, …) | Cœur de l'API — reste à plat sur `db.*` par design. |
| Scinder `db.schema.*` en `db.schema.*` + `db.meta.*` | Tranché au cadrage : un seul bloc cohérent (par domaine, comme spatial/etl). Carve éventuel reporté à v0.9.0 sur surface propre. |
| ETL incrémental / cross-DB / file sinks | Indépendant de la réorg — reporté (v0.7.0+). |

## Traceability

Which phases cover which requirements. Populated during roadmap creation (Step 10).

| Requirement | Phase | Status |
|-------------|-------|--------|
| REORG-01 | Phase [N] | Pending |
| REORG-02 | Phase [N] | Pending |
| REORG-03 | Phase [N] | Pending |
| REORG-04 | Phase [N] | Pending |
| REORG-05 | Phase [N] | Pending |
| TS-01 | Phase [N] | Pending |
| ADM-01 | Phase [N] | Pending |
| SCH-01 | Phase [N] | Pending |
| SCH-02 | Phase [N] | Pending |
| MNT-01 | Phase [N] | Pending |
| BKP-01 | Phase [N] | Pending |

**Coverage:**
- v1 requirements: 11 total
- Mapped to phases: 0 (pending roadmap)
- Unmapped: 11 ⚠️

---
*Requirements defined: 2026-06-17*
*Last updated: 2026-06-17 after initial definition*
