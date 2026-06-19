# Phase 24: Exports, Docs & Release v0.6.0 — Pattern Map

**Mapped:** 2026-06-19
**Files analyzed:** 12 files to edit + 1 verify-only
**Analogs found:** 12 / 12

---

## File Classification

| File (edited this phase) | Role | Data Flow | Closest Analog | Match Quality |
|--------------------------|------|-----------|----------------|---------------|
| `docs/api-autodoc.md` | doc-config | N/A | `docs/api-autodoc.md` lines 5–32 (existing `eval-rst` block) | exact — add inside same block |
| `docs/timescaledb.md` | doc-page | N/A | `docs/etl.md` + `docs/spatial.md` (accessor-style prose) | exact |
| `docs/roles-permissions.md` | doc-page | N/A | `docs/etl.md` + `docs/spatial.md` | exact |
| `docs/backup-restore.md` | doc-page | N/A | `docs/etl.md` + `docs/spatial.md` | exact |
| `docs/database.md` | doc-page | N/A | `docs/etl.md` + `docs/spatial.md` | exact |
| `docs/index.md` | doc-config | N/A | existing toctree structure | verify-only likely |
| `README.md` | readme | N/A | `README.md` lines 156–333 (existing flat sections to rewrite) + `docs/etl.md` (Namespaces model) | role-match |
| `CHANGELOG.md` | changelog | N/A | `CHANGELOG.md` lines 10–34 (`[0.5.0]` entry) | exact |
| `MIGRATION.md` | migration-guide | N/A | `MIGRATION.md` lines 1–47 (v0.2→v0.3 before/after style) | exact |
| `pyproject.toml` | release-config | N/A | `pyproject.toml` line 7 (version field) | 1-line edit |
| `docs/conf.py` | release-config | N/A | `docs/conf.py` line 17 (release field) | 1-line edit |
| `uv.lock` | release-artifact | N/A | prior `uv lock` runs | auto-generated |
| `pycopg/__init__.py` | package-init | N/A | — | **VERIFY-ONLY** — no edits |

---

## Pattern Assignments

### `docs/api-autodoc.md` (doc-config)

**Analog:** `docs/api-autodoc.md` — the existing `eval-rst` fence block (lines 5–32)

**Existing block shape** (lines 1–33):
```markdown
# API Reference (Autodoc)

Auto-generated API documentation from pycopg docstrings.

```{eval-rst}
.. automodule:: pycopg.database
   :members:

.. automodule:: pycopg.async_database
   :members:

.. automodule:: pycopg.spatial
   :members:

.. automodule:: pycopg.base
   :members:

.. automodule:: pycopg.config
   :members:

.. automodule:: pycopg.utils
   :members:

.. automodule:: pycopg.migrations
   :members:

.. automodule:: pycopg.pool
   :members:

.. automodule:: pycopg.exceptions
   :members:
```
```

**Pattern to add** — insert these 5 blocks after `.. automodule:: pycopg.spatial` and before `.. automodule:: pycopg.base`, maintaining the same spacing and `:members:` convention:
```rst
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

**Key rules (VERIFIED live):**
- Do NOT add `:noindex:` — accessor and Database stub methods have distinct qualified names, no collision.
- Do NOT add `undoc-members: False` — interrogate reports 100% coverage; all members have docstrings.
- Clear `docs/_build/` cache before the gate run: `rm -rf docs/_build/ && uv run sphinx-build -W --keep-going -b html docs docs/_build/html`

---

### `docs/timescaledb.md`, `docs/roles-permissions.md`, `docs/backup-restore.md`, `docs/database.md` (doc-pages, prose rewrite)

**Analog:** `docs/etl.md` lines 1–48 and `docs/spatial.md` lines 1–30 — the accessor-pattern doc template.

**Template structure to mirror** (from `docs/etl.md` lines 1–48 and `docs/spatial.md` lines 1–30):

1. **Opening paragraph** — `pycopg provides a db.X.* (and async_db.X.*) accessor namespace for…`
2. **`## Access Pattern` section** — sync code block first, async code block second, each annotated with `# Sync:` / `# Async:` comments.
3. **Deprecation notice** (new for v0.6.0, after the Access Pattern section):
   ```markdown
   > **Note:** The flat `db.*` methods (e.g. `db.create_hypertable`) are deprecated as of
   > v0.6.0 and will be removed in v0.7.0. Use `db.timescale.*` instead.
   > See [MIGRATION.md](../MIGRATION.md) for the complete name mapping.
   ```
   (Replace `db.timescale.*` / `db.create_hypertable` with the correct accessor and example for each page.)
