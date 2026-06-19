# Phase 24: Exports, Docs & Release v0.6.0 - Research

**Researched:** 2026-06-19
**Domain:** Python package documentation (Sphinx/MyST/autodoc), README rewrite, CHANGELOG/MIGRATION authoring, PyPI release mechanics
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Rewrite flat-method README sections to accessor paths AND add consolidated "Namespaces / Accessors" overview near top. Flat core (`execute`, `insert_batch`, `copy_insert`, `session`, DataFrame ops) stays flat.
- **D-02:** Autodoc the 5 new accessor modules in `docs/api-autodoc.md`; rewrite prose examples in `docs/roles-permissions.md`, `docs/backup-restore.md`, `docs/timescaledb.md`, `docs/database.md` to accessor paths.
- **D-03 [vigilance]:** `-W` (warnings-as-errors) is the hard doc gate. Build docs with `-W` before claiming criterion #2 done.
- **D-04:** Prepend `## Migration Guide: v0.5.0 → v0.6.0` at TOP of existing `MIGRATION.md` (keep v0.2→v0.3 content below). New section contains: full 56-name flat→accessor table (grouped by accessor), "removed in v0.7.0" notice, before/after example per accessor, D-06(P23) PostGIS-guard note.
- **D-05:** CHANGELOG `[0.6.0]` entry: Added (5 accessor namespaces with method counts + exports), Deprecated (all 56 flat names → DeprecationWarning, removal v0.7.0), Changed (D-06(P23) PostGIS-guard refinement on deprecated spatial path). Move from `[Unreleased]` to `[0.6.0] - <date>`.
- **D-06:** Clean-venv install smoke test is a MANUAL checkpoint, not CI. Post-`twine upload` step: `pip install pycopg==0.6.0` in throwaway venv, then `python -c "from pycopg import Database; db = Database.from_env(); print(db.timescale)"`.
- **D-07 [informational]:** Version bump in TWO places: `pyproject.toml:7` + `docs/conf.py:17` → `0.6.0`. Build `uv build`. Publish via GitHub Release → OIDC workflow. Tag `v0.6.0`. RTD rebuilds from tag.

### Claude's Discretion

- Exact wording/layout of the README "Namespaces" overview (table vs. nested list).
- Whether autodoc additions go in `api-autodoc.md` as more `automodule` blocks or a new grouped sub-section — follow existing shape.
- Per-plan decomposition (one docs plan + one release plan, or finer) — planner's call.
- Whether to add the 5 accessor topics to `docs/index.md` toctree narrative or rely on existing per-topic pages + autodoc.
- Exact release date string in CHANGELOG/MIGRATION (stamp at release time).

### Deferred Ideas (OUT OF SCOPE)

- Alias removal — v0.7.0.
- New helpers (CRUD, advanced TimescaleDB, spatial v2, enriched introspection, `db.meta.*`) — v0.8.0+.
- Conforming the 2 relocated spatial methods to builder/`_run` style — deferred to spatial v2 (v1.0.0).
- Automated install/import smoke test in CI — explicitly chosen MANUAL this phase (D-06).
- ETL incremental (watermarks) — separate candidate.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REORG-05 | New accessor classes exported in `__init__.py` `__all__`; README + Sphinx document the `db.X.*` surface; CHANGELOG + MIGRATION note the deprecation cycle (removal in v0.7.0) | Exports already complete (VERIFIED below). Sphinx autodoc of 5 modules builds `-W` clean (TESTED). README sections identified for rewrite. CHANGELOG/MIGRATION pattern from prior releases confirmed. |

</phase_requirements>

---

## Summary

Phase 24 is a pure docs-and-release phase. All 5 accessor classes (Timescale/Admin/Maint/Backup/Schema) and the 56 `@deprecated_alias` stubs already shipped in Phases 21–23. This phase has three tracks: (1) **documentation** — rewrite README flat-method examples to accessor paths, add a Namespaces overview, update 4 prose doc pages, add 5 accessor `automodule` blocks to `api-autodoc.md`; (2) **CHANGELOG + MIGRATION** — prepend the v0.5→v0.6 migration guide (56-name table) to `MIGRATION.md` and write the `[0.6.0]` CHANGELOG entry; (3) **release** — version bump in both places, `uv build`, GitHub Release → OIDC PyPI publish, manual smoke test.

The biggest pre-emptive finding: **the `-W` gate is already solved**. A live test confirmed that adding all 5 accessor `automodule` blocks to `api-autodoc.md` produces a clean Sphinx build with zero warnings. There are no duplicate-object warnings because `Database.create_hypertable` and `TimescaleAccessor.create_hypertable` are distinct objects in different modules/classes. There are no missing-docstring warnings because `interrogate` currently reports 100% coverage.

