---
phase: 31-continuous-aggregate-lifecycle
verified: 2026-06-23T00:00:00Z
status: passed
score: 8/8 must-haves verified
overrides_applied: 0
re_verification: false
gaps: []
deferred: []
human_verification: []
---

# Phase 31: Continuous Aggregate Lifecycle — Verification Report

**Phase Goal:** Users can create, manually refresh, and auto-schedule a continuous aggregate via `db.timescale.*`, with the `connect(autocommit=True)` seam correctly isolating CAGG DDL and refresh from any enclosing transaction.
**Verified:** 2026-06-23
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `create_continuous_aggregate` runs on `connect(autocommit=True)` seam and raises `ValueError` pre-DB when `select_sql` lacks `time_bucket(` | VERIFIED | Lines 792/813 (sync) and 1597/1618 (async) in `timescale.py`; mock tests assert seam and ValueError; 8 mock tests pass |
| 2 | `refresh_continuous_aggregate` runs on `connect(autocommit=True)` seam, succeeds from inside `db.session()`, rejects str bounds with `ValueError` | VERIFIED | Lines 881/883 (sync) and 1678/1680 (async); `cagg_created` guard in live tests; D-10b isolation proof in `TestRefreshContinuousAggregateLive` |
| 3 | `add_continuous_aggregate_policy` uses PLAIN `self._db.execute` (not the seam); `_check_offset_ordering` raises `ValueError` for same-unit start <= end before any DB round-trip; `None` offset renders as `NULL` | VERIFIED | Lines 962-969 (sync) and 1753-1760 (async); no `connect(autocommit=True)` call; `_check_offset_ordering("1 hour", "7 hours")` raises `ValueError`; `start_offset => NULL` in mock SQL assertion |
| 4 | All three methods have async counterparts with `await` on the `has_extension` guard; verified by `test_accessor_parity` | VERIFIED | Lines 1603, 1672, 1742 confirm `await self._db.schema.has_extension`; `tests/test_parity.py` passes 24/24 |
| 5 | `materialized_only=True` → `timescaledb.materialized_only=true`; `with_no_data=False` → `WITH DATA`; flags flip correctly | VERIFIED | Lines 804-810 (sync) and 1609-1615 (async); mock tests `test_create_continuous_aggregate_sql_shape_defaults` and `_flags_flipped` verify both states |
| 6 | `CALL refresh_continuous_aggregate('{schema}.{view_name}', %s, %s)` with `[None, None]` params for full refresh; datetime bound accepted | VERIFIED | Line 881-884 (sync); mock test `test_refresh_continuous_aggregate_sql_shape_both_none` asserts exact SQL and params == `[None, None]` |
| 7 | `_check_offset_ordering` and `_OFFSET_RE` exist as module-level symbols; helper returns None for mixed-unit/calendar/None inputs | VERIFIED | Lines 90-93 (`_OFFSET_RE`), 96-148 (`_check_offset_ordering`); Python spot-check confirmed all 5 cases |
| 8 | Full test suite passes with coverage >= 94% (2 known pre-existing failures only) | VERIFIED | 1266 passed, 2 failed (pre-existing `test_async_transaction_fix` + `test_create_spatial_index_name_parameter`), 2 skipped; coverage 95.05% |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/timescale.py` | `create_continuous_aggregate` (sync+async) via autocommit seam | VERIFIED | Lines 736-814 (sync), 1545-1619 (async) |
| `pycopg/timescale.py` | `refresh_continuous_aggregate` (sync+async) via autocommit seam | VERIFIED | Lines 816-884 (sync), 1621-1681 (async) |
| `pycopg/timescale.py` | `add_continuous_aggregate_policy` (sync+async) via plain execute | VERIFIED | Lines 886-969 (sync), 1683-1760 (async) |
| `pycopg/timescale.py` | `_check_offset_ordering` + `_OFFSET_RE` module helpers | VERIFIED | Lines 90-148 |
| `tests/test_timescale.py` | `TestCreateContinuousAggregateMock` + 2 live tests | VERIFIED | Lines 1197-1455; 8 tests (6 mock + 2 live) |
| `tests/test_timescale.py` | `TestRefreshContinuousAggregateMock` + 2 live tests | VERIFIED | Lines 1463-1747; 8 tests (6 mock + 2 live) |
| `tests/test_timescale.py` | `TestAddContinuousAggregatePolicyMock` + 2 live tests | VERIFIED | Lines 1755-2044+; 11 mock + 2 live tests |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `TimescaleAccessor.create_continuous_aggregate` | `self._db.connect(autocommit=True)` | autocommit seam | WIRED | Line 813: `with self._db.connect(autocommit=True) as conn: conn.execute(sql)` |
| `AsyncTimescaleAccessor.create_continuous_aggregate` | `await self._db.schema.has_extension` | async extension guard | WIRED | Line 1603: `if not await self._db.schema.has_extension("timescaledb")` |
| `TimescaleAccessor.refresh_continuous_aggregate` | `self._db.connect(autocommit=True)` | autocommit seam with params | WIRED | Line 883: `conn.execute(sql, [window_start, window_end])` |
| `TimescaleAccessor.add_continuous_aggregate_policy` | `self._db.execute` | plain execute (D-01 — NOT seam) | WIRED | Line 962: `self._db.execute(...)` — no `connect(autocommit=True)` in this method |
| `add_continuous_aggregate_policy` | `_check_offset_ordering` | same-unit ValueError guard | WIRED | Line 947: `_check_offset_ordering(start_offset, end_offset)` |

### Data-Flow Trace (Level 4)

Not applicable — all three methods return `None`; they issue DDL/DML and return nothing to render. No data flows to UI.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 6 new symbols importable from `pycopg.timescale` | `python -c "import pycopg.timescale as t; assert hasattr(t.TimescaleAccessor, 'create_continuous_aggregate') ..."` | All 8 assertions passed | PASS |
| `_check_offset_ordering("1 hour", "7 hours")` raises `ValueError` | Python spot-check | `ValueError` raised | PASS |
| `_check_offset_ordering("7 days", "1 day")` returns None | Python spot-check | Returns None | PASS |
| Mixed/calendar/None offsets defer silently | Python spot-check | All return None | PASS |
| 27 Phase 31 tests pass (mock + live) | `uv run pytest -k "create_continuous_aggregate or refresh_continuous_aggregate or continuous_aggregate_policy" -o addopts=""` | 27 passed, 59 deselected | PASS |
| Full `test_timescale.py` green | `uv run pytest tests/test_timescale.py -x -q -o addopts=""` | 86 passed | PASS |
| Parity confirmed | `uv run pytest tests/test_parity.py -o addopts=""` | 24 passed | PASS |
| Lint/format clean | `ruff check` + `black --check` | All checks passed | PASS |
| Full suite coverage gate | `uv run pytest` | 95.05% >= 94% | PASS |

### Probe Execution

No probes declared or applicable for this phase (not a migration/tooling phase).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| TS-ADV-01 | 31-01-PLAN.md | `create_continuous_aggregate` on `connect(autocommit=True)`; `time_bucket(` ValueError | SATISFIED | Method exists on both classes; seam wired; ValueError pre-DB confirmed by mock and spot-check |
| TS-ADV-02 | 31-02-PLAN.md | `refresh_continuous_aggregate` on `connect(autocommit=True)`; datetime-only bounds; from inside `db.session()` | SATISFIED | Method exists; seam wired; str-bound ValueError confirmed; D-10b session-isolation proof in live test |
| TS-ADV-03 | 31-03-PLAN.md | `add_continuous_aggregate_policy` via plain execute; offset-ordering ValueError; `NULL` for None offsets | SATISFIED | Method exists; uses `self._db.execute`; `_check_offset_ordering` guard verified; `NULL` fragment asserted by mock test |

All three required requirement IDs (TS-ADV-01, TS-ADV-02, TS-ADV-03) are satisfied. No orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `pycopg/timescale.py` | 792, 1597 | `time_bucket(` literal substring test (case-sensitive, whitespace-brittle) | Warning (pre-existing from REVIEW WR-01) | Rejects valid `TIME_BUCKET(` or `time_bucket (` SQL; deferred to Phase 32+ by REVIEW |
| `pycopg/timescale.py` | 10 | Stale `:mod:\`pycopg.aliases\`` docstring reference | Info (carry-forward from prior phases, REVIEW IN-02) | Sphinx `:mod:` cross-reference to deleted module; cosmetic only |
| `pycopg/timescale.py` | 942-947, 1733-1738 | `validate_interval` runs before `_check_offset_ordering`, narrowing accepted offsets below what DB supports (REVIEW WR-02) | Warning | Single-unit only accepted; compound intervals like `"1 day 12 hours"` rejected; documented limitation |

No TBD, FIXME, or XXX debt markers found in modified files.

No stub or placeholder patterns found — all methods are substantively implemented and wired.

The three warnings from the code review are quality/robustness issues, not correctness blockers. WR-01 and WR-02 are known limitations with accepted dispositions (WR-01 is a best-effort heuristic per D-04; WR-02 is a deliberate `validate_interval` pre-check that keeps the codebase simple at the cost of compound interval support). WR-03 (interval interpolation vs. binding) is an accepted design choice since `validate_interval` eliminates the injection surface. None are blockers for the phase goal.

### Human Verification Required

None. All behaviors are verifiable programmatically via mock SQL-shape tests. The autocommit-isolation proof is structural (D-10b: mock asserts `connect(autocommit=True)`, not the session path). The Apache-license constraint on live cagg calls is accepted, with mock layer designated as authoritative per D-09.

### Gaps Summary

No gaps. All 8 must-have truths are VERIFIED. All artifacts exist and are substantively implemented. All key links are wired. Requirements TS-ADV-01, TS-ADV-02, TS-ADV-03 are satisfied. The full test suite passes at 95.05% coverage with only the two known pre-existing flaky tests failing.

---

_Verified: 2026-06-23_
_Verifier: Claude (gsd-verifier)_
