---
phase: 50-crud-introspection-follow-ups
reviewed: 2026-07-04T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - pycopg/base.py
  - pycopg/database.py
  - pycopg/async_database.py
  - pycopg/queries.py
  - pycopg/schema.py
  - pycopg/__init__.py
  - tests/test_database.py
  - tests/test_async_database.py
  - tests/test_database_integration.py
  - tests/test_parity.py
  - tests/test_sql_injection.py
  - docs/api-reference.md
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 50: Code Review Report

**Reviewed:** 2026-07-04T00:00:00Z
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Reviewed the Phase 50 CRUD + introspection follow-ups: the raw-SQL escape hatch
(`QueryMixin._resolve_predicate`, `where_sql`/`where_params` threaded through
`exists`/`count`/`paginate`/`delete_where`/`update_where`), the pagination family
(`Page` dataclass, `QueryMixin._build_keyset_where`, `paginate_page`/`paginate_keyset`),
materialized-view introspection (`MATERIALIZED_VIEWS`/`MATERIALIZED_VIEW_COLUMNS`,
`materialized_views`/`materialized_view_columns`), and structured `describe(into=...)` +
`TableDescription`.

The security posture of the escape hatch is sound. Verified:

- **Injection containment holds.** `where_sql` is passed verbatim and never validated
  (documented escape hatch, C-02); `where_params` are always bound `%s` and never
  interpolated (proven by `TestWhereSqlValueInjection`). `table`/`schema`/`order_by`/
  `values.keys()`/`order_cols` all still route through `validate_identifiers`. No
  unintended unvalidated identifier reaches SQL.
- **Destructive guards intact.** `delete_where`/`update_where` reject an empty resolved
  predicate (`if not frag`) — no accidental full-table mutation. `where_params`-without-
  `where_sql` (D-04), `where`+`where_sql` conflict (D-02), and whitespace-only `where_sql`
  (D-03) all raise `ValueError` inside `_resolve_predicate`, which runs *before*
  `validate_identifiers` and before any cursor is opened. Guard ordering verified.
- **Descending-keyset fix is complete on both classes.** `_build_keyset_where` flips the
  row-value operator to `<`, and both `Database.paginate_keyset` and
  `AsyncDatabase.paginate_keyset` emit an all-columns `... DESC` ORDER BY that agrees with
  the flipped comparison (Pitfall 3). Sync/async bodies are byte-identical.
- **Sync/async parity holds** across every touched method; `next_cursor` is computed from
  the trimmed page (not the `limit+1` sentinel); `has_next` math is correct at the
  boundary; `with_total` counts the base predicate only (not the keyset `after` fragment).

Two robustness defects and three minor items are below. No blockers.

## Warnings

### WR-01: Empty `order_by` list produces invalid `ORDER BY` SQL

**File:** `pycopg/database.py:1586-1596` (`paginate_page`), `pycopg/database.py` (`paginate_keyset`), and mirror sites in `pycopg/async_database.py` (`paginate_page`, `paginate_keyset`); pre-existing in `paginate`.
**Issue:** The `order_by` handling guards each element (`any(not isinstance(c, str) or not c ...)` → "order_by columns must be non-empty strings") but never rejects an **empty list**. With `order_by=[]`:
- `order_by is not None` is `True`, so the clause branch runs.
- `order_by_cols = []`; the `any(...)` over an empty list is `False` (no rejection).
- `validate_identifiers()` with zero args is a no-op (its loop iterates nothing).
- `cols_str = ", ".join([]) == ""` → `order_clause = " ORDER BY "`.

The emitted SQL becomes `SELECT * FROM public.t ORDER BY  LIMIT 6`, which fails at the
database with a `syntax error at or near "LIMIT"` instead of either a clean `ValueError`
or a no-op ordering. In `paginate_keyset` this is reachable even though `order_by` is
"mandatory" — `order_by=[]` passes the `is None` check. A caller building `order_by`
dynamically (e.g. from an optional sort spec) can hit this with well-typed input.
**Fix:** Reject the empty list explicitly alongside the per-element check:
```python
if order_by is not None:
    order_by_cols = [order_by] if isinstance(order_by, str) else list(order_by)
    if not order_by_cols:
        raise ValueError("order_by must contain at least one column")
    if any(not isinstance(c, str) or not c for c in order_by_cols):
        raise ValueError("order_by columns must be non-empty strings")
    ...
```
Apply to `paginate_page`/`paginate_keyset` in both classes (and, ideally, retrofit
`paginate`).

