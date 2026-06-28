---
phase: 41-api-homogenization
plan: "02"
subsystem: exceptions
tags: [exception-rename, pep-562, deprecated-alias, n818, freeze-02, d-07, d-09, d-10]
dependency_graph:
  requires:
    - "41-01 (filterwarnings=-W error::DeprecationWarning gate)"
  provides:
    - "pycopg.exceptions.ExtensionNotAvailableError (canonical)"
    - "pycopg.exceptions.TableNotFoundError (canonical)"
    - "pycopg.exceptions.InvalidIdentifierError (canonical)"
    - "pycopg.exceptions.DatabaseExistsError (canonical)"
    - "pycopg.exceptions.__getattr__ (PEP 562 deprecated-alias resolver, _DEPRECATED_NAMES map)"
    - "pycopg.__getattr__ (package-level deprecated-alias resolver, _DEPRECATED_PACKAGE_ALIASES map)"
    - "Removal of [tool.ruff.lint.per-file-ignores] N818 suppression from pyproject.toml"
  affects:
    - "All internal pycopg/ raise sites (now use *Error names)"
    - "All test files (now import *Error canonical names)"
    - "ruff N818 gate (now enforced — no suppression)"
tech_stack:
  added: []
  patterns:
    - "PEP 562 module-level __getattr__ for deprecated exception alias resolution"
    - "stacklevel=2 DeprecationWarning (D-09: points to caller, not exceptions.py)"
    - "same-object guarantee: globals()[new_name] returns the *Error class object (D-07)"
    - "package-level __getattr__ in __init__.py for pycopg.OldName access"
key_files:
  created: []
  modified:
    - pycopg/exceptions.py
    - pycopg/__init__.py
    - pyproject.toml
    - tests/test_deprecations.py
    - pycopg/utils.py
    - pycopg/schema.py
    - pycopg/database.py
    - pycopg/async_database.py
    - pycopg/timescale.py
    - pycopg/spatial.py
    - pycopg/etl.py
    - pycopg/base.py
    - tests/test_exceptions.py
    - tests/test_utils.py
    - tests/test_base.py
    - tests/test_etl.py
    - tests/test_timescale.py
    - tests/test_audit_37_fixes.py
    - tests/test_async_database.py
    - tests/test_spatial.py
    - tests/test_database.py
    - tests/test_database_integration.py
    - tests/test_sql_injection.py
decisions:
  - "Atomic Task 1+2 interleaving: Task 1's Green phase required Task 2 changes upfront because the -W error gate immediately turns DeprecationWarnings from internal imports into errors; Task 1 was committed first (exceptions.py/__init__.py/pyproject.toml/test_deprecations.py), Task 2 committed next (all internal files + test files)"
  - "import warnings as _warnings moved to top of exceptions.py to fix ruff E402 (Module level import not at top)"
  - "from pycopg import exceptions placed first in __init__.py import block (alphabetical order per ruff I001)"
metrics:
  duration: "~40 minutes"
  completed: "2026-06-28"
  tasks_completed: 2
  tasks_total: 2
  files_created: 0
  files_modified: 23
---

# Phase 41 Plan 02: Exception Rename + PEP 562 Aliases Summary

**One-liner:** 4 N818-violating exception classes renamed to `*Error` convention with PEP 562 `__getattr__` deprecated aliases; all internal raise sites updated; N818 ruff suppression removed.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Rename exceptions, add PEP 562 __getattr__ aliases, fix __init__.py, remove N818 suppression | f61f20f | exceptions.py, __init__.py, pyproject.toml, test_deprecations.py |
| 2 | Update all internal raise sites, imports, docstrings; update existing tests | fa59485 | 19 source + test files |

## What Was Built

### Task 1: Exception Rename + PEP 562 Aliases

**`pycopg/exceptions.py`:**
- 4 class renames: `ExtensionNotAvailable`→`ExtensionNotAvailableError`, `TableNotFound`→`TableNotFoundError`, `InvalidIdentifier`→`InvalidIdentifierError`, `DatabaseExists`→`DatabaseExistsError`
- Added `import warnings as _warnings` at top (E402 compliance)
- Added `_DEPRECATED_NAMES: dict[str, str]` mapping old→new names
- Added `def __getattr__(name: str) -> type` (PEP 562) with `stacklevel=2` (D-09) pointing at caller; returns `globals()[new]` (same class object — D-07)

**`pycopg/__init__.py`:**
- Changed `from pycopg.exceptions import DatabaseExists, ExtensionNotAvailable, InvalidIdentifier, TableNotFound` to the 4 `*Error` canonical names (Pitfall 2 cleared — no ImportError at package init)
- Added `from pycopg import exceptions` for the package `__getattr__` resolver
- Added `_DEPRECATED_PACKAGE_ALIASES` + `def __getattr__(name: str)` for `pycopg.OldName` access (stacklevel=2)
- Added 4 `*Error` names to `__all__`; kept 4 old names in `__all__` with deprecation comment
- `python -c "import pycopg"` exits 0 confirmed

**`pyproject.toml`:**
- Removed `[tool.ruff.lint.per-file-ignores]` block entirely (the N818 suppression for `pycopg/exceptions.py` was the only key; empty table header also removed)
- `uv run ruff check pycopg/exceptions.py` passes; `grep -n 'N818' pyproject.toml` returns nothing

**`tests/test_deprecations.py`:**
- Removed 3 `@pytest.mark.xfail` markers from `TestExceptionAliases` (scaffolded in Plan 01)
- All 3 tests now PASS: `test_exception_alias_same_object`, `test_exception_alias_warns_on_access`, `test_old_exception_name_still_catchable`

### Task 2: Internal Raise Sites + Tests Updated

