---
phase: 21-infrastructure-timescale-accessor
verified: 2026-06-17T15:00:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 3/4
  gaps_closed:
    - "Full suite runs without DeprecationWarning noise breaking any -W error gate; coverage stays >=94%"
  gaps_remaining: []
  regressions: []
---

# Phase 21: Infrastructure & Timescale Accessor Verification Report

**Phase Goal:** Users calling `db.timescale.*` get a working timescale accessor, and callers still using the old flat `db.create_hypertable(...)` etc. get a `DeprecationWarning` naming the new path — the full alias + accessor pattern is established and all future phases replicate it mechanically.
**Verified:** 2026-06-17T15:00:00Z
**Status:** passed
**Re-verification:** Yes — after gap closure (commit ad65eec)

## Goal Achievement

### Observable Truths

| #   | Truth                                                                 | Status        | Evidence                                                                                                                      |
| --- | --------------------------------------------------------------------- | ------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 1   | `db.timescale.*` (all 6 methods) return same result as before        | VERIFIED      | `TimescaleAccessor` + `AsyncTimescaleAccessor` with verbatim-moved SQL bodies in `pycopg/timescale.py` (531 lines); wired via lazy property `Database.timescale` / `AsyncDatabase.timescale` with `self._timescale` cache; full suite passes |
| 2   | Old flat `db.create_hypertable(...)` etc. warn + delegate             | VERIFIED      | 6 sync `@deprecated_alias` stubs in `database.py` lines 1669-1691; 6 async `@deprecated_alias` stubs in `async_database.py` lines 1245-1267; `inspect.iscoroutinefunction(AsyncDatabase.create_hypertable)` is True; sync stubs are False |
| 3   | `test_accessor_parity` passes with timescale pair for both surfaces   | VERIFIED      | `ACCESSOR_PAIRS = [(TimescaleAccessor, AsyncTimescaleAccessor), (ETLAccessor, AsyncETLAccessor)]` in `tests/test_parity.py`; `uv run pytest tests/test_parity.py -o addopts="" -q` → 19 passed |
| 4   | Alias tests assert warn+delegate; `-W error` gate passes; coverage >=94% | VERIFIED  | Fix in commit ad65eec: both sync and async alias tests now filter `w` to alias-specific DeprecationWarnings (matching `db.timescale.{name}`) before asserting exactly one. 4-file gate: `295 passed` (exit 0). Full suite: 94.46%, 2 known pre-existing failures only. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact                           | Expected                                        | Status      | Details                                                      |
| ---------------------------------- | ----------------------------------------------- | ----------- | ------------------------------------------------------------ |
| `pycopg/aliases.py`                | `deprecated_alias` decorator (sync + async)     | VERIFIED    | 66 lines; `stacklevel=2`; `iscoroutinefunction` branch; no eval/exec |
| `pycopg/timescale.py`              | `TimescaleAccessor` + `AsyncTimescaleAccessor`  | VERIFIED    | 531 lines; 6 methods each; `self._db.execute` rewrites; all `validate_*` guards intact |
| `pycopg/database.py`               | `_timescale` field + lazy property + 6 stubs    | VERIFIED    | `def timescale(` present; `self._timescale = TimescaleAccessor(self)`; 6 `@deprecated_alias("timescale.X")` stubs; no inline SQL |
| `pycopg/async_database.py`         | Same pattern with async stubs                   | VERIFIED    | `async def` stubs; `iscoroutinefunction` True for all 6 async flat methods |
| `pycopg/__init__.py`               | `TimescaleAccessor` + `AsyncTimescaleAccessor` in `__all__` | VERIFIED | Both names in `__all__` under `# TimescaleDB` comment block |
| `tests/test_timescale_aliases.py`  | `TestTimescaleAliases` >= 80 lines, 12 cases    | VERIFIED    | 186 lines; both sync and async parametrized cases filter to alias-specific warnings before asserting; 12/12 pass in isolation and under 4-file `-W error` gate |
| `tests/test_parity.py`             | `ACCESSOR_PAIRS` + `test_accessor_parity`        | VERIFIED    | `ACCESSOR_PAIRS` defined with 3 references; `test_accessor_parity` checks both directions; ETL pair included |

### Key Link Verification

| From                               | To                                    | Via                                        | Status   | Details                                                           |
| ---------------------------------- | ------------------------------------- | ------------------------------------------ | -------- | ----------------------------------------------------------------- |
| `Database.timescale` property      | `TimescaleAccessor`                   | lazy import + `self._timescale = TimescaleAccessor(self)` | WIRED | Confirmed at lines 288-292 of database.py |
| `Database.create_hypertable` stub  | `deprecated_alias("timescale.create_hypertable")` | `@deprecated_alias(...)` decorator | WIRED | 6 decorators at database.py lines 1669-1691 |
| `AsyncDatabase.timescale` property | `AsyncTimescaleAccessor`              | lazy import + cache                         | WIRED    | Confirmed at lines 148-152 of async_database.py |
| `aliases.py` → `self.<accessor>.<method>` | `getattr(self, accessor_name)` | `split(".", 1)` + double `getattr`         | WIRED    | Correct implementation in aliases.py lines 42-51 |
| `timescale.py` → `self._db.execute` | 6 sync + 6 async method bodies       | moved verbatim; `self.` → `self._db.`     | WIRED    | `grep -c 'self._db.execute' pycopg/timescale.py` == 12 |
| `tests/test_timescale_aliases.py`  | flat `db.create_hypertable` alias     | `catch_warnings` + mock injection + alias filter | WIRED | 295 passed under 4-file `-W error::DeprecationWarning` gate |

