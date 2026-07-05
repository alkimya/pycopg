# Phase 53: CRUD Symmetry + Introspection Follow-ups - Pattern Map

**Mapped:** 2026-07-05
**Files analyzed:** 7 (new symbols across 5 files) + 1 test file
**Analogs found:** 7 / 7 (all exact — this is a symmetry-completion phase; the mirror IS the spec)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|--------------------|------|-----------|-----------------|----------------|
| `pycopg/database.py` :: `select_where`/`find` | service (flat-core query method) | CRUD (read) | `count` (database.py:1204-1259) | exact — same predicate-resolve + "empty predicate = read all" shape |
| `pycopg/database.py` :: `get`/`find_one` | service | CRUD (read, single-row) | `select_where` (new, this phase) forced `LIMIT 1` + `count`'s empty-ok policy | exact |
| `pycopg/database.py` :: `insert` (single row) | service | CRUD (write) | `upsert` (database.py:952-1013) | exact — same `_build_insert_sql` + `RETURNING *` tail, minus conflict-column computation |
| `pycopg/async_database.py` :: async mirrors of all 5 above | service (async) | CRUD | sync counterparts in `database.py` (byte-identical shape, `await`-prefixed body); async `exists`/`count`/`upsert` at lines 1033/1093/1924 | exact |
| `pycopg/schema.py` :: `column_exists` (SchemaAccessor + AsyncSchemaAccessor) | service (introspection accessor) | request-response (scalar bool) | `table_exists` (schema.py:336-352) | exact |
| `pycopg/schema.py` :: `table_size` (SchemaAccessor + AsyncSchemaAccessor) | service (introspection accessor) | request-response (scalar int) | `truncate_table`'s existence guard (schema.py:437-439) + `row_count` (schema.py:461) | exact |
| `pycopg/queries.py` :: `COLUMN_EXISTS` constant | config (SQL constant) | n/a | `TABLE_EXISTS` (queries.py:36) / `GET_COLUMNS` (queries.py:56) | exact |
| `tests/test_sql_injection.py` :: new injection tests | test | request-response (guard verification) | `TestSyncIdentifierInjection`/`TestAsyncIdentifierInjection` (lines 83+/179+), `TestWhereSqlValueInjection` (line 262) | exact |

## Pattern Assignments

### `pycopg/database.py :: select_where` / `find` (service, CRUD-read)

**Analog:** `count` (database.py:1204-1259), builder reuse from `base.py`

**Signature/imports pattern** (mirrors `count`'s existing imports — no new imports needed; `Sequence`/`Any` already imported at top of `database.py`):
```python
def count(
    self,
    table: str,
    *,
    where: dict[str, Any] | None = None,
    where_sql: str | None = None,
    where_params: Sequence[Any] | None = None,
    schema: str = "public",
) -> int:
```
Note: per CONTEXT.md D-01/Claude's-Discretion, `select_where`/`find`/`get`/`find_one` must use `delete_where`'s **positional-or-keyword** `where` (2nd positional arg), NOT `count`'s kw-only `where` — copy the empty-predicate-legal *logic* from `count`, but the *signature shape* (positional `where`) from `delete_where` (database.py:1015).

**Core predicate-resolve + read-all pattern** (database.py:1193-1202, contrast pair — `exists` REJECTS empty, `select_where` must NOT):
```python
# exists (database.py:1193-1202) — DO NOT copy this guard into select_where/get:
frag, pred_params = self._resolve_predicate(where, where_sql, where_params)
if not frag:
    raise ValueError(
        "exists requires a non-empty `where` dict or `where_sql` "
        "fragment — an existence check with no predicate is "
        "meaningless."
    )
validate_identifiers(table, schema)
sql = f"SELECT EXISTS(SELECT 1 FROM {schema}.{table} WHERE {frag})"
return bool(self.fetch_val(sql, pred_params))
```
`count`'s if/else shape (the one to copy, D-03's precedent) is documented at RESEARCH.md lines 353-358: `if frag: ... WHERE {frag} else: pred_params = []; sql = "SELECT ... FROM ..."` (no WHERE).

