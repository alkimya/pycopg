# Phase 42: Spatial v2 — Processing Helpers — Research

**Researched:** 2026-06-29
**Domain:** PostGIS geometry processing (ST_Union/Difference/Intersection/Simplify/ConvexHull/MakeValid) on top of the existing `pycopg/spatial.py` builder-pur pattern
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01** Result column names: `union`→`union_geom`, `simplify`→`simplified`, `convex_hull`→`convex_hull`, `make_valid`→`made_valid`, `difference`→`difference`, `intersection`→`intersection`. Frozen as both the `list[dict]` key AND the `into="gdf"` `geometry_column` arg passed to `_run`/`_arun`.
- **D-02** `method` whitelist = `{None, "linework", "structure"}`. Validate **after** `validate_identifiers`, **before** any SQL — unknown value raises `ValueError`. `method=None` → `ST_MakeValid(t.<geom>)`. `method` in `{"linework","structure"}` → `ST_MakeValid(t.<geom>, %s)` with the params string as `%s` (never f-string).
- **D-03** Expose `keep_collapsed: bool | None = None` — only meaningful when `method="structure"`. Builds `"method=structure keepcollapsed=true|false"`. Setting `keep_collapsed` while `method != "structure"` → recommended `ValueError`. `keep_collapsed is None` under structure → omit `keepcollapsed` (PostGIS default).
- **D-04** `method="structure"` requires PostGIS ≥ 3.2 / GEOS ≥ 3.10 → **document + passthrough**. NO server-version round-trip.
- **D-05** `tolerance` is **required** (keyword-only, no default). `preserve_topology=True` (default) → `ST_SimplifyPreserveTopology(t.<geom>, %s)`. `preserve_topology=False` → `ST_Simplify(t.<geom>, %s, %s)` with `tolerance` + `preserve_collapsed` both `%s`. Expose `preserve_collapsed: bool = False`. Setting `preserve_collapsed=True` while `preserve_topology=True` → recommended `ValueError`.
- **D-06** Mixed-SRID pairwise → **let PostGIS raise** (no pre-check). Document in docstrings; add a live integration test asserting a mixed-SRID pair raises.
- **D-07** NULL/EMPTY/type-change → **pass through unchanged**. Document. Tests: bowtie polygon → `make_valid` asserts non-NULL repaired output; all-points-within-tolerance → `simplify(preserve_topology=True)` asserts non-NULL.
- **D-08** Two test layers: (a) mock/SQL-shape authoritative unit tests + per-builder injection test; (b) live integration including NULL + mixed-SRID fixtures.
- **D-09** PLANNING CHECK (resolved in this research — see §CI PostGIS Version below): `make_valid(method="structure")` tested **live and authoritative**; guard only the live `structure` assertion if CI PostGIS < 3.2.
- **D-10** Signature: `table` **positional**; everything else **keyword-only**. New methods carry `filter=` ONLY — NO `where=` deprecated alias.
- **D-11** Sync/async parity non-negotiable: edit both classes in the **same change**. Enforced by `test_accessor_parity` AND `test_accessor_parameter_kind_parity`.
- **D-12** `validate_identifiers(table, schema, geom[, other_geom])` is **line 1** of every builder. `columns` validated when provided. All user values via `%s`. None of the six added to `_SCALAR_HELPERS`.

### Claude's Discretion

- Whether `union`/`difference`/`intersection` share a single `build_binary_op_sql(op_func, ...)` helper — encouraged for DRY; each must keep its own injection test + descriptive result column.
- Whether the unary trio shares a helper.
- Exact docstring wording for NULL/type-change/SRID/version notes (must exist; wording free).
- Final disposition of contradictory-arg combos (D-03/D-05): `ValueError` (recommended) vs documented-ignore.
- Plan/wave decomposition (e.g. binary trio + unary trio as two plans).

### Deferred Ideas (OUT OF SCOPE)

- `gridSize` precision parameter on `union`/`difference`/`intersection` (SPAT-F01, GEOS ≥ 3.9) — additive 1.x.
- Spatial aggregates (`collect_geometries`/`union_aggregate`/`extent`) → Phase 43.
- Serialization + MVT (`as_geojson`/`as_text`/`as_mvt`) → Phase 44.
- Constant-geometry inputs (wkt/geojson/point) for the pairwise ops — column-only by requirement.
- Transaction control, named params, health, logging, mypy-strict — Phases 45–46.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SPAT2-01 | User can compute the pairwise union of two geometry columns via `db.spatial.union(table, geom, other_geom, ...)` (ST_Union) | `build_binary_op_sql("ST_Union", ...)` pattern; result col `union_geom` |
| SPAT2-02 | User can simplify a geometry column via `db.spatial.simplify(table, geom, tolerance, preserve_topology=True)` (ST_SimplifyPreserveTopology by default) | Two-branch builder; `tolerance` required kw-only; result col `simplified` |
| SPAT2-03 | User can compute the convex hull of a geometry column via `db.spatial.convex_hull(table, geom, ...)` (ST_ConvexHull) | Simplest unary builder; no extra params; result col `convex_hull` |
| SPAT2-04 | User can repair invalid geometries via `db.spatial.make_valid(table, geom, method=None)` (ST_MakeValid; whitelist; `method="structure"` ≥ 3.2) | Params-string builder; whitelist guard; documented passthrough for version |
| SPAT2-05 | User can compute the difference of two geometry columns via `db.spatial.difference(table, geom, other_geom, ...)` (ST_Difference) | Same binary shape as union; result col `difference` |
| SPAT2-06 | User can compute the intersection of two geometry columns via `db.spatial.intersection(table, geom, other_geom, ...)` (ST_Intersection) | Same binary shape; result col `intersection` |
</phase_requirements>

---

## Summary

Phase 42 adds 6 geometry-processing methods to `SpatialAccessor` and `AsyncSpatialAccessor` using the existing **builder-pur** pattern established in `pycopg/spatial.py`. The implementation is straightforward: three pairwise (binary, 2-column) builders and three unary (single-column) builders, each following the `build_buffer_sql`/`build_transform_sql` template exactly. No new infrastructure is needed — all machinery (`_check_into`, `_append_tail`, `_run`/`_arun`, `validate_identifiers`, `_cols_str`) exists and is reused unchanged.

The single concrete external fact to verify (D-09) is resolved: the CI image `timescale/timescaledb-ha:pg17` installs `postgresql-17-postgis-3` from Ubuntu pgdg, which ships **PostGIS 3.6.4** [VERIFIED: ubuntuupdates.org + Dockerfile]. This is well above the 3.2 floor for `ST_MakeValid(method="structure")`, so the live `structure` assertion requires NO CI guard — the mock SQL-shape test and the live integration test are both authoritative and unguarded.