**Primary recommendation:** Plan three sequential plans — P01: README + docs prose rewrite; P02: CHANGELOG + MIGRATION + api-autodoc.md + index.md toctree check; P03: version bump + gates + release (human-checkpoint for PyPI publish).

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `__init__.py` exports verification | Package layer | — | Already complete; verify-only |
| README documentation | Repo root | — | Public surface map for callers |
| Sphinx autodoc additions | docs/ layer | — | RTD build; `api-autodoc.md` |
| Prose doc page rewrites | docs/ layer | — | 4 pages; follow `spatial.md`/`etl.md` model |
| CHANGELOG / MIGRATION authoring | Repo root | — | Release communication artifacts |
| Version bump (pyproject.toml + conf.py) | Package metadata | Docs config | BOTH must be updated |
| uv.lock refresh | Package metadata | CI gate | `uv lock --check` is a CI hard gate |
| PyPI publish | GitHub Actions (OIDC) | Manual smoke | Irreversible; human sign-off required |

---

## Standard Stack

This phase installs **no new packages**. All tooling is already in the dev environment.

### Tooling Already Present

| Tool | Command | Purpose | Version (verified) |
|------|---------|---------|-------------------|
| Sphinx + MyST | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` | Doc build gate | Sphinx 9.1.0 [VERIFIED: live build] |
| interrogate | `uv run interrogate pycopg --fail-under 95 --quiet` | Docstring coverage gate | 100% current [VERIFIED: live run] |
| pytest | `uv run pytest` | Coverage gate (≥94%) | passes [VERIFIED: project CI] |
| uv build | `uv build` | Wheel + sdist production | standard [VERIFIED: pyproject.toml] |
| uv lock | `uv lock` + `uv lock --check` | Lockfile refresh + CI gate | standard [VERIFIED: publish.yml] |
| gh CLI | `gh release create v0.6.0 ...` | GitHub Release creation | triggers OIDC publish [VERIFIED: publish.yml] |

### Release Gate Sequence (exact commands)

```bash
# Gate A — Coverage
uv run pytest                                       # must report >= 94%

# Gate B — Docstrings
uv run interrogate pycopg --fail-under 95 --quiet  # must exit 0

# Gate C — Sphinx -W
uv run sphinx-build -W --keep-going -b html docs docs/_build/html  # must exit 0

# Gate D — Build
uv build                                           # produces dist/pycopg-0.6.0*
uv lock --check                                    # lockfile must be current
```

## Package Legitimacy Audit

> This phase installs NO new external packages. Not applicable.

| Package | Status |
|---------|--------|
| (none) | Phase is docs + release only; no new `pip install` |

---

## Architecture Patterns

### System Architecture Diagram

```
Source of truth                 Outputs produced
────────────────                ──────────────────────────────────────────
pycopg/database.py              README.md (Namespaces overview +
pycopg/async_database.py   ──► rewritten flat sections)
  56 @deprecated_alias stubs
  (grep extracts 56 mappings)   MIGRATION.md (prepend v0.5→v0.6 section;
                                 56-name table; before/after examples)

pycopg/{timescale,admin,        CHANGELOG.md ([0.6.0] entry)
 maint,backup,schema,
 spatial}.py               ──► docs/api-autodoc.md (5 new automodule blocks)
  accessor method lists
                                docs/{roles-permissions,backup-restore,
pycopg/__init__.py   ──verify►  timescaledb,database}.md (prose rewrite)
  __all__ already complete
                                docs/index.md (toctree — verify or add)
pyproject.toml:7 + conf.py:17
  version = "0.5.0"        ──► version = "0.6.0" in BOTH files

                                uv.lock (refreshed after bump)

                                git tag v0.6.0 → GitHub Release
                                  → OIDC publish.yml → PyPI pycopg==0.6.0
```

### Recommended Project Structure

No new files or directories. Edits to existing files only:

```
pycopg/
├── __init__.py          # VERIFY-ONLY — __all__ already complete
pyproject.toml           # EDIT line 7: "0.5.0" → "0.6.0"
docs/
├── conf.py              # EDIT line 17: release = '0.6.0'
├── api-autodoc.md       # ADD 5 automodule blocks
├── index.md             # CHECK toctree — verify/add accessor nav entries
├── roles-permissions.md # REWRITE flat examples → db.admin.*
├── backup-restore.md    # REWRITE flat examples → db.backup.*
├── timescaledb.md       # REWRITE flat examples → db.timescale.*
├── database.md          # REWRITE flat examples → db.schema.*/db.maint.*
README.md                # ADD Namespaces section; REWRITE flat sections
CHANGELOG.md             # ADD [0.6.0] entry (from [Unreleased])
MIGRATION.md             # PREPEND v0.5→v0.6 section (keep v0.2→v0.3 below)
uv.lock                  # REFRESH with uv lock after version bump
```

### Pattern 1: Sphinx automodule addition (MyST eval-rst block)

The existing `docs/api-autodoc.md` uses a single `eval-rst` fence block. Add the 5 new accessor modules inside the same block, following the existing order and style:

```markdown
.. automodule:: pycopg.timescale
   :members:

.. automodule:: pycopg.admin
   :members:

.. automodule:: pycopg.maint
   :members:

.. automodule:: pycopg.backup
   :members:

.. automodule:: pycopg.schema
   :members:
```

**Why no `:noindex:` needed:** `Database.create_hypertable` and `TimescaleAccessor.create_hypertable` are distinct Python objects with distinct qualified names. Sphinx generates separate object index entries for each. No duplicate-object warnings. [VERIFIED: live `-W` build with all 5 modules added produced zero warnings.]

**Why no `undoc-members: False` needed:** `interrogate` currently reports **100%** docstring coverage (`uv run interrogate pycopg --fail-under 95` exits 0 with "actual: 100.0%"). The deprecated stubs in `database.py` have one-line docstrings. The accessor methods have full numpydoc docstrings. No `undoc-members` warning risk. [VERIFIED: live run 2026-06-19.]

### Pattern 2: Accessor prose doc page model

Follow `docs/spatial.md` and `docs/etl.md` exactly — they already show the accessor pattern:
- Open with `## Access Pattern` showing sync then async accessor usage
- Show `db.timescale.create_hypertable(...)` (not `db.create_hypertable(...)`)
- Add a deprecation notice box: "**Note:** The flat `db.*` methods (e.g. `db.create_hypertable`) are deprecated as of v0.6.0 and will be removed in v0.7.0. Use `db.timescale.*` instead."

`docs/etl.md` is the canonical accessor doc template. [VERIFIED: live read 2026-06-19.]

### Pattern 3: CHANGELOG entry shape

Mirror the `[0.5.0]` entry structure in `CHANGELOG.md`. The `[0.5.0]` entry uses Added/Deprecated/Changed buckets with per-feature granularity. [VERIFIED: live read of CHANGELOG.md 2026-06-19.]

```markdown
## [0.6.0] - <RELEASE_DATE>

### Added

- `db.timescale.*` / `async_db.timescale.*` namespace: 6 TimescaleDB methods
  (`create_hypertable`, `enable_compression`, `add_compression_policy`,
  `add_retention_policy`, `list_hypertables`, `hypertable_info`); full sync/async parity
- `db.admin.*` / `async_db.admin.*` namespace: 11 role & permission methods
  (`create_role`, `drop_role`, `role_exists`, `list_roles`, `alter_role`, `grant_role`,
  `revoke_role`, `grant`, `revoke`, `list_role_members`, `list_role_grants`); full sync/async parity
- `db.maint.*` / `async_db.maint.*` namespace: 6 maintenance methods
  (`size`, `table_size`, `table_sizes`, `vacuum`, `analyze`, `explain`); full sync/async parity
- `db.backup.*` / `async_db.backup.*` namespace: 4 dump/restore/CSV methods
  (`pg_dump`, `pg_restore`, `copy_to_csv`, `copy_from_csv`); full sync/async parity
- `db.schema.*` / `async_db.schema.*` namespace: 27 DDL + introspection methods
  (databases 4, extensions 4, schemas 4, tables+columns 8, constraints+indexes 7); full sync/async parity
- `TimescaleAccessor`, `AsyncTimescaleAccessor`, `AdminAccessor`, `AsyncAdminAccessor`,
  `MaintAccessor`, `AsyncMaintAccessor`, `BackupAccessor`, `AsyncBackupAccessor`,
  `SchemaAccessor`, `AsyncSchemaAccessor` exported from the `pycopg` top-level namespace

### Deprecated

- All 56 legacy flat names on `db.*` / `async_db.*` (the methods moved to accessor namespaces)
  now emit `DeprecationWarning` pointing to the new accessor path (e.g.
  `db.create_hypertable` warns: "use db.timescale.create_hypertable"). Scheduled for
  removal in **v0.7.0**. See MIGRATION.md for the complete flat-name → accessor-path table.

### Changed

- Calling the deprecated flat `db.create_spatial_index` or `db.list_geometry_columns`
  now raises `ExtensionNotAvailable` early (via the `db.spatial` PostGIS guard) when
  PostGIS is not installed, rather than a raw psycopg error. A strictly clearer failure
  mode on the deprecated path.
```

Compare-link footer additions (append to existing footer at bottom of CHANGELOG.md):
```
[Unreleased]: https://github.com/alkimya/pycopg/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/alkimya/pycopg/compare/v0.5.0...v0.6.0
```
(Replace existing `[Unreleased]` line; add the `[0.6.0]` line.)

### Pattern 4: MIGRATION table extraction

**Do not hand-type the 56-name table.** Use this grep command to extract the authoritative mapping from the source:

```bash
grep '@deprecated_alias' pycopg/database.py \
  | sed 's/.*@deprecated_alias("\(.*\)")/\1/' \
  | sort
```

This produces the sorted flat-accessor-path list (verified 56 entries, 2026-06-19):

