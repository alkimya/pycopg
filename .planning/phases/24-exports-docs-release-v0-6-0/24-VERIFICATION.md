---
phase: 24-exports-docs-release-v0-6-0
verified: 2026-06-19T13:00:00Z
status: passed
score: 4/4 must-haves verified
overrides_applied: 0
---

# Phase 24: Exports, Docs, Release v0.6.0 — Verification Report

**Phase Goal:** The 5 new accessor classes are publicly importable from `pycopg`, fully documented in README and Sphinx, with a CHANGELOG entry and MIGRATION note for the deprecation cycle, and v0.6.0 is tagged and published to PyPI.
**Verified:** 2026-06-19T13:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                                                           | Status     | Evidence                                                                                                              |
|----|---------------------------------------------------------------------------------------------------------------------------------|------------|-----------------------------------------------------------------------------------------------------------------------|
| 1  | All 10 accessor classes (5 sync + 5 async) import from `pycopg` and are in `__all__`                                           | ✓ VERIFIED | `uv run python -c "from pycopg import TimescaleAccessor, ... AsyncSchemaAccessor; print('OK')"` → OK; all 10 in `__init__.py` `__all__` (lines 64-77)                |
| 2  | README lists the `db.X.*` accessor surfaces with method names; Sphinx `-W` build is green; 5 automodule blocks documented      | ✓ VERIFIED | `grep -c 'Accessor Namespaces' README.md` = 1; `grep -c 'automodule:: pycopg.(timescale|admin|maint|backup|schema)'` = 5; Sphinx build via project venv exits 0 ("La compilation a réussi") |
| 3  | CHANGELOG has `[0.6.0]` entry (Added/Deprecated/Changed); MIGRATION.md has v0.5→v0.6 guide with 56-row table (1:1 with aliases) | ✓ VERIFIED | `grep -c '## \[0.6.0\]' CHANGELOG.md` = 1; `grep -c '@deprecated_alias' pycopg/database.py` = 56; `grep -c '| \`db\.' MIGRATION.md` = 56 |
| 4  | v0.6.0 git-tagged and published to PyPI; `pycopg.__version__` == '0.6.0'                                                       | ✓ VERIFIED | `git tag --list v0.6.0` → v0.6.0; PyPI JSON API returns version `0.6.0`; `uv run python -c "import pycopg; print(pycopg.__version__)"` → 0.6.0 |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact                   | Expected                                              | Status     | Details                                                                                         |
|----------------------------|-------------------------------------------------------|------------|-------------------------------------------------------------------------------------------------|
| `README.md`                | "Accessor Namespaces" overview + rewritten flat sections | ✓ VERIFIED | Contains `Accessor Namespaces` section with table; admin=11, schema=27 live counts; `db.execute`/`db.session`/`db.to_dataframe` remain flat |
| `docs/api-autodoc.md`      | 5 automodule blocks (timescale/admin/maint/backup/schema) | ✓ VERIFIED | Lines 15,18,21,24,27: all 5 accessor modules auto-documented via `.. automodule:: pycopg.<module>` with `:members:` |
| `docs/roles-permissions.md` | db.admin.* accessor paths + v0.6.0→v0.7.0 deprecation notice | ✓ VERIFIED | `grep -c 'db.admin.'` = 39; `grep -c 'v0.7.0'` = 1 |
| `docs/backup-restore.md`   | db.backup.* accessor paths + v0.6.0→v0.7.0 deprecation notice | ✓ VERIFIED | `grep -c 'db.backup.'` = 21; `grep -c 'v0.7.0'` = 1 |
| `docs/timescaledb.md`      | db.timescale.* accessor paths + v0.6.0→v0.7.0 deprecation notice | ✓ VERIFIED | `grep -c 'db.timescale.'` = 43; `grep -c 'v0.7.0'` = 1 |
| `docs/database.md`         | db.schema.*/db.maint.* accessor paths + deprecation notice | ✓ VERIFIED | `grep -c 'db.schema.'` = 13; `grep -c 'db.maint.'` = 43 |
| `CHANGELOG.md`             | `## [0.6.0]` entry with Added/Deprecated/Changed buckets | ✓ VERIFIED | `## [0.6.0] - 2026-06-19` at line 10; three buckets present; Deprecated lists 56 flat names, removal in v0.7.0; Changed notes ExtensionNotAvailable refinement; compare-link footer updated |
| `MIGRATION.md`             | Prepended v0.5→v0.6 guide with 56-row table           | ✓ VERIFIED | File starts with `# Migration Guide: v0.5.0 → v0.6.0`; table has 56 rows matching live `@deprecated_alias` count (56); ExtensionNotAvailable D-06 note present |
| `pyproject.toml`           | `version = "0.6.0"`                                   | ✓ VERIFIED | `grep '^version = "0.6.0"' pyproject.toml` matches |
| `docs/conf.py`             | `release = '0.6.0'`                                   | ✓ VERIFIED | `grep "release = '0.6.0'" docs/conf.py` matches |
| `uv.lock`                  | pinned pycopg 0.6.0                                   | ✓ VERIFIED | `version = "0.6.0"` at line 698 of uv.lock |

### Key Link Verification

