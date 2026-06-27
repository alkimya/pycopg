# Requirements: pycopg v1.0.0 — Spatial v2 + gel API

**Defined:** 2026-06-27
**Core Value:** Every public method in `Database` must have a working, tested equivalent in `AsyncDatabase` — full sync/async parity with a consistent, clean API.

> **The last big milestone.** Goal: a complete, stable, homogeneous high-level API (maximum capability without raw SQL), frozen under SemVer at 1.0. Scope locked at cadrage 2026-06-27: 3 spatial families + 4 backlog API gaps + API freeze. The ~14 family follow-ups (TSDB-F/ETL-INC-F/CRUD-F/INTRO-F) and raster are deferred to additive 1.x point releases (non-breaking under the frozen API).
>
> **Build order is dependency-fixed** (research SUMMARY.md): homogenization FIRST (new spatial builders adopt `filter=` from day one; exception renames precede the strict-typing gate) → Spatial v2 (processing → aggregates → serialization/MVT) → API gaps + logging → mypy-strict LAST → release.
>
> **Cross-cutting acceptance criteria for every new builder/method:** `validate_identifiers` is line 1 of every new SQL builder with a dedicated injection test (the v0.10.0 COPY-rewrite green-suite lesson); full sync/async parity enforced by `test_accessor_parity`; zero new RUNTIME dependencies (all 4 API gaps are psycopg3/psycopg_pool native; logging is stdlib).

## v1 Requirements

Requirements for the 1.0 release. Each maps to exactly one roadmap phase.

### Spatial v2 — Geometric Processing

Extend `db.spatial.*` / `async_db.spatial.*`. Column-only builder shape (no geometry resolver). PostGIS floor ≥ 3.0 (≥ 3.2 recommended).

- [ ] **SPAT2-01**: User can compute the pairwise union of two geometry columns via `db.spatial.union(table, geom, other_geom, ...)` (ST_Union)
- [ ] **SPAT2-02**: User can simplify a geometry column via `db.spatial.simplify(table, geom, tolerance, preserve_topology=True)` (ST_SimplifyPreserveTopology by default to avoid NULL collapse)
- [ ] **SPAT2-03**: User can compute the convex hull of a geometry column via `db.spatial.convex_hull(table, geom, ...)` (ST_ConvexHull)
- [ ] **SPAT2-04**: User can repair invalid geometries via `db.spatial.make_valid(table, geom, method=None)` (ST_MakeValid, method whitelist; `method="structure"` documented as PostGIS ≥ 3.2)
- [ ] **SPAT2-05**: User can compute the difference of two geometry columns via `db.spatial.difference(table, geom, other_geom, ...)` (ST_Difference)
- [ ] **SPAT2-06**: User can compute the intersection of two geometry columns via `db.spatial.intersection(table, geom, other_geom, ...)` (ST_Intersection)

### Spatial v2 — Spatial Aggregates

New GROUP BY aggregate builder shape (one row per group; optional `group_by`). Documented NULL-propagation behavior.

- [ ] **SPAT2-07**: User can collect geometries into a collection via `db.spatial.collect_geometries(table, geom, group_by=None, ...)` (ST_Collect)
- [ ] **SPAT2-08**: User can dissolve geometries into a single boundary via `db.spatial.union_aggregate(table, geom, group_by=None, ...)` (ST_Union aggregate)
- [ ] **SPAT2-09**: User can compute the bounding extent of a geometry column via `db.spatial.extent(table, geom, group_by=None, ...)` (ST_Extent; box2d for `into="rows"`, geometry for `into="gdf"`)

### Spatial v2 — Serialization

- [ ] **SPAT2-10**: User can serialize geometries to GeoJSON via `db.spatial.as_geojson(table, geom, max_decimal_digits=6, ...)` (ST_AsGeoJSON; text return)
- [ ] **SPAT2-11**: User can serialize geometries to WKT via `db.spatial.as_text(table, geom, ...)` (ST_AsText; text return)
- [ ] **SPAT2-12**: User can render a Mapbox Vector Tile via `db.spatial.as_mvt(table, geom, tile_z, tile_x, tile_y, ...)` returning `bytes` (enforced ST_Transform→ST_AsMVTGeom→ST_AsMVT pipeline; no raw-geometry shortcut)
- [ ] **SPAT2-13**: Every new spatial v2 method has a working, tested `AsyncDatabase` equivalent at full parity (`test_accessor_parity`); every new builder runs `validate_identifiers` first with a dedicated injection test

