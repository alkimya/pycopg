# Phase 43: Spatial v2 — Spatial Aggregates - Pattern Map

**Mapped:** 2026-06-29
**Files analyzed:** 3 (pycopg/spatial.py, tests/test_spatial.py, tests/test_parity.py)
**Analogs found:** 3 / 3

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `pycopg/spatial.py` (modify) | service/builder | request-response | `pycopg/spatial.py` `_build_binary_geom_sql` + Phase 42 builders | exact |
| `tests/test_spatial.py` (modify) | test | request-response | `tests/test_spatial.py` `TestBinaryGeomBuilders` + `TestAccessorRouting` | exact |
| `tests/test_parity.py` (modify) | test | request-response | `tests/test_parity.py` `test_spatial_v1_processing_surface` | exact |

---

## Pattern Assignments

### `pycopg/spatial.py` — `_append_tail` extension (D-03)

**Analog:** `pycopg/spatial.py` lines 149–186 (current) + `pycopg/timescale.py` lines 258–260 (GROUP BY precedent)

**Current `_append_tail` signature and body** (spatial.py lines 149–186):
```python
def _append_tail(
    sql: str,
    filter: str | None,
    order_by: str | None,
    limit: int | None,
    has_where: bool,
) -> str:
    if filter:
        sql += f" AND ({filter})" if has_where else f" WHERE {filter}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return sql
```

**Timescale GROUP BY precedent** (timescale.py lines 254–260):
```python
sql = (
    f"SELECT time_bucket(%s, {time_column}) AS bucket, {aggregates} "
    f"FROM {schema}.{table}"
)
if where is not None:
    sql += f" WHERE {where}"
sql += " GROUP BY bucket ORDER BY bucket"
```

**Required change:** Add a keyword-only `group_by: str | None = None` param to `_append_tail`, inserted between the WHERE and ORDER BY blocks. Must be keyword-only with `None` default to avoid breaking the 20+ existing call sites.

```python
# Extended signature — group_by inserted after WHERE, before ORDER BY
def _append_tail(
    sql: str,
    filter: str | None,
    order_by: str | None,
    limit: int | None,
    has_where: bool,
    *,
    group_by: str | None = None,   # NEW — pre-assembled, already validated string
) -> str:
    if filter:
        sql += f" AND ({filter})" if has_where else f" WHERE {filter}"
    if group_by:
        sql += f" GROUP BY {group_by}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return sql
```

All existing callers (`_append_tail(sql, f, o, l, has_where=False)`) are unaffected because `group_by` is keyword-only with a `None` default.

---

### `pycopg/spatial.py` — `_build_agg_geom_sql` internal helper

**Analog:** `pycopg/spatial.py` lines 957–980 (`_build_binary_geom_sql`)

**Source pattern** (spatial.py lines 957–980):
```python
def _build_binary_geom_sql(
    op_func: str,
    result_col: str,
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
    """Build SQL for a pairwise (binary, 2-column) geometry operation."""
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
```

**New `_build_agg_geom_sql`** — adapt by replacing `other_geom` binary op with GROUP-BY aggregate shape (D-01, D-02, D-03). No `columns=` (D-02). `group_by` validation is the key addition (Pitfall 1):

```python
def _build_agg_geom_sql(
    agg_func: str,
    result_col: str,
    table: str,
    geom: str,
    schema: str,
    *,
    group_by: list[str] | None,
    filter: str | None,
    order_by: str | None,
    limit: int | None,
) -> tuple[str, list]:
    """Build SQL for a single-column geometry aggregate (ST_Collect / ST_Union agg)."""
    validate_identifiers(table, schema, geom)  # LINE 1 — security invariant
    if group_by:
        validate_identifiers(*group_by)
    group_cols = [f"t.{col}" for col in group_by] if group_by else []
    select_prefix = ", ".join(group_cols + [f"{agg_func}(t.{geom}) AS {result_col}"])
    sql = f"SELECT {select_prefix} FROM {schema}.{table} AS t"
    group_by_str = ", ".join(group_cols) if group_cols else None
    sql = _append_tail(sql, filter, order_by, limit, has_where=False, group_by=group_by_str)
    return sql, []
```

