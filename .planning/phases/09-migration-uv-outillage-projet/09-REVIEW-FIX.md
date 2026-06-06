---
phase: 09-migration-uv-outillage-projet
fixed_at: 2026-06-06T00:00:00Z
review_path: .planning/phases/09-migration-uv-outillage-projet/09-REVIEW.md
iteration: 1
findings_in_scope: 1
fixed: 1
skipped: 6
status: all_fixed
---

# Phase 09: Code Review Fix Report

**Fixed at:** 2026-06-06
**Source review:** .planning/phases/09-migration-uv-outillage-projet/09-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 1 (WR-02 only, per scope constraint)
- Fixed: 1
- Skipped: 6 (out of scope — deferred or info-only)

## Fixed Issues

### WR-02: `publish.yml` build job does not enforce the lockfile

**Files modified:** `.github/workflows/publish.yml`
**Commit:** eba2b0f
**Applied fix:** Inserted a `Verify lockfile is current` step running `uv lock --check`
in the `build` job, positioned after the `astral-sh/setup-uv@v8.2.0` step and before
the `uv build` step. This gates the release path on the committed `uv.lock` being
current, so the published wheel is built under the same locked dependency set that
`tests.yml` validates.

**Verification:**
- `uv lock --check` exits 0 locally — the committed `uv.lock` IS current.
- YAML parses; `build` job step order is checkout → Install uv → Verify lockfile is
  current → Build package → Upload artifacts.
- `setup-uv@v8.2.0` and the `uv build` step are unchanged.
- The `publish` job is byte-for-byte unchanged: `environment: pypi`,
  `permissions: id-token: write`, `pypa/gh-action-pypi-publish@release/v1`.

## Skipped Issues

### WR-01: PyPI publish action pinned to a mutable floating branch ref

**File:** `.github/workflows/publish.yml:40`
**Reason:** deferred to Phase 15 per locked decision D-15
**Original issue:** `pypa/gh-action-pypi-publish@release/v1` resolves a branch, not an
immutable tag or SHA. SHA-pinning of GitHub Actions is explicitly out of Phase 9 scope.

### WR-03: Action tags are mutable; not pinned to SHA

**File:** `.github/workflows/publish.yml:12,15,21,34`; `.github/workflows/tests.yml:33,36`
**Reason:** deferred to Phase 15 per locked decision D-15
**Original issue:** `actions/checkout@v4`, `actions/upload-artifact@v4`,
`actions/download-artifact@v4`, and `astral-sh/setup-uv@v8.2.0` are pinned to mutable
Git tags rather than commit SHAs. SHA-pinning is Phase 15 scope.

### IN-01: `psql` client availability on the runner is an implicit dependency

**File:** `.github/workflows/tests.yml:44-50`
**Reason:** info-only, no action required
**Original issue:** The test DB setup step relies on `psql` being preinstalled on
`ubuntu-latest`, an undocumented assumption.

### IN-02: `setup-uv` Python provisioning vs. `.python-version` pin

**File:** `.github/workflows/tests.yml:36-38`; `.python-version:1`
**Reason:** info-only, no action required
**Original issue:** Documented-for-awareness note; reviewer confirmed no bug — the
matrix interpreter correctly overrides `.python-version`.

### IN-03: `format` Makefile target runs black then ruff --fix sequentially

**File:** `Makefile:12-14`
**Reason:** info-only, no action required
**Original issue:** Optional ordering preference; reviewer confirmed no functional defect.

### IN-04: Package version `0.3.1` is ahead of the documented `v0.2.0`

**File:** `pyproject.toml:7`; `CLAUDE.md`
**Reason:** info-only, no action required
**Original issue:** Documentation drift between `pyproject.toml` version and `CLAUDE.md`;
reviewer marked out of scope for this phase.

---

_Fixed: 2026-06-06_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
