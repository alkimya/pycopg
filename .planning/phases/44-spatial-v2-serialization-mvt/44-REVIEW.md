---
phase: 44-spatial-v2-serialization-mvt
reviewed: 2026-06-30T00:00:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - pycopg/spatial.py
  - tests/test_spatial.py
  - tests/test_parity.py
  - docs/api-reference.md
  - docs/spatial.md
  - docs/stability.md
  - README.md
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: issues_found
---

# Phase 44: Code Review Report

**Reviewed:** 2026-06-30
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Phase 44 adds the spatial-v2 serialization surface to `pycopg/spatial.py`:
three pure builders (`build_geojson_sql`, `build_text_sql`, `build_mvt_sql`)
and their accessor methods (`as_geojson`, `as_text`, `as_mvt`) plus the
`_run_mvt`/`_arun_mvt` bytea runners, mirrored on both `SpatialAccessor` and
`AsyncSpatialAccessor`.

The work is high quality against this codebase's security-critical
SQL-builder conventions:

- **SQL injection.** All three new builders call `validate_identifiers(...)`
  on line 1 for `table`/`schema`/`geom`, plus `validate_identifiers(*columns)`
  and `validate_identifiers(feature_id_column)` for MVT. The MVT
  `feature_id_column` is wrapped in single quotes as a SQL literal but only
  after identifier validation (quotes/semicolons are rejected), so injection
  is blocked. User values (`max_decimal_digits`, `options`, `layer_name`,
  `extent`) are emitted as `%s` binds; tile coords / `extent` / `srid` are
  `int()`-coerced before literal interpolation. DB-free injection tests assert
  each guard (`test_invalid_*_raises`). No identifier reaches SQL unguarded.
- **Sync/async parity.** The three new method signatures are byte-identical
  between sync and async, including the kw-only `*` boundary and the absence
  of `where=`/`into=` on `as_mvt`. Verified structurally by the passing
  `test_accessor_parameter_kind_parity` and `test_spatial_serialization_surface`.
- **Bytea contract.** `_run_mvt`/`_arun_mvt` correctly map `None` → `b""`,
  coerce `memoryview` → `bytes()`, and pass `b""`/`bytes` through; the `rows[0]`
  access is safe because `ST_AsMVT` is an aggregate without GROUP BY (always
  exactly one row). Both unit (mocked) and live integration tests cover the
  empty-tile and feature-count paths on both sync and async.

DB-free MVT, routing, and parity tests pass locally (34 passed). The findings
below are minor: one server-version compatibility gap and one duplicated
boilerplate observation, plus two info items.

## Warnings

### WR-01: `as_text(max_decimal_digits=...)` emits a two-arg `ST_AsText` that requires PostGIS 3.1, but the documented hard floor is PostGIS 3.0

**File:** `pycopg/spatial.py:918-919` (`build_text_sql`); docs `docs/stability.md:260` / `docs/spatial.md:333`
**Issue:** When `max_decimal_digits` is set, the builder emits
`ST_AsText(t.{geom}, %s)`. The two-argument form `ST_AsText(geometry, integer)`
was introduced in **PostGIS 3.1**, not 3.0. `docs/stability.md` declares
"PostGIS 3.0 (hard floor)" and the new `as_mvt` note reiterates a 3.0 floor.
On a PostGIS 3.0 server a caller passing `max_decimal_digits=` to `as_text`
gets a native `function st_astext(geometry, integer) does not exist` error,
which is neither documented nor mentioned in the `Raises` section. The default
path (`max_decimal_digits=None`, one-arg `ST_AsText`) is unaffected.
**Fix:** Document the version requirement the same way `make_valid
method="structure"` (3.2) and `as_mvt` (3.0) are documented — a one-line note
on `as_text` / its stability row, e.g.:
```text
**Note on `as_text` precision:** passing `max_decimal_digits=` uses the
two-arg `ST_AsText(geom, ndigits)` form, which requires PostGIS ≥ 3.1.
The default (`None`, full precision) works on all PostGIS 3.0+ servers.
```
(Documentation-only fix is sufficient; the D-04 "native-error passthrough"
convention already used for `make_valid` applies here.)

### WR-02: `where=`/`filter=` reconciliation block is copy-pasted ~18× across accessor methods

**File:** `pycopg/spatial.py` (e.g. `2298-2309`, `2383-2394`, `2472-2483`, and every other non-born-clean method, sync and async)
**Issue:** The identical 11-line `if where is not None: ... filter = where`
deprecation block is duplicated in every legacy accessor method on both
classes. Phase 44 correctly did **not** propagate it to the born-clean
`as_geojson`/`as_text`/`as_mvt` (good — these are 1.0-clean), so this is not a
phase-44 regression, but the new methods sit directly amongst the duplicated
blocks and the duplication is now large enough to be a maintenance liability:
a fix to the deprecation message or `stacklevel` must be applied in ~18 places,
and divergence would not be caught by the name/kind parity tests.
**Fix:** Extract a single helper and call it at the top of each legacy method:
```python
def _reconcile_filter(filter: str | None, where: str | None) -> str | None:
    if where is None:
        return filter
    if filter is not None:
        raise TypeError("Cannot specify both 'filter' and 'where'; use 'filter=' only.")
    warnings.warn(
        "The 'where' keyword argument is deprecated and will be removed in "
        "pycopg 2.0. Use 'filter=' instead.",
        DeprecationWarning, stacklevel=3,
    )
    return where
# in each method:  filter = _reconcile_filter(filter, where)
```
(Note the `stacklevel` bump to 3 to keep the warning pointing at the caller
through the extra frame.) Non-blocking; deferring to the P47 release cleanup
alongside the existing `where=`-docs carry-forward is acceptable.

## Info

### IN-01: `as_mvt` empty-tile contract depends on an undocumented PostGIS behavior (`ST_AsMVT` over zero rows → `b""`)

**File:** `pycopg/spatial.py:1085` / `2228-2232` / `4263-4267`
**Issue:** The `b""` empty-tile result relies on `ST_AsMVT` returning an empty
(zero-length) bytea — not `NULL` and not zero rows — when the inner
`WHERE q.geom_mvt IS NOT NULL` subquery yields no rows. The runners defensively
handle both `None` and `b""`, and the live `test_as_mvt_empty_tile_returns_empty_bytes`
test exercises the real path, so this is well-covered. Flagged only so the
reliance is recorded: if a future PostGIS release changed the zero-row
aggregate result, only the live test (not the mocked unit tests) would catch it.
**Fix:** None required — coverage is adequate. Optionally add a one-line code
comment at the `ST_AsMVT` assembly noting the zero-row → `b""` dependency.

### IN-02: Pre-existing `InvalidIdentifierErrorError` double-suffix docstring typos remain (not introduced by Phase 44)

**File:** `pycopg/spatial.py` (22 occurrences in older accessor docstrings, e.g. `2295`, `2380`, `2469`)
**Issue:** 22 docstring `Raises` entries read `InvalidIdentifierErrorError`
(double "Error"), a known P41-rename artifact already tracked in project
memory (IN-02 carry-forward). The diff confirms Phase 44 introduced **zero**
new occurrences — the new `as_geojson`/`as_text`/`as_mvt` docstrings correctly
use `InvalidIdentifierError`. Recorded for completeness; out of scope for this
phase's changes.
**Fix:** Bulk `sed` rename at the P47 release docs pass (already on the
carry-forward list).

---

_Reviewed: 2026-06-30_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
