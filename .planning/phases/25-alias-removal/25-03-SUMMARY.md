---
phase: 25-alias-removal
plan: "03"
subsystem: test-layer
tags: [alias-removal, test-cleanup, attribute-error, wr-01, tdd]
dependency_graph:
  requires: ["25-01", "25-02"]
  provides: ["ALIAS-RM-01", "ALIAS-RM-02", "ALIAS-RM-04"]
  affects: ["tests/test_alias_removal.py"]
tech_stack:
  added: []
  patterns: ["parametrized-pytest", "inspect-signature-assertion", "bare-config-fixture"]
key_files:
  created: ["tests/test_alias_removal.py"]
  modified: []
  deleted:
    - "pycopg/aliases.py"
    - "tests/test_admin_aliases.py"
    - "tests/test_maint_aliases.py"
    - "tests/test_schema_aliases.py"
    - "tests/test_backup_aliases.py"
    - "tests/test_timescale_aliases.py"
    - "tests/test_spatial_aliases.py"
decisions:
  - "Bare config fixture (no psycopg mock) for AttributeError tests — attribute lookup fails before connection"
  - "REMOVED_FLAT_NAMES hardcoded (56 entries) — not derived at runtime per D-05 and RESEARCH §Open Questions #2"
  - "Pool DeprecationWarning gate failures are pre-existing (psycopg_pool library) — not introduced by this plan"
metrics:
  duration: "4 minutes"
  completed: "2026-06-19"
  tasks_completed: 2
  files_changed: 7
---

# Phase 25 Plan 03: Delete aliases.py + alias tests, add test_alias_removal.py Summary

**One-liner:** Hard-delete `pycopg/aliases.py` and 6 warn+delegate alias test files; add 114-test `test_alias_removal.py` proving all 56 removed flat names raise `AttributeError` on Database/AsyncDatabase plus WR-01 inspect assertions.

## What Was Built

This plan completed the test-layer side of the alias removal:

1. **Deleted `pycopg/aliases.py`** — the `deprecated_alias` decorator module. Both importers (`database.py`, `async_database.py`) had their `from pycopg.aliases import deprecated_alias` lines removed in plans 25-01 and 25-02. No remaining consumers. Package imports cleanly with no `ModuleNotFoundError`.

2. **Deleted 6 warn+delegate alias test files** — `test_admin_aliases.py`, `test_maint_aliases.py`, `test_schema_aliases.py`, `test_backup_aliases.py`, `test_timescale_aliases.py`, `test_spatial_aliases.py`. These tested the old warn+delegate behavior that no longer exists. 1,184 lines removed.

3. **Created `tests/test_alias_removal.py`** — the positive proof test:
   - `REMOVED_FLAT_NAMES`: hardcoded list of exactly 56 names (verified via AST parse)
   - 112 parametrized `pytest.raises(AttributeError)` tests — 56 for `Database`, 56 for `AsyncDatabase`
   - 2 WR-01 `inspect` assertion tests — `test_no_varargs_on_database_public_surface` and `test_no_varargs_on_async_database_public_surface` verify no public method retains `*args/**kwargs`
   - Uses bare `config` fixture (no psycopg patch) per PATTERNS.md — attribute lookup fails before any connection attempt
   - 114 tests, all green

## Commits

| Hash | Message | Files |
|------|---------|-------|
| `6d833ff` | chore(25-03): delete aliases.py and 6 warn+delegate alias test files | 7 deleted |
| `fc9a425` | test(25-03): add test_alias_removal.py — AttributeError proof for 56 names + WR-01 | 1 created |

## Verification Results

| Check | Result |
|-------|--------|
| `test ! -f pycopg/aliases.py` | PASS |
| `grep -rq deprecated_alias pycopg/` | PASS (no matches) |
| `ls tests/test_*_aliases.py \| wc -l` | 0 |
| `test -f tests/test_sql_injection.py` | PASS (preserved) |
| `test -f tests/test_parity.py` | PASS (preserved, unmodified) |
| `uv run python -c "import pycopg"` | PASS |
| `uv run pytest tests/test_alias_removal.py -q -o addopts=""` | 114 passed |
| `uv run pytest tests/test_parity.py -q -o addopts=""` | 24 passed |
| `REMOVED_FLAT_NAMES` count (AST parse) | 56 |
| `uv run ruff check tests/test_alias_removal.py` | All checks passed |

## Deviations from Plan

### Pre-existing DeprecationWarning gate failures (out of scope)

The plan's verification includes `uv run pytest -W error::DeprecationWarning tests/ -o addopts=""`. This gate fails in the full test suite — but NOT due to our changes. The failures originate from `psycopg_pool` (third-party library) emitting a `DeprecationWarning` about the `ConnectionPool 'open' parameter` default changing. These failures affect `test_pool_stress.py`, `test_pool_commit.py`, and `test_integration.py::test_async_transaction_fix` — all pre-existing DB/pool tests documented in STATE.md as flaky pre-existing failures.

The DeprecationWarning gate passes cleanly for all alias-removal-related and non-pool tests (420 tests green when scoped to `test_alias_removal.py`, `test_parity.py`, `test_database.py`, `test_async_database.py`). No DeprecationWarning is emitted by any code written or modified in this plan.

**Tracking:** `[Out of Scope]` — pre-existing `psycopg_pool` library DeprecationWarning in test_pool_stress.py/test_pool_commit.py

## Decisions Made

1. **Bare config fixture, no psycopg mock** — PATTERNS.md explicitly overrides the RESEARCH.md template which included a `patch("pycopg.database.psycopg")` wrapper. The `AttributeError` is raised at Python attribute lookup, before any connection attempt. No mock needed.

2. **Hardcoded REMOVED_FLAT_NAMES list** — Per RESEARCH.md §Open Questions #2, the list is hardcoded rather than derived at runtime. This makes the test self-documenting and prevents accidental growth.

3. **Wave 2 post-removal tree** — The tests are designed to PASS in the post-removal tree (Wave 2, after plans 25-01/25-02). In a pre-removal tree, these tests would FAIL because the flat names would resolve to the deprecated stubs rather than raising AttributeError. This is the correct TDD wave-2 behavior.

## Known Stubs

None — no stubs were introduced. This plan only deletes code and adds AttributeError-proof tests.

## Threat Flags

No new security-relevant surface introduced. This plan only deletes files and adds test assertions.

## Self-Check: PASSED

- `tests/test_alias_removal.py` exists: CONFIRMED
- `pycopg/aliases.py` absent: CONFIRMED
- All 6 alias test files absent: CONFIRMED
- Commits `6d833ff` and `fc9a425` exist: CONFIRMED
- 114 tests green: CONFIRMED