### WR-02: `limit` cast to `int` for SQL but used raw for Python-side slice/compare

**File:** `pycopg/database.py` (`paginate_page` `has_next`/`rows[:limit]`, `paginate_keyset` same), and mirror sites in `pycopg/async_database.py`.
**Issue:** The SQL side defensively casts (`LIMIT {int(limit) + 1}`), but the Python-side
page-trim logic uses the **raw, un-cast** `limit`:
```python
has_next = len(rows) > limit
rows = rows[:limit]
```
The two sides disagree on type discipline. A non-`int` `limit` that the SQL cast tolerates
will crash the trim: e.g. `limit=5.0` produces valid SQL (`LIMIT 6`, fetches up to 6 rows)
but `rows[:5.0]` raises `TypeError: slice indices must be integers`. The failure surfaces
at the slice — after the query has already run — rather than as an upfront validation
error. This trim path is new in Phase 50 (`paginate` returns `fetchall()` unsliced, so it
was never exposed to this inconsistency).
**Fix:** Normalize once at the top and reuse:
```python
limit = int(limit)
...
has_next = len(rows) > limit
rows = rows[:limit]
```
Apply to both `paginate_page` and `paginate_keyset`, sync and async.

## Info

### IN-01: Keyset pagination silently mis-pages on NULLable `order_by` columns

**File:** `pycopg/base.py:390-434` (`_build_keyset_where`); consumed by `paginate_keyset`.
**Issue:** The row-value comparison `(c1, c2) > (%s, %s)` follows SQL NULL semantics: a row
whose ordered column contains `NULL` (or a `NULL` cursor value in `after`) makes the
comparison evaluate to `NULL`, so the row is excluded from the seek predicate — rows can be
silently skipped or the cursor can stall. The docstrings tell callers to supply a
"unique/total order" but never warn that the columns must also be **NOT NULL** for keyset
correctness. This is a documented limitation of row-value keyset paging, not a code bug, but
the caveat is worth surfacing.
**Fix:** Add a one-line caveat to `paginate_keyset`/`_build_keyset_where` docstrings: keyset
`order_by` columns should be NOT NULL (or callers must guarantee no NULLs), otherwise rows
with NULL keys are skipped.

### IN-02: Degenerate `limit <= 0` yields `has_next=True` with `next_cursor=None`

**File:** `pycopg/database.py` / `pycopg/async_database.py` (`paginate_keyset`).
**Issue:** With `limit=0`, `LIMIT 1` fetches one row, `has_next = len(rows) > 0` can be
`True`, then `rows = rows[:0] == []` and `next_cursor = ... if rows else None == None`. A
consumer following the documented `while page.has_next: ... after=page.next_cursor` pattern
would loop forever passing `after=None` (which restarts from the first page). Degenerate
input, but a `limit <= 0` guard (raise `ValueError`) would make the contract robust.
**Fix:** Validate `if int(limit) <= 0: raise ValueError("limit must be a positive integer")`
in `paginate_page`/`paginate_keyset`.

### IN-03: `api-reference.md` keyset loop example discards the first page

**File:** `docs/api-reference.md` (Pagination v1.1.0 example).
**Issue:** The shown loop fetches the first page, then immediately reassigns `page` at the
top of the `while page.has_next:` body before any rows are consumed — so the first page's
rows are never processed and the example does not illustrate correct cursor consumption.
**Fix:** Restructure to process before advancing, e.g.:
```python
page = db.paginate_keyset("events", 50, order_by=["created_at", "id"])
while True:
    for row in page.rows:
        ...  # process
    if not page.has_next:
        break
    page = db.paginate_keyset(
        "events", 50, order_by=["created_at", "id"], after=page.next_cursor
    )
```

---

_Reviewed: 2026-07-04T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
