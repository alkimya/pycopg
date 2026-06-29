# Phase 44: Spatial v2 — Serialization + MVT — Research

**Researched:** 2026-06-29
**Domain:** PostGIS serialization (ST_AsGeoJSON, ST_AsText, ST_AsMVT) + pycopg spatial accessor extension
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01: `as_mvt` parameter surface** — Pragmatic-full. Signature (all keyword-only except `table`):
```python
def as_mvt(
    self,
    table: str,
    *,
    geom: str = "geometry",
    schema: str = "public",
    tile_z: int,                       # required kw-only
    tile_x: int,                       # required kw-only
    tile_y: int,                       # required kw-only
    layer_name: str = "default",
    extent: int = 4096,
    columns: list[str] | None = None,
    feature_id_column: str | None = None,
    srid: int | None = None,
    filter: str | None = None,
) -> bytes:
```

**D-02: tile coordinate names** — `tile_z`, `tile_x`, `tile_y` (Z/X/Y order), required keyword-only, `int()` coercion, fed to `ST_TileEnvelope(z, x, y)`.

**D-03: target CRS always 3857** — Builder ALWAYS emits the full pipeline:
```sql
SELECT ST_AsMVT(q.*, layer_name, extent, 'geom_mvt'[, feature_id_name])
FROM (
    SELECT <columns>, ST_AsMVTGeom(
        ST_Transform(t.{geom}, 3857),
        ST_TileEnvelope({tile_z}, {tile_x}, {tile_y}),
        {extent}
    ) AS geom_mvt
    FROM {schema}.{table} AS t
    [WHERE {filter}]
) AS q
WHERE q.geom_mvt IS NOT NULL
```
No raw-geometry shortcut. `q.geom_mvt IS NOT NULL` drops geometries that clip away. ST_TileEnvelope is PostGIS ≥ 3.0 — document, don't gate (library floor is 3.0).

**D-04: `srid` source override** — `None` → `ST_Transform(t.{geom}, 3857)`. When set → `ST_Transform(ST_SetSRID(t.{geom}, {int(srid)}), 3857)`. Named `srid=` (consistent with spatial surface). `int(srid)` = injection-safe.

**D-05: always returns `bytes`** — Single bytea cell extracted from `rows[0]`; `memoryview`/`bytes` → `bytes(...)`; `None` → `b""`. (`as_mvt` does NOT use `_run`; needs a dedicated `_run_mvt`/`_arun_mvt` runner.)

**D-06: `as_geojson` options** — `max_decimal_digits: int = 6`, `include_bbox: bool = False`, `include_crs: bool = False`. Options bitmask: `(1 if include_bbox else 0) | (2 if include_crs else 0)` → passed as `%s`. Generated SQL: `SELECT <cols>, ST_AsGeoJSON(t.{geom}, %s, %s) AS geojson FROM …`. Result key `geojson` (JSON string; callers call `json.loads()` if needed).

**D-07: `as_text` precision** — `max_decimal_digits: int | None = None`. `None` → one-arg `ST_AsText(t.{geom})`. When set → two-arg `ST_AsText(t.{geom}, %s)`. Result key `wkt`.

**D-08: `columns=` on scalar serializers** — Both `as_geojson` and `as_text` carry `columns=`, `filter=`, `order_by=`, `limit=`. Both added to `_SCALAR_HELPERS` so `into="gdf"` raises `ValueError`.

**D-09: kw-only freeze** — `table` positional; everything else keyword-only. Born-clean `filter=` ONLY — NO `where=` deprecated alias.

**D-10: sync/async parity** — Every method mirrored 1:1 on `AsyncSpatialAccessor`, edited in the same change. Enforced by `test_accessor_parity` AND `test_accessor_parameter_kind_parity`.

### Claude's Discretion

- `as_geojson`/`as_text` builder factoring: each MUST keep its own injection test + frozen result key (`geojson` / `wkt`).
- `as_mvt` gets its own dedicated builder (`build_mvt_sql`) — NOT shared with scalar machinery.
- `as_mvt` bytea-extraction runner: exact mechanics of `_run_mvt`/`_arun_mvt` vs inline.
- Options-bitmask computation for `as_geojson` — inline vs helper.
- Plan/wave decomposition (scalar serializers + `as_mvt` as separate plans is recommended).

### Deferred Ideas (OUT OF SCOPE)

- Non-3857 MVT target CRS
- Per-geometry ST_AsMVTGeom clip/buffer tuning
- KML/GML/SVG/EncodedPolyline serializers
- ST_TileEnvelope PostGIS < 3.0 runtime guard
- `json` auto-parse for `as_geojson`
- Carry-forward to Phase 47 (release): IN-02 double-suffix typos, WR-01 where= docs, P43 WR-01/WR-02
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SPAT2-10 | `db.spatial.as_geojson(table, geom, max_decimal_digits=6, ...)` — ST_AsGeoJSON; text return | D-06: options bitmask + two-arg SQL; builder clones `build_area_sql` pattern |
| SPAT2-11 | `db.spatial.as_text(table, geom, ...)` — ST_AsText; text return | D-07: conditional one-arg vs two-arg SQL; `wkt` result key |
| SPAT2-12 | `db.spatial.as_mvt(table, geom, tile_z, tile_x, tile_y, ...)` — bytes | D-01..D-05: full pipeline; dedicated builder + runner; memoryview→bytes coercion |
| SPAT2-13 | Full async parity + validate_identifiers + injection tests + test_accessor_parity full surface | D-09/D-10; injection tests per builder; `test_spatial_serialization_surface` + full v2 surface parity |
</phase_requirements>

---

## Summary

