# Project Research Summary

**Project:** pycopg v1.0.0 — Spatial v2 + gel API
**Domain:** High-level Python API for PostgreSQL/PostGIS/TimescaleDB — final 1.0 milestone
**Researched:** 2026-06-27
**Confidence:** HIGH

## Executive Summary

pycopg v1.0.0 is a completion milestone, not an exploration: the library is mature (v0.10.0 shipped, 95%+ coverage, audit-hardened), the stack is locked, and the goal is to arrive at a stable, frozen, homogeneous public API. The milestone has three workstreams with a hard-fixed build order. Homogenization must come first so that every new spatial builder adopts the renamed conventions (where=→filter= on spatial, 4 N818 exception renames) from day one before mypy-strict freezes the type surface. Spatial v2 follows in three sub-phases (processing, aggregates, serialization/MVT). The 4 API completeness gaps (isolation + savepoints, named params, health checks, structured logging) are purely additive and can land in a dedicated phase. mypy-strict is the final gate — it must come last because all renaming and annotation work must be complete before the gate is raised to blocking.

All four API-gap features (isolation, savepoints, health checks, named params) are served by psycopg3 and psycopg_pool native APIs — zero new runtime dependencies are needed. Structured logging is stdlib-only (NullHandler pattern). The only new dependencies are 3 dev-group type stubs (pandas-stubs, types-geopandas, types-shapely) required to run mypy --strict cleanly over the DataFrame and GeoDataFrame code paths. This is the sharpest finding from the stack research: the entire 1.0 feature set is buildable without touching pyproject.toml's `[project.dependencies]` table.

The top risks are all known from pycopg's own history. The v0.10.0 COPY rewrite proved that a test suite stays green while validate_identifiers is silently absent from a new builder — the only reliable guard is a per-builder injection test in acceptance criteria. mypy-strict has no test signal: functions can be type-incorrect while running correctly at runtime, so enabling strict before the annotation work is complete stalls the milestone under a permanently red CI gate. Both risks have concrete prevention strategies documented below. The named-params feature is a documentation/annotation task, not a parser: building a :name→%(name)s translator is an anti-feature (psycopg3 uses %(name)s natively and that style must be the public contract).

## Key Findings

### Recommended Stack

The existing runtime stack requires no changes. psycopg 3.1.0+ provides IsolationLevel enum, nested transaction(savepoint_name=) context managers, and connection.closed/broken health attributes natively. psycopg_pool 3.2.0+ provides pool.check(), pool.get_stats(), and ConnectionPool.check_connection — the full health-check API surface. The PostGIS floor rises to 3.0 (hard) and 3.2 (recommended): PostGIS 3.0 is required for ST_AsMVT feature IDs and ST_TileEnvelope; PostGIS 3.2 unlocks ST_MakeValid(method="structure") which is 2.7x faster and semantically superior for complex geometry repair.

**Core technologies (no change from v0.10.0):**
- psycopg >= 3.1.0: IsolationLevel, savepoints, health attrs — all native, no shim needed
- psycopg_pool >= 3.2.0: pool.check(), check_connection, get_stats() — full health API at floor
- PostGIS server >= 3.0 (hard) / >= 3.2 (recommended): ST_AsMVT, ST_MakeValid structure method
- pandas >= 2.0.0, geopandas >= 0.14.0, shapely >= 2.0.0: no floor changes
- mypy 2.1.0: already installed; switch strict=true from non-blocking to blocking

**New dev-group dependencies only:**
- pandas-stubs >= 2.0.0: mypy strict over DataFrame-touching code
- types-geopandas >= 0.14.0: mypy strict over GeoDataFrame paths
- types-shapely >= 2.0.0: mypy strict over shapely geometry objects

**What NOT to add:**
- structlog or any logging framework (library rule: callers own the logging stack; stdlib NullHandler is correct)
- :name→%(name)s translator (psycopg3 uses %(name)s natively; translator introduces a fragile parser)
- PostGIS version introspection guard for ST_MakeValid options (document the floor, let PostgreSQL surface errors)

### Expected Features

**Must have — table stakes for a coherent 1.0:**

