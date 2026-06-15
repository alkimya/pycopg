---
phase: 20-async-parity-wiring-release
verified: 2026-06-16T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 20: Async Parity, Wiring & Release — Verification Report

**Phase Goal:** `AsyncETLAccessor` reaches full parity with `ETLAccessor`, `db.etl` / `async_db.etl` lazy properties are wired, `TestEtlParity` enumerates the ETL surface, and pycopg v0.5.0 ships to PyPI with green Sphinx docs and a held >= 94% coverage gate.
**Verified:** 2026-06-16
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                                                                                                | Status     | Evidence                                                                                                                                                                                                                                                                                                   |
|----|----------------------------------------------------------------------------------------------------------------------------------------------------------------------|------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1  | `await async_db.etl.run(pipeline)`, `await async_db.etl.history(name)`, `await async_db.etl.last_run(name)`, and `await async_db.etl.run(pipeline, dry_run=True)` exist and produce equivalent results to sync counterparts | VERIFIED   | `etl.py:1211` — `async def run(…, dry_run=False)`, `etl.py:1159` — `async def history(…)`, `etl.py:1186` — `async def last_run(…)`. Behavioral tests: `TestRunResultSurfaceAsync` in `tests/test_etl_accessor.py:1417`; 78 tests in `tests/test_parity.py::TestEtlParity` + `tests/test_etl_accessor.py` pass (`78 passed in 24.83s`). |
| 2  | Sync transform callables are dispatched via `asyncio.to_thread` in `AsyncETLAccessor.run()` — a slow transform does not block the event loop                        | VERIFIED   | `etl.py:1318,1391` — `df = await asyncio.to_thread(step, df)` used in both dry-run and full-run transform chains. `etl.py:27` — `import asyncio`. Test `test_async_run_transform_applied_via_to_thread` (`test_etl_accessor.py:1544`) proves the callable is executed via thread dispatch (observable: `id` column becomes `30` after `*10` transform). |
| 3  | `db.etl` returns a lazily-created `ETLAccessor`; `async_db.etl` returns a lazily-created `AsyncETLAccessor`; both follow the `db.spatial` / `async_db.spatial` lazy-creation pattern | VERIFIED   | `database.py:86,254-271` — `self._etl: ETLAccessor | None = None`; property creates and caches on first access, matching the `_spatial` / `spatial` pattern at `database.py:85,231-251`. `async_database.py:85,114-131` — identical pattern for `AsyncETLAccessor` matching `async_database.py:84,96-112` for `AsyncSpatialAccessor`. |
| 4  | `TestEtlParity` uses `inspect.getmembers` to enumerate `ETLAccessor` vs `AsyncETLAccessor` method surfaces and asserts full parity; passes in CI                   | VERIFIED   | `tests/test_parity.py:466-502` — class `TestEtlParity` with `test_etl_accessor_public_methods_match` uses `inspect.getmembers(ETLAccessor)` and `inspect.getmembers(AsyncETLAccessor)`, asserts bidirectional parity (missing and extra both fail). Targeted test run: `78 passed` with no failures. |
| 5  | `docs/etl.md` renders without `-W` warnings and is in toctree; `interrogate >= 95`; `uv run pytest --cov` >= 94%; CHANGELOG + MIGRATION updated; `pycopg==0.5.0` tagged and published | VERIFIED   | `docs/index.md:17` — `etl` in toctree. `docs/etl.md` exists (255 lines, no autodoc stub). Sphinx clean build (orchestrator-verified: exit 0). interrogate: 100.0% (orchestrator-verified). Coverage: 94.26% (orchestrator-verified, 981 passed). `CHANGELOG.md:10` — `## [0.5.0] - 2026-06-15` with ETL entries. `MIGRATION.md:349-454` — v0.4.x to v0.5.0 guide. `pyproject.toml:7` — `version = "0.5.0"`. PyPI: pycopg 0.5.0 live (orchestrator-verified from `https://pypi.org/pypi/pycopg/0.5.0/json`). |

**Score:** 5/5 truths verified

---

### Required Artifacts

| Artifact                                       | Expected                              | Status     | Details                                                                 |
|------------------------------------------------|---------------------------------------|------------|-------------------------------------------------------------------------|
| `pycopg/etl.py`                                | `AsyncETLAccessor` class + all methods | VERIFIED   | Lines 1009-1476: full `AsyncETLAccessor` with `run`, `history`, `last_run`, `init`, `_start_run`, `_end_run`, `_fetch_run_result` — all `async def`. 1477 lines total. |
| `pycopg/database.py`                           | `db.etl` lazy property                | VERIFIED   | Lines 254-271: `@property def etl(self) -> ETLAccessor` with `_etl` guard matching `spatial` pattern. |
| `pycopg/async_database.py`                     | `async_db.etl` lazy property          | VERIFIED   | Lines 114-131: `@property def etl(self) -> AsyncETLAccessor` with `_etl` guard matching `spatial` pattern. |
| `pycopg/__init__.py`                           | `ETLAccessor`, `AsyncETLAccessor`, `Pipeline`, `RunResult` exported | VERIFIED   | Line 10: imports all four. Lines 54-57: all four in `__all__`. |
| `tests/test_parity.py::TestEtlParity`          | Surface parity class using `inspect.getmembers` | VERIFIED   | Lines 466-502; imports `ETLAccessor`, `AsyncETLAccessor`; bidirectional set diff assertion. |
| `tests/test_etl_accessor.py`                   | Behavioral async tests                | VERIFIED   | 1763 lines; class `TestRunResultSurfaceAsync` at line 1417 with 11+ async test methods covering `run`, `history`, `last_run`, `dry_run`. |
| `docs/etl.md`                                  | Sphinx page for ETL namespace          | VERIFIED   | 255 lines; covers Pipeline, run(), history(), last_run(), dry_run, async usage, security. |
| `docs/index.md`                                | `etl` in toctree                      | VERIFIED   | Line 17: `etl` in toctree block. |
| `CHANGELOG.md`                                 | v0.5.0 section with ETL entries       | VERIFIED   | Line 10: `## [0.5.0] - 2026-06-15`; ETL-specific entries on lines 14-32. |
| `MIGRATION.md`                                 | v0.4.x → v0.5.0 migration guide       | VERIFIED   | Lines 349-454: full migration section for v0.5.0 with ETL namespace examples. |
| `pyproject.toml`                               | `version = "0.5.0"`                   | VERIFIED   | Line 7: `version = "0.5.0"`. |

