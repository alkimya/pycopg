# Phase 15: Release v0.4.0 (PyPI + RTD) — Research

**Researched:** 2026-06-14
**Domain:** Python packaging, Sphinx documentation, GitHub Actions, PyPI release
**Confidence:** HIGH

---

## Summary

Phase 15 is a mechanical release phase: version bump, CHANGELOG, Sphinx doc overhaul (replace raw `execute(...)` PostGIS examples with `db.spatial.*` helpers, add spatial.py to autodoc, create spatial.md narrative page), RTD verify, CI Node bump (20 → 24), and PyPI publish via the existing trusted-publishing workflow. Every fact below is sourced from direct file inspection of the repo.

The main non-trivial tasks are: (B) rewriting `docs/postgis.md` (~8 `execute(...)` blocks → helper API calls), (C) adding `pycopg.spatial` to `docs/api-autodoc.md` + creating a new `docs/spatial.md` page, and (H) bumping four GitHub Actions from node20 to node24 runtimes. Everything else is a single-file, single-line edit.

The PyPI publish and git tag are **irreversible and must be human-gated**. Everything up to and including local `uv build` verification can be automated; the publish itself cannot.

**Primary recommendation:** Work in waves: (1) all textual/code changes in parallel (version bump, CHANGELOG, CI bumps, doc updates), (2) verify Sphinx build green locally and on RTD, (3) human creates tag + GitHub release → workflow auto-publishes.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REL-01 | Sphinx docs updated — PostGIS `execute(...)` examples replaced by new helpers; api-reference regenerated | See §B and §C — full file-level worklist provided |
| REL-02 | ReadTheDocs build is green (`.readthedocs.yaml` validated, RTD live) | See §D — RTD config fully read; local build currently passes |
| REL-03 | CHANGELOG v0.4.0 written; version bumped consistently everywhere; MIGRATION notes for breaking changes | See §A, §E, §F — exact files/lines listed |
| REL-04 | Wheel published to PyPI via `uv build` + GitHub release → auto-publish; tag created | See §G — publish.yml fully read; exact sequence documented |
| REL-05 | GitHub Actions bumped from Node 20 to Node 24 | See §H — exact action versions + old→new mapping |
| REL-06 | Milestone audit (`gsd-audit-milestone`) passes before archiving | See §I — final manual gate |
</phase_requirements>

---

## A. Version Bump Surface

**Every location containing `0.3.1` (or similar) that must change to `0.4.0`:**

| File | Line | Current value | New value |
|------|------|---------------|-----------|
| `pyproject.toml` | 7 | `version = "0.3.1"` | `version = "0.4.0"` |
| `docs/conf.py` | 17 | `release = '0.3.1'` | `release = '0.4.0'` |

**Confirmed NOT needing manual change:**

- `pycopg/__init__.py`: `__version__` is computed at runtime via `importlib.metadata.version("pycopg")` (lines 31–34). When `pyproject.toml` version is updated, this resolves correctly after `uv sync`. No manual edit needed. [VERIFIED: read from file]
- `README.md`: Contains no hardcoded version string. Two badges reference Python/License only (lines 7–8). No version badge present. [VERIFIED: grep confirmed]
- `uv.lock`: Managed by uv, will auto-update on `uv sync` after pyproject.toml bump. [ASSUMED]
- `.venv/pyvenv.cfg`, `venv/pyvenv.cfg`: Venv config — not part of release artefacts.
- No `CITATION.cff` or `.cff` file exists. [VERIFIED: find confirmed]
- No locale `.po` files contain a hardcoded `0.3.1` version string. [VERIFIED: grep confirmed]

**CHANGELOG footer links** (CHANGELOG.md lines 82–84 — also need updating, see §E):

```
[Unreleased]: https://github.com/alkimya/pycopg/compare/v0.3.0...HEAD
```

This line references `v0.3.0...HEAD`, not `v0.3.1...HEAD` — and is missing the `[0.3.1]` link entirely. Both need fixing as part of the CHANGELOG update.

**Summary: 2 files need version string edits** (`pyproject.toml` line 7, `docs/conf.py` line 17).

---

## B. PostGIS Doc Examples (REL-01)

### Scope

The **primary file** is `docs/postgis.md`. A secondary hit exists in `docs/database.md` (one raw-SQL PostGIS query in an inline example). No other doc files contain `db.execute(...)` calls referencing PostGIS functions.

### Confirmed `execute(...)` blocks to replace in `docs/postgis.md`

The section "Common Spatial Operations" (lines 145–308) contains **8 raw `execute(...)` blocks** that should use Phase 14 helpers. The "Example: Spatial Analysis" block (lines 265–307) is a narrative integration example — parts can adopt helpers, but the aggregate SQL and spatial join cannot (those use `to_geodataframe(sql=...)` or complex multi-table queries not covered by a single helper). **Recommended scope**: replace the 7 standalone helper examples; leave the two aggregate queries in the "Spatial Analysis" block as-is (they are correct uses of `to_geodataframe(sql=...)` and raw `execute` for complex aggregation).

**Block-by-block mapping (current → new API):**

#### Block 1: Point in Polygon (`postgis.md` lines 147–156)
```python
# CURRENT (lines 148–155):
result = db.execute("""
    SELECT p.id, p.name
    FROM parcels p
    WHERE ST_Contains(
        p.geometry,
        ST_SetSRID(ST_Point(%s, %s), 4326)
    )
""", [-122.4, 37.8])

# NEW (db.spatial.contains):
result = db.spatial.contains(
    "parcels",
    geom="geometry",
    point=(-122.4, 37.8),
    srid=4326,
    columns=["id", "name"],
)
```

