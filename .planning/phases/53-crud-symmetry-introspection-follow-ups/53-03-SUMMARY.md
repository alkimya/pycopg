---
phase: 53-crud-symmetry-introspection-follow-ups
plan: 03
subsystem: database
tags: [introspection, schema-accessor, sync-async-parity, postgresql, sql-injection]

# Dependency graph
requires:
  - phase: 53-01
    provides: "select_where/find + get/find_one predicate reads (used indirectly by table_size's guard pattern precedent, and by db.get in adjacent live-DB tests)"
  - phase: 53-02
    provides: "insert single-row (CRUD-F06), completing the flat-core symmetry set before this plan's introspection-only surface"
provides:
  - "SchemaAccessor.column_exists / AsyncSchemaAccessor.column_exists — bool, mirrors table_exists mechanically (D-08)"
  - "SchemaAccessor.table_size / AsyncSchemaAccessor.table_size — guarded int (raw pg_total_relation_size bytes), TableNotFoundError on missing table (D-09)"
  - "test_schema_v120_surface — named frozenset locking column_exists/table_size on both schema accessors"
  - "Phase 53 (CRUD-F04..F06 + INTRO-F03/F04) fully documented in docs/api-reference.md + README.md; full phase-gate suite green"
affects: [54-release]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Existence-check family: column_exists mirrors table_exists byte-for-byte (self._db.execute(CONST, [schema, table, column]); len(result) > 0), no validate_identifiers call — safe purely by parameterization against information_schema.columns"
    - "Guarded scalar introspection: table_size copies truncate_table's existence guard verbatim (validate_identifiers + table_exists check + TableNotFoundError) then reuses the already-shipped queries.TABLE_SIZE constant, no duplicate SQL"

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
    - README.md

key-decisions:
  - "D-08: column_exists mirrors table_exists mechanically — 3 values (schema, table, column) bound as %s against information_schema.columns, no identifier interpolation, no validate_identifiers call needed"
  - "D-09: table_size is guarded (table_exists check first, raises TableNotFoundError on missing) and returns raw pg_total_relation_size bytes with no pretty formatting; reuses the already-shipped queries.TABLE_SIZE constant rather than duplicating it"

patterns-established:
  - "db.schema.table_size (raw bytes, guarded, TableNotFoundError) is documented as intentionally distinct from db.maint.table_size (pretty=True default, no existence guard) via a numpydoc See Also cross-reference — no deduplication (Pitfall 1)"

requirements-completed: [INTRO-F03, INTRO-F04]

# Metrics
duration: ~20min
completed: 2026-07-05
---

# Phase 53 Plan 03: column_exists + table_size introspection (INTRO-F03/F04) Summary

**Completed the `db.schema.*` existence/size introspection families with `column_exists` (bool, mirrors `table_exists` mechanically) and `table_size` (guarded raw-byte int, `TableNotFoundError` on a missing table, reusing the already-shipped `queries.TABLE_SIZE` constant) on both `SchemaAccessor` and `AsyncSchemaAccessor` — then documented the entire Phase 53 surface (7 new symbols across CRUD-F04..F06 + INTRO-F03/F04) and verified every phase-gate green.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-07-05 (session start)
- **Completed:** 2026-07-05T09:41:01+02:00
- **Tasks:** 3/3 completed
- **Files modified:** 9 (2 source, 5 test, 2 docs)

## Accomplishments

- Added one new SQL constant, `queries.COLUMN_EXISTS` (`information_schema.columns`, 3 bound `%s` values), inserted immediately after `GET_COLUMNS` in the `# TABLE QUERIES` section — no duplicate size constant added; `table_size` reuses the pre-existing `queries.TABLE_SIZE` (queries.py:301) verbatim.
- `column_exists(table, column, *, schema="public") -> bool` shipped on both `SchemaAccessor` and `AsyncSchemaAccessor` — a byte-for-byte mirror of `table_exists` (no `validate_identifiers` call; safe purely because all three values are bound `%s` params, never interpolated as SQL identifiers, D-08).
- `table_size(name, *, schema="public") -> int` shipped on both accessors — copies `truncate_table`'s existence guard verbatim (`validate_identifiers(name, schema)` then `table_exists` check), raises the library's `TableNotFoundError` with a clean `'schema.table'` message on a missing table (never a raw psycopg `UndefinedTable`, never a silent `0`), and returns the raw `pg_total_relation_size` byte count with no pretty formatting (D-09). Docstring carries a "See Also: `db.maint.table_size`" cross-reference — a deliberate non-deduplication (Pitfall 1), since that sibling method has different semantics (`str | int`, `pretty=True` default, no existence guard).
- `test_schema_v120_surface` added to `tests/test_parity.py` (named frozenset `{"column_exists", "table_size"}`), following the `test_schema_v110_surface` precedent — asserts both new methods are present on both schema accessor classes.
- Mocked unit tests (column_exists true/false, table_size guard raising `TableNotFoundError`) in `test_database.py`/`test_async_database.py`; parametrized identifier/value-binding injection tests in `test_sql_injection.py` — a value-binding proof for `column_exists` (no `validate_identifiers` guard exists by design; the payload is proven to reach the cursor as a bound param, never interpolated into the SQL text) and an `InvalidIdentifierError` proof for `table_size`'s explicit `validate_identifiers` guard on `name`/`schema`.
- Live-DB integration tests against `pycopg_test3` (sync + async): `column_exists` true/false against a seeded temp table, `table_size` returns a positive int for a populated table, and raises `TableNotFoundError` for a nonexistent table.
- Documented all 7 Phase 53 symbols in `docs/api-reference.md` — a new "CRUD Methods (v1.2.0)" table (`select_where`/`find`/`get`/`find_one`/`insert`) and a new "Introspection Methods (v1.2.0)" table (`column_exists`/`table_size`), plus matching README.md usage examples.
- Full phase-gate suite verified green: `pytest` 2397 passed/2 skipped @ 96.82% coverage (up from 96.80% baseline), `mypy --strict` 0 errors/18 files, `interrogate` 100%, `ruff check` clean, `sphinx-build -W` clean.

