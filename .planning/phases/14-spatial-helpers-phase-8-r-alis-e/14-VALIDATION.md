---
phase: 14
slug: spatial-helpers-phase-8-r-alis-e
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-12
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (asyncio_mode = "auto") |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x -q -o addopts=""` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~60 seconds (full suite with coverage gate) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q -o addopts=""` (scoped to touched test files for speed)
- **After every plan wave:** Run `uv run pytest` (full suite with coverage gate)
- **Before `/gsd-verify-work`:** Full suite must be green (modulo 3 known pre-existing flaky DB tests — not regressions)
- **Max feedback latency:** 90 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (filled by planner) | | | SPA-01..SPA-06 | | identifiers via validate_identifiers; values via %s only | unit + integration | `uv run pytest tests/test_spatial.py -q -o addopts=""` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_spatial.py` — DB-free pure-builder tests (exact SQL string + params assertions) for SPA-02, SPA-03, SPA-04
- [ ] PostGIS integration tests (local pycopg_test db, postgis installed) for SPA-03, SPA-06
- [ ] `tests/test_parity.py` — auto-detects `spatial` property on both Database and AsyncDatabase (SPA-05); sync + async accessors must land in the same wave

*Existing infrastructure (pytest, conftest fixtures, pycopg_test db with PostGIS 3.6.3) covers framework needs — no install required.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification — pure builders assert exact SQL without DB; accessors covered by PostGIS integration tests; parity by test_parity.py.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
