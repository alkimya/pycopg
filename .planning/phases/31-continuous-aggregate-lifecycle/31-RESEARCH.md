# Phase 31: Continuous Aggregate Lifecycle - Research

**Researched:** 2026-06-23
**Domain:** TimescaleDB continuous aggregates (create/refresh/policy) + psycopg 3 autocommit-seam isolation
**Confidence:** HIGH (all five SQL-surface items live-verified against the local TSDB 2.28.0 build; the one item that cannot be verified live — actual cagg materialization — is blocked by the Apache license, and that blockage is itself the headline finding)

> This is a **targeted** pass. CONTEXT.md D-01..D-10 are LOCKED and are NOT re-litigated below,
> EXCEPT where a live-DB check **contradicts** a stated assumption — flagged loudly in
> `## Contradictions with CONTEXT.md`, exactly as the Phase 30 pass did. One material
> contradiction was found (the most important output of this pass).

---

## Live Verification Results

**Environment confirmed live:** `psql -h localhost -U postgres -d pycopg_test`
- `SELECT extversion FROM pg_extension WHERE extname='timescaledb'` → **`2.28.0`** `[VERIFIED-LIVE]`
- `SHOW timescaledb.license` → **`apache`** `[VERIFIED-LIVE]`

### Task 1 — Autocommit-seam isolation for CAGG DDL — `[VERIFIED-LIVE + VERIFIED-DOCS]`

