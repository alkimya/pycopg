# Phase 14: Spatial Helpers (Phase 8 réalisée) — Research

**Researched:** 2026-06-12
**Domain:** PostGIS spatial query abstraction, Python accessor pattern
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01** — `into="rows"` (défaut, `list[dict]`) + `into="gdf"` délègue à `to_geodataframe` existant. `into="query"` différé au milestone ETL.

**D-02** — `into="gdf"` sur helper scalaire (`area`, `perimeter`, `distance`, `centroid`) lève `ValueError` explicite. Valide uniquement sur les helpers retournant une géométrie (contains, within, intersects, dwithin, nearest, buffer, transform).

**D-03** — `SELECT *` par défaut + `columns: list[str] | None` validé par `validate_identifiers` — pattern `_build_select_sql`.

**D-04** — Pas de `db.spatial.sql(...)` public.

**D-05** — 4 formes d'entrée géométrie partout : `point=(x,y)` / `wkt="..."` / `geojson={...}` / `ref=("table","geom")`. Mutuellement exclusives (sinon `ValueError`). Une seule fonction interne de résolution. Tout en `%s`.

**D-06** — Paramètre colonne géométrie : `geom`, keyword avec défaut `"geometry"`.

**D-07** — `srid=4326` par défaut, surchargeable.

**D-08** — `ref=` = sémantique EXISTS. Lignes de la table interrogée matchant au moins une géométrie de la table référencée (sous-requête EXISTS). `within` bi-tables garde sa signature jointure dédiée.

**D-09** — `unit="m"` par défaut (cast `::geography`, mètres) ; `unit="srid"` pour unités natives.

**D-10** — `unit=` exposé sur : `dwithin`, `distance`, `area`, `perimeter`, `buffer` uniquement. Pas sur les prédicats booléens, `nearest`, `centroid`, `transform`.

**D-11** — `where: str | None` optionnel, convention `_build_select_sql` (fragment sans mot-clé WHERE, combiné `AND (...spatial...) AND (where)`).

**D-12** — Trio `where=` + `order_by=` + `limit=` sur les helpers de filtrage.

### Claude's Discretion

- Détail KNN de `nearest` (opérateur `<->` geometry vs geography).
- Détail validation d'exclusivité mutuelle des formes d'entrée géométrie (D-05) et valeurs `unit=`/`into=` invalides.
- SQL exact généré par chaque builder (formes `ST_*`, casts, sous-requête EXISTS) et signatures/ordre exact des fonctions builder.
- Stratégie de cache de la garde PostGIS (vérif à la première utilisation, pattern `from_geodataframe`).
- Découpage en plans/vagues et granularité des commits.
- Forme des tests builders DB-free et des tests d'intégration PostGIS (fixtures, tables temporaires).

### Deferred Ideas (OUT OF SCOPE)

- `into="query"` (objet requête composable) → milestone ETL ultérieur.
- `db.spatial.sql(...)` public → écarté (D-04).
- `where_params=` → écarté en phase 1.
- Helpers spatiaux supplémentaires (union, simplify, clustering…) → hors catalogue phase 1.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SPAT-01 | 4 open design points (`into=`, geometry input, `unit=`, `where=`) resolved → 08-DESIGN.md updated | D-01..D-12 are fully locked; update task needs explicit plan step |
| SPAT-02 | `pycopg/spatial.py` with pure SQL builders + `SpatialAccessor` / `AsyncSpatialAccessor` | Pure-builder pattern from Phase 12 (`base.py` module-level functions); accessor lazy property pattern confirmed |
| SPAT-03 | ~10 helpers: contains, within, intersects, dwithin, distance, nearest, area, perimeter, centroid, buffer, transform | All 11 SQL forms verified against local PostGIS 3.6 |
| SPAT-04 | PostGIS guard (`has_extension`) + identifier validation + `%s` values | `has_extension` exists at `database.py:854` / `async_database.py:1055`; `validate_identifiers` in `utils.py`; pattern confirmed from existing spatial methods |
| SPAT-05 | `async_db.spatial` parity, covered by `test_parity` | `test_parity.py` inspects public members; `spatial` property must appear on both classes; introspection mechanism understood |
| SPAT-06 | Pure builder unit tests (no DB) + PostGIS integration tests | DB-free test pattern from `tests/test_base.py` (TestBuildPgDumpCmd); integration from `tests/test_postgis_errors.py`; PostGIS 3.6 confirmed on `pycopg_test` |
</phase_requirements>

---

## Summary

Phase 14 delivers the spatial helper namespace that was designed in Phase 8 but deferred. All four previously open design points (`into=`, geometry input forms, `unit=`, `where=`) are now locked (D-01..D-12 in 14-CONTEXT.md). The implementation follows the **pure-builder pattern** established in Phase 12: module-level SQL builder functions (no `self`, no I/O) shared byte-identical between `SpatialAccessor` and `AsyncSpatialAccessor`, with only `execute` / `await execute` differing between sides.

