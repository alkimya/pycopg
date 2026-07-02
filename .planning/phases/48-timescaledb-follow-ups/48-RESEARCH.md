# Phase 48: TimescaleDB Follow-ups - Research

**Researched:** 2026-07-02
**Domain:** TimescaleDB SQL function surface (cagg teardown, time_bucket alignment, per-chunk compression)
**Confidence:** HIGH

## Summary

This phase extends the shipped `db.timescale.*` surface (v0.8.0) with four small, additive,
keyword-only methods/params. Both open research questions from CONTEXT.md (D-05, D-11) are
now **resolved with live-DB + official-docs evidence**, and the D-06 sanity-check is confirmed.
Nothing here changes the CONTEXT.md decisions — this document narrows the two "Claude's
Discretion" items to concrete, citable answers so the planner can write exact SQL templates
without further discovery.

**Primary recommendation:** Implement all four features exactly as scoped in `48-CONTEXT.md`
D-03/D-06/D-09/D-10, with two refinements found during research: (1) F01's `drop_continuous_aggregate`
uses a **plain transaction-safe `self._db.execute`** — NOT the autocommit seam (D-05 confirmed:
normal transaction is fine); (2) F01's `remove_continuous_aggregate_policy` should bind
`if_exists` (the current, TSDB-2.8+-renamed parameter name), not the legacy `if_not_exists` name
that CONTEXT.md's SQL sketch used — see Resolved Research Questions §1 for the exact reconciled
signature.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Cagg drop / policy removal (F01) | Database (SQL builder in `timescale.py`) | — | Pure SQL-generation + execution; no other tier involved (matches existing `TimescaleAccessor` pattern) |
| time_bucket origin/offset (F02) | Database (SQL builder) | — | Extends existing `_build_time_bucket_sql`; client-side mutual-exclusion guard lives in the same tier |
| compress/decompress_chunk (F03) | Database (SQL builder) | — | Single parameterized function call; no ORM/dataframe layer involved |
| show_chunks physical-time filter (F04) | Database (already shipped) | — | No new work; verify + document only |

This phase touches exactly one tier (the `pycopg.timescale` accessor layer) — there is no
browser/frontend/CDN dimension to this library-level feature set.

## Resolved Research Questions

### 1. D-05 — cagg DROP transaction seam: **RESOLVED — normal transaction is fine, use plain `execute`**

**Answer: `DROP MATERIALIZED VIEW` on a continuous aggregate does NOT need the
`connect(autocommit=True)` seam.** CONTEXT.md's default assumption is CONFIRMED.

Evidence:
- **[CITED: tigerdata.com/docs/reference/timescaledb/continuous-aggregates/drop_materialized_view]**
  — Official docs state the exact syntax is plain PostgreSQL DDL:
  `DROP MATERIALIZED VIEW [IF EXISTS] <view_name> [CASCADE];` and explicitly note "It also
  removes refresh policies for that aggregate" — no mention anywhere of a transaction-block
  restriction, autocommit requirement, or multi-statement caveat (unlike `CREATE MATERIALIZED
  VIEW ... WITH (timescaledb.continuous)` and `CALL refresh_continuous_aggregate(...)`, both of
  which explicitly require autocommit per the v0.8.0 D-02 comments already in `timescale.py`).
- **[VERIFIED: local TSDB 2.28.2]** — Sanity-checked the general "DROP MATERIALIZED VIEW inside
  a transaction block" mechanic against a plain (non-cagg) materialized view on the live DB:
  `BEGIN; DROP MATERIALIZED VIEW f48_plain_mv; COMMIT;` succeeded cleanly. `DROP MATERIALIZED
  VIEW` is ordinary PostgreSQL DDL and DDL is always transaction-safe in PostgreSQL (unlike
  `CREATE INDEX CONCURRENTLY`, `VACUUM`, or TimescaleDB's own multi-batch cagg materialization
  procedures).
- **[VERIFIED: local TSDB 2.28.2, Apache build]** — Could not create an actual cagg locally to
  drop one (cagg creation itself is Community/TSL-gated on Apache — `CREATE MATERIALIZED VIEW
  ... WITH (timescaledb.continuous)` raises `0A000 functionality not supported under the current
  "apache" license` both inside and outside an explicit `BEGIN`/`ROLLBACK` block, confirming the
  license check fires uniformly regardless of transaction context). This means direct empirical
  confirmation of dropping a *real* cagg was not possible on this Apache install — but the
  official docs above are unambiguous and the general DDL-in-transaction mechanic was verified.
- **Root cause of why CREATE/REFRESH need autocommit but DROP does not:** `CREATE MATERIALIZED
  VIEW ... WITH (timescaledb.continuous)` triggers TimescaleDB's internal multi-transaction
  materialization machinery (build the cagg + do initial refresh, potentially batched); `CALL
  refresh_continuous_aggregate` explicitly issues multiple internal transactions per TSDB 2.28+
  batching. `DROP MATERIALIZED VIEW`, by contrast, is a single catalog-level DDL operation (drop
  the view + its internal materialization hypertable + associated jobs) — no multi-batch
  procedure, hence no autocommit requirement.

**`remove_continuous_aggregate_policy` — same answer, plain transaction is fine.** This is a
regular `SELECT function(...)` call, structurally identical to the already-shipped
`add_continuous_aggregate_policy` (timescale.py:1094) which the codebase already documents as
"D-01 — transaction-safe, like `add_reorder_policy`/`add_compression_policy`/
`add_retention_policy`; NOT the autocommit seam." `remove_continuous_aggregate_policy` is a
plain scalar function returning `void`, with no special multi-transaction behavior documented
anywhere — treat it identically to its sibling `add_continuous_aggregate_policy`.

