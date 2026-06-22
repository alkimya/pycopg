---
phase: 29-release-v0-7-0
verified: 2026-06-22T00:00:00Z
status: passed
score: 8/8 must-haves verified
overrides_applied: 0
---

# Phase 29: Release v0.7.0 Verification Report

**Phase Goal:** v0.7.0 is published to PyPI with all quality gates green, a complete CHANGELOG Breaking/Added section, and a MIGRATION v0.6→v0.7 guide that enables callers to upgrade safely
**Verified:** 2026-06-22
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | Version is `0.7.0` in `pyproject.toml` | ✓ VERIFIED | `grep '^version = "0.7.0"' pyproject.toml` → line 7, exits 0 |
| 2  | Version is `0.7.0` in `docs/conf.py` | ✓ VERIFIED | `grep "release = '0.7.0'" docs/conf.py` → line 17, exits 0 |
| 3  | Git tag `v0.7.0` exists | ✓ VERIFIED | `git tag --list v0.7.0` → `v0.7.0`; tag points to commit `0217c7d` |
| 4  | All quality gates pass (cov ≥94%, interrogate ≥95%, Sphinx -W clean, -W error::DeprecationWarning green) | ✓ VERIFIED | 29-02-GATES.md records all four gate commands with exit 0; deprecation gate re-run independently: exit 0, prints `0.7.0` |
| 5  | CHANGELOG `[0.7.0]` has `### Breaking` entry pointing to MIGRATION | ✓ VERIFIED | `CHANGELOG.md` line 12 `## [0.7.0] - 2026-06-22`; lines 12-22 contain `### Breaking` with 56-name note and MIGRATION pointer |
| 6  | CHANGELOG `[0.7.0]` has `### Added` entry (incremental ETL, no out-of-scope claims) | ✓ VERIFIED | Lines 23-43 contain `### Added`; grep for `initial_watermark|CDC|WAL|scheduler|multi-column` in `[0.7.0]` block returns clean; `docs/etl.md` pointer on line 41 |
| 7  | MIGRATION v0.6→v0.7 has the 56-name flat→accessor table | ✓ VERIFIED | Table rows: `grep -c '| \`db\.' MIGRATION.md` → 112 (56 names × 2 side-by-side columns); total stated as 56 at line 90 |
| 8  | MIGRATION v0.6→v0.7 has incremental-usage note pointing to `docs/etl.md` | ✓ VERIFIED | MIGRATION.md lines 100-119: `## New in v0.7.0: Incremental ETL` subsection; 5 occurrences of `incremental` in v0.6→v0.7 section; `docs/etl.md` pointer at line 118 |

