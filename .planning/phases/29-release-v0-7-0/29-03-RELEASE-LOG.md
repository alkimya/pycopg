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

## Task 2: Tag + GitHub Release (COMPLETE)

Completed by human on 2026-06-22.

| Field | Value |
|-------|-------|
| Git tag | `v0.7.0` (created and pushed to origin) |
| `origin/main` HEAD | `0217c7d` (push confirmed) |
| GitHub Release URL | https://github.com/alkimya/pycopg/releases/tag/v0.7.0 |
| Published at | 2026-06-22T12:37:43Z |
| Release title | v0.7.0 |
| Workflow run URL | https://github.com/alkimya/pycopg/actions/runs/27953179349 |
| Workflow conclusion | success (status: completed) |
| PyPI URL | https://pypi.org/project/pycopg/0.7.0/ |

**PyPI files published:**
- `pycopg-0.7.0-py3-none-any.whl`
- `pycopg-0.7.0.tar.gz`

**Verdict: PASS** — tag pushed, GitHub Release published, OIDC workflow succeeded, 0.7.0 live on PyPI.

---

## Task 3: Clean-venv Smoke Test (COMPLETE)

Completed by human on 2026-06-22 after PyPI confirmed live.

**Environment:** Fresh venv at `/tmp/pycopg-070-smoke`

**Install command:**
```bash
/tmp/pycopg-070-smoke/bin/pip install pycopg==0.7.0
```

**Install result:** SUCCESS — `pycopg-0.7.0` installed from live PyPI along with all dependencies:
- psycopg 3.3.4
- pandas 3.0.3
- numpy 2.5.0
- sqlalchemy 2.0.51

**Import + version check:**
```bash
/tmp/pycopg-070-smoke/bin/python -c "import pycopg; print(pycopg.__version__)"
```

**Output:** `IMPORT OK, version: 0.7.0` — exit 0

| Field | Value |
|-------|-------|
| Venv path | `/tmp/pycopg-070-smoke` |
| Install result | SUCCESS (pycopg-0.7.0 + deps from live PyPI) |
| Printed version | `0.7.0` |
| Exit code | 0 |
| Verdict | PASS |

**Verdict: PASS** — clean-venv install from live PyPI imports successfully and reports version 0.7.0.