**Source files updated (raise sites + imports):**
- `pycopg/utils.py`: 14 `raise InvalidIdentifier` → `raise InvalidIdentifierError`; import updated; docstrings updated
- `pycopg/timescale.py`: 30 `raise ExtensionNotAvailable` → `raise ExtensionNotAvailableError`; import updated; docstrings updated
- `pycopg/schema.py`: 2 `raise TableNotFound` → `raise TableNotFoundError`; import updated; docstrings updated
- `pycopg/database.py`: 1 `raise DatabaseExists` + 1 `raise ExtensionNotAvailable` → `*Error`; import updated; docstrings updated
- `pycopg/async_database.py`: same as database.py (sync/async parity D-11)
- `pycopg/spatial.py`: 2 `raise ExtensionNotAvailable` → `raise ExtensionNotAvailableError`; import updated; docstrings updated; **`validate_identifiers` count confirmed 27 (unchanged — T-41-03)**
- `pycopg/etl.py`: docstring-only updates (numpydoc `Raises:` sections; no raise sites)
- `pycopg/base.py`: docstring-only update (numpydoc `Raises:` section)

**Test files updated (imports + pytest.raises):**
- `tests/test_exceptions.py`, `tests/test_utils.py`, `tests/test_base.py`, `tests/test_etl.py`, `tests/test_timescale.py`, `tests/test_audit_37_fixes.py`, `tests/test_async_database.py`, `tests/test_spatial.py`, `tests/test_database.py`, `tests/test_database_integration.py`, `tests/test_sql_injection.py`
- All imports changed from old names to `*Error` canonical names
- All `pytest.raises(OldName)` updated to `pytest.raises(OldNameError)`
- Docstrings in test methods updated for consistency

## Verification Results

- `python -c "import pycopg"` → exits 0 (Pitfall 2 cleared)
- `uv run pytest tests/test_deprecations.py::TestExceptionAliases -x` → 3 passed
- `uv run ruff check pycopg/` → All checks passed (N818 suppression gone)
- `grep -n 'N818' pyproject.toml` → no output (suppression removed)
- `grep -rn 'raise ExtensionNotAvailable\b|raise TableNotFound\b|raise InvalidIdentifier\b|raise DatabaseExists\b' pycopg/ | grep -v Error` → 0 lines (D-10 ship-check)
- `grep -c 'validate_identifiers' pycopg/spatial.py` → 27 (unchanged, T-41-03)
- `python -c "import warnings,pycopg.exceptions as e; warnings.simplefilter('ignore'); assert e.InvalidIdentifier is e.InvalidIdentifierError"` → exits 0 (same object)
- `PGDATABASE=pycopg_test2 uv run pytest -q` → **1431 passed, 2 skipped, 3 xfailed** — 96.23% coverage (gate ≥95%)
- `-W error::DeprecationWarning` gate GREEN: no internal code routes through deprecated alias

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Ruff E402 on `import warnings` in exceptions.py**
- **Found during:** Task 1 — `uv run ruff check pycopg/exceptions.py` failed with E402 "Module level import not at top of file" because the `import warnings as _warnings` was placed after the class definitions
- **Fix:** Moved `import warnings as _warnings` to the top of `exceptions.py` (before all class definitions), which is the correct Python convention
- **Files modified:** `pycopg/exceptions.py`
- **Commit:** f61f20f

**2. [Rule 1 - Bug] Ruff I001 on `from pycopg import exceptions` import order in __init__.py**
- **Found during:** Task 1 — `uv run ruff check pycopg/__init__.py` failed with I001 "Import block is un-sorted or un-formatted" because `from pycopg import exceptions` was placed after `from pycopg.exceptions import (...)`
- **Fix:** Moved `from pycopg import exceptions` to the first position in the import block (alphabetically `pycopg` precedes `pycopg.admin`)
- **Files modified:** `pycopg/__init__.py`
- **Commit:** f61f20f

**3. [Rule 3 - Blocking] Task 1 and Task 2 required simultaneous execution**
- **Found during:** Task 1 verification — after renaming exceptions, the full import chain failed with `DeprecationWarning` turned into error because `pycopg/utils.py` (and all internal files) still imported `InvalidIdentifier` directly via PEP 562 `__getattr__`, which emits a `DeprecationWarning`, which the `-W error` gate converted to an error, blocking even `conftest.py` from loading
- **Fix:** Applied Task 2 changes (all internal raise sites + imports) before committing Task 1, then committed the two tasks in separate commits in the correct order (Task 1 commit, then Task 2 commit)
- **Impact:** Both tasks land in the same git wave but separate commits, consistent with the plan's "single atomic change" note

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The changes are pure Python exception class renames and import updates.

**T-41-03 (validate_identifiers guard in spatial.py):** CONFIRMED SAFE — `validate_identifiers` count in `pycopg/spatial.py` is 27 both before and after this plan. The 2 exception raise-site edits in spatial.py did not disturb the injection guards.

**T-41-04 (internal call routing through deprecated alias):** CONFIRMED MITIGATED — Full suite passes under `-W error::DeprecationWarning`. Zero internal DeprecationWarnings emitted.

**T-41-05 (ImportError from stale __init__ import):** CONFIRMED MITIGATED — `python -c "import pycopg"` exits 0. Old names removed from import block; only `*Error` names imported directly.

## Known Stubs

None — all exception renames are complete and wired throughout the codebase.

## Self-Check: PASSED

- `pycopg/exceptions.py` with `def __getattr__`: FOUND
- `pycopg/__init__.py` with `def __getattr__`: FOUND
- N818 suppression removed from pyproject.toml: CONFIRMED (grep returns nothing)
- Commit f61f20f (Task 1): EXISTS
- Commit fa59485 (Task 2): EXISTS
- Full suite 1431 passed, 96.23% coverage: CONFIRMED