The codebase already provides all necessary infrastructure: `validate_identifiers` in `utils.py`, `has_extension` on both `Database` and `AsyncDatabase`, `to_geodataframe` (sync and async with `run_sync`) for `into="gdf"`, and `ExtensionNotAvailable` in `exceptions.py`. The `test_parity.py` introspection mechanism will automatically detect the `spatial` property on both classes. PostGIS 3.6.3 is confirmed installed on the local `pycopg_test` database.

Current coverage is 93% (measured: `uv run pytest -o addopts="" --cov`). The gate is `--cov-fail-under=92`. Phase 14 adds a new module (`spatial.py`) with pure builders — the DB-free unit tests will be the primary coverage driver. The cliquet must be maintained at ≥ 92 (milestone target is 95, deferred from Phase 12; Phase 14 coverage target is "maintain 95" — but actual gate is currently 92, see ROADMAP note).

**Primary recommendation:** Build `pycopg/spatial.py` in two waves: (1) geometry resolver + all pure builders + `SpatialAccessor` sync; (2) `AsyncSpatialAccessor` + lazy `spatial` property on both classes + integration tests + parity verification.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| SQL builder (geometry resolver, ST_* forms) | `pycopg/spatial.py` module-level functions | — | Pure, stateless, DB-free; shared by both accessor classes byte-for-byte |
| Sync accessor (`db.spatial`) | `SpatialAccessor` in `spatial.py` | `Database` lazy property | Sync execution only; all SQL logic delegated to builders |
| Async accessor (`async_db.spatial`) | `AsyncSpatialAccessor` in `spatial.py` | `AsyncDatabase` lazy property | Mirrors `SpatialAccessor` exactly; only `await execute` differs |
| PostGIS guard | Lazy property on `Database` / `AsyncDatabase` | `SpatialAccessor.__init__` or first-call | Pattern matches `from_geodataframe` guard; check once, cache result |
| GeoDataFrame return (`into="gdf"`) | `to_geodataframe(sql=..., params=...)` on parent `Database` / `AsyncDatabase` | — | Reuse existing `to_geodataframe`; async uses `conn.run_sync` already handled |
| Identifier validation | `utils.validate_identifiers` | builder functions | Called in each builder before SQL assembly |
| Integration test fixtures | `tests/test_spatial.py` | `tests/conftest.py` | Temp tables created/dropped per test; `db_config` fixture reused |

---

## Standard Stack

### Core (No New Dependencies)

This phase installs **zero new packages**. All dependencies are already present.

| Asset | Location | Purpose |
|-------|----------|---------|
| `validate_identifier(s)` | `pycopg/utils.py:47,76` | Identifier injection prevention |
| `has_extension` (sync) | `pycopg/database.py:854` | PostGIS guard |
| `has_extension` (async) | `pycopg/async_database.py:1055` | PostGIS guard (async) |
| `to_geodataframe` (sync) | `pycopg/database.py:1498` | `into="gdf"` delegation target |
| `to_geodataframe` (async) | `pycopg/async_database.py:1964` | `into="gdf"` async delegation |
| `ExtensionNotAvailable` | `pycopg/exceptions.py:22` | PostGIS not installed error |
| `_build_select_sql` | `pycopg/base.py:159` | `where=`/`order_by=`/`limit=` convention to mirror |
| `build_pg_dump_cmd` | `pycopg/base.py:232` | Structural model for pure builder functions |

### Runtime Environment Verified

| Item | Version | Source |
|------|---------|--------|
| psycopg | 3.3.4 | `[VERIFIED: uv run python -c "import psycopg; print(psycopg.__version__)"]` |
| geopandas | 1.1.3 | `[VERIFIED: uv run python -c "import geopandas; print(geopandas.__version__)"]` |
| PostGIS | 3.6.3 | `[VERIFIED: psql pycopg_test SELECT PostGIS_Version()]` |
| timescaledb | 2.27.2 | `[VERIFIED: psql pycopg_test pg_extension table]` |
| pytest asyncio_mode | auto | `[VERIFIED: pyproject.toml]` |
| Coverage gate | `--cov-fail-under=92` | `[VERIFIED: pyproject.toml]` |
| Actual coverage | 93% | `[VERIFIED: uv run pytest -o addopts="" --cov]` |

---

## Package Legitimacy Audit

> Phase 14 installs **no external packages**. This section is not applicable.

No new dependencies. All required infrastructure (psycopg, geopandas, SQLAlchemy, validate_identifiers, has_extension) is already installed and verified in the project venv.

---

## Architecture Patterns

### System Architecture Diagram

