# Phase 18: Load Modes & Extract - Pattern Map

**Mapped:** 2026-06-15
**Files analyzed:** 4 (1 source: `pycopg/etl.py`; 3 test: `test_etl_accessor.py`, `test_etl.py`, `test_sql_injection.py`)
**Analogs found:** 9 / 9 symbols (1 has no analog — NaN→None)

> **CRITICAL upstream correction (RESEARCH Q1):** Do NOT call `db.insert_batch` / `db.upsert_many`
> inside a `db.transaction()` block — they acquire `self.cursor()` which commits on cursor exit
> when `INTRANS` (breaks atomicity) and crashes inside an explicit `transaction()`
> (`ProgrammingError: Explicit commit() forbidden`). The load executes `(sql, params)` **directly
> on the conn yielded by `db.transaction()`** via `with conn.cursor() as cur: cur.execute(sql, params)`.
> The new private builders supply that `(sql, params)`; they reuse the *SQL-construction + validation
> logic* of the existing methods, NOT the methods themselves.

## File Classification

| New/Modified Symbol | File | Role | Data Flow | Closest Analog | Match Quality |
|---------------------|------|------|-----------|----------------|---------------|
| `_build_insert_sql()` | `pycopg/etl.py` | builder (pure) | transform/SQL-gen | `build_truncate_sql()` etl.py:227-256 + `_build_batch_insert_sql()` base.py:114-156 | exact (shape) + role-match (logic) |
| `_build_upsert_sql()` | `pycopg/etl.py` | builder (pure) | transform/SQL-gen | `build_truncate_sql()` etl.py:227-256 + `upsert_many` db.py:539-551 | exact (shape) + role-match (logic) |
| `run()` body (replace stub) | `pycopg/etl.py` | service/orchestrator | request-response (extract→transform→load) | stub etl.py:425-448 + `_start_run`/`_end_run` etl.py:340-423 | exact (scaffold) |
| atomic load execution | `pycopg/etl.py` (in `run()`) | service | CRUD (transactional write) | working pattern `tests/test_etl_accessor.py:344-348` | exact |
| extract step | `pycopg/etl.py` (in `run()`) | service | request-response (read) | `db.to_dataframe` db.py:1429-1465 | exact |
| existence check | `pycopg/etl.py` (in `run()`) | service | request-response (catalog) | `db.table_exists` db.py:1011-1027 | exact |
| zero-row create (replace) | `pycopg/etl.py` (in `run()`) | service | file-I/O (DDL via engine) | `from_dataframe(if_exists='replace')` db.py:1388-1424 | exact |
| transform chain + `ETLTransformError` | `pycopg/etl.py` (in `run()`) | service | transform (in-memory) | exceptions.py:60-69 (bare class) + RESEARCH Q4 `_step_label` | role-match |
| NaN→None conversion | `pycopg/etl.py` (in `run()`) | utility | transform | **none** | none (RESEARCH Q2 idiom) |
| ETL injection tests | `tests/test_sql_injection.py` | test | — | `EVIL_IDENTIFIERS` parametrize test_sql_injection.py:19-26, 60-67 | exact |
| `_FakeDatabase` extension | `tests/test_etl_accessor.py` | test fixture | — | existing `_FakeDatabase` test_etl_accessor.py:40-87 | role-match |

## Pattern Assignments

### `_build_insert_sql(table, columns, rows, schema, on_conflict=None)` — etl.py (pure builder)

**Analog A (shape — copy this exactly):** `build_truncate_sql` (etl.py:255-256). Pure module-level
function, validates first, returns `(sql, params)` 2-tuple, no `self`, no I/O:
```python
validate_identifiers(table, schema)
return f"TRUNCATE TABLE {schema}.{table}", []
```

**Analog B (SQL-construction logic — borrow, do NOT call):** `_build_batch_insert_sql` (base.py:114-156).
Copy its body into the new pure builder verbatim (it is already a pure `(sql, params)` builder that
validates):
```python
validate_identifiers(table, schema, *columns)
cols_str = ", ".join(columns)
conflict_clause = f" ON CONFLICT {on_conflict}" if on_conflict else ""
placeholders = []
params = []
for row in rows:
    row_placeholders = ", ".join(["%s"] * len(columns))
    placeholders.append(f"({row_placeholders})")
    params.extend(row.get(col) for col in columns)
values_str = ", ".join(placeholders)
sql = f"INSERT INTO {schema}.{table} ({cols_str}) VALUES {values_str}{conflict_clause}"
return sql, params
```
NOTE: `base.py:_build_batch_insert_sql` is effectively the same builder pycopg already ships. The new
etl.py builder is the *minimal* duplication RESEARCH Q1 option (a) calls for (since the public
methods are unusable inside a txn). Mirror it, do not re-derive.

