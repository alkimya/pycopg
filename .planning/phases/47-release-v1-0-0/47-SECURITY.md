---
phase: 47
slug: release-v1-0-0
status: secured
threats_total: 12
threats_closed: 12
threats_open: 0
register_authored_at_plan_time: true
asvs_level: 1
created: 2026-07-02
---

# Phase 47 — Release v1.0.0 — Security Verification

Threat register authored at plan time across `47-01-PLAN.md`, `47-02-PLAN.md`, `47-03-PLAN.md`.
This document verifies each declared mitigation exists in the shipped tree — evidence is
grep/read/`git`/`gh`/PyPI-API output, not SUMMARY.md prose.

Source diff base: `5edf2e2`. Release commit: `df121ed` (`version = "1.0.0"`). Annotated tag
`v1.0.0` exists locally and on origin.

## Trust Boundaries

| Boundary | Description | Origin Plan |
|----------|--------------|-------------|
| Frozen 1.0 public docs -> downstream consumers | Docstrings/reference tables become the SemVer-frozen contract; incorrect names/floors mislead callers | 47-01 |
| Release content -> PyPI consumers | CHANGELOG/MIGRATION/version become the published 1.0 record; drift misleads upgraders | 47-02 |
| pyproject.toml -> uv.lock -> published artifact | Version must be identical across sources or the build/publish is inconsistent | 47-02 |
| Local repo -> origin (tag/commit push) | The tag/commit crossing to origin must match local exactly (no tampered ref) | 47-03 |
| GitHub Release -> PyPI (OIDC) | The publish workflow crosses from CI into PyPI; trust rests on OIDC, not a stored secret | 47-03 |
| PyPI artifact -> clean-venv consumer | The installed wheel must match the tagged/built commit | 47-03 |

