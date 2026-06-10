---
phase: 13-qualit-documentaire-docstrings-numpydoc-interrogate
plan: "06"
subsystem: documentation
tags: [numpydoc, sphinx, napoleon, interrogate, mypy, phase-gate]

requires:
  - phase: 13-03
    provides: numpydoc shallow docstrings in database.py (all ~77 methods)
  - phase: 13-04
    provides: numpydoc shallow docstrings in async_database.py (all ~70 methods)
  - phase: 13-05
    provides: numpydoc shallow docstrings in base.py, config.py, utils.py, migrations.py, pool.py

provides:
  - napoleon_google_docstring = False in docs/conf.py (numpy-only parsing locked)
  - Zero Google-style labels in all pycopg/*.py (grep -rcE passes)
  - Whole-phase gate evidence: pytest 698+2 / interrogate OK / sphinx-build -W exit 0 / mypy 32 errors (non-blocking)

affects: [sphinx-docs, CI]

tech-stack:
  added: []
  patterns:
    - "napoleon_google_docstring = False: disable Google parsing only after all modules migrated (Pattern 3)"
    - "Sphinx duplicate object warning fix: remove redundant Attributes entries for @property members"

key-files:
  created: []
  modified:
    - docs/conf.py
    - pycopg/__init__.py
    - pycopg/database.py
    - pycopg/async_database.py

key-decisions:
  - "D-06 applied to __init__.py module-level Example: block (deleted) — was outside prior plan scopes"
  - "Duplicate Sphinx object warnings for engine/async_engine fixed by removing redundant entries from class Attributes sections — @property already autodoc'd directly"
  - "napoleon_google_docstring = False added as final lock after confirming all modules are 100% numpydoc"

requirements-completed: [DOC-06, DOC-08, DOC-09]

duration: 8min
completed: "2026-06-10"
---

# Phase 13 Plan 06: Final Cleanup and Whole-Phase Gate Summary

**napoleon_google_docstring disabled post full-package numpydoc migration — Sphinx -W exit 0, interrogate 100%, 698 tests green, mypy 32 errors recorded (non-blocking)**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-10T12:35:00Z
- **Completed:** 2026-06-10T12:43:51Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments

- `napoleon_google_docstring = False` added to `docs/conf.py` immediately after `napoleon_numpy_docstring = True` — Google-style parsing is now explicitly disabled
- Module-level `Example:` block removed from `pycopg/__init__.py` per D-06 (was out-of-scope in all prior migration plans)
- Duplicate Sphinx object descriptions resolved: `engine` and `async_engine` removed from class-level `Attributes` sections (they were redundant with the `@property` autodoc entries)
- `grep -rcE "^\s*(Args|Returns|Raises|Example|Examples):" pycopg/*.py` returns 0 for every module — no Google-style labels remain
- `uv run interrogate pycopg --fail-under 95 --quiet` exits 0 (100% coverage maintained)
- `sphinx-build -W --keep-going` exits 0 — 0 warnings with Google parsing OFF
- `uv run pytest` (deselecting 3 known pre-existing local failures): **698 passed, 2 skipped**
- mypy: 32 errors across 5 files — recorded, non-blocking per D-05

## Consolidated Phase Gate Results

| Gate | Command | Result |
|------|---------|--------|
| Tests | `uv run pytest -o addopts="" -q --deselect ...3 known failures...` | **698 passed, 2 skipped** |
| Docstring coverage | `uv run interrogate pycopg --fail-under 95 --quiet` | **EXIT 0** (100%) |
| Sphinx guard | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` | **EXIT 0** (0 warnings) |
| mypy | `uv run mypy pycopg/` | 32 errors in 5 files (non-blocking per D-05) |

### mypy Details (non-blocking)

Selected errors from `uv run mypy pycopg/`:
- `async_database.py:569`: Incompatible return type (tuple vs dict)
- `async_database.py:1822,1827,1851,1854`: Returning Any from `str | int`
- `async_database.py:1917,2007`: Argument type `str | None` vs `str`
- `async_database.py:2669`: Returning Any from `int`
- `pyproject.toml`: unused override sections for geoalchemy2/shapely

Total: 32 errors in 5 files. All pre-existing per D-05 (type errors allowed, non-blocking). CI uses `continue-on-error: true` for mypy.

### 3 Known Pre-existing Test Failures (deselected)

- `tests/test_integration.py::TestAsyncIntegration::test_async_transaction_fix`
- `tests/test_parity.py::TestBehavioralParity::test_create_constructor_parity`
- `tests/test_postgis_errors.py::TestPostGISErrorHandling::test_create_spatial_index_name_parameter`

These are local-env pre-existing failures (verified against clean base, not regressions from Phase 13). CI is the authority.

## Task Commits

1. **Task 1: Disable napoleon_google_docstring + whole-phase gate** - `53f5d5c` (docs)

## Files Created/Modified

- `/home/loc/workspace/pycopg/docs/conf.py` — Added `napoleon_google_docstring = False`, removed old migration-era comment
- `/home/loc/workspace/pycopg/pycopg/__init__.py` — Deleted module-level `Example:` block (D-06)
- `/home/loc/workspace/pycopg/pycopg/database.py` — Removed `engine : Engine` from class Attributes section (duplicate Sphinx entry fix)
- `/home/loc/workspace/pycopg/pycopg/async_database.py` — Removed `async_engine : AsyncEngine` from class Attributes section (duplicate Sphinx entry fix)

## Decisions Made

- D-06 applied to `__init__.py` module-level `Example:` block: this block was outside scope of Plans 03-05 (as noted in environment notes and plan instructions). Deleted per D-06 — all `Example:` / `Examples:` occurrences in `pycopg/*.py` must be removed. Required to satisfy the acceptance criterion: `grep -rcE` returns 0 for every module.
- Sphinx duplicate object description warnings for `engine` and `async_engine` fixed by removing them from class-level `Attributes` sections: these properties were documented twice — once as `Attributes:` in the class docstring and once via `@property` autodoc. The `Attributes:` entries were redundant; the `@property` entries are the canonical source. This was a blocker for `sphinx-build -W exit 0`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed module-level Example: block from __init__.py**
- **Found during:** Task 1 (pre-commit verification of zero Google labels)
- **Issue:** `grep -rcE "^\s*(Args|Returns|Raises|Example|Examples):" pycopg/*.py` returned 1 match in `pycopg/__init__.py` (line 6: `Example:` block). This was out-of-scope for all prior migration plans (as noted in environment notes) but the plan acceptance criterion requires 0 for every module.
- **Fix:** Deleted the `Example:` block from the module docstring per D-06. Kept the first two lines of the module docstring.
- **Files modified:** `pycopg/__init__.py`
- **Verification:** `grep -rcE` returns 0 for all `pycopg/*.py` — PASSED
- **Committed in:** `53f5d5c` (Task 1 commit)

**2. [Rule 1 - Bug] Fixed Sphinx duplicate object description warnings for engine/async_engine**
- **Found during:** Task 1 (Sphinx guard build with `napoleon_google_docstring = False`)
- **Issue:** Clean Sphinx build (`-W --keep-going`) exited 1 with 2 warnings: "description dupliquée de l'objet pycopg.database.Database.engine" and "description dupliquée de l'objet pycopg.async_database.AsyncDatabase.async_engine". Root cause: both `engine` and `async_engine` were listed in the class docstring `Attributes` section AND documented as `@property` methods — Sphinx sees two domain entries for the same object.
- **Fix:** Removed the `engine : Engine` entry from `Database.Attributes` section and `async_engine : AsyncEngine` from `AsyncDatabase.Attributes` section. The `@property` docstrings remain and are the canonical autodoc source.
- **Files modified:** `pycopg/database.py`, `pycopg/async_database.py`
- **Verification:** `sphinx-build -W --keep-going` exits 0 with 0 warnings — PASSED
- **Committed in:** `53f5d5c` (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (1 missing D-06 application, 1 Sphinx duplicate object bug)
**Impact on plan:** Both auto-fixes necessary for acceptance criteria. No scope creep — both changes are docstring/documentation quality fixes within the phase's explicit scope.

## Issues Encountered

- `pycopg/__init__.py` contained a module-level `Example:` block that was not covered by any prior migration plan (Plans 03/04/05 targeted specific modules). The block was found when running the acceptance criterion grep check. Deleted per D-06 with no functional impact.
- Sphinx `sphinx-build -W` failed with "duplicate object" warnings for `engine` and `async_engine` properties. These warnings would have been present in prior clean builds as well but were masked by the pre-existing Google docstring RST warnings (25 total) that prevented `-W` from passing in earlier plans. Once Google parsing was disabled and all modules migrated, the 2 duplicate entries became the only warnings.

## Known Stubs

None.

## Threat Flags

None — documentation/config-only changes, no new trust boundaries.

## Self-Check

Files exist:
- `/home/loc/workspace/pycopg/docs/conf.py` — FOUND
- `/home/loc/workspace/pycopg/pycopg/__init__.py` — FOUND
- `/home/loc/workspace/pycopg/pycopg/database.py` — FOUND
- `/home/loc/workspace/pycopg/pycopg/async_database.py` — FOUND

Commits exist:
- `53f5d5c` — (committed; task commit)

Verification:
- `grep -c "napoleon_google_docstring = False" docs/conf.py` = 1 — PASSED
- `grep -rcE "^\s*(Args|Returns|Raises|Example|Examples):" pycopg/*.py` = 0 for every module — PASSED
- `uv run interrogate pycopg --fail-under 95 --quiet` exit 0 — PASSED
- `uv run sphinx-build -W --keep-going` exit 0, 0 warnings — PASSED
- `uv run pytest` (deselecting 3 known failures): 698 passed, 2 skipped — PASSED
- mypy: 32 errors (non-blocking, recorded) — NOTED

## Self-Check: PASSED

## Phase 13 Summary

Phase 13 is complete. All 6 plans executed:
- Plan 01: Tooling foundation (interrogate, mypy, Sphinx guard, napoleon_numpy_docstring)
- Plan 02: Exception inventory (ExtensionNotAvailable, DatabaseExists raise sites)
- Plan 03: database.py migration (~77 docstrings to numpydoc)
- Plan 04: async_database.py migration (~70 docstrings to numpydoc)
- Plan 05: 5 grouped modules migration (base.py, config.py, utils.py, migrations.py, pool.py)
- Plan 06: Final cleanup + whole-phase gate (this plan)

DOC-06 through DOC-09 requirements satisfied. The package is fully numpydoc, interrogate >= 95, Sphinx builds warning-free with Google parsing disabled, and CI gates are in place.

---
*Phase: 13-qualit-documentaire-docstrings-numpydoc-interrogate*
*Completed: 2026-06-10*