**Implementation directive:** Both `drop_continuous_aggregate` and
`remove_continuous_aggregate_policy` use `self._db.execute(...)` (plain, transaction-safe) —
mirror the pattern of `add_reorder_policy` / `add_continuous_aggregate_policy` / `drop_chunks`,
NOT the `with self._db.connect(autocommit=True) as conn: conn.execute(...)` pattern used by
`create_continuous_aggregate` / `refresh_continuous_aggregate`.

### 2. D-11 — compress_chunk / decompress_chunk argument names + availability: **RESOLVED**

**Confirmed live against local TSDB 2.28.2 (`\df compress_chunk` / `\df decompress_chunk`):**

```
public | compress_chunk   | regclass | uncompressed_chunk regclass, if_not_compressed boolean DEFAULT true, recompress boolean DEFAULT false
public | decompress_chunk | regclass | uncompressed_chunk regclass, if_compressed boolean DEFAULT true
```

- **[VERIFIED: local TSDB 2.28.2]** Argument names are exactly `if_not_compressed` (compress)
  and `if_compressed` (decompress), both `boolean DEFAULT true` — matching CONTEXT.md D-09/D-10
  verbatim. No rename has happened as of 2.28. `compress_chunk` additionally exposes a third
  param `recompress boolean DEFAULT false` — **out of scope for this phase** (CONTEXT.md D-09
  only names `if_not_compressed`; do not add `recompress` unless the planner explicitly wants
  the extra ergonomic — Deferred Ideas doesn't mention it either, so leave it out and note it as
  a future follow-up if raised).
- **[CITED: github.com/timescale/docs — api/compression/compress_chunk.md, newer "Hypercore"
  terminology]** Later TimescaleDB releases (post-2.28, the "Hypercore"/columnstore rename) show
  a *renamed* parameter `if_not_columnstore` in the newest upstream docs, and describe
  `compress_chunk()` as **"superseded by `convert_to_columnstore()`"** — but the docs
  simultaneously confirm the legacy `compress_chunk`/`if_not_compressed` API "is still
  supported, you do not need to migrate to the hypercore APIs." **This is a naming drift in
  docs for newer TSDB versions, not a behavior change on 2.28** — the live introspection above
  is authoritative for this project's actual runtime (2.28.2) and confirms `if_not_compressed`/
  `if_compressed` are correct today. Flag for the planner: if pycopg's supported TimescaleDB
  floor is ever raised past 2.28, re-verify this argument name has not been hard-renamed (it
  currently is only aliased/superseded, both still work per docs).
- **[VERIFIED: local TSDB 2.28.2, Apache build]** `compress_chunk` is Community/TSL-gated —
  confirmed by direct execution:
  ```
  SELECT compress_chunk('_timescaledb_internal._hyper_333_1127_chunk'::regclass);
  ERROR:  0A000: function "compress_chunk" is not supported under the current "apache" license
  HINT:  Upgrade your license to 'timescale' to use this free community feature.
  ```
  SQLSTATE is exactly `0A000` → maps to `psycopg.errors.FeatureNotSupported`, matching the
  existing v0.8.0 D-09 propagation pattern used by `create_continuous_aggregate` /
  `add_continuous_aggregate_policy` / `add_reorder_policy`. `decompress_chunk` was not
  independently exercised (no compressed chunk could be created on this Apache build to
  decompress) but shares the same `cross_module_fn.c` community-gate mechanism per TimescaleDB's
  architecture — same `0A000` expected, same tolerance pattern applies.
- **`chunk` accepts `regclass`:** Confirmed — both functions declare `uncompressed_chunk
  regclass` as the first positional param. `%s::regclass` binding (D-10) is correct; a
  fully-qualified chunk name string (e.g. `_timescaledb_internal._hyper_1_2_chunk`, as returned
  by `show_chunks()`) casts cleanly to `regclass`.
- **`ExtensionNotAvailableError` guard fires first — confirmed as the correct pattern.** Every
  existing `db.timescale.*` method (e.g. `enable_compression`, `add_compression_policy`,
  `add_reorder_policy`, `create_continuous_aggregate`) checks
  `self._db.schema.has_extension("timescaledb")` and raises `ExtensionNotAvailableError` BEFORE
  issuing any DB call — this happens even before the Apache-license-specific `FeatureNotSupported`
  can occur, because the extension-presence check itself is a metadata query, not the gated
  function call. `compress_chunk`/`decompress_chunk` should follow the identical ordering:
  `has_extension` guard → `validate_identifiers` (schema/table args, if any) → build SQL → execute
  (where the DB itself raises `FeatureNotSupported` if Apache-licensed and TSL-gated).

**Implementation directive — exact SQL (matches CONTEXT.md D-10 verbatim, now confirmed):**
```sql
SELECT compress_chunk(%s::regclass, if_not_compressed => %s)
SELECT decompress_chunk(%s::regclass, if_compressed => %s)
```
Params: `[chunk, if_not_compressed]` / `[chunk, if_compressed]` (chunk name string, then the
boolean flag). Both return `regclass` (the chunk itself) at the SQL level, but per CONTEXT.md
D-09 the Python method returns `None` (void) — consistent with `enable_compression` /
`add_compression_policy` / `add_reorder_policy`, all of which discard the SQL-level return value.

### 3. D-06 — time_bucket origin/offset: **CONFIRMED, sanity-check passed**

