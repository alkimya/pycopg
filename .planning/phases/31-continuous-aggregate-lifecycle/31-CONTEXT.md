# Phase 31: Continuous Aggregate Lifecycle - Context

**Gathered:** 2026-06-22
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the **full continuous-aggregate lifecycle** as three new methods on **both**
`db.timescale.*` (sync) and `async_db.timescale.*` (async), using the established
pure-builder + `validate_identifiers` + `%s`-params + lazy-accessor + sync/async-parity
contract — with the **`connect(autocommit=True)` seam** correctly isolating CAGG DDL and
refresh from any enclosing transaction:

- `create_continuous_aggregate(view_name, select_sql, schema="public", materialized_only=True, with_no_data=False)`
  → **autocommit seam** (`CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous, ...)`)
- `refresh_continuous_aggregate(view_name, window_start=None, window_end=None, schema="public")`
  → **autocommit seam** (`CALL refresh_continuous_aggregate(...)`)
- `add_continuous_aggregate_policy(view_name, start_offset, end_offset, schedule_interval="1 hour", schema="public", if_not_exists=True)`
  → **standard `self._db.execute()`** (transaction-safe `SELECT add_*_policy(...)`, see D-01)

The continuous-aggregate trio ships together — create + refresh + policy are an indivisible
lifecycle (locked at milestone scope, 2026-06-22).

**In scope:** the 3 methods (sync+async), the autocommit isolation seam for create+refresh,
their guards/validation (`time_bucket(` heuristic, offset best-effort guard, refresh-window
type guard), and `test_accessor_parity` coverage of the 3 new methods.

**Out of scope (other phases / deferred):**
- `time_bucket` / `time_bucket_gapfill` query helpers → Phase 32 (TS-ADV-06/07).
- Full TS-ADV-10 9-method parity confirmation + coverage-of-all-autocommit-branches gate →
  Phase 32 (the last feature phase where the full 9-method surface exists). This phase only
  confirms the **3 new** methods are mirrored.
- `drop_continuous_aggregate` / `remove_continuous_aggregate_policy` (lifecycle **removal**)
  → TSDB-F01 (deferred — raw SQL works, low value).
- cagg-on-cagg waterfall as a dedicated API → out of scope (user writes `FROM schema.lower_cagg`
  inside `select_sql`).
</domain>

<decisions>
## Implementation Decisions

