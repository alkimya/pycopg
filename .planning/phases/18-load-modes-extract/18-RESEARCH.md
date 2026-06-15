# Phase 18: Load Modes & Extract - Research

**Researched:** 2026-06-15
**Domain:** ETL extract + load mechanics (psycopg/pandas), transactional atomicity, identifier safety
**Confidence:** HIGH (all findings verified against live source + empirical psycopg 3.3.4 probes)

## Summary

Phase 18 fills the body of the Phase 17 `run()` stub: extract → transform → load under
append/replace/upsert, with `validate_identifiers` on every identifier and a transactionally
atomic replace. The CONTEXT.md decisions D-01..D-07 are sound in spirit, and the cited line
numbers are accurate against the live source. **However, one decision (D-01/D-04's literal
"call `db.insert_batch`/`db.upsert_many` inside one `db.transaction()`") is contradicted by
the live code path and would silently break SC-3 atomicity.** This is the single most important
finding of this research and is documented in full below.

The root cause: `Database.cursor()` (database.py:319-330) **commits the session connection at
each cursor exit** when the transaction status is `INTRANS`. `insert_batch` and `upsert_many`
both acquire their cursor via `self.cursor()`. Therefore composing TRUNCATE + INSERT through
those public methods does NOT produce one atomic transaction — empirically verified: a mid-load
failure leaves the target **empty** (`[]`), exactly the Pitfall 2 disaster. Worse, wrapping
those methods inside an explicit `db.transaction()` block **crashes** with psycopg's
`ProgrammingError: Explicit commit() forbidden within a Transaction context`.

**Primary recommendation:** The `replace` load path must execute TRUNCATE + INSERT **on the
single connection yielded by `db.transaction()`, building the INSERT SQL inline (reusing the
existing builder logic) rather than calling `db.insert_batch`/`db.upsert_many`** — because those
methods route through the premature-committing `Database.cursor()`. The accessor opens
`db.session()` internally (Claude's-Discretion recommendation) and runs the load inside one
`db.transaction()` on the yielded conn. `append` and `upsert` can technically use a single
`Database.cursor()` op (one statement = atomic), but for uniformity and identifier-validation
reuse, build all three load SQLs via the same inline path on the transactional conn. Every load
SQL still flows through `validate_identifiers` (SC-6).

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** All row writes go through psycopg-native primitives inside one `db.transaction()` —
  never through `from_dataframe`/`to_sql` for the row insert (it runs on the SQLAlchemy engine,
  a different connection; `to_sql`-based replace would leave the target empty on mid-load failure,
  violating SC-3). append → insert path; replace → TRUNCATE + insert in one transaction;
  upsert → `INSERT … ON CONFLICT DO UPDATE`.
- **D-02 (atomicity mechanism — MUST verify):** `insert_batch`/`upsert_many`→`insert_many`
  acquire their cursor via `self.cursor()`; `Database.cursor()` and `db.transaction()` reuse
  `self._session_conn` only when a session is active, else open their own connection that commits
  at exit. A bare `db.insert_batch()` does NOT join an outer `db.transaction()`. To make
  TRUNCATE + INSERT atomic on one connection, the load must run inside `db.session()`. Run-log
  writes must STAY isolated (dedicated autocommit conn, Phase 17); load writes must SHARE one
  transactional connection (this phase). **VERIFIED — with a critical correction, see Q1 below.**
- **D-03:** Existence checked via catalog query before load. append missing → raise
  `ETLTargetNotFoundError` (do not create). replace missing → create empty table once via
  `from_dataframe(if_exists='replace')` on a zero-row frame, then TRUNCATE + insert atomically.
  upsert missing → planner's call; lean toward raising `ETLTargetNotFoundError` (upsert needs a
  pre-existing unique index for ON CONFLICT — Pitfall 3).
- **D-03a:** Did NOT hand-build `CREATE TABLE IF NOT EXISTS` from DataFrame dtypes; zero-row
  `to_sql` create is the chosen mechanism.
- **D-04:** Reuse existing validated methods; author no new load builders. Only new builder is
  `build_truncate_sql()` (already shipped). The research sketch of a pure `build_upsert_sql()` is
  superseded by `upsert_many` — do not add it. **PARTIALLY CONTRADICTED by live code — see Q1.**
- **D-04a:** Authoring fresh pure `build_upsert_sql()`/`build_append_sql()` rejected (duplicates
  SQL `insert_batch`/`upsert_many` already validate). Truncate builder is the sole exception.
- **D-05:** Transform dispatch: `None` → identity no-op; single `Callable` → applied once;
  `list[Callable]` → applied in sequence, each receiving the previous step's output.
- **D-06:** On transform exception, raise `ETLTransformError` whose message identifies the
  failing step by step index AND function name (e.g. `transform step 2 ('normalize') raised
  ValueError: …`). Use `__name__`, fall back to `repr()` for lambdas/`partial`. Chain original
  (`raise ... from exc`) so traceback is preserved (ETL-08). Failed run recorded via
  `_end_run(status='failed', …)`. Index base 0 vs 1 is Claude's discretion (state in docstring).
- **D-07:** Load consumes the post-transform DataFrame, converts to `list[dict]`, reports
  `rows_loaded` = the int returned by the load methods (`cur.rowcount` sum). Exact DataFrame→dict
  conversion and NaN/tz handling deferred to research/planner; verify how existing
  `from_dataframe`/pandas path handles NaN and tz-naive timestamps for consistency.

### Claude's Discretion
- Whether the load body opens its own `db.session()` internally or documents that callers manage
  it — D-02 atomicity must hold regardless. Recommend the accessor opens the session internally.