**Score: 8/8 truths verified**

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` | `version = "0.7.0"` | ✓ VERIFIED | Line 7 confirmed |
| `docs/conf.py` | `release = '0.7.0'` | ✓ VERIFIED | Line 17 confirmed |
| `CHANGELOG.md` | `[0.7.0]` Breaking + Added, dated 2026-06-22 | ✓ VERIFIED | Fully populated, real date, no TBD |
| `MIGRATION.md` | 56-name table + incremental note | ✓ VERIFIED | 56 entries in table + `## New in v0.7.0: Incremental ETL` subsection |
| `.planning/phases/29-release-v0-7-0/29-02-GATES.md` | Recorded gate outputs | ✓ VERIFIED | File exists, all 4 gates documented with commands, exit statuses, measured values |
| `.planning/phases/29-release-v0-7-0/29-03-RELEASE-LOG.md` | Tag, Release URL, workflow run, smoke result | ✓ VERIFIED | File exists; records tag `v0.7.0`, GitHub Release URL, workflow run 27953179349 (conclusion: success), PyPI URL, clean-venv smoke exit 0 |
| `dist/pycopg-0.7.0.tar.gz` | Local build artifact | ✓ VERIFIED | File present in `dist/` |
| `dist/pycopg-0.7.0-py3-none-any.whl` | Local build artifact | ✓ VERIFIED | File present in `dist/` |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `CHANGELOG.md [0.7.0] Added` | `docs/etl.md` | `[docs/etl.md](docs/etl.md)` pointer | ✓ WIRED | Line 41 of CHANGELOG.md contains the pointer |
| `CHANGELOG.md [0.7.0] Breaking` | `MIGRATION.md` | `[MIGRATION.md](MIGRATION.md#...)` pointer | ✓ WIRED | Lines 18-21 of CHANGELOG.md link directly to MIGRATION.md |
| `MIGRATION.md incremental note` | `docs/etl.md` | `[docs/etl.md](docs/etl.md)` pointer | ✓ WIRED | Line 118 of MIGRATION.md contains the pointer |
| GitHub Release `published` event | `.github/workflows/publish.yml` OIDC | `release: types [published]` trigger | ✓ WIRED | Workflow run 27953179349 recorded in RELEASE-LOG.md with conclusion: success |
| PyPI `pycopg 0.7.0` | clean-venv smoke | `pip install pycopg==0.7.0` + import | ✓ WIRED | RELEASE-LOG.md records successful install + `import pycopg; print(pycopg.__version__)` → `0.7.0` |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `pyproject.toml` declares 0.7.0 | `grep '^version = "0.7.0"' pyproject.toml` | Line 7 matches, exit 0 | ✓ PASS |
| `docs/conf.py` declares 0.7.0 | `grep "release = '0.7.0'" docs/conf.py` | Line 17 matches, exit 0 | ✓ PASS |
| No stray 0.6.0 version | `grep '"0.6.0"' pyproject.toml` | exit non-zero | ✓ PASS |
| No TBD in release artifacts | grep TBD/FIXME/XXX over 4 release files | NONE FOUND | ✓ PASS |
| Deprecation import gate | `uv run python -W error::DeprecationWarning -c "import pycopg"` | exit 0, prints `0.7.0` | ✓ PASS |
| CHANGELOG 0.7.0 block clean of deferred items | grep `initial_watermark\|CDC\|scheduler\|multi-column` | OUT-OF-SCOPE CLEAN | ✓ PASS |
| Git tag exists | `git tag --list v0.7.0` | `v0.7.0` on commit `0217c7d` | ✓ PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| REL-07 | 29-01, 29-02, 29-03 | v0.7.0 released — version bumped, CHANGELOG finalized, MIGRATION complete, all gates green, tagged + published via OIDC, clean-venv smoke confirmed | ✓ SATISFIED | All sub-criteria verified above; REQUIREMENTS.md traceability table marks REL-07 Phase 29 Complete |

**Orphaned requirements check:** No additional Phase 29 requirement IDs exist in REQUIREMENTS.md beyond REL-07 — none orphaned.

---

### Anti-Patterns Found

No debt markers (TBD, FIXME, XXX) found in any of the four release artifacts (pyproject.toml, docs/conf.py, CHANGELOG.md, MIGRATION.md). No placeholders, empty stubs, or out-of-scope claims detected.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | None | — | — |

---

### Human Verification Required

All human-gated items in Plan 03 (tag creation, GitHub Release publish, OIDC workflow watch, clean-venv smoke) are recorded as completed in 29-03-RELEASE-LOG.md with explicit evidence:

- Git tag `v0.7.0` pushed to origin (commit `0217c7d`)
- GitHub Release at https://github.com/alkimya/pycopg/releases/tag/v0.7.0 published 2026-06-22T12:37:43Z
- OIDC workflow run 27953179349 conclusion: success
- PyPI https://pypi.org/project/pycopg/0.7.0/ live
- Clean-venv smoke: `pip install pycopg==0.7.0` from live PyPI → `0.7.0`, exit 0

These are externally-verifiable facts logged by the human operator. No additional human verification items remain open.

---

### Gaps Summary

No gaps. All 8 must-have truths verified against the actual codebase. All locally-checkable facts independently re-confirmed:

- Version strings correct in both source-of-truth files
- Git tag `v0.7.0` present on the release commit
- CHANGELOG `[0.7.0]` has both `### Breaking` and `### Added`, dated 2026-06-22, no out-of-scope claims
- MIGRATION 56-name table intact (112 `| \`db.` column cells = 56 entries)
- MIGRATION incremental subsection present with `docs/etl.md` pointer
- Deprecation import gate re-run independently: exit 0
- Quality gate record (29-02-GATES.md) substantive and complete
- Release log (29-03-RELEASE-LOG.md) records all external evidence

---

_Verified: 2026-06-22_
_Verifier: Claude (gsd-verifier)_
