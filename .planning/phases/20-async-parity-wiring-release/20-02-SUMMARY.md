---
phase: 20-async-parity-wiring-release
plan: "02"
subsystem: etl
tags: [async, etl, parity, testing, docs, sphinx]
dependency_graph:
  requires: [phases/20-async-parity-wiring-release/20-01]
  provides: [TestEtlParity, TestAsyncRunResultSurface, docs/etl.md, etl toctree entry]
  affects: [tests/test_parity.py, tests/test_etl_accessor.py, docs/etl.md, docs/index.md]
tech_stack:
  added: []
  patterns: [inspect.getmembers surface parity, pytest-asyncio auto mode, sphinx toctree]
key_files:
  created:
    - docs/etl.md
  modified:
    - tests/test_parity.py
    - tests/test_etl_accessor.py
    - docs/index.md
decisions:
  - "TestEtlParity uses both-direction set difference (sync-async and async-sync) to catch missing AND extra members"
  - "TestAsyncRunResultSurface uses async fixtures with asyncio_mode=auto (no @pytest.mark.asyncio needed)"
  - "async_etl_table fixture is async and creates/drops table via AsyncDatabase directly"
  - "cleanup_async_pipeline_runs creates a fresh AsyncDatabase per call to avoid fixture ordering issues"
  - "docs/etl.md follows spatial.md prose+examples convention with NO autodoc directives (Assumption A1)"
  - "etl toctree entry inserted between spatial and timescaledb per Pitfall 6 guidance"
metrics:
  duration: "~8 minutes"
  completed: "2026-06-15"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 4
---

# Phase 20 Plan 02: ETL Parity Tests + Docs Summary

Structural ETL surface parity test (`TestEtlParity`), behavioral async test class
(`TestAsyncRunResultSurface` — 7 tests covering `await async_db.etl.run/history/last_run/dry_run`
against the real DB), and `docs/etl.md` Sphinx page registered in the toctree.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add TestEtlParity + behavioral async ETL test class | 538a0df | tests/test_parity.py, tests/test_etl_accessor.py |
| 2 | Create docs/etl.md and add it to docs/index.md toctree | b091e80 | docs/etl.md, docs/index.md |

## What Was Built

### Task 1: TestEtlParity + TestAsyncRunResultSurface

**`tests/test_parity.py`** — Added `from pycopg.etl import AsyncETLAccessor, ETLAccessor`
import and appended `TestEtlParity` class at the bottom of the file.

`TestEtlParity.test_etl_accessor_public_methods_match`:
- Builds `sync_methods` and `async_methods` sets via `inspect.getmembers(cls)` filtered by `not name.startswith("_")`
- Asserts both directions: `sync_methods - async_methods == set()` (nothing missing in async) and `async_methods - sync_methods == set()` (no extra in async)
- Clear assertion messages naming the offending members in each direction
- Currently passes: both classes expose `{history, init, last_run, run}` as public surface

**`tests/test_etl_accessor.py`** — Added `AsyncDatabase` to imports and appended three async
fixtures plus the `TestAsyncRunResultSurface` class.

Async fixtures (all `async def`; `asyncio_mode = "auto"` means no marker needed):
- `async_db(db_config)` — yields `AsyncDatabase(db_config)`
- `async_etl_table(db_config)` — creates `etl_atgt_<hex>` table via async connection; drops on teardown
- `cleanup_async_pipeline_runs(db_config)` — drops `pipeline_runs` via async connection on teardown

`TestAsyncRunResultSurface` — 7 async tests:
1. `test_async_run_returns_run_result` — `isinstance(r, RunResult)`, `r.status == "success"`, `r.run_id` is int
2. `test_async_run_rows_extracted_and_loaded` — correct counts (2 rows extracted and loaded)
3. `test_async_history_two_runs_newest_first` — two runs → len==2, newest-first, all `RunResult`
4. `test_async_last_run_returns_most_recent` — `last_run` == `run` result `run_id`
5. `test_async_last_run_returns_none_for_unknown` — returns `None` for unknown pipeline name
6. `test_async_dry_run_status_and_no_row` — `status='dry_run'`, `run_id=None`, `rows_loaded=0`, no `pipeline_runs` row written
7. `test_async_run_transform_applied_via_to_thread` — transform callable mutates data correctly (`id*10 == 30`), proving `asyncio.to_thread` dispatch works (SC-2)