### Transaction Control

Additive to the flat transactional core (`db.transaction`/`db.session`), full sync/async parity. psycopg3-native, zero new runtime deps.

- [ ] **TXN-01**: User can set the transaction isolation level via `db.transaction(isolation_level=...)` and `db.session(isolation_level=...)` (psycopg3 `IsolationLevel`)
- [ ] **TXN-02**: User can create nested savepoints with partial rollback via a `db.savepoint(name=None)` context manager (and `transaction(savepoint_name=...)`)

### API Ergonomics & Observability

- [ ] **PARAM-01**: User can pass named query parameters as a dict using psycopg3-native `%(name)s` placeholders on `execute`/`fetch_one`/`fetch_val`/`fetch_all`/`to_dataframe`, documented and type-annotated (no `:name` translator — decided 2026-06-27)
- [ ] **HEALTH-01**: User can probe connection/pool health via `db.health()` returning `{connected, latency_ms, server_version}` (plus pool stats when pooled), sync + async
- [ ] **LOG-01**: User can enable structured logging of pycopg operations via stdlib `logging` (new `pycopg/logging.py`: `NullHandler` default, `get_logger` + `log_operation` context manager with `extra={}` fields), zero new runtime deps

### API Freeze & Homogenization

Breaking changes allowed; every break served via `@deprecated_alias`/`DeprecationWarning` (one cycle) + MIGRATION entry. Homogenization lands BEFORE Spatial v2 and mypy-strict.

