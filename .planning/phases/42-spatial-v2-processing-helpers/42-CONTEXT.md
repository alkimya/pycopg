# Phase 42: Spatial v2 — Processing Helpers - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can run the 6 core PostGIS geometry-**processing** operations on a table via
`db.spatial.*` and `async_db.spatial.*` **without raw SQL**:

- **Pairwise (2-column)** — `union` (`ST_Union`), `difference` (`ST_Difference`),
  `intersection` (`ST_Intersection`): row-by-row over two geometry columns on the **same table**.
- **Unary (single-column)** — `simplify` (`ST_SimplifyPreserveTopology`/`ST_Simplify`),
  `convex_hull` (`ST_ConvexHull`), `make_valid` (`ST_MakeValid`).

All six use the **column-only builder shape** (no `_resolve_geometry` resolver), `filter=` from
day one (born clean — see D-10), `validate_identifiers` line 1 + a dedicated injection test, and
full sync/async parity. Each produces a **geometry** result column, so `into="gdf"` is valid for
all six (none join `_SCALAR_HELPERS`).

**In scope (locked by REQUIREMENTS / ROADMAP — not re-litigated):**
- SPAT2-01..06 — the 6 processing methods on both `SpatialAccessor` and `AsyncSpatialAccessor`.
- Column-only shape; `filter=`; `validate_identifiers`-first + injection test per builder;
  `test_accessor_parity` + Phase-41 KIND-parity; zero new runtime deps; coverage ≥95%.
- `ST_SimplifyPreserveTopology` is the `simplify` default (SPAT2-02, avoids NULL collapse).
- `make_valid` `method` whitelist; `method="structure"` documented as PostGIS ≥ 3.2 (SPAT2-04).

**Out of scope (deferred to later phases / 1.x — do NOT pull in):**
- Spatial **aggregates** (`collect_geometries`/`union_aggregate`/`extent`) → Phase 43.
- **Serialization + MVT** (`as_geojson`/`as_text`/`as_mvt`) → Phase 44.
- Constant-geometry inputs (wkt/geojson/point) for the pairwise ops — REQUIREMENTS says
  column-only, no resolver.
- `gridSize` precision parameter on overlay ops (SPAT-F01, GEOS ≥ 3.9) — out of the high-level
  API; deferred to additive 1.x.
- Transaction control, named params, health, logging, mypy-strict — Phases 45–46.

</domain>

<decisions>
## Implementation Decisions

### Result/derived geometry column naming (D-01)
- **D-01:** **Per-op descriptive names**, each frozen at 1.0 as BOTH the `list[dict]` key AND
  the `into="gdf"` `geometry_column` (the 4th arg passed to `_run(...)` / `_arun(...)`). Mirrors
  the existing precedent (`buffer` aliases `AS buffer` → `_run(..., "buffer")`; `transform` →
  `AS geometry_transformed` → `_run(..., "geometry_transformed")`):
  - `union` → `union_geom`
  - `simplify` → `simplified`
  - `convex_hull` → `convex_hull`
  - `make_valid` → `made_valid`
  - `difference` → `difference`
  - `intersection` → `intersection`

### make_valid surface (D-02..D-04)
- **D-02:** `method` whitelist = `{None, "linework", "structure"}`. Validate **after**
  `validate_identifiers`, **before** any SQL — unknown value raises `ValueError`. `method=None` →
  `ST_MakeValid(t.<geom>)` (no params string). `method` in `{"linework","structure"}` →
  `ST_MakeValid(t.<geom>, %s)` with the params string passed as a `%s` value (never f-string).
- **D-03:** **Expose `keep_collapsed: bool | None = None`** — only meaningful when
  `method="structure"`; builds the params string `"method=structure keepcollapsed=true|false"`.
  When `keep_collapsed is None` under structure, omit `keepcollapsed` (PostGIS default). Setting
  `keep_collapsed` while `method != "structure"` is a contradictory combo → recommended
  `ValueError` (clean frozen contract, mirrors the Phase-41 "both filter and where" `TypeError`);
  planner may instead document-and-ignore — either way **document the rule**.
