---
phase: 15-release-v0-4-0-pypi-rtd
plan: 06
status: complete
requirements: [REL-04, REL-06]
completed: 2026-06-14
---

# 15-06 SUMMARY — Ship v0.4.0 + Milestone Audit

## Self-Check: PASSED

## Outcome

REL-04 and REL-06 satisfied: pycopg v0.4.0 is published to PyPI via the GitHub Release
(OIDC trusted publishing), the `v0.4.0` tag is on origin, the clean-venv install is verified,
and the milestone audit passed.

## Task 1 — Supply-chain confirmation of publish.yml (human-verify, automated-assisted)

| Check | Result |
|-------|--------|
| OIDC `id-token: write` present (publish.yml:34) | ✓ |
| Official `pypa/gh-action-pypi-publish@release/v1` (publish.yml:43) | ✓ |
| No hardcoded PyPI token/secret in any workflow | ✓ (the only matches were `POSTGRES_PASSWORD`/`PGPASSWORD` in tests.yml — local test DB, not PyPI) |
| `environment: pypi` (publish.yml:32) | ✓ |
| dist wheel = clean 0.4.0 artifact with `pycopg/spatial.py` (85,643 B) | ✓ |

## Task 2 — Create + push v0.4.0 tag (human-action, IRREVERSIBLE)

- Maintainer created annotated tag `v0.4.0` and pushed it.
- Confirmed on remote: `refs/tags/v0.4.0` → `30ff8ee` (= origin/main = local HEAD).

## Task 3 — Publish GitHub Release → PyPI + verify install (human-action, IRREVERSIBLE)

- Maintainer published the GitHub Release for `v0.4.0`; `publish.yml` build + publish jobs ran
  (OIDC trusted publishing). Maintainer confirmed "published".
- Clean-venv install verified by the orchestrator:
  `python -m venv /tmp/pycopg-verify && pip install pycopg==0.4.0` → exit 0;
  `python -c "import pycopg; print(pycopg.__version__)"` → **0.4.0**.
- pycopg 0.4.0 is live on PyPI.

## Task 4 — Milestone audit (human-verify, REL-06)

- `gsd-audit-milestone` run for v0.4.0 → **PASSED**.
- Report: `.planning/v0.4.0-MILESTONE-AUDIT.md`
  - Requirements: 46/46 satisfied (3-source cross-reference; 0 orphans)
  - Phases: 7/7 verified (9–14 `passed`; 15 verified at phase completion)
  - Integration: 4/4 E2E flows wired, 0 broken cross-phase links
  - Tech debt (non-blocking): Phase 12 coverage-95 stretch (actual 90→92/94); `TableNotFound`
    has no raise site (export-only); Nyquist backfill optional for phases 10/12.

## Key Files

- created: `.planning/phases/15-release-v0-4-0-pypi-rtd/15-06-SUMMARY.md`
- created: `.planning/v0.4.0-MILESTONE-AUDIT.md`
- updated: `.planning/REQUIREMENTS.md` (REL-02, REL-04, REL-06 → Complete)

## Notes

All tasks in this plan were irreversible and maintainer-gated. The tag, GitHub Release, and
PyPI publish were performed by the maintainer; the orchestrator confirmed the supply-chain
inspection, the clean-venv install, and ran the milestone audit.
