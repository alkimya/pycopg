# Phase 53: CRUD Symmetry + Introspection Follow-ups - Research

**Researched:** 2026-07-05
**Domain:** Flat transactional core (predicate reads, single-row insert) + `db.schema.*` introspection, PostgreSQL/psycopg3
**Confidence:** HIGH

## Summary

This phase is pure symmetry-completion: every one of the 5 new helpers (`select_where`, `find`, `get`, `find_one`, single-row `insert`, `column_exists`, `table_size`) has an already-shipped, line-verified sibling in the live codebase to mirror mechanically. All CONTEXT.md D-01..D-09 anchors were read directly from disk and confirmed **exact** — no drift. The predicate surface (`_resolve_predicate`, `_build_where_dict`, `_build_select_sql`) is fully built and requires zero new SQL-building logic; `select_where`/`find`/`get`/`find_one` are thin call-pattern compositions of existing builders. Single-row `insert` is a near-copy of `upsert` minus the `ON CONFLICT` computation. `column_exists` is a one-line mirror of `table_exists` plus one new `queries.py` constant. `table_size` has a genuinely important finding: **`db.maint.table_size` already exists** (different accessor, different semantics — `str | int` with a `pretty=` toggle, no existence guard) and its underlying SQL constant `queries.TABLE_SIZE = "SELECT pg_total_relation_size(%s) AS size"` (queries.py:301) is **already exactly what D-09 wants** for `db.schema.table_size` — the new method should reuse this existing constant rather than adding a duplicate, and only needs to add the `table_exists`-guard on top.

The parity gate is two-tier and **auto-extending for both classes touched in this phase**: `Database`/`AsyncDatabase` (flat core) are checked by a hardcoded set-diff (`test_all_database_public_methods_exist_in_async` + `test_database_core_parameter_kind_parity`) that needs **no registry edit** — any new public method on both classes is picked up automatically via `inspect.getmembers`. `SchemaAccessor`/`AsyncSchemaAccessor` are already present in the `ACCESSOR_PAIRS` list (test_parity.py:31) consumed by the parametrized `test_accessor_parity` / `test_accessor_parameter_kind_parity` — also no registry edit needed. The only test-authoring work is (a) the 7 new methods' own unit/integration/injection tests, and (b) optionally a named-frozenset "surface" test (`test_crud_v120_surface` / extend `test_schema_v120_surface`) following the `test_crud_v110_surface` (test_parity.py:128) / `test_schema_v110_surface` (test_parity.py:192) precedent — recommended but not gate-enforced.

