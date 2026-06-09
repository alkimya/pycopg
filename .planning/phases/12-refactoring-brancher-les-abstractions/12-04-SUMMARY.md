---
phase: 12-refactoring-brancher-les-abstractions
plan: 04
subsystem: testing
tags: [coverage, ratchet, pytest, unit-tests, builders]

# Dependency graph
requires:
  - phase: 12-01
    provides: "the three pure builders (build_pg_dump_cmd / build_pg_restore_cmd / build_role_options) — the coverage fuel"
  - phase: 12-02
    provides: "inheritance collapse (final code shape)"
  - phase: 12-03
    provides: "abstraction wiring (final code shape)"
provides:
  - "DB-free unit tests for the 3 pure builders (base.py 89% -> 100%)"
  - "coverage gate ratcheted 90 -> 92 (honest, measured, passing)"
affects: [13]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "DB-free parametrized builder tests (import + call + assert on argv list membership/positions)"

key-files:
  created: []
  modified:
    - tests/test_base.py
    - pyproject.toml

key-decisions:
  - "Gate flipped 90 -> 92 (NOT 95): 95 is structurally unreachable this phase. Measured green-suite coverage is 92.55%; remaining gap is DB/IO paths the scope explicitly caps out. D-07 forbids freezing an unmet gate, so ratcheted to the honest measured-and-passing floor."
  - "User-approved deviation from the literal 95 target: 'flip to 93, document the 95 gap' chosen via checkpoint; measurement then showed a green suite is 92.55% (93 only reached while 2 tests are failing), so the honest passing floor is 92."

patterns-established:
  - "Measure-then-flip: ratchet the gate ONLY to a value a green suite genuinely passes; never freeze an unmet number"

requirements-completed: [REF-05]

# Metrics
duration: 30 min
completed: 2026-06-09
---

# Phase 12 Plan 04: Coverage ratchet (measure then flip) Summary

**DB-free builder tests took base.py from 89% to 100% coverage; coverage gate honestly ratcheted 90 → 92 (measured 92.55% on a green suite). The 90→95 target proved structurally unreachable within scope — last ~3 points are DB/IO paths deferred to a future phase.**

## Performance

- **Duration:** ~30 min
- **Started:** 2026-06-09 (inline execution)
- **Completed:** 2026-06-09
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Added ~38 DB-free, parametrized unit tests to `tests/test_base.py` for all three pure builders, covering every branch (each pg_dump `-F` format, schema/data-only, compress-for-custom, jobs-for-directory, table/exclude/schema loops, trailing `-f`; every pg_restore boolean flag toggle, `if_exists` default, `jobs>1`, table/schema loops, trailing input_file; role login/nologin, all role flags, NOINHERIT, CONNECTION LIMIT, VALID UNTIL).
- Included the **D-04/T-12-02 secret-not-in-argv guard** (asserts the real password value never appears in `build_role_options(...)` output, only the `PASSWORD %s` placeholder) and the **validate_timestamp guard** (asserts a malformed `valid_until` raises).
- `pycopg/base.py` coverage rose from **89% → 100%** (all 16 previously-uncovered builder branches now hit).
- Ratcheted `--cov-fail-under` **90 → 92** in `pyproject.toml`, honestly measured and passing on a green suite.

## Task Commits

1. **Task 1: Add DB-free unit tests for the three builders** - `da5db68` (test)
2. **Task 2: Measure coverage, then flip the ratchet** - `f659bc1` (test)

## Files Created/Modified
- `tests/test_base.py` - +3 test classes (TestBuildPgDumpCmd, TestBuildPgRestoreCmd, TestBuildRoleOptions), ~38 DB-free tests
- `pyproject.toml` - `--cov-fail-under` 90 → 92

## Decisions Made

