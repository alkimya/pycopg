# Phase 25: Alias Removal - Context

**Gathered:** 2026-06-19
**Status:** Ready for planning
**Source:** Orchestrator-captured (no discuss-phase; mechanical phase, 3 design points decided via AskUserQuestion)

<domain>
## Phase Boundary

Permanently remove the v0.6.0 deprecated flat API surface. One deprecation cycle
was already served in v0.6.0 (the 56 flat names have emitted `DeprecationWarning`
since 2026-06-19). The real logic already lives in the accessors, so this is a
deletion phase — no new behavior, no new accessor methods.

**In scope:**
- Delete the 56 `@deprecated_alias` stubs on `Database` (`pycopg/database.py`) and
  the 56 on `AsyncDatabase` (`pycopg/async_database.py`) — 112 total.
- Delete the `pycopg/aliases.py` module (the `deprecated_alias` decorator) — nothing
  imports it after the stubs are gone.
- Delete the 7 `tests/test_*_aliases.py` warn+delegate test files; add one explicit
  `AttributeError` test proving removed flat names no longer resolve on live instances.
- MIGRATION v0.6→v0.7 section + CHANGELOG `[0.7.0]` Breaking entry.
- Close carried-forward WR-01 (IDE signature erasure) and IN-02 (stale flat-name
  references in error messages / comments).

**Out of scope (this phase):**
- Any Incremental ETL work (Phases 26–28).
- The v0.7.0 release itself (Phase 29) — no version bump here.
- Re-litigating the removal vs. a second deprecation cycle (decided: hard removal).
</domain>

<decisions>
## Implementation Decisions

### Removal mechanics
- **D-01**: Delete all 56 `@deprecated_alias` flat stubs from `pycopg/database.py`
  and all 56 from `pycopg/async_database.py` (112 total). Remove the
  `from pycopg.aliases import deprecated_alias` import line from both files. Removed
  names must resolve to a plain `AttributeError` (no stub, no warning, no delegation).
- **D-02 (CRITICAL — corrected by research)**: The alias stubs are **interleaved with
  real methods**, NOT a single contiguous block. In `database.py` (stubs ~L859–L1329) a
  `DATAFRAME OPERATIONS` block of 4 real methods sits at ~L983–L1192. In
  `async_database.py` (stubs ~L732–L1340) there are 3 interleaved real-method sections —
  DATAFRAME (~L940), BATCH OPERATIONS (~L1161), STREAMING (~L1247). The trailing lifecycle
  methods (`close`/`__enter__`/`__exit__`; `close`/`__aenter__`/`__aexit__`) also sit at
  EOF. **Removal MUST target each `@deprecated_alias`-decorated stub by text pattern
  (decorator + its 2–3 line stub body + leading docstring), never by deleting a line range.**
  All interleaved real methods MUST be preserved.

### aliases.py module
- **D-03**: Delete `pycopg/aliases.py` entirely. First verify no module other than
  `database.py`/`async_database.py` imports `deprecated_alias` (grep confirmed: only
  those two import it). The decorator has no post-removal purpose.

### Tests
- **D-04 (corrected by research — 6 files, not 7)**: Delete the **6** warn+delegate test
  files: `tests/test_admin_aliases.py`, `tests/test_maint_aliases.py`,
  `tests/test_schema_aliases.py`, `tests/test_backup_aliases.py`,
  `tests/test_timescale_aliases.py`, `tests/test_spatial_aliases.py`. They test the
  warn+delegate behavior being removed. NOTE: `tests/test_sql_injection.py` is NOT an alias
  test file (it stays — only its stale comment is fixed under D-08); the original "7th file"
  was a miscount.
- **D-05**: Add one new parametrized test (e.g. `tests/test_alias_removal.py`) asserting
  that a representative set of (or all 56) removed flat names raise `AttributeError`
  when accessed on a live `Database` AND `AsyncDatabase` instance. This is the positive
  proof for ALIAS-RM-02.
- **D-06**: `tests/test_parity.py` (`ACCESSOR_PAIRS`, `test_accessor_parity`, the
  public-method-parity and signature checks) MUST stay green and MUST NOT be modified
  to accommodate removal — accessors are the surface being verified, and they are
  unchanged. If a parity test references a flat name, that is a real regression to
  investigate, not a test to relax.

