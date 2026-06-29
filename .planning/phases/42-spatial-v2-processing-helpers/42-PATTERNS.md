# Phase 42: Spatial v2 — Processing Helpers - Pattern Map

**Mapped:** 2026-06-29
**Files analyzed:** 2 modified files (pycopg/spatial.py, tests/test_spatial.py) + 1 augmented (tests/test_parity.py)
**Analogs found:** 3 / 3 (all files have direct analogs in-codebase)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pycopg/spatial.py` — 6 builders | utility (pure builder) | transform | `build_buffer_sql` (line 830), `build_transform_sql` (line 898) | exact |
| `pycopg/spatial.py` — 6 sync accessor methods | service (accessor delegate) | request-response | `SpatialAccessor.buffer` (line 1864), `SpatialAccessor.transform` (line 1946) | exact |
| `pycopg/spatial.py` — 6 async accessor methods | service (async accessor delegate) | request-response | `AsyncSpatialAccessor.buffer` (line 2947), `AsyncSpatialAccessor.transform` (line 3032) | exact |
| `tests/test_spatial.py` — SQL-shape + injection tests | test | CRUD | `test_transform_parameterizes_to_srid` + `test_transform_invalid_table` (lines 440–465) | exact |
| `tests/test_spatial.py` — routing tests (`_HELPER_CALLS`/`_GDF_CALLS`) | test | request-response | `_HELPER_CALLS`/`_GDF_CALLS` (lines 752–773) | exact |
| `tests/test_spatial.py` — live integration tests | test | request-response | `test_buffer_into_gdf_returns_geodataframe` + `test_contains_returns_correct_rows` (lines 585–658) | role-match |
| `tests/test_parity.py` — `test_spatial_v1_processing_surface` | test | — | `test_timescale_v080_surface` (line 64) / `test_schema_v090_surface` (line 101) | exact |

---

## Pattern Assignments

### Builders: `build_buffer_sql` (line 830) and `build_transform_sql` (line 898)

These two are the canonical templates for all 6 new builders. The full body for `build_transform_sql` (the simpler of the two — no `unit=` branching, one param) is:

**Imports pattern** (top of `pycopg/spatial.py`, lines 1–30 area):
```python
from pycopg.utils import validate_identifiers
from pycopg.exceptions import InvalidIdentifierError
```
Both are already imported; no new imports needed for the builders.

**`build_transform_sql` — full body** (lines 945–954 — the exact template for unary builders):
```python
validate_identifiers(table, schema, geom)          # LINE 1 — security invariant (D-12)
if columns:
    validate_identifiers(*columns)
sql = (
    f"SELECT {_cols_str(columns)}, "
    f"ST_Transform(t.{geom}, %s) AS geometry_transformed "
    f"FROM {schema}.{table} AS t"
)
sql = _append_tail(sql, filter, order_by, limit, has_where=False)
return sql, [to_srid]
```

**`build_buffer_sql` — full body** (lines 882–895 — shows params list + helper call pattern):
```python
validate_identifiers(table, schema, geom)          # LINE 1
if columns:
    validate_identifiers(*columns)
_validate_unit(unit)                               # extra domain validation AFTER identifiers
if unit == "m":
    buffer_expr = f"ST_Buffer(t.{geom}::geography, %s)::geometry"
else:
    buffer_expr = f"ST_Buffer(t.{geom}, %s)"
sql = (
    f"SELECT {_cols_str(columns)}, {buffer_expr} AS buffer "
    f"FROM {schema}.{table} AS t"
)
sql = _append_tail(sql, filter, order_by, limit, has_where=False)
return sql, [distance]
```

**`_append_tail` signature** (lines 149–155):
```python
def _append_tail(
    sql: str,
    filter: str | None,
    order_by: str | None,
    limit: int | None,
    has_where: bool,
) -> str:
```
All 6 new builders call `_append_tail(..., has_where=False)` — none have a built-in WHERE.

**Supporting constants** (lines 959–963):
```python
_SCALAR_HELPERS = frozenset({"area", "perimeter", "distance", "centroid"})
# ↑ DO NOT add any of the 6 new helpers here — all return geometry (D-12)

