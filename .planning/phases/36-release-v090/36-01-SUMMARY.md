---
phase: 36-release-v090
plan: "01"
subsystem: release
tags: [version-bump, changelog, docs, cosmetic-debt, quality-gates]
dependency_graph:
  requires: [35-02]
  provides: [version-0.9.0-content]
  affects: [pyproject.toml, uv.lock, docs/conf.py, CHANGELOG.md, README.md, docs/api-reference.md, docs/database.md, docs/async-database.md, docs/index.md, pycopg/schema.py, pycopg/maint.py, pycopg/admin.py, pycopg/backup.py, pycopg/timescale.py]
tech_stack:
  added: []
  patterns: [numpydoc, sphinx-autodoc, interrogate, coverage-ratchet]
key_files:
  created: []
  modified:
    - pyproject.toml
    - uv.lock
    - docs/conf.py
    - CHANGELOG.md
    - README.md
    - docs/api-reference.md
    - docs/database.md
    - docs/async-database.md
    - docs/index.md
    - pycopg/schema.py
    - pycopg/maint.py
    - pycopg/admin.py
    - pycopg/backup.py
    - pycopg/timescale.py
    - pycopg/database.py
    - pycopg/async_database.py
    - tests/test_async_database.py
decisions:
  - "D-36-01 honored: pyproject.toml is the single canonical version source; pycopg/__init__.py untouched (dynamic __version__ preserved)"
  - "D-36-03 honored: all 12 CHANGELOG signatures verified verbatim from live source files before writing"
  - "D-36-04 honored: CLAUDE.md v0.5.0 -> v0.9.0 (on disk, gitignored), dead pycopg.aliases xrefs removed from 5 accessor modules"
  - "WR-01 DEFERRED: time_bucket( case-sensitive guard is runtime behavior — no change"
  - "WR-03 DEFERRED: %s::interval cast approach is runtime behavior — no change"
metrics:
  duration: "~60 minutes"
  completed: "2026-06-25"
  tasks_completed: 5
  tasks_total: 5
  files_modified: 17
---

# Phase 36 Plan 01: Release v0.9.0 Content + Gates Summary

**One-liner:** Version bump 0.8.0→0.9.0, Added-only CHANGELOG for 12 new methods, docs surfaces updated (README 27→32 methods), cosmetic debt cleared (aliases xrefs removed), all 4 quality gates green (coverage 94.11%, interrogate 100%, Sphinx -W clean, DeprecationWarning clean).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Bump version to 0.9.0 | 482b648 | pyproject.toml, uv.lock, docs/conf.py, CLAUDE.md (on disk) |
| 2 | Write CHANGELOG [0.9.0] Added-only section | 4dc7b70 | CHANGELOG.md |
| 3 | Update docs surfaces | 03dfbdc | README.md, docs/api-reference.md, docs/database.md, docs/async-database.md, docs/index.md |
| 4 | Clear soldered cosmetic debt | a93f465 | pycopg/schema.py, maint.py, admin.py, backup.py, timescale.py |
| 5 | Measure 4 quality gates + fixes | e405f8e | tests/test_async_database.py, pycopg/database.py, pycopg/async_database.py, docs/async-database.md |

## Gate Baseline (for 36-02 to re-confirm)

| Gate | Target | Measured | Status |
|------|--------|----------|--------|
| GATE A: Coverage | >=94% | 94.11% | GREEN |
| GATE B: interrogate | >=95% | 100% | GREEN |
| GATE C: Sphinx -W | clean | exits 0 | GREEN |
| GATE D: DeprecationWarning | clean | exits 0 | GREEN |

**Coverage measurement:** `PGDATABASE=pycopg_test2 uv run pytest --cov=pycopg` (1331 passed, 4 failed). The bare `uv run pytest` exits at 77% because the default `pycopg_test` DB is broken (TSDB catalog mismatch — documented environment issue). The 4 failures with pycopg_test2 are: `test_async_transaction_fix` (known pre-existing flaky), and 3 PostGIS error tests that require PostGIS installed in pycopg_test2 (also pre-existing environment gap).

**interrogate:** `uv run interrogate pycopg --fail-under 95` → `RESULT: PASSED (minimum: 95.0%, actual: 100.0%)`

**Sphinx:** `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` → `La compilation a réussi.`