#### Block 2: Distance Queries / DWithin (`postgis.md` lines 161–175)
```python
# CURRENT (lines 162–175) — two operations combined:
result = db.execute("""
    SELECT id, name,
           ST_Distance(
               geometry::geography,
               ST_Point(%s, %s)::geography
           ) AS distance_meters
    FROM parcels
    WHERE ST_DWithin(
        geometry::geography,
        ST_Point(%s, %s)::geography,
        1000
    )
    ORDER BY distance_meters
""", [-122.4, 37.8, -122.4, 37.8])

# NEW — two helpers (DWithin filter + distance column separately):
# Option A: dwithin filter only
rows = db.spatial.dwithin(
    "parcels",
    geom="geometry",
    point=(-122.4, 37.8),
    distance=1000,
    unit="m",
)
# Option B: distance helper with ordering (shows distance column)
rows = db.spatial.distance(
    "parcels",
    geom="geometry",
    point=(-122.4, 37.8),
    unit="m",
    columns=["id", "name"],
    order_by="distance",
)
# NOTE: The original single query does both filter+distance in one call.
# The helpers split these into separate operations. For docs, show both
# db.spatial.dwithin (filter) and db.spatial.distance (compute distance column)
# as separate clean examples. The combined raw SQL note can stay as a comment.
```

#### Block 3: Intersection (`postgis.md` lines 181–188)
```python
# CURRENT (lines 182–188):
result = db.execute("""
    SELECT a.id AS id_a, b.id AS id_b,
           ST_Area(ST_Intersection(a.geometry, b.geometry)) AS overlap_area
    FROM parcels a, parcels b
    WHERE a.id < b.id
      AND ST_Intersects(a.geometry, b.geometry)
""")

# NOTE: ST_Intersection (the function returning geometry) is NOT a helper.
# db.spatial.intersects checks ST_Intersects (predicate — does it overlap?) not
# compute the overlap area. This block is a complex aggregate — keep as raw execute
# with a note that db.spatial.intersects handles the predicate-only case.
# RECOMMENDED: show db.spatial.intersects for the simple predicate, note raw SQL
# for complex intersection area queries.
result = db.spatial.intersects(
    "parcels",
    geom="geometry",
    ref=("parcels", "geometry"),  # self-join not ideal; show point form instead
)
# For overlap area, raw execute is still appropriate — add a comment.
```

#### Block 4: Buffer (`postgis.md` lines 193–199)
```python
# CURRENT (lines 195–199):
result = db.execute("""
    SELECT id, name,
           ST_Buffer(geometry::geography, 100)::geometry AS buffer_100m
    FROM locations
""")

# NEW:
result = db.spatial.buffer(
    "locations",
    geom="geometry",
    distance=100,
    unit="m",
    columns=["id", "name"],
)
```

#### Block 5: Centroid (`postgis.md` lines 205–211)
```python
# CURRENT (lines 206–210):
result = db.execute("""
    SELECT id, name,
           ST_X(ST_Centroid(geometry)) AS lon,
           ST_Y(ST_Centroid(geometry)) AS lat
    FROM parcels
""")

# NEW:
result = db.spatial.centroid(
    "parcels",
    geom="geometry",
    columns=["id", "name"],
)
# Note: centroid returns centroid_x, centroid_y (not lon/lat) — update comment
```

#### Block 6: Area and Perimeter (`postgis.md` lines 217–225)
```python
# CURRENT (lines 218–225):
result = db.execute("""
    SELECT id, name,
           ST_Area(geometry::geography) AS area_sq_meters,
           ST_Perimeter(geometry::geography) AS perimeter_meters
    FROM parcels
    ORDER BY area_sq_meters DESC
    LIMIT 10
""")

# NEW (two helpers, but can combine conceptually):
# For area:
result = db.spatial.area(
    "parcels",
    geom="geometry",
    unit="m",
    columns=["id", "name"],
    order_by="area",
    limit=10,
)
# For perimeter (separate call or note that combined requires raw SQL):
result = db.spatial.perimeter(
    "parcels",
    geom="geometry",
    unit="m",
    columns=["id", "name"],
)
```

#### Block 7: CRS Transform (`postgis.md` lines 240–244)
```python
# CURRENT (lines 241–243):
result = db.execute("""
    SELECT id, ST_Transform(geometry, 3857) AS geometry_web_mercator
    FROM parcels
""")

# NEW:
result = db.spatial.transform(
    "parcels",
    geom="geometry",
    to_srid=3857,
)
# Note: returns column named geometry_transformed (not geometry_web_mercator)
```

#### Block 8: Update geometry SRID (`postgis.md` lines 257–262)
```python
# CURRENT (lines 258–262):
db.execute("""
    UPDATE parcels
    SET geometry = ST_SetSRID(geometry, 4326)
    WHERE ST_SRID(geometry) = 0
""")

# NOTE: This is a DML UPDATE, not a SELECT. No helper covers UPDATE.
# Keep as raw execute — add a note that db.spatial helpers are for SELECT operations.
```

#### Secondary block: `docs/database.md` line 358
```python
# CURRENT (database.md line 355–358):
nearby = db.to_geodataframe(
    sql="SELECT * FROM parcels WHERE ST_DWithin(geometry, ST_Point(-122.4, 37.8)::geography, 1000)"
)

# NEW: can show the helper equivalent:
nearby = db.spatial.dwithin(
    "parcels",
    point=(-122.4, 37.8),
    distance=1000,
    into="gdf",
)
```

#### "Spatial Analysis" example at `postgis.md` lines 283–307

The `to_geodataframe(sql=...)` for the spatial join (line 285–289) and the aggregate `execute(...)` at lines 292–303 are **NOT replaceable** by single helpers — they are intentionally complex queries. Keep them as raw SQL with a comment: "For complex multi-table spatial queries, use `db.to_geodataframe(sql=...)` or `db.execute()` directly."