4. **Method examples** — replace every `db.method_name(...)` call with `db.accessor.method_name(...)`.

**Sync accessor pattern** (from `docs/spatial.md` lines 15–18):
```python
from pycopg import Database

db = Database.from_env()

# Sync: db.X is initialized lazily on first access
result = db.X.method_name(...)
```

**Async accessor pattern** (from `docs/spatial.md` lines 22–26):
```python
from pycopg import AsyncDatabase

async_db = AsyncDatabase.from_env()

# Async: async_db.X mirrors the sync API with awaited methods
result = await async_db.X.method_name(...)
```

**Per-page accessor substitution map:**

| Doc page | Flat prefix to replace | Accessor path |
|----------|----------------------|---------------|
| `docs/timescaledb.md` | `db.create_hypertable`, `db.enable_compression`, etc. | `db.timescale.method_name` |
| `docs/roles-permissions.md` | `db.create_role`, `db.grant`, `db.revoke`, etc. | `db.admin.method_name` |
| `docs/backup-restore.md` | `db.pg_dump`, `db.pg_restore`, `db.copy_to_csv`, etc. | `db.backup.method_name` |
| `docs/database.md` | `db.list_schemas`, `db.list_tables`, `db.size`, `db.vacuum`, etc. | `db.schema.method_name` / `db.maint.method_name` |

**Existing flat example** (from `docs/roles-permissions.md` lines 10–12, to replace):
```python
# Create a user that can log in
db.create_role("appuser", password="secret123", login=True)
```
**Becomes:**
```python
# Create a user that can log in
db.admin.create_role("appuser", password="secret123", login=True)
```

**Strict scope rule:** Change flat calls to accessor paths and add the deprecation notice. Do NOT add new examples, remove existing valid content, or change method signatures.

---

### `README.md` (readme, two tasks: rewrite + add Namespaces section)

**Analog:** `README.md` lines 156–333 (the 6 flat sections to rewrite) + `docs/etl.md` (the accessor overview model).

**Sections to rewrite** (flat → accessor):

| README section | Approx lines | Flat prefix | Accessor path |
|----------------|-------------|-------------|---------------|
| Database Exploration | ~L78–90 | `db.list_schemas`, `db.table_info`, `db.size`, `db.table_sizes` | `db.schema.*` / `db.maint.*` |
| Roles & Permissions | ~L156–181 | `db.create_role`, `db.grant`, `db.revoke`, `db.alter_role` | `db.admin.*` |
| Backup & Restore | ~L183–210 | `db.pg_dump`, `db.pg_restore`, `db.copy_to_csv`, `db.copy_from_csv` | `db.backup.*` |
| Async Admin Operations | ~L268–285 | `await db.vacuum`, `await db.create_index` | `await db.maint.*` / `await db.schema.*` |
| Async Backup Operations | ~L287–300 | `await db.pg_dump`, etc. | `await db.backup.*` |
| Async Role Management | ~L302–316 | `await db.create_role`, etc. | `await db.admin.*` |
| Async PostGIS & TimescaleDB | ~L318–333 | `await db.create_spatial_index`, `await db.create_hypertable`, etc. | `await db.spatial.*` / `await db.timescale.*` |

**Items that stay flat** (do NOT touch):
- `execute`, `execute_many`, `fetch_one`, `fetch_val`, `insert_batch`, `copy_insert`, `session`, `to_dataframe`, `from_dataframe`, `to_geodataframe`, `from_geodataframe`, connection pooling — the transactional core stays as-is per PROJECT.md.

**Namespaces overview section to ADD** (near the top, after Quick Start, before Core Features):

Pattern: a compact table. Mirror the terse README tone. Example structure:
```markdown
## Accessor Namespaces

pycopg organizes database operations into typed accessor namespaces:

| Accessor | Access | Methods |
|----------|--------|---------|
| `db.schema.*` | DDL + introspection | `list_schemas`, `list_tables`, `table_info`, `create_index`, … (27 methods) |
| `db.admin.*` | Roles & permissions | `create_role`, `grant`, `revoke`, `list_roles`, … (11 methods) |
| `db.maint.*` | Maintenance | `size`, `vacuum`, `analyze`, `explain`, … (6 methods) |
| `db.backup.*` | Backup & restore | `pg_dump`, `pg_restore`, `copy_to_csv`, `copy_from_csv` (4 methods) |
| `db.timescale.*` | TimescaleDB | `create_hypertable`, `enable_compression`, `add_retention_policy`, … (6 methods) |
| `db.spatial.*` | PostGIS helpers | `contains`, `within`, `intersects`, `create_spatial_index`, … (13 methods) |
| `db.etl.*` | ETL pipelines | `run`, `history`, `last_run`, `init` (4 methods) |

All accessors expose an identical async surface on `AsyncDatabase` (e.g. `async_db.admin.*`).
Flat methods are deprecated as of v0.6.0; see [MIGRATION.md](MIGRATION.md).
```

