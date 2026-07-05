---
phase: 54-release-v1-2-0
reviewed: 2026-07-05T00:00:00Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - CHANGELOG.md
  - docs/spatial.md
  - docs/api-reference.md
  - docs/conf.py
  - pyproject.toml
  - Makefile
  - .github/workflows/tests.yml
  - vulture_whitelist.py
findings:
  critical: 0
  warning: 0
  info: 2
  total: 2
status: clean
---

# Phase 54: Code Review Report

**Reviewed:** 2026-07-05
**Depth:** standard
**Files Reviewed:** 8
**Status:** clean

## Summary

This is the pycopg 1.2.0 release diff (release mechanics only — no new library
logic). Reviewed for release-correctness before the irreversible annotated tag +
OIDC PyPI publish. Every high-priority release invariant was checked against the
actual shipped source, and all held:

1. **CHANGELOG signature fidelity (verified against source):** Every method name,
   parameter, default, and return type in the new `## [1.2.0]` `### Added` block
   matches the shipped source exactly:
   - Spatial (`pycopg/spatial.py`): `union`/`difference`/`intersection` all carry
     the keyword-only `grid_size: float | None = None` (snake_case — NOT
     `gridSize`; confirmed on both sync and async, all overloads + impl + builder
     helpers). `length`, `envelope`, `point_on_surface`, `is_valid`,
     `is_valid_reason`, and `overlaps`/`touches`/`crosses`/`disjoint` signatures
     are byte-accurate against the impl `def`s (lines 4476, 5845, 5945, 4544,
     4606, 3357/3493/3629/3765). Scalar helpers correctly documented as
     `-> list[dict]`; geometry helpers as `-> list[dict] | GeoDataFrame`.
   - CRUD (`pycopg/database.py`): `select_where`/`find` (line 1314/1404),
     `get`/`find_one` (1462/1538), and `insert` (1015) signatures match exactly,
     including `where_sql`/`where_params`, the `offset` presence on
     select_where/find and absence on get/find_one, and `on_conflict=None`.
   - Introspection (`pycopg/schema.py`): `column_exists(table, column, *,
     schema="public") -> bool` (354) and `table_size(name, *, schema="public")
     -> int` (501) match; the "three values bound as `%s`" and
     "`pg_total_relation_size`, no pretty formatting" claims are confirmed against
     `pycopg/queries.py` (COLUMN_EXISTS / TABLE_SIZE).
   - **Sync/async parity** claimed in the intro is real: async twins exist for
     every listed method (`async_database.py` 1150/1240/1298/1374/2262;
     `schema.py` 1311/1411; `spatial.py` async block).
2. **CHANGELOG compare-link footer:** `[Unreleased]` correctly repointed to
   `compare/v1.2.0...HEAD`; new `[1.2.0]: .../compare/v1.1.0...v1.2.0` line added
   in correct descending order above `[1.1.0]`. This exact footer was a real
   defect in a prior release; it is correct here.
3. **Version consistency:** `pyproject.toml` (1.2.0), `docs/conf.py` `release`
   (1.2.0), and `uv.lock` (`name = "pycopg"` / `version = "1.2.0"`) all agree.
   `uv lock --check` passes, so the OIDC publish gate will hold. The `[1.2.0]`
   header date `2026-07-05` equals today.
4. **DOC-14 prose:** `docs/spatial.md:30` and `docs/api-reference.md:273` now read
   `ExtensionNotAvailableError`; no over-correction (the only two prose sites were
   changed; `docs/stability.md` intentionally retains the bare alias names because
   it documents the deprecated aliases themselves; no code sample or import was
   broken).
5. **TOOL-01 wiring:** the Makefile `deadcode` target and the tests.yml
   `Dead-code scan (vulture)` step run the byte-identical command
   `uv run vulture pycopg/ vulture_whitelist.py --min-confidence 80`. `.PHONY`
   includes `deadcode`. The CI step is valid YAML and correctly placed after the
   mypy step. The new `Hashable` whitelist entry is a genuine, load-bearing false
   positive: `vulture pycopg/ --min-confidence 80` (without the whitelist) reports
   `unused import 'Hashable' (90% confidence)` in both `database.py:11` and
   `async_database.py:11`, and `Hashable` is in fact only referenced inside the
   string-literal `cast("dict[Hashable, Any] | None", dtype)` (database.py:2299,
   async_database.py:1941) — it cannot be removed without breaking `mypy --strict`.
   With the whitelist, the full CI command exits 0. Not masking real dead code.

No blocking or quality defects were found in the reviewed release diff. The two
Info items below are genuine repo-state inconsistencies surfaced during
verification but fall outside the reviewed file set and do not affect the package
shipped to PyPI.

## Info

### IN-01: CLAUDE.md version line stale at v1.1.0

**File:** `CLAUDE.md:13` (outside the reviewed file set)
**Issue:** The project instructions header still reads `**pycopg v1.1.0** - ...`
while this release ships `1.2.0` (pyproject/conf.py/uv.lock all agree on 1.2.0).
This is the same "CLAUDE.md stale version" tax noted as recurring across prior
milestones. It does not ship to PyPI and is not part of the release diff, so it
does not gate the tag/publish, but it is a live inconsistency at the release
moment.
**Fix:** Bump the version line to `**pycopg v1.2.0**` (can be folded into the
release commit or a follow-up housekeeping commit).

### IN-02: Committed docs/_build artifacts still show the pre-DOC-14 exception name

**File:** `docs/_build/spatial.html:295`, `docs/_build/api-reference.html:944`,
`docs/_build/_sources/*.md.txt` (generated output, outside the reviewed file set)
**Issue:** Stale Sphinx build output is git-tracked and still renders the bare
`ExtensionNotAvailable` prose that DOC-14 corrected in the `.md` sources. These
are regenerated by Read the Docs on publish and are not the shipped source, so
there is no user-facing impact, but tracking generated `_build/` output invites
exactly this kind of drift.
**Fix:** Out of scope for this release, but consider `git rm -r --cached
docs/_build` and adding it to `.gitignore` so generated HTML is never a source of
apparent inconsistency.

---

_Reviewed: 2026-07-05_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
