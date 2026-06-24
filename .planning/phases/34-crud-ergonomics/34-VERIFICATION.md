---
phase: 34-crud-ergonomics
verified: 2026-06-24T00:00:00Z
status: passed
score: 13/13
overrides_applied: 0
re_verification: null
---

# Phase 34: CRUD Ergonomics — Verification Report

**Phase Goal:** Users can call ergonomic single-row and predicate-driven CRUD helpers on `Database` and `AsyncDatabase` next to their existing batch analogs, with full sync/async parity
**Verified:** 2026-06-24
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `_build_where_dict` pure builder exists on `QueryMixin`, validates keys first, returns `(fragment, params)` | VERIFIED | `base.py:210-237` — `@staticmethod`, `validate_identifiers(*where.keys())` first, `" AND ".join(f"{col} = %s" ...)`, returns `(fragment, params)` |
| 2 | Column keys in where dict are validated via `validate_identifiers` before any interpolation | VERIFIED | `base.py:234` — `validate_identifiers(*where.keys())` is first line of builder body |
| 3 | Builder is pure (no DB access), callable as `QueryMixin._build_where_dict({"id":1,"k":"v"}) == ('id = %s AND k = %s', [1, 'v'])` | VERIFIED | Manual check passed: `python -c "... assert QueryMixin._build_where_dict(...) == ..."` output `OK` |
| 4 | `db.upsert(table, row, conflict_columns)` inserts-or-updates and returns affected row dict via `RETURNING *` | VERIFIED | `database.py:647-700` — builds ON CONFLICT DO UPDATE SET, appends `RETURNING *`, returns `cur.fetchone()`; `async_database.py:1228-1281` identical async twin |
| 5 | `upsert` raises `ValueError` when conflict-only row yields empty update set | VERIFIED | `database.py:680-685`, `async_database.py:1261-1266` — guard `if not update_columns: raise ValueError(...)` before any SQL composition |
| 6 | `db.delete_where(table, where={...})` returns rowcount int; raises `ValueError` on empty where before any DB round-trip | VERIFIED | `database.py:702-740` — `if not where: raise ValueError(...)` at line 730, before `validate_identifiers` and cursor; returns `cur.rowcount` |
| 7 | `db.update_where(table, values={...}, where={...})` returns rowcount int; raises `ValueError` on empty where/values before any DB round-trip | VERIFIED | `database.py:742-790` — guards at lines 775-780 before any cursor; returns `cur.rowcount`; async twin identical |
| 8 | `db.exists(table, where={...})` returns bool via `SELECT EXISTS`; raises `ValueError` on empty where | VERIFIED | `database.py:792-831` — guard at line 823, SQL `SELECT EXISTS(SELECT 1 FROM ...)` at line 830; `async_database.py:764-803` identical |
| 9 | `db.count(table, where=None)` returns int via `SELECT COUNT(*)`; `where=None` routes around `_build_where_dict` | VERIFIED | `database.py:833-868` — `if where:` branches at line 862; `else:` emits `SELECT COUNT(*) FROM {schema}.{table}` with no WHERE and empty params; `async_database.py:805-840` identical |
| 10 | `db.paginate(table, limit, offset, order_by, where, descending)` returns `list[dict]`; order_by columns validated; None/non-string order_by elements raise `ValueError`; limit/offset int-cast | VERIFIED | `database.py:1114-1191` — `validate_identifiers(*order_by_cols)` at line 1176; guard `if any(not isinstance(c, str) or not c ...)` at line 1174; `LIMIT {int(limit)} OFFSET {int(offset)}` at line 1185; `async_database.py:842-919` identical |
| 11 | `db.fetch_all(sql, params)` returns `list[dict]`; `fetch_all` docstring contains literal token `dict_row` (CRUD-07) | VERIFIED | `database.py:1077-1112` — docstring at line 1081 contains `dict_row`; `async_database.py:727-762` — docstring at line 731 contains `dict_row`; assertions both passed |
| 12 | Every new method exists identically (same param names) on `AsyncDatabase` using native async | VERIFIED | `python` signature comparison for all 8 methods — all 8 param lists match exactly; CRUD-08 test `test_all_database_public_methods_exist_in_async` + `test_method_signatures_match` pass |
| 13 | `tests/test_parity.py` enumerates and passes for all sync/async pairs including the 8 new methods | VERIFIED | `PGDATABASE=pycopg_test2 uv run pytest tests/test_parity.py` — 25/25 passed |

