---
phase: 49-incremental-etl-follow-ups
verified: 2026-07-03T14:35:00Z
status: passed
score: 4/4 requirements verified
overrides_applied: 0
---

# Phase 49: Incremental ETL Follow-ups Verification Report

**Phase Goal:** A user of the ETL pipeline runner can (F01) seed the first incremental run instead of full-loading, (F02) configure the incremental boundary with an inclusive `>=` and/or a lookback overlap, (F03) declare a composite multi-column watermark key, and (F04) serialize concurrent runs of the same pipeline via a PostgreSQL advisory lock — all additive under frozen SemVer 1.0, with default values byte-identical to prior behavior and full sync/async parity.

**Verified:** 2026-07-03T14:35:00Z
**Status:** passed
**Re-verification:** No — initial verification (executed inline)

## Goal Achievement

### Observable Truths (one per requirement)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| F01 | A user can set `Pipeline.initial_watermark` so the FIRST incremental run is bounded (`WHERE col > seed`), consulted only when no stored watermark exists and ignored after the first `max(col)` is recorded; sync + async | ✓ VERIFIED | Field `pycopg/etl.py:313` + `__post_init__` guard (requires `incremental_column`, scalar `{datetime,int,str}` allowlist). Seed-floor fallback wired at all 4 `run()` watermark-read sites (explicit `is None` — 0 is a valid floor). Live proof: `TestInitialWatermarkSeedFloor` (sync) + `TestAsyncInitialWatermarkSeedFloor` — seed bounds first run, ignored after recorded watermark, 0 honored, empty-batch re-seed. |
| F02 | A user can configure the boundary via `incremental_inclusive` (`>=`) and/or `incremental_lookback` (read-window overlap); the recorded watermark stays the true `max(col)`; sync + async | ✓ VERIFIED | Fields `pycopg/etl.py:314-315`; builder gains kw-only `inclusive` (`op = ">=" if inclusive else ">"`); `_apply_lookback` (`:845`, isinstance dispatch, str/mismatch → `ETLError`) applied at all 4 forks BEFORE `_do_extract`; recorded-watermark capture untouched (D-07). Live: `TestIncrementalBoundaryLive` — read `col > 90` while recorded == true max 137, `lookback=None` baseline, inclusive re-includes boundary row, str+lookback `ETLError`; async mirror. |
| F03 | A user can declare a composite (multi-column) `incremental_column`; the extract filters on the native row-value compare and the recorded watermark is the true greatest ROW; single-column byte-identical; sync + async | ✓ VERIFIED | Field widened `:312`; `_build_incremental_extract_sql` composite branch `WHERE {lhs} {op} {placeholders}` (`:836/:840`) with one bound `%s` per element; `_encode_composite_watermark` (`:952`) + `"composite"` decode tag; `_capture_watermark` (`:1084`) greatest-ROW via `sort_values` reading each element from its own sorted column (per-element NaN void); `_reconcile_watermark_binds` (`:1133`) → `:wm{i}`. Live: `TestCompositeWatermarkLive` — recorded `(2,1)` NOT `(2,99)`, second-run `(day,seq) > recorded` filter, composite seed floor; `TestAsyncCompositeWatermarkLive` mirror. |
| F04 | A user can serialize concurrent runs via `Pipeline.concurrency="wait"|"skip"` — a session-scoped advisory lock keyed server-side on the bound pipeline name; `"skip"`-when-held returns a transient `'skipped'` RunResult writing no row; sync + async | ✓ VERIFIED | `queries.ETL_ADVISORY_LOCK/TRY_LOCK/UNLOCK` (`:410-412`, `hashtextextended(%s, 0)`, name bound, key server-side). Field `pycopg/etl.py:316` + guard. `run()` (`:1593`/`:2372`) = thin lock wrapper over `_run_impl` (`:1662`/async): dedicated autocommit connection, session-scoped, finally-release + close auto-release. Live: `TestAdvisoryLockLive` — held-lock skip → `'skipped'` + no row + runs after release, crash releases lock, `"wait"` blocks until peer releases; `TestAsyncAdvisoryLockLive` mirror. |

**Score:** 4/4 requirements verified

### Required Artifacts

