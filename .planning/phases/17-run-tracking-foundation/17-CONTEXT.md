# Phase 17: Run-Tracking Foundation - Context

**Gathered:** 2026-06-15
**Status:** Ready for planning

<domain>
## Phase Boundary

The **run-tracking I/O foundation** of the v0.5.0 ETL layer. Phase 16 shipped the
pure, DB-free layer (`Pipeline` dataclass, the 5 ETL SQL constants, `build_init_sql()`/
`build_truncate_sql()`, exception hierarchy). Phase 17 delivers the **actual database
writes** for run tracking and the **accessor that hosts them** — so every subsequent
load phase inherits correct transaction-boundary behavior.

**In scope (Phase 17):**
- A **sync `ETLAccessor` class** (in `etl.py`) holding `init()` and the internal
  `_start_run` / `_end_run` run-log writes.
- A **lazy `db.etl` property** on `Database`, mirroring `db.spatial` exactly.
- `db.etl.init()` — idempotent `CREATE TABLE IF NOT EXISTS pipeline_runs` (D-15 DDL).
- The **separate-connection run-log write pattern**: run-log writes use a dedicated
  autocommit connection, never the load transaction, so the failure record always commits.
- Failed-run recording semantics: a run that fails during load records `status='failed'`
  with non-null `error_message` + `error_traceback`, committed independently of the
  (rolled-back) load transaction.
- Auto-create on first `run()` (the `CREATE TABLE IF NOT EXISTS` call site) — even though
  the full `run()` body lands in Phases 18/19, the auto-create hook is established here.

**Out of scope (later phases):**
- Extract, the three load modes, transform execution (Phase 18 — ETL-02..06, ETL-16).
- The full `run()` / `RunResult` / `history()` / `last_run()` / `dry_run` surface (Phase 19 —
  ETL-10/11/15/17). Phase 17 builds the run-log primitives those will call.
- `AsyncETLAccessor`, `async_db.etl` wiring, `TestEtlParity`, Sphinx docs, release
  (Phase 20 — ETL-12). **Note:** this phase narrows Phase 20's "lazy `db.etl` wiring" to
  **async-only** wiring (see D-01).

Mirrors `spatial.py` / `db.spatial` exactly: pure shared builders (Phase 16) + a thin
accessor doing the I/O (this phase).

**Requirements covered:** ETL-07, ETL-08, ETL-09, ETL-14.
</domain>

<decisions>
## Implementation Decisions

### Accessor skeleton timing
- **D-01:** **Create the sync `ETLAccessor` class AND wire the lazy `db.etl` property
  on `Database` in Phase 17** (not deferred to Phase 20). The roadmap's Phase 20 "lazy
  `db.etl` wiring" is hereby **narrowed to async-only** (`AsyncETLAccessor` + `async_db.etl`).
  Rationale: Phase 17 success criteria #2/#3 name `db.etl.init()` and "first `run()`
  auto-creates" — those are only literally testable if `db.etl` exists now. The sync
  accessor is the natural home for `init`/`_start_run`/`_end_run`.
- **D-02:** The `db.etl` property mirrors `db.spatial` **exactly** (lazy `self._etl: ETLAccessor | None`
  field, `from pycopg.etl import ETLAccessor` inside the property, store + return).
  See `database.py` lines ~228–249 for the template. `ETLAccessor.__init__(self, db)` stores
  `self._db = db` — same shape as `SpatialAccessor`.
- **D-03:** In Phase 17 the `ETLAccessor` exposes **`init()` publicly** and `_start_run` /
  `_end_run` as internal helpers. A public `run()` may exist as a thin stub if the planner
  needs the auto-create call site testable now, but its full body (extract/transform/load)
  is Phase 18/19 — do **not** implement extract/load logic in this phase.

### Dedicated-connection lifecycle (the core of this phase)
- **D-04:** Run-log writes use a **fresh, short-lived autocommit connection per write**
  via the existing `db.connect(autocommit=True)` path (which wraps `_connect_with_retry`,
  tenacity-backed). `_start_run` opens one connection (INSERT … RETURNING run_id, then
  closes); `_end_run` opens another (UPDATE … then closes). ~2 short connections per run —
  negligible for metadata, no held state on the accessor. Matches the lib's open-per-operation
  idiom and how admin/autocommit work is already done.