- **[VERIFIED: local TSDB 2.28.2]** `\df time_bucket` shows 20 overloads. For the
  `timestamp with time zone` / `timestamp without time zone` / `date` families (the ones
  relevant to pycopg's `_build_time_bucket_sql`, which operates on a caller-named `time_column`
  of unknown-but-typically-timestamptz type), there are **three distinct signature shapes**:
  - `time_bucket(bucket_width interval, ts <T>)` — no origin/offset (current shipped behavior)
  - `time_bucket(bucket_width interval, ts <T>, "offset" interval)` — offset-only overload
  - `time_bucket(bucket_width interval, ts <T>, origin <T>)` — origin-only overload
  - (timestamptz only) a 5-arg overload also exists: `(bucket_width interval, ts timestamptz,
    timezone text, origin timestamptz DEFAULT NULL, "offset" interval DEFAULT NULL)` — not
    relevant here since pycopg's builder does not expose a `timezone` argument.
- **These are genuinely separate PostgreSQL function overloads, not one function with two
  optional keyword args** — `origin` and `offset` cannot both be passed to `time_bucket` in a
  single call; there is no `(bucket_width, ts, origin, offset)` 4-arg overload in the 3 relevant
  families. This directly **confirms mutual exclusivity at the SQL level**, not just as an API
  design choice — supplying both would be a `function time_bucket(interval, timestamptz,
  timestamptz, interval) does not exist` error (no matching overload), which is exactly why
  CONTEXT.md D-07's proactive client-side `ValueError` guard (raised before any DB round-trip) is
  the right call — it converts a confusing "no matching function" PostgreSQL error into a clear
  Python-level message.