Spatial processing (6 methods on db.spatial.*):
- `union(table, geom, other_geom=...)` — 2-column pairwise union; column-only builder shape
- `simplify(table, geom, tolerance=, preserve_topology=True)` — ST_SimplifyPreserveTopology default prevents NULL collapse
- `convex_hull(table, geom)` — simplest builder; expected by every GIS user
- `make_valid(table, geom, method=None)` — geometry repair with method whitelist; method="structure" requires PostGIS 3.2
- `difference(table, geom, other_geom=...)` — A minus B; same 2-column builder shape as union
- `intersection(table, geom, other_geom=...)` — shared region; symmetric; same shape as difference

Spatial aggregates (3 methods — new GROUP BY builder pattern):
- `collect_geometries(table, geom, group_by=None)` — ST_Collect; fastest aggregate, no boundary dissolve
- `union_aggregate(table, geom, group_by=None)` — ST_Union(agg); dissolves boundaries; most important aggregate
- `extent(table, geom, group_by=None)` — ST_Extent; returns box2d text (rows) or geometry (gdf with srid=)

Spatial serialization:
- `as_geojson(table, geom, max_decimal_digits=6, ...)` — ST_AsGeoJSON; text return; in _SCALAR_HELPERS
- `as_text(table, geom, max_decimal_digits=None)` — ST_AsText / WKT; text return; in _SCALAR_HELPERS

API completeness gaps (4):
- `db.transaction(isolation_level=, savepoint_name=)` and `db.session(isolation_level=)` — psycopg3 native
- `db.savepoint(name=None)` context manager — nested transaction via conn.transaction(savepoint_name=)
- Named params: %(name)s dict-style documented + type-annotated on execute/fetch_all (no code change needed)
- `db.health()` returning {connected, latency_ms, server_version}; pool variant adds pool_stats

API freeze:
- Homogenization pass: where=→filter= on all 11 existing spatial methods + 4 N818 exception renames with DeprecationWarning aliases
- SemVer/deprecation policy document (docs/stability.md)
- mypy strict blocking (strict=true, remove continue-on-error)
- py.typed completeness verified (zero strict errors)

**Should have — differentiators:**
- `as_mvt(table, geom, tile_z, tile_x, tile_y, ...)` — returns bytes; ST_Transform+ST_AsMVTGeom+ST_AsMVT pipeline; removes ~15 lines of boilerplate per tile endpoint
- Structured logging via stdlib logging.getLogger + extra={} dicts; new pycopg/logging.py with log_operation context manager; zero new deps

**Explicitly deferred to 1.x:**
- Raster support — large distinct surface, explicitly out of scope
- gridSize precision parameter on overlay functions — GEOS 3.9 dependency, edge case
- TSDB-F, ETL-INC-F, CRUD-F, INTRO-F family follow-ups — all locked out per 2026-06-27 cadrage
- Cross-DB ETL, dynamic pool sizing, pyright as second type checker

### Architecture Approach

v1.0.0 touches three architectural layers without creating any new accessors or modules (except pycopg/logging.py). Spatial v2 adds 8-10 builders and methods to the existing spatial.py using the column-only and new aggregate builder shapes — no involvement of _resolve_geometry(). The flat transactional core (database.py / async_database.py) gains three new parameters on existing methods (isolation_level, savepoint_name, dict params) plus one new method (health()). Cross-cutting: exceptions.py gets 4 renames with deprecated aliases; utils.py gets _rewrite_named_params(); logging.py is a new file shared across sync and async paths.

**Major components and their v1.0.0 changes:**
1. `pycopg/spatial.py` — Modified: 8-10 new build_*_sql builders (column-only + aggregate shape); _SCALAR_HELPERS extended with "extent", "as_geojson", "as_text"; SpatialAccessor + AsyncSpatialAccessor gain ~11 new methods + as_mvt; all new builders use filter= not where=
2. `pycopg/database.py` + `async_database.py` — Modified: transaction() gains isolation_level + savepoint_name; session() gains isolation_level; execute() params type widened to Sequence|dict|None; health() added; full sync/async parity required
3. `pycopg/exceptions.py` — Modified: 4 renames (ExtensionNotAvailableError, TableNotFoundError, InvalidIdentifierError, DatabaseExistsError) with old names as DeprecationWarning aliases
4. `pycopg/utils.py` — Modified: _rewrite_named_params() added (pure function, safe in both sync/async)
5. `pycopg/logging.py` — New: get_logger() + log_operation() context manager; stdlib only
6. `pycopg/base.py`, `queries.py`, all other accessors — Unchanged