---

### `_build_upsert_sql(table, rows, conflict_columns, update_columns, schema)` — etl.py (pure builder)

**Analog (ON CONFLICT construction):** `upsert_many` (db.py:539-551). Borrow the conflict-clause logic,
then delegate the INSERT body to `_build_insert_sql(..., on_conflict=on_conflict)`:
```python
columns = list(rows[0].keys())
if update_columns is None:
    update_columns = [c for c in columns if c not in conflict_columns]
validate_identifiers(*conflict_columns)
validate_identifiers(*update_columns)
conflict_str = ", ".join(conflict_columns)
update_str = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_columns])
on_conflict = f"({conflict_str}) DO UPDATE SET {update_str}"
# then: return _build_insert_sql(table, columns, rows, schema, on_conflict)
```
SC-6 satisfied: `validate_identifiers` runs for conflict + update columns here, and for
`table/schema/columns` inside `_build_insert_sql`, all before any f-string.

---

### `run(self, pipeline: Pipeline) -> int` body — etl.py (orchestrator)

**Signature change (RESEARCH Q5 — MUST flag):** stub is `run(self, name: str = "pipeline")`; new is
`run(self, pipeline: Pipeline) -> int`, deriving `name = pipeline.name`. Phase 17 tests calling
`db.etl.run("auto")` / `db.etl.run("demo")` (test_etl_accessor.py:210, 222) **will break** — migrate
them to pass a `Pipeline(...)`.

**Scaffold analog (init / start / try / end success|failed / re-raise):** stub etl.py:445-448 +
the autocommit run-log methods etl.py:340-423. The run-log seam stays EXACTLY as-is (dedicated
autocommit conn — ETL-09 must not regress):
```python
self.init()
run_id = self._start_run(name)
# ... try: extract→transform→load; self._end_run(run_id, "success", rows_extracted, rows_loaded)
# ... except: self._end_run(run_id, "failed", rows_extracted, 0,
#                 error_message=str(exc), error_traceback=traceback.format_exc()); raise
return run_id
```
Return the bare `run_id` (int) — preserve the stub's return type; Phase 19 upgrades to `RunResult`.
`_end_run` signature (etl.py:368-376): `(run_id, status, rows_extracted, rows_loaded, error_message=None, error_traceback=None)`. Use literal `'failed'` (CHECK constraint).

**Extract analog:** `db.to_dataframe` (db.py:1429-1465). Two paths via `_is_sql_source` (etl.py:200-224).
Note `to_dataframe(sql=...)` uses `pd.read_sql(text(sql), self.engine, params=params)` with a **dict**
params and SQLAlchemy `:name` bind syntax (db.py:1465) — NOT `%s`. Per RESEARCH `extract_limit`:
- table source: `validate_identifiers(table, schema)` then `to_dataframe(sql=f"SELECT * FROM {schema}.{table} LIMIT :lim", params={"lim": n})`.
- SQL source: `to_dataframe(sql=f"SELECT * FROM ({source}) AS _etl_sub LIMIT :lim", params={"lim": n})`.
- `rows_extracted = len(df)` after extract, before transform.

**Existence check analog:** `db.table_exists` (db.py:1011-1027) — `self._db.table_exists(target, schema)`.
append missing → raise `ETLTargetNotFoundError`; upsert missing → raise `ETLTargetNotFoundError`
(RESEARCH Q3, Pitfall 5); replace missing → create then proceed.

**Zero-row create analog (replace, missing target):** `from_dataframe` (db.py:1388-1424). Runs on
`self.engine` (separate conn) — call it BEFORE opening `db.transaction()`:
```python
self._db.from_dataframe(df.head(0), target, schema, if_exists="replace")
```

**Atomic load execution analog (THE seam — copy this):** working pattern test_etl_accessor.py:344-348:
```python
with db.session():                         # accessor opens session internally (Claude's discretion rec.)
    with db.transaction() as conn:         # real psycopg txn on the session conn
        with conn.cursor() as cur:
            cur.execute(sql, params)        # (sql, params) from _build_insert_sql / _build_upsert_sql
            rows_loaded += cur.rowcount
        # replace: cur.execute(*build_truncate_sql(...)) THEN cur.execute(insert_sql, insert_params)
        #          — both on this same conn → atomic (SC-3)
# raising inside the block rolls the whole txn back
```
`rows_loaded` = sum of `cur.rowcount` (D-07).

---

### Transform chain + `ETLTransformError` — etl.py (in `run()`)