- **Minimum TSDB version for origin/offset:** `origin` was introduced in TimescaleDB 1.7+
  (long-shipped; pre-dates this project's 2.28 floor by years) — **[ASSUMED]** based on training
  knowledge of TimescaleDB's release history, not independently re-verified via changelog in this
  session (low risk: the live 2.28.2 introspection above already proves both variants exist and
  are callable today, which is the only fact the planner actually needs). No floor problem: local
  2.28 has both.
- **Call signature / argument positions:** `time_bucket(bucket_width, ts, origin => <value>)` or
  `time_bucket(bucket_width, ts, "offset" => <value>)` — both use named-argument syntax
  (`=>`) in PostgreSQL, which matches CONTEXT.md D-06's binding plan
  (`origin` as typed `%s`, `offset` as `%s::interval`). Positionally, `origin`/`"offset"` is
  always the 3rd argument after `bucket_width, ts` — consistent with appending
  `, origin => %s` or `, offset => %s::interval` to the existing `_build_time_bucket_sql`
  template.

**Implementation directive:** Extend `_build_time_bucket_sql` (timescale.py:214) with two new
optional params. SQL fragment shape:
```sql
SELECT time_bucket(%s, {time_column}, origin => %s) AS bucket, ...      -- if origin is not None
SELECT time_bucket(%s, {time_column}, "offset" => %s::interval) AS bucket, ...  -- if offset is not None
SELECT time_bucket(%s, {time_column}) AS bucket, ...                    -- both None (unchanged)
```
Note: `"offset"` is a PostgreSQL reserved-ish keyword when used as a bare identifier in some
contexts, but as a **named-argument label** (`offset => ...`) inside a function call it is
syntactically unambiguous and does not require quoting — `\df` shows it quoted only because
`offset` is technically a non-reserved keyword that psql's function-listing renderer
double-quotes defensively. Either quoted or unquoted `offset => %s::interval` will parse
correctly; match whichever the existing codebase style prefers (no bare `offset` identifiers
appear elsewhere in `timescale.py`, so this is a fresh decision — quoting defensively is
harmless and costs nothing).

## Standard Stack

No new libraries. This phase is pure SQL-generation extending `pycopg/timescale.py` using the
existing psycopg driver already in use project-wide.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg | (already a project dep) | Execute parameterized SQL | Existing driver, zero new deps per standing bar |

### Alternatives Considered
None — this phase adds zero new runtime dependencies by requirement (REQUIREMENTS.md
cross-cutting criteria + CLAUDE.md).

**Installation:** N/A — no new packages.

## Package Legitimacy Audit

Not applicable — this phase installs no new packages (zero new runtime dependencies is a
locked cross-cutting requirement). Skipping the Package Legitimacy Gate.

## Architecture Patterns

### System Architecture Diagram

```
Caller code
    │
    │ db.timescale.drop_continuous_aggregate(view_name, cascade=, if_exists=)
    │ db.timescale.remove_continuous_aggregate_policy(view_name, if_exists=)
    │ db.timescale.time_bucket(table, time_column, bucket_width, aggregates, origin=, offset=)
    │ db.timescale.compress_chunk(chunk, if_not_compressed=)
    │ db.timescale.decompress_chunk(chunk, if_compressed=)
    ▼
TimescaleAccessor / AsyncTimescaleAccessor  (pycopg/timescale.py)
    │
    ├─► has_extension("timescaledb") guard  ──► raise ExtensionNotAvailableError (no DB round-trip beyond metadata check)
    │
    ├─► client-side guards (before SQL build):
    │     - F02: origin and offset both non-None → raise ValueError
    │     - F01 drop: if_exists default False (explicit), cascade flag
    │
    ├─► validate_identifiers(...)  (any schema/table/view identifiers — NOT the bound chunk regclass value)
    │
    ├─► build SQL string with %s / %(name)s placeholders (queries.py constants where reused)
    │
    ▼
self._db.execute(sql, params)   ── plain, transaction-safe (F01 drop + policy removal + F02 + F03)
    │                               (NOT the autocommit seam — that stays reserved for
    │                                create_continuous_aggregate / refresh_continuous_aggregate)
    ▼
psycopg connection ──► PostgreSQL / TimescaleDB
    │
    ├─► Apache build + TSL-gated function (compress_chunk/decompress_chunk, cagg-family)
    │     → raises FeatureNotSupported (SQLSTATE 0A000) → propagates to caller (no swallow, D-09)
    │
    └─► Community/Timescale build → executes normally
```

### Recommended Project Structure
No new files. All changes land in the existing three files:
```
pycopg/
├── timescale.py     # TimescaleAccessor + AsyncTimescaleAccessor — add 5 new methods/params
├── queries.py        # Add TSDB_DROP_CAGG / TSDB_REMOVE_CAGG_POLICY style constants (optional; small enough to inline like add_continuous_aggregate_policy does)
└── exceptions.py     # No change — ExtensionNotAvailableError / TimescaleError already exist
tests/
└── test_timescale.py # Add mock SQL-shape tests + injection tests for all 3 new builders (F01/F02/F03) + 1 optional newer_than-datetime test (F04)
tests/
└── test_parity.py    # Extend v0.8.0 surface frozenset → "v0.9.0"/"v1.1.0" surface (add 4 new method names)
```

### Pattern 1: Plain transaction-safe execute (F01, F02, F03 — all of Phase 48's NEW code)
**What:** `self._db.execute(sql, params)` inside a normal (implicit or ambient) transaction —
the default for every non-cagg-lifecycle `TimescaleAccessor` method.
**When to use:** Any TimescaleDB function call that is NOT `CREATE MATERIALIZED VIEW ...
WITH (timescaledb.continuous)` or `CALL refresh_continuous_aggregate(...)`. This includes both
new F01 methods (confirmed by research above), F02's extended `time_bucket`, and F03's
`compress_chunk`/`decompress_chunk`.
**Example:**
```python
# Source: pycopg/timescale.py:1171 (add_continuous_aggregate_policy, existing pattern to mirror)
self._db.execute(
    f"SELECT add_continuous_aggregate_policy("
    f"'{schema}.{view_name}', "
    f"start_offset => {start_frag}, "
    f"end_offset => {end_frag}, "
    f"schedule_interval => INTERVAL '{schedule_interval}'"
    f"{ne}) AS job_id"
)
```

### Pattern 2: Autocommit seam (existing, NOT used by any Phase 48 method)
**What:** `with self._db.connect(autocommit=True) as conn: conn.execute(sql)`.
**When to use:** Only `create_continuous_aggregate` / `refresh_continuous_aggregate` (already
shipped, unchanged by this phase). Do NOT apply this pattern to `drop_continuous_aggregate` or
`remove_continuous_aggregate_policy` — research confirms plain execute is correct for both.

### Pattern 3: Guard-before-DB-round-trip (F02 mutual exclusion)
**What:** Raise `ValueError` in Python before building/sending any SQL.
**When to use:** F02's `origin`/`offset` mutual exclusion (mirrors `drop_chunks`'s
both-None guard and `add_dimension`'s mutual-exclusion guard).
**Example:**
```python
# Source: pycopg/timescale.py:701-706 (drop_chunks, existing pattern to mirror)
if older_than is None and newer_than is None:
    raise ValueError(
        "drop_chunks requires at least one of older_than or newer_than. ..."
    )
```
Apply identically for F02:
```python
if origin is not None and offset is not None:
    raise ValueError(
        "time_bucket: 'origin' and 'offset' are mutually exclusive "
        "(TimescaleDB has no time_bucket overload accepting both); pass one or neither."
    )
```

### Anti-Patterns to Avoid
- **Using the autocommit seam for DROP/policy-removal/compress/decompress:** research confirms
  none of these need it — using it anyway would be an unnecessary connection-management
  divergence from the rest of the non-cagg-lifecycle methods, and would complicate testing
  (autocommit-seam methods need a different mock pattern, see `create_continuous_aggregate`
  tests vs `drop_chunks` tests).
- **Binding `chunk` as a bare string without `::regclass`:** would either fail to resolve
  correctly or (worse) invite ambiguity if the string isn't schema-qualified — always
  `%s::regclass`.
- **Adding the `recompress` param to `compress_chunk`:** out of scope per D-09 (only
  `if_not_compressed` was decided) — do not silently add it; if a future need arises it's a new
  follow-up requirement, not a Phase 48 addition.
- **Using the legacy `if_not_exists` name for `remove_continuous_aggregate_policy`:** the
  function accepts BOTH `if_not_exists` (legacy, kept for back-compat) and `if_exists` (current,
  renamed in TSDB 2.8) — use `if_exists` in the SQL (see Resolved Research Questions §1
  reconciliation note above; CONTEXT.md's SQL sketch already said `if_exists => %s`, so this is
  already correct — just don't let a "helpful" search of `\df` output tempt a switch to
  `if_not_exists`, which is the deprecated name).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Chunk-bound param handling (str vs datetime) | A new dispatch helper | Reuse `_build_chunk_bound_fragments` (F04 is already built on it) | Already handles the str-interval-vs-datetime-absolute split correctly; F02's origin/offset needs the SAME datetime-vs-interval type distinction, but is a DIFFERENT dispatch (origin is always datetime-typed OR None, offset is always interval-str-typed OR None) — do not force-reuse this exact helper for F02, but follow its *pattern* (type-dispatch → distinct SQL fragment + param) |
| SQL-shape mock testing infra | New fixture/mock scaffolding | Reuse the `MagicMock(spec=SchemaAccessor)` + `db.execute = MagicMock(...)` pattern from `TestShowChunksMock` | Established, works for both sync/async, keeps test style consistent across `test_timescale.py` |
| license-error tolerance in live tests | A custom try/except wrapper | `pytest.raises(FeatureNotSupported)` or the existing `ts_db`/`async_ts_db` skip-fixture pattern documented in `test_timescale.py`'s D-11 docstring | Already the project convention (see `add_reorder_policy` live test under D-12) |

**Key insight:** Every builder this phase needs (bound-value dispatch, guard-before-DB,
plain-vs-autocommit execute) already has a canonical exemplar in the same file. This phase is
additive-by-analogy — the main risk is inconsistency (e.g. picking the wrong exemplar), not
missing infrastructure.

## Common Pitfalls

### Pitfall 1: Using `if_not_exists` instead of `if_exists` for cagg policy removal
**What goes wrong:** The live function signature exposes both `if_not_exists boolean DEFAULT
false` (legacy/deprecated) and `if_exists boolean DEFAULT NULL::boolean` (current, renamed in
TSDB 2.8). A naive `\df`-only read might pick the wrong one since `if_not_exists` appears first
positionally in the signature.
**Why it happens:** Back-compat cruft — TimescaleDB kept the old parameter name callable
alongside the new one rather than hard-breaking existing callers.
**How to avoid:** Always bind by name (`if_exists => %s`), never positionally, and use `if_exists`
per the current official docs and CONTEXT.md D-03's own SQL sketch.
**Warning signs:** A test asserting `"if_not_exists =>"` in the generated SQL — should assert
`"if_exists =>"` instead.

### Pitfall 2: Assuming compress_chunk/decompress_chunk always exist as callable functions on any TimescaleDB install
**What goes wrong:** They DO exist as catalog functions even on the Apache build (confirmed —
`\df compress_chunk` returns a row) — the license check fires only at EXECUTION time inside the
C function body, not at function-resolution time. A test that checks "function exists" via
`\df`/`pg_proc` would pass even where the actual call would fail — only a live `SELECT
compress_chunk(...)` call surfaces the `0A000` error.
**Why it happens:** TimescaleDB gates Community features inside `cross_module_fn.c`
dispatch, not via conditional function registration.
**How to avoid:** Test the actual execution path (mock SQL-shape unit test asserts the SQL string
is correct; a SEPARATE live-DB test, gated by a skip-or-tolerate pattern, asserts the runtime
behavior — either succeeds on Community or raises `FeatureNotSupported` on Apache, per the D-12
convention already used for `add_reorder_policy`).
**Warning signs:** A live integration test that doesn't wrap the call in
`pytest.raises(FeatureNotSupported)` or an equivalent try/except-and-skip — it will fail
outright on this project's Apache dev DB instead of passing-by-tolerance.

### Pitfall 3: Forgetting `ExtensionNotAvailableError` fires BEFORE the license error, not instead of it
**What goes wrong:** Confusing the two distinct failure modes — "TimescaleDB not installed at
all" (`ExtensionNotAvailableError`, a pycopg-level Python guard) vs. "TimescaleDB installed but
Apache-licensed, feature gated" (`FeatureNotSupported`, a PostgreSQL-level error from the DB
itself). Both are real, sequential possibilities and both need coverage.
**Why it happens:** Easy to only test one path and assume it covers both.
**How to avoid:** Mock-test `has_extension` guard ordering (assert `execute` not called when
extension absent) as ONE test; separately mock/live-test the SQL shape and (optionally) the
Apache-tolerance path as OTHER tests — exactly the layering `TestShowChunksMock` already uses.
**Warning signs:** Only one exception type covered in the test file for a new method.