**1a. Does CAGG DDL fail inside a transaction block?**
On this **Apache** build the question is moot at the license layer (see Contradiction #1) — but
the transaction-block restriction is independently real and documented for Community builds.

Live, inside `BEGIN; CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous) ... WITH NO DATA; ROLLBACK;`:
```
ERREUR:  0A000: functionality not supported under the current "apache" license.
EMPLACEMENT : error_no_default_fn_community, cross_module_fn.c : 119
```
The **same statement in autocommit (no txn block) also fails identically** with `0A000`. So on
this build the failure is the **license**, not the transaction. `[VERIFIED-LIVE]`

**The transaction-block restriction itself (the seam's true justification on a Community build)
is documented** `[VERIFIED-DOCS]`:
- `refresh_continuous_aggregate()` "cannot run inside a transaction block since the refresh runs
  across two transactions (one to move the invalidation threshold and one to materialize)."
  Workaround: run on an **autocommit** connection. (TimescaleDB issue #2876; docs)
- For **create**: the official docs state *"To create a continuous aggregate within a transaction
  block, use the `WITH NO DATA` option."* → it is specifically the **`WITH DATA`
  materialization** that cannot run in a txn block; a `WITH NO DATA` create can. The autocommit
  seam covers **both** cases safely, so the seam is the correct, conservative choice for create.

**Exact error psycopg raises (what NOT to catch):** verified via `uv run python` —
`psycopg.errors.FeatureNotSupported`, `sqlstate='0A000'`. This is the **license** error, distinct
from the transaction-block error (which on a Community build surfaces as
`psycopg.errors.ActiveSqlTransaction`/`InvalidTransactionState`, SQLSTATE `25xxx`). Neither should
be caught by the create/refresh methods — the seam *prevents* the txn-block error from ever
arising, and the license error must propagate to the caller (mirrors `add_reorder_policy`). `[VERIFIED-LIVE]`

**ETL seam shape at `etl.py:787-817` is the correct verbatim precedent** `[VERIFIED-LIVE in code]`:
```python
with self._db.connect(autocommit=True) as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(queries.ETL_INIT_PIPELINE_RUNS)
```
`db.connect(autocommit=True)` (database.py:374-396) and `async_database.py:371-395) both pass
`autocommit` straight to `psycopg.connect(...)` / `AsyncConnection.connect(...)`. Correct seam.

**Async: `autocommit=True` MUST be passed at `connect()` time** `[VERIFIED-LIVE]`:
```
await conn.execute("SELECT 1")        # opens an implicit txn
await conn.set_autocommit(True)
→ ProgrammingError: can't change 'autocommit' now: connection in transaction status INTRANS
```
Passing it at connect time works: `connect(autocommit=True).autocommit == True`. Because the
pycopg async seam (`async_database.py:371-375`) already passes `autocommit=` into
`AsyncConnection.connect(...)`, `async with self._db.connect(autocommit=True) as conn:` is the
correct async mirror. **Confirms D-02.**

### Task 2 — `create_continuous_aggregate` SQL surface (D-03/D-04) — `[VERIFIED-LIVE (parse path) + VERIFIED-DOCS (options)]`

- **`WITH (...)` option spelling:** `timescaledb.continuous` + `timescaledb.materialized_only`
  are the correct option keys; the statement **parsed** (reached the license gate, not a syntax
  error) on 2.28.0 with `WITH (timescaledb.continuous, timescaledb.materialized_only=true)`.
  `[VERIFIED-LIVE]`
- **`materialized_only=True` is the 2.13+ default** — `[VERIFIED-DOCS / ASSUMED-from-CONTEXT]`.
  The local docs page did not restate the version; CONTEXT D-03 carries this from milestone
  research (HIGH-confidence project research). Rendering it **explicitly** (rather than relying on
  the server default) is the safe choice and is what D-03 specifies. Keep rendering it explicitly.
- **`WITH NO DATA` vs `WITH DATA` trailing clause:** confirmed by docs — default create is
  `WITH DATA` (populated immediately); `WITH NO DATA` creates instantly and defers materialization
  to a refresh/policy. The trailing clause is `WITH NO DATA` / `WITH DATA` (no `timescaledb.`
  prefix). `[VERIFIED-DOCS]`
- **`time_bucket(` realistically required (D-04 heuristic justification):** a continuous aggregate
  must group by a `time_bucket(...)` of the hypertable time column — this is a hard TimescaleDB
  requirement, not a style preference. A cagg `select_sql` without `time_bucket(` is therefore
  almost always a user error → the pre-DB `ValueError` substring check is well-founded.
  `[VERIFIED-DOCS]`

**Rendered template (recommended):**
```sql
CREATE MATERIALIZED VIEW {schema}.{view_name}
WITH (timescaledb.continuous, timescaledb.materialized_only={true|false})
AS {select_sql}
WITH {NO DATA | DATA}
```
`{schema}`/`{view_name}` are `validate_identifiers`-checked then interpolated; `{select_sql}` is
structural SQL passed through (documented not-from-untrusted-input, like `aggregates` in Phase 32);
the two booleans render literal `true`/`false` and `NO DATA`/`DATA` (no `%s` params — there are no
runtime *values* in a create, only structure).

### Task 3 — `refresh_continuous_aggregate` CALL signature (D-05/D-06) — `[VERIFIED-LIVE (catalog) + VERIFIED-DOCS]`

**Exact procedure signature on 2.28.0** (from `pg_proc`, license-independent) `[VERIFIED-LIVE]`:
```
refresh_continuous_aggregate(
  IN continuous_aggregate regclass,
  IN window_start "any",
  IN window_end   "any",
  IN force   boolean DEFAULT false,
  IN options jsonb   DEFAULT NULL)
```
- It is a **procedure** → invoked with `CALL`, **returns nothing**. `[VERIFIED-LIVE]`
- `window_start`/`window_end` are `"any"` → accept `NULL` (full refresh) and accept a
  `%s`-bound Python `datetime` (psycopg 3 adapts `datetime` → `timestamptz`). Passing `NULL, NULL`
  is the documented "refresh the entire range" form. **Confirms D-06.** `[VERIFIED-LIVE + DOCS]`
- **Window bounds are absolute timestamps, NOT relative intervals** — confirmed by the procedure
  semantics (start/end of a materialization *range*) and docs. A relative `"7 days"` string is
  semantically wrong here, so **D-05's `str` rejection is correct** and the planner must NOT copy
  the Phase-30 `drop_chunks` `str→%s::interval` cast. `[VERIFIED-DOCS]`
- New in 2.28.0: refresh batches the window by default (`buckets_per_batch=10`), each batch in its
  own txn — this is **exactly why** it cannot run in an enclosing transaction block, reinforcing
  the autocommit seam. `[VERIFIED-DOCS]`

**Rendered template (recommended):**
```sql
CALL refresh_continuous_aggregate('{schema}.{view_name}', %s, %s)
```
with params `[window_start_or_None, window_end_or_None]`. `None` → psycopg binds SQL `NULL`. Both
positional args are always present (D-06). Run on the **autocommit cursor**, not `self._db.execute`.

> Note: `'{schema}.{view_name}'` is a `regclass` literal — `validate_identifiers(view_name, schema)`
> then interpolate. (psycopg cannot bind a regclass via `%s` cleanly here; the identifier-validation
> path is the established pycopg approach, consistent with every other timescale method.)

### Task 4 — `add_continuous_aggregate_policy` signature + offset ordering (D-07/D-08) — `[VERIFIED-LIVE]`

**Exact signature on 2.28.0** (from `pg_proc`) `[VERIFIED-LIVE]`:
```
add_continuous_aggregate_policy(
  continuous_aggregate regclass,
  start_offset "any",
  end_offset   "any",
  schedule_interval interval,
  if_not_exists boolean DEFAULT false,
  initial_start timestamptz DEFAULT NULL,
  timezone text DEFAULT NULL,
  ... (more optional args; ignore — D-08 keeps surface minimal))
```
Argument **names and order match D-08**: `continuous_aggregate, start_offset, end_offset,
schedule_interval, if_not_exists`. Use named args (`start_offset =>`, `end_offset =>`,
`schedule_interval =>`, `if_not_exists =>`) for clarity, mirroring the existing
`add_compression_policy` / `add_reorder_policy` shape.

**License gate — CRITICAL confirmation of D-09** `[VERIFIED-LIVE]`:
```python
conn.execute("SELECT add_continuous_aggregate_policy('public.r31_metrics',
              start_offset => INTERVAL '7 days', end_offset => INTERVAL '1 hour',
              schedule_interval => INTERVAL '1 hour')")
→ psycopg.errors.FeatureNotSupported  sqlstate=0A000
  msg: function "add_continuous_aggregate_policy" is not supported under the current "apache" license
```
So the cagg policy **IS license-gated on this build** → D-09's mock-authoritative +
live-tolerant strategy is correct **for the policy**, AND (per Contradiction #1) must also be
applied to create + refresh.

**DB error when `start_offset` shorter than `end_offset`:** could **not** be observed live on this
build — the license gate (`0A000`) fires *before* the offset-ordering check, so the DB never
reaches the comparison. `[UNVERIFIABLE-LIVE]`. On a Community build TimescaleDB raises
`ERROR: 22023: start_offset` (... ) `must be greater than end_offset` (invalid_parameter_value).
D-07's best-effort Python guard catches the unambiguous same-unit case *before* any DB round-trip,
which is what ROADMAP criterion #3 requires and works regardless of license — this is the
**right** design given the gate.

**D-07 comparator — concrete recommendation (Claude's Discretion item, now resolved):**
Parse with `^(\d+)\s+(second|minute|hour|day|week)s?$` (case-insensitive). When **both** offsets
match **and share the same unit**, compare the integer counts and raise `ValueError` if
`start_offset <= end_offset`. **Cover `second | minute | hour | day | week`** (all fixed-duration
units). **Defer `month` / `year`** (calendar-anchored, ambiguous) and **any mixed-unit pair**
(`"1 day"` vs `"6 hours"`) to the DB. Verified live:
```
"7 days"→(7,'day')  "1 hour"→(1,'hour')  "30 minutes"→(30,'minute')
"45 seconds"→(45,'second')  "2 weeks"→(2,'week')  "1 month"→None (deferred)  ✓
```
Rationale for not cross-converting units: it would require a real interval-to-seconds parser
(week→day is safe, but day→hour assumes 24h which DST can break; month/year are calendar). D-07
explicitly forbids a new parser and "zero new deps". Same-unit integer comparison is exact and
dependency-free. `validate_interval` already accepts every form above `[VERIFIED-LIVE]`, so the
comparator runs **after** `validate_interval` syntax-checks both offsets (skip the check when an
offset is `None` for open-ended).

### Task 5 — Async `await`-guard parity (Pitfall 5 / Phase-23 gotcha) — `[VERIFIED-LIVE in code]`

Audited `pycopg/timescale.py`: **every** async method uses
`if not await self._db.schema.has_extension("timescaledb"):` (lines 720, 763, 818, 855, 881, 909,
962, 1043, 1168, 1230 — including the async `add_reorder_policy` at 1230). The sync methods use the
same without `await`. The async guard pattern to replicate verbatim on all 3 new async methods:
```python
if not await self._db.schema.has_extension("timescaledb"):
    raise ExtensionNotAvailable(
        "TimescaleDB extension not installed. "
        "Run db.schema.create_extension('timescaledb')"
    )
```
**The recurring Phase-23 bug** is omitting `await` (the coroutine is truthy → guard always passes,
silently). The planner's acceptance criteria MUST assert `await` is present on the `has_extension`
call in all 3 new async methods. A cheap, robust check: an async mock test where
`mock_schema.has_extension = AsyncMock(return_value=False)` and the method is expected to raise
`ExtensionNotAvailable` — a missing `await` makes the coroutine truthy and the test fails. This
pattern already exists for `add_reorder_policy` (`test_add_reorder_policy_async_no_extension_raises`,
test_timescale.py:997) — copy it for each new async method.

### Task 6 — Info-view assertions for tests — `[VERIFIED-LIVE]`

**`timescaledb_information.continuous_aggregates` columns on 2.28.0** (assert a view exists):
```
hypertable_schema, hypertable_name, view_schema, view_name, view_owner,
materialized_only, compression_enabled,
materialization_hypertable_schema, materialization_hypertable_name, view_definition
```
Assertion: `SELECT 1 FROM timescaledb_information.continuous_aggregates
WHERE view_schema = %s AND view_name = %s`.

**`timescaledb_information.jobs` columns on 2.28.0** (assert a policy job row exists):
```
job_id, application_name, schedule_interval, max_runtime, max_retries, retry_period,
proc_schema, proc_name, owner, scheduled, fixed_schedule, config, next_start, initial_start,
hypertable_schema, hypertable_name, check_schema, check_name
```
Assertion (Community build only): `SELECT job_id FROM timescaledb_information.jobs
WHERE hypertable_name = %s AND proc_name = 'policy_refresh_continuous_aggregate'`.
(`config` JSONB carries `start_offset`/`end_offset`; `CALL run_job(job_id)` then exercises it.)

**`queries.py` constant recommendation (Claude's Discretion — resolved):** a
`TSDB_LIST_CONTINUOUS_AGGREGATES` constant is **NOT warranted**. The two info-view queries above
are test-only assertions, used in at most a couple of live tests, and Phase 30 set the precedent of
inlining `timescaledb_information.jobs` assertions directly in the test
(`test_database_integration.py:1154`). Inline them. The production methods need **no** `queries.py`
constant either — create/refresh/policy SQL is rendered inline like every other timescale method
(no existing TSDB method uses a `queries.py` constant for its DDL). **Net: no `queries.py` change.**

---

## Contradictions with CONTEXT.md

### ⚠️ Contradiction #1 (MATERIAL — must reach the planner): D-09 "create + refresh are NOT license-gated" is FALSE on the Apache build

CONTEXT D-09 states:
> "**`create` + `refresh` are NOT license-gated** — they run on any TSDB 2.x build, so their live
> tests assert real materialization (view in `timescaledb_information.continuous_aggregates`,
> materialized rows appear after refresh)."

**Live result contradicts this.** Continuous aggregates are a **TSL/Community-only** feature. On
the local/CI **Apache** build (`timescaledb.license = apache`, the documented project + CI env):

| Operation | Live result on Apache 2.28.0 | Exception |
|-----------|------------------------------|-----------|
| `CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous)` | **0A000** functionality not supported | `FeatureNotSupported` |
| `CALL refresh_continuous_aggregate(...)` | reaches cagg machinery → same TSL gate | `FeatureNotSupported` (Community-only path) |
| `SELECT add_continuous_aggregate_policy(...)` | **0A000** function not supported | `FeatureNotSupported` |

Cross-checked against TimescaleDB licensing: *"continuous aggregates, compression, and tiered
storage are licensed under the TSL ... not available under the Apache license alone."*

**Consequence for the test plan (the important part):** the D-09/D-10 plan to have create + refresh
**live tests assert real materialization** is **not achievable on the local/CI build**. The
`timescaledb_information.continuous_aggregates` row assertion and "materialized rows appear after
refresh" assertion will **never run green** here — they will hit `FeatureNotSupported` exactly like
the policy. The autocommit-isolation proofs (ROADMAP #1/#2, D-10) that depend on a *successfully
created* cagg are likewise blocked on this build.

**This is NOT a blocker for the phase** — it is a test-strategy correction. The recommended
resolution is in `## Test plan` below: treat **all three** methods as mock-authoritative +
live-tolerant (the Phase-30 `add_reorder_policy` pattern, already proven), and make the
autocommit-isolation proofs **structural** (assert the seam is used) rather than
materialization-dependent. The planner should surface this to the user as a one-line decision
("cagg live tests are license-tolerant like reorder-policy; isolation proven structurally") since
it adjusts D-09/D-10 — but it changes *testing*, not the *API surface*, which is unchanged.

### No other contradictions

D-01 (policy = plain `execute()`), D-02 (autocommit seam shape + async-connect-time), D-03
(option spellings), D-04 (`time_bucket(` requirement), D-05 (absolute-timestamp windows),
D-06 (both-None=full), D-07 (best-effort guard), D-08 (policy signature) all **verified consistent**
with the live DB and catalog.

---

## Recommended approach per method

All three live in **both** `TimescaleAccessor` and `AsyncTimescaleAccessor` in
`pycopg/timescale.py`. Guard order for every method: **`validate_*` → extension guard → execute**
(sync uses plain `has_extension`; async uses `await has_extension`).

### `create_continuous_aggregate(view_name, select_sql, schema="public", materialized_only=True, with_no_data=False)`
```python
# 1. structural validation (pre-DB)
validate_identifiers(view_name, schema)
if "time_bucket(" not in select_sql:                      # D-04
    raise ValueError(
        "select_sql for a continuous aggregate must contain a time_bucket(...) "
        "grouping (got a select without one)."
    )
# 2. extension guard (sync shown; async: `if not await self._db.schema.has_extension(...)`)
if not self._db.schema.has_extension("timescaledb"):
    raise ExtensionNotAvailable("TimescaleDB extension not installed. Run db.schema.create_extension('timescaledb')")
# 3. render
mo = "true" if materialized_only else "false"
data = "NO DATA" if with_no_data else "DATA"
sql = (
    f"CREATE MATERIALIZED VIEW {schema}.{view_name}\n"
    f"WITH (timescaledb.continuous, timescaledb.materialized_only={mo})\n"
    f"AS {select_sql}\n"
    f"WITH {data}"
)
# 4. AUTOCOMMIT SEAM (sync; async mirrors with `async with ... await conn.execute(...)`)
with self._db.connect(autocommit=True) as conn:
    conn.execute(sql)        # create returns nothing → plain conn.execute is fine (D's discretion)
```

### `refresh_continuous_aggregate(view_name, window_start=None, window_end=None, schema="public")`
```python
validate_identifiers(view_name, schema)
for bound in (window_start, window_end):                  # D-05: reject relative-interval strings
    if bound is not None and not isinstance(bound, datetime):
        raise ValueError(
            "refresh window bounds must be datetime or None (absolute timestamps); "
            f"got {type(bound).__name__}. Relative interval strings are not accepted — "
            "a refresh window is an absolute materialization range."
        )
if not self._db.schema.has_extension("timescaledb"):      # async: await
    raise ExtensionNotAvailable(...)
sql = f"CALL refresh_continuous_aggregate('{schema}.{view_name}', %s, %s)"   # D-06: both args always
with self._db.connect(autocommit=True) as conn:           # AUTOCOMMIT SEAM
    conn.execute(sql, [window_start, window_end])          # None → NULL; datetime → timestamptz
```

### `add_continuous_aggregate_policy(view_name, start_offset, end_offset, schedule_interval="1 hour", schema="public", if_not_exists=True)`
```python
validate_identifiers(view_name, schema)
if start_offset is not None: validate_interval(start_offset)   # D-07 syntax
if end_offset   is not None: validate_interval(end_offset)
_check_offset_ordering(start_offset, end_offset)               # D-07 best-effort same-unit compare → ValueError
validate_interval(schedule_interval)
if not self._db.schema.has_extension("timescaledb"):           # async: await
    raise ExtensionNotAvailable(...)
ne = ", if_not_exists => true" if if_not_exists else ""
# D-01: PLAIN execute() — NOT the autocommit seam (transaction-safe SELECT add_*_policy)
self._db.execute(                                              # async: await self._db.execute(...)
    f"SELECT add_continuous_aggregate_policy("
    f"'{schema}.{view_name}', "
    f"start_offset => INTERVAL '{start_offset}', "      # or NULL when None — render NULL literal
    f"end_offset => INTERVAL '{end_offset}', "
    f"schedule_interval => INTERVAL '{schedule_interval}'{ne}) AS job_id"
)
# NOTE: this raises FeatureNotSupported on the Apache build — propagate it (like add_reorder_policy).
```
where the `_check_offset_ordering` helper:
```python
_OFFSET_RE = re.compile(r"^(\d+)\s+(second|minute|hour|day|week)s?$", re.IGNORECASE)
def _check_offset_ordering(start_offset, end_offset):
    if start_offset is None or end_offset is None:
        return                                  # open-ended → DB authority
    ms, me = _OFFSET_RE.match(start_offset.strip()), _OFFSET_RE.match(end_offset.strip())
    if ms and me and ms.group(2).lower() == me.group(2).lower():   # same fixed unit only
        if int(ms.group(1)) <= int(me.group(1)):
            raise ValueError(
                f"start_offset ({start_offset!r}) must cover a longer window than "
                f"end_offset ({end_offset!r})."
            )
    # mixed-unit / month / year → defer to the DB (it raises 22023 on a Community build)
```
> When an offset is `None`, render the SQL literal `NULL` (not `INTERVAL 'None'`). The render snippet
> above assumes non-None; the planner should branch the fragment per-offset (`NULL` vs
> `INTERVAL '...'`). `start_offset`/`end_offset` are `"any"`-typed so a literal `NULL` is valid for
> open-ended offsets.

---

## Test plan

Two layers, mirroring Phase 30 (D-09/D-11). **The license finding (Contradiction #1) means all
three methods are mock-authoritative + live-tolerant — not just the policy.**

### Layer 1 — Mock SQL-shape unit tests (AUTHORITATIVE for all 3 methods)
Use `MagicMock(spec=SchemaAccessor)` / `MagicMock(spec=AsyncSchemaAccessor)` with
`has_extension` returning truthy, and mock the connection seam. For create/refresh the seam is
`self._db.connect(autocommit=True)` returning a context manager whose `conn.execute` is a
`MagicMock` capturing the SQL — assert:
- **create:** SQL contains `CREATE MATERIALIZED VIEW {schema}.{view}`,
  `WITH (timescaledb.continuous, timescaledb.materialized_only=true)`, and trailing `WITH DATA`
  (and `materialized_only=false` / `WITH NO DATA` when flags flipped); assert `connect` was called
  with `autocommit=True`.
- **create ValueError:** `select_sql` without `time_bucket(` raises `ValueError` **before** any
  `connect`/`execute` (assert seam never opened).
- **refresh:** SQL == `CALL refresh_continuous_aggregate('{schema}.{view}', %s, %s)`, params
  `[start, end]`; both-None → params `[None, None]`; assert `connect(autocommit=True)`.
- **refresh ValueError:** `str` window bound raises `ValueError` before the seam opens.
- **policy:** SQL contains `add_continuous_aggregate_policy(`, the offset/schedule INTERVALs, and
  `if_not_exists => true` (and its absence when `if_not_exists=False`); plain `db.execute` used
  (NOT the autocommit seam) — assert `connect` was **not** called.
- **policy offset ValueError:** `start_offset="1 hour", end_offset="7 hours"` (same unit, start<end)
  raises `ValueError` before any execute; mixed-unit `"1 day"`/`"6 hours"` does **not** raise in
  Python (defers to DB).
- **async parity for all of the above:** `AsyncMock`; **assert `await` on `has_extension`** via an
  async no-extension test (`has_extension=AsyncMock(return_value=False)` → `ExtensionNotAvailable`)
  for each of the 3 methods (this is the Phase-23 `await`-omission catch).

### Layer 2 — Live-DB integration tests (LICENSE-TOLERANT — extend `tests/test_timescale.py`)
Because the local/CI build is Apache, **wrap the real cagg calls in
`try/except FeatureNotSupported: pass`** for all three methods (mirror the existing
`test_add_reorder_policy_live`, test_timescale.py ~1140 / test_database_integration.py ~866-878):
- **create live:** build a hypertable via the existing `_make_hypertable` helper, call
  `create_continuous_aggregate(... time_bucket select ...)` inside `try/except FeatureNotSupported`.
  On a Community build, additionally assert the `timescaledb_information.continuous_aggregates` row
  exists. On Apache, the `except` makes the test green while still exercising the code path + seam.
- **refresh live:** same tolerance; on Community, refresh then assert materialized rows.
- **policy live:** same tolerance; on Community, assert the `timescaledb_information.jobs` row
  (`proc_name='policy_refresh_continuous_aggregate'`) + `CALL run_job(job_id)` succeeds.

### Autocommit-isolation proofs (ROADMAP #1/#2, D-10) — make them STRUCTURAL on this build
The materialization-dependent proofs from D-10 ("create succeeds after a prior `db.execute`",
"refresh from inside `db.session()` materializes rows") cannot complete on Apache because the cagg
never materializes. Recommended:
1. **Mock-level structural proof (authoritative):** assert create/refresh call
   `self._db.connect(autocommit=True)` (a *fresh* connection), proving they bypass the
   session-aware path — this is the real guarantee and runs license-independently.
2. **Live tolerant proof:** still issue `db.execute("SELECT 1")` then `create_...` inside
   `try/except FeatureNotSupported`, and call `refresh_...` from inside a `db.session()` block
   inside `try/except FeatureNotSupported` — confirming the seam does not raise a *transaction*
   error (only the license error), which is the observable part of the isolation guarantee on
   Apache. On a Community build these become full materialization proofs unchanged.

### Parity
`ACCESSOR_PAIRS` already registers `(TimescaleAccessor, AsyncTimescaleAccessor)` (test_parity.py:25)
— adding the 3 methods to **both** classes auto-satisfies the 3-method parity sub-goal via
`test_accessor_parity`. **No registry change.** (Full TS-ADV-10 9-method gate is Phase 32.)

### Coverage
Ratchet ≥94% must hold. The autocommit branches of create/refresh execute under the mock seam in
Layer 1, so they are covered even though the live cagg is license-blocked. Confirm the mock seam
context-manager is wired so `conn.execute` lines register as covered.

---

## Open Questions for planner

1. **D-09/D-10 wording update (needs a one-line user ack, like Phase 30's D-08/D-12 reshape).**
   Continuous aggregates are TSL/Community-only; the local/CI build is Apache, so create + refresh
   are license-gated **too** (not just policy). Recommended resolution: all 3 methods
   mock-authoritative + live-tolerant; isolation proven structurally (see Test plan). Confirm this
   adjusts D-09/D-10 as testing-only (API surface unchanged). *(This is the headline of this pass.)*
2. **`None`-offset SQL rendering for the policy** — when `start_offset`/`end_offset` is `None`,
   render the literal `NULL` (open-ended) rather than `INTERVAL 'None'`. The skeleton above flags
   it; the planner should make the per-offset fragment branch explicit in the task.
3. **`conn.execute` vs explicit `conn.cursor()` in the seam (D's discretion, D-142 area):** create
   and refresh return nothing, so plain `conn.execute(sql, params)` on the autocommit connection is
   sufficient and simpler than the ETL `with conn.cursor(row_factory=dict_row) as cur` form
   (which exists only because ETL needs `RETURNING run_id`). Recommend plain `conn.execute`.

---

## Validation Architecture

> Nyquist applies (config has no `workflow.nyquist_validation: false`). Framework: **pytest** via
> `uv run pytest` (config in `pyproject.toml`; `asyncio_mode = "auto"`).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (+ pytest-asyncio, `asyncio_mode="auto"`) via `uv run` |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`; coverage gate in `addopts`) |
| Quick run command | `uv run pytest tests/test_timescale.py -x -q -o addopts=""` |
| Full suite command | `uv run pytest` (enforces coverage ratchet ≥94%) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TS-ADV-01 | create cagg via autocommit seam; `time_bucket(` ValueError; materialized_only default | unit (mock-authoritative) + live-tolerant | `uv run pytest tests/test_timescale.py -k create_continuous_aggregate -o addopts=""` | ❌ Wave 0 (extend) |
| TS-ADV-02 | refresh via autocommit seam; both-None=full; `str`-window ValueError; session-bypass | unit (mock-authoritative) + live-tolerant | `uv run pytest tests/test_timescale.py -k refresh_continuous_aggregate -o addopts=""` | ❌ Wave 0 |
| TS-ADV-03 | policy via plain execute; offset-ordering ValueError; jobs row / run_job (Community) | unit (authoritative) + live-tolerant | `uv run pytest tests/test_timescale.py -k continuous_aggregate_policy -o addopts=""` | ❌ Wave 0 |
| (cross) | async parity + `await` on guard (all 3) | unit (parity + async no-ext) | `uv run pytest tests/test_parity.py tests/test_timescale.py -k async -o addopts=""` | partial (parity exists; per-method async tests ❌ Wave 0) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_timescale.py -x -q -o addopts=""`
- **Per wave merge:** `uv run pytest tests/test_timescale.py tests/test_parity.py -o addopts=""`
- **Phase gate:** `uv run pytest` (full suite green, coverage ≥94%) before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] Extend `tests/test_timescale.py` with mock SQL-shape classes for create / refresh / policy
      (sync + async) — covers TS-ADV-01/02/03 authoritatively.
- [ ] Add live-tolerant integration tests (`try/except FeatureNotSupported`) reusing `_make_hypertable`,
      `ts_db` / `async_ts_db` fixtures (all already present in test_timescale.py).
- [ ] No new fixtures, no new test file, no `conftest.py` change — Phase-30 scaffold suffices.
- [ ] No framework install needed (pytest + pytest-asyncio already configured).

---

## Project Constraints (from CLAUDE.md)

- **Independent PyPI lib** — no Solaris/MarketStream/Kala deps; **zero new deps** for this phase
  (D-07 explicitly; the offset comparator uses stdlib `re` only).
- **Independent venv** — run everything via `uv run` (`uv sync --all-extras --dev` first if
  `pyproject.toml` changes; it will not here).
- **Quality gates** — `uv run ruff check pycopg tests`; `uv run black pycopg tests`; numpydoc
  docstrings (interrogate ≥95 at release); coverage ratchet ≥94%.
- **Targeted runs** use `-o addopts=""` to bypass the coverage gate (per project memory); 2 named
  DB tests are pre-existing-flaky and unrelated to this phase.

---

## Sources

### Primary (HIGH confidence — live DB / catalog / code)
- Live `psql -h localhost -U postgres -d pycopg_test` on TSDB **2.28.0**, `license=apache`:
  cagg create/refresh/policy `0A000 FeatureNotSupported`; `pg_proc` signatures for
  `refresh_continuous_aggregate` + `add_continuous_aggregate_policy`;
  `timescaledb_information.{continuous_aggregates,jobs}` columns.
- `uv run python` + psycopg 3: `FeatureNotSupported`/`sqlstate=0A000` mapping; async
  `set_autocommit` post-open `ProgrammingError`; `connect(autocommit=True)` works.
- Codebase: `etl.py:787-817` (seam), `timescale.py` (policy + async guard audit, all 10 sites),
  `utils.py` (`validate_interval`, `_INTERVAL_PATTERN`), `database.py:374-396` /
  `async_database.py:371-395` (connect seam), `test_parity.py:24-32`, `test_timescale.py` fixtures
  + reorder mock/live precedents.

### Secondary (MEDIUM-HIGH — official docs)
- TimescaleDB / TigerData docs — create-a-continuous-aggregate (WITH NO DATA in txn block;
  `WITH (timescaledb.continuous)`); `refresh_continuous_aggregate()` API (two-transaction
  restriction, 2.28 batching).
- TimescaleDB issue #2876 (cagg refresh cannot run in a transaction block; autocommit workaround).

### Tertiary (MEDIUM — verified against the live `0A000` finding)
- TimescaleDB licensing (TSL vs Apache): continuous aggregates / compression / tiered storage are
  TSL/Community-only, not available under Apache — corroborates the live `0A000` on all 3 methods.

Sources:
- [TimescaleDB issue #2876 — Allow cagg refresh within transaction block](https://github.com/timescale/timescaledb/issues/2876)
- [refresh_continuous_aggregate() — TigerData docs](https://docs.timescale.com/api/latest/continuous-aggregates/refresh_continuous_aggregate/)
- [Create a continuous aggregate — TigerData docs](https://www.tigerdata.com/docs/use-timescale/latest/continuous-aggregates/create-a-continuous-aggregate)
- [supabase discussion #19475 — continuous aggregates not supported under apache license](https://github.com/orgs/supabase/discussions/19475)
- [Timescale License (TSL) — TigerData legal](https://www.tigerdata.com/legal/licenses)

## Metadata

**Confidence breakdown:**
- Method SQL surfaces (create/refresh/policy signatures, options): **HIGH** — live catalog + parse + docs.
- License gating of all 3 methods: **HIGH** — live `0A000` on each, corroborated by TSL docs.
- Autocommit seam (sync + async-connect-time): **HIGH** — live psycopg behavior + existing precedent.
- D-07 comparator unit set: **HIGH** — live regex + `validate_interval` acceptance check.
- DB error wording for offset-ordering (`22023`): **MEDIUM** — `UNVERIFIABLE-LIVE` (license gate
  fires first); from TSDB behavior, not blocking since D-07 guards in Python pre-DB.

**Research date:** 2026-06-23
**Valid until:** ~2026-07-23 (stable; TSDB 2.x cagg surface + license model are settled)

---

## RESEARCH COMPLETE

**Phase:** 31 - Continuous Aggregate Lifecycle
**Confidence:** HIGH

### Key Findings
- **Contradiction with D-09 (headline):** continuous aggregates are TSL/Community-only; the
  local/CI build is **Apache 2.28.0**, so **create + refresh + policy ALL raise
  `FeatureNotSupported` (0A000)** live — not just the policy. D-09's "create+refresh assert real
  materialization" plan is unachievable on this build → all 3 methods become mock-authoritative +
  live-tolerant; isolation proven structurally.
- Autocommit seam **verified**: async `autocommit` must be set at `connect()` time
  (`set_autocommit` post-open raises `ProgrammingError`); the pycopg `connect(autocommit=True)`
  seam + ETL `etl.py:787-817` shape are the correct verbatim precedent.
- Exact 2.28 signatures captured from `pg_proc`: `refresh_continuous_aggregate(regclass, "any",
  "any", force, options)` (a procedure → `CALL`, returns nothing; `NULL,NULL`=full refresh);
  `add_continuous_aggregate_policy(regclass, start_offset, end_offset, schedule_interval,
  if_not_exists, ...)` — names/order match D-08.
- D-05 confirmed: refresh windows are absolute timestamps → reject `str` (do **not** copy the
  Phase-30 `drop_chunks` interval cast). D-07 comparator: same-unit integer compare over
  `second|minute|hour|day|week`; defer `month|year`/mixed to DB; zero new deps.
- Info-view columns captured for test assertions; **no `queries.py` constant needed** (inline,
  per Phase-30 precedent).

### File Created
`.planning/phases/31-continuous-aggregate-lifecycle/31-RESEARCH.md`

### Confidence Assessment
| Area | Level | Reason |
|------|-------|--------|
| Standard Stack / SQL surfaces | HIGH | live `pg_proc` + parse + official docs |
| Architecture (autocommit seam) | HIGH | live psycopg behavior + existing ETL precedent |
| Pitfalls (license gate, async await) | HIGH | live `0A000` on all 3 + code audit of 10 async guards |

### Open Questions
- D-09/D-10 need a one-line user/planner ack: cagg create+refresh are license-gated like policy →
  test strategy shifts to mock-authoritative + structural isolation proof (API surface unchanged).
- `None`-offset → render SQL `NULL` (planner to make per-offset branch explicit).

### Ready for Planning
Research complete. Planner can create PLAN.md files; the only judgement call is acknowledging the
D-09/D-10 license-gating correction (Contradiction #1).
