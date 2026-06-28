---
phase: 41-api-homogenization
plan: "01"
subsystem: infra
tags: [deprecation-gate, pytest, filterwarnings, test-scaffold]
dependency_graph:
  requires: []
  provides:
    - "filterwarnings = error::DeprecationWarning gate in pyproject.toml"
    - "tests/test_deprecations.py Wave-0 scaffold (TestExceptionAliases, TestWhereDeprecation, TestKwOnlyEnforcement)"
  affects:
    - "All subsequent pytest runs (gate is now active for full suite)"
    - "Plans 02/03/04 (their test bodies already have homes in test_deprecations.py)"
tech_stack:
  added: []
  patterns:
    - "-W error::DeprecationWarning via [tool.pytest.ini_options] filterwarnings list"
    - "pytest.mark.xfail(strict=False) scaffold pattern for not-yet-implemented test bodies"
key_files:
  created:
    - tests/test_deprecations.py
  modified:
    - pyproject.toml
decisions:
  - "Discovery run showed ZERO third-party DeprecationWarnings at current dep versions; added defensive ignore entries for psycopg, geopandas, pandas per PATTERNS.md (T-41-01 threat mitigation)"
  - "No ignore::DeprecationWarning:pycopg entry added (T-41-01 compliance: gate must catch future pycopg-internal deprecation leaks)"
  - "N818 per-file-ignore block left UNCHANGED (Plan 02 owns it atomically with the rename)"
metrics:
  duration: "~13 minutes"
  completed: "2026-06-28"
  tasks_completed: 2
  tasks_total: 2
  files_created: 1
  files_modified: 1
---

# Phase 41 Plan 01: DeprecationWarning CI Gate + Test Scaffold Summary

**One-liner:** `-W error::DeprecationWarning` pytest gate added to pyproject.toml; `tests/test_deprecations.py` Wave-0 scaffold with 3 test classes and 6 xfail tests.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Discover third-party DeprecationWarnings and add the -W error gate to pyproject.toml | 1abece4 | pyproject.toml |
| 2 | Scaffold tests/test_deprecations.py with the three test classes | 4e98710 | tests/test_deprecations.py |

## What Was Built

### Task 1: pytest filterwarnings gate (`pyproject.toml`)

Added a `filterwarnings` list to `[tool.pytest.ini_options]` with:
- First entry: `"error::DeprecationWarning"` — the D-10 enforcement gate
- Discovery run (2026-06-28): the full suite under `-W error::DeprecationWarning` produced **zero** third-party DeprecationWarning failures at current dependency versions
- Three defensive suppression entries added for `psycopg`, `geopandas`, `pandas` (known upstream emitters that may activate with package updates)
- No `ignore::DeprecationWarning:pycopg` entry — any future pycopg-internal deprecation routing will turn the suite red immediately (T-41-01 compliance)
- N818 per-file-ignore block for `pycopg/exceptions.py` left intact (Plan 02 owns it)

### Task 2: `tests/test_deprecations.py` scaffold

Created the Wave-0 test module with module docstring and xfail cross-reference comments. Three test classes:

- **`TestExceptionAliases`** (3 tests, xfail until Plan 02): tests PEP 562 `__getattr__` behavior — identity assertion (`OldName is NewError`), `DeprecationWarning` emission, catchability
- **`TestWhereDeprecation`** (2 tests, xfail until Plan 03): tests `where=`→`filter=` shim stacklevel (D-09) and `TypeError` on both-supplied conflict
- **`TestKwOnlyEnforcement`** (1 test, xfail until Plan 04): tests positional geom raises `TypeError` (FREEZE-03/D-03)

All 6 tests use **real final assertion bodies** from 41-PATTERNS.md. Only the `@pytest.mark.xfail` markers are temporary. The `w.filename.endswith("test_deprecations.py")` assertions (2 occurrences) are present verbatim for D-09 stacklevel verification.

## Verification Results

- `uv run pytest` (PGDATABASE=pycopg_test2): **1427 passed, 2 skipped, 6 xfailed** — gate is GREEN
- `uv run pytest tests/test_deprecations.py --collect-only -q`: lists **6 test functions** across 3 classes
- `grep -n 'filterwarnings' pyproject.toml`: line 102 confirms gate exists
- `grep 'ignore::DeprecationWarning:pycopg' pyproject.toml`: returns nothing (T-41-01 compliant)
- N818 block at lines 92-96: **unchanged**

## Deviations from Plan

None — plan executed exactly as written. The discovery run confirmed the assumption from PATTERNS.md that no third-party DeprecationWarnings fire at current dep versions; defensive suppressions were added as planned.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. This plan is pure configuration + test scaffold.

## Self-Check: PASSED

- `tests/test_deprecations.py`: FOUND
- `pyproject.toml` `filterwarnings` entry: FOUND (line 102)
- Commit 1abece4 (Task 1): EXISTS
- Commit 4e98710 (Task 2): EXISTS
- Full suite green: CONFIRMED (1427 passed, 6 xfailed, 96.32% coverage)