**Recommended composition for `select_where`/`find`** (RESEARCH.md Pattern 1, verified against `_build_select_sql` base.py:248 and `fetch_all` database.py:1475):
```python
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
`find` = a real concrete `def find(...)` delegating to `select_where` with an identical param list (D-02 — NOT `@deprecated_alias`, NOT a PEP 562 module alias; both machineries are reserved/removed for other uses).

**Pitfall guard (must carry into docstring + test):** `_build_select_sql`'s `where` param is a pre-resolved fragment STRING (base.py:267-268 docstring: "WHERE clause without the WHERE keyword") — never pass the raw dict. `order_by` is appended verbatim with NO `validate_identifiers` call (base.py:290-291) — same trust model as `where_sql`; document and injection-test it identically (RESEARCH.md Pitfall 3).

---

### `pycopg/database.py :: get` / `find_one` (service, CRUD-read single-row)

**Analog:** `select_where` (this phase) + D-04's forced `LIMIT 1`, `count`'s empty-ok policy

**Core pattern (D-04/D-05 — force LIMIT 1 server-side, do NOT expose caller `limit`/`offset`, do NOT Python-side-truncate):**
```python
def get(
    self,
    table: str,
    where: dict[str, Any] | None = None,
    *,
    where_sql: str | None = None,
    where_params: Sequence[Any] | None = None,
    columns: list[str] | None = None,
    order_by: str | None = None,
    schema: str = "public",
) -> dict[str, Any] | None:
    frag, pred_params = self._resolve_predicate(where, where_sql, where_params)
    sql = self._build_select_sql(
        table, columns, schema, where=frag or None,
        order_by=order_by, limit=1, offset=None,
    )
    return self.fetch_one(sql, pred_params)
```
`find_one` = concrete `def find_one(...)` delegating to `get` with identical params (D-02 twin rule). `fetch_one` signature: `fetch_one(self, sql, params=None) -> dict[str, Any] | None` (database.py:1432).

**Anti-pattern to avoid:** implementing `get` as `self.select_where(..., limit=1)[0:1]` — pushes limiting to Python instead of SQL; must pass `limit=1` into `_build_select_sql` directly (RESEARCH.md Pitfall 4).

---

### `pycopg/database.py :: insert` (single row) (service, CRUD-write)

**Analog:** `upsert` (database.py:952-1013)

**Exact tail to replicate** (database.py:1007-1013, verbatim per CONTEXT D-06):
```python
sql, _ = self._build_insert_sql(table, columns, schema, on_conflict)
sql += " RETURNING *"
params = [row[c] for c in columns]

with self.cursor() as cur:
    cur.execute(sql, params)
    return cur.fetchone()
```

**Full new method shape:**
```python
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
Difference from `upsert`: skip the `conflict_columns`/`update_columns` computation that precedes `upsert`'s call to `_build_insert_sql` — `insert`'s `on_conflict` is a raw passthrough string (`"DO NOTHING"`, `"DO UPDATE SET ..."`), mirroring `insert_many`'s `on_conflict: str | None = None` kw-only shape (database.py:868). `_build_insert_sql` itself lives at base.py:169: `_build_insert_sql(table, columns, schema="public", on_conflict=None) -> tuple[str, str]` — runs `validate_identifiers` internally, so no separate guard call is needed in `insert`.

Document the `None`-on-`DO NOTHING`-conflict path (D-07), mirroring `upsert`'s existing documented `dict | None` return.

---

### `pycopg/async_database.py` (async mirrors of all 5 above)

**Analog:** byte-identical sync methods in `database.py`; existing async precedent at `exists` (1033), `count` (1093), `upsert` (1924), `delete_where` (1987), `update_where` (2047), `fetch_one` (951), `fetch_all` (994).

**Pattern:** every sync method above has an async twin with an *identical parameter shape*, `async def`, and `await`-prefixed body (`await self.fetch_all(...)`, `async with self.cursor() as cur: await cur.execute(...); return await cur.fetchone()`). No behavioral divergence is permitted — `test_all_database_public_methods_exist_in_async` and `test_database_core_parameter_kind_parity` (tests/test_parity.py:396, 632) enforce this automatically (no registry edit needed; both tests do a live `inspect.getmembers`/`inspect.Parameter.kind` diff).

---

### `pycopg/schema.py :: column_exists` (SchemaAccessor + AsyncSchemaAccessor)

**Analog:** `table_exists` (schema.py:336-352)

**Exact pattern to mirror** (schema.py:336-352, verbatim structure):
```python
def table_exists(self, name: str, *, schema: str = "public") -> bool:
    result = self._db.execute(queries.TABLE_EXISTS, [schema, name])
    return len(result) > 0
```

