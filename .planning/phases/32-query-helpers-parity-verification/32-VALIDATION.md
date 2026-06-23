---
phase: 32
slug: query-helpers-parity-verification
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-23
---

# Phase 32 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Reconstructed retroactively (State B) after a completed, fully-tested phase.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (`asyncio_mode = "auto"`, `pytest-cov`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_timescale.py -k "TimeBucket or time_bucket" -o addopts="" -q` |
| **Full suite command** | `uv run pytest` (enforces `--cov-fail-under=94`) |
| **Estimated runtime** | ~4s targeted · ~70s full suite |

---

## Sampling Rate

- **After every task commit:** Run the task's `<automated>` verify one-liner (import/shape/AST checks).
- **After every plan wave:** Run `uv run pytest tests/test_timescale.py tests/test_parity.py -o addopts=""` (the shared-mapper carry-forward gate).
- **Before `/gsd-verify-work`:** Full suite green at coverage ≥94%.
- **Max feedback latency:** ~70 seconds (full suite).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 32-01-01 | 01 | 1 | TS-ADV-06 / TS-ADV-07 | T-32-01 / T-32-02 | `validate_identifiers` first; values `%s`-bound only | unit (builders) | `uv run python -c "from pycopg.timescale import _build_time_bucket_sql, _build_time_bucket_gapfill_sql, ..."` (Task 1 verify) | ✅ | ✅ green |
| 32-01-02 | 01 | 1 | TS-ADV-06 / TS-ADV-07 | T-32-01 / T-32-03 | sync helpers; `into="gdf"`→ValueError before DB | unit (signature) | `inspect.signature(TimescaleAccessor.time_bucket)` (Task 2 verify) | ✅ | ✅ green |
| 32-01-03 | 01 | 1 | TS-ADV-10 | — | async parity; awaited `has_extension` guard | unit (AST + parity) | AST `await self._db.schema.has_extension` check + public-surface set-eq (Task 3 verify) | ✅ | ✅ green |
| 32-02-01 | 02 | 2 | TS-ADV-06 / TS-ADV-07 | T-32-01/02/03 | SQL shape, `bucket` alias, named-bind df routing, gapfill 5-param double-bind, `gdf`→ValueError no-DB, awaited async guard | unit (mock) | `uv run pytest tests/test_timescale.py -k "TimeBucket and Mock" -o addopts=""` (15 tests) | ✅ | ✅ green |
| 32-02-02 | 02 | 2 | TS-ADV-06 / TS-ADV-07 | T-32T-01 | REAL `time_bucket` live output; license-tolerant gapfill (`datetime` binds); `finally`-drop cleanup | integration (live DB) | `uv run pytest tests/test_timescale.py -k "(time_bucket and live) or (TimeBucket and Live)" -o addopts=""` (6 tests) | ✅ | ✅ green |
| 32-02-03 | 02 | 2 | TS-ADV-10 | — | bidirectional parity set-diff + explicit 9-name surface; coverage ratchet ≥94% | unit + suite gate | `uv run pytest tests/test_parity.py -o addopts=""` + `uv run pytest` (cov ≥94) | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Requirement → Test Coverage (Gap Analysis)

| Requirement | Behavior | Tests | Gap |
|-------------|----------|-------|-----|
| **TS-ADV-06** (`time_bucket`) | df/rows routing, `bucket` alias, `gdf`→ValueError, extension guard, async await, REAL live output | `TestTimeBucketMock` (8) + 4 live (`test_time_bucket_*_returns_*`, sync+async) | **COVERED** |
| **TS-ADV-07** (`time_bucket_gapfill`) | 5-param double-bind, df/rows, `gdf`→ValueError, extension guard, async double-bind await, license-tolerant live | `TestTimeBucketGapfillMock` (7) + 2 live (`test_time_bucket_gapfill_live` + async twin) | **COVERED** |
| **TS-ADV-10** (9-method parity) | bidirectional set-diff for the timescale pair + explicit 9-name surface assertion | `test_accessor_parity[TimescaleAccessor-AsyncTimescaleAccessor]` + `test_timescale_v080_surface` | **COVERED** |

All 22 Phase-32 tests pass (`22 passed, 110 deselected`); full suite 1288 passed at 95.11% coverage. No MISSING or PARTIAL requirements.

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.* The `tests/test_timescale.py` `ts_db`/`async_ts_db` skip-fixtures (added Phase 30) and `tests/test_parity.py` `ACCESSOR_PAIRS` registry (pre-existing) already cover every Phase-32 behavior. No framework install, no new fixtures, no stubs required.

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

The one residual non-automated nuance is benign and documented elsewhere: `time_bucket_gapfill`'s REAL gap-filled NULL-padded output cannot be asserted unconditionally on the local Apache 2.28.0 build (it raises `FeatureNotSupported` — a TSL/Community-only feature). The live test tolerates this via `try/except FeatureNotSupported`, and the mock SQL-shape test is the authoritative assertion for the gapfill query contract — so there is no manual gap, only a license-gated runtime branch that is structurally covered by the mock layer.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (none — existing infra covers all)
- [x] No watch-mode flags
- [x] Feedback latency < 70s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-23

---

## Validation Audit 2026-06-23

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
