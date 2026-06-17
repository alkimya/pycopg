# Phase 18: Load Modes & Extract - Context

**Gathered:** 2026-06-15
**Status:** Ready for planning

<domain>
## Phase Boundary

The **extract + load mechanics** of the v0.5.0 ETL layer. Phase 16 shipped the pure
DB-free layer (`Pipeline`, builders, exceptions); Phase 17 shipped the run-tracking I/O
foundation (`ETLAccessor` with `init`/`_start_run`/`_end_run` on dedicated autocommit
connections, lazy `db.etl`). Phase 18 fills in the **body of the work** that the Phase 17
`run()` stub left for later: extract a DataFrame from the source, run the transform chain,
and load the result into the target under all three load modes — with transactional safety
and `validate_identifiers` on every identifier.

**In scope (Phase 18):**
- **Extract** (ETL-02): `source="SELECT ..."` (SQL) and `source="table_name"` (table) both
  produce a DataFrame, delegating to `db.to_dataframe` (via the `_is_sql_source` heuristic
  already in `etl.py`). `extract_limit` (already a `Pipeline` field) appended as `LIMIT %s`.
- **Transform chain** (ETL-03, ETL-16): `transform=None` no-op; single `Callable`; list of
  callables applied in sequence; an exception raises `ETLTransformError` identifying the
  failing step and records a failed run.
- **Load — append** (ETL-04): insert into an existing target; missing target →
  `ETLTargetNotFoundError`; re-run doubles row count.
- **Load — replace** (ETL-05): truncate-load; mid-load error leaves original rows intact
  (atomic); missing target is created.
- **Load — upsert** (ETL-06): `INSERT … ON CONFLICT DO UPDATE` keyed on `conflict_columns`;
  re-run updates existing + inserts new, no duplicates.
- **Security** (ETL-16/SC-6): every load path routes table/conflict/column identifiers
  through `validate_identifiers` before any string interpolation.
- Wiring all of the above into the **real `run()` body** (replacing the Phase 17 stub),
  so `_start_run`/`_end_run` bracket the real extract→transform→load with correct
  `rows_extracted`/`rows_loaded`/`status` and failed-run recording.

**Out of scope (later phases):**
- `RunResult` object, `history()`, `last_run()`, `dry_run` (Phase 19 — ETL-10/11/15/17).
  Phase 18's `run()` may return a bare value (e.g. `run_id` or counts) that Phase 19
  upgrades to a `RunResult`; do not pre-build `RunResult` here.
- `AsyncETLAccessor`, `async_db.etl` wiring, `TestEtlParity`, Sphinx docs, release
  (Phase 20 — ETL-12/13).
- Advisory-lock concurrency guard, `extract_batch_size` streaming, COPY-based loads,
  GeoDataFrame routing — all deferred (see Deferred Ideas).

**Requirements covered:** ETL-02, ETL-03, ETL-04, ETL-05, ETL-06, ETL-16.
(Note: ETL-09 — load-txn-separate-from-run-log — is already complete from Phase 17; Phase 18
inherits and must not break it.)
</domain>

<decisions>
## Implementation Decisions

### Write primitive & replace-mode atomicity (the architectural crux)
- **D-01:** **All row writes go through psycopg-native primitives inside one
  `db.transaction()`** — never through `from_dataframe`/pandas `to_sql` for the row insert.
  Rationale: `from_dataframe` delegates to `df.to_sql(con=self.engine, …)` which runs on the
  **SQLAlchemy engine**, a different connection from psycopg's `db.transaction()`. TRUNCATE
  (psycopg) and a `to_sql` insert (SQLAlchemy) can never share one transaction, so a
  `to_sql`-based replace would leave the target **empty** on a mid-load failure — violating
  SC-3. Therefore:
    - **append** → `db.insert_batch(table, rows, schema)` inside the load transaction.
    - **replace** → `build_truncate_sql()` (TRUNCATE) **+** `db.insert_batch(...)`, both inside
      **one** `db.transaction()` so a failed mid-INSERT rolls the TRUNCATE back too (SC-3).
    - **upsert** → `db.upsert_many(table, rows, conflict_columns, schema)` (emits
      `INSERT … ON CONFLICT DO UPDATE`) inside the load transaction.