- **D-04:** `method="structure"` requires PostGIS ≥ 3.2 / GEOS ≥ 3.10 → **document + passthrough**.
  NO server-version round-trip; PostGIS raises its native error on older servers. Documented in
  the method docstring + the `docs/stability.md` support matrix (and the new methods' stable-tier
  rows).

### simplify surface (D-05)
- **D-05:** `tolerance` is **required** (keyword-only, no default). `preserve_topology=True`
  (default) → `ST_SimplifyPreserveTopology(t.<geom>, %s)` with `tolerance` as `%s`.
  `preserve_topology=False` → `ST_Simplify(t.<geom>, %s, %s)` with `tolerance` + `preserve_collapsed`
  both `%s`. **Expose `preserve_collapsed: bool = False`** — consulted only when
  `preserve_topology=False`. Setting `preserve_collapsed=True` while `preserve_topology=True` is a
  contradictory combo → same disposition as D-03 (recommended `ValueError`, document the rule).

### Edge / error posture (D-06, D-07)
- **D-06 (mixed-SRID, Pitfall 2):** pairwise `union`/`difference`/`intersection` over two columns
  with mismatched SRID → **let PostGIS raise** (no pre-check). Document in docstrings; add a live
  integration test asserting a mixed-SRID pair raises.
- **D-07 (NULL/EMPTY/type-change, Pitfall 4):** `simplify`/`make_valid` may return `NULL` or
  `GEOMETRYCOLLECTION EMPTY`, and `make_valid` may change geometry type (POLYGON→MULTIPOLYGON/
  GEOMETRYCOLLECTION) → **pass through unchanged** (None rows in `gdf`). Document the behavior in
  docstrings. Tests: a self-intersecting (bowtie) polygon → `make_valid` asserts non-NULL repaired
  output; all-points-within-tolerance → `simplify(preserve_topology=True)` asserts non-NULL
  (topology preserved); document that `ST_Simplify` (preserve_topology=False) can return NULL.

### Test strategy (D-08, D-09)
- **D-08:** Two layers — (a) **mock/SQL-shape authoritative** unit tests asserting the generated
  SQL (correct `ST_*` function, `%s` placement, `AS <descriptive_col>`, `filter`/`order_by`/`limit`
  tail) + a **per-builder injection test** (malicious identifier → `InvalidIdentifierError` before
  any SQL is sent); (b) **live integration** on local PostGIS 3.6.4 / GEOS 3.13.1, including the
  NULL-geometry and mixed-SRID fixtures from D-06/D-07.
- **D-09:** `make_valid(method="structure")` is tested **live and authoritative** (local env
  supports it). **PLANNING CHECK:** this assumes CI runs PostGIS ≥ 3.2. If the CI PostGIS floor is
  < 3.2, the planner must guard **only the structure live assertion** with a version/feature skip
  (the mock SQL-shape test stays authoritative and unguarded). Verify CI's PostGIS version during
  planning.

### Signature & parity (D-10, D-11) — carried forward from Phase 41, restated for the new methods
- **D-10:** Signature shape per Phase 41 D-03 — `table` **positional**; everything else
  **keyword-only**: `geom="geometry"`, `schema="public"`, `other_geom` (binary ops), `tolerance`/
  `preserve_topology`/`preserve_collapsed` (simplify), `method`/`keep_collapsed` (make_valid),
  `into="rows"`, `columns`, `filter`, `order_by`, `limit`. The new methods carry **`filter=` only —
  NO `where=` deprecated alias** (the `where=`→`filter=` shim exists solely for the 11 pre-existing
  methods migrated in Phase 41; new builders are born clean to keep signatures clean for the
  Phase-46 mypy-strict / `@overload` pass and the `-W error::DeprecationWarning` gate).
- **D-11:** Sync/async parity is non-negotiable — every method mirrored 1:1 on
  `AsyncSpatialAccessor` (`async def` + `await self._run(...)`), edited in the **same change** as the
  sync class (Phase-41 lesson). Enforced by `test_accessor_parity` **and**
  `test_accessor_parameter_kind_parity` — the keyword-only markers must be identical on both classes.