---

### `CHANGELOG.md` (changelog, add `[0.6.0]` entry)

**Analog:** `CHANGELOG.md` lines 10–34 (`[0.5.0]` entry — Added bucket with accessor + method counts + exported classes).

**Existing `[0.5.0]` pattern to mirror** (lines 10–34):
```markdown
## [0.5.0] - 2026-06-15

### Added

- `db.etl.*` / `async_db.etl.*` namespace: ETL pipeline runner (`run`, `history`, `last_run`,
  `dry_run`) with full sync/async parity; both accessors live under a lazy-initialised property
  following the `db.spatial` pattern
- `ETLAccessor`, `AsyncETLAccessor`, `RunResult`, `Pipeline` exported from the `pycopg`
  top-level namespace
```

**Pattern for `[0.6.0]`** — replace `[Unreleased]` section (line 8) with:
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

**Footer update** — replace line 164 and add line after 165 (current `CHANGELOG.md` lines 164–165):
```markdown
[Unreleased]: https://github.com/alkimya/pycopg/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/alkimya/pycopg/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/alkimya/pycopg/compare/v0.4.0...v0.5.0
```
(Replace existing `[Unreleased]` line; insert new `[0.6.0]` line; keep rest unchanged.)

---

### `MIGRATION.md` (migration-guide, prepend v0.5→v0.6 section)

**Analog:** `MIGRATION.md` lines 1–47 (v0.2→v0.3 before/after example style).

**Pattern** (from `MIGRATION.md` lines 1–47):
- H1 title: `# Migration Guide: vX.Y to vZ.W`
- Introductory sentence: "This guide helps you upgrade from pycopg X.Y to Z.W."
- Numbered H2 sub-sections per change
- Before/after `python` code blocks for each change
- Impact note per change

**New section to PREPEND** (before the existing H1 on line 1 — shift existing content to start after the new section):

```markdown
# Migration Guide: v0.5.0 → v0.6.0

This guide helps you upgrade from pycopg 0.5.0 to 0.6.0. Version 0.6.0 introduces
accessor namespaces (`db.timescale.*`, `db.admin.*`, `db.schema.*`, `db.maint.*`,
`db.backup.*`) for all non-transactional operations. The flat names are deprecated and
will be **removed in v0.7.0**.

## Deprecation: Flat Method Names → Accessor Paths

All 56 methods that moved to accessor namespaces now emit `DeprecationWarning` when called
via the old flat name. They continue to work in v0.6.0 — update your code before v0.7.0.

### Before (v0.5.0) / After (v0.6.0)

**Timescale:**
```python
# Before
db.create_hypertable("events", "time")
await async_db.enable_compression("events", segment_by="device_id")

# After
db.timescale.create_hypertable("events", "time")
await async_db.timescale.enable_compression("events", segment_by="device_id")
```

**Admin:**
```python
# Before
db.create_role("appuser", password="secret", login=True)
db.grant("SELECT", "users", "readonly")

# After
db.admin.create_role("appuser", password="secret", login=True)
db.admin.grant("SELECT", "users", "readonly")
```

**Schema:**
```python
# Before
db.list_schemas()
db.create_index("users", "email", unique=True)

# After
db.schema.list_schemas()
db.schema.create_index("users", "email", unique=True)
```

**Maint:**
```python
# Before
db.vacuum("users", analyze=True)
db.size()

# After
db.maint.vacuum("users", analyze=True)
db.maint.size()
```

**Backup:**
```python
# Before
db.pg_dump("backup.dump")
db.copy_to_csv("users", "users.csv")

# After
db.backup.pg_dump("backup.dump")
db.backup.copy_to_csv("users", "users.csv")
```

**Spatial (relocated in v0.6.0):**
```python
# Before
db.create_spatial_index("parcels", "geometry")

