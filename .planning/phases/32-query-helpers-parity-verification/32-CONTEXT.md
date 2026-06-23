# Phase 32: Query Helpers & Parity Verification - Context

**Gathered:** 2026-06-23
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the **two TimescaleDB query helpers** as new methods on **both**
`db.timescale.*` (sync) and `async_db.timescale.*` (async), then **confirm full
TS-ADV-10 sync/async parity across all 9 new v0.8.0 methods**:

- `time_bucket(table, time_column, bucket_width, aggregates, where=None, schema="public", into="df")`
  → bucketed aggregation; returns a `DataFrame` (`into="df"`, default) or `list[dict]`
  (`into="rows"`); `into="gdf"` raises `ValueError`. Result DataFrame has a deterministic
  `bucket` column.
- `time_bucket_gapfill(table, time_column, bucket_width, start, finish, aggregates, where=None, schema="public", into="df")`
  → gap-filled bucketed aggregation; `start`/`finish` are **required** absolute bounds (no
  WHERE-inference); returns gap-filled rows including NULL-padded buckets as `DataFrame`/`list[dict]`.

These are **query helpers** (read-only `SELECT`, `into="df"/"rows"` routing — the spatial
accessor precedent), **NOT DDL** and **NOT the autocommit seam**. They use the established
pure-builder + `validate_identifiers` + `%s`-params + lazy-accessor + sync/async-parity contract.

**In scope:**
- The 2 new methods (sync + async) with `into="df"/"rows"` routing.
- Module-level pure SQL builders + local routing helpers in `timescale.py`.
- Mock SQL-shape unit tests + **real** live integration tests (gapfill is Apache-licensed —
  unlike Phase-31 caggs — so live tests assert real gap-filled output, no license `try/except`).
- **TS-ADV-10 confirmation:** all 9 new methods mirrored, enforced by the existing
  `test_accessor_parity` over the registered `(TimescaleAccessor, AsyncTimescaleAccessor)` pair,
  plus one explicit 9-method-name set assertion; coverage ratchet ≥94% holds.