_VALID_INTO = ("rows", "gdf")
```

---

### New builder: `build_union_sql` / `build_difference_sql` / `build_intersection_sql`

These three are **binary** (pairwise, 2-column) builders. Template structure follows `build_transform_sql` but adds `other_geom` as a required keyword-only parameter and also validates it.

**Signature shape to copy** (derived from `build_transform_sql` + D-10/D-12):
```python
def build_union_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    other_geom: str,                     # required kw-only — no default (D-10)
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
```

**Body pattern** (D-12 + RESEARCH Pattern 1):
```python
validate_identifiers(table, schema, geom, other_geom)   # LINE 1 — 4-arg form for binary
if columns:
    validate_identifiers(*columns)
sql = (
    f"SELECT {_cols_str(columns)}, "
    f"ST_Union(t.{geom}, t.{other_geom}) AS union_geom "
    f"FROM {schema}.{table} AS t"
)
sql = _append_tail(sql, filter, order_by, limit, has_where=False)
return sql, []                                           # no params — identifiers are in SQL
```

Result column names (D-01 — frozen at 1.0):
- `build_union_sql` → `"union_geom"`
- `build_difference_sql` → `"difference"`
- `build_intersection_sql` → `"intersection"`

---

### New builder: `build_simplify_sql`

**Body pattern** (D-05 + RESEARCH Pattern 2):
```python
validate_identifiers(table, schema, geom)       # LINE 1
if columns:
    validate_identifiers(*columns)
# Contradictory-arg guard AFTER validate_identifiers, BEFORE SQL (D-05)
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

Result column name (D-01): `"simplified"`. Params list has 1 or 2 elements depending on branch.

**Existing analog for domain-validation-after-identifiers ordering** (from `build_buffer_sql` line 882–885):
```python
validate_identifiers(table, schema, geom)   # LINE 1
if columns:
    validate_identifiers(*columns)
_validate_unit(unit)                        # domain validation comes AFTER identifiers
```
Apply the same ordering for `preserve_collapsed`/`preserve_topology` in `build_simplify_sql` and `method`/`keep_collapsed` in `build_make_valid_sql`.

---

### New builder: `build_convex_hull_sql`

Simplest unary builder — no extra parameters, no params list.

**Body pattern** (RESEARCH Pattern 4):
```python
validate_identifiers(table, schema, geom)    # LINE 1
if columns:
    validate_identifiers(*columns)
sql = (
    f"SELECT {_cols_str(columns)}, ST_ConvexHull(t.{geom}) AS convex_hull "
    f"FROM {schema}.{table} AS t"
)
sql = _append_tail(sql, filter, order_by, limit, has_where=False)
return sql, []
```

Result column name (D-01): `"convex_hull"`. Empty params list.

---

### New builder: `build_make_valid_sql`

**Body pattern** (D-02/D-03/D-04 + RESEARCH Pattern 3):
```python
validate_identifiers(table, schema, geom)    # LINE 1
if columns:
    validate_identifiers(*columns)
# method whitelist guard — AFTER validate_identifiers (D-02)
_VALID_MAKE_VALID_METHODS = {None, "linework", "structure"}
if method not in _VALID_MAKE_VALID_METHODS:
    raise ValueError(
        f"method must be one of {sorted(str(m) for m in _VALID_MAKE_VALID_METHODS)}, "
        f"got {method!r}"
    )
# Contradictory-arg guard (D-03)
if keep_collapsed is not None and method != "structure":
    raise ValueError(
        "keep_collapsed is only valid when method='structure'; "
        f"got method={method!r}"
    )
if method is None:
    expr = f"ST_MakeValid(t.{geom})"
    params: list = []
else:
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
    params = [params_str]                  # assembled from literals → bound as %s (D-02)
sql = (
    f"SELECT {_cols_str(columns)}, {expr} AS made_valid "
    f"FROM {schema}.{table} AS t"
)
sql = _append_tail(sql, filter, order_by, limit, has_where=False)
return sql, params
```

Result column name (D-01): `"made_valid"`.

---

### Sync accessor methods: `SpatialAccessor.buffer` (line 1864) and `SpatialAccessor.transform` (line 1946)

**Key observation for new methods:** The new 6 methods do NOT have a `where=` deprecated alias (D-10 — born clean). Omit the `where is not None` block entirely. This simplifies the accessor body vs the existing `buffer`/`transform` analogs.