Phase 44 adds three serialization methods to `db.spatial.*` / `async_db.spatial.*`:
`as_geojson`, `as_text`, and `as_mvt`. The first two follow the established scalar-helper
pattern (`_SCALAR_HELPERS`, `_append_tail`, `_run`) with minor variations (options bitmask,
conditional precision arg). `as_mvt` is the phase's critical-path item — it has a unique SQL
shape (subquery aggregate), a unique return type (`bytes`), and needs its own builder +
dedicated runner that bypasses `_run` entirely.

This is the last spatial v2 phase. SPAT2-13 finalizes here: `test_accessor_parity` and
`test_accessor_parameter_kind_parity` must cover the full P42+P43+P44 spatial v2 surface, and
a new `test_spatial_serialization_surface` function asserts all three P44 methods exist on both
accessors. The `test_accessor_parity` generic check already catches missing methods automatically
once both accessors are updated.

**Primary recommendation:** Plan as two work units: (1) scalar serializers (`as_geojson` +
`as_text`) as one plan — trivial builder clones with frozen result keys; (2) `as_mvt` as its
own plan — unique subquery shape, bytea runner, multi-arg injection surface, and live
decode-to-feature-count integration test.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| SQL builder (GeoJSON/WKT/MVT) | Python module level | — | Pure functions; no DB, no self; shared between sync and async |
| Identifier validation | Python module level | — | Line-1 guard in every `build_*_sql`; `validate_identifiers` from `pycopg.utils` |
| Options bitmask computation | Python module level | — | Two bools → one int; inline in `build_geojson_sql`; no DB |
| Bytea cell extraction + coercion | `SpatialAccessor._run_mvt` / `AsyncSpatialAccessor._arun_mvt` | — | Dedicated runner; reads `rows[0]` first value; `None`→`b""` |
| `into=` rejection for scalar | `_check_into` / `_SCALAR_HELPERS` | — | Existing pattern; add `"as_geojson"`, `"as_text"` to frozenset |
| MVT tile pipeline | PostGIS (ST_Transform + ST_AsMVTGeom + ST_TileEnvelope + ST_AsMVT) | — | All in DB; `as_mvt` builder assembles the SQL, does not touch the binary |
| Parity enforcement | `tests/test_parity.py` | `tests/test_spatial.py` | `test_accessor_parity` (name-level) + `test_accessor_parameter_kind_parity` (kind-level) |

---

## Standard Stack

### Core (no new dependencies)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `psycopg3` | already pinned | `database.execute` returns `list[dict]` where bytea = `bytes` | Project baseline |
| `pycopg.utils.validate_identifiers` | internal | Line-1 guard for all identifiers | Established pattern (Pitfall 1) |
| `pycopg.spatial._append_tail` | internal | WHERE/ORDER BY/LIMIT tail for scalar builders | Shared by all spatial builders |
| PostGIS 3.0+ | installed | `ST_AsGeoJSON`, `ST_AsText`, `ST_AsMVT`, `ST_AsMVTGeom`, `ST_TileEnvelope` | Local instance confirmed: PostGIS 3.6 |

Zero new runtime dependencies — constraint from SPAT2-13 / CONTEXT.md.

### Test-Only (dev group — no impact on runtime)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `mapbox-vector-tile` | 2.2.0 (PyPI) | MVT decode for integration test feature-count assertion | OPTIONAL — pure Python decoder in conftest is lighter (see below) |
| Pure Python MVT decoder | N/A (inline in test) | Parse protobuf to count layers/features without deps | PREFERRED — no new dep, proven working (see Code Examples) |

**Recommendation:** Use the pure Python MVT decoder (6 lines, inline in test helper or conftest).
`mapbox-vector-tile` is a real package (published 2025-07-08, author Rob Marianski,
`github.com/tilezen/mapbox-vector-tile`) but adding it to the dev group is overhead for what
a minimal protobuf reader handles cleanly. The pure decoder was verified against a live PostGIS
3.6 MVT blob and correctly returns layers=1, features=1 for a single-point tile.

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Pure Python MVT decoder | `mapbox-vector-tile` pkg | `mapbox-vector-tile` needs `protobuf` dep; pure decoder is 15 lines and covers the feature-count assertion |
| `int()` coercion for tile coords | `%s` params | `int()` is injection-safe for integer literals in SQL; `%s` would also work but is unnecessary for true integers |

**Installation:** No new packages to install at runtime. If `mapbox-vector-tile` is chosen for tests: `uv add mapbox-vector-tile --dev` (but pure decoder is preferred).

---

## Package Legitimacy Audit

This phase adds **zero new runtime packages**. The dev-group decision (pure Python decoder vs
`mapbox-vector-tile`) is documented above.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| mapbox-vector-tile | PyPI | ~8 yrs | N/A | github.com/tilezen/mapbox-vector-tile | [ASSUMED] | Optional test-only — prefer pure decoder (no dep needed) |

**slopcheck** was unavailable at research time. `mapbox-vector-tile` is tagged `[ASSUMED]` for
provenance. It passes `pip index versions` check (2.2.0 available) and matches the Tilezen
organization GitHub repo — but the pure Python decoder is the PREFERRED approach precisely
because it avoids this dependency entirely.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none (no new runtime deps; test-only dep deferred to planner discretion)

---

## Architecture Patterns

### System Architecture Diagram

