---
phase: 53-crud-symmetry-introspection-follow-ups
plan: 01
subsystem: database
tags: [crud, predicate-reads, sync-async-parity, postgresql, sql-injection]

# Dependency graph
requires:
  - phase: 50-crud-introspection-follow-ups
    provides: "QueryMixin._resolve_predicate (D-01..D-04 where/where_sql/where_params guard) + _build_select_sql (order_by/limit/offset composition), reused verbatim"
provides:
  - "Database.select_where / AsyncDatabase.select_where — list[dict] predicate read with columns=/order_by=/limit=/offset=, read-all on empty predicate"
  - "Database.find / AsyncDatabase.find — real concrete delegating twin of select_where"
  - "Database.get / AsyncDatabase.get — dict|None single-row read, forced server-side LIMIT 1, no raise on >1 match"
  - "Database.find_one / AsyncDatabase.find_one — real concrete delegating twin of get"
affects: [53-02, 53-03, 54-release]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Predicate-read composition: _resolve_predicate -> _build_select_sql(where=frag or None, ...) -> fetch_all/fetch_one"
    - "Real delegating twin (find->select_where, find_one->get) instead of @deprecated_alias or PEP 562 module alias"

key-files:
  created: []
  modified:
    - pycopg/database.py
    - pycopg/async_database.py
    - tests/test_database.py
    - tests/test_async_database.py
    - tests/test_sql_injection.py
    - tests/test_database_integration.py

key-decisions:
  - "D-01: select_where/find carry the full read surface (columns=/order_by=/limit=/offset=), reusing _build_select_sql rather than a new builder"
  - "D-02: find/find_one are concrete delegating def twins of select_where/get, not @deprecated_alias or PEP 562 aliases"
  - "D-03: empty predicate is legal for reads (read-all), unlike delete_where/update_where/exists which reject it"
  - "D-04: get/find_one force LIMIT 1 server-side and never raise on >1 match; order_by makes the first match deterministic"
  - "D-05: get/find_one expose columns=/order_by= but deliberately omit limit=/offset= (would contradict the forced LIMIT 1)"

patterns-established:
  - "order_by is a documented, caller-owned raw-SQL escape hatch identical in trust model to where_sql — never run through validate_identifiers, verified by a dedicated non-rejection test"

requirements-completed: [CRUD-F04, CRUD-F05]

# Metrics
duration: ~25min
completed: 2026-07-05
---

# Phase 53 Plan 01: select_where/find + get/find_one predicate reads Summary

**Added the missing predicate-read CRUD siblings (`select_where`/`find` -> `list[dict]`, `get`/`find_one` -> `dict | None`) to the flat transactional core on both `Database` and `AsyncDatabase`, purely by composing the already-shipped `_resolve_predicate` + `_build_select_sql` + `fetch_all`/`fetch_one` primitives — no new SQL-building logic.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-05 (session start)
- **Completed:** 2026-07-05T09:04:09+02:00
- **Tasks:** 3/3 completed
- **Files modified:** 6 (2 source, 4 test)

## Accomplishments

- `select_where`/`find` (list[dict]) and `get`/`find_one` (dict | None) shipped on both `Database` and `AsyncDatabase` — 8 new methods total, full sync/async parity verified by `test_parity.py` (169 passed, auto-extending gate).
- Empty predicate legally reads all rows (D-03) instead of raising, matching `count`'s policy rather than `delete_where`/`exists`'s destructive-guard policy.
- `get`/`find_one` force a server-side `LIMIT 1` (never Python-side truncation) and never raise on a >1-row match (D-04); `order_by` makes the "first" match deterministic.
- `find`/`find_one` are real concrete delegating `def` twins (D-02) — not `@deprecated_alias`, not PEP 562 module aliases — verified byte-identical to `select_where`/`get` in both mocked and live-DB tests.
- `order_by` (like `where_sql`) is a documented, intentional, caller-owned raw-SQL escape hatch: a dedicated test proves multi-column syntax (`"a DESC, b ASC"`) is accepted, not rejected, by `validate_identifiers`.
- Full standing-bar gates green: `uv run pytest` 2295 passed/2 skipped @ 96.79% coverage (up from 96.78% baseline), `mypy --strict` 0 errors/18 files, `ruff check` clean, `test_parity.py` green.

## Task Commits

Each task was committed atomically:

