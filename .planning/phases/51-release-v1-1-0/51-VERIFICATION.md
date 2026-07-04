---
phase: 51-release-v1-1-0
verified: 2026-07-04T13:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 51: Release v1.1.0 Verification Report

**Phase Goal:** pycopg v1.1.0 is published to PyPI with correct, stable-1.x package metadata and documentation, all quality gates green.
**Verified:** 2026-07-04T13:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
| --- | --- | --- | --- |
| 1 | `pyproject.toml` classifier = `5 - Production/Stable`, api-reference Exceptions import block uses only `*Error` names, CLAUDE.md Version = `pycopg v1.1.0` (on disk) | ✓ VERIFIED | `grep -c '5 - Production/Stable' pyproject.toml`=1, `4 - Beta`=0; api-reference lines 518-520 = `ExtensionNotAvailableError`/`TableNotFoundError`/`InvalidIdentifierError`, bare-alias-with-comma imports = 0/0/0; CLAUDE.md:13 `pycopg v1.1.0`, `v0.9.0`=0 |
| 2 | `pip install pycopg==1.1.0` from PyPI yields `__version__ == "1.1.0"` + Phase 48-50 symbols | ✓ VERIFIED | Smoke venv, run from neutral cwd `/tmp`: `__file__` = site-packages wheel, `version 1.1.0`, `from pycopg import Page, TableDescription` ok, `paginate_keyset`=True, prints `smoke ok 1.1.0`. dist-info METADATA `Version: 1.1.0`; no `direct_url.json` + `INSTALLER=pip` → genuine index install, not editable/local |
| 3 | CHANGELOG `## [1.1.0] - 2026-07-04` code-exact: `### Added` + exactly one `### Fixed` (WR-01), no Changed/Removed/Deprecated; every name resolves in `pycopg/` | ✓ VERIFIED | 1 `[1.1.0]` heading, 1 `[Unreleased]`, only `### Added`+`### Fixed`; single Fixed entry = WR-01 guard-order; all 21 documented names resolve to real defs (timescale.py/etl.py dataclass fields 311-314/database.py/schema.py/base.py); compare-link footer present (lines 542-544, WARNING fix landed) |
| 4 | WR-01: `time_bucket` raises origin/offset ValueError before `has_extension()` on sync + async; guard count 3; sync+async regression tests assert `has_extension` not called | ✓ VERIFIED | `grep -c 'origin is not None and offset is not None'`=3 (builder 271, sync 1552, async 2888); guards sit after `_check_into`, before `has_extension()` in both accessors, byte-identical message; tests at 2552/2579/2603 assert `has_extension.assert_not_called()` (async uses `AsyncMock`) |
| 5 | The 5 release gates green on release commit 6e47cf7 | ✓ VERIFIED | No gate-relevant source diff `6e47cf7..HEAD` (only planning docs). Spot-checks live: time_bucket-origin 7 passed; interrogate 100.0% PASSED; mypy `Success: no issues found in 18 source files`. 51-02 recorded cov 96.65%, Sphinx -W clean, -W error::DeprecationWarning clean |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| --- | --- | --- | --- |
| `pyproject.toml` | version 1.1.0 + stable classifier | ✓ VERIFIED | line 7 `version = "1.1.0"`, classifier `5 - Production/Stable` |
| `docs/conf.py` | release 1.1.0 | ✓ VERIFIED | line 17 `release = '1.1.0'` |
| `uv.lock` | local pycopg pin 1.1.0 | ✓ VERIFIED | lines 709-710 `name = "pycopg"` / `version = "1.1.0"` |
| `docs/api-reference.md` | canonical `*Error` import block | ✓ VERIFIED | lines 518-520 `*Error` names only |
| `CLAUDE.md` | `pycopg v1.1.0` (on-disk, gitignored) | ✓ VERIFIED | line 13; correctly not tracked |
| `pycopg/timescale.py` | 3 origin/offset guards | ✓ VERIFIED | lines 271/1552/2888 |
| `tests/test_timescale.py` | sync+async WR-01 regression tests | ✓ VERIFIED | 3 `has_extension.assert_not_called()` assertions |
| `CHANGELOG.md` | code-exact `[1.1.0]` | ✓ VERIFIED | Added + one Fixed, footer links present |
| git tag `v1.1.0` | annotated, on release commit, on origin | ✓ VERIFIED | `cat-file -t`=`tag`; `v1.1.0^{commit}`=6e47cf7; `ls-remote origin` shows `refs/tags/v1.1.0` (ca354b4) |
| PyPI `pycopg 1.1.0` | published distribution | ✓ VERIFIED | wheel installed in smoke venv, METADATA Version 1.1.0 |