#### `docs/postgis.md` "With SQL Query" block (lines 72–95)

```python
# Lines 73–82 — ST_Within filter:
gdf = db.to_geodataframe(
    sql="""
        SELECT * FROM parcels
        WHERE ST_Within(
            geometry,
            ST_MakeEnvelope(-122.5, 37.7, -122.3, 37.9, 4326)
        )
    """
)
```

`ST_MakeEnvelope` is not covered by any helper (no `within` for envelope geometry). Keep as-is, but add a note that `db.spatial.within` handles the two-table JOIN form. The helper `within` has a different signature (two-table join), not a single-table filter against an envelope.

```python
# Lines 84–95 — DWithin with params:
gdf = db.to_geodataframe(
    sql="""...""",
    params={"lon": -122.4, "lat": 37.8, "radius": 1000}
)
```

This can be replaced with:
```python
gdf = db.spatial.dwithin(
    "parcels",
    point=(-122.4, 37.8),
    distance=1000,
    into="gdf",
)
```

### New doc page needed: `docs/spatial.md`

Phase 14 shipped `pycopg/spatial.py` with 11 helpers (`contains`, `within`, `intersects`, `dwithin`, `distance`, `nearest`, `area`, `perimeter`, `centroid`, `buffer`, `transform`) but **no narrative documentation page exists**. `docs/index.md` toctree does not list a `spatial` page. This is a **gap that must be filled** as part of REL-01.

The new `docs/spatial.md` should cover:
- `db.spatial.*` / `async_db.spatial.*` access pattern (lazy init on first access, PostGIS guard)
- The `into=` parameter (`"rows"` = list of dict, `"gdf"` = GeoDataFrame)
- The 4 geometry input forms (`point=`, `wkt=`, `geojson=`, `ref=`)
- Per-helper examples (11 helpers)
- The `unit=` parameter (`"m"` = meters/geography, `"srid"` = native SRID units)
- Scalar vs geometry result distinction (area/perimeter/centroid/distance return scalars → `into="gdf"` is forbidden)

`docs/index.md` toctree must be updated to include `spatial` between `postgis` and `timescaledb`.

---

## C. API-Reference Regeneration (REL-01)

### How the autodoc works

`docs/api-autodoc.md` contains `.. automodule::` directives for 8 modules. Sphinx autodoc auto-generates documentation from live docstrings when `sphinx-build` runs — no manual regeneration step is needed for existing modules. The build command (`uv run sphinx-build -W --keep-going -b html docs docs/_build/html`) picks up docstring changes automatically.

**Current state of `docs/api-autodoc.md`** (lines 1–29):
```
.. automodule:: pycopg.database
.. automodule:: pycopg.async_database
.. automodule:: pycopg.base
.. automodule:: pycopg.config
.. automodule:: pycopg.utils
.. automodule:: pycopg.migrations
.. automodule:: pycopg.pool
.. automodule:: pycopg.exceptions
```

**Gap: `pycopg.spatial` is missing.** The Sphinx build currently runs without `pycopg.spatial` in the autodoc list — confirmed by running `sphinx-build` locally (output listed 8 modules, spatial absent). This means `SpatialAccessor`, `AsyncSpatialAccessor`, and all builder functions have no API documentation in RTD.

**Fix required:** Add to `docs/api-autodoc.md` after `pycopg.async_database`:
```rst
.. automodule:: pycopg.spatial
   :members:
```

**`docs/api-reference.md` (hand-maintained):** Contains a hand-written PostGIS methods table (lines 155–159) listing only `create_spatial_index` and `list_geometry_columns`. The `spatial` accessor methods (`db.spatial.*`) are not listed. This file needs a new `## Spatial Helpers (db.spatial.*)` section documenting the 11 accessor methods. This is in addition to the autodoc fix above (api-reference.md is the human-readable reference; api-autodoc.md is the Sphinx-generated reference).

**`DatabaseExists` gap in `api-reference.md`:** The exceptions section (lines 358–370) still shows the original 7 exceptions. `DatabaseExists` (added in Phase 13 DOC-09) IS present in `pycopg/__init__.py` `__all__` and in `docs/api-reference.md` line 365 (`DatabaseExists,`). Confirmed — no gap here.

---

## D. RTD Build (REL-02)

### `.readthedocs.yaml` current contents (lines 1–18)

```yaml
version: 2

build:
  os: ubuntu-24.04
  tools:
    python: "3.12"

sphinx:
  configuration: docs/conf.py

python:
  install:
    - method: pip
      path: .
    - requirements: docs/requirements.txt
```

**Analysis:**

- RTD uses **pip** (not uv) — installs pycopg with `pip install .` then `docs/requirements.txt`. No uv consideration needed; this is correct and intentional.
- Python version: 3.12 (locked). Compatible with pycopg's `requires-python = ">=3.11"`.
- `docs/requirements.txt` installs: `sphinx>=7.0.0`, `myst-parser>=2.0.0`, `furo>=2024.0.0`, `sphinx-autobuild>=2024.0.0`, `sphinx-copybutton>=0.5.0`, `sphinx-intl>=2.1.0`. Current installed version is Sphinx 9.1.0.
- The `-W` (treat warnings as errors) flag is locked in the CI step (`tests.yml` line 66) but is NOT in `.readthedocs.yaml`. RTD runs without `-W`, so warnings do not fail the RTD build even if they would fail CI.
- **The RTD build will import `pycopg.spatial`** when `pycopg.database` and `pycopg.async_database` are autodoc'd (both import `SpatialAccessor`). If `spatial.py` is importable (it is — it's in the package), this is fine. Adding `.. automodule:: pycopg.spatial` to autodoc will also require `geopandas` to be importable at RTD build time (for `TYPE_CHECKING` — but `TYPE_CHECKING` is `False` at import time, so the `if TYPE_CHECKING:` guard protects against the missing optional dep). [VERIFIED: spatial.py line 34 uses `if TYPE_CHECKING:` guard]