### Task 2: docs/etl.md + toctree

**`docs/etl.md`** — Full Sphinx documentation page following `docs/spatial.md` prose+examples convention. Sections:
- Intro paragraph: declarative E→T→L with run tracking, no new deps, full sync/async parity
- Access Pattern: sync + async code examples with lazy property note
- Defining a Pipeline: three load modes table, source forms (SQL vs table name), transform (None/callable/list), extract_limit
- `### run`: usage + `RunResult` fields
- `### history`: usage + empty-list behavior for unknown names
- `### last_run`: usage + `None` return for no runs
- `### Dry runs`: usage + full `RunResult` fields explanation
- Async Usage: all four methods with `await`, `asyncio.to_thread` note for transforms
- Security: `validate_identifiers` for identifiers; parameterized `%s` for data; `CREATE TABLE IF NOT EXISTS` for init path

**`docs/index.md`** — Inserted `etl` between `spatial` and `timescaledb` in the toctree.

## Verification

All acceptance criteria confirmed:

```
# Task 1
grep -q "class TestEtlParity" tests/test_parity.py          # PASS
uv run pytest tests/test_parity.py::TestEtlParity -o addopts="" -x -q
  1 passed in 0.01s                                          # PASS

uv run pytest tests/test_etl_accessor.py::TestAsyncRunResultSurface -o addopts="" -x -q
  7 passed in 3.00s                                          # PASS

uv run ruff check tests/test_parity.py tests/test_etl_accessor.py
  All checks passed!                                         # PASS

# Task 2
test -f docs/etl.md                                         # PASS
grep -q "async_db.etl" docs/etl.md                          # PASS
grep -qx "etl" docs/index.md                                # PASS
uv run sphinx-build -W --keep-going -b html docs docs/_build/html
  La compilation a réussi.                                   # PASS (0 warnings)

# Full plan verification
uv run pytest tests/test_parity.py::TestEtlParity tests/test_etl_accessor.py \
  -o addopts="" -x -q
  65 passed in 18.61s                                        # PASS
```

## Success Criteria

- [x] SC-4: `TestEtlParity` enumerates and asserts full ETL surface parity (both directions) and passes
- [x] Async code path covered behaviorally: run/history/last_run/dry_run against real `pycopg_test` DB (ETL-12/ETL-13)
- [x] SC-5 (docs): `docs/etl.md` renders without `-W` warnings and is in the toctree
- [x] `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` exits 0

## Deviations from Plan

None — plan executed exactly as written.

### Worktree Base Recovery (infrastructure)

Worktree was forked from commit `333e070` (stale `origin/HEAD`) instead of the dispatch
base `8f6c08d` (local `main` HEAD containing Wave 1 work). Since zero commits were ahead
of the stale base, `git reset --hard 8f6c08d6c672a84989a77bc6faf6aa2439fb65e3` was safe
to execute before starting work. This is the documented recurring worktree-base-mismatch
recovery for this repository.

## Known Stubs

None — only tests and documentation were added.

## Threat Surface Scan

No new security surface introduced. Plan 02 adds tests and documentation only — no production
code, no new SQL, no new identifier paths, no network endpoints. Per the plan's threat model
T-20-03 disposition: accepted.

## Self-Check: PASSED

| Item | Status |
|------|--------|
| tests/test_parity.py exists and contains TestEtlParity | FOUND |
| tests/test_etl_accessor.py exists and contains TestAsyncRunResultSurface | FOUND |
| docs/etl.md exists and contains async_db.etl | FOUND |
| docs/index.md toctree contains exact line 'etl' | FOUND |
| commit 538a0df (Task 1) exists | FOUND |
| commit b091e80 (Task 2) exists | FOUND |
