---
phase: 50-crud-introspection-follow-ups
plan: 02
subsystem: database
tags: [postgres, psycopg, pagination, keyset, seek-pagination, dataclass, sync-async-parity]

# Dependency graph
requires:
  - phase: 50-crud-introspection-follow-ups (plan 01)
    provides: "QueryMixin._resolve_predicate guard/resolver, reused unchanged for the base predicate on both new pagination methods"
provides:
  - "Page frozen dataclass (rows/total/has_next/next_cursor), exported from pycopg"
  - "QueryMixin._build_keyset_where row-value keyset builder ((c1, c2) > (%s, %s), flips to < when descending)"
  - "paginate_page() and paginate_keyset() on Database + AsyncDatabase, both returning Page"
affects: [50-03-materialized-view-introspection, 50-04-describe-structured-output]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Row-value keyset compare: (c1, c2) > (%s, %s) lexicographic tuple compare, index-friendly, reused from the shipped ETL composite-watermark builder shape"
    - "limit+1 fetch-and-trim for cheap has_next; separate opt-in COUNT(*) for total (avoids surprise COUNT on deep/keyset pages)"
    - "Multi-column DESC must be applied to every ORDER BY column, not just the trailing one, to stay consistent with a flipped row-value operator"

key-files:
  created: []
  modified:
    - pycopg/base.py
    - pycopg/database.py
    - pycopg/async_database.py
    - pycopg/__init__.py
    - tests/test_database.py
    - tests/test_async_database.py
    - tests/test_sql_injection.py
    - tests/test_database_integration.py
    - tests/test_parity.py
    - docs/api-reference.md

key-decisions:
  - "Page defined in database.py (not base.py) — mirrors the RunResult module-ownership precedent; async_database.py imports it via from pycopg.database import Page"
  - "paginate_page/paginate_keyset carry NO @overload — return type is unconditionally Page (with_total only changes the value of Page.total, never the return type)"
  - "paginate_keyset's WHERE composition ANDs the keyset row-value fragment first, then the optional where/where_sql predicate second: (c1,c2) > (%s,%s) AND <predicate>"
  - "with_total's COUNT(*) uses only the base predicate params, never the keyset after fragment — total is the full filtered set, not the remaining-after-cursor set (D-10)"

patterns-established:
  - "test_crud_v110_surface checks Database/AsyncDatabase directly (not an ACCESSOR_PAIRS entry) since paginate_page/paginate_keyset live on the flat core, not an accessor"

requirements-completed: [CRUD-F02, CRUD-F03]

# Metrics
duration: 18min
completed: 2026-07-03
---

# Phase 50 Plan 02: Keyset Pagination + Page Envelope (CRUD-F02/F03) Summary

**Added `paginate_page()`/`paginate_keyset()` on both `Database` and `AsyncDatabase` returning a frozen `Page` envelope, with `paginate_keyset` implementing stable, index-friendly seek pagination via a PostgreSQL row-value comparison `(c1, c2) > (%s, %s)` — while leaving the existing `paginate()` untouched (still `list[dict]`).**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-07-03T21:37:21Z
- **Completed:** 2026-07-03T21:54:58Z
- **Tasks:** 3
- **Files modified:** 10

