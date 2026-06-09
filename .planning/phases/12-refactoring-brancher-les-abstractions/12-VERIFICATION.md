---
phase: 12-refactoring-brancher-les-abstractions
verified: 2026-06-09T00:00:00Z
status: passed
score: 5/5
overrides_applied: 1
overrides:
  - must_have: "Coverage ratchet raised to 95% (--cov-fail-under=95)"
    reason: "D-07 'measure then flip' — green-suite coverage measured 92.55%; remaining ~3 points are DB/IO paths (subprocess, engine.dispose, runtime error branches) explicitly capped out of scope. Gate honestly ratcheted to 92 (measured-and-passing floor). Deviation user-approved at checkpoint. 95 target deferred to a future phase. Verify HONEST (gate matches measured-and-passing reality), not 95."
    accepted_by: "loc"
    accepted_at: "2026-06-09T00:00:00Z"
re_verification: null
gaps: []
---

# Phase 12: Refactoring — Brancher les Abstractions — Verification Report

**Phase Goal:** Eliminate duplication by wiring `base.py` and `queries.py` into Database/AsyncDatabase; coverage ratchet raised to 95 (honestly).
**Verified:** 2026-06-09
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | ~25 inline SQL strings replaced by `queries.*` constants (single source of SQL truth) | VERIFIED | `grep -c 'queries\.'` returns 28 (database.py) and 29 (async_database.py); pre-phase baseline was 3 per file |
| 2 | `Database(DatabaseBase, QueryMixin)` and `AsyncDatabase(DatabaseBase, QueryMixin)`; concrete `from_env`/`from_url`/`__repr__` gone from subclasses; batch INSERT via `_build_batch_insert_sql` | VERIFIED | Both class declarations confirmed; `def from_env/from_url/__repr__` count = 0 in each subclass; `_build_batch_insert_sql` called once in each |
| 3 | Three pure builders in base.py; DB-free unit-tested | VERIFIED | `build_pg_dump_cmd`, `build_pg_restore_cmd`, `build_role_options` exist as module-level functions; 62 DB-free tests pass including all builder branches |
| 4 | Dead code removed (`*_SIMPLE` constants, Phase-3 comments, unread `stdout`, no-op try/except) | VERIFIED | `TABLE_INFO_SIMPLE`/`LIST_ROLES_SIMPLE` absent from all files; "available in Phase 3" absent from async_database.py; `stdout, stderr = await` replaced by `_, stderr = await` at 3 sites; no-op try/except removed; `import re` confirmed already absent |
| 5 | Coverage gate raised honestly (gate value matches measured-and-passing reality) | PASSED (override) | `pyproject.toml` gate = `--cov-fail-under=92`; measured green-suite coverage 92.55%; gate matches measured floor per D-07. Override: 95 target deferred — DB/IO paths structurally uncoverable within scope |