### Builder mechanics (D-12) — carried forward
- **D-12:** `validate_identifiers(table, schema, geom[, other_geom])` is **line 1** of every
  builder; `columns` validated when provided; all user values (`tolerance`, the make_valid params
  string) go through `%s`. Pure builders return `(sql, params)`; accessor delegates →
  `_check_into(into, name)` → `build_*_sql(...)` → `_run/_arun(sql, params, into, <result_col>)`.
  **None of the six are added to `_SCALAR_HELPERS`** (all return geometry → `into="gdf"` valid).

### Claude's Discretion
- **Builder factoring:** whether `union`/`difference`/`intersection` share a single
  binary-op helper (e.g. `build_binary_op_sql(op_func, ...)`) and whether the unary trio shares a
  helper — encouraged for DRY, but each method MUST keep its own injection test + descriptive
  result column. Research suggests the binary trio share the 2-column shape.
- Exact docstring wording for the NULL/type-change/SRID/version notes (must exist; wording free).
- Final disposition of contradictory-arg combos (D-03/D-05): `ValueError` (recommended) vs
  documented-ignore.
- Plan/wave decomposition (e.g. binary trio + unary trio as two plans).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope & requirements
- `.planning/REQUIREMENTS.md` §"Spatial v2 — Geometric Processing" (SPAT2-01..06) + the
  "Cross-cutting acceptance criteria for every new builder/method" note (line ~22:
  `validate_identifiers` first + injection test + `test_accessor_parity` parity + zero new runtime
  deps) — the locked requirements this phase satisfies.
- `.planning/ROADMAP.md` "Phase 42: Spatial v2 — Processing Helpers" — goal + 5 success criteria.

### Research (HIGH confidence, this milestone)
- `.planning/research/FEATURES.md` §"Workstream 1: Spatial V2 — Geometry Processing"
  (SPAT-V2-01..06) — API shapes, PostGIS signatures, result-column proposals.
  **CAVEAT:** the code blocks there show `where=` (written 2026-06-27, before Phase 41) — use
  `filter=` per D-10; they are otherwise authoritative.
- `.planning/research/PITFALLS.md` — Pitfall 1 (validate_identifiers dropped in builder additions),
  Pitfall 2 (SRID mismatch in binary ops → D-06), Pitfall 4 (NULL/degenerate geometry from
  simplify/make_valid → D-05/D-07), Pitfall 11 (sync/async parity drift → D-11). Also the
  "Looks Done But Isn't" checklist + "Integration Gotchas" table.
- `.planning/research/SUMMARY.md` §"Phase 42: Spatial v2 — Processing Helpers" — rationale,
  delivers, addresses; §"Architecture Approach" (no new accessors; no `_resolve_geometry`).

### Source to modify (templates to copy)
- `pycopg/spatial.py`:
  - `_append_tail` (~line 149) — the `filter`/`order_by`/`limit` tail choke-point.
  - `build_buffer_sql` (~830) + `build_transform_sql` (~898) — **the derived-geometry-column
    builder templates** (validate first → `SELECT {_cols_str(columns)}, <expr> AS <name> FROM
    {schema}.{table} AS t` → `_append_tail(...)` → return `(sql, params)`).
  - `_SCALAR_HELPERS` (959), `_VALID_INTO` (963), `_check_into` (971).
  - `_run` sync (1052) / `_arun` async (2109) — derived col passed as `geometry_column`.
  - `SpatialAccessor.buffer` (1864, `_run(..., "buffer")`) / `transform` (1946,
    `_run(..., "geometry_transformed")`) — **accessor method templates** (incl. `into=` routing);
    `AsyncSpatialAccessor.buffer` (2947) / `transform` (3032) — async mirrors.
  - `SpatialAccessor` class (~1025) / `AsyncSpatialAccessor` class (~2090) — where the 6×2 new
    methods land.
- `pycopg/utils.py` — `validate_identifiers` (the line-1 guard).
- `pycopg/exceptions.py` — `InvalidIdentifierError` (raised by the guard; the injection-test target).