```
User code
    │
    ▼
db.spatial.as_geojson("roads", geom="geometry", max_decimal_digits=6)
db.spatial.as_text("roads", geom="geometry")
    │
    ▼
build_geojson_sql() / build_text_sql()   ← pure builder
  validate_identifiers(table, schema, geom, *columns)  [line 1]
  options = (1 if include_bbox else 0) | (2 if include_crs else 0)
  SELECT <cols>, ST_AsGeoJSON(t.geom, %s, %s) AS geojson FROM schema.table AS t
  _append_tail(sql, filter, order_by, limit, has_where=False)
  returns (sql, [max_decimal_digits, options])
    │
    ▼
_check_into(into, "as_geojson")  # gdf rejected via _SCALAR_HELPERS
    │
    ▼
_run(sql, params, into="rows", geometry_column=geom)
→ self._db.execute(sql, params) → list[dict]   [rows[*]["geojson"] = JSON string]


db.spatial.as_mvt("roads", tile_z=12, tile_x=2048, tile_y=1361)
    │
    ▼
build_mvt_sql()   ← dedicated pure builder
  validate_identifiers(table, schema, geom, *columns, feature_id_column)  [line 1]
  SELECT ST_AsMVT(q.*, %s, %s, 'geom_mvt'[, %s])
  FROM (
    SELECT <columns>, ST_AsMVTGeom(
      ST_Transform([ST_SetSRID(]t.{geom}[, {int(srid)}]), 3857),
      ST_TileEnvelope({int(z)}, {int(x)}, {int(y)}),
      {int(extent)}
    ) AS geom_mvt
    FROM {schema}.{table} AS t
    [WHERE {filter}]
  ) AS q
  WHERE q.geom_mvt IS NOT NULL
  returns (sql, params_list)
    │
    ▼
_run_mvt(sql, params)   ← NEW dedicated runner (no into=)
  rows = self._db.execute(sql, params)   → list[dict]
  val = rows[0][first_col]              → bytes or None
  return bytes(val) if isinstance(val, memoryview) else (val if val is not None else b"")
→ bytes  (always; b"" for empty tile)
```

### Recommended Project Structure

No new files. Changes are contained to:
```
pycopg/
└── spatial.py   # Add build_geojson_sql, build_text_sql, build_mvt_sql
                 # Add _run_mvt, _arun_mvt helpers in SpatialAccessor/AsyncSpatialAccessor
                 # Add as_geojson, as_text, as_mvt methods to both accessor classes
                 # Add "as_geojson", "as_text" to _SCALAR_HELPERS frozenset
tests/
└── test_spatial.py  # SQL-shape mock tests + injection tests + live integration
tests/
└── test_parity.py   # Add test_spatial_serialization_surface + update _HELPER_CALLS
```

### Pattern 1: Scalar Serializer Builder (`build_geojson_sql`)

Clone of `build_area_sql` / `build_perimeter_sql` — same structure, different ST_* call and params list.

**What:** Pure module-level function returning `(sql, params)`. Validates all identifiers first.
**When to use:** `as_geojson`, `as_text` — any scalar text serializer that returns one computed text column per row.

```python
# Source: pycopg/spatial.py build_area_sql pattern (lines 662-721) + CONTEXT.md D-06
def build_geojson_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    max_decimal_digits: int = 6,
    include_bbox: bool = False,
    include_crs: bool = False,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    validate_identifiers(table, schema, geom)         # LINE 1: injection guard
    if columns:
        validate_identifiers(*columns)
    options = (1 if include_bbox else 0) | (2 if include_crs else 0)
    sql = (
        f"SELECT {_cols_str(columns)}, "
        f"ST_AsGeoJSON(t.{geom}, %s, %s) AS geojson "
        f"FROM {schema}.{table} AS t"
    )
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, [max_decimal_digits, options]
```

### Pattern 2: `build_text_sql` — conditional one-arg vs two-arg

```python
# Source: CONTEXT.md D-07 + PostGIS docs (verified locally against PostGIS 3.6)
def build_text_sql(
    table: str,
    geom: str = "geometry",
    schema: str = "public",
    *,
    max_decimal_digits: int | None = None,
    columns: list[str] | None = None,
    filter: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    validate_identifiers(table, schema, geom)         # LINE 1: injection guard
    if columns:
        validate_identifiers(*columns)
    if max_decimal_digits is not None:
        st_call = f"ST_AsText(t.{geom}, %s) AS wkt"
        params = [max_decimal_digits]
    else:
        st_call = f"ST_AsText(t.{geom}) AS wkt"
        params = []
    sql = f"SELECT {_cols_str(columns)}, {st_call} FROM {schema}.{table} AS t"
    sql = _append_tail(sql, filter, order_by, limit, has_where=False)
    return sql, params
```

### Pattern 3: `build_mvt_sql` — dedicated subquery aggregate builder

```python
# Source: CONTEXT.md D-01..D-04 + FEATURES.md ~line 494 + local PostGIS 3.6 verification
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
    validate_identifiers(table, schema, geom)         # LINE 1: injection guard
    if columns:
        validate_identifiers(*columns)
    if feature_id_column is not None:
        validate_identifiers(feature_id_column)       # identifier, not a param

    # Build transform expression (D-04)
    z, x, y, ext = int(tile_z), int(tile_x), int(tile_y), int(extent)
    if srid is not None:
        transform = f"ST_Transform(ST_SetSRID(t.{geom}, {int(srid)}), 3857)"
    else:
        transform = f"ST_Transform(t.{geom}, 3857)"

    # Build inner SELECT
    col_prefix = (_cols_str(columns) + ", ") if columns else ""
    inner_select = (
        f"SELECT {col_prefix}ST_AsMVTGeom("
        f"{transform}, "
        f"ST_TileEnvelope({z}, {x}, {y}), "
        f"{ext}) AS geom_mvt "
        f"FROM {schema}.{table} AS t"
    )
    if filter:
        inner_select += f" WHERE {filter}"

    # Build ST_AsMVT aggregate call (D-03)
    # layer_name, extent = %s params; feature_id_column = identifier not param
    if feature_id_column is not None:
        # feature_id_column already validated as identifier above
        agg_call = f"ST_AsMVT(q.*, %s, %s, 'geom_mvt', '{feature_id_column}')"
    else:
        agg_call = "ST_AsMVT(q.*, %s, %s, 'geom_mvt')"
    sql = (
        f"SELECT {agg_call} "
        f"FROM ({inner_select}) AS q "
        f"WHERE q.geom_mvt IS NOT NULL"
    )
    return sql, [layer_name, ext]
```

