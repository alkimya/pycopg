# Phase 43: Spatial v2 — Spatial Aggregates - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-29
**Phase:** 43-Spatial v2 — Spatial Aggregates
**Areas discussed:** group_by ergonomics, extent dual-return, Result column names, NULL/empty posture

---

## group_by ergonomics — type

| Option | Description | Selected |
|--------|-------------|----------|
| `str \| list[str] \| None` | Bare str for single-column (`group_by="region"`), list for composite, None = whole-table; normalize str→[str] internally | ✓ |
| `list[str] \| None` only | Strict per research; always a list; simpler for mypy-strict/@overload | |

**User's choice:** `str | list[str] | None`
**Notes:** Frozen API at 1.0 → add the ergonomic single-string form now; still validates as a list. → D-01.

## group_by ergonomics — columns= fate

| Option | Description | Selected |
|--------|-------------|----------|
| Drop `columns=` entirely | SELECT is just group_by cols + aggregate; cleanest frozen contract, no foot-gun | ✓ |
| Keep `columns=`, document constraint | Signature symmetry but easy misuse → server error not InvalidIdentifierError | |

**User's choice:** Drop columns= entirely
**Notes:** SQL forbids non-grouped non-aggregate columns; group_by cols are the only legal non-agg select. → D-02.

---

## extent dual-return — SRID source

| Option | Description | Selected |
|--------|-------------|----------|
| `srid=4326` keyword param | int(srid)-interpolated (existing pattern); library-wide default; caller overrides | ✓ |
| `srid` required when into='gdf' | No default; raises ValueError if missing; forces explicit CRS | |
| Infer SRID from the column | Find_SRID round-trip; breaks pure-builder shape; not recommended | |

**User's choice:** srid=4326 keyword param
**Notes:** box2d loses the SRID; 4326 is the library default; int(srid) is injection-safe. → D-05.

## extent dual-return — output shape

| Option | Description | Selected |
|--------|-------------|----------|
| Builder takes into=, emits the right SQL | One `build_extent_sql(..., into)`; ::text for rows, ST_SetSRID(...::geometry, srid) for gdf; NOT in _SCALAR_HELPERS | ✓ |
| Two separate builders | build_extent_text_sql + build_extent_geom_sql; keeps builder into-agnostic but duplicates | |

**User's choice:** Builder takes into=, emits the right SQL
**Notes:** The box2d-vs-geometry return is intrinsic to ST_Extent — can't be routed purely in _run. One builder + one branch (DRY). → D-04.

---

## Result column names (frozen at 1.0)

| Option | Description | Selected |
|--------|-------------|----------|
| collected / dissolved / extent | 'dissolved' = GIS term for ST_Union-aggregate; avoids reusing Phase 42's pairwise 'union_geom' | ✓ |
| collected / union_geom / extent | Matches pairwise union's column name but blurs the two distinct unions | |
| collection / unioned / extent | 'collection' noun-y; 'unioned' plainer than 'dissolved' | |

**User's choice:** collected / dissolved / extent
**Notes:** Frozen as BOTH the list[dict] key and the gdf geometry_column. → D-06.

---

## NULL / empty-aggregate posture

| Option | Description | Selected |
|--------|-------------|----------|
| Pass-through, document + test | Return the NULL-geometry row as-is; document + intentional-NULL fixture; consistent with Phase 42 D-07; satisfies SPAT2 criterion 3 | ✓ |
| Filter out NULL aggregate rows | HAVING <agg> IS NOT NULL; hides empty groups; surprising zero-row whole-table case; diverges from let-PostGIS-behave posture | |

**User's choice:** Pass-through, document + test
**Notes:** PostGIS aggregates skip NULL inputs; an all-NULL/empty group yields one NULL-aggregate row (whole-table always one row). → D-07.

---

## Claude's Discretion

- Aggregate-tail mechanism (D-03): extend `_append_tail` with optional `group_by` arg vs a small new helper — planner's call.
- Builder factoring: share `_build_agg_geom_sql` for collect_geometries + union_aggregate; extent its own builder. Each keeps its own injection test + frozen result column.
- Group-column `t.` alias qualification — consistency-preferred but free.
- Exact docstring wording for the NULL/box2d/SRID notes.
- Plan/wave decomposition.

## Deferred Ideas

- Serialization + MVT (`as_geojson`/`as_text`/`as_mvt`) → Phase 44 (scheduled).
- `gridSize` precision on `union_aggregate` (SPAT-F01, GEOS ≥ 3.9) → additive 1.x.
- 2-geometry `ST_Collect(g1, g2)` form — only the aggregate form is in scope.
- `HAVING`-style group filtering — not requested; raw `db.execute()` covers it.
