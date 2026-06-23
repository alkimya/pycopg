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

## Human-Gated Publish Steps (Task 3 — PENDING)

> **Status: AWAITING HUMAN ACTION**

The following steps must be performed by the human. The executor must NOT perform these.

### Steps

1. **Push release commit to origin/main:**
   ```bash
   git push origin main
   ```

2. **Create and push annotated tag:**
   ```bash
   git tag -a v0.8.0 -m "pycopg v0.8.0 — TimescaleDB advanced"
   git push origin v0.8.0
   ```

3. **Create GitHub Release** (fires `publish.yml` via `release: published`):
   ```bash
   gh release create v0.8.0 --title "v0.8.0 — TimescaleDB Advanced" --notes-from-tag
   ```
   Or paste the `CHANGELOG.md` `[0.8.0]` Added section as release notes.

4. **Watch publish workflow:**
   ```bash
   gh run watch
   ```
   Or visit the Actions tab. The `build` job runs `uv lock --check` + `uv build`, then the `publish` job OIDC-publishes to PyPI (no API token needed).

5. **Confirm live on PyPI:**
   Visit https://pypi.org/project/pycopg/0.8.0/

6. **Clean-venv install smoke:**
   ```bash
   python -m venv /tmp/pycopg-080-smoke
   /tmp/pycopg-080-smoke/bin/pip install "pycopg==0.8.0"
   /tmp/pycopg-080-smoke/bin/python -c "import pycopg; print(pycopg.__version__)"
   ```
   Must print `0.8.0` with no errors.

---

## Publish Outcome (to be filled after human-gated steps)

| Step | Result |
|------|--------|
| Tag v0.8.0 pushed | PENDING |
| GitHub Release created | PENDING |
| publish.yml `publish` job | PENDING |
| PyPI 0.8.0 URL live | PENDING |
| Clean-venv smoke (prints 0.8.0) | PENDING |
| Workflow run URL | PENDING |