**NOTE on `feature_id_column`:** PostGIS requires the feature_id column to be an integer type
in the source data. If it is not, PostGIS raises `InternalError_: mvt_agg_transfn: Could not
find column 'X' of integer type`. This is a PostGIS constraint; document in the docstring.
Since it is a validated identifier (not a %s param), it is safe to interpolate directly into
the SQL string — but only after passing `validate_identifiers`.

### Pattern 4: `_run_mvt` — dedicated bytea single-cell runner

```python
# Source: CONTEXT.md D-05 + local psycopg3 verification
def _run_mvt(self, sql: str, params: list) -> bytes:
    rows = self._db.execute(sql, params)
    # ST_AsMVT always returns exactly one row; the aggregate returns b"" for
    # zero matching rows, NULL is theoretically possible only if the aggregate
    # is applied over a zero-row input (also returns b"" per local tests).
    val = rows[0][next(iter(rows[0]))]  # first column value
    if isinstance(val, memoryview):
        return bytes(val)
    return val if val is not None else b""

# Async mirror:
async def _arun_mvt(self, sql: str, params: list) -> bytes:
    rows = await self._db.execute(sql, params)
    val = rows[0][next(iter(rows[0]))]
    if isinstance(val, memoryview):
        return bytes(val)
    return val if val is not None else b""
```

**Verified behavior (psycopg3 with dict_row + PostGIS 3.6):**
- Non-empty tile: `bytes` object, e.g., `b'\x1a\x16\n\x04...'` (starts with `0x1a` = field 3 wire-type 2 = layer tag)
- Empty tile (all geometry clipped away): `b""` — NOT `None`
- Zero-row inner subquery: `b""` — NOT `None`
- NULL bytea: `None` — only possible if aggregate is `NULL`, not seen with `ST_AsMVT`

So `val is not None` guard is a defensive `b""` fallback that covers an edge case not observed
in practice but required by the D-05 contract.

### Pattern 5: `_SCALAR_HELPERS` update and accessor method wiring

```python
# Source: pycopg/spatial.py line 1784 — add two entries
_SCALAR_HELPERS = frozenset({"area", "perimeter", "distance", "centroid", "as_geojson", "as_text"})
```

Accessor method template for `as_geojson` (no `where=` shim — born clean per D-09):

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
    _check_into(into, "as_geojson")   # gdf rejected via _SCALAR_HELPERS
    sql, params = build_geojson_sql(
        table, geom=geom, schema=schema,
        max_decimal_digits=max_decimal_digits,
        include_bbox=include_bbox, include_crs=include_crs,
        columns=columns, filter=filter, order_by=order_by, limit=limit,
    )
    return self._run(sql, params, into, geom)
