# Phase 12: Refactoring — brancher les abstractions - Pattern Map

**Mapped:** 2026-06-09
**Files analyzed:** 5 modified (base.py, queries.py, database.py, async_database.py, tests/test_parity.py)
**Analogs found:** 5 / 5 (all in-codebase — refactor wires existing abstractions, no external patterns needed)

> Behavior-preserving refactor. Zero API/signature/return-shape change (D-06). Every analog is an existing file in this repo. numpydoc homogenization is **deferred to Phase 13** — copy docstrings verbatim onto the base, do not reformat.

## File Classification

| Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------|------|-----------|----------------|---------------|
| `pycopg/base.py` (add 3 builders) | utility (pure builders) | transform (args → list/str) | `pycopg/base.py::QueryMixin._build_*` staticmethods | exact (same file, same kind) |
| `pycopg/queries.py` (remove 2 consts) | config (SQL constants) | n/a | existing canonical constants `TABLE_INFO` / `LIST_ROLES` | exact |
| `pycopg/database.py` (inherit + wire) | model/facade | CRUD + request-response | `pycopg/base.py::DatabaseBase` + existing `queries.` refs (database.py:1018,1031) | exact |
| `pycopg/async_database.py` (inherit + wire) | model/facade | CRUD + request-response | `pycopg/database.py` (its sync twin, post-Phase-11) | exact |
| `tests/test_parity.py` (add builder tests) | test | request-response (introspection) | existing class-level tests `TestAsyncParity` (test_parity.py:13-52) | role-match |

---

## Pattern Assignments

### `pycopg/base.py` — add 3 module-level builders (REF-03, D-03/D-04)

**Analog:** `QueryMixin._build_insert_sql` / `_build_batch_insert_sql` / `_build_select_sql` (base.py:69-173). These are the existing pure-builder pattern: staticmethods, explicit args, `validate_identifiers` up front, return a value, no `self`, no I/O.

**Decision divergence from analog:** the 3 new builders are **module-level functions** (not staticmethods) — explicit D-03 choice for DB-free testability. Names: `build_role_options`, `build_pg_dump_cmd`, `build_pg_restore_cmd` (note: no leading underscore; module-level public-to-package). Place after the existing classes in `base.py`.

**Pattern to copy — pure builder shape** (base.py:96-131, `_build_batch_insert_sql`):
```python
@staticmethod
def _build_batch_insert_sql(table, columns, rows, schema="public", on_conflict=None):
    validate_identifiers(table, schema, *columns)   # validation first
    cols_str = ", ".join(columns)
    conflict_clause = f" ON CONFLICT {on_conflict}" if on_conflict else ""
    placeholders, params = [], []
    for row in rows:                                  # loop builds list
        ...
    return sql, params                                # returns value, no I/O
```

**Source for `build_pg_dump_cmd` — extract the argv-building lines ONLY** (database.py:2424-2459). The builder takes explicit args (`host, port, user, database, output_file, format, schema_only, data_only, tables, exclude_tables, schemas, compress, jobs`) and returns the `cmd` list. **Leave env + subprocess in the method** (database.py:2461-2468) — D-04, no password through the pure builder:
```python
output_file = Path(output_file)
cmd = ["pg_dump"]
cmd.extend(["-h", self.config.host]); cmd.extend(["-p", str(self.config.port)])
cmd.extend(["-U", self.config.user]); cmd.extend(["-d", self.config.database])
format_map = {"plain": "p", "custom": "c", "directory": "d", "tar": "t"}
cmd.extend(["-F", format_map[format]])
if schema_only: cmd.append("--schema-only")
if data_only:   cmd.append("--data-only")
if compress and format == "custom": cmd.extend(["-Z", str(compress)])
if jobs > 1 and format == "directory": cmd.extend(["-j", str(jobs)])
if tables:         [cmd.extend(["-t", t]) for t in tables]
if exclude_tables: [cmd.extend(["-T", t]) for t in exclude_tables]
if schemas:        [cmd.extend(["-n", s]) for s in schemas]
cmd.extend(["-f", str(output_file)])
# ↑ all of this → build_pg_dump_cmd(...); ↓ stays in method
env = {"PGPASSWORD": self.config.password} if self.config.password else {}
result = subprocess.run(cmd, env={**os.environ, **env}, capture_output=True, text=True)
if result.returncode != 0: raise RuntimeError(f"pg_dump failed: {result.stderr}")
```