| Artifact | Expected | Status |
|----------|----------|--------|
| `pycopg/etl.py` | `Pipeline` fields: `initial_watermark`, `incremental_inclusive`, `incremental_lookback`, widened `incremental_column`, `concurrency` | ✓ VERIFIED (`:312-316`) |
| `pycopg/etl.py` | pure helpers `_apply_lookback`, `_encode_composite_watermark`, `_capture_watermark`, `_reconcile_watermark_binds`, `_encode_watermark_value`, `_coerce_watermark_scalar` | ✓ VERIFIED |
| `pycopg/etl.py` | `run()`/`_run_impl` split with advisory-lock wrap on both accessors | ✓ VERIFIED (`grep -c "def run("` == 2; 2× `_run_impl`) |
| `pycopg/queries.py` | 3 `ETL_ADVISORY_*` constants; status CHECK unchanged | ✓ VERIFIED (`:410-412`; CHECK still `('running','success','failed')`) |
| `tests/test_etl.py` | DB-free construction/builder/codec/constant tests | ✓ VERIFIED (`TestInitialWatermark`, `TestIncrementalBoundaryConstruction`, `TestCompositeWatermark`, `TestEncodeDecodeWatermark` composite, `TestAdvisoryLock`) |
| `tests/test_etl_accessor.py` | live-DB sequence tests (sync+async) for all 4 features | ✓ VERIFIED (SeedFloor, BoundaryLive, CompositeWatermarkLive, AdvisoryLockLive + async mirrors) |
| `docs/etl.md` | boundary-config + composite-key + concurrency documentation | ✓ VERIFIED (v1.1.0 subsections; stale "composite not supported"/"exclusive boundary" corrected) |

### Key Link Verification

| From | To | Via | Status |
|------|-----|-----|--------|
| `run()` seed/read floor | `_do_extract` → `_build_incremental_extract_sql` | `wm is None → initial_watermark`; lookback `read_floor = wm - lookback` | ✓ WIRED |
| composite `incremental_column` | `WHERE (c1,c2) > (%s,%s)` | builder row-value branch + `_reconcile_watermark_binds` → `:wm{i}` | ✓ WIRED |
| composite max ROW | recorded envelope | `_capture_watermark` (sorted last row) → `_encode_watermark_value` → `_end_run` | ✓ WIRED |
| `run()` lock wrap | `queries.ETL_ADVISORY_*` | dedicated `connect(autocommit=True)`, name bound `%s`, finally-release | ✓ WIRED |
| `concurrency="skip"` held | `RunResult(status="skipped", run_id=None)` | `pg_try_advisory_lock` false → early return, no `pipeline_runs` row | ✓ WIRED |

## Standing-bar gates

| Gate | Result |
|------|--------|
| Full suite (`PGDATABASE=pycopg_test3 uv run pytest`) | **1844 passed, 2 skipped** |
| Coverage ratchet ≥95% | **96.29%** (etl.py 97%) |
| `uv run mypy pycopg` (strict) | **0 errors / 18 files** |
| `uv run ruff check` | clean |
| Sphinx `-W` | clean |
| `interrogate` ≥95% | **100%** |
| sync/async parity (`test_parity.py -k etl`) | green |
| zero new runtime/dev dependencies | confirmed (advisory-lock uses `pg_catalog` built-ins) |

## Deviations carried (documented in plan SUMMARYs)

1. Live-DB feature tests live in `tests/test_etl_accessor.py` (where the DB fixtures are), not `tests/test_etl.py` which is deliberately DB-free — the plans named `test_etl.py`; construction/builder/codec/constant tests DO live there as specified.
2. 49-03 builder composite branch was folded into the Task-1 commit (mypy-green required the field and its builder consumer together); 49-03 added fail-loud composite-`run()` seams that 49-04 replaced.
3. `_apply_lookback` also rejects datetime↔int type mismatches (not just the str case named), a cleaner runtime contract.

## Verdict

**PASSED — 4/4 requirements (ETL-INC-F01..F04) delivered and verified end-to-end.** Phase 49 goal fully achieved: additive incremental-ETL follow-ups shipped under frozen SemVer 1.0 with default byte-identical behavior and full sync/async parity.

## Non-blocking follow-ups (for milestone close / P51)

- `"wait"` cross-process serialization is proven via an in-process threaded holder; a true two-process manual verification remains an optional belt-and-suspenders check (noted in 49-VALIDATION.md's manual-only section).
- Carry-forward from P48 (WR-01 `time_bucket` origin/offset guard-hoist) still open for P51.