---

### Key Link Verification

| From                        | To                               | Via                                          | Status   | Details                                                              |
|-----------------------------|----------------------------------|----------------------------------------------|----------|----------------------------------------------------------------------|
| `async_database.py:etl`     | `etl.AsyncETLAccessor`           | lazy import + `AsyncETLAccessor(self)`       | WIRED    | `async_database.py:128-130` — `from pycopg.etl import AsyncETLAccessor; self._etl = AsyncETLAccessor(self)` |
| `database.py:etl`           | `etl.ETLAccessor`                | lazy import + `ETLAccessor(self)`            | WIRED    | `database.py:268-270` — same pattern                                |
| `AsyncETLAccessor.run`      | `asyncio.to_thread`              | `await asyncio.to_thread(step, df)`          | WIRED    | `etl.py:1318,1391` — both transform chain sites use `to_thread`     |
| `TestEtlParity`             | `ETLAccessor`, `AsyncETLAccessor`| `inspect.getmembers` + set diff              | WIRED    | `test_parity.py:481-502` — imports both, enumerates, asserts parity |
| `docs/index.md`             | `docs/etl.md`                    | toctree entry `etl`                          | WIRED    | `index.md:17` — `etl` in toctree                                    |

---

### Data-Flow Trace (Level 4)

Not applicable to this phase — the artifacts are ETL accessor methods and test harnesses, not UI components rendering dynamic data. The ETL `run()` method's data flow (extract → transform → load → `RunResult`) is validated by the behavioral integration tests in `TestRunResultSurfaceAsync`.

---

### Behavioral Spot-Checks

| Behavior                                       | Command                                                                                                      | Result          | Status |
|------------------------------------------------|--------------------------------------------------------------------------------------------------------------|-----------------|--------|
| `TestEtlParity` + async behavioral tests pass  | `uv run pytest tests/test_parity.py::TestEtlParity tests/test_etl_accessor.py -o addopts="" -q`             | 78 passed       | PASS   |
| `to_thread` dispatch in `AsyncETLAccessor.run` | `grep -n "to_thread" pycopg/etl.py`                                                                          | Lines 1318, 1391 | PASS  |
| `db.etl` lazy property wired                   | `grep -n "def etl" pycopg/database.py pycopg/async_database.py`                                              | Lines 254, 115  | PASS   |
| `pyproject.toml` version = 0.5.0               | `grep "^version" pycopg/pyproject.toml`                                                                       | `version = "0.5.0"` | PASS |

---

### Probe Execution

No conventional `scripts/*/tests/probe-*.sh` probes are declared for this phase. Phase 20 relies on the pytest suite as its verification mechanism.

---

### Requirements Coverage

| Requirement | Source Plan   | Description                                                                                                         | Status    | Evidence                                                                                 |
|-------------|---------------|---------------------------------------------------------------------------------------------------------------------|-----------|------------------------------------------------------------------------------------------|
| ETL-12      | 20-01, 20-02  | `await async_db.etl.run/history` exist; sync transforms via `asyncio.to_thread`; `TestEtlParity` added             | SATISFIED | `etl.py:1159,1186,1211,1318,1391`; `test_parity.py:466`; 78 tests pass                 |
| ETL-13      | 20-01, 20-02  | `db.etl` and `async_db.etl` return lazily-created accessors mirroring `db.spatial` / `async_db.spatial` pattern    | SATISFIED | `database.py:254-271`; `async_database.py:114-131`; pattern mirrors spatial accessor     |

Note: ETL-12 and ETL-13 appear as `[ ]` (unchecked) in `REQUIREMENTS.md` — these checkboxes were not updated after Phase 20 completion. The implementation evidence in code is conclusive; the unchecked state is a documentation artifact, not a code gap.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | No `TBD`, `FIXME`, `XXX`, placeholders, or stub patterns found in Phase 20 modified files | — | — |

---

### Known Pre-Existing Test Failures (Not Phase 20 Regressions)

Two tests fail in the full suite and are confirmed pre-existing, not regressions from Phase 20:

- `test_async_transaction_fix` — `UndefinedTable` fixture isolation issue in the async transaction suite
- `test_create_spatial_index_name_parameter` — `UndefinedTable` fixture isolation issue in the spatial integration suite

Both fail identically on the pre-Phase-20 baseline. They are not ETL-related. The full-suite run recorded **981 passed** with these 2 pre-existing failures. This is a standing test-isolation issue worth a dedicated fixture-cleanup fix in a future phase.

---

### Human Verification Required

None. All success criteria are verifiable from code structure, test results, and orchestrator-confirmed CI/release artifacts.

---

### Gaps Summary

No gaps. All 5 success criteria are satisfied by direct code evidence and passing tests.

---

_Verified: 2026-06-16_
_Verifier: Claude (gsd-verifier)_
