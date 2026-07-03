---
phase: 48-timescaledb-follow-ups
verified: 2026-07-03T13:10:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
---

# Phase 48: TimescaleDB Follow-ups Verification Report

**Phase Goal:** Users can fully manage a continuous aggregate's lifecycle, align time buckets to a custom origin, control compression at the individual-chunk level, and filter `show_chunks` by physical time — completing the `db.timescale.*` surface opened in v0.8.0.

**Verified:** 2026-07-03T13:10:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can drop a continuous aggregate and separately remove its refresh policy via `db.timescale.drop_continuous_aggregate(name)` / `remove_continuous_aggregate_policy(name)`, sync and async | ✓ VERIFIED | `pycopg/timescale.py:1293` (sync `drop_continuous_aggregate`), `:1350` (sync `remove_continuous_aggregate_policy`), `:2619` (async twin), `:2677` (async twin). Both `validate_identifiers(view_name, schema)` as line 1, plain `self._db.execute`/`await self._db.execute` (not autocommit seam), `DROP MATERIALIZED VIEW [IF EXISTS ]{schema}.{view}[CASCADE]` and `SELECT remove_continuous_aggregate_policy('{schema}.{view}', if_exists => true/false)` confirmed byte-for-byte via `Read` + passing `TestDropContinuousAggregateMock`/`TestRemoveContinuousAggregatePolicyMock` (10 tests, sync+async+guard+injection). |
| 2 | User can align `time_bucket` output to a custom origin/offset via keyword-only `origin=`/`offset=` params, sync and async | ✓ VERIFIED | `_build_time_bucket_sql` (`:214`) gains `origin: datetime \| None`, `offset: str \| None`, dispatches `, origin => %s` (bare bind) or `, "offset" => %s::interval`; mutual-exclusion `ValueError` before SQL build. All 8 `time_bucket` signatures (3 `@overload` + impl × sync/async at `:1425-1566`/`:2755-2896`) carry `origin=`/`offset=` in identical position (KIND-parity, `grep -c` = 9). Call-sites forward both kwargs to the builder. `TestTimeBucketOriginOffsetMock` (5 tests) green. Non-blocking advisory (WR-01, already flagged in 48-REVIEW.md and pre-accepted per task instructions): the mutual-exclusion guard fires after the `has_extension` DB round-trip, contradicting the docstring's "before any DB round-trip" claim — does not block the goal (guard still fires before any SQL is built/executed). |
| 3 | User can compress or decompress a single named chunk via `db.timescale.compress_chunk(chunk)` / `decompress_chunk(chunk)`, sync and async | ✓ VERIFIED | `pycopg/timescale.py:524` (sync `compress_chunk`), `:565` (sync `decompress_chunk`), `:1880` (async), `:1923` (async). Exact SQL `SELECT compress_chunk(%s::regclass, if_not_compressed => %s)` / decompress mirror, `chunk` bound as `%s::regclass` (never interpolated), `has_extension` guard first, return `None`. `TestCompressChunkMock`/`TestDecompressChunkMock` (10 tests) including `test_*_binds_not_interpolates` proving the malicious string lands only in `params[0]`. |
| 4 | User can filter `show_chunks` by physical time via keyword-only `newer_than=`/`older_than=` bounds, sync and async | ✓ VERIFIED | `show_chunks` (`:699` sync, `:2059` async) already carries `older_than: str \| datetime \| None`, `newer_than: str \| datetime \| None` keyword-only params, dispatched through `_build_chunk_bound_fragments` (`:33`) which type-dispatches `datetime` → bare `%s` (physical time) vs `str` → `%s::interval`. Pre-existing from v0.8.0; Phase 48 added `test_show_chunks_sql_shape_datetime_newer_than` symmetry test + `docs/timescaledb.md` datetime examples for both bounds (lines 364-372). |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/timescale.py` | `drop_continuous_aggregate`/`remove_continuous_aggregate_policy` on both accessors | ✓ VERIFIED | Defined sync (:1293, :1350) + async (:2619, :2677) |
| `pycopg/timescale.py` | `compress_chunk`/`decompress_chunk` on both accessors | ✓ VERIFIED | Defined sync (:524, :565) + async (:1880, :1923) |
| `pycopg/timescale.py` | `time_bucket` origin/offset on both accessors (8 signatures) | ✓ VERIFIED | 9 occurrences of `origin: datetime \| None = None` (1 builder + 8 signatures) |
| `pycopg/timescale.py` | `show_chunks` newer_than/older_than physical-time | ✓ VERIFIED | Pre-existing, confirmed unchanged and correctly dispatching datetime |
| `tests/test_timescale.py` | Mock SQL-shape/guard/injection test classes for all new methods | ✓ VERIFIED | `TestDropContinuousAggregateMock` (:2125), `TestRemoveContinuousAggregatePolicyMock` (:2220), `TestTimeBucketOriginOffsetMock` (:2490), `TestCompressChunkMock` (:2603), `TestDecompressChunkMock` (:2699) — all present, all pass |
| `tests/test_parity.py` | `test_timescale_v110_surface` frozenset with 4 method names | ✓ VERIFIED | `:101-121`, asserts `drop_continuous_aggregate`, `remove_continuous_aggregate_policy`, `compress_chunk`, `decompress_chunk` on both `TimescaleAccessor` and `AsyncTimescaleAccessor` |
| `docs/timescaledb.md` | Per-chunk compression + cagg teardown + newer_than doc examples | ✓ VERIFIED | `compress_chunk`/`decompress_chunk` (:132-149), teardown (:321-344), `newer_than` datetime (:364-372) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `drop_continuous_aggregate` | `self._db.execute` | plain transaction-safe execute | ✓ WIRED | No `connect(autocommit=True)` anywhere in these methods |
| `remove_continuous_aggregate_policy` | SQL `if_exists =>` | current param name | ✓ WIRED | `grep "if_exists =>"` present; `if_not_exists` absent from that method |
| `time_bucket` impl | `_build_time_bucket_sql(..., origin=origin, offset=offset)` | call-site forwarding | ✓ WIRED | Both sync/async impls forward both kwargs |
| `_build_time_bucket_sql` | `ValueError` on mutual exclusion | client-side guard | ✓ WIRED | Fires before any SQL string is built (though after `has_extension` at the accessor level — WR-01, non-blocking) |
| `compress_chunk`/`decompress_chunk` | `%s::regclass` bind | parameter binding, no interpolation | ✓ WIRED | Confirmed via `test_*_binds_not_interpolates` |
| `test_timescale_v110_surface` | `TimescaleAccessor`/`AsyncTimescaleAccessor` | frozenset subset assertion | ✓ WIRED | Passing test, 4/4 names present on both classes |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| TSDB-F01 | 48-01 | Drop cagg + remove refresh policy | ✓ SATISFIED | Truth #1 above |
| TSDB-F02 | 48-02 | `time_bucket` origin/offset alignment | ✓ SATISFIED | Truth #2 above |
| TSDB-F03 | 48-03 | Per-chunk compress/decompress | ✓ SATISFIED | Truth #3 above |
| TSDB-F04 | 48-03 | `show_chunks` physical-time filter | ✓ SATISFIED | Truth #4 above (verify+doc only per CONTEXT D-01/D-02, correctly scoped) |

All 4 requirement IDs declared in PLAN frontmatter (48-01: TSDB-F01; 48-02: TSDB-F02; 48-03: TSDB-F03, TSDB-F04) match REQUIREMENTS.md exactly. No orphaned requirements for Phase 48 — REQUIREMENTS.md traceability table lists exactly these 4 IDs mapped to Phase 48, all marked "Complete", consistent with codebase evidence.

### Anti-Patterns Found

None. Scanned `pycopg/timescale.py`, `tests/test_timescale.py`, `tests/test_parity.py`, `docs/timescaledb.md` for `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` — zero matches. No empty implementations, no hardcoded stub returns on the new methods (all execute real bound SQL against `self._db.execute`).

### Behavioral Spot-Checks / Automated Verification

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| mypy --strict on timescale.py | `uv run mypy pycopg/timescale.py` | "Success: no issues found in 1 source file" | ✓ PASS |
| mypy --strict whole package | `uv run mypy pycopg/` | "Success: no issues found in 18 source files" | ✓ PASS |
| Targeted test suite | `PGDATABASE=pycopg_test3 uv run pytest tests/test_timescale.py tests/test_parity.py -o addopts="" -q` | 171 passed | ✓ PASS |
| Full test suite (phase gate) | `PGDATABASE=pycopg_test3 uv run pytest -q` | 1763 passed, 2 skipped, coverage 96.37% (gate ≥95%) | ✓ PASS |
| interrogate docstring coverage | `uv run interrogate pycopg` | 100% (gate ≥95%) | ✓ PASS |
| Sphinx docs build | `cd docs && uv run sphinx-build -W -b html . _build/html -q` | exit 0, no warnings | ✓ PASS |

### Probe Execution

Not applicable — this is a library-code phase (no `scripts/*/tests/probe-*.sh` conventions apply; no probes declared in PLAN/SUMMARY).

### Human Verification Required

None. All 4 success criteria are verifiable via static code inspection + automated test execution (mock SQL-shape assertions), consistent with the library's established test conventions (live TSL/Community-license compression behavior on Apache is out of scope per the task's explicit note — mocked SQL-shape assertions are the correct and sufficient verification method here).

### Gaps Summary

No gaps. All 4 phase success criteria are observably true in the codebase:
1. Cagg teardown pair exists on both accessors, plain-execute, validated identifiers, tested.
2. `time_bucket` origin/offset threaded through all 8 signatures with KIND-parity, mutual-exclusion guard, tested.
3. Per-chunk compress/decompress exist on both accessors, bound `%s::regclass`, tested including injection-by-binding.
4. `show_chunks` physical-time filter (pre-existing from v0.8.0) confirmed correct, symmetry-tested, now documented.

One non-blocking advisory carried forward from code review (48-REVIEW.md WR-01): the `time_bucket` origin/offset mutual-exclusion `ValueError` fires after the `has_extension()` round-trip rather than strictly before it, contradicting the docstring's literal wording. This was explicitly flagged in the verification task instructions as a known, accepted, non-goal-blocking nuance — noted here for traceability, not treated as a gap.

---

_Verified: 2026-07-03T13:10:00Z_
_Verifier: Claude (gsd-verifier)_