- **D-05:** **Never** use the load transaction (or a pooled connection shared with the load)
  for run-log writes. This is the locked separation (ETL-08/09): the `pipeline_runs` failure
  record must commit even when the load transaction rolls back. `_start_run`/`_end_run` are
  fully independent of `db.transaction()`.
- **D-06 (run-log write failure):** If a run-log write **itself** fails, let the exception
  **propagate**. `_connect_with_retry` already retries transient `OperationalError`s first;
  if it still fails, it surfaces. A `pipeline_runs` row left in `status='running'` (when the
  load committed but `_end_run` could not) is an **honest** signal of a DB problem — documented
  as a known edge, **not** silently swallowed. No try/except-and-warn wrapper in v0.5.0.

### Status CHECK constraint & dry_run
- **D-07:** The `pipeline_runs` CHECK stays **3-valued**: `status IN ('running','success','failed')`,
  exactly as authored in Phase 16's `ETL_INIT_PIPELINE_RUNS`. **`dry_run` is never persisted**
  to `pipeline_runs` (ETL-15: a dry run writes no row). The `RunResult(status='dry_run')` of
  Phase 19 exists only in memory and never hits the CHECK. The Phase 16 DDL is **final** —
  no later migration needed. (Note: ROADMAP Phase 17 SC-1's status list does not include
  `dry_run`; this confirms consistency.)

### Tracking-table schema qualification
- **D-08:** `pipeline_runs` stays **unqualified** in the DDL and all run-log SQL — it resolves
  via the connection's `search_path` (typically `public`). **No configurable schema** for the
  tracking table in v0.5.0; `ETLAccessor(db)` takes **no `schema` argument**. This keeps the
  `init`/`_start_run`/`_end_run` SQL as **pure `%s`-only constants** with no identifier
  interpolation (preserves the Phase 16 contract and adds no injection surface).
  - The research `ETLAccessor(db, schema='etl')` idea is an explicit **Future Enhancement**, not
    v0.5.0 scope (see `.planning/research/SUMMARY.md` Future Enhancements).
  - `Pipeline.schema` is **unrelated** to the tracking table — it controls the **source/target**
    tables (wired in Phase 18). Don't conflate the two.

### Carried forward from Phase 16 (locked — do not re-litigate)
- **D-09:** `pipeline_runs` DDL is **final as shipped** in `ETL_INIT_PIPELINE_RUNS` /
  `build_init_sql()`: `BIGSERIAL` PK `run_id`, `pipeline_name TEXT`, `started_at TIMESTAMPTZ DEFAULT now()`,
  `finished_at TIMESTAMPTZ`, `status TEXT + CHECK`, `rows_extracted`/`rows_loaded BIGINT`,
  `error_message`/`error_traceback TEXT`, nullable `watermark JSONB` (always NULL in v0.5.0,
  forward-compat for v0.6.0 — OD-1/D-14). `CREATE TABLE IF NOT EXISTS` → idempotent (D-15).
- **D-10:** Both init strategies (OD-3/D-15): explicit `db.etl.init()` **and** lazy auto-create
  on first `run()` — the same idempotent DDL backs both. Phase 17 establishes both call sites
  (the auto-create hook may sit in a `run()` stub per D-03).
- **D-11:** Failure exception strategy (OD-2/D-09 of Phase 16): for known cases raise the domain
  exceptions (`ETLTransformError`, `ETLTargetNotFoundError` — defined in Phase 16, raised in
  Phase 18); for unknown errors **re-raise the original** (no `PipelineError` wrapper). Phase 17
  only records the failed run + re-raises; it does not introduce new exception types.
- **D-12:** SQL constants stay `%s`-only, no f-string identifier interpolation; any builder that
  touches an identifier calls `validate_identifiers(...)` first (v0.3.1 security invariant; mirrors
  `spatial.py`). Run-log writes touch no user identifiers, so they interpolate nothing.

