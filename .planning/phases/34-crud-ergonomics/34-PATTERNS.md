# Phase 34: CRUD Ergonomics - Pattern Map

**Mapped:** 2026-06-24
**Files analyzed:** 4 (base.py, database.py, async_database.py, tests/test_parity.py — all *modified*, no new files)
**Analogs found:** 8 / 8 (every new method has an in-repo analog)

## File Classification

All new methods are *additions to existing files*. No new files, no new accessor (locked: flat
transactional core). Pure builder(s) added to `base.py`; public methods added symmetrically to
`Database` and `AsyncDatabase`.

| New Method (on BOTH Database + AsyncDatabase) | Role | Data Flow | Closest Analog | Match Quality |
|-----------------------------------------------|------|-----------|----------------|---------------|
| `upsert(table, row, conflict_columns, ...)` | core write | CRUD (single upsert+RETURNING) | `upsert_many` (`database.py:602`, `async_database.py:989`) | exact |
| `delete_where(table, where={...}) -> int` | core write | CRUD (predicate delete) | `execute_many`/`insert_many` rowcount return (`database.py:543`,`565`) | role-match |
| `update_where(table, values, where) -> int` | core write | CRUD (predicate update) | `upsert_many` SET-clause + rowcount | role-match |
| `exists(table, where) -> bool` | core read | request-response (scalar) | `fetch_val` (`database.py:834`) | exact |
| `count(table, where=None) -> int` | core read | request-response (scalar) | `fetch_val` (`database.py:834`) | exact |
| `paginate(table, limit, offset, ...) -> list[dict]` | core read | CRUD (paged read) | `_build_select_sql` (`base.py:158`) + `execute` (`database.py:518`) | role-match |
| `fetch_all(sql, params) -> list[dict]` | core read | request-response | `fetch_one` (`database.py:815`) + `execute` (`database.py:518`) | exact |
| `_build_where_dict(where) -> (str, list)` (new builder, base.py) | utility/builder | transform (dict→SQL) | `_build_batch_insert_sql` param-accumulation (`base.py:113`) | role-match |

| New Builder File location | Role | Data Flow | Closest Analog | Match Quality |
|---------------------------|------|-----------|----------------|---------------|
| `pycopg/base.py` `_build_*` staticmethod | builder | transform | `_build_insert_sql`/`_build_select_sql` (`base.py:79`,`158`) | exact |

## Pattern Assignments

### `_build_where_dict` — NEW pure builder (base.py, builder, transform)

**Analog:** `_build_batch_insert_sql` (`pycopg/base.py:113-156`) for the `validate_identifiers` →
`%s` placeholder → param-list accumulation shape; `_build_insert_sql` (`base.py:79-111`) for the
`-> tuple[str, ...]` return convention.

**Convention to copy (validate-first, values as `%s`):** from `base.py:104-107`:
```python
validate_identifiers(table, schema, *columns)
cols_str = ", ".join(columns)
placeholders = ", ".join(["%s"] * len(columns))
```

**Param accumulation (the dict→params idiom) — from `base.py:146-151`:**
```python
placeholders = []
params = []
for row in rows:
    row_placeholders = ", ".join(["%s"] * len(columns))
    placeholders.append(f"({row_placeholders})")
    params.extend(row.get(col) for col in columns)
```

**New builder shape (D-12 — separate/safer than the existing `where: str` path):** validate the
dict KEYS via `validate_identifiers(*where.keys())`, then emit AND-ed `col = %s`, values as params:
```python
@staticmethod
def _build_where_dict(where: dict) -> tuple[str, list]:
    validate_identifiers(*where.keys())
    fragment = " AND ".join(f"{col} = %s" for col in where)
    params = list(where.values())
    return fragment, params
```
This fragment is interpolated into the SQL string (`WHERE {fragment}`), params bound positionally —
mirrors how `_build_select_sql` (`base.py:199-200`) appends `WHERE {where}` but with the dict path
producing the `%s`-bound fragment instead of trusting a raw string.

**Do NOT overload `_build_select_sql`'s `where: str` param** (`base.py:163,199`) — that one is a
RAW SQL string (legacy, injection-prone-by-caller). The dict path is a distinct, safer mechanism.

---

### `upsert` (core write, CRUD) — singular complement to `upsert_many`

**Analog:** `upsert_many` — sync `pycopg/database.py:602-645`, async `pycopg/async_database.py:989-1032`.

