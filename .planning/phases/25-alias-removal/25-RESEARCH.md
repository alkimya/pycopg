# Phase 25: Alias Removal — Research

**Researched:** 2026-06-19
**Domain:** Python source deletion — flat-alias stubs, decorator module, test cleanup, doc update
**Confidence:** HIGH — all claims verified against live source

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01**: Delete all 56 `@deprecated_alias` stubs from `pycopg/database.py` and all 56 from `pycopg/async_database.py` (112 total). Remove the `from pycopg.aliases import deprecated_alias` import line from both files. Removed names must resolve to a plain `AttributeError` (no stub, no warning, no delegation).
- **D-02**: The stubs are NOT a single trailing block — in `database.py` the alias region sits between the "DATABASE ADMINISTRATION" section (~L855) and the lifecycle methods `close`/`__enter__`/`__exit__` at EOF. Removal must preserve those trailing lifecycle methods. Same care for `async_database.py` (`close`/`__aenter__`/`__aexit__` at EOF). Delete the stubs, not "everything after line N".
- **D-03**: Delete `pycopg/aliases.py` entirely. First verify no module other than `database.py`/`async_database.py` imports `deprecated_alias` (grep confirmed: only those two import it). The decorator has no post-removal purpose.
- **D-04**: Delete the 6 `tests/test_*_aliases.py` files: `test_admin_aliases.py`, `test_maint_aliases.py`, `test_schema_aliases.py`, `test_backup_aliases.py`, `test_timescale_aliases.py`, `test_spatial_aliases.py`. (Note: CONTEXT.md says "7 files" — live filesystem has exactly 6; see Pitfall #1.)
- **D-05**: Add one new parametrized test (e.g. `tests/test_alias_removal.py`) asserting that a representative set of (or all 56) removed flat names raise `AttributeError` when accessed on a live `Database` AND `AsyncDatabase` instance. This is the positive proof for ALIAS-RM-02.
- **D-06**: `tests/test_parity.py` (`ACCESSOR_PAIRS`, `test_accessor_parity`, the public-method-parity and signature checks) MUST stay green and MUST NOT be modified to accommodate removal.
- **D-07 (WR-01)**: Removal resolves WR-01 structurally — verify (don't just assert) that the public surface now exposes only accessor-namespaced methods with real signatures and no `*args/**kwargs` stub remains on `Database`/`AsyncDatabase`.
- **D-08 (IN-02)**: Fix stale flat-name references in non-test code and comments (full scope documented in IN-02 Sweep section below).
- **D-09**: Add a `Migration Guide: v0.6.0 → v0.7.0` section to `MIGRATION.md` with a 1:1 flat→accessor replacement table covering all 56 names.
- **D-10**: Add CHANGELOG `[0.7.0]` with a `### Breaking` entry stating the 56 flat aliases are removed and pointing to the MIGRATION v0.6→v0.7 section.
- **D-11**: `-W error::DeprecationWarning` must be clean after removal. Coverage ratchet (≥94) must hold.

### Claude's Discretion

- Exact new test file name/structure for D-05 (parametrized over a name list vs. introspecting `ACCESSOR_PAIRS`).
- Whether to drive the 56-name list in MIGRATION from the existing v0.6.0 table verbatim or regenerate it.
- Wave/plan decomposition (source removal vs. tests vs. docs vs. IN-02 cleanup).

### Deferred Ideas (OUT OF SCOPE)

- Any Incremental ETL work (Phases 26–28).
- The v0.7.0 release itself (Phase 29) — no version bump here.
- Re-litigating the removal vs. a second deprecation cycle (decided: hard removal).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ALIAS-RM-01 | 56 `@deprecated_alias` stubs removed from both `Database` and `AsyncDatabase` (112 total); public surface is accessor-only | Removal mechanics section: exact line ranges, safe-delete boundaries, `grep -c deprecated_alias` → 0 acceptance check |
| ALIAS-RM-02 | Calling any removed flat name raises plain `AttributeError`; alias-specific tests removed; `test_parity`/`ACCESSOR_PAIRS` still pass green | AttributeError section: no `__getattr__` fallback; parity test symmetry analysis; D-05 test design |
| ALIAS-RM-03 | MIGRATION v0.6→v0.7 section with 56-name table; CHANGELOG `[0.7.0]` Breaking entry pointing to it | Docs section: reuse existing v0.6.0 table verbatim, reframe as "removed in v0.7.0"; CHANGELOG `[Unreleased]` is currently empty |
| ALIAS-RM-04 | WR-01 (IDE signature erasure) and IN-02 (stale flat-name error messages) closed | WR-01 verification approach; IN-02 sweep: 16 stale message sites across 4 files + 4 doc source files |
</phase_requirements>

---

## Summary

Phase 25 is a pure deletion phase. The deprecation cycle was served in v0.6.0; this phase hard-removes the 112 `@deprecated_alias` stubs (56 per class), deletes the `aliases.py` decorator module, replaces 6 warn+delegate test files with one `AttributeError` proof test, and updates docs and error messages to reference accessor paths.

The critical mechanical risk is **non-alias real methods interleaved inside the alias region** of both source files. In `database.py`, a `DATAFRAME OPERATIONS` block (4 real methods: `from_dataframe`, `to_dataframe`, `from_geodataframe`, `to_geodataframe`) sits between L983 and L1192 inside what would naively look like a single alias block. In `async_database.py`, the interleaving is more extensive: `DATAFRAME OPERATIONS` (L940–), `BATCH OPERATIONS` (L1161–), `STREAMING` (L1247–), and `LISTEN/NOTIFY` (L1341–) blocks all sit inside the alias region. Every one of these real method blocks must be preserved.

The second significant finding is that **IN-02 is broader than previously documented**: not just `pycopg/spatial.py:966`, but also `pycopg/async_database.py:1119`, `pycopg/database.py:1108`, and 12 sites in `pycopg/timescale.py` all contain stale `"Run db.create_extension(...)"` error messages. Additionally, 4 `docs/*.md` source files contain flat-name code examples (not cross-refs, so no Sphinx `-W` failure, but correct post-v0.7.0 documentation requires updating them).

**Primary recommendation:** Decompose into three waves — (1) source deletion + import removal + aliases.py delete, (2) test swap (delete 6 alias test files, add `test_alias_removal.py`), (3) docs/error-message cleanup (IN-02 fixes + MIGRATION + CHANGELOG). All three waves can be verified independently before moving to the next.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Stub deletion (`database.py`, `async_database.py`) | Source (pycopg package) | — | Direct edit to class bodies |
| Decorator module deletion (`aliases.py`) | Source (pycopg package) | — | Whole-file delete; no consumers remain |
| Test swap (delete 6, add 1) | Test layer | — | Remove warn+delegate assertions, add AttributeError proof |
| Error-message IN-02 fixes | Source (pycopg package) | — | String literals inside accessor methods |
| Docs update | Documentation | — | Flat-name code examples in markdown; no autodoc cross-refs |
| MIGRATION + CHANGELOG | Documentation | — | Additive; reuse existing v0.6.0 table |

---

## 1. Removal Mechanics

### database.py — Exact Boundaries

[VERIFIED: live grep]

- **First alias decorator:** L859 (`@deprecated_alias("schema.create_database")`)
- **Last alias stub body:** L1329 (`"""Deprecated: use ``db.backup.copy_from_csv`` instead."""`)
- **First lifecycle method:** L1330 (`def close(self) -> None:`)
- **Import to remove:** L29 (`from pycopg.aliases import deprecated_alias`)

**Interleaved real-method block that MUST be preserved:**

| Section | Lines | Methods |
|---------|-------|---------|
| `# DATAFRAME OPERATIONS` | L983–L1192 | `from_dataframe` (L987), `to_dataframe` (L1028), `from_geodataframe` (L1066), `to_geodataframe` (L1147) |

The alias stubs resume at L1194 (`@deprecated_alias("spatial.create_spatial_index")`) after the dataframe block ends at L1192.

**Safe deletion strategy for database.py:**
Delete each `@deprecated_alias` + `def name(self, *args, **kwargs):` + docstring body as individual units (2–3 lines each). Do NOT delete by line-range. Also delete section-header comments that become empty (`# DATABASE ADMINISTRATION`, `# EXTENSIONS`, etc.) unless they contain real methods underneath — DATAFRAME OPERATIONS header at L983 must stay.

**All 56 flat names in database.py (verified count: 56):**
`add_compression_policy`, `add_foreign_key`, `add_primary_key`, `add_retention_policy`,
`add_unique_constraint`, `alter_role`, `analyze`, `columns_with_types`, `copy_from_csv`,
`copy_to_csv`, `create_database`, `create_extension`, `create_hypertable`, `create_index`,
`create_role`, `create_schema`, `create_spatial_index`, `database_exists`, `drop_database`,
`drop_extension`, `drop_index`, `drop_role`, `drop_schema`, `drop_table`, `enable_compression`,
`explain`, `grant`, `grant_role`, `has_extension`, `hypertable_info`, `list_columns`,
`list_constraints`, `list_databases`, `list_extensions`, `list_geometry_columns`,
`list_hypertables`, `list_indexes`, `list_role_grants`, `list_role_members`, `list_roles`,
`list_schemas`, `list_tables`, `pg_dump`, `pg_restore`, `revoke`, `revoke_role`, `role_exists`,
`row_count`, `schema_exists`, `size`, `table_exists`, `table_info`, `table_size`, `table_sizes`,
`truncate_table`, `vacuum`

### async_database.py — Exact Boundaries

[VERIFIED: live grep]

- **First alias decorator:** L732 (`@deprecated_alias("schema.list_schemas")`)
- **Last alias stub body:** L1340 (`"""Deprecated: use ``async_db.backup.copy_from_csv`` instead."""`)
- **First post-alias real section:** L1341 (`# LISTEN/NOTIFY`) → `listen` at L1345, `notify` at L1365
- **Lifecycle methods:** `close` at L1383, `__aenter__` at L1395, `__aexit__` at L1399
- **Import to remove:** L28 (`from pycopg.aliases import deprecated_alias`)

**Interleaved real-method blocks that MUST be preserved:**

| Section | Lines | Methods |
|---------|-------|---------|
| `# DATAFRAME OPERATIONS` | L940–L1160 | `to_dataframe` (L944), `from_dataframe` (L986), `to_geodataframe` (L1030), `from_geodataframe` (L1077) |
| `# BATCH OPERATIONS` | L1161–L1246 | `insert_many` (L1165), `upsert_many` (L1202) |
| `# STREAMING` | L1247–L1284 | `stream` (L1251) |

The alias stubs continue in the `# DATABASE ADMINISTRATION` section (L1285–) then `# UTILITY` (L1305–) then `# BACKUP & RESTORE` (L1321–), ending at L1340. After L1340, `# LISTEN/NOTIFY` (L1341) contains real methods `listen` and `notify`, then lifecycle.

**All 56 flat names in async_database.py are identical to database.py** (verified count: 56). [VERIFIED: live grep — `grep -oP 'async def \K\w+(?=\(self, \*args)' async_database.py | sort -u | wc -l` → 56]

---

## 2. AttributeError Behavior

[VERIFIED: live grep]

After removing the 56 stubs from both classes, accessing a removed flat name (e.g. `db.create_hypertable`) will raise a plain `AttributeError` from Python's default attribute lookup. This is guaranteed because:

1. **No `__getattr__` anywhere in the package.** Grep of all `pycopg/*.py` for `__getattr__` and `__getattribute__` returns zero results. Python's default attribute resolution mechanism applies; no fallback intercepts the missing attribute.

2. **Class hierarchy has no fallback.** `Database` and `AsyncDatabase` both inherit from `DatabaseBase(ABC)` and `QueryMixin` (confirmed `class Database(DatabaseBase, QueryMixin)` at `database.py:56`, `class AsyncDatabase(DatabaseBase, QueryMixin)` at `async_database.py:56`). Neither `DatabaseBase` nor `QueryMixin` define `__getattr__`.

3. **`__init__.py` does not re-export flat names.** The `pycopg/__init__.py` `__all__` exports only class names (`Database`, `AsyncDatabase`, `Config`, accessors, exceptions, utils). No flat method name is re-exported. [VERIFIED: live read of `__init__.py`]

**Conclusion:** After removal, `db.create_hypertable` raises `AttributeError: 'Database' object has no attribute 'create_hypertable'` — no warning, no delegation.

---

## 3. Parity Test Impact (test_parity.py stays green without modification)

[VERIFIED: live analysis of test_parity.py]

`tests/test_parity.py` compares public method surfaces of `Database` vs `AsyncDatabase`. After alias removal:

- Both classes lose exactly the same 56 flat names symmetrically. The parity delta is zero.
- `SYNC_ONLY_METHODS = {'engine'}` — still correct (async has `async_engine`).
- `ASYNC_ONLY_METHODS = {'async_engine', 'listen'}` — still correct (`listen` is async-only by design; `notify` exists in both: `database.py:680` and `async_database.py:1365`).
- `KNOWN_SIGNATURE_MISMATCHES = set()` — still empty (aliases had `*args, **kwargs` on both sides, creating false signature "parity"; post-removal, the real accessor methods are not compared by this test).
- `test_exception_lists_are_minimal` verifies that everything in `SYNC_ONLY_METHODS`/`ASYNC_ONLY_METHODS` is still actually asymmetric after removal — it will still pass.
- `test_accessor_parity` (the `ACCESSOR_PAIRS` parametrized test) checks accessor classes only (`TimescaleAccessor` vs `AsyncTimescaleAccessor`, etc.) — unaffected by alias removal.

**No modification to test_parity.py is needed.**

---

## 4. WR-01 Verification Approach

[VERIFIED: live grep]

Currently, every `*args, **kwargs` on `Database` and `AsyncDatabase` belongs to an alias stub. Confirmed counts:
- `grep -c '\*args, \*\*kwargs' pycopg/database.py` → **56**
- `grep -c '\*args, \*\*kwargs' pycopg/async_database.py` → **56**

No real (non-alias) method in either file uses `*args, **kwargs`.

**Concrete checkable assertion for WR-01 closure:**

After removal, run:

```bash
grep -c '\*args, \*\*kwargs' pycopg/database.py pycopg/async_database.py
```

Must output `0` for both files.

**Additionally**, verify via `inspect` that no public method on `Database` or `AsyncDatabase` has `args` or `kwargs` in its parameter list:

```python
import inspect
from pycopg import Database, AsyncDatabase

for cls in (Database, AsyncDatabase):
    for name, member in inspect.getmembers(cls, predicate=callable):
        if name.startswith('_'):
            continue
        try:
            params = inspect.signature(member).parameters
            for p in params.values():
                assert p.kind not in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ), f"{cls.__name__}.{name} still has *args/**kwargs"
        except (ValueError, TypeError):
            pass
```

This can be a test in `test_alias_removal.py` or a CI one-liner. It proves that IDE autocomplete now sees real signatures for all public methods on both classes.

---

## 5. IN-02 Sweep — Complete Stale Flat-Name Site List

[VERIFIED: live grep across all pycopg/ source files]

### Stale error-message sites (non-test source — MUST fix)

| File | Line | Current text | Corrected text |
|------|------|-------------|----------------|
| `pycopg/spatial.py` | 966 | `"PostGIS extension not installed. Run db.create_extension('postgis')"` | `"PostGIS extension not installed. Run db.schema.create_extension('postgis')"` |
| `pycopg/database.py` | 1108 | `"PostGIS extension not installed. Run db.create_extension('postgis')"` | `"PostGIS extension not installed. Run db.schema.create_extension('postgis')"` |
| `pycopg/async_database.py` | 1119 | `"PostGIS extension not installed. Run db.create_extension('postgis')"` | `"PostGIS extension not installed. Run db.schema.create_extension('postgis')"` |
| `pycopg/timescale.py` | 80 | `"TimescaleDB extension not installed. Run db.create_extension('timescaledb')"` | `"TimescaleDB extension not installed. Run db.schema.create_extension('timescaledb')"` |
| `pycopg/timescale.py` | 124 | `"Run db.create_extension('timescaledb')"` | `"Run db.schema.create_extension('timescaledb')"` |
| `pycopg/timescale.py` | 177 | `"Run db.create_extension('timescaledb')"` | `"Run db.schema.create_extension('timescaledb')"` |
| `pycopg/timescale.py` | 214 | `"Run db.create_extension('timescaledb')"` | `"Run db.schema.create_extension('timescaledb')"` |
| `pycopg/timescale.py` | 240 | `"Run db.create_extension('timescaledb')"` | `"Run db.schema.create_extension('timescaledb')"` |
| `pycopg/timescale.py` | 268 | `"Run db.create_extension('timescaledb')"` | `"Run db.schema.create_extension('timescaledb')"` |
| `pycopg/timescale.py` | 332 | `"TimescaleDB extension not installed. Run db.create_extension('timescaledb')"` | `"TimescaleDB extension not installed. Run db.schema.create_extension('timescaledb')"` |
| `pycopg/timescale.py` | 376 | `"Run db.create_extension('timescaledb')"` | `"Run db.schema.create_extension('timescaledb')"` |
| `pycopg/timescale.py` | 431 | `"Run db.create_extension('timescaledb')"` | `"Run db.schema.create_extension('timescaledb')"` |
| `pycopg/timescale.py` | 468 | `"Run db.create_extension('timescaledb')"` | `"Run db.schema.create_extension('timescaledb')"` |
| `pycopg/timescale.py` | 494 | `"Run db.create_extension('timescaledb')"` | `"Run db.schema.create_extension('timescaledb')"` |
| `pycopg/timescale.py` | 522 | `"Run db.create_extension('timescaledb')"` | `"Run db.schema.create_extension('timescaledb')"` |

**Summary:** 15 error-message sites total. 3 are PostGIS guards (`spatial.py`, `database.py`, `async_database.py`), 12 are TimescaleDB guards in `timescale.py`. All use an identical pattern: `sed -i 's/Run db.create_extension/Run db.schema.create_extension/g'` applied to both files handles all 15 in one pass.

### Stale test comment (fix, do not delete)

| File | Line | Issue | Fix |
|------|------|-------|-----|
| `tests/test_sql_injection.py` | ~38 | Comment in `sync_db` fixture: `"the deprecated flat spatial aliases now route through the PostGIS-guarded SpatialAccessor (D-06)"` — stale post-removal | Update comment to reflect that the fixture patches `has_extension` because `SpatialAccessor.__init__` guards PostGIS; remove the alias routing note |

### Stale docs code examples (fix for correctness — NOT a Sphinx -W failure)

The Sphinx build runs `sphinx-build -W --keep-going` (confirmed in `.github/workflows/tests.yml`). The flat-name code examples in docs are inside fenced code blocks, not `:meth:` or `.. automethod::` cross-references — they will **not** cause Sphinx `-W` warnings. However, they are factually wrong post-v0.7.0 and should be updated as part of D-09 docs work:

| File | Line | Current code example | Updated form |
|------|------|---------------------|-------------|
| `docs/index.md` | 53 | `print(db.list_tables("public"))` | `print(db.schema.list_tables("public"))` |
| `docs/getting-started.md` | 88 | `tables = db.list_tables()` | `tables = db.schema.list_tables()` |
| `docs/postgis.md` | 18 | `db.create_extension("postgis")` | `db.schema.create_extension("postgis")` |
| `docs/postgis.md` | 112 | `db.create_index("parcels", "geometry", method="gist")` | `db.schema.create_index(...)` |
| `docs/postgis.md` | 115 | `db.create_index("parcels", "properties", method="gin")` | `db.schema.create_index(...)` |
| `docs/postgis.md` | 308 | `db.create_extension("postgis")` | `db.schema.create_extension("postgis")` |
| `docs/async-database.md` | 263 | `await db.create_schema("new_schema")` | `await db.schema.create_schema(...)` |
| `docs/async-database.md` | 266 | `tables = await db.list_tables("public")` | `await db.schema.list_tables(...)` |
| `docs/async-database.md` | 283 | `await db.create_extension("uuid-ossp")` | `await db.schema.create_extension(...)` |
| `docs/async-database.md` | 338 | `await db.create_index("products", "name", unique=True)` | `await db.schema.create_index(...)` |
| `docs/async-database.md` | 363 | `await db.vacuum("large_table", analyze=True)` | `await db.maint.vacuum(...)` |
| `docs/async-database.md` | 384 | `await db.pg_dump("backup.dump")` | `await db.backup.pg_dump(...)` |
| `docs/async-database.md` | 390 | `rows_exported = await db.copy_to_csv(...)` | `await db.backup.copy_to_csv(...)` |
| `docs/async-database.md` | 404 | `await db.create_database("analytics", owner="analyst")` | `await db.schema.create_database(...)` |
| `docs/async-database.md` | 418 | `await db.create_role("appuser", ...)` | `await db.admin.create_role(...)` |
| `docs/async-database.md` | 465 | `await db.create_hypertable(...)` | `await db.timescale.create_hypertable(...)` |

Additionally, three doc files have deprecation-warning notes that should be updated from "deprecated as of v0.6.0, will be removed in v0.7.0" to "removed in v0.7.0":
- `docs/roles-permissions.md:26`
- `docs/backup-restore.md:26`
- `docs/timescaledb.md:34`
- `docs/database.md:187`

`docs/_build/` is generated — do not edit HTML files directly; rebuild after source edits.

---

## 6. Coverage Ratchet Risk Assessment

[VERIFIED: live analysis]

**Current ratchet:** `--cov-fail-under=94` in `pyproject.toml` addopts. Last measured baseline: **95.64%** at v0.6.0 ship (from STATE.md).

**What gets deleted from source:**
- 112 alias stub bodies (3 lines each ≈ 336 source lines)
- `aliases.py` (65 lines, entirely executable)
- 6 alias test files (1,119 test lines total)

**Coverage arithmetic:**

When a source file is deleted, it leaves the coverage denominator. When its test file is also deleted, the tests that exercised those source lines are also gone. The net effect is roughly neutral because:

- The 112 stubs each had 1 executable line (a `pass`-like body); all were executed by the alias test files that are being deleted.
- `aliases.py` had ~15 executable lines (the decorator, the two wrapper functions). These were exercised by the alias tests.
- After removal: both numerator (covered lines) and denominator (total lines) shrink proportionally.

**Risk: LOW.** Baseline was 95.64% (1.64% headroom above the 94% gate). The alias stubs are short (1–2 executable lines each) and represent a small fraction of the ~1,400-line source files. Even if coverage drops slightly due to the new `test_alias_removal.py` not achieving 100% on its own, the headroom is substantial.

**Required verification step:** Run `uv run pytest tests/test_alias_removal.py -v --cov=pycopg --cov-report=term-missing` after the stub deletion and new test creation to confirm coverage is ≥94 before committing.

**Do NOT omit `aliases.py` from coverage** in `pyproject.toml` — it is being deleted, so no change needed. The `[tool.coverage.run]` `omit` list already excludes `*/tests/*` and `*/venv/*` but not `pycopg/aliases.py`; after deletion the file simply doesn't exist and has no coverage impact.

---

## 7. Sphinx -W Gate Analysis

[VERIFIED: live read of `.github/workflows/tests.yml` and `docs/conf.py`]

**CI command:** `uv run sphinx-build -W --keep-going -b html docs docs/_build/html`

**What Sphinx -W catches:**
- Broken `:meth:`, `:class:`, `:func:`, `:attr:` cross-references in `.rst`/`.md` files
- Undefined `.. automethod::` or `.. autoclass::` targets
- Malformed docstrings that Sphinx cannot parse

**What Sphinx -W does NOT catch:**
- Flat names inside fenced code blocks (e.g. `db.list_tables()` in a ` ``` ` block is rendered as text, not resolved as a reference)
- Runtime accuracy of code examples

**Impact of alias removal on Sphinx -W:**

1. `api-autodoc.md` uses `.. automodule:: pycopg.database :members:` — this will autodocument all public members. After removal, the 56 stubs are gone; Sphinx simply won't document them. No cross-reference breaks, because the stubs' docstrings only used double-backtick inline literals (e.g. `` ``db.schema.create_database`` ``), not `:meth:` cross-refs.

2. `pycopg/aliases.py` is NOT in `api-autodoc.md`'s module list — its deletion has zero Sphinx impact.

3. The stale code examples in `docs/*.md` listed in the IN-02 sweep above are in code blocks — they do not cause Sphinx `-W` failures. They are incorrect documentation that should be updated for accuracy but will not break the CI gate.

**Conclusion:** Sphinx `-W` gate will pass after alias removal even without updating the docs code examples. However, the docs updates should still be done (D-08/D-09) for documentation correctness.

---

## 8. Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Verifying 0 remaining alias stubs | Custom Python introspection | `grep -c 'deprecated_alias' pycopg/database.py pycopg/async_database.py` → must be 0 for both |
| Generating the 56-name MIGRATION table | Re-deriving by hand | Reuse the existing table verbatim from `MIGRATION.md:L96–L158` (already generated, already verified) |
| Detecting remaining `*args/**kwargs` stubs | Manual inspection | `grep -c '\*args, \*\*kwargs' pycopg/database.py pycopg/async_database.py` → must be 0 |

---

## Common Pitfalls

### Pitfall 1: Alias Test File Count Off-by-One
**What goes wrong:** Planner expects 7 alias test files (per CONTEXT.md wording), executor finds only 6 and suspects a mistake.
**Why it happens:** The CONTEXT.md description lists "admin, maint, schema, backup, timescale, spatial, sql" — the "sql" refers to the stale comment in `test_sql_injection.py`, not a separate `test_sql_aliases.py` file. There is no 7th alias test file.
**Reality:** `ls tests/test_*aliases*` → exactly 6 files. Plans should specify all 6 by name.

### Pitfall 2: Deleting Real Methods by Line Range
**What goes wrong:** Executor uses `sed -i 'L855,L1329d'` on `database.py` and accidentally deletes the `DATAFRAME OPERATIONS` block (L983–L1192) containing `from_dataframe`, `to_dataframe`, `from_geodataframe`, `to_geodataframe`.
**Why it happens:** The alias block is not a single contiguous region — real methods are interleaved in it.
**How to avoid:** Delete stubs method-by-method using `Edit` tool targeting individual `@deprecated_alias` + `def name(self, *args, **kwargs):` + docstring body patterns. Or use `grep -n '@deprecated_alias'` to get exact stub boundaries and delete those exact text blocks only.

### Pitfall 3: Same Pitfall in async_database.py — More Interleaving
**What goes wrong:** Executor deletes the async alias block from L732 to L1337 and inadvertently destroys `DATAFRAME OPERATIONS` (L940), `BATCH OPERATIONS` (L1161), `STREAMING` (L1247), and their real method implementations.
**Why it happens:** `async_database.py` has 4 interleaved real-method sections vs 1 in `database.py`.
**How to avoid:** Same as above — target stub patterns by text, not line range.

### Pitfall 4: Section-Header Comment Cleanup
**What goes wrong:** After deleting stubs, empty section headers like `# POSTGIS SPATIAL OPERATIONS` or `# TIMESCALEDB OPERATIONS` remain as dead comments in both files.
**Why it happens:** The stubs were grouped under descriptive section headers. After removal, the headers are orphaned.
**How to avoid:** Plans should explicitly list which section-header comment blocks to remove after stub deletion. In `database.py`, headers for `DATABASE ADMINISTRATION`, `EXTENSIONS`, `SCHEMAS & TABLES`, `CONSTRAINTS & INDEXES`, `POSTGIS SPATIAL OPERATIONS`, `TIMESCALEDB OPERATIONS`, `MAINTENANCE & STATS`, `ROLES & USERS`, `ROLE MANAGEMENT`, `BACKUP & RESTORE` all become empty. The `DATAFRAME OPERATIONS` header must stay.

### Pitfall 5: import line surviving in aliases.py deletion flow
**What goes wrong:** Executor deletes `aliases.py` but forgets to remove the `from pycopg.aliases import deprecated_alias` import at `database.py:29` and `async_database.py:28`. The package fails to import with `ModuleNotFoundError`.
**Why it happens:** File deletion and import cleanup are separate steps.
**How to avoid:** Plans must explicitly include import-line removal as a step that accompanies (or immediately precedes) `aliases.py` deletion. The acceptance check `python -c "import pycopg"` catches this immediately.

### Pitfall 6: test_parity.py test_known_exceptions_documented False Failure
**What goes wrong:** The `test_known_exceptions_documented` test fails with "Unknown async-only methods: {'stream'}" or similar.
**Why it happens:** If `stream` is in `AsyncDatabase` but not `Database` for some reason, or if aliases were masking an asymmetry that becomes visible after removal.
**Reality:** `stream` exists in both (`database.py:648`, `async_database.py:1251`); `insert_many` and `upsert_many` exist in both. `listen` is the only async-only real method. After alias removal, parity is maintained. This is a non-issue but worth verifying immediately after Wave 1 with `uv run pytest tests/test_parity.py -v -o addopts=""`.

---

## Validation Architecture

> Nyquist validation is enabled (key absent from `.planning/config.json` — treated as enabled).

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (via `uv run pytest`) |
| Config | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_alias_removal.py tests/test_parity.py -v -o addopts=""` |
| Full suite command | `uv run pytest` (includes coverage gate ≥94, addopts in pyproject.toml) |
| DeprecationWarning gate | `uv run pytest -W error::DeprecationWarning tests/ -o addopts=""` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ALIAS-RM-01 | `grep -c deprecated_alias database.py async_database.py` → 0/0; `aliases.py` absent | structural grep | `bash -c 'grep -c deprecated_alias pycopg/database.py pycopg/async_database.py && echo "FAIL" || echo "PASS"'` | N/A — shell check |
| ALIAS-RM-01 | Import smoke: `python -c "import pycopg"` succeeds (no ModuleNotFoundError from missing aliases.py import) | smoke | `uv run python -c "import pycopg"` | N/A — one-liner |
| ALIAS-RM-02 | Removed flat names raise `AttributeError` on live `Database` and `AsyncDatabase` instances | unit | `uv run pytest tests/test_alias_removal.py -v -o addopts=""` | ❌ Wave 0 |
| ALIAS-RM-02 | `-W error::DeprecationWarning` gate is clean (no stubs left to fire) | regression | `uv run pytest -W error::DeprecationWarning tests/ -o addopts=""` | N/A — flag |
| ALIAS-RM-02 | `test_parity.py` accessor pairs + Database/AsyncDatabase surface parity still passes | regression | `uv run pytest tests/test_parity.py -v -o addopts=""` | ✅ exists |
| ALIAS-RM-03 | MIGRATION.md has v0.6→v0.7 section with 56-name table | doc structural | `grep -c 'v0.6.0 → v0.7.0' MIGRATION.md` → ≥1 | N/A — grep |
| ALIAS-RM-03 | CHANGELOG has `[0.7.0]` Breaking entry | doc structural | `grep '## \[0.7.0\]' CHANGELOG.md` | N/A — grep |
| ALIAS-RM-04 (WR-01) | No `*args, **kwargs` on public Database/AsyncDatabase surface | structural grep | `bash -c 'grep -c "\*args, \*\*kwargs" pycopg/database.py pycopg/async_database.py'` → 0/0 | N/A — grep |
| ALIAS-RM-04 (IN-02) | `db.create_extension` absent from non-test pycopg/ source error messages | structural grep | `grep -rn "db\.create_extension" pycopg/ --include="*.py"` → 0 results | N/A — grep |

### Wave 0 Gaps

- [ ] `tests/test_alias_removal.py` — covers ALIAS-RM-02 (AttributeError for all 56 removed names + WR-01 no-`*args/**kwargs` assertion)

**Recommended structure for `tests/test_alias_removal.py`:**

```python
"""Proof that removed v0.6.0 flat aliases raise AttributeError (ALIAS-RM-02)."""
import inspect
import pytest
from unittest.mock import MagicMock, patch

from pycopg import Database, AsyncDatabase
from pycopg.config import Config

# The 56 removed flat names — must match the v0.7.0 removal exactly
REMOVED_FLAT_NAMES = [
    "add_compression_policy", "add_foreign_key", "add_primary_key",
    "add_retention_policy", "add_unique_constraint", "alter_role", "analyze",
    "columns_with_types", "copy_from_csv", "copy_to_csv", "create_database",
    "create_extension", "create_hypertable", "create_index", "create_role",
    "create_schema", "create_spatial_index", "database_exists", "drop_database",
    "drop_extension", "drop_index", "drop_role", "drop_schema", "drop_table",
    "enable_compression", "explain", "grant", "grant_role", "has_extension",
    "hypertable_info", "list_columns", "list_constraints", "list_databases",
    "list_extensions", "list_geometry_columns", "list_hypertables", "list_indexes",
    "list_role_grants", "list_role_members", "list_roles", "list_schemas",
    "list_tables", "pg_dump", "pg_restore", "revoke", "revoke_role", "role_exists",
    "row_count", "schema_exists", "size", "table_exists", "table_info",
    "table_size", "table_sizes", "truncate_table", "vacuum",
]

@pytest.fixture
def sync_db(config):
    with patch("pycopg.database.psycopg"):
        yield Database(config)

@pytest.fixture
def async_db(config):
    yield AsyncDatabase(config)

@pytest.mark.parametrize("name", REMOVED_FLAT_NAMES)
def test_removed_flat_name_raises_attribute_error_sync(name, sync_db):
    with pytest.raises(AttributeError):
        getattr(sync_db, name)

@pytest.mark.parametrize("name", REMOVED_FLAT_NAMES)
def test_removed_flat_name_raises_attribute_error_async(name, async_db):
    with pytest.raises(AttributeError):
        getattr(async_db, name)

def test_no_varargs_on_database_public_surface():
    """WR-01: No *args/**kwargs stubs remain on Database (py.typed IDE signatures restored)."""
    for name, member in inspect.getmembers(Database, predicate=callable):
        if name.startswith('_'):
            continue
        try:
            params = inspect.signature(member).parameters.values()
            for p in params:
                assert p.kind not in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ), f"Database.{name} still has *args/**kwargs"
        except (ValueError, TypeError):
            pass

def test_no_varargs_on_async_database_public_surface():
    """WR-01: No *args/**kwargs stubs remain on AsyncDatabase."""
    for name, member in inspect.getmembers(AsyncDatabase, predicate=callable):
        if name.startswith('_'):
            continue
        try:
            params = inspect.signature(member).parameters.values()
            for p in params:
                assert p.kind not in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ), f"AsyncDatabase.{name} still has *args/**kwargs"
        except (ValueError, TypeError):
            pass
```

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_alias_removal.py tests/test_parity.py -v -o addopts=""`
- **Per wave merge:** `uv run pytest -W error::DeprecationWarning tests/ -o addopts=""` + structural grep checks
- **Phase gate:** `uv run pytest` (full suite, coverage ≥94) before `/gsd-verify-work`

---

## Standard Stack (No New Dependencies)

This phase installs no packages. Zero new dependencies (locked decision D-11 / CONTEXT.md). No package legitimacy audit required.

---

## Architecture Patterns

### Recommended Wave Decomposition

```
Wave 1 — Source deletion
  Plan A: database.py stubs + aliases.py delete + import removal
  Plan B: async_database.py stubs + import removal

Wave 2 — Test swap
  Plan C: Delete 6 alias test files, add tests/test_alias_removal.py

Wave 3 — Docs + error messages
  Plan D: IN-02 error message fixes (15 sites: spatial.py, database.py,
           async_database.py, timescale.py) + test_sql_injection.py comment
  Plan E: MIGRATION.md v0.6→v0.7 section + CHANGELOG [0.7.0] Breaking +
           docs/*.md code example updates
```

Each wave is independently verifiable; Wave 1 must precede Wave 2 (stub deletion must exist before AttributeError tests can pass). Wave 3 is independent of Wave 2 but must be sequenced last for CHANGELOG accuracy.

### Safe Deletion Pattern for Alias Stubs

To safely remove each stub without touching adjacent real methods:

```python
# Each alias stub is exactly this pattern (2-5 lines):
#
#   @deprecated_alias("accessor.method")
#   def flat_name(self, *args, **kwargs):
#       """Deprecated: use ``db.accessor.method`` instead."""
#
# (or async def for async_database.py)
#
# Delete by targeting the decorator + def + docstring as a unit.
# Never use line-range deletion.
```

The section header comments (`# EXTENSIONS`, `# SCHEMAS & TABLES`, etc.) that group alias stubs into categories should also be deleted as part of alias removal — except `# DATAFRAME OPERATIONS` in both files (which contains real methods).

---

## Environment Availability

Step 2.6: SKIPPED (no external dependencies — this is a pure code/test/doc deletion phase).

---

## Runtime State Inventory

Step 2.5: SKIPPED (not a rename/refactor/migration phase in the rename sense — this is a deletion of Python source methods, not a string-rename across external state stores).

---

## Open Questions (RESOLVED)

1. **Should `aliases.py` be deleted before or after the stubs are removed?**
   - What we know: Both `database.py` and `async_database.py` import `from pycopg.aliases import deprecated_alias`. As long as any stub or import remains, deleting `aliases.py` causes `ImportError`.
   - Recommendation: Remove the import lines from both source files first (or in the same edit), then delete `aliases.py`. Alternatively, delete all stubs and import lines in one task, then delete `aliases.py` as the final step of Wave 1.

2. **Should the 56-name list in `test_alias_removal.py` be hardcoded or derived at test time?**
   - Hardcoded list: Explicit, fast, clearly documents what was removed. Will not grow accidentally.
   - Derived at test time: Fragile — if the test reads from MIGRATION.md it introduces file-system coupling.
   - Recommendation: Hardcode the list in `test_alias_removal.py` (see Wave 0 template above). The list is stable post-v0.7.0.

---

## Sources

### Primary (HIGH confidence)
- Live grep of `/home/loc/workspace/pycopg/pycopg/database.py` — stub line ranges, interleaved methods, `*args/**kwargs` counts
- Live grep of `/home/loc/workspace/pycopg/pycopg/async_database.py` — stub line ranges, interleaved methods, real method positions
- Live read of `/home/loc/workspace/pycopg/pycopg/__init__.py` — no flat name re-exports
- Live grep of `/home/loc/workspace/pycopg/pycopg/` for `__getattr__`/`__getattribute__` — zero results
- Live grep for `db.create_extension` across all pycopg source — 15 stale error-message sites
- Live read of `/home/loc/workspace/pycopg/.github/workflows/tests.yml` — confirmed `sphinx-build -W --keep-going`
- Live read of `/home/loc/workspace/pycopg/pyproject.toml` — coverage gate `--cov-fail-under=94`, no sphinx `-W` in scripts
- Live read of `/home/loc/workspace/pycopg/tests/test_parity.py` — `SYNC_ONLY_METHODS`, `ASYNC_ONLY_METHODS`, `ACCESSOR_PAIRS` analysis
- Live read of `/home/loc/workspace/pycopg/MIGRATION.md` — existing 56-name table at L96–L158

### Secondary (MEDIUM confidence)
- Coverage arithmetic (estimated from file line counts and v0.6.0 baseline) — risk assessed as LOW

---

## Assumptions Log

No claims tagged `[ASSUMED]` — all findings verified against live source in this session.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | — | — | — |

**All claims in this research were verified or cited — no user confirmation needed.**

---

## Metadata

**Confidence breakdown:**
- Removal mechanics: HIGH — grep-verified line numbers and method names
- AttributeError behavior: HIGH — grep-verified absence of `__getattr__` in all source files
- IN-02 sweep: HIGH — grep-verified all 15 sites
- Coverage risk: MEDIUM — arithmetic from line counts; actual impact verified by running tests post-removal
- Sphinx -W gate: HIGH — CI workflow read, docs structure confirmed

**Research date:** 2026-06-19
**Valid until:** 2026-07-19 (stable codebase, no moving parts)

---

## Project Constraints (from CLAUDE.md)

| Directive | Impact on This Phase |
|-----------|---------------------|
| Independent PyPI lib — no Solaris deps | Confirmed: no new deps added; `aliases.py` is internal |
| Venv: `pycopg/venv/` (not workspace uv Solaris) | All commands use `uv run pytest`, `uv run python` per CLAUDE.md |
| Tests: `uv run pytest tests/ -x -q` | Quick gate after each wave |
| Lint: `uv run ruff check pycopg tests` | Run after stub deletion to catch any import references missed |
| Format: `uv run black pycopg tests` | Run after edits to maintain formatting |
| Coverage ratchet ≥94 | Assessed as LOW risk — baseline 95.64%, symmetric deletion preserves ratio |
| Numpydoc docstrings | Not applicable — no new public methods added |
| Version: v0.5.0 → now v0.6.0 shipped, this is v0.7.0 phase | No version bump in Phase 25 (that's Phase 29) |
