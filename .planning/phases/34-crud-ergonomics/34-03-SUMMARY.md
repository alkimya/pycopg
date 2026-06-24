---
phase: 34-crud-ergonomics
plan: "03"
subsystem: core
tags: [crud, exists, count, paginate, fetch_all, sql-safety, sync-async-parity]
dependency_graph:
  requires: [_build_where_dict on QueryMixin (34-01), upsert/delete_where/update_where (34-02)]
  provides: [exists on Database, count on Database, paginate on Database, fetch_all on Database, exists on AsyncDatabase, count on AsyncDatabase, paginate on AsyncDatabase, fetch_all on AsyncDatabase]
  affects: [pycopg/database.py, pycopg/async_database.py, tests/test_database_integration.py, tests/test_async_database.py]
tech_stack:
  added: []
  patterns: [SELECT-EXISTS-no-materialize, SELECT-COUNT-star, validate-identifiers-order_by, whole-clause-DESC, int-cast-limit-offset, dict_row-by-default, tdd-red-green]
key_files:
  created: []
  modified:
    - pycopg/database.py
    - pycopg/async_database.py
    - tests/test_database_integration.py
    - tests/test_async_database.py
decisions:
  - "exists/count placed after update_where in database.py; fetch_all/paginate placed after fetch_val — logical proximity to sibling methods"
  - "exists ValueError guard fires BEFORE validate_identifiers and BEFORE any cursor — empty dict is rejected at the front door"
  - "count None-where arm routes around _build_where_dict completely — never calls builder with {}"
  - "paginate order_by: str normalized to list before validate_identifiers — single-column API matches multi-column"
  - "paginate whole-clause descending via DESC suffix — per-column direction deferred (CRUD-F02)"
  - "fetch_all docstring contains 'dict_row' token (CRUD-07 part a deliverable) on both sync and async"
  - "async paginate/fetch_all use native async with/await fetchall — no to_thread pattern"
metrics:
  duration: "8m"
  completed: "2026-06-24T16:02:35Z"
  tasks_completed: 3
  tasks_total: 3
  files_modified: 4
---

# Phase 34 Plan 03: Read Helpers (exists/count/paginate/fetch_all) Summary

**One-liner:** Added `exists` (SELECT EXISTS), `count` (SELECT COUNT(*)), `paginate` (validated order_by + whole-clause DESC + int-cast limit/offset + optional dict-WHERE), and `fetch_all` (list[dict] twin to fetch_one, dict_row documented) to both `Database` and `AsyncDatabase` with full sync/async parity.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| RED | Failing tests for exists/count/paginate/fetch_all (sync + async) | 961264e | tests/test_database_integration.py, tests/test_async_database.py |
| GREEN (T1+T2) | Implement all four methods on both classes | 9b71aa6 | pycopg/database.py, pycopg/async_database.py |

## What Was Built

### `exists(table, where: dict, schema="public") -> bool` (CRUD-04)

On both `Database` and `AsyncDatabase`:

1. **ValueError guard FIRST** (before validate_identifiers, before cursor): `if not where: raise ValueError(...)` — empty dict is meaningless and never reaches the builder or DB.
2. `validate_identifiers(table, schema)` — T-34-06 mitigation.
3. `_build_where_dict(where)` → `(fragment, params)` — reuses 34-01 builder.
4. SQL: `SELECT EXISTS(SELECT 1 FROM {schema}.{table} WHERE {fragment})` — never materializes rows.
5. Delegates to `self.fetch_val(sql, params)` (sync) / `await self.fetch_val(sql, params)` (async); coerces `bool(...)`.

### `count(table, where=None, schema="public") -> int` (CRUD-05)

On both classes:

1. `validate_identifiers(table, schema)` first.
2. **Routing guard:** when `where is None`, emits `SELECT COUNT(*) FROM {schema}.{table}` with empty params — NEVER calls `_build_where_dict({})`. When `where` is a non-empty dict, calls `_build_where_dict(where)` and appends `WHERE {fragment}`.
3. Delegates to `fetch_val`; coerces `int(...)`.

### `paginate(table, limit, offset=0, order_by=None, where=None, descending=False, schema="public") -> list[dict]` (CRUD-06)

On both classes:

1. `validate_identifiers(table, schema)` first.
2. Optional `where` dict: `_build_where_dict(where)` → `WHERE {fragment}` with bound params.
3. Optional `order_by`: normalizes `str` to `list`; calls `validate_identifiers(*order_by_cols)` — T-34-06 mitigation for order_by columns; builds `ORDER BY {cols} [DESC]`.
4. `LIMIT {int(limit)} OFFSET {int(offset)}` — int-cast as `base.py:203-206`.
5. Fetch: `with self.cursor() as cur: cur.execute(sql, params); return cur.fetchall() if cur.description else []` (sync) / `async with self.cursor()` + `await cur.fetchall()` (async).

### `fetch_all(sql, params=None) -> list[dict]` (CRUD-07)

On both classes:

- Thin `list[dict]` complement to `fetch_one` — opens cursor, executes, returns `cur.fetchall() if cur.description else []`.
- **CRUD-07 (a) docstring deliverable:** both sync and async `fetch_all` docstrings contain the token `dict_row`, documenting dicts-by-default behavior. Verified: `python -c "from pycopg.database import Database; assert 'dict_row' in (Database.fetch_all.__doc__ or '')"` exits 0.
- No `into=` toggle, no tuples path.

### Tests Added

**`tests/test_database_integration.py` — `TestDatabaseReadHelpers`:**
- `test_exists_true_and_false` — exists returns True for seeded row, False for absent predicate.
- `test_exists_empty_where_raises` — `pytest.raises(ValueError)` with `{}`.
- `test_count_all_and_filtered` — `count()` == 3; `count(where={"active": True})` == 2.
- `test_paginate_orders_and_slices` — 3 rows seeded; page1 has 2, page2 has 1; descending reverses order.
- `test_paginate_where_filters` — `where={"active": True}` narrows to 2 of 3 rows.
- `test_paginate_invalid_order_by_raises` — `pytest.raises(InvalidIdentifier)` for `"bad;col"`.
- `test_fetch_all_returns_dicts` — returns `list[dict]`; empty-result query returns `[]`.

**`tests/test_async_database.py` — `TestAsyncDatabaseReadHelpers`:**
- `test_exists_async` — True for present row, False for absent.
- `test_exists_empty_where_raises_async` — `pytest.raises(ValueError)` with `{}`.
- `test_count_async` — total count and filtered count.
- `test_paginate_async` — 2-row page1 and 1-row page2.
- `test_fetch_all_async` — `list[dict]` and `[]` for empty result.

## Verification

```
uv run ruff check pycopg/database.py pycopg/async_database.py  → All checks passed (clean)
PGDATABASE=pycopg_test2 uv run pytest tests/test_parity.py -o addopts="" -q  → 25 passed
PGDATABASE=pycopg_test2 uv run pytest tests/test_database_integration.py \
  tests/test_async_database.py -k "exists or count or paginate or fetch_all" \
  -o addopts="" -q  → 33 passed
```

Manual checks:
- `SELECT EXISTS(SELECT 1 FROM` present in both `database.py:823` and `async_database.py:802`.
- `SELECT COUNT(*) FROM` present in both files.
- `raise ValueError` in `exists` body before `validate_identifiers` on both classes.
- `order_by` columns pass through `validate_identifiers` before interpolation.
- `int(limit)` / `int(offset)` cast in paginate SQL.
- No `into=` param anywhere in the new code.
- `'dict_row' in Database.fetch_all.__doc__` and `'dict_row' in AsyncDatabase.fetch_all.__doc__` verified True.

## Deviations from Plan

None — plan executed exactly as written.

## TDD Gate Compliance

- RED gate commit (test): 961264e — failing tests for all four methods on sync + async.
- GREEN gate commit (feat): 9b71aa6 — implementation of all four methods on both classes.
- No REFACTOR commit needed (code already clean; ruff passes).

## Threat Model Coverage

| Threat | Mitigation | Status |
|--------|------------|--------|
| T-34-06 Identifier injection via table/schema/where keys/order_by | `validate_identifiers` on table, schema, where keys (via `_build_where_dict`), order_by columns | Implemented + tested |
| T-34-07 Value injection via where values / limit / offset | where values bound as `%s`; limit/offset `int()`-cast | Implemented + tested |
| T-34-08 Raw SQL injection via fetch_all(sql) | Accept — caller-owned SQL, same trust model as execute/fetch_one | Accepted (no new surface) |
| T-34-SC No new runtime dependencies | No installs in this plan | Confirmed |

## Known Stubs

None — all methods build real SQL and execute against the live DB.

## Threat Flags

None — no new network endpoints, auth paths, or schema changes. Methods operate on existing tables in the calling context.

## Self-Check: PASSED

- [x] `pycopg/database.py` contains `def exists(`, `def count(`, `def paginate(`, `def fetch_all(`
- [x] `pycopg/async_database.py` contains `async def exists(`, `async def count(`, `async def paginate(`, `async def fetch_all(`
- [x] `SELECT EXISTS(SELECT 1 FROM` at `database.py:823` and `async_database.py:802`
- [x] `raise ValueError` before any SQL in `exists` on both classes (guard fires pre-cursor)
- [x] `count` None-where arm routes around `_build_where_dict` (no malformed WHERE)
- [x] `order_by` columns pass through `validate_identifiers` in paginate on both classes
- [x] `int(limit)` / `int(offset)` cast in paginate SQL
- [x] No `into=` param in any new code
- [x] `dict_row` token in `fetch_all.__doc__` on both classes (CRUD-07 deliverable)
- [x] Commit 961264e exists (RED tests)
- [x] Commit 9b71aa6 exists (GREEN implementation)
- [x] 33 targeted live-DB tests pass; 25 parity tests pass; ruff clean
