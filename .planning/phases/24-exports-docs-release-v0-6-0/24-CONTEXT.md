# Phase 24: Exports, Docs & Release v0.6.0 - Context

**Gathered:** 2026-06-19
**Status:** Ready for planning

<domain>
## Phase Boundary

The **final phase of the v0.6.0 accessor-reorganization milestone** — a pure **docs + release**
phase. The 5 new accessor classes and the 56 deprecation aliases already SHIPPED in Phases 21–23;
this phase makes the new surface **publicly visible, documented, and released**. No new code logic,
no new accessor methods, no behavior changes — this is wrap-up.

What "done" means (ROADMAP Phase 24 success criteria):
1. `from pycopg import TimescaleAccessor, AdminAccessor, SchemaAccessor, MaintAccessor, BackupAccessor`
   (and async variants) succeeds — all in `__all__`.
2. README lists the `db.X.*` accessor surfaces with their method names; Sphinx/RTD builds cleanly
   (`-W` green) with each accessor documented.
3. CHANGELOG has a `[0.6.0]` entry noting the new accessor paths and the deprecation cycle (removal
   in v0.7.0); MIGRATION.md instructs callers how to update from flat names.
4. `pip install pycopg==0.6.0` installs the release; a clean-venv import smoke test
   (`from pycopg import Database; db = Database.from_env(); print(db.timescale)`) works.

### Already-true state verified during discussion (DO NOT redo — only verify)
- **Exports criterion #1 is ALREADY SATISFIED.** `pycopg/__init__.py` already imports and lists all
  5 accessor classes + async variants in `__all__` (Timescale/Admin/Maint/Backup/Schema, lines added
  incrementally by Phases 21–23). The "wire exports" task collapses to a **verification + smoke-test
  assertion**, not new wiring. Researcher/planner: confirm, don't re-add.