**`SpatialAccessor.transform` body** (lines 2000–2023 — the transform dispatch with where-shim; new methods drop the shim):
```python
# Existing transform (has deprecated where= shim — DO NOT copy the shim for new methods):
if where is not None:
    if filter is not None:
        raise TypeError(...)
    warnings.warn(...)
    filter = where
_check_into(into, "transform")
sql, params = build_transform_sql(
    table, geom=geom, schema=schema, to_srid=to_srid,
    columns=columns, filter=filter, order_by=order_by, limit=limit,
)
return self._run(sql, params, into, "geometry_transformed")
```

**New method body — copy this shape (no where= shim)**:
```python
def union(
    self,
    table: str,
    *,
    geom: str = "geometry",
    schema: str = "public",
    other_geom: str,
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
    return self._run(sql, params, into, "union_geom")   # D-01 result col
```

**`_run` signature** (lines 1052–1078 — already exists, not changed):
```python
def _run(
    self, sql: str, params: list, into: str, geometry_column: str
) -> list[dict] | gpd.GeoDataFrame:
    if into == "gdf":
        named_sql, binds = _to_named_binds(sql, params)
        return self._db.to_geodataframe(
            sql=named_sql, params=binds, geometry_column=geometry_column
        )
    return self._db.execute(sql, params)
```

`_check_into` call ordering in sync: `_check_into` FIRST, then builder, then `_run`. No PostGIS guard (guarded at `__init__`).

---

### Async accessor methods: `AsyncSpatialAccessor.buffer` (line 2947) and `AsyncSpatialAccessor.transform` (line 3032)

**Async body shape** (lines 3017–3030 — transform dispatch — new methods drop `where=` shim):
```python
await self._check_postgis()                    # FIRST — lazy PostGIS guard (async only)
_check_into(into, "transform")
sql, params = build_transform_sql(
    table, geom=geom, schema=schema, to_srid=to_srid,
    columns=columns, filter=filter, order_by=order_by, limit=limit,
)
return await self._run(sql, params, into, "geometry_transformed")
```

**New async method body — copy this shape**:
```python
async def union(
    self,
    table: str,
    *,
    geom: str = "geometry",
    schema: str = "public",
    other_geom: str,
    into: str = "rows",
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict] | gpd.GeoDataFrame:
    """..."""
    await self._check_postgis()               # FIRST in async (lazy guard)
    _check_into(into, "union")
    sql, params = build_union_sql(
        table, geom=geom, schema=schema, other_geom=other_geom,
        columns=columns, filter=filter, order_by=order_by, limit=limit,
    )
    return await self._run(sql, params, into, "union_geom")
```

**Critical difference from sync:** `await self._check_postgis()` is line 1 in async. In sync there is no such call (guarded at `__init__`). This ordering difference is correct by design (confirmed in RESEARCH Open Question 2).

---

### Test patterns: SQL-shape unit tests

**Exact analog: `test_transform_parameterizes_to_srid`** (lines 440–447):
```python
def test_transform_parameterizes_to_srid(self):
    """transform emits ST_Transform with to_srid as %s param."""
    sql, params = build_transform_sql("parcels", to_srid=3857)
    assert sql == (
        "SELECT *, ST_Transform(t.geometry, %s) AS geometry_transformed "
        "FROM public.parcels AS t"
    )
    assert params == [3857]
```

Copy this exact structure for each new builder test. For binary ops:
```python
def test_union_emits_st_union(self):
    """union emits ST_Union with union_geom alias and empty params."""
    sql, params = build_union_sql("parcels", other_geom="geom2")
    assert sql == (
        "SELECT *, ST_Union(t.geometry, t.geom2) AS union_geom "
        "FROM public.parcels AS t"
    )
    assert params == []
```

**Tail clauses test analog** (lines 449–460):
```python
def test_transform_tail_clauses(self):
    sql, _ = build_transform_sql(
        "parcels", to_srid=2154, columns=["id"],
        filter="id < 9", order_by="id", limit=7,
    )
    assert sql.startswith("SELECT id, ST_Transform(")
    assert sql.endswith("WHERE id < 9 ORDER BY id LIMIT 7")
```

---

### Test patterns: injection tests

**Exact analog: `test_transform_invalid_table`** (lines 462–465):
```python
def test_transform_invalid_table(self):
    """transform validates the table identifier."""
    with pytest.raises(InvalidIdentifierError):
        build_transform_sql("bad-name", to_srid=4326)
```

