---
phase: 15-release-v0-4-0-pypi-rtd
plan: "02"
subsystem: release/packaging
tags: [release, version, changelog, migration, lockfile]
completed: "2026-06-14"
duration_seconds: 340

dependency_graph:
  requires: []
  provides:
    - version 0.4.0 in pyproject.toml + docs/conf.py
    - uv.lock consistent with 0.4.0 (uv lock --check passes)
    - CHANGELOG [0.4.0] section with corrected footer links
    - MIGRATION.md v0.3.x→v0.4.0 section (3 breaking changes)
  affects:
    - publish.yml (uv lock --check is first CI build step)
    - RTD (docs/conf.py release string)
    - pycopg.__version__ (resolved from pyproject.toml via importlib.metadata)

tech_stack:
  added: []
  patterns:
    - dynamic __version__ via importlib.metadata (no hand-edit of __init__.py)
    - Keep a Changelog 1.1.0 format
    - uv lock for lockfile regeneration

key_files:
  modified:
    - pyproject.toml (line 7: version 0.3.1 → 0.4.0)
    - docs/conf.py (line 17: release '0.3.1' → '0.4.0')
    - uv.lock (regenerated; pycopg v0.3.1 → v0.4.0)
    - CHANGELOG.md (added [0.4.0] section + fixed footer links)
    - MIGRATION.md (appended v0.3.x→v0.4.0 section)

decisions:
  - "Version bump touches exactly 2 hand-maintained files (pyproject.toml + docs/conf.py); __init__.py untouched per CLAUDE.md"
  - "uv lock (not uv sync) used to regenerate lockfile — minimal side-effects, no dep set change"
  - "CHANGELOG footer had missing [0.3.1] link and stale v0.3.0...HEAD ref; both corrected"
  - "MD024/MD025 markdownlint warnings in CHANGELOG and MIGRATION are pre-existing pattern inherent to multi-version changelog/multi-guide migration formats; not fixed (not Sphinx errors)"
  - "Sphinx build run after installing docs/requirements.txt via uv pip install — system sphinx-build broken (missing pygments in global Python 3.13 env, pre-existing)"
---

# Phase 15 Plan 02: Version Bump, Lockfile, CHANGELOG, and MIGRATION Summary

**One-liner:** Bumped version to 0.4.0 in 2 hand-maintained files, regenerated uv.lock, wrote complete CHANGELOG [0.4.0] section with corrected footer links, and appended MIGRATION.md v0.3.x→v0.4.0 guide for 3 real breaking changes.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Bump version to 0.4.0 + regenerate uv.lock | ccdee25 | pyproject.toml, docs/conf.py, uv.lock |
| 2 | CHANGELOG [0.4.0] section + MIGRATION.md v0.3.x→v0.4.0 | cdf0258 | CHANGELOG.md, MIGRATION.md |

## Verification Results

**Task 1:**
- `grep -n 'version = "0.4.0"' pyproject.toml` → line 7 (no 0.3.1 remaining)
- `grep -n "release = '0.4.0'" docs/conf.py` → line 17
- `uv lock --check` → exit 0 ("Resolved 43 packages in 1ms")
- `uv sync --all-extras --dev && python -c "import pycopg; print(pycopg.__version__)"` → `0.4.0`
- `pycopg/__init__.py` unchanged (dynamic importlib.metadata resolution confirmed)

**Task 2:**
- `grep -c '## \[0.4.0\]' CHANGELOG.md` → 1, dated 2026-06-14
- `grep -c '\[0.4.0\]: .../compare/v0.3.1...v0.4.0' CHANGELOG.md` → 1
- `grep -c '\[0.3.1\]: .../compare/v0.3.0...v0.3.1' CHANGELOG.md` → 1
- `grep '\[Unreleased\]:' CHANGELOG.md` → compares v0.4.0...HEAD
- `grep -c 'Migration Guide: v0.3.x to v0.4.0' MIGRATION.md` → 1
- `grep -c 'ExtensionNotAvailable' MIGRATION.md` → 6 (named in all 3 breaking change entries)
- `grep -c 'DatabaseExists' MIGRATION.md` → 5
- `grep -c 'psycopg_async' MIGRATION.md` → 3
- `grep -c 'Migration Guide: v0.2.0 to v0.3.0' MIGRATION.md` → 1 (prior guide preserved)
- `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` → "La compilation a réussi" (exit 0)

## Deviations from Plan

### Auto-fixed Issues

None — plan executed exactly as written.

### Observations

**System sphinx-build broken (pre-existing, not a regression):** The system `sphinx-build`
at `/home/loc/.local/bin/sphinx-build` fails with `ModuleNotFoundError: No module named 'pygments'`
due to a broken global Python 3.13 installation. This is pre-existing. Workaround: run
`uv pip install -r docs/requirements.txt` first so that `uv run sphinx-build` uses the
project venv (which has Sphinx 9.1.0 + pygments). The plan's verify command
`uv run sphinx-build ...` works correctly after this install step.

**MD024/MD025 markdownlint warnings:** CHANGELOG.md and MIGRATION.md emit duplicate-heading
and multiple-H1 warnings (markdownlint). These are inherent to Keep-a-Changelog format
(each version section repeats `### Added`, `### Changed`, etc.) and to a multi-version
migration guide (multiple `# Migration Guide:` top-level headers). They are not Sphinx
errors and do not affect the build.

## CHANGELOG [0.4.0] Content Summary

- **### Added:** 11 spatial helpers (db.spatial.*), SpatialAccessor/AsyncSpatialAccessor
  exports, async/sync parity completions, PooledDatabase.execute commit fix, DatabaseExists
  exception, 5 new validate_* utils, interrogate CI, mypy CI, uv.lock/.python-version
- **### Changed (3 BREAKING):** psycopg_async URL, close() disposes engine, custom exceptions
  replace RuntimeError/ValueError; plus signature alignment, numpydoc migration, uv tooling
- **### Fixed:** session() exception masking, atomic migrations, subprocess.os.environ,
  async create_role validation, async from_dataframe primary_key, __version__ fix
- **### Security:** identifier validation closed residual create_role async gap

## MIGRATION.md v0.3.x→v0.4.0 Sections

1. **AsyncDatabase engine URL (psycopg_async driver)** — impact: low; API unchanged
2. **AsyncDatabase.close() now disposes the engine** — impact: low (was already incorrect to use after close)
3. **Custom exception types replace RuntimeError/ValueError** — impact: medium; shows
   `except RuntimeError` → `except ExtensionNotAvailable` and `except DatabaseExists` examples

## Known Stubs

None. All changes are release metadata and documentation — no UI or data-flow stubs.

## Threat Flags

None. No new executable surface introduced — version/changelog/lockfile edits only.

## Self-Check

- [x] `pyproject.toml` exists with `version = "0.4.0"` at line 7
- [x] `docs/conf.py` exists with `release = '0.4.0'` at line 17
- [x] `uv.lock` updated (uv lock --check exits 0)
- [x] `CHANGELOG.md` has `## [0.4.0]` section + 5-line corrected footer block
- [x] `MIGRATION.md` has `Migration Guide: v0.3.x to v0.4.0` section (3 breaking changes)
- [x] Commits ccdee25 and cdf0258 verified in git log
- [x] Sphinx build green (exit 0)

## Self-Check: PASSED
