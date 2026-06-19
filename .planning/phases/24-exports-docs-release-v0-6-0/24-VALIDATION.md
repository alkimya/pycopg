---
phase: 24
slug: exports-docs-release-v0-6-0
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-19
---

# Phase 24 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> **Docs + release phase — no new code.** "Tests" here are the three release gates
> (coverage / interrogate / Sphinx `-W`) plus the manual clean-venv smoke test.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (`uv run pytest`) |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` — `addopts = "-v --cov=pycopg --cov-report=term-missing --cov-report=html --cov-fail-under=94"` |
| **Quick run command** | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` (the doc gate is the fast per-task sanity check) |
| **Full suite command** | `uv run pytest` (coverage ≥94) + `uv run interrogate pycopg --fail-under 95 --quiet` + `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` |
| **Estimated runtime** | ~60–120 seconds (full three-gate sequence) |

---

## Sampling Rate

- **After every task commit:** Run `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` (catches `-W` regressions from doc edits immediately)
- **After every plan wave:** Run the full three-gate sequence (pytest + interrogate + sphinx -W)
- **Before `/gsd-verify-work`:** All three gates green AND the manual clean-venv smoke test confirmed
- **Max feedback latency:** ~120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (exports verify) | release | — | REORG-05 | — | N/A | smoke import | `python -c "from pycopg import TimescaleAccessor, AdminAccessor, SchemaAccessor, MaintAccessor, BackupAccessor, AsyncTimescaleAccessor, AsyncAdminAccessor, AsyncSchemaAccessor, AsyncMaintAccessor, AsyncBackupAccessor; print('OK')"` | ✅ inline | ⬜ pending |
| (Sphinx -W gate) | docs | — | REORG-05 | — | N/A | doc gate | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` | ✅ build cmd | ⬜ pending |
| (interrogate gate) | docs | — | REORG-05 | — | N/A | doc gate | `uv run interrogate pycopg --fail-under 95 --quiet` | ✅ tool cmd | ⬜ pending |
| (coverage gate) | release | — | REORG-05 | — | N/A | coverage gate | `uv run pytest` | ✅ full suite | ⬜ pending |
| (release smoke) | release | — | REORG-05 | — | N/A | manual smoke | clean-venv `pip install pycopg==0.6.0` → `python -c "from pycopg import Database; db = Database.from_env(); print(db.timescale)"` | manual | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> Plan/Wave columns are finalized by the planner. This phase's verification is gate-based, not new-test-based — every row is an existing command, not a new `tests/test_*.py`.

---

## Wave 0 Requirements

*None — existing test infrastructure covers all phase requirements. This phase adds no new code, no new test files, and no new framework dependencies. Sphinx, interrogate, and pytest are all already present and verified live.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Clean-venv install smoke test | REORG-05 (criterion #4) | Requires a published PyPI artifact + a throwaway venv + a live PostgreSQL connection — matches the manual flow of the three prior PyPI releases (v0.3/0.4/0.5); deliberately NOT automated in CI (D-06). | In a fresh venv: `pip install pycopg==0.6.0`; then `python -c "from pycopg import Database; db = Database.from_env(); print(db.timescale)"`. Confirm import + accessor repr print. |
| PyPI publish + GitHub release + git tag | REORG-05 (criterion #4) | Outward-facing, irreversible publish — requires human sign-off before `twine`/`gh release create` (Pitfall 6). | Human approves release at the checkpoint; OIDC publish to PyPI; `git tag v0.6.0`; RTD rebuilds from tag. |

---

## Validation Sign-Off

- [ ] All tasks have an `<automated>` verify command or are explicitly Manual-Only (above)
- [ ] Sampling continuity: no 3 consecutive tasks without an automated verify
- [ ] Wave 0 covers all MISSING references (N/A — no Wave 0 for this phase)
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