```

### Anti-Patterns to Avoid

- **Skipping `validate_identifiers` in a new builder:** Silent injection hole. `build_mvt_sql` has 5 potential identifiers — `table`, `schema`, `geom`, each item in `columns`, and `feature_id_column`. All must be validated at builder entry.
- **Adding `as_mvt` to `_SCALAR_HELPERS`:** It does NOT use `_run`; it returns `bytes` from `_run_mvt`. Adding it to `_SCALAR_HELPERS` would cause wrong error messages and bypass the bytea runner.
- **Passing `feature_id_column` as `%s` to ST_AsMVT:** PostGIS requires it to be a literal SQL identifier embedded in the query string (it reads the column name from the query structure, not from a bind parameter). It must be identifier-validated and interpolated directly.
- **Adding `where=` deprecated alias to new methods:** These are born-clean 1.0 methods. No `where=` shim.
- **Editing sync but not async (or vice versa):** Violates D-10. `test_accessor_parameter_kind_parity` will catch KIND drift; `test_accessor_parity` will catch missing methods.
- **Not updating `_HELPER_CALLS` in `test_spatial.py`:** The `TestAccessorRouting` parametrized routing tests cover every accessor method. Add `("as_geojson", {})`, `("as_text", {})` to `_HELPER_CALLS`. `as_mvt` is NOT added to `_HELPER_CALLS` (different return shape — add a dedicated routing test).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| GeoJSON serialization | Custom geometry→JSON converter | ST_AsGeoJSON in SQL | PostGIS handles all geometry types, CRS, bbox; custom serialization misses edge cases |
| WKT serialization | Custom WKB→WKT decoder | ST_AsText in SQL | PostGIS handles multi-geometries, Z/M coords, full precision |
| MVT tile encoding | Custom protobuf encoder | ST_AsMVT aggregate | MVT encoding requires coordinate space transform + clipping + protobuf; PostGIS is the only correct tool |
| MVT tile envelope | Manual extent math | ST_TileEnvelope(z, x, y) | Tile envelope formula is non-trivial (Web Mercator bounds, power-of-2 subdivision); PostGIS does it correctly |
| MVT decode for tests | Full protobuf library | Pure Python varint reader | 15 lines; no dep; proven correct against PostGIS 3.6 MVT output (see Code Examples) |
| Identifier injection guard | Regex in builder | `validate_identifiers` from `pycopg.utils` | Already exists; must be called as LINE 1 |

**Key insight:** MVT generation in PostGIS is the ecosystem-standard approach. The ST_Transform → ST_AsMVTGeom → ST_AsMVT pipeline is documented in PostGIS 3.x official docs and is what every production tile server using PostGIS runs. Any hand-rolled alternative would be wrong.

---

## Common Pitfalls

### Pitfall 1: `validate_identifiers` dropped in a new builder
**What goes wrong:** Builder is written without the line-1 guard. SQL injection is possible via `table`, `geom`, `columns`, or `feature_id_column`. Suite stays green (correctness tests don't test injection). Precedent: COPY rewrite in v0.10.0.
**Why it happens:** Each builder is written in isolation; the security invariant is not obvious from the function signature.
**How to avoid:** Line 1 of every `build_*_sql` is `validate_identifiers(table, schema, geom)`. Add explicit injection test for every builder (including `feature_id_column` for `build_mvt_sql`).
**Warning signs:** A `build_*_sql` function whose first statement is not `validate_identifiers`.

### Pitfall 2: MVT wrong coordinate system (tiles show nothing)
**What goes wrong:** ST_AsMVT is called on raw SRID 4326 geometry without `ST_Transform` + `ST_AsMVTGeom`. The tile is produced without error but coordinates are in degrees, not pixel space. Map renderers show nothing.
**Why it happens:** ST_AsGeoJSON works fine on 4326 data; applying the same pattern to ST_AsMVT silently produces corrupted tiles.
**How to avoid:** D-03 is non-negotiable — builder ALWAYS emits `ST_Transform(…, 3857)` AND `ST_AsMVTGeom`. Integration test MUST decode the MVT to check feature count (not just `isinstance(result, bytes)`).
**Warning signs:** Generated SQL doesn't contain `ST_Transform` or `ST_AsMVTGeom`.

### Pitfall 3: SRID-0 / untagged column produces wrong transform
**What goes wrong:** A geometry column stored with SRID 0 (untagged) is transformed to 3857, but PostGIS uses SRID 0 = "unknown" and the transform produces wrong or zero results without error.
**Why it happens:** `ST_Transform(t.geom, 3857)` trusts the stored SRID. SRID 0 = undefined = silent wrong result.
**How to avoid:** D-04 `srid` override parameter: `ST_Transform(ST_SetSRID(t.geom, {int(srid)}), 3857)`. Document the SRID-0 failure mode in the `as_mvt` docstring. Integration test can verify `srid=4326` override produces the same result as a column with SRID 4326 stored.
**Warning signs:** No `srid=` parameter; docstring does not mention SRID-0.

### Pitfall 4: `feature_id_column` must be integer-typed in the source
**What goes wrong:** Caller passes `feature_id_column="name"` (a text column). PostGIS raises `InternalError_: mvt_agg_transfn: Could not find column 'name' of integer type`.
**Why it happens:** The MVT spec's feature_id must be a 64-bit integer; PostGIS enforces this at query time.
**How to avoid:** Document in the `as_mvt` docstring: "The feature_id_column must reference an integer-type column in the source table." This is a PostGIS constraint; pycopg cannot validate it at builder time. Pass `feature_id_column=None` (the default) to omit.
**Warning signs:** Integration test with `feature_id_column` does not use an integer column.

### Pitfall 5: Accessing bytea cell by column name in `_run_mvt`
**What goes wrong:** `rows[0]["st_asmvt"]` — the auto-generated column name from `ST_AsMVT(q.*, ...)` is `st_asmvt` with the psycopg3 `dict_row` factory (lowercase, no alias). Using a hardcoded key breaks if PostGIS changes the function name casing.
**How to avoid:** Use `rows[0][next(iter(rows[0]))]` — first key from the dict (the query returns exactly one column). Alternatively, alias the column: `SELECT ST_AsMVT(…) AS mvt` and then `rows[0]["mvt"]`. Using an alias is cleaner and makes the key predictable in tests — prefer `AS mvt` in `build_mvt_sql`.
**Warning signs:** Hardcoded `rows[0]["st_asmvt"]` — fragile; use alias or first-key accessor.

### Pitfall 6: `test_accessor_parameter_kind_parity` failure on `as_mvt`
**What goes wrong:** `as_mvt` sync has `tile_z: int` as keyword-only; async accidentally has it as positional-or-keyword. `test_accessor_parameter_kind_parity` catches the KIND mismatch.
**Why it happens:** The `*` separator must appear before `tile_z` in the async definition too. Copy-paste from sync omits the `*` or inserts it in the wrong place.
**How to avoid:** Edit both sync and async in the same commit. Verify by running `test_accessor_parameter_kind_parity` before merging.
**Warning signs:** `as_mvt` added to sync only; async added in a follow-up commit.

### Pitfall 7: `into="gdf"` not rejected for `as_geojson` / `as_text`
**What goes wrong:** `as_geojson(table, into="gdf")` is called. `_check_into` does not raise because `"as_geojson"` is not in `_SCALAR_HELPERS`. The `_run` method calls `to_geodataframe` with a `geojson` text column — geopandas tries to parse text as WKB and raises confusingly.
**How to avoid:** Add `"as_geojson"` and `"as_text"` to `_SCALAR_HELPERS`. Do NOT add `"as_mvt"` (it has its own return path).
**Warning signs:** `_SCALAR_HELPERS` frozenset not updated after adding the two scalar serializers.

---

## Code Examples

### Pure Python MVT Decoder (test helper — no runtime deps)

```python
# Source: verified against PostGIS 3.6 ST_AsMVT output (2026-06-29)
# Layer = protobuf field 3, wire type 2 (length-delimited), tag = 0x1a
# Feature inside layer = field 2, wire type 2, tag = 0x12

def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    result, shift = 0, 0
    while pos < len(data):
        b = data[pos]; pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80): break
        shift += 7
    return result, pos


