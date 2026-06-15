# Phase 17: Run-Tracking Foundation - Pattern Map

**Mapped:** 2026-06-15
**Files analyzed:** 2 modified
**Analogs found:** 2 / 2 (both exact, in-repo)

This phase is a tight mirror of the existing `spatial.py` / `db.spatial` accessor
pattern. Every new construct has a byte-close analog already in the codebase — no
RESEARCH.md fallback is needed. All excerpts below are read-only references; the only
file this agent wrote is this PATTERNS.md.

## File Classification

| Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------|------|-----------|----------------|---------------|
| `pycopg/etl.py` (add `class ETLAccessor`) | accessor / service | CRUD (run-log INSERT/UPDATE), request-response (init DDL) | `pycopg/spatial.py` `class SpatialAccessor` (L1023-1048) | exact (role + module-twin) |
| `pycopg/database.py` (add `self._etl` field + `etl` property) | provider / lazy-accessor wiring | request-response | `pycopg/database.py` `spatial` property (L228-249) + `self._spatial` field (L84) | exact (same file, same pattern) |

No new file is created. No `async_database.py` change (Phase 20). No new `queries.py`
constant — `ETL_INIT_PIPELINE_RUNS` / `ETL_INSERT_RUN` / `ETL_UPDATE_RUN` already exist
(Phase 16). No migration file — table is created at runtime via idempotent DDL.

## Pattern Assignments

### `pycopg/etl.py` — add `class ETLAccessor` (accessor, CRUD + DDL)

**Analog:** `pycopg/spatial.py` `class SpatialAccessor` — `__init__(self, db)` + `self._db` shape.

**`__init__` pattern** (`spatial.py` L1033-1048). Copy the `self._db = db` store. Drop the
PostGIS extension guard — `ETLAccessor` takes **no** `schema` arg (D-08) and has **no**
construction-time extension check (run-log is core, not an extension):

```python
class SpatialAccessor:
    def __init__(self, db: Database) -> None:
        self._db = db
        if not db.has_extension("postgis"):          # <- ETLAccessor OMITS this guard
            raise ExtensionNotAvailable(_POSTGIS_GUARD_MSG)
```

`ETLAccessor.__init__` reduces to `self._db = db` only.

