---
phase: 31-continuous-aggregate-lifecycle
plan: "03"
subsystem: timescale
tags: [timescaledb, continuous-aggregate, policy, plain-execute, tdd, sync, async, d-01, d-07, d-09]
dependency_graph:
  requires: [31-01, 31-02]
  provides: [add_continuous_aggregate_policy-sync, add_continuous_aggregate_policy-async, _check_offset_ordering, _OFFSET_RE]
  affects: [pycopg/timescale.py, tests/test_timescale.py]
tech_stack:
  added: []
  patterns:
    - "plain self._db.execute (D-01) for SELECT add_*_policy — NOT the autocommit seam"
    - "_OFFSET_RE + _check_offset_ordering module-level best-effort same-unit guard (D-07)"
    - "None offset renders as SQL literal NULL (not INTERVAL 'None')"
    - "mock-authoritative + live-tolerant pattern for Apache-licensed TimescaleDB Community features (D-09)"
    - "async await-guard (Phase-23 catch) verified by AsyncMock no-extension test"
key_files:
  created: []
  modified:
    - pycopg/timescale.py
    - tests/test_timescale.py
decisions:
  - "D-01 confirmed: add_continuous_aggregate_policy uses plain self._db.execute (not the autocommit seam) — matches add_reorder_policy/add_compression_policy/add_retention_policy"
  - "D-07: _check_offset_ordering is best-effort same-unit only; mixed/calendar/None defer to DB"
  - "D-09: mock-authoritative + live-tolerant (try/except FeatureNotSupported) for all cagg policy tests"
  - "None offset renders as SQL literal NULL via branched fragment (not INTERVAL 'None')"
metrics:
  duration: "~20 minutes"
  completed: "2026-06-23"
  tasks_completed: 3
  files_changed: 2
---

# Phase 31 Plan 03: add_continuous_aggregate_policy Summary

**One-liner:** `add_continuous_aggregate_policy` (sync + async) via plain `self._db.execute` (D-01) with `_check_offset_ordering` best-effort guard, `NULL`-for-None offsets, mock-authoritative SQL-shape tests, license-tolerant live integration tests, and the final 3-method `test_accessor_parity` confirmation.

## What Was Built

### Task 1: Add _check_offset_ordering helper + import re
**Commit:** `1aa48b6`
**Files:** `pycopg/timescale.py`

Added `import re` to the stdlib import block. Defined two module-level symbols:

- `_OFFSET_RE = re.compile(r"^(\d+)\s+(second|minute|hour|day|week)s?$", re.IGNORECASE)` — matches fixed-duration interval literals (excludes calendar units `month`/`year` intentionally).
- `_check_offset_ordering(start_offset, end_offset) -> None` — best-effort same-unit guard (D-07): raises `ValueError` when both offsets share a fixed-duration unit and `start_count <= end_count`; silently returns for `None`, mixed-unit, or calendar offsets (DB is the final authority for those).

Guard behavior verified:
- `_check_offset_ordering("1 hour", "7 hours")` → `ValueError`
- `_check_offset_ordering("7 days", "1 day")` → `None` (longer window is start; no error)
- `_check_offset_ordering("1 day", "6 hours")` → `None` (mixed units, deferred)
- `_check_offset_ordering("1 month", "1 day")` → `None` (calendar deferred)
- `_check_offset_ordering(None, "1 day")` → `None` (open-ended deferred)

### Task 2: Implement add_continuous_aggregate_policy (sync + async) via plain execute
**Commit:** `2abdab5`
**Files:** `pycopg/timescale.py`

Added `add_continuous_aggregate_policy` to both `TimescaleAccessor` (sync, inserted before `class AsyncTimescaleAccessor:`) and `AsyncTimescaleAccessor` (async, appended at end of file).

Guard/validate order (both classes):
1. `validate_identifiers(view_name, schema)` — pre-DB identifier safety
2. `if start_offset is not None: validate_interval(start_offset)` — skip None (open-ended)
3. `if end_offset is not None: validate_interval(end_offset)` — skip None
4. `_check_offset_ordering(start_offset, end_offset)` — D-07 best-effort same-unit ValueError
5. `validate_interval(schedule_interval)` — always required
6. Extension guard (sync: `self._db.schema.has_extension`; async: `await self._db.schema.has_extension`) — MANDATORY `await` on async (Phase-23 catch)

Rendered SQL (plain `self._db.execute`, NOT the autocommit seam — D-01):
```
SELECT add_continuous_aggregate_policy('{schema}.{view_name}',
  start_offset => {NULL | INTERVAL '{start_offset}'},
  end_offset => {NULL | INTERVAL '{end_offset}'},
  schedule_interval => INTERVAL '{schedule_interval}'
  [, if_not_exists => true]) AS job_id
```