- **56 deprecated flat names per surface** (sync `database.py` + async `async_database.py`, verified
  via `grep -c '@deprecated_alias'` = 56 each): **11 admin + 4 backup + 6 maint + 27 schema +
  2 spatial + 6 timescale = 56**. (Note: `v0.6.0-SCOPE.md` text says "admin 12" but the live count
  is **11** — validate against the live 56, not the SCOPE prose. The cosmetic SCOPE/ROADMAP "~26
  schema" wording also stays informational; Phase 23's D-01 already authoritatively set schema = 27.)
- **Version lives in TWO places** — `pyproject.toml:7` (`version = "0.5.0"`) AND `docs/conf.py:17`
  (`release = '0.5.0'`). Both must bump to `0.6.0`.
- **`MIGRATION.md` already exists** at repo root but documents only **v0.2.0 → v0.3.0** (464 lines).
  It is the file to extend (see D-09), NOT created fresh. (`docs/migrations.md` is the unrelated
  schema-migrations *feature* doc — do not touch it for this.)

</domain>

<decisions>
## Implementation Decisions

> **LOCKED upstream — carried forward, NOT re-litigated here:** D-SCOPE-1..4 (`v0.6.0-SCOPE.md`):
> alias + `DeprecationWarning`, removal in **v0.7.0**; real impl in accessor, flat name is wrapper;
> 5 accessors this milestone; sync/async parity. Version is **0.6.0** (minor bump justified by public-
> API deprecation — D-SCOPE q5). The deprecation mechanics, accessor classes, and 56 aliases are
> DONE (Phases 21–23). The decisions below cover only Phase-24-specific doc/release presentation.

### README presentation
- **D-01:** **Rewrite the in-section examples to the accessor paths AND add a consolidated
  "Namespaces / Accessors" overview section near the top.** The existing README sections that show
  flat methods — **Database Exploration** (`db.list_schemas`/`list_tables`/`size`), **Roles &
  Permissions** (`db.create_role`/`grant`/`revoke`), **Backup & Restore** (`db.pg_dump`/`pg_restore`/
  `copy_to_csv`), and the **TimescaleDB**/**Async Support** examples — are rewritten to
  `db.schema.*` / `db.admin.*` / `db.maint.*` / `db.backup.*` / `db.timescale.*`. Plus one overview
  table mapping each accessor → its method names. README becomes the canonical surface map. The
  transactional core (`execute`, `insert_batch`, `copy_insert`, `session`, DataFrame ops) stays shown
  flat — it is NOT moving (PROJECT.md / SCOPE "reste à plat").

### Sphinx / RTD docs depth
- **D-02:** **Autodoc the 5 new accessor modules AND rewrite the per-topic prose examples.**
  - Add `pycopg.timescale`, `pycopg.admin`, `pycopg.maint`, `pycopg.backup`, `pycopg.schema` (and
    they expose both sync + async classes) to the `automodule` list in `docs/api-autodoc.md` (today
    it autodocs only `database`/`async_database`/`spatial`/`base`/`config`/`utils`/`migrations`/`pool`/
    `exceptions` — the 5 accessor modules are MISSING). This is what satisfies "each accessor
    documented" + keeps `-W` green (undocumented members are the usual `-W` tripwire).
  - Rewrite the flat-method prose examples in `docs/roles-permissions.md`, `docs/backup-restore.md`,
    `docs/timescaledb.md`, and `docs/database.md` to the accessor paths, mirroring the README rewrite
    for consistency.
- **D-03 [vigilance]:** `-W` (warnings-as-errors) is the hard gate for criterion #2. The likely
  failure modes the researcher must pre-empt: (a) a newly-autodoc'd accessor module with a member
  lacking a docstring (interrogate is ≥95 but `-W` is stricter on cross-refs), (b) duplicate-object
  warnings if a method is documented both via `pycopg.database` autodoc (the deprecated stub) and the
  accessor module autodoc, (c) broken `:ref:`/toctree links after edits. Plan must build docs with
  `-W` locally before declaring done. *(Tagged `[vigilance]`: a gate to hold, not a citable feature.)*

### MIGRATION.md structure
- **D-04:** **Prepend a new `## Migration Guide: v0.5.0 → v0.6.0` section at the TOP of the existing
  `MIGRATION.md`** (keep the old v0.2→v0.3 content below, unchanged). The new section contains a
  **COMPLETE flat-name → accessor-path mapping table for all 56 deprecated names**, grouped by
  accessor (timescale 6 / admin 11 / schema 27 / maint 6 / backup 4 / spatial 2), plus: the
  "deprecated now, **removed in v0.7.0**" notice, a short before/after example per accessor, and a
  note on the D-06(P23) PostGIS-guard behavior change (see D-06 below). The table is the actionable
  core — callers should be able to find any flat name and read its replacement.

### CHANGELOG `[0.6.0]` entry
- **D-05:** **Per-accessor granularity, Keep-a-Changelog three-bucket shape** (matches the v0.5.0
  entry style):
  - **Added:** the 5 accessor namespaces (`db.timescale.*` / `db.admin.*` / `db.schema.*` /
    `db.maint.*` / `db.backup.*` and async variants) WITH method counts (6/11/27/6/4), the 5 accessor
    classes exported from the top-level `pycopg` namespace. NOT every method enumerated.
  - **Deprecated:** one entry — all 56 legacy flat names on `db.*`/`async_db.*` emit
    `DeprecationWarning` pointing to the accessor path; **scheduled for removal in v0.7.0**; pointer to
    MIGRATION.md.
  - **Changed:** the **D-06(P23) refinement** — the deprecated `db.create_spatial_index` /
    `db.list_geometry_columns` path now raises `ExtensionNotAvailable` early (via the `db.spatial`
    PostGIS constructor guard) instead of a raw psycopg error when PostGIS is absent. A strictly
    clearer failure on the deprecated path.
  - Move the entry out of `[Unreleased]` into `[0.6.0] - <release date>` on release.

### Release mechanics & smoke test
- **D-06:** **The clean-venv install smoke test is a MANUAL release-checklist step**, not an
  automated CI/test artifact — matching exactly how v0.3.0/v0.4.0/v0.5.0 shipped (three prior PyPI
  releases, same hands-on flow). The plan documents it as a post-`twine upload` verification step:
  in a throwaway venv, `pip install pycopg==0.6.0`, then run
  `python -c "from pycopg import Database; db = Database.from_env(); print(db.timescale)"`. Phase
  completion = the human runs it once and confirms. No new CI workflow to maintain.
- **D-07 [informational]:** Standard release tail (Claude/planner handles by precedent, not a user
  gray area): bump version in BOTH `pyproject.toml:7` and `docs/conf.py:17` → `0.6.0`; build with
  `uv build`; `twine`/publish to PyPI; git tag `v0.6.0`; RTD rebuilds from the tag. Mirror the v0.5.0
  release plan. *(Tagged `[informational]`: mechanical, excluded from the decision-coverage gate.)*

### Claude's Discretion
- Exact wording/layout of the README "Namespaces" overview (table vs. nested list) — pick whatever
  reads cleanly and matches the existing README tone.
- Whether the autodoc additions go in `api-autodoc.md` as more `automodule` blocks or a new grouped
  sub-section — follow the existing `api-autodoc.md` shape.
- Per-plan decomposition (e.g. one docs plan + one release plan, or finer) — planner's call.
- Whether to also add the 5 accessor topics to the `docs/index.md` toctree narrative or rely on the
  existing per-topic pages + autodoc — follow what keeps `-W` green and the nav coherent.
- Exact release date string in CHANGELOG/MIGRATION (stamp at release time).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope & locked decisions
- `.planning/v0.6.0-SCOPE.md` — D-SCOPE-1..4 (LOCKED): alias+`DeprecationWarning`, removal v0.7.0,
  5 accessors, sync/async parity; §"Exports `__init__.py`"; §"Questions ouvertes" q5 (version → 0.6.0).
  ⚠ Its "admin 12" / "schema ~26" counts are approximate — live counts are **admin 11 / schema 27 /
  56 total** (verified this discussion).
- `.planning/PROJECT.md` § "Current Milestone: v0.6.0" — locked decisions (transactional core +
  DataFrame stay flat; spatial-index → `db.spatial.*`).
- `.planning/ROADMAP.md` § "Phase 24" — goal + 4 success criteria + requirement REORG-05.
- `.planning/REQUIREMENTS.md` — REORG-05 acceptance text (the exports/docs/release requirement).

### Prior-phase context (the deprecation cycle this phase documents)
- `.planning/phases/23-schema-accessor-spatial-relocation/23-CONTEXT.md` — **D-06 (PostGIS-guard
  behavior refinement on the deprecated spatial path)** that CHANGELOG/MIGRATION must note (see D-05/
  D-04 here); D-01 (schema = 27, not 26); the `<deferred>` block that explicitly hands Phase 24 its
  scope (README/Sphinx/CHANGELOG/MIGRATION/version/PyPI + the cosmetic "~26"→"27" doc fix).
- `.planning/phases/21-infrastructure-timescale-accessor/21-CONTEXT.md` /
  `.planning/phases/22-admin-maint-backup-accessors/22-CONTEXT.md` — the pattern + the per-accessor
  method inventories the README overview / MIGRATION table must enumerate.

### Files this phase EDITS (release artifacts)
- `pycopg/__init__.py` — `__all__` already lists all 5 accessor classes + async variants (lines under
  the `# Timescale`…`# Schema` comments); criterion #1 is verify-only.
- `pyproject.toml` § `version` (line 7) — bump `0.5.0` → `0.6.0`.
- `docs/conf.py` § `release` (line 17) — bump `0.5.0` → `0.6.0` (second version source).
- `CHANGELOG.md` — has empty `[Unreleased]`; add `[0.6.0]` (D-05).
- `MIGRATION.md` (repo root) — prepend v0.5→v0.6 section with full 56-name table (D-04). NOT
  `docs/migrations.md` (unrelated feature doc).
- `README.md` — rewrite flat examples + add Namespaces overview (D-01). Current flat sections:
  "Database Exploration" (~L78), "Roles & Permissions" (~L156), "Backup & Restore" (~L183),
  "TimescaleDB"/"Async Support" (~L211+).
- `docs/api-autodoc.md` — add `automodule` for `pycopg.{timescale,admin,maint,backup,schema}` (D-02).
- `docs/roles-permissions.md`, `docs/backup-restore.md`, `docs/timescaledb.md`, `docs/database.md` —
  rewrite flat prose examples to accessor paths (D-02).
- `docs/index.md` — toctree (check whether accessor topics need a nav entry; keep `-W` green).

### Source of truth for the accessor method inventories (for README table + MIGRATION table)
- `pycopg/timescale.py`, `pycopg/admin.py`, `pycopg/maint.py`, `pycopg/backup.py`, `pycopg/schema.py`,
  `pycopg/spatial.py` — the canonical method lists per accessor (sync + async classes).
- `pycopg/database.py` / `pycopg/async_database.py` — the 56 `@deprecated_alias("<accessor>.<m>")`
  stubs (`grep '@deprecated_alias'`) are the authoritative flat-name → accessor-path map for the
  MIGRATION table.

### Release precedent to mirror
- `.planning/phases/20-*` (v0.5.0 release plan/summary) and `.planning/phases/15-*` (v0.4.0) — the
  exact build/publish/tag/RTD checklist + the manual clean-venv smoke step (D-06/D-07).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`pycopg/__init__.py` `__all__`** — already complete for all 5 accessors; reuse as the export
  source of truth. No new wiring; assert it in the smoke test.
- **CHANGELOG `[0.5.0]` and `[0.4.0]` entries** — direct templates for the `[0.6.0]` entry shape
  (Added/Deprecated/Changed buckets, per-accessor granularity).
- **Existing `MIGRATION.md` v0.2→v0.3 section** — before/after example style to mirror for the new
  v0.5→v0.6 section (prepended above it).
- **`docs/etl.md` / `docs/spatial.md`** — accessor-style doc pages (they already document `db.etl.*` /
  `db.spatial.*`) — the model for how the rewritten per-topic prose should read.
- **v0.3/v0.4/v0.5 release plans** — reuse the build→publish→tag→RTD→manual-smoke checklist verbatim.

### Established Patterns
- **Two version sources** (`pyproject.toml`, `docs/conf.py`) — both bumped every release; don't miss
  the docs one.
- **Sphinx + MyST Markdown, autodoc via `eval-rst` automodule blocks** in `api-autodoc.md`; `-W`
  warnings-as-error gate on the RTD build.
- **Keep-a-Changelog + SemVer** (CHANGELOG header states this) — `[0.6.0]` follows the format.
- **numpydoc docstrings, `interrogate ≥ 95`** — already satisfied; autodoc just surfaces them.

### Integration Points
- Smoke test asserts the import surface (`__init__.py` `__all__`) — the one place criterion #1/#4 meet.
- `api-autodoc.md` automodule list ↔ the 5 accessor modules — the criterion-#2 "each accessor
  documented" hinge.
- MIGRATION table ↔ the 56 `@deprecated_alias` stubs — must stay in 1:1 sync (regenerate from grep,
  don't hand-transcribe and risk drift).

</code_context>

<specifics>
## Specific Ideas

- **This phase ADDS NO POWER and CHANGES NO LOGIC** — it surfaces, documents, and ships what Phases
  21–23 already built. Any temptation to "improve" an accessor method, add a helper, or refactor while
  writing docs is scope creep → defer.
- **Exports are already done** — the single biggest risk is *re-implementing* what exists. Verify
  `__init__.py`, write the smoke test, move on.
- **The MIGRATION table and README overview must be generated from the live source** (the 56
  `@deprecated_alias` stubs + the accessor class method lists), not hand-typed from the SCOPE doc —
  the SCOPE counts are stale (admin 11≠12, schema 27≠~26).
- **`-W` green is the doc gate** — the realistic failure is a duplicate-object or missing-docstring
  warning when the 5 accessor modules get autodoc'd alongside the deprecated stubs in `database.py`.
  Build docs with `-W` before claiming criterion #2.
- **Manual clean-venv smoke test** is the release-completion proof for criterion #4 — same hands-on
  flow as the three prior PyPI releases.

</specifics>

<deferred>
## Deferred Ideas

- **Alias removal** — v0.7.0 (the deprecation cycle this phase documents culminates there).
- **New helpers** (CRUD ergonomics, advanced TimescaleDB, spatial v2, enriched introspection,
  `db.meta.*` carve-out) — v0.8.0+; this milestone moved existing surface only.
- **Conforming the 2 relocated spatial methods to the pure-builder/`_run` house style** — deferred to
  spatial v2 (v1.0.0) per Phase 23 D-07.
- **Automated install/import smoke test in CI** — explicitly chosen as MANUAL this phase (D-06); could
  be promoted to a gated CI step in a future release-hardening pass if desired.
- **ETL incremental (watermarks)** — separate candidate, independent of this reorganization.

None beyond the above — discussion stayed within phase scope.

</deferred>

---

*Phase: 24-Exports, Docs & Release v0.6.0*
*Context gathered: 2026-06-19*
