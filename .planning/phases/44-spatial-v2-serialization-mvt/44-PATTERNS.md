# Phase 44: Spatial v2 — Serialization + MVT — Pattern Map

**Mapped:** 2026-06-29
**Files analyzed:** 2 (pycopg/spatial.py modifications, tests/test_spatial.py + tests/test_parity.py additions)
**Analogs found:** 6 / 6 (all in pycopg/spatial.py and tests/test_spatial.py + tests/test_parity.py)

---

## File Classification

| New/Modified Symbol | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|-----------|----------------|---------------|
| `build_geojson_sql` (module-level) | builder | transform | `build_area_sql` (spatial.py:662) | exact |
| `build_text_sql` (module-level) | builder | transform | `build_perimeter_sql` (spatial.py:724) | exact |
| `build_mvt_sql` (module-level) | builder | transform | `build_extent_sql` (spatial.py:~1765, P43) | role-match (different SQL shape) |
| `SpatialAccessor._run_mvt` | utility | request-response | `SpatialAccessor._run` (spatial.py:1877) | role-match (different return type) |
| `AsyncSpatialAccessor._arun_mvt` | utility | request-response | `AsyncSpatialAccessor._run` (spatial.py:3639) | role-match (different return type) |
| `SpatialAccessor.as_geojson` | accessor method | request-response | `SpatialAccessor.area` (spatial.py:2455) | exact (minus `where=` shim) |
| `SpatialAccessor.as_text` | accessor method | request-response | `SpatialAccessor.area` (spatial.py:2455) | exact (minus `where=` shim) |
| `SpatialAccessor.as_mvt` | accessor method | request-response | `SpatialAccessor.area` (spatial.py:2455) | partial (different runner + return type) |
| `AsyncSpatialAccessor.as_geojson` | accessor method | request-response | `AsyncSpatialAccessor.area` (spatial.py:4234) | exact (minus `where=` shim) |
| `AsyncSpatialAccessor.as_text` | accessor method | request-response | `AsyncSpatialAccessor.area` (spatial.py:4234) | exact (minus `where=` shim) |
| `AsyncSpatialAccessor.as_mvt` | accessor method | request-response | `AsyncSpatialAccessor.area` (spatial.py:4234) | partial (different runner + return type) |
| `_SCALAR_HELPERS` update | config | — | `_SCALAR_HELPERS` (spatial.py:1784) | exact |
| `TestBuildGeojsonSql` (tests) | test | — | `TestBuilderColumnsValidation` (test_spatial.py:1571) | exact |
| `TestBuildTextSql` (tests) | test | — | `TestBuilderColumnsValidation` (test_spatial.py:1571) | exact |
| `TestBuildMvtSql` (tests) | test | — | `TestAggregateBuilders` (test_spatial.py:1651) | role-match |
| `test_spatial_serialization_surface` (test_parity.py) | test | — | `test_spatial_aggregates_surface` (test_parity.py:170) | exact |

---

## Pattern Assignments

### `build_geojson_sql` (module-level builder, transform)

**Analog:** `build_area_sql` — `pycopg/spatial.py` lines 662–721

**Imports / top-of-file pattern** (spatial.py lines 1–20 region):
```python
from pycopg.utils import validate_identifiers
# validate_identifiers is the LINE-1 guard for every build_*_sql
```

**Builder structure** (spatial.py lines 711–721 — copy exactly, changing ST_* call and params):
```python
def build_area_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    unit: str = "m",
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    validate_identifiers(table, schema, geom)   # LINE 1 — copy this
    if columns:
        validate_identifiers(*columns)
    _validate_unit(unit)
    cast = "::geography" if unit == "m" else ""
    sql = (
        f"SELECT {_cols_str(columns)}, ST_Area(t.{geom}{cast}) AS area "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []
```

**Adaptation for `build_geojson_sql`:**
- Replace `unit: str = "m"` with `max_decimal_digits: int = 6`, `include_bbox: bool = False`, `include_crs: bool = False`
- Replace ST_Area expression with: `ST_AsGeoJSON(t.{geom}, %s, %s) AS geojson`
- Add bitmask before building SQL: `options = (1 if include_bbox else 0) | (2 if include_crs else 0)`
- Return `(sql, [max_decimal_digits, options])` instead of `(sql, [])`
- Remove `_validate_unit` call (not applicable)
- Result key is `geojson` (frozen per D-06)