```
User call: db.spatial.contains("parcels", point=(-122.4, 37.8))
                    |
                    v
      [Database.spatial property]  ← lazy: creates SpatialAccessor(db) on first access
                    |
                    v
      [SpatialAccessor.contains(table, *, point=, geom=, srid=, columns=, where=, ...)]
                    |
                    v
      [_resolve_geometry(point=, wkt=, geojson=, ref=)]  ← pure fn, returns (sql_fragment, params)
                    |
                    v
      [build_contains_sql(table, geom_col, geom_sql, ...)]  ← pure fn, returns (sql, params)
                    |                                           no DB, no self, testable
                    |
         +----------+----------+
         |                     |
    into="rows"           into="gdf"
         |                     |
   db.execute(sql, params)    db.to_geodataframe(sql=sql, params=params, geometry_column=geom)
         |
    list[dict]
```

For `AsyncSpatialAccessor`:
- Same builders (byte-identical import from `spatial.py`)
- `await db.execute(sql, params)` instead of `db.execute`
- `await db.to_geodataframe(...)` instead of `db.to_geodataframe`

### Recommended Project Structure

```
pycopg/
├── spatial.py           # NEW: pure builders + SpatialAccessor + AsyncSpatialAccessor
├── database.py          # ADD: spatial property (lazy, ~5 lines)
├── async_database.py    # ADD: spatial property (lazy, ~5 lines)
└── __init__.py          # MAYBE: export SpatialAccessor, AsyncSpatialAccessor types

tests/
└── test_spatial.py      # NEW: DB-free builder tests + PostGIS integration tests
```

### Pattern 1: Pure Builder Function (from Phase 12)

**What:** Module-level functions with explicit args, no `self`, no I/O. Return `(sql, params)` tuple.
**When to use:** All SQL assembly in `spatial.py`.

```python
# Source: pycopg/base.py:232 (build_pg_dump_cmd structural model) [VERIFIED: codebase]
def build_contains_sql(
    table: str,
    geom_col: str,
    geom_fragment: str,
    schema: str = "public",
    columns: list[str] | None = None,
    where: str | None = None,
    order_by: str | None = None,
    limit: int | None = None,
) -> tuple[str, list]:
    """Pure SQL builder for ST_Contains — no DB access."""
    validate_identifiers(table, geom_col, schema)
    if columns:
        validate_identifiers(*columns)
    cols_str = ", ".join(columns) if columns else "*"
    spatial_cond = f"ST_Contains({geom_col}, {geom_fragment})"
    where_clause = f"WHERE {spatial_cond}"
    if where:
        where_clause += f" AND ({where})"
    sql = f"SELECT {cols_str} FROM {schema}.{table} {where_clause}"
    if order_by:
        sql += f" ORDER BY {order_by}"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return sql
```

### Pattern 2: Geometry Resolver (one internal function, all 4 forms)

**What:** Single function mapping the 4 mutually-exclusive geometry input forms to a `(sql_fragment, params)` pair.
**When to use:** Called at the top of each builder that accepts a geometry input.

```python
# Source: D-05 locked decision; SQL forms verified against PostGIS 3.6 [VERIFIED: local DB]

def _resolve_geometry(
    point: tuple[float, float] | None = None,
    wkt: str | None = None,
    geojson: dict | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
) -> tuple[str, list]:
    """
    Returns (sql_fragment, params) for use in ST_* calls.
    Exactly one of point/wkt/geojson/ref must be provided.
    ref= returns an EXISTS subquery fragment (D-08).
    """
    given = sum(x is not None for x in [point, wkt, geojson, ref])
    if given != 1:
        raise ValueError("Exactly one of point=, wkt=, geojson=, ref= must be provided")

    if point is not None:
        x, y = point
        return f"ST_SetSRID(ST_MakePoint(%s, %s), {int(srid)})", [x, y]

    if wkt is not None:
        return f"ST_GeomFromText(%s, {int(srid)})", [wkt]

    if geojson is not None:
        import json
        return f"ST_SetSRID(ST_GeomFromGeoJSON(%s), {int(srid)})", [json.dumps(geojson)]

    if ref is not None:
        ref_table, ref_col = ref
        validate_identifiers(ref_table, ref_col)
        # Returns a correlated subquery placeholder — consumed by the helper that knows
        # the primary table alias.
        return ("ref", (ref_table, ref_col))  # special sentinel; caller builds EXISTS
```

**Note on `ref=` with EXISTS:** The EXISTS subquery form requires knowledge of both the primary table (`t`) and the reference table (`z`):
```sql
WHERE EXISTS (SELECT 1 FROM {ref_table} AS _ref WHERE ST_Contains(_ref.{ref_col}, t.{geom_col}))
```
The builder that calls `_resolve_geometry` handles this sentinel return. The resolver still validates identifiers.

### Pattern 3: Lazy Accessor Property

**What:** `@property` on `Database` / `AsyncDatabase` that instantiates the accessor on first access.
**When to use:** `db.spatial`, `async_db.spatial`.