Key design choices:
- `None` offset → `NULL` fragment (not `INTERVAL 'None'`)
- `if_not_exists=True` (default) → `, if_not_exists => true`; `False` → omitted
- `FeatureNotSupported` (0A000) propagates — no swallow (D-09)

### Task 3: Mock SQL-shape + live-tolerant tests + final 3-method parity gate
**Commit:** `26a64a0`
**Files:** `tests/test_timescale.py`

Added two test classes:

**`TestAddContinuousAggregatePolicyMock`** (9 tests — authoritative per D-09):
- `test_add_continuous_aggregate_policy_sql_shape_defaults` — verifies named-arg SQL form, `db.execute` called, `db.connect` NOT called (plain execute confirmed)
- `test_add_continuous_aggregate_policy_if_not_exists_false` — verifies `if_not_exists` fragment absent
- `test_add_continuous_aggregate_policy_none_start_offset_renders_null` — `None` start → `start_offset => NULL`
- `test_add_continuous_aggregate_policy_none_end_offset_renders_null` — `None` end → `end_offset => NULL`
- `test_add_continuous_aggregate_policy_offset_ordering_same_unit_raises` — `"1 hour"/"7 hours"` raises `ValueError` before any execute
- `test_add_continuous_aggregate_policy_offset_ordering_mixed_unit_no_raise` — `"1 day"/"6 hours"` does NOT raise in Python
- `test_add_continuous_aggregate_policy_no_extension_raises` — `ExtensionNotAvailable`; execute + connect not called
- `test_add_continuous_aggregate_policy_async_sql_shape` — async mirror with `AsyncMock`
- `test_add_continuous_aggregate_policy_async_no_extension_raises` — Phase-23 `await`-omission catch

**`TestAddContinuousAggregatePolicyLive`** (2 tests — license-tolerant):
- `test_add_continuous_aggregate_policy_live` — builds hypertable + cagg (tolerate create error), calls policy in `try/except FeatureNotSupported: pass`; on Community builds asserts `timescaledb_information.jobs` row + `CALL run_job(job_id)` succeeds
- `test_add_continuous_aggregate_policy_async_live` — async mirror

`test_accessor_parity` (no changes to `test_parity.py`) confirms all 3 new cagg methods are mirrored on `AsyncTimescaleAccessor`.

## Verification Results

```
uv run pytest tests/test_timescale.py -k continuous_aggregate_policy -o addopts=""
# 11 passed, 75 deselected

uv run pytest tests/test_parity.py -o addopts=""
# 24 passed

uv run pytest tests/test_timescale.py -x -q -o addopts=""
# 86 passed

uv run pytest
# 1266 passed, 2 failed (pre-existing flaky), 2 skipped
# Coverage: 95.05% (above 94% ratchet)

uv run ruff check pycopg/timescale.py tests/test_timescale.py
# All checks passed

uv run black --check pycopg/timescale.py tests/test_timescale.py
# 2 files would be left unchanged
```

## Commits

| Task | Name | Commit |
|------|------|--------|
| 1 | Add _check_offset_ordering helper + import re | 1aa48b6 |
| 2 | Implement add_continuous_aggregate_policy (sync + async) | 2abdab5 |
| 3 | Mock SQL-shape + live-tolerant tests + parity gate | 26a64a0 |

## Deviations from Plan

### Auto-fixed Issues

None - plan executed exactly as written.

The implementation matches the RESEARCH skeleton verbatim (lines 339-377), including the exact `_OFFSET_RE` pattern, the `_check_offset_ordering` logic, and the `NULL`-for-None offset branching. The test classes mirror `TestAddReorderPolicyMock` as specified.

## Threat Surface Scan

T-31-07 (SQL injection via `view_name`/`schema`) — mitigated via `validate_identifiers(view_name, schema)` as required.
T-31-08 (SQL injection via interval offsets/schedule) — mitigated via `validate_interval()` on each non-None offset and `schedule_interval` before interpolation.
T-31-09 (offset-ordering guard) — pure stdlib `re` regex; raises `ValueError` only; no eval/exec.

No new security-relevant surface introduced beyond what is documented in the threat model.

## Known Stubs

None — `add_continuous_aggregate_policy` is fully wired via plain `self._db.execute` and exercised by both mock and live tests.

## Self-Check: PASSED

- `pycopg/timescale.py` contains `def add_continuous_aggregate_policy(` and `async def add_continuous_aggregate_policy(`
- `pycopg/timescale.py` contains `import re`, `_OFFSET_RE = re.compile(`, and `def _check_offset_ordering(`
- `tests/test_timescale.py` contains `class TestAddContinuousAggregatePolicyMock`, `def test_add_continuous_aggregate_policy_live`, and `test_add_continuous_aggregate_policy_async_live`
- Commit 1aa48b6 exists
- Commit 2abdab5 exists
- Commit 26a64a0 exists