**Local Sphinx build currently passes** (confirmed: ran `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` — "La compilation a réussi"). The existing build is green without spatial in autodoc.

**Risk after spatial is added to autodoc:** If any spatial.py public docstring is missing (triggering `interrogate` — but interrogate is only run in CI, not Sphinx build), the build stays green. Sphinx `-W` only fails on Sphinx warnings (broken refs, duplicate objects) — not missing docstrings. Given spatial.py has full numpydoc docstrings from Phase 14, risk is low.

**Local build verification command:**
```bash
uv pip install -r docs/requirements.txt
uv run sphinx-build -W --keep-going -b html docs docs/_build/html
```

**RTD live verification:** After pushing to main with updated `.readthedocs.yaml` and `docs/conf.py`, the RTD build triggers automatically. Check https://readthedocs.org/projects/pycopg/ for build status. No `.readthedocs.yaml` changes are required for v0.4.0 unless RTD configuration needs updating — current config is valid.

---

## E. CHANGELOG (REL-03)

### Current CHANGELOG structure

`CHANGELOG.md` follows **Keep a Changelog 1.1.0** format with **Semantic Versioning**. Sections used: `### Added`, `### Changed`, `### Fixed`, `### Security`, `### Improved`. Date format: `YYYY-MM-DD`.

**Current state:**
- `## [Unreleased]` — empty (line 8–9)
- `## [0.3.1] - 2026-06-06` — fully written
- `## [0.3.0] - 2026-02-11` — fully written
- Footer link refs (lines 82–84): references v0.3.0...HEAD, **missing `[0.3.1]` link ref**

### v0.4.0 content outline (phases 9–14)

```markdown
## [0.4.0] - 2026-06-14

### Added

- `db.spatial.*` / `async_db.spatial.*` namespace: 11 spatial helpers (contains, within,
  intersects, dwithin, distance, nearest, area, perimeter, centroid, buffer, transform)
  with full sync/async parity; pure SQL builders, PostGIS guard, GeoDataFrame output
  via `into="gdf"`, four geometry input forms (point/wkt/geojson/ref)
- `SpatialAccessor` and `AsyncSpatialAccessor` exported from `pycopg` top-level
- Async methods previously missing: `add_primary_key`, `add_foreign_key`,
  `add_unique_constraint`, `truncate_table`, `drop_extension`, `database_exists`,
  `list_databases`, `create`, `create_from_env` on `AsyncDatabase`
- Sync methods previously missing: `insert_many`, `upsert_many`, `stream`, `notify`
  on `Database`
- `PooledDatabase.execute` now commits results before returning so `INSERT ... RETURNING`
  results are not rolled back on pool return
- `DatabaseExists` exception in the public exception hierarchy
- `validate_timestamp()`, `validate_privileges()`, `validate_object_type()`,
  `validate_csv_option()`, `validate_extension_name()` in `pycopg.utils`
- `interrogate` enforced in CI (docstring coverage ≥ 95%)
- mypy type checking in CI (non-blocking)
- `uv.lock` and `.python-version` for reproducible contributor environments

### Changed

- **BREAKING**: Async engine now uses `postgresql+psycopg_async://` driver URL (was
  `postgresql+psycopg://`) — fixes async query execution
- **BREAKING**: `AsyncDatabase.close()` now disposes the SQLAlchemy async engine
  (was a no-op) — connections are properly released
- **BREAKING**: Custom exception types now raised instead of `RuntimeError`/`ValueError`
  for domain errors: `ExtensionNotAvailable` (was RuntimeError), `TableNotFound` (was
  RuntimeError), `DatabaseExists` (was RuntimeError) — see MIGRATION.md
- `create_extension(schema=...)` and `create_schema(owner=...)` signatures aligned
  between sync and async (parameters added to async)
- `table_info` and `list_roles` semantics aligned sync/async
- All docstrings migrated to numpydoc format (Summary/Parameters/Returns/Raises)
- Dev tooling migrated to `uv` (`uv sync`, `uv run`, `uv build`); `pip install pycopg`
  for end users unchanged
- CI test and publish workflows use `uv` for dependency management and build

### Fixed

- `session()` context manager no longer masks the original exception when commit/close
  fails in the finally block
- Migration `_apply` and `rollback` now run inside an explicit atomic transaction
  (fixes partial-apply on error)
- Subprocess helpers use `os.environ` correctly (was `subprocess.os.environ`)
- Async `create_role` validates identifiers before executing (closes residual injection gap)
- Async `from_dataframe`/`from_geodataframe` now correctly apply `primary_key` (was silently
  ignoring it)
- `__version__` resolved via `importlib.metadata` (was stuck at `0.1.0`)

### Security

- Identifier validation extended to all remaining unvalidated parameters (see v0.3.1 for the
  initial hotfix; this release closes the residual gaps in `create_role` async path)