1. **Task 1: select_where + find (sync + async), predicate read-all composition** - `fc9f384` (feat)
2. **Task 2: get + find_one (sync + async), forced LIMIT 1 single-row read** - `fd463df` (feat)
3. **Task 3: live-DB integration tests for the four predicate reads** - `8eb0a30` (test)

**Plan metadata:** (this commit, docs)

## Files Created/Modified

- `pycopg/database.py` - added `select_where`, `find`, `get`, `find_one` (sync)
- `pycopg/async_database.py` - added `async select_where`, `async find`, `async get`, `async find_one` (async mirrors)
- `tests/test_database.py` - `TestSelectWhereFind`, `TestGetFindOne` mocked unit tests
- `tests/test_async_database.py` - `TestAsyncSelectWhereFind`, `TestAsyncGetFindOne` mocked unit tests
- `tests/test_sql_injection.py` - `TestSelectWhereFindIdentifierInjection`, `TestGetFindOneIdentifierInjection`, extended `TestWhereSqlValueInjection`, new `TestOrderByEscapeHatch`
- `tests/test_database_integration.py` - `TestSelectWhereGetIntegration` live-DB tests (sync + async)

## Decisions Made

All decisions were pre-locked in `53-CONTEXT.md` (D-01..D-05) and followed exactly:

- Rich single-SELECT shape for `select_where`/`find` (columns=/order_by=/limit=/offset=), reusing `_build_select_sql` rather than hand-rolling a new builder.
- `find`/`find_one` implemented as concrete delegating `def`s, never `@deprecated_alias` (hard-removed in v0.7.0) or a module-level alias.
- Empty predicate legal for reads (read-all), consistent with `count`'s no-predicate = count-all policy — no destructive guard on these four read helpers.
- `get`/`find_one` force `LIMIT 1` server-side via `_build_select_sql(limit=1, offset=None)` and never raise on multiple matches; uniqueness is the caller's responsibility.
- `get`/`find_one` deliberately omit `limit=`/`offset=` params — exposing them would contradict the forced `LIMIT 1`.

Additional pattern established during execution (not a deviation, just documentation): `order_by`'s trust model (caller-owned, unvalidated raw SQL) is treated identically to `where_sql` and now has its own dedicated non-rejection injection test, mirroring the precedent for `where_sql` from Phase 50.

## Deviations from Plan

None - plan executed exactly as written. All 3 tasks, all `must_haves.truths`, and all threat-model mitigations (T-53-01 identifier validation, T-53-02 value binding, T-53-03 documented `order_by`/`where_sql` escape hatch) were implemented and tested as specified.

## Known Stubs

None - all 8 new methods are fully wired to real SQL execution against `fetch_all`/`fetch_one`; no placeholder or mock data paths ship in production code.

## Threat Flags

None - the threat model in `53-01-PLAN.md` (T-53-01, T-53-02, T-53-03) fully covers the new surface (identifiers validated via `_build_select_sql`, values bound as `%s`, `order_by`/`where_sql` documented as caller-owned escape hatches). No new trust boundary was introduced beyond what the plan anticipated.

## Issues Encountered

None. One process note: the first implementation pass wrote Task 1 and Task 2 in a single combined edit; before committing, the working tree was reverted (`git checkout --` on the 5 touched files, an intentional single-file discard, not a blanket reset) and re-applied in two passes so each task landed in its own atomic commit as required.

## Next Phase Readiness

- `select_where`/`find`/`get`/`find_one` are live on both `Database` and `AsyncDatabase`; ready for Plan 02 (single-row `insert`, CRUD-F06) and Plan 03 (`column_exists`/`table_size` introspection, INTRO-F03/F04) to proceed independently.
- Standing bar held: coverage 96.79% (>=95% ratchet), mypy strict 0/18, ruff clean, full parity gate green.

---
*Phase: 53-crud-symmetry-introspection-follow-ups*
*Plan: 01*
*Completed: 2026-07-05*

## Self-Check: PASSED

- FOUND: pycopg/database.py
- FOUND: pycopg/async_database.py
- FOUND: tests/test_database.py
- FOUND: tests/test_async_database.py
- FOUND: tests/test_sql_injection.py
- FOUND: tests/test_database_integration.py
- FOUND commit: fc9f384 (Task 1: select_where + find)
- FOUND commit: fd463df (Task 2: get + find_one)
- FOUND commit: 8eb0a30 (Task 3: live-DB integration tests)
