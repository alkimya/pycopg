# Phase 30: Chunk Management & Partitioning - Research

**Researched:** 2026-06-22
**Domain:** TimescaleDB 2.28.0 chunk/partition management via psycopg 3 pure-builder accessors (pycopg v0.8.0)
**Confidence:** HIGH (all SQL shapes live-verified against local TSDB 2.28.0)

## Summary

This phase adds four management methods to both `TimescaleAccessor` and `AsyncTimescaleAccessor`.
The CONTEXT is complete (11 locked decisions); this research resolves the one deferred question
(D-05 chunk ordering) **definitively against the live DB** and live-verifies every candidate SQL
string. It also surfaces **two environment-driven facts that contradict CONTEXT/PITFALLS premises**
and must reshape the plan:

1. **D-08 is unverifiable as written.** On TSDB 2.28, `add_dimension(table, by_hash(...))` /
   `by_range(...)` **succeed on a non-empty hypertable** — the modern builder form does NOT raise the
   "has existing data" error that the legacy positional form raised. There is no error to catch and
   re-raise as `TimescaleError` for the non-empty case. The catchable, reliable error is
   **"column ... is already a dimension"** (duplicate dimension, SQLSTATE `TS160`).
2. **`add_reorder_policy` (TS-ADV-09) cannot run on the local/CI DB.** It is a TimescaleDB
   Community-License feature; the local build is `timescaledb.license = apache`, which rejects it
   (and `add_retention_policy`/`add_compression_policy`) with `FeatureNotSupported` (SQLSTATE
   `0A000`). The live integration test must tolerate `FeatureNotSupported` exactly as the existing
   v0.6.0 policy test does; the mock SQL-shape unit test is the real SQL assertion.

**Primary recommendation:** For `show_chunks`/`drop_chunks`, use the **native `show_chunks()` SRF
JOINed to `timescaledb_information.chunks`, ordered by `range_start ASC`** — this gives native
filter semantics, D-04 fully-qualified unquoted names, and D-05 oldest-first ordering in one query.
`drop_chunks` must **capture the ordered preview list BEFORE dropping** (the info-view rows vanish
post-drop), unifying the `dry_run` and real paths.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| show_chunks / drop_chunks SQL build | API / pycopg accessor | Database / TSDB | Pure builder; SRF+info-view join executed by DB |
| chunk ordering (range_start ASC) | Database / TSDB | — | `ORDER BY` pushed to SQL, not Python — DB owns range metadata |
| dry_run preview | API / pycopg accessor | — | Builder reuses show_chunks query; no extra DB concept |
| add_dimension by_hash/by_range | Database / TSDB | API / pycopg accessor | Builder validates+interpolates; TSDB performs DDL |
| mutual-exclusivity / both-None guards | API / pycopg accessor | — | Construction-time `ValueError` before any round-trip |
| add_reorder_policy | Database / TSDB (Community license) | API / pycopg accessor | Job registration is a licensed server feature |

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TS-ADV-04 | `show_chunks(table, older_than, newer_than, schema)` -> list[str] fully-qualified, oldest-first | SRF+info-view JOIN ordered by `range_start ASC`; live-verified SQL below |
| TS-ADV-05 | `drop_chunks(..., dry_run)` -> list[str]; ValueError both-None; DESTRUCTIVE | Capture-before-drop pattern; `dry_run` shares show_chunks builder; live-verified return shape |
| TS-ADV-08 | `add_dimension` by_hash/by_range + mutual-exclusivity ValueError + clear error | by_hash/by_range live-verified on 2.28; **D-08 reshaped — see Finding 1** |
| TS-ADV-09 | `add_reorder_policy(table, index_name, schema, if_not_exists)` + job row | Signature live-verified; **live test must tolerate FeatureNotSupported — see Finding 2** |
</phase_requirements>

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (verbatim summary — see 30-CONTEXT.md for full text)
- **D-01:** `older_than`/`newer_than` accept `str | datetime | None`; str = relative interval, datetime = absolute cutoff.
- **D-02:** Builder branches on Python type: `str` -> `%s::interval`; `datetime` -> bare `%s`; `None` -> omit arg entirely. Each non-None bound = exactly one `%s` + cast.
- **D-03:** `drop_chunks` raises `ValueError` when both bounds None (before DB round-trip). `dry_run=True` previews without deleting. Docstring marks DESTRUCTIVE/IRREVERSIBLE.
- **D-04:** Both methods return `list[str]` of fully-qualified chunk names (`_timescaledb_internal._hyper_N_M_chunk`), copy-paste usable. `drop_chunks` (incl. dry_run) returns identical shape to `show_chunks`.
- **D-05:** List sorted oldest-first by `range_start ASC`, NOT native order, NOT lexicographic. **[RESOLVED — see "D-05 Resolution" below]**
- **D-06:** Local/CI TSDB is **2.28.0** (re-verified this session) -> use modern `by_hash`/`by_range`. No pre-2.13 fallback.
- **D-07:** Construction-time `ValueError` for hash<->`number_partitions` / range<->`chunk_interval` mutual exclusivity, before any DB round-trip.
- **D-08:** On non-empty hypertable, `add_dimension` surfaces a clear pycopg-domain error via attempt-DDL-catch-reraise as `TimescaleError`. **[CONTRADICTED BY LIVE DB — see Finding 1]**
- **D-09:** Add `class TimescaleError(PycopgError)` to `exceptions.py` (milestone-wide, reused Phases 31-32). Phase 30 touches a third file.
- **D-10:** New `tests/test_timescale.py`; port the `ts_db` skip-fixture from `TestDatabaseTimescaleCoverage`.
- **D-11:** Two test layers: mock SQL-shape unit tests (no live DB) + live-DB integration tests (ts_db skip-gated). `asyncio_mode = "auto"` already set.

