---
phase: 13
slug: qualit-documentaire-docstrings-numpydoc-interrogate
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-10
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (pytest-cov, pytest-asyncio) |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q -o addopts=""` |
| **Full suite command** | `uv run pytest` (coverage gate 92%) |
| **Estimated runtime** | ~60 seconds (full suite) |

**Local env caveat:** 3 full-suite DB tests fail in the local env (pre-existing, not regressions). Targeted runs use `-o addopts=""`.

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q -o addopts=""`
- **After every plan wave:** Run `uv run pytest` (full suite with coverage gate)
- **Before `/gsd-verify-work`:** Full suite green + `uv run interrogate pycopg --fail-under 95 --quiet` + warning-free `sphinx-build`
- **Max feedback latency:** ~60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | — | 0 | DOC-07 | — | N/A | CI smoke | `uv run interrogate pycopg --fail-under 95 --quiet` | ❌ W0 | ⬜ pending |
| TBD | — | 0 | DOC-08 | — | N/A | CI build | `uv run sphinx-build -W -b html docs docs/_build/html` | ❌ W0 | ⬜ pending |
| TBD | — | 0 | DOC-11 / DOC-12 | — | N/A | CI (non-blocking) | `uv run mypy pycopg/` | ❌ W0 | ⬜ pending |
| TBD | — | — | DOC-06 | — | N/A | sphinx (form) + interrogate (coverage) | `sphinx-build -W … && uv run interrogate pycopg --fail-under 95` | ❌ W0 | ⬜ pending |
| TBD | — | — | DOC-09 | — | N/A | unit | `uv run pytest tests/test_database_integration.py tests/test_async_database.py -k "timescale or postgis or extension" -x -o addopts=""` | ✅ (needs update) | ⬜ pending |
| TBD | — | — | DOC-09 | — | N/A | unit/integration | `uv run pytest tests/test_async_database.py -k "create_raises_when_exists" -o addopts=""` | ✅ (needs update) | ⬜ pending |
| TBD | — | — | DOC-10 | — | N/A | unit | `uv run pytest tests/test_version.py -o addopts=""` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*The planner fills Task IDs / Plan / Wave columns when PLAN.md files are created.*

---

## Wave 0 Requirements

- [ ] `.github/workflows/tests.yml` — CI step for interrogate (blocking, `--fail-under 95`) — covers DOC-07
- [ ] `.github/workflows/tests.yml` — CI step for sphinx-build (warning guard, D-08) — covers DOC-08
- [ ] `.github/workflows/tests.yml` — CI step for mypy (non-blocking, D-05) — covers DOC-11/DOC-12
- [ ] Baseline measure: `uv run interrogate pycopg --verbose` before locking `fail-under = 95`
- [ ] Empirical check: does `sphinx-build -W` escalate napoleon malformed-section warnings to exit 1? (Sphinx #9142 — fallback: grep stderr)
- [ ] `tests/test_version.py` — covers DOC-10

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Rendered HTML docs read correctly (numpydoc sections render as tables) | DOC-06/DOC-08 | Visual rendering quality not assertable | Build docs, open `docs/_build/html`, spot-check 2-3 migrated pages |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