**Exception analog:** exceptions.py:60-69 — `ETLTransformError(ETLError)` and
`ETLTargetNotFoundError(ETLError)` are **bare `pass` classes** (no custom constructor); construct with
a single message string. **Dispatch + label pattern (RESEARCH Q4, 1-based index — state in docstring):**
```python
def _step_label(fn):
    return getattr(fn, "__name__", None) or repr(fn)   # lambda/partial → repr fallback

# transform=None → no-op; single Callable → [callable]; list → as-is
for i, step in enumerate(steps, start=1):
    try:
        df = step(df)
    except Exception as exc:
        raise ETLTransformError(
            f"transform step {i} ('{_step_label(step)}') raised "
            f"{type(exc).__name__}: {exc}"
        ) from exc
```
`raise ... from exc` preserves the chained traceback for `error_traceback` (ETL-08). The except block
in `run()` records the failed run via `_end_run(..., "failed", ..., error_traceback=traceback.format_exc())`.

---

### NaN→None conversion — etl.py (no analog)

**No existing analog** — there is NO NaN/NaT or tz handling anywhere in `pycopg/*.py` (RESEARCH Q2,
verified). Use the RESEARCH-recommended idiom before building rows:
```python
rows = df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")
```
`.astype(object)` first prevents pandas re-coercing None→NaN in numeric columns. `to_dict("records")`
yields `list[dict]` keyed by column — the exact contract `_build_insert_sql` consumes
(`columns = list(rows[0].keys())`, `row.get(col)`). Do NOT coerce tz — document tz-localization as the
user's responsibility (matches `from_dataframe`). Document the scalar-column limit (list/array cells out of scope).

---

### ETL injection tests — tests/test_sql_injection.py

**Analog:** `EVIL_IDENTIFIERS` parametrize (lines 19-26) + a sync test method (lines 60-67):
```python
EVIL_IDENTIFIERS = [
    "users; DROP TABLE users; --", 'x"; DROP TABLE y; --',
    "a' OR '1'='1", "schema.table", "tab le",
]

@pytest.mark.parametrize("evil", EVIL_IDENTIFIERS)
def test_drop_index(self, sync_db, evil):
    with pytest.raises(InvalidIdentifier):
        sync_db.drop_index(evil)
```
New ETL cases: feed `evil` as `Pipeline(target=evil, ...)` / `conflict_columns=(evil,)` and assert the
load path raises `InvalidIdentifier` before SQL reaches the (mocked) DB. The `sync_db` fixture
(lines 29-41) mocks `pycopg.database.psycopg`. Prefer testing the pure `_build_insert_sql` /
`_build_upsert_sql` builders directly with `evil` identifiers (no DB needed) for the unit guard.

---

### `_FakeDatabase` extension — tests/test_etl_accessor.py

**Analog:** existing `_FakeDatabase` (lines 40-87) — currently implements only `connect()`. To unit-test
`run()` it must also gain `session()`, `transaction()` (yielding a conn with `cursor()`), and
`table_exists()`. Mirror the nested-context-manager style already used in `_FakeConn`/`_FakeCursor`.
**Alternative (RESEARCH preferred):** test `run()` exclusively against real `pycopg_test` PG — the
atomicity/idempotency behaviors (especially `replace_atomic_rollback`) only manifest against a real DB.

## Shared Patterns

### Identifier validation (SC-6, v0.3.1 invariant)
**Source:** `validate_identifiers` (utils.py:76) — called in `build_truncate_sql` (etl.py:255),
`_build_batch_insert_sql` (base.py:141), `upsert_many` (db.py:543-544).
**Apply to:** every new builder, before any f-string interpolation. User *values* always `%s`/bind param.

### Run-log isolation (ETL-09 — must NOT regress)
**Source:** `_start_run`/`_end_run` (etl.py:340-423) — all use `with self._db.connect(autocommit=True)`.
**Apply to:** keep run-log writes on the dedicated autocommit conn; the load uses a SEPARATE
transactional conn. The two connection lifetimes are deliberately opposite (Phase 17 / Phase 18 duality).

### Atomic write seam
**Source:** test_etl_accessor.py:344-348.
**Apply to:** all three load modes — execute `(sql, params)` on the `db.transaction()`-yielded conn;
never call `db.insert_batch`/`db.upsert_many` inside the txn block.

## No Analog Found

| Symbol | Role | Data Flow | Reason |
|--------|------|-----------|--------|
| NaN→None conversion | utility | transform | No NaN/NaT/tz handling exists anywhere in `pycopg/*.py` (RESEARCH Q2 verified); use the standard pandas `astype(object).where(notnull, None)` idiom. |

## Metadata

**Analog search scope:** `pycopg/etl.py`, `pycopg/database.py`, `pycopg/base.py`, `pycopg/exceptions.py`,
`tests/test_etl_accessor.py`, `tests/test_sql_injection.py`.
**Files scanned:** 6
**Pattern extraction date:** 2026-06-15
