# Phase 31: Continuous Aggregate Lifecycle - Pattern Map

**Mapped:** 2026-06-23
**Files analyzed:** 2 (`pycopg/timescale.py`, `tests/test_timescale.py`) + 1 confirmed-no-change (`pycopg/queries.py`)
**Analogs found:** 6 / 6 (every new method/test has a verbatim in-repo precedent)

> All line numbers below were re-confirmed against the current tree (CONTEXT.md numbers had drifted in a few places — corrected here). The executor should mirror these exact shapes.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pycopg/timescale.py` → `create_continuous_aggregate` (sync) | new accessor method | DDL via **autocommit seam** | `ETLAccessor.init`/`_start_run` (`etl.py:787`, `811`) for seam + `add_reorder_policy` (`timescale.py:622`) for guard/validate shell | exact (seam) + role-match (method shell) |
| `pycopg/timescale.py` → `create_continuous_aggregate` (async) | new accessor method | DDL via **autocommit seam** | async `_init`/`_start_run` (`etl.py:1486`, `1508`) + async `add_reorder_policy` (`timescale.py:1198`) | exact + role-match |
| `pycopg/timescale.py` → `refresh_continuous_aggregate` (sync+async) | new accessor method | `CALL`-proc via **autocommit seam**, `%s` params | same seam analogs (`etl.py:811`/`1508`) | exact (seam) |
| `pycopg/timescale.py` → `add_continuous_aggregate_policy` (sync+async) | new accessor method | `SELECT add_*_policy(...)` via **plain `execute()`** | `add_reorder_policy` sync `timescale.py:622-667` / async `1198-1241` | exact |
| `pycopg/timescale.py` → `_check_offset_ordering` (module helper) | pure validator | transform (regex, no I/O) | `validate_interval` (`utils.py:125`) call-site pattern | role-match (new logic, no exact analog) |
| `tests/test_timescale.py` → mock SQL-shape tests (3 methods × sync/async) | test extension | unit / mock | `TestAddReorderPolicyMock` (`test_timescale.py:936-1012`) | exact |
| `tests/test_timescale.py` → live-tolerant integration tests (3 methods) | test extension | live-DB / `try/except FeatureNotSupported` | `test_add_reorder_policy_live` (`test_timescale.py:1140`) / async `1165` | exact |
| `pycopg/queries.py` | **NO CHANGE** | — | — | n/a (RESEARCH §Task 6 resolved: no constant warranted) |

## Pattern Assignments

### `create_continuous_aggregate` / `refresh_continuous_aggregate` — AUTOCOMMIT SEAM

**Analog (sync):** `pycopg/etl.py:787-789` and `:811-817`
**Analog (async):** `pycopg/etl.py:1486-1488` and `:1508-1514`

The new methods reuse this seam **verbatim**. The ETL form uses an explicit `conn.cursor(row_factory=dict_row)` only because it needs `RETURNING run_id`; create/refresh return nothing, so per CONTEXT D-discretion (option 154) and RESEARCH Open-Q #3, a plain `conn.execute(...)` on the autocommit connection is sufficient and simpler.

Sync seam (mirror this exactly; drop the cursor wrapper since no fetch is needed):
```python
with self._db.connect(autocommit=True) as conn:       # etl.py:787 / :811 precedent
    conn.execute(sql)                                  # create: no params
    # refresh: conn.execute(sql, [window_start, window_end])
```

Async seam — note `async with` AND `await conn.execute(...)`; `autocommit=True` MUST be passed at `connect()` time (read-only after open, RESEARCH Task 1):
```python
async with self._db.connect(autocommit=True) as conn:  # etl.py:1486 / :1508 precedent
    await conn.execute(sql)                             # refresh: await conn.execute(sql, [start, end])
```

`connect(autocommit: bool = False)` signature: sync `database.py:379`, async `async_database.py:378` — both pass `autocommit` straight through to psycopg.

**Guard + validation shell** (wraps the seam) — copy from `add_reorder_policy` sync `timescale.py:656-662`:
```python
if not self._db.schema.has_extension("timescaledb"):   # async: if not await self._db.schema.has_extension(...)
    raise ExtensionNotAvailable(
        "TimescaleDB extension not installed. "
        "Run db.schema.create_extension('timescaledb')"
    )