**`_append_tail` pattern** (spatial.py lines 149–157 — reuse unchanged):
```python
def _append_tail(
    sql: str,
    filter: str | None,
    order_by: str | None,
    limit: int | None,
    has_where: bool,
    *,
    group_by: str | None = None,
) -> str:
```
Call as: `_append_tail(sql, filter, order_by, limit, has_where=False)` — no `group_by` for scalar serializers.

---

### `build_text_sql` (module-level builder, transform)

**Analog:** `build_perimeter_sql` — `pycopg/spatial.py` lines 724–784

**Core pattern** (spatial.py lines 773–784):
```python
    validate_identifiers(table, schema, geom)   # LINE 1
    if columns:
        validate_identifiers(*columns)
    _validate_unit(unit)
    cast = "::geography" if unit == "m" else ""
    sql = (
        f"SELECT {_cols_str(columns)}, "
        f"ST_Perimeter(t.{geom}{cast}) AS perimeter "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, []
```

**Adaptation for `build_text_sql`:**
- Parameter: `max_decimal_digits: int | None = None` instead of `unit`
- Conditional ST_* call (D-07): one-arg vs two-arg branch:
  ```python
  if max_decimal_digits is not None:
      st_call = f"ST_AsText(t.{geom}, %s) AS wkt"
      params: list = [max_decimal_digits]
  else:
      st_call = f"ST_AsText(t.{geom}) AS wkt"
      params = []
  sql = f"SELECT {_cols_str(columns)}, {st_call} FROM {schema}.{table} AS t"
  ```
- Result key is `wkt` (frozen per D-07)
- Return `(sql, params)` where params is `[]` or `[max_decimal_digits]`

---

### `build_mvt_sql` (module-level builder, transform)

**Analog:** `build_extent_sql` — `pycopg/spatial.py` lines ~1765–1779 (P43 — the `int(srid)` precedent)

**`int(srid)` injection-safe interpolation pattern** (spatial.py line 1770):
```python
    agg_expr = f"ST_SetSRID(ST_Extent(t.{geom})::geometry, {int(srid)}) AS extent"
```
Reuse the same `int()` coercion for `tile_z`, `tile_x`, `tile_y`, `extent`, and `srid` in `build_mvt_sql`.

**Identifier guard at line 1 pattern** (spatial.py line 1765):
```python
    validate_identifiers(table, schema, geom)  # LINE 1 — security invariant (T-43-01)
    if group_by:
        validate_identifiers(*group_by)
```
For `build_mvt_sql` extend to also validate `columns` and `feature_id_column`:
```python
    validate_identifiers(table, schema, geom)   # LINE 1
    if columns:
        validate_identifiers(*columns)
    if feature_id_column is not None:
        validate_identifiers(feature_id_column)
```

**Full builder structure to write** (from RESEARCH.md Pattern 3, verified against D-01..D-04):
```python
def build_mvt_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    tile_z: int,
    tile_x: int,
    tile_y: int,
    layer_name: str = "default",
    extent: int = 4096,
    columns: list[str] | None = None,
    feature_id_column: str | None = None,
    srid: int | None = None,
    filter: str | None = None,
) -> tuple[str, list]:
    validate_identifiers(table, schema, geom)   # LINE 1
    if columns:
        validate_identifiers(*columns)
    if feature_id_column is not None:
        validate_identifiers(feature_id_column)

    z, x, y, ext = int(tile_z), int(tile_x), int(tile_y), int(extent)
    if srid is not None:
        transform = f"ST_Transform(ST_SetSRID(t.{geom}, {int(srid)}), 3857)"
    else:
        transform = f"ST_Transform(t.{geom}, 3857)"

    col_prefix = (_cols_str(columns) + ", ") if columns else ""
    inner = (
        f"SELECT {col_prefix}ST_AsMVTGeom("
        f"{transform}, ST_TileEnvelope({z}, {x}, {y}), {ext}"
        f") AS geom_mvt FROM {schema}.{table} AS t"
    )
    if filter:
        inner += f" WHERE {filter}"

    if feature_id_column is not None:
        agg = f"ST_AsMVT(q.*, %s, %s, 'geom_mvt', '{feature_id_column}')"
    else:
        agg = "ST_AsMVT(q.*, %s, %s, 'geom_mvt')"
    sql = f"SELECT {agg} AS mvt FROM ({inner}) AS q WHERE q.geom_mvt IS NOT NULL"
    return sql, [layer_name, ext]
```

