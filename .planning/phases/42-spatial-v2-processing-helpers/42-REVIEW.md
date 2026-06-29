---
phase: 42-spatial-v2-processing-helpers
reviewed: 2026-06-29T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - pycopg/spatial.py
  - tests/test_spatial.py
  - tests/test_parity.py
  - docs/stability.md
  - docs/api-reference.md
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 42: Code Review Report

**Reviewed:** 2026-06-29
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

Phase 42 adds six PostGIS geometry-processing builders to `pycopg/spatial.py` —
three binary (`union`/`difference`/`intersection`) and three unary
(`simplify`/`convex_hull`/`make_valid`) — each exposed as a pure module-level
`build_*_sql` function plus a method on both `SpatialAccessor` and
`AsyncSpatialAccessor`. The implementation is high quality and the security
posture is sound.

The two review focus areas both pass:

- **SQL injection:** Every new builder calls `validate_identifiers` on
  `table`/`schema`/`geom`/`other_geom` (binary helpers via the shared
  `_build_binary_geom_sql`, line 971) and on `columns` entries before any
  f-string interpolation. Every user value is bound via `%s`: `tolerance` and
  `preserve_collapsed` in `build_simplify_sql` (lines 1262-1266), and the
  `make_valid` method/keepcollapsed string in `build_make_valid_sql` (lines
  1422-1432). The `make_valid` params string is assembled from
  programmer-controlled whitelisted literals and bound through `%s` — never
  interpolated. The `method=` value is also whitelisted against
  `_VALID_MAKE_VALID_METHODS` (line 1405). The `op_func`/`result_col` arguments
  of `_build_binary_geom_sql` are hardcoded literals supplied only by the three
  public wrappers, never reachable from user input. No injection vector found.

- **sync/async parity:** All six methods are byte-identical in signature
  between the two accessor classes, verified by introspection (parameter KIND
  *and* defaults match for all six). Method ordering, `into=` routing, geometry
  column names, and the `_check_into`/`build_*`/`_run` call sequence are
  mirrored exactly. `test_spatial_v1_processing_surface` and
  `test_accessor_parameter_kind_parity` lock this in. No KIND-parity divergence
  (the v0.10/Phase 41 failure class) is present.

DB-free test suites pass: `tests/test_spatial.py` (174 passed) and the
DB-free parity tests (22 passed). Builder unit tests, accessor-routing tests,
columns-validation tests, and the gdf named-bind path are all covered for the
six new helpers.

The findings below are all documentation/quality issues; none affect runtime
correctness or security.

## Warnings

### WR-01: api-reference.md spatial table documents the deprecated `where=` for pre-1.0 helpers, contradicting the new `filter=` rows

**File:** `docs/api-reference.md:199-209`
**Issue:** The pre-existing spatial rows (`contains`, `within`, `intersects`,
`dwithin`, `distance`, `nearest`, `area`, `perimeter`, `centroid`, `buffer`,
`transform`) still list `where=` as a key parameter, while the six new Phase 42
rows (lines 210-215) correctly list `filter=`. Per Phase 41 FREEZE-01 the
canonical parameter is `filter=` and `where=` is deprecated (confirmed in the
code: every old method emits a `DeprecationWarning` when `where=` is used, e.g.
`spatial.py:1633`, and `docs/stability.md:37` lists `where=` as deprecated). The
api-reference table — a file modified in this phase — now points users at the
deprecated parameter for 11 of 17 spatial helpers and reads inconsistently
against its own new rows. A reader copying the documented signature will trip a
deprecation warning.
**Fix:** Update the older rows to use `filter=` as the primary parameter (the
authoritative `filter=`/`where=` boundary is already correct in
`docs/stability.md` lines 96-114). For example:
```
| `contains` | `table, geom="geometry", point=, wkt=, geojson=, ref=, srid=4326, into="rows", columns=, filter=, order_by=, limit=` | `list[dict] \| GeoDataFrame` |
```
Optionally note `where=` is a deprecated alias.

