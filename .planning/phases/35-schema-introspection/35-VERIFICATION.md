---
phase: 35-schema-introspection
verified: 2026-06-25T09:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 35: Schema Introspection Verification Report

**Phase Goal:** Users can call enriched read-only introspection helpers on `db.schema.*` to retrieve primary keys, foreign keys, sequences, views, and a consolidated table description, with full sync/async parity
**Verified:** 2026-06-25
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `db.schema.primary_key(table, schema="public")` returns PK column name(s) (dict or None) | VERIFIED | `schema.py:676-699` (sync), `schema.py:1457-1480` (async); queries `PRIMARY_KEY` pg_catalog constant; returns `{constraint_name, columns}` or `None`; `validate_identifiers` at line 692/1473 |
| 2 | `db.schema.foreign_keys(table, schema="public")` returns list of entries with local column(s), referenced table, referenced column(s) | VERIFIED | `schema.py:701-739` (sync), `schema.py:1482-1520` (async); exactly 4 keys `constraint_name/columns/referenced_table/referenced_columns`; grouping by `constraint_name` with `conkey/confkey` ordering via `FOREIGN_KEYS` constant |
| 3 | `db.schema.sequences(schema)` and `db.schema.views(schema)` return `list[str]`; views excludes matviews | VERIFIED | `schema.py:741-757/759-775` (sync), `schema.py:1522-1538/1540-1556` (async); `SEQUENCES` queries `information_schema.sequences`; `VIEWS` queries `information_schema.views` which naturally omits matviews; live-DB matview exclusion test at `test_database_integration.py:1215` passes |
| 4 | `db.schema.describe(table, schema="public")` returns consolidated dict (columns+types, primary_key, foreign_keys, indexes), composes standalone helpers, no new SQL | VERIFIED | `schema.py:777-804` (sync), `schema.py:1558-1585` (async); body references only `self.table_info/primary_key/foreign_keys/list_indexes`; no `DESCRIBE` constant in `queries.py` (confirmed by grep); composition-equality asserted in live-DB test `test_describe_keys_and_composition_equality` |
| 5 | Every new method callable identically on `AsyncSchemaAccessor`; `test_accessor_parity` passes | VERIFIED | All 5 async methods at lines 1457/1482/1522/1540/1558; `test_accessor_parity` — 26 passed; `test_schema_v090_surface` frozenset test asserting all 5 methods on both classes at `test_parity.py:101-132` passes |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/queries.py` | PRIMARY_KEY, FOREIGN_KEYS, SEQUENCES, VIEWS SQL constants | VERIFIED | Lines 141, 156, 179, 186; pg_catalog for PK/FK, information_schema for sequences/views; all use `%s` binding |
| `pycopg/schema.py` | 4 sync + 4 async + describe (sync+async) = 10 methods | VERIFIED | Lines 676/701/741/759/777 (sync), 1457/1482/1522/1540/1558 (async) |
| `tests/test_database.py` | Mock unit tests for all 4 helpers + describe | VERIFIED | `TestDatabaseIntrospectionHelpers` at line 1089; 10 test functions including `test_primary_key`, `test_primary_key_composite`, `test_primary_key_none`, `test_foreign_keys`, `test_foreign_keys_empty`, `test_sequences`, `test_sequences_empty`, `test_views`, `test_views_empty`, `test_describe_composes_four_helpers` |
| `tests/test_database_integration.py` | Live-DB tests (composite PK order, matview exclusion, describe composition equality) | VERIFIED | `TestIntrospectionHelpers` at line 1108; 11 test functions including composite PK key-order, FK grouping, matview exclusion, nonexistent-table graceful return, describe composition equality |
| `tests/test_parity.py` | `test_schema_v090_surface` named surface test | VERIFIED | Lines 101-132; frozenset of all 5 new methods asserted on both SchemaAccessor and AsyncSchemaAccessor |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `schema.py:primary_key` | `queries.py:PRIMARY_KEY` | `self._db.execute(queries.PRIMARY_KEY, [schema, table])` | WIRED | Line 693 (sync), 1474 (async) |
| `schema.py:foreign_keys` | `queries.py:FOREIGN_KEYS` | `self._db.execute(queries.FOREIGN_KEYS, [schema, table])` | WIRED | Line 720 (sync), 1501 (async) |
| `schema.py:sequences` | `queries.py:SEQUENCES` | `self._db.execute(queries.SEQUENCES, [schema])` | WIRED | Line 756 (sync), 1537 (async) |
| `schema.py:views` | `queries.py:VIEWS` | `self._db.execute(queries.VIEWS, [schema])` | WIRED | Line 774 (sync), 1555 (async) |
| `schema.py:describe` | `schema.py:table_info/primary_key/foreign_keys/list_indexes` | four `self.*` composition calls | WIRED | Lines 800-804 (sync), 1581-1585 (async); no new SQL |
| All 8 standalone methods | `utils.py:validate_identifiers` | called as first line before any execute | WIRED | Lines 692, 719, 755, 773 (sync); 1473, 1500, 1536, 1554 (async) |

### Data-Flow Trace (Level 4)

All five methods are read-only introspection (not rendering components). SQL constants are non-empty, bind `%s` parameters, and query real catalog tables (`pg_constraint`, `information_schema.sequences`, `information_schema.views`). The `describe` method composes four live DB calls. No static returns, no empty array stubs. Data-flow: FLOWING for all methods.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Mock unit tests (10 tests) | `uv run pytest tests/test_database.py -o addopts="" -q -k "primary_key or foreign_keys or sequences or views or describe"` | 10 passed | PASS |
| Parity tests (26 tests incl. v090 surface) | `PGDATABASE=pycopg_test2 uv run pytest tests/test_parity.py -o addopts="" -q` | 26 passed | PASS |
| Live-DB integration tests (11 tests) | `PGDATABASE=pycopg_test2 uv run pytest tests/test_database_integration.py -o addopts="" -q -k "primary_key or foreign_keys or sequences or views or describe"` | 11 passed | PASS |
| Full targeted suite | `PGDATABASE=pycopg_test2 uv run pytest tests/test_parity.py tests/test_database.py tests/test_database_integration.py -o addopts="" -q -k "primary_key or foreign_keys or sequences or views or describe or accessor_parity or v090"` | 31 passed | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| INTRO-01 | 35-01 | `db.schema.primary_key(table, schema)` returns PK column name(s) | SATISFIED | `schema.py:676-699`; live test `test_primary_key_single_column`, `test_primary_key_composite`, `test_primary_key_no_pk`, `test_primary_key_nonexistent_table` |
| INTRO-02 | 35-01 | `db.schema.foreign_keys(table, schema)` returns FK entries | SATISFIED | `schema.py:701-739`; live test `test_foreign_keys_basic`, `test_foreign_keys_empty`, `test_foreign_keys_nonexistent_table` |
| INTRO-03 | 35-01 | `db.schema.sequences(schema)` returns list of sequences | SATISFIED | `schema.py:741-757`; live test `test_sequences_includes_serial` |
| INTRO-04 | 35-01 | `db.schema.views(schema)` returns list of regular views | SATISFIED | `schema.py:759-775`; live test `test_views_excludes_materialized_view` |
| INTRO-05 | 35-02 | `db.schema.describe(table, schema)` returns consolidated dict | SATISFIED | `schema.py:777-804`; live tests `test_describe_keys_and_composition_equality`, `test_describe_missing_table_returns_empty` |
| INTRO-06 | 35-01 + 35-02 | Every new helper callable identically on AsyncSchemaAccessor | SATISFIED | All 5 async twins at lines 1457-1585; `test_accessor_parity` 26 passed; `test_schema_v090_surface` passed |

**Note:** REQUIREMENTS.md traceability table shows INTRO-01..04 as "Pending" and checkboxes unchecked — this is a pre-existing tooling tracking drift (noted in project memory as recurring across milestones). The implementations and tests are fully present; only the REQUIREMENTS.md administrative state needs updating (Phase 36 release task).

### Anti-Patterns Found

No debt markers (TBD/FIXME/XXX) in `pycopg/queries.py` or `pycopg/schema.py` in phase-35 modified lines. No stub patterns (return null, empty arrays without data source) in phase-35 code. The pre-existing ~35 ruff errors (N818/W291/F841/E722) are in files not modified by this phase and are a pre-existing condition confirmed by project memory.

### Human Verification Required

None. All success criteria are verifiable programmatically and confirmed by running the test suite.

### Gaps Summary

No gaps. All 5 success criteria are verified with substantive, wired, data-flowing implementations and passing tests.

---

_Verified: 2026-06-25T09:00:00Z_
_Verifier: Claude (gsd-verifier)_