**Primary recommendation:** Implement `select_where`/`find`/`get`/`find_one`/`insert` in `database.py` + `async_database.py` (flat core, mirroring `delete_where`/`exists`/`upsert` exactly), and `column_exists`/`table_size` in `schema.py` (mirroring `table_exists`/`truncate_table`'s guard pattern), reusing `_resolve_predicate`, `_build_select_sql`, `_build_insert_sql`, and the existing `queries.TABLE_SIZE` constant verbatim. Add one new `queries.py` constant (`COLUMN_EXISTS`). No new runtime dependency, no new architecture.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `select_where`/`find` predicate read | API / Backend (flat `Database`/`AsyncDatabase` core) | Database (SQL SELECT execution) | Pure library method — no HTTP/browser tier exists in pycopg; the "backend" here is the flat transactional core that owns query building + execution |
| `get`/`find_one` single-row read | API / Backend | Database | Same tier as above — a thin `LIMIT 1` specialization of `select_where` |
| single-row `insert` | API / Backend | Database | Mirrors `upsert`'s tier — builder in `base.py` (`QueryMixin`), execution in `database.py`/`async_database.py` |
| `column_exists` | API / Backend (`db.schema.*` accessor) | Database (`information_schema.columns` catalog) | Introspection accessors already own this responsibility (`table_exists`, `schema_exists`, `database_exists` all live here) |
| `table_size` | API / Backend (`db.schema.*` accessor) | Database (`pg_total_relation_size` catalog function) | Same tier as `row_count` — `db.schema.*` is the introspection namespace; `db.maint.*` already owns a *different*, pretty-formatting table-size helper (see Pitfall 1) |

pycopg has no browser/SSR/CDN tiers — it is a single-tier Python library wrapping psycopg3. All 5 capabilities land in the same "API/Backend" tier as every other flat-core/accessor method; there is no tier-misassignment risk in this phase.

## Standard Stack

### Core

No new libraries. This phase is 100% additive Python code on top of the existing stack:

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg | (already a pinned dep) | SQL execution, `dict_row` factory | Existing dependency, unchanged |

**Version verification:** N/A — no new packages. Existing `pyproject.toml` dependency set is untouched; `uv.lock` diff for this phase should be **empty** (same invariant enforced at Phase 54 release gates).

### Supporting

None — no new supporting libraries.

### Alternatives Considered

Not applicable — CONTEXT.md D-01..D-09 lock the mechanical-mirror approach; there is no design-space exploration needed. The only real "alternative" that was live-considered and rejected is documented in D-04 (strict "raise on >1 match" `.get()` semantics) and D-09 (human-readable `table_size` formatter) — both explicitly rejected by the user, not re-litigated here.

**Installation:** None — no new packages to install.

## Package Legitimacy Audit

Not applicable. This phase installs zero external packages (standing constraint: "zero new runtime dependencies", confirmed in REQUIREMENTS.md and CONTEXT.md). The Package Legitimacy Gate is skipped in its entirety.

## Live Code Verification (canonical anchors — all confirmed exact against disk)

Every anchor cited in `53-CONTEXT.md` was read directly from the live source tree. **Zero drift found.** All line numbers below are current as of this research session (2026-07-05).

### `pycopg/base.py` (`QueryMixin`)

| Symbol | Actual line | Signature (verified) | Notes |
|--------|-------------|----------------------|-------|
| `_build_insert_sql` | 168 (`@staticmethod` at 168, `def` at 169) | `_build_insert_sql(table: str, columns: list[str], schema: str = "public", on_conflict: str \| None = None) -> tuple[str, str]` | Returns `(sql_template, cols_str)`; `sql` already ends right before `RETURNING` — callers append `" RETURNING *"` themselves (see `upsert`, database.py:1007-1008) |
| `_build_batch_insert_sql` | 202-245 | n/a (not touched by this phase) | The `insert_many`/`upsert_many` builder — single-row `insert` does NOT use this |
| `_build_select_sql` | 247 (`@staticmethod`), `def` at 248 | `_build_select_sql(table: str, columns: list[str] \| None = None, schema: str = "public", where: str \| None = None, order_by: str \| None = None, limit: int \| None = None, offset: int \| None = None) -> str` | **CONFIRMED**: already accepts `columns`/`order_by`/`limit`/`offset` exactly as D-01 assumes. `columns=None` → `SELECT *`; `where` (already-resolved fragment string, NOT a dict) is appended as `WHERE {where}` only if truthy; `order_by`/`limit`/`offset` appended unconditionally when not `None`. `validate_identifiers(table, schema)` + `validate_identifiers(*columns)` (if given) run as line-1 guards. **This builder takes the ALREADY-RESOLVED where fragment as a plain string** — `select_where`/`get` must call `_resolve_predicate` first, then pass the resulting fragment string into `_build_select_sql(where=frag, ...)`, and separately track `pred_params` for the cursor call. |
| `_build_where_dict` | 299 (`@staticmethod`), `def` at 300 | `_build_where_dict(where: dict[str, Any]) -> tuple[str, list[Any]]` | Returns AND-ed `col = %s` fragment + positional params, insertion order preserved. Raises if `where` is empty (caller's job to reject) — but `_resolve_predicate` (below) already treats falsy `where` as "no source", never calls this with an empty dict. |
| `_resolve_predicate` | 328 (`@staticmethod`), `def` at **329** (matches CONTEXT exactly) | `_resolve_predicate(where: dict[str, Any] \| None, where_sql: str \| None, where_params: Sequence[Any] \| None) -> tuple[str, list[Any]]` | **CONFIRMED return contract**: empty predicate → `("", [])`. Raises `ValueError` if `where_params` given without `where_sql` (D-04 guard), if both `where` and `where_sql` given (D-02 guard), or if `where_sql` is present but blank/whitespace (D-03 guard). This is a `@staticmethod` — callable as `self._resolve_predicate(...)` or `QueryMixin._resolve_predicate(...)`; `delete_where`/`update_where`/`exists`/`count` all call it as `self._resolve_predicate(...)`. `select_where`/`get` should do the same. |
| `_build_keyset_where` | 390-438 | n/a (not touched by this phase — Phase 50 pagination builder) | Not relevant to CRUD-F04/F05/F06 |

### `pycopg/database.py` (sync flat core)

| Symbol | Actual line | Notes |
|--------|-------------|-------|
| `insert_many` | 868 (exact match) | `on_conflict: str \| None = None` kw-only passthrough shape — this is the shape D-06 wants `insert`'s `on_conflict=` to mirror |
| `upsert` | 952 (exact match) | Full body read (lines 952-1013). Builds `columns = list(row.keys())`; computes `on_conflict` from `conflict_columns`/`update_columns`; calls `self._build_insert_sql(table, columns, schema, on_conflict)` at **line 1007** (exact CONTEXT match); appends `" RETURNING *"` at line 1008; binds `params = [row[c] for c in columns]`; executes via `with self.cursor() as cur: cur.execute(sql, params); return cur.fetchone()`. **Single-row `insert` (D-06/D-07) should replicate this exact tail (build → append RETURNING → bind params-in-columns-order → `cur.fetchone()`) but skip the `conflict_columns`/`update_columns` computation** — `insert`'s `on_conflict` is a raw passthrough string (e.g. `"DO NOTHING"`), not computed from column lists. |
| `delete_where` | 1015 (exact match) | Template for predicate-consumer shape: `frag, pred_params = self._resolve_predicate(where, where_sql, where_params)`, followed by a guard (destructive-only, N/A for reads), then `validate_identifiers(table, schema)`, then SQL build + execute |
| `update_where` | 1075 (exact match) | Same predicate-consumer shape, plus a `SET` clause |
| `exists` | 1144 (exact match) | Read-that-resolves-predicate template: `frag, pred_params = self._resolve_predicate(...)`; **raises if `not frag`** (existence check needs a predicate) — this guard must NOT be copied into `select_where`/`get` per D-03 (empty predicate is legal for reads) |
| `count` | 1204 (exact match) | The one read helper that already implements "empty predicate = read all" (D-03's precedent): `if frag: ... WHERE {frag} else: pred_params = []; sql = "SELECT COUNT(*) FROM ..."` (no WHERE). **`select_where`/`get` should follow this exact `if frag / else` shape**, not `exists`'s reject-empty shape. Note `count`'s `where` is **kw-only** (`*, where: ... = None`) — CONTEXT's Claude's-Discretion note confirms `select_where`/`get`/`find`/`find_one` should instead mirror `delete_where`'s **positional-or-keyword** `where` (2nd positional arg after `table`), not `count`'s kw-only shape. |
| `fetch_one` | 1432 (exact match) | `fetch_one(self, sql: str, params: Params = None) -> dict[str, Any] \| None` — thin `cur.execute(sql, params); return cur.fetchone()`. `get`/`find_one` could delegate execution through this, or open their own cursor like `upsert`/`exists` do — **either is fine; `exists`/`count` do NOT go through `fetch_val`'s public wrapper internally for their WHERE-building logic, they build SQL then call `self.fetch_val`/inline cursor** so a `get` that builds via `_build_select_sql` + calls `self.fetch_one(sql, pred_params)` is the cleanest, most consistent composition (no separate cursor-management code needed). |
| `fetch_val` | 1453 | Not directly needed by this phase's 5 helpers, but is the execution primitive `exists`/`count` route through |
| `fetch_all` | 1475 (exact match) | `fetch_all(self, sql: str, params: Params = None) -> list[dict[str, Any]]` — thin `cur.execute` + `cur.fetchall()`/`[]`. **`select_where`/`find` should build via `_build_select_sql` + resolve predicate, then delegate to `self.fetch_all(sql, pred_params)`** — same reasoning as `get` above: reuse the existing thin execution wrapper rather than hand-rolling a new cursor block. |

**Design implication for the planner:** Because `fetch_all`/`fetch_one` already provide the "build SQL string, bind params, execute, shape result" tail, `select_where`/`find`/`get`/`find_one` can be implemented as: (1) resolve predicate via `self._resolve_predicate(where, where_sql, where_params)`, (2) build SQL via `self._build_select_sql(table, columns, schema, where=frag, order_by=order_by, limit=limit, offset=offset)` (with `get`/`find_one` forcing `limit=1` and never exposing caller `limit`/`offset` per D-05), (3) delegate to `self.fetch_all(sql, pred_params)` (or `self.fetch_one` for `get`). This is a **thinner** implementation than `delete_where`/`update_where`/`upsert`, which manage their own cursor block because they need `cur.rowcount`/`cur.fetchone()` — reads can route through the two already-public fetch wrappers instead.

### `pycopg/async_database.py` (async flat core — all call-site line numbers independently confirmed)

| Symbol | Actual line |
|--------|-------------|
| `exists` | 1033 (matches CONTEXT's "1033/1093/1987/2047 etc." citation exactly) |
| `count` | 1093 (exact match) |
| `insert_many` | 1838 |
| `upsert_many` | 1876 |
| `upsert` | 1924 (body read — identical structure to sync, `await cur.execute`/`await cur.fetchone()`) |
| `delete_where` | 1987 (exact match) |
| `update_where` | 2047 (exact match) |
| `fetch_one` | 951 |
| `fetch_all` | 994 |

Every sync method above has a byte-identical async mirror (same param shape, `await`-prefixed body) — confirms the mirroring convention holds with zero exceptions in this file.

### `pycopg/schema.py` (sync `SchemaAccessor` + async `AsyncSchemaAccessor`)

| Symbol | Actual line (sync) | Actual line (async) | Notes |
|--------|--------------------|--------------------|-------|
| `table_exists` | 336 (exact match) | 1237 | `result = self._db.execute(queries.TABLE_EXISTS, [schema, name]); return len(result) > 0` — the exact 2-line shape `column_exists` (D-08) should mirror, binding `[schema, table, column]` against a new 3-param `COLUMN_EXISTS` query |
| `row_count` | 461 (exact match) | 1313 | `result = self._db.execute(queries.ROW_COUNT, [schema, name]); return result[0]["count"] if result else 0` |
| `truncate_table` (existence guard) | 437-439 (exact match to CONTEXT's "438") | 1378-1380 | `validate_identifiers(name, schema); if not self.table_exists(name, schema=schema): raise TableNotFoundError(f"Table '{schema}.{name}' does not exist.")` — **this exact 3-line guard is what `table_size` (D-09) should copy verbatim** before running the size query |
| `TableDescription` / `describe` | 37-64, 884-958 | 1789-1863 | Not touched by this phase |

### `pycopg/queries.py` (parametrized SQL constants)

| Constant | Actual line | SQL |
|----------|-------------|-----|
| `TABLE_EXISTS` | 36 | `SELECT 1 FROM information_schema.tables WHERE table_schema = %s AND table_name = %s` |
| `GET_COLUMNS` | 56 | `SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position` |
| `ROW_COUNT` | 63 | `SELECT reltuples::bigint AS count FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = %s AND c.relname = %s` |
| `TABLE_SIZE_PRETTY` | 297 | `SELECT pg_size_pretty(pg_total_relation_size(%s)) AS size` |
| **`TABLE_SIZE`** | **301** | **`SELECT pg_total_relation_size(%s) AS size`** — **this is EXACTLY the query D-09 describes building from scratch. It already exists.** See Pitfall 1 below — reuse this constant, do not add a duplicate. |
| `TABLE_SIZES` | 305 | Per-schema batch size listing (uses `format('%I.%I', ...)`, unrelated pattern) |

**No `COLUMN_EXISTS` constant exists yet** — confirmed via grep across `queries.py`. A new constant must be added, following the `TABLE_EXISTS`/`SCHEMA_EXISTS` naming and shape convention:

```python
COLUMN_EXISTS = """
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = %s AND table_name = %s AND column_name = %s
"""
```

Recommended insertion point: immediately after `GET_COLUMNS` (queries.py:56-61), inside the existing `# TABLE QUERIES` section (queries.py:24-68) — `column_exists` is conceptually a sibling of `GET_COLUMNS`/`TABLE_EXISTS`, not a new section.

### `pycopg/exceptions.py`

`TableNotFoundError` (line 33) confirmed — a bare `PycopgError` subclass with a docstring, no custom `__init__`. Already imported in `schema.py` (line 24: `from pycopg.exceptions import TableNotFoundError`) and already raised by `truncate_table`. `table_size` (D-09) can raise it directly with no new import needed.

### `tests/test_parity.py` (parity gate mechanics)

Two independent, complementary parity checks exist — **both auto-extend for this phase's additions with zero registry edits needed**:

1. **Accessor-level** (`ACCESSOR_PAIRS`, line 24-32): a parametrized list of `(SyncClass, AsyncClass)` tuples. `(SchemaAccessor, AsyncSchemaAccessor)` is **already in this list** (line 31) — adding `column_exists`/`table_size` to both classes is automatically picked up by `test_accessor_parity` (line 36, bidirectional `inspect.getmembers` set-diff) and `test_accessor_parameter_kind_parity` (line 569, per-parameter `inspect.Parameter.kind` comparison for every shared method). **No edit to `ACCESSOR_PAIRS` needed.**
2. **Flat-core-level** (`Database`/`AsyncDatabase` directly, not accessor-wrapped): `test_all_database_public_methods_exist_in_async` (line 396, inside `class TestAsyncParity`) does the same bidirectional-ish set-diff (one direction: `db_methods - SYNC_ONLY_METHODS` must be a subset of `async_methods`) and `test_database_core_parameter_kind_parity` (line 632, standalone function) does the same per-parameter kind check for `Database`/`AsyncDatabase` shared methods. **Both auto-extend** — adding `select_where`/`find`/`get`/`find_one`/`insert` identically to both classes satisfies these gates automatically; there is no hardcoded flat-core method list to edit.

**Named "surface" tests** (`test_timescale_v080_surface`, `test_timescale_v110_surface`, `test_crud_v110_surface` (line 128), `test_schema_v090_surface` (line 158), `test_schema_v110_surface` (line 192), `test_spatial_finish_surface` (line 328)) are a **separate, non-gate-enforced convention**: a named `frozenset` of method names asserted as a subset of `inspect.getmembers(cls)` for both sync/async classes, added once per milestone/phase to catch "silently dropped or renamed method" regressions. **Recommended but not required** by the phase's success criteria — following precedent, a `test_crud_v120_surface` (flat-core methods: `select_where`, `find`, `get`, `find_one`, `insert`) and an extension to `test_schema_v110_surface`-style pattern (or a new `test_schema_v120_surface`, `column_exists`/`table_size`) would mirror `test_crud_v110_surface`/`test_schema_v110_surface` exactly.

**`@overload` stubs:** per D-02/Claude's-Discretion, `find`/`find_one` need `@overload` stubs matching `select_where`/`get` shapes so `mypy --strict` sees them as first-class. No new `Literal`-based branching return type is needed (return type is monomorphic: `list[dict]` for `select_where`/`find`, `dict | None` for `get`/`find_one`) — `@overload` here is purely to keep `find`'s delegating signature visible to static analysis with the exact same param shape as `select_where`, not for polymorphic return narrowing (contrast with the `into=` triplet overloads used in `spatial.py`/`timescale.py`/`schema.py.describe`).

### `tests/test_sql_injection.py` (injection-test-per-helper convention)

Confirmed as the canonical location (not `test_database.py`). Structure:
- `EVIL_IDENTIFIERS` (line 23-29): a shared list of 5 malicious identifier payloads (`"users; DROP TABLE users; --"`, `'x"; DROP TABLE y; --'`, `"a' OR '1'='1"`, `"schema.table"` (dotted), `"tab le"` (space))
- `sync_db`/`async_db` fixtures (line 32-80): mock the psycopg connection layer; a real `SchemaAccessor`/`AsyncSchemaAccessor` is attached with only `has_extension` stubbed (needed for `SpatialAccessor.__init__`'s PostGIS guard — irrelevant to this phase but the fixture is shared)
- `class TestSyncIdentifierInjection` / `TestAsyncIdentifierInjection` (line 83, 179): `@pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)` tests asserting `InvalidIdentifierError` is raised before any SQL reaches the mock
- `class TestSyncValueInjection` / `TestAsyncValueInjection` (line 135, 217): asserts *values* (not identifiers) are bound as `%s` params, never interpolated
- `class TestWhereSqlValueInjection` (line 262): specifically tests the `where_sql`/`where_params` escape hatch — **this is the exact class new `select_where`/`get` tests should extend**, following the existing `test_where_sql_params_bound_sync`/`_async` pattern (line 273, 299) already covering `delete_where`/`update_where`/`exists`/`count`

**New tests needed for this phase** (both sync + async, following the file's existing per-class organization):
- `select_where`/`find`/`get`/`find_one`: table/schema/`columns=` identifier injection (`TestSyncIdentifierInjection`/`TestAsyncIdentifierInjection`), `where_sql`/`where_params` value-binding (`TestWhereSqlValueInjection`) — `order_by=` is a **caller-authored raw SQL fragment** like `where_sql` (per `_build_select_sql`'s signature — it takes a plain string, not a column list, and does NOT run `validate_identifiers` on it), so it needs its own documented-escape-hatch treatment/test, analogous to `where_sql`.
- single-row `insert`: table/schema/column-name (from `row.keys()`) identifier injection (mirrors `insert_many`'s existing `test_insert_many_column_injection`, line 250)
- `column_exists`: table/schema/column identifier injection (mirrors `test_drop_index`-style tests, line 87)
- `table_size`: table/schema identifier injection (mirrors `table_exists`)

## Architecture Patterns

### System Architecture Diagram

```
Caller (application code)
    │
    ├─► db.select_where(table, where={...} | where_sql=..., where_params=..., columns=, order_by=, limit=, offset=)
    │       │
    │       ├─► self._resolve_predicate(where, where_sql, where_params)  [base.py:329]
    │       │       └─► ("", [])  if no predicate  (D-03: legal, read-all)
    │       │       └─► (frag, params)  from _build_where_dict or verbatim where_sql
    │       │
    │       ├─► self._build_select_sql(table, columns, schema, where=frag, order_by, limit, offset)  [base.py:248]
    │       │       └─► validate_identifiers(table, schema[, *columns])
    │       │       └─► "SELECT {cols} FROM {schema}.{table} [WHERE {frag}] [ORDER BY ...] [LIMIT n] [OFFSET n]"
    │       │
    │       └─► self.fetch_all(sql, params)  [database.py:1475]
    │               └─► cursor.execute(sql, params) → cursor.fetchall() → list[dict]
    │
    ├─► db.get(table, where=..., columns=, order_by=)     [same path, limit forced to 1, fetch_one instead of fetch_all]
    │
    ├─► db.find(table, ...) ──delegates──► db.select_where(table, ...)   [D-02: real delegating twin, not alias]
    ├─► db.find_one(table, ...) ──delegates──► db.get(table, ...)
    │
    ├─► db.insert(table, row, *, schema, on_conflict=None)
    │       ├─► columns = list(row.keys())
    │       ├─► self._build_insert_sql(table, columns, schema, on_conflict)  [base.py:169, upsert's exact path]
    │       ├─► sql += " RETURNING *"
    │       └─► cursor.execute(sql, [row[c] for c in columns]) → cursor.fetchone() → dict | None
    │
    └─► db.schema.column_exists(table, column, *, schema)
            └─► self._db.execute(queries.COLUMN_EXISTS, [schema, table, column])  [new constant]
            └─► len(result) > 0
    └─► db.schema.table_size(name, *, schema)
            ├─► if not self.table_exists(name, schema=schema): raise TableNotFoundError  [schema.py:437-439 guard, mirrored]
            └─► self._db.execute(queries.TABLE_SIZE, [f"{schema}.{name}"])  [REUSE existing constant, queries.py:301]
            └─► int(result[0]["size"])
```

Every arrow above terminates in already-shipped, tested infrastructure (`_resolve_predicate`, `_build_select_sql`, `_build_insert_sql`, `fetch_all`/`fetch_one`, `table_exists`, `queries.TABLE_SIZE`). No new SQL-building logic is required — this phase is pure composition.

### Recommended Project Structure

No new files or directories. All changes are additions to existing files:

```
pycopg/
├── database.py        # + select_where, find, get, find_one, insert (sync flat core)
├── async_database.py   # + async mirrors of the above 5 methods
├── schema.py           # + column_exists, table_size (SchemaAccessor + AsyncSchemaAccessor)
├── queries.py          # + COLUMN_EXISTS constant (reuse existing TABLE_SIZE for table_size)
├── base.py             # unchanged — _resolve_predicate/_build_select_sql/_build_insert_sql reused verbatim
└── exceptions.py        # unchanged — TableNotFoundError reused verbatim

tests/
├── test_database.py            # unit tests for select_where/find/get/find_one/insert (sync)
├── test_async_database.py       # unit tests for the async mirrors
├── test_database_integration.py # live-DB integration tests (predicate reads, RETURNING *, column_exists/table_size against a real table)
├── test_async_database.py       # (also carries async integration tests per existing convention)
├── test_sql_injection.py        # + injection tests per new helper (both sync+async classes)
└── test_parity.py               # optional: test_crud_v120_surface / test_schema_v120_surface named frozensets
```

### Pattern 1: Predicate-read composition (`select_where`/`find`, `get`/`find_one`)

**What:** Resolve predicate → build SELECT → delegate to existing fetch wrapper.
**When to use:** Any read helper needing the dict-or-raw-SQL predicate surface.
**Example (sync, mirrors `count`'s empty-predicate-allowed shape, NOT `exists`'s reject-empty shape):**
```python
# Source: pycopg/database.py:1204 (count) + base.py:248 (_build_select_sql) + base.py:329 (_resolve_predicate)
def select_where(
    self,
    table: str,
    where: dict[str, Any] | None = None,
    *,
    where_sql: str | None = None,
    where_params: Sequence[Any] | None = None,
    columns: list[str] | None = None,
    order_by: str | None = None,
    limit: int | None = None,
    offset: int | None = None,
    schema: str = "public",
) -> list[dict[str, Any]]:
    frag, pred_params = self._resolve_predicate(where, where_sql, where_params)
    sql = self._build_select_sql(
        table, columns, schema, where=frag or None,
        order_by=order_by, limit=limit, offset=offset,
    )
    return self.fetch_all(sql, pred_params)
```
Note: `_build_select_sql`'s `where` param only appends `WHERE {where}` when truthy (base.py:288 `if where:`) — passing `frag` (which is `""` when no predicate) directly works, but passing `frag or None` is more explicit/defensive; either is correct because `""` is falsy in the `if where:` check.

### Pattern 2: Single-row insert (mirrors `upsert` minus conflict-column computation)

**What:** Build INSERT with `on_conflict` passthrough, append `RETURNING *`, fetch one row.
**When to use:** `insert`'s exact shape — D-06/D-07.
**Example:**
```python
# Source: pycopg/database.py:952-1013 (upsert), reusing _build_insert_sql at the same call site as database.py:1007
def insert(
    self,
    table: str,
    row: dict[str, Any],
    *,
    schema: str = "public",
    on_conflict: str | None = None,
) -> dict[str, Any] | None:
    columns = list(row.keys())
    sql, _ = self._build_insert_sql(table, columns, schema, on_conflict)
    sql += " RETURNING *"
    params = [row[c] for c in columns]
    with self.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()
```

### Pattern 3: Guarded introspection scalar (`table_size`, mirrors `truncate_table`'s guard + reuses existing `TABLE_SIZE` constant)

**What:** Existence guard (raise `TableNotFoundError`) then a bound scalar query.
**When to use:** `table_size` — D-09.
**Example:**
```python
# Source: pycopg/schema.py:436-441 (truncate_table's guard) + pycopg/queries.py:301 (TABLE_SIZE, already exists)
def table_size(self, name: str, *, schema: str = "public") -> int:
    validate_identifiers(name, schema)
    if not self.table_exists(name, schema=schema):
        raise TableNotFoundError(f"Table '{schema}.{name}' does not exist.")
    result = self._db.execute(queries.TABLE_SIZE, [f"{schema}.{name}"])
    return int(result[0]["size"])
```

### Anti-Patterns to Avoid

- **Adding a duplicate `TABLE_SIZE`-shaped constant for `db.schema.table_size`:** `queries.TABLE_SIZE` (queries.py:301) already runs `pg_total_relation_size(%s)`. Reuse it — do not write a second, near-identical constant under a different name (e.g. `SCHEMA_TABLE_SIZE`).
- **Copying `exists`'s "reject empty predicate" guard into `select_where`/`get`:** D-03 is explicit — empty predicate is legal for reads. Only `delete_where`/`update_where`/`exists` (destructive or meaningless-without-predicate) reject it.
- **Hand-rolling a new cursor-management block for `select_where`/`find`/`get`/`find_one`:** `fetch_all`/`fetch_one` already exist as public methods on the same class — delegate to them instead of duplicating `with self.cursor() as cur: cur.execute(...); return cur.fetchall()`.
- **Running `validate_identifiers` over `where_sql`, `order_by`, or the values inside `where_params`:** these are documented, intentional escape hatches passed through verbatim (per `_resolve_predicate`'s own docstring, base.py:340-345). Only `table`/`schema`/`columns`/dict-`where` keys are identifiers subject to validation.
- **Using `@deprecated_alias` or PEP 562 module-level `__getattr__` for `find`/`find_one`:** explicitly rejected by D-02 — both machineries were hard-removed in v0.7.0/reserved for the exception-rename use case respectively. `find`/`find_one` are real, first-class, concrete methods.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Predicate resolution (dict WHERE vs raw SQL) | A new mini-parser or second `_resolve_predicate`-like function | `QueryMixin._resolve_predicate` (base.py:329) | Already handles D-02/D-03/D-04 mutual-exclusion guards, already tested by `test_where_sql_params_bound_sync`/`_async` |
| SELECT SQL string assembly (columns/order/limit/offset) | A new SELECT builder | `QueryMixin._build_select_sql` (base.py:248) | Already accepts every param D-01 needs; identifier validation baked in |
| INSERT ... RETURNING * SQL assembly | A new single-row insert builder | `QueryMixin._build_insert_sql` (base.py:169) — the exact function `upsert` calls at database.py:1007 | Handles `on_conflict` clause + placeholder generation + identifier validation already |
| Table-size byte count query | A new `pg_total_relation_size` SQL constant | `queries.TABLE_SIZE` (queries.py:301) | Already exists, already bound correctly (`%s` text arg, implicit `regclass` cast) — verified byte-identical to what D-09 describes |
| Table-existence guard before a destructive/size op | A new existence check inline | `self.table_exists(name, schema=schema)` (schema.py:336) + the exact 3-line raise pattern from `truncate_table` (schema.py:437-439) | Already the established idiom for "guard, then raise `TableNotFoundError`" |

**Key insight:** This phase has essentially zero "don't hand-roll" risk because CONTEXT.md's D-01..D-09 already point at every reusable builder by name and line number, and this research confirms every one of those pointers is accurate. The only genuinely new code is: 5 thin method bodies (mostly 3-6 lines each) + 1 new `queries.py` constant (`COLUMN_EXISTS`) + docstrings + tests.

## Common Pitfalls

### Pitfall 1: `db.maint.table_size` already exists with different semantics — naming collision risk in docs/mental model, not in Python

**What goes wrong:** A developer (or future contributor) searching the codebase for "table_size" will find TWO methods: `db.maint.table_size(table, *, schema="public", pretty=True) -> str | int` (existing, `maint.py:73`, no existence guard, returns human-readable size by default) and the new `db.schema.table_size(name, *, schema="public") -> int` (this phase, raises `TableNotFoundError` on missing table, always raw bytes). There is **no Python namespace collision** (different accessor classes, `db.maint.table_size` vs `db.schema.table_size`), but it is a genuine API-surface duplication that could confuse users and reviewers.
**Why it happens:** `db.maint.*` (size/vacuum/analyze/explain, moved verbatim in the v0.6.0 accessor reorganisation) already owned "size" queries before `db.schema.*` grew its own introspection family (`row_count`, and now `column_exists`/`table_size`). The two accessors' responsibilities partially overlap by historical accident, not by current design intent.
**How to avoid:** This is explicitly **not a blocker** — D-09 is a locked decision and the roadmap explicitly frames `table_size` as "complementing `row_count`" (both live in `db.schema.*`, the introspection accessor). The planner should simply (a) confirm the new method's docstring cross-references `db.maint.table_size` for the pretty-printed/optional-guard alternative (numpydoc "See Also" section, matching existing cross-reference conventions elsewhere in the codebase), and (b) NOT attempt to deduplicate or remove `db.maint.table_size` — that would be an out-of-scope breaking change under frozen SemVer 1.0. Flag this in the phase's docs update (Phase 54 will also touch `docs/api-reference.md`, which already has a "Size/Stats Methods" section (line 369) — the new `db.schema.table_size` entry should go under "Introspection Methods (v1.2.0)" near `row_count`, not under "Size/Stats Methods").
**Warning signs:** A code reviewer or the plan-checker flags "duplicate table_size definition" — this is a false positive; verify the two are in different accessor classes (`SchemaAccessor` vs `MaintAccessor`) before treating it as an error.

### Pitfall 2: `_build_select_sql`'s `where` parameter is a pre-resolved fragment STRING, not a dict

**What goes wrong:** A naive implementation might try to pass the raw `where` dict argument straight into `_build_select_sql(where=where)`, expecting it to call `_build_where_dict` internally. It does not — `_build_select_sql`'s `where: str | None` parameter expects an already-resolved SQL fragment (base.py:267-268 docstring: "WHERE clause (without WHERE keyword)").
**Why it happens:** The two-stage pipeline (`_resolve_predicate` → fragment string → `_build_select_sql`) is not obvious from `_build_select_sql`'s signature alone; you have to read `_resolve_predicate`'s call sites in `delete_where`/`count` to see the expected composition.
**How to avoid:** Always call `self._resolve_predicate(where, where_sql, where_params)` FIRST to get `(frag, pred_params)`, then pass `where=frag` (or `frag or None`) into `_build_select_sql`, and separately bind `pred_params` to the cursor/`fetch_all` call. Never pass the raw `where` dict into `_build_select_sql`.
**Warning signs:** A `TypeError` or malformed SQL (`WHERE {'col': 'val'}`) at runtime if the dict is passed directly and f-string-interpolated somewhere.

### Pitfall 3: `order_by` on `select_where`/`get` is a caller-authored raw string — same trust model as `where_sql`, needs its own docstring warning + injection test

**What goes wrong:** `_build_select_sql`'s `order_by: str | None` parameter is appended verbatim as `f" ORDER BY {order_by}"` (base.py:290-291) with **no identifier validation** — unlike `columns`, which IS validated (base.py:282-283 `if columns: validate_identifiers(*columns)`). If a caller passes user-controlled input as `order_by` without validating it themselves, this is an injection vector identical in shape to `where_sql`.
**Why it happens:** `order_by` was designed as a flexible escape hatch (supports `"col1 DESC, col2 ASC"` compound expressions, which a validated identifier list cannot express) — the same design tradeoff as `where_sql`, but it is easy to overlook because D-01 doesn't call this out explicitly the way D-02/D-03/D-04 do for `where_sql`.
**How to avoid:** Document `order_by` in the new methods' docstrings with the same "caller owns this SQL text, not validated" language used for `where_sql` (see `delete_where`'s docstring, database.py:1035-1042, as the template). Add an injection test class or extend `TestWhereSqlValueInjection` to cover `order_by` — confirming it is NOT rejected by `InvalidIdentifierError` for typical multi-column syntax, and that the documented trust boundary is intentional, not a gap.
**Warning signs:** A future security audit (this project runs periodic threat-model passes, see STATE.md "SECURED" phase closures) flags `order_by` as an unvalidated injection surface if the docstring doesn't already document it as an intentional escape hatch.

### Pitfall 4: `get`/`find_one` must NOT expose `limit`/`offset` per D-05 — but the underlying `_build_select_sql` call still needs `limit=1` passed internally

**What goes wrong:** A naive "just delegate to `select_where`" implementation for `get` might accidentally forward a caller-supplied `limit`/`offset` if the delegation isn't careful about which kwargs are exposed at the public signature level vs which are hardcoded internally.
**Why it happens:** D-04/D-05 want `get`/`find_one` to force `LIMIT 1` server-side without exposing a caller `limit=`/`offset=` — a signature-shape decision, not a builder-capability limitation (the builder happily accepts any `limit`).
**How to avoid:** `get`'s public signature should simply not declare `limit`/`offset` parameters at all (only `where`/`where_sql`/`where_params`/`columns`/`order_by`/`schema`), and internally call `self._build_select_sql(..., limit=1, offset=None)` unconditionally. Do NOT implement `get` as a thin wrapper calling `self.select_where(..., limit=1)[0:1]` (Python-side truncation) — push `LIMIT 1` into the SQL itself (matches D-04's "append LIMIT 1" language) so the database does the row-limiting, not Python.
**Warning signs:** `mypy --strict`/`test_accessor_parameter_kind_parity` won't catch this (it's a semantic bug, not a signature bug) — a live-DB integration test with >1 matching row and an `order_by` is the actual verification (assert the returned row is deterministically the first per `order_by`, not an arbitrary one).

## Code Examples

### Reusing `_resolve_predicate` in a new read helper (verified pattern from `count`, database.py:1252-1259)

```python
# Source: pycopg/database.py:1204-1259 (count) — the ONE existing read helper with
# "empty predicate = read all" semantics; select_where/find/get/find_one must copy
# this if/else shape, NOT exists's "raise on empty" shape (database.py:1193-1202).
validate_identifiers(table, schema)
frag, pred_params = self._resolve_predicate(where, where_sql, where_params)
if frag:
    sql = f"SELECT COUNT(*) FROM {schema}.{table} WHERE {frag}"
else:
    pred_params = []
    sql = f"SELECT COUNT(*) FROM {schema}.{table}"
return int(self.fetch_val(sql, pred_params))
```

### The exact `upsert` tail single-row `insert` must replicate (database.py:1007-1013)

```python
# Source: pycopg/database.py:1007-1013 — insert (D-06/D-07) reuses this exact
# build → RETURNING → bind → fetchone tail, just without the conflict_columns/
# update_columns computation that precedes it in upsert.
sql, _ = self._build_insert_sql(table, columns, schema, on_conflict)
sql += " RETURNING *"
params = [row[c] for c in columns]

with self.cursor() as cur:
    cur.execute(sql, params)
    return cur.fetchone()
```

### `truncate_table`'s existence guard — the exact 3 lines `table_size` (D-09) must copy (schema.py:437-439)

```python
# Source: pycopg/schema.py:437-439
validate_identifiers(name, schema)
if not self.table_exists(name, schema=schema):
    raise TableNotFoundError(f"Table '{schema}.{name}' does not exist.")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| No predicate-based read helper on the flat core (only `execute`/`fetch_all` with hand-written SQL, or `delete_where`/`update_where`/`exists`/`count` for non-SELECT-all operations) | `select_where`/`find`/`get`/`find_one` complete the CRUD-read symmetry | This phase (v1.2.0, Phase 53) | Users can now do `db.select_where("users", {"active": True}, order_by="created_at DESC", limit=10)` instead of hand-writing SQL for the common filter+order+cap case |
| No single-row `insert` with `RETURNING *` (only `insert_many`/`upsert`, both requiring a list-of-rows or conflict-column args even for a single row) | `insert(table, row, *, on_conflict=None)` | This phase | Symmetric with `upsert`; no more forcing a 1-element list through `insert_many` to get `RETURNING *` behavior |
| `db.schema.*` existence family (`table_exists`/`schema_exists`/`database_exists`) missing column-level granularity | `column_exists` added | This phase | Completes the existence-check family — matches the pattern already established by 3 sibling methods |
| `db.schema.row_count` (approximate row count via `pg_stat`) with no size counterpart in the SAME accessor | `db.schema.table_size` (raw bytes via `pg_total_relation_size`) | This phase | `db.schema.*` — the introspection accessor — now has both row-count and byte-size, matching the "row_count + table_size" pairing implied by the roadmap's own framing ("complementing row_count") |

**Deprecated/outdated:** Nothing in this phase deprecates or replaces any shipped method — 100% additive under frozen SemVer 1.0, consistent with the milestone character stated in REQUIREMENTS.md.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `order_by` should be documented/tested with the same "caller-owned, unvalidated escape hatch" language as `where_sql`, rather than treated as requiring `validate_identifiers` | Pitfall 3, Anti-Patterns | LOW — this is a documentation/test-coverage recommendation, not a code-behavior claim; the underlying `_build_select_sql` behavior (no validation on `order_by`) is directly verified from source, not assumed. If the planner decides to add validation instead, that is a valid alternative implementation choice, not a correctness bug either way. |
| A2 | A `test_crud_v120_surface` / `test_schema_v120_surface`-style named-frozenset test is "recommended but not required" | Architecture Patterns / test_parity.py section | LOW — this is a stylistic-convention judgment call based on precedent (4 prior "surface" tests exist, none are referenced by the phase's 5 success criteria or REQUIREMENTS.md's standing bar). If the planner treats it as mandatory instead, no harm — it's strictly additive test coverage following an established pattern. |

**If this table is empty:** N/A — two low-risk stylistic assumptions are logged above; every functional/mechanical claim in this research (line numbers, signatures, return contracts, SQL constants, parity-gate mechanics, exception classes) was directly read from the live source tree in this session, not inferred from training data.

## Open Questions

1. **Should `table_size`'s docstring cross-reference `db.maint.table_size`?**
   - What we know: The two methods coexist without a Python namespace collision (Pitfall 1); D-09 is locked and does not mention `db.maint.table_size` at all.
   - What's unclear: Whether the planner/executor should add a numpydoc "See Also" cross-reference, given this project's established docstring conventions (several existing methods do cross-reference siblings, e.g. `fetch_all`'s docstring references `fetch_one`).
   - Recommendation: Low-stakes stylistic addition — recommend including a one-line "See Also: `db.maint.table_size` for a human-readable/pretty-printed alternative" note, but this is not a blocking decision; either way the phase's 5 success criteria are satisfied.

2. **Does `find`/`find_one`'s `@overload` stub need to exactly duplicate `select_where`/`get`'s parameter list, or can it use `*args, **kwargs` forwarding with a single overload?**
   - What we know: D-02 requires `find`/`find_one` to be "real delegating twins... with an **identical** signature" and "matching `@overload` stubs so `mypy --strict` and the parity gate see them as first-class methods". The codebase's existing `@overload` usage (`describe`, spatial `into=` triplets) is for polymorphic-return-type narrowing, a different use case (monomorphic delegation here).
   - What's unclear: The exact minimal `@overload` shape needed — since `find`'s return type never varies (`list[dict]` always), a single concrete `def find(...) -> list[dict[str, Any]]:` with the SAME parameter list as `select_where` (fully spelled out, not `*args`/`**kwargs`) may not need `@overload` at all — `@overload` is typically reserved for functions whose return type depends on an input value (`Literal` dispatch). A plain concrete signature match may already satisfy both `mypy --strict` and the parity gate.
   - Recommendation: Planner should verify empirically whether a concrete (non-overloaded) `find`/`find_one` definition satisfies `mypy --strict` before assuming `@overload` stubs are structurally required — CONTEXT.md's mention of `@overload` may be describing the general v1.0-era convention rather than a strict requirement for this specific monomorphic case. Either approach (plain concrete signature, or `@overload` + implementation) satisfies the parity gate; the choice affects only mypy-strict cleanliness, which is empirically verifiable during implementation (run `uv run mypy` after writing the delegating body).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL server | Live-DB integration tests for all 7 new methods | ✓ | Running (`pg_isready` confirmed: "accepting connections" on 5432) | — |
| `pycopg_test3` DB | Integration tests (per MEMORY.md — `pycopg_test`/`pycopg_test2` are broken by TimescaleDB `.so` version drift) | Not independently re-verified this session; documented as working in memory notes | — | Run all DB tests with `PGDATABASE=pycopg_test3` per established project convention |
| uv / Python 3.11-3.13 | Dev environment | Assumed present (standard project setup, unchanged by this phase) | — | — |

**Missing dependencies with no fallback:** None identified for this phase — no new external dependency required.

**Missing dependencies with fallback:** None beyond the already-documented `PGDATABASE=pycopg_test3` DB-selection workaround (carried forward from prior phases, not new to this research).

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (pinned via `uv sync --all-extras --dev`), `pytest-cov` for coverage |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` (line 95): `testpaths = ["tests"]`, `addopts = "-v --cov=pycopg --cov-report=term-missing --cov-report=html --cov-fail-under=95"` |
| Quick run command | `uv run pytest tests/test_database.py tests/test_async_database.py tests/test_sql_injection.py -x -q -o addopts=""` (bypass coverage gate for a fast targeted run; use `PGDATABASE=pycopg_test3` prefix for any test touching a real connection) |
| Full suite command | `PGDATABASE=pycopg_test3 uv run pytest` (full suite + coverage ratchet ≥95%, per project convention) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CRUD-F04 | `select_where`/`find` return `list[dict]` filtered by dict `where` | unit (mocked) | `pytest tests/test_database.py -k select_where -x` | ❌ Wave 0 — new test method needed in `test_database.py`/`test_async_database.py` |
| CRUD-F04 | `select_where`/`find` support `where_sql`/`where_params` raw escape hatch | unit + injection | `pytest tests/test_sql_injection.py -k select_where -x` | ❌ Wave 0 — extend `TestWhereSqlValueInjection` |
| CRUD-F04 | `select_where`/`find` honor `columns=`/`order_by=`/`limit=`/`offset=`, empty predicate = read-all | integration (live DB) | `PGDATABASE=pycopg_test3 pytest tests/test_database_integration.py -k select_where -x` | ❌ Wave 0 |
| CRUD-F05 | `get`/`find_one` return `dict \| None`, `LIMIT 1` on >1 match, no raise | unit + integration | `PGDATABASE=pycopg_test3 pytest tests/test_database_integration.py -k "test_get or test_find_one" -x` | ❌ Wave 0 |
| CRUD-F06 | `insert` single row returns `RETURNING *` dict; `on_conflict="DO NOTHING"` + pre-existing conflict → `None` | integration (live DB, needs a real UNIQUE constraint to trigger DO NOTHING no-row path) | `PGDATABASE=pycopg_test3 pytest tests/test_database_integration.py -k test_insert -x` | ❌ Wave 0 |
| INTRO-F03 | `column_exists` true/false for existing/missing column | unit (mocked) + integration | `pytest tests/test_database.py -k column_exists -x` | ❌ Wave 0 |
| INTRO-F04 | `table_size` raises `TableNotFoundError` on missing table, returns `int` bytes on success | unit (mocked, guard path) + integration (real byte count > 0 for a populated table) | `PGDATABASE=pycopg_test3 pytest tests/test_database_integration.py -k table_size -x` | ❌ Wave 0 |
| (all) | sync/async parity — no manual test needed, auto-enforced | automated gate | `pytest tests/test_parity.py -x` | ✅ Exists — `test_accessor_parity`, `test_accessor_parameter_kind_parity`, `test_all_database_public_methods_exist_in_async`, `test_database_core_parameter_kind_parity` all auto-extend; zero registry edits needed |
| (all) | injection guards on every new identifier param | automated (per-helper) | `pytest tests/test_sql_injection.py -x` | ❌ Wave 0 — new parametrized test methods needed, extending existing `TestSyncIdentifierInjection`/`TestAsyncIdentifierInjection`/`TestWhereSqlValueInjection` classes |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_database.py tests/test_async_database.py tests/test_sql_injection.py -x -q -o addopts=""` (fast, mocked-DB subset)
- **Per wave merge:** `PGDATABASE=pycopg_test3 uv run pytest tests/test_database_integration.py tests/test_parity.py -x -q -o addopts=""` (live-DB + parity gates)
- **Phase gate:** `PGDATABASE=pycopg_test3 uv run pytest` full suite green (cov ≥95%, currently 96.78% baseline) before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_database.py` — unit tests (mocked psycopg) for `select_where`/`find`/`get`/`find_one`/`insert` covering param-shape and empty-predicate-read-all behavior
- [ ] `tests/test_async_database.py` — async mirrors of the above
- [ ] `tests/test_database_integration.py` (+ async counterpart section) — live-DB behavioral tests: predicate filtering, `order_by`/`limit`/`offset` correctness, `RETURNING *` shape, `on_conflict="DO NOTHING"` → `None` path, `column_exists` true/false, `table_size` guard + real byte count
- [ ] `tests/test_sql_injection.py` — new parametrized injection tests for all 5 new identifier-accepting call sites (table/schema/columns for reads, table/schema/row-keys for insert, table/schema/column for `column_exists`, table/schema for `table_size`) — both sync and async
- [ ] `pycopg/schema.py` — add `COLUMN_EXISTS` to `queries.py` (no framework gap, just a missing constant)
- [ ] Optional: `tests/test_parity.py` — `test_crud_v120_surface` / a `test_schema_v120_surface` extension (named frozenset), following the `test_crud_v110_surface` (line 128) / `test_schema_v110_surface` (line 192) precedent

*(Framework itself is fully present — pytest + coverage + parity harness all exist and require no new install.)*

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | no | Not touched by this phase — no auth surface |
| V3 Session Management | no | Not touched |
| V4 Access Control | no | Not touched — pycopg is a library, not a service with its own authz layer |
| V5 Input Validation | **yes** | `validate_identifiers` (pycopg/utils.py:120) for every table/schema/column-name identifier; all user *values* (dict-`where` values, `where_params`, inserted row values) bound as `%s` positional params via psycopg — never string-interpolated |
| V6 Cryptography | no | Not touched — no new crypto surface |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| SQL injection via table/schema/column identifiers | Tampering | `validate_identifiers`/`validate_identifier` (pycopg/utils.py) — regex-based allowlist (letters/digits/underscore, must start with letter/underscore), rejects reserved words; called as line-1 (or near-line-1) guard in every new builder, per the project's established "validate_identifiers-first" convention |
| SQL injection via bound values (`where` dict values, `where_params`, inserted `row` values) | Tampering | Never string-interpolated — always passed as a params list/tuple to `cursor.execute(sql, params)`, letting psycopg's server-side parameter binding neutralize injection |
| SQL injection via the intentional `where_sql`/`order_by` raw-SQL escape hatches | Tampering | **By design, NOT validated** — these are documented, caller-owned escape hatches (per `_resolve_predicate`'s docstring, base.py:340-345). The security boundary is: the SQL *text* is trusted (caller-authored, like any hand-written query string elsewhere in the codebase), but any *values* interpolated into that text by the caller must themselves be passed via `where_params`/bound `%s` placeholders — this is the same trust model already accepted for `execute`/`fetch_all`'s raw `sql` parameter. Pitfall 3 flags that `order_by` needs this same documented-and-tested treatment, since it currently lacks an explicit test/docstring callout unlike `where_sql`. |
| Denial-of-service via unbounded reads (`select_where` with no `limit`) | — (not a STRIDE injection category, but a robustness concern) | Not mitigated by this phase — D-03 explicitly allows unbounded reads (mirrors `count()`'s existing no-predicate-count-all behavior); callers needing paging should use the already-shipped `paginate`/`paginate_page`/`paginate_keyset` (Phase 34/50). This is a documented, intentional non-goal, not a gap. |

## Sources

### Primary (HIGH confidence — all read directly from the live repository in this session)

- `/home/loc/workspace/pycopg/pycopg/base.py` — `QueryMixin._resolve_predicate`, `_build_where_dict`, `_build_select_sql`, `_build_insert_sql`, `_build_batch_insert_sql`, `_build_keyset_where` (full bodies read, lines 1-745)
- `/home/loc/workspace/pycopg/pycopg/database.py` — `insert_many`, `upsert_many`, `upsert`, `delete_where`, `update_where`, `exists`, `count`, `fetch_one`, `fetch_val`, `fetch_all` (lines 840-1518 read in full)
- `/home/loc/workspace/pycopg/pycopg/async_database.py` — line-number confirmation for all sync mirrors + `upsert`/`delete_where` body verification
- `/home/loc/workspace/pycopg/pycopg/schema.py` — full file read (1864 lines): `SchemaAccessor`/`AsyncSchemaAccessor`, `table_exists`, `row_count`, `truncate_table`, `describe`/`TableDescription`
- `/home/loc/workspace/pycopg/pycopg/queries.py` — `TABLE_EXISTS`, `GET_COLUMNS`, `ROW_COUNT`, `TABLE_SIZE`, `TABLE_SIZE_PRETTY`, `TABLE_SIZES`, `DATABASE_SIZE`/`DATABASE_SIZE_PRETTY` constants (confirmed no existing `COLUMN_EXISTS`)
- `/home/loc/workspace/pycopg/pycopg/exceptions.py` — full file read: `TableNotFoundError`, `PycopgError` hierarchy, `_DEPRECATED_NAMES` PEP 562 mechanism
- `/home/loc/workspace/pycopg/pycopg/maint.py` — `MaintAccessor.size`/`table_size`/`table_sizes` (the pre-existing `db.maint.table_size`, Pitfall 1)
- `/home/loc/workspace/pycopg/pycopg/utils.py` — `validate_identifier`/`validate_identifiers` signatures
- `/home/loc/workspace/pycopg/tests/test_parity.py` — `ACCESSOR_PAIRS`, `test_accessor_parity`, `test_accessor_parameter_kind_parity`, `test_database_core_parameter_kind_parity`, `TestAsyncParity.test_all_database_public_methods_exist_in_async`, and 6 existing "surface" test precedents
- `/home/loc/workspace/pycopg/tests/test_sql_injection.py` — full injection-test-convention read: fixtures, `EVIL_IDENTIFIERS`, all 6 test classes
- `/home/loc/workspace/pycopg/tests/test_database_integration.py` — confirmed `test_select_where` (line 108) is an unrelated raw-SQL test, no naming collision with the new `select_where` method
- `/home/loc/workspace/pycopg/pyproject.toml` — `[tool.pytest.ini_options]` config, dependency/classifier list
- `/home/loc/workspace/pycopg/.planning/phases/53-crud-symmetry-introspection-follow-ups/53-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`, `.planning/config.json`

### Secondary (MEDIUM confidence)

None — no WebSearch/external-source claims were needed for this phase; the entire research surface was resolvable from the live codebase, which is the authoritative source for a symmetry-completion phase.

### Tertiary (LOW confidence)

None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new libraries; zero-dependency claim directly verified (no `pip install`/`uv add` needed)
- Architecture: HIGH — every builder/pattern cited was read directly from disk with exact line-number confirmation; zero drift from CONTEXT.md's citations
- Pitfalls: HIGH — Pitfall 1 (`db.maint.table_size` collision) and the `queries.TABLE_SIZE` reuse finding are both directly verified via `grep`/`Read`, not inferred; Pitfalls 2-4 are derived from direct reading of `_build_select_sql`'s actual parameter-handling code

**Research date:** 2026-07-05
**Valid until:** Stable for the remainder of this phase's planning/execution window (Phase 53) — the underlying codebase is not expected to change out from under this research before Phase 53 executes. Standard 30-day validity for a stable-codebase symmetry phase; re-verify anchors if Phase 53 planning is deferred beyond a few weeks.