## Accomplishments
- `Page` frozen dataclass (`pycopg/database.py`) — `rows`/`total`/`has_next`/`next_cursor`, mirroring the `RunResult` precedent, exported as `pycopg.Page`
- `QueryMixin._build_keyset_where` (`pycopg/base.py`) — the row-value keyset builder shared by both classes, `validate_identifiers` on `order_cols` as line 1, flips `>` to `<` when `descending=True`
- `paginate_page()` on both classes — offset-pagination sibling of `paginate()` returning `Page`; `has_next` via a cheap `limit + 1` fetch-and-trim; `total` via a separate `COUNT(*)` only when `with_total=True`
- `paginate_keyset()` on both classes — `order_by` mandatory (raises `ValueError` if omitted), `after=` cursor tuple keyed positionally to `order_by`, arity validated before any DB round-trip, keyset fragment ANDs with the optional `where`/`where_sql` predicate, `next_cursor` keyed to `order_by` columns
- `test_crud_v110_surface` registers `{paginate_page, paginate_keyset}` on both `Database` and `AsyncDatabase`; KIND-parity auto-covered by the existing `test_database_core_parameter_kind_parity`
- Live-DB proof (sync + async, `pycopg_test3`): forward keyset paging is monotonic and non-overlapping across pages with `has_next` flipping `False` on the last page; `after=None` returns the first page; `descending=True` pages in reverse and stays monotonic; `paginate_page(with_total=True).total` matches the full filtered `COUNT(*)`; `paginate_page` composes `where_sql`
- `docs/api-reference.md` updated: `where_sql`/`where_params` note on the five predicate helpers, a new "Pagination (v1.1.0)" section documenting `paginate_page`/`paginate_keyset` + the `Page` dataclass fields

## Task Commits

Each task was committed atomically:

1. **Task 1: Page dataclass + _build_keyset_where builder + Page export** - `13ac430` (feat)
2. **Task 2: paginate_page + paginate_keyset on both classes (Page-returning)** - `ef0b647` (feat)
3. **Task 3: Live keyset/offset integration + parity surface + docs** - `041c551` (test)

## Files Created/Modified
- `pycopg/base.py` — `QueryMixin._build_keyset_where` static row-value builder, placed directly after `_resolve_predicate`
- `pycopg/database.py` — `Page` frozen dataclass; `paginate_page`/`paginate_keyset` methods on `Database`
- `pycopg/async_database.py` — `Page` imported from `pycopg.database`; identical async mirrors of both new methods
- `pycopg/__init__.py` — `Page` imported and added to `__all__`
- `tests/test_database.py` — `TestPageDataclass` (3 tests), `TestBuildKeysetWhere` (4 tests), `TestPaginatePage` (5 mock-shape tests), `TestPaginateKeyset` (8 mock-shape + guard tests)
- `tests/test_async_database.py` — `TestAsyncPaginatePage` (4 tests), `TestAsyncPaginateKeyset` (8 tests) — async mirrors
- `tests/test_sql_injection.py` — `TestKeysetInjection` (order_by validation + after-value binding, parametrized over `EVIL_IDENTIFIERS`)
- `tests/test_database_integration.py` — `TestPaginationV110Integration` (9 live-DB tests: 5 sync + 4 async) — forward/descending monotonic keyset paging, `with_total`, `where_sql` composition
- `tests/test_parity.py` — `test_crud_v110_surface`
- `docs/api-reference.md` — CRUD table `where_sql`/`where_params` note, new Pagination (v1.1.0) section + `Page` field table