Key points:
- `AS mvt` alias makes `rows[0]["mvt"]` reliable in `_run_mvt` (RESEARCH.md Pitfall 5)
- `filter` goes in the INNER subquery — NOT through `_append_tail` (D-03, RESEARCH.md Open Q 3)
- `layer_name` and `ext` (extent) are the only two `%s` params; tile coords and extent literal are `int()` coerced
- `feature_id_column` is interpolated as an identifier (validated, not a `%s` param) — PostGIS requires literal column name

---

### `SpatialAccessor._run_mvt` and `AsyncSpatialAccessor._arun_mvt`

**Analog:** `SpatialAccessor._run` (spatial.py lines 1877–1903) and `AsyncSpatialAccessor._run` (spatial.py lines 3639–3665)

**Sync `_run` pattern to adapt** (spatial.py lines 1877–1903):
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

**`_run_mvt` to write** (simpler — no routing, no `into=`, single-cell bytea):
```python
    def _run_mvt(self, sql: str, params: list) -> bytes:
        rows = self._db.execute(sql, params)
        val = rows[0]["mvt"]   # "mvt" alias set in build_mvt_sql
        if isinstance(val, memoryview):
            return bytes(val)
        return val if val is not None else b""
```

**Async mirror** (spatial.py lines 3639–3665 for pattern, adapt same way):
```python
    async def _arun_mvt(self, sql: str, params: list) -> bytes:
        rows = await self._db.execute(sql, params)
        val = rows[0]["mvt"]
        if isinstance(val, memoryview):
            return bytes(val)
        return val if val is not None else b""
```

Note: Use `rows[0]["mvt"]` (the `AS mvt` alias) rather than `next(iter(rows[0]))` — more explicit and testable.

---

### `SpatialAccessor.as_geojson` and `SpatialAccessor.as_text` (accessor methods)

**Analog:** `SpatialAccessor.area` — `pycopg/spatial.py` lines 2455–2532

**Template structure** (spatial.py lines 2509–2532 — the body WITHOUT the `where=` shim):
```python
        _check_into(into, "area")
        sql, params = build_area_sql(
            table,
            geom=geom,
            schema=schema,
            unit=unit,
            columns=columns,
            filter=filter,
            order_by=order_by,
            limit=limit,
        )
        return self._run(sql, params, into, geom)
```

**Critical difference for new methods (D-09):** Do NOT copy the `where=` shim block (lines 2509–2520). New methods are born-clean:
```python
# DO NOT COPY THIS BLOCK — pre-1.0 migration aid only:
#   if where is not None:
#       if filter is not None:
#           raise TypeError(...)
#       warnings.warn("The 'where' keyword argument...", DeprecationWarning, stacklevel=2)
#       filter = where
```

**`as_geojson` signature** (no `where=`, no `unit=`):
```python
    def as_geojson(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        max_decimal_digits: int = 6,
        include_bbox: bool = False,
        include_crs: bool = False,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        _check_into(into, "as_geojson")
        sql, params = build_geojson_sql(
            table, geom=geom, schema=schema,
            max_decimal_digits=max_decimal_digits,
            include_bbox=include_bbox, include_crs=include_crs,
            columns=columns, filter=filter, order_by=order_by, limit=limit,
        )
        return self._run(sql, params, into, geom)
```

**`as_text` signature** (same minus the options params):
```python
    def as_text(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        max_decimal_digits: int | None = None,
        into: str = "rows",
        columns: list[str] | None = None,
        filter: str | None = None,
        order_by: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        _check_into(into, "as_text")
        sql, params = build_text_sql(
            table, geom=geom, schema=schema,
            max_decimal_digits=max_decimal_digits,
            columns=columns, filter=filter, order_by=order_by, limit=limit,
        )
        return self._run(sql, params, into, geom)
```

