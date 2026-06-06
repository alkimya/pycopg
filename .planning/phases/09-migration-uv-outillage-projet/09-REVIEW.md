---
phase: 09-migration-uv-outillage-projet
reviewed: 2026-06-06T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - .github/workflows/publish.yml
  - .github/workflows/tests.yml
  - .python-version
  - Makefile
  - README.md
  - pyproject.toml
findings:
  critical: 0
  warning: 3
  info: 4
  total: 7
status: issues_found
---

# Phase 9: Code Review Report

**Reviewed:** 2026-06-06
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Reviewed the uv tooling migration: new `tests.yml` CI workflow, migrated
`publish.yml`, new `Makefile`, `.python-version`, README `## Development`
section, and the PEP 735 dependency-group migration in `pyproject.toml`.

The migration is mostly correct. Confirmed positives:

- The `dev` extra was correctly **removed** from
  `[project.optional-dependencies]` and moved to `[dependency-groups].dev`
  (PEP 735). No doc or recipe references the now-removed `[dev]` extra.
- `hatchling` build backend is unchanged.
- Coverage gate `--cov-fail-under=70` is intact in `[tool.pytest.ini_options]`.
- `setup-uv` is pinned to `@v8.2.0` (the version the phase brief expects), not
  the spurious `@v6`.
- OIDC trusted publishing is preserved in `publish.yml` (`environment: pypi`,
  `permissions: id-token: write`, no API token in the publish step).
- `uv.lock` resolves `black`, `ruff`, `tenacity`, etc., so `uv sync --locked`
  will not fail on a stale lock.

No Critical issues. The findings below are supply-chain hardening (mutable
action refs), one functional gap in `publish.yml` (no lock enforcement at build
time), and minor consistency items.

## Warnings

### WR-01: PyPI publish action pinned to a mutable floating branch ref

**File:** `.github/workflows/publish.yml:40`
**Issue:** `pypa/gh-action-pypi-publish@release/v1` resolves a **branch**, not
an immutable tag or SHA. This is the action that performs the OIDC-authenticated
upload to PyPI — the highest-trust step in the pipeline. A compromise or
unintended change on the `release/v1` branch would execute against your PyPI
identity on the next release with no diff in your repo. Supply-chain best
practice for the publishing step is to pin to a full commit SHA (optionally with
a human-readable tag comment).
**Fix:**
```yaml
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@<full-40-char-sha>  # v1.x.y
```
At minimum pin a release tag (`@v1.12.4`); preferably a SHA.

### WR-02: `publish.yml` build job does not enforce the lockfile

**File:** `.github/workflows/publish.yml:14-18`
**Issue:** The build job runs `uv build` directly after `setup-uv`, with no
`uv sync --locked`. `uv build` resolves the build environment independently of
`uv.lock`, so the artifact uploaded to PyPI is **not** guaranteed to be built
under the locked, reviewed dependency set that `tests.yml` validates. This
breaks the build/test reproducibility guarantee the lockfile is supposed to
provide: tests pass against `uv.lock`, but the published wheel could be built
under different build-backend resolution. For a pure-Python hatchling wheel the
practical blast radius is small, hence Warning not Blocker, but the lock should
still gate the release path.
**Fix:** Either build through the locked env or assert the lock is current:
```yaml
      - name: Install uv
        uses: astral-sh/setup-uv@v8.2.0

      - name: Verify lockfile is current
        run: uv lock --check

      - name: Build package
        run: uv build
```

### WR-03: Action tags are mutable; not pinned to SHA

**File:** `.github/workflows/publish.yml:12,15,21,34`; `.github/workflows/tests.yml:33,36`
**Issue:** `actions/checkout@v4`, `actions/upload-artifact@v4`,
`actions/download-artifact@v4`, and `astral-sh/setup-uv@v8.2.0` are pinned to
**mutable** Git tags. A `vN` major tag (and even a patch tag) can be force-moved
by the publisher, so these refs do not pin a verifiable artifact. For a library
that publishes to PyPI, pinning third-party actions to full commit SHAs is the
recommended hardening. `astral-sh/setup-uv@v8.2.0` is the least risky (exact
patch tag) but is still tag-mutable.
**Fix:** Pin each `uses:` to a 40-char commit SHA with a trailing version
comment, e.g.:
```yaml
      - uses: actions/checkout@<sha>  # v4.2.2
```
This is acceptable to defer if the project policy only requires pinning the
publish step (WR-01); document the decision either way.

## Info

### IN-01: `psql` client availability on the runner is an implicit dependency

**File:** `.github/workflows/tests.yml:44-50`
**Issue:** The "Set up test database" step invokes `psql` on the runner host
(the `postgres` service is a container; `psql` runs outside it). This works today
only because `ubuntu-latest` ships the `postgresql-client` package
preinstalled. That is an undocumented assumption — if GitHub ever trims the
runner image, or `ubuntu-latest` rolls to a major that drops the client, this
step fails. Low likelihood, hence Info.
**Fix:** Make the dependency explicit, e.g. add a step
`sudo apt-get install -y postgresql-client` before the DB setup, or run the
`CREATE DATABASE`/`CREATE EXTENSION` via `docker exec` against the service
container.

### IN-02: `setup-uv` Python provisioning vs. `.python-version` pin

**File:** `.github/workflows/tests.yml:36-38`; `.python-version:1`
**Issue:** `setup-uv` is given `python-version: ${{ matrix.python-version }}`,
which correctly overrides the repo's `.python-version` (`3.12`) per matrix leg,
so all three legs (3.11/3.12/3.13) run as intended. No bug. Worth noting only
that `uv run pytest` and `uv sync --locked` will honor the matrix interpreter
because `setup-uv` exports it — verify locally if you later add a tool that
reads `.python-version` directly (it would see `3.12` regardless of the leg).
**Fix:** None required; documented for awareness.

### IN-03: `format` Makefile target runs black then ruff --fix sequentially

**File:** `Makefile:12-14`
**Issue:** `format` runs `uv run black` then `uv run ruff check --fix`. Make
recipes abort on the first failing line by default, so if `black` exits non-zero
the `ruff --fix` line is skipped — acceptable. The two tools can also disagree
on formatting (black formats, ruff's isort/UP rules rewrite), but since `E501`
is ignored and line-length is shared (100) this is unlikely to thrash. No
functional defect. `.PHONY` is correct and recipes use TAB indentation.
**Fix:** None required. Optionally swap order (ruff `--fix` then black) so black
has the last word on formatting.

### IN-04: Package version `0.3.1` is ahead of the documented `v0.2.0`

**File:** `pyproject.toml:7`; `CLAUDE.md`
**Issue:** `pyproject.toml` declares `version = "0.3.1"` (matching `uv.lock`),
while `CLAUDE.md` still states "pycopg v0.2.0". This predates and is outside the
Phase 9 tooling scope (not a file changed by this migration's intent), but the
mismatch is a documentation-drift footgun for contributors following CLAUDE.md.
**Fix:** Out of scope for this phase; update `CLAUDE.md` to the current version
in a docs pass.

---

_Reviewed: 2026-06-06_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
