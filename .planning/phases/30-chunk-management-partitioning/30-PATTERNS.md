# Phase 30: Chunk Management & Partitioning - Pattern Map

**Mapped:** 2026-06-22
**Files analyzed:** 4 source files + 5 source/test symbols (4 methods × 2 classes, 2+ SQL constants, 1 exception, 1 new test file)
**Analogs found:** 8 / 8 (every new symbol has an exact or role-match analog in the repo)

All new code lands in just 4 files (CONTEXT D-09 confirms the 3rd source file is intentional):

| File | New/Modified | What lands here |
|------|--------------|-----------------|
| `pycopg/timescale.py` | modified | 4 methods on `TimescaleAccessor` + 4 mirror methods on `AsyncTimescaleAccessor` |
| `pycopg/queries.py` | modified | `TSDB_SHOW_CHUNKS`, `TSDB_DROP_CHUNKS` (names = planner's discretion) |
| `pycopg/exceptions.py` | modified | `class TimescaleError(PycopgError)` |
| `tests/test_timescale.py` | **new** | mock SQL-shape unit tests + live-DB integration (ts_db skip-fixture) |
| `tests/test_parity.py` | **unchanged** | pair already registered — see Shared Pattern "Parity" |

## File Classification

| New File/Symbol | Role | Data Flow | Closest Analog | Match Quality |
|-----------------|------|-----------|----------------|---------------|
| `TimescaleAccessor.show_chunks` | accessor method (sync) | request-response (read) | `TimescaleAccessor.hypertable_info` (returns rows) | exact (role+flow) |
| `TimescaleAccessor.drop_chunks` | accessor method (sync) | request-response (read-then-mutate) | `hypertable_info` (read) + `add_retention_policy` (mutate) | role-match |
| `TimescaleAccessor.add_dimension` | accessor method (sync) | request-response (DDL) | `TimescaleAccessor.create_hypertable` | exact |
| `TimescaleAccessor.add_reorder_policy` | accessor method (sync) | request-response (DDL) | `TimescaleAccessor.add_retention_policy` | exact |
| `AsyncTimescaleAccessor.*` (×4) | accessor method (async) | mirror of sync | matching `Async...` method in same file | exact |
| `TSDB_SHOW_CHUNKS` / `TSDB_DROP_CHUNKS` | SQL constant | — | `HYPERTABLE_INFO` / `TABLE_SIZES` (use `%%I`) | exact |
| `TimescaleError(PycopgError)` | exception | — | `ExtensionNotAvailable` / `TableNotFound` | exact |
| `tests/test_timescale.py` | test file | — | `TestDatabaseTimescaleCoverage` + `test_async_database.py` mocks | exact |
| conditional `%s` cast (D-02 builder) | builder fragment | request-response | `etl._build_incremental_extract_sql` | role-match (closest in repo) |

## Pattern Assignments

### `TimescaleAccessor.add_dimension` + `add_reorder_policy` (sync DDL methods)

**Analog:** `TimescaleAccessor.create_hypertable` / `add_retention_policy`, `pycopg/timescale.py:45-94` and `:187-222`.

This is the canonical pure-builder template. Copy this exact body shape (guard → validate → f-string interpolate → `self._db.execute`):

```python
def create_hypertable(self, table, time_column, schema="public",
                      chunk_time_interval="1 day", if_not_exists=True, migrate_data=True) -> None:
    if not self._db.schema.has_extension("timescaledb"):          # GUARD (sync: no await)
        raise ExtensionNotAvailable(
            "TimescaleDB extension not installed. Run db.schema.create_extension('timescaledb')"
        )
    validate_identifiers(table, schema, time_column)               # VALIDATE identifiers
    validate_interval(chunk_time_interval)                         # VALIDATE interval
    self._db.execute(f"""                                          # BUILD + EXECUTE
        SELECT create_hypertable('{schema}.{table}', '{time_column}',
            chunk_time_interval => INTERVAL '{chunk_time_interval}', ...)
    """)
```

**`add_reorder_policy` SQL** (from RESEARCH, live-verified):
```sql
SELECT add_reorder_policy('{schema}.{table}', '{index_name}', if_not_exists => true) AS job_id
```
Validate `table, schema, index_name` via `validate_identifiers`.

**`add_dimension` SQL** (from RESEARCH §"add_dimension Resolution", D-06/D-07):
```python
if partition_type == "hash":
    dim = f"by_hash('{column}', {int(number_partitions)})"
else:  # range
    validate_interval(chunk_interval)
    dim = f"by_range('{column}', INTERVAL '{chunk_interval}')"
ne = ", if_not_exists => true" if if_not_exists else ""
# D-07 ValueError mutual-exclusivity raised BEFORE this, before any round-trip
self._db.execute(f"SELECT add_dimension('{schema}.{table}', {dim}{ne})")
```
`validate_interval(chunk_interval)` call form matches existing usage at `timescale.py:84` (`create_hypertable`) and `:173,210,427,463` (the policy methods). `validate_interval` is defined at `pycopg/utils.py:125`; `validate_identifier`/`validate_identifiers` at `:78`/`:107`.

**D-08 reshape (Finding 1):** wrap the *duplicate-dimension* DB error, not non-empty. The attempt-DDL → catch → re-raise shape has no existing analog in `timescale.py` (all current methods let DB errors propagate). Use a broad `except Exception`-style catch around the `add_dimension` execute and re-raise as `TimescaleError` (TS160 surfaces as a generic psycopg `DatabaseError` subclass — confirm class at implementation). Only exercised with `if_not_exists=False`.

---

### `TimescaleAccessor.show_chunks` (sync read, conditional-`%s` builder)

**Analog (body shape):** `TimescaleAccessor.hypertable_info`, `pycopg/timescale.py:245-277` — guard, then `self._db.execute(query_constant, params)` returning rows.

**SQL constant** goes in `queries.py` next to `LIST_HYPERTABLES`/`HYPERTABLE_INFO` (`queries.py:228-243`). RESEARCH-recommended, live-verified:
```sql
SELECT c.chunk_schema || '.' || c.chunk_name AS chunk_name
FROM show_chunks('{schema}.{table}'{older_arg}{newer_arg}) AS sc
JOIN timescaledb_information.chunks c
  ON format('%%I.%%I', c.chunk_schema, c.chunk_name)::regclass = sc
ORDER BY c.range_start ASC
```
Note the `%%I.%%I` — psycopg eats a literal `%`, so the SQL `format('%I.%I', ...)` must be written `%%I.%%I` in the query string. **This is the exact convention already used in `HYPERTABLE_INFO` (`queries.py:241-242`) and `TABLE_SIZES` (`queries.py:198-203`):**
```python
HYPERTABLE_INFO = """
    SELECT
        hypertable_size(format('%%I.%%I', %s::text, %s::text)) AS total_size, ...
"""
```
And the caller comments it (`timescale.py:272-275`):
```python
result = self._db.execute(
    # %%I in queries.HYPERTABLE_INFO is escaped so psycopg passes a
    # literal %I through to PostgreSQL's format() function.
    queries.HYPERTABLE_INFO, [schema, table, schema, table],
)
```
Return shape: `[r["chunk_name"] for r in rows]` (D-04 fully-qualified, D-05 oldest-first comes from `ORDER BY range_start ASC` — do NOT sort in Python, lexical sort is wrong).

**Conditional `%s` composition (D-02) — closest analog:** `pycopg/etl.py:_build_incremental_extract_sql` (`etl.py:527-588`). It is the repo's reference for "append a `%s` + matching param in lockstep, never f-string the value":
```python
# etl.py:585-586 — placeholder and param built together
sql = f"SELECT * FROM ({clean}) {_PYCOPG_INC_ALIAS} WHERE {column} > %s"
return sql, [watermark]
```
**Phase 30 twist:** the cast is type-driven (D-02). Build fragment + param in the SAME conditional branch so they stay aligned:
- `str older_than` → fragment `", older_than => %s::interval"`, param `older_than`
- `datetime older_than` → fragment `", older_than => %s"`, param `older_than`
- `None` → emit neither fragment nor param
- Then the same for `newer_than`.

**PARAM-ORDERING FOOTGUN:** the params list must match placeholder appearance order — **`older_than` first, then `newer_than`**. The SQL fragments are appended `{older_arg}{newer_arg}`, so the params list must be built in that identical order. A mismatched order silently binds the wrong cutoff to the wrong filter.

---

### `TimescaleAccessor.drop_chunks` (sync read-then-mutate)

**Analog:** combines `hypertable_info` (read, `timescale.py:245`) + `add_retention_policy` (mutate, `timescale.py:187`).

**Capture-before-mutate (RESEARCH Pattern 3, live-verified necessity):**
1. **D-03 guard FIRST, before any round-trip:** `if older_than is None and newer_than is None: raise ValueError(...)`. No DB analog needed — pure Python guard like D-07's mutual-exclusivity check.
2. Run the `TSDB_SHOW_CHUNKS`-shaped query to capture the ordered list while chunks still exist.
3. If `dry_run`: return the captured list, **do not drop**.
4. Else execute `SELECT drop_chunks('{schema}.{table}'{args})` then return the captured list.

Do NOT JOIN the `drop_chunks()` SRF to the info view — its return column is `text` not `regclass`, and rows vanish post-drop (RESEARCH anti-pattern). `dry_run` and real paths share the same capture query → identical D-04 shape.

---

### `AsyncTimescaleAccessor.*` (all 4 async mirrors)

**Analog:** the matching `async def` in the same file, e.g. `AsyncTimescaleAccessor.create_hypertable` (`pycopg/timescale.py:297-346`) and `add_retention_policy` (`:441-476`).

**CRITICAL — the recurring Phase 23 missing-`await` gotcha.** The async guard MUST `await` `has_extension`. Copy this exact shape verbatim (`timescale.py:330` / `:465`):
```python
async def create_hypertable(self, ...):
    if not await self._db.schema.has_extension("timescaledb"):   # ← await REQUIRED
        raise ExtensionNotAvailable(...)
    validate_identifiers(...)            # validators are sync — NO await
    validate_interval(...)               # sync — NO await
    await self._db.execute(f"""...""")   # ← await REQUIRED
```
Without `await`, `has_extension(...)` returns a truthy coroutine and the guard never fires. The parity test catches *signature* drift but NOT a missing `await` — review each of the 4 async methods by hand. `drop_chunks` async: the capture query and the drop are both `await self._db.execute(...)`; the `ValueError`/mutual-exclusivity guards stay plain (no await).

---

## Shared Patterns

### Extension guard
**Source:** every method in `pycopg/timescale.py` (sync `:78`, async `:330`).
**Apply to:** all 8 new methods.
- Sync: `if not self._db.schema.has_extension("timescaledb"):`
- Async: `if not await self._db.schema.has_extension("timescaledb"):`
- Raise `ExtensionNotAvailable("TimescaleDB extension not installed. Run db.schema.create_extension('timescaledb')")`.

Note: existing methods are inconsistent about guard-vs-validate ordering (`create_hypertable` guards first; `add_retention_policy` validates first). Planner picks one; D-03/D-07 pure-Python guards (`ValueError`) should fire **before** the DB-touching extension guard so a bad-argument call never needs a connection.

### New exception `TimescaleError`
**Source:** `pycopg/exceptions.py:24-33` — `ExtensionNotAvailable` / `TableNotFound`.
**Apply to:** `add_dimension` duplicate-dimension re-wrap (D-08/D-09), reused Phases 31-32.
Follow the exact one-liner-docstring + `pass` pattern:
```python
class TimescaleError(PycopgError):
    """Error raised by TimescaleDB management operations."""

    pass
```
No `__init__` — base `PycopgError(Exception)` is used as-is (`exceptions.py:6-9`). Place it after the existing subclasses.

### Parity registration — NO CHANGE NEEDED
**Source:** `tests/test_parity.py:24-32` (`ACCESSOR_PAIRS`) + `:35-60` (`test_accessor_parity`).
The pair is **already registered** (proof, `test_parity.py:25`):
```python
ACCESSOR_PAIRS = [
    (TimescaleAccessor, AsyncTimescaleAccessor),   # ← line 25, already present
    ...
]
```
`test_accessor_parity` reflects public members of both classes and asserts symmetric difference is empty. Adding the same 4 method names to both classes auto-satisfies TS-ADV-10 with **zero registry edits**. The only failure mode is a typo'd name present in one class but not the other.

### SQL constant `%%I` escaping
**Source:** `queries.py:198-203` (`TABLE_SIZES`), `:241-242` (`HYPERTABLE_INFO`).
**Apply to:** `TSDB_SHOW_CHUNKS` JOIN key (`format('%%I.%%I', c.chunk_schema, c.chunk_name)::regclass`). Place the new constants in the TIMESCALEDB section (`queries.py:224-243`).

## Test File Scaffold (`tests/test_timescale.py` — NEW)

Two layers (D-11), both with existing analogs.

**Layer 1 — live-DB integration:** port the `ts_db` skip-fixture from `tests/test_database_integration.py:836-848`:
```python
class TestDatabaseTimescaleCoverage:
    @pytest.fixture
    def ts_db(self, db):
        if not db.schema.has_extension("timescaledb"):
            try:
                db.schema.create_extension("timescaledb", if_not_exists=True)
            except Exception:
                pytest.skip("TimescaleDB extension not available")
        if not db.schema.has_extension("timescaledb"):
            pytest.skip("TimescaleDB extension not available")
        return db
```
Add an async equivalent for the async live tests (`asyncio_mode = "auto"` is set, so no per-test marker).

**`FeatureNotSupported` tolerance** for `add_reorder_policy` (D-12, Apache license) — mirror `test_database_integration.py:866-878`:
```python
from psycopg.errors import FeatureNotSupported
try:
    ts_db.timescale.add_reorder_policy(t, index_name=...)
except FeatureNotSupported:
    pass
```
The job-row assertion (`timescaledb_information.jobs`) + `CALL run_job(job_id)` must sit behind this tolerance so they stay green on the Apache build.

**Layer 2 — mock SQL-shape unit tests (authoritative for `add_reorder_policy`):** port from `tests/test_async_database.py:2334-2351`:
```python
db = AsyncDatabase(config)
mock_schema = MagicMock(spec=AsyncSchemaAccessor)
mock_schema.has_extension = AsyncMock(return_value=True)
db._schema = mock_schema
db.execute = AsyncMock(return_value=[])      # use return_value=[...] for show_chunks shape

await db.timescale.add_reorder_policy("events", index_name="idx")
mock_schema.has_extension.assert_called_once_with("timescaledb")
sql = db.execute.call_args[0][0]
assert "add_reorder_policy" in sql
# for show_chunks/drop_chunks also assert params order:
# params = db.execute.call_args[0][1]; assert params == [older, newer]
```
The negative analog (extension-missing raises) is at `test_async_database.py:2353-2367`; the sync monkeypatch-on-accessor analog at `test_database_integration.py:880-889`.

## No Analog Found

None — all 8 new symbols map to an exact or role-match analog. The single partial case (attempt-DDL → catch → re-raise for D-08) has no in-file analog because no existing `timescale.py` method wraps DB errors; the planner adds a try/except around the `add_dimension` execute re-raising `TimescaleError` (new pattern, but trivial).

## Metadata

**Analog search scope:** `pycopg/timescale.py`, `pycopg/queries.py`, `pycopg/exceptions.py`, `pycopg/utils.py`, `pycopg/etl.py`, `tests/test_parity.py`, `tests/test_database_integration.py`, `tests/test_async_database.py`.
**Files scanned:** 8
**Pattern extraction date:** 2026-06-22