---

### `SpatialAccessor.as_mvt` (accessor method, bytes return)

**Analog:** `SpatialAccessor.area` structure (spatial.py 2455–2532) but with `_run_mvt` and no `into=` or `_check_into`:

```python
    def as_mvt(
        self,
        table: str,
        *,
        geom: str = "geometry",
        schema: str = "public",
        tile_z: int,
        tile_x: int,
        tile_y: int,
        layer_name: str = "default",
        extent: int = 4096,
        columns: list[str] | None = None,
        feature_id_column: str | None = None,
        srid: int | None = None,
        filter: str | None = None,
    ) -> bytes:
        sql, params = build_mvt_sql(
            table, geom=geom, schema=schema,
            tile_z=tile_z, tile_x=tile_x, tile_y=tile_y,
            layer_name=layer_name, extent=extent,
            columns=columns, feature_id_column=feature_id_column,
            srid=srid, filter=filter,
        )
        return self._run_mvt(sql, params)
```

No `_check_into` call (returns `bytes`, not rows/gdf). No `into=` parameter.

---

### `AsyncSpatialAccessor` mirrors

**Analog:** `AsyncSpatialAccessor.area` — `pycopg/spatial.py` lines 4234–4314

The async pattern (lines 4290–4314):
```python
        await self._check_postgis()   # async-specific: lazy PostGIS guard
        _check_into(into, "area")
        sql, params = build_area_sql(...)
        return await self._run(sql, params, into, geom)
```

**For `async def as_geojson` / `async def as_text`:**
- Add `await self._check_postgis()` before `_check_into`
- Replace `return self._run(...)` with `return await self._run(...)`

**For `async def as_mvt`:**
- Add `await self._check_postgis()`
- Use `return await self._arun_mvt(sql, params)` (the async bytea runner)

---

### `_SCALAR_HELPERS` update

**Analog:** `_SCALAR_HELPERS` — `pycopg/spatial.py` line 1784

```python
# Current (line 1784):
_SCALAR_HELPERS = frozenset({"area", "perimeter", "distance", "centroid"})

# New (add two entries, NOT as_mvt):
_SCALAR_HELPERS = frozenset({"area", "perimeter", "distance", "centroid", "as_geojson", "as_text"})
```

`as_mvt` is explicitly NOT added (it uses `_run_mvt`, not `_run`; it returns `bytes` with no `into=` parameter at all).

---

### `_check_into` (existing — no change, just use it)

**Source:** `pycopg/spatial.py` lines 1796–1818

```python
def _check_into(into: str, helper: str) -> None:
    if into not in _VALID_INTO:
        raise ValueError(f"into must be one of {_VALID_INTO}, got {into!r}")
    if into == "gdf" and helper in _SCALAR_HELPERS:
        raise ValueError(
            f"into='gdf' is invalid for {helper}(): it returns a scalar, "
            "not a geometry"
        )
```

Called as `_check_into(into, "as_geojson")` and `_check_into(into, "as_text")`. Once `_SCALAR_HELPERS` is updated, `into="gdf"` auto-raises for both new scalar serializers. `as_mvt` does NOT call `_check_into`.

---

## Test Patterns

### Injection test pattern (per builder)

**Analog:** `TestBuilderColumnsValidation` — `tests/test_spatial.py` lines 1571–1648

Template to copy for each new builder:
```python
class TestBuildGeojsonSql:
    def test_invalid_table_raises(self):
        with pytest.raises(InvalidIdentifierError):
            build_geojson_sql("'; DROP TABLE foo; --")

    def test_invalid_geom_raises(self):
        with pytest.raises(InvalidIdentifierError):
            build_geojson_sql("roads", geom="'; DROP TABLE foo; --")

    def test_invalid_column_raises(self):
        with pytest.raises(InvalidIdentifierError):
            build_geojson_sql("roads", columns=["'; DROP TABLE foo; --"])
```

