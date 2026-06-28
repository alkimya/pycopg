# Phase 42: Spatial v2 — Processing Helpers - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-28
**Phase:** 42-Spatial v2 — Processing Helpers
**Areas discussed:** Result column naming, make_valid/simplify parameter surface, Edge/error posture, Test strategy

---

## Area selection

| Option | Description | Selected |
|--------|-------------|----------|
| Result column name | Frozen dict key + gdf geometry_column per helper | ✓ |
| make_valid/simplify params | method whitelist, version gate, optional flag exposure | ✓ |
| Edge/error posture | mixed-SRID + NULL/EMPTY handling | ✓ |
| Test strategy | mock + live; structure live vs version-tolerant | ✓ |

**User's choice:** all four areas.

---

## Result column naming

| Option | Description | Selected |
|--------|-------------|----------|
| Per-op descriptive | union_geom / simplified / convex_hull / made_valid / difference / intersection; matches buffer/geometry_transformed precedent | ✓ |
| Uniform result_geom | one name for all six; max homogeneity, loses self-documenting signal, diverges from precedent | |

**User's choice:** Per-op descriptive (Recommended).
**Notes:** Each name is frozen at 1.0 as both the `list[dict]` key and the `into="gdf"` geometry_column (D-01).

---

## make_valid / simplify parameter surface

| Option | Description | Selected |
|--------|-------------|----------|
| structure: document + passthrough | whitelist in Python, let PostGIS raise on < 3.2, no version round-trip | ✓ |
| structure: pre-guard version check | query PostGIS version, raise clear pycopg error on < 3.2 (extra round-trip + code path) | |
| make_valid: expose keep_collapsed | add keep_collapsed (structure's only knob); completes surface, avoids 1.x follow-up | ✓ |
| make_valid: omit keep_collapsed | smaller surface; callers needing it drop to raw SQL | |
| simplify: expose preserve_collapsed | add preserve_collapsed (3-arg ST_Simplify when preserve_topology=False) | ✓ |
| simplify: keep minimal | tolerance + preserve_topology only | |

**User's choice:** document + passthrough; expose keep_collapsed; expose preserve_collapsed (all Recommended).
**Notes:** On-theme with the milestone framing "un maximum de fonctions sans SQL brut" + freezing the surface at 1.0 (D-02..D-05).

---

## Edge / error posture

| Option | Description | Selected |
|--------|-------------|----------|
| Document + test | mixed-SRID lets PostGIS raise; NULL/EMPTY pass through; tests assert documented behavior | ✓ |
| Add guardrails | SRID pre-check / coalesce NULL-EMPTY; more hand-holding, extra frozen behavior + round-trips | |

**User's choice:** Document + test (Recommended).
**Notes:** Matches research recommendation (Pitfalls 2 & 4); no silent rewriting of PostGIS semantics (D-06, D-07).

---

## Test strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Live, authoritative | structure tested live (local PostGIS 3.6.4/GEOS 3.13.1) + NULL/mixed-SRID fixtures | ✓ |
| Version-tolerant skip | wrap structure live test in version/feature skip (v0.8.0 TSL-only pattern) for portability | |

**User's choice:** Live, authoritative (Recommended).
**Notes:** Flagged as a PLANNING CHECK — assumes CI runs PostGIS ≥ 3.2; if the CI floor is lower, planner guards only the structure live assertion (mock SQL-shape test stays authoritative) (D-08, D-09).

---

## Claude's Discretion

- Builder factoring (shared binary/unary helpers vs per-method), provided each keeps its own
  injection test + descriptive result column.
- Exact docstring wording for NULL/type-change/SRID/version notes.
- Contradictory-arg disposition (keep_collapsed without structure; preserve_collapsed with
  preserve_topology): `ValueError` (recommended) vs documented-ignore.
- Plan/wave decomposition.

## Deferred Ideas

- `gridSize` precision parameter on overlay ops (SPAT-F01, GEOS ≥ 3.9) — out of high-level API; 1.x.
- Spatial aggregates → Phase 43; serialization + MVT → Phase 44 (already scheduled).
- Constant-geometry inputs (wkt/geojson/point) for pairwise ops — excluded by column-only/no-resolver.
