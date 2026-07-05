---
phase: 53-crud-symmetry-introspection-follow-ups
fixed_at: 2026-07-05T08:04:11Z
review_path: .planning/phases/53-crud-symmetry-introspection-follow-ups/53-REVIEW.md
iteration: 1
findings_in_scope: 3
fixed: 3
skipped: 0
status: all_fixed
---

# Phase 53: Code Review Fix Report

**Fixed at:** 2026-07-05T08:04:11Z
**Source review:** .planning/phases/53-crud-symmetry-introspection-follow-ups/53-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 3 (WR-01, WR-02, WR-03 — IN-01/IN-02 explicitly out of scope per fix directive)
- Fixed: 3
- Skipped: 0

## Fixed Issues

### WR-01: `insert()` with an empty row dict raises a raw Postgres `SyntaxError` instead of failing cleanly

**Files modified:** `pycopg/database.py`, `pycopg/async_database.py`, `tests/test_database.py`, `tests/test_async_database.py`
**Commit:** `8b2ab3a`
**Applied fix:** Added `if not row: raise ValueError("insert: 'row' must be a non-empty dict.")` at the top of `insert()` in both `Database` and `AsyncDatabase`, before any DB round-trip, matching the `insert_many`/`upsert_many` convention of guarding the empty-input case (those return 0 for empty lists; `insert()`'s singular-row return shape makes raising the clean choice, as the review's Fix suggested). Added a `Raises` docstring entry documenting the new `ValueError`. Added `test_insert_empty_row_raises_before_db_round_trip` to both `TestInsertSingleRow` (sync, mocked) and `TestAsyncInsertSingleRow` (async, mocked).

### WR-02: `select_where`/`find` accept negative `limit`/`offset` and let a raw Postgres error escape

**Files modified:** `pycopg/database.py`, `pycopg/async_database.py`, `tests/test_database.py`, `tests/test_async_database.py`
**Commit:** `f913c71`
**Applied fix:** Added the `IN-02`-style guard to `select_where` in both classes:
```python
if limit is not None:
    limit = int(limit)
    if limit < 0:
        raise ValueError("limit must not be negative")
if offset is not None:
    offset = int(offset)
    if offset < 0:
        raise ValueError("offset must not be negative")
```
placed before `_build_select_sql` is called. `find()` delegates to `select_where`, so it inherits the guard automatically — no separate change needed there. **Deviation from the review's literal Fix text:** the review said to apply the guard "in both select_where/get", but `get()`/`find_one()` do not accept `limit`/`offset` parameters at all — they force a hardcoded server-side `LIMIT 1` by design (D-05, explicitly documented in `get()`'s own docstring: "Does not expose limit/offset — they would be contradictory with the forced LIMIT 1"). Guarding `get()` would require adding new parameters, which is out of scope and contradicts an explicit design decision from this same phase, so only `select_where` (and its `find` delegate) were guarded. The threshold is `< 0` (not paginate's `<= 0`) because `limit=0`/`offset=0` are semantically valid for an optional predicate read (unlike paginate's mandatory-positive-limit contract) — this matches the review's own suggested fix snippet exactly. Added `test_select_where_negative_limit_raises`, `test_select_where_negative_offset_raises`, and `test_find_negative_limit_raises` to both sync and async test classes.

### WR-03: `test_crud_v120_surface` docstring claims KIND-parity coverage that does not exist

**Files modified:** `tests/test_parity.py`
**Commit:** `9085435`
**Applied fix:** Added a new `test_crud_v120_kind_parity` test, mirroring the comparison logic in `test_accessor_parameter_kind_parity` (same `inspect.signature` + per-parameter `.kind` diff approach), but scoped explicitly to the 5 named Phase 53 methods (`select_where`, `find`, `get`, `find_one`, `insert`) on `(Database, AsyncDatabase)` directly, rather than iterating `ACCESSOR_PAIRS`. Corrected `test_crud_v120_surface`'s docstring to stop citing `test_accessor_parameter_kind_parity` (which is `ACCESSOR_PAIRS`-only and does not include `(Database, AsyncDatabase)`) and instead point to the new `test_crud_v120_kind_parity`.

**Note for context:** while reading `tests/test_parity.py` to build this fix, found that `test_database_core_parameter_kind_parity` (added in Phase 41, `92018dd`) *already* generically covers every shared `Database`/`AsyncDatabase` method — including these 5 — via `set(sync_methods) & set(async_methods)`, so the actual regression-detection gap described by WR-03 does not exist today. The review's premise ("no automated protection") is therefore not fully accurate, but its secondary ask — a dedicated, explicitly-named assertion for these 5 methods plus a corrected docstring — was implemented as directed, since it locks the specific Phase 53 surface down independently of the generic test (defense in depth: a future narrowing of the generic test's scope would still be caught).

## Skipped Issues

None — all 3 in-scope findings (WR-01, WR-02, WR-03) were fixed. IN-01 and IN-02 were explicitly out of scope per the fix directive and were not attempted.

---

_Fixed: 2026-07-05T08:04:11Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
