# Phase 52: Spatial Finish - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-04
**Phase:** 52-spatial-finish
**Areas discussed:** gridSize policy, point_on_surface shape, disjoint semantics, output conventions

---

## gridSize policy (SPAT-F01)

### gridSize= validation

| Option | Description | Selected |
|--------|-------------|----------|
| Pure passthrough | No client-side guard; bind gridSize as %s, let PostGIS interpret all floats. Matches buffer + D-06 SRID passthrough. | ✓ |
| Guard negatives | Raise ValueError if gridSize < 0 (make_valid-style guard). Rejects PostGIS's legit 'disable grid' semantics. | |

### Version gating (needs PostGIS ≥3.1 / GEOS ≥3.9)

| Option | Description | Selected |
|--------|-------------|----------|
| Passthrough native error | No server-version pre-check; older servers raise native PostGIS error (D-04 make_valid precedent). Document requirement in docstring. | ✓ |
| Client-side pre-check | Query server version, raise friendly error before round-trip. Costs a round-trip + inconsistent with make_valid. | |

**User's choice:** Pure passthrough + passthrough native error.
**Notes:** Byte-identical None path is already locked by the ROADMAP success criterion; no numeric range is genuinely invalid in PostGIS, so a guard adds no value.

---

## point_on_surface shape (SPAT-F04)

| Option | Description | Selected |
|--------|-------------|----------|
| Geometry point column | Return a 'point_on_surface' geometry column; into='rows'/'gdf' like envelope. Preserves SRID + geometry-ness. | ✓ |
| Mirror centroid (scalar x/y) | Return scalar pos_x/pos_y, rows-only, byte-symmetric with centroid. Discards geometry + SRID. | |
| Both x/y AND geometry | Emit geometry + x/y scalars. Widest surface, inconsistent with one-result-per-helper convention. | |

**User's choice:** Geometry point column.
**Notes:** Divergence from centroid's scalar shape is intentional — the guaranteed-inside label/marker point is most useful as a real geometry for mapping/gdf.

---

## disjoint semantics (SPAT-F06)

### ref= behavior

| Option | Description | Selected |
|--------|-------------|----------|
| Uniform EXISTS, documented | disjoint supports all 4 input forms like siblings; docstring warns ref= means 'EXISTS a disjoint ref row' not 'disjoint from all'. Faithful to SPAT-F06 (pairwise DE-9IM). | ✓ |
| Omit ref= for disjoint | Single-geometry forms only; avoids footgun but breaks input-form parity. | |
| Special-case as NOT EXISTS(intersects) | ref= = 'disjoint from ALL ref rows'; more useful but invents set-semantics not asked for. | |

### Index caveat (ST_Disjoint can't use spatial indexes)

| Option | Description | Selected |
|--------|-------------|----------|
| Document in docstring | Perf note pointing to NOT ST_Intersects / filter= for large indexed tables. Zero code cost. | ✓ |
| Leave silent | Uniform docstrings; users hit the perf cliff unaided. | |

**User's choice:** Uniform EXISTS (documented) + document index caveat.
**Notes:** overlaps/touches/crosses mirror intersects mechanically — no decision needed there.

---

## output conventions (SPAT-F02/F03/F05)

### Result-column AS labels

| Option | Description | Selected |
|--------|-------------|----------|
| Bare operation names | length/envelope/point_on_surface/is_valid/is_valid_reason. Matches majority convention (difference/intersection/area). | ✓ |
| _geom suffix on geometry cols | envelope_geom/point_on_surface_geom to match union_geom. Less uniform. | |

### length unit handling

| Option | Description | Selected |
|--------|-------------|----------|
| Mirror area/perimeter | unit='m' (::geography → meters) or 'srid'; identical signature + _validate_unit. Document 0-for-non-linear. | ✓ |
| No unit= (raw ST_Length) | Always SRID units, no cast/param. Breaks symmetry, gives degrees for geographic SRIDs. | |

**User's choice:** Bare operation names + mirror area/perimeter unit handling.
**Notes:** union_geom stays the lone historical naming exception; no _geom suffix on new columns.

---

## Claude's Discretion

- `@overload` stub shapes, numpydoc docstring wording, injection-test structure, `_run` wiring — standard pattern-following from the shipped `build_*_sql` + accessor + async-mirror template.

## Deferred Ideas

None — discussion stayed within phase scope. Raster (RASTER-F01) and CDC (ETL-INC-F05) remain in the frozen backlog per the milestone decision; not re-litigated.