For `TestBuildMvtSql` add `feature_id_column` injection test:
```python
    def test_invalid_feature_id_column_raises(self):
        with pytest.raises(InvalidIdentifierError):
            build_mvt_sql("roads", tile_z=0, tile_x=0, tile_y=0,
                          feature_id_column="'; DROP TABLE foo; --")
```

### `_HELPER_CALLS` update

**Analog:** `_HELPER_CALLS` list — `tests/test_spatial.py` lines 1438–1458

Add to `_HELPER_CALLS` (NOT `as_mvt` — different return shape):
```python
    ("as_geojson", {}),
    ("as_text", {}),
```

For `as_mvt`, write a separate routing test class `TestMvtRouting` (similar to `TestAccessorRouting` but with a mock db that returns `[{"mvt": b"\x1a\x05..."}]` from `execute`).

### `test_spatial_serialization_surface` in test_parity.py

**Analog:** `test_spatial_aggregates_surface` — `tests/test_parity.py` lines 170–199

Copy structure exactly, changing frozenset content and docstring:
```python
def test_spatial_serialization_surface():
    """Assert both spatial accessors expose the 3 Phase 44 serialization methods."""
    v44_surface = frozenset({"as_geojson", "as_text", "as_mvt"})

    for cls in (SpatialAccessor, AsyncSpatialAccessor):
        public = {
            name for name, _ in inspect.getmembers(cls) if not name.startswith("_")
        }
        missing = v44_surface - public
        assert (
            not missing
        ), f"{cls.__name__} is missing Phase 44 method(s): {sorted(missing)}"
```

### SQL-shape assertions for `TestBuildMvtSql`

**Analog:** `TestAggregateBuilders` SQL-shape tests — `tests/test_spatial.py` lines 1651+

The `as_mvt` mock test must assert (per RESEARCH.md validation map, criterion #2):
1. `"ST_Transform"` in sql
2. `"ST_AsMVTGeom"` in sql
3. `"ST_TileEnvelope"` in sql — and that the integers z/x/y appear literally
4. `"ST_AsMVT"` in sql
5. `"q.geom_mvt IS NOT NULL"` in sql
6. When `srid=4326`: `"ST_SetSRID"` in sql AND `"4326"` in sql
7. `params == [layer_name, extent]` (only 2 params, not 5)

---

## Shared Patterns

### `validate_identifiers` line-1 guard
**Source:** `pycopg/utils.py` (line 1), called as first statement in every `build_*_sql`
**Apply to:** `build_geojson_sql`, `build_text_sql`, `build_mvt_sql`
**Precedent in spatial.py:** lines 711, 773, 1765

### `int()` injection-safe integer interpolation
**Source:** `pycopg/spatial.py` line 1770 (`build_extent_sql`)
```python
agg_expr = f"ST_SetSRID(ST_Extent(t.{geom})::geometry, {int(srid)}) AS extent"
```
**Apply to:** `build_mvt_sql` — `int(tile_z)`, `int(tile_x)`, `int(tile_y)`, `int(extent)`, `int(srid)`

### `_cols_str(columns)` helper
**Source:** `pycopg/spatial.py` line 146
```python
return ", ".join(columns) if columns else "*"
```
**Apply to:** All three builders — already used in `build_area_sql` for the `SELECT` prefix.

### Born-clean `filter=` only (NO `where=` shim)
**Source:** D-09; the shim block is in `SpatialAccessor.area` lines 2509–2520 (DO NOT COPY)
**Apply to:** All new accessor methods — `as_geojson`, `as_text`, `as_mvt` on both sync and async classes

### `await self._check_postgis()` in async methods
**Source:** `AsyncSpatialAccessor.area` line 4302
**Apply to:** All three `AsyncSpatialAccessor` new methods (before `_check_into` or builder call)

---

## No Analog Found

All new symbols have close analogs in the codebase. No gaps.

---

## Metadata

**Analog search scope:** `pycopg/spatial.py` (full), `tests/test_spatial.py` (full), `tests/test_parity.py` (full)
**Files scanned:** 3 source files + CONTEXT.md + RESEARCH.md
**Pattern extraction date:** 2026-06-29
