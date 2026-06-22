---
phase: 30-chunk-management-partitioning
verified: 2026-06-22T21:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
deferred:
  - truth: "All four methods have async counterparts verified by test_accessor_parity; coverage ratchet ≥94% holds — TS-ADV-10 full-9-method parity"
    addressed_in: "Phase 32"
    evidence: "REQUIREMENTS.md traceability table: 'TS-ADV-10 | Phase 32 | Pending'. Phase 30 verifies the 4 Phase-30 methods are mirrored (test_accessor_parity 7 passed); the remaining 5 methods land in Phases 31-32. Coverage 94.98% ≥ 94% is fully satisfied."
---

# Phase 30: Chunk Management & Partitioning — Verification Report

**Phase Goal:** Users can inspect and manage hypertable chunks, and add partitioning dimensions and a reorder policy, via `db.timescale.*` using the established pure-builder pattern with no new connection seams.
**Verified:** 2026-06-22T21:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `show_chunks` returns fully-qualified chunk names oldest-first; `older_than`/`newer_than` filter the subset (TS-ADV-04) | VERIFIED | `show_chunks` exists on both `TimescaleAccessor` and `AsyncTimescaleAccessor`; SQL constant `TSDB_SHOW_CHUNKS` contains `ORDER BY c.range_start ASC`; mock tests assert `[older_than, newer_than]` param order; 3 live-DB integration tests (incl. oldest-first ordering with 12-chunk hypertable) + async equivalent — 24 show_chunks/drop_chunks tests passed |
| 2 | `drop_chunks` deletes matching chunks; `dry_run` returns would-be-dropped list without deleting; both-None raises `ValueError` before any DB round-trip (TS-ADV-05) | VERIFIED | Behavioral spot-check confirmed: `drop_chunks('ht')` raises `ValueError` with `execute.call_count=0` and `has_extension.call_count=0`; mock test asserts dry_run issues only the capture SQL (not `SELECT drop_chunks(`); live-DB test confirms real drop reduces count and disjoint sets; all 4 docstrings mark DESTRUCTIVE/IRREVERSIBLE |
| 3 | `add_dimension` registers a dimension using TSDB 2.28 `by_hash`/`by_range` form; wrong type/param combo raises `ValueError` at construction time; duplicate dimension with `if_not_exists=False` raises `TimescaleError` (D-08 reshape, TS-ADV-08) | VERIFIED | Mock tests assert `by_hash('device_id', 4)` and `by_range('ts2', INTERVAL '7 days')` SQL shapes; 4 mutual-exclusivity ValueErrors tested (hash w/o number_partitions, hash w/ chunk_interval, range w/o chunk_interval, range w/ number_partitions); `DatabaseError` re-raised as `TimescaleError` confirmed via mock and live-DB; WR-01 fix: catch narrowed to `except DatabaseError` (not broad `Exception`); WR-03 fix: bool/float/non-positive `number_partitions` rejected at construction |
| 4 | `add_reorder_policy` generates SQL asserted by a mock unit test (authoritative); live test tolerates `FeatureNotSupported` under Apache license (D-12, TS-ADV-09) | VERIFIED | `TestAddReorderPolicyMock.test_add_reorder_policy_sql_shape` asserts `add_reorder_policy(`, `idx_events_ts`, `if_not_exists => true`, `public.events`; behavioral spot-check confirmed same SQL; live test wraps call in `try/except FeatureNotSupported: pass`; both sync and async variants present |
| 5 | All four methods have async counterparts verified by `test_accessor_parity`; coverage ratchet ≥94% holds | VERIFIED | `uv run pytest tests/test_parity.py -k accessor_parity -q -o addopts=""` → 7 passed; all 4 Phase-30 methods confirmed on both classes via `dir()`; all 4 async methods use `await self._db.schema.has_extension(...)` AND `await self._db.execute(...)`; full suite: 1239 passed, 94.98% coverage ≥ 94% ratchet; 2 failures are pre-existing flaky tests untouched by Phase 30 |

**Score:** 5/5 truths verified

### Deferred Items

