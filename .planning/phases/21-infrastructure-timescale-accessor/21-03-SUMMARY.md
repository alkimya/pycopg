---
phase: 21-infrastructure-timescale-accessor
plan: "03"
subsystem: timescale-accessor
tags: [test, alias, parity, migration, deprecated, coverage, reorg]
dependency_graph:
  requires:
    - plan-01 (pycopg.aliases.deprecated_alias + pycopg.timescale.TimescaleAccessor + AsyncTimescaleAccessor)
    - plan-02 (Database.timescale lazy property + 6 deprecated_alias stubs)
  provides:
    - tests/test_timescale_aliases.py (TestTimescaleAliases — D-09)
    - ACCESSOR_PAIRS registry + test_accessor_parity (D-10)
    - 27 migrated call-sites across 3 test files (D-08)
  affects:
    - Full suite coverage gate (held at 94.46%)
    - pytest -W error::DeprecationWarning gate (REORG-04)
tech_stack:
  added: []
  patterns:
    - warnings.catch_warnings(record=True) + simplefilter("always") for DeprecationWarning assertion
    - MagicMock(spec=TimescaleAccessor) injected via db._timescale for DB-free alias tests
    - AsyncMock per-method injection for async alias tests
    - ACCESSOR_PAIRS registry pattern — parametrized both-direction parity test
key_files:
  created:
    - tests/test_timescale_aliases.py
  modified:
    - tests/test_parity.py
    - tests/test_database_integration.py
    - tests/test_async_database.py
    - tests/test_sql_injection.py
decisions:
  - "Used basename comparison (basename != 'aliases.py') rather than substring check for stacklevel proof — test filename test_timescale_aliases.py contains 'aliases.py' as substring, so substring check would always fail"
  - "Folded TestEtlParity into ACCESSOR_PAIRS registry — zero behavior change, cleaner registry for phases 22-24"
  - "Full suite run from worktree (uv sync --all-extras --dev to get geopandas) needed because worktree .venv lacked extras on startup"
metrics:
  duration: "12 minutes"
  completed: "2026-06-17T13:00:00Z"
  tasks_completed: 3
  files_created: 1
  files_modified: 4
---

# Phase 21 Plan 03: Test Coverage, Parity Registry & Call-Site Migration Summary

Completes Phase 21 by delivering the full test + coverage layer: per-alias warn+delegate tests (D-09), data-driven ACCESSOR_PAIRS parity registry seeded with (TimescaleAccessor, AsyncTimescaleAccessor) (D-10), and migration of all 27 existing timescale call-sites to db.timescale.* (D-08 / REORG-04).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create tests/test_timescale_aliases.py — per-alias warn+delegate (D-09) | 5386ab6 | tests/test_timescale_aliases.py |
| 2 | Add ACCESSOR_PAIRS parity registry to test_parity.py (D-10) | c5d3e81 | tests/test_parity.py |
| 3 | Migrate 27 call-sites + final no-noise / coverage gate (D-08, REORG-04) | 955e070 | tests/test_database_integration.py, tests/test_async_database.py, tests/test_sql_injection.py |

## What Was Built

### Task 1: `tests/test_timescale_aliases.py`

New file `TestTimescaleAliases` with two parametrized tests:

- `test_sync_alias_warns_and_delegates` — 6 variants (one per flat alias)
  - Creates `Database(config)`, injects `MagicMock(spec=TimescaleAccessor)` via `db._timescale`
  - Asserts: exactly 1 `DeprecationWarning`, message contains `db.timescale.<name>` + `v0.7.0`
  - Asserts stacklevel: `os.path.basename(w[0].filename) != "aliases.py"` AND `!= "database.py"` (Footgun 2 proof)
  - Asserts delegation: `mock_accessor.<name>.assert_called_once_with(*args)`

- `test_async_alias_warns_and_delegates` — 6 variants (one per async alias)
  - Creates `AsyncDatabase(config)`, injects `MagicMock(spec=AsyncTimescaleAccessor)` with per-method `AsyncMock` 
  - Same assertions adapted for async path

Key deviation found during implementation: the basename check `"aliases.py" not in w[0].filename` was using substring matching on the full path, which matched `test_timescale_aliases.py`. Fixed by checking `os.path.basename(w[0].filename) != "aliases.py"` (exact filename comparison).

### Task 2: `tests/test_parity.py`

Added:
- `from pycopg.timescale import AsyncTimescaleAccessor, TimescaleAccessor`
- `ACCESSOR_PAIRS = [(TimescaleAccessor, AsyncTimescaleAccessor), (ETLAccessor, AsyncETLAccessor)]`
- `test_accessor_parity(sync_cls, async_cls)` — parametrized, checks BOTH directions (missing-in-async + extra-in-async)

Removed: `TestEtlParity` class (folded into registry — identical logic, zero behavior change).

### Task 3: 27 call-site migrations

Mechanical `db.<m>(...)` → `db.timescale.<m>(...)` rewrites:

| File | Sites migrated |
|------|---------------|
| `tests/test_database_integration.py` | 6 (create_hypertable, hypertable_info, list_hypertables, enable_compression, add_compression_policy, add_retention_policy) |
| `tests/test_async_database.py` | 18 (TestAsyncDatabaseTimescaleDB × 15 + async integration × 3) |
| `tests/test_sql_injection.py` | 4 (sync/async add_compression_policy + add_retention_policy) |

All injection tests still raise `InvalidIdentifier` — the `validate_*` guards in the accessor body are intact (T-21-02 verified).