## Task Commits

Each task was committed atomically:

1. **Task 1: COLUMN_EXISTS constant + column_exists + table_size (sync + async) + unit/injection tests** - `d5e8a42` (feat)
2. **Task 2: live-DB introspection tests + test_schema_v120_surface** - `505db81` (test)
3. **Task 3: docs surfaces for the 7 new symbols + full phase-gate verification** - `016b84a` (docs)

## Files Created/Modified

- `pycopg/queries.py` - added `COLUMN_EXISTS` constant (reuses existing `TABLE_SIZE`)
- `pycopg/schema.py` - added `column_exists` + `table_size` to `SchemaAccessor` and `AsyncSchemaAccessor`
- `tests/test_database.py` - mocked `column_exists`/`table_size` unit tests
- `tests/test_async_database.py` - mocked async `column_exists`/`table_size` unit tests
- `tests/test_sql_injection.py` - `TestColumnExistsValueInjection` (value-binding proof), `TestTableSizeIdentifierInjection` (validate_identifiers proof)
- `tests/test_database_integration.py` - `TestColumnExistsTableSizeIntegration` live-DB tests (sync + async)
- `tests/test_parity.py` - `test_schema_v120_surface` (new)
- `docs/api-reference.md` - "CRUD Methods (v1.2.0)" + "Introspection Methods (v1.2.0)" tables + usage snippet
- `README.md` - flat-CRUD summary line update + "CRUD Reads + Single-Row Insert (v1.2.0)" section + introspection examples

## Decisions Made

Both decisions were pre-locked in `53-CONTEXT.md` (D-08, D-09) and followed exactly:

- `column_exists` mirrors `table_exists` mechanically — no `validate_identifiers` call, safe purely by parameterization (3 values bound `%s` against `information_schema.columns`).
- `table_size` is guarded (existence check first, `TableNotFoundError` on missing) and returns raw `pg_total_relation_size` bytes with no pretty formatting — reuses the already-shipped `queries.TABLE_SIZE` constant rather than adding a duplicate.

## Deviations from Plan

None - plan executed exactly as written. All 3 tasks, all `must_haves.truths`, and all threat-model mitigations (T-53-01 identifier validation for `table_size` + value-binding for `column_exists`, T-53-02 bound-parameter convention, T-53-01b information-disclosure guard raising `TableNotFoundError` instead of leaking a raw psycopg error) were implemented and tested as specified.

## Known Stubs

None - both `column_exists` and `table_size` are fully wired to real SQL execution against `self._db.execute`; no placeholder or mock data paths ship in production code.

## Threat Flags

None - the threat model in `53-03-PLAN.md` (T-53-01, T-53-02, T-53-01b) fully covers the new surface (column_exists's parameterized-not-interpolated binding, table_size's validate_identifiers + existence guard, and the TableNotFoundError information-disclosure mitigation). No new trust boundary was introduced beyond what the plan anticipated.

## Issues Encountered

None. One minor doc-lint note: the newly added "Introspection Methods (v1.2.0)" table triggered pre-existing markdownlint MD060 (table-column-style) warnings that already apply uniformly to every other table in `docs/api-reference.md` (the whole file uses unaligned pipe style) — not a regression introduced by this plan, and not a gate (`sphinx-build -W` and the standing bar do not check markdownlint). A draft internal anchor link (`#size/stats-methods`) was caught by the IDE's MD051 link-fragment check before commit and replaced with a plain-text cross-reference to avoid a broken-link false positive.

## Next Phase Readiness

- `column_exists`/`table_size` are live on both `SchemaAccessor` and `AsyncSchemaAccessor`, completing INTRO-F03/F04. Combined with Plans 01 (CRUD-F04/F05) and 02 (CRUD-F06), **Phase 53 (CRUD Symmetry + Introspection Follow-ups) is now fully complete: 5 requirements (CRUD-F04, CRUD-F05, CRUD-F06, INTRO-F03, INTRO-F04) all shipped.**
- Standing bar held: coverage 96.82% (>=95% ratchet, up from 96.80%), mypy strict 0/18, ruff clean, interrogate 100%, Sphinx `-W` clean, full parity gate green (including the new `test_schema_v120_surface`).
- Ready for `/gsd-verify-work` on Phase 53, then Phase 54 (Release v1.2.0 — DOC-14, TOOL-01, REL-13).

---
*Phase: 53-crud-symmetry-introspection-follow-ups*
*Plan: 03*
*Completed: 2026-07-05*

## Self-Check: PASSED

- FOUND: pycopg/queries.py
- FOUND: pycopg/schema.py
- FOUND: tests/test_database.py
- FOUND: tests/test_async_database.py
- FOUND: tests/test_sql_injection.py
- FOUND: tests/test_database_integration.py
- FOUND: tests/test_parity.py
- FOUND: docs/api-reference.md
- FOUND: README.md
- FOUND commit: d5e8a42 (Task 1: COLUMN_EXISTS constant + column_exists + table_size)
- FOUND commit: 505db81 (Task 2: live-DB introspection tests + test_schema_v120_surface)
- FOUND commit: 016b84a (Task 3: docs surfaces + full phase-gate verification)
