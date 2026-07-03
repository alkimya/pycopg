---
phase: 50-crud-introspection-follow-ups
verified: 2026-07-04T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 50: CRUD + Introspection Follow-ups Verification Report

**Phase Goal:** Users get richer, more production-ready query ergonomics on the flat
transactional core and deeper structural visibility via `db.schema.*` — an escape hatch for
conditions the dict-WHERE form can't express, stable deep pagination, and materialized-view
introspection.

**Verified:** 2026-07-04
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can pass a raw-SQL WHERE fragment with bound params as an escape hatch to `delete_where`/`update_where`/`count`/`exists`/`paginate`, sync and async (CRUD-F01) | ✓ VERIFIED | `QueryMixin._resolve_predicate` (pycopg/base.py:328-388) enforces D-02/D-03/D-04; wired into all 5 helpers on both `Database` (pycopg/database.py:1015-1259, 1514-1608) and `AsyncDatabase` (pycopg/async_database.py:1033-1230+, 1987-2100+). Live-tested against `pycopg_test3`: `count(..., where_sql="val > %s", where_params=[10])` returned correct count; guard `ValueError` fired for both `where`+`where_sql` and for `delete_where` with no predicate. Sync + async both confirmed live. |
| 2 | User can paginate by keyset/cursor (seek method) for stable, index-friendly deep pagination, sync and async (CRUD-F02) | ✓ VERIFIED | `paginate_keyset` on `Database` (database.py:1734) and `AsyncDatabase` (async_database.py:1372), backed by `QueryMixin._build_keyset_where` (base.py:390-438, row-value `(c1,c2) > (%s,%s)`, flips to `<` when descending, `validate_identifiers` line 1). Live-walked a 20-row table 5-at-a-time via `after=page.next_cursor` sync and async, consumed all 20 rows monotonically with `has_next` correctly flipping `False` on the last page. |
| 3 | User can retrieve a page envelope carrying `total` and `has_next` alongside the rows (`Page` dataclass) (CRUD-F03) | ✓ VERIFIED | `Page` frozen dataclass (database.py:135-171: `rows`/`total`/`has_next`/`next_cursor`), exported as `pycopg.Page` (pycopg/__init__.py:17,98). `paginate_page(..., with_total=True).total` matched live `COUNT(*)` (20); `with_total=False` yields `total=None` by construction (D-10). |
| 4 | User can get `db.schema.describe()` output as a structured dataclass and/or DataFrame, not only a plain dict (INTRO-F01) | ✓ VERIFIED | `describe(into="dict"\|"dataclass"\|"dataframe")` `@overload` quadruplet on both `SchemaAccessor` (schema.py:884-958) and `AsyncSchemaAccessor` (schema.py:1789-1862). `TableDescription` frozen dataclass exported as `pycopg.TableDescription` (schema.py:37-63; __init__.py:36,127). Live-verified: `into="dataclass"`'s `.columns` == `into="dict"`'s `["columns"]` (no drift); `into="dataframe"` returned a `pd.DataFrame` with one row per column; `into="bogus"` raised `ValueError`. Sync + async both confirmed live. |
| 5 | User can introspect materialized views and their columns via `db.schema.materialized_views()` + per-view column introspection, sync and async (INTRO-F02) | ✓ VERIFIED | `queries.MATERIALIZED_VIEWS`/`MATERIALIZED_VIEW_COLUMNS` (pycopg/queries.py:197-208+, `pg_matviews`/`pg_attribute` with `relkind='m'`). `materialized_views()`/`materialized_view_columns()` on both `SchemaAccessor` (schema.py:830-882) and `AsyncSchemaAccessor` (schema.py:1733-1787), `validate_identifiers` line 1. Live-created a matview on `pycopg_test3`, confirmed it appears in `materialized_views()`, and `materialized_view_columns()` output keys matched `table_info()` keys byte-for-byte (8-key shape). Sync + async both confirmed live. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/base.py::QueryMixin._resolve_predicate` | guard/resolver for D-01..D-04 | ✓ VERIFIED | Present, exact invariant order matches RESEARCH spec |
| `pycopg/base.py::QueryMixin._build_keyset_where` | row-value keyset builder | ✓ VERIFIED | `validate_identifiers` line 1, `<`/`>` flip on `descending` |
| `pycopg/database.py::Page` | frozen dataclass rows/total/has_next/next_cursor | ✓ VERIFIED | Present, exported |
| `pycopg/database.py` (`delete_where`/`update_where`/`exists`/`count`/`paginate`) | `where_sql`/`where_params` | ✓ VERIFIED | All 5 helpers wired |
| `pycopg/database.py::paginate_page`/`paginate_keyset` | Page-returning pagination | ✓ VERIFIED | Both present, both return `Page`, WR-01/WR-02/IN-02 guards present |
| `pycopg/async_database.py` (5 helpers + paginate_page/paginate_keyset) | async mirrors | ✓ VERIFIED | Byte-identical logic to sync, `await` throughout |
| `pycopg/__init__.py` | `Page`, `TableDescription` exports | ✓ VERIFIED | Both imported + in `__all__` |
| `pycopg/queries.py::MATERIALIZED_VIEWS`/`MATERIALIZED_VIEW_COLUMNS` | pg_catalog query constants | ✓ VERIFIED | Present, `relkind = 'm'` filter confirmed |
| `pycopg/schema.py` (`materialized_views`/`materialized_view_columns`) | both accessors | ✓ VERIFIED | Sync + async, `validate_identifiers` line 1 |
| `pycopg/schema.py::TableDescription` | frozen dataclass | ✓ VERIFIED | 4 fields, exported |
| `pycopg/schema.py::describe(into=...)` | `@overload` quadruplet, both accessors | ✓ VERIFIED | 8 overloads total (4 sync + 4 async), default byte-identical to v0.9.0 |
| `tests/test_parity.py::test_crud_v110_surface` | `{paginate_page, paginate_keyset}` on both classes | ✓ VERIFIED | Present, passes |
| `tests/test_parity.py::test_schema_v110_surface` | `{materialized_views, materialized_view_columns}` on both accessors | ✓ VERIFIED | Present, passes |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `database.py` 5 helpers | `QueryMixin._resolve_predicate` | `self._resolve_predicate(where, where_sql, where_params)` | ✓ WIRED | Confirmed by source read + live execution |
| `async_database.py` 5 helpers | `QueryMixin._resolve_predicate` | same | ✓ WIRED | Confirmed by source read + live async execution |
| `database.py paginate_keyset` | `QueryMixin._build_keyset_where` | `self._build_keyset_where(order_cols, after, descending)` | ✓ WIRED | Live-walked, monotonic pages |
| `pycopg/__init__.py` | `pycopg.database.Page` | `from pycopg.database import Database, Page` | ✓ WIRED | `pycopg.Page` resolves |
| `schema.py materialized_views` | `queries.MATERIALIZED_VIEWS` | `self._db.execute(queries.MATERIALIZED_VIEWS, [schema])` | ✓ WIRED | Live-confirmed |
| `schema.py materialized_view_columns` | `queries.MATERIALIZED_VIEW_COLUMNS` | `self._db.execute(queries.MATERIALIZED_VIEW_COLUMNS, [schema, name])` | ✓ WIRED | Live-confirmed, byte-identical shape to `table_info` |
| `schema.py describe(into='dataclass')` | `TableDescription` | `TableDescription(**flat)` | ✓ WIRED | Live no-drift confirmed |
| `schema.py describe(into='dataframe')` | `pd.DataFrame` | `pd.DataFrame(flat['columns'])` | ✓ WIRED | Live-confirmed one-row-per-column |

### Data-Flow Trace (Level 4)

All artifacts in this phase are backend query/introspection methods (not UI components with
external data sources) — Level 4 tracing was performed via direct live-DB execution against
`pycopg_test3` rather than upstream state tracing. Results:

| Artifact | Data Source | Produces Real Data | Status |
|----------|-------------|---------------------|--------|
| `count`/`exists`/`delete_where` w/ `where_sql` | live `verify50_t` table (20 rows) | Yes — correct counts/existence | ✓ FLOWING |
| `paginate_keyset` | live `verify50_t` table | Yes — walked all 20 rows across 4 pages, monotonic | ✓ FLOWING |
| `paginate_page(with_total=True)` | live `COUNT(*)` | Yes — `total=20` matched actual row count | ✓ FLOWING |
| `materialized_views`/`materialized_view_columns` | live `pg_matviews`/`pg_attribute` catalog | Yes — real matview created+queried | ✓ FLOWING |
| `describe(into=...)` | live `table_info`/`primary_key`/`foreign_keys`/`list_indexes` helpers | Yes — dataclass/DataFrame equal dict sub-values | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| where_sql escape hatch (sync) | live script against `pycopg_test3`: `count`/`exists`/guard `ValueError`s | correct counts, guards fired | ✓ PASS |
| where_sql escape hatch (async) | live async script: `count` with `where_sql` | correct count (5) | ✓ PASS |
| Keyset pagination full walk (sync) | live script: 20 rows, limit=5, walked via `next_cursor` | 20/20 rows seen, monotonic, `has_next` flips False at end | ✓ PASS |
| Keyset pagination (async) | live async script: `paginate_keyset` first page | 3 rows, `has_next=True`, `Page` type confirmed | ✓ PASS |
| paginate_page with_total | live script: `with_total=True` | `total == 20` matches actual row count | ✓ PASS |
| Materialized view introspection (sync) | live `CREATE MATERIALIZED VIEW` + `materialized_views()`/`materialized_view_columns()` | matview listed, columns byte-identical to `table_info` | ✓ PASS |
| Materialized view introspection (async) | live async equivalent | matview listed via async accessor | ✓ PASS |
| describe(into=) no-drift (sync) | live `describe(into="dict"/"dataclass"/"dataframe")` + invalid `into` | no drift, `ValueError` on bogus value | ✓ PASS |
| describe(into=) no-drift (async) | live async `describe(into="dataclass")` | `TableDescription` instance returned | ✓ PASS |
| Full test suite | `PGDATABASE=pycopg_test3 uv run pytest tests/ -q -o addopts=""` | 2019 passed, 2 skipped | ✓ PASS |
| mypy --strict | `uv run mypy pycopg` | 0 errors, 18 files | ✓ PASS |
| Coverage gate | `pytest --cov=pycopg` | 96.67% (≥95% required) | ✓ PASS |
| Parity surface tests | `pytest tests/test_parity.py -k "crud_v110 or schema_v110 or kind_parity"` | 10 passed | ✓ PASS |

### Probe Execution

No `scripts/*/tests/probe-*.sh` files exist in this repository and none were declared in the
PLAN/SUMMARY files for this phase. Step 7c: SKIPPED (no declared or conventional probes;
behavioral verification performed instead via live-DB execution above, which supersedes probe
narration).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| CRUD-F01 | 50-01-PLAN.md | Raw-SQL WHERE escape hatch on 5 predicate helpers, sync+async | ✓ SATISFIED | Truth #1 |
| CRUD-F02 | 50-02-PLAN.md | Keyset/cursor pagination, sync+async | ✓ SATISFIED | Truth #2 |
| CRUD-F03 | 50-02-PLAN.md | Page envelope (total/has_next) | ✓ SATISFIED | Truth #3 |
| INTRO-F01 | 50-04-PLAN.md | describe() as dataclass/DataFrame | ✓ SATISFIED | Truth #4 |
| INTRO-F02 | 50-03-PLAN.md | Materialized-view introspection, sync+async | ✓ SATISFIED | Truth #5 |

No orphaned requirements found — REQUIREMENTS.md lists exactly these 5 IDs mapped to Phase 50,
and all 5 appear in a plan's `requirements:` frontmatter field.

### Anti-Patterns Found

None. Scanned all modified source files (`pycopg/base.py`, `pycopg/database.py`,
`pycopg/async_database.py`, `pycopg/schema.py`, `pycopg/queries.py`, `pycopg/__init__.py`) for
`TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` debt markers and stub-return patterns. Zero
matches beyond legitimate SQL "%s placeholder" documentation prose (not a debt marker).

Code review (50-REVIEW.md) found 2 warnings + 3 info items (WR-01 empty order_by, WR-02 limit
type-discipline mismatch, IN-01 NULL keyset caveat, IN-02 limit<=0 footgun, IN-03 docs example
bug) — all 5 confirmed fixed in commits `685b81f` (WR-01/WR-02/IN-02) and `a29eed0` (IN-01
docstring, IN-03 docs example), independently re-verified present in the current source
(`limit = int(limit)` + `limit <= 0` guard + `order_by must contain at least one column` guard
found in both `database.py` and `async_database.py`).

### Human Verification Required

None. All 5 success criteria are backend API behaviors fully verifiable by direct live-DB
execution (sync + async), which was performed as part of this verification.

### Gaps Summary

No gaps. All 5 ROADMAP success criteria for Phase 50 are independently confirmed both by static
source inspection (matching every `must_haves` artifact/key_link in all 4 plan frontmatters) and
by live execution against `pycopg_test3` (sync and async, exercising the escape hatch, keyset
walk, Page envelope, matview introspection, and describe(into=) no-drift). Full standing quality
bar re-verified independently: suite 2019 passed / 2 skipped @ 96.67% coverage, mypy --strict 0
errors, no anti-patterns in touched files, all 5 code-review findings confirmed fixed in the
current source.

---

_Verified: 2026-07-04_
_Verifier: Claude (gsd-verifier)_