### WR-02: api-reference.md new spatial rows omit the `unit=`/geometry-input columns documented for sibling helpers, creating a column-format mismatch

**File:** `docs/api-reference.md:210-215`
**Issue:** The six new rows use a different "Key Parameters" formatting
convention than the existing rows in the same table: they spell out `*`,
`schema="public"`, and `=None` defaults (e.g.
`table, *, geom="geometry", schema="public", other_geom, ...`) whereas every
prior row uses the terse `param=` form without `*`/`schema`/`None`. This is a
cosmetic inconsistency in a reviewed doc file. More substantively, the prose
note above the table (`docs/api-reference.md:195`) states scalar helpers
"`perimeter`, `distance`, `centroid`) only support `into="rows"`" and does not
mention the new geometry-returning helpers — the documentation surrounding the
table was not updated to describe the new processing family at all (no prose
paragraph explains `union`/`difference`/`intersection`/`simplify`/
`convex_hull`/`make_valid`).
**Fix:** Normalize the six new rows to the table's existing terse column format
for visual consistency, and add a short prose paragraph (mirroring
`docs/stability.md` D-04 / D-07 notes) introducing the binary and unary
processing helpers, including the `make_valid(method="structure")` PostGIS ≥ 3.2
caveat.

## Info

### IN-01: `make_valid` invalid-method error message renders Python `None` as the string `'None'`

**File:** `pycopg/spatial.py:1406-1410`
**Issue:** The error built from `_VALID_MAKE_VALID_METHODS` produces
`method must be one of ['linework', 'structure', 'None'], got 'bogus'`. The
`'None'` entry (from `str(None)`) is misleading: it implies the *string*
`"None"` is an accepted value, when the accepted sentinel is the Python
singleton `None` (the default). A user could reasonably pass `method="None"`
and hit the same error.
**Fix:** Render the sentinel distinctly, e.g.
`method must be one of None, 'linework', 'structure'; got 'bogus'`:
```python
raise ValueError(
    "method must be one of None, 'linework', 'structure'; "
    f"got {method!r}"
)
```

### IN-02: New Phase 42 docstrings use correct `InvalidIdentifierError`, but the 11 pre-existing methods in the same file still carry the `InvalidIdentifierErrorError` typo

**File:** `pycopg/spatial.py:1625` (and 21 further occurrences)
**Issue:** The six new methods' docstrings correctly reference
`InvalidIdentifierError` in their Raises sections. The 11 older accessor
methods (sync + async) contain a doubled-suffix typo
`InvalidIdentifierErrorError` (22 occurrences total, all in pre-Phase-42 code).
Since `spatial.py` is a file under review and the new code establishes the
correct spelling, the divergence is now visible side-by-side. Not introduced by
this phase.
**Fix:** Search-and-replace `InvalidIdentifierErrorError` →
`InvalidIdentifierError` across the older docstrings to match the new methods
(no runtime impact — docstrings only).

### IN-03: `tests/test_spatial.py:1016` and siblings assert on bare `Exception` for the mismatched-SRID PostGIS path

**File:** `tests/test_spatial.py:1016`, `1053`, `1090`
**Issue:** `test_union_mixed_srid_raises` / `test_difference_mixed_srid_raises`
/ `test_intersection_mixed_srid_raises` use
`with pytest.raises(Exception):`. A bare `Exception` matcher is broad — it would
also pass if the helper raised an unrelated `InvalidIdentifierError`,
`AttributeError`, or a setup failure inside `_make_mixed_srid_table`, masking a
real regression rather than proving the *native PostGIS SRID-mismatch* error
(D-06) fired. These are DB-integration tests (skipped without PostGIS), so the
risk is contained, but the assertion does not pin the intended failure.
**Fix:** Narrow to the actual driver error class (e.g. `psycopg.errors.Error`
or the project's wrapped DB error) and/or add a `match=` on the SRID-mismatch
message so the test fails loudly if a different exception is raised.

---

_Reviewed: 2026-06-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