## Verification Results

```
uv run pytest tests/test_timescale_aliases.py tests/test_parity.py -x -q -o addopts=""
→ 31 passed

uv run pytest -W error::DeprecationWarning -q -o addopts=""
  tests/test_async_database.py tests/test_sql_injection.py
  tests/test_parity.py tests/test_timescale_aliases.py
→ 295 passed (REORG-04 no-noise gate GREEN)

uv run pytest -q (full suite — worktree)
→ 994 passed, 2 failed (pre-existing), 2 skipped
→ Total coverage: 94.46% ≥ 94% (PASS)

uv run ruff check tests/test_timescale_aliases.py tests/test_parity.py
→ All checks passed

grep -c 'mocker' tests/test_timescale_aliases.py
→ 0 (stdlib unittest.mock only — confirmed)

grep -rEc '(await )?(ts_db|db|sync_db|async_db)\.(create_hypertable|...)(...)'
  tests/test_database_integration.py tests/test_async_database.py tests/test_sql_injection.py
→ 0 (no remaining flat calls in migrated files)

grep -c 'filterwarnings' pyproject.toml
→ 0 (unchanged — no suppressions added)
```

## Full Suite Results

**Known pre-existing failures (NOT regressions from plan-03):**
- `tests/test_integration.py::TestAsyncIntegration::test_async_transaction_fix` — pre-existing UndefinedTable transaction error
- `tests/test_postgis_errors.py::TestPostGISErrorHandling::test_create_spatial_index_name_parameter` — pre-existing UndefinedTable fixture-isolation bug

**Full `-W error::DeprecationWarning` note:**
The full suite under `-W error::DeprecationWarning` also shows pool test failures from `psycopg_pool`'s own DeprecationWarning (about the `open` parameter default change). This is a pre-existing issue in the main workspace that predates this plan — it is from a third-party library, not from pycopg code. The plan's verification gate specifies running against the specific migrated files only, which passes cleanly.

## Acceptance Criteria Check

| Criterion | Result |
|-----------|--------|
| `class TestTimescaleAliases` in test_timescale_aliases.py | PASS |
| ≥12 test cases (6 sync + 6 async) | PASS (12) |
| Message contains `db.timescale.<m>` + `v0.7.0` | PASS |
| stacklevel proof: basename != "aliases.py" AND != "database.py" | PASS |
| delegation: `assert_called_once_with(*args)` | PASS |
| `grep -c 'mocker' tests/test_timescale_aliases.py` == 0 | PASS (0) |
| `ruff check tests/test_timescale_aliases.py` exits 0 | PASS |
| `grep -c 'ACCESSOR_PAIRS' tests/test_parity.py` ≥ 2 | PASS (3) |
| (TimescaleAccessor, AsyncTimescaleAccessor) is first entry | PASS |
| test_accessor_parity checks BOTH directions | PASS |
| `grep -c 'class TestEtlParity' tests/test_parity.py` == 0 | PASS (0) |
| (ETLAccessor, AsyncETLAccessor) in ACCESSOR_PAIRS | PASS |
| `ruff check tests/test_parity.py` exits 0 | PASS |
| All 27 flat call-sites migrated (grep check == 0) | PASS (0) |
| Injection tests still pass (T-21-02) | PASS |
| `-W error::DeprecationWarning` gate (migrated test files) | PASS (295 passed) |
| Full suite coverage ≥ 94% | PASS (94.46%) |
| `grep -c 'filterwarnings' pyproject.toml` unchanged (0) | PASS |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed stacklevel assertion using substring vs. exact basename comparison**
- **Found during:** Task 1 — test run immediately after writing the file
- **Issue:** `"aliases.py" not in w[0].filename` matched the full path which contains `test_timescale_aliases.py`, so the assertion always failed
- **Fix:** Changed to `os.path.basename(w[0].filename) != "aliases.py"` (exact basename comparison)
- **Files modified:** tests/test_timescale_aliases.py
- **Commit:** 5386ab6 (included in task commit)

**2. [Rule 3 - Blocking Issue] Synced worktree .venv to install geopandas/extras**
- **Found during:** Full suite run (Task 3 verification)
- **Issue:** Worktree `.venv` did not have `geopandas`, `python-dotenv`, and other extras — causing 14 extra failures from unrelated tests (GeoDataFrame, dotenv, spatial)
- **Fix:** `uv sync --all-extras --dev` from worktree directory (7 packages installed)
- **Commit:** No commit needed (environment fix only)

None other — plan executed as designed.

## Known Stubs

None — all test migrations are functional (call the real accessor path). No placeholder data flows.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced.

T-21-02 verified: SQL injection tests migrated and still raise `InvalidIdentifier` on evil inputs.
T-21-04 mitigated: all 27 call-sites migrated; `-W error::DeprecationWarning` passes for the migrated test files.

## Self-Check: PASSED

Files exist:
- tests/test_timescale_aliases.py — FOUND
- tests/test_parity.py (ACCESSOR_PAIRS) — FOUND
- .planning/phases/21-infrastructure-timescale-accessor/21-03-SUMMARY.md — FOUND (this file)

Commits exist:
- 5386ab6 (test(21-03): create test_timescale_aliases.py) — FOUND
- c5d3e81 (feat(21-03): add ACCESSOR_PAIRS parity registry) — FOUND
- 955e070 (refactor(21-03): migrate 27 timescale call-sites) — FOUND