**The where=→filter= seam is the most critical homogenization decision.** After 1.0: where= always means dict equality (CRUD), filter= always means raw SQL fragment (spatial). This rename must happen in Phase 41 so all new spatial v2 builders use filter= from day one.

**Build order is dependency-fixed:**
Homogenization → Spatial v2 processing → Spatial v2 aggregates → Spatial v2 serialization (incl. as_mvt) → API gaps + logging → mypy strict + py.typed gate → Release

### Critical Pitfalls

1. **validate_identifiers silently dropped in new spatial builders** — The v0.10.0 COPY rewrite dropped validate_identifiers and the full suite stayed green (caught only by code review). Every new build_*_sql function's first line must be validate_identifiers(table, schema, geom). Every new builder must have an injection test asserting InvalidIdentifier on a malicious identifier. This is a per-phase acceptance criterion, not a code-review note.

2. **mypy strict enabled as blocking before stub gaps are resolved — stalls the milestone** — Enabling strict before @overload stubs are written and stub gaps handled means every commit turns CI red. Sequence: run mypy non-strict first → resolve stub gaps via [[tool.mypy.overrides]] → write @overload on all into= methods → only then enable strict=true as blocking.

3. **mypy strict has no test signal — latent type errors stay hidden** — Test suite stays green while type annotations are wrong. Budget the error count first (uv run mypy --strict pycopg/ | grep error | wc -l). Fix bottom-up: utils.py → exceptions.py → base.py → spatial.py. Use list[Any] / dict[str, Any] for intentionally dynamic types.

4. **ST_AsMVT wrong coordinate system produces silently corrupted tiles** — The builder must always emit ST_Transform(col, 3857) + ST_AsMVTGeom + ST_AsMVT — never a raw geometry path. Integration test must decode the returned bytes with a minimal MVT parser, not just check isinstance(result, bytes).

5. **Deprecation cycle wrong stacklevel or internal call sites using deprecated names** — stacklevel=2 must be verified by a test asserting the warning points to the caller's file, not pycopg/. Internal pycopg/ code must use the new names. The CI gate -W error::DeprecationWarning will fire if any internal code goes through a deprecated wrapper.

6. **Scope bloat re-attracting deferred items** — The 2026-06-27 cadrage is a hard fence. Every phase plan's "Out of scope" section must explicitly name TSDB-F/ETL-INC-F/CRUD-F/INTRO-F/raster as deferred. A phase count that grows during execution is a scope creep signal.

## Implications for Roadmap

Based on research, suggested phase structure (7 phases, starting at Phase 41):

### Phase 41: API Homogenization

**Rationale:** Must come first. New spatial v2 builders must use filter= from day one — writing them before the rename means an immediate double-rename. Exception renames (N818) must happen before mypy-strict to avoid re-annotating renamed sites under the strict gate.

**Delivers:** where=→filter= rename on all 11 existing spatial methods with DeprecationWarning aliases; 4 exception renames (ExtensionNotAvailableError etc.) with deprecated aliases; into= documentation pass; SemVer/deprecation policy doc (docs/stability.md); MIGRATION guide section for all renamed names.

**Addresses:** FREEZE-01, FREEZE-02; Pitfalls 5 (deprecation cycle), 7 (where= inconsistency), 8 (N818 deferred decision)

**Avoids:** Double-rename on new builders; re-annotating renamed exception types under mypy-strict gate.

---

### Phase 42: Spatial v2 — Processing Helpers

**Rationale:** 6 processing helpers using column-only builder shape — the simplest spatial v2 builders. Two sub-groups: (union, difference, intersection) share the 2-column binary shape; (simplify, convex_hull, make_valid) are unary column operations. All use filter= from day one (renamed in Phase 41).

**Delivers:** `union`, `simplify`, `convex_hull`, `make_valid`, `difference`, `intersection` on both SpatialAccessor and AsyncSpatialAccessor. All builders have validate_identifiers as first line + injection tests. ST_SimplifyPreserveTopology is the default. Mixed-SRID integration tests for binary operations.

**Addresses:** SPAT-V2-01..06; Pitfalls 1 (injection), 2 (SRID mismatch), 4 (NULL/degenerate geometry)