- Transform step index base (0 vs 1) in the `ETLTransformError` message.
- Exact `rows_extracted` source (likely `len(df)` after extract, before transform) and how
  `extract_limit` is appended (`LIMIT %s` param vs the existing `to_dataframe` surface).
- The exact catalog-existence query (`to_regclass(...)` vs `information_schema`) for D-03.
- Whether `run()` returns `run_id`, a counts tuple, or a dict in Phase 18 (Phase 19 upgrades to
  `RunResult` — keep it minimal, don't pre-build `RunResult`).
- DataFrame→`list[dict]` conversion call (`to_dict(orient='records')` vs `itertuples` vs
  `to_records`) per D-07, after verifying NaN/tz behavior.
- Whether `Pipeline` (and any new symbols) get exported in `__init__.py` now or in Phase 20
  (currently only the 3 ETL exceptions are exported; pull forward only if a test needs it).

### Deferred Ideas (OUT OF SCOPE)
- `extract_batch_size` streaming (chunked extract) — v0.6.0. Phase 18 honors `extract_limit` only.
- COPY-based / staging-table truncate-load — deferred. Phase 18 uses TRUNCATE + insert in one txn.
- Advisory-lock concurrency guard (`pg_try_advisory_lock`, `PipelineAlreadyRunning`) — not v0.5.0.
- GeoDataFrame-aware load — deferred.
- `RunResult` / `history()` / `last_run()` / `dry_run` — Phase 19. `run()` returns a minimal value.
- `AsyncETLAccessor` parity — Phase 20.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ETL-02 | Extract from `source` (SQL or table) → DataFrame, delegating to `to_dataframe` | `to_dataframe(table=...)` and `to_dataframe(sql=...)` verified (database.py:1429-1465); `_is_sql_source` heuristic in etl.py:200-224. LIMIT injection mechanism — see Q-extract below. |
| ETL-03 | Transform applied before load; exception → `ETLTransformError` + failed run | Transform dispatch design (Q4); `_end_run(status='failed', ...)` verified (etl.py:368-423). |
| ETL-04 | append; re-run doubles rows; missing target → `ETLTargetNotFoundError` | `table_exists()` verified (database.py:1011-1026); append SQL path (Q1). |
| ETL-05 | replace truncate-load; re-run = latest only; auto-create; TRUNCATE+INSERT atomic | `build_truncate_sql` verified (etl.py:227-256); atomicity mechanism corrected (Q1); zero-row create (Q3). |
| ETL-06 | upsert by `conflict_columns`; re-run no duplicates; ctor guard | `upsert_many` ON CONFLICT verified (database.py:508-551); ctor guard already in `Pipeline.__post_init__` (etl.py:179-182). |
| ETL-16 | transform list applied in sequence; error reports which step | Transform chain design (Q4); single callable & None remain valid (D-05). |
| ETL-09 (must NOT regress) | Load txn separate from run-log txn | Run-log on dedicated autocommit conn verified (etl.py:336-423); load on separate transactional conn (Q1/Q5). |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Extract (source → DataFrame) | API/Backend (`db.to_dataframe` over SQLAlchemy engine) | — | Read path already delegates to pandas `read_sql` on the engine. |
| Transform chain | Application (Python callables in-process) | — | Pure in-memory DataFrame transforms; no DB tier. |
| Load (row writes) | Database (psycopg-native, one transactional conn) | — | Atomicity (SC-3) requires psycopg transaction, NOT the SQLAlchemy engine. |
| Target existence check | Database (catalog query) | — | `to_regclass`/`information_schema` lookup. |
| Run-log writes | Database (dedicated autocommit conn) | — | Must stay isolated from load txn (Phase 17 D-04/D-05, ETL-09). |
| Identifier validation | Application (`validate_identifiers`) before interpolation | — | v0.3.1 invariant; runs before any SQL string is built. |

## Standard Stack

No new packages. Phase 18 composes existing pycopg primitives only (PROJECT.md locked constraint:
zero new runtime deps). Verified environment:

| Library | Version | Purpose | Source |
|---------|---------|---------|--------|
| psycopg | 3.3.4 | Native row writes, transactions, cursors | `uv run python -c "import psycopg; print(psycopg.__version__)"` [VERIFIED] |
| pandas | (installed) | Extract DataFrame, dtype→SQL mapping for zero-row create | imported in database.py [VERIFIED] |
| SQLAlchemy | (installed) | `self.engine` for `to_dataframe`/`from_dataframe` (extract + create only) | database.py:1417,1465 [VERIFIED] |

**No installation step. No Package Legitimacy Audit required** — Phase 18 installs nothing.

## Architecture Patterns

### ETL Execution Flow (sync, corrected)

```
db.etl.run(pipeline)
   │
   ├─ self.init()                          # auto-create pipeline_runs (autocommit conn, Phase 17)
   ├─ run_id = self._start_run(name)       # 'running' row   (dedicated autocommit conn — ISOLATED)
   │
   ├─ try:
   │     df = <extract>                    # db.to_dataframe(table|sql)  (+ LIMIT)   ETL-02
   │     rows_extracted = len(df)          # count BEFORE transform (Claude's discretion)
   │     df = <transform chain>            # None | callable | list   → ETLTransformError  ETL-03/16
   │     rows = <df → list[dict], NaN→None>
   │
   │     with db.session():                # ONE shared connection for the whole load
   │         <existence check>             # to_regclass / table_exists
   │         <replace-only: create-if-missing via from_dataframe zero-row frame>   (D-03)
   │         with db.transaction() as conn:        # ← real psycopg txn on session conn
   │             # append  : execute INSERT on conn directly
   │             # replace : execute TRUNCATE then INSERT on conn directly   ← ATOMIC
   │             # upsert  : execute INSERT … ON CONFLICT on conn directly
   │             rows_loaded += cur.rowcount
   │     # txn commits on clean exit; rolls back on exception (atomic)
   │
   │     self._end_run(run_id, 'success', rows_extracted, rows_loaded)   # autocommit conn — ISOLATED
   │     return run_id
   │
   └─ except (known + unknown):
         self._end_run(run_id, 'failed', rows_extracted, 0,
                       error_message=str(exc), error_traceback=traceback.format_exc())
         raise                              # re-raise original (OD-2) or domain exception
```

The two connection lifetimes are deliberately OPPOSITE (the Phase 17 / Phase 18 duality):
- **Run-log writes:** dedicated autocommit conn — commit immediately, survive load rollback (ETL-09).
- **Load writes:** one shared transactional conn — all-or-nothing (SC-3).

### Anti-Patterns to Avoid
- **Calling `db.insert_batch`/`db.upsert_many` inside a `db.transaction()` block.** Crashes with
  `ProgrammingError: Explicit commit() forbidden within a Transaction context` (empirically
  verified, psycopg 3.3.4). See Q1.
- **Composing TRUNCATE + INSERT as two separate `Database.cursor()`/`db.execute()` ops inside a
  session.** NON-ATOMIC — each cursor exit commits when `INTRANS` (database.py:324-325). A
  mid-load failure leaves the target EMPTY. Empirically verified (Pitfall 2 disaster). See Q1.
- **Using `from_dataframe`/`to_sql` for the row insert.** Runs on the SQLAlchemy engine, a
  different connection from `db.transaction()` (D-01). Only acceptable for the zero-row
  create-if-missing step (D-03), which is consciously non-atomic and only fires when the table
  is absent (nothing to lose).
- **Letting pandas NaN/NaT reach the INSERT params.** Becomes a float-NaN literal, not SQL NULL
  (Integration Gotchas / D-07). See Q2.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TRUNCATE SQL | inline f-string | `build_truncate_sql(table, schema)` (etl.py:227) | Already validates identifiers (SC-6). |
| Identifier safety | regex checks | `validate_identifiers(*names)` (utils.py:76) | The mandated v0.3.1 gate. |
| Empty-table create | hand CREATE TABLE from dtypes | `from_dataframe(zero_row, if_exists='replace')` | Borrows pandas dtype→SQL mapping (D-03/D-03a). |
| Target existence | bespoke catalog SQL | `db.table_exists(name, schema)` (database.py:1011) OR `to_regclass` | Already exists; see Q3 for the schema-qualification caveat. |
| Run-log writes | reinvent | `_start_run`/`_end_run` (Phase 17) | Already isolated on autocommit conns (ETL-09). |
| upsert ON CONFLICT SQL | hand-build | `_build_batch_insert_sql` builder logic (the one `insert_many`/`insert_batch` use) | Already validates. **But execute on the txn conn, not via `self.cursor()` — see Q1.** |

**Key insight:** The existing builders' *SQL-construction + validation logic* is what to reuse;
their *cursor acquisition via `self.cursor()`* is the part that breaks atomicity. The planner
needs the SQL string, executed on the transactional connection.

## Common Pitfalls

### Pitfall 1: The `Database.cursor()` premature-commit trap (CRITICAL — see Q1)
**What goes wrong:** `insert_batch`/`upsert_many` inside a session don't share one transaction;
each `self.cursor()` exit commits when `INTRANS`. TRUNCATE commits before INSERT.
**Why:** database.py:322-325 auto-commits the session connection at cursor exit.
**How to avoid:** Execute load SQL directly on the `db.transaction()`-yielded connection.
**Warning signs:** A replace test where mid-load failure leaves the target EMPTY instead of with
its original rows. (Empirically reproduced: `[]` after failure instead of `[1]`.)

### Pitfall 2: `commit()` forbidden inside a transaction block
**What goes wrong:** Calling a method that internally commits (any `Database.cursor()`-based
method) inside `with db.transaction()` raises `ProgrammingError`.
**Why:** psycopg 3.x `Transaction` context forbids explicit `commit()`.
**How to avoid:** Inside `db.transaction()`, only `cur.execute(...)` on the yielded conn; let the
context manager commit on clean exit.

### Pitfall 3: pandas NaN/NaT → float-NaN literal, not SQL NULL (D-07)
**What goes wrong:** A DataFrame cell that is `NaN`/`NaT` becomes `float('nan')` in the params
list; psycopg sends it as a float NaN, not NULL — corrupting nullable/non-float columns.
**How to avoid:** Coerce `NaN/NaT → None` before building rows. See Q2 for the exact mechanism.

### Pitfall 4: tz-naive `datetime64` into `TIMESTAMPTZ` (D-07)
**What goes wrong:** A tz-naive timestamp loaded into `TIMESTAMPTZ` is interpreted in the
session's `TimeZone` and silently shifts.
**How to avoid:** Document tz-localization as the user's responsibility (matching existing
`from_dataframe` behavior — there is NO tz coercion anywhere in the codebase, verified). Do not
silently coerce. See Q2.