Items not yet met but explicitly addressed in later milestone phases.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | TS-ADV-10 full-9-method parity (all 9 v0.8.0 methods mirrored) | Phase 32 | REQUIREMENTS.md traceability: `TS-ADV-10 | Phase 32 | Pending`. Phase 30 delivers 4 of 9 methods; Phases 31-32 add the remaining 5. The 4 Phase-30 methods are already parity-verified. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/exceptions.py` | `class TimescaleError(PycopgError)` | VERIFIED | Line 54-57: `class TimescaleError(PycopgError): "Error raised by TimescaleDB management operations." pass`; `issubclass(TimescaleError, PycopgError)` → True |
| `pycopg/queries.py` | `TSDB_SHOW_CHUNKS` with `%%I.%%I` and `ORDER BY range_start ASC` | VERIFIED | Lines 260-266: constant present with literal `%%I.%%I` JOIN key, `ORDER BY c.range_start ASC`, `{schema}.{table}{older_arg}{newer_arg}` format placeholders; `TSDB_DROP_CHUNKS` also present |
| `pycopg/timescale.py` | `show_chunks`, `drop_chunks`, `add_dimension`, `add_reorder_policy` on both `TimescaleAccessor` and `AsyncTimescaleAccessor` (8 method defs total) | VERIFIED | All 8 methods confirmed via `dir()` on both classes; sync methods at lines 338, 397, 493, 622; async methods at lines 923, 982, 1078, 1198 |
| `tests/test_timescale.py` | Mock SQL-shape + live-DB integration tests for all 4 methods, ts_db + async_ts_db fixtures, `FeatureNotSupported` import | VERIFIED | 1190 lines; `ts_db`/`async_ts_db` fixtures present; `from psycopg.errors import FeatureNotSupported` at line 26; `TestShowChunksMock`, `TestDropChunksMock`, `TestAddDimensionMock`, `TestAddReorderPolicyMock`, `TestShowChunksLive`, `TestDropChunksLive`, `TestAddDimensionLive`, `TestAddReorderPolicyLive` — all 8 test classes present |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `timescale.py show_chunks` | `queries.TSDB_SHOW_CHUNKS` | `queries.TSDB_SHOW_CHUNKS.format(schema=..., table=..., older_arg=..., newer_arg=...)` + `self._db.execute(sql, params)` | WIRED | Lines 388-394 (sync), 973-979 (async); format call confirmed; params built by `_build_chunk_bound_fragments` |
| `drop_chunks dry_run path` | `show_chunks capture query` | Capture-before-drop: `TSDB_SHOW_CHUNKS`-shaped query first, then `TSDB_DROP_CHUNKS` on non-dry_run | WIRED | Lines 472-491 (sync), 1057-1076 (async); dry_run short-circuits at line 481/1067 before drop SQL |
| `add_dimension` | `TimescaleError` | `except DatabaseError as exc: raise TimescaleError(...)` (D-08 reshape) | WIRED | Lines 614-620 (sync), 1190-1196 (async); catch narrowed to `DatabaseError` (WR-01 fix); `TimescaleError` imported at line 21 |
| `add_reorder_policy live test` | `psycopg.errors.FeatureNotSupported` | `try/except FeatureNotSupported: pass` | WIRED | `tests/test_timescale.py` lines 1159, 1186; imported at line 26 |
| `tests/test_timescale.py` | `ts_db` create-extension-or-skip fixture | ported from `TestDatabaseTimescaleCoverage` | WIRED | Lines 46-59: `has_extension` check + `create_extension` attempt + skip guard |

### Data-Flow Trace (Level 4)

All 4 methods are DDL/DML operations (not UI components). Data flow:

| Artifact | Data Path | Produces Real Data | Status |
|----------|-----------|-------------------|--------|
| `show_chunks` | `TSDB_SHOW_CHUNKS.format(...)` → `execute(sql, params)` → `[r["chunk_name"] for r in rows]` | Yes — DB returns actual chunk rows; no static fallback | FLOWING |
| `drop_chunks` | capture via `TSDB_SHOW_CHUNKS` → optional `TSDB_DROP_CHUNKS` → returns captured list | Yes — capture-before-drop pattern; live test verifies count decreases | FLOWING |
| `add_dimension` | `f"SELECT add_dimension('{schema}.{table}', {dim}{ne})"` → `execute(sql)` | Yes — DDL executed; live test queries `timescaledb_information.dimensions` to verify | FLOWING |
| `add_reorder_policy` | `f"SELECT add_reorder_policy('{schema}.{table}', '{index_name}'{ne}) AS job_id"` → `execute(sql)` | Yes on Community builds; propagates `FeatureNotSupported` on Apache (D-12) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `TimescaleError` subclasses `PycopgError` | `issubclass(TimescaleError, PycopgError)` | `True` | PASS |
| `TSDB_SHOW_CHUNKS` has `%%I.%%I` and `range_start ASC` | Python assertion | Both present | PASS |
| `show_chunks` exists as coroutine on async class | `inspect.iscoroutinefunction(AsyncTimescaleAccessor.show_chunks)` | `True` | PASS |
| `drop_chunks()` raises `ValueError` before any DB call | `drop_chunks('ht')` with mocked DB | `ValueError` raised; `execute.call_count=0`; `has_extension.call_count=0` | PASS |
| `add_dimension` hash without `number_partitions` raises `ValueError` | `add_dimension('ht','col',partition_type='hash')` | `ValueError: partition_type='hash' requires number_partitions` | PASS |
| `add_reorder_policy` SQL contains `add_reorder_policy(`, index name, `if_not_exists => true` | Mock assertion | `SELECT add_reorder_policy('public.ht', 'idx', if_not_exists => true) AS job_id` | PASS |
| `DatabaseError` from `execute` in `add_dimension` wrapped as `TimescaleError` | Mock: `execute` raises `DatabaseError('already a dimension')` | `TimescaleError` raised | PASS |
| All 4 async methods `await` both `has_extension` and `execute` | `inspect.getsource` check | All 4 confirmed | PASS |
| Full test suite: `tests/test_timescale.py` | `uv run pytest tests/test_timescale.py -q -o addopts=""` | 59 passed | PASS |
| Parity test | `uv run pytest tests/test_parity.py -k accessor_parity -q -o addopts=""` | 7 passed | PASS |
| Coverage ratchet | `uv run pytest` (full suite) | 94.98% ≥ 94%; 1239 passed, 2 pre-existing flaky failures | PASS |

### Probe Execution

No probe scripts (`scripts/*/tests/probe-*.sh`) defined for Phase 30. Behavioral spot-checks above serve as equivalent validation.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| TS-ADV-04 | Plans 01, 02 | `show_chunks` returning fully-qualified oldest-first `list[str]` | SATISFIED | `show_chunks` exists on both classes; `TSDB_SHOW_CHUNKS` with `ORDER BY range_start ASC`; live test asserts ordering; REQUIREMENTS.md traceability marked Complete |
| TS-ADV-05 | Plans 01, 02 | `drop_chunks` with `ValueError`/both-None guard, `dry_run` preview, DESTRUCTIVE docstring | SATISFIED | Both-None `ValueError` before DB confirmed; `dry_run` short-circuit verified; docstring marks DESTRUCTIVE/IRREVERSIBLE; capture-before-drop wired |
| TS-ADV-08 | Plans 01, 03 | `add_dimension` with `by_hash`/`by_range` form, construction-time `ValueError`, D-08 reshape | SATISFIED | SQL shapes asserted by mock tests; 4 mutual-exclusivity ValueErrors confirmed; `DatabaseError` → `TimescaleError` wrap confirmed; live-DB test passes |
| TS-ADV-09 | Plans 01, 03 | `add_reorder_policy` with mock-authoritative SQL assertion and Apache tolerance | SATISFIED | `TestAddReorderPolicyMock` is authoritative per D-12; live test wraps with `try/except FeatureNotSupported`; SQL shape confirmed by spot-check |
| TS-ADV-10 (partial) | Plan 03 | 4 Phase-30 methods mirrored on `AsyncTimescaleAccessor`; `test_accessor_parity` green | SATISFIED (for Phase-30 scope) | 7 parity tests pass; all 4 methods present on async class; all 4 async methods confirmed to `await` both guard and execute. Full 9-method TS-ADV-10 deferred to Phase 32. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `pycopg/exceptions.py` | 24, 30, 36, 48 | N818 "Exception name should have Error suffix" for pre-existing `ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier`, `DatabaseExists` | Info | Pre-existing across all phases; not introduced by Phase 30; no impact |
| `tests/setup_test_db.py` | 103 | W291 Trailing whitespace | Info | Pre-existing in a test setup utility; not a Phase 30 file |

No blockers. No TODOs, FIXMEs, or XXX markers in Phase 30 files. No stub return patterns (`return null`, `return []`, `return {}`) in `timescale.py`.

**Note on post-execution review fixes:** A code review after Plan 03 identified 3 substantive warnings:
- WR-01: `except Exception` in `add_dimension` narrowed to `except DatabaseError` (both sync and async) — confirmed fixed in commit `1325f29`
- WR-03: `number_partitions` validation (bool/float/non-positive rejected) — confirmed present in code at lines 563-574 (sync) and 1141-1152 (async)
- WR-04: `_build_chunk_bound_fragments` now raises `TypeError` for non-str/non-datetime bounds — confirmed present at lines 63-66 and 77-80

All 3 fixes are in the current codebase. 13 regression tests were added to cover them.

### Human Verification Required

None identified. All success criteria are verifiable programmatically. The Apache-license `FeatureNotSupported` tolerance for `add_reorder_policy` is verified by the mock-authoritative test (D-12 design decision explicitly accounts for this).

### Gaps Summary

No gaps. All 5 roadmap success criteria are verified against the actual codebase.

---

_Verified: 2026-06-22T21:00:00Z_
_Verifier: Claude (gsd-verifier)_
