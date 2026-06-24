---
phase: 34-crud-ergonomics
reviewed: 2026-06-24T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - pycopg/base.py
  - pycopg/database.py
  - pycopg/async_database.py
  - tests/conftest.py
  - tests/test_base.py
  - tests/test_database_integration.py
  - tests/test_async_database.py
findings:
  critical: 0
  warning: 2
  info: 4
  total: 6
status: resolved
resolution: "WR-01, WR-02, IN-01, IN-02 fixed in 607b7e3 (+ 2 guard tests). IN-03, IN-04 deferred (cosmetic)."
---

# Phase 34: Code Review Report

**Reviewed:** 2026-06-24
**Depth:** standard
**Files Reviewed:** 5 source + 3 test files (phase-34 additions only)
**Status:** issues_found

## Summary

Reviewed the new CRUD ergonomics surface added in Phase 34: the pure
`_build_where_dict` builder on `QueryMixin` (base.py) and the eight new public
methods `upsert`, `delete_where`, `update_where`, `exists`, `count`, `paginate`,
`fetch_all` on both `Database` (database.py) and `AsyncDatabase`
(async_database.py), plus the `PGDATABASE` conftest override.

**SQL-injection posture is solid.** Every identifier path is covered:
`_build_where_dict` validates `where` keys first; `delete_where`/`update_where`/
`exists`/`count`/`paginate` validate `table`/`schema` (and `paginate` validates
each `order_by` column); `upsert` validates `conflict_columns`/`update_columns`
and routes `table`/`schema`/`columns` through `_build_insert_sql`'s
`validate_identifiers`. Every user VALUE binds as `%s` — no value is ever
string-formatted into SQL. `limit`/`offset` are `int()`-cast. The empty-where
destructive guard (D-04) is correctly positioned BEFORE any cursor open or SQL
build in all three of `delete_where`/`update_where`/`exists`, and
`count`/`paginate` route around `_build_where_dict` on the `where is None`/falsy
branch, so a malformed `WHERE ` is genuinely unreachable. Sync/async parity is
faithful: the async twins use native `async with` / `await execute` /
`await fetchone`/`await fetchall` with no sync-blocking calls.

The findings below are one correctness edge case in `upsert` (malformed SQL on a
conflict-only row), one parity robustness gap, and minor quality/doc nits. No
Critical (security/data-loss) issues found.

## Warnings

### WR-01: `upsert` builds malformed `DO UPDATE SET ` (empty SET) when the row contains only conflict columns

**File:** `pycopg/database.py:666-678`, `pycopg/async_database.py:1245-1257`
**Issue:** When `update_columns` is omitted and every key in `row` is also a
conflict column, the defaulting line
`update_columns = [c for c in columns if c not in conflict_columns]` yields `[]`,
so `update_str = ""` and the composed SQL becomes
`INSERT INTO ... ON CONFLICT (id) DO UPDATE SET  RETURNING *` — a syntax error.
Reasonable call: `db.upsert("t", {"id": 1}, ["id"])`. There is no guard, so this
crashes at execute time with a Postgres `SyntaxError` rather than a clear
application error. (The same latent shape exists in the pre-existing
`upsert_many` at database.py:633-643, but `upsert` is a NEW method this phase and
inherits the defect into the new surface.)
**Fix:** Guard the empty-update case before composing SQL, e.g.:
```python
columns = list(row.keys())
if update_columns is None:
    update_columns = [c for c in columns if c not in conflict_columns]
if not update_columns:
    raise ValueError(
        "upsert: no non-conflict columns to update. Provide update_columns "
        "explicitly, or include a non-conflict column in `row`, or use "
        "ON CONFLICT DO NOTHING semantics."
    )
```
Apply identically in both the sync and async `upsert`.

### WR-02: `paginate` order_by accepts `None` elements / non-string columns, producing a `TypeError` mid-join instead of a clear error

**File:** `pycopg/database.py:1156-1164`, `pycopg/async_database.py:887-895`
**Issue:** `validate_identifiers` skips `None` (utils.py:120-122). If a caller
passes `order_by=[None, "id"]` (or a non-string), the `None` slips past
validation, then `", ".join(order_by_cols)` raises an opaque
`TypeError: sequence item 0: expected str instance, NoneType found`. A `None`
column is never a valid sort key, so this should be rejected explicitly. Not an
injection (the value never reaches SQL as an identifier), but a poor failure mode
on a plausible mistake.
**Fix:** After normalizing to a list, reject empty/None entries before
validation:
```python
order_by_cols = [order_by] if isinstance(order_by, str) else list(order_by)
if any(not isinstance(c, str) or not c for c in order_by_cols):
    raise ValueError("order_by columns must be non-empty strings")
validate_identifiers(*order_by_cols)
```

## Info

### IN-01: `delete_where`/`update_where` error messages reference a bare `truncate_table` that is not a top-level method

**File:** `pycopg/database.py:727,762`, `pycopg/async_database.py:1306,1341`
**Issue:** The guard messages say "use truncate_table" / "use execute with an
explicit SQL statement", but `truncate_table` lives on the `db.schema.*` accessor
(schema.py:384 / 1072), not on `Database`/`AsyncDatabase`. A user copy-pasting
`db.truncate_table(...)` would hit `AttributeError`.
**Fix:** Reference the correct path, e.g. "use `db.schema.truncate_table(...)` to
affect all rows."

### IN-02: `update_where` docstring for `values` says "use truncate_table to affect all rows" — wrong clause copied

**File:** `pycopg/database.py:752-756`, `pycopg/async_database.py:1331-1335`
**Issue:** The `where` parameter docstring in `update_where` reads "Must be
non-empty — use truncate_table to affect all rows," copied from `delete_where`.
For an UPDATE, truncating is not the affect-all escape (the code's own ValueError
message correctly says "use execute with an explicit SQL statement"). The
docstring and the runtime message disagree.
**Fix:** Align the `where` docstring in `update_where` with its actual guard
message ("use `execute` with an explicit UPDATE statement to affect all rows").

### IN-03: Async `upsert` docstring omits the `Raises`/`InvalidIdentifier` section present on the read helpers

**File:** `pycopg/async_database.py:1226-1244` (and sync `database.py:647-665`)
**Issue:** `upsert` can raise `InvalidIdentifier` (via `_build_insert_sql` and the
`validate_identifiers` calls) but its docstring has no `Raises` section, unlike
`exists`/`count`/`paginate`. Minor numpydoc inconsistency across the new surface.
**Fix:** Add a `Raises\n------\nInvalidIdentifier` stanza to both sync and async
`upsert` docstrings for parity with the other new methods.

### IN-04: Duplicated `import uuid` and ad-hoc table-name helpers inside async CRUD test classes

**File:** `tests/test_async_database.py` (TestAsyncDatabaseCRUDErgonomics,
TestAsyncDatabaseReadHelpers)
**Issue:** `import uuid` is repeated inside several test methods and `_t()`
helpers are redefined per class; the async tests also do manual
`CREATE`/`DROP TABLE` in `try/finally` rather than using a shared fixture. Not a
correctness problem (tests are self-cleaning), but it duplicates table-lifecycle
logic the sync suite already centralizes via `temp_table_name`/`cleanup_table`.
**Fix:** Hoist `import uuid` to module top and consider a shared async
table-name/cleanup fixture. Low priority — test-only.

---

_Reviewed: 2026-06-24_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