### Carried-forward debt (ALIAS-RM-04)
- **D-07 (WR-01)**: The deprecated stubs used `*args/**kwargs` signatures, erasing IDE
  autocomplete/signatures on this `py.typed` package. Removal resolves WR-01 structurally
  — verify (don't just assert) that the public surface now exposes only accessor-namespaced
  methods with real signatures and no `*args/**kwargs` stub remains on `Database`/`AsyncDatabase`.
- **D-08 (IN-02 — corrected by research: 15 source sites, not 1)**: Fix all stale flat-name
  references in non-test code/comments. Research enumerated 15 error-message sites:
  - PostGIS guard `"...Run db.create_extension('postgis')"` → `db.schema.create_extension('postgis')`
    at THREE sites: `pycopg/spatial.py:966`, `pycopg/database.py:1108`, `pycopg/async_database.py:1119`.
  - TimescaleDB guard `"...Run db.create_extension('timescaledb')"` → `db.schema.create_extension('timescaledb')`
    at TWELVE sites in `pycopg/timescale.py` (~L80, 124, 177, 214, 240, 268, 332, 376, 431, 468, + 2 more).
  - `tests/test_sql_injection.py` (~L38): stale comment "the deprecated flat spatial aliases
    now route through ..." — test bodies already call accessor paths; update/remove the comment.
  - 4 docs source files contain flat-name code examples (factually wrong post-v0.7.0, though
    NOT Sphinx `-W` failures since they're fenced code, not `:meth:` refs) — fix for accuracy.
  - Re-grep `pycopg/` after edits to confirm zero remaining `db.create_extension(` / flat
    `db.<method>(` references in error strings.

### Documentation (ALIAS-RM-03)
- **D-09**: Add a `Migration Guide: v0.6.0 → v0.7.0` section to `MIGRATION.md` with a 1:1
  flat→accessor replacement table covering all 56 names (the v0.6.0 "Complete Flat-Name →
  Accessor-Path Table" already exists at ~L81 and is the source of truth for the mapping —
  reuse it, reframed as "removed in v0.7.0").
- **D-10**: Add CHANGELOG `[0.7.0]` with a `### Breaking` entry stating the 56 flat aliases
  are removed and pointing to the MIGRATION v0.6→v0.7 section. Move the existing `[Unreleased]`
  content if appropriate. (No version bump in code — that is Phase 29.)

### Gates
- **D-11**: `-W error::DeprecationWarning` must be clean after removal — there are no stubs
  left to fire the warning. Coverage ratchet (≥94) must hold. Research confirms the deletion
  is **symmetric** (stub source lines AND their covering tests disappear together) and the
  current baseline is **95.64%** (1.64% headroom), so net coverage should not regress —
  but the plan MUST run the full suite with coverage post-removal to confirm ≥94, not assume it.
  The `*args/**kwargs` count is exactly 56 per file and belongs entirely to alias stubs.

### Claude's Discretion
- Exact new test file name/structure for D-05 (parametrized over a name list vs. introspecting
  `ACCESSOR_PAIRS`).
- Whether to drive the 56-name list in MIGRATION from the existing v0.6.0 table verbatim or
  regenerate it.
- Wave/plan decomposition (source removal vs. tests vs. docs vs. IN-02 cleanup).
- Whether to delete the now-orphaned section-header comments (`# EXTENSIONS`,
  `# POSTGIS SPATIAL OPERATIONS`, etc.) that become empty once their stubs are removed
  (research open question — recommended yes, they are dead headers).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Source — alias stubs to remove
- `pycopg/database.py` — 56 `@deprecated_alias` stubs (region ~L859–L1329, between the
  "DATABASE ADMINISTRATION" comment and the `close`/`__enter__`/`__exit__` lifecycle methods).
- `pycopg/async_database.py` — 56 `@deprecated_alias` stubs (region ~L732–L1338, before the
  `close`/`__aenter__`/`__aexit__` lifecycle methods at EOF).
- `pycopg/aliases.py` — the `deprecated_alias` decorator module to delete.

### Accessors (the surface that STAYS — do not touch)
- `pycopg/timescale.py`, `pycopg/admin.py`, `pycopg/maint.py`, `pycopg/backup.py`,
  `pycopg/schema.py`, `pycopg/spatial.py` — accessor implementations. Unchanged.

### Tests
- `tests/test_parity.py` — `ACCESSOR_PAIRS` registry + parity/signature checks. Must stay green.
- `tests/test_{admin,maint,schema,backup,timescale,spatial}_aliases.py` — delete.
- `tests/test_sql_injection.py` — stale alias comment to fix (~L38); test bodies already accessor-based.

### IN-02 sites
- `pycopg/spatial.py` (~L966) — `_POSTGIS_GUARD_MSG` flat-name error string.

### Docs
- `MIGRATION.md` — existing v0.5→v0.6 deprecation table (~L81) is the 56-name mapping source.
- `CHANGELOG.md` — `[Unreleased]` / `[0.6.0]` structure; add `[0.7.0]` Breaking.

### Requirements / milestone
- `.planning/REQUIREMENTS.md` — ALIAS-RM-01..04 + locked decisions.
- `.planning/ROADMAP.md` — Phase 25 goal + 5 success criteria.
</canonical_refs>

<specifics>
## Specific Ideas

- The 56-name count is verified: `grep -oP 'deprecated_alias\("\K[^"]+' pycopg/database.py | sort -u | wc -l` → 56; same for async. Use this as an acceptance check (0 `deprecated_alias` occurrences in both files after removal).
- Acceptance for ALIAS-RM-01: `grep -c deprecated_alias pycopg/database.py pycopg/async_database.py` → 0 / 0; `pycopg/aliases.py` does not exist.
- Acceptance for ALIAS-RM-02: a removed flat name (e.g. `db.create_hypertable`, `db.create_extension`) raises `AttributeError`; `pytest -W error::DeprecationWarning tests/` is green; `test_parity.py` passes.
</specifics>

<deferred>
## Deferred Ideas

- None — Phase 25 covers its scope. (Incremental ETL is Phases 26–28; release is Phase 29.)
</deferred>

---

*Phase: 25-alias-removal*
*Context gathered: 2026-06-19 via orchestrator capture (3 design points decided)*