### Conventions & contracts inherited
- `.planning/phases/41-api-homogenization/41-CONTEXT.md` — D-03 (kw-only contract), D-09
  (stacklevel), D-10 (no internal deprecated paths; `-W error::DeprecationWarning` gate), D-11
  (parity). The new methods inherit these.
- `docs/stability.md` (new in Phase 41) — support matrix (PostGIS floor 3.0 hard / 3.2
  recommended). The `make_valid(method="structure")` ≥ 3.2 note + the 6 new methods' stable-tier
  rows land here.
- `tests/test_spatial.py` — existing injection-test + parity-test conventions to extend.
- `.planning/codebase/CONVENTIONS.md`, `.planning/codebase/ARCHITECTURE.md` — builder-pur + lazy
  accessor pattern.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `build_buffer_sql` / `build_transform_sql` — exact templates for a builder that emits a **new
  derived geometry column** (vs the predicate builders that filter); copy their structure.
- `_append_tail(sql, filter, order_by, limit, has_where=False)` — single choke-point for the
  `filter`/`order_by`/`limit` tail; all 6 new builders route through it (`has_where=False`, since
  processing helpers have no built-in WHERE).
- `_check_into(into, helper)` + `_VALID_INTO` — validate `into=` before SQL; do **not** add the 6
  to `_SCALAR_HELPERS`.
- `_run` / `_arun` — `into="gdf"` path uses `_to_named_binds` + `to_geodataframe(geometry_column=…)`;
  pass each helper's descriptive result-column name (D-01) as `geometry_column`.
- `validate_identifiers`, `_cols_str(columns)` — identifier guard + column-list rendering.

### Established Patterns
- Pure module-level `build_*_sql` (DB-free, returns `(sql, params)`) + thin accessor that
  delegates; `SpatialAccessor` and `AsyncSpatialAccessor` are 1:1.
- Derived-geometry helpers pass the **derived** column name (not `geom`) as `geometry_column`
  to `_run` (e.g. `buffer`→`"buffer"`). The new methods follow this with their D-01 names.
- Coverage ratchet ≥95% (baseline 96.09% post-Phase-41); `# pragma: no cover` only with em-dash
  justification.

### Integration Points
- `SpatialAccessor` (+6 methods) and `AsyncSpatialAccessor` (+6 methods) — edit both in one change.
- `tests/test_spatial.py` — add SQL-shape, per-builder injection, live-integration (incl. NULL +
  mixed-SRID fixtures), and parity coverage; `test_accessor_parity` +
  `test_accessor_parameter_kind_parity` must register the 6 new methods.
- Docs: `docs/api-reference.md` spatial rows, the spatial guide page, README spatial method count,
  and `docs/stability.md` (make_valid structure version note + stable-tier rows).

</code_context>

<specifics>
## Specific Ideas

- Milestone framing "un maximum de fonctions sans SQL brut" + the SemVer freeze at 1.0 →
  **expose the full PostGIS knob set now** (`keep_collapsed`, `preserve_collapsed`) rather than
  defer to a 1.x additive release, since the API freezes here.
- The new methods are **born with `filter=` only** — no `where=` deprecated alias. The Phase-41
  shim is exclusively a migration aid for the 11 pre-existing spatial methods.
- The `make_valid` params string is a **user value through `%s`**, never f-string-interpolated.

</specifics>

<deferred>
## Deferred Ideas

- **`gridSize` precision parameter** on `union`/`difference`/`intersection` (SPAT-F01, GEOS ≥ 3.9)
  — explicitly out of the high-level API; callers needing it use raw `db.execute()`. Additive 1.x.
- **Spatial aggregates** (`collect_geometries`/`union_aggregate`/`extent`) → Phase 43 (already
  scheduled, not a deferral).
- **Serialization + MVT** (`as_geojson`/`as_text`/`as_mvt`) → Phase 44 (already scheduled).
- **Constant-geometry inputs** (wkt/geojson/point) for the pairwise ops — excluded by the
  REQUIREMENTS "column-only, no resolver" decision; would be a separate 1.x design if ever wanted.

</deferred>

---

*Phase: 42-Spatial v2 — Processing Helpers*
*Context gathered: 2026-06-28*