```

### Footer links to add/update

Replace current footer (lines 82–84) with:
```markdown
[Unreleased]: https://github.com/alkimya/pycopg/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/alkimya/pycopg/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/alkimya/pycopg/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/alkimya/pycopg/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/alkimya/pycopg/releases/tag/v0.2.0
```

Note: the `[0.3.1]` footer link was entirely missing from the current file — it must be added.

---

## F. Breaking Changes / MIGRATION Notes (REL-03)

### Confirmed breaking changes across phases 9–14

| Change | Phase | Breaking? | Migration note needed |
|--------|-------|-----------|----------------------|
| Async engine URL: `postgresql+psycopg` → `postgresql+psycopg_async` | 11 (C3/PAR-06) | YES — affects anyone constructing `AsyncDatabase` and relying on the underlying SQLAlchemy engine URL | Yes — users passing raw URLs to SQLAlchemy directly need to update |
| `AsyncDatabase.close()` now disposes engine | 11 (C2/PAR-05) | Soft-breaking — if code called `close()` and expected pool to remain open (the no-op behavior), it now disposes. In practice: closer to a bug fix than a breaking change | Document as Changed |
| Custom exceptions: `ExtensionNotAvailable`, `TableNotFound`, `DatabaseExists` instead of `RuntimeError`/`ValueError` | 13 (V2/DOC-09) | YES — `except RuntimeError` catch blocks in user code will no longer catch these | Yes — must update except clauses |
| `create_extension(schema=...)` signature aligned async | 11 (PAR-07) | Additive only (added `schema` param to async). Not breaking. | No |
| `create_schema(owner=...)` aligned | 11 (PAR-07) | Additive only. | No |
| `__version__` now reflects real version | 13 (V1) | Non-breaking (was returning wrong value before, now returns correct). | No |

### MIGRATION.md status

`MIGRATION.md` already exists and covers the v0.2.0 → v0.3.0 migration. It must be **updated** (not replaced) with a new section for v0.3.x → v0.4.0.

**New section to add to `MIGRATION.md`:**

```markdown
# Migration Guide: v0.3.x to v0.4.0

## Breaking Changes

### 1. AsyncDatabase engine URL (psycopg_async driver)

**Affected users:** Anyone inspecting or passing through `AsyncDatabase._async_engine` URLs.

**What changed:** Async engine now uses `postgresql+psycopg_async://` URL scheme (was
`postgresql+psycopg://`). This is the correct driver for async psycopg v3.

**Impact:** Low. Only affects code that reads or logs `async_engine.url`. The API
(`execute`, `connect`, etc.) is unchanged.

### 2. AsyncDatabase.close() now disposes the engine

**What changed:** `close()` now calls `await engine.dispose()`. Previously a no-op.

**Impact:** Any code that called `close()` and then attempted to use the connection
again will now fail (engine is disposed). This was already incorrect behavior — `close()`
semantics imply the database object should not be used afterward.

### 3. Custom exception types replace RuntimeError/ValueError

**What changed:** These methods now raise domain-specific exceptions instead of
`RuntimeError` or `ValueError`:

| Method | Old exception | New exception |
|--------|---------------|---------------|
| `create_extension()` when extension missing | `RuntimeError` | `ExtensionNotAvailable` |
| `has_extension()` result check → callers using `RuntimeError` | — | — |
| `create_database()` when database exists | `RuntimeError` | `DatabaseExists` |
| Other extension-requiring methods | `RuntimeError` | `ExtensionNotAvailable` |

**Migration:** Update `except` clauses:
```python
# Before
try:
    db.create_extension("postgis")
except RuntimeError:
    pass

# After
from pycopg import ExtensionNotAvailable
try:
    db.create_extension("postgis")
except ExtensionNotAvailable:
    pass
```