---

### `pycopg/spatial.py` — `build_collect_geometries_sql` and `build_union_aggregate_sql`

**Analog:** `pycopg/spatial.py` lines 983–1028 (`build_union_sql`) — thin public wrapper over the shared internal helper

**Pattern** (build_union_sql lines 983–1040 condensed — only the delegation structure matters):
```python
def build_union_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    other_geom: str,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """..."""
    return _build_binary_geom_sql(
        "ST_Union", "union_geom", table, geom, schema,
        other_geom=other_geom, columns=columns,
        filter=filter, order_by=order_by, limit=limit,
    )
```

**New public builders** — thin wrappers over `_build_agg_geom_sql`:
```python
def build_collect_geometries_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    group_by: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    return _build_agg_geom_sql(
        "ST_Collect", "collected", table, geom, schema,
        group_by=group_by, filter=filter, order_by=order_by, limit=limit,
    )


def build_union_aggregate_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    group_by: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    return _build_agg_geom_sql(
        "ST_Union", "dissolved", table, geom, schema,
        group_by=group_by, filter=filter, order_by=order_by, limit=limit,
    )
```

---

### `pycopg/spatial.py` — `build_extent_sql`

**Analog:** `pycopg/spatial.py` lines 1275–1326 (`build_convex_hull_sql`) for the skeleton; `int(srid)` pattern at lines 120, 123, 126 for injection-safe SRID interpolation

**`int(srid)` interpolation pattern** (spatial.py lines 120, 123, 126):
```python
return f"ST_SetSRID(ST_MakePoint(%s, %s), {int(srid)})", [x, y]
return f"ST_GeomFromText(%s, {int(srid)})", [wkt]
return f"ST_SetSRID(ST_GeomFromGeoJSON(%s), {int(srid)})", [json.dumps(geojson)]
```

**`build_convex_hull_sql` skeleton** (spatial.py lines 1318–1326):
```python
validate_identifiers(table, schema, geom)  # LINE 1 — security invariant
if columns:
    validate_identifiers(*columns)
sql = (
    f"SELECT {_cols_str(columns)}, ST_ConvexHull(t.{geom}) AS convex_hull "
    f"FROM {schema}.{table} AS t"
)
sql = _append_tail(sql, filter, order_by, limit, has_where=False)
return sql, []
```

**New `build_extent_sql`** — unique because `into=` determines the SQL branch (D-04); no `columns=` (D-02):
```python
def build_extent_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    group_by: list[str] | None = None,
    srid: int = 4326,
    into: str = "rows",
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    validate_identifiers(table, schema, geom)  # LINE 1 — security invariant
    if group_by:
        validate_identifiers(*group_by)
    group_cols = [f"t.{col}" for col in group_by] if group_by else []
    if into == "gdf":
        agg_expr = f"ST_SetSRID(ST_Extent(t.{geom})::geometry, {int(srid)}) AS extent"
    else:
        agg_expr = f"ST_Extent(t.{geom})::text AS extent"
    select_prefix = ", ".join(group_cols + [agg_expr]) if group_cols else agg_expr
    sql = f"SELECT {select_prefix} FROM {schema}.{table} AS t"
    group_by_str = ", ".join(group_cols) if group_cols else None
    sql = _append_tail(sql, filter, order_by, limit, has_where=False, group_by=group_by_str)
    return sql, []
```

Note: `build_extent_sql` receives `into` only to select the SQL branch. The accessor still calls `_check_into` BEFORE the builder. `extent` is NOT added to `_SCALAR_HELPERS` (D-04 explicit: `into="gdf"` is valid via the cast). The `int(srid)` cast belongs in the builder f-string, following lines 120/123/126.

---

### `pycopg/spatial.py` — `SpatialAccessor` new methods (sync)

