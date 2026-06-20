---
phase: 27-incremental-etl-run-log-integration
verified: 2026-06-20T14:43:37Z
status: passed
score: 6/6 must-haves verified
verdict: pass
overrides_applied: 0
re_verification: false
---

# Phase 27: Incremental ETL Run-Log Integration — Verification Report

**Phase Goal:** Wire the Phase-26 typed watermark envelope through the sync run-log persistence layer and prove four success-only persistence invariants against a real PostgreSQL DB: `_read_watermark`, `_end_run(watermark=)`, and `run()` max(col) capture.
**Verified:** 2026-06-20T14:43:37Z
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC-1 / ETL-INC-02: First run persists `watermark = max(incremental_column)` as non-NULL JSONB envelope | VERIFIED | `test_first_run_records_watermark` passes; row asserts `{"type": "int", "value": 5}` and `_read_watermark == 5` against real DB |
| 2 | SC-2 / ETL-INC-06: Failed run records `watermark IS NULL`; `_read_watermark` returns prior W0, not the failed run | VERIFIED | `test_failed_run_does_not_advance_watermark` passes; explicitly checks `frows[0]["watermark"] is None` and `_read_watermark == w0` |
| 3 | SC-3 / ETL-INC-05: Empty batch records `status='success'`, `rows_loaded=0`, `watermark IS NULL`, prior watermark preserved | VERIFIED | `test_empty_batch_preserves_watermark` passes; `_end_run` on empty-batch path (line 1239) passes no watermark kwarg — NULL by SQL design |
| 4 | SC-4 / ETL-INC-10: timestamp/int/text round-trip through JSONB with no type/tz/precision drift, zero new runtime deps | VERIFIED | `test_watermark_jsonb_roundtrip` (3 parametrize cases) passes; `pyproject.toml` unchanged, `psycopg.types.json.Jsonb` is a submodule of the already-pinned `psycopg` |
| 5 | D-04: `_read_watermark` returns `None` on first run (no qualifying success row) | VERIFIED | `test_read_watermark_none_first_run` passes; `_read_watermark` body checks `row is None or row["watermark"] is None` before decoding |
| 6 | D-06: Missing `incremental_column` in extracted batch raises `ETLError` naming the column, not a bare `KeyError` | VERIFIED | `test_incremental_column_missing_raises_etlerror` passes with `pytest.raises(ETLError, match="missing_col")`; code at etl.py:1195-1198 raises `ETLError(f"incremental_column {col!r} not found...")` before any dict access |

**Score:** 6/6 truths verified