**Score:** 13/13 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/base.py` | `_build_where_dict` pure staticmethod on `QueryMixin` | VERIFIED | Lines 210-237; `@staticmethod`, validates keys, returns `(fragment, params)` |
| `tests/test_base.py` | Unit tests for `_build_where_dict` | VERIFIED | `test_build_where_dict_basic` (line 193), `test_build_where_dict_multi_key` (line 200), `test_build_where_dict_validates_identifiers` (line 208) — 65/65 tests pass |
| `pycopg/database.py` | sync `upsert`, `delete_where`, `update_where`, `exists`, `count`, `paginate`, `fetch_all` | VERIFIED | All 7 methods confirmed at lines 647, 702, 742, 792, 833, 1077, 1114 |
| `pycopg/async_database.py` | async twins of all 7 + `upsert` | VERIFIED | All 8 confirmed at lines 727, 764, 805, 842, 1228, 1283, 1323 |
| `tests/test_database_integration.py` | live-DB sync tests for all new methods | VERIFIED | 12 test functions confirmed; 24 tests pass under `-k "upsert or delete_where or update_where or exists or count or paginate or fetch_all"` |
| `tests/test_async_database.py` | live-DB async tests for async twins | VERIFIED | 8 test functions confirmed; 20 tests pass under same filter |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `base.py:_build_where_dict` | `utils.py:validate_identifiers` | `validate_identifiers(*where.keys())` | WIRED | `base.py:234` — call confirmed |
| `database.py:delete_where` | `base.py:_build_where_dict` | build validated WHERE fragment | WIRED | `database.py:736` — `self._build_where_dict(where)` |
| `database.py:update_where` | `base.py:_build_where_dict` | build validated WHERE fragment | WIRED | `database.py:785` — `self._build_where_dict(where)` |
| `database.py:exists` | `base.py:_build_where_dict` | build validated WHERE fragment | WIRED | `database.py:829` — `self._build_where_dict(where)` |
| `database.py:count` | `base.py:_build_where_dict` | build WHERE when `where` given | WIRED | `database.py:863` — conditional call; `where=None` routes around |
| `database.py:paginate` | `base.py:_build_where_dict` | optional dict-WHERE | WIRED | `database.py:1164` — conditional call |
| `database.py:upsert` | `cur.fetchone (RETURNING *)` | single-row RETURNING * → dict or None | WIRED | `database.py:695,700` — sql ends with `RETURNING *`; `return cur.fetchone()` |
| `async_database.py:delete_where` | `base.py:_build_where_dict` | build validated WHERE fragment | WIRED | `async_database.py:1317` |
| `async_database.py:update_where` | `base.py:_build_where_dict` | build validated WHERE fragment | WIRED | `async_database.py:1366` |
| `async_database.py:exists` | `base.py:_build_where_dict` | build validated WHERE fragment | WIRED | `async_database.py:801` |
| `async_database.py:count` | `base.py:_build_where_dict` | conditional WHERE | WIRED | `async_database.py:835` |
| `async_database.py:paginate` | `ORDER BY / LIMIT / OFFSET` | validated order_by + int-cast | WIRED | `async_database.py:904,913` — `validate_identifiers`, `int(limit)`, `int(offset)` |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `_build_where_dict` returns correct fragment and params | `python -c "from pycopg.base import QueryMixin; assert QueryMixin._build_where_dict({'id':1,'k':'v'}) == ('id = %s AND k = %s', [1, 'v'])"` | exit 0 | PASS |
| `Database.fetch_all` docstring contains `dict_row` | `python -c "from pycopg.database import Database; assert 'dict_row' in (Database.fetch_all.__doc__ or '')"` | exit 0 | PASS |
| `AsyncDatabase.fetch_all` docstring contains `dict_row` | `python -c "from pycopg.async_database import AsyncDatabase; assert 'dict_row' in (AsyncDatabase.fetch_all.__doc__ or '')"` | exit 0 | PASS |
| All 8 methods have identical signatures on both classes | `python` inspect comparison | all 8 match | PASS |
| Parity test suite | `PGDATABASE=pycopg_test2 uv run pytest tests/test_parity.py -o addopts="" -q` | 25 passed | PASS |
| Sync CRUD integration tests | `PGDATABASE=pycopg_test2 uv run pytest tests/test_database_integration.py -k "upsert or delete_where ..."` | 24 passed | PASS |
| Async CRUD integration tests | `PGDATABASE=pycopg_test2 uv run pytest tests/test_async_database.py -k "upsert or delete_where ..."` | 20 passed | PASS |
| Full targeted suite (base + parity + integration sync + async) | `PGDATABASE=pycopg_test2 uv run pytest ... -k "build_where or parity or upsert or ..."` | 74 passed | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| CRUD-01 | 34-02 | `db.upsert(table, row, conflict_columns)` singular upsert returning dict | SATISFIED | `database.py:647`, `async_database.py:1228`; `RETURNING *` present; tests pass |
| CRUD-02 | 34-02 | `db.delete_where(table, where={...})` → rowcount int | SATISFIED | `database.py:702`, `async_database.py:1283`; `ValueError` on empty where; tests pass |
| CRUD-03 | 34-02 | `db.update_where(table, values={...}, where={...})` → rowcount int | SATISFIED | `database.py:742`, `async_database.py:1323`; `ValueError` on empty where/values; tests pass |
| CRUD-04 | 34-01, 34-03 | `db.exists(table, where={...}) -> bool` without fetching rows | SATISFIED | `database.py:792`; `SELECT EXISTS(SELECT 1 FROM ...)`; ValueError guard; tests pass |
| CRUD-05 | 34-01, 34-03 | `db.count(table, where=None) -> int` | SATISFIED | `database.py:833`; `SELECT COUNT(*)`; `where=None` routes around builder; tests pass |
| CRUD-06 | 34-01, 34-03 | `db.paginate(table, limit, offset=0, order_by=..., where=None)` returning page rows | SATISFIED | `database.py:1114`; validated order_by, int-cast limit/offset, optional where; tests pass |
| CRUD-07 | 34-03 | `list[dict]` fetch and dicts-by-default documented | SATISFIED | `database.py:1077`; `fetch_all` returns `list[dict]`; `dict_row` token in both docstrings; assertions pass |
| CRUD-08 | 34-02, 34-03 | Every new method has `AsyncDatabase` equivalent, identical signature, enforced by `test_parity.py` | SATISFIED | All 8 methods on both classes; identical param names verified programmatically; `test_all_database_public_methods_exist_in_async` + `test_method_signatures_match` pass |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| No debt markers (`TBD`, `FIXME`, `XXX`) found in any phase-modified file | — | — | — | — |
| No stubs (empty return values, placeholder components) found | — | — | — | — |
| All `return null`/`return []` patterns are conditional on `not cur.description` — correct behavior, not stubs | — | — | — | — |

### Review Findings (from 34-REVIEW.md)

The code review found 2 warnings and 4 info items. All were resolved in commit `607b7e3`.

| Finding | Severity | Status |
|---------|----------|--------|
| WR-01: `upsert` would build empty `DO UPDATE SET` on conflict-only rows → SyntaxError | Warning | FIXED — `if not update_columns: raise ValueError(...)` guard added at `database.py:680`, `async_database.py:1261` |
| WR-02: `paginate` accepted `None` elements in order_by list → opaque TypeError | Warning | FIXED — `if any(not isinstance(c, str) or not c ...)` guard added at `database.py:1174`, `async_database.py:902` |
| IN-01: `delete_where`/`update_where` error messages referenced bare `truncate_table` | Info | FIXED — messages updated to `db.schema.truncate_table` |
| IN-02: `update_where` docstring `where` param copied wrong clause from `delete_where` | Info | FIXED — docstring aligned with actual guard message |
| IN-03: `upsert` docstring missing `Raises` section | Info | Deferred (cosmetic) |
| IN-04: Duplicated `import uuid` / ad-hoc table helpers in async tests | Info | Deferred (test-only, cosmetic) |

---

## Gaps Summary

No gaps. All 13 must-haves are VERIFIED. All 8 requirements (CRUD-01 through CRUD-08) are SATISFIED. The code review warnings (WR-01, WR-02) that were found post-execution have been fixed and confirmed in the codebase. Two cosmetic info findings (IN-03, IN-04) were explicitly deferred and do not affect correctness or goal achievement.

---

_Verified: 2026-06-24_
_Verifier: Claude (gsd-verifier)_
