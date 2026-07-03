---
phase: 50-crud-introspection-follow-ups
plan: 03
subsystem: database
tags: [postgresql, pg_catalog, introspection, schema, sync-async-parity]

# Dependency graph
requires:
  - phase: 50-crud-introspection-follow-ups (plan 01/02)
    provides: house pattern for keyword-only additive params, validate_identifiers-first
      builders, sync/async parity registered in test_parity.py
provides:
  - "db.schema.materialized_views(*, schema='public') -> list[str] (both accessors)"
  - "db.schema.materialized_view_columns(name, *, schema='public') -> list[dict] in the
    same 8-key shape as table_info (both accessors)"
  - "queries.MATERIALIZED_VIEWS / queries.MATERIALIZED_VIEW_COLUMNS pg_catalog constants"
  - "test_schema_v110_surface parity registration"
affects: [50-04-describe-into, future matview-metadata follow-ups]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "pg_catalog dedicated query for a surface information_schema structurally
      cannot serve (matviews excluded from views/columns per SQL standard)"
    - "byte-for-byte shape reproduction of an existing query constant via
      information_schema._pg_* helper functions"

key-files:
  created: []
  modified:
    - pycopg/queries.py
    - pycopg/schema.py
    - tests/test_database.py
    - tests/test_async_database.py
    - tests/test_sql_injection.py
    - tests/test_database_integration.py
    - tests/test_parity.py
    - docs/api-reference.md

key-decisions:
  - "D-13/D-14 confirmed as researched: dedicated pg_catalog queries required (pg_matviews
    for names, pg_attribute/pg_class relkind='m' for columns); views()/table_info() left
    unchanged"
  - "D-15 honored: names + columns only, no ispopulated/definition/size"
  - "validate_identifiers kept as defense-in-depth on materialized_view_columns even
    though name/schema only ever reach the query as bound %s params (never interpolated),
    matching table_info's own posture documented in RESEARCH"

patterns-established:
  - "Matview introspection: pg_matviews for names, pg_attribute+_pg_* helpers for columns
    byte-identical to TABLE_INFO's 8-key shape"

requirements-completed: [INTRO-F02]

# Metrics
duration: 15min
completed: 2026-07-04
---

# Phase 50 Plan 03: Materialized-View Introspection Summary

**`db.schema.materialized_views()` + `materialized_view_columns()` close the `information_schema` gap for matviews via dedicated `pg_catalog` queries, byte-identical to `table_info`'s 8-key shape, on both sync and async accessors.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-07-04T00:00:00+02:00 (approx, following 50-02 completion)
- **Completed:** 2026-07-04T00:08:39+02:00
- **Tasks:** 2 completed
- **Files modified:** 8

## Accomplishments

- `queries.MATERIALIZED_VIEWS` (`pg_matviews`) and `queries.MATERIALIZED_VIEW_COLUMNS`
  (`pg_catalog.pg_attribute`/`pg_class` with `relkind='m'`, using the same
  `information_schema._pg_*` helper functions `information_schema.columns` itself uses)
  added to `pycopg/queries.py`.
- `materialized_views(*, schema="public") -> list[str]` and
  `materialized_view_columns(name, *, schema="public") -> list[dict[str, Any]]` added to
  both `SchemaAccessor` and `AsyncSchemaAccessor` in the same commit, `validate_identifiers`
  line 1.
- Live-DB integration test (sync + async) proves `materialized_view_columns` output matches
  `table_info`'s 8-key shape byte-for-byte on `data_type`/`character_maximum_length`/
  `numeric_precision`/`numeric_scale`, and faithfully reports `is_nullable='YES'` +
  `column_default=None` for matview columns (Pitfall 1 — matviews never carry NOT NULL
  constraints or defaults).
- `test_schema_v110_surface` registers the two new methods on both accessors in
  `tests/test_parity.py`.
- `docs/api-reference.md` gained an "Introspection Methods (v1.1.0)" table.

## Task Commits

Each task was committed atomically:

1. **Task 1: Matview query constants + accessor methods (both accessors)** - `fd9d886` (feat)
2. **Task 2: Live matview integration + parity surface + docs** - `7399dac` (test)

**Plan metadata:** commit pending (this SUMMARY + STATE/ROADMAP update)

## Files Created/Modified

- `pycopg/queries.py` - `MATERIALIZED_VIEWS` + `MATERIALIZED_VIEW_COLUMNS` constants
- `pycopg/schema.py` - `materialized_views`/`materialized_view_columns` on `SchemaAccessor`
  and `AsyncSchemaAccessor`
- `tests/test_database.py` - mock SQL-shape unit tests (`test_materialized_views_sql`,
  `test_materialized_view_columns_sql` + empty-result variants)
- `tests/test_async_database.py` - async mock twins (`TestAsyncMaterializedViewsMock`)
- `tests/test_sql_injection.py` - `TestMaterializedViewIdentifierInjection` (evil name/schema
  rejected on both accessors)
- `tests/test_database_integration.py` - `TestMaterializedViewIntegration` (live matview
  fixture, sync + async, byte-for-byte shape proof)
- `tests/test_parity.py` - `test_schema_v110_surface`
- `docs/api-reference.md` - Introspection Methods (v1.1.0) table

## Decisions Made

None beyond the locked D-13/D-14/D-15 decisions from 50-CONTEXT.md, which this plan
implemented as researched (dedicated `pg_catalog` queries, names + columns only, `views()`/
`table_info()` unchanged).

## Deviations from Plan

None - plan executed exactly as written. The matview SQL was copied verbatim from the
live-validated `50-RESEARCH.md` § 1 (confirmed byte-for-byte against `pycopg_test3` during
this execution's live integration test).

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- INTRO-F02 fully shipped: `db.schema.materialized_views()` / `materialized_view_columns()`
  on both accessors, full sync/async parity, `validate_identifiers` line 1, injection-tested,
  live-DB-proven byte-identical shape to `table_info`.
- Full suite green: 1990 passed @ 96.59% coverage, `mypy --strict` 0/18, `interrogate` 100%,
  `ruff check` clean, Sphinx `-W` clean.
- Ready to proceed to plan 50-04 (INTRO-F01 — `describe(into=...)` dataclass/DataFrame).

---
*Phase: 50-crud-introspection-follow-ups*
*Completed: 2026-07-04*

## Self-Check: PASSED

- FOUND: .planning/phases/50-crud-introspection-follow-ups/50-03-SUMMARY.md
- FOUND: fd9d886 (Task 1 commit)
- FOUND: 7399dac (Task 2 commit)
- FOUND: 9426f55 (SUMMARY commit)