The primary research outcomes are: (1) exact PostGIS function signatures for all 6 operations, (2) the `make_valid` params string assembly format, (3) a verified factoring recommendation for the binary trio and the Claude's-discretion unary factoring, (4) concrete contradictory-arg patterns matching the project's existing `ValueError`/`TypeError` conventions, (5) concrete test fixtures for NULL/EMPTY/bowtie/mixed-SRID edge cases, and (6) a complete Validation Architecture covering all three test layers D-08 specifies.

**Primary recommendation:** Follow `build_buffer_sql` as the template for each builder. Share a `build_binary_op_sql` internal helper for the three binary ops (DRY; each still has its own `build_union_sql`/`build_difference_sql`/`build_intersection_sql` public wrapper for clarity and individual injection tests). The unary trio is simple enough that individual builders without a shared helper are also fine — the planner decides.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| SQL builder (PostGIS expression assembly) | Module-level pure functions in `pycopg/spatial.py` | — | Stateless, no I/O; shared byte-identical between sync/async accessors |
| Identifier validation + injection guard | Module-level pure functions (`validate_identifiers` in `utils.py`) | — | Called line-1 by every builder; security invariant |
| `into=` routing and PostGIS guard | `SpatialAccessor` / `AsyncSpatialAccessor` methods | — | Thin accessor delegates to builder then `_run`/`_arun` |
| Result delivery (rows/GDF) | `_run` (sync) / `_arun` (async) in accessor classes | `_to_named_binds` for GDF path | Already exists; no changes needed |
| Tests | `tests/test_spatial.py` | `tests/test_parity.py` | SQL-shape + injection + parity + live integration |
| Docs | `docs/stability.md` (new stable-tier rows) | API reference spatial table | 6 new method rows land in stability.md |

---

## Standard Stack

### Core (no changes — reuse verbatim)

| Component | Version | Purpose | Source |
|-----------|---------|---------|--------|
| `pycopg/spatial.py` | current | Add 6 builders + 12 accessor methods (6 sync + 6 async) | [VERIFIED: codebase read] |
| `pycopg/utils.py` `validate_identifiers` | current | Line-1 guard; reused unchanged | [VERIFIED: codebase read] |
| `pycopg/exceptions.py` `InvalidIdentifierError` | current | Raised by `validate_identifiers`; the injection-test target | [VERIFIED: codebase read] |
| PostGIS `ST_Union(geomA, geomB)` | 3.0+ | Pairwise geometry union (scalar 2-arg form, not aggregate) | [CITED: postgis.net/docs/ST_Union.html] |
| PostGIS `ST_Difference(geomA, geomB)` | 3.0+ | Set difference (A minus B) | [CITED: postgis.net/docs/ST_Difference.html] |
| PostGIS `ST_Intersection(geomA, geomB)` | 3.0+ | Shared portion of two geometries | [CITED: postgis.net/docs/ST_Intersection.html] |
| PostGIS `ST_SimplifyPreserveTopology(geom, tol)` | 3.0+ | Topology-safe simplification (default path) | [CITED: postgis.net/docs/ST_SimplifyPreserveTopology.html] |
| PostGIS `ST_Simplify(geom, tol[, preserveCollapsed])` | 3.0+ | Fast simplification; can return NULL | [CITED: postgis.net/docs/ST_Simplify.html] |
| PostGIS `ST_ConvexHull(geom)` | 3.0+ | Minimum convex polygon | [CITED: postgis.net/docs/ST_ConvexHull.html] |
| PostGIS `ST_MakeValid(geom)` | 3.0+ | Geometry repair (default algorithm) | [CITED: postgis.net/docs/ST_MakeValid.html] |
| PostGIS `ST_MakeValid(geom, params_text)` | 3.2+ | Geometry repair with algorithm selection (`method=structure` requires GEOS ≥ 3.10) | [CITED: postgis.net/docs/ST_MakeValid.html] |

### Package Legitimacy Audit

This phase installs **no new packages** — only modifying existing source files in `pycopg/spatial.py`, `tests/test_spatial.py`, `tests/test_parity.py`, and `docs/stability.md`. No legitimacy audit required.

---

## CI PostGIS Version — D-09 Resolution

**Finding (HIGH confidence, VERIFIED):**

