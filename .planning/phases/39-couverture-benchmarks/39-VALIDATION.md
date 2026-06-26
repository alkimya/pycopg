---
phase: 39
slug: couverture-benchmarks
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-26
---

# Phase 39 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (real-DB integration tests against live Postgres/PostGIS/TimescaleDB) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (`addopts` carries `--cov-fail-under`) |
| **Quick run command** | `PGDATABASE=pycopg_test2 uv run pytest tests/test_async_database.py -x -q -o addopts=""` |
| **Full suite command** | `PGDATABASE=pycopg_test2 uv run pytest` (local) · `uv run pytest` (CI, `pycopg_test`) |
| **Estimated runtime** | ~60–120 seconds (full suite, real DB) |

> **Local-env note:** default `pycopg_test` DB is broken since 2026-06-24 — run all measurements with `PGDATABASE=pycopg_test2`. Use `-o addopts=""` for targeted runs to bypass the `--cov-fail-under` gate while iterating. `pytest-randomly` is active: every new test must be order-independent. `benchmarks/` is OUTSIDE `testpaths` — it is never run by `uv run pytest` and never enters the coverage gate.

---

## Sampling Rate

- **After every task commit:** Run the quick run command (targeted test module).
- **After every plan wave:** Run the full suite command.
- **Before `/gsd-verify-work`:** Full suite green AND `--cov-fail-under=95` passes under `PGDATABASE=pycopg_test2`.
- **Max feedback latency:** ~120 seconds.

---

## Per-Task Verification Map

> Filled per-plan during planning/Nyquist. COV-01 tasks verify via coverage delta; PERF-04 tasks verify via benchmark execution + readable table output (NO timing assertion in the test gate — D-03).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 39-01-01 | 01 | 1 | COV-01 | — | N/A | integration (real DB) | `PGDATABASE=pycopg_test2 uv run pytest tests/test_async_database.py -q -o addopts=""` | ❌ W0 | ⬜ pending |
| 39-02-01 | 02 | 1 | PERF-04 | — | N/A | manual run (out of gate) | `python -m benchmarks --rows 1000` (smoke) | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] New behavioral tests in `tests/` targeting the precise uncovered lines (researcher pinned `async_database.py` `insert_batch` L685–718 as the highest-value pool) — REQ COV-01
- [ ] `benchmarks/` top-level package (`__main__.py`, `__init__.py`, `README.md`) — REQ PERF-04
- [ ] No new framework install — existing pytest infra + stdlib (`time`, `statistics`) cover all phase requirements.

*Existing infrastructure (real-DB fixtures in `tests/conftest.py`, `tests/setup_test_db.py`) covers all COV-01 requirements.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Benchmark comparative table (rows/s, speedup vs `insert_batch`) | PERF-04 | D-03: no automated timing assertion (would re-introduce Phase-37-eliminated flakiness); regression is a human reading | `make bench` (or `python -m benchmarks`), read the table, confirm COPY paths stay a multiple faster than `insert_batch` per `benchmarks/README.md` protocol |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