**Columns injection analog** (`TestBuilderColumnsValidation`, lines 911–914):
```python
def test_transform_columns_validated(self):
    with pytest.raises(InvalidIdentifierError):
        build_transform_sql("parcels", to_srid=4326, columns=["bad-col"])
```

For binary builders, also test `other_geom` injection:
```python
def test_union_invalid_other_geom(self):
    with pytest.raises(InvalidIdentifierError):
        build_union_sql("parcels", other_geom="bad-col; DROP TABLE")
```

---

### Test patterns: routing registry (`_HELPER_CALLS` / `_GDF_CALLS`)

**Exact analog** (lines 752–773):
```python
_HELPER_CALLS = [
    ...existing...,
    # Add for Phase 42:
    ("union", {"other_geom": "geometry2"}),
    ("difference", {"other_geom": "geometry2"}),
    ("intersection", {"other_geom": "geometry2"}),
    ("simplify", {"tolerance": 0.01}),
    ("convex_hull", {}),
    ("make_valid", {}),
]

_GDF_CALLS = [
    ...existing...,
    # Add for Phase 42:
    ("union", {"other_geom": "geometry2"}, "union_geom"),
    ("difference", {"other_geom": "geometry2"}, "difference"),
    ("intersection", {"other_geom": "geometry2"}, "intersection"),
    ("simplify", {"tolerance": 0.01}, "simplified"),
    ("convex_hull", {}, "convex_hull"),
    ("make_valid", {}, "made_valid"),
]
```

**How the routing test uses these** (lines 779–839 — parametrized, no changes needed to test body):
```python
@pytest.mark.parametrize("helper,kwargs", _HELPER_CALLS)
def test_sync_rows_path(self, helper, kwargs):
    db = _RecordingSyncDb()
    acc = SpatialAccessor(db)
    result = getattr(acc, helper)("parcels", **kwargs)
    assert result == [{"ok": 1}]
    kind, sql, params = db.calls[-1]
    assert kind == "execute"
    assert sql.count("%s") == len(params)
```
The recording stub does not actually execute SQL — it just records calls. Adding entries to `_HELPER_CALLS`/`_GDF_CALLS` is sufficient; no stub changes needed.

---

### Test patterns: live integration tests

**Exact analog: `test_buffer_into_gdf_returns_geodataframe`** (lines 646–658):
```python
def test_buffer_into_gdf_returns_geodataframe(self, sdb):
    t = _uniq("spat_buffer")
    try:
        self._make_points(sdb, t)
        gdf = sdb.spatial.buffer(t, distance=1000, into="gdf")
        assert isinstance(gdf, gpd.GeoDataFrame)
        assert len(gdf) == 3
        assert gdf.geometry.name == "buffer"
    finally:
        sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)
```

**`_make_points` helper** (lines 570–583):
```python
def _make_points(self, db, t):
    db.execute(
        f'CREATE TABLE "{t}" (id INT PRIMARY KEY, '
        "geometry geometry(Point, 4326))",
        autocommit=True,
    )
    db.execute(
        f'INSERT INTO "{t}" VALUES '
        "(1, ST_GeomFromText('POINT(0 0)', 4326)), "
        "(2, ST_GeomFromText('POINT(0.1 0.1)', 4326)), "
        "(3, ST_GeomFromText('POINT(10 10)', 4326))",
        autocommit=True,
    )
```

For Phase 42 integration tests, add a second fixture helper (RESEARCH Open Question 1 recommendation):
```python
def _make_two_geom_table(self, db, t):
    """Two polygon geometry columns for binary op tests."""
    db.execute(
        f'CREATE TABLE "{t}" (id INT PRIMARY KEY, '
        "geom_a geometry(Polygon, 4326), geom_b geometry(Polygon, 4326))",
        autocommit=True,
    )
    db.execute(
        f'INSERT INTO "{t}" VALUES '
        "(1, ST_GeomFromText('POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))', 4326), "
        "    ST_GeomFromText('POLYGON((0.5 0.5, 1.5 0.5, 1.5 1.5, 0.5 1.5, 0.5 0.5))', 4326))",
        autocommit=True,
    )
```

