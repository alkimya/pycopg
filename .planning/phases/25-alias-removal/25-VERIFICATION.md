---
phase: 25-alias-removal
verified: 2026-06-19T22:00:00Z
status: passed
score: 5/5
overrides_applied: 0
re_verification: false
---

# Phase 25: Alias Removal — Verification Report

**Phase Goal:** The v0.6.0 deprecated flat API surface is permanently removed; callers that haven't migrated get a clear AttributeError; carried-forward WR-01 (IDE signature erasure) and IN-02 (stale error messages) are closed.
**Verified:** 2026-06-19T22:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | The 112 `@deprecated_alias` stubs (56 on `Database` + 56 on `AsyncDatabase`) are gone; the public surface is accessor-only | VERIFIED | `grep -c deprecated_alias pycopg/database.py` → 0; `grep -c deprecated_alias pycopg/async_database.py` → 0 (both were 57 pre-phase). `aliases.py` deleted. No `from pycopg.aliases` import anywhere in `pycopg/`. |
| 2 | Calling any removed flat name on a live `Database` or `AsyncDatabase` instance raises `AttributeError` with no warning, no delegation | VERIFIED | `uv run pytest tests/test_alias_removal.py -q -o addopts=""` → 114 passed (112 parametrized AttributeError cases × 2 classes + 2 WR-01 inspect tests). REMOVED_FLAT_NAMES list confirmed at 56 entries via AST parse. |
| 3 | All per-alias warn+delegate tests are removed; `test_parity` and `ACCESSOR_PAIRS` still pass green; `-W error::DeprecationWarning` gate is clean | VERIFIED | `ls tests/test_*_aliases.py` → 0 files. `uv run pytest tests/test_parity.py` → 24 passed. `uv run pytest -W error::DeprecationWarning tests/test_alias_removal.py tests/test_parity.py tests/test_database.py tests/test_async_database.py` → 420 passed. |
| 4 | MIGRATION.md has a `v0.6→v0.7` section with a 1:1 flat→accessor replacement table covering all 56 names; CHANGELOG `[0.7.0]` has a `Breaking` entry pointing to it | VERIFIED | MIGRATION.md L1 is `# Migration Guide: v0.6.0 → v0.7.0` with 56-row table (timescale 6 / admin 11 / backup 4 / maint 6 / schema 27 / spatial 2). CHANGELOG `## [0.7.0] - TBD` has `### Breaking` entry with `[MIGRATION.md](MIGRATION.md#migration-guide-v060--v070)` link. |
| 5 | IDE autocomplete shows only accessor-namespaced methods (no `*args/**kwargs` stubs); error messages in `ExtensionNotAvailable` reference accessor paths | VERIFIED | `grep -c '*args, **kwargs' pycopg/database.py` → 0; same for `async_database.py` → 0. `grep -c "db\.create_extension(" pycopg/spatial.py` → 0; `grep -c "db\.schema\.create_extension('postgis')" pycopg/spatial.py` → 1. `grep -c "db\.schema\.create_extension('timescaledb')" pycopg/timescale.py` → 12. `grep -c "db\.create_extension(" pycopg/database.py pycopg/async_database.py pycopg/timescale.py pycopg/spatial.py` → all 0. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/database.py` | 0 deprecated_alias stubs, 0 *args/**kwargs, 4 DATAFRAME + 3 lifecycle preserved | VERIFIED | 0 stubs, 0 *args/**kwargs, 4 DATAFRAME methods, 3 lifecycle methods confirmed. ruff clean. |
| `pycopg/async_database.py` | 0 deprecated_alias stubs, 0 *args/**kwargs, DATAFRAME+BATCH+STREAMING+LISTEN-NOTIFY+lifecycle preserved | VERIFIED | 0 stubs, 0 *args/**kwargs, 4 DATAFRAME, 5 BATCH+STREAMING+LISTEN/NOTIFY, 3 lifecycle confirmed. ruff clean. |
| `pycopg/aliases.py` | DELETED | VERIFIED | File does not exist. `! grep -rq deprecated_alias pycopg/` passes. |
| `tests/test_alias_removal.py` | Exists with 56-entry REMOVED_FLAT_NAMES, 112 parametrized AttributeError tests, 2 WR-01 inspect tests | VERIFIED | 150 lines, 56-name list (AST-confirmed), `pytest.raises(AttributeError)` in both parametrized functions, inspect.getmembers loop for WR-01 in both WR-01 tests. 114 passing. |
| `tests/test_parity.py` | Unmodified and green | VERIFIED | File preserved; 24 passing. |
| `tests/test_sql_injection.py` | Stale alias-routing comment removed; test bodies unchanged; suite green | VERIFIED | `grep -c "deprecated flat spatial alias"` → 0. 92 passing (confirmed in plan 04 summary; combined run shows 230 passing across alias_removal + parity + sql_injection). |
| `pycopg/spatial.py` | 0 `db.create_extension(` references; 1 `db.schema.create_extension('postgis')` | VERIFIED | Counts confirmed by grep. |
| `pycopg/timescale.py` | 0 `db.create_extension(` references; 12 `db.schema.create_extension('timescaledb')` | VERIFIED | Counts confirmed by grep. |
| `MIGRATION.md` | v0.6.0 → v0.7.0 section with 56-name removal table | VERIFIED | H1 prepended at top; 56 rows in flat→accessor table. |
| `CHANGELOG.md` | [0.7.0] Breaking entry linking to MIGRATION.md | VERIFIED | `## [0.7.0] - TBD` with `### Breaking` section containing MIGRATION.md link. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `pycopg/database.py` | pycopg.schema accessor | PostGIS error message references `db.schema.create_extension` | VERIFIED | `grep -c "db.schema.create_extension" pycopg/database.py` → 1 |
| `pycopg/async_database.py` | pycopg.schema accessor | PostGIS error message references `db.schema.create_extension` | VERIFIED | `grep -c "db.schema.create_extension('postgis')" pycopg/async_database.py` → 1 |
| `pycopg/timescale.py` | pycopg.schema accessor | 12 ExtensionNotAvailable guards reference `db.schema.create_extension` | VERIFIED | `grep -c "db.schema.create_extension('timescaledb')" pycopg/timescale.py` → 12 |
| `tests/test_alias_removal.py` | pycopg.Database / pycopg.AsyncDatabase | `getattr(db, name)` raises AttributeError under `pytest.raises` | VERIFIED | `pytest.raises(AttributeError)` present in both parametrized test functions; 114 passing |
| `CHANGELOG.md` | `MIGRATION.md` | Breaking entry links to `MIGRATION.md#migration-guide-v060--v070` | VERIFIED | Link present in [0.7.0] Breaking section |

### Data-Flow Trace (Level 4)

Not applicable — this phase produces only deletion/string-literal changes and a proof test file. No new dynamic data rendering paths.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 56 removed flat names raise AttributeError on Database | `uv run pytest tests/test_alias_removal.py -q -o addopts=""` | 114 passed in 0.16s | PASS |
| 24 parity tests green (sync/async surface symmetry) | `uv run pytest tests/test_parity.py -q -o addopts=""` | 24 passed in 3.50s | PASS |
| No DeprecationWarning from alias stubs | `uv run pytest -W error::DeprecationWarning tests/test_alias_removal.py tests/test_parity.py tests/test_database.py tests/test_async_database.py -q -o addopts=""` | 420 passed | PASS |
| Package imports cleanly (no ModuleNotFoundError) | `uv run python -c "import pycopg"` | Exit 0 | PASS |
| Ruff clean on modified source files | `uv run ruff check pycopg/database.py pycopg/async_database.py pycopg/spatial.py pycopg/timescale.py` | All checks passed | PASS |

### Probe Execution

Not applicable — no probe scripts declared or conventional for this phase type (pure source deletion + documentation).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ALIAS-RM-01 | 25-01, 25-02, 25-03 | 56 deprecated_alias stubs removed from both Database and AsyncDatabase; accessor-only surface | SATISFIED | 0 deprecated_alias in both files; aliases.py deleted; no imports remain |
| ALIAS-RM-02 | 25-03 | Removed flat names raise AttributeError; alias warn+delegate tests removed; test_parity green | SATISFIED | 114 test_alias_removal.py passing; 0 alias test files; test_parity 24/24 |
| ALIAS-RM-03 | 25-05 | MIGRATION v0.6→v0.7 section + CHANGELOG [0.7.0] Breaking entry | SATISFIED | Both documents verified in codebase |
| ALIAS-RM-04 | 25-01, 25-02, 25-03, 25-04, 25-05 | WR-01 (IDE signature erasure) + IN-02 (stale error messages) closed | SATISFIED | 0 *args/**kwargs in both database files; 0 flat db.create_extension( in all 4 source files; 12+1 corrected guard strings |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `pycopg/timescale.py` | 10 | Stale `:mod:`pycopg.aliases`` docstring reference — module says "aliases remain as thin deprecated aliases" and links to deleted module | WARNING | Dangling Sphinx cross-reference; misinforms readers about current state. Caught by code review as WR-01 (review). Not a correctness break — module imports cleanly and no code path uses this string. |
| `pycopg/maint.py` | 10 | Same stale docstring pattern as timescale.py | WARNING | Same — 4 additional accessor files (maint.py, schema.py, backup.py, admin.py) have identical stale docstrings. Not in the IN-02 error-string scope but documentation drift. |
| `pycopg/schema.py` | 11 | Same stale docstring pattern | WARNING | See maint.py row above. |
| `pycopg/backup.py` | 11 | Same stale docstring pattern | WARNING | See maint.py row above. |
| `pycopg/admin.py` | 11 | Same stale docstring pattern | WARNING | See maint.py row above. |
| `tests/test_sql_injection.py` | 72-73 | Dead assignments: `db.role_exists = AsyncMock(...)` and `db.has_extension = AsyncMock(...)` on `async_db` fixture — post-alias-removal no production code path reads these instance attributes | WARNING | Maintenance trap caught by code review as WR-02. Tests pass; no correctness break. |

**Classification:** All 6 items are WARNING tier (code review already documented them; no BLOCKER-tier patterns found).

**Debt-marker gate:** No `TBD`, `FIXME`, or `XXX` markers found in any file modified by this phase. Gate: CLEAN.

### Human Verification Required

None. All success criteria are programmatically verifiable. The code review warnings (WR-01 stale docstrings in 5 accessor files, WR-02 dead async_db fixture assignments) are quality/maintainability issues for a follow-up plan — they do not block the phase goal.

### Gaps Summary

No gaps. All 5 roadmap success criteria are verified in the codebase. All 4 requirement IDs (ALIAS-RM-01 through ALIAS-RM-04) are satisfied.

**Notes on code review warnings (non-blocking):**

- **WR-01 (expanded):** The code review flagged `timescale.py:10` for a stale `:mod:`pycopg.aliases`` docstring. Verification confirms this pattern appears in 5 accessor files (timescale.py, maint.py, schema.py, backup.py, admin.py). These are module-level prose docstrings — not IN-02 error strings — and were not in the phase's IN-02 sweep scope. They are documentation drift candidates for a future cleanup plan. The modules import cleanly; no runtime impact.

- **WR-02:** Dead assignments `db.role_exists` and `db.has_extension` in `tests/test_sql_injection.py` async_db fixture (lines 72-73) are unreachable post-removal but tests pass. Maintenance trap for future consideration.

- **Version not bumped:** CHANGELOG `[0.7.0]` date is `TBD` — correct per plan (Phase 29 handles the release). Not a gap.

---

_Verified: 2026-06-19T22:00:00Z_
_Verifier: Claude (gsd-verifier)_