**DeprecationWarning:** `uv run python -W error::DeprecationWarning -c "import pycopg"` → exits 0

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Sphinx -W gate: 3 warnings treated as errors**
- **Found during:** Task 5 (Gate C measurement)
- **Issue 1:** `database.py` upsert docstring `RETURNING *` — the bare `*` is parsed as RST emphasis start-string without end-string (line 14 of docstring, confirmed pre-existing from Phase 34)
- **Issue 2:** Same in `async_database.py` upsert docstring
- **Issue 3:** `async-database.md` cross-reference `[Database CRUD Helpers](database.md#crud-helpers-v090)` — anchor ID `crud-helpers-v090` does not match MyST-generated anchor for heading `## CRUD Helpers (v0.9.0)` (introduced in Task 3)
- **Fix 1+2:** Changed `RETURNING *` to `` ``RETURNING *`` `` (backtick-inline-code escape) in both sync and async upsert docstrings
- **Fix 3:** Removed the broken anchor fragment; link now points to `database.md` page without anchor
- **Files modified:** `pycopg/database.py`, `pycopg/async_database.py`, `docs/async-database.md`
- **Commit:** e405f8e

**2. [Rule 2 - Missing coverage] Added async schema introspection integration tests**
- **Found during:** Task 5 (Gate A measurement)
- **Issue:** `PGDATABASE=pycopg_test2 uv run pytest` coverage was 93.31% (below 94% gate). Root cause: `pycopg/schema.py` async introspection methods (`primary_key`, `foreign_keys`, `sequences`, `views`, `describe`) had no live-DB async integration tests. Phase 34/35 added the sync tests but the async parity was only checked via signature inspection, not executed.
- **Fix:** Added `TestAsyncSchemaIntrospection` class (6 tests) to `tests/test_async_database.py`. All 6 pass with `PGDATABASE=pycopg_test2`. Coverage rose to 94.11%.
- **Files modified:** `tests/test_async_database.py`
- **Commit:** e405f8e

### WR-01/WR-03 Deferred (D-36-04)

**WR-01 (case-sensitive `time_bucket(` guard in continuous-aggregate check):** The guard at `pycopg/timescale.py:968` (`if "time_bucket(" not in select_sql`) is a case-sensitive runtime string check. Making it case-insensitive would alter runtime behavior (callers passing `TIME_BUCKET(` would then pass the guard). **DEFERRED** — behavioral change.

**WR-03 (INTERVAL-literal-vs-`%s::interval`):** The `older_than => %s::interval` pattern at `pycopg/timescale.py:60` passes string interval literals via `%s::interval` cast in SQL. Changing to an INTERVAL-literal approach would alter the parameterization behavior. **DEFERRED** — behavioral change.

### Cosmetic Notes

**CLAUDE.md gitignored:** CLAUDE.md is in `.gitignore` and cannot be committed. The version line `**pycopg v0.5.0**` was updated to `**pycopg v0.9.0**` on disk (D-36-04 satisfied) but the change does not appear in git history. This is expected behavior for this project.

**Pre-existing ruff N818 warnings:** 4 `N818` errors (exception names not using `Error` suffix) in `pycopg/exceptions.py` were reported by `ruff check pycopg`. These are pre-existing (existed before Phase 36) and in a file not touched by this plan. Logged to deferred items.

**Pre-existing black queries.py:** `uv run black --check pycopg` wants to reformat `pycopg/queries.py`. Pre-existing, not touched in this plan. Logged to deferred items.

## Known Stubs

None — all documentation is wired to real methods delivered in Phases 34/35.

## Threat Flags

None — this plan adds no new runtime attack surface (documentation and version bumping only per the threat model in the plan).

## Self-Check: PASSED

Files verified:
- pyproject.toml: `grep 'version = "0.9.0"' pyproject.toml` → found
- docs/conf.py: `grep "release = '0.9.0'" docs/conf.py` → found
- CHANGELOG.md: `grep '## \[0.9.0\]' CHANGELOG.md` → found (all 12 method names present)
- README.md: `grep '(32 methods)' README.md` → found
- pycopg/schema.py: `grep -rn 'pycopg\.aliases' pycopg/` → nothing (D-36-04 cleared)

Commits verified:
- 482b648: `chore(36-01): bump version to 0.9.0 across canonical sources`
- 4dc7b70: `docs(36-01): write CHANGELOG [0.9.0] Added-only section with exact signatures`
- 03dfbdc: `docs(36-01): update docs surfaces for v0.9.0 CRUD + introspection methods`
- a93f465: `chore(36-01): clear stale pycopg.aliases xrefs from accessor module docstrings`
- e405f8e: `test(36-01): add async schema introspection tests + fix Sphinx -W warnings`