---

### Phase 43: Spatial v2 — Spatial Aggregates

**Rationale:** Aggregates establish a new builder shape (GROUP BY, one-row-per-group cardinality). Must come after processing to have the builder infrastructure pattern established.

**Delivers:** `collect_geometries`, `union_aggregate`, `extent` on both accessors. Shared build_spatial_aggregate_sql builder. extent's box2d vs geometry branching for into="gdf". NULL-propagation behavior documented + tested with NULL geometry fixture rows.

**Addresses:** SPAT-V2-07..09; Pitfall 5 (aggregate NULL propagation)

---

### Phase 44: Spatial v2 — Serialization + as_mvt

**Rationale:** as_geojson and as_text are trivial; grouping with as_mvt lets simple methods establish _SCALAR_HELPERS additions before tackling as_mvt's unique bytes-return path (the most complex spatial feature).

**Delivers:** `as_geojson` and `as_text` in _SCALAR_HELPERS. `as_mvt` as dedicated method returning bytes unconditionally — SQL always contains ST_Transform(..., 3857) + ST_AsMVTGeom + ST_AsMVT. Integration test decodes MVT bytes to verify feature count. PostGIS guard for ST_TileEnvelope.

**Addresses:** SPAT-V2-10..12; Pitfall 3 (ST_AsMVT wrong coordinate system)

---

### Phase 45: API Completeness Gaps + Structured Logging

**Rationale:** Purely additive to the flat transactional core; no interaction with spatial.py or homogenization work. All 5 features are independent and small enough to share a phase.

**Delivers:** `db.transaction(isolation_level=, savepoint_name=)` and `db.session(isolation_level=)` extended; `db.savepoint(name=None)` context manager; execute/fetch_all type widened to accept dict params + %(name)s documented (no code change needed); `db.health()` returning latency + server_version + pool_stats; pycopg/logging.py with log_operation context manager; key methods instrumented.

**Addresses:** API-01..05; named params is docs + type annotation only (anti-feature note: no :name translator)

**Key note:** Named params is a documentation/annotation task. psycopg3 already accepts %(name)s dict-style in cursor.execute(). The deliverable is: type annotation update + docstring examples + tests confirming dict params on all execute/fetch methods.

---

### Phase 46: mypy Strict + py.typed Gate

**Rationale:** Must come last. All renaming (Phase 41), new builders (Phases 42-44), and new method signatures (Phase 45) must be complete before the strict gate is raised to blocking.

**Delivers:** mypy strict=true as blocking in CI (remove continue-on-error); 3 dev stubs added (pandas-stubs, types-geopandas, types-shapely); @overload stubs on all into="rows"/"gdf" accessor methods; zero mypy --strict errors on full pycopg/ tree; ignore_missing_imports overrides audited; FREEZE-04 py.typed completeness confirmed; coverage ratchet held at 95%.

**Addresses:** FREEZE-03, FREEZE-04; Pitfalls 9 (mypy strict sequencing), 10 (latent type errors)

**Key note:** Start by measuring the error budget: uv run mypy --strict pycopg/ 2>&1 | grep error | wc -l. If >100 errors, plan as multi-session. The hardest work is @overload on all 20+ spatial methods with into= return types.

---

### Phase 47: Release

**Rationale:** Standard release phase — same gate process as every prior milestone.

**Delivers:** pycopg 1.0.0 on PyPI. CHANGELOG [1.0.0] with Breaking (homogenization renames) + Added sections. MIGRATION guide complete. docs/stability.md published. Stable API Contract section listing positional vs keyword-only parameters for all public methods. Gates: coverage 95%, interrogate 100%, Sphinx -W, -W error::DeprecationWarning, mypy --strict exit 0.

---

### Phase Ordering Rationale

- Homogenization BEFORE spatial v2: new builders must use filter= from day one; writing them before the rename means naming debt from the first commit
- Homogenization BEFORE mypy-strict: exception renames touch ~30+ raise/except sites; doing them before strict means fixing annotations once, not twice
- Spatial processing BEFORE aggregates: the column-only builder shape must be established before the new GROUP BY aggregate shape extends it
- API gaps AFTER spatial v2: the flat core changes are purely additive and have no dependency on spatial.py work; keeping them separate avoids entanglement during the most complex builder phase
- Logging BEFORE mypy-strict: log_operation wrappers introduce extra={} dict arguments that may require type annotations mypy-strict will flag
- mypy-strict LAST: it freezes the type surface; all renaming, parameter additions, and annotation work must precede the gate

