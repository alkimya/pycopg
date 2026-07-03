---
phase: 50-crud-introspection-follow-ups
plan: 01
subsystem: database
tags: [postgres, psycopg, crud, sql-injection, escape-hatch, sync-async-parity]

# Dependency graph
requires:
  - phase: 49-incremental-etl-follow-ups
    provides: house pattern precedent (keyword-only additive params, guards fire before DB round-trip, both-accessors-same-commit)
provides:
  - "QueryMixin._resolve_predicate static guard/resolver (pycopg/base.py)"
  - "where_sql/where_params keyword-only params on delete_where/update_where/exists/count/paginate (Database + AsyncDatabase)"
  - "where widened to Optional on the three destructive helpers (non-breaking widening)"
affects: [50-02-crud-pagination-page-envelope, 50-03-materialized-view-introspection, 50-04-describe-structured-output]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Raw-SQL WHERE escape hatch: where_sql fragment passed verbatim (never validate_identifiers), where_params bound %s"
    - "Predicate resolver: single QueryMixin._resolve_predicate call site shared by 5 helpers x 2 classes, enforces D-02/D-03/D-04 guards before any DB round-trip"

key-files:
  created: []
  modified:
    - pycopg/base.py
    - pycopg/database.py
    - pycopg/async_database.py
    - tests/test_database.py
    - tests/test_async_database.py
    - tests/test_sql_injection.py
    - tests/test_database_integration.py

key-decisions:
  - "D-02/D-03/D-04 guards centralized in one static resolver (_resolve_predicate) rather than duplicated across 10 call sites (5 helpers x 2 classes)"
  - "Destructive guard (delete_where/update_where/exists) reworded to check the RESOLVED fragment (post-_resolve_predicate), not the raw where dict — a non-empty where_sql now satisfies the guard by design (D-03)"
  - "where widened from required-positional to Optional[dict] on delete_where/update_where/exists — non-breaking widening (C-03), allows where_sql-only calls"

patterns-established:
  - "Escape-hatch trust boundary: where_sql is caller-owned SQL text, intentionally excluded from validate_identifiers (documented in every touched docstring); where_params remain the only untrusted-value path, always bound %s"

requirements-completed: [CRUD-F01]

# Metrics
duration: 15min
completed: 2026-07-03
---

# Phase 50 Plan 01: Raw-SQL WHERE Escape Hatch (CRUD-F01) Summary

**Added a keyword-only `where_sql`/`where_params` raw-SQL escape hatch to `delete_where`/`update_where`/`exists`/`count`/`paginate` on both `Database` and `AsyncDatabase`, routed through a single shared `QueryMixin._resolve_predicate` guard that enforces mutual-exclusion, non-empty-fragment, and param-desync invariants before any DB round-trip.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-03T21:20:19Z
- **Completed:** 2026-07-03T21:35:37Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments
- `QueryMixin._resolve_predicate` (pycopg/base.py) — a single static resolver shared by all 10 call sites (5 helpers x sync/async) that enforces D-02 (dict/where_sql mutual exclusion), D-03 (reject empty/whitespace-only where_sql), and D-04 (where_params requires where_sql) before touching the DB
- All five predicate helpers (`delete_where`, `update_where`, `exists`, `count`, `paginate`) on both `Database` and `AsyncDatabase` now accept `where_sql: str | None = None` and `where_params: Sequence[Any] | None = None`, with the raw fragment passed through verbatim (never run through `validate_identifiers` — the documented C-02 escape hatch) and only `where_params` bound as `%s`
- The three destructive helpers (`delete_where`/`update_where`/`exists`) had `where` widened from required-positional to `dict[str, Any] | None = None` (non-breaking widening under frozen SemVer 1.0, C-03) so `where_sql`-only calls are legal, while the "predicate required" guard now fires on the *resolved* fragment — a non-empty `where_sql` satisfies it, an absent/empty one still raises
- Full sync/async parity verified by `test_accessor_parameter_kind_parity`/`test_database_core_parameter_kind_parity` (KIND-parity) with zero manual registration needed (reflection-based)
- Live-DB proof (sync + async) that the raw predicate executes correctly against `pycopg_test3` for all four call shapes: `count`, `exists`, `delete_where` (with an interval expression), `paginate`

