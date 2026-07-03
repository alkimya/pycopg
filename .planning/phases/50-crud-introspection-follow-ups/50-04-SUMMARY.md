---
phase: 50-crud-introspection-follow-ups
plan: 04
subsystem: database
tags: [postgresql, introspection, schema, dataclass, dataframe, sync-async-parity]

# Dependency graph
requires:
  - phase: 50-crud-introspection-follow-ups (plan 01/02/03)
    provides: house pattern for keyword-only additive params, RunResult/Page
      dataclass export precedent, sync/async parity registered in
      test_parity.py
provides:
  - "db.schema.describe(table, into='dict'|'dataclass'|'dataframe') -> dict | TableDescription | pd.DataFrame (both accessors)"
  - "pycopg.TableDescription frozen dataclass (columns/primary_key/foreign_keys/indexes)"
affects: []
completes: [50-crud-introspection-follow-ups]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "@overload quadruplet (default-literal/dataclass/dataframe/str-fallback)
      for a 3-way into= output selector, mirroring the timescale.py time_bucket
      default-value-placement template"
    - "wrap-don't-reshape: TableDescription(**flat) and pd.DataFrame(flat['columns'])
      reuse describe()'s existing flat dict verbatim, zero new SQL"

key-files:
  created: []
  modified:
    - pycopg/schema.py
    - pycopg/__init__.py
    - tests/test_database.py
    - tests/test_async_database.py
    - tests/test_database_integration.py
    - docs/api-reference.md

key-decisions:
  - "D-11/D-12 confirmed as researched: describe(into=...) keyword param,
      default 'dict' byte-identical to v0.9.0 (C-03); TableDescription typed
      wrapper for 'dataclass', columns-section DataFrame for 'dataframe'"
  - "pandas imported top-level in schema.py (import pandas as pd), matching
      the etl.py precedent for a hard runtime dependency — not the lazy
      per-function import used by to_dataframe/time_bucket, since describe's
      dataframe branch needs pd.DataFrame at every call"

patterns-established:
  - "describe(into=): dict (frozen default) / dataclass (typed wrapper) /
      dataframe (columns table) — house into= convention extended to a
      3-literal overload set"

requirements-completed: [INTRO-F01]

# Metrics
duration: ~25min
completed: 2026-07-04
---

# Phase 50 Plan 04: Structured describe() Summary

**`db.schema.describe(into="dict"|"dataclass"|"dataframe")` adds a typed `TableDescription` dataclass and a one-row-per-column `pandas.DataFrame` view on top of the frozen v0.9.0 flat-dict default, on both sync and async accessors — completing Phase 50.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-07-03T~21:55:00Z (approx, following 50-03 completion)
- **Completed:** 2026-07-03T22:22:59Z
- **Tasks:** 3 completed
- **Files modified:** 6

## Accomplishments

- `TableDescription` frozen dataclass added to `pycopg/schema.py` (introspection-owned,
  D-12): fields `columns`/`primary_key`/`foreign_keys`/`indexes` mirror `describe`'s
  four dict keys 1:1, each the unreshaped output of its standalone helper. Exported
  from `pycopg/__init__.py` (`from pycopg import TableDescription`), mirroring the
  `RunResult`/`Page` precedent.
- `describe(table, *, schema="public", into="dict")` gains the `@overload` quadruplet
  (default-valued `Literal["dict"] = "dict"`, defaultless `Literal["dataclass"]`,
  defaultless `Literal["dataframe"]`, `str` fallback) on **both** `SchemaAccessor` and
  `AsyncSchemaAccessor` in the same commit (C-01). Default `into="dict"` return is
  byte-identical to the v0.9.0 flat dict (C-03) — verified by direct equality test
  against the un-parameterized call. `into="dataclass"` returns
  `TableDescription(**flat)`; `into="dataframe"` returns
  `pd.DataFrame(flat["columns"])`; an unrecognized `into` raises `ValueError`.
- `pandas` imported top-level in `schema.py` (`import pandas as pd`) — the
  `describe(into="dataframe")` branch calls `pd.DataFrame` at every invocation, so
  the etl.py hard-runtime-dep precedent (not the lazy per-function import used by
  `to_dataframe`/`time_bucket`) applies.
