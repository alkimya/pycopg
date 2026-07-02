---
phase: 47-release-v1-0-0
reviewed: 2026-07-02T14:35:22Z
depth: standard
files_reviewed: 8
files_reviewed_list:
  - pycopg/spatial.py
  - docs/api-reference.md
  - docs/spatial.md
  - docs/stability.md
  - docs/conf.py
  - CHANGELOG.md
  - MIGRATION.md
  - pyproject.toml
findings:
  critical: 0
  warning: 2
  info: 1
  total: 3
status: issues_found
---

# Phase 47: Code Review Report

**Reviewed:** 2026-07-02T14:35:22Z
**Depth:** standard
**Files Reviewed:** 8
**Status:** issues_found

## Summary

Phase 47 is a low-risk release phase: `pycopg/spatial.py` changes are confirmed
docstring-only (22 `InvalidIdentifierErrorError` -> `InvalidIdentifierError` typo fixes,
verified against the live `pycopg.exceptions.InvalidIdentifierError` class; plus two
`ST_AsText` PostGIS >= 3.1 notes), and `docs/api-reference.md` / `docs/spatial.md` gained
correct, verified `where=` -> `filter=` corrections limited to the 13 spatial/timescale
rows the plan scoped. All CHANGELOG method signatures for the 12 new Spatial v2 helpers
were cross-checked against the live implementation in `pycopg/spatial.py` (`union`,
`difference`, `intersection`, `simplify`, `convex_hull`, `make_valid`,
`collect_geometries`, `union_aggregate`, `extent`, `as_geojson`, `as_text`, `as_mvt`) —
every parameter, default, and keyword-only boundary matches exactly. Version strings in
`pyproject.toml` and `docs/conf.py` are both `1.0.0` and consistent with the CHANGELOG's
`[1.0.0] - 2026-07-02` header. No source (executable) lines changed in `spatial.py`, and
no SQL-injection surface was touched.

Two real, verifiable defects remain in the reviewed files that are directly relevant to
this release's stated goal ("frozen public API surface... class names matching real
exceptions", "version consistency across sources"): the `docs/api-reference.md`
Exceptions section still documents the pre-1.0 deprecated exception names as the
canonical import surface (not fixed by this phase, but squarely the kind of doc drift
this phase exists to catch), and `pyproject.toml`'s trove classifier still reads
`Development Status :: 4 - Beta` despite the version bump to a "first stable major
release" in the same commit.

## Warnings

### WR-01: `docs/api-reference.md` Exceptions section documents deprecated names as canonical, causing new 1.0 users to trigger `DeprecationWarning` on the first copy-pasted example

**File:** `docs/api-reference.md:191`, `docs/api-reference.md:432-440`

**Issue:** Two places in the reviewed file still present the pre-1.0 exception names as
the primary/only API:

- Line 191: "the accessor is initialized lazily on first access and raises
  `ExtensionNotAvailable` if PostGIS is not installed" — the real class raised is
  `ExtensionNotAvailableError` (renamed in Phase 41, FREEZE-02). `ExtensionNotAvailable`
  is now only a deprecated `PEP 562` alias.
- Lines 432-440, the `## Exceptions` code block:
  ```python
  from pycopg import (
      PycopgError,        # Base exception
      ConnectionError,    # Connection failed
      ConfigurationError, # Bad config
      ExtensionNotAvailable,  # Missing extension
      TableNotFound,      # Table doesn't exist
      InvalidIdentifier,  # SQL injection attempt
      MigrationError,     # Migration failed
  )
  ```
  This is the canonical "how do I import exceptions" reference for the whole library and
  it lists three of the four Phase-41-renamed classes (`ExtensionNotAvailable`,
  `TableNotFound`, `InvalidIdentifier`) using the deprecated names with no mention that
  `*Error` suffixed versions exist or are preferred. `DatabaseExistsError`/
  `DatabaseExists` isn't listed here at all either way.

Verified empirically — importing exactly as documented emits three `DeprecationWarning`s:
```
$ python3 -c "from pycopg import ExtensionNotAvailable, TableNotFound, InvalidIdentifier"
DeprecationWarning: ExtensionNotAvailable is deprecated and will be removed in pycopg 2.0. Use ExtensionNotAvailableError instead.
DeprecationWarning: TableNotFound is deprecated and will be removed in pycopg 2.0. Use TableNotFoundError instead.
DeprecationWarning: InvalidIdentifier is deprecated and will be removed in pycopg 2.0. Use InvalidIdentifierError instead.
```
Because this project's own `pyproject.toml` sets
`filterwarnings = ["error::DeprecationWarning"]` for pytest, any consumer who copies this
exact code block into a test suite configured the same way will get an immediate failure
on a freshly-released 1.0.0 — the opposite of what a "stable, frozen" release doc should
demonstrate. This is not introduced by the Phase 47 diff, but it is precisely the class of
defect ("docstring class names matching real exceptions") this release phase was
chartered to close, and the file is in the reviewed set.

**Fix:**
```python
from pycopg import (
    PycopgError,             # Base exception
    ConnectionError,         # Connection failed
    ConfigurationError,      # Bad config
    ExtensionNotAvailableError,  # Missing extension
    TableNotFoundError,      # Table doesn't exist
    InvalidIdentifierError,  # SQL injection attempt
    DatabaseExistsError,     # Database already exists
    MigrationError,          # Migration failed
)
```
And on line 191: `raises \`ExtensionNotAvailableError\` if PostGIS is not installed`.

### WR-02: `pyproject.toml` trove classifier still says "4 - Beta" on the same commit that bumps the version to 1.0.0 and calls it the "first stable major release"

**File:** `pyproject.toml:25`

**Issue:** The diff for this phase touches exactly one line of `pyproject.toml` — the
`version = "0.10.1"` -> `version = "1.0.0"` bump. The
`classifiers = [...]` list a few lines below is untouched and still reads:
```
"Development Status :: 4 - Beta",
```
`CHANGELOG.md:12` (also part of this phase's diff) explicitly describes 1.0.0 as
"First stable major release". PyPI renders trove classifiers on the package's project
page and uses them for search/filtering — shipping a "Beta" classifier alongside a 1.0.0
stable release is a real, user-visible metadata inconsistency introduced by this exact
diff (the version line changed; the adjacent, semantically-linked classifier line did
not).

**Fix:**
```toml
classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Intended Audience :: Developers",
    ...
]
```

## Info

### IN-01: `CLAUDE.md` "Version" line still reads v0.9.0, now three releases stale (0.10.0, 0.10.1, 1.0.0 all shipped since)

**File:** `CLAUDE.md:13` (not in the reviewed file list, but directly load-bearing for the
version-consistency check this phase's scope note asks for)

**Issue:** `CLAUDE.md` line 13 reads `**pycopg v0.9.0** - High-level PostgreSQL/...`. This
was previously flagged and marked resolved in v0.9.0 per project memory, then drifted
again across 0.10.0/0.10.1/1.0.0. It is outside the explicit `files:` scope for this
review, so it is not a blocker for this phase's diff, but since Phase 47 is specifically
the "version consistency across sources" phase it is worth a one-line fix while the topic
is hot, to avoid yet another recurrence of this specific documented recurring-debt pattern
(see project memory: "CLAUDE.md 'Version' line stale-since-v0.6.0").

**Fix:** Update `CLAUDE.md:13` to `**pycopg v1.0.0** - ...` in a follow-up commit (or fold
into a future housekeeping pass — not release-blocking).

---

_Reviewed: 2026-07-02T14:35:22Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