**Source for `build_pg_restore_cmd` — argv lines** (database.py:2522-2556). Same split: builder returns `cmd`, the `.sql`/non-exists early-return-to-`_psql_restore` branch (database.py:2516-2520) and env+subprocess (2558-2565) stay in the method. Args: `host, port, user, database, input_file, clean, if_exists, create, data_only, schema_only, tables, schemas, jobs, no_owner, no_privileges`.

**Source for `build_role_options` — extract option-list logic** (database.py:2025-2048, `create_role`). Returns the `options` list. **Keep `validate_timestamp(valid_until)` inside the builder** (it is pure validation, mirrors the QueryMixin `validate_identifiers`-first convention). The `"PASSWORD %s"` placeholder string is part of the returned list — the actual password value is bound by the caller via parameterized execute, never passed to the builder (D-04 parallel: no secret through the pure builder). NOTE: `alter_role` (database.py:2155-2169) uses a *different* on/off form (`"LOGIN" if login else "NOLOGIN"`, `NOSUPERUSER`, etc.) — confirm whether one builder covers both or only `create_role`; do **not** force-merge divergent semantics (mirrors D-02's "don't unify divergent code" caution).

**Async symmetry:** `AsyncDatabase.pg_dump` (async_database.py:2344) calls the **same** `build_pg_dump_cmd`. Verify async pg_restore/create_role share the byte-identical argv before routing; if async diverges, note it rather than alter behavior.

---

### `pycopg/queries.py` — remove orphan `*_SIMPLE` constants (REF-04, D-05)

**Analog:** the surviving canonical constants in the same file — `TABLE_INFO` (queries.py:41-54), `LIST_ROLES` (queries.py:162-175).

**Confirmed dead (grep, zero refs outside their own definition):**
- `TABLE_INFO_SIMPLE` (queries.py:63-74)
- `LIST_ROLES_SIMPLE` (queries.py:177-188)

Delete both blocks plus their `# Simplified version for AsyncDatabase` comments (queries.py:63, 177). No other edit to queries.py.

---

### `pycopg/database.py` — inherit base + wire constants (REF-01/REF-02, D-01)

**Analog:** `DatabaseBase` (base.py:18-59) for the inheritance collapse; existing `queries.` call sites (database.py:1018 `self.execute(queries.TABLE_EXISTS, [schema, name])`, 1031/1046 `queries.GET_COLUMNS`) for the SQL-constant wiring pattern.

**Inheritance pattern** — change `class Database:` (database.py:51) → `class Database(DatabaseBase, QueryMixin):`. The base `from_env`/`from_url`/`__repr__` are **byte-identical** to the concrete ones (compare base.py:33-59 vs database.py:96-124, 2731), so:
- **Delete** `from_env` (database.py:95-124), `from_url` (111-124), `__repr__` (2731+). They become inherited.
- The `-> Database` return annotations vanish with them; base uses `cls(...)` so the right subclass is returned (D-01).
- **Keep** `__init__` (database.py:85-93), but change body to call `super().__init__(config)` (which sets `self.config`) then keep the subclass-specific lines `self._engine = None` / `self._session_conn = None`. Base `__init__` is base.py:25-31.

**Constant-wiring pattern (REF-01)** — for each of the ~25 inline SQL strings, replace the f-string/triple-quote with the canonical constant. Two sub-shapes:

1. **Param-only (use directly):** e.g. database.py:2099-2112 `list_roles` → `self.execute(queries.LIST_ROLES.format(where_clause=where_clause))`. The `LIST_ROLES` constant already carries the `{where_clause}` slot (queries.py:173) — keep the existing `where_clause = "" if include_system else "WHERE rolname NOT LIKE 'pg_%'"` line, just `.format()` the constant instead of inlining.
2. **Plain SELECT:** replace the literal with `queries.<NAME>` exactly as database.py:1018 already does.

**Preserve all `validate_*` calls** (database.py:32-42, 2019, 2047) in any rebranched path — explicit Phase-10 carry-over (canonical_refs). Do not strip validation when swapping to a constant.

**pg_dump/pg_restore (REF-03):** replace argv-build lines with `cmd = build_pg_dump_cmd(...)` / `build_pg_restore_cmd(...)`, import from `pycopg.base`. Keep env+subprocess (see base.py assignment above).

---

### `pycopg/async_database.py` — same collapse + wire (REF-01/REF-02/REF-04, D-01/D-05)

**Analog:** its sync twin `pycopg/database.py` after the edits above, plus `DatabaseBase` (base.py:18-59).

- `class AsyncDatabase:` (async_database.py:50) → `class AsyncDatabase(DatabaseBase, QueryMixin):`.
- **Delete** `from_env` (async_database.py:93), `from_url` (105), `__repr__` (2784); inherit from base. They are identical to base except the `-> AsyncDatabase` annotation, which goes away (D-01).
- **Keep** `__init__` (async_database.py:73-81): `super().__init__(config)` then `self._session_conn = None` / `self._async_engine = None`. Keep the `async_engine` property (async_database.py:83-90) untouched — async-only by design (test_parity ASYNC_ONLY context).
- **D-05 wiring:** `table_info` (async_database.py:701-716) currently inlines the **full** TABLE_INFO form (8 columns) → route to `queries.TABLE_INFO`. `list_roles` (async_database.py:1372-1385) inlines the **full** LIST_ROLES form → route to `queries.LIST_ROLES.format(where_clause=where_clause)`. Both already produce the post-Phase-11 rich shape, so this is net-safe; `test_parity` asserts the full field set (test_parity.py:383 `test_table_info_field_parity`, 402 `test_list_roles_field_parity`).
- **REF-04:** delete the stale `Note: Requires add_primary_key (available in Phase 3).` comments (async_database.py:1891, 1981).

---

### `tests/test_parity.py` — add DB-free builder tests (REF-05, D-04/D-07)

**Analog:** the existing class-level (no-DB, no fixture) tests `TestAsyncParity.test_all_database_public_methods_exist_in_async` (test_parity.py:33-52) — pure `import` + call + `assert`, no `db_config` fixture, no `@pytest.mark.asyncio`. The builder tests follow this DB-free shape (NOT the `TestBehavioralParity` async/DB fixture shape at test_parity.py:182+).

**Pattern to copy** (DB-free, synchronous):
```python
from pycopg.base import build_pg_dump_cmd, build_pg_restore_cmd, build_role_options

def test_build_pg_dump_cmd_custom_format():
    cmd = build_pg_dump_cmd(host="h", port=5432, user="u", database="d",
                            output_file="out.dump", format="custom", compress=6)
    assert cmd[:5] == ["pg_dump", "-h", "h", "-p", "5432"]
    assert "-F" in cmd and cmd[cmd.index("-F") + 1] == "c"
    assert "-Z" in cmd
```
Cover the branchy paths (each `format`, each flag, table/schema loops, `compress`/`jobs` gates, role-option combinations) — these are the 90→95 coverage fuel (D-07). Write tests **only** for the newly-extracted builders; do not add characterization tests for already-covered paths (D-06). `--cov-fail-under` 90→95 flips in `pyproject.toml` **only after** measuring ≥95 (D-07).

---

## Shared Patterns

### Inheritance collapse (DatabaseBase)
**Source:** `pycopg/base.py:18-59`
**Apply to:** `database.py`, `async_database.py`
Both subclasses: `class X(DatabaseBase, QueryMixin)`, delete concrete `from_env`/`from_url`/`__repr__`, keep `__init__` calling `super().__init__(config)`. No MRO conflict (single base each today). Exported surface unchanged (`__init__.py` exports the class names).

### SQL-constant wiring (REF-01)
**Source:** existing `queries.` call sites — `database.py:1018,1031,1046`; `async_database.py:659,672,687`
**Apply to:** every inline SQL in both files (~25 sync). Two shapes: direct `queries.NAME` for param-only queries; `queries.NAME.format(where_clause=...)` for the `{where_clause}` constants (`LIST_ROLES` queries.py:173, `LIST_GEOMETRY_COLUMNS` queries.py:246). Constant is single source of truth.

### Pure-builder split (pure argv vs I/O shell)
**Source:** `pycopg/base.py::QueryMixin._build_*` (base.py:69-173) as the shape; D-04 as the split rule
**Apply to:** all 3 new builders. Builder = validation + list/str assembly + `return`. Caller keeps env-dict + `subprocess.run` + returncode check. No secret (`PGPASSWORD`, role password value) ever enters the pure builder.

### Validation preservation (Phase-10 carry-over)
**Source:** `pycopg/utils.py::validate_identifier(s)`, `validate_timestamp`, etc.
**Apply to:** every rebranched SQL path and every builder. Never drop a `validate_*` call when swapping inline SQL → constant or inline argv → builder.

---

## No Analog Found

None. Every target maps to an existing in-repo analog — this phase wires already-written abstractions rather than introducing new shapes.

---

## Metadata

**Analog search scope:** `pycopg/` (base.py, queries.py, database.py, async_database.py, utils.py), `tests/`
**Files scanned:** 5 source + 1 test
**Grep verification:** `*_SIMPLE` constants confirmed zero-reference; `import re` live only in utils/pool/migrations (not in target files); `Phase 3` comments at async_database.py:1891,1981 confirmed
**Pattern extraction date:** 2026-06-09