# After
db.spatial.create_spatial_index("parcels", "geometry")
# Note: the deprecated flat path now raises ExtensionNotAvailable early when
# PostGIS is absent (stricter than the raw psycopg error it raised before).
```

## Complete Flat-Name → Accessor-Path Table

Generated from live source (`grep '@deprecated_alias' pycopg/database.py`). Do not use
the SCOPE doc counts — use this table.

| Flat name (deprecated) | Accessor path (use this) |
|------------------------|--------------------------|
| `db.add_compression_policy` | `db.timescale.add_compression_policy` |
| `db.add_retention_policy` | `db.timescale.add_retention_policy` |
| `db.create_hypertable` | `db.timescale.create_hypertable` |
| `db.enable_compression` | `db.timescale.enable_compression` |
| `db.hypertable_info` | `db.timescale.hypertable_info` |
| `db.list_hypertables` | `db.timescale.list_hypertables` |
| `db.alter_role` | `db.admin.alter_role` |
| `db.create_role` | `db.admin.create_role` |
| `db.drop_role` | `db.admin.drop_role` |
| `db.grant` | `db.admin.grant` |
| `db.grant_role` | `db.admin.grant_role` |
| `db.list_role_grants` | `db.admin.list_role_grants` |
| `db.list_role_members` | `db.admin.list_role_members` |
| `db.list_roles` | `db.admin.list_roles` |
| `db.revoke` | `db.admin.revoke` |
| `db.revoke_role` | `db.admin.revoke_role` |
| `db.role_exists` | `db.admin.role_exists` |
| `db.copy_from_csv` | `db.backup.copy_from_csv` |
| `db.copy_to_csv` | `db.backup.copy_to_csv` |
| `db.pg_dump` | `db.backup.pg_dump` |
| `db.pg_restore` | `db.backup.pg_restore` |
| `db.analyze` | `db.maint.analyze` |
| `db.explain` | `db.maint.explain` |
| `db.size` | `db.maint.size` |
| `db.table_size` | `db.maint.table_size` |
| `db.table_sizes` | `db.maint.table_sizes` |
| `db.vacuum` | `db.maint.vacuum` |
| `db.add_foreign_key` | `db.schema.add_foreign_key` |
| `db.add_primary_key` | `db.schema.add_primary_key` |
| `db.add_unique_constraint` | `db.schema.add_unique_constraint` |
| `db.columns_with_types` | `db.schema.columns_with_types` |
| `db.create_database` | `db.schema.create_database` |
| `db.create_extension` | `db.schema.create_extension` |
| `db.create_index` | `db.schema.create_index` |
| `db.create_schema` | `db.schema.create_schema` |
| `db.database_exists` | `db.schema.database_exists` |
| `db.drop_database` | `db.schema.drop_database` |
| `db.drop_extension` | `db.schema.drop_extension` |
| `db.drop_index` | `db.schema.drop_index` |
| `db.drop_schema` | `db.schema.drop_schema` |
| `db.drop_table` | `db.schema.drop_table` |
| `db.has_extension` | `db.schema.has_extension` |
| `db.list_columns` | `db.schema.list_columns` |
| `db.list_constraints` | `db.schema.list_constraints` |
| `db.list_databases` | `db.schema.list_databases` |
| `db.list_extensions` | `db.schema.list_extensions` |
| `db.list_indexes` | `db.schema.list_indexes` |
| `db.list_schemas` | `db.schema.list_schemas` |
| `db.list_tables` | `db.schema.list_tables` |
| `db.row_count` | `db.schema.row_count` |
| `db.schema_exists` | `db.schema.schema_exists` |
| `db.table_exists` | `db.schema.table_exists` |
| `db.table_info` | `db.schema.table_info` |
| `db.truncate_table` | `db.schema.truncate_table` |
| `db.create_spatial_index` | `db.spatial.create_spatial_index` |
| `db.list_geometry_columns` | `db.spatial.list_geometry_columns` |

**Total: 56 deprecated names** (timescale 6 / admin 11 / backup 4 / maint 6 / schema 27 / spatial 2).
All `async_db.*` flat names are identical (same 56, same accessor paths with `async_db` prefix).

**Regeneration command** (verify against live source before publishing):
```bash
grep '@deprecated_alias' pycopg/database.py \
  | sed 's/.*@deprecated_alias("\(.*\)")/\1/' \
  | sort
```

---

```

**Existing content** (old `# Migration Guide: v0.2.0 to v0.3.0` section, currently line 1) follows unchanged below the separator.