**New method:**
```python
def column_exists(self, table: str, column: str, *, schema: str = "public") -> bool:
    result = self._db.execute(queries.COLUMN_EXISTS, [schema, table, column])
    return len(result) > 0
```
Async mirror in `AsyncSchemaAccessor` (schema.py:1237 has `table_exists`'s async twin) — same body, `await self._db.execute(...)`. No `validate_identifiers` call needed here (mirrors `table_exists`, which relies on `execute`'s own identifier-free parametrized query — table/schema/column are bound as `%s` values against `information_schema.columns`, not interpolated as SQL identifiers, so no identifier validation applies to this query shape).

---

### `pycopg/schema.py :: table_size` (SchemaAccessor + AsyncSchemaAccessor)

**Analog:** `truncate_table`'s existence guard (schema.py:437-439) + reuse of the ALREADY-EXISTING `queries.TABLE_SIZE` constant (queries.py:301 — do NOT add a duplicate constant)

**Exact guard to copy verbatim** (schema.py:437-439):
```python
validate_identifiers(name, schema)
if not self.table_exists(name, schema=schema):
    raise TableNotFoundError(f"Table '{schema}.{name}' does not exist.")
```

**New method** (D-09):
```python
def table_size(self, name: str, *, schema: str = "public") -> int:
    validate_identifiers(name, schema)
    if not self.table_exists(name, schema=schema):
        raise TableNotFoundError(f"Table '{schema}.{name}' does not exist.")
    result = self._db.execute(queries.TABLE_SIZE, [f"{schema}.{name}"])
    return int(result[0]["size"])
```
`TableNotFoundError` already imported in `schema.py` line 24 (`from pycopg.exceptions import TableNotFoundError`) — no new import needed. `row_count` (schema.py:461, `AsyncSchemaAccessor` mirror at 1313) is the sibling introspection scalar this complements — same "`self._db.execute(CONST, [schema, name])` → shape result in Python" convention.

**Naming-collision note (non-blocking, Pitfall 1):** `db.maint.table_size` (maint.py:73) already exists with different semantics (`str | int`, `pretty=True` default, no existence guard). No Python namespace collision (different accessor class) — do NOT deduplicate; add a numpydoc "See Also" cross-reference to `db.maint.table_size` in the new method's docstring per project convention.

---

### `pycopg/queries.py :: COLUMN_EXISTS` (config, new SQL constant)

**Analog:** `TABLE_EXISTS` (queries.py:36), `GET_COLUMNS` (queries.py:56)

```python
TABLE_EXISTS = """
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = %s AND table_name = %s
"""
GET_COLUMNS = """
    SELECT column_name, data_type FROM information_schema.columns
    WHERE table_schema = %s AND table_name = %s ORDER BY ordinal_position
"""
```

