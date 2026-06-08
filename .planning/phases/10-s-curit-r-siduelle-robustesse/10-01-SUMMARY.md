---
phase: 10-s-curit-r-siduelle-robustesse
plan: "01"
subsystem: pool, security-audit
tags: [bug-fix, security, b1, sec-01, sec-05, pool, commit, injection]
dependency_graph:
  requires: []
  provides:
    - "PooledDatabase.execute commits before returning RETURNING rows (B1 fix)"
    - "AsyncPooledDatabase.execute commits before returning RETURNING rows (B1 fix)"
    - "D-01 audit: all 17 SEC-05 + Success-Criterion-#1 validations confirmed acquired"
    - "Red->green regression test for B1 (INSERT...RETURNING persistence)"
  affects:
    - pycopg/pool.py
    - tests/test_pool_commit.py
    - .planning/phases/10-s-curit-r-siduelle-robustesse/10-AUDIT-D01.md
tech_stack:
  added: []
  patterns:
    - "Commit-before-return pattern: capture rows, commit, then return"
    - "Real-DB integration test (D-06 form) for pool transaction semantics"
    - "Audit-as-artifact: D-01 checklist documents call sites and covering tests"
key_files:
  created:
    - tests/test_pool_commit.py
    - .planning/phases/10-s-curit-r-siduelle-robustesse/10-AUDIT-D01.md
  modified:
    - pycopg/pool.py
decisions:
  - "B1 fix: restructure both execute methods to capture rows, then commit, then return (commit precedes fetchall return on RETURNING path)"
  - "D-01 audit result: all 17 items ACQUIRED, no new production code added"
  - "D-06 form for B1 test: real-DB integration (pool transaction semantics not mockable)"
metrics:
  duration: "9 minutes"
  completed: "2026-06-08T20:31:37Z"
  tasks_completed: 3
  tasks_total: 3
  files_changed: 2
  files_created: 2
requirements: [SEC-01, SEC-05, SEC-06]
---

# Phase 10 Plan 01: B1 Fix + D-01 Audit Summary

**One-liner:** Fixed `PooledDatabase.execute` silent data loss on INSERT...RETURNING (commit before return), added real-DB regression test, and confirmed all 17 v0.3.1 injection mitigations are acquired with covering tests.

---

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix B1 — commit before RETURNING rows (sync + async) | f6dd305 | `pycopg/pool.py` |
| 2 | Red->green regression test for B1 | cec96e3 | `tests/test_pool_commit.py` |
| 3 | D-01 audit — SEC-05 + Success-Criterion-#1 validations | 650a4ff | `.planning/phases/10-s-curit-r-siduelle-robustesse/10-AUDIT-D01.md` |

---

## What Was Built

### Task 1: B1 Fix (SEC-01, D-03)

**Bug:** In both `PooledDatabase.execute` and `AsyncPooledDatabase.execute`, the control flow committed only on the no-`description` (non-SELECT) branch. When `cur.description` was truthy (INSERT...RETURNING, SELECT), the code returned rows immediately, BEFORE calling `conn.commit()`. This caused the connection to be returned to the pool with an open uncommitted transaction, which psycopg rolled back on return — silent data loss.

**Fix applied:**

Before (buggy):
```python
if cur.description:
    return cur.fetchall()   # returns without committing!
conn.commit()
return []
```

After (fixed):
```python
rows = cur.fetchall() if cur.description else []
conn.commit()
return rows
```

Same fix applied to `AsyncPooledDatabase.execute` with `await`. `execute_many` was NOT touched (already correct).

### Task 2: Regression Test (D-06 form: real-DB integration)

Created `tests/test_pool_commit.py` with:
- `test_insert_returning_persists_after_pool_return` — 3 separate pool checkouts: CREATE TABLE (fixture), INSERT...RETURNING (captures id), SELECT on separate checkout (proves row persists). This test FAILS on pre-fix code and PASSES on fixed code.
- `test_insert_without_returning_still_commits` — guards non-RETURNING path against regression.
- `test_multiple_returning_rows_all_persist` — verifies multi-row INSERT...RETURNING.

D-06 rationale: the bug only manifests across pool checkouts; mocks cannot reproduce psycopg's transaction rollback-on-return semantics.

Tests verified passing with local PostgreSQL (unix socket, `loc` user) and designed for CI `timescale/timescaledb-ha` service.

### Task 3: D-01 Audit (SEC-05, Success-Criterion-#1)

Produced `.planning/phases/10-s-curit-r-siduelle-robustesse/10-AUDIT-D01.md` with 17-item checklist:
- 16 Success-Criterion-#1 items (compression policy, retention policy, spatial index, vacuum, analyze, drop_index, dataframe table/column, insert_many, upsert_many, valid_until create/alter role, create_extension schema, grant/revoke privilege whitelist, grant/revoke object_type, CSV options)
- 1 SEC-05 row (async `create_role` validates `name` identifier + `valid_until` timestamp up-front)

**Result:** ALL 17 items marked ACQUIRED. Zero gaps found. Zero new production code written.
**Injection test suite:** 64 tests, all passing.

---

## Deviations from Plan

None — plan executed exactly as written.

The only notable finding: local PostgreSQL requires `loc` user via Unix socket (`/var/run/postgresql`) rather than `postgres`/password. This is expected for a development environment; the CI workflow uses `timescale/timescaledb-ha` with `POSTGRES_PASSWORD=postgres` where the tests will run correctly.

---

## Known Stubs

None — all code is functional with no placeholder values.

---

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The B1 fix is an in-place edit of existing methods. No new threat surface.

---

## Self-Check

| Check | Result |
|-------|--------|
| `pycopg/pool.py` exists | FOUND |
| `tests/test_pool_commit.py` exists | FOUND |
| `10-AUDIT-D01.md` exists | FOUND |
| `10-01-SUMMARY.md` exists | FOUND |
| commit f6dd305 (Task 1) | FOUND |
| commit cec96e3 (Task 2) | FOUND |
| commit 650a4ff (Task 3) | FOUND |

## Self-Check: PASSED
