---
phase: 10-s-curit-r-siduelle-robustesse
plan: "03"
subsystem: pycopg.database (backup/restore subprocess env)
tags: [security, bug-fix, subprocess, b5, sec-04]
dependency_graph:
  requires: []
  provides: [B5-fixed, subprocess-env-robustness]
  affects: [pycopg/database.py, tests/test_subprocess_env.py]
tech_stack:
  added: []
  patterns: [os.environ merge, unittest.mock.patch, monkeypatch.delattr]
key_files:
  created:
    - tests/test_subprocess_env.py
  modified:
    - pycopg/database.py
decisions:
  - "D-04: Use os.environ (module-level import) instead of subprocess.os.environ at 3 backup/restore sites"
  - "D-06: Targeted mock form for B5 tests — patch subprocess.run, no real pg_dump/psql needed"
  - "Ruff I001 pre-existing import ordering fixed as part of ruff check acceptance gate"
metrics:
  duration: "~10 minutes"
  completed: "2026-06-08T20:31:42Z"
  tasks_completed: 2
  files_changed: 2
---

# Phase 10 Plan 03: Fix B5 — subprocess.os.environ Robustness Summary

Fix B5 (SEC-04): replaced `subprocess.os.environ` with explicit `os.environ` at the three backup/restore subprocess env construction sites in `pycopg/database.py`, plus a dedicated red->green regression test.

## Objective

Close B5 (SEC-04, D-04): `pg_dump`, `pg_restore`, and `_psql_restore` in `pycopg/database.py` built the subprocess child environment using `{**subprocess.os.environ, **env}`. `subprocess.os` is an undocumented re-export of the `os` module that can be absent in some Python runtime configurations, causing `AttributeError`. The fix uses the explicit `os.environ` form (already used on the async side).

## Tasks Completed

### Task 1: Fix B5 — replace subprocess.os.environ with os.environ (commit 589a919)

**Files modified:** `pycopg/database.py`

Changes:
- Added `import os` to the top-level import block (was missing from database.py; present in async_database.py)
- Replaced `env={**subprocess.os.environ, **env}` with `env={**os.environ, **env}` at three sites:
  - `pg_dump()` (~line 2170)
  - `pg_restore()` (~line 2265)
  - `_psql_restore()` (~line 2284)
- Applied ruff `--fix` to resolve pre-existing I001 import ordering issue (required for acceptance gate)

**Verification passed:**
- `grep -c "subprocess.os.environ" pycopg/database.py` = 0
- `grep -rc "subprocess.os.environ" pycopg/` = 0 (none in package)
- `grep -c "os.environ" pycopg/database.py` = 3 (all three sites)
- `grep -n "^import os" pycopg/database.py` = line 10
- `uv run ruff check pycopg/database.py` passes
- `uv run python -c "import pycopg.database"` succeeds

### Task 2: Red->green regression test for B5 (commit 1103f1b)

**Files created:** `tests/test_subprocess_env.py`

10 tests in 3 classes:

**TestPgDumpEnv (4 tests):**
- `test_env_inherits_os_environ` — asserts `PATH` present in env passed to subprocess.run
- `test_env_merges_pgpassword` — asserts `PGPASSWORD` = config.password when set
- `test_env_no_pgpassword_empty_value_when_no_config_password` — asserts no empty PGPASSWORD injected
- `test_subprocess_os_independence` (RED->GREEN proof) — `monkeypatch.delattr(subprocess, "os")` then call pg_dump; succeeds on fixed code, would raise `AttributeError` on buggy code

**TestPgRestoreEnv (3 tests):**
- env inheritance, PGPASSWORD merge, subprocess.os independence (same pattern)

**TestPsqlRestoreEnv (3 tests):**
- env inheritance, PGPASSWORD merge, subprocess.os independence (same pattern)

**Test form D-06:** targeted mock — `patch("subprocess.run")` (subprocess locally imported inside each method, so patched at module level). No real pg_dump/psql/postgres required.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Pre-existing I001 import ordering in database.py**
- **Found during:** Task 1 (ruff check acceptance gate)
- **Issue:** Pre-existing I001 ruff error in database.py import block (psycopg/sqlalchemy/tenacity import ordering + tenacity imports not grouped). The plan's acceptance criteria requires `uv run ruff check pycopg/database.py` to pass, which requires fixing this.
- **Fix:** Ran `uv run ruff check pycopg/database.py --fix` — reorganized import block: `psycopg.pq.TransactionStatus` before `psycopg.rows.dict_row`, tenacity imports expanded to multi-line grouped, `pycopg.queries` moved before `pycopg.config`, `Optional`/`Iterator`/`Sequence` moved from `typing` to `collections.abc`.
- **Files modified:** `pycopg/database.py`
- **Commit:** 589a919 (included in Task 1 commit)

**2. [Rule 3 - Blocking] pytest-mock not installed; mocker fixture unavailable**
- **Found during:** Task 2 (first test run attempt)
- **Issue:** Initial test implementation used `mocker` fixture from `pytest-mock`, which is not in project dependencies. `fixture 'mocker' not found`.
- **Fix:** Rewrote tests using `unittest.mock.patch` (context manager form) and `monkeypatch` (pytest built-in). No new dependency added.
- **Files modified:** `tests/test_subprocess_env.py`
- **Commit:** 1103f1b

**3. [Rule 3 - Blocking] pycopg.database.subprocess not patchable as module attribute**
- **Found during:** Task 2 (second test run attempt)
- **Issue:** `subprocess` is imported locally inside each method (`import subprocess` at line 2135/2223/2278), not at module level. `patch("pycopg.database.subprocess.run")` fails with `AttributeError: module 'pycopg.database' has no attribute 'subprocess'`.
- **Fix:** Patch `subprocess.run` at the `subprocess` module itself (`patch("subprocess.run")`). For the independence test, `monkeypatch.delattr(subprocess, "os")` removes the attribute from the actual subprocess module (which the locally-imported module reference resolves to).
- **Files modified:** `tests/test_subprocess_env.py`
- **Commit:** 1103f1b

### Known Limitations

**Coverage gate fails on isolated runs:** `uv run pytest tests/test_subprocess_env.py -x -q` exits with `Coverage failure: total of 24 is less than fail-under=70`. This is a pre-existing project configuration issue — the `--cov-fail-under=70` threshold in `pyproject.toml` is designed for the full suite including integration tests. The 10 new tests themselves all pass. Tests verified with `--no-cov` for unit-level verification.

## Self-Check

**Files created/modified:**
- `/home/loc/workspace/pycopg/.claude/worktrees/agent-a5f5f128d7dcc7697/pycopg/database.py` — exists, modified
- `/home/loc/workspace/pycopg/.claude/worktrees/agent-a5f5f128d7dcc7697/tests/test_subprocess_env.py` — exists, created

**Commits verified:**
- `589a919` — fix(10-03): fix B5
- `1103f1b` — test(10-03): add red->green regression test

## Self-Check: PASSED

All files exist. Both commits verified in git log. All 10 tests pass on fixed code. Zero `subprocess.os.environ` occurrences in `pycopg/`. `import os` present at line 10 of `database.py`.

## Threat Model Coverage

T-10-04 (DoS — broken env breaks backup/restore): mitigated by the fix (explicit `os.environ`) and the regression test (independence + PGPASSWORD merge assertions).

T-10-04-IE (PGPASSWORD information disclosure): accepted — PGPASSWORD passed via env (libpq standard), not argv; not logged; unchanged by this fix.