## Threat Register

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|--------------|--------|----------|
| T-47-01 | Information (frozen-contract) | mitigate | **CLOSED** | `grep -c "InvalidIdentifierErrorError" pycopg/spatial.py` = `0`; `grep -c "InvalidIdentifierError" pycopg/spatial.py` = `71` (>=22); `pycopg/exceptions.py:39` `class InvalidIdentifierError(PycopgError):` is a real, importable class. |
| T-47-02 | Information (frozen-contract) | mitigate | **CLOSED** | `grep -n "where=" docs/api-reference.md` returns exactly 2 lines: 102 (`count`), 103 (`paginate`) — both CRUD dict-equality, correct. `pycopg/spatial.py:884-885` and `:3421`/`:6246` (sync+async parity) state the two-arg `ST_AsText`/`as_text` form "requires PostGIS >= 3.1"; `docs/spatial.md:318` and `docs/stability.md:139` carry the matching >= 3.1 note. |
| T-47-03 | Tampering (blind find/replace) | accept (guarded) | **CLOSED** (guard held) | `git diff 5edf2e2..HEAD -- pycopg/spatial.py` shows exactly 3 changed line-pairs, all docstring/comment text: the `InvalidIdentifierError` Raises: fix and two PostGIS->3.1 note additions. Grep for `def \|raise \|has_where\|filter=\|where=` in the diff returns **zero** matches — no executable line touched. CRUD rows `count`/`paginate` in api-reference.md remain `where=` (see T-47-02). |
| T-47-04 | Information (frozen-contract) | mitigate | **CLOSED** | Spot-checked live defs against CHANGELOG `[1.0.0]` text: `union` (`pycopg/spatial.py:3855`) signature matches verbatim; `as_mvt` (`:3460`) matches verbatim; `transaction` (`pycopg/database.py:529`, `*, isolation_level=None, savepoint_name=None`) matches; `session` (`:583`, `autocommit=False, *, isolation_level=None`) matches; `savepoint` (`:666`, `*, name=None`) matches; `health` (`:711`, `-> dict[str, Any]`) matches. No drift found in any of the 6 cross-checked signatures. |
| T-47-05 | Tampering (version mismatch) | mitigate | **CLOSED** | `pyproject.toml:7` = `version = "1.0.0"`; `docs/conf.py:17` = `release = '1.0.0'`; `uv.lock` `pycopg` entry = `version = "1.0.0"`; `uv lock --check` exits 0 (resolved 48 packages, no drift). |
| T-47-06 | Repudiation (MIGRATION drift) | mitigate | **CLOSED** | MIGRATION.md documents exactly 5 breaking-change sections (`filter=` spatial, 4 `*Error` renames, kw-only enforcement, timescale `filter=`, mypy-strict-blocking) matching CHANGELOG `[1.0.0]` Changed/Breaking's 5 bullets 1:1 — no asymmetry. The 4 renamed classes + PEP 562 alias dict (`pycopg/exceptions.py:82-85`, `__getattr__` at `:109`) and re-exports in `pycopg/__init__.py:140-143` match the documented before/after table exactly. |
| T-47-07 | Elevation (accidental hardcode) | accept (guarded) | **CLOSED** (guard held) | `git diff 5edf2e2..HEAD -- pycopg/__init__.py` is empty (zero lines changed). `pycopg/__init__.py:47-53` resolves `__version__` via `from importlib.metadata import version; __version__ = version("pycopg")` with a `PackageNotFoundError` fallback — never a hardcoded literal. |
| T-47-08 | Tampering (Supply-chain) | mitigate (existing infra) | **CLOSED** | `.github/workflows/publish.yml`: `on: release: types: [published]` (+ `workflow_dispatch`); build job runs `uv lock --check` then `uv build`; publish job runs under `environment: pypi` with `permissions: id-token: write`, using `pypa/gh-action-pypi-publish@release/v1` — no long-lived token step anywhere. `git diff 5edf2e2..HEAD -- .github/workflows/publish.yml` is empty; `git log --follow` shows the file predates Phase 47 (created `610ed55`, last touched in an unrelated Actions-node-version bump `9c81746`) — genuinely pre-existing infra, not a new/unverified claim. |
| T-47-09 | Tampering (Version/tag) | mitigate | **CLOSED** | `git cat-file -t v1.0.0` = `tag` (annotated, not lightweight). `git show v1.0.0:pyproject.toml` = `version = "1.0.0"`. `git rev-parse v1.0.0` = `5f1a95623ba5b7ff20e5064044cde44e48dd03de`; `git ls-remote --tags origin v1.0.0` returns the identical SHA `5f1a95623ba5b7ff20e5064044cde44e48dd03de` — pushed tag matches local exactly. The tag's target commit `df121ed` carries `version = "1.0.0"`. |
| T-47-10 | Information (Secret exposure) | mitigate (existing infra) | **CLOSED** | `grep -in "password\|pypi_token\|twine\|api-token\|TWINE_\|secrets\." .github/workflows/publish.yml` = no match (exit 1). Repo-wide grep for PyPI token patterns (`pypi-AgEIcHlwaS5vcmc`, `PYPI_API_TOKEN`, `TWINE_PASSWORD`) across the working tree = no match. Publish relies solely on OIDC (`id-token: write` + `environment: pypi`) — nothing to leak. |
| T-47-11 | Spoofing (premature publish) | mitigate | **CLOSED** | `47-03-PLAN.md` Task 3 is `type="checkpoint:human-verify" gate="blocking-human"` with an explicit `<resume-signal>` requiring operator approval; Tasks 1-2 are gate-running/tagging only and Task 2's action text states "Do NOT push the tag or create the GitHub Release in this task." Independently confirmed via `gh release view v1.0.0` (published `2026-07-02T14:26:20Z`) and `gh run list --workflow=publish.yml` showing run `28597685797` (`v1.0.0`, trigger `release`) completed successfully in 40s — the human-gated publish actually fired and succeeded, not merely claimed. |
| T-47-SC | Tampering (Supply-chain) | mitigate (existing infra) | **CLOSED** | `publish.yml` builds via `uv build` in CI from the checked-out release ref (no separate artifact-substitution step). Independently queried `https://pypi.org/pypi/pycopg/1.0.0/json`: `info.version` = `1.0.0`, `urls` contains both `pycopg-1.0.0-py3-none-any.whl` and `pycopg-1.0.0.tar.gz` — confirms the published artifact exists and matches the frozen 1.0 surface (SUMMARY's clean-venv smoke claim independently corroborated, not just trusted). |

## Accepted Risks (accept-guarded, CLOSED)

Both accept-disposition threats are **closed** because their stated guard condition is present
in the shipped diff, per the plan's own acceptance criteria:

- **AR-47-01 / T-47-03** — Risk: a blind `where=`->`filter=` find/replace could silently break
  CRUD-correct `where=` rows or touch executable spatial.py code. Guard: line-range-scoped edits
  only (verified via `git diff`), `grep -c "where=" docs/api-reference.md == 2` holds, and the
  `pycopg/spatial.py` diff contains zero executable-line changes. Accepted with guard present —
  no further action required.
- **AR-47-02 / T-47-07** — Risk: a release-bump task could accidentally hardcode `__version__`
  in `pycopg/__init__.py` instead of leaving it dynamic. Guard: `git diff 5edf2e2..HEAD --
  pycopg/__init__.py` is empty and `__version__` resolves via `importlib.metadata.version`
  with a documented fallback. Accepted with guard present — no further action required.

## Unregistered Flags

None. No `## Threat Flags` sections were present in `47-01-SUMMARY.md`, `47-02-SUMMARY.md`, or
`47-03-SUMMARY.md` — no new attack surface was flagged by the executor during implementation
beyond the 12 registered threats.

## Audit Trail

**Date:** 2026-07-02
**Auditor:** gsd-security-auditor
**Method:** Adversarial verification — every mitigation assumed absent until proven present by
direct grep/read/git/gh/PyPI-API evidence in the shipped tree (commit range `5edf2e2..HEAD`,
release commit `df121ed`, tag `v1.0.0`). No implementation files were modified. Independent
corroboration was performed beyond SUMMARY.md claims for T-47-09 (tag SHA comparison), T-47-11
(live `gh release view` + `gh run list`), and T-47-SC (live PyPI JSON API query) rather than
trusting the executor's self-reported results.

**Result:** 12/12 threats CLOSED (10 mitigate + 2 accept-guarded, both guards verified present).
0 open. 0 unregistered flags. Phase 47 is cleared from a threat-mitigation-verification standpoint.