### Claude's Discretion
- `queries.py` constant names (SUMMARY suggested `TSDB_SHOW_CHUNKS`/`TSDB_DROP_CHUNKS`); whether dry_run re-invokes `show_chunks` vs shared internal builder — planner's call as long as D-04/D-05 hold.
- `TimescaleError` message wording for the (now repurposed) error case.
- Whether `add_dimension`/`add_reorder_policy` apply `validate_interval` on `chunk_interval`.

### Deferred Ideas (OUT OF SCOPE)
- `show_chunks` `created_before`/`created_after` physical-time filters (TSDB-F04).
- Per-chunk `compress_chunk`/`decompress_chunk` (TSDB-F03).
- Continuous aggregates (Phase 31); `time_bucket`/`gapfill` helpers (Phase 32).
</user_constraints>

## Project Constraints (from CLAUDE.md)

- pycopg is an independent PyPI lib — **no Solaris/MarketStream/Kala deps**.
- **Zero new dependencies** this milestone — everything via existing psycopg 3 + pure SQL.
- Own venv at `pycopg/venv`; dev via `uv sync --all-extras --dev`; tests via `uv run pytest`.
- Lint `uv run ruff check pycopg tests`; format `uv run black pycopg tests`.
- numpydoc docstrings; coverage ratchet gate (see Validation Architecture).

## D-05 Resolution (PRIMARY OPEN QUESTION — RESOLVED, HIGH confidence)

**Mechanism: native `show_chunks()` SRF JOINed to `timescaledb_information.chunks`, ordered by
`range_start ASC`.** This was the deferred question; it is now resolved with live output.

### Why not the bare SRF alone

The bare `show_chunks()` SRF returns a `regclass` column. Its **native row order is NOT guaranteed
to be range-ascending** (it matched insertion order in this test only by coincidence), and casting to
text + sorting lexicographically is provably wrong [VERIFIED: live DB]:

```
-- ORDER BY show_chunks::text  (WRONG — lexicographic):
_timescaledb_internal._hyper_270_10_chunk   <- _10 sorts before _1
_timescaledb_internal._hyper_270_11_chunk
_timescaledb_internal._hyper_270_12_chunk
_timescaledb_internal._hyper_270_1_chunk
...
```

The SRF gives no range column to ORDER BY. The info view (`timescaledb_information.chunks`) carries
`range_start`, `range_end`, `chunk_schema`, `chunk_name`.

### Recommended SHOW_CHUNKS SQL (live-verified)

JOIN the SRF (for native filter semantics) to the info view (for `range_start` + name parts).
The SRF column is `regclass`; build a matching `regclass` from the info view via
`format('%I.%I', chunk_schema, chunk_name)::regclass`. **The join key is `regclass = regclass`**
(both sides cast to regclass — do NOT compare regclass to text, that errors `operator does not exist: regclass = text`).