**EXCLUDED SET-clause construction to reuse (D-03) — from `database.py:633-645`:**
```python
columns = list(rows[0].keys())
if update_columns is None:
    update_columns = [c for c in columns if c not in conflict_columns]

validate_identifiers(*conflict_columns)
validate_identifiers(*update_columns)

conflict_str = ", ".join(conflict_columns)
update_str = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_columns])
on_conflict = f"({conflict_str}) DO UPDATE SET {update_str}"
```

**Singular adaptation (D-01/D-02/D-03):** `row: dict` (not `rows: list[dict]`); `conflict_columns`
stays a required positional (matches `upsert_many` signature at `database.py:606`); build a single-row
`INSERT ... ON CONFLICT (...) DO UPDATE SET ...`, **append `RETURNING *`**, and `fetchone()` →
`dict | None` (None on no-op / no row affected). Reuse `_build_insert_sql` (`base.py:79`) for the
single-row VALUES scaffold, then append the `DO UPDATE SET ... RETURNING *` tail.

**Cursor/execute + RETURNING pattern — model on `fetch_one` (`database.py:830-832`):**
```python
with self.cursor() as cur:
    cur.execute(sql, params)
    return cur.fetchone()          # dict | None  (dict_row factory)
```

**Async twin — `async_database.py:1017-1032` idiom (NATIVE async, NOT to_thread):**
```python
async with self.cursor() as cur:
    await cur.execute(sql, params)
    return await cur.fetchone()
```

---

### `delete_where` / `update_where` (core write, CRUD) — predicate writes, return rowcount

**Analog:** rowcount-return write methods — `insert_many` (`database.py:565-600`), `execute_many`
(`database.py:543-563`); SET-clause from `upsert_many`.

**Empty-where guard (D-04) — raise BEFORE any DB round-trip (no in-repo analog; new guard):**
```python
if not where:
    raise ValueError("delete_where requires a non-empty `where` dict; "
                     "use truncate_table to affect all rows")
```

**Affected-count return (D-07) — copy the `cur.rowcount` pattern from `insert_many` (`database.py:598-600`):**
```python
with self.cursor() as cur:
    cur.execute(sql, params)
    return cur.rowcount
```

**`update_where` SET-clause:** build `SET col = %s, ...` from `values` dict — same `%s` + param
accumulation as the EXCLUDED clause but with bound values; validate keys via `validate_identifiers`.
Compose `WHERE {fragment}` + params from `_build_where_dict`; concatenate SET params + where params.

**Async twins:** native `async with self.cursor()` / `await cur.execute()` then `return cur.rowcount`
(`async_database.py:985-987`).

---

### `exists` (core read, scalar) and `count` (core read, scalar)

**Analog:** `fetch_val` — sync `database.py:834-852`, async `async_database.py:707-725`.

**D-05 `exists -> bool`:** `SELECT EXISTS(SELECT 1 FROM {schema}.{table} WHERE {fragment})` — never
materializes rows. **D-06 `count -> int`:** `SELECT COUNT(*) FROM ... [WHERE {fragment}]`;
`where=None` allowed (skip WHERE), the destructive guard does NOT apply here (D-04 is write-only).

**Scalar fetch pattern to reuse — `fetch_val` (`database.py:849-852`):**
```python
row = self.fetch_one(sql, params)
if row:
    return list(row.values())[0]
return None
```
Build the SQL via `_build_where_dict` (when `where` given) and delegate to `self.fetch_val(sql, params)`;
cast/coerce the scalar (`bool(...)` / `int(...)`). Async: `await self.fetch_val(...)`.

---

### `paginate` (core read, CRUD) -> list[dict]

**Analog:** `_build_select_sql` (`base.py:158-208`) for the SELECT/ORDER BY/LIMIT/OFFSET scaffold;
`execute` (`database.py:518-541`) for the `list[dict]` fetch.

**LIMIT/OFFSET int-cast already established — `base.py:203-206`:**
```python
if limit is not None:
    sql += f" LIMIT {int(limit)}"
if offset is not None:
    sql += f" OFFSET {int(offset)}"
```

**D-10/D-11 new pieces:** `order_by: str | list[str]` of COLUMN NAMES run through
`validate_identifiers` (not raw SQL); whole-clause `descending: bool` → append `DESC` to the
`ORDER BY col, col` list. `where=None` allowed. Signature:
`paginate(table, limit, offset=0, order_by=None, where=None, descending=False, schema="public")`.

**Fetch pattern — `execute` (`database.py:537-541`), returns `list[dict]` (D-09):**
```python
with self.cursor(autocommit=autocommit) as cur:
    cur.execute(sql, params)
    if cur.description:
        return cur.fetchall()
    return []
```
Compose `_build_select_sql` (raw-where=None) + the dict-where fragment, or add a new builder; the
`where` dict params bind positionally. Async mirrors `execute` at `async_database.py:540-544`.

