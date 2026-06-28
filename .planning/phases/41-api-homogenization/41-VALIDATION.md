---
phase: 41
slug: api-homogenization
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-28
---

# Phase 41 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~60–120 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | FREEZE-01..04 | — | N/A | unit | `uv run pytest tests/` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*The planner fills this table per task; the rows above are placeholders. See `41-RESEARCH.md` § Validation Architecture for the per-requirement validation approach.*

---

## Wave 0 Requirements

- [ ] `-W error::DeprecationWarning` CI gate added to `pyproject.toml`/CI (does NOT exist yet — Wave 0 deliverable per RESEARCH.md) after a discovery run suppresses third-party DeprecationWarnings
- [ ] `tests/test_deprecations.py` — `pytest.warns` stubs asserting warning location (caller's file) for the `where=` shim and exception `__getattr__` (FREEZE-01, FREEZE-02)
- [ ] Existing `tests/test_spatial.py`, `tests/test_accessor_parity.py`, `tests/test_exceptions*.py` cover the rename/parity behaviors

*Existing pytest infrastructure covers most phase requirements; the deprecation-warning gate + warns-location tests are the new Wave 0 additions.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `docs/stability.md` renders + is linked from README and Sphinx toctree | FREEZE-04 | Doc/site rendering | `uv run sphinx-build -W docs docs/_build` is clean; README contains a link to stability doc |
| FREEZE-03 audit findings table reviewed by user before fixes land | FREEZE-03 | Human review gate (D-05) | User approves the inventory table before any consistency fix is applied |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