def _count_mvt_features(blob: bytes | memoryview) -> int:
    """Return total feature count across all layers in an MVT blob.

    Returns 0 for an empty blob (b'' = empty tile).
    """
    data = bytes(blob) if isinstance(blob, memoryview) else blob
    pos, features = 0, 0
    while pos < len(data):
        tag, pos = _read_varint(data, pos)
        fn, wt = tag >> 3, tag & 0x07
        if wt == 0:
            _, pos = _read_varint(data, pos)
        elif wt == 1:
            pos += 8
        elif wt == 2:
            length, pos = _read_varint(data, pos)
            if fn == 3:  # MVT layer field
                end = pos + length
                lpos = pos
                while lpos < end:
                    t2, lpos = _read_varint(data, lpos)
                    f2, w2 = t2 >> 3, t2 & 0x07
                    if w2 == 0: _, lpos = _read_varint(data, lpos)
                    elif w2 == 2:
                        l2, lpos = _read_varint(data, lpos)
                        if f2 == 2: features += 1   # feature
                        lpos += l2
                    elif w2 == 5: lpos += 4
                    elif w2 == 1: lpos += 8
                    else: break
            pos += length
        elif wt == 5:
            pos += 4
        else:
            break
    return features

# Test: count_mvt_features(blob_from_single_point) == 1
# Test: count_mvt_features(b"") == 0
```

### ST_AsGeoJSON Options Bitmask (verified PostGIS 3.6)

```python
# Source: CONTEXT.md D-06 + local PostGIS 3.6 test (2026-06-29)
# options=0: {"type":"Point","coordinates":[…]}            — no bbox, no CRS
# options=1: {"type":"Point","bbox":[…],"coordinates":[…]} — bbox included
# options=2: {"type":"Point","crs":{…},"coordinates":[…]}  — short CRS included
# options=3: bbox + CRS both included

options = (1 if include_bbox else 0) | (2 if include_crs else 0)
```

### MVT SQL Shape (canonical from D-03)

```sql
-- Source: CONTEXT.md D-03 + FEATURES.md ~line 494 + local PostGIS 3.6 verification
-- Without srid override (D-04 None path):
SELECT ST_AsMVT(q.*, %s, %s, 'geom_mvt') AS mvt
FROM (
    SELECT ST_AsMVTGeom(
        ST_Transform(t.geometry, 3857),
        ST_TileEnvelope(12, 2048, 1361),   -- z,x,y as int() literals
        4096                                -- extent as int() literal
    ) AS geom_mvt
    FROM public.roads AS t
    WHERE active = true                     -- filter= goes here, in the inner query
) AS q
WHERE q.geom_mvt IS NOT NULL

-- With srid=4326 override (D-04 set path):
-- ST_Transform(ST_SetSRID(t.geometry, 4326), 3857)
```

Params list: `[layer_name, extent]` — only 2 `%s` placeholders because tile coords and
`extent` are injected as `int()` literals (injection-safe), and `feature_id_column` (when set)
is a validated identifier interpolated directly.

### `_run_mvt` coercion contract (D-05)

```python
# Source: CONTEXT.md D-05 + psycopg3 local verification (2026-06-29)
# psycopg3 returns bytes (not memoryview) for bytea with dict_row factory.
# ST_AsMVT returns b"" (not None) for zero matching rows.
# Defensive None→b"" handles theoretical NULL aggregate case.

val = rows[0][next(iter(rows[0]))]       # first col value (prefer AS mvt alias)
return bytes(val) if isinstance(val, memoryview) else (val if val is not None else b"")
```

### Injection-test template (per builder)

```python
# Source: tests/test_spatial.py injection test pattern (lines ~1578-1652)
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

For `build_mvt_sql` add also `feature_id_column` injection test:
```python
    def test_invalid_feature_id_column_raises(self):
        with pytest.raises(InvalidIdentifierError):
            build_mvt_sql("roads", tile_z=0, tile_x=0, tile_y=0,
                          feature_id_column="'; DROP TABLE foo; --")
```

---

## Runtime State Inventory

Phase 44 is a greenfield addition (new methods + new test assertions). No renames, no refactors.
This section is SKIPPED — no runtime state inventory needed.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | Integration tests | ✓ | local (peer auth) | Use `PGDATABASE=pycopg_test2` per MEMORY |
| PostGIS | ST_AsGeoJSON/ST_AsText/ST_AsMVT | ✓ | 3.6 (PostGIS 3.6 USE_GEOS=1) | — |
| ST_AsMVT | as_mvt integration test | ✓ | PostGIS 3.6 (confirmed in pg_proc) | — |
| ST_TileEnvelope | as_mvt pipeline | ✓ | PostGIS 3.6 (confirmed in pg_proc) | — |
| ST_AsMVTGeom | as_mvt pipeline | ✓ | PostGIS 3.6 (confirmed in pg_proc) | — |
| uv | tests | ✓ | current | — |
| mapbox-vector-tile (PyPI) | MVT decode in test | ✗ (not installed) | — | Pure Python decoder (PREFERRED) |

**Missing dependencies with fallback:**
- `mapbox-vector-tile` — not needed; pure Python decoder handles the integration test assertion.

**Missing dependencies with no fallback:** None.

---

## Validation Architecture

