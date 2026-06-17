---
phase: 19
slug: sync-runner-query-surface
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-15
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (configured in `pyproject.toml` `[tool.pytest.ini_options]`) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/test_etl_accessor.py tests/test_etl.py -x -q -o addopts=""` |
| **Full suite command** | `uv run pytest` (coverage gate: `--cov-fail-under=94`) |
| **Estimated runtime** | ~30–60 seconds (targeted ETL); full suite longer w/ coverage |

**Known caveat:** Three pre-existing full-suite DB tests are flaky in the local env (memory `pycopg-flaky-db-tests`). For targeted ETL runs always pass `-o addopts=""` to strip the coverage/HTML flags. Coverage gate stays **94** this phase — measure before any ratchet.

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_etl_accessor.py tests/test_etl.py -x -q -o addopts=""`
- **After every plan wave:** Run `uv run pytest tests/test_etl_accessor.py tests/test_etl.py -o addopts=""`
- **Before `/gsd-verify-work`:** Full suite `uv run pytest` must be green (coverage ≥ 94)
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (planner assigns) | — | 0 | D-10 | — | N/A | unit | `uv run pytest tests/test_etl.py -k test_row_to_result -x -o addopts=""` | ❌ W0 | ⬜ pending |
| (planner assigns) | — | — | ETL-10 (SC-1) | — | N/A | integration | `uv run pytest tests/test_etl_accessor.py -k test_run_returns_run_result -x -o addopts=""` | ❌ W0 | ⬜ pending |
| (planner assigns) | — | — | ETL-11 (SC-2) | — | N/A | integration | `uv run pytest tests/test_etl_accessor.py -k test_history -x -o addopts=""` | ❌ W0 | ⬜ pending |
| (planner assigns) | — | — | ETL-17 (SC-3) | — | N/A | integration | `uv run pytest tests/test_etl_accessor.py -k test_last_run -x -o addopts=""` | ❌ W0 | ⬜ pending |
| (planner assigns) | — | — | ETL-15 (SC-4) | — | N/A | integration | `uv run pytest tests/test_etl_accessor.py -k test_dry_run -x -o addopts=""` | ❌ W0 | ⬜ pending |
| (planner assigns) | — | — | Phase 17 non-regression | — | run-log isolation intact | integration | `uv run pytest tests/test_etl_accessor.py::TestETLAccessorIntegration -x -o addopts=""` | ✅ exists | ⬜ pending |
| (planner assigns) | — | — | Phase 18 non-regression | — | load paths untouched | integration | `uv run pytest tests/test_etl_accessor.py::TestRunPipelineIntegration -x -o addopts=""` | ✅ exists (needs edit) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_etl.py` — `TestRowToResult` unit class for `_row_to_result` (pure, DB-free): all-8-fields, `error_message → error`, `error_traceback`/`watermark` dropped, frozen.
- [ ] `tests/test_etl_accessor.py` — `TestRunResultSurface` integration class: SC-1 (run → RunResult), SC-2 (history newest-first / two-entries), SC-3 (last_run most-recent / None), SC-4 (dry_run skips load, writes no row, `status='dry_run'`, `rows_loaded=0`, `run_id=None`).
- [ ] Audit + fix existing assertions: `test_run_accepts_pipeline_object` (`isinstance(run_id, int)` → `isinstance(result, RunResult)`) and the ≥5 `run_id = db.etl.run(p)` sites in `TestRunPipelineIntegration` (→ `result = db.etl.run(p); run_id = result.run_id`).

*Existing infrastructure (real `pycopg_test` PG fixtures, conftest) covers the DB harness — only the new test bodies and assertion fixes are Wave 0.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | — |

*All phase behaviors have automated verification (SC-1..SC-4 are integration-testable against `pycopg_test`; D-10 is a pure unit test).*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (new test classes + assertion fixes)
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