**Score:** 5/5 truths verified (1 with user-approved override)

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/base.py` | 3 module-level pure builders | VERIFIED | `build_pg_dump_cmd`, `build_pg_restore_cmd`, `build_role_options` present; no self, no I/O, no PGPASSWORD |
| `pycopg/database.py` | `class Database(DatabaseBase, QueryMixin)` with builders imported | VERIFIED | Inheritance confirmed; builders imported at lines 34-36; `super().__init__(config)` called |
| `pycopg/async_database.py` | `class AsyncDatabase(DatabaseBase, QueryMixin)` with builders imported | VERIFIED | Inheritance confirmed; builders imported at lines 33-35; `async_engine` property preserved |
| `pycopg/queries.py` | `TABLE_INFO_SIMPLE` and `LIST_ROLES_SIMPLE` removed | VERIFIED | grep returns 0 matches across all files; canonical `TABLE_INFO` and `LIST_ROLES` intact |
| `tests/test_base.py` | DB-free unit tests for 3 builders | VERIFIED | 3 test classes (TestBuildPgDumpCmd, TestBuildPgRestoreCmd, TestBuildRoleOptions), ~38 parametrized tests covering all branches |
| `pyproject.toml` | Coverage gate raised and passing | VERIFIED | `--cov-fail-under=92`; honest measured-and-passing value (see override above) |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `pycopg/database.py` | `pycopg.base.build_pg_dump_cmd` | import + call at line 2225 | WIRED | `subprocess.run` I/O shell preserved at lines 2243+ |
| `pycopg/database.py` | `pycopg.base.build_pg_restore_cmd` | import + call at line 2302 | WIRED | `subprocess.run` I/O shell preserved |
| `pycopg/database.py` | `pycopg.base.build_role_options` | import + call at line 1874 | WIRED | `validate_identifier(name)` preserved in method body |
| `pycopg/async_database.py` | `pycopg.base.build_pg_dump_cmd` | import + call at line 2184 | WIRED | `asyncio.create_subprocess_exec` I/O shell preserved |
| `pycopg/async_database.py` | `pycopg.base.build_pg_restore_cmd` | import + call at line 2267 | WIRED | `asyncio.create_subprocess_exec` I/O shell preserved |
| `pycopg/async_database.py` | `pycopg.base.build_role_options` | import + call at line 1309 | WIRED | validation preserved |
| `pycopg/database.py::insert_many` | `QueryMixin._build_batch_insert_sql` | inherited + called (1 occurrence) | WIRED | Returns `(sql, flat_params)`; executed via `cursor.execute` |
| `pycopg/async_database.py::insert_many` | `QueryMixin._build_batch_insert_sql` | inherited + called (1 occurrence) | WIRED | Same pattern, async execute |
| `pycopg/database.py` | `queries.*` constants | `import pycopg.queries` + call sites | WIRED | 28 references; TABLE_INFO, LIST_ROLES, LIST_GEOMETRY_COLUMNS, HYPERTABLE_INFO, etc. |
| `pycopg/async_database.py` | `queries.TABLE_INFO` / `queries.LIST_ROLES` | `queries.TABLE_INFO` / `.format(where_clause=...)` | WIRED | D-05 async routing confirmed |
| `tests/test_base.py` | `pycopg.base.build_pg_dump_cmd` | import + call + assert | WIRED | 62 tests pass; secret-not-in-argv guard present |

---

## Behavior Preservation (D-06)

| Check | Status | Evidence |
|-------|--------|----------|
| Factory methods return correct subclass | VERIFIED | `Database.from_url(...)` returns `Database('d' @ h:5432)`; `AsyncDatabase.from_url(...)` returns `AsyncDatabase('d' @ h:5432)` |
| PGPASSWORD stays in method bodies, not builders | VERIFIED | `grep PGPASSWORD pycopg/base.py` returns 0; database.py and async_database.py each have 4 occurrences (env injection in method bodies) |
| `validate_identifier` count not reduced | VERIFIED | database.py: 63 calls (drop of 2 is the documented and expected subsuming of 2 explicit calls into `_build_batch_insert_sql`'s `validate_identifiers(table, schema, *columns)` — net-equivalent protection); async_database.py: 64 calls |
| Intentional `except ValueError: raise` preserved | VERIFIED | Lines 1387 (database.py) and 1823 (async_database.py) — both confirmed present; they prevent `except Exception` below from masking ValueError |
| Async I/O shell unchanged | VERIFIED | `asyncio.create_subprocess_exec` at 3 sites in async_database.py; `subprocess.run` at 3 sites in database.py |
| 129 DB-free + injection tests pass | VERIFIED | `uv run pytest tests/test_base.py tests/test_sql_injection.py -q -o addopts=""` → 129 passed |

---

## Validation Preservation (Security)

| Check | Status | Evidence |
|-------|--------|----------|
| `validate_timestamp` called inside `build_role_options` | VERIFIED | Line 418 of base.py; test asserts malformed `valid_until` raises |
| `validate_identifier(name)` preserved in `create_role` | VERIFIED | Present in both database.py and async_database.py `create_role` method bodies |
| `_build_batch_insert_sql` calls `validate_identifiers(table, schema, *columns)` | VERIFIED | base.py line 115; injection tests green |
| SQL injection tests pass | VERIFIED | 67 injection tests pass |
| `PASSWORD %s` placeholder only; real secret not in builder output | VERIFIED | `build_role_options(password="s3cr3t")` returns `"PASSWORD %s"` and asserts real value absent |

---

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Builders importable as module-level functions | `from pycopg.base import build_pg_dump_cmd, build_pg_restore_cmd, build_role_options` | ImportError absent | PASS |
| Factory returns correct subclass | `Database.from_url('postgresql://u:p@h:5432/d')` repr | `Database('d' @ h:5432)` | PASS |
| AsyncDatabase factory returns correct subclass | `AsyncDatabase.from_url('postgresql://u:p@h:5432/d')` repr | `AsyncDatabase('d' @ h:5432)` | PASS |
| DB-free builder tests pass (62 tests) | `uv run pytest tests/test_base.py -q -o addopts=""` | 62 passed in 0.05s | PASS |
| Injection tests pass (67 tests) | `uv run pytest tests/test_sql_injection.py -q -o addopts=""` | 67 passed | PASS |
| Coverage gate value honest | `grep cov-fail-under pyproject.toml` | `--cov-fail-under=92` | PASS |

---

## Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| REF-01 | ~25 inline SQL strings replaced by `queries.py` constants | SATISFIED | 28 queries references in database.py, 29 in async_database.py (up from 3 each) |
| REF-02 | Database and AsyncDatabase inherit (DatabaseBase, QueryMixin); `from_env`/`from_url`/`__repr__` and batch-insert builder lifted up | SATISFIED | Both class declarations confirmed; `_build_batch_insert_sql` wired in both |
| REF-03 | Pure stateless builders extracted and unit-tested without DB | SATISFIED | 3 builders in base.py; 38 DB-free parametrized tests in test_base.py |
| REF-04 | Residual dead code removed | SATISFIED | `*_SIMPLE` constants gone; Phase-3 comments gone; `_, stderr` replacements made; no-op try/except removed |
| REF-05 | Coverage ratchet raised and passing (honestly) | SATISFIED (override) | Gate at 92 (measured-and-passing floor); D-07 respected; 95 deferred |

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `pyproject.toml` (ruff config) | — | Deprecated top-level `select`/`ignore` keys (ruff warning) | Info | Pre-existing; not introduced by Phase 12; ruff still passes cleanly on all modified files |

No `TBD`, `FIXME`, `XXX` markers found in any Phase 12-modified file. No stub returns. No hardcoded empty data structures in production paths.

---

## Pre-existing Issues (NOT Phase 12 Regressions)

The following three test failures exist in the full DB suite and are documented as pre-existing from before Phase 12. They are **explicitly out of scope** for this behavior-preserving refactor:

1. `tests/test_postgis_errors.py::TestPostGISErrorHandling::test_create_spatial_index_name_parameter` — temp-table connection-scope test design bug (UndefinedTable); pre-existing.
2. `tests/test_integration.py::TestAsyncIntegration::test_async_transaction_fix` — ProgrammingError: commit forbidden in transaction context; pre-existing.
3. `tests/test_parity.py::TestBehavioralParity::test_create_constructor_parity` — intermittent ObjectInUse teardown race; passes in isolation; pre-existing.

These are **not counted** as Phase 12 regressions.

---

## Human Verification Required

None. All must-haves are mechanically verifiable. The refactor is behavior-preserving (no new user-facing features, no UI changes). DB-dependent test coverage is the only gap and is documented as a known limitation of the honest ratchet at 92.

---

## Gaps Summary

No gaps blocking goal achievement. All five requirements are satisfied:

- REF-01, REF-02, REF-03, REF-04: fully verified by code inspection and test execution.
- REF-05: satisfied with one user-approved override — the gate is honest (92 = measured green-suite floor per D-07) rather than frozen at an unmet 95. The 95 target is deferred to a future phase once DB/IO test infrastructure (mocked subprocess, reliable test DB) exists.

The phase goal — eliminating duplication by wiring base.py and queries.py into Database/AsyncDatabase — is demonstrably achieved in the codebase.

---

_Verified: 2026-06-09_
_Verifier: Claude (gsd-verifier)_