- [ ] **FREEZE-01**: Spatial `where=` (raw SQL fragment) is renamed to `filter=` so `where=` means dict-equality consistently across the whole surface; the old `where=` keyword keeps working for one deprecation cycle with `DeprecationWarning` + MIGRATION
- [ ] **FREEZE-02**: Domain exceptions adopt the `*Error` (N818) convention — `ExtensionNotAvailable`→`ExtensionNotAvailableError`, `TableNotFound`→`TableNotFoundError`, `InvalidIdentifier`→`InvalidIdentifierError`, `DatabaseExists`→`DatabaseExistsError` — with old names as deprecated aliases + MIGRATION; internal call sites use the new names
- [ ] **FREEZE-03**: Public API consistency pass — homogenize return-shape and `into=` conventions, parameter naming/order across the 7 accessors + flat core; documented Stable API Contract (positional vs keyword-only parameters) for every public method
- [ ] **FREEZE-04**: SemVer + deprecation policy published (`docs/stability.md`) — the 1.0 stability contract (what's stable, deprecation timeline, supported versions)
- [ ] **FREEZE-05**: `mypy --strict` made blocking in CI (remove `continue-on-error`) with 3 dev-group stubs (`pandas-stubs`, `types-geopandas`, `types-shapely`) and `@overload` on all `into="rows"/"gdf"` methods; complete `py.typed` (zero strict errors over `pycopg/`)

### Release

- [ ] **REL-11**: pycopg 1.0.0 released to PyPI via OIDC — version bump (all sources), CHANGELOG `[1.0.0]` Breaking + Added, MIGRATION guide complete, all gates green (coverage ≥ 95%, interrogate 100%, Sphinx `-W`, `-W error::DeprecationWarning`, `mypy --strict` exit 0), annotated tag `v1.0.0`, clean-venv smoke confirms `__version__ == "1.0.0"`

## Future Requirements (deferred to additive 1.x — non-breaking under the frozen API)

### Raster (post-1.0)

- **RASTER-F01**: PostGIS raster I/O and processing surface — large distinct subsystem, deferred post-1.0

### Spatial follow-ups

- **SPAT-F01**: `gridSize` precision parameter on overlay functions (union/difference/intersection) — GEOS ≥ 3.9 edge case

### TimescaleDB follow-ups (from v0.8.0)

- **TSDB-F01**: `drop_continuous_aggregate` / `remove_continuous_aggregate_policy` lifecycle removal
- **TSDB-F02**: `time_bucket` `origin`/`offset` alignment parameters
- **TSDB-F03**: `compress_chunk` / `decompress_chunk` per-chunk control
- **TSDB-F04**: `show_chunks` physical-time filters

### ETL incremental follow-ups (from v0.7.0)

- **ETL-INC-F01**: `initial_watermark` first-run bound
- **ETL-INC-F02**: configurable `>=`/lookback boundary
- **ETL-INC-F03**: multi-column watermarks
- **ETL-INC-F04**: advisory-lock concurrency
- **ETL-INC-F05**: CDC / WAL change capture

### CRUD / introspection follow-ups (from v0.9.0)

- **CRUD-F01**: raw-SQL `where=` escape hatch
- **CRUD-F02**: keyset / cursor pagination
- **CRUD-F03**: page envelope with total / has_next
- **INTRO-F01**: `describe` as dataclass / DataFrame
- **INTRO-F02**: `materialized_views()` + per-view column introspection

## Out of Scope

Explicitly excluded from 1.0. Documented to prevent scope creep.

| Feature | Reason |
| --- | --- |
| `:name` parameter translator | psycopg3-native `%(name)s` chosen (PARAM-01); a hand-rolled `:name`→`%(name)s` parser is too fragile to freeze under SemVer (must handle `::cast`, quoted literals) |
| Raster support | Large distinct PostGIS subsystem, not core to "no raw SQL"; post-1.0 (RASTER-F01) |
| structlog / logging framework dependency | Library rule: callers own the logging stack; stdlib `logging` + `NullHandler` is the correct integration (LOG-01) |
| pyright as a second type checker | `mypy --strict` is sufficient for the freeze gate |
| The ~14 family follow-ups (TSDB-F/ETL-INC-F/CRUD-F/INTRO-F) | "1.0 net + 1.x additifs" decision (2026-06-27) — additive, non-breaking under the frozen API; ship as 1.1/1.2 |
| Cross-DB ETL & DataFrame/CSV/parquet source/sink | ETL is same-DB by design |
| Dynamic connection pool sizing | Fixed sizing is acceptable (pre-existing Out of Scope) |
| ORM / model layer, query builder / fluent API, SQLAlchemy as a dependency | Duplicates SQLAlchemy; never as good as SQLAlchemy Core (pre-existing Out of Scope) |
| Schema diff / auto-migration | Complex, error-prone (pre-existing Out of Scope) |

## Traceability

Which phases cover which requirements. Populated during roadmap creation.

| Requirement | Phase | Status |
| --- | --- | --- |
| SPAT2-01 | Phase 42 | Pending |
| SPAT2-02 | Phase 42 | Pending |
| SPAT2-03 | Phase 42 | Pending |
| SPAT2-04 | Phase 42 | Pending |
| SPAT2-05 | Phase 42 | Pending |
| SPAT2-06 | Phase 42 | Pending |
| SPAT2-07 | Phase 43 | Pending |
| SPAT2-08 | Phase 43 | Pending |
| SPAT2-09 | Phase 43 | Pending |
| SPAT2-10 | Phase 44 | Pending |
| SPAT2-11 | Phase 44 | Pending |
| SPAT2-12 | Phase 44 | Pending |
| SPAT2-13 | Phase 44 | Pending |
| TXN-01 | Phase 45 | Pending |
| TXN-02 | Phase 45 | Pending |
| PARAM-01 | Phase 45 | Pending |
| HEALTH-01 | Phase 45 | Pending |
| LOG-01 | Phase 45 | Pending |
| FREEZE-01 | Phase 41 | Pending |
| FREEZE-02 | Phase 41 | Pending |
| FREEZE-03 | Phase 41 | Pending |
| FREEZE-04 | Phase 41 | Pending |
| FREEZE-05 | Phase 46 | Pending |
| REL-11 | Phase 47 | Pending |

**Coverage:**

- v1 requirements: 24 total
- Mapped to phases: 24 (roadmap complete)
- Unmapped: 0

---

*Requirements defined: 2026-06-27*
*Last updated: 2026-06-27 — traceability table populated by roadmapper (Phases 41-47)*