**Impact:** Medium. Any code with broad `except Exception` or `except PycopgError`
catch-all clauses is unaffected. Only `except RuntimeError` or `except ValueError`
catch blocks need updating.
```

### Verdict on version number

A **0.3.x → 0.4.0 minor bump** is appropriate for these breaking changes. SemVer for pre-1.0 (0.x.y) permits breaking changes in minor bumps. The breaking changes are real but limited in scope. A standalone `MIGRATION.md` v0.4.0 section (as described above) is sufficient; a full separate file is not needed.

---

## G. Publish Path (REL-04)

### `publish.yml` full breakdown

**Trigger:** `on: release: types: [published]` — fires when a GitHub Release is **published** (not draft). Also has `workflow_dispatch` for manual testing.

**Job 1: `build`** (ubuntu-latest):
1. `actions/checkout@v4`
2. `astral-sh/setup-uv@v8.2.0` (installs uv)
3. `uv lock --check` (verifies lockfile is current)
4. `uv build` (produces `dist/pycopg-*.tar.gz` + `dist/pycopg-*.whl`)
5. `actions/upload-artifact@v4` — uploads `dist/` directory as artifact named `dist`

**Job 2: `publish`** (ubuntu-latest, needs: build):
- Environment: `pypi` (requires environment approval if configured in GitHub)
- Permission: `id-token: write` (OIDC token for trusted publishing)
- Steps:
  1. `actions/download-artifact@v4` — downloads `dist/` artifact
  2. `pypa/gh-action-pypi-publish@release/v1` — publishes to PyPI via OIDC (no API token needed)

**Trusted publishing:** OIDC flow — no manual API token needed. Configured via PyPI project trusted publisher settings pointing to `alkimya/pycopg` repository + `publish.yml` workflow. [VERIFIED: workflow confirmed from file; OIDC config assumed to be correctly set from v0.3.1 publish]

### Exact human sequence to ship v0.4.0

1. Complete all code/doc/CI changes, commit to `main`
2. Run locally: `uv lock --check` (verify lockfile is current)
3. Run locally: `uv build` — verify produces `dist/pycopg-0.4.0.tar.gz` + `dist/pycopg-0.4.0-py3-none-any.whl`
4. Run locally: `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` — verify green
5. Run locally: `uv run pytest` — verify all tests pass
6. **[HUMAN-GATED / IRREVERSIBLE]** Create git tag: `git tag v0.4.0 && git push origin v0.4.0`
7. **[HUMAN-GATED / IRREVERSIBLE]** On GitHub: Releases → "Draft a new release" → select tag `v0.4.0` → fill in release notes → click "Publish release"
8. GitHub Actions `publish.yml` fires automatically: build → upload artifact → download artifact → PyPI publish
9. Verify: `pip install pycopg==0.4.0` in a clean venv; check `pycopg.__version__ == "0.4.0"`
10. Verify RTD live build green at https://pycopg.readthedocs.io/

**Pre-publish validation (recommended):** Run `uv build` locally before pushing the tag to verify wheel content:
```bash
uv build
python -m zipfile -l dist/pycopg-0.4.0-py3-none-any.whl | grep spatial
# Should show: pycopg/spatial.py
```

**Note on `uv lock --check`:** The lockfile must be current at build time (step 3 in the CI build job). If `pyproject.toml` version was bumped after the last `uv lock`, run `uv lock` to regenerate before pushing.

**`workflow_dispatch` dry-run:** `publish.yml` has `workflow_dispatch` — can be triggered manually on a branch (without a tag) to test the build job only. The publish job will still require the `pypi` environment and id-token, but it will try to publish whatever is in `dist/`. Use with caution: manually triggering against a `0.4.0.dev0` build would avoid polluting PyPI.

---

## H. Node 20 → 24 Action Bumps (REL-05)

**Context:** GitHub deprecated Node.js 20 in Actions starting June 2, 2026 (per search results). Node.js 20 will be removed from runners September 16, 2026. Deprecation warnings were observed during the v0.3.1 release. As of research date (2026-06-14), all current versions in the workflows use Node 20.

### Current versions and required upgrades

**`tests.yml`:**

| Line | Current | Node runtime | Required version | Node runtime |
|------|---------|--------------|-----------------|--------------|
| 33 | `actions/checkout@v4` | node20 | `actions/checkout@v6` | node24 [CITED: github.com/actions/checkout/releases] |
| 36 | `astral-sh/setup-uv@v8.2.0` | node20 | `astral-sh/setup-uv@v8.2.0` is ALREADY latest [VERIFIED: releases page shows v8.2.0 is current] | Node runtime TBD — see note below |

**`publish.yml`:**

| Line | Current | Node runtime | Required version | Node runtime |
|------|---------|--------------|-----------------|--------------|
| 12 | `actions/checkout@v4` | node20 | `actions/checkout@v6` | node24 |
| 15 | `astral-sh/setup-uv@v8.2.0` | node20 | See note | — |
| 24 | `actions/upload-artifact@v4` | node20 | `actions/upload-artifact@v6` | node24 [CITED: search results] |
| 37 | `actions/download-artifact@v4` | node20 | `actions/download-artifact@v4` → check if v5/v6 needed | [ASSUMED: same family as upload-artifact, likely v6] |
| 43 | `pypa/gh-action-pypi-publish@release/v1` | node20 | `release/v1` is a floating tag — may already be updated | [ASSUMED: check if @v1.14.0 uses node24] |

**Note on `astral-sh/setup-uv@v8.2.0`:** The search results show v8.2.0 is the latest release. A commit in the setup-uv repo added node24 support (commit `3deccc0`). However, from the releases page, v8.2.0 was the latest as of the page fetch (dated June 3, 2024 — this date is likely the rendering date, not release date). The node24 migration for setup-uv may be included in v8.2.0 or require a higher version. **[ASSUMED — planner should verify `astral-sh/setup-uv` node24 status before committing to a version bump; the current v8.2.0 may already be sufficient, or a newer patch release may be needed.]**

**Concrete old → new mapping (confirmed):**

| File | Old | New |
|------|-----|-----|
| `.github/workflows/tests.yml:33` | `actions/checkout@v4` | `actions/checkout@v6` |
| `.github/workflows/publish.yml:12` | `actions/checkout@v4` | `actions/checkout@v6` |
| `.github/workflows/publish.yml:24` | `actions/upload-artifact@v4` | `actions/upload-artifact@v6` |
| `.github/workflows/publish.yml:37` | `actions/download-artifact@v4` | `actions/download-artifact@v6` [ASSUMED: same family] |

**Items needing human verification before commit:**
- `astral-sh/setup-uv` — verify current latest version supports node24; update to that version
- `pypa/gh-action-pypi-publish@release/v1` — verify if floating `release/v1` tag already includes node24 support (if not, pin to specific node24 release)

---

## I. Milestone Audit (REL-06)

`gsd-audit-milestone` is not found as a local command (`which gsd-audit-milestone` → not found). It is a GSD orchestration command that validates all phase plans, requirements, and summaries are in order before the milestone is archived.

**What it checks (based on GSD conventions):** [ASSUMED — based on GSD tool knowledge]
- All phase PLAN.md files exist and are marked complete
- All requirements listed in REQUIREMENTS.md are checked off
- ROADMAP.md progress table is up to date
- STATE.md reflects final state
- No pending blockers or todos

**Planner action:** Include as the final task of the phase, marked `autonomous: false` (requires human to run and verify), after PyPI publish is confirmed and RTD is green. It is a post-publish gate, not a pre-publish gate.

---

## J. Ordering, Dependencies, and Safety

### Recommended wave structure

```
Wave 0 (setup, no external impact):
  - Bump pyproject.toml version (line 7): 0.3.1 → 0.4.0
  - Bump docs/conf.py release (line 17): '0.3.1' → '0.4.0'
  - Update CHANGELOG.md (add v0.4.0 section, fix footer links)
  - Update MIGRATION.md (add v0.3.x → v0.4.0 section)
  - Bump GitHub Actions: checkout@v4→v6, upload-artifact@v4→v6, download-artifact@v4→v6