```
admin.alter_role        admin.create_role       admin.drop_role
admin.grant             admin.grant_role        admin.list_role_grants
admin.list_role_members admin.list_roles        admin.revoke
admin.revoke_role       admin.role_exists
backup.copy_from_csv    backup.copy_to_csv      backup.pg_dump
backup.pg_restore
maint.analyze           maint.explain           maint.size
maint.table_size        maint.table_sizes       maint.vacuum
schema.add_foreign_key  schema.add_primary_key  schema.add_unique_constraint
schema.columns_with_types  schema.create_database  schema.create_extension
schema.create_index     schema.create_schema    schema.database_exists
schema.drop_database    schema.drop_extension   schema.drop_index
schema.drop_schema      schema.drop_table       schema.has_extension
schema.list_columns     schema.list_constraints schema.list_databases
schema.list_extensions  schema.list_indexes     schema.list_schemas
schema.list_tables      schema.row_count        schema.schema_exists
schema.table_exists     schema.table_info       schema.truncate_table
spatial.create_spatial_index   spatial.list_geometry_columns
timescale.add_compression_policy  timescale.add_retention_policy
timescale.create_hypertable       timescale.enable_compression
timescale.hypertable_info         timescale.list_hypertables
```

**Counts confirmed** (live grep 2026-06-19):
- timescale: 6 | admin: 11 | schema: 27 | maint: 6 | backup: 4 | spatial: 2 = **56 total**
- Sync and async `@deprecated_alias` lists are **IDENTICAL** (verified via diff).

### Pattern 5: Release sequence (exact mirror of v0.5.0 plan 20-03-PLAN.md)

```bash
# Step 1: Bump version in BOTH places
# pyproject.toml line 7: version = "0.5.0" → "0.6.0"
# docs/conf.py line 17: release = '0.5.0' → '0.6.0'

# Step 2: Refresh lockfile
uv lock
uv sync --all-extras --dev

# Step 3: Verify runtime version
python -c "import pycopg; assert pycopg.__version__ == '0.6.0'; print('OK')"

# Step 4: Run all three release gates
uv run pytest                                       # coverage >= 94%
uv run interrogate pycopg --fail-under 95 --quiet  # docstrings >= 95%
uv run sphinx-build -W --keep-going -b html docs docs/_build/html  # -W clean

# Step 5: Build artifacts (pre-release verification)
uv build
uv lock --check
ls dist/pycopg-0.6.0-py3-none-any.whl dist/pycopg-0.6.0.tar.gz

# Step 6: Commit + tag + GitHub Release [HUMAN SIGN-OFF REQUIRED]
git add pyproject.toml docs/conf.py uv.lock CHANGELOG.md MIGRATION.md README.md docs/api-autodoc.md ...
git commit -m "release: bump version to 0.6.0, update docs and CHANGELOG"
git tag v0.6.0
git push origin main && git push origin v0.6.0
gh release create v0.6.0 --title "v0.6.0 — Accessor reorganization" --notes "<CHANGELOG [0.6.0] body>"
# ↑ This triggers .github/workflows/publish.yml → OIDC PyPI publish

# Step 7: Manual smoke test (post-publish)
python -m venv /tmp/smoke-0.6.0 && /tmp/smoke-0.6.0/bin/pip install pycopg==0.6.0
/tmp/smoke-0.6.0/bin/python -c "from pycopg import Database; db = Database.from_env(); print(db.timescale)"
```

### Anti-Patterns to Avoid

- **Re-implementing exports:** `pycopg/__init__.py` `__all__` is **already complete** for all 5 accessor classes + async variants + exceptions. Do NOT add any new export lines. Task = verify-only + smoke-test assertion.
- **Hand-typing the 56-name table:** Use the grep extraction command (Pattern 4) to regenerate from live source. Manual transcription against the (stale) SCOPE doc will produce errors.
- **Using SCOPE.md counts:** The SCOPE says "admin 12" and "schema ~26". Live counts are **admin 11** and **schema 27**. Always use the live grep counts.
- **Editing `pycopg/__version__`:** `pycopg/__init__.py` resolves `__version__` from `importlib.metadata.version("pycopg")` — it auto-updates after `uv lock && uv sync`. Do NOT hardcode a version string there.
- **Forgetting the lockfile:** `uv lock` after the version bump is mandatory. The CI `publish.yml` runs `uv lock --check` as a hard gate before build.
- **Adding `:noindex:` or `undoc-members: False`:** Not needed. The `-W` build with all 5 accessor modules passes cleanly without these options. [VERIFIED: live test.]
- **Touching `docs/migrations.md`:** That file documents the schema-migrations *feature* (SQL migration runner). The deprecation migration guide goes in `MIGRATION.md` (repo root), not `docs/migrations.md`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 56-name mapping table | Manual count from SCOPE.md | `grep '@deprecated_alias' pycopg/database.py` | SCOPE counts are stale (admin 12 → 11, schema ~26 → 27) |
| Sphinx duplicate-object protection | `:noindex:` / `:no-index:` directives | Nothing — not needed | Accessor methods and stub methods have different qualified names; no collision |
| pycopg version at runtime | Hardcode in `__init__.py` | `importlib.metadata.version("pycopg")` + `uv sync` | Already wired; only pyproject.toml needs editing |
| PyPI publishing | Manual `twine upload` | GitHub Release → OIDC publish.yml | Existing workflow; OIDC trusted, no token management |
| `__all__` additions | New export lines | Verify existing lines | Already complete for all 5 accessor classes |

