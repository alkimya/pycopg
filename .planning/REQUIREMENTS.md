# Requirements: pycopg v1.2.0 — Polish & finitions additives

**Defined:** 2026-07-04
**Core Value:** Every public method in `Database` must have a working, tested equivalent in `AsyncDatabase` — full sync/async parity with a consistent, clean API.

> **Milestone character:** Additive-only maturity/polish release under the **frozen SemVer 1.0** public API. No new subsystem, no breaking change, every default path byte-identical. Standing bar for every code requirement: full sync/async parity (verified by `test_accessor_parity` / `test_accessor_parameter_kind_parity`), `validate_identifiers`-first builders with user values bound as `%s` + a dedicated injection test, zero new runtime dependencies, coverage ratchet ≥95% (baseline 96.65%), `mypy --strict` stays a blocking gate, interrogate 100%, Sphinx `-W` clean.

## v1.2.0 Requirements

Requirements for this milestone. Each maps to exactly one roadmap phase (traceability below).

### Spatial (`db.spatial.*`)

- [x] **SPAT-F01**: User can pass a keyword-only `gridSize=` to `union` / `difference` / `intersection` for fixed-precision overlay output (PostGIS/GEOS ≥ 3.9); default `None` keeps the shipped SQL byte-identical.
- [x] **SPAT-F02**: User can compute the length of linear geometries via `db.spatial.length` (ST_Length), complementing the existing `area` / `perimeter`.
- [ ] **SPAT-F03**: User can get the per-row bounding-box geometry via `db.spatial.envelope` (ST_Envelope).
- [ ] **SPAT-F04**: User can get a guaranteed-inside representative point via `db.spatial.point_on_surface` (ST_PointOnSurface), complementing `centroid`.
- [x] **SPAT-F05**: User can check geometry validity and its reason via `db.spatial.is_valid` (ST_IsValid) and `db.spatial.is_valid_reason` (ST_IsValidReason), complementing `make_valid`.
- [ ] **SPAT-F06**: User can test the `overlaps` / `touches` / `crosses` / `disjoint` DE-9IM predicates via `db.spatial.*`, completing the `contains` / `intersects` / `within` / `dwithin` predicate family.

### CRUD symmetry (flat transactional core)

- [ ] **CRUD-F04**: User can read rows by predicate via `select_where` / `find` returning `list[dict]` — accepting both a dict-equality WHERE and a raw-SQL `where_sql` / `where_params` escape hatch through the shared `QueryMixin._resolve_predicate` guard (the missing read sibling of `delete_where` / `update_where` / `exists` / `count`).
- [ ] **CRUD-F05**: User can read a single matching row via `get` / `find_one` returning `dict | None` (same predicate surface as CRUD-F04).
- [ ] **CRUD-F06**: User can insert a single row via `insert` with `RETURNING *` — the singular twin of the existing `insert_many` / `upsert`.

### Introspection (`db.schema.*`)

- [ ] **INTRO-F03**: User can check a column's existence via `db.schema.column_exists`, completing the `table_exists` / `schema_exists` / `database_exists` family.
- [ ] **INTRO-F04**: User can get a table's on-disk size via `db.schema.table_size` (`pg_total_relation_size`), complementing `row_count`.

### Hygiene & tooling

- [ ] **DOC-14**: Documentation prose references the current `*Error` exception names — the deprecated `ExtensionNotAvailable` residue is removed from `docs/spatial.md` and `docs/api-reference.md` (the intentional deprecated-alias mentions in `docs/stability.md` are left as-is).
- [ ] **TOOL-01**: The `vulture` dead-code scan runs via a `make deadcode` target and in CI, settling the deferred AUDIT-02 (`vulture_whitelist.py` + dev-dep already exist but only run manually today).

### Release

- [ ] **REL-13**: pycopg 1.2.0 is published to PyPI — version bumped across `pyproject.toml` / `docs/conf.py` / `uv.lock`, a code-exact `[1.2.0]` Added CHANGELOG entry, all 5 release gates green (coverage ≥95%, interrogate 100%, Sphinx `-W`, `-W error::DeprecationWarning`, `mypy --strict` 0/18), annotated tag + human-gated OIDC publish + clean-venv smoke.

## Future Requirements

Deferred to a later cycle. Tracked in the frozen backlog, not in this roadmap.

### ETL

- **ETL-INC-F05**: CDC / WAL change capture (logical replication) — a large distinct subsystem; feasibility under zero-new-runtime-deps (psycopg3 replication protocol support) must be verified before it becomes a milestone.

### Spatial

- **RASTER-F01**: PostGIS raster I/O subsystem — a whole new PostGIS capability; a scoping decision (SQL-native zero-dep vs full GDAL/rasterio I/O as an optional extra) is required before it becomes a milestone.

## Out of Scope

Explicitly excluded from v1.2.0. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| CDC / WAL streaming ingest (ETL-INC-F05) | Large subsystem + zero-dep feasibility risk; stays a **maturity** cycle, not an expansion. Frozen backlog. |
| PostGIS raster (RASTER-F01) | Whole new subsystem; contradicts the polish/maturity direction chosen for v1.2. Frozen backlog. |
| Any breaking API change | Public API frozen under SemVer 1.0 — this milestone is additive-only. |
| New runtime dependency | Standing constraint; every helper builds on psycopg3/PostGIS SQL already available. |
| `docs/stability.md` deprecated-name mentions | Intentional — that page documents the deprecated aliases on purpose (DOC-14 touches only prose residue elsewhere). |

## Traceability

Which phases cover which requirements. Populated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SPAT-F01 | Phase 52 | Complete |
| SPAT-F02 | Phase 52 | Complete |
| SPAT-F03 | Phase 52 | Pending |
| SPAT-F04 | Phase 52 | Pending |
| SPAT-F05 | Phase 52 | Complete |
| SPAT-F06 | Phase 52 | Pending |
| CRUD-F04 | Phase 53 | Pending |
| CRUD-F05 | Phase 53 | Pending |
| CRUD-F06 | Phase 53 | Pending |
| INTRO-F03 | Phase 53 | Pending |
| INTRO-F04 | Phase 53 | Pending |
| DOC-14 | Phase 54 | Pending |
| TOOL-01 | Phase 54 | Pending |
| REL-13 | Phase 54 | Pending |

**Coverage:**

- v1.2.0 requirements: 14 total
- Mapped to phases: 14 (filled by roadmap)
- Unmapped: 0

---
*Requirements defined: 2026-07-04*
*Last updated: 2026-07-04 after roadmap creation (14/14 requirements mapped to Phases 52-54)*
