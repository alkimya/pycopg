---
phase: 48-timescaledb-follow-ups
reviewed: 2026-07-03T10:53:27Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - pycopg/timescale.py
  - tests/test_timescale.py
  - tests/test_parity.py
  - docs/timescaledb.md
findings:
  critical: 0
  warning: 1
  info: 2
  total: 3
status: issues_found
---

# Phase 48: Code Review Report

**Reviewed:** 2026-07-03T10:53:27Z
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the Phase 48 (v1.1.0) TimescaleDB follow-up additions to
`pycopg/timescale.py` and the supporting test/doc changes. Scope: the cagg
teardown pair (`drop_continuous_aggregate` / `remove_continuous_aggregate_policy`),
`time_bucket` `origin`/`offset` keyword-only params, per-chunk
`compress_chunk`/`decompress_chunk`, and the `show_chunks` physical-time bounds
(F04).

**Security posture is clean.** Every identifier reaching SQL passes through
`validate_identifiers` (`view_name`, `schema`, `table`, `time_column`), and every
value is a bind parameter, never string-interpolated:
- `origin` → bare typed `%s` (line 281-282)
- `offset` → `%s::interval` (line 284-285)
- `chunk` (compress/decompress) → `%s::regclass` (lines 561, 602, 1919, 1960)
- `older_than`/`newer_than` → `%s::interval` or bare `%s` via
  `_build_chunk_bound_fragments`
- `drop_continuous_aggregate` / `remove_continuous_aggregate_policy` interpolate
  only validated identifiers plus static bool-driven keyword fragments
  (`IF EXISTS`, `CASCADE`, `if_exists => true/false`).

I traced the injection test coverage (`bad; DROP TABLE users; --` cases at
test lines 2194, 2292) and it correctly asserts `InvalidIdentifierError` before
any execute.

**Sync/async parity is intact.** Both accessors mirror each other exactly for
all four features; all async paths correctly `await` `has_extension` and
`execute`; no missing-await. `test_timescale_v110_surface` locks the four new
method names onto both classes, and `test_accessor_parameter_kind_parity`
guards KIND parity.

No BLOCKER-class defects found. One WARNING (a guard-ordering/contract mismatch
on the `origin`/`offset` mutual-exclusion check) and two INFO items.

## Narrative Findings (AI reviewer)

## Warnings

### WR-01: `time_bucket` origin/offset mutual-exclusion fires *after* a DB round-trip, contradicting its documented contract

**File:** `pycopg/timescale.py:271-276` (guard body); reached from
`time_bucket` at `1551-1556` (sync) and `2881-2886` (async)

**Issue:** The `origin`/`offset` mutual-exclusion `ValueError` lives inside
`_build_time_bucket_sql`, which is called *after* the `has_extension("timescaledb")`
check in both `time_bucket` methods:

```python
_check_into(into, "time_bucket")
if not self._db.schema.has_extension("timescaledb"):   # <-- DB round-trip runs FIRST
    raise ExtensionNotAvailableError(...)
sql, params = _build_time_bucket_sql(..., origin=origin, offset=offset)  # <-- ValueError only here
```

`has_extension()` issues a real `pg_extension` query. So the guard does **not**
fire "before any DB round-trip," yet both the method docstring and the builder
docstring explicitly promise exactly that:

- method docstring (line 1531-1533 / 2861-2863): *"raised before any DB
  round-trip (D-07, TSDB-F02)"*
- builder docstring (line 264-267): *"raised before any SQL is built"*

Two observable consequences:
1. Passing both `origin` and `offset` against a database **without** TimescaleDB
   surfaces `ExtensionNotAvailableError` instead of the `ValueError` that
   describes the actual programmer error — the less-helpful message wins.
2. Even on a TimescaleDB build, an always-invalid argument combination costs a
   wasted round-trip before failing.

This also diverges from the established sibling pattern: `add_dimension`
(line 914-952) and `_check_into` both run their pure-Python guards *before*
`has_extension`. The existing test `test_time_bucket_origin_offset_mutual_exclusion`
(test line 2552) only asserts `db.execute`/`db.to_dataframe` were not called — it
does **not** assert `has_extension` was skipped, so it cannot catch this
divergence.

**Fix:** Hoist the mutual-exclusion check into `time_bucket` (both sync and
async) ahead of the extension guard, mirroring `add_dimension`:

```python
_check_into(into, "time_bucket")
if origin is not None and offset is not None:
    raise ValueError(
        "time_bucket: 'origin' and 'offset' are mutually exclusive; "
        "pass one or neither."
    )
if not self._db.schema.has_extension("timescaledb"):
    raise ExtensionNotAvailableError(...)
```

(The builder can keep its own defensive check as well.) Then extend the test to
assert `mock_schema.has_extension.assert_not_called()`.

## Info

### IN-01: `time_bucket` `origin` accepts any type without validation (inconsistent with `refresh_continuous_aggregate`)

**File:** `pycopg/timescale.py:214-293` (builder), `1469-1566` / `2799-2896`
(callers)

**Issue:** `refresh_continuous_aggregate` explicitly validates its window bounds
are `datetime` or `None` (line 1172-1179 / 2509-2516) and raises a friendly
`ValueError` for anything else. `time_bucket`'s `origin` has no such guard — a
stray `str`/`date`/`int` is bound as a bare `%s` and deferred to the DB, which
returns a lower-level type error. This is **not** a security issue (the value is
a bind parameter), only an ergonomics inconsistency between two sibling methods.

**Fix:** Optionally add a symmetric guard:
`if origin is not None and not isinstance(origin, datetime): raise ValueError(...)`.
Left as INFO because "DB is the authority" is a documented posture elsewhere in
this module (D-09).

### IN-02: docs example passes `chunk_interval=100` (int) but the parameter is typed `str | None`

**File:** `docs/timescaledb.md:410-415`

**Issue:** The `add_dimension` range example passes `chunk_interval=100` (an
int), but `add_dimension` types `chunk_interval` as `str | None` and processes
it via `validate_interval(chunk_interval)` + `INTERVAL '{chunk_interval}'`. An
int argument would not match the documented contract and would misbehave at
`validate_interval` / interval interpolation. Pre-existing (introduced in Phase
33 `docs(33-02)`, not a Phase 48 change) but it sits in a file touched by this
phase, so noting it while here.

**Fix:** Use a valid interval string, e.g. `chunk_interval="7 days"`, matching
the surrounding examples.

---

_Reviewed: 2026-07-03T10:53:27Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