`workflow.nyquist_validation` key is absent from `.planning/config.json` — treated as enabled.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7+ with pytest-asyncio |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_spatial.py tests/test_parity.py -x -q` |
| Full suite command | `uv run pytest` (coverage gate `--cov-fail-under=95`) |

**IMPORTANT:** Integration tests require `PGDATABASE=pycopg_test2` (see MEMORY: pycopg_test DB broken).

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SPAT2-10 | `as_geojson` SQL shape: options bitmask; `include_bbox=True` → `options=1`; `include_crs=True` → `options=2` | unit (mock) | `uv run pytest tests/test_spatial.py -k "TestBuildGeojsonSql" -x -q` | ❌ Wave 0 |
| SPAT2-10 | `as_geojson` injection: malicious table/geom/column raises `InvalidIdentifierError` | unit (mock) | `uv run pytest tests/test_spatial.py -k "geojson_invalid" -x -q` | ❌ Wave 0 |
| SPAT2-10 | `as_geojson` live: returns `list[dict]` with `geojson` key as JSON string | integration | `PGDATABASE=pycopg_test2 uv run pytest tests/test_spatial.py -k "as_geojson" -x -q` | ❌ Wave 0 |
| SPAT2-10 | `as_geojson(into="gdf")` raises `ValueError` | unit (mock) | `uv run pytest tests/test_spatial.py -k "geojson_gdf" -x -q` | ❌ Wave 0 |
| SPAT2-11 | `as_text` SQL shape: one-arg vs two-arg conditional | unit (mock) | `uv run pytest tests/test_spatial.py -k "TestBuildTextSql" -x -q` | ❌ Wave 0 |
| SPAT2-11 | `as_text` injection: malicious identifiers raise `InvalidIdentifierError` | unit (mock) | `uv run pytest tests/test_spatial.py -k "text_invalid" -x -q` | ❌ Wave 0 |
| SPAT2-11 | `as_text` live: returns `list[dict]` with `wkt` key | integration | `PGDATABASE=pycopg_test2 uv run pytest tests/test_spatial.py -k "as_text" -x -q` | ❌ Wave 0 |
| SPAT2-12 | `as_mvt` SQL shape: contains `ST_Transform`, `ST_AsMVTGeom`, `ST_TileEnvelope`, `ST_AsMVT`, `q.geom_mvt IS NOT NULL`; `srid=` branch includes `ST_SetSRID` | unit (mock) | `uv run pytest tests/test_spatial.py -k "TestBuildMvtSql" -x -q` | ❌ Wave 0 |
| SPAT2-12 | `as_mvt` injection: malicious table/geom/columns/feature_id_column raises `InvalidIdentifierError` | unit (mock) | `uv run pytest tests/test_spatial.py -k "mvt_invalid" -x -q` | ❌ Wave 0 |
| SPAT2-12 | `as_mvt` live: non-empty tile returns `bytes` with `len > 0`; feature count decoded ≥ 1 | integration | `PGDATABASE=pycopg_test2 uv run pytest tests/test_spatial.py -k "as_mvt and feature_count" -x -q` | ❌ Wave 0 |
| SPAT2-12 | `as_mvt` empty tile: out-of-range coordinates return `b""` (isinstance + zero feature count) | integration | `PGDATABASE=pycopg_test2 uv run pytest tests/test_spatial.py -k "as_mvt and empty_tile" -x -q` | ❌ Wave 0 |
| SPAT2-12 | `as_mvt` always returns `bytes` (not `None`, not `memoryview`) | unit (mock + integration) | above | ❌ Wave 0 |
| SPAT2-13 | `test_spatial_serialization_surface`: both accessors expose `as_geojson`, `as_text`, `as_mvt` | unit (inspection) | `uv run pytest tests/test_parity.py -k "serialization_surface" -x -q` | ❌ Wave 0 |
| SPAT2-13 | `test_accessor_parity(SpatialAccessor, AsyncSpatialAccessor)` passes with all 3 new methods | unit (inspection) | `uv run pytest tests/test_parity.py -k "test_accessor_parity" -x -q` | ✅ (auto-extends) |
| SPAT2-13 | `test_accessor_parameter_kind_parity` passes (kw-only markers match sync/async) | unit (inspection) | `uv run pytest tests/test_parity.py -k "kind_parity" -x -q` | ✅ (auto-extends) |
| SPAT2-13 | `_HELPER_CALLS` updated with `("as_geojson", {})`, `("as_text", {})` | unit (routing) | `uv run pytest tests/test_spatial.py -k "TestAccessorRouting" -x -q` | ✅ (auto-extends) |

### Specific SQL-shape assertions for `as_mvt` (criterion #2)

The SQL-shape mock test must verify:
1. `"ST_Transform"` in sql
2. `"ST_AsMVTGeom"` in sql
3. `"ST_TileEnvelope"` in sql (with correct z, x, y integers)
4. `"ST_AsMVT"` in sql
5. `"q.geom_mvt IS NOT NULL"` in sql
6. When `srid=4326` is passed: `"ST_SetSRID"` in sql AND `"4326"` in sql
7. `layer_name` and `extent` are in params list (not interpolated)

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_spatial.py tests/test_parity.py -x -q`
- **Per wave merge:** `uv run pytest` (full suite, coverage gate)
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_spatial.py` — `TestBuildGeojsonSql`, `TestBuildTextSql`, `TestBuildMvtSql` classes
- [ ] `tests/test_spatial.py` — integration tests for `as_geojson`, `as_text`, `as_mvt` (live PostGIS)
- [ ] `tests/test_parity.py` — `test_spatial_serialization_surface` function
- [ ] `tests/test_spatial.py` — `_HELPER_CALLS` updated + `as_mvt` routing test

*(Existing test infrastructure covers the framework; only new test classes/functions are needed.)*

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Raw SQL for GeoJSON | `ST_AsGeoJSON(geom, maxdecimaldigits, options)` | PostGIS 1.x+ | Standard; 3-arg form with bitmask options has been stable |
| Raw ST_AsMVT + ST_AsMVTGeom boilerplate | `db.spatial.as_mvt()` abstraction | Phase 44 | Removes ~15 lines of tile endpoint boilerplate |
| `where=` deprecated alias | `filter=` born-clean (Phase 41) | Phase 41 | New methods must NOT carry the shim |
| Positional `x, y, z` coords (FEATURES.md pre-Phase 41) | `tile_z`, `tile_x`, `tile_y` kw-only (D-02) | Phase 44 | Z/X/Y order matches URL convention and ST_TileEnvelope arg order |

**PostGIS version notes:**
- `ST_AsGeoJSON` — baseline PostGIS (available since PostGIS 1.x) [VERIFIED: local PostGIS 3.6]
- `ST_AsText` — baseline PostGIS; two-arg precision form available since PostGIS 2.x [VERIFIED: local PostGIS 3.6]
- `ST_AsMVT` / `ST_AsMVTGeom` / `ST_TileEnvelope` — **PostGIS ≥ 3.0** [VERIFIED: local PostGIS 3.6; document in docstrings and stability.md, no runtime gate needed since library floor is 3.0]

---

## Project Constraints (from CLAUDE.md)

- **Independent library:** `pycopg` is a generic library published on PyPI; no Solaris/MarketStream deps
- **Independent venv:** `pycopg/venv/` — use `uv run pytest` not workspace pytest
- **Test command:** `uv run pytest tests/ -x -q` (quick); `uv run pytest` (full with coverage gate)
- **Linting:** `uv run ruff check pycopg tests`; `uv run black pycopg tests`
- **Coverage gate:** `--cov-fail-under=95` (currently ~96.10% post-P43)
- **Zero new runtime deps** (hard constraint from SPAT2-13)
- **PGDATABASE=pycopg_test2** for integration tests (pycopg_test DB broken per MEMORY)

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `mapbox-vector-tile` package (github.com/tilezen/mapbox-vector-tile) is legitimate | Package Legitimacy Audit | Low — alternative (pure Python decoder) is the recommended approach |
| A2 | `feature_id_column` must be an identifier interpolated into SQL (not a `%s` param) | Pattern 3 / Pitfall 4 | If PostGIS accepts it as a param, the SQL shape would simplify — but local test confirms PostGIS raises on non-integer column, suggesting it resolves by name |

**All other claims verified locally against PostGIS 3.6 and the pycopg codebase.**

---

## Open Questions

1. **`as_mvt` column alias in SQL**
   - What we know: `ST_AsMVT(…)` without alias produces column `st_asmvt` in psycopg3 `dict_row`
   - What's unclear: Should `build_mvt_sql` emit `AS mvt` to make the column name predictable?
   - Recommendation: Yes — emit `SELECT ST_AsMVT(…) AS mvt` and use `rows[0]["mvt"]` in `_run_mvt`. Predictable key is better than `next(iter(rows[0]))` heuristic.

2. **`as_mvt` `_HELPER_CALLS` routing test**
   - What we know: `_HELPER_CALLS` drives `TestAccessorRouting` parametrized tests (calls each method with `into="rows"`)
   - What's unclear: `as_mvt` returns `bytes`, not `list[dict]`. It cannot share the `_HELPER_CALLS` structure.
   - Recommendation: Do NOT add `as_mvt` to `_HELPER_CALLS`. Add a separate `TestMvtRouting` class with a mock `_RecordingSyncDb` that returns a fake bytes row from `execute`, and assert the coercion path.

3. **`filter=` placement in `build_mvt_sql` inner vs outer query**
   - What we know: D-03 specifies `filter` goes in the inner subquery (`FROM {schema}.{table} AS t WHERE {filter}`)
   - Confirmed: The inner-WHERE placement is correct — it filters source rows before clipping; outer WHERE only filters `q.geom_mvt IS NOT NULL`.
   - Recommendation: `filter` in inner query only; `_append_tail` is NOT called for `as_mvt` (its tail structure is unique).

---

## Sources

### Primary (HIGH confidence — verified in this session)
- `pycopg/spatial.py` (lines 1-5300) — builder patterns, `_SCALAR_HELPERS`, `_check_into`, `_append_tail`, `_run`, async `_run` [VERIFIED: codebase read]
- `pycopg/utils.py` — `validate_identifiers` signature and behavior [VERIFIED: codebase read]
- `pycopg/exceptions.py` — `InvalidIdentifierError` [VERIFIED: codebase read]
- `tests/test_parity.py` — `test_accessor_parity`, `test_accessor_parameter_kind_parity`, `test_spatial_aggregates_surface` pattern [VERIFIED: codebase read]
- `tests/test_spatial.py` — injection test conventions, `_HELPER_CALLS`, `_RecordingSyncDb` [VERIFIED: codebase read]
- PostGIS 3.6 local instance — ST_AsGeoJSON options bitmask, ST_AsText one/two-arg, ST_AsMVT pipeline, bytea return types, empty tile = `b""`, psycopg3 `bytes` (not `memoryview`) for bytea [VERIFIED: live queries 2026-06-29]
- `.planning/phases/44-spatial-v2-serialization-mvt/44-CONTEXT.md` — all locked decisions D-01..D-10 [VERIFIED: file read]
- `.planning/REQUIREMENTS.md` — SPAT2-10..SPAT2-13 [VERIFIED: file read]

### Secondary (MEDIUM confidence)
- `.planning/research/FEATURES.md` §"Workstream 1: Spatial V2 — Serialization" (~line 373) — PostGIS API signatures, SQL shape [CITED: project research file; pre-dates Phase 41 — `where=` and positional coords updated by CONTEXT.md locked decisions]
- `.planning/research/PITFALLS.md` — Pitfall 1 (validate_identifiers), Pitfall 2 (SRID mismatch), Pitfall 3 (MVT coordinate system), Pitfall 11 (parity drift) [CITED: project research file]

### Tertiary (LOW confidence — training knowledge, not session-verified)
- None — all architecture claims were verified against the live codebase and PostGIS instance.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new deps; all patterns are clones of existing verified code
- Architecture patterns: HIGH — verified builder patterns + live PostGIS SQL verification
- MVT mechanics: HIGH — verified against PostGIS 3.6: `b""` empty tile, `bytes` return type, pure Python decoder working
- Pitfalls: HIGH — grounded in pycopg history (MEMORY) and live verification
- Test strategy: HIGH — follows the established P42/P43 pattern with specific additions for MVT decode

**Research date:** 2026-06-29
**Valid until:** 2026-07-30 (stable — PostGIS SQL API and psycopg3 bytea semantics are stable)