**Key insight:** This phase has zero new code logic. Every "implementation" task is a verification + prose edit. The only dangerous trap is implementing something that already exists.

---

## Critical Verification: Exports Already Complete

**Finding:** `pycopg/__init__.py` already imports and lists all 5 accessor classes + async variants in `__all__`. [VERIFIED: live read 2026-06-19.]

Exact `__all__` sections present:
```python
# TimescaleDB
"TimescaleAccessor",
"AsyncTimescaleAccessor",
# Admin
"AdminAccessor",
"AsyncAdminAccessor",
# Maint
"MaintAccessor",
"AsyncMaintAccessor",
# Backup
"BackupAccessor",
"AsyncBackupAccessor",
# Schema
"SchemaAccessor",
"AsyncSchemaAccessor",
```

**Verification command for executor:**
```bash
python -c "
from pycopg import (TimescaleAccessor, AsyncTimescaleAccessor,
                    AdminAccessor, AsyncAdminAccessor,
                    MaintAccessor, AsyncMaintAccessor,
                    BackupAccessor, AsyncBackupAccessor,
                    SchemaAccessor, AsyncSchemaAccessor)
print('All 10 accessor classes importable - OK')
"
```

---

## Critical Verification: Sphinx -W Gate Already Passes with 5 Modules Added

**Finding:** A live test was run: `docs/api-autodoc.md` was temporarily edited to include all 5 new accessor `automodule` blocks, then `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` was executed. **Result: "La compilation a réussi." (Build succeeded.) Zero warnings.** [VERIFIED: live test 2026-06-19.]

**Why no duplicate-object warnings:**
- `Database.create_hypertable` (in `pycopg.database`) and `TimescaleAccessor.create_hypertable` (in `pycopg.timescale`) are different Python objects with different fully-qualified names. Sphinx indexes them under `pycopg.database.Database.create_hypertable` and `pycopg.timescale.TimescaleAccessor.create_hypertable` respectively. No collision.

**Why no missing-docstring warnings:**
- The deprecated stubs in `database.py` each carry a one-line docstring (`"""Deprecated: use ``db.timescale.create_hypertable`` instead."""`). These are valid docstrings; autodoc renders them. No `undoc-members` warning.
- Accessor modules have full numpydoc docstrings. `interrogate` reports 100%. [VERIFIED: live run.]

**D-03 gate remains the hard gate for the release criterion,** but the executor can be confident the edit is straightforward: add 5 `automodule` blocks, run the build command, expect green.

---

## Live Method Inventories (for README overview + MIGRATION table)

These counts and method lists are extracted from live source, not SCOPE/ROADMAP prose.

### Timescale (6 methods) — `db.timescale.*`
`create_hypertable`, `enable_compression`, `add_compression_policy`, `add_retention_policy`, `list_hypertables`, `hypertable_info`

### Admin (11 methods) — `db.admin.*`
`create_role`, `drop_role`, `role_exists`, `list_roles`, `alter_role`, `grant_role`, `revoke_role`, `grant`, `revoke`, `list_role_members`, `list_role_grants`

### Maint (6 methods) — `db.maint.*`
`size`, `table_size`, `table_sizes`, `vacuum`, `analyze`, `explain`

### Backup (4 methods) — `db.backup.*`
`pg_dump`, `pg_restore`, `copy_to_csv`, `copy_from_csv`

### Schema (27 methods) — `db.schema.*`
Databases (4): `create_database`, `drop_database`, `database_exists`, `list_databases`
Extensions (4): `create_extension`, `drop_extension`, `list_extensions`, `has_extension`
Schemas (4): `create_schema`, `drop_schema`, `list_schemas`, `schema_exists`
Tables/Columns (8): `list_tables`, `table_exists`, `list_columns`, `columns_with_types`, `drop_table`, `truncate_table`, `table_info`, `row_count`
Constraints/Indexes (7): `add_primary_key`, `add_foreign_key`, `add_unique_constraint`, `create_index`, `drop_index`, `list_indexes`, `list_constraints`

### Spatial (2 relocated methods) — `db.spatial.*` (already existed; 2 methods added in Phase 23)
`create_spatial_index`, `list_geometry_columns`
(Plus the original 11 spatial helpers that were never flat: `contains`, `within`, `intersects`, `dwithin`, `distance`, `nearest`, `area`, `perimeter`, `centroid`, `buffer`, `transform`)

**Total deprecated aliases:** 56 (timescale 6 + admin 11 + schema 27 + maint 6 + backup 4 + spatial 2). [VERIFIED: `grep -c '@deprecated_alias' pycopg/database.py` = 56; async identical.]

---

## File-by-File Edit Map

### Files requiring edits (with what to change)