```sql
-- TSDB_SHOW_CHUNKS (table/schema interpolated after validate_identifiers;
-- bounds appended conditionally per D-02)
SELECT c.chunk_schema || '.' || c.chunk_name AS chunk_name
FROM show_chunks('{schema}.{table}'{older_arg}{newer_arg}) AS sc
JOIN timescaledb_information.chunks c
  ON format('%I.%I', c.chunk_schema, c.chunk_name)::regclass = sc
ORDER BY c.range_start ASC
```

Where the conditional arg fragments per D-02 are:
- str `older_than`  -> `, older_than => %s::interval`
- datetime `older_than` -> `, older_than => %s`
- str `newer_than`  -> `, newer_than => %s::interval`
- datetime `newer_than` -> `, newer_than => %s`
- None bound -> emit nothing (omit arg AND its `%s`).

Params list is built in the same conditional order (older first if present, then newer).

**Live output (both-None, 12-chunk hypertable) — correct oldest-first, fully-qualified, unquoted:**
```
_timescaledb_internal._hyper_270_1_chunk
_timescaledb_internal._hyper_270_2_chunk
...
_timescaledb_internal._hyper_270_9_chunk
_timescaledb_internal._hyper_270_10_chunk     <- _10 correctly AFTER _9 (range order, not lexical)
_timescaledb_internal._hyper_270_11_chunk
_timescaledb_internal._hyper_270_12_chunk
```

### regclass -> text rendering (D-04)

Use `chunk_schema || '.' || chunk_name` from the info view. This yields the **unquoted**
`_timescaledb_internal._hyper_N_M_chunk` form — **exactly matching the CONTEXT example** and
copy-paste usable. No `quote_ident`/`%I` quoting is needed on the OUTPUT (TSDB-internal identifiers
are already valid bare identifiers). `%I` is used only on the JOIN key for the regclass cast.
[VERIFIED: live DB]

### Parameter binding confirmed (D-02)

`older_than => $1::interval` with a text param ('700 days') and `older_than => $1` with a
timestamptz param both bind correctly via prepared statements (psycopg uses identical `%s` server
binding) [VERIFIED: live DB]. Native filter semantics confirmed: `older_than` keeps chunks whose
range is entirely before the cutoff; `newer_than` keeps chunks after; both together = window.

## drop_chunks Resolution (TS-ADV-05 — RESOLVED, HIGH confidence)

**Recommended mechanism: capture the ordered preview list FIRST (via the TSDB_SHOW_CHUNKS query),
THEN execute the side-effecting `drop_chunks()`. Return the pre-captured list.**

Rationale (live-verified):
1. The `drop_chunks()` SRF return column is typed **`text`, not `regclass`** (unlike `show_chunks`),
   so the regclass JOIN that orders `show_chunks` **fails on the drop SRF**
   (`operator does not exist: regclass = text`) [VERIFIED: live DB].
2. After a real drop, the dropped chunks' rows are **gone from `timescaledb_information.chunks`**,
   so you cannot JOIN post-drop to recover `range_start` ordering at all.
3. Therefore the only way to return the **identical shape to `show_chunks`** (D-04, oldest-first,
   fully-qualified) is to run the show_chunks-shaped query first (while chunks exist), keep that
   ordered list, then issue `drop_chunks`.

This naturally unifies `dry_run`:
- `dry_run=True`  -> run TSDB_SHOW_CHUNKS, return list, **do not drop**.
- `dry_run=False` -> run TSDB_SHOW_CHUNKS (capture), then `SELECT drop_chunks('{schema}.{table}'{args})`, return the captured list.