**Test run result:** 8 passed (5 standalone + 3 parametrize), 77 deselected, 3.03s — all 6 test functions green.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/queries.py` | `ETL_GET_LAST_WATERMARK` and `ETL_UPDATE_RUN_WATERMARK` constants | VERIFIED | Both present at lines 303 and 313; correct predicates, correct parameter order, no trailing `;` |
| `pycopg/etl.py` | `_read_watermark` method, `_end_run(watermark=)` kwarg, `run()` capture block, `Jsonb` import | VERIFIED | All four elements confirmed in source; `from psycopg.types.json import Jsonb` at line 36; `_read_watermark` at line 960; `_end_run` signature extended at line 803; capture block at lines 1182-1208 |
| `tests/test_etl_accessor.py` | 6 live-DB integration tests proving SC-1..SC-4 + D-04 + D-06 | VERIFIED | All 6 test functions present (lines 1378-1611); all 8 test cases pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `etl.py run()` success path (line 1310-1311) | `_end_run(..., watermark=wm_env)` | `wm_env = _encode_watermark(raw_watermark) if raw_watermark is not None else None` | WIRED | Pattern `_end_run\(.*watermark=` confirmed at line 1311 |
| `etl.py _end_run` watermark-not-None branch (line 868-880) | `queries.ETL_UPDATE_RUN_WATERMARK` with `Jsonb(watermark)` | Dedicated success-path SQL constant; `Jsonb(` at line 878 wraps the already-encoded envelope | WIRED | `Jsonb(` confirmed; parameter list order matches SQL constant's SET clause |
| `etl.py _read_watermark` (line 994) | `queries.ETL_GET_LAST_WATERMARK` → `_decode_watermark` | Autocommit `dict_row` read; `row["watermark"]` dict passed to frozen `_decode_watermark` at line 997 | WIRED | `ETL_GET_LAST_WATERMARK` reference at line 994 confirmed; decode at line 997 confirmed |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `etl.py run()` | `raw_watermark` | `df[col].max()` from real extracted DataFrame, coerced to Python scalar | Yes — test seeds real rows, asserts `{"type": "int", "value": 5}` from DB | FLOWING |
| `etl.py _read_watermark` | return value | `ETL_GET_LAST_WATERMARK` query → `_decode_watermark(row["watermark"])` | Yes — 8 test cases confirm non-None return after successful load, None before any load | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 6 SC tests (8 cases) pass against live PostgreSQL | `uv run pytest tests/test_etl_accessor.py -k "first_run_records_watermark or failed_run_does_not_advance_watermark or empty_batch_preserves_watermark or watermark_jsonb_roundtrip or read_watermark_none_first_run or incremental_column_missing_raises_etlerror" -o addopts="" -q` | `8 passed, 77 deselected in 3.03s` | PASS |
| SQL constants have correct structure | `uv run python -c "from pycopg import queries; assert \"status = 'success'\" in queries.ETL_GET_LAST_WATERMARK and 'watermark IS NOT NULL' in queries.ETL_GET_LAST_WATERMARK and 'watermark = %s' in queries.ETL_UPDATE_RUN_WATERMARK and not queries.ETL_GET_LAST_WATERMARK.rstrip().endswith(';')..."` | `OK` | PASS |
| etl.py structural invariants | `uv run python -c "import inspect, pycopg.etl as e; assert 'from psycopg.types.json import Jsonb' in inspect.getsource(e); assert hasattr(e.ETLAccessor, '_read_watermark'); assert 'watermark' in inspect.signature(e.ETLAccessor._end_run).parameters; assert not hasattr(e.AsyncETLAccessor, '_read_watermark')..."` | `OK` | PASS |
| Ruff lint clean | `uv run ruff check pycopg/etl.py pycopg/queries.py` | `All checks passed!` | PASS |
| Black format clean | `uv run black --check pycopg/etl.py pycopg/queries.py` | `2 files would be left unchanged.` | PASS |
| Interrogate docstring gate | `uv run interrogate pycopg/etl.py` | `PASSED (minimum: 95.0%, actual: 100.0%)` | PASS |

---

### Probe Execution

Step 7c: SKIPPED — no `scripts/*/tests/probe-*.sh` discovered; phase is not a migration/tooling phase. Behavioral spot-checks above are the equivalent verification mechanism.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ETL-INC-02 | 27-01-PLAN.md | First run records `max(incremental_column)` as watermark | SATISFIED | `test_first_run_records_watermark` green; run() capture block + `_end_run(watermark=wm_env)` on success path |
| ETL-INC-05 | 27-01-PLAN.md | Empty batch preserves prior watermark (no NULL write) | SATISFIED | `test_empty_batch_preserves_watermark` green; empty-batch `_end_run` at line 1239 passes no watermark kwarg |
| ETL-INC-06 | 27-01-PLAN.md | Failed run does not advance watermark; reads prior success | SATISFIED | `test_failed_run_does_not_advance_watermark` green; failed `_end_run` at lines 1300-1307 passes no watermark kwarg; `ETL_UPDATE_RUN` (not `ETL_UPDATE_RUN_WATERMARK`) used on that path |
| ETL-INC-10 | 27-01-PLAN.md | Watermark round-trips through JSONB for timestamp/int/text, zero new deps | SATISFIED | `test_watermark_jsonb_roundtrip` (3 parametrize cases) green; `pyproject.toml` unchanged confirmed by `git diff cfe8f1e~1 HEAD -- pyproject.toml` (empty) |

---

### Frozen Symbol Integrity

| Symbol | Expected: Unchanged | Status | Evidence |
|--------|--------------------|----|---------|
| `_encode_watermark` (etl.py:581) | Body not modified | VERIFIED | `git diff cfe8f1e~1 HEAD -- pycopg/etl.py` shows no `-` lines for `_encode_watermark` body |
| `_decode_watermark` (etl.py:630) | Body not modified | VERIFIED | Same diff — no `-` lines for `_decode_watermark` body |
| `_row_to_result` (etl.py:688) | Unchanged — still drops `watermark` | VERIFIED | No `-` lines in diff touching `_row_to_result` |
| `RunResult` (etl.py:260) | Unchanged — no `watermark_used`/`watermark_recorded` fields | VERIFIED | No `-` lines in diff touching `RunResult` |
| `AsyncETLAccessor` (etl.py:1315) | Not modified — no `_read_watermark`, no incremental wiring | VERIFIED | `not hasattr(e.AsyncETLAccessor, '_read_watermark')` assertion confirmed; class start shifted from 1214→1315 due to new code inserted above |
| `ETL_UPDATE_RUN` (queries.py:270) | No `watermark` column in SET clause | VERIFIED | SET clause has 6 fields (`status, finished_at, rows_extracted, rows_loaded, error_message, error_traceback`), no `watermark = %s`; `git diff` shows only additions after `ETL_GET_RUN` |
| `ETL_GET_LAST_RUN` (queries.py:289) | Unchanged | VERIFIED | Same diff — no `-` lines for `ETL_GET_LAST_RUN` |

---

### Scope Fence Verification

The plan explicitly defers the following to Phase 28. Each was verified to be absent from this phase's changes:

| Deferred Item | Phase | Absence Confirmed |
|---------------|-------|-------------------|
| `WHERE col > last_watermark` extract filter (ETL-INC-03) | 28 | `_read_watermark` has explicit docstring note; no WHERE filter added to `run()` extract block |
| `RunResult.watermark_used` / `watermark_recorded` (ETL-INC-07) | 28 | `RunResult` dataclass unchanged; `_row_to_result` unchanged |
| `history()` / `last_run()` watermark surfacing (ETL-INC-08) | 28 | Neither method modified |
| `AsyncETLAccessor` mirror (ETL-INC-11) | 28 | `AsyncETLAccessor` untouched; no `_read_watermark` on async class |
| WR-01/WR-02 decode hardening | 28 | `_decode_watermark` frozen; deferral rationale confirmed in PLAN notes |

---

### Anti-Patterns Found

No blockers. No `TBD`, `FIXME`, or `XXX` markers in any of the three modified files. No stubs, placeholder returns, or disconnected props detected.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | — | — | — |

---

### Human Verification Required

None. All success criteria are verifiable programmatically through live-DB integration tests. No visual, UX, or external-service behavior is involved.

---

### Deferred Items

Items not yet met but explicitly addressed in later milestone phases.

| # | Item | Addressed In | Evidence |
|---|------|-------------|----------|
| 1 | `WHERE col > last_watermark` extract filter | Phase 28 | REQUIREMENTS.md ETL-INC-03: "Phase 28 | Pending" |
| 2 | `RunResult.watermark_used` / `watermark_recorded` | Phase 28 | REQUIREMENTS.md ETL-INC-07: "Phase 28 | Pending" |
| 3 | `AsyncETLAccessor` incremental mirror | Phase 28 | REQUIREMENTS.md ETL-INC-11: "Phase 28 | Pending" |
| 4 | WR-01/WR-02 `_decode_watermark` hardening | Phase 28 | PLAN notes: "every envelope Phase 27 reads back was written by its OWN strict `_encode_watermark`"; hardening deferred to Phase 28 where `history()`/`last_run()` surface arbitrary historical rows |

---

## Summary

Phase 27 achieved its goal. All six success criteria are observed in the codebase through live integration tests that pass against a real PostgreSQL database.

**Key correctness points verified beyond "file exists":**

1. The no-advance-on-failure invariant is enforced at the SQL layer, not just a runtime branch: the failed/empty `_end_run` callers structurally use `ETL_UPDATE_RUN` (which has no `watermark` column), while only the success path uses `ETL_UPDATE_RUN_WATERMARK`. A coding error that accidentally passed `watermark=x` to a failed `_end_run` would still leave the column NULL if the caller uses the wrong SQL constant — but the code is also correct at the call site (lines 1300-1307 pass no `watermark` kwarg).

2. The empty-batch path correctly exits at line 1239 with `self._end_run(run_id, "success", rows_extracted, 0)` — no watermark, leaves NULL for that run, and `ETL_GET_LAST_WATERMARK`'s `watermark IS NOT NULL` predicate means the prior success watermark is returned on the next `_read_watermark` call.

3. The JSONB round-trip test compares against the COERCED `max()` (`m.to_pydatetime()` for timestamp, not a hand literal), correctly accounting for UTC normalization pitfall documented in RESEARCH.

4. Zero new runtime dependencies: `psycopg.types.json.Jsonb` is a submodule of the already-pinned `psycopg>=3.1.0`; `pyproject.toml` was not modified.

5. All frozen symbols (`_encode_watermark`, `_decode_watermark`, `_row_to_result`, `RunResult`, `AsyncETLAccessor`, `ETL_UPDATE_RUN`, `ETL_GET_LAST_RUN`) confirmed unchanged via `git diff cfe8f1e~1 HEAD`.

---

_Verified: 2026-06-20T14:43:37Z_
_Verifier: Claude (gsd-verifier)_