## Task Commits

Each task was committed atomically:

1. **Task 1: Add QueryMixin._resolve_predicate guard/resolver (base.py)** - `3d0f4ac` (feat)
2. **Task 2: Wire where_sql/where_params + guards into the five helpers on both classes** - `d4d8f0c` (feat)
3. **Task 3: Live integration for the raw predicate (sync + async) + quick gate** - `7d0b108` (test)

_Note: Task 1 was written with an accompanying test (`test_resolve_predicate_guard_matrix`, split into 8 assertion methods) in the same commit; Task 2 similarly bundled mock-shape + guard + injection tests with the production wiring._

## Files Created/Modified
- `pycopg/base.py` - `QueryMixin._resolve_predicate` static guard/resolver, placed directly after `_build_where_dict`
- `pycopg/database.py` - `where_sql`/`where_params` on `delete_where`/`update_where`/`exists`/`count`/`paginate`; `where` widened to Optional on the three destructive helpers
- `pycopg/async_database.py` - identical async mirrors, same commit as the sync edits
- `tests/test_database.py` - `TestResolvePredicate` (8 guard-matrix tests), `TestWhereSqlShape` (6 mock SQL-shape tests), `TestWhereSqlGuards` (7 guard tests)
- `tests/test_async_database.py` - `TestAsyncWhereSqlShape` (5 tests), `TestAsyncWhereSqlGuards` (7 tests) — async mirrors of the sync mock suites
- `tests/test_sql_injection.py` - `TestWhereSqlValueInjection` (sync + async, parametrized over `EVIL_IDENTIFIERS`) proving `where_params` bind as `%s` and never reach the SQL string
- `tests/test_database_integration.py` - `TestWhereSqlEscapeHatchIntegration` (9 live-DB tests: 5 sync + 4 async) proving the raw predicate executes against `pycopg_test3`

## Decisions Made
- Centralized all four D-02/D-03/D-04 guard checks in one static `_resolve_predicate` method rather than duplicating guard logic at each of the 10 call sites — matches the existing `_build_where_dict` sibling pattern and keeps the destructive-guard rewording (Pitfall 2 from RESEARCH.md) to a single source of truth
- Kept the destructive guard's exact wording style ("requires a non-empty 'where' dict...") but extended it to also mention `where_sql`, preserving message continuity for any existing callers matching on the ValueError text
- Named the local resolved-predicate variables `frag`/`pred_params` (not `fragment`/`where_params`) inside each helper body to avoid shadowing the new `where_params` keyword argument — this was a deliberate naming choice while wiring Task 2, not a plan deviation

## Deviations from Plan

None - plan executed exactly as written. The one implementation nuance (renaming local variables to avoid keyword-argument shadowing) was a necessary mechanical detail of the D-01 signature change described in the plan's Task 2 action, not a change in scope or behavior.

## Issues Encountered

None. All three tasks' `<automated>` verify commands passed on the first attempt; the full standing-bar quality gate (full suite, mypy --strict, ruff, interrogate, Sphinx `-W`) was run once at the end of Task 3 and was green without needing fixes.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `QueryMixin._resolve_predicate` is now available for reuse by plan 50-02's `paginate_page`/`paginate_keyset` (both accept `where_sql`/`where_params` per D-01, and both should route the base predicate through this same resolver alongside the new keyset row-value fragment)
- Full suite 1898 passed @ 96.64% coverage (baseline was 96.29% at Phase 49), mypy --strict 0/18 files, ruff clean, interrogate 100%, Sphinx `-W` clean
- No blockers for plan 50-02 (keyset/seek pagination + Page envelope) — CRUD-F01 is fully independent of and does not touch the pagination surface beyond the shared resolver

---
*Phase: 50-crud-introspection-follow-ups*
*Completed: 2026-07-03*

## Self-Check: PASSED

All 7 modified source/test files and the summary file confirmed present on disk; all 4 commit hashes (3d0f4ac, d4d8f0c, 7d0b108, 3503e69) confirmed present in git log.