| File | Change | Scope |
|------|--------|-------|
| `pyproject.toml:7` | `version = "0.5.0"` → `"0.6.0"` | 1 line |
| `docs/conf.py:17` | `release = '0.5.0'` → `'0.6.0'` | 1 line |
| `uv.lock` | `uv lock` after version bump | auto-generated |
| `CHANGELOG.md` | Add `[0.6.0]` section + update compare-link footer | ~30 lines added |
| `MIGRATION.md` | Prepend v0.5→v0.6 section at TOP | ~100+ lines prepended |
| `README.md` | Add Namespaces overview + rewrite 6 flat sections | substantial rewrite |
| `docs/api-autodoc.md` | Add 5 `automodule` blocks inside the existing eval-rst fence | ~15 lines added |
| `docs/index.md` | Verify/add toctree entries for accessor pages | check only, likely 0 changes |
| `docs/roles-permissions.md` | Rewrite `db.create_role` etc. → `db.admin.*` | 342 lines total |
| `docs/backup-restore.md` | Rewrite `db.pg_dump` etc. → `db.backup.*` | 388 lines total |
| `docs/timescaledb.md` | Rewrite `db.create_hypertable` etc. → `db.timescale.*` | 377 lines total |
| `docs/database.md` | Rewrite schema/maint flat examples → `db.schema.*`/`db.maint.*` | 405 lines total |

### Files that are verify-only (no edits expected)

| File | Verify Command | Expected Result |
|------|----------------|-----------------|
| `pycopg/__init__.py` | `python -c "from pycopg import TimescaleAccessor, SchemaAccessor; print('OK')"` | Passes — already complete |

### Files that must NOT be touched

| File | Reason |
|------|--------|
| `docs/migrations.md` | Schema-migration *feature* docs — unrelated to this migration guide |
| `pycopg/*.py` (accessor modules) | No code logic changes this phase |
| `tests/` | No test changes this phase (REORG-05 is docs-only) |

---

## Common Pitfalls

### Pitfall 1: Forgetting the Second Version Source

**What goes wrong:** `pyproject.toml` is bumped to `0.6.0` but `docs/conf.py:17` still says `'0.5.0'`. The Sphinx build shows `0.5.0` in the HTML header and RTD. The CI publish is correct (it reads `pyproject.toml`), but the docs advertise the wrong version.
**Why it happens:** Two version sources is non-obvious. CLAUDE.md says `0.5.0` and points to `pyproject.toml`; `conf.py` is easy to miss.
**How to avoid:** Explicit task: "bump version in BOTH `pyproject.toml:7` AND `docs/conf.py:17`." Verify both with `grep`.
**Warning signs:** `grep -r "0.5.0" pyproject.toml docs/conf.py` returns any hits after the bump.

### Pitfall 2: Forgetting `uv lock` After the Version Bump

**What goes wrong:** `pyproject.toml` is updated to `0.6.0` but `uv.lock` still pins `0.5.0`. The CI `publish.yml` runs `uv lock --check` as a hard gate and fails. The release workflow is blocked.
**Why it happens:** `uv.lock` is auto-managed; the developer forgets to run `uv lock` manually after the bump.
**How to avoid:** Immediately after bumping `pyproject.toml`, run `uv lock && uv sync --all-extras --dev`. Verify with `uv lock --check`.
**Warning signs:** `grep -A2 'name = "pycopg"' uv.lock` shows `0.5.0` after the bump.

### Pitfall 3: Sphinx Build Against Stale `_build` Cache

**What goes wrong:** A stale `docs/_build/html` from a previous build (e.g. the v0.5.0 RTD cache) contains pre-existing metadata that makes the incremental build skip new module pages. A `-W` run appears to succeed but the new accessor pages are not rendered.
**Why it happens:** Sphinx's pickled environment (`_build/.doctrees/`) is incremental; adding entirely new `automodule` directives to an unchanged `api-autodoc.md` may not trigger full re-processing.
**How to avoid:** Before the gate run, clear the build cache: `rm -rf docs/_build/ && uv run sphinx-build -W --keep-going -b html docs docs/_build/html`.
**Warning signs:** After adding the 5 accessor `automodule` blocks, the build says "0 added, 1 modified, 0 removed" — it should show more if processing the new modules for the first time.

### Pitfall 4: Hand-Transcribing the 56-Name MIGRATION Table from SCOPE.md

**What goes wrong:** The executor copies method lists from `v0.6.0-SCOPE.md` or `REQUIREMENTS.md` into `MIGRATION.md`. Those documents say "admin: 12" (not 11) and "schema: ~26" (not 27). The MIGRATION table is wrong.
**Why it happens:** SCOPE was written before Phase 23 finalized the counts.
**How to avoid:** Always generate from live source: `grep '@deprecated_alias' pycopg/database.py | sed 's/.*@deprecated_alias("\(.*\)")/\1/' | sort`. This is the authoritative list.
**Warning signs:** The MIGRATION table lists 12 admin methods or 26 schema methods — cross-check counts.

### Pitfall 5: Editing `docs/migrations.md` Instead of `MIGRATION.md`

**What goes wrong:** The executor finds `docs/migrations.md` in the filesystem and edits it for the v0.5→v0.6 migration guide. That file documents the SQL-file migration runner feature (`Migrator` class). The actual `MIGRATION.md` at repo root is unchanged.
**Why it happens:** Both filenames contain "migration"; `docs/migrations.md` is closer to "documentation."
**How to avoid:** The target file is `MIGRATION.md` at the **repo root** (464 lines, documents only v0.2→v0.3 currently). Path: `/home/loc/workspace/pycopg/MIGRATION.md`.
**Warning signs:** After editing, the file being changed discusses `Migrator` class or SQL migration files.