### Key Link Verification

| From | To | Via | Status | Details |
| --- | --- | --- | --- | --- |
| tests/test_timescale.py | timescale.py time_bucket | `has_extension.assert_not_called()` | ✓ WIRED | 3 assertions present; async uses AsyncMock |
| api-reference Exceptions block | pycopg/exceptions.py canonical `*Error` | import example | ✓ WIRED | only `*Error` names imported |
| CHANGELOG [1.1.0] Added | pycopg/ shipped defs | every name resolves | ✓ WIRED | all 21 names → real defs |
| annotated tag v1.1.0 | publish.yml OIDC | GitHub Release published event | ✓ WIRED | published wheel present on PyPI (smoke) |
| clean-venv smoke | PyPI wheel | `__version__` + symbol import | ✓ WIRED | `smoke ok 1.1.0` from neutral cwd |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| --- | --- | --- | --- |
| time_bucket origin/offset tests | `pytest tests/test_timescale.py -k "time_bucket and origin"` | 7 passed | ✓ PASS |
| docstring coverage | `interrogate pycopg` | 100.0% PASSED | ✓ PASS |
| type strictness | `mypy pycopg` | 0 errors / 18 files | ✓ PASS |
| published wheel smoke | `smoke-venv python -c ...` (neutral cwd) | `smoke ok 1.1.0` | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| --- | --- | --- | --- | --- |
| DOC-13 | 51-01 | stable-1.x metadata/docs (classifier, `*Error` names, CLAUDE.md version) | ✓ SATISFIED | Truth #1 verified on disk |
| REL-12 | 51-02, 51-03 | v1.1.0 released to PyPI (version sources, CHANGELOG, 5 gates, tag, OIDC publish, smoke) | ✓ SATISFIED | Truths #2/#3/#5 + tag + smoke verified |

No orphaned requirements — REQUIREMENTS.md maps only DOC-13 and REL-12 to Phase 51, both claimed.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| --- | --- | --- | --- | --- |
| pycopg/timescale.py | — | none in changed region | — | no unreferenced TODO/FIXME/XXX |
| docs/api-reference.md | 273 | prose backtick-inline `ExtensionNotAvailable` (non-import) | ℹ️ Info | Not part of the import block; markdown prose is not executed → does not trip `-W error::DeprecationWarning`. Outside criterion #1 scope. Minor doc-staleness only. |

### Human Verification Required

None. The human-gated publish (51-03 Task 2) was already completed by the user; the resulting PyPI artifact is verifiable programmatically (clean-venv smoke against the installed wheel) and passes.

### Gaps Summary

No gaps. All 5 ROADMAP success criteria are independently confirmed against the actual codebase, the installed PyPI wheel, and the git remote:

- Metadata/docs corrections (DOC-13) are present on disk exactly as specified (classifier, `*Error` import block, CLAUDE.md version).
- The v1.1.0 artifact is live on PyPI: a fresh venv install (no `direct_url.json`, `INSTALLER=pip`) reports `__version__ == "1.1.0"` and exposes the Phase 48-50 surface (`Page`, `TableDescription`, `Database.paginate_keyset`).
- The `[1.1.0]` CHANGELOG is code-exact (Added + exactly one Fixed, no Changed/Removed/Deprecated), every documented name resolves to a real definition, and the compare-link footer (the single code-review WARNING) was fixed in the tagged commit 6e47cf7.
- The WR-01 guard is hoisted before `has_extension()` on both sync and async accessors (3 guards total, byte-identical message), with sync+async regression tests that genuinely prove ordering via `has_extension.assert_not_called()`.
- The annotated tag `v1.1.0` points at the release commit 6e47cf7 and is on origin; no gate-relevant source changed since the tag, and targeted gate spot-checks (tests, interrogate 100%, mypy 0/18) are green.

Note (milestone-close bookkeeping, not a phase gap): the REQUIREMENTS.md traceability table still shows DOC-13 and REL-12 as `Pending` / unchecked — a known GSD close-time reconciliation item, not a codebase deficiency.

---

_Verified: 2026-07-04T13:00:00Z_
_Verifier: Claude (gsd-verifier)_