---

### `fetch_all(sql, params) -> list[dict]` (core read, request-response)

**Analog:** `fetch_one` (`database.py:815-832`) for the signature/shape; `execute`
(`database.py:518-541`) for the `fetchall()` body. D-08: this is a thin discoverability alias for
the dicts-by-default `execute` — a `list[dict]` symmetry twin to `fetch_one`'s `dict | None`.
**Do NOT** add an `into=` toggle or tuples path.

```python
def fetch_all(self, sql: str, params: Sequence | None = None) -> list[dict]:
    with self.cursor() as cur:
        cur.execute(sql, params)
        if cur.description:
            return cur.fetchall()
        return []
```
Async: native `async with self.cursor()` / `await cur.execute()` / `await cur.fetchall()`
(see `async_database.py:540-544`).

## Shared Patterns

### Identifier validation (every builder calls FIRST)
**Source:** `validate_identifiers(*names)` — `pycopg/utils.py:107-122` (skips `None`; raises
`InvalidIdentifier`). **Apply to:** every new builder — validate `table`, `schema`, and all
column names (`where` keys, `values` keys, `order_by` columns, `conflict_columns`, `update_columns`)
BEFORE any string interpolation. Established usage: `base.py:104`, `base.py:192-194`,
`database.py:637-638`.
```python
validate_identifiers(table, schema, *columns)   # base.py:104
```

### Dicts-by-default (why dict-fetch is mostly free — D-08)
**Source:** `row_factory=dict_row` in `pycopg/pool.py`; proven by `execute -> list[dict]`
(`database.py:518`) and `fetch_one -> dict | None` (`database.py:815`). **Apply to:** `upsert`
(`RETURNING *` → dict), `paginate`, `fetch_all` — all return dicts WITHOUT extra row-factory work.

### Pure builder convention
**Source:** `BaseDatabase` staticmethods `_build_insert_sql` / `_build_batch_insert_sql` /
`_build_select_sql` (`pycopg/base.py:79-208`). **Apply to:** the new `_build_where_dict` (and any
SET/ORDER-BY builder) — pure `@staticmethod` returning `(sql, params)` or `str`; the public method
owns the cursor + execute. Builders live on `BaseDatabase` so BOTH `Database` and `AsyncDatabase`
inherit them.

### Sync/async parity idiom (CRUD-08)
**Source:** every method pair, e.g. `execute` sync `database.py:537-541` vs async
`async_database.py:540-544`. **Idiom is NATIVE async** — `async with self.cursor()` +
`await cur.execute()` + `await cur.fetchone()/fetchall()`; the rowcount path uses plain
`return cur.rowcount` (no await — see `async_database.py:986-987`). **There is NO `to_thread`
pattern** for these core methods. Builders are SHARED (sync call, no await). Delegating methods
mirror delegation: sync `self.fetch_val(...)` → async `await self.fetch_val(...)`.
**Enforcement:** add each method to BOTH classes with IDENTICAL parameter names; `test_parity.py`
auto-covers them (`test_all_database_public_methods_exist_in_async` at `tests/test_parity.py:121`,
`test_method_signatures_match` at `:142`) — no SYNC_ONLY/ASYNC_ONLY entry needed
(`test_parity.py:107-115`); leave those sets untouched.

### Affected-count returns
**Source:** `insert_many`/`execute_many`/`upsert_many` return `cur.rowcount` (`database.py:563,600,645`).
**Apply to:** `delete_where`, `update_where` (D-07).

## No Analog Found

| Pattern | Reason | Planner Guidance |
|---------|--------|------------------|
| Empty-`where` guard (D-04) | No existing destructive predicate method exists | New `ValueError` raised pre-round-trip; reference D-04. Reuse `truncate_table` as the "affect-all" escape (mentioned in error message). |
| `SELECT EXISTS(...)` wrapper (D-05) | No scalar-existence helper exists yet | Build SQL by hand, fetch via `fetch_val` analog. |
| `descending: bool` whole-clause ORDER BY (D-10) | `_build_select_sql` takes a raw `order_by: str` only | Extend builder: column-name list + single `DESC` suffix. Per-column direction deferred (CRUD-F02-adjacent). |

(No new exception class anticipated — `ValueError` for empty-where, `InvalidIdentifier` from validation.)

## Metadata

**Analog search scope:** `pycopg/base.py`, `pycopg/database.py`, `pycopg/async_database.py`,
`pycopg/utils.py`, `tests/test_parity.py` (named in CONTEXT canonical_refs).
**Files scanned:** 5
**Pattern extraction date:** 2026-06-24
