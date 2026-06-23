# Phase 32: Query Helpers & Parity Verification - Pattern Map

**Mapped:** 2026-06-23
**Files analyzed:** 2 (pycopg/timescale.py, tests/test_timescale.py; +1 explicit assert in tests/test_parity.py)
**Analogs found:** 10 / 10 (all from the v0.6.0 spatial accessor + existing timescale/chunk-mgmt code)

> **Line-number drift vs CONTEXT.md (verified live, commit at HEAD):**
> - `spatial.py` async `_run` is at **1942** (CONTEXT said `~1945` — within tolerance, exact = 1942–1968).
> - Spatial module-level builders are **public** `build_*_sql` (no leading `_`) returning `tuple[str, list]` — e.g. `build_contains_sql` at **188** (CONTEXT's "module-level builder pattern" — the *role* analog; note naming convention is public `build_*_sql`, NOT `_build_*`). The phase's new builders are named `_build_time_bucket_sql` per D-05 (Claude's discretion on name — fine, but note divergence from spatial's public naming).
> - `_check_into` **970–992**, `_to_named_binds` **995–1021**, sync `_run` **1051–1077** — all exactly as cited.
> - `TimescaleAccessor` class **152**, sync `create_hypertable` guard **204**; `AsyncTimescaleAccessor` class **972**, async `create_hypertable` guard **1022** — exact.
> - `database.py:935` `pd.read_sql(text(sql), ..., params=params)` — exact. Async sink is `async_database.py:770` (CONTEXT said `731+`; 731 is the `def to_dataframe`, the read_sql line is 770).
> - utils: `validate_identifier` 78, `validate_identifiers` 107, `validate_interval` 125 — exact.
> - `ACCESSOR_PAIRS` 24 (timescale pair line 25), `test_accessor_parity` 36 (decorator 35) — exact; timescale pair already registered.

## File Classification

| New/Modified File | Symbol(s) | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|-----------|------|-----------|----------------|---------------|
| `pycopg/timescale.py` | `_build_time_bucket_sql`, `_build_time_bucket_gapfill_sql` | module-level builder | transform (→ `(sql, params)`) | `spatial.py:188 build_contains_sql` | exact (role+flow) |
| `pycopg/timescale.py` | `_to_named_binds` (local copy) | utility | transform | `spatial.py:995` | exact (copy verbatim) |
| `pycopg/timescale.py` | `_check_into` (timescale-local) | utility/guard | request-response | `spatial.py:970` | role-match (INVERSE valid set) |
| `pycopg/timescale.py` | sync `_run` | dispatcher | request-response | `spatial.py:1051` | exact |
| `pycopg/timescale.py` | async `_run` | dispatcher | request-response | `spatial.py:1942` | exact |
| `pycopg/timescale.py` | sync `time_bucket`, `time_bucket_gapfill` | accessor method | query (read SELECT) | `timescale.py:204` guard + `spatial` `_run` routing | role-match |
| `pycopg/timescale.py` | async `time_bucket`, `time_bucket_gapfill` | accessor method | query (read SELECT) | `timescale.py:1022` guard + `spatial` async `_run` | role-match |
| `tests/test_timescale.py` | mock SQL-shape tests | test | request-response | `test_timescale.py:118` | exact |
| `tests/test_timescale.py` | real live tests | test | query | `test_timescale.py:440` | exact (REAL asserts per D-08) |
| `tests/test_parity.py` | explicit 9-name assert | test | — | `test_parity.py:36` (auto-covers; add named set) | exact |

## Pattern Assignments

### `_build_time_bucket_sql` / `_build_time_bucket_gapfill_sql` (module-level builder, transform)

**Analog:** `pycopg/spatial.py:188-258` `build_contains_sql` — the canonical `(sql, params)` pure builder: validate identifiers up front, interpolate validated identifiers into f-string, append runtime values to a `params: list`, return `(sql, params)`.

**Shape to mirror** (`spatial.py:202`, `247-253`):
```python
) -> tuple[str, list]:
    """..."""
    validate_identifiers(table, schema, geom)   # identifiers interpolated, not bound
    ...
    params: list = []
    # ... append runtime values as %s binds ...
    return sql, params
```

Local in-repo precedent for the **fragment+params** style (timescale's own): `timescale.py:30-83` `_build_chunk_bound_fragments` returns `(older_frag, newer_frag, params)` with `%s` binds and `%s::interval` for str — same param-ordering discipline the gapfill double-bind (D-10) needs.

**For `_build_time_bucket_gapfill_sql` (D-01, D-10):** builder owns the `AS bucket` alias (D-01), and binds `start`/`finish` **twice** — once in `time_bucket_gapfill(%s, <col>, %s, %s)` args and once in `WHERE <col> >= %s AND <col> < %s` — so `params = [bucket_width, start, finish, start, finish, *where_params]`. Exact template (named-vs-positional gapfill args, `>=`/`<` inclusivity) is **planner/researcher live-verify** per D-10/Discretion.

---

### `_to_named_binds` (utility, transform) — COPY VERBATIM

**Analog:** `pycopg/spatial.py:995-1021`. Per D-06 copy into `timescale.py` (do NOT import). Excerpt:
```python
def _to_named_binds(sql: str, params: list) -> tuple[str, dict]:
    """Convert ``%s`` placeholders to named binds for SQLAlchemy ``text()``."""
    parts = sql.split("%s")
    out = parts[0]
    binds: dict = {}
    for i, part in enumerate(parts[1:]):
        out += f":p{i}{part}"
        binds[f"p{i}"] = params[i]
    return out, binds
```

---

### `_check_into` (timescale-local guard) — MIRROR SHAPE, DO NOT IMPORT (D-03)

**Analog:** `pycopg/spatial.py:962, 970-992`. Spatial's `_VALID_INTO = ("rows", "gdf")` — the **INVERSE** of what timescale needs. Mirror the *shape* with a timescale-local set:
```python
# spatial.py:962, 986-987 — the shape to mirror:
_VALID_INTO = ("rows", "gdf")          # timescale uses ("df", "rows"), default "df"
def _check_into(into: str, helper: str) -> None:
    if into not in _VALID_INTO:
        raise ValueError(f"into must be one of {_VALID_INTO}, got {into!r}")
```
Timescale version: valid set `("df", "rows")`, default `"df"`; raises `ValueError` before any SQL — this is how `into="gdf"` is rejected (criterion #1). No scalar-helper sub-check needed (no `_SCALAR_HELPERS` concept here).

---

### sync `_run` (dispatcher, request-response)

**Analog:** `pycopg/spatial.py:1051-1077`. Excerpt the `into=` dispatch:
```python
def _run(self, sql, params, into, geometry_column):
    if into == "gdf":
        named_sql, binds = _to_named_binds(sql, params)
        return self._db.to_geodataframe(sql=named_sql, params=binds, geometry_column=geometry_column)
    return self._db.execute(sql, params)
```
Timescale mirror: `if into == "df": named_sql, binds = _to_named_binds(sql, params); return self._db.to_dataframe(sql=named_sql, params=binds)` else `return self._db.execute(sql, params)`. Drop the `geometry_column` arg (no geometry — Discretion).

---

### async `_run` (dispatcher, request-response) — D-07 await audit

**Analog:** `pycopg/spatial.py:1942-1968`. Exact mirror with `await`:
```python
async def _run(self, sql, params, into, geometry_column):
    if into == "gdf":
        named_sql, binds = _to_named_binds(sql, params)
        return await self._db.to_geodataframe(sql=named_sql, params=binds, geometry_column=geometry_column)
    return await self._db.execute(sql, params)
```
**FLAG (recurring Phase-23/30/31 gotcha):** the per-method extension guard must be `await`ed in the async path — `if not await self._db.schema.has_extension("timescaledb")` (see async analog at `timescale.py:1022`), and `await self._db.to_dataframe(...)` / `await self._db.execute(...)` in `_run`.

---

### sync `time_bucket` / `time_bucket_gapfill` (accessor method, query)

**Guard analog:** `pycopg/timescale.py:204-210` (`create_hypertable`):
```python
if not self._db.schema.has_extension("timescaledb"):
    raise ExtensionNotAvailable(
        "TimescaleDB extension not installed. Run db.schema.create_extension('timescaledb')"
    )
validate_identifiers(table, schema, time_column)
validate_interval(chunk_time_interval)
```
Method body shape (D-05): guard → `_check_into(into, "time_bucket")` → `validate_identifiers(table, schema, time_column)` (+ `validate_interval(bucket_width)` if treating bucket_width as interval — but D-09 binds it as `%s`, so likely no validate_interval; planner's call) → `sql, params = _build_time_bucket_sql(...)` → `return self._run(sql, params, into)`.

### async `time_bucket` / `time_bucket_gapfill` (accessor method, query)

**Guard analog:** `pycopg/timescale.py:1022-1028` (awaited twin of above). Same body but `await self._db.schema.has_extension(...)` and `return await self._run(...)`. Methods land near class `AsyncTimescaleAccessor` (line 972), appended after existing methods.

---

### `to_dataframe(sql=, params=dict)` named-bind sink (D-02)

**Sync:** `pycopg/database.py:935`:
```python
return pd.read_sql(text(sql), self.engine, params=params)
```
**Async:** `pycopg/async_database.py:770`:
```python
lambda sync_conn: pd.read_sql(text(sql), sync_conn, params=params)
```
Both wrap SQL in SQLAlchemy `text()` → `%s` will NOT bind; must use `:pN` named binds (hence `_to_named_binds` on the `into="df"` path). `into="rows"` uses `db.execute(sql, params)` with the positional `%s` list directly.

---

### Identifier / interval validators (`pycopg/utils.py`)

```python
def validate_identifier(name: str) -> None: ...      # utils.py:78
def validate_identifiers(*names: str) -> None: ...    # utils.py:107  (skips None)
def validate_interval(interval: str) -> None: ...     # utils.py:125
```
Use `validate_identifiers(table, schema, time_column)` (interpolated into the f-string SQL). `bucket_width`/`start`/`finish`/`where`-params are bound as `%s`, not validated (D-09).

---

### Tests — two-layer pattern (D-08)

**Mock SQL-shape analog:** `tests/test_timescale.py:118-194`. Pattern: `MagicMock(spec=SchemaAccessor)` with `has_extension → True`, `db.execute = MagicMock(...)`, call the method, then `sql, params = db.execute.call_args[0]` and assert SQL substrings + params. For `into="df"` tests, mock `db.to_dataframe` and assert the named-bind dict instead. Add a test asserting `into="gdf"` raises `ValueError`.

**Real live analog:** `tests/test_timescale.py:440-453` (`test_show_chunks_returns_list`) — uses `ts_db` fixture, `_make_hypertable(ts_db, table, days=...)` (helper at `test_timescale.py:85`), asserts on **real output**, drops table in `finally`. Async twin uses `async_ts_db` fixture (`test_timescale.py:63`).

**CRITICAL (D-08):** gapfill/`time_bucket`/`locf`/`interpolate` are Apache-licensed (free) — live tests assert REAL gap-filled output (NULL-padded buckets present, `bucket` column, aggregate values). Do **NOT** wrap in `try/except FeatureNotSupported` (that was Phase-31's TSL-only cagg pattern; `FeatureNotSupported` is imported at `test_timescale.py:26` but must NOT be used here). Live tests pass Python `datetime` objects for `start`/`finish` (ROADMAP criterion #2).

**Fixtures (`tests/test_timescale.py`):** `ts_db` (46), `async_ts_db` (63) — create-extension-or-skip.

---

### Parity proof (D-11)

**Analog:** `tests/test_parity.py:35-61` `test_accessor_parity`, parametrized over `ACCESSOR_PAIRS` (line 24). The `(TimescaleAccessor, AsyncTimescaleAccessor)` pair is **already registered** (line 25) — adding the 2 methods to both classes auto-satisfies bidirectional set-diff parity, **no registry change**. The test does symmetric `sync_methods - async_methods` / `async_methods - sync_methods` over public (non-`_`) members.

**D-11 explicit assert (NEW):** add ONE test asserting the timescale pair exposes the expected 9 v0.8.0 method names as a named set (so a dropped/renamed method fails loudly). The 9 = the v0.8.0 additions across Phases 30–32 (e.g. `show_chunks`, `drop_chunks`, `add_dimension`, cagg create/refresh/policy trio, `time_bucket`, `time_bucket_gapfill` — planner confirms the exact 9 from ROADMAP/REQUIREMENTS). No per-method signature parity (deferred, D-11).

## Shared Patterns

### Pure-builder + lazy-accessor
**Source:** `spatial.py:188` (`build_*_sql`) + `spatial.py:1051/1942` (`_run`).
**Apply to:** both new methods × both classes — module builder returns `(sql, params)`; sync/async methods stay thin and identical, sharing the builder.

### Per-method extension guard
**Source:** `timescale.py:204` (sync) / `timescale.py:1022` (async).
**Apply to:** all 4 new methods. Async MUST `await self._db.schema.has_extension("timescaledb")` (D-07 await audit).

### `%s` → named-bind for the DataFrame path
**Source:** `spatial.py:995` `_to_named_binds` + `database.py:935` / `async_database.py:770`.
**Apply to:** the `into="df"` branch of both `_run` dispatchers.

## No Analog Found

None. Every symbol maps cleanly to a v0.6.0 spatial-accessor or existing timescale/chunk-mgmt precedent.

## Metadata

**Analog search scope:** `pycopg/{spatial,timescale,database,async_database,utils}.py`, `tests/{test_timescale,test_parity}.py`
**Files scanned:** 7
**Pattern extraction date:** 2026-06-23