### Pitfall 6: Publishing to PyPI Without Human Sign-Off

**What goes wrong:** A task marked `autonomous: true` runs the full release sequence including `gh release create`, triggering the OIDC publish workflow. A version published to PyPI cannot be re-uploaded (even if the tag is deleted).
**Why it happens:** An executor treating the release as just another task.
**How to avoid:** The publish task MUST be `checkpoint:human-verify` type. Per D-06 precedent from Phase 20: "Do NOT auto-publish to PyPI."

### Pitfall 7: Scope Creep During Doc Rewrite

**What goes wrong:** While rewriting `docs/timescaledb.md`, the executor notices the `create_spatial_index` async example and decides to "fix" it, or adds a new example showing a v0.7.0 helper, or improves the `pg_dump` signature documentation.
**Why it happens:** Documentation work invites editorial judgment.
**How to avoid:** Strict rule: change flat method calls to accessor paths; add the deprecation notice; keep the rest identical. Do NOT add new examples, remove existing valid content, or document methods outside the 5 accessors.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `db.create_hypertable(...)` flat call | `db.timescale.create_hypertable(...)` accessor | v0.6.0 (Phase 21) | Deprecation warning; removal in v0.7.0 |
| `db.create_role(...)` flat call | `db.admin.create_role(...)` accessor | v0.6.0 (Phase 22) | Deprecation warning; removal in v0.7.0 |
| `db.list_schemas(...)` flat call | `db.schema.list_schemas()` accessor | v0.6.0 (Phase 23) | Deprecation warning; removal in v0.7.0 |
| `db.vacuum(...)` flat call | `db.maint.vacuum(...)` accessor | v0.6.0 (Phase 22) | Deprecation warning; removal in v0.7.0 |
| `db.pg_dump(...)` flat call | `db.backup.pg_dump(...)` accessor | v0.6.0 (Phase 22) | Deprecation warning; removal in v0.7.0 |
| `db.create_spatial_index(...)` flat call (no PostGIS guard) | `db.spatial.create_spatial_index(...)` (with PostGIS guard) | v0.6.0 (Phase 23) | Deprecated flat path now raises `ExtensionNotAvailable` early — strictly clearer failure (D-06 P23) |

**Deprecated/outdated (MUST document in CHANGELOG + MIGRATION):**
- All 56 flat `db.*` / `async_db.*` method names for moved methods: deprecated in v0.6.0, removal scheduled v0.7.0.

---

## Validation Architecture

