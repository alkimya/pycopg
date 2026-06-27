# Pitfalls Research

**Domain:** pycopg v1.0.0 — Spatial v2 + API Freeze on a mature published PyPI library
**Researched:** 2026-06-27
**Confidence:** HIGH (all findings grounded in pycopg's own history, codebase, and PostGIS/mypy documentation)

---

## Critical Pitfalls

### Pitfall 1: validate_identifiers Silently Dropped During Spatial v2 Builder Additions

**What goes wrong:**

New spatial v2 builders (`build_union_sql`, `build_difference_sql`, `build_simplify_sql`, etc.) are
written without the `validate_identifiers(table, schema, geom)` guard at the top. The SQL template
assembles correctly, the suite stays green, the PR ships. Users can now inject arbitrary SQL via the
`table` or `geom` argument.

This is not hypothetical: the v0.10.0 COPY rewrite on `from_dataframe` / `from_geodataframe`
silently dropped `validate_identifiers` and was caught only by the code-review gate — the test
suite stayed completely green (milestone MEMORY: "the COPY rewrite dropped `validate_identifiers`
→ caught by code-review gate, fixed 863e894 inside the helpers"). The same failure mode is
identically likely for every new builder written for Spatial v2.

**Why it happens:**

Each new builder is written in isolation, following the existing builder signature shape but without
internalizing the security invariants documented in `spatial.py`'s module docstring. The existing
builders all call `validate_identifiers(table, schema, geom)` as their first line; new builders
added without reading that module docstring omit it. Unit tests test correctness, not absence of
injection guards — a builder that correctly builds the SQL without calling `validate_identifiers`
passes all correctness tests.

**How to avoid:**

1. The first line of every new `build_*_sql` function in `spatial.py` must be
   `validate_identifiers(table, schema, geom)` (plus `validate_identifiers(*columns)` if
   `columns=` is accepted). This is a mechanical checklist item for the Spatial v2 phase plan.
2. Add an explicit injection-safety regression test for every new builder: call it with a
   `table="'; DROP TABLE foo; --"` argument and assert `InvalidIdentifier` is raised. This test
   goes into the builder's unit test file, not just the integration suite. It will catch any
   future rewrite that drops the guard.
3. The Spatial v2 phase plan must include a requirement: "injection-safety regression test written
   for every new builder (table, schema, geom, and columns)."

**Warning signs:**

- A new `build_*_sql` function in `spatial.py` whose first statement is NOT `validate_identifiers`.
- A new builder that has no test asserting `InvalidIdentifier` on a malicious identifier.
- The phrase "test suite stayed green" after a significant spatial.py rewrite.

**Phase to address:**

Spatial v2 processing phase (Phase 41 or equivalent). Requirement must be in the phase's
acceptance criteria, not just a code review note.

---

### Pitfall 2: SRID Mismatch Causes Silent Wrong Results or Cryptic Errors in Binary Operations

**What goes wrong:**

`ST_Union`, `ST_Difference`, and `ST_Intersection` operating on two geometry arguments fail with:

```
ERROR: Operation on mixed SRID geometries (SRID 4326 != SRID 32632)
```

or, worse, silently produce a geometry in the wrong coordinate system when PostGIS accepts the
operation (e.g., both inputs are in SRID 0 = undefined). The API user passed geometries from two
different sources without noticing they were in different SRIDs. The error message is a raw
psycopg `ProgrammingError`, not a pycopg domain error.

For aggregate operations (`ST_Union(agg)`, `ST_Extent`), PostGIS will raise the mixed-SRID error
at execution time only if rows in the same table have inconsistent SRIDs — which is valid from
a storage perspective but catastrophic for the aggregation. There is no guard at the SQL level.

**Why it happens:**

The existing spatial v1 builders operate on single-table single-geometry-column paths where SRID
consistency is assumed from the table schema. Spatial v2 binary operations (Difference,
Intersection) and aggregates operate across rows that may have mixed SRIDs if the table was
loaded inconsistently. pycopg's builder cannot validate SRIDs at builder time (they are DB values);
the error surfaces only at execution time as a raw psycopg error.

**How to avoid:**

1. For binary processing builders (`union`, `difference`, `intersection`): document clearly that
   both geometry operands must share the same SRID. If the API takes a `srid=` parameter, use it
   to emit `ST_SetSRID(..., srid)` on user-supplied WKT/GeoJSON inputs and `ST_Transform(col,
   srid)` on table-column inputs. Do not silently assume SRID matches.
2. For aggregate builders: document that mixed-SRID tables will raise a PostGIS error at
   execution time. Recommend `ST_Transform` preprocessing or an explicit SRID filter in `where=`.
3. Wrap raw PostGIS SRID errors in a pycopg domain exception at the accessor level (a
   `SpatialError` or use `ExtensionNotAvailable` pattern) so users see a clear pycopg message,
   not a bare `ProgrammingError`.
4. Integration tests must use consistent-SRID fixtures. Add a test with a deliberate SRID mismatch
   that asserts a clear exception (not a silent wrong result).

**Warning signs:**

- Integration tests pass because all test geometries happen to be SRID 4326 — no mixed-SRID
  coverage.
- A new binary operation builder with no `srid=` parameter or SRID documentation in the docstring.
- `ProgrammingError` surfaces raw from a spatial accessor instead of a pycopg domain error.

**Phase to address:**

Spatial v2 processing phase. Each binary operation method must document SRID assumptions. At least
one mixed-SRID test per binary operation.

---

### Pitfall 3: ST_AsMVT Requires EPSG:3857 + ST_AsMVTGeom Clipping — Wrong Coordinate System Produces Corrupted Tiles

**What goes wrong:**

`ST_AsMVT` is called directly on geometries stored in SRID 4326 (WGS84 lat/lon). The tile comes
back without error but the coordinates are in degrees, not tile pixel space. Map renderers
(MapLibre, Leaflet) display nothing or garbage.

The correct sequence is:
1. `ST_Transform(geom, 3857)` — project to Web Mercator
2. `ST_AsMVTGeom(transformed_geom, ST_TileEnvelope(z, x, y))` — clip to tile envelope and scale
   to pixel space (0–4096)
3. `ST_AsMVT(agg.*)` — binary encode the result

Skipping ST_AsMVTGeom or using the raw geometry skips the clipping step; geometries outside the
tile boundary are not clipped to the envelope, producing corrupted vector tiles.

Additionally, `ST_TileEnvelope(z, x, y)` is a PostGIS 3.0+ function. On PostGIS < 3.0, it does
not exist and the call raises `UndefinedFunction`.

**Why it happens:**

Developers familiar with `ST_AsGeoJSON` (which works correctly on 4326 data) apply the same
"just wrap the geometry column" mental model to `ST_AsMVT`. MVT has fundamentally different
coordinate space requirements from GeoJSON. The transform-and-clip steps are not optional.

**How to avoid:**

1. The `as_mvt` accessor method signature must accept `z`, `x`, `y` tile coordinates as required
   positional parameters. The builder internally uses `ST_TileEnvelope(z, x, y)` for the clip
   envelope. Document that the input geometry column must be in a projected CRS or accept a
   `from_srid=` parameter to apply the transform automatically.
2. The builder must always emit `ST_Transform(col, 3857)` followed by `ST_AsMVTGeom` + `ST_AsMVT`
   — never expose a raw-geometry path.
3. Integration test: call `as_mvt` with tile (0, 0, 0), assert the result is non-empty bytes, and
   decode with the `mapbox-vector-tile` library (or a minimal MVT parser) to verify the tile
   contains at least one feature. A test that only asserts `isinstance(result, bytes)` does not
   catch the wrong-coordinate-system bug.
4. Add a PostGIS version check or a `try/except UndefinedFunction` guard for `ST_TileEnvelope`
   with a clear error on PostGIS < 3.0.

**Warning signs:**

- The `as_mvt` builder takes only a geometry column name with no tile coordinate parameters.
- The generated SQL does not contain `ST_Transform` and `ST_AsMVTGeom`.
- Integration test only checks `result is not None` or `len(result) > 0`.

**Phase to address:**

Spatial v2 serialization phase. MVT is the highest-complexity serialization target; it must be
designed from the PostGIS 3.x `ST_AsMVT` specification, not inferred from the GeoJSON pattern.

---

### Pitfall 4: ST_MakeValid and ST_Simplify Return NULL or Degenerate Geometry — Not Handled

**What goes wrong:**

`ST_Simplify(geom, tolerance)` returns `NULL` when the result collapses to an empty geometry (all
points within tolerance distance of each other). `ST_MakeValid` returns a
`GEOMETRYCOLLECTION EMPTY` for pathological inputs. These NULLs and empty collections propagate
silently into the GeoDataFrame output as None geometries. When `into="gdf"` is used, geopandas
raises on geometry operations over a GeoDataFrame containing null geometries (e.g., `.area`,
`.buffer`), producing confusing downstream errors.

`ST_MakeValid` can also change geometry type: a POLYGON with a self-intersection becomes a
MULTIPOLYGON or GEOMETRYCOLLECTION. A column typed as `geometry(Polygon, 4326)` may receive a
GEOMETRYCOLLECTION back — PostGIS accepts it but geopandas explodes the geometry type assumptions
downstream.

**Why it happens:**

The builders emit `ST_Simplify(t.geom, %s)` or `ST_MakeValid(t.geom)` and return the result.
Nothing in the builder chain checks whether the output is NULL or EMPTY. Unit tests use
well-formed synthetic geometries that don't trigger collapse or type change.

**How to avoid:**

1. Wrap simplify results in `ST_SimplifyPreserveTopology` by default — it avoids the NULL collapse
   on simple geometries. Expose `preserve_topology: bool = True` as a parameter. Only use bare
   `ST_Simplify` when `preserve_topology=False` is explicit.
2. For `make_valid`, document in the docstring: "The output geometry type may differ from the
   input (e.g., POLYGON may become MULTIPOLYGON or GEOMETRYCOLLECTION)." Add a note that NULL
   results (for empty inputs) are passed through.
3. Integration tests must include at least one degenerate case: a self-intersecting polygon
   (bowtie) passed to `make_valid`, asserting non-NULL, non-empty output; and a geometry with
   all points within tolerance passed to `simplify`, asserting the result is handled (either NULL
   returned or documented).

**Warning signs:**

- The `simplify` accessor uses `ST_Simplify` with no `preserve_topology` parameter.
- Integration tests use only clean, convex polygon fixtures.
- No test asserts behavior on a degenerate input geometry.

**Phase to address:**

Spatial v2 processing phase. `ST_SimplifyPreserveTopology` must be the default; `ST_Simplify` is
the opt-out.

---

### Pitfall 5: Spatial Aggregate NULL Propagation — GROUP BY Without FILTER Silently Drops Groups

**What goes wrong:**

`ST_Union(agg)` and `ST_Collect` on a column that contains some NULL geometries produce a result
that silently excludes NULL rows from the aggregate (PostgreSQL aggregate semantics: NULLs are
ignored). The user expects a result covering all groups but receives an aggregate over only the
non-NULL subset. On tables where NULL geometries are common (e.g., optional spatial data), the
output is systematically incomplete without any error.

`ST_Extent` (bounding box aggregate) returns NULL for an empty group — when `where=` filters
produce zero rows for a given group, `ST_Extent` returns NULL for that group, which surfaces as
a None-valued row in the output.

**Why it happens:**

Aggregate NULL-skipping is correct SQL behavior but violates the user's expectation when building
spatial aggregates. The builder has no visibility into which rows have NULL geometries. Integration
tests use clean fixtures without NULL geometries.

**How to avoid:**

1. Document NULL-skipping behavior explicitly in docstrings for `union_agg`, `collect`, and
   `extent`: "NULL geometries are skipped per SQL aggregate semantics. Rows where the geometry
   column is NULL do not contribute to the aggregate."
2. Integration tests must include at least one NULL geometry row and assert the output reflects
   only non-NULL geometries (verifying the behavior is documented, not that it is wrong).
3. For `extent`, document that an empty group returns NULL (not an empty geometry) and test this
   case.

**Warning signs:**

- No test with NULL geometries in the fixture table.
- Docstrings say nothing about NULL behavior.

**Phase to address:**

Spatial v2 aggregates phase.

---

### Pitfall 6: Deprecation Cycle Done Wrong — DeprecationWarning Invisible or Wrong stacklevel

**What goes wrong:**

The homogenization pass renames methods (e.g., `db.schema.table_info` to `db.schema.describe`,
or exception class renames). Old names are wrapped with `@deprecated_alias` or equivalent. But:

- `stacklevel=2` in the `warnings.warn()` call points to the wrapper function, not the caller's
  line. Users see the warning pointing at pycopg internals, not their own code.
- `pytest` runs with `-W error::DeprecationWarning` (enforced by the CI gate). If a new deprecation
  wrapper is accidentally used internally (e.g., an internal call that goes through the deprecated
  path), CI turns red immediately on the next test run for an unrelated reason.
- The MIGRATION guide lists the old name but not the full signature diff. If the new method has a
  different parameter name or different return type, users get an AttributeError or TypeError after
  migrating, not a deprecation warning.

**Why it happens:**

The `@deprecated_alias` decorator was established in v0.6.0 and worked correctly for the
accessor-reorganization case (old flat name → new accessor path). The v1.0.0 homogenization is
a different shape: same accessor, different method name or signature. The decorator must be applied
at the right layer. The stacklevel must be set correctly for the new wrapping depth.

The historical pattern (v0.6.0 → v0.7.0) was: one milestone to add the deprecation, next
milestone to remove it. v1.0.0 is the final milestone, so the deprecation cycle must be
compressed: add deprecation warning + MIGRATION, then hard-remove in the same milestone. This
changes the test sequencing.

**How to avoid:**

1. Every deprecated name must use `warnings.warn(..., stacklevel=2)` counted from the wrapper's
   call frame — verify this by running a test that calls the deprecated method and asserting the
   warning points to the test file, not to `pycopg/`.
2. The CI gate `-W error::DeprecationWarning` must stay green. Run the full suite against the
   deprecation wrappers before removing them in the same milestone.
3. The MIGRATION guide entry for each renamed method must include: old name, new name, any
   parameter differences, any return type differences, and a before/after code example.
4. Internal call sites in pycopg/ must use the new name, not the deprecated wrapper. Grep for
   old method names in `pycopg/` source before shipping.
5. If removing deprecated names in the same milestone as adding them: the removal phase must
   run the full test suite AFTER removal to confirm no internal call sites remain.

**Warning signs:**

- A `warnings.warn` call with no explicit `stacklevel` parameter (defaults to 1, points at
  the wrong frame).
- MIGRATION guide entry says "rename X to Y" with no parameter/type notes.
- `grep -r "old_method_name" pycopg/` returns hits in non-test files after the removal phase.

**Phase to address:**

API freeze / homogenization phase. Each renamed or reshaped method needs a MIGRATION entry
written before the deprecation wrapper is coded (spec first).

---

### Pitfall 7: Freezing an Inconsistent API — where= Is a Raw Fragment on Spatial, a Dict on CRUD

**What goes wrong:**

`db.spatial.contains(table, where="status = 'active'")` accepts a raw SQL fragment string.
`db.delete_where(table, where={"status": "active"})` requires a dict. Users who read one API
and apply it to the other get a silent wrong result (passing a string dict-style, or a dict
to the string-fragment path that ignores it) or a runtime TypeError.

If this inconsistency is frozen at 1.0 without a homogenization decision, it is locked in
for the 1.x lifetime. It is the most visible API incoherence in the current surface.

**Why it happens:**

The `where=` string-fragment convention was established in the spatial accessor (Phase 14,
decision D-11: "raw SQL filter is the caller's responsibility"). The dict-of-equality convention
was established later in CRUD helpers (v0.9.0, `_build_where_dict`). Both are correct within
their context. They were not compared across the surface before v1.0.0.

**How to avoid:**

The homogenization phase must make an explicit decision about `where=`:
- Option A: Standardize spatial on dict-of-equality for simple cases, keep string-fragment as
  an escape hatch. This is a breaking change to the spatial API.
- Option B: Standardize CRUD on string-fragment. This is a breaking change to CRUD.
- Option C: Document the difference explicitly in a `where= conventions` section of the API
  reference, freeze both forms. This is "freeze the inconsistency," which is acceptable IF
  documented but creates ongoing user confusion.

The decision must be made in the homogenization design phase, not after builders are written.
Whatever is chosen, the MIGRATION guide must document the collision clearly.

**Warning signs:**

- The API reference for v1.0.0 has no `where=` conventions section.
- `db.spatial.*` methods and `db.delete_where` are documented independently with no
  cross-reference.
- A user reports TypeError passing a dict to a spatial method's `where=`.

**Phase to address:**

Homogenization / API freeze phase (before any Spatial v2 builders are written, since new
builders will set a precedent for `where=` in v2 methods).

---

### Pitfall 8: Exception Naming — N818 Suppression Deferred to v1.0.0, Now Must Be Resolved

**What goes wrong:**

`pyproject.toml` currently suppresses ruff N818 (exception names should end in `Error`) for
`pycopg/exceptions.py` with the comment: "Reconsider at the v1.0.0 API freeze." The deferred
exceptions are: `ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier`, `DatabaseExists`.
Renaming them at v1.0.0 is a breaking change to any user who catches these by name.

If the decision is to rename (add `Error` suffix), the homogenization phase must:
1. Add the old name as a deprecated alias for one release cycle.
2. Export both names from `__all__`.
3. Update every `raise` site in pycopg/ to use the new name.
4. Update every `except` in tests to use the new name.
5. Update docs.
6. List in MIGRATION guide.

If the decision is to keep the old names (freeze the N818 suppression), the pyproject.toml
comment must be updated to say "kept as-is at v1.0.0" and the suppression must be justified.

**Why it happens:**

The decision was explicitly deferred in v0.10.0 (`pyproject.toml` line 95-96). It has not been
resolved. The v1.0.0 freeze is the last opportunity to rename without committing to the old
names forever.

**How to avoid:**

Make the decision at the start of the homogenization phase, not after the milestone is underway.
The decision is: rename (breaking, must serve via deprecation alias) or keep (freeze the
inconsistency, remove the ruff suppression comment). Either is defensible; the non-decision is
not.

If renaming: do it in a single atomic commit that updates `exceptions.py`, all `raise` sites,
all `except` sites in tests, and adds the old-name aliases. Run the full suite before removing
old names.

**Warning signs:**

- The pyproject.toml N818 suppression comment still says "Reconsider at v1.0.0" at the end
  of the freeze phase.
- Exception renaming is scattered across multiple phases rather than done atomically.

**Phase to address:**

Homogenization / API freeze phase, first task.

---

### Pitfall 9: mypy Strict Made Blocking Before Stub Gaps Are Resolved — Stalls the Milestone

**What goes wrong:**

`--strict` is added to the mypy CI gate. The suite immediately produces hundreds of errors from
third-party stub gaps: `geopandas`, `geoalchemy2`, `shapely`, and `psycopg` do not have complete
stub packages. `pandas` stubs exist (via `pandas-stubs`) but have gaps for DataFrame operations
pycopg uses. Every `into="gdf"` return type requires `@overload` to express `list[dict] |
gpd.GeoDataFrame`, which requires `gpd.GeoDataFrame` to be typed — but geopandas has no py.typed
marker and no complete stubs.

Making strict blocking before these stub gaps are addressed stalls the milestone entirely:
every subsequent commit turns CI red on mypy, blocking merges, demoralizing progress.

**Why it happens:**

The previous milestones kept mypy non-blocking (`continue-on-error: true` in CI). The switch to
blocking is the right v1.0.0 goal, but the sequence matters: enabling strict before resolving
stub gaps means the entire milestone runs under a red CI gate.

**How to avoid:**

Sequence the mypy work explicitly:

1. First, run mypy in non-strict mode on the existing codebase and fix all non-strict errors
   (these are already surfaced but ignored). This is low-cost and should be done before Spatial v2
   work starts.
2. Identify the stub gap for each external dependency: which functions/classes pycopg uses that
   lack type annotations. For each gap, write `[[tool.mypy.overrides]] ignore_missing_imports =
   true` (already present for most) OR write a local stub file (`pycopg/py.typed` is already
   present — the package is `py.typed` but stubs for deps are the issue).
3. For `into="rows"/"gdf"` return types: use `@overload` with `Literal["rows"]` and
   `Literal["gdf"]` to give correct return types. This requires careful signature design — do not
   add `@overload` retroactively after all spatial v2 builders are written.
4. Enable `--strict` only after steps 1-3 are complete. The `--strict` flag turns red only on
   new code that does not yet type-annotate, not on pre-existing stub gaps that are properly
   suppressed.
5. Do NOT enable `--strict` as blocking at the start of the milestone and "fix as you go" —
   this is the pattern that stalls.

**Warning signs:**

- mypy strict is toggled in CI before any stub gap audit has been run.
- `@overload` is absent on accessor methods that return `list[dict] | gpd.GeoDataFrame`.
- The phrase "fix mypy as we go" appears in a phase plan.

**Phase to address:**

Dedicated mypy phase, after Spatial v2 builders are complete but before the release phase. The
mypy phase must have a clear acceptance criterion: mypy strict passes with zero errors on the
full pycopg/ tree.

---

### Pitfall 10: mypy Strict Surfaces Latent Type Errors With No Test Signal

**What goes wrong:**

mypy strict enabled. Zero test failures. Dozens of mypy errors. The test suite stays green
because the type errors are in code paths exercised at runtime with dynamically typed values —
the functions run correctly in tests but their type annotations are wrong. Examples specific to
pycopg:

- `_to_named_binds` returns `tuple[str, dict]` but `dict` should be `dict[str, Any]` — mypy
  strict requires the key/value types.
- `_run` returns `list[dict] | gpd.GeoDataFrame` but `list[dict]` should be
  `list[dict[str, Any]]` — strict requires explicit Any.
- `params: list` should be `list[Any]` — strict flags untyped `list`.
- `validate_identifiers(*names: str)` — strict may flag that `None` can be passed (the current
  implementation has `if name is not None: validate_identifier(name)`, which accepts None at
  runtime but the type annotation says `str`).

These are not bugs — the code is correct — but mypy strict counts them as errors, and fixing them
requires touching many files simultaneously. If not planned, this becomes a large unscoped
refactor during the release phase.

**How to avoid:**

1. Run `uv run mypy --strict pycopg/ 2>&1 | grep error | wc -l` at the start of the mypy phase
   to count the error budget. Budget 30 minutes per error as a rough estimate.
2. Fix errors in bottom-up dependency order: `utils.py` and `exceptions.py` first (they have no
   internal imports), then `base.py`, then `spatial.py`, then accessor files.
3. For `Any`-typed parameters that must remain flexible (params lists, row dicts), use
   `from typing import Any` explicitly and annotate `list[Any]`, `dict[str, Any]`. This is
   correct typing — it documents intentional dynamic typing.
4. The `validate_identifiers(*names: str)` None-check is a latent signature mismatch — fix the
   signature to `*names: str | None` or remove the None check and require callers to not pass
   None. Choose before the mypy phase, not during.

**Warning signs:**

- The mypy error count exceeds 50 errors after enabling strict.
- Type errors are concentrated in `spatial.py` (the largest module with the most complex return
  types).
- The phrase "add `# type: ignore`" appears more than 5 times in a single PR.

**Phase to address:**

Dedicated mypy phase. The mypy phase's first task is counting the error budget; if > 100 errors,
schedule the mypy fix as a multi-session effort, not a single-day sprint.

---

### Pitfall 11: Sync/Async Parity Drift on New Spatial v2 Methods

**What goes wrong:**

A new spatial v2 method is added to `SpatialAccessor` (sync). The async version is added to
`AsyncSpatialAccessor` but with a slightly different signature: a parameter that is keyword-only
in sync becomes positional in async, or a default value differs, or the method is added to
`SpatialAccessor` but not yet to `AsyncSpatialAccessor` (forgotten). The parity test
`test_accessor_parity` catches missing methods but does NOT catch signature differences
(D-11 in the parity test: "per-method signature parity is intentionally deferred").

After v1.0.0 API freeze, signature differences between sync and async are locked in.

**Why it happens:**

The spatial.py file is 2832 lines for v1 (11 methods × 2 classes). Adding Spatial v2 (~12 more
methods) will expand it to ~5000 lines. With this volume, copy-paste errors between the sync and
async accessor class are likely. The existing `test_accessor_parity` only checks that method names
exist on both classes — it does not compare signatures.

**How to avoid:**

1. Add signature-level parity assertions to the existing `test_accessor_parity` mechanism for the
   Spatial v2 methods. Use `inspect.signature(sync_method)` vs `inspect.signature(async_method)`
   and assert parameter names and defaults match. This is the highest-leverage parity guard.
2. Follow the v1 implementation pattern: write the builder (module-level, shared), write the
   sync accessor method, write the async accessor method immediately after in the same commit.
   Do not write all sync methods first and all async methods later (divergence window grows).
3. The Spatial v2 phase plan must explicitly list both `SpatialAccessor` and
   `AsyncSpatialAccessor` as implementation targets for every method.

**Warning signs:**

- A commit adds a method to `SpatialAccessor` but not `AsyncSpatialAccessor`.
- `inspect.signature(SpatialAccessor.simplify)` differs from
  `inspect.signature(AsyncSpatialAccessor.simplify)`.
- The phrase "add async parity later" appears in a commit message or TODO comment.

**Phase to address:**

Each Spatial v2 sub-phase. The acceptance criteria for every Spatial v2 phase must include:
"async parity verified (`test_accessor_parity` passes + signature diff is zero)."

---

### Pitfall 12: Scope Bloat in the Final Milestone — The Original v1.0.0 Split Lesson

**What goes wrong:**

The original v1.0.0 milestone was Spatial v2 + audit + performance + API freeze. It was too large
and was split into v0.10.0 (audit + performance) and v1.0.0 (Spatial v2 + API freeze). The
split was correct. The risk is that v1.0.0 now attracts the deferred items from v0.10.0 PLUS
new ideas that arise during implementation, growing back to the original scope.

Specific scope-creep attractors for v1.0.0:
- TSDB-F01..04 follow-ups (deferred to 1.x)
- ETL-INC-F01..05 follow-ups (deferred to 1.x)
- CRUD-F01..03 follow-ups (deferred to 1.x)
- Raster support (explicitly deferred post-1.0)
- "While we're freezing, let's also add X" additions

The "last big milestone" pressure is real: because v1.0.0 is the final planned large milestone,
there is psychological pressure to make it complete by adding deferred items.

**How to avoid:**

1. The scope-lock decision from 2026-06-27 is definitive: "1.0 net + 1.x additifs." Deferred
   items are 1.x, not 1.0. A phase plan that adds any item from the deferred list must be
   rejected at roadmap review, not at implementation time.
2. Create a `1.x-backlog` section in FUTURE-MILESTONES.md at the start of v1.0.0. Every time a
   "while we're here..." idea arises, it goes in the backlog, not the milestone.
3. The v1.0.0 roadmap phase count should be fixed at the milestone start. A phase count that
   grows during execution is a scope creep signal.
4. "Looks small, fits in a phase" is not a sufficient reason to add to v1.0.0. "Is it in the
   locked scope?" is the criterion.

**Warning signs:**

- A REQUIREMENTS.md row appears that was not in the original v1.0.0 scope (Spatial v2, 4 API
  gaps, API freeze).
- The phrase "while we're already in this file..." in a phase plan.
- Phase count grows from the initial roadmap during execution.

**Phase to address:**

Roadmap creation and phase 41 planning. The scope lock must be documented as a hard constraint
in every phase plan's "Out of scope" section.

---

### Pitfall 13: SemVer Commitments Made Without Understanding the Freeze Surface

**What goes wrong:**

v1.0.0 ships with a SemVer policy document that says "no breaking changes in 1.x." After
shipping, a user discovers that `db.spatial.contains(table, "geom", "public", ...)` used
positional arguments for `geom` and `schema`, which are now keyword-only in a patch release.
This is a breaking change the team didn't notice because internal tests always used keyword args.

Or: the `into=` parameter is documented as `str` but the correct type is `Literal["rows",
"gdf"]`. A future mypy-strict upgrade changes the inferred type, breaking user type-checked code.

**Why it happens:**

The SemVer policy is declared before the public surface is fully audited. Methods that have mixed
positional/keyword signatures, or undocumented constraints, become unexpected compatibility traps.
The deprecation policy is declared in the CHANGELOG but not tested.

**How to avoid:**

1. Before declaring the API frozen, run a surface audit: for every public method, document whether
   arguments are positional or keyword-only. Prefer keyword-only (via `*` separator) for any
   parameter that is not the first 1-2 positional arguments. Freeze the keyword-only surface.
2. The MIGRATION guide for v1.0.0 must include a "Stable API Contract" section that explicitly
   lists: (a) which parameters are positional and thus pinned, (b) which return types are part of
   the contract, (c) which exception types are part of the contract.
3. The SemVer policy document must define "breaking change" concretely for pycopg: adding a
   required parameter is breaking; adding an optional parameter with a default is not; changing
   a default value is breaking; changing an exception type is breaking.

**Warning signs:**

- The API reference for v1.0.0 does not mark parameters as positional vs keyword-only.
- `into=` is typed as `str` in signatures that should use `Literal`.
- The SemVer policy says "follow SemVer" without defining what constitutes a breaking change
  for this library.

**Phase to address:**

API freeze phase. The surface audit must happen before the freeze is declared, not after.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| New spatial builder without `validate_identifiers` | Faster to write | SQL injection vulnerability; past v0.10.0 history shows tests stay green | Never — it's a one-line fix |
| `@overload` deferred "until after builders are done" | Builders written faster | Must touch every builder again; mypy strict blocks release | Never — add `@overload` at builder-write time |
| `# type: ignore` to silence mypy strict errors | CI turns green | Latent type error hidden; counts against the "strict" claim | Acceptable only for third-party stub gaps with a comment explaining the gap |
| Freeze the `where=` inconsistency without documenting it | No breaking change | User confusion for the full 1.x lifetime; constant support overhead | Acceptable only if explicitly documented in API reference |
| Skip signature parity tests ("method names match, close enough") | Less test code | Signature divergence locked in at 1.0; sync/async API incompatibility for 1.x lifetime | Never — add signature diff assertions for v2 methods |
| Add raster "since we're in spatial" | Scope feels complete | Raster is a separate, complex feature family; inflates timeline; was already explicitly deferred | Never — explicitly deferred to post-1.0 |
| Defer exception renaming to 1.1 | No breaking change in 1.0 | If renamed in 1.1, users must update again; 1.0 freeze loses meaning | Never — either rename at 1.0 with deprecation or freeze the old names permanently |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| PostGIS ST_AsMVT | Pass raw SRID 4326 geometry, expect valid tile | Always: `ST_Transform(geom, 3857)` → `ST_AsMVTGeom(...)` → `ST_AsMVT(agg.*)` |
| PostGIS binary ops (Difference/Intersection) | Pass geometries from different SRIDs | Validate or document that both operands must share the same SRID; emit `ST_Transform` on user inputs |
| geopandas `into="gdf"` with NULL geometries | Expect clean GeoDataFrame | Document that NULL/empty geometries in the column produce None rows; `simplify` can return NULL |
| `@deprecated_alias` stacklevel | Default `stacklevel=1` points to pycopg internals | Set `stacklevel=2` and verify warning points to caller's file in tests |
| mypy strict + geopandas | `gpd.GeoDataFrame` is untyped; `ignore_missing_imports` needed | Already in `[[tool.mypy.overrides]]`; ensure all geopandas call sites use `Any` where needed |
| psycopg `params: list` vs `list[Any]` | mypy strict rejects untyped `list` | Annotate as `list[Any]` throughout; import `Any` from `typing` |
| ST_TileEnvelope on PostGIS < 3.0 | `UndefinedFunction` error | Guard with `try/except` or check PostGIS version at accessor init |
| DeprecationWarning + `-W error` CI gate | Internal code calling deprecated path turns CI red | Grep for deprecated names in pycopg/ source before shipping; ensure internal call sites use new names |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| New spatial v2 builder missing `validate_identifiers` | SQL injection via `table`, `schema`, or `geom` arguments | First line of every builder must be `validate_identifiers(table, schema, geom)`; injection test required for every builder |
| New builder that accepts a `group_by` or `column_alias` string without validation | SQL injection via aggregate grouping column | Any string interpolated into SQL must pass `validate_identifier` or be emitted as `%s` |
| The `where=` string-fragment path (existing, accepted T-14-04 limitation) | SQL injection in `where=` values | If `where=` string path is extended to new v2 methods, document clearly that it is the caller's responsibility; consider restricting v2 methods to dict-only |

---

## "Looks Done But Isn't" Checklist

- [ ] **Every new `build_*_sql` builder:** `validate_identifiers(table, schema, geom)` is the first
  statement — verify with an injection test asserting `InvalidIdentifier`.
- [ ] **ST_AsMVT method:** SQL contains `ST_Transform(..., 3857)` AND `ST_AsMVTGeom(...)` — verify by
  inspecting the generated SQL string in a unit test.
- [ ] **ST_Simplify:** Uses `ST_SimplifyPreserveTopology` by default — verify with a test on a
  geometry where point spacing < tolerance; no NULL returned.
- [ ] **Every deprecated name:** `stacklevel=2` and warning points to caller frame — verify with a
  test that captures the warning and checks `filename` in `warnings.warn_explicit`.
- [ ] **Every new accessor method:** present on both `SpatialAccessor` and `AsyncSpatialAccessor`
  with identical signatures — verify with `inspect.signature` diff in the parity test.
- [ ] **mypy strict:** `uv run mypy --strict pycopg/` exits 0 — zero errors, not just "fewer errors".
- [ ] **Exception naming decision:** N818 suppression comment updated to "resolved at v1.0.0" —
  either old names kept (frozen) or new names shipped (with deprecation aliases).
- [ ] **API freeze contract:** "Stable API Contract" section exists in the MIGRATION guide listing
  positional vs keyword-only parameters for all public methods.
- [ ] **Coverage ratchet:** `--cov-fail-under=95` still passes after Spatial v2 additions — new
  code must have coverage, not just the existing code.
- [ ] **Async parity:** `test_accessor_parity` passes after every Spatial v2 phase — not just at the
  end of the milestone.

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| `validate_identifiers` missing in shipped builder | HIGH | Hotfix release (1.0.x); announce security advisory; fix all new builders in one commit |
| SRID mismatch not caught until after freeze | MEDIUM | Document behavior in 1.0.1 changelog; add explicit SRID check in next minor (1.1) |
| ST_AsMVT wrong coordinate system shipped | MEDIUM | Behavioral change in 1.0.x with MIGRATION note; the old behavior was silently wrong |
| mypy strict errors stall the milestone | MEDIUM | Temporarily exclude problematic modules with `[[tool.mypy.overrides]]`; fix in dedicated phase |
| Scope bloat detected mid-milestone | LOW | Defer the added items to 1.x immediately; do not "finish just this one" |
| Deprecation warning wrong stacklevel | LOW | Hotfix the stacklevel in next patch; low user impact but confusing |
| Exception renaming breaks user code in 1.0 | MEDIUM | If old names removed without deprecation cycle, add them back as aliases in 1.0.1; apologize in changelog |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-----------------|--------------|
| Missing `validate_identifiers` in new builders | Every Spatial v2 phase (Phase 41+) | Injection test for every new builder; regressions in `test_spatial.py` |
| SRID mismatch in binary ops | Spatial v2 processing phase | Mixed-SRID integration test per binary operation |
| ST_AsMVT wrong coordinate system | Spatial v2 serialization phase | SQL inspection test; MVT decode test |
| ST_Simplify NULL collapse | Spatial v2 processing phase | Degenerate geometry fixture in `test_spatial.py` |
| Aggregate NULL propagation | Spatial v2 aggregates phase | Fixture with NULL geometry rows; behavior documented |
| Deprecation cycle wrong stacklevel | Homogenization phase | `warnings.warn` stacklevel test for each deprecated name |
| `where=` inconsistency not resolved | Homogenization phase (first decision, before builders) | API reference has `where= conventions` section |
| Exception naming deferred | Homogenization phase (first task) | N818 suppression comment updated; no unresolved "reconsider" TODOs |
| mypy strict stalls milestone | Dedicated mypy phase (after Spatial v2, before release) | `uv run mypy --strict pycopg/` exits 0 |
| mypy strict latent type errors | Dedicated mypy phase | Zero `# type: ignore` except for documented stub gaps |
| Sync/async parity drift | Every Spatial v2 phase | `test_accessor_parity` after each phase; `inspect.signature` diff for new methods |
| Scope bloat | Roadmap creation + every phase kickoff | Phase plan "Out of scope" section explicitly lists deferred items |
| SemVer commitment without surface audit | API freeze phase (before declaring freeze) | "Stable API Contract" in MIGRATION guide with positional/keyword inventory |

---

## Sources

- pycopg source: `/home/loc/workspace/pycopg/pycopg/spatial.py` — module docstring security
  invariants (D-05 to D-12); `validate_identifiers` guard pattern; `_check_into`/`_SCALAR_HELPERS`
  pattern; `_to_named_binds` adapter; sync/async accessor class structure
- pycopg source: `/home/loc/workspace/pycopg/pycopg/exceptions.py` — N818 suppression background;
  current exception hierarchy
- pycopg source: `/home/loc/workspace/pycopg/pycopg/utils.py` — `validate_identifiers(*names: str)`
  signature with runtime None-check; pattern for all identifier validation
- pycopg source: `/home/loc/workspace/pycopg/pyproject.toml` — mypy config (non-strict, existing
  overrides); N818 suppression comment ("Reconsider at the v1.0.0 API freeze"); ruff config
- pycopg source: `/home/loc/workspace/pycopg/tests/test_parity.py` — `ACCESSOR_PAIRS` registry;
  `test_accessor_parity` (name-level check); "per-method signature parity is intentionally
  deferred" comment (D-11)
- pycopg MEMORY: v0.10.0 COPY rewrite dropped `validate_identifiers`; caught by code-review gate,
  NOT tests; fixed in 863e894 — direct precedent for Pitfall 1
- pycopg PROJECT.md: v1.0.0 locked scope (2026-06-27); original v1.0.0 split lesson; `where=`
  string-fragment accepted limitation T-14-04; N818 deferred decision
- PostGIS docs: `ST_AsMVT` requires `ST_AsMVTGeom` + `ST_TileEnvelope` + EPSG:3857 transform
- PostGIS docs: `ST_Simplify` vs `ST_SimplifyPreserveTopology` (NULL collapse on degenerate input)
- PostGIS docs: `ST_MakeValid` geometry-type change behavior (POLYGON → MULTIPOLYGON)
- Python docs: `warnings.warn` `stacklevel` parameter semantics
- mypy docs: `--strict` flag enables `disallow_untyped_defs`, `disallow_any_generics`,
  `warn_return_any`, etc. — requires explicit `Any` annotations

---
*Pitfalls research for: pycopg v1.0.0 — Spatial v2 + API freeze*
*Researched: 2026-06-27*