**Analog:** `pycopg/spatial.py` lines 2793–2852 (`convex_hull` — born-clean Phase 42 method, `filter=` only, no `where=`)

**Full `convex_hull` sync method** (spatial.py lines 2793–2852):
```python
def convex_hull(
    self,
    table: str,
    *,
    geom: str = "geometry",
    schema: str = "public",
    into: str = "rows",
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict] | gpd.GeoDataFrame:
    """Select rows with the convex hull of each geometry (ST_ConvexHull).

    Adds a ``convex_hull`` geometry column (D-01). Returns ``NULL`` for
    empty geometries (pass-through, D-07). Valid for ``into="gdf"``. No
    ``where=`` deprecated alias (born clean, D-10).
    ...
    """
    _check_into(into, "convex_hull")
    sql, params = build_convex_hull_sql(
        table,
        geom=geom,
        schema=schema,
        columns=columns,
        filter=filter,
        order_by=order_by,
        limit=limit,
    )
    return self._run(sql, params, into, "convex_hull")
```

**New `collect_geometries` sync accessor** — differences from `convex_hull`: no `columns=` (D-02), adds `group_by=` param, normalizes `str→[str]` (D-01), result column is `"collected"` (D-06):
```python
def collect_geometries(
    self,
    table: str,
    *,
    geom: str = "geometry",
    schema: str = "public",
    group_by: str | list[str] | None = None,
    into: str = "rows",
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict] | gpd.GeoDataFrame:
    if isinstance(group_by, str):
        group_by = [group_by]
    _check_into(into, "collect_geometries")
    sql, params = build_collect_geometries_sql(
        table, geom=geom, schema=schema, group_by=group_by,
        filter=filter, order_by=order_by, limit=limit,
    )
    return self._run(sql, params, into, "collected")
```

**`union_aggregate` sync** — identical shape, `build_union_aggregate_sql`, result column `"dissolved"`.

**`extent` sync** — adds `srid=4326` kw-only; builder receives `into=` (D-04 exception):
```python
def extent(
    self,
    table: str,
    *,
    geom: str = "geometry",
    schema: str = "public",
    group_by: str | list[str] | None = None,
    srid: int = 4326,
    into: str = "rows",
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict] | gpd.GeoDataFrame:
    if isinstance(group_by, str):
        group_by = [group_by]
    _check_into(into, "extent")
    sql, params = build_extent_sql(
        table, geom=geom, schema=schema, group_by=group_by,
        srid=srid, into=into, filter=filter, order_by=order_by, limit=limit,
    )
    return self._run(sql, params, into, "extent")
```

---

### `pycopg/spatial.py` — `AsyncSpatialAccessor` new methods (async)

**Analog:** `pycopg/spatial.py` lines 4317–4379 (`async def convex_hull`)

**Full `async def convex_hull`** (spatial.py lines 4317–4379):
```python
async def convex_hull(
    self,
    table: str,
    *,
    geom: str = "geometry",
    schema: str = "public",
    into: str = "rows",
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict] | gpd.GeoDataFrame:
    """Select rows with the convex hull of each geometry — async (ST_ConvexHull).

    Async mirror of :meth:`SpatialAccessor.convex_hull`. Adds a
    ``convex_hull`` geometry column (D-01). Valid for ``into="gdf"``.
    No ``where=`` deprecated alias (born clean, D-10).
    ...
    """
    await self._check_postgis()
    _check_into(into, "convex_hull")
    sql, params = build_convex_hull_sql(
        table,
        geom=geom,
        schema=schema,
        columns=columns,
        filter=filter,
        order_by=order_by,
        limit=limit,
    )
    return await self._run(sql, params, into, "convex_hull")
```

**Async mirrors** are byte-identical to their sync counterparts except:
1. `async def` declaration
2. `await self._check_postgis()` call at the top (before `_check_into`)
3. `return await self._run(...)` instead of `return self._run(...)`

The docstring says "Async mirror of :meth:`SpatialAccessor.<method_name>`." (see line 4329 pattern).