The CI workflow (`tests.yml` line 20) uses Docker image `timescale/timescaledb-ha:pg17`. The Dockerfile for this image ([GitHub: timescale/timescaledb-docker-ha](https://github.com/timescale/timescaledb-docker-ha)) sets `ARG POSTGIS_VERSIONS="3"` and installs `postgresql-17-postgis-3` from the Ubuntu pgdg repository. The current `postgresql-17-postgis-3` package on Ubuntu jammy-pgdg is **version 3.6.4+dfsg-2.pgdg22.04+1** — PostGIS **3.6.4** [VERIFIED: ubuntuupdates.org pgdg package page].

**Consequence for D-09:**
- PostGIS 3.6.4 >> PostGIS 3.2 floor → `ST_MakeValid(method="structure")` is fully supported in CI.
- The live `make_valid(method="structure")` assertion requires **NO version-guard or `pytest.mark.skipif`**.
- Both the mock SQL-shape test AND the live integration test for `structure` are authoritative and unguarded.
- Local env (PostGIS 3.6.4 / GEOS 3.13.1) is identical to CI. No fixture divergence.

---

## Architecture Patterns

### System Architecture Diagram

```
User code
    │
    ▼
db.spatial.union("table", other_geom="geom2", ...)     ← accessor method (kw-only contract)
    │
    ├─ 1. _check_into(into, "union")                   ← validates into= before any SQL
    ├─ 2. build_union_sql(table, geom, schema,         ← pure module-level builder
    │        other_geom, columns, filter,              ← validate_identifiers LINE 1
    │        order_by, limit)                          ← returns (sql, params)
    │         │
    │         ├─ validate_identifiers(table, schema, geom, other_geom)
    │         ├─ if columns: validate_identifiers(*columns)
    │         ├─ sql = "SELECT {cols}, ST_Union(t.{geom}, t.{other_geom}) AS union_geom FROM {schema}.{table} AS t"
    │         └─ sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    │
    └─ 3. self._run(sql, params, into, "union_geom")   ← routes on into=
              │
              ├─ into="rows"  → db.execute(sql, params)           → list[dict]
              └─ into="gdf"   → _to_named_binds → db.to_geodataframe(geometry_column="union_geom") → GeoDataFrame
```

### Recommended Project Structure (changes only)

```
pycopg/
└── spatial.py        # Add 6 build_*_sql builders + 6 SpatialAccessor methods
                      # + 6 AsyncSpatialAccessor methods (same file, same change)
tests/
└── test_spatial.py   # Add SQL-shape, injection, live integration tests
                      # + _HELPER_CALLS / _GDF_CALLS registration for 6 new methods
tests/
└── test_parity.py    # Add v1_processing_surface frozenset test (like v080/v090 patterns)
docs/
└── stability.md      # Add 6 rows to db.spatial.* table + make_valid ≥3.2 note
```

### Pattern 1: Binary Op Builder (DRY — Claude's Discretion)

The three binary ops (`union`, `difference`, `intersection`) share an identical SQL template shape: `SELECT {cols}, ST_<Op>(t.{geom}, t.{other_geom}) AS {result_col} FROM {schema}.{table} AS t`. A shared internal helper is cleaner:

```python
# Source: derived from existing build_buffer_sql / build_transform_sql templates
# in pycopg/spatial.py (verified by codebase read)

def _build_binary_geom_sql(
    op_func: str,           # "ST_Union", "ST_Difference", "ST_Intersection"
    result_col: str,        # "union_geom", "difference", "intersection"
    table: str,
    geom: str,
    schema: str,
    *,
    other_geom: str,
    columns: list[str] | None,
    filter: str | None,
    order_by: str | None,
    limit: int | None,
) -> tuple[str, list]:
    # validate_identifiers is LINE 1 — security invariant
    validate_identifiers(table, schema, geom, other_geom)
    if columns:
        validate_identifiers(*columns)
    sql = (
        f"SELECT {_cols_str(columns)}, "
        f"{op_func}(t.{geom}, t.{other_geom}) AS {result_col} "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []


def build_union_sql(table, geom="geometry", schema="public", *, other_geom, ...) -> tuple[str, list]:
    return _build_binary_geom_sql("ST_Union", "union_geom", table, geom, schema, other_geom=other_geom, ...)

def build_difference_sql(table, geom="geometry", schema="public", *, other_geom, ...) -> tuple[str, list]:
    return _build_binary_geom_sql("ST_Difference", "difference", table, geom, schema, other_geom=other_geom, ...)

def build_intersection_sql(table, geom="geometry", schema="public", *, other_geom, ...) -> tuple[str, list]:
    return _build_binary_geom_sql("ST_Intersection", "intersection", table, geom, schema, other_geom=other_geom, ...)
```

**Each public `build_*_sql` function must still have its own dedicated injection test** — `_build_binary_geom_sql` is internal and has no injection test of its own.

### Pattern 2: Simplify Builder (two SQL variants)

```python
# Source: D-05 locked decision + ST_Simplify/ST_SimplifyPreserveTopology PostGIS signatures
# [CITED: postgis.net/docs]

def build_simplify_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    tolerance: float,                   # required kw-only
    preserve_topology: bool = True,     # True → ST_SimplifyPreserveTopology (safe default)
    preserve_collapsed: bool = False,   # only consulted when preserve_topology=False
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    validate_identifiers(table, schema, geom)               # LINE 1
    if columns:
        validate_identifiers(*columns)
    # Contradictory-arg guard (D-05 recommendation)
    if preserve_collapsed and preserve_topology:
        raise ValueError(
            "preserve_collapsed=True has no effect when preserve_topology=True; "
            "set preserve_topology=False to use ST_Simplify with preserve_collapsed."
        )
    if preserve_topology:
        expr = f"ST_SimplifyPreserveTopology(t.{geom}, %s)"
        params = [tolerance]
    else:
        expr = f"ST_Simplify(t.{geom}, %s, %s)"
        params = [tolerance, preserve_collapsed]
    sql = (
        f"SELECT {_cols_str(columns)}, {expr} AS simplified "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, params
```

### Pattern 3: make_valid Builder (params string assembly)

```python
# Source: D-02/D-03/D-04 locked decisions + ST_MakeValid PostGIS signature
# [CITED: postgis.net/docs/ST_MakeValid.html]

def build_make_valid_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    method: str | None = None,          # None | "linework" | "structure"
    keep_collapsed: bool | None = None, # only for method="structure"
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    validate_identifiers(table, schema, geom)               # LINE 1
    if columns:
        validate_identifiers(*columns)
    # method whitelist guard (D-02) — AFTER validate_identifiers
    _VALID_MAKE_VALID_METHODS = {None, "linework", "structure"}
    if method not in _VALID_MAKE_VALID_METHODS:
        raise ValueError(
            f"method must be one of {sorted(str(m) for m in _VALID_MAKE_VALID_METHODS)}, "
            f"got {method!r}"
        )
    # Contradictory-arg guard (D-03 recommendation)
    if keep_collapsed is not None and method != "structure":
        raise ValueError(
            "keep_collapsed is only valid when method='structure'; "
            f"got method={method!r}"
        )
    if method is None:
        expr = f"ST_MakeValid(t.{geom})"
        params = []
    else:
        # Build params string — always a %s value, never f-string (D-02)
        if method == "linework":
            params_str = "method=linework"
        else:  # "structure"
            if keep_collapsed is None:
                params_str = "method=structure"
            elif keep_collapsed:
                params_str = "method=structure keepcollapsed=true"
            else:
                params_str = "method=structure keepcollapsed=false"
        expr = f"ST_MakeValid(t.{geom}, %s)"
        params = [params_str]
    sql = (
        f"SELECT {_cols_str(columns)}, {expr} AS made_valid "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, params
```

### Pattern 4: convex_hull Builder (simplest unary)

```python
# Source: ST_ConvexHull PostGIS signature [CITED: postgis.net/docs/ST_ConvexHull.html]

def build_convex_hull_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    validate_identifiers(table, schema, geom)               # LINE 1
    if columns:
        validate_identifiers(*columns)
    sql = (
        f"SELECT {_cols_str(columns)}, ST_ConvexHull(t.{geom}) AS convex_hull "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []
```

### Pattern 5: Accessor Method Shape (sync template)

```python
# Source: SpatialAccessor.buffer ~line 1864 (verified by codebase read)

def union(
    self,
    table: str,              # positional (D-10)
    *,                       # everything after is keyword-only (D-10)
    geom: str = "geometry",
    schema: str = "public",
    other_geom: str,         # required kw-only — no default
    into: str = "rows",
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict] | gpd.GeoDataFrame:
    """..."""
    _check_into(into, "union")
    sql, params = build_union_sql(
        table, geom=geom, schema=schema, other_geom=other_geom,
        columns=columns, filter=filter, order_by=order_by, limit=limit,
    )
    return self._run(sql, params, into, "union_geom")   # D-01 result col name
```

**The async mirror is identical but prefixed `async def` and uses `await self._run(...)`:**

```python
async def union(self, table: str, *, geom="geometry", schema="public",
                other_geom: str, into="rows", columns=None, filter=None,
                order_by=None, limit=None) -> list[dict] | gpd.GeoDataFrame:
    await self._check_postgis()
    _check_into(into, "union")
    sql, params = build_union_sql(...)
    return await self._run(sql, params, into, "union_geom")
```

**Note:** Sync `SpatialAccessor` calls `_check_into` BEFORE calling the builder. Async `AsyncSpatialAccessor` calls `await self._check_postgis()` FIRST (PostGIS guard), then `_check_into`, then builder. Verify this ordering is consistent with the existing `buffer`/`transform` templates.

### Anti-Patterns to Avoid

- **Dropping `validate_identifiers` from a new builder** — the v0.10.0 COPY rewrite precedent: test suite stays green, injection vulnerability ships. Line 1, always.
- **Adding the 6 new helpers to `_SCALAR_HELPERS`** — they all return geometry columns; `into="gdf"` must be valid for all six.
- **Using f-string interpolation for `method` or the make_valid params string** — must go through `%s` (D-02). The params string is assembled in Python and then bound as a single `%s` value.
- **Adding `where=` deprecated alias to the new builders** — the shim is exclusively for the 11 pre-Phase-41 methods. New methods are born clean (D-10).
- **Writing sync and async methods in separate commits** — Phase 41 lesson: kind-parity divergence is caught only at commit time by `test_accessor_parameter_kind_parity`. Both classes in one change.
- **Emitting `int(tolerance)` instead of `%s` for numeric values** — the `int()` shortcut is only safe for SRID. `tolerance` is a float and must be `%s`.

---

## Make_Valid Params String: Exact Assembly

The PostGIS `ST_MakeValid(geom, params_text)` accepts a text parameter in the format `"method=<method> [keepcollapsed=<bool>]"`. [CITED: postgis.net/docs/ST_MakeValid.html]

**Exact strings that are valid for the `%s` parameter value:**

| `method` arg | `keep_collapsed` arg | Params string passed as `%s` |
|-------------|---------------------|------------------------------|
| `"linework"` | `None` (default) | `"method=linework"` |
| `"linework"` | `True` | RAISE `ValueError` (contradictory) |
| `"linework"` | `False` | RAISE `ValueError` (contradictory) |
| `"structure"` | `None` (default) | `"method=structure"` (PostGIS uses its own default for keepcollapsed) |
| `"structure"` | `True` | `"method=structure keepcollapsed=true"` |
| `"structure"` | `False` | `"method=structure keepcollapsed=false"` |
| `None` (default) | `None` (default) | No second arg — `ST_MakeValid(t.geom)` form |
| `None` | `True` or `False` | RAISE `ValueError` (contradictory) |

**Why `method=linework` with `keep_collapsed` is a contradiction:** `keepcollapsed` only applies to the `structure` algorithm. The PostGIS docs do not define its behavior for `linework`. Raising `ValueError` early is cleaner than silently ignoring the value.

---

## Contradictory-Arg Disposition (D-03, D-05)

**Recommendation: `ValueError` in all cases** — consistent with the project's existing pattern.

Evidence from codebase:
- `_validate_unit(unit)` in `spatial.py` raises `ValueError` for unknown `unit=` values [VERIFIED: codebase read, line 63-67]
- `_check_into(into, helper)` raises `ValueError` for unknown `into=` values [VERIFIED: codebase read, line 987-993]
- `_resolve_geometry(...)` raises `ValueError` for zero/multiple geometry inputs [VERIFIED: codebase read, line 116]

The Phase 41 `TypeError` for `both 'filter' and 'where'` is a different shape: it's ambiguity (user passed two competing *routing* args). The contradictory combos in D-03/D-05 are semantic conflicts between *value* parameters — `ValueError` is the correct Python convention for invalid argument values. [ASSUMED — semantic distinction not officially documented but consistent with Python stdlib]

**Guard placement in builder (not in accessor):** The `ValueError` for contradictory args is raised in the builder, **after** `validate_identifiers` (D-02 ordering for `make_valid`), before SQL assembly. This is consistent with how `_validate_unit` is called inside the builder.

---

## NULL/EMPTY/Type-Change Test Fixtures

### Fixture 1: Bowtie (self-intersecting) polygon for `make_valid`

```python
# Source: D-07 + PITFALLS.md Pitfall 4
# A figure-eight bowtie: outer ring crosses itself at the origin.
# ST_MakeValid converts this to a MULTIPOLYGON or GEOMETRYCOLLECTION.
BOWTIE_WKT = "POLYGON((0 0, 1 1, 1 0, 0 1, 0 0))"

# Insert into test table:
# INSERT INTO "{t}" VALUES (1, ST_GeomFromText('POLYGON((0 0, 1 1, 1 0, 0 1, 0 0))', 4326))

# Assertion: result is non-NULL and non-empty (repair succeeded)
rows = sdb.spatial.make_valid(t, columns=["id"])
assert rows[0]["made_valid"] is not None
# Also verify the geometry type has changed (POLYGON → MULTIPOLYGON or similar)
# This is documented behavior, not an error.
```

### Fixture 2: All-points-within-tolerance for `simplify`

```python
# Source: D-07 + PITFALLS.md Pitfall 4
# A very small polygon where all points are within tolerance of each other.
# ST_SimplifyPreserveTopology (preserve_topology=True) MUST return non-NULL.
# ST_Simplify (preserve_topology=False) CAN return NULL for this input.
TINY_POLYGON_WKT = "POLYGON((0 0, 0.0001 0, 0.0001 0.0001, 0 0.0001, 0 0))"
TOLERANCE = 1.0   # 1 degree — much larger than the polygon

# Assertion (preserve_topology=True): non-NULL (topology preserved)
rows = sdb.spatial.simplify(t, tolerance=TOLERANCE, preserve_topology=True, columns=["id"])
assert rows[0]["simplified"] is not None   # ST_SimplifyPreserveTopology guarantees this

# Document-only (do NOT assert NULL for preserve_topology=False):
# ST_Simplify with tolerance > polygon size may return NULL — documented behavior.
# Test: assert the call succeeds without exception (NULL is a valid result).
rows = sdb.spatial.simplify(t, tolerance=TOLERANCE, preserve_topology=False, columns=["id"])
# No assertion on rows[0]["simplified"] value — NULL is documented and valid.
```

### Fixture 3: Mixed-SRID pair for binary ops (D-06)

```python
# Source: D-06 locked decision + PITFALLS.md Pitfall 2
# Two geometry columns with different SRIDs — PostGIS raises at query time.
# Table must have geom_a in SRID 4326 and geom_b in SRID 32632.
# CREATE TABLE "{t}" (id INT, geom_a geometry(Point, 4326), geom_b geometry(Point, 32632))

import psycopg  # or any psycopg3 exception
with pytest.raises(Exception):   # psycopg.errors.InvalidParameterValue or similar
    sdb.spatial.union(t, geom="geom_a", other_geom="geom_b")
```

**Note on exception type for mixed-SRID:** PostGIS raises a PostgreSQL error that surfaces as a psycopg3 `ProgrammingError` or `psycopg.errors.InvalidParameterValue`. The test should use `pytest.raises(Exception)` broadly or import `psycopg.errors.InternalError` — do NOT wrap in a pycopg domain exception (D-06: let PostGIS raise natively, just document it).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Params string construction for ST_MakeValid | String interpolation of user values | Python string concat of whitelisted literals assigned to `%s` | All literal values ("method=linework", "keepcollapsed=true") are programmer-controlled — the only user value is `method` which is whitelisted. The assembled string goes through `%s`, never f-string. |
| SRID mismatch detection | Pre-query SRID lookup with additional DB round-trip | Let PostGIS raise (D-06) | The mixed-SRID check would require fetching `ST_SRID(col)` for both columns — adds latency, adds complexity, doesn't prevent concurrent SRID changes. PostGIS error is clear enough. |
| Geometry validity pre-check | Calling `ST_IsValid` before `ST_MakeValid` | Just call `ST_MakeValid` | ST_MakeValid operates on both valid and invalid geometries safely — no pre-check needed. |
| PostGIS version guard for `make_valid(method="structure")` | Version introspection at runtime | Document + passthrough; let PostGIS raise on old servers (D-04) | Saves a DB round-trip on every call; CI and local env are both 3.6.4 — no guard needed. |

**Key insight:** The builder-pur pattern entirely eliminates the "where do I put validation?" question. All validation (identifier, whitelist, contradictory-args) goes in the builder. The accessor adds only PostGIS availability check + `_check_into` + routing.

---

## Common Pitfalls

### Pitfall 1: validate_identifiers Dropped in New Builder

**What goes wrong:** A new `build_*_sql` function omits `validate_identifiers` as line 1. The SQL still assembles correctly; the test suite stays green. SQL injection vulnerability ships. This is not hypothetical — it happened in v0.10.0 (COPY rewrite, commit 863e894).

**Why it happens:** New builder is written by following the SQL template but not internalizing the security invariants in the module docstring.

**How to avoid:** Every plan task that adds a builder must list `validate_identifiers(table, schema, geom[, other_geom])` as line 1. Every new builder gets a dedicated injection test asserting `InvalidIdentifierError` on `table="'; DROP TABLE users; --"`. This test is the compile-time guarantee.

**Warning signs:** A `build_*_sql` whose first non-comment statement is not `validate_identifiers`.

### Pitfall 2: Adding New Helpers to `_SCALAR_HELPERS`

**What goes wrong:** One of the 6 new helpers is accidentally added to `_SCALAR_HELPERS` (the frozenset controlling `into="gdf"` rejection). All 6 return geometry columns — `into="gdf"` must be valid. Adding to `_SCALAR_HELPERS` causes `ValueError` for any user who passes `into="gdf"`.

**How to avoid:** `_SCALAR_HELPERS = frozenset({"area", "perimeter", "distance", "centroid"})` — this set must remain unchanged after Phase 42. Write a test asserting `into="gdf"` works for each new helper (via the recording mock).

### Pitfall 3: Sync/Async Parity Divergence

**What goes wrong:** A parameter is keyword-only in `SpatialAccessor.simplify` but positional in `AsyncSpatialAccessor.simplify`. `test_accessor_parity` catches missing methods; `test_accessor_parameter_kind_parity` catches kind divergence — but only if the new methods are registered in `_HELPER_CALLS`/`_GDF_CALLS` or the test is updated.

**How to avoid:** Write both sync and async methods in the **same commit** (Phase 41 lesson: CR-01). Update `_HELPER_CALLS` and `_GDF_CALLS` in `test_spatial.py` to include all 6 new helpers. `test_accessor_parameter_kind_parity` is parametrized over `ACCESSOR_PAIRS` which includes `(SpatialAccessor, AsyncSpatialAccessor)` — it will auto-catch kind divergence for any registered method.

### Pitfall 4: `make_valid` Params String as f-String

**What goes wrong:** Developer writes `expr = f"ST_MakeValid(t.{geom}, 'method={method}')"` — injection via `method` if not whitelisted, AND bypasses the `%s` invariant even if whitelisted.

**How to avoid:** The params string must ALWAYS be a Python-assembled string from whitelisted literals that is then passed as a `%s` value. The pattern is:
```python
params_str = "method=structure keepcollapsed=true"  # assembled from literals
expr = f"ST_MakeValid(t.{geom}, %s)"                # %s placeholder — not the value
params = [params_str]                                # value goes in params list
```

### Pitfall 5: Missing `other_geom` in Accessor Signature for Parity Test

**What goes wrong:** `_HELPER_CALLS` in `test_spatial.py` lists binary ops without `other_geom` kwarg → `TypeError` at test run time (it's required).

**How to avoid:** Register binary ops in `_HELPER_CALLS` with `other_geom="geometry2"` (or whatever test column exists). The test table needs a second geometry column.

---

## PostGIS Function Signatures (Implementation-Ready)

All signatures verified from official PostGIS documentation. [CITED: postgis.net/docs]

```sql
-- Pairwise binary ops (SPAT2-01, 05, 06)
geometry ST_Union(geometry geomA, geometry geomB)
geometry ST_Difference(geometry geomA, geometry geomB[, float8 gridSize = -1])
geometry ST_Intersection(geometry geomA, geometry geomB[, float8 gridSize = -1])

-- Unary simplification (SPAT2-02)
geometry ST_SimplifyPreserveTopology(geometry geom, float8 tolerance)
  -- Never returns NULL; topology preserved; safe default
geometry ST_Simplify(geometry geom, float8 tolerance[, boolean preserveCollapsed = false])
  -- CAN return NULL when geometry collapses below tolerance
  -- preserveCollapsed=true prevents NULL for point/linestring-like results

-- Unary hull (SPAT2-03)
geometry ST_ConvexHull(geometry geomA)
  -- Returns NULL for empty geometry

-- Geometry repair (SPAT2-04)
geometry ST_MakeValid(geometry input)                          -- PostGIS 3.0+
geometry ST_MakeValid(geometry input, text params)             -- PostGIS 3.2+
  -- params examples:
  --   'method=linework'
  --   'method=structure'
  --   'method=structure keepcollapsed=true'
  --   'method=structure keepcollapsed=false'
  -- Requires GEOS >= 3.10 for method=structure
```

**Note on `gridSize` for Difference/Intersection:** The `gridSize` parameter (GEOS ≥ 3.9 precision model) is NOT exposed in the pycopg high-level API per the deferred decisions. The SQL builders emit `ST_Difference(t.geom1, t.geom2)` without `gridSize`. Callers needing it use raw `db.execute()`.

---

## Validation Architecture

> Nyquist validation is ENABLED (no `workflow.nyquist_validation: false` in `.planning/config.json`).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (verified: `pyproject.toml` test setup) |
| Config | `pyproject.toml` `[tool.pytest.ini_options]` + conftest.py |
| Quick run | `uv run pytest tests/test_spatial.py -x -q` |
| Full suite | `uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SPAT2-01 | `build_union_sql` emits correct ST_Union SQL with `union_geom` alias | unit (SQL-shape) | `uv run pytest tests/test_spatial.py::TestBuilders::test_union_* -x` | ❌ Wave 0 |
| SPAT2-01 | `build_union_sql` raises `InvalidIdentifierError` on malicious table | injection | `uv run pytest tests/test_spatial.py::TestBuilders::test_union_invalid_table -x` | ❌ Wave 0 |
| SPAT2-01 | Live: union of two geometry columns returns correct geometry rows | integration | `uv run pytest tests/test_spatial.py::TestIntegration::test_union_pairwise -x` | ❌ Wave 0 |
| SPAT2-01 | Live: mixed-SRID pair raises (D-06) | integration | `uv run pytest tests/test_spatial.py::TestIntegration::test_union_mixed_srid_raises -x` | ❌ Wave 0 |
| SPAT2-02 | `build_simplify_sql` emits ST_SimplifyPreserveTopology by default | unit | `uv run pytest tests/test_spatial.py::TestBuilders::test_simplify_preserve_topology_default -x` | ❌ Wave 0 |
| SPAT2-02 | `build_simplify_sql` emits ST_Simplify with 2 params when preserve_topology=False | unit | `uv run pytest tests/test_spatial.py::TestBuilders::test_simplify_no_preserve_topology -x` | ❌ Wave 0 |
| SPAT2-02 | `build_simplify_sql` raises ValueError for contradictory preserve_collapsed=True+preserve_topology=True | unit | `uv run pytest tests/test_spatial.py::TestBuilders::test_simplify_contradictory_args -x` | ❌ Wave 0 |
| SPAT2-02 | Live: tiny polygon simplified with preserve_topology=True returns non-NULL | integration | `uv run pytest tests/test_spatial.py::TestIntegration::test_simplify_preserve_topology_non_null -x` | ❌ Wave 0 |
| SPAT2-03 | `build_convex_hull_sql` emits ST_ConvexHull with convex_hull alias | unit | `uv run pytest tests/test_spatial.py::TestBuilders::test_convex_hull_* -x` | ❌ Wave 0 |
| SPAT2-04 | `build_make_valid_sql` emits ST_MakeValid(geom) when method=None | unit | `uv run pytest tests/test_spatial.py::TestBuilders::test_make_valid_no_method -x` | ❌ Wave 0 |
| SPAT2-04 | `build_make_valid_sql` emits ST_MakeValid(geom, %s) with correct params string for linework/structure | unit | `uv run pytest tests/test_spatial.py::TestBuilders::test_make_valid_linework -x` | ❌ Wave 0 |
| SPAT2-04 | `build_make_valid_sql` raises ValueError for invalid method | unit | `uv run pytest tests/test_spatial.py::TestBuilders::test_make_valid_invalid_method -x` | ❌ Wave 0 |
| SPAT2-04 | `build_make_valid_sql` raises ValueError for keep_collapsed without structure | unit | `uv run pytest tests/test_spatial.py::TestBuilders::test_make_valid_keep_collapsed_without_structure -x` | ❌ Wave 0 |
| SPAT2-04 | Live: bowtie polygon repaired → non-NULL output | integration | `uv run pytest tests/test_spatial.py::TestIntegration::test_make_valid_bowtie -x` | ❌ Wave 0 |
| SPAT2-04 | Live: make_valid(method="structure") succeeds (PostGIS 3.6.4 in CI, no guard needed) | integration | `uv run pytest tests/test_spatial.py::TestIntegration::test_make_valid_structure -x` | ❌ Wave 0 |
| SPAT2-05 | `build_difference_sql` emits ST_Difference with difference alias | unit | `uv run pytest tests/test_spatial.py::TestBuilders::test_difference_* -x` | ❌ Wave 0 |
| SPAT2-06 | `build_intersection_sql` emits ST_Intersection with intersection alias | unit | `uv run pytest tests/test_spatial.py::TestBuilders::test_intersection_* -x` | ❌ Wave 0 |
| D-11 parity | 6 new methods present on AsyncSpatialAccessor | parity | `uv run pytest tests/test_parity.py::test_accessor_parity -x` | ✅ (auto-extends) |
| D-11 kind | Keyword-only `*` boundary identical on sync/async | parity | `uv run pytest tests/test_parity.py::test_accessor_parameter_kind_parity -x` | ✅ (auto-extends) |
| D-12 injection | All 6 builders: malicious table → InvalidIdentifierError | injection | `uv run pytest tests/test_spatial.py -k "injection" -x` | ❌ Wave 0 |

### Test Layers and Their Roles (D-08)

**Layer (a) — Mock/SQL-shape authoritative unit tests (no DB required):**

These are the authoritative record that the builder generates exactly the right SQL. Because they are DB-free, they run in <1 second, cover all branches, and catch regressions without any environment setup.

Each test asserts:
1. The SQL string contains the correct PostGIS function (`ST_Union`, etc.)
2. `%s` placeholders match the params list length (`sql.count("%s") == len(params)`)
3. The result column alias is the D-01 name (`"AS union_geom"`, etc.)
4. `_append_tail` clauses are present when `filter=`/`order_by=`/`limit=` are provided
5. `validate_identifiers` is called: injection test proves it (malicious table → `InvalidIdentifierError` before any SQL)

**Layer (b) — Live integration tests against PostGIS (real DB):**

These prove the SQL is semantically correct against the actual PostGIS engine. They run in the `TestIntegration` class using the `sdb` fixture (which skips if PostGIS unavailable).

Required coverage:
- Each of the 6 ops returns non-empty results on a valid input
- Binary ops work with `into="gdf"` (geometry column name is the D-01 name)
- NULL/degenerate input behaviors (bowtie → make_valid, tiny polygon → simplify)
- Mixed-SRID pair raises (D-06)
- make_valid(method="structure") works live (D-09, no guard needed)

### Mock Recording Pattern for Routing Tests

Extend `_HELPER_CALLS` and `_GDF_CALLS` to include new methods:

```python
# In TestAccessorRouting — add to existing lists
_HELPER_CALLS = [
    ...existing...,
    ("union", {"other_geom": "geom2"}),                                 # SPAT2-01
    ("difference", {"other_geom": "geom2"}),                            # SPAT2-05
    ("intersection", {"other_geom": "geom2"}),                         # SPAT2-06
    ("simplify", {"tolerance": 0.01}),                                  # SPAT2-02
    ("convex_hull", {}),                                                 # SPAT2-03
    ("make_valid", {}),                                                  # SPAT2-04
]

_GDF_CALLS = [
    ...existing...,
    ("union", {"other_geom": "geom2"}, "union_geom"),
    ("difference", {"other_geom": "geom2"}, "difference"),
    ("intersection", {"other_geom": "geom2"}, "intersection"),
    ("simplify", {"tolerance": 0.01}, "simplified"),
    ("convex_hull", {}, "convex_hull"),
    ("make_valid", {}, "made_valid"),
]
```

The recording db stubs (`_RecordingSyncDb`, `_RecordingAsyncDb`) need a second geometry column for the routing test table — or the tests can be structured to avoid needing a real second column in the mock (the mock stubs don't actually run SQL, they just record).

### v1 Processing Surface Test (pattern: `test_timescale_v080_surface`)

Add to `test_parity.py`:

```python
def test_spatial_v1_processing_surface():
    """Assert both spatial accessors expose the 6 Phase 42 processing methods."""
    v42_surface = frozenset({
        "union", "difference", "intersection",
        "simplify", "convex_hull", "make_valid",
    })
    for cls in (SpatialAccessor, AsyncSpatialAccessor):
        public = {name for name, _ in inspect.getmembers(cls) if not name.startswith("_")}
        missing = v42_surface - public
        assert not missing, f"{cls.__name__} is missing Phase 42 method(s): {sorted(missing)}"
```

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_spatial.py -x -q` (SQL-shape + injection + routing; ~5 seconds)
- **Per wave merge:** `uv run pytest` (full suite including parity + integration; ~30-60 seconds)
- **Phase gate:** Full suite green + coverage ≥95% before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_spatial.py` — new `TestBuilders` methods for 6 builders
- [ ] `tests/test_spatial.py` — new injection tests (6 builders × malicious table + malicious other_geom for binary)
- [ ] `tests/test_spatial.py` — new `TestIntegration` methods (live PostGIS)
- [ ] `tests/test_spatial.py` — `_HELPER_CALLS` and `_GDF_CALLS` updated for routing tests
- [ ] `tests/test_parity.py` — `test_spatial_v1_processing_surface` frozenset test

---

## Stability.md Updates

The following additions are required to `docs/stability.md` [VERIFIED: file read]:

**In `### db.spatial.* / async_db.spatial.*` table**, add 6 rows:

| Method | Positional args | Keyword-only params |
|--------|-----------------|---------------------|
| `union` | `table` | `geom`, `schema`, `other_geom`, `filter`, `into`, `columns`, `order_by`, `limit` |
| `difference` | `table` | `geom`, `schema`, `other_geom`, `filter`, `into`, `columns`, `order_by`, `limit` |
| `intersection` | `table` | `geom`, `schema`, `other_geom`, `filter`, `into`, `columns`, `order_by`, `limit` |
| `simplify` | `table` | `geom`, `schema`, `tolerance`, `preserve_topology`, `preserve_collapsed`, `filter`, `into`, `columns`, `order_by`, `limit` |
| `convex_hull` | `table` | `geom`, `schema`, `filter`, `into`, `columns`, `order_by`, `limit` |
| `make_valid` | `table` | `geom`, `schema`, `method`, `keep_collapsed`, `filter`, `into`, `columns`, `order_by`, `limit` |

**In `## Supported Versions` / PostGIS floor note**, add:

> `ST_MakeValid(method="structure")` requires PostGIS ≥ 3.2 / GEOS ≥ 3.10. On older servers, `method="structure"` raises a native PostGIS error — pycopg does not pre-check the server version.

**In `## API Stability Tiers`**, the `db.spatial.*` row is already Stable — no change needed.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostGIS (local) | Live integration tests | ✓ | 3.6.4 (GEOS 3.13.1) | — |
| PostGIS (CI) | Live integration tests | ✓ | 3.6.4 (from `timescaledb-ha:pg17` / pgdg) | — |
| pytest | Test runner | ✓ | from `uv sync --dev` | — |

**Missing dependencies with no fallback:** None.

**D-09 finding explicitly:** CI PostGIS 3.6.4 ≥ 3.2 → no `pytest.mark.skipif` needed for any test in this phase.

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | YES | `validate_identifiers` line 1 in every builder; per-builder injection test |
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V6 Cryptography | no | — |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via `table` / `schema` / `geom` / `other_geom` | Tampering | `validate_identifiers` line 1 in every builder + injection test |
| SQL injection via `make_valid` method name | Tampering | Whitelist `{None, "linework", "structure"}` + `ValueError`; value goes through `%s` |
| SQL injection via `make_valid` params string | Tampering | Params string is assembled from programmer-controlled literals; bound as `%s`, not interpolated |
| SQL injection via `columns=` | Tampering | `validate_identifiers(*columns)` after line-1 guard |
| SQL injection via `tolerance` float | Tampering | Goes through `%s` — psycopg3 handles float serialization; no interpolation |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | CI PostGIS version is 3.6.4 based on `timescale/timescaledb-ha:pg17` → Ubuntu pgdg `postgresql-17-postgis-3` package version. Verified via package version page, but Docker image tag `:pg17` is floating — could be rebuilt with a different apt snapshot. | CI PostGIS Version | If CI PostGIS < 3.2, the `make_valid(method="structure")` live test needs `pytest.mark.skipif`; impact LOW since 3.6.4 is current. |
| A2 | `ValueError` (not `TypeError`) for contradictory args in D-03/D-05 is semantically consistent with existing project patterns. | Contradictory-Arg Disposition | If the team prefers `TypeError` for consistency with Phase 41's `both filter and where` case, the error type changes but the behavior doesn't; LOW impact. |
| A3 | The internal `_build_binary_geom_sql` helper is cleaner than 3 fully independent builders. | Pattern 1 | If planner prefers 3 independent builders (more verbose but no shared state), both approaches are correct. |

**If this table is empty:** All claims in this research were verified or cited — no user confirmation needed. (This table has 3 low-risk assumptions.)

---

## Open Questions (RESOLVED)

1. **Second geometry column in routing tests**
   - What we know: `_HELPER_CALLS` must supply `other_geom="geometry2"` for binary ops; the recording mock doesn't need a real DB column but the integration tests do.
   - What's unclear: Does the existing `_make_points` helper in `TestIntegration` need a second geometry column added, or should binary op integration tests use a separate `_make_two_geom_table` helper?
   - Recommendation: Add `_make_two_geom_table` helper that creates a table with `geom_a geometry(Polygon, 4326), geom_b geometry(Polygon, 4326)`, separate from the existing `_make_points` helper. This keeps test setup focused.

2. **Order of `_check_into` vs `await self._check_postgis()` in async accessor**
   - What we know: Existing `AsyncSpatialAccessor.buffer` calls `_check_postgis()` first, then `_check_into`. The `SpatialAccessor.buffer` calls `_check_into` first (no PostGIS guard needed at call time — guarded at init).
   - What's unclear: This ordering difference is correct by design (async guard is lazy), but it means `into="gdf"` on a non-PostGIS env raises `ExtensionNotAvailableError` (not `ValueError`) for the async class.
   - Recommendation: Follow the existing template exactly — `await self._check_postgis()` first in async. This is consistent behavior, already documented.

---

## Sources

### Primary (HIGH confidence)

- `pycopg/spatial.py` (codebase read, lines 1–3200) — `_append_tail`, `build_buffer_sql`, `build_transform_sql`, `_check_into`, `_SCALAR_HELPERS`, `_run`, `_arun`, `SpatialAccessor.buffer`, `SpatialAccessor.transform`, `AsyncSpatialAccessor.buffer`, `AsyncSpatialAccessor.transform` — exact template patterns
- `pycopg/utils.py` (codebase read) — `validate_identifiers` signature + behavior
- `pycopg/exceptions.py` (codebase read) — `InvalidIdentifierError` definition
- `tests/test_spatial.py` (codebase read) — injection test pattern, `_HELPER_CALLS`, `_GDF_CALLS`, `_RecordingSyncDb`, `TestIntegration` fixture structure
- `tests/test_parity.py` (codebase read) — `test_accessor_parity`, `test_accessor_parameter_kind_parity`, `test_timescale_v080_surface` pattern
- `docs/stability.md` (codebase read) — PostGIS floor note, Stable API Contract table for db.spatial.*
- `.github/workflows/tests.yml` (codebase read) — `timescale/timescaledb-ha:pg17` CI image
- [timescale/timescaledb-docker-ha Dockerfile](https://github.com/timescale/timescaledb-docker-ha) — `POSTGIS_VERSIONS="3"`, installs `postgresql-17-postgis-3`
- [Ubuntu Updates pgdg postgresql-15-postgis-3](https://www.ubuntuupdates.org/package/postgresql/jammy-pgdg/main/base/postgresql-15-postgis-3) — current version 3.6.4+dfsg-2.pgdg22.04+1 confirming PostGIS 3.6.4

### Secondary (MEDIUM confidence)

- [PostGIS ST_Union](https://postgis.net/docs/ST_Union.html) — 2-geom and aggregate signatures, gridSize parameter
- [PostGIS ST_Difference](https://postgis.net/docs/ST_Difference.html) — signature with optional gridSize
- [PostGIS ST_Intersection](https://postgis.net/docs/ST_Intersection.html) — signature with optional gridSize
- [PostGIS ST_Simplify](https://postgis.net/docs/ST_Simplify.html) — NULL-collapse behavior, preserveCollapsed parameter
- [PostGIS ST_SimplifyPreserveTopology](https://postgis.net/docs/ST_SimplifyPreserveTopology.html) — non-NULL guarantee
- [PostGIS ST_ConvexHull](https://postgis.net/docs/ST_ConvexHull.html) — signature
- [PostGIS ST_MakeValid](https://postgis.net/docs/ST_MakeValid.html) — params string format, method= and keepcollapsed= keys, PostGIS 3.2 / GEOS 3.10 requirement
- `.planning/research/FEATURES.md` §"Workstream 1: Spatial V2 — Geometry Processing" — API shapes, PostGIS signatures (written pre-Phase-41; `filter=` substituted per D-10)
- `.planning/research/PITFALLS.md` — Pitfall 1 (validate_identifiers), Pitfall 2 (SRID mismatch), Pitfall 4 (NULL/degenerate geometry), Pitfall 11 (parity drift)
- `.planning/research/SUMMARY.md` §"Phase 42" + §"Architecture Approach"
- `.planning/phases/42-spatial-v2-processing-helpers/42-CONTEXT.md` — all decisions D-01 through D-12

---

## Metadata

**Confidence breakdown:**
- CI PostGIS version: HIGH — directly verified via Dockerfile + pgdg package version page
- PostGIS function signatures: HIGH — cited from official postgis.net docs
- Builder pattern: HIGH — verified from codebase (build_buffer_sql, build_transform_sql templates)
- Test fixtures: HIGH — grounded in PostGIS documented behavior + PITFALLS.md
- make_valid params string format: HIGH — cited from postgis.net/docs/ST_MakeValid.html
- Contradictory-arg ValueError: MEDIUM — consistent with existing patterns, semantic reasoning

**Research date:** 2026-06-29
**Valid until:** 2026-07-30 (PostGIS version claim; other claims are codebase-grounded and stable)