validate_identifiers(view_name, schema)                # utils.py:107
```

**`create` pre-DB guards** (before the extension guard, per RESEARCH §Recommended approach): `validate_identifiers(view_name, schema)` then `if "time_bucket(" not in select_sql: raise ValueError(...)` (D-04). Rendered SQL template — RESEARCH lines 92-97:
```sql
CREATE MATERIALIZED VIEW {schema}.{view_name}
WITH (timescaledb.continuous, timescaledb.materialized_only={true|false})
AS {select_sql}
WITH {NO DATA | DATA}
```
No `%s` values — all structure (booleans render literal `true`/`false`, `NO DATA`/`DATA`).

**`refresh` pre-DB guard** (D-05, **deliberate divergence** from Phase-30 `drop_chunks` — do NOT copy the `str→%s::interval` cast): reject non-`datetime`/non-`None` bounds with `ValueError`. Template — RESEARCH line 128:
```sql
CALL refresh_continuous_aggregate('{schema}.{view_name}', %s, %s)
```
params `[window_start, window_end]` (both always present, D-06; `None` → SQL `NULL`). Run on the autocommit cursor.

---

### `add_continuous_aggregate_policy` — PLAIN `execute()` (NOT the seam, D-01)

**Analog:** `add_reorder_policy` — sync `timescale.py:622-667`, async `:1198-1241`. This is the closest analog in the repo; mirror it line-for-line.

Sync skeleton (from `timescale.py:656-667`):
```python
if not self._db.schema.has_extension("timescaledb"):   # async line 1230: if not await ...
    raise ExtensionNotAvailable(
        "TimescaleDB extension not installed. "
        "Run db.schema.create_extension('timescaledb')"
    )
