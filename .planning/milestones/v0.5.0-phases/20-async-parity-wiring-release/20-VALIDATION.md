---
phase: 20
slug: async-parity-wiring-release
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-15
---

# Phase 20 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest with pytest-asyncio |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_parity.py tests/test_etl_accessor.py -o addopts="" -x -q` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~20 seconds (quick) · ~90 seconds (full suite on real PG) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_parity.py tests/test_etl_accessor.py -o addopts="" -x -q`
- **After every plan wave:** Run the quick command above plus `uv run pytest tests/test_etl.py -o addopts="" -x -q`
- **Before `/gsd-verify-work`:** Full suite must be green at ≥ 94% coverage — `uv run pytest`
- **Max feedback latency:** 90 seconds

> ⚠️ **Coverage gate caveat (Pitfall 5 in RESEARCH §Coverage Gate):** the `-o addopts=""` targeted-run trick used for fast task-level feedback does **NOT** measure full coverage. The SC-5 ≥94% coverage gate MUST be measured with the bare `uv run pytest` full suite (which carries `--cov-fail-under=94` in pyproject addopts). There are ~3 pre-existing flaky full-suite DB tests unrelated to Phase 20 — do not mistake them for regressions; the two `TestAsyncParity` failures, by contrast, become green once `async_db.etl` is wired.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 20-async-run | async accessor | 1 | ETL-12 | — | `await async_db.etl.run(pipeline)` returns `RunResult` equivalent to sync; transform dispatched via `asyncio.to_thread` | integration | `uv run pytest tests/test_etl_accessor.py -o addopts="" -x` | ✅ | ⬜ pending |
| 20-async-history | async accessor | 1 | ETL-12 | — | `await async_db.etl.history(name)` returns `list[RunResult]` | integration | `uv run pytest tests/test_etl_accessor.py -o addopts="" -x` | ✅ | ⬜ pending |
| 20-async-lastrun | async accessor | 1 | ETL-12 | — | `await async_db.etl.last_run(name)` returns `RunResult \| None` | integration | `uv run pytest tests/test_etl_accessor.py -o addopts="" -x` | ✅ | ⬜ pending |
| 20-async-tothread | async accessor | 1 | ETL-12 | — | Slow transform does not block event loop for concurrent coroutines (SC-2) | behavioral | `uv run pytest tests/test_etl_accessor.py -o addopts="" -x` | ✅ | ⬜ pending |
| 20-wire-etl | wiring | 1 | ETL-13 | — | `async_db.etl` lazy property returns `AsyncETLAccessor` (mirrors `async_db.spatial`) | unit | `uv run pytest tests/test_parity.py::TestEtlParity -o addopts="" -x` | ❌ W0 | ⬜ pending |
| 20-parity-test | parity | 2 | ETL-13 | — | `TestEtlParity` enumerates `ETLAccessor` vs `AsyncETLAccessor` and asserts full surface parity (SC-4) | structural | `uv run pytest tests/test_parity.py::TestEtlParity -o addopts="" -x` | ❌ W0 | ⬜ pending |
| 20-exports | wiring | 1 | ETL-13 | — | `ETLAccessor`, `AsyncETLAccessor`, `RunResult`, `Pipeline` importable from `pycopg` | unit | `uv run python -c "from pycopg import ETLAccessor, AsyncETLAccessor, RunResult, Pipeline"` | ✅ | ⬜ pending |
| 20-cov-gate | release | 3 | SC-5 | — | Full-suite coverage ≥ 94%; ratchet held | gate | `uv run pytest` | ✅ | ⬜ pending |
| 20-interrogate | release | 3 | SC-5 | — | Docstring coverage ≥ 95 on ETL surface | gate | `uv run interrogate pycopg --fail-under 95 --quiet` | ✅ | ⬜ pending |
| 20-sphinx | release | 3 | SC-5 | — | `docs/etl.md` renders without `-W` warnings; in toctree | gate | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_parity.py::TestEtlParity` — structural surface-parity class (covers ETL-13 / SC-4), drop-in following the existing `TestAsyncParity` pattern (`inspect.getmembers`, `not name.startswith("_")`)
- [ ] (Optional, add if SC-5 coverage is at risk) behavioral async parity tests in `tests/test_etl_accessor.py` — exercise `await async_db.etl.run/history/last_run/dry_run` against real DB so the async code path is covered, not just structurally enumerated

*Existing infrastructure (pytest + pytest-asyncio + real-PG fixtures from `tests/test_etl_accessor.py`) covers everything else.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `docs/etl.md` live on ReadTheDocs | SC-5 | RTD build happens on the hosted service post-merge, not in local CI | After tag/push, confirm the ETL page renders at the project's RTD URL |
| `pycopg==0.5.0` published to PyPI | SC-5 | Publish runs via GitHub Release → `publish.yml` (OIDC trusted publish), not locally | After creating the GitHub Release, confirm `pip install pycopg==0.5.0` resolves from PyPI |

*All in-repo phase behaviors have automated verification; the two above are external-service post-merge confirmations.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (`TestEtlParity`)
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