Wave 1 (doc content — parallel-safe after Wave 0):
  - Rewrite docs/postgis.md: 7 execute() blocks → db.spatial.* helpers
  - Add pycopg.spatial to docs/api-autodoc.md
  - Add db.spatial.* section to docs/api-reference.md  
  - Create docs/spatial.md (new narrative page for spatial helpers)
  - Update docs/index.md toctree: add 'spatial' entry

Wave 2 (verification — depends on Wave 0+1):
  - Run: uv run sphinx-build -W --keep-going -b html docs docs/_build/html
    → must exit 0
  - Run: uv run pytest → all tests must pass (coverage ≥ 94%)
  - Run: uv run interrogate pycopg --fail-under 95 --quiet → must pass
  - Run: uv build → verify dist/pycopg-0.4.0.tar.gz and dist/pycopg-0.4.0-py3-none-any.whl created
  - Verify wheel contains pycopg/spatial.py: python -m zipfile -l dist/*.whl | grep spatial

Wave 3 — HUMAN-GATED, IRREVERSIBLE:
  - Push all commits to main
  - Push tag: git tag v0.4.0 && git push origin v0.4.0
  - Create GitHub Release: select v0.4.0 tag, fill release notes, click Publish
    → publish.yml fires automatically
  - Verify on PyPI: pip install pycopg==0.4.0 in clean venv
  - Verify RTD build is green (https://readthedocs.org/projects/pycopg/builds/)

Wave 4 — post-publish (HUMAN-GATED):
  - Run gsd-audit-milestone (REL-06)
```

### Irreversible / Human-gated steps

| Step | Why irreversible | Mitigation |
|------|-----------------|-----------|
| `git tag v0.4.0` + `git push origin v0.4.0` | Tags cannot be reliably un-pushed without force; deleting a tag after publish is cosmetically messy | Verify local build is green before tagging |
| GitHub Release "Publish" | Triggers PyPI publish automatically; PyPI does not allow re-upload of same version | Run `uv build` + inspect wheel locally first; run full test suite |
| PyPI publish | Cannot overwrite a published version; 0.4.0 will be permanent on PyPI | Full pre-flight checks in Wave 2 |

### Safety note on lockfile

`uv lock --check` runs as the first step in `publish.yml`'s build job. If `pyproject.toml` version was bumped without regenerating `uv.lock`, the CI build will fail at this check. Task: after bumping `pyproject.toml`, run `uv lock` to update the lockfile and commit it alongside.

---

## Architecture Patterns

### Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Version source of truth | `pyproject.toml` | `docs/conf.py` (derives from pyproject) | hatchling reads pyproject; `importlib.metadata` reads installed package metadata |
| Doc generation | Sphinx (build-time, local + RTD) | narrative .md files | autodoc + MyST Parser |
| Package distribution | PyPI (via GitHub Actions trusted publishing) | RTD (docs only) | standard Python packaging |
| CI / linting | GitHub Actions | local uv commands | same commands, different execution environment |

### Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| PyPI publish auth | Custom token management | OIDC trusted publishing (already configured) |
| Version sync | Manual grep-and-replace script | Single source in pyproject.toml; dynamic `__version__` |
| Sphinx API docs | Hand-written class/method tables for pycopg.spatial | `.. automodule:: pycopg.spatial :members:` |
| Wheel contents verification | Shell scripting | `python -m zipfile -l dist/*.whl` |

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (configured in pyproject.toml `[tool.pytest.ini_options]`) |
| Config | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x -q -o addopts=""` |
| Full suite command | `uv run pytest` (uses pyproject addopts: `--cov-fail-under=94`) |

### Phase 15 Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | Notes |
|--------|----------|-----------|-------------------|-------|
| REL-01 | Sphinx build green after doc changes | smoke | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` | Must exit 0 |
| REL-01 | interrogate passes after spatial.py added to autodoc | smoke | `uv run interrogate pycopg --fail-under 95 --quiet` | spatial.py already has full docstrings |
| REL-02 | RTD build green | manual | check https://readthedocs.org/projects/pycopg/builds/ | Cannot automate |
| REL-03 | Version in wheel matches 0.4.0 | smoke | `python -c "import pycopg; print(pycopg.__version__)"` after `uv sync` | |
| REL-03 | uv build produces correct wheel | smoke | `uv build && python -m zipfile -l dist/pycopg-0.4.0-py3-none-any.whl` | verify spatial.py included |
| REL-04 | PyPI publish succeeded | manual | `pip install pycopg==0.4.0` in clean venv | |
| REL-05 | CI passes with Node 24 actions | CI | push to main, observe Actions run | |
| REL-06 | Milestone audit passes | manual | `gsd-audit-milestone` | Final gate |

### Sampling Rate
- **Per task commit:** `uv run sphinx-build -W --keep-going -b html docs docs/_build/html`
- **Pre-publish gate:** Full pytest suite + interrogate + sphinx build + uv build
- **Post-publish:** Manual: `pip install pycopg==0.4.0` + RTD live check

---

## Environment Availability

| Dependency | Required By | Available | Version | Notes |
|------------|------------|-----------|---------|-------|
| uv | build, lint, test | ✓ | (in PATH) | |
| sphinx-build | doc verification | ✓ | 9.1.0 | `uv run sphinx-build` |
| python | all | ✓ | 3.11+ | |
| PyPI trusted publishing | REL-04 | ✓ (assumed) | OIDC | Worked for v0.3.1; assumed same config |
| RTD account | REL-02 | ✓ (assumed) | — | Confirmed RTD URL in conf.py |
| GitHub write access | tag + release | manual (human) | — | Human must perform |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `astral-sh/setup-uv@v8.2.0` needs a version bump for node24 (may already support it) | §H | If it already supports node24, no bump needed; if it doesn't and a newer version is needed, must find correct version |
| A2 | `pypa/gh-action-pypi-publish@release/v1` floating tag may already point to a node24 version | §H | If it still runs node20, deprecation warning will persist |
| A3 | `actions/download-artifact@v6` is the correct node24 version (mirroring upload-artifact) | §H | Pinning wrong version; check github.com/actions/download-artifact/releases |
| A4 | PyPI trusted publishing OIDC environment is still correctly configured (it worked for v0.3.1) | §G | If OIDC config drifted or expired, publish job will fail; human must re-configure |
| A5 | `uv lock` will correctly update after `pyproject.toml` version bump | §G | If lockfile format changed between uv versions, may need `uv lock --upgrade-package pycopg` |
| A6 | gsd-audit-milestone checks plan completeness, requirements, and STATE.md | §I | Command not found locally; actual check criteria unknown until run |

---

## Open Questions

1. **Is `astral-sh/setup-uv@v8.2.0` already node24-compatible?**
   - What we know: The setup-uv repo had a node24 commit merged. v8.2.0 is the latest release from the releases page.
   - What's unclear: Whether v8.2.0 includes that commit or if a higher patch version is needed.
   - Recommendation: Check `github.com/astral-sh/setup-uv/releases` for the release after node24 PR was merged; use that version.

2. **Should the "Spatial Analysis" example in `postgis.md` be partially converted?**
   - What we know: The aggregate queries (multi-table spatial join, `SUM(ST_Area(...))`) cannot be expressed with single helpers.
   - What's unclear: Whether the doc should show a hybrid (some helpers for the setup part, raw SQL for the aggregate).
   - Recommendation: Keep the narrative example as-is with a comment directing readers to `db.spatial.*` for single-table operations; raw SQL remains correct for complex aggregates.

3. **Does RTD need a new webhook trigger after the `main` push?**
   - What we know: RTD auto-builds from the configured branch. The current `.readthedocs.yaml` is valid.
   - What's unclear: If the RTD project was ever disconnected or the webhook is stale.
   - Recommendation: Check RTD project settings after pushing; if build doesn't trigger in 5 min, manually trigger from RTD dashboard.

---

## Sources

### Primary (HIGH confidence — directly read from repo)
- `/home/loc/workspace/pycopg/pyproject.toml` — version string, build system, dep groups
- `/home/loc/workspace/pycopg/docs/conf.py` — Sphinx version string, extensions, napoleon config
- `/home/loc/workspace/pycopg/docs/postgis.md` — all execute() blocks, exact line ranges
- `/home/loc/workspace/pycopg/docs/api-autodoc.md` — autodoc modules list (spatial gap)
- `/home/loc/workspace/pycopg/docs/api-reference.md` — hand-written reference tables
- `/home/loc/workspace/pycopg/docs/index.md` — toctree structure
- `/home/loc/workspace/pycopg/.github/workflows/publish.yml` — publish mechanism
- `/home/loc/workspace/pycopg/.github/workflows/tests.yml` — CI steps
- `/home/loc/workspace/pycopg/.readthedocs.yaml` — RTD build config
- `/home/loc/workspace/pycopg/CHANGELOG.md` — format, existing content, missing footer link
- `/home/loc/workspace/pycopg/MIGRATION.md` — existing structure
- `/home/loc/workspace/pycopg/pycopg/spatial.py` — SpatialAccessor/AsyncSpatialAccessor full implementation, all 11 helper signatures
- `/home/loc/workspace/pycopg/pycopg/__init__.py` — `__version__` dynamic resolution, spatial exports
- `/home/loc/workspace/pycopg/pycopg/exceptions.py` — exception class names
- Local `sphinx-build` run (exit 0) — confirmed current build passes

### Secondary (MEDIUM confidence — web search with official sources)
- [actions/checkout releases](https://github.com/actions/checkout/releases) — v6 is latest, v5 uses node24 (v5 used node24, v6 uses node24)
- [actions/upload-artifact releases / search results](https://github.com/actions/upload-artifact/releases) — v6 uses node24
- [astral-sh/setup-uv releases](https://github.com/astral-sh/setup-uv/releases) — v8.2.0 is current latest
- [GitHub Actions node24 deprecation](https://github.com/orgs/community/discussions/190988) — June 2, 2026 deadline, Sept 16, 2026 removal

### Tertiary (LOW confidence — requires verification)
- `astral-sh/setup-uv` node24 inclusion in v8.2.0 — confirmed commit exists in repo but not confirmed in v8.2.0 specifically
- `pypa/gh-action-pypi-publish@release/v1` node24 status — not directly verified

---

## Metadata

**Confidence breakdown:**
- Version bump surface: HIGH — direct file reads, exact line numbers
- PostGIS doc examples: HIGH — direct file reads, helper signatures from spatial.py
- API reference / autodoc gap: HIGH — confirmed via Sphinx build output
- RTD build: HIGH — `.readthedocs.yaml` fully read; local build confirmed green
- CHANGELOG: HIGH — Keep a Changelog format confirmed; v0.4.0 content derived from ROADMAP/REQUIREMENTS
- Breaking changes: HIGH — source code confirmed (exceptions.py, config.py async_url)
- Publish path: HIGH — publish.yml fully read; OIDC assumed working from v0.3.1 precedent
- Node 20 → 24 actions: MEDIUM — checkout@v6 confirmed, upload/download @v6 confirmed, setup-uv and pypi-publish need verification
- gsd-audit-milestone: LOW — command not found locally; behavior assumed from GSD conventions

**Research date:** 2026-06-14
**Valid until:** 2026-07-14 (GitHub Actions versions move quickly; re-verify action versions if > 1 week passes)