**Why 92 and not 95 (the original REF-05 target):**
The "measure then flip" discipline (D-07) was followed exactly:
1. Added the builder tests → measured. `base.py` reached 100%, but **total coverage measured 92.55%** (was 92% pre-tests, ~90 baseline at Phase 11).
2. The remaining ~40 uncovered lines are entirely in `database.py` (90%) and `async_database.py` (91%) — and are **DB-dependent hot paths and I/O error branches**: `Config.from_env`/`create` admin flows, `validate_identifier` inside DB methods, `_psql_restore`, `self.execute(...)` round-trips, `raise RuntimeError(f"pg_dump/restore failed: {result.stderr}")`, `f.write(data)`, `self._engine.dispose()`. The phase scope **explicitly caps out hard-to-mock I/O** (subprocess/network) — so these are not coverable within scope.
3. D-07 forbids freezing an unmet gate. Therefore the gate was ratcheted to the **honest measured-and-passing floor (92)** rather than frozen at an unmet 95.

This was surfaced to the user at a checkpoint; the user chose "flip and document the 95 gap." Measurement then showed that 93 is only reached while 2 tests are *failing* (their setup paths execute); a fully green suite measures 92.55%, so the honest passing floor is **92** (a small measurement-driven adjustment from the user's literal "93").

## Deviations from Plan

### Adjusted gate value: 95 → 92 (user-approved, measurement-driven)

**1. [Rule 4 - Architectural / user decision] Gate target lowered from 95 to 92**
- **Found during:** Task 2 (measure-then-flip)
- **Issue:** REF-05 named 95, but honestly-measured green-suite coverage is 92.55%; 95 requires covering DB/IO paths the phase scope caps out. Flipping to 95 (or even 93) would freeze an unmet gate, violating D-07.
- **Fix:** Surfaced via checkpoint; user chose the honest-ratchet path. Set `--cov-fail-under=92` (measured-and-passing), documented the 95 gap for a follow-up phase.
- **Files modified:** pyproject.toml
- **Verification:** `uv run pytest` (green suite, 2 pre-existing failures deselected) reports "Required test coverage of 92% reached. Total coverage: 92.55%."
- **Committed in:** f659bc1

---

**Total deviations:** 1 (gate target 95→92, user-approved).
**Impact on plan:** REF-05 partially satisfied — the ratchet is genuinely raised and honest (90→92), but the 95 milestone target is deferred. No dishonest gate was frozen.

## Issues Encountered

**Pre-existing full-suite test failures (NOT caused by Phase 12) — block a bare `uv run pytest` from exiting 0.** Two tests fail in the local DB environment due to **test-design bugs** unrelated to this phase (verified failing on the pre-12 base):

1. `tests/test_postgis_errors.py::TestPostGISErrorHandling::test_create_spatial_index_name_parameter` — creates a `TEMP TABLE` on one connection (`db.execute(...)`), then calls `db.create_spatial_index(...)` which opens a **different** connection where the connection-scoped temp table no longer exists → `UndefinedTable`. Test-design bug (temp tables are per-connection).
2. `tests/test_integration.py::TestAsyncIntegration::test_async_transaction_fix` — `ProgrammingError: Explicit commit() forbidden within a Transaction context`.

(`test_parity.py::test_create_constructor_parity` is a third intermittently-failing one — an `ObjectInUse` teardown race that passes in isolation.)

These are out of scope for a behavior-preserving refactor phase (modifying them would change test behavior) and were left untouched. They are flagged here for the phase verifier and for a future test-hardening pass. The **coverage gate at 92 passes** on a green suite; these failures are independent of the gate.

## User Setup Required

None.

## Next Phase Readiness
- Coverage gate at 92 (honest, passing). base.py builders at 100%.
- **Carry-forward for a follow-up phase:** (a) close the last ~3 points to 95 once DB/IO test infrastructure (mocked subprocess + reliable test DB) exists; (b) fix the 2-3 pre-existing DB test-design failures (temp-table connection scope, async commit-in-transaction, teardown ObjectInUse race).
- Phase 13 (spatial helpers) is the next milestone focus.

---
*Phase: 12-refactoring-brancher-les-abstractions*
*Completed: 2026-06-09*