### Pitfall 5: upsert requires a pre-existing unique index (Pitfall 3 in research)
**What goes wrong:** `ON CONFLICT (cols)` errors at runtime if no unique constraint/index matches.
**How to avoid:** Require the upsert target (with its unique constraint) to pre-exist; raise
`ETLTargetNotFoundError` when missing (D-03 recommendation). Do NOT auto-create for upsert.

### Pitfall 6: identifier injection via `target`/`conflict_columns` (SC-6)
**How to avoid:** `validate_identifiers` on every identifier before interpolation; add ETL cases
to `tests/test_sql_injection.py` (see Validation Architecture).

## Code Examples

### Verified: `Database.cursor()` premature commit inside a session (the landmine)
```python
# Source: pycopg/database.py:318-330 (VERIFIED)
if self._session_conn is not None:
    with self._session_conn.cursor(row_factory=dict_row) as cur:
        yield cur
        if not autocommit:
            status = self._session_conn.info.transaction_status
            if status == TransactionStatus.INTRANS:
                self._session_conn.commit()        # ← commits at EACH cursor exit
            elif status == TransactionStatus.INERROR:
                self._session_conn.rollback()
```

### Verified: `db.transaction()` reuses the session conn (the correct atomic seam)
```python
# Source: pycopg/database.py:350-353 (VERIFIED)
if self._session_conn is not None:
    with self._session_conn.transaction():   # real psycopg txn on the session conn
        yield self._session_conn             # ← run TRUNCATE + INSERT on THIS conn directly
```

