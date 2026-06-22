---
phase: 31
slug: continuous-aggregate-lifecycle
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-23
---

# Phase 31 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (+ pytest-asyncio, `asyncio_mode="auto"`) via `uv run` |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`; coverage gate ≥94% in `addopts`) |
| **Quick run command** | `uv run pytest tests/test_timescale.py -x -q -o addopts=""` |
| **Full suite command** | `uv run pytest` (enforces coverage ratchet ≥94%) |
| **Estimated runtime** | ~5 seconds (targeted) / ~60 seconds (full suite) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_timescale.py -x -q -o addopts=""`
- **After every plan wave:** Run `uv run pytest tests/test_timescale.py tests/test_parity.py -o addopts=""`
- **Before `/gsd-verify-work`:** Full suite (`uv run pytest`) must be green, coverage ≥94%
- **Max feedback latency:** ~5 seconds (targeted run)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 31-01-* | 01 | 1 | TS-ADV-01 | — | identifier validation (`validate_identifiers`) blocks SQL injection on `view_name`/`schema`; `time_bucket(` ValueError pre-DB | unit (mock-authoritative) + live-tolerant | `uv run pytest tests/test_timescale.py -k create_continuous_aggregate -o addopts=""` | ❌ W0 (extend) | ⬜ pending |
| 31-02-* | 02 | 1 | TS-ADV-02 | — | identifier validation on `view_name`/`schema`; `str`-window ValueError pre-DB; both-None=full refresh | unit (mock-authoritative) + live-tolerant | `uv run pytest tests/test_timescale.py -k refresh_continuous_aggregate -o addopts=""` | ❌ W0 | ⬜ pending |
| 31-03-* | 03 | 1 | TS-ADV-03 | — | identifier + interval validation; offset-ordering ValueError; license error propagates (no swallow) | unit (authoritative) + live-tolerant | `uv run pytest tests/test_timescale.py -k continuous_aggregate_policy -o addopts=""` | ❌ W0 | ⬜ pending |
| 31-*-async | 01/02/03 | 1 | TS-ADV-01/02/03 | — | async `await` on `has_extension` guard (no silent guard bypass) | unit (parity + async no-ext) | `uv run pytest tests/test_parity.py tests/test_timescale.py -k async -o addopts=""` | partial (parity exists) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Extend `tests/test_timescale.py` with mock SQL-shape unit classes for create / refresh / policy
      (sync + async) — covers TS-ADV-01/02/03 authoritatively (mock is the authoritative layer on the
      Apache build per CONTEXT D-09).
- [ ] Add live-tolerant integration tests (`try/except FeatureNotSupported: pass`) reusing the
      `ts_db` / `async_ts_db` skip-fixtures and the hypertable helper already present in
      `tests/test_timescale.py` (Phase-30 scaffold).
- [ ] No new fixtures, no new test file, no `conftest.py` change — Phase-30 scaffold suffices.
- [ ] No framework install needed (pytest + pytest-asyncio already configured).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real cagg materialization (view in `timescaledb_information.continuous_aggregates`; materialized rows after refresh; `jobs` row + `CALL run_job`) | TS-ADV-01/02/03 | Continuous aggregates are a Community/TSL-only feature; the local/CI build is Apache 2.28.0 → all 3 methods raise `FeatureNotSupported` (0A000). Live materialization assertions only run green on a Community-licensed TimescaleDB. | On a Community/TSL build: run the live integration tests without the `FeatureNotSupported` tolerance and confirm the info-view rows + materialized rows appear. On Apache, the live tests pass by tolerating `0A000` (the structural autocommit-isolation assertion still runs). |

*Autocommit-isolation (ROADMAP #1/#2) is proven STRUCTURALLY at the mock layer (assert `connect(autocommit=True)` seam is used, not the session path) — license-independent and automated.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 5s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
