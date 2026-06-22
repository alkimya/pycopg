# Phase 29 Plan 03 — Release Log v0.7.0

Date: 2026-06-22

---

## Task 1: Release Artifacts and Local Build (COMPLETE)

### Plan 01 + Plan 02 Status

- **Plan 01 (version bump + release artifacts):** COMPLETE (commit `1b461b7`)
  - `pyproject.toml` — version 0.7.0
  - `docs/conf.py` — version 0.7.0
  - `CHANGELOG.md` — [0.7.0] Breaking + Added sections, dated 2026-06-22
  - `MIGRATION.md` — incremental-ETL upgrade note added

- **Plan 02 (quality gates):** COMPLETE (commit `02675c2`) — all 4 gates GREEN:
  - pytest coverage: 95.11% (threshold 94%) — PASS
  - interrogate docstring: 100.0% (threshold 95%) — PASS
  - Sphinx -W clean build: no warnings — PASS
  - DeprecationWarning import gate: exit 0 — PASS

### uv lock --check

**Command:** `uv lock --check`

**Exit status:** 0

**Output:**
```
Resolved 43 packages in 1ms
```

**Verdict: PASS** — lockfile is current.

### uv build

**Command:** `uv build`

**Exit status:** 0

**Output:**
```
Building source distribution...
Building wheel from source distribution...
Successfully built dist/pycopg-0.7.0.tar.gz
Successfully built dist/pycopg-0.7.0-py3-none-any.whl
```

### Built Artifacts

| Artifact | Size | Status |
|----------|------|--------|
| `dist/pycopg-0.7.0.tar.gz` | 810K | BUILT |
| `dist/pycopg-0.7.0-py3-none-any.whl` | 82K | BUILT |

Both artifacts verified present in `dist/` on 2026-06-22.

---

## Task 2: Tag + GitHub Release (PENDING — human-gated)

_To be completed by human._

**Instructions for Task 2:**
1. Push main: `git push origin main`
2. Create and push tag: `git tag v0.7.0 && git push origin v0.7.0`
3. Create GitHub Release for tag `v0.7.0` (title `v0.7.0`, paste CHANGELOG `[0.7.0]` notes) and click Publish.
   CLI option: `gh release create v0.7.0 --title v0.7.0 --notes-from-tag`
4. Watch the "Publish to PyPI" workflow run to success (`gh run watch` or Actions tab).
5. Confirm live: https://pypi.org/project/pycopg/0.7.0/

| Field | Value |
|-------|-------|
| Git tag | (pending) |
| GitHub Release URL | (pending) |
| Workflow run URL | (pending) |
| PyPI URL | https://pypi.org/project/pycopg/0.7.0/ |

---

## Task 3: Clean-venv Smoke Test (PENDING — post-publish)

_To be completed after Task 2 (PyPI publish confirmed live)._

**Instructions:**
```bash
python -m venv /tmp/pycopg-070-smoke
/tmp/pycopg-070-smoke/bin/pip install pycopg==0.7.0
/tmp/pycopg-070-smoke/bin/python -c "import pycopg; print(pycopg.__version__)"
```

Expected output: `0.7.0`

| Field | Value |
|-------|-------|
| Install result | (pending) |
| Printed version | (pending) |
| Verdict | (pending) |