**`_run` / `_arun` signatures** are identical (spatial.py lines 1536–1562 sync, 3016–3042 async):
```python
# sync _run (lines 1557–1562)
if into == "gdf":
    named_sql, binds = _to_named_binds(sql, params)
    return self._db.to_geodataframe(
        sql=named_sql, params=binds, geometry_column=geometry_column
    )
return self._db.execute(sql, params)

# async _run (lines 3037–3042) — identical logic, await added
if into == "gdf":
    named_sql, binds = _to_named_binds(sql, params)
    return await self._db.to_geodataframe(
        sql=named_sql, params=binds, geometry_column=geometry_column
    )
return await self._db.execute(sql, params)
```

---

### `tests/test_spatial.py` — injection tests

**Analog:** `tests/test_spatial.py` lines 497–505 (union injection tests):
```python
def test_union_invalid_table(self):
    """union validates the table identifier."""
    with pytest.raises(InvalidIdentifierError):
        build_union_sql("bad-name", other_geom="geom2")

def test_union_invalid_other_geom(self):
    """union validates the other_geom identifier."""
    with pytest.raises(InvalidIdentifierError):
        build_union_sql("parcels", other_geom="bad-col; DROP TABLE")
```

**New injection tests** — each aggregate builder needs 3 tests: malicious `table`, `geom`, `group_by` (Pitfall 1 — `group_by` validation is new and must be tested explicitly):
```python
def test_collect_geometries_invalid_table(self):
    with pytest.raises(InvalidIdentifierError):
        build_collect_geometries_sql("bad-name")

def test_collect_geometries_invalid_geom(self):
    with pytest.raises(InvalidIdentifierError):
        build_collect_geometries_sql("zones", geom="bad; DROP TABLE")

def test_collect_geometries_invalid_group_by(self):
    """Pitfall 1: group_by columns must also be validated."""
    with pytest.raises(InvalidIdentifierError):
        build_collect_geometries_sql("zones", group_by=["region; DROP TABLE users; --"])
```

Repeat for `build_union_aggregate_sql` and `build_extent_sql`.

---

### `tests/test_spatial.py` — routing lists `_HELPER_CALLS` and `_GDF_CALLS`

**Analog:** `tests/test_spatial.py` lines 1228–1261

**Current `_HELPER_CALLS`** (lines 1228–1245):
```python
_HELPER_CALLS = [
    ("contains", {"point": (1, 2)}),
    ...
    ("convex_hull", {}),
    ("make_valid", {}),
]
```

**Current `_GDF_CALLS`** (lines 1247–1261):
```python
_GDF_CALLS = [
    ("contains", {"point": (1, 2)}, "geometry"),
    ...
    ("convex_hull", {}, "convex_hull"),
    ("make_valid", {}, "made_valid"),
]
```

**Additions needed** — append to both lists:
```python
# Append to _HELPER_CALLS:
("collect_geometries", {}),
("union_aggregate", {}),
("extent", {}),

# Append to _GDF_CALLS:
("collect_geometries", {}, "collected"),
("union_aggregate", {}, "dissolved"),
("extent", {"into": "gdf"}, "extent"),   # needs into="gdf" explicitly (builder branches on it)
```

Note: `extent` needs `into="gdf"` in `_GDF_CALLS` because the builder uses `into` to choose the SQL branch; `_RecordingSyncDb.execute` mock records the call, so the rows-path also works for the `_HELPER_CALLS` entry.

---

### `tests/test_parity.py` — `test_spatial_aggregates_surface`

**Analog:** `tests/test_parity.py` lines 135–167 (`test_spatial_v1_processing_surface`)

**Full source pattern** (lines 135–167):
```python
def test_spatial_v1_processing_surface():
    """Assert both spatial accessors expose the 6 Phase 42 processing methods."""
    v42_surface = frozenset(
        {
            "union",
            "difference",
            "intersection",
            "simplify",
            "convex_hull",
            "make_valid",
        }
    )
    for cls in (SpatialAccessor, AsyncSpatialAccessor):
        public = {
            name for name, _ in inspect.getmembers(cls) if not name.startswith("_")
        }
        missing = v42_surface - public
        assert (
            not missing
        ), f"{cls.__name__} is missing Phase 42 method(s): {sorted(missing)}"
```