- Live-DB integration tests (sync + async) prove zero shape drift: a real table's
  `describe(t, into="dataclass")` sub-values equal `describe(t)`'s sub-values exactly,
  and `describe(t, into="dataframe")` has one row per column with the 8 `table_info`
  keys as DataFrame columns.
- `docs/api-reference.md` `describe` row updated to show the three `into=` literals +
  union return, with a `TableDescription` field-reference block alongside the existing
  `Page` block.

## Task Commits

Each task was committed atomically:

1. **Task 1: TableDescription dataclass + pandas import + export** - `f7c4b07` (feat)
2. **Task 2: describe(into=...) with @overload quadruplet (both accessors)** - `f14a447` (feat)
3. **Task 3: Live no-drift integration + docs + phase gate** - `d0270ad` (test)

**Plan metadata:** commit pending (this SUMMARY + STATE/ROADMAP update)

## Files Created/Modified

- `pycopg/schema.py` - `TableDescription` frozen dataclass; `describe(into=...)`
  `@overload` quadruplet + implementation on `SchemaAccessor` and
  `AsyncSchemaAccessor`; top-level `import pandas as pd` / `Literal` / `overload` /
  `dataclass` imports
- `pycopg/__init__.py` - `TableDescription` export (import line + `__all__`)
- `tests/test_database.py` - `TestTableDescriptionDataclass` (field round-trip +
  frozen-immutability); `describe_into` mock unit tests (dict/dataclass/dataframe/
  invalid) in `TestDatabaseIntrospectionHelpers`
- `tests/test_async_database.py` - `TestAsyncDescribeIntoMock` async mock twins
  (dict/dataclass/dataframe/invalid)
- `tests/test_database_integration.py` - `TestDescribeIntoIntegration` live-DB
  no-drift proof, sync + async
- `docs/api-reference.md` - `describe` row + `TableDescription` field-reference block

## Decisions Made

None beyond the locked D-11/D-12 decisions from 50-CONTEXT.md, which this plan
implemented as researched (keyword `into=` selector, default byte-identical,
wrap-don't-reshape for both structured forms).

## Deviations from Plan

None - plan executed exactly as written. One naming adjustment during Task 3: the
initial live-integration test names (`test_describe_dataclass_matches_dict_no_drift`,
`test_describe_dataframe_one_row_per_column`) didn't match the plan's verify command
filter (`-k describe_into`); renamed to `test_describe_into_dataclass_no_drift` /
`test_describe_into_dataframe_one_row_per_column` so the filter selects them (not a
Rule 1-3 deviation — a naming fix caught by running the plan's own verify command).

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- INTRO-F01 fully shipped: `db.schema.describe(into=...)` on both accessors, full
  sync/async parity, `TableDescription` exported and typed, default return frozen
  byte-identical, mypy-strict overloads resolve, live-DB-proven zero shape drift.
- Full suite green: 2003 passed / 2 skipped @ 96.61% coverage, `mypy --strict` 0/18,
  `interrogate` 100%, `ruff check` clean, Sphinx `-W` clean.
- **Phase 50 (CRUD + Introspection Follow-ups) is now fully complete**: all 4 plans
  shipped (50-01 CRUD-F01 raw-SQL escape hatch, 50-02 CRUD-F02/F03 pagination +
  `Page` envelope, 50-03 INTRO-F02 materialized-view introspection, 50-04 INTRO-F01
  structured `describe()`). All 5 requirements (CRUD-F01..F03, INTRO-F01..F02)
  delivered, additive/non-breaking under the frozen SemVer 1.0 API.
- Ready for `/gsd-validate-phase 50` and milestone-level review (v1.1.0 will then be
  3/4 phases done, pending Phase 51 DOC-13 + REL-12).

---
*Phase: 50-crud-introspection-follow-ups*
*Completed: 2026-07-04*

## Self-Check: PASSED

- FOUND: pycopg/schema.py
- FOUND: pycopg/__init__.py
- FOUND: tests/test_database.py
- FOUND: tests/test_async_database.py
- FOUND: tests/test_database_integration.py
- FOUND: docs/api-reference.md
- FOUND: .planning/phases/50-crud-introspection-follow-ups/50-04-SUMMARY.md
- FOUND: f7c4b07 (Task 1 commit)
- FOUND: f14a447 (Task 2 commit)
- FOUND: d0270ad (Task 3 commit)
- FOUND: a1ba9d8 (SUMMARY commit)