### Connection path per method (autocommit seam vs standard execute)
- **D-01 [resolves a prior-doc contradiction]:** `add_continuous_aggregate_policy` uses the
  **standard `self._db.execute()` path** — *not* an autocommit seam. Rationale: it is an
  ordinary `SELECT add_continuous_aggregate_policy(...)` function call, which is fully
  transaction-safe, exactly like the three already-shipped policy methods
  (`add_compression_policy`, `add_retention_policy`, and the Phase-30 `add_reorder_policy` —
  verified all three use plain `self._db.execute()`). The earlier STATE.md note ("policy also
  uses autocommit for consistency and safety") **predates** Phase 30 proving the policy
  precedent and is superseded. **Only `create_continuous_aggregate` and
  `refresh_continuous_aggregate` get the `connect(autocommit=True)` seam** — those two run
  internal multi-transaction operations and fail inside a transaction block.

- **D-02 [autocommit seam — reuse ETL precedent verbatim]:** `create_continuous_aggregate` and
  `refresh_continuous_aggregate` open a **dedicated** `with self._db.connect(autocommit=True) as conn:`
  connection and execute on its cursor — mirroring `ETLAccessor._start_run`/`_end_run`
  (`pycopg/etl.py:787-817`) **exactly**. This is the single architectural element new to this
  phase. The async side passes `autocommit=True` at `connect()` time (cannot be set after the
  async connection is open — milestone research SUMMARY §"Recommended Stack"). **Async guard
  must `await self._db.schema.has_extension("timescaledb")`** — the recurring Phase-23 gotcha;
  audit both async methods.

### `create_continuous_aggregate` surface
- **D-03 [WITH-clause options — keep minimal]:** Expose **exactly two flags**:
  `materialized_only` (default `True`, matches TSDB 2.13+ default) → renders
  `timescaledb.materialized_only=true|false` inside `WITH (timescaledb.continuous, ...)`; and
  `with_no_data` (default `False`) → renders trailing `WITH NO DATA` vs `WITH DATA`. **No other
  knobs** (`create_group_indexes` etc. deferred — user can write raw SQL). `select_sql` is
  passed through as structural SQL (documented as not-from-untrusted-input, like `aggregates`
  in the Phase-32 helpers).
- **D-04 [`time_bucket(` heuristic — locked at milestone scope]:** `create_continuous_aggregate`
  raises **`ValueError` before any DB round-trip** if `select_sql` does **not** contain the
  substring `time_bucket(`. (Carried forward from STATE.md milestone decisions; a cagg select
  without a `time_bucket` is almost always a user error.)

### `refresh_continuous_aggregate` window types
- **D-05 [window bounds are absolute timestamps, NOT relative intervals]:** `window_start` /
  `window_end` accept **`datetime | None`** (type hint `datetime | None`). A `datetime` is
  bound as a **bare `%s`** (psycopg 3 adapts to `timestamptz`). **`str` is rejected with a clear
  `ValueError`** — unlike Phase-30 `drop_chunks` (D-01/D-02), a refresh window is an absolute
  materialization range, so a relative `"7 days"` interval is semantically wrong here. This is a
  **deliberate divergence** from the `drop_chunks` `str|datetime|None` contract — note it for the
  planner so it doesn't blindly copy the Phase-30 type-driven cast.
- **D-06 [both-None = full refresh]:** Both bounds `None` → emit `NULL, NULL` (refresh the entire
  cagg range). One side `None` → open-ended on that side (emit `NULL` for that argument). The
  `CALL refresh_continuous_aggregate('schema.view', <start-or-NULL>, <end-or-NULL>)` always
  passes both positional window args.

### `add_continuous_aggregate_policy` offset validation
- **D-07 [best-effort guard; DB is the authority]:** `validate_interval(start_offset)` and
  `validate_interval(end_offset)` for **syntax** always (consistent with existing
  `validate_interval` usage on intervals in `timescale.py`; `None` is allowed for open-ended
  offsets and skips that check). For the ROADMAP criterion #3 "start_offset shorter than
  end_offset raises `ValueError` before any DB round-trip": add a **best-effort numeric
  comparison only when both offsets are simple, unambiguous same-unit forms** the code can parse
  with certainty (e.g. both `"N days"`, both `"N hours"`) → raise `ValueError` there. **Mixed or
  calendar units** (`"1 month"` vs `"30 days"`, `"1 year"` …) **skip** the Python comparison and
  let the **DB raise** (TimescaleDB enforces `start_offset > end_offset` correctly with a
  calendar anchor). Zero new deps (no interval-to-seconds parser). Document that the DB is the
  final authority on offset ordering.
- **D-08 [policy SQL surface]:** Mirror the `add_reorder_policy` shape: `start_offset`,
  `end_offset`, `schedule_interval` (default `"1 hour"`) rendered into the
  `add_continuous_aggregate_policy(...)` call; `if_not_exists` (default `True`) renders
  `, if_not_exists => true`. Identifiers (`view_name`, `schema`) validated; interval values as
  `%s` / validated intervals per the established pattern.

### Test strategy (carried-forward Apache-license constraint)
- **D-09 [REVISED 2026-06-23 after Phase-31 targeted research live-verification + user ack — ALL 3 methods mock-authoritative + license-tolerant]:**
  Local/CI TimescaleDB reports `timescaledb.license = apache` on **build 2.28.0**. Phase-31
  research **live-verified** (vs the Phase-30 *assumption*) that continuous aggregates are a
  **Community/TSL-only feature in their entirety** — **all three** methods raise
  `psycopg.errors.FeatureNotSupported` (SQLSTATE `0A000`) on the Apache build, not just the policy:
  `CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)`, `CALL refresh_continuous_aggregate(...)`,
  **and** `SELECT add_continuous_aggregate_policy(...)`. The original D-09 claim that "`create` +
  `refresh` are NOT license-gated … live tests assert real materialization" is **FALSE on the
  local/CI build** and is superseded. **Resolution (user-acked 2026-06-23):** *all three* methods
  follow the Phase-30 `add_reorder_policy` pattern — the **mock SQL-shape unit test is the
  authoritative assertion** for each generated statement; the **live integration test wraps each
  call in `try/except FeatureNotSupported: pass`** so it stays green/tolerated on Apache and asserts
  real materialization (`timescaledb_information.continuous_aggregates` row; materialized rows
  appear after refresh; `timescaledb_information.jobs` job row + `CALL run_job(job_id)`) **only on a
  Community-licensed build**. Mirror `tests/test_database_integration.py` ~lines 866-878 and the
  Phase-30 reorder-policy test. The license error must **propagate** to the caller (no swallow in
  the method body), exactly like `add_reorder_policy`.
- **D-10 [REVISED 2026-06-23 — autocommit isolation proven STRUCTURALLY, not via materialization]:**
  ROADMAP success criteria #1/#2 require proving the autocommit seam isolates create/refresh from an
  enclosing transaction. Because the cagg never materializes on Apache (D-09 revised), the
  materialization-dependent proofs cannot complete on the local/CI build. **Resolution
  (user-acked 2026-06-23):** prove isolation **structurally**:
  (a) **Mock-level (authoritative, license-independent):** assert `create`/`refresh` open a
  `connect(autocommit=True)` connection and execute on it — i.e. they do **not** route through the
  session-aware `self._db.execute()` path. This is the real guarantee.
  (b) **Live-level (license-tolerant, observable part):** wrap in `try/except FeatureNotSupported` —
  call `create_continuous_aggregate` after a prior `db.execute("SELECT 1")` in the same session, and
  call `refresh_continuous_aggregate` from inside a `db.session()` context, confirming the seam raises
  **only** the license error (`0A000`) and **not** a transaction-block error (`25001`/active-txn) —
  proving the autocommit connection bypassed the enclosing transaction. On a Community build these
  same tests assert real materialization. New tests extend `tests/test_timescale.py`
  (Phase-30 `ts_db` / `async_ts_db` skip-fixtures).

### Claude's Discretion
- Exact `queries.py` constant name(s) if any are added (milestone research suggests an optional
  `TSDB_LIST_CONTINUOUS_AGGREGATES` for an info-view JOIN used in test assertions — planner's
  call whether a constant is warranted or the test inlines the `timescaledb_information`
  queries).
- The precise set of "unambiguous same-unit" interval forms the D-07 best-effort comparator
  parses (e.g. whether to cover `seconds`/`minutes`/`hours`/`days`/`weeks` or just the common
  `days`/`hours`) — researcher/planner's call, as long as mixed/calendar units defer to the DB.
- Exact `ValueError` / docstring wording for the `time_bucket(` heuristic (D-04), the `str`
  rejection on refresh windows (D-05), and the offset-ordering guard (D-07).
- Whether the autocommit seam uses `conn.execute(...)` directly or `conn.cursor(...) as cur`
  (ETL uses an explicit cursor with `dict_row`; `create`/`refresh` return `None` so a plain
  `conn.execute` may suffice) — planner's call, must preserve the autocommit isolation.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope
- `.planning/REQUIREMENTS.md` — **TS-ADV-01/02/03** verbatim signatures + baked criteria
  (create on `connect(autocommit=True)`, `materialized_only=True` default; refresh `CALL`-based,
  both-None=full refresh; policy `start_offset`/`end_offset`/`schedule_interval`/`if_not_exists`)
- `.planning/ROADMAP.md` §"Phase 31: Continuous Aggregate Lifecycle" — goal + 4 success criteria
  (autocommit isolation proof, `time_bucket(` ValueError, offset-ordering ValueError, async
  `await`-guard parity)

### Research (project-level, HIGH confidence, already done)
- `.planning/research/SUMMARY.md` — §"Architecture Approach" Pattern 2 (autocommit seam = 2
  methods: create+refresh, mirrors `ETLAccessor._start_run`/`_end_run`); §"Recommended Stack"
  (async `autocommit=True` must be passed at `connect()` time, read-only after open);
  §"Critical Pitfalls" 1 (CAGG DDL+refresh can't run in a txn block), 5 (async guard `await`),
  6 (policy tests use `CALL run_job()`, never sleep-and-wait)
- `.planning/research/PITFALLS.md` — pitfall 1 (autocommit seam), 5 (async `await` guard),
  6 (policy job-row + `run_job`, no scheduler sleep)
- `.planning/research/FEATURES.md`, `.planning/research/STACK.md`, `.planning/research/ARCHITECTURE.md`

### Prior phase context (directly relevant)
- `.planning/phases/30-chunk-management-partitioning/30-CONTEXT.md` — **D-12** (Apache-license
  `FeatureNotSupported` policy-test strategy, carried forward here as D-09); **D-10/D-11** (new
  `tests/test_timescale.py` + `ts_db`/`async_ts_db` skip-fixtures + mock/live two-layer testing);
  **D-09** (`TimescaleError` already added to `exceptions.py`, available for reuse)

### Codebase patterns to mirror
- `pycopg/etl.py:787-817` — `ETLAccessor._start_run`/`_end_run`: the **exact** autocommit-seam
  precedent (`with self._db.connect(autocommit=True) as conn: with conn.cursor(...) as cur:`)
- `pycopg/timescale.py:209-281` — `add_compression_policy` / `add_retention_policy`: the
  `SELECT add_*_policy(...)` + `validate_interval` + plain `execute()` shape for the policy method
- `pycopg/timescale.py:622-668` — `add_reorder_policy` (Phase 30): closest policy analog
  (`if_not_exists` rendering, license-tolerance docstring, plain `execute()`)
- `pycopg/database.py:379` / `pycopg/async_database.py:378` — `connect(autocommit=False)` seam
  used by create/refresh (`autocommit=True`)
- `pycopg/exceptions.py` — `PycopgError` base + `TimescaleError` (from Phase 30, D-09) + `ExtensionNotAvailable`
- `pycopg/utils.py` — `validate_identifier`/`validate_identifiers` (78/107) + `validate_interval` (125)
- `tests/test_parity.py` §`ACCESSOR_PAIRS` (line 24) — `(TimescaleAccessor, AsyncTimescaleAccessor)`
  already registered; `test_accessor_parity` (line 35) auto-covers the 3 new methods — **no
  registry change**
- `tests/test_timescale.py` — extend (created in Phase 30); `ts_db` + `async_ts_db` skip-fixtures
- `tests/test_database_integration.py` ~lines 866-878 — `try/except FeatureNotSupported: pass`
  live-policy-test pattern to mirror for the cagg policy
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Autocommit seam (`pycopg/etl.py:787-817`):** `with self._db.connect(autocommit=True) as conn:`
  is already proven for transaction-isolated writes — `create`/`refresh` reuse it verbatim.
- **`validate_interval` (`pycopg/utils.py:125`):** syntax-validates `start_offset`/`end_offset`/
  `schedule_interval` strings (D-07).
- **`TimescaleError` (`pycopg/exceptions.py`):** milestone-wide TSDB-domain error added in
  Phase 30 — available if any cagg DB error needs domain-wrapping.
- **`ts_db` / `async_ts_db` skip-fixtures (`tests/test_timescale.py`):** create-extension-or-skip,
  ready to host the 3 new methods' live tests.
- **`ACCESSOR_PAIRS` + `test_accessor_parity`:** timescale pair registered — adding the 3 methods
  to both classes auto-satisfies the 3-method parity sub-goal (full TS-ADV-10 is Phase 32).

### Established Patterns
- **Per-method extension guard** raising `ExtensionNotAvailable` (sync) / `await ... ` (async).
  The async `await` omission is the recurring Phase-23 gotcha — **audit both async cagg methods**.
- **Policy methods** = `SELECT add_*_policy(...)` on plain `execute()`, `if_not_exists => true`
  rendered conditionally, `validate_interval` on interval args (D-01/D-08).
- **Pure-builder** = identifiers validated + interpolated; runtime values bound as `%s`. The
  create/refresh twist: the `%s` values run on the **autocommit cursor**, not `self._db.execute`.

### Integration Points
- New methods → both classes in `pycopg/timescale.py`; possible 1 SQL constant →
  `pycopg/queries.py`; new tests → `tests/test_timescale.py`. No other files (`exceptions.py`
  already has `TimescaleError`; `ACCESSOR_PAIRS` unchanged).
- `db.timescale` / `async_db.timescale` lazy accessors already wired (v0.6.0) — methods just appear.
</code_context>

<specifics>
## Specific Ideas

- The autocommit isolation must be **proven by test**, not just assumed: create succeeds after a
  prior same-session `db.execute`, and refresh succeeds from inside a `db.session()` context
  (D-10). These are the two ROADMAP criteria that justify the seam's existence.
- `refresh` windows are **absolute timestamps** — reject relative-interval strings (D-05). This
  is a deliberate departure from Phase-30 `drop_chunks`; the planner must not blindly copy the
  Phase-30 `str→%s::interval` cast onto the refresh window.
- Offset validation is **honest about its limits** (D-07): catch the unambiguous common case in
  Python, defer calendar-unit comparisons to the DB. Don't fake a full interval parser.
</specifics>

<deferred>
## Deferred Ideas

- **`drop_continuous_aggregate` / `remove_continuous_aggregate_policy`** (lifecycle removal) →
  TSDB-F01 (deferred — raw SQL works, low value). Not requested; listed to mark the boundary.
- **`create_group_indexes` and other `WITH (...)` cagg knobs** → deferred (D-03 keeps the surface
  to `materialized_only` + `with_no_data`). User can write raw SQL for advanced options.
- **cagg-on-cagg waterfall as a dedicated API** → out of scope (user writes `FROM schema.lower_cagg`
  in `select_sql`).
- **`time_bucket` / `time_bucket_gapfill` query helpers** → Phase 32 (in milestone, not this phase).
- **Full TS-ADV-10 9-method parity + all-autocommit-branch coverage gate** → Phase 32.

None of these arose as scope-creep requests — listed only to mark the boundary explicitly.
</deferred>

---

*Phase: 31-Continuous Aggregate Lifecycle*
*Context gathered: 2026-06-22*
