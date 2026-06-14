---
phase: 15
slug: release-v0-4-0-pypi-rtd
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-14
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
>
> **Phase character:** Release phase — work is docs/CI/version edits, not new library
> behavior. Verification is dominated by *smoke* checks (build green, version string,
> wheel contents) and *manual/irreversible* gates (PyPI publish, RTD live, milestone
> audit). No new pytest unit tests are expected; the existing suite is the regression net.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (`[tool.pytest.ini_options]` in `pyproject.toml`) |
| **Config file** | `pyproject.toml` (`addopts: --cov-fail-under=94`) |
| **Quick run command** | `uv run pytest tests/ -x -q -o addopts=""` |
| **Full suite command** | `uv run pytest` |
| **Doc build (primary gate)** | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` |
| **Estimated runtime** | ~60–120 seconds (suite) · ~20s (sphinx build) |

---

## Sampling Rate

- **After every task commit (docs/version tasks):** `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` must exit 0
- **After every plan wave:** `uv run pytest tests/ -x -q -o addopts=""` (existing-suite regression — release edits must not break behavior)
- **Before the publish task:** full suite + `interrogate` + `sphinx-build -W` + `uv build` all green
- **Max feedback latency:** ~120 seconds for the sphinx/smoke loop

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (docs) | postgis/spatial docs | 1 | REL-01 | — | N/A | smoke | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` (exit 0) | ✅ | ⬜ pending |
| (autodoc) | spatial autodoc surface | 1 | REL-01 | — | N/A | smoke | `uv run interrogate pycopg --fail-under 95 --quiet` | ✅ | ⬜ pending |
| (version) | version bump | 1 | REL-03 | — | N/A | smoke | `uv sync && python -c "import pycopg; print(pycopg.__version__)"` → `0.4.0` | ✅ | ⬜ pending |
| (build) | wheel contents | 2 | REL-03 | — | N/A | smoke | `uv build && python -m zipfile -l dist/pycopg-0.4.0-py3-none-any.whl` (contains `pycopg/spatial.py`) | ✅ | ⬜ pending |
| (changelog) | CHANGELOG + MIGRATION | 1 | REL-03 | — | N/A | source | `grep -q '0.4.0' CHANGELOG.md` ; MIGRATION section present | ✅ | ⬜ pending |
| (ci-node) | Node 20→24 action bumps | 1 | REL-05 | — | N/A | source+CI | `grep` workflows for old pins absent; push → Actions green | ✅ | ⬜ pending |
| (rtd) | RTD build | 3 | REL-02 | — | N/A | manual | check https://readthedocs.org/projects/pycopg/builds/ live | ✅ | ⬜ pending |
| (publish) | PyPI publish + tag | 4 | REL-04 | — | N/A | manual | `pip install pycopg==0.4.0` in clean venv | ✅ | ⬜ pending |
| (audit) | milestone audit | 4 | REL-06 | — | N/A | manual | `gsd-audit-milestone` passes | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.* No new test framework or fixtures
needed — pytest, interrogate, mypy, and `sphinx-build -W` are all configured (Phases 9/13).
The release work is verified by the existing suite plus the doc-build smoke gate above.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| RTD build is live and green | REL-02 | RTD builds run on ReadTheDocs infra, not locally; cannot be asserted by CI | After docs merge, open https://readthedocs.org/projects/pycopg/builds/ and confirm latest build passed |
| Wheel published to PyPI | REL-04 | **Irreversible, outward-facing** — publishing to PyPI cannot be undone; requires human at the GitHub Release step | After tag + GitHub Release, confirm `publish.yml` ran; `pip install pycopg==0.4.0` in a clean venv resolves |
| Git tag `v0.4.0` created/pushed | REL-04 | **Irreversible, outward-facing** — pushed tags trigger the publish workflow; must be human-confirmed | Human creates/pushes tag after all prep verified green |
| Milestone audit passes | REL-06 | Meta-process gate run before archiving the milestone | Run `gsd-audit-milestone` as the final closing step |

---

## Validation Sign-Off

- [ ] All tasks have an `<automated>` smoke verify OR are listed as Manual-Only above
- [ ] Sampling continuity: doc-build smoke runs after every docs/version task commit
- [ ] Wave 0 covers all MISSING references (none — existing infra)
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] Every irreversible step (PyPI publish, git tag, GitHub release) is `autonomous: false`
- [ ] `nyquist_compliant: true` set in frontmatter once the plan-checker confirms the map

**Approval:** pending
