---
phase: 15-release-v0-4-0-pypi-rtd
plan: 05
status: complete
requirements: [REL-02]
completed: 2026-06-14
---

# 15-05 SUMMARY — ReadTheDocs Verification

## Self-Check: PASSED

## Outcome

REL-02 satisfied: the v0.4.0 docs are pushed to `main` and the live ReadTheDocs build is
confirmed green by the maintainer.

## Task 1 — Validate .readthedocs.yaml + spatial importability (automated)

| Check | Result |
|-------|--------|
| `.readthedocs.yaml` parses, `version: 2`, `configuration: docs/conf.py` | ✓ rtd-yaml-ok |
| `python -c "import pycopg.spatial"` (TYPE_CHECKING guard → no geopandas needed) | ✓ spatial-import-ok |
| `.readthedocs.yaml` unchanged vs pre-phase-15 base (RESEARCH §D: no change needed) | ✓ unchanged |

Conclusion: `.readthedocs.yaml` needs **no change** for v0.4.0. The new `pycopg.spatial`
autodoc surface imports cleanly without geopandas (optional dep guarded under
`if TYPE_CHECKING:`), so RTD's pip env can autodoc it.

## Task 2 — Push to main + confirm live RTD build (human-gated)

- `git push origin main` — fast-forward `3ba6aaf..b658c69`; `origin/main` now equals local
  HEAD (`b658c69`, 0 behind / 0 ahead). Push performed by the orchestrator at maintainer
  request ("push to main only now").
- Live ReadTheDocs build for the new `main` commit confirmed **green** by the maintainer
  (resume-signal: "approved"). The Spatial Helpers page and `pycopg.spatial` autodoc
  entries render on https://pycopg.readthedocs.io/.

## Key Files

- created: `.planning/phases/15-release-v0-4-0-pypi-rtd/15-05-SUMMARY.md`
- verified-unchanged: `.readthedocs.yaml`

## Notes

No repo files were modified by this plan. It validated the existing RTD config and confirmed
the external (RTD dashboard) build state. The remaining Wave 4 steps (tag, GitHub Release,
PyPI publish, milestone audit) are irreversible and maintainer-gated.