**New constant (insert immediately after `GET_COLUMNS`, inside the existing `# TABLE QUERIES` section, queries.py:24-68):**
```python
COLUMN_EXISTS = """
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = %s AND table_name = %s AND column_name = %s
"""
```
`table_size` needs NO new constant — reuse `queries.TABLE_SIZE` (queries.py:301, exact match to D-09's spec: `SELECT pg_total_relation_size(%s) AS size`).

---

### `tests/test_sql_injection.py` (injection tests for all new identifier-accepting call sites)

**Analog:** `TestSyncIdentifierInjection`/`TestAsyncIdentifierInjection` (lines 83-100+/179+), `TestWhereSqlValueInjection` (line 262)

**Fixture pattern already shared (no changes needed)** — `sync_db`/`async_db` fixtures (lines 32-80) mock the psycopg connection layer and attach a real `SchemaAccessor`/`AsyncSchemaAccessor` with only `has_extension` stubbed.

**Exact parametrized-test shape to mirror** (lines 83-99):
```python
EVIL_IDENTIFIERS = [
    "users; DROP TABLE users; --",
    'x"; DROP TABLE y; --',
    "a' OR '1'='1",
    "schema.table",
    "tab le",
]

class TestSyncIdentifierInjection:
    @pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
    def test_drop_index(self, sync_db, evil):
        with pytest.raises(InvalidIdentifierError):
            sync_db.schema.drop_index(evil)
```

**New tests needed (both sync + async, following this exact per-class shape):**
- `select_where`/`find`/`get`/`find_one`: parametrize `evil` over `table=`, `schema=`, and each `columns=` entry → `InvalidIdentifierError`.
- `where_sql`/`where_params` value-binding for the new read helpers → extend `TestWhereSqlValueInjection` (line 262) following its existing `test_where_sql_params_bound_sync`/`_async` pattern (lines 273, 299).
- `order_by=` — needs its OWN documented-escape-hatch test (NOT an identifier-validation test — `order_by` is intentionally unvalidated, same trust model as `where_sql`; assert typical multi-column syntax like `"col1 DESC, col2 ASC"` passes through and is NOT rejected by `InvalidIdentifierError`, confirming the escape hatch is intentional, not a gap).
- single-row `insert`: parametrize `evil` over `table=`, `schema=`, and each key of `row` → `InvalidIdentifierError` (mirrors `insert_many`'s existing `test_insert_many_column_injection`, referenced at RESEARCH.md line 157).
- `column_exists`: parametrize `evil` over `table=`, `schema=`, `column=` → mirrors `test_drop_index`'s exact shape above.
- `table_size`: parametrize `evil` over `name=`, `schema=` → mirrors `table_exists`-style tests.

## Shared Patterns

### Predicate resolution (`_resolve_predicate`)
**Source:** `pycopg/base.py:329` (`QueryMixin._resolve_predicate`, `@staticmethod`)
**Apply to:** `select_where`/`find`/`get`/`find_one` (database.py + async_database.py)
```python
frag, pred_params = self._resolve_predicate(where, where_sql, where_params)
```
Returns `("", [])` for no predicate source — this IS the D-03 "read all" path, requires no special-casing. Raises `ValueError` on: both `where` and `where_sql` given; `where_params` given without `where_sql`; `where_sql` blank/whitespace.

### SELECT SQL assembly (`_build_select_sql`)
**Source:** `pycopg/base.py:248`
**Apply to:** `select_where`/`find`/`get`/`find_one`
```python
_build_select_sql(table, columns, schema, where=frag_or_None, order_by=..., limit=..., offset=...)
```
`where` param takes a PRE-RESOLVED fragment string, not a dict — always call `_resolve_predicate` first. Runs `validate_identifiers(table, schema)` + `validate_identifiers(*columns)` (if given) internally — no separate guard needed in the calling method.

### validate_identifiers-first convention
**Source:** `pycopg/utils.py` (`validate_identifiers`/`validate_identifier`)
**Apply to:** every new method taking table/schema/column names — either called explicitly (as in `table_size`, mirroring `truncate_table`) or transitively via `_build_select_sql`/`_build_insert_sql` (as in `select_where`/`insert`). Never validate `where_sql`, `order_by`, or values inside `where_params`/`row` — those are bound as `%s` or are documented escape hatches, per project convention.

### Error handling
**Source:** `pycopg/exceptions.py` (`TableNotFoundError`, already imported in `schema.py:24`)
**Apply to:** `table_size` only (guard pattern from `truncate_table`, schema.py:437-439). No new exception type needed anywhere else in this phase.

### Execution delegation (avoid hand-rolled cursors)
**Source:** `fetch_all` (database.py:1475) / `fetch_one` (database.py:1432)
**Apply to:** `select_where`/`find` → `self.fetch_all(sql, pred_params)`; `get`/`find_one` → `self.fetch_one(sql, pred_params)`. Only `insert` needs its own `with self.cursor() as cur:` block (mirrors `upsert`, which needs `cur.fetchone()` directly for the `RETURNING *` row — not a generic fetch wrapper case).

## No Analog Found

None — every new symbol in this phase has a confirmed, line-verified analog in the live codebase (this is the defining property of a symmetry-completion phase; see RESEARCH.md "Live Code Verification" section for the full anchor-by-anchor confirmation).

## Metadata

**Analog search scope:** `pycopg/base.py`, `pycopg/database.py`, `pycopg/async_database.py`, `pycopg/schema.py`, `pycopg/queries.py`, `pycopg/exceptions.py`, `tests/test_sql_injection.py`, `tests/test_parity.py` (all read directly in this session or in the prior RESEARCH.md session with confirmed exact line numbers — zero drift).
**Files scanned:** 8
**Pattern extraction date:** 2026-07-05