For bowtie / make_valid fixture (RESEARCH fixture 1):
```python
BOWTIE_WKT = "POLYGON((0 0, 1 1, 1 0, 0 1, 0 0))"
# Assertion: result is non-NULL (repair succeeded)
rows = sdb.spatial.make_valid(t, columns=["id"])
assert rows[0]["made_valid"] is not None
```

For mixed-SRID test (D-06 + RESEARCH fixture 3):
```python
import pytest
# Table: geom_a SRID 4326, geom_b SRID 32632
with pytest.raises(Exception):    # PostGIS raises natively — do NOT wrap
    sdb.spatial.union(t, geom="geom_a", other_geom="geom_b")
```

---

### Test patterns: parity surface test in `tests/test_parity.py`

**Exact analog: `test_timescale_v080_surface`** (lines 64–98):
```python
def test_timescale_v080_surface():
    v080_surface = frozenset({
        "show_chunks", "drop_chunks", "add_dimension", ...
    })
    for cls in (TimescaleAccessor, AsyncTimescaleAccessor):
        public = {name for name, _ in inspect.getmembers(cls) if not name.startswith("_")}
        missing = v080_surface - public
        assert not missing, f"{cls.__name__} is missing v0.8.0 method(s): {sorted(missing)}"
```

New test to add for Phase 42 (copy this structure exactly):
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

---

## Shared Patterns

### validate_identifiers — line 1 of every builder
**Source:** `pycopg/utils.py` (already imported in `spatial.py`)
**Apply to:** All 6 new `build_*_sql` functions — MUST be the first executable statement.
**Binary form** (4 args for pairwise ops): `validate_identifiers(table, schema, geom, other_geom)`
**Unary form** (3 args): `validate_identifiers(table, schema, geom)`
**Precedent / anti-pattern warning:** v0.10.0 COPY rewrite dropped `validate_identifiers` from a builder; test suite stayed green; injection vulnerability shipped. Fixed in commit 863e894.

### `_check_into` — validate `into=` before SQL in every accessor method
**Source:** `pycopg/spatial.py` lines 971–993
```python
def _check_into(into: str, helper: str) -> None:
    if into not in _VALID_INTO:
        raise ValueError(f"into must be one of {_VALID_INTO}, got {into!r}")
    if into == "gdf" and helper in _SCALAR_HELPERS:
        raise ValueError(...)
```
**Apply to:** All 6 sync + 6 async new accessor methods. Called AFTER `await self._check_postgis()` in async, as the first call in sync.

### No `where=` deprecated alias
**Source:** D-10 decision. The existing `buffer`/`transform` accessor methods (lines 1920–1931, 3005–3016) contain the shim — new methods do NOT include it. Born clean.

### `_SCALAR_HELPERS` must remain unchanged
**Source:** `pycopg/spatial.py` line 959
```python
_SCALAR_HELPERS = frozenset({"area", "perimeter", "distance", "centroid"})
```
None of the 6 new helpers are added here. All return geometry → `into="gdf"` valid for all 6.

### Execution ordering
| Class | Order |
|-------|-------|
| `SpatialAccessor` (sync) | `_check_into(into, name)` → `build_*_sql(...)` → `self._run(sql, params, into, result_col)` |
| `AsyncSpatialAccessor` (async) | `await self._check_postgis()` → `_check_into(into, name)` → `build_*_sql(...)` → `await self._run(sql, params, into, result_col)` |

---

## No Analog Found

All 6 builder types have a direct analog in the codebase. No files without analogs.

---

## D-01 Result Column Name Reference

| Method | Builder | Result column (`geometry_column` arg to `_run`) |
|--------|---------|------------------------------------------------|
| `union` | `build_union_sql` | `"union_geom"` |
| `difference` | `build_difference_sql` | `"difference"` |
| `intersection` | `build_intersection_sql` | `"intersection"` |
| `simplify` | `build_simplify_sql` | `"simplified"` |
| `convex_hull` | `build_convex_hull_sql` | `"convex_hull"` |
| `make_valid` | `build_make_valid_sql` | `"made_valid"` |

---

## Metadata

**Analog search scope:** `pycopg/spatial.py`, `tests/test_spatial.py`, `tests/test_parity.py`
**Files scanned:** 3 source files (targeted reads using known line refs from CONTEXT.md)
**Pattern extraction date:** 2026-06-29