**New `test_spatial_aggregates_surface`** — copy verbatim, swap frozenset and label:
```python
def test_spatial_aggregates_surface():
    """Assert both spatial accessors expose the 3 Phase 43 aggregate methods."""
    v43_surface = frozenset(
        {
            "collect_geometries",
            "union_aggregate",
            "extent",
        }
    )
    for cls in (SpatialAccessor, AsyncSpatialAccessor):
        public = {
            name for name, _ in inspect.getmembers(cls) if not name.startswith("_")
        }
        missing = v43_surface - public
        assert (
            not missing
        ), f"{cls.__name__} is missing Phase 43 method(s): {sorted(missing)}"
```

---

## Shared Patterns

### validate_identifiers — line 1 security invariant
**Source:** `pycopg/spatial.py` line 1318 (convex_hull) / line 971 (_build_binary_geom_sql)
**Apply to:** All 3 new builders (`build_collect_geometries_sql`, `build_union_aggregate_sql`, `build_extent_sql`) AND to `_build_agg_geom_sql`
```python
validate_identifiers(table, schema, geom)  # LINE 1 — security invariant
if group_by:
    validate_identifiers(*group_by)
```
The `group_by` validation is the new addition vs Phase 42 builders. It must come before any f-string interpolation of group columns.

### `_check_into` — validate before SQL runs
**Source:** `pycopg/spatial.py` lines 1455–1477
**Apply to:** All 3 new accessor methods (sync + async), called before the builder
```python
_check_into(into, "collect_geometries")  # before build_*_sql call
```
`extent` is NOT in `_SCALAR_HELPERS` (D-04 explicit). The `_check_into` call still validates that `into` is one of `("rows", "gdf")`.

### Born-clean `filter=` only — no `where=` deprecated alias
**Source:** `pycopg/spatial.py` lines 2793–2852 (convex_hull — Phase 42)
**Apply to:** All 3 new accessor methods (sync + async)
New Phase 43 methods have no `where=` parameter and no deprecation shim. The `where=` shim exists only on the 11 pre-Phase-41 spatial methods.

### Docstring NULL-propagation note (D-07)
**Source:** `pycopg/spatial.py` lines 2805–2809 (convex_hull docstring pattern)
**Apply to:** All 3 new accessor methods
Each docstring must contain a note about NULL geometry inputs: "NULL geometry inputs are skipped by the PostGIS aggregate; a group (or the whole table) with all-NULL inputs yields one row with a NULL aggregate value. No ``HAVING`` filter is applied (D-07)."

---

## No Analog Found

No files are without analog. All patterns exist in the codebase.

---

## Key Pitfalls for Executor (from RESEARCH.md)

| # | Pitfall | Guard |
|---|---------|-------|
| 1 | Missing `validate_identifiers` on `group_by` columns | Injection test: malicious `group_by` → `InvalidIdentifierError` |
| 2 | `_append_tail` positional `group_by` arg breaks existing callers | Use keyword-only `*, group_by=None` |
| 3 | `extent` added to `_SCALAR_HELPERS` | D-04 explicit: do NOT add it |
| 4 | `HAVING ... IS NOT NULL` added | NULL fixture test verifies 1 row with NULL aggregate, not 0 rows |
| 5 | `group_by=[]` empty list → `GROUP BY ` syntax error | Raise `ValueError` or normalize to `None` |
| 6 | KIND parity drift (`group_by`/`srid` positional in async) | `test_accessor_parameter_kind_parity` catches it |

---

## Metadata

**Analog search scope:** `pycopg/spatial.py`, `pycopg/timescale.py`, `tests/test_spatial.py`, `tests/test_parity.py`
**Files scanned:** 4
**Pattern extraction date:** 2026-06-29