### Verified pattern: atomic load on the yielded conn (from the Phase 17 test, the model to follow)
```python
# Source: tests/test_etl_accessor.py:344-348 (VERIFIED — this is the working pattern)
with db.session():
    with db.transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)     # execute load SQL directly — NOT via db.insert_batch
        # raising here rolls the whole txn back atomically
```

### Existing upsert SQL the planner reuses (build the SQL, execute on the txn conn)
```python
# Source: pycopg/database.py:543-549 (VERIFIED) — the ON CONFLICT construction
validate_identifiers(*conflict_columns)
validate_identifiers(*update_columns)
conflict_str = ", ".join(conflict_columns)
update_str = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_columns])
on_conflict = f"({conflict_str}) DO UPDATE SET {update_str}"
# Then INSERT ... ON CONFLICT {on_conflict}
```

## Questions Answered (code-grounded)

### Q1 — D-02 atomicity seam (CRITICAL). Confirmed mechanism + correction.

**Verified facts (all line numbers accurate):**
- `Database.cursor()` (database.py:305-336): if `self._session_conn is not None`, yields a cursor
  on the session conn and **commits the session conn at cursor exit when status is INTRANS**
  (lines 322-325). Else opens a fresh connection that commits at exit (lines 331-336).
- `db.transaction()` (database.py:338-357): if session active, `with self._session_conn.transaction(): yield self._session_conn`
  (lines 350-353). Else opens a fresh conn + `conn.transaction()` (lines 354-357).
- `db.session()` (database.py:359-411): sets `self._session_conn = psycopg.connect(...)`;
  commits + closes on exit; always clears `_session_conn` in finally.
- `insert_batch` (database.py:601-669): acquires cursor via `with self.cursor() as cur:` (line 650).
- `insert_many` (database.py:471-506, called by `upsert_many` database.py:508-551): acquires
  cursor via `with self.cursor() as cur:` (line 504). `upsert_many` calls `validate_identifiers`
  twice (lines 543-544); `insert_batch` calls `validate_identifiers(table, schema)` (line 640) +
  per-column `validate_identifier` (lines 643-644). Both return `cur.rowcount` sum (int).

**Proof a bare `db.insert_batch()` does NOT join an outer `db.transaction()`:** outside a session,
`self._session_conn is None`, so `db.transaction()` opens its own conn (line 355) and
`insert_batch`'s `self.cursor()` opens *another* independent conn (line 332) that commits itself
(line 336). Two different connections — no shared transaction. **CONTEXT.md D-02 is correct here.**

**THE CORRECTION (empirically verified, psycopg 3.3.4):** CONTEXT.md D-02/D-04 conclude "run the
load inside `db.session()` so `transaction()`/`cursor()`/`insert_batch`/`upsert_many` all share
`self._session_conn`, making TRUNCATE + INSERT atomic." This does **NOT** hold, because of the
premature commit at database.py:324-325:

1. **Session + two `db.execute`/`insert_batch` ops (no explicit `transaction()`):** each
   cursor exit commits the session conn when INTRANS. TRUNCATE commits independently; a failed
   INSERT leaves the target EMPTY. Empirically reproduced:
   `Pattern A rows after failure (atomic would be [1], broken shows []): []`. **NON-ATOMIC.**
2. **Session + `db.transaction()` wrapping `insert_batch`/`upsert_many`:** the inner
   `self.cursor()` calls `self._session_conn.commit()`, which inside the active
   `transaction()` block raises:
   `ProgrammingError: Explicit commit() forbidden within a Transaction context.` **CRASHES.**

**The seam the planner must wire:** open `db.session()` internally (Claude's-Discretion
recommendation), then run the load inside `with db.transaction() as conn:` and execute the load
SQL **directly on the yielded `conn`** (via `with conn.cursor() as cur: cur.execute(sql, params)`),
NOT via `db.insert_batch`/`db.upsert_many`. This is exactly the working pattern already proven in
`tests/test_etl_accessor.py:344-348`. Empirically verified atomic: a forced rollback after
TRUNCATE preserves the original rows (`rows after forced rollback: [(1,)]`).

