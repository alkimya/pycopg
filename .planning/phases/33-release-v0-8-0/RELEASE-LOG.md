# Release Log — pycopg v0.8.0

**Date:** 2026-06-23
**Release:** v0.8.0 — TimescaleDB Advanced

---

## Build Verification

**Lockfile:** `uv lock --check` → PASS (43 packages resolved, lockfile current)

**Build artifacts (via `uv build`):**
- `pycopg-0.8.0.tar.gz` — sdist
- `pycopg-0.8.0-py3-none-any.whl` — wheel

Both artifacts carry version `0.8.0` in their filenames. Build successful.

---

## Release Commit

**Commit SHA:** `9c12bd12a14403adb85d92fa38f8a12f0b98d059`

**Commit message:** `chore(33-03): run 4 quality gates and record GATES.md (D-02, D-12, D-13)`

**Working tree:** clean (verified via `git status --porcelain` → empty)

**Commits in this release (Plans 01-03):**

| Hash | Description |
|------|-------------|
| `9c12bd1` | chore(33-03): run 4 quality gates and record GATES.md |
| `593adec` | docs(33-02): complete docs-rewrite plan — SUMMARY + STATE + ROADMAP |
| `a77cd77` | docs(33-02): update README accessor count to (15 methods) + add v0.8.0 highlights |
| `3df42cd` | docs(33-02): extend api-reference.md TimescaleDB Methods table with 9 new rows |
| `f6b7817` | docs(33-02): rewrite timescaledb.md time-series sections + add Advanced Chunk section |
| `24077d7` | docs(33-01): complete version-bump-and-changelog plan |

**Changes in v0.8.0:**
- `pyproject.toml`: version `0.7.0` → `0.8.0`
- `docs/conf.py`: release `0.7.0` → `0.8.0`
- `CHANGELOG.md`: `## [0.8.0] - 2026-06-23` Added entry (4 chunk/dim + 3 cagg + 2 query helper methods)
- `docs/timescaledb.md`: rewrote raw-SQL sections to first-class API + new Advanced Chunk section
- `docs/api-reference.md`: +9 rows to TimescaleDB Methods table
- `README.md`: accessor count (6) → (15) + compact v0.8.0 examples

---

## Human-Gated Publish Steps (Task 3 — COMPLETE)

> **Status: COMPLETED — v0.8.0 LIVE ON PyPI**

All steps were performed by the human. Outcome recorded below.

---

## Publish Outcome

| Step | Result |
|------|--------|
| Tag v0.8.0 pushed | SUCCESS — tag `v0.8.0` commit `5ce5d0063dd1684425c6075266e10f6f5080ea1c` pushed to origin |
| GitHub Release created | SUCCESS — "v0.8.0 — TimescaleDB Advanced" published on GitHub (fired `release: published` event) |
| publish.yml `publish` job | SUCCESS — OIDC trusted publish, no API token; run completed in 32s |
| PyPI 0.8.0 URL live | SUCCESS — https://pypi.org/project/pycopg/0.8.0/ returns HTTP 200 |
| Clean-venv smoke (prints 0.8.0) | SUCCESS — `pip install pycopg==0.8.0` + `import pycopg; print(pycopg.__version__)` printed `0.8.0` |
| Workflow run URL | https://github.com/alkimya/pycopg/actions/runs/28044147070 |

### Publish Detail

- **Tag commit SHA:** `5ce5d0063dd1684425c6075266e10f6f5080ea1c`
- **Workflow run ID:** `28044147070`
- **Workflow run URL:** https://github.com/alkimya/pycopg/actions/runs/28044147070
- **Publish method:** OIDC trusted publishing via `.github/workflows/publish.yml` (`release: published` event) — no API token
- **Workflow duration:** 32 seconds
- **PyPI release URL:** https://pypi.org/project/pycopg/0.8.0/
- **Clean-venv smoke result:** `import pycopg; print(pycopg.__version__)` → printed `0.8.0` (no errors)
- **Origin/main sync:** 0 ahead / 0 behind (fully synced before tagging)
