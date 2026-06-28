---
phase: 41
slug: api-homogenization
status: approved
nyquist_compliant: true
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
| 41-01-01 | 01 | 1 | FREEZE-01, FREEZE-02 | T-41-SC | `-W error::DeprecationWarning` gate green (no internal pycopg path warns) | gate | `uv run pytest -q` | ❌ W0 | ⬜ pending |
| 41-01-02 | 01 | 1 | FREEZE-01, FREEZE-02 | — | warns-location scaffold (xfail) | unit | `uv run pytest tests/test_deprecations.py -q` | ❌ W0 | ⬜ pending |
| 41-02-01 | 02 | 2 | FREEZE-02 | T-41-04 | old name → same class object, warns on import/access (D-07/D-09) | unit | `uv run pytest tests/test_deprecations.py::TestExceptionAliases -x -q && python -c "import pycopg" && uv run ruff check pycopg/exceptions.py` | ✅ | ⬜ pending |
| 41-02-02 | 02 | 2 | FREEZE-02 | T-41-05 | all internal raise sites on new `*Error`; N818 suppression removed; no deprecated internal path (D-10) | suite | `uv run pytest -q` | ✅ | ⬜ pending |
| 41-03-01 | 03 | 3 | FREEZE-01 | T-41-07 | builders `filter=`-only; `validate_identifiers` count unchanged (no injection regression) | unit | `uv run pytest tests/test_spatial.py -x -q` | ✅ | ⬜ pending |
| 41-03-02 | 03 | 3 | FREEZE-01 | T-41-08 | `where=` shim warns at caller's file (D-09); `TypeError` if both; sync/async parity (D-11) | unit | `uv run pytest tests/test_deprecations.py::TestWhereDeprecation tests/test_parity.py -x -q` | ✅ | ⬜ pending |
| 41-04-01 | 04 | 4 | FREEZE-03 | — | consistency findings table produced (discovery, no code) | artifact | `test -f` audit table + `grep` headers | ✅ | ⬜ pending |
| 41-04-02 | 04 | 4 | FREEZE-03 | — | **D-05 user review gate** — fixes blocked until approval | manual | `checkpoint:human-verify` (`autonomous: false`) | — | ⬜ pending |
| 41-04-03 | 04 | 4 | FREEZE-03 | T-41-11 | kw-only `*` enforced (D-03/D-04, clean break); `within()` 4-positional flagged; parity (D-11) | unit | `uv run pytest tests/test_deprecations.py::TestKwOnlyEnforcement tests/test_parity.py -x -q` | ✅ | ⬜ pending |
| 41-05-01 | 05 | 5 | FREEZE-04 | — | `docs/stability.md` builds under Sphinx `-W`; linked from README + toctree (D-01/D-02) | doc | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html && grep -qi 'stability' README.md` | ⬜ | ⬜ pending |
| 41-05-02 | 05 | 5 | FREEZE-04 (+01/02/03) | — | MIGRATION `v0.10.x → 1.0.0` section lists every rename + D-08 relaxation note | doc | `grep -q 'v0.10.x' MIGRATION.md` + rename anchors | ⬜ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky · File Exists: ✅ exists · ❌ W0 created in Wave 0 · ⬜ created this phase*

*Per-requirement validation approach: see `41-RESEARCH.md` § Validation Architecture. Task IDs follow the `41-PP-TT` convention (plan-task); see each `41-PP-PLAN.md` for the named tasks.*

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