**Out of scope (other phases / deferred):**
- Docs/CHANGELOG/version bump/release gates → **Phase 33** (REL-08).
- `into="query"` (raw-SQL escape hatch) → deferred (matches spatial's deferral to a later ETL milestone).
- Any new autocommit-seam code — the helpers are plain `execute`/`to_dataframe` (the autocommit
  branches that criterion #3 mentions are **inherited Phase-31 wording**; create/refresh already
  covered at 95.05%, Phase 32 adds none).
- WHERE-inference of the gapfill range from a `where=` predicate → structurally rejected;
  `start`/`finish` are required explicit args (TS-ADV-07).
</domain>

<decisions>
## Implementation Decisions

### `into=` routing, output shape & WHERE
- **D-01 [bucket column — builder-injected]:** The pure builder always renders the bucket
  expression with a fixed `AS bucket` alias (e.g. `time_bucket(%s, <time_col>) AS bucket`), so
  the output column is deterministically named `bucket` regardless of caller (satisfies ROADMAP
  criterion #1). The caller supplies only `bucket_width` (bound as `%s`) and `aggregates`
  (structural SQL); they do **not** write the `time_bucket(...)` expression themselves.
- **D-02 [`into="df"` execution path — reuse the spatial named-bind adapter]:** `to_dataframe`
  wraps SQL in SQLAlchemy `text()` and binds a **dict** (`pd.read_sql(text(sql), engine,
  params=params)`, `database.py:935` / `async_database.py`), so psycopg `%s` placeholders will
  **not** bind directly. For `into="df"`, convert `%s` → `:p0,:p1,…` via a local `_to_named_binds`
  (identical to `spatial._to_named_binds`) and call `self._db.to_dataframe(sql=named, params=binds)`.
  For `into="rows"`, call `self._db.execute(sql, params)` with the positional `%s` list directly.
  **This resolves the milestone open question** ("confirm `to_dataframe` `%s`-vs-named-bind path").
- **D-03 [`into=` guard — timescale-local valid set, `df` default]:** Valid set is
  `("df", "rows")`; default `into="df"`. A local `_check_into`-style guard raises `ValueError`
  **before any SQL runs** if `into` is not in the set — which is exactly how `into="gdf"` gets
  rejected (criterion #1). **Note for planner:** do NOT import `spatial._check_into` — spatial's
  `_VALID_INTO` is `("rows", "gdf")`, the opposite of what these helpers need. Use a timescale-local
  valid set.
- **D-04 [`where=` — optional structural-SQL `%s` fragment]:** `where` (default `None`) is an
  optional structural SQL fragment string; when provided, render `WHERE <where>` (sync) — documented
  as structural SQL (not from untrusted input), same posture as `aggregates`. For
  `time_bucket_gapfill`, the time-range WHERE (`start`/`finish` as `%s`) is **always** present; an
  extra `where` **ANDs** onto it. Matches the REQ signatures (both list `where=None`).

### Builder / file structure (self-contained `timescale.py`)
- **D-05 [module-level pure builders]:** Add `_build_time_bucket_sql(...)` and
  `_build_time_bucket_gapfill_sql(...)` as **module-level functions** in `timescale.py`, each
  returning `(sql, params)`. Both sync and async accessor methods call the same builder — mirrors
  spatial.py's module-level builder pattern, keeps the sync/async method bodies thin and identical,
  and makes the SQL shape unit-testable in isolation.
- **D-06 [local routing helpers — no cross-accessor import]:** Add **local copies** in
  `timescale.py`: `_to_named_binds` (identical logic to spatial's), a timescale `_check_into`
  (valid set `df`/`rows`), and `_run` / async `_run` dispatchers. Rationale: avoid a
  `timescale → spatial` dependency on private helpers, and `_check_into` can't be shared anyway
  (different valid set). `_to_named_binds` is tiny; each accessor stays self-contained. (Promoting
  to `utils.py` was considered but rejected — it would touch `spatial.py`, outside this phase's
  file scope.)
- **D-07 [async parity — mirror spatial async `_run`, audit the `await`s]:** The async accessor gets
  its own `_run` that does `await self._db.to_dataframe(sql=named, params=binds)` for `df` and
  `await self._db.execute(sql, params)` for `rows` — an exact mirror of spatial's async
  `SpatialAccessor._run` (~`spatial.py:1945`). **Audit the `await` on the per-method extension guard**
  (`await self._db.schema.has_extension("timescaledb")`) — the recurring Phase-23/30/31 missing-`await`
  gotcha.

### `time_bucket_gapfill` validation & binding
- **D-08 [license — Apache-licensed, REAL live assertions; NOT the Phase-31 pattern]:** Unlike
  Phase-31 continuous aggregates (TSL/Community-only → `FeatureNotSupported` on the local 2.28.0
  Apache build), `time_bucket`, `time_bucket_gapfill`, `locf()` and `interpolate()` are in the
  **Apache 2 (free) edition** and run for real on the local/CI build. **Live tests assert real
  behavior** (bucketed/gap-filled output, NULL-padded buckets present, `bucket` column, aggregate
  values) — they are **NOT** wrapped in `try/except FeatureNotSupported`. This is the v0.6.0
  spatial-style two-layer pattern (mock SQL-shape + real live), **not** the Phase-31 license-tolerant
  pattern. Planner/researcher should still live-verify gapfill isn't gated on the local build, but
  default to real assertions.
- **D-09 [minimal pre-flight guards — honest about limits]:** Validate identifiers
  (`table`, `time_column`, `schema`) and enforce `start`/`finish` as required (the signature does
  this). Bind `bucket_width`/`start`/`finish`/`where`-params as `%s`. Do **NOT** add semantic guards:
  no Python `start < finish` check, no heuristic requiring `locf(`/`interpolate(` in `aggregates`
  (gapfill is valid without `locf` — it still NULL-pads). Let the DB raise on bad usage. Matches the
  D-07 "honest-about-limits" philosophy from Phase 31.
- **D-10 [gapfill binds `start`/`finish` in TWO places]:** `time_bucket_gapfill` requires an explicit
  bounded time range or it errors. Render `start`/`finish` as `%s` in **both** the
  `time_bucket_gapfill(%s, <time_col>, %s, %s)` call args **and** the `WHERE <time_col> >= %s AND
  <time_col> < %s` range — passing the `start`/`finish` values **twice** in the params list
  (`bucket_width` + 4 datetime binds, plus any `where`-fragment params). This is the structurally
  correct gapfill pattern: the `%s` placeholders work fine in the WHERE; only the gapfill-arg planner
  *inference* from a WHERE predicate is broken (hence required explicit args, TS-ADV-07). **Planner
  must live-verify** the exact template (named gapfill args vs positional; WHERE bound inclusivity
  `>=`/`<`) against TSDB 2.x + the local DB.

### TS-ADV-10 parity proof & coverage
- **D-11 [parity proof = existing test + explicit 9-name set]:** Rely on the existing parametrized
  `test_accessor_parity` (`tests/test_parity.py:35`) — it already does a symmetric set-difference
  over all public members of the registered `(TimescaleAccessor, AsyncTimescaleAccessor)` pair, so it
  auto-covers all 9 methods **both directions** with **no registry change**. **Add ONE explicit
  assertion** that the timescale pair exposes the expected 9 new method names (a named set), so a
  silently-dropped/renamed method fails loudly and the TS-ADV-10 surface is documented. Do **not**
  add per-method signature-level parity (a new pattern beyond this phase's scope).
- **D-12 [coverage — Phase-32 lines + ratchet ≥94%; no new autocommit branches]:** Phase 32 only
  needs its own new lines covered (both helpers, both `into=` branches, the `gdf` `ValueError`,
  `where` present/absent, the gapfill double-bind) by mock + live tests, and the global ratchet to
  stay ≥94% (baseline 95.05% after Phase 31). The criterion-#3 "all new autocommit branches covered"
  clause is **inherited milestone wording** from Phase-31's create/refresh seam (already covered);
  **Phase 32 adds no autocommit code** — the planner should not hunt for nonexistent new autocommit
  branches.

### Claude's Discretion
- Exact module-level builder names (`_build_time_bucket_sql` etc.) and whether `_run`/async `_run`
  take a `geometry_column`-style extra arg or a leaner signature (no geometry here).
- Exact `ValueError` / docstring wording for the `into=` guard (D-03) and the gapfill required-args.
- Whether a `queries.py` SQL constant is warranted (the helpers build dynamic SQL with validated
  identifiers + `%s`; likely inlined in the builders rather than a constant — planner's call).
- The precise gapfill SQL template details flagged in D-10 (named vs positional gapfill args, WHERE
  bound inclusivity) — to be live-verified by researcher/planner against TSDB 2.x.
- Exact column naming for aggregate outputs beyond the fixed `bucket` alias (caller supplies
  `aggregates` with their own aliases).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope
- `.planning/REQUIREMENTS.md` — **TS-ADV-06** (`time_bucket` verbatim signature: `bucket_width`/`where`
  as `%s`, identifiers validated, `aggregates` = structural SQL, `into="df"` default returning
  `DataFrame`/`list[dict]`), **TS-ADV-07** (`time_bucket_gapfill`: `start`/`finish` **required** explicit
  args — `%s` WHERE-inference structurally broken; `locf()`/`interpolate()` supplied inside `aggregates`),
  **TS-ADV-10** (full 9-method parity via `ACCESSOR_PAIRS`, async guard `await`ed).
- `.planning/ROADMAP.md` §"Phase 32: Query Helpers & Parity Verification" — goal + 3 success criteria
  (`into="df"`→DataFrame with `bucket` column / `into="rows"`→`list[dict]` / `into="gdf"`→`ValueError`;
  gapfill with Python `datetime` bound params returning NULL-padded buckets, `start`+`finish` required;
  `test_accessor_parity` over all 9 methods + ratchet ≥94%).

### Research (project-level, HIGH confidence, already done — commit 618a968)
- `.planning/research/SUMMARY.md` — 9 method signatures verified vs TSDB 2.x; §"Critical Pitfalls"
  (gapfill needs explicit non-optional `start`/`finish`, `%s` WHERE-inference broken; async guard must
  be `await`ed).
- `.planning/research/PITFALLS.md` — gapfill `start`/`finish` requirement + async `await` guard.
- `.planning/research/FEATURES.md`, `.planning/research/STACK.md`, `.planning/research/ARCHITECTURE.md`.

### Prior phase context (directly relevant)
- `.planning/phases/31-continuous-aggregate-lifecycle/31-CONTEXT.md` — D-09/D-10 (Apache-license
  `FeatureNotSupported` test pattern — explicitly **NOT** applicable to gapfill per this phase's D-08;
  caggs are TSL-only, gapfill is free); `tests/test_timescale.py` `ts_db`/`async_ts_db` skip-fixtures;
  the pure-builder + parity contract.
- `.planning/phases/30-chunk-management-partitioning/30-CONTEXT.md` — `TimescaleError` in
  `exceptions.py`; `tests/test_timescale.py` + skip-fixtures created here.

### Codebase patterns to mirror
- `pycopg/spatial.py:970-993` — `_check_into` (the `into=` validation pattern; timescale needs a
  **different valid set** `df`/`rows`).
- `pycopg/spatial.py:995-1021` — `_to_named_binds` (`%s`→`:pN` adapter — copy locally per D-06).
- `pycopg/spatial.py:1051-1077` — sync `SpatialAccessor._run` (the `into=` dispatcher to mirror).
- `pycopg/spatial.py:~1945-1965` — async `SpatialAccessor._run` (awaited `into=` dispatch — D-07).
- `pycopg/database.py:899-935` / `pycopg/async_database.py:731+` — `to_dataframe(sql=, params=dict)`
  via `pd.read_sql(text(sql), engine, params=params)` — the named-bind `df` path (D-02).
- `pycopg/timescale.py:152` (`TimescaleAccessor`) / `:972` (`AsyncTimescaleAccessor`) — where the 2
  new methods land; per-method `has_extension("timescaledb")` guard pattern.
- `pycopg/utils.py` — `validate_identifier`/`validate_identifiers` (78/107), `validate_interval` (125).
- `tests/test_parity.py:24` `ACCESSOR_PAIRS` (timescale pair already registered) + `:35`
  `test_accessor_parity` (symmetric set-diff — auto-covers all 9 methods, **no registry change**; D-11).
- `tests/test_timescale.py` — extend with mock SQL-shape + **real** live tests (D-08); `ts_db` /
  `async_ts_db` skip-fixtures.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`_to_named_binds` (`spatial.py:995`):** the `%s`→`:pN` + dict adapter the `into="df"` path needs;
  copy locally into `timescale.py` (D-06).
- **`SpatialAccessor._run` sync/async (`spatial.py:1051`, `~1945`):** the exact `into=` dispatch
  shape to mirror — `gdf`/`df` via `to_(geo)dataframe(named, binds)`, `rows` via `execute`.
- **`to_dataframe(sql=, params=dict)` (`database.py:899` / `async_database.py:731`):** the DataFrame
  sink; takes a **dict** of named binds (SQLAlchemy `text()`), confirming D-02's named-bind requirement.
- **`validate_identifiers` / `validate_interval` (`utils.py`):** identifier + interval syntax validation
  for `table`/`time_column`/`schema` and `bucket_width`.
- **`ts_db` / `async_ts_db` skip-fixtures (`tests/test_timescale.py`):** create-extension-or-skip,
  ready to host the 2 new helpers' **real** live tests.
- **`ACCESSOR_PAIRS` + `test_accessor_parity`:** timescale pair registered — adding the 2 methods to
  both classes auto-satisfies bidirectional parity; D-11 adds the explicit 9-name assertion.

### Established Patterns
- **Pure-builder + lazy-accessor:** module-level builder returns `(sql, params)`; identifiers validated
  and interpolated, runtime values bound as `%s`; sync + async methods share the builder (D-05).
- **`into=` routing accessor (spatial):** validate `into=` before SQL, dispatch on it; `df`/`gdf`
  path uses named binds + `to_(geo)dataframe`, `rows` path uses positional `execute`.
- **Per-method extension guard:** `has_extension("timescaledb")` raising `ExtensionNotAvailable`
  (sync) / **`await`ed** (async — recurring missing-`await` gotcha, D-07).

### Integration Points
- New code is confined to **`pycopg/timescale.py`** (2 methods × 2 classes + module-level builders +
  local routing helpers) and **`tests/test_timescale.py`** (+ possibly a 9-name assertion in
  `tests/test_parity.py`). No `queries.py` constant expected (planner's call). `exceptions.py`
  unchanged (`TimescaleError` already exists). `ACCESSOR_PAIRS` unchanged.
- `db.timescale` / `async_db.timescale` lazy accessors already wired (v0.6.0) — methods just appear.
</code_context>

<specifics>
## Specific Ideas

- The `bucket` column is a **contract** (ROADMAP criterion #1) — the builder owns the `AS bucket`
  alias so callers can't accidentally break the promised DataFrame shape (D-01).
- Gapfill is **not** Phase-31's caggs: it's Apache-free, so live tests must assert **real**
  NULL-padded gap-fill output, not hide behind a `FeatureNotSupported` `try/except` (D-08). This is the
  single most important framing difference from the prior phase — don't copy Phase-31's test pattern.
- The gapfill `start`/`finish` are bound **twice** (gapfill args + WHERE range), and they are
  **`datetime` bound params**, not literals (ROADMAP criterion #2) — the test must pass Python
  `datetime` objects (D-10).
- `into=` validation is **timescale-local** (`df`/`rows`), the inverse of spatial's (`rows`/`gdf`) —
  do not import spatial's `_check_into` (D-03).

</specifics>

<deferred>
## Deferred Ideas

- **`into="query"`** (return the built SQL/params instead of executing) → deferred, mirrors spatial's
  deferral to a later ETL milestone. Not requested; noted to mark the boundary.
- **Semantic gapfill guards** (Python `start < finish`, `locf`-presence heuristic) → intentionally
  **not** added (D-09); the DB is the authority. Listed to record the deliberate omission.
- **Per-method signature-level parity** (param names/defaults match across sync/async) → deferred
  (D-11); the project has not done signature-level parity and it's beyond Phase 32 scope.
- **Promoting `_to_named_binds` to `utils.py`** for cross-accessor reuse → deferred (D-06); it would
  touch `spatial.py`, outside this phase's file scope. A future cleanup if a 3rd accessor needs it.
- **Docs / CHANGELOG / version bump / release gates** → **Phase 33** (REL-08), the next and final
  v0.8.0 phase.

None of these arose as scope-creep requests — listed only to mark the boundary explicitly.

</deferred>

---

*Phase: 32-Query Helpers & Parity Verification*
*Context gathered: 2026-06-23*