- **D-02 (atomicity mechanism — MUST verify in research/plan):** `insert_batch` and
  `upsert_many`→`insert_many` both acquire their cursor via **`self.cursor()`**, and
  `Database.cursor()` reuses `self._session_conn` **only when a session is active** (see
  `database.py:305–337`); otherwise each opens its own connection that **commits at cursor
  exit**. Likewise `db.transaction()` reuses the session conn when a session is active, else
  opens its own (`database.py:339–357`). **Consequence:** a bare `db.insert_batch()` does NOT
  join an outer `db.transaction()` — it commits independently. To make TRUNCATE + INSERT
  atomic on **one** connection, the load must run **inside a `db.session()`** (so
  `transaction()` and `cursor()` all share `self._session_conn`). The planner must confirm
  this is the seam and wire the load body accordingly. This is the same session-vs-fresh-conn
  subtlety that drove the Phase 17 run-log isolation gap closure (17-02) — get it right here,
  in the opposite direction: run-log writes must STAY isolated (dedicated autocommit conn,
  Phase 17), while the load writes must SHARE one transactional connection (this phase).

### Target existence & create semantics
- **D-03:** **Existence is checked via a catalog query** (e.g. `to_regclass` /
  `information_schema.tables`) before the load:
    - **append**, missing target → raise **`ETLTargetNotFoundError`** (SC-2). Do not create.
    - **replace**, missing target → **create the empty table once** via
      `from_dataframe(if_exists='replace')` on a **zero-row** frame (this borrows pandas'
      dtype→SQL column-type mapping for free), **then** run TRUNCATE + `insert_batch`
      atomically inside the load transaction (SC-3 "if the target does not exist it is
      created"). The create step is a separate, non-atomic statement, but it only fires on the
      **first run** when the table is absent (and an absent target has nothing to lose);
      steady-state re-runs are fully atomic.
    - **upsert**, missing target → out of the four SCs, not specified. Planner's call:
      reasonable to require the target (with its unique constraint) to pre-exist, since upsert
      needs an existing unique index for `ON CONFLICT` anyway (Pitfall 3). Lean toward raising
      `ETLTargetNotFoundError` for symmetry with append unless research shows a cleaner option.
- **D-03a (chosen over the alternative):** We explicitly did **not** hand-build a
  `CREATE TABLE IF NOT EXISTS` from DataFrame dtypes inside the transaction — that duplicates
  pandas/SQLAlchemy type-mapping and is an edge-case burden (tz, object columns). The
  zero-row `to_sql` create is the chosen mechanism (D-03).

### Load SQL builders
- **D-04:** **Reuse the existing validated methods; author no new load builders.** The only
  new builder is `build_truncate_sql()` — **already shipped in `etl.py`** (Phase 16). Mapping:
  append → `db.insert_batch` (calls `validate_identifiers(table, schema)` + per-column
  `validate_identifier`), upsert → `db.upsert_many` (calls `validate_identifiers(*conflict_columns)`
  and `validate_identifiers(*update_columns)`), replace → `build_truncate_sql` (validates) +
  `insert_batch`. SC-6 ("every load SQL builder calls `validate_identifiers` before
  interpolation") is satisfied because every path's SQL flows through an existing
  `validate_identifiers` call site. **The research sketch of a pure `build_upsert_sql()` in
  `etl.py` is superseded by `upsert_many`** — do not add it.
- **D-04a (consciously rejected):** Authoring fresh pure `build_upsert_sql()`/`build_append_sql()`
  in `etl.py` (max spatial.py consistency) was rejected because it duplicates SQL that
  `insert_batch`/`upsert_many` already generate and validate. The truncate builder is the sole
  exception (it has no existing method).

### Transform chain & error reporting
- **D-05:** Transform dispatch: `transform=None` → identity no-op; a single `Callable` →
  applied once; a `list[Callable]` → applied **in sequence**, each receiving the previous
  step's output DataFrame.
- **D-06:** On any transform exception, raise **`ETLTransformError`** whose message identifies
  the failing step by **both step index AND function name** — e.g.
  `transform step 2 ('normalize') raised ValueError: …`. Use the callable's `__name__`, falling
  back to `repr()` for lambdas/`functools.partial`. **Chain the original exception**
  (`raise ETLTransformError(...) from exc`) so the traceback is preserved and stored in
  `pipeline_runs.error_traceback` (ETL-08). The failed run is recorded via `_end_run(status='failed', …)`.
  (Index base — 0 vs 1 — is Claude's discretion; pick the most readable, state it in the docstring.)

### DataFrame → rows handoff (load input)
- **D-07 (contract locked; conversion mechanism = planner's call):** The load consumes the
  **post-transform DataFrame**, converts it to `list[dict]` for `insert_batch`/`upsert_many`,
  and reports **`rows_loaded` = the int returned by those methods** (`cur.rowcount` sum).
  The exact DataFrame→dict conversion and the NaN→NULL / timezone handling are **deferred to
  the researcher/planner**, who must first verify how the existing `from_dataframe`/pandas
  path currently handles NaN and tz-naive timestamps so the ETL load stays **consistent** with
  it. Research flags two known traps to resolve (do not ignore): pandas `NaN`/`NaT` reaching a
  column becomes a float-NaN literal rather than SQL `NULL` (Integration Gotchas), and tz-naive
  `datetime64` into `TIMESTAMPTZ` silently shifts. Likely resolution: coerce `NaN/NaT → None`
  before insert; **document** tz-localization as the user's responsibility (matching existing
  `from_dataframe` behavior) rather than silently coercing — but the planner confirms against
  the live code.

### Claude's Discretion
- Whether the load body opens its own `db.session()` internally or documents that callers
  manage it — but D-02's atomicity requirement (one shared connection for TRUNCATE+INSERT)
  must hold regardless. Recommend the accessor opens the session internally so `run()` is
  atomic without caller ceremony.
- Transform step index base (0 vs 1) in the `ETLTransformError` message (D-06).
- Exact `rows_extracted` source (likely `len(df)` after extract, before transform) and how
  `extract_limit` is appended (`LIMIT %s` param vs the existing `to_dataframe` surface).
- The exact catalog-existence query (`to_regclass(...)` vs `information_schema`) for D-03.
- Whether `run()` returns `run_id`, a counts tuple, or a dict in Phase 18 (Phase 19 upgrades
  it to `RunResult` — keep it minimal, don't pre-build `RunResult`).
- DataFrame→`list[dict]` conversion call (`to_dict(orient='records')` vs `itertuples` vs
  `to_records`) per D-07, after verifying NaN/tz behavior.
- Whether `Pipeline` (and any new symbols) get exported in `__init__.py` now or in Phase 20
  (currently only the 3 ETL exceptions are exported; pull forward only if a test needs it).

### Folded Todos
None — STATE.md "Pending Todos: None"; no todos matched this phase.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope (authoritative)
- `.planning/ROADMAP.md` §"Phase 18: Load Modes & Extract" — Goal + 6 success criteria
  (both extract types → `to_dataframe`; append double-count + `ETLTargetNotFoundError`;
  replace truncate-load atomicity + auto-create; upsert no-duplicates; transform chain +
  `ETLTransformError` step identification; `validate_identifiers` on every load builder).
- `.planning/REQUIREMENTS.md` — **ETL-02** (extract SQL/table), **ETL-03** (transform + failed
  run on error), **ETL-04** (append + target-must-exist), **ETL-05** (replace truncate-load
  atomic + create-if-absent), **ETL-06** (upsert by conflict key + construction-time guard),
  **ETL-16** (transform list + which-step-failed). Plus **ETL-09** (already complete, Phase 17 —
  load txn separate from run-log txn; must not regress) and the "Out of Scope" table (no
  SQL-only transforms, no DAG/scheduling, no new runtime deps).
- `.planning/PROJECT.md` §"Current Milestone: v0.5.0" — milestone goal, locked constraints
  (zero new runtime deps, mirror `spatial.py`, Python-callable transforms, same-DB only).

### Prior phase context (decisions that flow into this phase)
- `.planning/phases/17-run-tracking-foundation/17-CONTEXT.md` — D-01..D-12 of Phase 17. Phase 18
  **inherits** the run-log isolation contract (D-04/D-05: run-log writes on a dedicated
  autocommit connection, independent of the load txn) and must keep it intact while wiring the
  real `run()` body. **The opposite-direction subtlety matters here** (D-02 above).
- `.planning/phases/17-run-tracking-foundation/17-02-SUMMARY.md` — the session-path run-log
  isolation gap closure; the same session-vs-fresh-connection mechanic governs D-02's load
  atomicity (in the opposite direction — load SHARES one conn, run-log STAYS isolated).
- `.planning/phases/16-pure-etl-layer/16-CONTEXT.md` — `Pipeline` field semantics (source
  heuristic `_is_sql_source`, `conflict_columns` tuple normalization, `extract_limit` guard,
  `transform` field), `build_truncate_sql` contract, exception hierarchy. **Do not re-author.**

### ETL research (HIGH confidence — read source directly)
- `.planning/research/PITFALLS.md` — **the** load-mechanics reference for this phase:
  Pitfall 2 (truncate-then-fail → wrap TRUNCATE+INSERT in one transaction; COPY incompatible
  with outer txn without staging), Pitfall 3 (upsert conflict-key correctness, empty-update-set
  guard), Pitfall 6 (identifier injection in load builders — `validate_identifiers` day-one),
  Pitfall 7 (full-table materialization OOM → `extract_limit`), the "Integration Gotchas" table
  (psycopg `executemany` row-by-row; pandas NaN → float-NaN not NULL; tz-naive → `TIMESTAMPTZ`
  silent shift; `validate_identifier` vs DataFrame column names), and the "Looks Done But Isn't"
  checklist (truncate atomicity, upsert idempotency, identifier validation tests).
- `.planning/research/ARCHITECTURE.md` §"Data Flow / ETL Execution Flow (sync)"
  (lines ~207–232) — the extract→transform→load sequence and where the load transaction sits
  relative to the run-log writes. **NOTE:** the research sketches `build_upsert_sql()` and a
  `LoadSpec` dataclass — both **superseded**: load SQL reuses `upsert_many`/`insert_batch`
  (D-04), and there is no `LoadSpec` (the `Pipeline` dataclass shipped in Phase 16 carries
  `target`/`schema`/`load_mode`/`conflict_columns` directly). Use the *flow*, not the literal
  `LoadSpec`/`build_upsert_sql` code.
- `.planning/research/STACK.md` — psycopg/pandas load mechanics (`insert_batch` vs
  `copy_insert` thresholds; `to_dataframe`/`from_dataframe` engine path).

### Codebase precedent (the methods to compose)
- `pycopg/etl.py` — `Pipeline`, `_is_sql_source`, `build_truncate_sql`, and the `ETLAccessor`
  with `init`/`_start_run`/`_end_run` + the **`run()` stub** (lines ~425–448) that Phase 18
  replaces with the real extract→transform→load body.
- `pycopg/database.py` §`to_dataframe` (lines ~1429–1465) — extract delegate (table → validated
  `SELECT *`; sql → `pd.read_sql`); §`from_dataframe` (lines ~1388–1424) — **note it uses
  `self.engine`/`to_sql`, NOT psycopg** (the reason for D-01); §`insert_batch` (lines ~601–669)
  and §`upsert_many`→`insert_many` (lines ~508–551) — the psycopg-native load writers (both use
  `self.cursor()`); §`transaction` (lines ~339–357), §`session` (lines ~359–411), §`cursor`
  (lines ~305–337) — **the session-vs-fresh-connection mechanics that govern D-02**;
  §`add_primary_key` (line ~1152).
- `pycopg/utils.py` — `validate_identifiers` / `validate_identifier` (the mandated gate, D-04/SC-6).
- `pycopg/exceptions.py` — `ETLTransformError`, `ETLTargetNotFoundError` (defined Phase 16;
  **raised for the first time in Phase 18**).
- `pycopg/queries.py` §"ETL QUERIES" — `ETL_INSERT_RUN`/`ETL_UPDATE_RUN` (the run-log constants
  `run()` brackets the load with). No new ETL constants needed this phase.
- `tests/test_sql_injection.py` — **must gain** ETL cases (`db.etl.run` with a malicious
  `target`/`conflict_columns`) per Pitfall 6.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `db.to_dataframe(table=…)` / `db.to_dataframe(sql=…)` — the extract delegate (ETL-02). The
  `_is_sql_source` heuristic (already in `etl.py`) routes to one or the other.
- `db.insert_batch` / `db.upsert_many` — the validated psycopg-native row writers for
  append / upsert (D-04). Both already call `validate_identifiers`.
- `build_truncate_sql(table, schema)` — already shipped (Phase 16); the only load builder.
- `db.transaction()` + `db.session()` + `db.cursor()` — compose these so TRUNCATE+INSERT
  share one connection (D-02 atomicity).
- `from_dataframe(if_exists='replace')` on a zero-row frame — the create-missing-target
  mechanism for replace (D-03), borrowing pandas dtype→SQL mapping.

### Established Patterns
- Run-log writes use a dedicated autocommit connection, **independent** of the load txn
  (Phase 17 D-04/D-05). Phase 18 must keep this isolation while making the **load** writes
  share one transactional connection — the two are deliberately opposite (D-02).
- `validate_identifiers` before any identifier interpolation (v0.3.1 invariant; spatial.py /
  Phase 16 precedent). Every load path honors it via the reused methods (D-04).
- `%s`-only parameterization; user values never f-string interpolated.
- Open-per-operation connections (autocommit) for metadata; transactional session for the load.

### Integration Points
- `pycopg/etl.py` `ETLAccessor.run()` gains the real body: `_start_run` → extract → transform
  chain → mode-dispatched load (inside a session/transaction) → `_end_run(success|failed)`,
  re-raising originals (OD-2) and `ETLTransformError`/`ETLTargetNotFoundError` for known cases.
- No `async_database.py` changes (async is Phase 20).
- No new `queries.py` constants.
- `tests/test_sql_injection.py` gains ETL injection cases (Pitfall 6).
- Coverage: ETL load/extract paths are I/O-heavy — test against real `pycopg_test` PG, not
  mocks (Pitfall 12); measure before any ratchet change (gate stays 94 this phase).

</code_context>

<specifics>
## Specific Ideas

- The throughline of every choice this phase: **compose the existing, already-hardened pycopg
  primitives rather than write new load SQL** — `insert_batch`/`upsert_many` are the validated
  builders; only `build_truncate_sql` is bespoke (and it already exists). Same
  "mirror/reuse, no speculative generality" instinct the user carried through Phase 17.
- The user immediately accepted that **`to_sql` cannot be used for the row insert** — atomicity
  (SC-3) is non-negotiable and dictates psycopg-native writes in one transaction (D-01). This
  is the single most consequential decision of the phase; everything else follows from it.
- Transform errors should be **maximally debuggable** — step index *and* function name, with
  the original exception chained (D-06), not a terse position-only message.
- NaN/timezone conversion is acknowledged as a real correctness concern but deliberately left
  to research/planning to resolve **consistently with existing `from_dataframe` behavior** (D-07),
  rather than guessing now.

</specifics>

<deferred>
## Deferred Ideas

- **`extract_batch_size` streaming** (chunked extract via `db.stream()` for tables too large to
  materialize) — Pitfall 7 / ETL-STREAM-01; v0.6.0. Phase 18 honors `extract_limit` only.
- **COPY-based / staging-table truncate-load** (large-data fast path) — research Pitfall 2;
  deferred for v0.5.0's medium-data scope. Phase 18 uses TRUNCATE + `insert_batch` in one txn.
- **Advisory-lock concurrency guard** (`pg_try_advisory_lock`, `PipelineAlreadyRunning`) —
  Pitfall 8; not v0.5.0 (Phase 17 D-06 chose the honest left-`running` row over a concurrency
  guard). Revisit if concurrent-run corruption proves real.
- **GeoDataFrame-aware load** (route post-transform GeoDataFrames to `from_geodataframe`) —
  ETL-GEO-01; opportunistic, deferred unless spatial ETL demand emerges.
- **`RunResult` / `history()` / `last_run()` / `dry_run`** — Phase 19 (ETL-10/11/15/17), not this
  phase. Phase 18's `run()` returns a minimal value Phase 19 upgrades.
- **`AsyncETLAccessor` parity** — Phase 20 (ETL-12/13).

### Reviewed Todos (not folded)
None — no pending todos existed to review.

</deferred>

---

*Phase: 18-load-modes-extract*
*Context gathered: 2026-06-15*