## Decisions Made
- Defined `Page` in `database.py` (not `base.py`) per the `RunResult` module-ownership precedent (`paginate*` live on `Database`/`AsyncDatabase` directly, not `QueryMixin`); `async_database.py` and `pycopg/__init__.py` both import it from there
- No `@overload` on either new method — `Page` is the unconditional return type; `with_total` only changes the *value* of `Page.total`, never the return type shape (matches RESEARCH's explicit anti-pattern guidance)
- `paginate_keyset`'s WHERE composition orders the keyset row-value fragment first, ANDed with the optional predicate fragment second, matching the RESEARCH assembly order
- `with_total`'s `COUNT(*)` intentionally uses only the base predicate params (never the keyset `after` fragment) so `Page.total` always represents the full filtered set, not "remaining after this cursor" (D-10)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed `paginate_keyset` multi-column `descending` ORDER BY**
- **Found during:** Task 3 (writing the live `descending=True` monotonic-progress integration test)
- **Issue:** The initial Task 2 implementation reused `paginate`'s existing single-suffix `direction = " DESC" if descending else ""` idiom, producing `ORDER BY val, id DESC` for `order_by=["val", "id"]` — in SQL this applies `DESC` only to the trailing column (`id`), leaving `val` ascending. This silently disagreed with the row-value comparison's fully-flipped `<` operator (Pitfall 3, explicitly called out in RESEARCH.md), producing wrong page ordering and non-monotonic results whenever more than one `order_by` column was used with `descending=True`. `paginate()` itself intentionally documents this exact "per-column direction is deferred" limitation as frozen v0.9.0 behavior (C-03) — the bug was specific to reusing that idiom for the keyset builder, where full multi-column reversal is a correctness requirement, not a documented limitation.
- **Fix:** `paginate_keyset` (both classes) now emits `f"{c} DESC"` for every `order_by` column when `descending=True` (`"val DESC, id DESC"`), keeping every column consistent with the row-value operator flip. `paginate_page` and `paginate()` were left untouched (their existing trailing-only-DESC behavior is documented and frozen).
- **Files modified:** `pycopg/database.py`, `pycopg/async_database.py`, `tests/test_database.py`, `tests/test_async_database.py` (two mock-shape assertions updated to the corrected SQL string)
- **Verification:** `TestPaginationV110Integration::test_paginate_keyset_descending_monotonic_progress` and its async mirror now pass, proving full-reverse monotonic paging across a multi-row, multi-page table with a shared `val` tiebreak on `id`
- **Committed in:** `041c551` (Task 3 commit)

**2. [Process note] `test_crud_v110_surface` added one task earlier than planned**
- **Found during:** Task 2
- **Issue:** The plan's Task 2 `<verify>` command already selects on `kind_parity`, and its own acceptance criteria implicitly require the surface to exist for KIND-parity to be meaningfully exercised on the new methods; Task 3 is where the plan formally lists adding `test_crud_v110_surface`.
- **Fix:** Added `test_crud_v110_surface` in Task 2's commit instead of Task 3's — pure sequencing, no scope or behavior change; Task 3 confirmed it still exists per its own acceptance criteria.
- **Files modified:** `tests/test_parity.py` (committed in `ef0b647` instead of `041c551`)
- **Verification:** `grep -c "test_crud_v110_surface" tests/test_parity.py` → 1 (confirmed present at Task 3's gate)
- **Committed in:** `ef0b647` (Task 2 commit)

---

**Total deviations:** 2 (1 auto-fixed bug, 1 sequencing note)
**Impact on plan:** The descending-ORDER-BY fix was necessary for correctness — without it, `descending=True` with a multi-column `order_by` would silently return wrong/duplicate pages. No scope creep; both fixes stayed within the plan's declared files.

## Issues Encountered

None beyond the descending-ORDER-BY bug documented above. All three tasks' `<automated>` verify commands passed after that one fix; the full standing-bar quality gate (full suite, mypy, ruff, interrogate, Sphinx `-W`) was run once at the end of Task 3 and was green without further fixes.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `Page` and `QueryMixin._build_keyset_where` are now available; plan 50-03 (materialized-view introspection) and 50-04 (structured `describe()`) do not depend on either — INTRO-F01/F02 are self-contained per RESEARCH's "two independently-plannable halves" split
- Full suite 1947 passed @ 96.58% coverage (up from 1898 @ 96.64% at plan 01 — net delta reflects the ~49 new tests added this plan against a slightly larger denominator), mypy 0/18 files, ruff clean, interrogate 100%, Sphinx `-W` clean
- No blockers for plan 50-03/50-04 — CRUD-F02/F03 is fully independent of `db.schema.*` introspection

---
*Phase: 50-crud-introspection-follow-ups*
*Completed: 2026-07-03*

## Self-Check: PASSED

All 10 modified source/test/docs files and the summary file confirmed present on disk; all 3 commit hashes (13ac430, ef0b647, 041c551) confirmed present in git log.