`drop_chunks` runs fine through the standard `self._db.execute()` path (no autocommit seam needed —
that is Phase 31's cagg problem) [VERIFIED: live DB, drop succeeded inside normal connection].

**Both-None guard (D-03):** raise `ValueError` before any DB round-trip when `older_than is None and
newer_than is None`. (Native `drop_chunks` with no bounds would wipe everything.)

**Live-verified drop:** dropping `older_than => '2024-01-04'` on the 12-chunk table removed
`_hyper_270_1/2/3_chunk` and left 4..12; the SRF returned exactly those 3 dropped names.

## add_dimension Resolution (TS-ADV-08 — RESHAPED, see Finding 1)

### by_hash / by_range live-verified on 2.28 (D-06)

```sql
-- hash form (number_partitions):
SELECT add_dimension('{schema}.{table}', by_hash('{column}', {number_partitions}){if_ne})
-- range form (chunk_interval):
SELECT add_dimension('{schema}.{table}', by_range('{column}', INTERVAL '{chunk_interval}'){if_ne})
```
where `{if_ne}` = `, if_not_exists => true` when `if_not_exists` is True.

Both forms succeeded on 2.28 [VERIFIED: live DB]. `if_not_exists => true` on a duplicate dimension
returns `(job_id, f)` with a `NOTICE: column "..." is already a dimension, skipping` — no error.

**Identifier handling:** `column` via `validate_identifier`; `table`/`schema` via `validate_identifiers`;
`number_partitions` is an int (cast/validate as int, interpolate directly); `chunk_interval` via
`validate_interval` then interpolate inside `INTERVAL '...'` (consistent with existing
`create_hypertable`). **D-07 mutual-exclusivity** (`hash` requires `number_partitions` & forbids
`chunk_interval`; `range` requires `chunk_interval` & forbids `number_partitions`) -> construction
`ValueError` before any round-trip.

### Finding 1 — D-08 must be reshaped (CRITICAL, HIGH confidence)

CONTEXT D-08 and PITFALLS #6 assume `add_dimension` on a **non-empty hypertable raises** an error to
re-raise as `TimescaleError`. **This is FALSE on TSDB 2.28 with the modern builder form**
[VERIFIED: live DB]:

```
-- hypertable WITH a row already inserted:
SELECT add_dimension('public.x', by_hash('device_id', 4));   -> (279,t)  SUCCESS
SELECT add_dimension('public.x', by_range('ts2', INTERVAL '7 days')); -> (280,t)  SUCCESS
```

The "has existing data" error only ever applied to the **legacy positional form**, and even that now
errors on **duplicate dimension**, not on data presence:
```
SELECT add_dimension('public.x', 'device_id', number_partitions => 2);
ERROR: column "device_id" is already a dimension          (SQLSTATE TS160)
```

**Implication for the planner:** there is no non-empty-hypertable error to catch. The
attempt-DDL-catch-reraise pattern (D-08) should be **repurposed** to wrap the reliably-occurring DB
error — the **duplicate-dimension** error (`already a dimension`, SQLSTATE `TS160`) — re-raised as
`TimescaleError`. Confirm the exact mapped psycopg error class at implementation time (TS160 is a
TimescaleDB-custom SQLSTATE; psycopg surfaces it as a generic `psycopg.errors.DatabaseError` /
`OperationalError` subclass — catch broadly and re-wrap). **The planner / discuss-phase should
confirm this repurposing with the user**, since it changes the documented behavior of TS-ADV-08's
"clear error on non-empty hypertable" success criterion. [ASSUMED] that wrapping the duplicate-dim
error is the intended substitute — needs user confirmation (logged A1).

## add_reorder_policy Resolution (TS-ADV-09 — see Finding 2)

### Signature live-verified

```sql
SELECT add_reorder_policy('{schema}.{table}', '{index_name}', if_not_exists => true) AS job_id
```
Identifiers: `table`/`schema`/`index_name` via `validate_identifiers`.

### Finding 2 — add_reorder_policy is Community-License-only; local DB is Apache (CRITICAL, HIGH confidence)

The local DB reports `timescaledb.license = apache` [VERIFIED: live DB: `SHOW timescaledb.license` ->
`apache`]. Under this license, `add_reorder_policy` raises:
```
ERROR: function "add_reorder_policy" is not supported under the current "apache" license
HINT: Upgrade your license to 'timescale' to use this free community feature.
```
This is **SQLSTATE `0A000`**, surfaced by psycopg as `psycopg.errors.FeatureNotSupported`
[VERIFIED: live DB]. The **same limitation already affects** the existing v0.6.0
`add_retention_policy` / `add_compression_policy` — and the existing test at
`tests/test_database_integration.py:866-878` already tolerates it:

```python
from psycopg.errors import FeatureNotSupported
try:
    ts_db.timescale.add_retention_policy(t, drop_after="365 days")
except FeatureNotSupported:
    pass
```

**Implication for the planner:**
- The `add_reorder_policy` **live integration test cannot assert the job row** on this DB — it must
  wrap the call in `try/except FeatureNotSupported: pass` (mirroring the existing pattern), OR
  skip-gate on license. The **mock SQL-shape unit test (D-11)** is the authoritative SQL assertion
  for TS-ADV-09.
- The job-row assertion (`timescaledb_information.jobs`) and `CALL run_job(job_id)` deterministic
  test (PITFALLS #6) **only work on a Community/`timescale`-licensed build**; they will not exercise
  on local/CI. Write them defensively behind the license tolerance so the suite stays green here.

(`timescaledb_information.jobs` columns for the assertion when on a licensed build:
`job_id, application_name, proc_name, hypertable_schema, hypertable_name, config`.)

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg | 3.x (already a dep) | DB driver + `%s` server-side param binding | Existing pycopg driver; zero new deps |
| TimescaleDB | 2.28.0 (server) | Hypertable/chunk SQL functions | Target server; live-verified |

No new packages. Slopcheck/registry audit N/A (zero new dependencies — CLAUDE.md mandate).

## Architecture Patterns

### Pattern 1: Pure-builder accessor method with per-method extension guard
**What:** Each method first checks `self._db.schema.has_extension("timescaledb")` (sync) /
`await self._db.schema.has_extension("timescaledb")` (async), raising `ExtensionNotAvailable`;
validates identifiers; builds SQL with interpolated identifiers + `%s` runtime params; calls
`self._db.execute(sql, params)`.
**When to use:** All four Phase 30 methods.
**Source:** existing `TimescaleAccessor.create_hypertable`/`add_retention_policy` (`pycopg/timescale.py`).

### Pattern 2: Type-driven cast for chunk bounds (D-02)
**What:** branch on `isinstance(bound, str)` -> `%s::interval` vs datetime -> bare `%s`; None -> omit.
Build SQL fragment + param in lockstep so each non-None bound adds exactly one `%s`.

### Pattern 3: Capture-before-mutate for drop_chunks
**What:** run the read-only show-chunks query to capture the ordered list BEFORE the destructive
`drop_chunks()`; return the captured list. `dry_run` short-circuits before the drop.

### Anti-Patterns to Avoid
- **Sorting chunk names lexicographically** — `_hyper_N_10` sorts before `_hyper_N_2`. Always
  `ORDER BY range_start ASC` in SQL. [VERIFIED wrong: live DB]
- **JOINing the `drop_chunks()` SRF to the info view** — SRF is `text` not `regclass`, and rows are
  gone post-drop. Capture via show_chunks first. [VERIFIED: live DB]
- **Comparing `regclass = text`** in the show_chunks JOIN — errors. Cast info-view name to regclass.
- **Async guard without `await`** — recurring Phase 23 gotcha; every async guard MUST `await`
  `self._db.schema.has_extension(...)` (see existing async methods). [VERIFIED: codebase]
- **Asserting the reorder job row unconditionally** — fails under Apache license. Tolerate
  `FeatureNotSupported`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Chunk range ordering | Python sort of chunk-name strings | `ORDER BY range_start ASC` in SQL | Lexical sort is wrong; DB knows true range order |
| Fully-qualified chunk name | String-concat from parsed regclass | `chunk_schema \|\| '.' \|\| chunk_name` from info view | Native, unquoted, matches CONTEXT example |
| Chunk filter semantics | Manual `range_start`/`range_end` WHERE math | native `show_chunks(older_than, newer_than)` SRF | Exact TSDB semantics, incl. boundary handling |
| Identifier safety | Manual escaping | `validate_identifiers` / `validate_interval` (utils.py) | Established, tested |

## Common Pitfalls

### Pitfall 1: D-08 non-empty error does not exist on 2.28 (Finding 1)
**What goes wrong:** Test "add_dimension on non-empty hypertable raises TimescaleError" never sees an
error — the call succeeds. **How to avoid:** repurpose the catch to the duplicate-dimension error
(`already a dimension`, TS160); confirm intent with user.

### Pitfall 2: add_reorder_policy blocked by Apache license (Finding 2)
**What goes wrong:** live test fails with `FeatureNotSupported` on local/CI. **How to avoid:** wrap
in `try/except FeatureNotSupported: pass`; rely on mock SQL-shape test for the assertion.

### Pitfall 3: drop_chunks irreversibility / both-None wipe (PITFALLS #3, D-03)
**What goes wrong:** both-None drops everything; no rollback. **How to avoid:** `ValueError` on
both-None before round-trip; `dry_run` preview; DESTRUCTIVE docstring Notes.

### Pitfall 4: async `await` omission on the guard (PITFALLS #5)
**What goes wrong:** missing `await` on `has_extension` -> truthy coroutine, guard never fires.
**How to avoid:** copy the async guard verbatim from existing async methods; parity test catches
signature drift but not the missing await — review each.

## Code Examples

### show_chunks builder (recommended SQL, live-verified)
```python
# Source: live DB (TSDB 2.28.0), this session
# identifiers validated; bounds appended conditionally (D-02)
sql = (
    "SELECT c.chunk_schema || '.' || c.chunk_name AS chunk_name "
    f"FROM show_chunks('{schema}.{table}'{older_frag}{newer_frag}) AS sc "
    "JOIN timescaledb_information.chunks c "
    "  ON format('%%I.%%I', c.chunk_schema, c.chunk_name)::regclass = sc "  # %%I -> literal %I
    "ORDER BY c.range_start ASC"
)
# older_frag: "" | ", older_than => %s::interval" | ", older_than => %s"
rows = self._db.execute(sql, params)   # params in older-then-newer order
return [r["chunk_name"] for r in rows]
```
**Note the `%%I` escaping** — psycopg treats `%` specially; `format('%I.%I', ...)` must be written
`%%I.%%I` in a psycopg query string (same convention as existing `HYPERTABLE_INFO`/`TABLE_SIZES` in
`queries.py`). [VERIFIED: codebase convention + live SQL].

### add_dimension by_hash / by_range (live-verified)
```python
if partition_type == "hash":
    dim = f"by_hash('{column}', {int(number_partitions)})"
else:  # range
    validate_interval(chunk_interval)
    dim = f"by_range('{column}', INTERVAL '{chunk_interval}')"
ne = ", if_not_exists => true" if if_not_exists else ""
self._db.execute(f"SELECT add_dimension('{schema}.{table}', {dim}{ne})")
```

## Runtime State Inventory

> Not a rename/refactor phase — greenfield method additions. Section omitted intentionally except:
**Nothing found** — no stored data keys, service config, OS-registered state, secrets, or build
artifacts are affected. Verified: phase only adds Python methods + SQL constants + one exception class.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `add_dimension(t,'col',number_partitions=>N)` positional | `add_dimension(t, by_hash('col',N))` builder | TSDB 2.13 | Use builder (D-06); positional now errors on dup, not data |
| `add_dimension` errors on non-empty hypertable | builder form **succeeds** on non-empty | by 2.28 | D-08 must be reshaped (Finding 1) |

**Deprecated/outdated:** PITFALLS #6 "add_dimension requires empty hypertable" — **outdated for the
builder form on 2.28**. Legacy positional form is not used here.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The `add_dimension` "clear error" (TS-ADV-08) should be repurposed to wrap the duplicate-dimension error since the non-empty error no longer exists on 2.28 | add_dimension / Finding 1 | If user wants a different behavior (e.g., a pre-check for data + raise), the method shape changes; needs user confirmation in discuss-phase |
| A2 | `add_reorder_policy` live test tolerating `FeatureNotSupported` satisfies TS-ADV-09's "job row" criterion via the mock test instead | add_reorder_policy / Finding 2 | If a Community-licensed CI is required for the job-row assertion, an env change is needed |

## Open Questions

1. **TS-ADV-08 clear-error semantics (A1).**
   - What we know: builder form succeeds on non-empty; duplicate-dim error (TS160) is the reliable catch.
   - What's unclear: whether the user wants the original "non-empty -> error" behavior re-created via
     a pre-check (`COUNT(*) FROM timescaledb_information.chunks`) or accepts the repurposed dup-dim wrap.
   - Recommendation: discuss-phase confirms; default to wrapping dup-dim as `TimescaleError`.

2. **TS-ADV-09 job-row coverage under Apache license (A2).**
   - What we know: live DB rejects `add_reorder_policy`; existing tests tolerate `FeatureNotSupported`.
   - Recommendation: assert SQL shape via mock test; tolerate `FeatureNotSupported` in live test.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL (local) | all live tests | yes | (running, TCP localhost) | — |
| TimescaleDB extension | all 4 methods | yes | 2.28.0 | ts_db skip-fixture |
| TSDB Community license | add_reorder_policy live job-row test | **no (apache)** | — | tolerate `FeatureNotSupported`; mock SQL-shape test |

**Missing dependencies with fallback:** Community license — fall back to `FeatureNotSupported`
tolerance + mock test (established v0.6.0 pattern).

**Connection note:** `sudo -u postgres psql` (peer) is unavailable in this non-TTY environment; use
`PGPASSWORD=postgres psql -h localhost -U postgres -d pycopg_test` (TCP md5) instead. Tests use
`Database.from_env()` — unaffected.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (+ pytest-asyncio, `asyncio_mode = "auto"`) |
| Config file | `pyproject.toml` (coverage ratchet gate) |
| Quick run command | `uv run pytest tests/test_timescale.py -x -q` |
| Full suite command | `uv run pytest` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TS-ADV-04 | show_chunks oldest-first fully-qualified | unit (mock SQL) + integration (live) | `uv run pytest tests/test_timescale.py -k show_chunks` | ❌ Wave 0 (new file) |
| TS-ADV-05 | drop_chunks dry_run + ValueError both-None | unit + integration | `uv run pytest tests/test_timescale.py -k drop_chunks` | ❌ Wave 0 |
| TS-ADV-08 | add_dimension by_hash/by_range + ValueError mutual-excl | unit + integration | `uv run pytest tests/test_timescale.py -k add_dimension` | ❌ Wave 0 |
| TS-ADV-09 | add_reorder_policy SQL shape (+ job row if licensed) | unit (mock) + integration (license-tolerant) | `uv run pytest tests/test_timescale.py -k reorder` | ❌ Wave 0 |
| TS-ADV-10 | sync/async parity | unit | `uv run pytest tests/test_parity.py -k accessor_parity` | ✅ (auto via ACCESSOR_PAIRS) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_timescale.py -x -q`
- **Per wave merge:** `uv run pytest tests/test_timescale.py tests/test_parity.py -q`
- **Phase gate:** full `uv run pytest` green + coverage ratchet held before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_timescale.py` — new file; covers TS-ADV-04/05/08/09 (sync + async). Port `ts_db`
      skip-fixture from `tests/test_database_integration.py:839`; add async equivalent.
- [ ] Mock SQL-shape unit tests (`mock_schema.has_extension` style, see `tests/test_async_database.py`)
      for all 4 methods — the authoritative assertion for `add_reorder_policy` (Apache license).
- [ ] License tolerance: `from psycopg.errors import FeatureNotSupported` try/except in the live
      reorder test (mirror `test_database_integration.py:869-878`).
- No framework install needed (pytest + pytest-asyncio already present).

## Sources

### Primary (HIGH confidence)
- **Live DB** TSDB 2.28.0 (`pycopg_test`, this session) — all SQL shapes, ordering, drop semantics,
  by_hash/by_range, license rejection, SQLSTATEs (`0A000`, `TS160`) executed and output recorded.
- `pycopg/timescale.py`, `pycopg/queries.py`, `pycopg/exceptions.py`, `pycopg/utils.py` — patterns.
- `tests/test_database_integration.py:836-889` — `ts_db` fixture + `FeatureNotSupported` tolerance.

### Secondary (MEDIUM confidence)
- `.planning/research/PITFALLS.md` — pitfalls 3/5/6 (note #6 partially outdated for 2.28 builder form).
- `.planning/phases/30-chunk-management-partitioning/30-CONTEXT.md` — 11 locked decisions.

## Metadata

**Confidence breakdown:**
- D-05 chunk ordering / show_chunks SQL: HIGH — live-verified, lexical-vs-range proven with 12 chunks.
- drop_chunks shape: HIGH — live-verified capture-before-drop necessity (text SRF + vanishing rows).
- add_dimension: HIGH — by_hash/by_range live-verified; D-08 contradiction live-verified.
- add_reorder_policy: HIGH on SQL shape + license block (live); MEDIUM on job-row columns (cannot
  exercise on Apache build).

**Research date:** 2026-06-22
**Valid until:** ~30 days (stable server version; re-verify if TSDB upgraded past 2.28).