validate_identifiers(view_name, schema)                # + validate_interval per offset (see below)
ne = ", if_not_exists => true" if if_not_exists else ""   # timescale.py:664 — verbatim
self._db.execute(                                      # async: await self._db.execute(...)
    f"SELECT add_continuous_aggregate_policy('{schema}.{view_name}', ...{ne}) AS job_id"
)
```
Named args `start_offset =>`, `end_offset =>`, `schedule_interval =>` (RESEARCH Task 4). **`None` offset → render literal `NULL`, NOT `INTERVAL 'None'`** (RESEARCH Open-Q #2 — branch each fragment). License error (`FeatureNotSupported`/`0A000`) must **propagate** — no swallow in method body (mirrors reorder docstring `timescale.py:651-654`).

**Offset validation** (D-07), order: `validate_interval(start_offset)` / `validate_interval(end_offset)` (skip when `None`) → `_check_offset_ordering(...)` → `validate_interval(schedule_interval)`.

`validate_interval` is at `utils.py:125` (raises `InvalidIdentifier` on bad syntax; accepts `second|minute|hour|day|week|month|year` via `_INTERVAL_PATTERN` `utils.py:16`).

New module helper `_check_offset_ordering` (no exact analog — new pure logic from RESEARCH lines 359-373):
```python
_OFFSET_RE = re.compile(r"^(\d+)\s+(second|minute|hour|day|week)s?$", re.IGNORECASE)
# both same fixed unit → integer compare → ValueError if start <= end;
# None / mixed-unit / month|year → return (defer to DB)
```

---

### `tests/test_timescale.py` — mock SQL-shape (AUTHORITATIVE, all 3 methods)

**Analog:** `TestAddReorderPolicyMock` (`test_timescale.py:936-1012`). Copy the four-test shape per method:

1. **sync SQL-shape** (`:943-960`): `MagicMock(spec=SchemaAccessor)`, `has_extension=MagicMock(return_value=True)`, `db._schema = mock_schema`, `db.execute = MagicMock(...)`; call method; `mock_schema.has_extension.assert_called_once_with("timescaledb")`; assert SQL substrings.
2. **sync no-extension** (`:962-977`): `has_extension=MagicMock(return_value=False)` → `pytest.raises(ExtensionNotAvailable, match="TimescaleDB extension not installed")`; `db.execute.assert_not_called()`.
3. **async SQL-shape** (`:979-995`): `MagicMock(spec=AsyncSchemaAccessor)`, `has_extension=AsyncMock(return_value=True)`, `db.execute=AsyncMock(...)`, `await` the call.
4. **async no-extension** (`:997-1012`): `has_extension=AsyncMock(return_value=False)` → raises. **This is the Phase-23 `await`-omission catch** — a missing `await` makes the coroutine truthy and this test fails. One per new async method (mandatory).

**Seam-specific divergence for create/refresh:** the mock must intercept `self._db.connect(autocommit=True)` (a context manager whose `conn.execute` is a `MagicMock` capturing SQL), and assert `connect` was called with `autocommit=True` — proving they bypass `self._db.execute`. For the **policy** test, assert `connect` was **NOT** called (it uses plain `db.execute`). For create-ValueError / refresh-ValueError / policy-offset-ValueError tests, assert the seam/`execute` was never opened (raise is pre-DB).

### `tests/test_timescale.py` — live-tolerant integration (all 3 methods)

**Analog:** `test_add_reorder_policy_live` (`test_timescale.py:1140-1163`) + async `:1165-1189`. Pattern: `_make_hypertable(ts_db, table, days=...)` (`test_timescale.py:85`) inside `try: ... finally: DROP TABLE`, with an inner `try: <call + Community-build assert> except FeatureNotSupported: pass` (`:1149-1161`). `FeatureNotSupported` imported at `test_timescale.py:26`. Community-build assertions use inlined `timescaledb_information.continuous_aggregates` / `.jobs` queries (RESEARCH Task 6 columns) — no `queries.py` constant.

Fixtures already present: `ts_db` (`:46`), `async_ts_db` (`:63`), `_make_hypertable` (`:85`). No new fixtures, no `conftest.py` change.

## Shared Patterns

### Autocommit isolation seam
**Source:** `pycopg/etl.py:787` / `:811` (sync), `:1486` / `:1508` (async)
**Apply to:** `create_continuous_aggregate`, `refresh_continuous_aggregate` (both sync+async) ONLY. Use plain `conn.execute` (no cursor wrapper) since nothing is fetched.

### Extension guard (`ExtensionNotAvailable`)
**Source:** `pycopg/timescale.py:656-660` (sync), `:1230-1234` (async)
**Apply to:** all 3 new methods, both classes. **Async MUST `await self._db.schema.has_extension(...)`** — recurring Phase-23 bug; the async no-extension mock test (analog `:997`) is the guard against it.

### Identifier / interval validation
**Source:** `validate_identifiers` (`utils.py:107`), `validate_interval` (`utils.py:125`)
**Apply to:** `view_name`/`schema` in all 3; `start_offset`/`end_offset`/`schedule_interval` in the policy method (skip `None` offsets).

### Policy method shape (`SELECT add_*_policy(...)` + `if_not_exists`)
**Source:** `pycopg/timescale.py:622-667` (`add_reorder_policy`); siblings `add_compression_policy:209`, `add_retention_policy:246`
**Apply to:** `add_continuous_aggregate_policy`. Plain `execute()`, `ne = ", if_not_exists => true" if if_not_exists else ""` verbatim, license error propagates.

### License-tolerant live test
**Source:** `test_timescale.py:1140-1163` / `:1165-1189`; secondary `test_database_integration.py:867-877`
**Apply to:** all 3 new methods' live integration tests.

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `_check_offset_ordering` helper | pure validator | transform | New same-unit regex comparator (D-07); no existing equivalent. Pattern modeled on `validate_interval` call sites but logic is new (RESEARCH lines 359-373). |

## Confirmed No-Change

- `pycopg/queries.py` — RESEARCH §Task 6: cagg DDL rendered inline like every other timescale method; info-view test assertions inlined per Phase-30 precedent (`test_database_integration.py:1154`). **No constant added.**
- `pycopg/exceptions.py` — `TimescaleError` (`:54`), `ExtensionNotAvailable` (`:24`) already present (Phase 30). No change.
- `tests/test_parity.py` — `ACCESSOR_PAIRS` (`:24-25`) already registers `(TimescaleAccessor, AsyncTimescaleAccessor)`; `test_accessor_parity` (`:36`) auto-covers the 3 new methods. **No registry change.**

## Metadata

**Analog search scope:** `pycopg/{etl.py,timescale.py,utils.py,exceptions.py,database.py,async_database.py,queries.py}`, `tests/{test_timescale.py,test_parity.py,test_database_integration.py}`
**Files scanned:** 10
**Pattern extraction date:** 2026-06-23