### Claude's Discretion
- Exact internal signatures of `_start_run(name) -> int` and `_end_run(run_id, status, rows_extracted,
  rows_loaded, error_message=None, error_traceback=None)` — the column set is locked (D-09), the
  parameter packing is the planner's call.
- Whether `init()` is literally `self._db.execute(ETL_INIT_PIPELINE_RUNS, autocommit=True)` or goes
  through `build_init_sql()` — both exist; pick the one consistent with how `_start_run`/`_end_run`
  consume `ETL_INSERT_RUN`/`ETL_UPDATE_RUN`.
- Whether a thin `run()` stub lands now (to make the auto-create + start/end-run path testable) or
  whether Phase 17 ships `init` + `_start_run`/`_end_run` with direct unit/integration tests and
  leaves `run()` entirely to Phase 18/19. Either satisfies the SC; planner decides what gives the
  cleanest testable seam for SC #1 and #4.
- How to capture `error_traceback` (e.g. `traceback.format_exc()`) — stdlib, planner's choice.
- Whether `Pipeline` gets exported in `__init__.py` now (it currently is **not** — only the ETL
  exceptions are; Phase 20 was to wire exports). Since `db.etl` lands now, the planner may pull the
  `Pipeline` export forward if a test needs it; not required by these decisions.

### Folded Todos
None — no pending todos matched this phase (STATE.md "Pending Todos: None").

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope (authoritative)
- `.planning/ROADMAP.md` §"Phase 17: Run-Tracking Foundation" — Goal + 4 success criteria
  (the `pipeline_runs` row contract, idempotent `db.etl.init()`, first-`run()` auto-create, the
  failed-run-committed-on-separate-autocommit-connection behavior).
- `.planning/REQUIREMENTS.md` — **ETL-07** (run row contract + reserved watermark), **ETL-08**
  (failed run committed independently), **ETL-09** (load txn separate from run-tracking txn),
  **ETL-14** (auto-create + explicit `init()`). Plus the "Open Design Decisions" table
  (OD-1/OD-2/OD-3) and "Out of Scope" table.
- `.planning/PROJECT.md` §"Current Milestone: v0.5.0" — milestone goal, locked constraints
  (zero new runtime deps, mirror `spatial.py`, watermark deferred additively).

### Prior phase context (decisions that flow into this phase)
- `.planning/phases/16-pure-etl-layer/16-CONTEXT.md` — D-01..D-15 of Phase 16; the `pipeline_runs`
  DDL constraints (D-14), both-init strategy (D-15), failure strategy (D-09), security invariants
  (D-12/D-13). **This phase consumes those; does not re-author them.**

### ETL research (HIGH confidence, read source directly)
- `.planning/research/ARCHITECTURE.md` §"Pattern 3: Separate Transaction for Run-Log Write"
  (lines ~178–201) + §"Data Flow / ETL Execution Flow (sync)" (lines ~207–232) — **the** reference
  for `_start_run`/`_end_run` on an independent connection. **NOTE:** the example uses `status="error"`;
  the locked value is **`'failed'`** (matches the CHECK constraint — D-07). Use the *pattern*, not the
  literal status string.
- `.planning/research/SUMMARY.md` lines ~120–130 — independent autocommit connections for run-log
  writes; the anti-pattern of run-log-in-same-transaction-as-load; Future Enhancement list
  (schema-configurable tracking table = NOT v0.5.0).
- `.planning/research/STACK.md` §6 "Run tracking — `pipeline_runs` table" — confirms `CREATE TABLE
  IF NOT EXISTS` is sufficient (no alembic), append-heavy run log.
- `.planning/research/PITFALLS.md` — Pitfall 6 (schema must be TEXT+CHECK + JSONB watermark, no ENUM)
  — already honored by the Phase 16 DDL.

### Codebase precedent (the template to mirror)
- `pycopg/spatial.py` §`class SpatialAccessor` (lines ~1023–1077) — accessor `__init__(self, db)` +
  `self._db` shape; `ETLAccessor` copies it.
- `pycopg/database.py` §`spatial` property (lines ~228–249) — the lazy-accessor wiring template for
  `db.etl`; §`_connect_with_retry` (lines ~258–260) + `connect()` (lines ~262–280) — the
  autocommit-connection path the run-log writes use (D-04).
