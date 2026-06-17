---
phase: 21
slug: infrastructure-timescale-accessor
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-17
---

# Phase 21 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (`asyncio_mode = "auto"`, `--cov-fail-under=94`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_timescale_aliases.py tests/test_parity.py -x -q -o addopts=""` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~60 seconds (full suite); ~5 seconds (quick) |

---

## Sampling Rate

- **After every task commit:** Run the quick command above.
- **After every plan wave:** Run the full suite command.
- **Before `/gsd-verify-work`:** Full suite must be green AND `uv run pytest -W error::DeprecationWarning -o addopts=""` passes (no DeprecationWarning noise — REORG-04 gate).
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

> Planner fills one row per task during planning (anchored to the requirement map below).

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 21-01-01 | 01 | 1 | REORG-01 | T-21-01 / — | decorator warns + delegates; no eval/exec on the target-path string | unit | `uv run pytest tests/test_timescale_aliases.py -x -q -o addopts=""` | ❌ W0 | ⬜ pending |

### Requirement → Test Map (from RESEARCH.md, verified)

| Req ID | Behavior | Test Type | File | Automated Command |
|--------|----------|-----------|------|-------------------|
| REORG-01 | decorator emits `DeprecationWarning`, correct `stacklevel` (points at caller) | unit | `tests/test_timescale_aliases.py` (new) | `uv run pytest tests/test_timescale_aliases.py -x -q -o addopts=""` |
| REORG-02 | flat alias still delegates correctly (same result as accessor call) | unit | `tests/test_timescale_aliases.py` (new) | same |
| REORG-03 | sync/async parity for `(TimescaleAccessor, AsyncTimescaleAccessor)` via registry | unit | `tests/test_parity.py` | `uv run pytest tests/test_parity.py -x -q -o addopts=""` |
| REORG-04 | no `DeprecationWarning` noise in main suite under `-W error` | integration | all migrated tests | `uv run pytest -W error::DeprecationWarning -x -q -o addopts=""` |
| TS-01 | the 6 accessor methods return identical results to the old flat methods | integration | `tests/test_database_integration.py` + `tests/test_async_database.py` (migrated) | `uv run pytest tests/test_database_integration.py tests/test_async_database.py -x -q -o addopts=""` |

---

## Wave 0 Requirements

- [ ] `pycopg/aliases.py` — new module (the `@deprecated_alias` decorator) — does not exist yet
- [ ] `pycopg/timescale.py` — new module (`TimescaleAccessor` / `AsyncTimescaleAccessor`) — does not exist yet
- [ ] `tests/test_timescale_aliases.py` — new test file (D-09: per-alias warn + delegate)
- [ ] `tests/test_parity.py` — data-driven `ACCESSOR_PAIRS` registry (D-10) extended, not just appended-to

*Existing pytest infrastructure (config, fixtures, coverage gate) covers everything else.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Sphinx autodoc builds clean under `-W` with the new accessor + deprecated stubs | REORG-04 (docs hygiene) | Sphinx `-W` build is run in CI/Phase 24, not in the unit suite | `uv run sphinx-build -W -b html docs docs/_build` (if a docs build is wired) — otherwise deferred to Phase 24 export hardening |

*All test-asserted behaviors (warn, delegate, parity, coverage, no-noise) have automated verification. The Sphinx `-W` cleanliness for the stub docstrings is the only item that lands in a doc build rather than the pytest suite; `interrogate ≥ 95` IS automated in CI.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (`aliases.py`, `timescale.py`, new test file)
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-17 (plan-checker VERIFICATION PASSED, all 12 dimensions)