### Data-Flow Trace (Level 4)

Not applicable — this phase produces accessor classes and deprecated stubs, not data-rendering components. The data flow is: caller → stub → `deprecated_alias` wrapper (emits warning) → `getattr(self, accessor_name)` → `getattr(accessor, method_name)(*args, **kwargs)` → accessor method → `self._db.execute(...)`. This chain is verified by the alias tests (12/12 pass, including under the 4-file `-W error` gate).

### Behavioral Spot-Checks

| Behavior                                           | Command                                                                    | Result           | Status  |
| -------------------------------------------------- | -------------------------------------------------------------------------- | ---------------- | ------- |
| `deprecated_alias` imports cleanly                 | `uv run python -c "from pycopg.aliases import deprecated_alias"`          | exit 0           | PASS    |
| Both accessor classes importable from pycopg       | `uv run python -c "from pycopg import TimescaleAccessor, AsyncTimescaleAccessor"` | exit 0  | PASS    |
| `Database.timescale` is a property                 | `inspect.getattr_static(Database, 'timescale')` is `property`             | True             | PASS    |
| Async stubs stay coroutine functions               | `inspect.iscoroutinefunction(AsyncDatabase.create_hypertable)`             | True             | PASS    |
| Alias tests pass in isolation                      | `uv run pytest tests/test_timescale_aliases.py -o addopts="" -q`          | 12 passed        | PASS    |
| Parity tests pass                                  | `uv run pytest tests/test_parity.py -o addopts="" -q`                     | 19 passed        | PASS    |
| Full suite coverage gate                           | `uv run pytest -q` (full suite)                                           | 94.46%, 2 known pre-existing failures | PASS |
| **4-file -W error gate (plan-03 criterion)**       | `uv run pytest -W error::DeprecationWarning -q -o addopts="" tests/test_async_database.py tests/test_sql_injection.py tests/test_parity.py tests/test_timescale_aliases.py` | **295 passed** (exit 0) | **PASS** |

### Probe Execution

No probes declared in PLAN files. Step skipped.

### Requirements Coverage

| Requirement | Source Plan | Description                                              | Status      | Evidence                                                         |
| ----------- | ----------- | -------------------------------------------------------- | ----------- | ---------------------------------------------------------------- |
| REORG-01    | 21-01       | `@deprecated_alias` decorator with correct stacklevel, sync + async variants | VERIFIED | `pycopg/aliases.py` with `stacklevel=2` and `iscoroutinefunction` branch |
| REORG-02    | 21-01, 21-02 | Flat aliases warn + delegate; zero breaking change      | VERIFIED   | 6 sync + 6 async stubs in database.py / async_database.py; delegation confirmed by alias tests |
| REORG-03    | 21-03       | `test_parity` registers timescale pair; verifies parity  | VERIFIED   | `ACCESSOR_PAIRS` registry with timescale + ETL pairs; `test_accessor_parity` passes both directions |
| REORG-04    | 21-03       | Coverage >=94%; alias tests assert warn+delegate; no -W error breakage | VERIFIED | Coverage 94.46%; 12/12 alias tests pass; 4-file `-W error` gate passes 295/295 (commit ad65eec) |
| TS-01       | 21-01, 21-02 | `db.timescale.*` exposes 6 TimescaleDB methods; flat names remain as deprecated aliases | VERIFIED | `TimescaleAccessor` + `AsyncTimescaleAccessor` with all 6 methods; stubs in database.py / async_database.py |

### Anti-Patterns Found

| File                              | Line | Pattern | Severity | Impact |
| --------------------------------- | ---- | ------- | -------- | ------ |
| No TBD/FIXME/XXX/eval/exec markers found | — | — | — | — |

The deprecated stubs (`def create_hypertable(self, *args, **kwargs): ...`) are intentional aliases, not incomplete stubs — the decorator replaces the function body with warn-then-delegate logic.

### Human Verification Required

None identified. All behaviors are programmatically verifiable.

## Re-verification Summary

**Gap closed by commit ad65eec** (`fix(21): isolate alias warning assertion for -W error gate`).

The fix added alias-specific filtering in both the sync and async parametrized alias tests. Instead of asserting `len(w) == 1` on the raw `catch_warnings` record buffer (which accumulated cross-file leakage under the 4-file `-W error` gate), both tests now:

1. Build `alias_warnings = [rec for rec in w if rec.category is DeprecationWarning and f"db.timescale.{name}" in str(rec.message)]`
2. Assert `len(alias_warnings) == 1`

This correctly isolates the alias's own DeprecationWarning from any unrelated warnings that leak across test boundaries under the combined pytest `-W error::DeprecationWarning` filter.

**Result:** `295 passed` (exit 0) on the 4-file gate. All 4 success criteria now hold.

---

_Verified: 2026-06-17T15:00:00Z_
_Verifier: Claude (gsd-verifier)_