| From                                       | To                                            | Via                          | Status     | Details                                                                                                |
|--------------------------------------------|-----------------------------------------------|------------------------------|------------|--------------------------------------------------------------------------------------------------------|
| `docs/api-autodoc.md` automodule blocks    | `pycopg.timescale/admin/maint/backup/schema`  | Sphinx autodoc               | ✓ WIRED    | 5 `.. automodule:: pycopg.<module>` directives; Sphinx build exits 0 — all modules resolved correctly |
| `README.md` Accessor Namespaces table      | live accessor method names                    | Method-name enumeration      | ✓ WIRED    | All 6 accessors listed (schema/admin/maint/backup/timescale/spatial) with live counts and example methods |
| `MIGRATION.md` 56-name table               | `pycopg/database.py` @deprecated_alias stubs  | 1:1 flat-name → accessor-path | ✓ WIRED   | `grep -c '@deprecated_alias' pycopg/database.py` = 56; `grep -c '| \`db\.' MIGRATION.md` = 56 — exact match |
| `CHANGELOG.md` [0.6.0] Changed bucket      | Phase 23 D-06 PostGIS-guard refinement        | ExtensionNotAvailable note   | ✓ WIRED    | Line 41 mentions ExtensionNotAvailable in the Changed bucket; MIGRATION.md line 77 also notes it |
| `pyproject.toml` version                   | `uv.lock` pinned version                      | `uv lock` after bump         | ✓ WIRED    | uv.lock line 698: `version = "0.6.0"` |
| `git tag v0.6.0`                           | `PyPI pycopg==0.6.0`                          | GitHub Release → OIDC publish.yml | ✓ WIRED | Git tag present; PyPI JSON API returns `0.6.0` as latest version |

### Behavioral Spot-Checks

| Behavior                                                 | Command                                                                                           | Result       | Status  |
|----------------------------------------------------------|---------------------------------------------------------------------------------------------------|--------------|---------|
| All 10 accessor classes importable from pycopg            | `uv run python -c "from pycopg import TimescaleAccessor, ... AsyncSchemaAccessor; print('OK')"` | OK           | ✓ PASS  |
| Sphinx -W build exits 0 (no warnings)                    | `venv/bin/sphinx-build -W --keep-going -b html docs docs/_build/html`                            | "La compilation a réussi" (exit 0) | ✓ PASS |
| interrogate docstring coverage ≥95%                      | `uv run interrogate pycopg --fail-under 95 --quiet`                                              | exit 0       | ✓ PASS  |
| `pycopg.__version__` == '0.6.0'                           | `uv run python -c "import pycopg; print(pycopg.__version__)"`                                    | 0.6.0        | ✓ PASS  |
| PyPI latest version is 0.6.0                             | `curl -s https://pypi.org/pypi/pycopg/json \| python3 -c "... print(info['version'])"`          | 0.6.0        | ✓ PASS  |
| git tag v0.6.0 exists                                    | `git tag --list v0.6.0`                                                                           | v0.6.0       | ✓ PASS  |
| @deprecated_alias count == MIGRATION table rows           | `grep -c '@deprecated_alias' pycopg/database.py` vs `grep -c '| \`db\.' MIGRATION.md`           | 56 == 56     | ✓ PASS  |

### Requirements Coverage

| Requirement | Source Plans         | Description                                                                                                     | Status      | Evidence                                                                      |
|-------------|----------------------|-----------------------------------------------------------------------------------------------------------------|-------------|-------------------------------------------------------------------------------|
| REORG-05    | 24-01, 24-02, 24-03  | Accessor classes in `__all__`; README + Sphinx document `db.X.*`; CHANGELOG + MIGRATION note deprecation cycle | ✓ SATISFIED | All four clauses verified: exports in `__all__`, README Namespaces section, Sphinx automodule blocks, CHANGELOG `[0.6.0]` entry, MIGRATION 56-row table |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | No TBD/FIXME/XXX/TODO/PLACEHOLDER markers found in any phase-modified file |

### Human Verification Required

None. All success criteria are programmatically verifiable.

The one deliberate manual check (Task 3 of 24-03: clean-venv install smoke test) was performed by the executor and documented in the SUMMARY with specific output (`<pycopg.timescale.TimescaleAccessor object at 0x7ff617e6aab0>`). PyPI publication is confirmed via the JSON API. RTD rebuild is expected to follow automatically from the tag (same behaviour as v0.5.0, per project memory) — not verifiable programmatically without waiting for the CDN.

### Gaps Summary

No gaps. All four phase success criteria are fully satisfied in the live codebase.

**Notes:**

- `REQUIREMENTS.md` line 34 says ADM-01 has "12 role & permission methods" but names only 11. The live `pycopg/admin.py` has 11 public sync methods. The docs and CHANGELOG correctly state 11. This is a pre-existing REQUIREMENTS.md copy-paste error (not introduced by Phase 24) and does not affect REORG-05 satisfaction.
- The Sphinx build was invoked via `venv/bin/sphinx-build` (the project-local venv) because `sphinx` is not installed in the `uv`-managed `.venv` (no sphinx entry in `[dependency-groups]`). This is a pre-existing environment configuration, not a Phase 24 issue. The build exits 0.
- MIGRATION.md deprecation-notice links in the 4 Sphinx prose pages use absolute GitHub URLs instead of `../MIGRATION.md`, as documented in the 24-01 SUMMARY. This was a deliberate fix (Sphinx cannot resolve root-level files outside the `docs/` source tree with `-W`).

---

_Verified: 2026-06-19T13:00:00Z_
_Verifier: Claude (gsd-verifier)_