**Consequence for D-04:** "reuse `insert_batch`/`upsert_many`" must be read as "reuse their *SQL
construction + identifier-validation logic*", not "call the public methods". Practical options
for the planner (any satisfies SC-6 as long as `validate_identifiers` runs before interpolation):
- (a) **Recommended:** add small private helpers in `etl.py` that build `(sql, params)` for
  insert and upsert (mirroring `_build_batch_insert_sql`'s logic, calling `validate_identifiers`),
  and execute them on the txn conn. This keeps the spatial.py "pure builder" instinct and is
  fully unit-testable. NOTE: this is *not* the rejected speculative `build_upsert_sql` of D-04a —
  it is the minimal builder needed because the public methods are unusable inside a txn block.
- (b) Refactor `Database.cursor()`/`insert_batch` to be transaction-aware (do not commit if
  already inside a `transaction()`). Larger blast radius; out of phase scope — avoid.

Recommend (a). `build_truncate_sql` is already a pure builder; mirroring it for insert/upsert is
consistent and the only way to honor both SC-3 and D-01 with the current `Database` API.

### Q2 — D-07 NaN/tz behavior. Verified + recommendation.

**Verified:** there is **NO** NaN/NaT handling and **NO** tz coercion anywhere in `pycopg/*.py`
(grep for `isna|isnull|notna|NaN|NaT|fillna|to_dict|orient` returned nothing). The existing
`from_dataframe` path delegates entirely to `df.to_sql(con=self.engine, ...)` (database.py:1417-1424);
SQLAlchemy/pandas handles NaN→NULL for `to_sql` internally, but the **psycopg-native** path
(`insert_batch`, line 661: `params.extend(row.get(col) for col in columns)`) passes values through
raw — a NaN cell becomes a float NaN literal, NOT NULL.

**Recommendation (consistent + correct):**
- **Coerce `NaN`/`NaT` → `None` before building rows.** The robust mechanism:
  `df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")` — `where(notnull, None)`
  replaces all NaN/NaT with None across mixed dtypes; `.astype(object)` first prevents pandas from
  re-coercing None back to NaN in numeric columns. This yields `list[dict]` in exactly the shape
  `insert_batch`/`upsert_many` consume (verified: line 642 `columns = list(rows[0].keys())`,
  line 661 `row.get(col)`).
- **Do NOT silently coerce tz.** Document tz-localization as the user's responsibility, matching
  the existing (zero-coercion) `from_dataframe` behavior. State this in the `run()`/load docstring.
- **`rows_loaded`** = sum of `cur.rowcount` from the executed INSERT(s) (D-07). For a multi-batch
  insert, sum across batches as `insert_batch` already does (database.py:649,667).

**DataFrame→list[dict] conversion call (Claude's discretion, resolved):** use
`df.astype(object).where(pd.notnull(df), None).to_dict(orient="records")`. `to_dict(orient="records")`
is correct because it produces `list[dict]` keyed by column name — the exact input contract of
`insert_batch`/`upsert_many`. `itertuples`/`to_records` produce tuples/structured arrays and would
require column remapping. (One caveat to note in the plan: `pd.notnull` on a DataFrame containing
list/array cells can misbehave; v0.5.0 scope is scalar columns — acceptable, document the limit.)

### Q3 — D-03 target existence + create.

**Catalog query — recommendation:** use **`SELECT to_regclass(%s)`** with the schema-qualified
name (`f"{schema}.{target}"` after `validate_identifiers(target, schema)`), checking the result
is non-NULL. Rationale: `to_regclass` resolves through `search_path` and returns NULL (not an
error) for a missing relation — a single clean round-trip. The existing `db.table_exists`
(database.py:1011-1026) uses `information_schema.tables` filtered by `table_schema`/`table_name`
and works equally well; either satisfies D-03. Prefer `table_exists` for reuse (already validated
path, no new SQL), unless the planner wants the one-liner — both are HIGH confidence.

**replace create path:** `from_dataframe(zero_row_frame, target, schema, if_exists='replace')`
produces a usable empty table with column types from pandas' dtype→SQL mapping (database.py:1417,
`df.to_sql(...)`; `to_sql` with `if_exists='replace'` issues a CREATE on the engine). A zero-row
frame still carries dtypes, so columns are typed. This is non-atomic and on the SQLAlchemy engine
(separate conn) — acceptable per D-03 because it only fires on first run when the table is absent
(nothing to lose), then the steady-state TRUNCATE + INSERT inside the txn is atomic. **Caveat for
the plan:** call the create BEFORE opening `db.transaction()` (it commits on the engine; mixing it
into the txn would not roll back anyway and would muddy the seam).

**upsert missing target:** raise `ETLTargetNotFoundError` (symmetry with append). Confirmed
sound: upsert needs a pre-existing unique index for `ON CONFLICT` (Pitfall 5); auto-creating a
zero-row frame would NOT create that unique constraint, so the very next ON CONFLICT would error.
Raising is the honest, correct behavior.

### Q4 — D-06 `ETLTransformError` construction.

**VERIFIED — exceptions.py:60-69:** `ETLTransformError(ETLError)` and
`ETLTargetNotFoundError(ETLError)` are **bare `pass` classes with NO custom constructor.** They
inherit `Exception.__init__`, so they take a single message string. (CONTEXT.md asks "verify the
constructor signature" — answer: there is no custom signature; it's `Exception(msg)`.)

**Recommendation:** construct with a formatted message and chain:
```python
def _step_label(fn):
    return getattr(fn, "__name__", None) or repr(fn)   # lambdas/partial → repr fallback

# in the chain loop (index base = 1, more readable; state in docstring):
try:
    df = step(df)
except Exception as exc:
    raise ETLTransformError(
        f"transform step {i} ('{_step_label(step)}') raised "
        f"{type(exc).__name__}: {exc}"
    ) from exc
```
- `__name__` → `repr()` fallback handles lambdas (`<lambda>` actually has `__name__='<lambda>'`,
  so optionally detect that and prefer `repr`) and `functools.partial` (no `__name__` → repr).
- `raise ... from exc` preserves `__cause__`; `traceback.format_exc()` in the `run()` except
  block then captures the full chained traceback into `error_traceback` (ETL-08).
- The failed run is recorded via `_end_run(run_id, 'failed', rows_extracted, 0, error_message=str(exc_or_etlerror), error_traceback=traceback.format_exc())` (etl.py:368-423, VERIFIED signature).
- **Index base:** recommend **1-based** ("step 1", "step 2") as more human-readable; state in the
  docstring (Claude's discretion per D-06).

### Q5 — run() wiring.

**VERIFIED — etl.py:425-448:** the `run()` stub currently does `self.init(); run_id =
self._start_run(name); self._end_run(run_id, "success", 0, 0); return run_id` and returns `int`.
- `_start_run(name) -> int` returns `run_id` from `RETURNING run_id` (etl.py:340-366, VERIFIED).
- `_end_run(run_id, status, rows_extracted, rows_loaded, error_message=None, error_traceback=None)`
  is the recording path; `status='failed'` is the failed-run path (etl.py:368-423, VERIFIED). The
  CHECK constraint accepts only `'running'/'success'/'failed'` (queries.py:255). Use literal
  `'failed'`.
- Run-log writes stay on the dedicated autocommit conn: `init`/`_start_run`/`_end_run` all use
  `with self._db.connect(autocommit=True) as conn:` (etl.py:336,360,410, VERIFIED) — independent
  of the load txn. ETL-09 does not regress as long as Phase 18 does NOT route run-log writes
  through the session/txn. Keep them exactly as-is.

**run() return value (Claude's discretion, resolved):** return the **bare `run_id` (int)** in
Phase 18, preserving the current stub's return type. Phase 19 upgrades to `RunResult`. Do NOT
pre-build `RunResult`. (Rationale: the existing integration test `test_run_writes_full_row` asserts
`run_id = db.etl.run("demo")` is usable as an int key — keeping the int return avoids churning the
Phase 17 tests.)

**`run()` signature note:** the stub is `run(self, name: str = "pipeline")`. Phase 18 must change
the signature to accept a `Pipeline` (the requirement is `db.etl.run(pipeline)`). Recommend
`run(self, pipeline: Pipeline) -> int`, deriving `name = pipeline.name`. **This is a
signature/contract change the planner must flag**: the Phase 17 tests call `db.etl.run("auto")`,
`db.etl.run("demo")` with a *string*. Those three tests (`test_first_run_auto_creates`,
`test_run_writes_full_row`, and the auto-create assertion) **will break** and must be migrated to
pass a `Pipeline(...)` in Phase 18. Confirmed by reading tests/test_etl_accessor.py:210,222.

### `extract_limit` injection (Claude's discretion, resolved)

`to_dataframe(sql=...)` calls `pd.read_sql(text(sql), self.engine, params=params)` with `params`
as a **dict** (database.py:1465). It does NOT support a positional `LIMIT %s`. Recommendation:
- **table source:** build `SELECT * FROM {schema}.{table} LIMIT {n}` — but since `to_dataframe`
  builds its own `SELECT * FROM {schema}.{table}` (database.py:1463) with no limit hook, the
  cleanest path is to pass a SQL string instead: construct
  `sql = f"SELECT * FROM {schema}.{table} LIMIT :lim"` after `validate_identifiers(table, schema)`,
  call `to_dataframe(sql=sql, params={"lim": n})`. (SQLAlchemy `text()` uses `:name` bind params,
  NOT `%s` — verified by the `text(sql)` wrapper at line 1465.)
- **SQL source:** wrap as a subquery: `SELECT * FROM ({source}) AS _etl_sub LIMIT :lim` with
  `params={"lim": n}`. The limit value is bound, never interpolated.
- `extract_limit` is already validated as a positive int at construction (etl.py:186-197), so the
  value is safe; still pass it as a bind param, not an f-string, for hygiene.
- `rows_extracted = len(df)` after extract, before transform (Claude's discretion, confirmed
  reasonable).

## Runtime State Inventory

Not applicable — Phase 18 is a greenfield feature implementation (new `run()` body), not a
rename/refactor/migration. No stored data, live service config, OS-registered state, secrets, or
build artifacts carry phase-affected names. **None — verified by inspection of phase scope.**

## State of the Art

| Old (CONTEXT.md sketch) | Current (verified) | Why |
|-------------------------|--------------------|-----|
| "session makes insert_batch/upsert_many share one atomic txn" (D-02/D-04) | session + `db.transaction()` on the *yielded conn* is atomic; the public methods crash/break inside it | `Database.cursor()` premature commit + psycopg `commit() forbidden in Transaction` |
| ARCHITECTURE.md `build_upsert_sql()` / `LoadSpec` | superseded; reuse builder *logic* on txn conn | D-04 + Q1 correction |

**Deprecated/outdated:** ARCHITECTURE.md's `build_upsert_sql()`/`LoadSpec` sketches (already
flagged superseded in CONTEXT.md canonical_refs). Use the flow, not the literal code.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `from_dataframe(zero_row, if_exists='replace')` creates a typed empty table with usable column types | Q3 | LOW — pandas/SQLAlchemy `to_sql` is well-established; verify in a DB test (covered in Validation Architecture). |
| A2 | `df.astype(object).where(pd.notnull(df), None).to_dict('records')` correctly NaN→None for scalar columns | Q2 | LOW — standard pandas idiom; verify with a NaN-bearing DataFrame DB test. List/array cells out of scope (documented). |
| A3 | 1-based step index is preferred for readability | Q4 | NONE — cosmetic, Claude's discretion. |

All other claims in this research are `[VERIFIED]` against live source or empirical psycopg probes.

## Open Questions (RESOLVED)

1. **Builder placement for insert/upsert SQL (Q1 option a). — RESOLVED: pure builders in `etl.py` (option a).**
   - What we know: the public `insert_batch`/`upsert_many` cannot be used inside the txn block.
   - Resolution: add private `_build_insert_sql`/`_build_upsert_sql` helpers in `etl.py`
     (mirroring `build_truncate_sql`, each calling `validate_identifiers`) — most consistent
     with spatial.py and fully unit-testable. Adopted by 18-01-PLAN.md and PATTERNS.md; not in
     `database.py`, not via extracting `_build_batch_insert_sql`.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL (pycopg_test) | All DB integration tests | ✓ | 5432/pycopg_test | — |
| psycopg | Native load writes | ✓ | 3.3.4 | — |
| pandas | Extract + zero-row create | ✓ | installed | — |
| SQLAlchemy engine | `to_dataframe`/`from_dataframe` | ✓ | installed | — |

No missing dependencies. (Note from MEMORY: 3 full-suite DB tests are pre-existing flaky in the
local env — use `uv run pytest -o addopts="" <targeted>` for focused runs; not a Phase 18 concern.)

## Validation Architecture

> nyquist_validation: key absent in `.planning/config.json` → treated as ENABLED. Coverage gate
> stays at **94** this phase (no ratchet) — confirmed `pyproject.toml:90 --cov-fail-under=94`.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (+ pytest-cov) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, addopts at line 90) |
| Quick run command | `uv run pytest tests/test_etl.py tests/test_etl_accessor.py -x -q -o addopts=""` |
| Full suite command | `uv run pytest` |
| DB fixture | `db` (from `db_config`) → real `pycopg_test`; pattern in tests/test_etl_accessor.py:18-32 |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ETL-02 | extract SQL source → DataFrame | integration | `pytest tests/test_etl_accessor.py -k extract_sql -x` | ❌ Wave 0 |
| ETL-02 | extract table source + `extract_limit` LIMIT | integration | `pytest tests/test_etl_accessor.py -k extract_table_limit -x` | ❌ Wave 0 |
| ETL-03 | transform applied; single callable | integration | `pytest tests/test_etl_accessor.py -k transform_single -x` | ❌ Wave 0 |
| ETL-03 | transform raises → `ETLTransformError` + failed run row | integration | `pytest tests/test_etl_accessor.py -k transform_error_failed_run -x` | ❌ Wave 0 |
| ETL-16 | transform list applied in sequence; error reports which step | integration/unit | `pytest tests/test_etl.py -k transform_chain_step_index -x` | ❌ Wave 0 |
| ETL-04 | append re-run doubles row count | integration | `pytest tests/test_etl_accessor.py -k append_double_count -x` | ❌ Wave 0 |
| ETL-04 | append missing target → `ETLTargetNotFoundError` | integration | `pytest tests/test_etl_accessor.py -k append_missing_target -x` | ❌ Wave 0 |
| ETL-05 | replace re-run = latest only | integration | `pytest tests/test_etl_accessor.py -k replace_latest_only -x` | ❌ Wave 0 |
| ETL-05 | **replace mid-load error leaves ORIGINAL rows intact (atomic)** | integration | `pytest tests/test_etl_accessor.py -k replace_atomic_rollback -x` | ❌ Wave 0 |
| ETL-05 | replace auto-creates missing target (zero-row frame) | integration | `pytest tests/test_etl_accessor.py -k replace_creates_missing -x` | ❌ Wave 0 |
| ETL-06 | upsert re-run updates existing + inserts new, no duplicates | integration | `pytest tests/test_etl_accessor.py -k upsert_no_duplicates -x` | ❌ Wave 0 |
| ETL-06 | upsert missing target → `ETLTargetNotFoundError` | integration | `pytest tests/test_etl_accessor.py -k upsert_missing_target -x` | ❌ Wave 0 |
| ETL-09 (regress guard) | failed load rolls back, run-log row still committed | integration | reuse `test_failed_run_commits_despite_load_rollback` + new `run()`-level variant | ✅ exists (adapt) |
| ETL-16/SC-6 | injection via `target` / `conflict_columns` rejected | unit (mocked) | `pytest tests/test_sql_injection.py -k etl -x` | ❌ Wave 0 |
| D-07 | NaN/NaT cell → SQL NULL (not float-NaN) | integration | `pytest tests/test_etl_accessor.py -k nan_to_null -x` | ❌ Wave 0 |

### Critical atomicity test (the one that catches the Q1 landmine)
`replace_atomic_rollback` MUST: seed target with baseline rows → run a replace pipeline whose
transform/load fails mid-INSERT (e.g. a row violating a constraint, or a forced error after
TRUNCATE) → assert the target STILL contains the baseline rows (NOT empty). With the broken
Pattern A this test fails (target empty `[]`); with the correct seam it passes (`[1]` preserved).
This is the single highest-value test of the phase.

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_etl.py tests/test_etl_accessor.py tests/test_sql_injection.py -x -q -o addopts=""`
- **Per wave merge:** `uv run pytest -o addopts=""` (targeted full, skip flaky via -k as needed)
- **Phase gate:** `uv run pytest` green (incl. `--cov-fail-under=94`) before `/gsd-verify-work`;
  `uv run ruff check pycopg tests`; `uv run black --check pycopg tests`.

### Wave 0 Gaps
- [ ] Extend `_FakeDatabase` in `tests/test_etl_accessor.py` to support `cursor()`, `session()`,
      `transaction()`, and `table_exists()` for unit-level `run()` tests (current fake only
      implements `connect()` — verified lines 40-87). Or test `run()` exclusively against real PG.
- [ ] New integration test cases per the map above (all `❌ Wave 0`).
- [ ] ETL injection cases in `tests/test_sql_injection.py` (malicious `target`/`conflict_columns`
      via `db.etl.run(Pipeline(...))`) — follow `EVIL_IDENTIFIERS` parametrize pattern (lines 19-25).
- [ ] Migrate Phase 17 tests that call `db.etl.run("string")` to `db.etl.run(Pipeline(...))`
      (test_first_run_auto_creates:210, test_run_writes_full_row:222) — see Q5 signature change.
- [ ] NaN→NULL and (documented) tz-naive behavior tests (D-07).

## Security Domain

> `security_enforcement` key absent in config → treated as enabled. ETL adds new SQL-emitting
> paths, so the input-validation category applies directly.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V5 Input Validation | yes | `validate_identifiers`/`validate_identifier` (utils.py:47,76) on every table/schema/conflict/update/column identifier before interpolation (SC-6). |
| V6 Cryptography | no | No crypto in ETL load path. |
| V2/V3/V4 Auth/Session/Access | no | Library-level; DB auth handled by connection config, unchanged. |

### Known Threat Patterns for pycopg ETL
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via `target`/`schema`/`conflict_columns`/columns | Tampering | `validate_identifiers` before any f-string; all user *values* via `%s`/bind params (never interpolated). Verified: `insert_batch` (db.py:640,643-644), `upsert_many` (db.py:543-544), `build_truncate_sql` (etl.py:255). New inline builders MUST replicate this. |
| Injection via `extract_limit` | Tampering | Bind as param (`:lim`), already validated positive int at construction (etl.py:186-197). |
| Injection via SQL `source` string | Tampering | `source` is user-authored SQL by design (same-DB, trusted author per scope); wrapped as subquery for LIMIT — document that `source` is the user's own SQL, not third-party input. |

## Sources

### Primary (HIGH confidence)
- `pycopg/etl.py` (read in full) — Pipeline, `_is_sql_source`, `build_truncate_sql`, ETLAccessor,
  `run()` stub at 425-448.
- `pycopg/database.py:295-357,471-551,601-669,1011-1026,1388-1465` — cursor/transaction/session,
  insert_many/upsert_many/insert_batch, table_exists, from_dataframe/to_dataframe.
- `pycopg/exceptions.py:54-69` — ETLError/ETLTransformError/ETLTargetNotFoundError (bare classes).
- `pycopg/utils.py:47-91` — validate_identifier/validate_identifiers.
- `pycopg/queries.py:36-39,249-287` — TABLE_EXISTS, ETL_INIT/INSERT/UPDATE_RUN.
- `tests/test_etl_accessor.py` (read in full) — fixtures, `_FakeDatabase`, the working atomic
  pattern (344-348), Phase 17 string-arg `run()` calls (210,222).
- `tests/test_sql_injection.py:1-70` + `tests/conftest.py:14-40` — injection test pattern, db_config.
- **Empirical psycopg 3.3.4 probes** (this session): (1) `commit()` inside `transaction()` raises
  `ProgrammingError`; (2) Pattern A session-only leaves target `[]` after mid-load failure;
  (3) Pattern B (direct on yielded conn) preserves `[1]` after forced rollback.

### Secondary (MEDIUM confidence)
- `.planning/research/PITFALLS.md` (Pitfalls 2,3,6,7), `.planning/research/ARCHITECTURE.md`,
  `.planning/research/STACK.md` — corroborate atomicity/NaN/identifier concerns.

### Tertiary (LOW confidence)
- None — all critical claims verified against live source or empirical probe.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new deps; all primitives verified in source.
- Architecture (atomicity seam): HIGH — empirically verified, including the D-02/D-04 correction.
- Pitfalls: HIGH — the two critical traps reproduced empirically.
- NaN/tz (D-07): MEDIUM-HIGH — recommendation is a standard idiom; needs DB test confirmation (A2).

**Research date:** 2026-06-15
**Valid until:** 2026-07-15 (stable internal codebase; re-verify if database.py cursor/session/
transaction or insert_batch/upsert_many change).

## Drift Report (CONTEXT.md cited lines vs live source)

| CONTEXT.md citation | Live source | Status |
|---------------------|-------------|--------|
| cursor `database.py:305-337` | 305-336 | ✓ accurate (off by 1 trailing) |
| transaction `database.py:339-357` | 338-357 | ✓ accurate |
| session `database.py:359-411` | 359-411 | ✓ exact |
| to_dataframe `database.py:1429-1465` | 1429-1465 | ✓ exact |
| from_dataframe `database.py:1388-1424` | 1388-1424 | ✓ exact; confirmed `df.to_sql(con=self.engine)` (line 1417) — the D-01 rationale |
| insert_batch `database.py:601-669` | 601-669 | ✓ exact; uses `self.cursor()` (650), returns rowcount sum (667) |
| upsert_many→insert_many `database.py:508-551` | 508-551 / insert_many 471-506 | ✓ exact; both via `self.cursor()`; `validate_identifiers` ×2 (543-544) |
| run() stub `etl.py:425-448` | 425-448 | ✓ exact; returns int run_id |
| add_primary_key `database.py:1152` | 1152 | ✓ accurate |

**Decisions the live code contradicts:** D-02/D-04's literal "use insert_batch/upsert_many inside
one db.transaction() / session for atomicity" — see Q1. The *intent* (atomic TRUNCATE+INSERT on one
connection) is achievable and correct; the *mechanism* must execute load SQL on the yielded txn
conn directly, not via the public methods. No other contradictions found.