```python
# Source: async_database.py:82-88 (async_engine lazy property) [VERIFIED: codebase]
# In database.py:
@property
def spatial(self) -> "SpatialAccessor":
    """Lazy accessor for spatial helpers."""
    if self._spatial is None:
        from pycopg.spatial import SpatialAccessor
        self._spatial = SpatialAccessor(self)
    return self._spatial
```

**`__init__` addition:**
```python
self._spatial: "SpatialAccessor | None" = None
```

### Pattern 4: PostGIS Guard

**What:** Check `has_extension("postgis")` in the accessor's `__init__` or on first method call, raise `ExtensionNotAvailable` if missing.
**Recommendation (Claude's Discretion):** Check at accessor instantiation time (in `SpatialAccessor.__init__`). This matches `from_geodataframe` pattern and fails fast, giving a clear error before any method call. Caching is natural — the accessor object is the cache.

```python
# Source: database.py:1457-1459 (from_geodataframe guard) [VERIFIED: codebase]
class SpatialAccessor:
    def __init__(self, db: "Database") -> None:
        self._db = db
        if not db.has_extension("postgis"):
            raise ExtensionNotAvailable(
                "PostGIS extension not installed. Run db.create_extension('postgis')"
            )
```

For `AsyncSpatialAccessor`, the guard must be async (since `has_extension` is async on `AsyncDatabase`). Two options:
1. Factory classmethod `await AsyncSpatialAccessor.create(db)` — complex pattern.
2. Defer guard to first method call (lazy check). Each async method calls `await self._db.has_extension("postgis")` once and caches result as `self._postgis_verified`.

**Recommended (discretion):** Option 2 — lazy check with `self._postgis_verified: bool = False` flag; any method call that finds it False runs the check once and caches True. This avoids the factory pattern complexity while maintaining the fast-fail characteristic.

### Anti-Patterns to Avoid

- **f-string values:** Never `f"... WHERE ST_DWithin(..., {distance})"`. All user values go through `%s`. [VERIFIED: Phase 10 rule, hotfix v0.3.1]
- **Non-validated identifiers in SQL:** Table, column, schema names must pass `validate_identifiers` before string interpolation into SQL.
- **Duplicate guard logic:** Do not re-implement the PostGIS check — reuse `has_extension` which already queries `pg_extension`.
- **accessor in `__init__.py` import chain before `spatial.py` exists:** Import `SpatialAccessor` lazily inside the property body (not at module top level) to avoid circular imports and import errors when `spatial.py` doesn't exist yet.
- **`unit=` on non-metric helpers:** `nearest`, `centroid`, `transform`, `contains`, `within`, `intersects` do not accept `unit=` — adding it silently would suggest a nonexistent feature (D-10).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| GeoDataFrame output | Custom gpd.read_postgis call | `db.to_geodataframe(sql=sql, params=params)` | Already handles sync engine + async run_sync; handles geometry column detection |
| JSON serialization for geojson= | Custom json serializer | `json.dumps(geojson)` + `%s` placeholder | Simple and correct; PostGIS `ST_GeomFromGeoJSON` accepts JSON string |
| Async geodataframe | Custom `run_sync` wrapper | `async_db.to_geodataframe(sql=sql, params=params)` | Already wrapped with `conn.run_sync` in async_database.py:2004 |
| Extension check | Raw SQL check | `db.has_extension("postgis")` | Already implemented, already tested |
| Identifier injection prevention | Regex on table names | `validate_identifiers(table, schema, geom_col)` | Already covers all identifier patterns, raises `InvalidIdentifier` |
| `SELECT *` vs column list | Custom column SQL | `_build_select_sql` column pattern | Follow exact convention: `", ".join(columns) if columns else "*"` |

**Key insight:** `spatial.py` is 90% SQL string assembly and 10% routing. The hard parts (execution, geopandas integration, identifier validation, extension detection) are all solved infrastructure that spatial.py delegates to.

---

## PostGIS SQL Reference

### Verified SQL Forms (against PostGIS 3.6.3, pycopg_test)

All forms below were tested directly against the local PostGIS instance. [VERIFIED: local DB]

#### Geometry Input Forms

```sql
-- point=(x, y) with srid
ST_SetSRID(ST_MakePoint(%s, %s), 4326)   -- params: [x, y]

-- wkt="POLYGON(...)"
ST_GeomFromText(%s, 4326)                 -- params: [wkt_string]

-- geojson={...}
ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)  -- params: [json_string]
-- Note: ST_GeomFromGeoJSON ignores embedded CRS; ST_SetSRID override is correct

-- ref=("zones", "geom") → EXISTS subquery (D-08)
WHERE EXISTS (SELECT 1 FROM zones AS _ref WHERE ST_Contains(_ref.geom, t.geometry))
```

#### Helper SQL Patterns

```sql
-- contains: rows in table where geom CONTAINS input point
SELECT {cols} FROM {schema}.{table} AS t
WHERE ST_Contains(t.{geom}, {geom_input})
[AND ({where})] [ORDER BY {order_by}] [LIMIT {limit}]

-- within: rows in left table where geom IS WITHIN any row of right table (join form per 08-DESIGN)
SELECT {cols} FROM {schema}.{left_table} a
JOIN {schema}.{right_table} b ON ST_Within(a.{left_geom}, b.{right_geom})
[WHERE {where}] [ORDER BY {order_by}] [LIMIT {limit}]

-- intersects
WHERE ST_Intersects(t.{geom}, {geom_input})

-- dwithin (unit="m" = geography; unit="srid" = native)
-- unit="m":
WHERE ST_DWithin(t.{geom}::geography, {geom_input}::geography, %s)
-- unit="srid":
WHERE ST_DWithin(t.{geom}, {geom_input_same_type}, %s)

-- distance (returns scalar column + optional ORDER BY)
-- unit="m":
SELECT *, ST_Distance(t.{geom}::geography, {geom_input}::geography) AS distance
-- unit="srid":
SELECT *, ST_Distance(t.{geom}, {geom_input}) AS distance

-- nearest (KNN, Claude's Discretion: use geometry <-> for index use, geography <-> for m)
-- Recommended: geography <-> for metric distance ordering
ORDER BY t.{geom}::geography <-> {geom_input}::geography
LIMIT %s

-- area
-- unit="m": ST_Area({geom}::geography) → m²
-- unit="srid": ST_Area({geom}) → native SRID units
SELECT *, ST_Area(t.{geom}::geography) AS area FROM {schema}.{table} t

-- perimeter
-- unit="m": ST_Perimeter({geom}::geography)
-- unit="srid": ST_Perimeter({geom})

-- centroid (always returns x,y coords — not a geometry — so into="gdf" is invalid per D-02)
SELECT *, ST_X(ST_Centroid(t.{geom})) AS centroid_x, ST_Y(ST_Centroid(t.{geom})) AS centroid_y
FROM {schema}.{table} t

-- buffer (returns geometry — valid for into="gdf")
-- unit="m": cast to geography for meter-based buffer
SELECT *, ST_Buffer(t.{geom}::geography, %s)::geometry AS buffer FROM {schema}.{table} t

-- transform (returns transformed geometry — valid for into="gdf")
SELECT *, ST_Transform(t.{geom}, %s) AS geometry_transformed FROM {schema}.{table} t
```

#### KNN Operator Decision (Claude's Discretion)

The `<->` operator works in both geometry and geography modes:
- `geom <-> point` — returns distance in SRID units (degrees for 4326). Fast with GiST index.
- `geom::geography <-> point::geography` — returns meters. Slightly more expensive but correct for WGS84.

**Recommendation:** Use `::geography` cast for `nearest` (consistent with D-09 "m default") and note in docstring that a GiST index on the geometry column accelerates this. Verified: geography `<->` returns ~14175m between two test points as expected. [VERIFIED: local DB]

---

## Common Pitfalls

### Pitfall 1: `test_parity` Will Fail If `spatial` Is Not Symmetric

**What goes wrong:** `test_parity.py` uses `inspect.getmembers` on both `Database` and `AsyncDatabase`. If `spatial` is a property on `Database` but not on `AsyncDatabase`, `TestAsyncParity.test_all_database_public_methods_exist_in_async` will fail with `Methods in Database but missing in AsyncDatabase: ['spatial']`.

**Why it happens:** The parity test is comprehensive — it catches ALL public members not in the allow-list.

**How to avoid:** Add the lazy `spatial` property to **both** classes in the same plan wave. Do not merge partial work.

**Warning signs:** Run `python -c "from pycopg import Database, AsyncDatabase; import inspect; print(set(n for n,_ in inspect.getmembers(Database) if not n.startswith('_')) - set(n for n,_ in inspect.getmembers(AsyncDatabase) if not n.startswith('_')))"` — should be `{'engine'}` only after Phase 14.

### Pitfall 2: `into="gdf"` on Scalars Not Guarded

**What goes wrong:** `area(table)` returns a `SELECT *, ST_Area(...) AS area` row, not a geometry column. Calling `to_geodataframe` on it will fail with a geopandas error about missing geometry column.

**Why it happens:** `to_geodataframe` looks for a geometry column by name.

**How to avoid:** Each accessor method that is scalar-only must check `if into == "gdf": raise ValueError(...)` before executing. The list: `area`, `perimeter`, `distance`, `centroid` (D-02).

**Warning signs:** A geopandas `ValueError: column 'geometry' not found` in integration tests.

### Pitfall 3: async `has_extension` Guard Timing

**What goes wrong:** If the guard runs in `AsyncSpatialAccessor.__init__`, it cannot use `await` — Python `__init__` is synchronous. Putting a sync `has_extension` call there would use the wrong method.

**Why it happens:** `AsyncDatabase.has_extension` is `async def` (confirmed at line 1055).

**How to avoid:** Use the lazy-check flag pattern: `self._postgis_ok: bool = False`. First method call that detects `not self._postgis_ok` awaits the check and caches the result.

**Warning signs:** `RuntimeWarning: coroutine 'has_extension' was never awaited` in tests.

### Pitfall 4: `json.dumps` Import Not in `spatial.py` Header

**What goes wrong:** `json` is a stdlib module but must be imported in `spatial.py`. If the `geojson=` form is called without the import, `NameError: name 'json' is not defined`.

**How to avoid:** `import json` at module top in `spatial.py`.

### Pitfall 5: Coverage Regression From New Uncovered Branches

**What goes wrong:** New code in `spatial.py` has branches (e.g., `if into == "gdf"`, `if unit == "m"`, `if where:`) that integration tests don't reach — coverage drops below 92%.

**Why it happens:** Pure builders are 100% coverable without DB; integration paths need actual PostGIS.

**How to avoid:** Write DB-free unit tests for ALL builder paths (every `if/else` branch) before integration tests. Pattern: `tests/test_base.py::TestBuildPgDumpCmd` — exact SQL string assertions, parametrized.

**Warning signs:** Coverage report shows `spatial.py` with >20% miss lines.

### Pitfall 6: `within` Signature Differs From Other Helpers

**What goes wrong:** `within` takes two tables (`left_table`, `left_geom`, `right_table`, `right_geom`) — join form, not single-table + geometry input (per 08-DESIGN §3). This breaks the pattern uniformity.

**How to avoid:** Keep `within` as the explicit two-table join. Document it clearly in the docstring. `test_parity` will still detect it because it only checks method names, not signatures.

### Pitfall 7: `interrogate` Gate Will Fail Without Numpydoc Docstrings

**What goes wrong:** Phase 13 set `interrogate fail-under=95`. Any public method in `spatial.py` without a numpydoc docstring will drop the score.

**Why it happens:** `interrogate` counts all public members, including class methods on `SpatialAccessor`.

**How to avoid:** Every public method on `SpatialAccessor` and `AsyncSpatialAccessor` must have a numpydoc docstring with at minimum Summary, Parameters, Returns, and Raises sections (no Examples per convention). Module docstring required. Classes require class-level docstring.

---

## Test Architecture

### Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio |
| asyncio_mode | `auto` (all async tests run automatically) |
| Quick run | `uv run pytest tests/test_spatial.py -x -q -o addopts=""` |
| Full suite | `uv run pytest` (with coverage gate `--cov-fail-under=92`) |
| Coverage tool | pytest-cov (configured in pyproject.toml) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command |
|--------|----------|-----------|-------------------|
| SPAT-01 | 08-DESIGN.md updated with D-01..D-12 | Manual verify | File diff check in plan |
| SPAT-02 | `spatial.py` exists with builders + accessors | Unit (import) | `uv run pytest tests/test_spatial.py::TestBuilders -x -q -o addopts=""` |
| SPAT-03 | All ~11 helpers exist and build correct SQL | Unit (DB-free) | `uv run pytest tests/test_spatial.py::TestBuilders -x -q -o addopts=""` |
| SPAT-04 | PostGIS guard raises `ExtensionNotAvailable`; injection rejected | Unit (mock) + Integration | `uv run pytest tests/test_spatial.py::TestGuard -x -q -o addopts=""` |
| SPAT-05 | `spatial` property on both `Database` and `AsyncDatabase` | Parity (existing test) | `uv run pytest tests/test_parity.py -x -q -o addopts=""` |
| SPAT-06 | Integration tests run against PostGIS on `pycopg_test` | Integration | `uv run pytest tests/test_spatial.py::TestIntegration -x -q -o addopts=""` |

### Test Structure for `tests/test_spatial.py`

```python
# DB-free pure builder tests (fast, no DB required)
class TestGeometryResolver:
    """Tests for _resolve_geometry — all 4 forms, exclusivity validation."""

class TestBuilders:
    """Exact SQL string assertions for each of the ~11 builders.
    Parametrized like TestBuildPgDumpCmd in test_base.py."""
    # test_contains_sql_point_form
    # test_contains_sql_wkt_form
    # test_contains_sql_geojson_form
    # test_contains_sql_ref_form (EXISTS subquery)
    # test_contains_into_gdf_valid
    # test_area_into_gdf_raises_valueerror  (D-02)
    # test_dwithin_unit_m_uses_geography_cast  (D-09)
    # test_dwithin_unit_srid_no_cast  (D-09)
    # ... one test class or section per helper

class TestGuard:
    """PostGIS extension guard behavior."""
    # test_accessor_raises_when_postgis_missing (mock has_extension to return False)
    # test_async_accessor_raises_when_postgis_missing

class TestIntegration:
    """Real DB tests requiring PostGIS on pycopg_test."""
    # Uses db_config fixture from conftest.py
    # Creates TEMP TABLE per test, drops in finally
    # test_contains_returns_correct_rows
    # test_dwithin_filters_by_distance
    # test_nearest_returns_k_closest
    # test_buffer_into_gdf_returns_geodataframe
    # test_transform_changes_srid
    # ... one per helper, minimal fixture table
```

### Wave 0 Gaps

- [ ] `tests/test_spatial.py` — new file, entire test suite (Wave 0 from plan perspective is writing spatial.py; tests are Wave 1 or concurrent)
- No framework config changes needed (`asyncio_mode = auto` already set)
- No fixture changes needed (`db_config` already exists in `conftest.py`)

### Coverage Strategy

Pure builders in `spatial.py` are 100% coverable without a DB. ~200 lines of builder code with unit tests = significant coverage gain. The integration tests cover the accessor execution paths. The `into="gdf"` path requires PostGIS on the real DB but is straightforward.

**Estimated new code:** ~300-400 lines in `spatial.py` + ~250-350 lines in `tests/test_spatial.py`. With high unit test coverage on builders, net coverage should stay at or above 92%.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL | Integration tests | Yes | 17.x (local) | — |
| PostGIS extension | Integration tests | Yes | 3.6.3 on pycopg_test | Skip with `pytest.mark.skipif` |
| geopandas | `into="gdf"` path | Yes | 1.1.3 | — |
| psycopg3 | All DB operations | Yes | 3.3.4 | — |
| pytest-asyncio | Async tests | Yes | configured (auto mode) | — |

**Missing dependencies with no fallback:** None. All required tools are available.

**Pre-existing flaky tests (not regressions, per MEMORY.md):**
- `tests/test_integration.py::TestAsyncIntegration::test_async_transaction_fix` — FAILED (pre-existing)
- `tests/test_postgis_errors.py::TestPostGISErrorHandling::test_create_spatial_index_name_parameter` — FAILED (pre-existing)

Use `-o addopts=""` for targeted runs to avoid coverage gate: `uv run pytest tests/test_spatial.py -x -q -o addopts=""`.

---

## Validation Architecture

> `workflow.nyquist_validation` not set in `.planning/config.json` → treat as enabled.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 + pytest-asyncio 0.23+ |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_spatial.py -x -q -o addopts=""` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SPAT-01 | 08-DESIGN.md reflects D-01..D-12 | Manual | File read check | ✅ (update task) |
| SPAT-02 | `spatial.py` importable with correct classes | Unit | `uv run pytest tests/test_spatial.py -k "import" -o addopts=""` | ❌ Wave 0 |
| SPAT-03 | Each builder returns expected SQL string | Unit (DB-free) | `uv run pytest tests/test_spatial.py::TestBuilders -o addopts=""` | ❌ Wave 0 |
| SPAT-04 | Guard raises `ExtensionNotAvailable`; identifier injection raises `InvalidIdentifier` | Unit+Integration | `uv run pytest tests/test_spatial.py::TestGuard -o addopts=""` | ❌ Wave 0 |
| SPAT-05 | `spatial` in both `Database` and `AsyncDatabase` members | Parity (existing) | `uv run pytest tests/test_parity.py -o addopts=""` | ✅ |
| SPAT-06 | Integration queries return correct rows on PostGIS | Integration | `uv run pytest tests/test_spatial.py::TestIntegration -o addopts=""` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_spatial.py tests/test_parity.py -x -q -o addopts=""`
- **Per wave merge:** `uv run pytest tests/ -o addopts="" -q` (full suite, no coverage gate)
- **Phase gate:** `uv run pytest` (full suite + coverage gate ≥ 92) + `uv run interrogate pycopg` (≥ 95)

### Wave 0 Gaps

- [ ] `tests/test_spatial.py` — entire new test file (TestGeometryResolver, TestBuilders, TestGuard, TestIntegration)
- [ ] `pycopg/spatial.py` — entire new module (builders + accessors)

*(Existing test infrastructure is complete — no fixture or framework changes needed)*

---

## Security Domain

> `security_enforcement` not explicitly set → enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | — |
| V3 Session Management | No | — |
| V4 Access Control | No | — |
| V5 Input Validation | Yes | `validate_identifiers` for table/schema/geom/column names; `%s` for all values |
| V6 Cryptography | No | — |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via table name | Tampering | `validate_identifiers(table, schema, geom_col)` before any SQL assembly |
| SQL injection via geometry value | Tampering | All coordinates, WKT, GeoJSON, distances via `%s` parameterized |
| SQL injection via `where=` fragment | Tampering | `where=` is a raw SQL fragment (same as `_build_select_sql`) — documented limitation; `where_params=` deferred to future |
| Unsafe `ref=` table name | Tampering | `validate_identifiers(ref_table, ref_col)` in `_resolve_geometry` |
| SRID integer injection | Tampering | `int(srid)` cast before interpolation (integer coercion is safe) |

**Critical note on `where=`:** Like the existing `_build_select_sql`, the `where=` fragment is a raw SQL string — values within it are the caller's responsibility. This is the existing convention and is documented. The deferred `where_params=` is the eventual solution but is out of scope for Phase 14.

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| `db.execute("SELECT ... WHERE ST_Contains(...)")` | `db.spatial.contains("table", point=(x,y))` | No hand-written SQL for common operations |
| No geometry input abstraction | Single `_resolve_geometry` function (4 forms) | Uniform pattern across all helpers |
| Geography vs geometry confusion | `unit="m"` default → `::geography` cast | Eliminates "distances in degrees" bugs |

**Not deprecated:** `db.execute` remains the escape hatch for complex spatial SQL not covered by the helpers.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `within` uses a join form (not EXISTS), as stated in 08-DESIGN §3 | Architecture Patterns | If EXISTS is also valid for within, signature differs from other helpers — low risk, design is locked |
| A2 | The `spatial` property name is not currently taken on Database/AsyncDatabase | Architecture Patterns | Grep confirms no existing `spatial` property [VERIFIED: codebase grep] |
| A3 | `asyncio_mode = "auto"` means async test methods in test classes run automatically | Test Architecture | If not, tests need `@pytest.mark.asyncio` — confirmed by existing test_parity.py usage [VERIFIED: codebase] |

**Verified that `spatial` property does not yet exist:**
- `grep -n "def spatial\|spatial" pycopg/database.py` — only found "spatial_index" and "list_geometry_columns" references, no `spatial` property [VERIFIED: codebase]

---

## Open Questions (RESOLVED)

1. **Coverage gate value for Phase 14**
   - What we know: Gate is `--cov-fail-under=92` (current). Milestone target is 95. Phase 12 achieved 92.55% but deferred the 95 gate flip.
   - What's unclear: Should Phase 14 flip the gate to 95? The milestone says "maintain 95" but the gate is 92.
   - Recommendation: Measure after implementing spatial.py. If total coverage rises above 95, flip the gate in the final plan wave. If it stays at ~93%, leave at 92 and note. Do not force-flip to 95 if unmet (cliquet rule: "never freeze an unmet gate").

2. **`__init__.py` export of accessor types**
   - What we know: `SpatialAccessor` and `AsyncSpatialAccessor` are new public types.
   - What's unclear: Should they appear in `__all__`? They are accessible via `db.spatial` without direct import.
   - Recommendation: Export them for type annotation use (`from pycopg import SpatialAccessor`). Minimal surface, no downside.

---

## Sources

### Primary (HIGH confidence)

- `pycopg/base.py` — pure builder pattern (build_pg_dump_cmd), `_build_select_sql` convention [VERIFIED: codebase]
- `pycopg/utils.py` — `validate_identifier`, `validate_identifiers` [VERIFIED: codebase]
- `pycopg/exceptions.py` — `ExtensionNotAvailable` [VERIFIED: codebase]
- `pycopg/database.py:854` — `has_extension` sync [VERIFIED: codebase]
- `pycopg/async_database.py:1055` — `has_extension` async [VERIFIED: codebase]
- `pycopg/database.py:1498` — `to_geodataframe` sync [VERIFIED: codebase]
- `pycopg/async_database.py:1964` — `to_geodataframe` async [VERIFIED: codebase]
- `tests/test_parity.py` — parity introspection mechanism [VERIFIED: codebase]
- `tests/test_base.py` — DB-free builder test pattern [VERIFIED: codebase]
- Local PostGIS 3.6.3 on pycopg_test — all SQL forms verified via direct psql [VERIFIED: local DB]
- `docs/postgis.md` — Common Spatial Operations catalogue [VERIFIED: codebase]
- `14-CONTEXT.md` — D-01..D-12 locked decisions [VERIFIED: planning file]
- `08-DESIGN.md` — validated design: API surface, SQL patterns, file organization [VERIFIED: planning file]
- `pyproject.toml` — test config, asyncio_mode, coverage gate [VERIFIED: codebase]

### Secondary (MEDIUM confidence)

- KNN geography `<->` operator returning meters — tested empirically on local DB [VERIFIED: local DB]

### Tertiary (LOW confidence)

- None. All claims in this research are either codebase-verified or DB-verified.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all assets verified in codebase
- SQL forms: HIGH — all verified against local PostGIS 3.6.3
- Architecture patterns: HIGH — follows directly from Phase 12 established patterns
- Test architecture: HIGH — follows existing test_base.py and test_parity.py patterns
- Coverage outcome: MEDIUM — depends on branch coverage of new code (estimated, not measured)

**Research date:** 2026-06-12
**Valid until:** 2026-09-12 (stable PostGIS API — 90 days)