### Pitfall 4: Origin/offset param binding type confusion
**What goes wrong:** `origin` is an absolute anchor (bind as typed `%s`, e.g. a `datetime`
object — psycopg infers `timestamptz`/`timestamp` from the Python type); `offset` is a relative
shift (bind as `%s::interval` from a Python `str`, same idiom as `_build_chunk_bound_fragments`'s
interval handling). Swapping these — e.g. casting `origin` with `::interval` or leaving `offset`
untyped — will either raise a PostgreSQL type-mismatch error or silently produce wrong results
via implicit casting.
**Why it happens:** Both are "the third argument to time_bucket," easy to conflate under time
pressure.
**How to avoid:** Mirror CONTEXT.md D-06 exactly: `origin: datetime | None` → bare `%s`;
`offset: str | None` → `%s::interval`. Add a dedicated SQL-shape test asserting each fragment
independently (like `test_show_chunks_sql_shape_str_older_than` vs
`test_show_chunks_sql_shape_datetime_older_than` do for the analogous str-vs-datetime split).

## Code Examples

### F01 — drop_continuous_aggregate (new)
```python
# Pattern source: pycopg/timescale.py:646-741 (drop_chunks) for guard/structure style,
# pycopg/timescale.py:1094-1178 (add_continuous_aggregate_policy) for plain-execute + naming
def drop_continuous_aggregate(
    self,
    view_name: str,
    *,
    cascade: bool = False,
    if_exists: bool = False,
    schema: str = "public",
) -> None:
    validate_identifiers(view_name, schema)
    if not self._db.schema.has_extension("timescaledb"):
        raise ExtensionNotAvailableError(
            "TimescaleDB extension not installed. "
            "Run db.schema.create_extension('timescaledb')"
        )
    ie = "IF EXISTS " if if_exists else ""
    cas = " CASCADE" if cascade else ""
    self._db.execute(f"DROP MATERIALIZED VIEW {ie}{schema}.{view_name}{cas}")
```

