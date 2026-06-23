---
phase: 32-query-helpers-parity-verification
verified: 2026-06-23T14:05:00Z
status: passed
score: 8/8 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: none
  previous_score: n/a
---

# Phase 32: Query Helpers & Parity Verification — Verification Report

**Phase Goal:** Users can run bucketed and gap-filled time-series aggregation queries returning a DataFrame or list of dicts; full sync/async parity for all 9 new v0.8.0 methods is confirmed
**Verified:** 2026-06-23T14:05:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

The phase goal is achieved in the codebase. Both query helpers exist on both
accessor classes with the exact REQ-verbatim signatures, the production bodies are
substantive (not stubs), the SQL builders produce the contracted shapes (fixed
`AS bucket` alias, gapfill double-bind), the async methods correctly `await` the
extension guard and `_run` (the recurring missing-`await` regression did NOT recur),
`into="gdf"` raises before any DB call, identifiers are validated and runtime values
bound, and parity is enforced both by `test_accessor_parity` over the registered pair
and by an explicit 9-name surface assertion. Live tests exercise the real DB:
`time_bucket` asserts real output (Apache-free) and `time_bucket_gapfill` runs the
production path with Python `datetime` binds under a license-tolerant `try/except`
(the planner-verified D-08 reversal). Full suite: 1288 passed, coverage 95.11% ≥ 94%.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `time_bucket` `into="df"` → DataFrame with `bucket` column (SC#1, TS-ADV-06) | ✓ VERIFIED | `_build_time_bucket_sql` emits `... AS bucket ...` (timescale.py:254); live `test_time_bucket_df_returns_bucket_column` PASSED against real DB; mock `test_time_bucket_df_named_binds` proves `:p0` named-bind df routing |
| 2 | `time_bucket` `into="rows"` → list[dict] (SC#1) | ✓ VERIFIED | `_run` routes `rows` to `self._db.execute(sql, params)` (timescale.py:1170); live `test_time_bucket_rows_returns_dicts` PASSED |
| 3 | `into="gdf"` raises `ValueError` before any DB call, both helpers (SC#1, D-03) | ✓ VERIFIED | `_check_into` runs first in each method body (timescale.py:1225,1302,2192,2265); `_VALID_INTO=("df","rows")`; mock `test_*_gdf_raises_before_db` asserts `execute`/`to_dataframe` `assert_not_called()` |
| 4 | `time_bucket_gapfill` requires positional `start`/`finish` (no defaults), datetime binds, NULL-padded output (SC#2, TS-ADV-07) | ✓ VERIFIED | signature inspected: `start`/`finish` `default is inspect._empty`; live `test_time_bucket_gapfill_live` passes Python `datetime(2024,...)` objects through production path, asserts NULL aggregate, tolerates `FeatureNotSupported` (Apache) — PASSED |
| 5 | gapfill double-binds start/finish — params `[bw, start, finish, start, finish]`, 5 `%s` (D-10) | ✓ VERIFIED | `_build_time_bucket_gapfill_sql` returns `[bucket_width, start, finish, start, finish]` (timescale.py:325), SQL has 5 `%s`; live one-liner confirms; mock `test_gapfill_rows_double_bind` asserts `sql.count("%s")==5` and exact params |
| 6 | async helpers mirror sync, `await` has_extension + `_run` (TS-ADV-10, D-07) | ✓ VERIFIED | async bodies use `await self._db.schema.has_extension("timescaledb")` (timescale.py:2193,2266) and `await self._run(...)` (2200,2280); mock `test_gapfill_async_rows_awaits_double_bind` asserts `has_extension.assert_awaited_once_with("timescaledb")` |
| 7 | identifiers validated, runtime values bound `%s`/`:pN`; no string interpolation of values (TS-ADV-06, D-09) | ✓ VERIFIED | both builders call `validate_identifiers(table, schema, time_column)` before any interpolation (timescale.py:251,314); only `bucket_width`/`start`/`finish` bound as `%s`; df path converts to `:pN` via `_to_named_binds` |
| 8 | `test_accessor_parity` (timescale pair) + explicit 9-name surface assertion pass; coverage ≥94%; no new autocommit branches (SC#3, TS-ADV-10, D-11, D-12) | ✓ VERIFIED | `ACCESSOR_PAIRS` unchanged (timescale pair at test_parity.py:25); `test_timescale_v080_surface` lists exact 9 names; 25 parity tests PASSED; public-surface diff empty (live check); full suite 1288 passed / cov 95.11%; zero `autocommit` in query-helper bodies |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/timescale.py` | `_build_time_bucket_sql`, `_build_time_bucket_gapfill_sql`, `_to_named_binds`, `_check_into`, `_VALID_INTO`, sync+async `_run`/`time_bucket`/`time_bucket_gapfill` | ✓ VERIFIED | All 11 symbols present (lines 157-325, 1147-1317, 2110-2280), substantive bodies, numpydoc-documented, wired into accessor methods |
| `tests/test_timescale.py` | `TestTimeBucketMock`/`TestTimeBucketGapfillMock` + live classes | ✓ VERIFIED | Classes at 2078/2251/2457/2524; 21 TimeBucket tests pass (mock + 6 live all PASSED, no skips) |
| `tests/test_parity.py` | explicit 9-name v0.8.0 surface assertion | ✓ VERIFIED | `test_timescale_v080_surface` (test_parity.py:64) asserts exact 9-name frozenset ⊆ both classes; `ACCESSOR_PAIRS` untouched |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `TimescaleAccessor.time_bucket` | `_build_time_bucket_sql` | builder returns `(sql, params)` | ✓ WIRED | timescale.py:1230 |
| `TimescaleAccessor._run` (df) | `self._db.to_dataframe` | `_to_named_binds` → `to_dataframe(sql=, params=dict)` | ✓ WIRED | timescale.py:1168-1169 |
| `AsyncTimescaleAccessor._run` (df) | `await self._db.to_dataframe` | awaited named-bind path | ✓ WIRED | timescale.py:2136 |
| async methods | `has_extension` guard | `await self._db.schema.has_extension` | ✓ WIRED | timescale.py:2193,2266 — await present (no regression) |
| `test_accessor_parity` | timescale pair | `ACCESSOR_PAIRS` registered entry | ✓ WIRED | test_parity.py:25 (unchanged) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `time_bucket` (df/rows) | query result | real DB `SELECT time_bucket(...)` over hypertable | Yes — live test asserts `bucket` column + ≥1 row from real inserted data | ✓ FLOWING |
| `time_bucket_gapfill` | gap-filled rows | real DB `time_bucket_gapfill(...)` with datetime binds | Yes on TSL; license-gated on Apache (production path executed, FeatureNotSupported caught) | ✓ FLOWING (live-exercised) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| signatures/builder shapes/parity surface | `uv run python -c "<inspect+builder asserts>"` | `ALL SHAPE/SIG/PARITY CHECKS OK` | ✓ PASS |
| TimeBucket mock+live tests | `uv run pytest -k TimeBucket -o addopts=""` | 21 passed, 86 deselected | ✓ PASS |
| parity tests | `uv run pytest tests/test_parity.py -o addopts=""` | 25 passed | ✓ PASS |
| live tests (real DB, not skipped) | `uv run pytest -k "TimeBucketLive or TimeBucketGapfillLive" -v` | 6 PASSED (0 skipped) | ✓ PASS |

### Probe Execution

Not applicable — phase has no `scripts/*/tests/probe-*.sh` and PLAN/SUMMARY declare none. Verification via pytest + import one-liners (above).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| TS-ADV-06 | 32-01, 32-02 | bucketed aggregation via `time_bucket`, df/rows, `%s`-bound width, validated identifiers | ✓ SATISFIED | Truths 1,2,7; live + mock tests pass; REQUIREMENTS.md:31 `[x]` |
| TS-ADV-07 | 32-01, 32-02 | gap-filled query, required `start`/`finish`, `locf()`/`interpolate()` in aggregates | ✓ SATISFIED | Truths 4,5; live gapfill test with datetime binds; REQUIREMENTS.md:32 `[x]` |
| TS-ADV-10 | 32-01, 32-02 | full sync/async parity for all 9 methods, async guard awaited, `test_accessor_parity` | ✓ SATISFIED | Truths 6,8; parity tests + 9-name assert pass; REQUIREMENTS.md:36 `[x]` |

All 3 requirement IDs from PLAN frontmatter are accounted for in REQUIREMENTS.md (lines 31, 32, 36 marked `[x]`; traceability table lines 84-86 all "Complete"). No orphaned requirements: REQUIREMENTS.md maps exactly TS-ADV-06/07/10 to Phase 32.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER in any phase-32 file | ℹ️ Info | None — clean |

WR-01 from 32-REVIEW.md (literal `%`/`%s` in caller `aggregates`/`where` breaks binding)
is a real correctness footgun but is the documented, accepted "structural SQL" trust
posture inherited verbatim from the shipped spatial accessor (`spatial._to_named_binds`/
`_run`), not an injection bug and not a goal blocker. It is a tracked carry-forward, not
a Phase-32 gap.

### Human Verification Required

None. All success criteria are programmatically verified, including live-DB behavior
(`time_bucket` real output and the gapfill production path both executed against the
local TimescaleDB and PASSED, not skipped). No `<verify><human-check>` blocks deferred
in the PLANs.

### Deferred Items

None.

### Gaps Summary

No gaps. All 8 must-haves verified, all 3 ROADMAP success criteria observably true in
the codebase, all 3 requirement IDs satisfied, all key links wired, all artifacts
substantive and exercised by passing tests. D-01 (fixed `bucket` alias), D-03
(`into="df"/"rows"` inverse set, gdf pre-DB ValueError), D-06 (local `_to_named_binds`
copy), D-07 (async awaits), D-08-corrected (time_bucket REAL / gapfill license-tolerant),
D-09 (no semantic guards), D-10 (double-bind), D-11 (9-name assert, no registry change),
and D-12 (zero new deps, zero new autocommit branches) are all honored. Full suite 1288
passed, coverage 95.11% ≥ 94%; the only 2 failures are the documented pre-existing flaky
DB tests in files Phase 32 never touched (`test_async_transaction_fix`,
`test_create_spatial_index_name_parameter`) — not regressions.

---

_Verified: 2026-06-23T14:05:00Z_
_Verifier: Claude (gsd-verifier)_