**Module header / imports pattern** (`etl.py` L25-32 — already present in the target file).
New imports `ETLAccessor` needs: `TYPE_CHECKING` guard for `Database` (mirror `spatial.py`
L29, L34-38), and the three SQL constants via the existing `from pycopg import queries`
already imported at L30 (reference as `queries.ETL_INSERT_RUN`, etc.). Add a `traceback`
stdlib import only if `_end_run`/`run()` captures `error_traceback` here (Claude's Discretion).

```python
# spatial.py L34-38 — the TYPE_CHECKING block to mirror for the Database type:
if TYPE_CHECKING:
    from pycopg.database import Database
```

**Core CRUD pattern — `init()` / `_start_run` / `_end_run`.** All three route through the
single existing `Database.execute(sql, params, autocommit=True)` method
(`database.py` L402-425). `execute` already: opens a fresh cursor over `connect()`
(L421), returns `RETURNING` rows via `cur.fetchall()` (L423-424), and returns `[]` for
non-SELECT statements. This *is* the "fresh, short-lived autocommit connection per write"
of D-04 — no new connection plumbing is required, because `cursor(autocommit=True)` →
`connect(autocommit=True)` → `_connect_with_retry` opens-and-closes per call.

- `init()` → `self._db.execute(queries.ETL_INIT_PIPELINE_RUNS, autocommit=True)`.
  (Equivalent: `sql, params = build_init_sql(); self._db.execute(sql, params, autocommit=True)`
  — `build_init_sql()` at `etl.py` L252-279 returns `(ETL_INIT_PIPELINE_RUNS, [])`. Pick the
  form consistent with how `_start_run`/`_end_run` consume their constants — Claude's Discretion.)

- `_start_run(name) -> int` → INSERT … RETURNING:
  ```python
  rows = self._db.execute(
      queries.ETL_INSERT_RUN,           # queries.py L264-268
      [name, "running", <started_at>],  # %s order: pipeline_name, status, started_at
      autocommit=True,
  )
  return rows[0]["run_id"]              # execute returns list[dict]; RETURNING run_id
  ```

- `_end_run(run_id, status, rows_extracted, rows_loaded, error_message=None, error_traceback=None)`
  → UPDATE:
  ```python
  self._db.execute(
      queries.ETL_UPDATE_RUN,           # queries.py L270-279
      # %s order: status, finished_at, rows_extracted, rows_loaded,
      #           error_message, error_traceback, run_id
      [status, <finished_at>, rows_extracted, rows_loaded,
       error_message, error_traceback, run_id],
      autocommit=True,
  )
  ```

**SQL constants consumed** (read-only — already authored Phase 16):

```sql
-- queries.py L264-268
ETL_INSERT_RUN = INSERT INTO pipeline_runs (pipeline_name, status, started_at)
                 VALUES (%s, %s, %s) RETURNING run_id
-- queries.py L270-279
ETL_UPDATE_RUN = UPDATE pipeline_runs SET status=%s, finished_at=%s,
                 rows_extracted=%s, rows_loaded=%s, error_message=%s,
                 error_traceback=%s WHERE run_id=%s
-- queries.py L249-262: ETL_INIT_PIPELINE_RUNS (CREATE TABLE IF NOT EXISTS, 3-valued CHECK)
```

CHECK is 3-valued `('running','success','failed')` — use literal `'failed'`, never the
research example's `"error"` (D-07). Status `'dry_run'` is never persisted.

**Error handling pattern.** D-06: do **not** wrap run-log writes in try/except-and-warn. Let
the exception propagate — `_connect_with_retry` (`database.py` L251-260, tenacity `@retry`
on `OperationalError`, `reraise=True`) already retries transient failures, then surfaces. A
left-`running` row is an honest signal, not papered over. `ETLAccessor` introduces **no new
exception types** (D-11).

**Optional `run()` stub** (D-03). If the planner wants the auto-create + start/end seam
testable now, a thin `run()` may call `self.init()` (auto-create hook) then `_start_run`/
`_end_run`, but extract/transform/load bodies are Phase 18/19 — do not implement them here.

---

### `pycopg/database.py` — add `self._etl` field + `etl` property (provider, request-response)

**Analog:** the `spatial` lazy property and its `self._spatial` field — same file.

**Field declaration pattern** (`database.py` L82-84). Add `self._etl` alongside, identical shape:

```python
self._engine: Engine | None = None
self._session_conn: psycopg.Connection | None = None
self._spatial: SpatialAccessor | None = None
# ADD: self._etl: ETLAccessor | None = None
```

**Lazy property pattern** (`database.py` L228-249). Copy the body exactly: `None`-check,
in-property import (avoids import cycle), store, return. The `ETLAccessor` property has **no**
extension-guard docstring clause (no `Raises` for `ExtensionNotAvailable`):

```python
@property
def spatial(self) -> SpatialAccessor:
    if self._spatial is None:
        from pycopg.spatial import SpatialAccessor
        self._spatial = SpatialAccessor(self)
    return self._spatial
```

→ becomes:

```python
@property
def etl(self) -> ETLAccessor:
    if self._etl is None:
        from pycopg.etl import ETLAccessor
        self._etl = ETLAccessor(self)
    return self._etl
```

Use a numpydoc docstring with `Returns` only (no `Raises`). Add the `ETLAccessor` symbol to
the `TYPE_CHECKING` import block at the top of `database.py` (mirror however `SpatialAccessor`
is type-imported for the field annotation).

---

## Shared Patterns

### Fresh autocommit connection per write (the core of this phase)
**Source:** `pycopg/database.py` `execute` L402-425 → `cursor` L282+ → `connect` L262-280 →
`_connect_with_retry` L251-260 (tenacity `@retry`, `reraise=True`).
**Apply to:** every `ETLAccessor` run-log write (`init`, `_start_run`, `_end_run`).
**Pattern:** call `self._db.execute(SQL, params, autocommit=True)`. This already opens-and-
closes one connection per call (open-per-operation idiom — same as `notify` L575, `create_role`
L2088, `vacuum` L1968). Never reuse the load transaction (D-05).

```python
# database.py L262-280 — connect(): open, yield, close-in-finally (the per-write lifecycle)
@contextmanager
def connect(self, autocommit: bool = False) -> Iterator[psycopg.Connection]:
    conn = self._connect_with_retry(autocommit=autocommit)
    try:
        yield conn
    finally:
        conn.close()
```

### Lazy accessor namespace wiring
**Source:** `database.py` L82-84 (field) + L228-249 (property).
**Apply to:** the `db.etl` wiring. Field `None` default + in-property import + store + return.

### `%s`-only SQL constants, no identifier interpolation
**Source:** `etl.py` L16-22 module docstring; `queries.py` L264-279.
**Apply to:** all run-log writes — they bind only values via `%s`, touch no user identifiers,
so **no** `validate_identifiers` call is needed (D-08/D-12). `pipeline_runs` stays unqualified
(resolves via `search_path`).

### numpydoc docstrings
**Source:** project CLAUDE.md + every method in `spatial.py` / `database.py`.
**Apply to:** all new methods/properties. Match the `Parameters` / `Returns` / `Raises` style
shown in `spatial.py` L1033-1048 and `database.py` L228-249. Run `ruff check` + `black`.

## No Analog Found

None. Every Phase 17 construct mirrors an existing in-repo pattern.

## Metadata

**Analog search scope:** `pycopg/spatial.py`, `pycopg/database.py`, `pycopg/queries.py`,
`pycopg/etl.py`.
**Files scanned:** 4.
**Pattern extraction date:** 2026-06-15.
