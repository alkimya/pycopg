---
phase: 38-performance-copy
plan: "03"
subsystem: core
tags: [performance, insert_batch, micro-opt, parity]
dependency_graph:
  requires: ["38-01"]
  provides: [hoisted-row-placeholders-sync, hoisted-row-placeholders-async, PERF-03-non-regression-test]
  affects: [pycopg/database.py, pycopg/async_database.py, tests/test_database.py]
tech_stack:
  added: []
  patterns: [loop-invariant-hoist, builder-pur, sync-async-parity, mock-based-non-regression]
key_files:
  created: []
  modified:
    - pycopg/database.py
    - pycopg/async_database.py
    - tests/test_database.py
decisions:
  - "D-05 applied: row_placeholders hoisted before for-row loop in both sync and async insert_batch — strictly byte-exact (SQL + params unchanged)"
  - "Non-regression test uses mock_psycopg pattern, asserts exact (%s, %s) tuple count and flat params order — no timing assertions (D-06)"
metrics:
  duration: "2m 53s"
  completed: "2026-06-26"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
---

# Phase 38 Plan 03: insert_batch placeholder hoist (D-05) Summary

**One-liner:** Hoisted `row_placeholders = ", ".join(["%s"] * len(columns))` out of the per-row loop in both sync and async `insert_batch`; byte-exact SQL/params guaranteed by a mock-based non-regression test.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Hoist row_placeholders out of per-row loop (sync + async, D-05) | dcf0c65 | database.py, async_database.py |
| 2 | Byte-exact non-regression test for insert_batch placeholder hoist (PERF-03) | 25a03b9 | tests/test_database.py |

## What Was Built

### Task 1: row_placeholders hoist (D-05)

In both `Database.insert_batch` (database.py) and `AsyncDatabase.insert_batch` (async_database.py), the line:

```python
row_placeholders = ", ".join(["%s"] * len(columns))
```

was moved from inside `for row in batch:` to immediately before the loop (once per batch). The `for row in batch:` body retains `placeholders.append(f"({row_placeholders})")` and `params.extend(row.get(col) for col in columns)` unchanged. The produced INSERT SQL and params are byte-exact identical — only the computation site moves.

- `database.py` L1046: hoisted before `for row in batch:` (was inside)
- `async_database.py` L697: identical hoist for sync/async parity (PERF-05)
- Signatures unchanged; non-breaking

### Task 2: Non-regression test (PERF-03)

Added `test_insert_batch_placeholder_hoist_regression` to `tests/test_database.py` (class `TestInsertBatch`). Uses the established `mock_psycopg` pattern:

- Inserts 3 rows × 2 columns (`name`, `score`)
- Captures `(sql, params)` from `mock_cursor.execute.call_args`
- Asserts `sql.count("(%s, %s)") == 3` — one placeholder tuple per row
- Asserts `list(params) == ["Alice", 10, "Bob", 20, "Carol", 30]` — flat column-ordered values
- Mock-based, deterministic, no timing assertions (D-06)

## Verification Results

- `uv run ruff check pycopg tests`: **0 errors**
- `uv run interrogate -f 100 pycopg/database.py pycopg/async_database.py`: **PASSED (100%)**
- `tests/test_database.py -k insert_batch`: **6 passed** (5 original + 1 new)
- `tests/test_database_integration.py -k insert_batch`: **1 passed**
- `tests/test_database.py + tests/test_async_database.py` full: **309 passed**
- Sync/async parity confirmed

## Deviations from Plan

None — plan executed exactly as written. The hoist was applied at the exact sites specified (database.py ~L983, async_database.py ~L624 — actual current lines L1046 and L697 after Phase 38-01/02 additions). `row_placeholders` is now computed once before the per-row loop in both implementations.

## Known Stubs

None.

## Threat Flags

No new security surface introduced. The hoist touches no identifier-handling code (`validate_identifiers`/`validate_identifier` still run first), and no new interpolation or parameterization was added. T-38-07 and T-38-08 dispositions from the plan's threat model remain unchanged.

## Self-Check: PASSED

- pycopg/database.py: FOUND (L1046 row_placeholders before for row in batch)
- pycopg/async_database.py: FOUND (L697 row_placeholders before for row in batch)
- tests/test_database.py: FOUND (test_insert_batch_placeholder_hoist_regression)
- dcf0c65: FOUND in git log
- 25a03b9: FOUND in git log