---

### `pyproject.toml` + `docs/conf.py` (release-config, version bump)

**Pattern:** 1-line edit each.

`pyproject.toml` line 7:
```toml
version = "0.5.0"   # BEFORE
version = "0.6.0"   # AFTER
```

`docs/conf.py` line 17:
```python
release = '0.5.0'   # BEFORE
release = '0.6.0'   # AFTER
```

**Verification after bump:**
```bash
grep -n "0.5.0" pyproject.toml docs/conf.py   # must return 0 hits
grep -n "0.6.0" pyproject.toml docs/conf.py   # must return 2 hits (one each)
```

**Then run:**
```bash
uv lock
uv sync --all-extras --dev
python -c "import pycopg; assert pycopg.__version__ == '0.6.0'; print('OK')"
```

---

### `pycopg/__init__.py` (verify-only, no edits)

**Verification command** (from RESEARCH.md — VERIFIED 2026-06-19):
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

If this passes, criterion #1 is done. Do NOT add any new lines to `__init__.py`.

---

## Shared Patterns

### Release Gate Sequence
**Source:** RESEARCH.md "Release Gate Sequence" / Phase 20 pattern  
**Apply to:** Plan P03 (release plan) — run in this order before tagging:

```bash
# Gate A — Coverage
uv run pytest

# Gate B — Docstrings
uv run interrogate pycopg --fail-under 95 --quiet

# Gate C — Sphinx -W (clear cache first)
rm -rf docs/_build/
uv run sphinx-build -W --keep-going -b html docs docs/_build/html

# Gate D — Build artifacts
uv build
uv lock --check
ls dist/pycopg-0.6.0-py3-none-any.whl dist/pycopg-0.6.0.tar.gz
```

### Release Sequence
**Source:** `.planning/milestones/v0.5.0-phases/20-async-parity-wiring-release/20-03-PLAN.md` (referenced in RESEARCH.md Pattern 5)  
**Apply to:** Plan P03 — after gates pass:

```bash
git add pyproject.toml docs/conf.py uv.lock CHANGELOG.md MIGRATION.md README.md \
        docs/api-autodoc.md docs/timescaledb.md docs/roles-permissions.md \
        docs/backup-restore.md docs/database.md docs/index.md
git commit -m "release: bump version to 0.6.0, update docs and CHANGELOG"
git tag v0.6.0
git push origin main && git push origin v0.6.0
gh release create v0.6.0 --title "v0.6.0 — Accessor reorganization" \
   --notes "<CHANGELOG [0.6.0] body>"
# ↑ triggers .github/workflows/publish.yml → OIDC PyPI publish
```

**Human sign-off required before `gh release create`** (D-06 / RESEARCH Pitfall 6). This step is irreversible on PyPI.

### Manual Smoke Test (post-publish)
**Source:** D-06 decision  
**Apply to:** Final checkpoint after PyPI publish:

```bash
python -m venv /tmp/smoke-0.6.0
/tmp/smoke-0.6.0/bin/pip install pycopg==0.6.0
/tmp/smoke-0.6.0/bin/python -c \
  "from pycopg import Database; db = Database.from_env(); print(db.timescale)"
```

### MIGRATION Table Regeneration Command
**Source:** RESEARCH.md Pattern 4  
**Apply to:** Verification step in P02 (MIGRATION authoring) — cross-check table counts:

```bash
grep '@deprecated_alias' pycopg/database.py \
  | sed 's/.*@deprecated_alias("\(.*\)")/\1/' \
  | sort
# Expected: 56 lines
grep -c '@deprecated_alias' pycopg/database.py   # must print 56
```

---

## No Analog Found

None — every file this phase touches has a direct existing analog in the codebase.

---

## Files That Must NOT Be Touched

| File | Reason |
|------|--------|
| `docs/migrations.md` | Documents the `Migrator` class feature — unrelated to this deprecation guide |
| `pycopg/*.py` (accessor modules, database.py, async_database.py) | No code logic changes this phase |
| `tests/` | No test changes this phase |
| `pycopg/__init__.py` | Verify-only; `__all__` already complete |

---

## Metadata

**Analog search scope:** `docs/`, `CHANGELOG.md`, `MIGRATION.md`, `README.md`, `pyproject.toml`, `docs/conf.py`
**Files scanned:** 13
**Pattern extraction date:** 2026-06-19
**All analog claims VERIFIED by RESEARCH.md live reads (2026-06-19)**