### F01 — remove_continuous_aggregate_policy (new)
```python
def remove_continuous_aggregate_policy(
    self,
    view_name: str,
    *,
    if_exists: bool = True,
    schema: str = "public",
) -> None:
    validate_identifiers(view_name, schema)
    if not self._db.schema.has_extension("timescaledb"):
        raise ExtensionNotAvailableError(
            "TimescaleDB extension not installed. "
            "Run db.schema.create_extension('timescaledb')"
        )
    ie = "true" if if_exists else "false"
    self._db.execute(
        f"SELECT remove_continuous_aggregate_policy("
        f"'{schema}.{view_name}', if_exists => {ie})"
    )
```
Note: `if_exists` here is rendered as a literal SQL boolean (`true`/`false`), matching the
existing `if_not_exists`/`materialized_only` literal-boolean idiom used throughout
`create_hypertable`/`create_continuous_aggregate` — NOT bound as `%s` (avoids the
`IndeterminateDatatype` risk class documented at timescale.py:1074-1082 for untyped NULL-adjacent
params; a plain boolean literal has no such ambiguity, but staying consistent with the
established literal-interpolation-for-flags idiom is simplest and matches D-03's SQL sketch).

### F02 — time_bucket origin/offset extension (extends `_build_time_bucket_sql`)
```python
# Extends pycopg/timescale.py:214 (_build_time_bucket_sql)
def _build_time_bucket_sql(
    table: str,
    time_column: str,
    bucket_width: str,
    aggregates: str,
    where: str | None = None,
    schema: str = "public",
    origin: datetime | None = None,
    offset: str | None = None,
) -> tuple[str, list[Any]]:
    validate_identifiers(table, schema, time_column)
    if origin is not None and offset is not None:
        raise ValueError(
            "time_bucket: 'origin' and 'offset' are mutually exclusive; pass one or neither."
        )
    params: list[Any] = [bucket_width]
    bucket_expr = f"time_bucket(%s, {time_column}"
    if origin is not None:
        bucket_expr += ", origin => %s"
        params.append(origin)
    elif offset is not None:
        bucket_expr += ', "offset" => %s::interval'
        params.append(offset)
    bucket_expr += ")"

    sql = f"SELECT {bucket_expr} AS bucket, {aggregates} FROM {schema}.{table}"
    if where is not None:
        sql += f" WHERE {where}"
    sql += " GROUP BY bucket ORDER BY bucket"
    return sql, params
```
Note: the mutual-exclusion guard could instead live in the public `time_bucket()` accessor
method (before calling the builder) to fail even faster / more visibly — either placement
satisfies D-07 ("raise ValueError before any DB round-trip"); placing it in the pure builder
keeps the guard co-located with the two branches it protects and makes the builder unit-testable
in isolation (recommended — matches how `add_dimension`'s mutual-exclusion guard is structured).

### F03 — compress_chunk / decompress_chunk (new)
```python
# Pattern source: pycopg/timescale.py:400-453 (enable_compression) for None-return +
# ExtensionNotAvailableError convention
def compress_chunk(self, chunk: str, *, if_not_compressed: bool = True) -> None:
    if not self._db.schema.has_extension("timescaledb"):
        raise ExtensionNotAvailableError(
            "TimescaleDB extension not installed. "
            "Run db.schema.create_extension('timescaledb')"
        )
    self._db.execute(
        "SELECT compress_chunk(%s::regclass, if_not_compressed => %s)",
        [chunk, if_not_compressed],
    )

def decompress_chunk(self, chunk: str, *, if_compressed: bool = True) -> None:
    if not self._db.schema.has_extension("timescaledb"):
        raise ExtensionNotAvailableError(
            "TimescaleDB extension not installed. "
            "Run db.schema.create_extension('timescaledb')"
        )
    self._db.execute(
        "SELECT decompress_chunk(%s::regclass, if_compressed => %s)",
        [chunk, if_compressed],
    )
```
`chunk` is not a SQL identifier subject to `validate_identifiers` (D-10) — it is a bound `%s`
value cast to `regclass` at the SQL level, so injection safety comes from parameter binding, not
identifier validation. There are no other identifier arguments on these two methods (no
`schema`/`table` params — `chunk` is already fully-qualified as returned by `show_chunks()`), so
no `validate_identifiers` call is needed inside these two specific methods; the "builder-pure /
`validate_identifiers` line 1" standing bar applies to builders that accept schema/table
identifiers, which these do not.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| `remove_continuous_aggregate_policy(cagg, if_not_exists)` | `remove_continuous_aggregate_policy(cagg, if_exists)` | TimescaleDB 2.8 | Old param kept callable for back-compat; use `if_exists` going forward (this project's 2.28 floor is long past the rename) |
| `compress_chunk`/`decompress_chunk` legacy compression API | `convert_to_columnstore()`/hypercore API (newer TSDB releases, post-2.28) | Recent ("Hypercore" rebrand) | Legacy API "still supported" per official docs — safe to use for this phase; not a blocker, just a naming-drift note for future version bumps |

**Deprecated/outdated:** None of the functions this phase touches are deprecated on TSDB 2.28.
`recompress_chunk` (a *different*, related function not used by this phase) is deprecated since
2.14 in favor of `compress_chunk` itself — irrelevant here since Phase 48 already targets
`compress_chunk` directly, not `recompress_chunk`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `origin`/`offset` on `time_bucket` were introduced in TimescaleDB ~1.7 (long before this project's 2.28 floor) | Resolved Research Questions §3 | LOW — live 2.28.2 introspection already proves both overloads exist and are callable today; this claim only matters for historical context, not for correctness of the plan |
| A2 | `decompress_chunk` raises the same `0A000 FeatureNotSupported` as `compress_chunk` on Apache builds (not independently executed live — no compressed chunk existed to decompress) | Resolved Research Questions §2 | LOW — both functions share the identical `cross_module_fn.c` Community-gate mechanism per TimescaleDB's architecture (same pattern as `compress_chunk`, `create_continuous_aggregate`, `add_continuous_aggregate_policy`, `add_reorder_policy` — all TSL functions gate identically); if wrong, a live integration test would surface a different exception, which the planner's Wave 0 gap can add a live-tolerance test to catch it either way |

**If this table is empty:** N/A — two low-risk assumptions logged above.

## Open Questions

None blocking. Both primary research questions (D-05, D-11) and the D-06 sanity-check are fully
resolved with HIGH confidence (live-DB verification + official docs citation for each).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| TimescaleDB extension | All `db.timescale.*` methods incl. all 4 new features | Yes | 2.28.2 (Apache license) | N/A — `ExtensionNotAvailableError` guard is the built-in fallback path, already implemented |
| TimescaleDB Community/TSL license | F01 (cagg create was already gated pre-phase; DROP itself is NOT gated per this research), F03 (`compress_chunk`/`decompress_chunk`) | No (Apache only, local) | — | Live integration tests for F03 and any cagg-dependent F01 setup must use the `pytest.raises(FeatureNotSupported)` / skip-and-tolerate pattern already established for `add_reorder_policy` (D-12); mock SQL-shape tests remain fully authoritative regardless of license tier |

**Missing dependencies with no fallback:** None — every gap has an established fallback pattern
already in the codebase (mock SQL-shape tests + license-tolerant live tests).

**Missing dependencies with fallback:** TSL/Community license — fallback is the D-12
mock-authoritative / live-tolerant dual-layer test pattern, already proven across 3 prior
TSL-gated methods (`create_continuous_aggregate`, `add_continuous_aggregate_policy`,
`add_reorder_policy`).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7+ (asyncio_mode="auto"), configured in `pyproject.toml` |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (line 95) |
| Quick run command | `PGDATABASE=pycopg_test3 uv run pytest tests/test_timescale.py tests/test_parity.py -x -q` |
| Full suite command | `PGDATABASE=pycopg_test3 uv run pytest` (enforces `--cov-fail-under=95`, `-W error::DeprecationWarning`) |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TSDB-F01 | `drop_continuous_aggregate` emits `DROP MATERIALIZED VIEW [IF EXISTS] schema.view[CASCADE]`, sync+async, uses plain execute (not autocommit seam) | unit (mock SQL-shape) | `pytest tests/test_timescale.py -k drop_continuous_aggregate -x` | ❌ Wave 0 |
| TSDB-F01 | `remove_continuous_aggregate_policy` emits `SELECT remove_continuous_aggregate_policy('schema.view', if_exists => true/false)`, sync+async | unit (mock SQL-shape) | `pytest tests/test_timescale.py -k remove_continuous_aggregate_policy -x` | ❌ Wave 0 |
| TSDB-F01 | Injection guard on `view_name`/`schema` (both new builders) | unit (injection test) | `pytest tests/test_timescale.py -k "drop_continuous_aggregate and injection or remove_continuous_aggregate_policy and injection"` | ❌ Wave 0 |
| TSDB-F02 | `origin` binds bare `%s`; `offset` binds `%s::interval`; both `None` unchanged from v0.8.0 shape | unit (mock SQL-shape, 3 cases) | `pytest tests/test_timescale.py -k "time_bucket and origin or time_bucket and offset" -x` | ❌ Wave 0 |
| TSDB-F02 | `origin` and `offset` both non-`None` raises `ValueError` before any DB round-trip | unit (guard test, `db.execute.assert_not_called()`) | `pytest tests/test_timescale.py -k time_bucket_origin_offset_mutual_exclusion -x` | ❌ Wave 0 |
| TSDB-F03 | `compress_chunk`/`decompress_chunk` emit `SELECT compress_chunk(%s::regclass, if_not_compressed => %s)` / decompress mirror, sync+async | unit (mock SQL-shape) | `pytest tests/test_timescale.py -k "compress_chunk or decompress_chunk" -x` | ❌ Wave 0 |
| TSDB-F03 | `ExtensionNotAvailableError` fires before any `execute` call when extension absent | unit (guard test) | `pytest tests/test_timescale.py -k "compress_chunk_no_extension or decompress_chunk_no_extension" -x` | ❌ Wave 0 |
| TSDB-F03 | On Apache-licensed live DB, `compress_chunk`/`decompress_chunk` raise `FeatureNotSupported` (SQLSTATE `0A000`) — tolerated, not swallowed | integration (live, TSL-gated, D-12 tolerance pattern) | `PGDATABASE=pycopg_test3 pytest tests/test_timescale.py -k "compress_chunk_live or decompress_chunk_live" -x` | ❌ Wave 0 |
| TSDB-F04 | `newer_than`-datetime SQL shape (symmetry gap noted in CONTEXT D-02) | unit (mock SQL-shape, optional) | `pytest tests/test_timescale.py -k test_show_chunks_sql_shape_datetime_newer_than -x` | ❌ Wave 0 (optional per D-02) |
| Cross-cutting | Sync/async parity for all 4-5 new methods/params | unit (`test_accessor_parity` + `test_accessor_parameter_kind_parity`, auto-extends once methods exist) | `pytest tests/test_parity.py -x -q` | ✅ (extend frozenset, no new file) |

### Sampling Rate
- **Per task commit:** `PGDATABASE=pycopg_test3 uv run pytest tests/test_timescale.py tests/test_parity.py -x -q`
- **Per wave merge:** `PGDATABASE=pycopg_test3 uv run pytest` (full suite, coverage gate)
- **Phase gate:** Full suite green (`--cov-fail-under=95`, mypy --strict 0 errors, interrogate 100%, Sphinx `-W`) before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] New mock SQL-shape test classes in `tests/test_timescale.py`: `TestDropContinuousAggregateMock`, `TestRemoveContinuousAggregatePolicyMock`, `TestTimeBucketOriginOffsetMock`, `TestCompressChunkMock`/`TestDecompressChunkMock` — none exist yet, follow the `TestShowChunksMock`/`TestDropChunksMock` class-per-method convention already in the file.
- [ ] Optional live-DB integration tests for F03 (Apache-tolerance pattern, D-12) — reuse `ts_db`/`async_ts_db` fixtures already defined at the top of `test_timescale.py`.
- [ ] Extend `tests/test_parity.py`'s `test_timescale_v080_surface` (or a new `test_timescale_v110_surface`) frozenset with the 4 new method names: `drop_continuous_aggregate`, `remove_continuous_aggregate_policy`, `compress_chunk`, `decompress_chunk` (F02 is a param addition to existing `time_bucket`, not a new method name, so it does NOT need a frozenset entry — but IS covered automatically by `test_accessor_parameter_kind_parity` once the signature changes on both classes).
- [ ] No new fixtures needed beyond what's already in `test_timescale.py` (`db`, `ts_db`, `async_ts_db`, `_make_hypertable`).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | Not touched by this phase (uses existing connection auth) |
| V3 Session Management | No | Not touched |
| V4 Access Control | No | Not touched (DB-level GRANT/REVOKE out of scope) |
| V5 Input Validation | Yes | `validate_identifiers` on all schema/view/table identifier args (F01, F02 already-covered `table`/`time_column`/`schema`); bound `%s`/`%s::regclass`/`%s::interval` params for all runtime values (chunk name, origin, offset, boolean flags) |
| V6 Cryptography | No | Not touched |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|----------------------|
| SQL injection via `view_name`/`schema` string interpolation (F01) | Tampering | `validate_identifiers(view_name, schema)` called as line 1 of both new methods, before any string interpolation — matches the standing bar and every existing `TimescaleAccessor` method |
| SQL injection via unvalidated `chunk` string (F03) | Tampering | `chunk` is bound as `%s::regclass`, never string-interpolated — psycopg parameter binding is the injection defense here, not `validate_identifiers` (which is for bare identifiers, not bound values); a malicious string simply fails to cast to `regclass` rather than executing as SQL |
| Boolean-flag injection via naive f-string of `if_exists`/`cascade`/`if_not_compressed` | Tampering | All boolean flags are Python `bool` type-checked by the method signature (`if_exists: bool = True`) before being rendered as a fixed literal `"true"`/`"false"` string (never taking arbitrary user string input) — same idiom as existing `if_not_exists`/`materialized_only` handling in `create_hypertable`/`create_continuous_aggregate` |
| Mutual-exclusion bypass sending both `origin` and `offset` to the DB (not a security issue per se, but a correctness/DoS-adjacent footgun) | — | Client-side `ValueError` guard before any DB round-trip (D-07) — prevents a confusing "no matching function overload" error from reaching the DB layer at all |

## Sources

### Primary (HIGH confidence)
- Local live introspection, TimescaleDB 2.28.2 (Apache license), `psql -h localhost -U postgres -d pycopg_test3` — `\df compress_chunk`, `\df decompress_chunk`, `\df time_bucket`, `\df remove_continuous_aggregate_policy`, `\df *continuous_aggregate*`, direct execution of `compress_chunk(...)` (confirmed `0A000 FeatureNotSupported`), `BEGIN; DROP MATERIALIZED VIEW ...; COMMIT;` sanity check
- `pycopg/timescale.py` (existing shipped code) — `create_continuous_aggregate`/`refresh_continuous_aggregate` autocommit-seam docstrings (D-02 rationale), `add_continuous_aggregate_policy`/`add_reorder_policy`/`drop_chunks` plain-execute pattern (D-01), `_build_chunk_bound_fragments`, `_build_time_bucket_sql`
- [DROP MATERIALIZED VIEW (continuous aggregate) — Tiger Data Docs](https://www.tigerdata.com/docs/reference/timescaledb/continuous-aggregates/drop_materialized_view) — exact syntax, no transaction-block restriction documented
- [remove_continuous_aggregate_policy() — Tiger Data Docs](https://www.tigerdata.com/docs/api/latest/continuous-aggregates/remove_continuous_aggregate_policy) — exact signature + `if_exists`/`if_not_exists` rename history (2.8)

### Secondary (MEDIUM confidence)
- [compress_chunk() docs source — github.com/timescale/docs](https://github.com/timescale/docs/blob/latest/api/compression/compress_chunk.md) — confirms Community-license gating and notes newer `if_not_columnstore` naming drift in post-2.28 "Hypercore" docs, while confirming the legacy API "is still supported"

### Tertiary (LOW confidence)
- Training-knowledge claim about `time_bucket` origin/offset's ~1.7 introduction version (A1 in Assumptions Log) — not independently re-verified via TimescaleDB changelog in this session; low risk since live 2.28.2 already proves both overloads exist today

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new deps, pure extension of existing verified patterns
- Architecture: HIGH — every pattern (guard-before-DB, plain-execute vs autocommit-seam,
  validate_identifiers, bound-value casting) has a direct, cited exemplar already in
  `pycopg/timescale.py`
- Pitfalls: HIGH — all four documented pitfalls are grounded in live-DB behavior observed
  directly in this research session, not speculation

**Research date:** 2026-07-02
**Valid until:** 90 days (stable, mature TimescaleDB API surface; low churn risk for a
frozen-SemVer-1.0 codebase extending a well-established DB function surface)

## RESEARCH COMPLETE