- `pycopg/queries.py` §"ETL QUERIES" — `ETL_INIT_PIPELINE_RUNS`, `ETL_INSERT_RUN`, `ETL_UPDATE_RUN`
  (the constants `init`/`_start_run`/`_end_run` consume — already authored, do not re-author).
- `pycopg/etl.py` — `Pipeline` + `build_init_sql()`/`build_truncate_sql()` already present;
  `ETLAccessor` is the **new** class added to this module this phase.
- `pycopg/exceptions.py` — `ETLError`/`ETLTransformError`/`ETLTargetNotFoundError` (defined Phase 16;
  not raised in Phase 17 beyond re-raise semantics).
- `pycopg/__init__.py` — current ETL exports are the 3 exceptions only; `Pipeline` not yet exported.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `db.spatial` lazy property + `SpatialAccessor(db)` — the **exact** template for `db.etl` +
  `ETLAccessor(db)`. Copy the property body (lazy `None` field, in-property import, store, return).
- `db.connect(autocommit=True)` (context manager, wraps `_connect_with_retry` → tenacity) — the
  dedicated autocommit connection for run-log writes. No new connection plumbing needed.
- `ETL_INIT_PIPELINE_RUNS` / `ETL_INSERT_RUN` / `ETL_UPDATE_RUN` constants + `build_init_sql()` —
  authored in Phase 16; Phase 17 only *calls* them.

### Established Patterns
- Lazy accessor namespaces (`db.spatial`, `db.engine`) with a `self._x: X | None = None` field set
  in `Database.__init__`. Add `self._etl: ETLAccessor | None = None` the same way.
- Open-per-operation connections for autocommit/admin work (e.g. `create_database`,
  `pg_notify` use `autocommit=True`); run-log writes follow suit (D-04).
- `%s`-only SQL constants; `validate_identifiers` gate before any identifier interpolation.
  Run-log writes interpolate no identifiers, so they stay constant.

### Integration Points
- `pycopg/etl.py` gains `class ETLAccessor` (+ `init`, `_start_run`, `_end_run`, optional `run` stub).
- `pycopg/database.py` gains `self._etl` field in `__init__` + the `etl` lazy property.
- No `async_database.py` changes this phase (async accessor is Phase 20).
- No new `queries.py` constants (the 3 needed already exist from Phase 16).
- `pipeline_runs` table is created at runtime (init/auto-create) — no migration file.

</code_context>

<specifics>
## Specific Ideas

- User consistently chose the **lower-scope, mirror-existing-pattern** option across all four gray
  areas: create the sync accessor now (not module helpers), fresh connect-per-write (not a held
  connection), keep the 3-valued CHECK (no pre-emptive `dry_run`), and keep `pipeline_runs`
  unqualified (no configurable tracking schema). The throughline: **do exactly what `spatial.py`/
  `db.spatial` did, no speculative generality.**
- User explicitly wants a **left-`running` row to be visible**, not papered over, when a run-log
  write fails — honesty over forgiveness for metadata-write failures (D-06).
- This phase **redefines Phase 20's scope**: "lazy `db.etl` wiring" becomes **async-only** wiring,
  because the sync `db.etl` lands here. The planner/roadmapper for Phase 20 should expect the sync
  accessor + property to already exist.

</specifics>

<deferred>
## Deferred Ideas

- **Configurable tracking-table schema** (`ETLAccessor(db, schema='etl')`) — Future Enhancement per
  research SUMMARY; not v0.5.0. Revisit if multi-tenant isolation demand emerges.
- **Swallow-and-warn on run-log write failure** — considered and rejected for v0.5.0 (D-06); could
  revisit if real-world run-log flakiness proves noisy.
- (Carried, not this phase) Watermark/incremental extract using the reserved `watermark` column —
  v0.6.0 (ETL-INC-01).

### Reviewed Todos (not folded)
None — no pending todos existed to review.

</deferred>

---

*Phase: 17-run-tracking-foundation*
*Context gathered: 2026-06-15*