### Research Flags

Phases needing explicit design at plan time (architecture decisions, not external research):
- **Phase 43 (aggregates):** GROUP BY aggregate builder shape is new to pycopg; build_spatial_aggregate_sql interface must be specced in the phase plan before implementation
- **Phase 44 (as_mvt):** ST_Transform + ST_AsMVTGeom + ST_AsMVT subquery composition must be fully specced in the phase plan; the SQL shape is non-trivial
- **Phase 46 (mypy strict):** Start by measuring error count; @overload budget for 20+ spatial methods may require multi-session plan

Phases with well-documented standard patterns (skip research-phase):
- **Phase 41 (homogenization):** @deprecated_alias mechanism established in v0.6.0; N818 rename pattern is mechanical
- **Phase 42 (processing):** Column-only builder shape is the dominant existing pattern in spatial.py
- **Phase 45 (API gaps):** psycopg3/psycopg_pool APIs fully verified; named params is docs-only
- **Phase 47 (release):** Same release gate process as every prior milestone

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Verified against psycopg3 Context7 docs, PostGIS official docs, mypy 2.1.0 docs, PyPI package pages; zero ambiguity on runtime deps |
| Features | HIGH | PostGIS function signatures verified from postgis.net/docs; psycopg3 transaction API confirmed from official docs; codebase read directly |
| Architecture | HIGH | Direct code inspection of spatial.py (2832 lines), base.py, database.py, async_database.py, exceptions.py, PROJECT.md |
| Pitfalls | HIGH | All findings grounded in pycopg's own history (v0.10.0 COPY rewrite validate_identifiers precedent), codebase, and PostGIS/mypy docs |

**Overall confidence:** HIGH

### Gaps to Address

- **@overload error count:** The exact count of mypy --strict errors across pycopg/ is unknown until Phase 46 starts. Measure first; if >100, plan multi-session.
- **psycopg3 inline stubs coverage:** Whether [[tool.mypy.overrides]] ignore_missing_imports entries for psycopg/psycopg_pool are still needed under strict=true has not been tested. Phase 46 must audit.
- **MVT decode in CI:** Verifying as_mvt output requires decoding the bytea MVT. If mapbox-vector-tile is not in dev deps, Phase 44 plan must decide on a structural check substitute.
- **Mixed-SRID fixture data:** Integration tests for binary operations need fixtures with inconsistent SRIDs. Phase 42 plan must confirm fixture availability in pycopg_test2.

## Sources

### Primary (HIGH confidence)
- psycopg3 Context7 docs `/websites/psycopg_psycopg3` and `/psycopg/psycopg` — IsolationLevel, transaction(savepoint_name=), named params %(name)s, pool check/stats
- psycopg_pool 3.3.1 PyPI — check(), check_connection, get_stats() confirmed at version floor
- postgis.net/docs — ST_MakeValid, ST_AsMVT, ST_AsGeoJSON, ST_Union, ST_Collect, ST_Extent, ST_Simplify, ST_Difference, ST_Intersection, ST_AsMVTGeom, ST_TileEnvelope function signatures
- mypy.readthedocs.io 2.1.0 — --strict flag list (13 flags), config_file reference
- pycopg codebase direct inspection: spatial.py (2832 lines), base.py (581 lines), database.py, async_database.py, exceptions.py, utils.py, PROJECT.md
- pycopg MEMORY: v0.10.0 COPY rewrite validate_identifiers drop + green suite precedent (commit 863e894)

### Secondary (MEDIUM confidence)
- pandas-stubs 3.0.3.*, types-geopandas 1.1.3.20260518, types-shapely PyPI pages — stub coverage for pycopg usage patterns inferred, not fully tested under strict
- CrunchyData blog on PostGIS 3.2 ST_MakeValid structure method — corroborates postgis.net docs

### Tertiary (LOW confidence)
- @overload error count estimate for Phase 46 — approximate; actual count determined at Phase 46 start

---
*Research completed: 2026-06-27*
*Ready for roadmap: yes*