> `workflow.nyquist_validation` is absent from `.planning/config.json` — treated as enabled.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (uv run pytest) |
| Config file | `pyproject.toml [tool.pytest.ini_options]` — `addopts = "-v --cov=pycopg --cov-report=term-missing --cov-report=html --cov-fail-under=94"` |
| Quick run command | `uv run pytest tests/ -x -q -o addopts=""` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REORG-05 (exports) | `from pycopg import TimescaleAccessor, ...` succeeds | smoke import | `python -c "from pycopg import TimescaleAccessor, AdminAccessor, SchemaAccessor, MaintAccessor, BackupAccessor; print('OK')"` | Inline — no new test file needed |
| REORG-05 (Sphinx) | `sphinx-build -W --keep-going` exits 0 | doc gate | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` | N/A — build command |
| REORG-05 (interrogate) | docstring coverage >= 95% | doc gate | `uv run interrogate pycopg --fail-under 95 --quiet` | N/A — interrogate command |
| REORG-05 (coverage) | test coverage >= 94% | coverage gate | `uv run pytest` | N/A — full suite |

### Phase 24 does NOT add new test files

This phase is docs + release only. No new `tests/test_*.py` files. No new assertions on accessor functionality (that was Phases 21–23). The "tests" for this phase are the three release gates (coverage/interrogate/Sphinx-W) plus the manual smoke test.

### Sampling Rate

- **Per task commit:** `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` (fast enough as a sanity gate)
- **Per wave merge:** Full three-gate sequence (pytest + interrogate + sphinx-W)
- **Phase gate:** All three gates green + manual smoke test before `/gsd-verify-work`

### Wave 0 Gaps

None — existing test infrastructure covers all phase requirements. This phase adds no new code.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `uv` | Build, lock, sync, run | ✓ | (in project dev env) | — |
| `sphinx-build` | Sphinx gate | ✓ | Sphinx 9.1.0 [VERIFIED: live build] | — |
| `interrogate` | Docstring gate | ✓ | Reports 100% [VERIFIED: live run] | — |
| `pytest` | Coverage gate | ✓ | in dev env | — |
| `uv build` | Build wheel/sdist | ✓ | standard | — |
| `gh` CLI | GitHub Release creation | [ASSUMED] | — | Manual GitHub UI |
| PostgreSQL | Manual smoke test | ✓ | (local test DB exists per project memory) | — |

**Missing dependencies with no fallback:** None blocking.

**`gh` CLI note:** The v0.5.0 release plan (20-03-PLAN.md) used `gh release create`. If `gh` is unavailable, the GitHub Release can be created via the GitHub web UI. [ASSUMED: gh available, consistent with prior releases.]

---

## Security Domain

> `security_enforcement` is not explicitly `false` in config.json — including this section.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | no | — |
| V6 Cryptography | no | — |
| Supply chain (publish) | yes | OIDC trusted publishing via `pypa/gh-action-pypi-publish@release/v1` — no long-lived PyPI token |

### Known Threat Patterns for release phases

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unauthorized PyPI publish | Tampering / Repudiation | Human-checkpoint gate on `gh release create`; OIDC workflow requires GitHub environment approval |
| Version confusion (wrong version published) | Tampering | Verify `uv lock --check` + `python -c "import pycopg; assert pycopg.__version__ == '0.6.0'"` before tagging |
| Supply chain from new packages | Tampering | Not applicable — no new packages installed this phase |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `gh` CLI is available on the executor machine for `gh release create` | Environment Availability | Would need to use GitHub web UI instead — low risk, easy fallback |
| A2 | RTD rebuilds automatically from the `v0.6.0` tag after publish (as it did for v0.5.0) | Release Sequence | Would need to trigger RTD rebuild manually — low risk |

**All other claims in this research were verified by live tool execution or direct file reads in this session.**

---

## Open Questions

1. **`docs/index.md` toctree: does it need new entries for the accessor namespaces?**
   - What we know: `docs/index.md` currently lists `timescaledb`, `roles-permissions`, `backup-restore` in the toctree (the per-topic prose pages). Those pages document the accessor surface after the D-02 rewrite. No new toctree entry is strictly required — the accessor content is in existing pages.
   - What's unclear: Whether an explicit "Accessors" toctree section or a dedicated `accessor-overview.md` page would improve navigation (Claude's Discretion per CONTEXT.md).
   - Recommendation: Check after rewriting the 4 prose pages whether the nav is coherent. If the README "Namespaces" overview is comprehensive enough, skip a new toctree page.

2. **README "Namespaces" overview: table vs nested list?**
   - What we know: CONTEXT.md leaves this to Claude's discretion. `docs/etl.md` uses prose + code blocks; `docs/spatial.md` uses a parameter table.
   - Recommendation: A compact table listing each accessor, its method count, and 2–3 representative methods is the most scannable format for a README. Follow the existing README tone (terse, code-first).

---

## Sources

### Primary (HIGH confidence)

- `pycopg/__init__.py` — live read confirming all 10 accessor classes in `__all__` [VERIFIED 2026-06-19]
- `pycopg/database.py` + `pycopg/async_database.py` — live `grep -c '@deprecated_alias'` = 56 each; diff confirmed identical [VERIFIED 2026-06-19]
- Live Sphinx build with 5 accessor modules added — `sphinx-build -W --keep-going` exits 0 [VERIFIED 2026-06-19]
- `uv run interrogate pycopg --fail-under 95` — exits 0, actual: 100.0% [VERIFIED 2026-06-19]
- `.planning/milestones/v0.5.0-phases/20-async-parity-wiring-release/20-03-PLAN.md` — verbatim release playbook [VERIFIED: read 2026-06-19]
- `.github/workflows/publish.yml` — OIDC publish flow, `uv lock --check` gate [VERIFIED: read 2026-06-19]
- `CHANGELOG.md` — live read of [0.5.0] entry structure and compare-link footer [VERIFIED 2026-06-19]
- `MIGRATION.md` — 464 lines, v0.2→v0.3 only, confirmed prepend target [VERIFIED 2026-06-19]
- `docs/conf.py:17` — `release = '0.5.0'` [VERIFIED: live read 2026-06-19]
- `pyproject.toml:7` — `version = "0.5.0"` [VERIFIED: live read 2026-06-19]
- `docs/api-autodoc.md` — current state: 9 modules, missing 5 accessor modules + etl + aliases [VERIFIED: live read 2026-06-19]
- `docs/spatial.md`, `docs/etl.md` — accessor doc page templates [VERIFIED: live read 2026-06-19]

### Secondary (MEDIUM confidence)

- Phase 23 CONTEXT.md D-06 — PostGIS-guard behavior change on deprecated spatial path; must note in CHANGELOG/MIGRATION

### Tertiary (LOW confidence — no unverified claims used)

None. All factual claims are from live verification.

---

## Metadata

**Confidence breakdown:**
- Exports status: HIGH — live grep + import verification
- Sphinx -W gate: HIGH — live build test with all 5 accessor modules
- Release mechanics: HIGH — read from prior phase plan (20-03-PLAN.md) + publish.yml
- Method inventories: HIGH — extracted from live source via grep
- Prose docs scope: HIGH — read actual files + line counts

**Research date:** 2026-06-19
**Valid until:** 2026-07-19 (stable Python packaging ecosystem; no fast-moving dependencies)
