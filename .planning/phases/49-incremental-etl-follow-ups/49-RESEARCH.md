# Phase 49: Incremental ETL Follow-ups - Research

**Researched:** 2026-07-03
**Domain:** PostgreSQL advisory locks, SQL row-value comparison, JSONB envelope codecs, pandas dtype dispatch (pycopg internal `Pipeline`/`etl.py` extension)
**Confidence:** HIGH

## Summary

Phase 49 is a pure extension of the existing `pycopg/etl.py` incremental-ETL machinery — no new
runtime dependency, no new accessor method, no new SQL constant category. All four features
(F01 seed floor, F02 boundary knobs, F03 composite watermark, F04 advisory-lock concurrency) are
additive `Pipeline` dataclass fields plus internal extensions to five existing pure functions
(`_build_incremental_extract_sql`, `_encode_watermark`/`_decode_watermark`, `_read_watermark`,
`run()`). The 15 CONTEXT.md decisions (D-01..D-15) are already grounded in the real current code
— every line reference cited in CONTEXT.md was re-verified against the live file in this session
and is accurate as of 2026-07-03 (etl.py is currently 2179 lines; see per-decision line numbers
below, which shifted slightly from CONTEXT.md's citations due to normal drift — re-verified
exact numbers are used throughout this document).

The two DB-verification targets flagged as Claude's Discretion were both confirmed empirically
against a live local PostgreSQL 18.4 instance in this session (not training-data assumptions):
`hashtextextended(text, bigint) -> bigint` exists in `pg_catalog` (core, no extension), and a
session-scoped advisory lock acquired on a dedicated connection is (a) visible to a second
concurrent session via `pg_try_advisory_lock` returning `false` while held, and (b)
automatically released the instant the holding connection closes — confirming D-14's "no
orphaned locks even on crash" premise is correct, not merely documented folklore.

**Primary recommendation:** Extend the five pure functions in place, in the fixed dependency
order the CONTEXT.md decisions already imply — floor resolution (D-01/D-02, seed) → lookback
widening (D-05/D-06/D-07) → inclusive/exclusive operator choice (D-05) → composite tuple
handling (D-09/D-10/D-11) → advisory lock wrapping the whole `run()` (D-12..D-15, outermost).
Composite (F03) touches the most surfaces and should be sequenced last among the three
non-lock features so the tuple-comparison SQL and the composite envelope tag can be built once
the scalar extensions (seed/lookback/inclusive) are already working and tested.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `initial_watermark` seed floor (F01) | API / Backend (pycopg library) | Database (read via `ETL_GET_LAST_WATERMARK`) | Pure Python fallback value consulted only when the DB has no stored watermark row — no new SQL |
| Inclusive/lookback boundary (F02) | API / Backend | Database (SQL comparison operator + bound values) | Operator choice (`>` vs `>=`) and floor arithmetic are computed in the SQL-builder layer; DB executes the comparison |
| Composite watermark key (F03) | API / Backend | Database (`(c1,c2) > (%s,%s)` row-value comparison, JSONB envelope storage) | Tuple comparison is a native Postgres SQL feature (lexicographic `ROW` compare); pycopg only builds the SQL and encodes/decodes the JSONB shape |
| Advisory-lock concurrency (F04) | Database (session-scoped `pg_advisory_lock`/`pg_try_advisory_lock`) | API / Backend (dedicated-connection lifecycle, `finally` release) | Mutual exclusion MUST be server-side and deterministic across processes — Python-side locking (`threading.Lock`, `PYTHONHASHSEED`-salted `hash()`) cannot serialize across OS processes; this is a Database-tier primitive orchestrated by the Backend |

No Browser/Client, Frontend-Server, or CDN tier involvement — `pycopg` is a server-side library
with no UI; the entire phase lives in the API/Backend + Database tiers of a consuming
application.

## User Constraints (from CONTEXT.md)

<user_constraints>

### Locked Decisions

**Carried forward from shipped v0.7.0 incremental ETL (LOCKED — do not reopen)**
- **C-01:** Incremental requires `load_mode="upsert"` (v0.7.0 D-16) — `append`/`replace` rejected at construction. This idempotency is what makes every F02 `>=`/lookback replay and every F03 boundary re-read safe. All four features build on it.
- **C-02:** Watermark is a typed JSONB envelope `{"type": ..., "value": ...}`, allowlist exactly `{datetime, int, str}`; `bool` and `float` are rejected loud (`ETLError`). `bool` rejected before the `int` branch (subclass trap). Encode/decode helpers: `_encode_watermark`, `_decode_watermark` — frozen; extend by adding a new tag, never mutate the existing three.
- **C-03:** High-water mark = `max(col)` of the raw batch before transforms; advances only on a real load; empty batch (0 rows) records no watermark and preserves the prior via `ETL_GET_LAST_WATERMARK`'s `status='success' AND watermark IS NOT NULL` predicate. Never NULL-overwrites.
- **C-04:** Builder-pur (`validate_identifiers` line 1, user values bound `%s`/`%(name)s`, never interpolated); full sync/async parity — edit both `ETLAccessor` and `AsyncETLAccessor` in the same commit, register any new public method/param in `tests/test_parity.py`.

**F01 — first-run seed (`initial_watermark`)**
- **D-01:** Seed-floor-only semantics. When NO stored watermark exists (true first run), use `initial_watermark` as the `WHERE col > initial_watermark` floor — turning the first full-load into a bounded incremental load. Once the first successful run records `max(col)`, `initial_watermark` is never consulted again. Implemented as the value returned by `_read_watermark` when the stored watermark is absent — falls straight out of the existing `_read_watermark(None)` → full-load path. NOT a persistent clamp; no `max(initial, stored)` on every run.
- **D-02:** New frozen `Pipeline` field `initial_watermark: datetime | int | str | Sequence[...] | None = None`, next to `incremental_column`. Validated in `__post_init__`: requires `incremental_column` set (else `ValueError`, same shape as the D-16 guard); scalar type checked against the `{datetime, int, str}` allowlist (reuse `_encode_watermark`'s guard rationale — `bool`/`float` rejected). NOT a `run()` param — declarative + inspectable, consistent with the existing `incremental_column`.
- **D-03:** Empty first (seeded) batch → record nothing, re-seed next run. No special-casing: no watermark is stored (C-03), so the next run again finds no stored watermark and re-applies `initial_watermark`. Preserves the "advance only on a real load" invariant.
- **D-04 (composite interaction, links F03):** For a composite `incremental_column`, `initial_watermark` must be a matching-length sequence of scalars (one per key column). Validated at construction: `len(initial_watermark) == len(incremental_column tuple)` else `ValueError`; each element type-checked against the allowlist.

**F02 — boundary knobs (`>=` and/or lookback)**
- **D-05:** Two orthogonal keyword-only frozen `Pipeline` fields: `incremental_inclusive: bool = False` (`>=` vs `>`) and `incremental_lookback: timedelta | int | None = None`. Either, both, or neither. Default `(False, None)` = today's exact SQL, byte-identical. Each independently testable. NOT a single boundary-mode enum.
- **D-06:** Lookback typed `timedelta | int`, subtracted in Python before binding. The effective read floor is computed in Python — `datetime floor − timedelta`, `int floor − int` — then bound as the usual `%s`. NOT a SQL `%s::interval` (keeps the pure builder simple and covers the int case). A `str`-typed watermark + a set `incremental_lookback` → `ETLError` at run time (can't subtract from a str); the type is only known once the watermark is read, so this is a runtime guard, not a construction guard. Reuses the `{datetime,int,str}` type dispatch already in `run()`.
- **D-07:** The RECORDED high-water mark is always the true `max(col)` — lookback only widens the read window, it never regresses the stored watermark. (floor=100, lookback=10 → read `WHERE col > 90`, but still record `max(col)`≈137.) Combined form: `WHERE col >= (floor − lookback)`.
- **D-08:** Accept + document the boundary/overlap replay. Inclusive `>=` (and lookback) re-read and re-process the boundary row / overlap window every run; this is an idempotent no-op ON CONFLICT (C-01). Document in the docstring ("inclusive/lookback re-scan overlaps every run; safe because incremental requires upsert"). No dedup machinery.

**F03 — composite (multi-column) watermark**
- **D-09:** Widen the existing field: `incremental_column: str | Sequence[str] | None`. A `str` stays single-column (byte-identical, back-compat); a sequence declares a composite key. Normalized internally to a `tuple[str, ...]` in `__post_init__` — exactly how `conflict_columns` already coerces list→tuple. One declarative knob; NO second field, NO mutual-exclusion guard. `validate_identifiers` runs over every element.
- **D-10:** Row-value comparison + true max-row (per-column is a correctness trap). SQL: `WHERE (c1, c2) > (%s, %s)` — Postgres lexicographic tuple comparison (`>=` when `incremental_inclusive`), each value a bound `%s`. Recorded watermark = the actual greatest row: sort the raw batch by the key columns and take that row's tuple (e.g. `df.sort_values(cols).iloc[-1][cols]`). NOT `WHERE c1>%s AND c2>%s` with per-column `(max(c1), max(c2))` — that fabricates a tuple no row has and silently skips rows whose `c1` advanced but `c2` didn't. Extend `_build_incremental_extract_sql` for the tuple form (SQL-string source → wrap subquery then `WHERE (c1,c2) > (%s,%s)`; table source → append the clause).
- **D-11:** New `"composite"` envelope tag; the shipped single-scalar shape is untouched. Single-column keeps `{"type":"int"|"datetime"|"str","value":...}` verbatim → zero migration, old rows read exactly as before. Composite uses a new tagged shape `{"type":"composite","columns":[...],"values":[{scalar-envelope}, ...]}`. `_decode_watermark` dispatches on the `type` tag — `"composite"` joins the existing three; `_encode` reuses the per-scalar encoder for each element (`bool`/`float` still rejected loud). Decoded composite = an ordered tuple of scalars fed to the `(c1,c2) > (%s,%s)` builder.

**F04 — advisory-lock concurrency**
- **D-12:** Opt-in `Pipeline` field `concurrency: Literal["wait", "skip"] | None = None`. `None` (default) = no lock, byte-identical to today (opt-in, NOT always-on — no extra round-trip unless requested). `"wait"` = `pg_advisory_lock` (block until the other run finishes → serialize). `"skip"` = `pg_try_advisory_lock` (refuse to overlap). Declarative + inspectable, consistent with D-02/D-05/D-09. Available to ALL pipelines, not just incremental (concurrent `replace`/`append` race too), though incremental is the primary motivation.
- **D-13:** `concurrency="skip"` + lock already held → transient `'skipped'` RunResult. Return `RunResult(status="skipped", run_id=None, rows_extracted=0, rows_loaded=0)` and write NO `pipeline_runs` row — mirrors the `dry_run` precedent. Scheduler-friendly (inspect `result.status`, no `try/except` per tick). Needs NO change to the `pipeline_runs.status` CHECK constraint (`'running','success','failed'`) because a skipped run is never persisted. `'skipped'` is a documented transient status value only (like `'dry_run'`). NOT a raised exception.
- **D-14:** Session-scoped lock on a dedicated connection, released in `finally`. Acquire a SESSION-scoped `pg_advisory_lock` / `pg_try_advisory_lock` on a dedicated connection opened first thing in `run()`, held for the entire read→extract→load→record span (which crosses the separate autocommit run-log writes AND the load transaction), released in a `finally` (`pg_advisory_unlock`, and closing the connection auto-releases even on crash → no orphaned locks). NOT `pg_advisory_xact_lock` — a transaction-scoped lock only guards the load txn, leaving the watermark-read/extract race (the exact race F04 targets) open.
- **D-15:** DB-side key derivation: `SELECT pg_try_advisory_lock(hashtextextended(%s, 0))` (or `pg_advisory_lock(...)` for `"wait"`), pipeline name bound as `%s`. Deterministic server-side, identical for every client/process — the correct property for cross-process mutual exclusion. NOT a Python-side `hash()` (salted by `PYTHONHASHSEED` → different key per process → lock does not serialize). Name is bound, never interpolated.

**Standing bar (from REQUIREMENTS.md cross-cutting acceptance criteria)**
- Sync/async parity — every new field/param/method on BOTH `ETLAccessor` and `AsyncETLAccessor`, enforced by `test_accessor_parity` / `test_accessor_parameter_kind_parity`; async mirrors sync 1:1 (`await` every DB call, `asyncio.to_thread` transforms).
- Builder-pur + injection safety — `validate_identifiers` line 1 of every new/extended SQL builder, user values bound `%s`, dedicated injection test per new builder path (composite tuple compare, seed floor, lookback, advisory-lock key).
- Additive/non-breaking — all new params keyword-only, no `DeprecationWarning`, defaults reproduce current behavior exactly.
- Zero new runtime deps; `mypy --strict` 0 errors (blocking gate — widen `incremental_column` / `initial_watermark` union types and add `@overload` stubs where a return type branches); `interrogate` 100%; coverage ratchet ≥95% (baseline 96.37% at Phase 48); Sphinx `-W` clean.

### Claude's Discretion

- Exact new SQL constant names/placement in `queries.py` (e.g. an advisory-lock statement pair) — follow existing `ETL_*` style.
- `hashtextextended` availability confirmation (it is core PostgreSQL since 9.x, no extension) and the precise `pg_try_advisory_lock` return-handling.
- Whether the composite max-row is computed via `sort_values`/`nlargest` or an equivalent — any approach that yields the true lexicographic max row tuple (not per-column maxes) satisfies D-10.
- Test layering: mock SQL-shape unit tests (both accessors) + live-DB integration; advisory-lock integration likely needs two connections/sessions to exercise the held-lock path.
- New `RunResult` field additions, if any — none decided as required; keep the 10-field shape unless a knob demands surfacing (e.g. lookback-applied floor). If added, mirror the `watermark_used`/`watermark_recorded` optional-default pattern.

### Deferred Ideas (OUT OF SCOPE)

- **ETL-INC-F05 (CDC / WAL change capture)** — logical replication slots + output-plugin decoding; a large distinct subsystem, deferred 2026-07-02 to keep v1.1.0 a coherent additive set. Don't re-litigate.
- **Cross-pipeline / global advisory locks** — F04 is per-pipeline (keyed on `pipeline.name`); a shared-resource lock across different pipelines is a future ergonomic if requested.
- **`concurrency` on a `run()` override** — decided as a Pipeline field (D-12); a per-call override could be a future additive convenience.
- **Surfacing the lookback-applied floor / seed on `RunResult`** — only if a concrete need appears; kept to Claude's Discretion above.
- Milestone-level deferrals already recorded (don't re-litigate): SPAT-F01 (gridSize), RASTER-F01 (raster).

</user_constraints>

## Phase Requirements

<phase_requirements>

| ID | Description | Research Support |
|----|-------------|------------------|
| ETL-INC-F01 | User can set an `initial_watermark` on a `Pipeline` to bound (or seed) the first incremental run instead of a full initial load. | `_read_watermark` seed fallback confirmed at etl.py:1007 (sync)/:1722 (async); `__post_init__` guard placement confirmed at etl.py:211-269; composite-length validation (D-04) has a concrete precedent in the existing `conflict_columns` tuple-length pattern. See "Code Examples" §F01. |
| ETL-INC-F02 | User can configure the incremental boundary — inclusive `>=` and/or a lookback overlap — instead of the fixed exclusive `>`. | `_build_incremental_extract_sql` exact current SQL shape re-verified at etl.py:539-600 (both SQL-string-wrap and table-append paths); the max-capture type-dispatch block re-verified at etl.py:1315-1347 (sync) and :2011-2043 (async, shifted from CONTEXT's :1315-1347 citation which was the sync-only reference) plus the dry-run mirror at etl.py:1226-1250 (sync) / :1922-1946 (async). See "Code Examples" §F02. |
| ETL-INC-F03 | User can define a `Pipeline` with a composite (multi-column) incremental watermark key. | `conflict_columns` list→tuple normalization precedent at etl.py:241-244; envelope codec frozen-tag dispatch re-verified at etl.py:607-688; Postgres row-value (tuple) comparison is a native, well-documented SQL feature — no extension needed. See "Code Examples" §F03. |
| ETL-INC-F04 | User can run the same pipeline concurrently from two processes and have the second run safely serialize (or refuse to overlap) via a PostgreSQL advisory lock, sync and async. | `hashtextextended(text, bigint) -> bigint` and `pg_advisory_lock`/`pg_try_advisory_lock`/`pg_advisory_unlock` signatures confirmed live against PostgreSQL 18.4 in this session (see "Package Legitimacy Audit" is N/A — no packages — and "Environment Availability" below for the verification transcript); session-scoped release-on-disconnect empirically confirmed with a two-session test. `dry_run` early-fork precedent (writes no `pipeline_runs` row) re-verified at etl.py:1211-1284 (sync) / :1907-1980 (async) as the model for `'skipped'`. See "Code Examples" §F04. |

</phase_requirements>

## Standard Stack

No new runtime dependency. This phase extends `pycopg/etl.py` using only:

| Library | Version (in use) | Purpose | Why Standard |
|---------|-------------------|---------|---------------|
| `psycopg` | already a pycopg dependency (v3) | Executes the new advisory-lock SQL and the composite tuple-compare SQL exactly like every other builder in etl.py | Already the sole DB driver; no new API surface needed — `pg_advisory_lock`/`pg_try_advisory_lock`/`pg_advisory_unlock` are plain SQL functions callable via `cur.execute` |
| `pandas` | already a pycopg dependency | `df.sort_values(cols).iloc[-1]` for the composite max-row (D-10); existing `df[col].max()` dtype-dispatch pattern is reused/extended for lookback arithmetic | Already the extract-batch representation throughout etl.py — no new pattern class introduced |
| stdlib `datetime`/`timedelta` | stdlib | Lookback arithmetic (`floor - lookback`) computed in Python before binding (D-06) | No SQL `::interval` cast needed — keeps builders pure/testable without a DB |
| stdlib `typing.Literal` | stdlib (already imported pattern elsewhere in etl.py, e.g. `load_mode` string literals) | `concurrency: Literal["wait", "skip"] | None` field typing | Matches existing `_VALID_LOAD_MODES` validation style; needed for a clean `mypy --strict` union |

**Installation:** None — zero new packages. `uv sync --all-extras --dev` is unaffected.

**Version verification:** N/A — no new package pins to verify.

## Package Legitimacy Audit

**Not applicable.** This phase introduces zero new runtime or dev dependencies — every function
used (`pg_advisory_lock`, `pg_try_advisory_lock`, `pg_advisory_unlock`, `hashtextextended`) is a
built-in `pg_catalog` SQL function shipped with core PostgreSQL (confirmed live, see
"Environment Availability"), not an installable package. `slopcheck`/registry verification does
not apply to SQL built-ins. No `Package Legitimacy Audit` table is required.

**Packages removed due to slopcheck [SLOP] verdict:** none (N/A — no packages).
**Packages flagged as suspicious [SUS]:** none (N/A — no packages).

## Architecture Patterns

### System Architecture Diagram

```
Pipeline.run(pipeline)                              [entry point: db.etl.run(pipeline)]
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│ 0. LOCK ACQUIRE (F04, new — outermost, D-14)               │
│    if pipeline.concurrency is not None:                    │
│      open dedicated connection                             │
│      key = hashtextextended(pipeline.name, 0)  [server-side]│
│      "wait"  -> pg_advisory_lock(key)      (blocks)         │
│      "skip"  -> pg_try_advisory_lock(key)  (bool)           │
│         └─ False -> return RunResult(status="skipped")      │
│            (no pipeline_runs row written — dry_run model)   │
└───────────────────────────────────────────────────────────┘
        │ (lock held)
        ▼
┌───────────────────────────────────────────────────────────┐
│ 1. READ WATERMARK  (_read_watermark, extended F01/F03)     │
│    stored = SELECT watermark FROM pipeline_runs WHERE ...  │
│    if stored is None and pipeline.initial_watermark:       │
│         floor = initial_watermark        (F01, D-01)       │
│    else:                                                    │
│         floor = decode(stored)           (existing)        │
│    if composite (F03): floor is a tuple, not a scalar       │
└───────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│ 2. APPLY LOOKBACK (F02, new, D-06/D-07)                    │
│    read_floor = floor - incremental_lookback (if set)       │
│    (RECORD watermark stays the true max — never regressed) │
└───────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│ 3. EXTRACT  (_build_incremental_extract_sql, extended)     │
│    scalar:    WHERE col  >  %s   (or >=  when inclusive)   │
│    composite: WHERE (c1,c2) > (%s,%s)  (or >=)  — D-10     │
└───────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│ 4. TRANSFORM CHAIN (unchanged)                              │
└───────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│ 5. MAX-ROW CAPTURE (extended F02/F03)                       │
│    scalar:    raw_watermark = df[col].max()      (existing) │
│    composite: raw_watermark = df.sort_values(cols)          │
│                                  .iloc[-1][cols]  (D-10)     │
└───────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│ 6. LOAD (unchanged — COPY append/replace, execute upsert)   │
└───────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│ 7. RECORD WATERMARK (extended F03: new "composite" tag)     │
│    _end_run(..., watermark=_encode_watermark(raw_watermark))│
└───────────────────────────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────────────────────────┐
│ 8. LOCK RELEASE  (F04, new — finally, D-14)                 │
│    pg_advisory_unlock(key); close dedicated connection      │
│    (also auto-released on crash/disconnect — verified live) │
└───────────────────────────────────────────────────────────┘
        │
        ▼
   RunResult (returned to caller)
```

A reader can trace the primary use case (a concurrent incremental run) from the `concurrency=`
opt-in at the top, through the lock-guarded extract/transform/load body, to the guaranteed
`finally` release at the bottom — the exact span D-14 requires the lock to cover.

### Recommended Project Structure

No new files or directories — every change lands inside the existing three-file surface:

```
pycopg/
├── etl.py       # Pipeline dataclass + __post_init__ + all 5 extended pure functions + run()
├── queries.py   # ETL_* SQL constants — add advisory-lock statement pair here (D-15 discretion)
└── exceptions.py  # ETLError already covers D-06 (lookback-on-str) and D-04 (bool/float) — no new class needed

tests/
├── test_etl.py       # extend TestPipeline, TestBuildIncrementalExtractSql, TestEncodeDecodeWatermark
│                      # + new TestAdvisoryLock / TestComposite* classes
└── test_parity.py    # ACCESSOR_PAIRS already includes (ETLAccessor, AsyncETLAccessor) — no new
                       # registration needed unless a NEW public method is added (none is; all four
                       # features are Pipeline fields, not new run()/accessor params)
```

### Pattern 1: Additive frozen-dataclass field with construction-time guard

**What:** Add a new `Pipeline` field with a default that reproduces today's exact behavior, then
add a `__post_init__` branch that validates it — following the exact shape of the existing
`extract_limit`/`incremental_column` guards.
**When to use:** F01 (`initial_watermark`), F02 (`incremental_inclusive`/`incremental_lookback`),
F04 (`concurrency`).
**Example:**
```python
# Source: pycopg/etl.py:255-269 (existing extract_limit guard — the pattern to replicate)
if self.extract_limit is not None:
    if isinstance(self.extract_limit, bool) or not isinstance(
        self.extract_limit, int
    ):
        raise ValueError(
            "extract_limit must be a positive integer or None, got "
            f"{self.extract_limit!r}"
        )
    if self.extract_limit <= 0:
        raise ValueError(
            f"extract_limit must be a positive integer, got {self.extract_limit!r}"
        )
```

### Pattern 2: List→tuple normalization for a widened field (D-09)

**What:** Accept `str | Sequence[str]` at the call site but always store a normalized
`tuple[str, ...]` internally — exactly how `conflict_columns` already works.
**When to use:** F03 widening `incremental_column`.
**Example:**
```python
# Source: pycopg/etl.py:236-244 (existing conflict_columns normalization — the pattern to replicate)
if not isinstance(self.conflict_columns, tuple):
    object.__setattr__(
        self, "conflict_columns", tuple(self.conflict_columns)
    )
```
Applying the same shape to `incremental_column`: a bare `str` is NOT iterated into characters
(same bare-string trap the `conflict_columns` guard already defends against) — it must be
wrapped as a 1-tuple `(value,)`, not `tuple(value)`, before any `Sequence` branch runs.

### Pattern 3: PostgreSQL row-value (tuple) comparison for composite watermarks (D-10)

**What:** `WHERE (c1, c2) > (%s, %s)` — native lexicographic comparison, documented PostgreSQL
behavior (row constructor comparison, compares element-by-element left to right, exactly matching
Python tuple comparison semantics). No extension, no custom operator needed.
**When to use:** F03 composite extract filter.
**Example (grounded in the exact current builder shape, etl.py:587-600):**
```python
# Source: pycopg/etl.py:587-600, extended for the composite case
def _build_incremental_extract_sql(source, column, schema="public", watermark=None, *, inclusive=False):
    # column may now be a tuple[str, ...] (composite) or a str (scalar, unchanged)
    is_composite = isinstance(column, tuple)
    validate_identifiers(*column) if is_composite else validate_identifiers(column)
    op = ">=" if inclusive else ">"
    if watermark is None:
        ...  # unchanged full-select path
    if is_composite:
        cols_sql = "(" + ", ".join(column) + ")"
        placeholders = "(" + ", ".join(["%s"] * len(column)) + ")"
        clause = f"WHERE {cols_sql} {op} {placeholders}"
        params = list(watermark)  # watermark is an ordered tuple of scalars
    else:
        clause = f"WHERE {column} {op} %s"
        params = [watermark]
    ...
```

### Pattern 4: Session-scoped advisory lock on a dedicated connection (D-14/D-15)

**What:** Open a connection distinct from the run-log connections and the load-transaction
connection, acquire the lock as the very first action in `run()`, release it in a `finally` that
wraps the entire method body.
**When to use:** F04.
**Example (verified function signatures against live PostgreSQL 18.4 in this session):**
```python
# New queries.py constants (discretion — follow existing ETL_* naming):
ETL_ADVISORY_LOCK = "SELECT pg_advisory_lock(hashtextextended(%s, 0))"
ETL_ADVISORY_TRY_LOCK = "SELECT pg_try_advisory_lock(hashtextextended(%s, 0))"
ETL_ADVISORY_UNLOCK = "SELECT pg_advisory_unlock(hashtextextended(%s, 0))"

# Sync run() — sketch of the lock-wrapping shape (D-14: covers the ENTIRE run, not just the load txn)
def run(self, pipeline: Pipeline, *, dry_run: bool = False) -> RunResult:
    if pipeline.concurrency is None or dry_run:
        return self._run_inner(pipeline, dry_run=dry_run)  # unchanged path, byte-identical

    lock_conn = self._db.connect(autocommit=True).__enter__()
    try:
        cur = lock_conn.cursor()
        if pipeline.concurrency == "skip":
            cur.execute(queries.ETL_ADVISORY_TRY_LOCK, [pipeline.name])
            got = cur.fetchone()[0]
            if not got:
                now = datetime.now(UTC)
                return RunResult(
                    run_id=None, pipeline_name=pipeline.name, status="skipped",
                    rows_extracted=0, rows_loaded=0,
                    started_at=now, finished_at=now, error=None,
                )
        else:  # "wait"
            cur.execute(queries.ETL_ADVISORY_LOCK, [pipeline.name])
        return self._run_inner(pipeline, dry_run=dry_run)
    finally:
        cur.execute(queries.ETL_ADVISORY_UNLOCK, [pipeline.name])
        lock_conn.close()
```
(Exact refactor shape — e.g. whether `run()` is split into an inner helper — is an implementation
detail for planning; the important invariant verified here is that the lock/unlock pair must
wrap `_do_extract` + the transform chain + the load transaction + `_end_run`, matching D-14.)

### Anti-Patterns to Avoid

- **`pg_advisory_xact_lock` for F04:** transaction-scoped — only guards the load transaction,
  leaving the watermark-read/extract race open (the exact race F04 targets). Rejected by D-14;
  do not substitute it even though it auto-releases on commit/rollback (that's the wrong scope,
  not a convenience).
- **Python-side `hash(pipeline.name)` for the lock key:** `PYTHONHASHSEED` is randomized per
  process by default in CPython 3.3+ — two processes would compute different keys and the lock
  would silently fail to serialize. Rejected by D-15; the key MUST be computed server-side via
  `hashtextextended`.
- **Per-column composite max `(max(c1), max(c2))`:** fabricates a watermark tuple no row actually
  has, silently skipping rows whose `c1` advanced but `c2` didn't. Rejected by D-10; always sort
  by key columns and take the actual max row's tuple.
- **`WHERE c1 > %s AND c2 > %s` for composite:** wrong semantics vs. row-value comparison — it
  requires BOTH columns to individually exceed the floor, which is not what a composite
  watermark means (a row where `c1` is unchanged but `c2` increased must still pass). Rejected by
  D-10 in favor of the native tuple compare `(c1,c2) > (%s,%s)`.
- **SQL `%s::interval` for lookback:** couples the builder to a cast that doesn't make sense for
  an integer watermark. Rejected by D-06 in favor of pure-Python subtraction before binding.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-process mutual exclusion | A custom lock table (`SELECT ... FOR UPDATE` on a sentinel row, or a Redis/file lock) | PostgreSQL advisory locks (`pg_advisory_lock`/`pg_try_advisory_lock`) | Already the correct primitive for this exact problem — session-scoped, auto-released on disconnect (verified live in this session), zero extra schema, zero new dependency |
| Deterministic string→int64 hash for the lock key | Python `hashlib.md5(name).digest()[:8]` or similar | `hashtextextended(text, bigint) -> bigint` (core Postgres) | Server-side, identical output for every client/process by construction; a Python-side hash means every process computing its own key (which the `PYTHONHASHSEED` anti-pattern above shows is broken for the built-in `hash()`, and reinventing a stable custom hash is unnecessary work) |
| Composite key row comparison | A hand-rolled `OR`-chain (`c1 > x1 OR (c1 = x1 AND c2 > x2)`) — the textbook manual expansion of tuple comparison | Native PostgreSQL row-value comparison `(c1, c2) > (%s, %s)` | Postgres already implements exactly this lexicographic semantics as a first-class row-constructor comparison; hand-expanding it is more code, easier to get wrong (operator precedence, boundary off-by-ones), and no faster |

**Key insight:** every "hard part" of this phase (mutual exclusion, deterministic hashing, tuple
comparison) already has a first-class, zero-dependency PostgreSQL primitive. The pycopg-side work
is exclusively about correctly *sequencing* existing primitives (lock span, floor resolution
order, envelope tagging) — not implementing new algorithms.

## Common Pitfalls

### Pitfall 1: Lock scope too narrow (transaction-scoped instead of session-scoped)
**What goes wrong:** Using `pg_advisory_xact_lock` (or wrapping only the load transaction) still
lets two processes race on `_read_watermark` → both extract the same batch → both attempt the
upsert. Idempotency (C-01) hides the symptom (no duplicate rows) but the watermark race can still
cause a lost update where a slower process overwrites a newer watermark with a stale one.
**Why it happens:** It's tempting to reuse the existing `self._db.transaction()` context manager
since the codebase already has one for the load step.
**How to avoid:** Acquire the lock on a connection opened before `_read_watermark` is called and
release it only after `_end_run` completes (D-14) — a dedicated `lock_conn`, never the load
transaction's connection.
**Warning signs:** A code review sees `pg_advisory_lock`/`pg_try_advisory_lock` called inside
`with self._db.transaction()` rather than wrapping the whole `run()` body.

### Pitfall 2: `bool` watermark elements skip the allowlist guard in the composite path
**What goes wrong:** The existing `_encode_watermark` bool-before-int check is per-scalar; a
naive composite implementation that does `[_encode_watermark(v) for v in values]` is fine, but a
shortcut that does bulk type inspection (e.g. `all(isinstance(v, (int, str, datetime)) for v in
values)`) will silently accept `bool` values, because `bool` is an `int` subclass — reintroducing
the exact trap C-02/D-04 already closed for the scalar case.
**Why it happens:** Composite validation is new code; it's easy to write a "faster" bulk check
that skips the ordering-sensitive bool-before-int guard.
**How to avoid:** Always reuse `_encode_watermark` per-element for composite values (D-11 already
specifies this: "`_encode` reuses the per-scalar encoder for each element") — never write a
parallel bulk-type check.
**Warning signs:** A composite `Pipeline(initial_watermark=[True, 5])` construction that does NOT
raise `ETLError`/`ValueError`.

### Pitfall 3: Composite max-row computed via per-column `.max()` instead of sorted last row
**What goes wrong:** `{"c1": df["c1"].max(), "c2": df["c2"].max()}` looks like the natural
generalization of the existing scalar `df[col].max()` line, but it fabricates a tuple that may not
correspond to any actual row, and can cause the next run's `WHERE (c1,c2) > (%s,%s)` filter to
silently skip real rows (D-10's explicit warning).
**Why it happens:** The existing scalar capture block (etl.py:1315-1347) is the closest visible
precedent, and its literal `.max()` call is the most obvious thing to "widen" to multiple columns.
**How to avoid:** Sort the raw batch by the composite key columns and take the last row's values
as an ordered tuple — `df.sort_values(list(cols)).iloc[-1][list(cols)]` — never take
per-column maxima independently.
**Warning signs:** A test with two rows `{"day": 1, "seq": 99}` and `{"day": 2, "seq": 1}` — the
correct composite max-row is `(2, 1)` (the row with the greatest `day`), NOT `(2, 99)` (which no
row has).

### Pitfall 4: NULL watermark component in a composite tuple
**What goes wrong:** If any element of a composite watermark tuple is `NULL`/`NaN` in the raw
batch, PostgreSQL's row-value comparison treats a row containing a NULL specially (the comparison
result becomes `NULL`/unknown for that row rather than `TRUE`/`FALSE`), which can silently exclude
rows from the next extract in a way that's hard to detect.
**Why it happens:** The scalar path already guards this (`pd.isna(m)` check before the type
dispatch, etl.py:1325-1330) but a naive composite implementation might only check the *last*
sort column for NaN, missing NaN in an earlier composite column.
**How to avoid:** Apply the existing `pd.isna()` guard to every element of the composite tuple
before encoding; if ANY element is NaN, treat the whole row's watermark as unavailable (fall back
to "record nothing this run", mirroring the existing all-NULL scalar behavior).
**Warning signs:** A composite pipeline with a nullable secondary key column silently drops rows
after a run where that column happened to be NULL in the max row.

### Pitfall 5: `mypy --strict` breakage from widening `incremental_column`
**What goes wrong:** Changing `incremental_column: str | None` to
`incremental_column: str | Sequence[str] | None` (and similarly widening `initial_watermark`)
without adding `@overload` stubs at internal call sites that currently assume a bare `str` (e.g.
`validate_identifiers(self.incremental_column)`) will produce new `mypy --strict` errors — this
gate is BLOCKING per the standing bar.
**Why it happens:** `mypy --strict` narrows unions conservatively; every call site touching the
widened field needs an `isinstance` check (or `cast`) before it can pass a scalar-typed argument
to a function like `validate_identifiers(*names: str)`.
**How to avoid:** After widening the field, run `uv run mypy pycopg` locally before considering
the task done — Phase 46 (mypy-strict) already found 2 latent bugs this way; the same discipline
applies here. Normalize `incremental_column` to `tuple[str, ...]` in `__post_init__` immediately
(mirroring `conflict_columns`) so every downstream consumer sees one type, not a union.
**Warning signs:** New `error: Argument 1 to "validate_identifiers" has incompatible type` lines
in `mypy --strict` output after the D-09 widening.

### Pitfall 6: Forgetting the async `_run_inner`/lock-wrapping mirror
**What goes wrong:** Implementing the advisory-lock wrap only in `ETLAccessor.run()` (sync) and
missing the identical wrap in `AsyncETLAccessor.run()` — the two `run()` implementations are
currently ~280 lines each with zero shared code (full duplication, not a shared helper), so it is
easy to edit one and forget the other.
**Why it happens:** The existing codebase already fully duplicates `run()` between sync/async
(verified in this session: both are near-identical ~280-line blocks) — there is no shared
private helper to change in one place.
**How to avoid:** Treat every `run()` edit as a two-file (same-file, two-class) edit in the same
commit, per C-04/Phase 41 KIND-parity lesson; grep for `def run(` after the change to confirm both
occurrences were touched identically. `test_accessor_parity` will not catch this since both
methods already exist — only careful diffing or a dedicated behavioral test will.
**Warning signs:** `git diff` for the commit shows edits to only one `run()` occurrence in
`etl.py`.

## Code Examples

### F01 — seed-floor fallback (grounded in the exact current `_read_watermark`, etl.py:1007-1045)

```python
# Source: pycopg/etl.py:1039-1045 (current) — the exact insertion point for D-01's fallback
with self._db.connect(autocommit=True) as conn:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(queries.ETL_GET_LAST_WATERMARK, [name])
        row = cur.fetchone()
if row is None or row["watermark"] is None:
    return None   # <-- D-01: change to `return pipeline.initial_watermark` when set
return _decode_watermark(row["watermark"])
```
Note `_read_watermark` currently takes only `name: str` — implementing D-01 requires either
passing `pipeline.initial_watermark` in as a new parameter, or moving the fallback to the call
site in `run()`/`_do_extract` (both call sites already have `pipeline` in scope). Either is a
valid implementation choice; the call-site fallback (`wm = self._read_watermark(name) or
pipeline.initial_watermark` — with a caveat that a falsy-but-valid watermark like `0` must not be
treated as absent, so use `is None` not truthiness) avoids touching `_read_watermark`'s signature
at all and is the smaller diff.

### F02 — lookback arithmetic (grounded in the exact current max-capture dispatch, etl.py:1315-1347)

```python
# Source: pycopg/etl.py:1331-1347 (current type dispatch) — the pattern D-06 reuses for lookback
elif isinstance(m, pd.Timestamp):
    raw_watermark = m.to_pydatetime()          # plain datetime, offset preserved
elif isinstance(m, str):
    raw_watermark = str(m)                     # normalize numpy.str_ -> str
elif pd.api.types.is_float(m):
    raise ETLError(...)                        # float has no defined watermark semantics
else:
    raw_watermark = int(m)                     # numpy.int64 -> plain int

# D-06 lookback subtraction happens on the READ FLOOR (before extract), using the same
# three-way type dispatch on the stored/seeded floor value:
if pipeline.incremental_lookback is not None:
    if isinstance(floor, datetime):
        read_floor = floor - pipeline.incremental_lookback   # timedelta subtraction
    elif isinstance(floor, int):
        read_floor = floor - pipeline.incremental_lookback   # int subtraction
    else:  # str
        raise ETLError(
            f"incremental_lookback cannot be applied to a str-typed watermark "
            f"({floor!r}); lookback requires a datetime or int watermark"
        )
else:
    read_floor = floor
```

### F03 — composite envelope shape (extends the frozen tag dispatch, etl.py:656-688)

```python
# Source: pycopg/etl.py:676-688 (current _decode_watermark) — D-11 adds one new branch
def _decode_watermark(envelope):
    tag = envelope["type"]
    value = envelope["value"]
    if tag == "datetime":
        return datetime.fromisoformat(value)
    if tag == "int":
        return int(value)
    if tag == "str":
        return str(value)
    if tag == "composite":                       # D-11 new tag
        return tuple(
            _decode_watermark(v) for v in envelope["values"]
        )
    raise ETLError(f"Unknown watermark type tag {tag!r} ...")
```

### F04 — verified live PostgreSQL behavior (this session, PostgreSQL 18.4)

```sql
-- Confirmed via \df in a live psql session against localhost PostgreSQL 18.4:
-- pg_catalog.hashtextextended(text, bigint) -> bigint      (1 overload)
-- pg_catalog.pg_advisory_lock(bigint) -> void              (+ (int,int) overload)
-- pg_catalog.pg_try_advisory_lock(bigint) -> boolean       (+ (int,int) overload)
-- pg_catalog.pg_advisory_unlock(bigint) -> boolean         (+ (int,int) overload)

-- Empirical two-session test performed in this session:
-- Session A: SELECT pg_advisory_lock(hashtextextended('nightly_test_lock2', 0)); SELECT pg_sleep(5);
-- Session B (while A holds):  SELECT pg_try_advisory_lock(hashtextextended('nightly_test_lock2', 0));
--   -> returned FALSE (correctly blocked)
-- After Session A's connection closed (sleep ended, psql -c exited):
-- Session B: SELECT pg_try_advisory_lock(hashtextextended('nightly_test_lock2', 0));
--   -> returned TRUE (lock auto-released on disconnect — confirms D-14's crash-safety premise)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| Fixed exclusive `>` watermark boundary, single-column only, no first-run bound, no concurrency guard | Configurable `>=`/lookback, composite multi-column key, `initial_watermark` seed, opt-in advisory-lock concurrency | This phase (v1.1.0 Phase 49, first release after v1.0.0's SemVer freeze) | Turns the v0.7.0 incremental-ETL MVP into a production-hardenable feature set without any breaking change — every knob defaults to today's exact behavior |

**Deprecated/outdated:** Nothing in this phase deprecates prior behavior — all four features are
strictly additive per the frozen SemVer 1.0 contract (REQUIREMENTS.md Out-of-Scope: "Any breaking
change to a public signature").

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The exact line numbers cited throughout this document (e.g. etl.py:1315-1347 for sync, :2011-2043 for async) reflect the file as read in this research session (2179 total lines) and may drift by a handful of lines once Phase 49's own edits begin — treat as "this session's snapshot," not an immutable contract. | Code Examples, Phase Requirements | Low — the planner should re-grep for the named functions/comments (e.g. `# 1b. INCREMENTAL WATERMARK CAPTURE`) rather than trust absolute line numbers if the file has already been touched by an earlier wave |
| A2 | The suggested `run()` refactor shape in Pattern 4 (an `_run_inner` extraction to avoid duplicating the ~280-line body under the lock) is ONE valid implementation approach, not a locked design — CONTEXT.md's D-14 only requires the lock to span the whole method, not a specific refactor shape. | Architecture Patterns / Pattern 4 | Low — if the planner instead chooses to wrap the existing method body in a `try/finally` without extracting a helper, that also satisfies D-14; either is acceptable, this doc's sketch is illustrative only |
| A3 | `hashtextextended` has been part of core PostgreSQL since 9.x per training-data recollection; this was NOT independently re-verified against release notes in this session (only its *current* presence/signature on PostgreSQL 18.4 was verified live). | Standard Stack, Don't Hand-Roll | Low — irrelevant in practice since the project's supported PostgreSQL versions (per README/pyproject) are all well past 9.x; flagged only because the "since 9.x" historical claim itself is `[ASSUMED]`, not verified this session |

**If this table is empty:** N/A — see entries above; all are low-risk provenance notes, not
decisions requiring user reconfirmation (the CONTEXT.md decisions D-01..D-15 themselves are
already locked and out of scope for renegotiation).

## Open Questions

1. **Should `_read_watermark`'s signature change to accept `pipeline` instead of `name: str`?**
   - What we know: Implementing D-01 (seed fallback) needs `pipeline.initial_watermark` available
     somewhere in the watermark-read path; `_read_watermark(self, name: str)` currently only takes
     the pipeline name.
   - What's unclear: Whether to (a) widen `_read_watermark`'s signature to take the whole
     `pipeline` object, or (b) keep it name-only and apply the seed fallback at each of the two
     call sites (`run()` and the `dry_run` fork) after calling it.
   - Recommendation: Prefer (b) — smaller diff, and `_read_watermark` stays a pure "what does the
     DB say" query, keeping its existing unit tests valid unchanged. The planner should confirm
     this choice explicitly in the plan since it affects which existing tests need updating.

2. **Exact `queries.py` constant names for the advisory-lock SQL.**
   - What we know: D-15 fixes the SQL shape (`pg_try_advisory_lock(hashtextextended(%s, 0))` /
     `pg_advisory_lock(...)` / `pg_advisory_unlock(...)`); CONTEXT.md leaves the naming to
     discretion, "follow existing `ETL_*` style."
   - What's unclear: Whether to use `ETL_ADVISORY_LOCK`/`ETL_ADVISORY_TRY_LOCK`/
     `ETL_ADVISORY_UNLOCK` (suggested in this document) or some other naming.
   - Recommendation: Use the three names suggested in Pattern 4 above — they follow the existing
     `ETL_<VERB>_<NOUN>` convention (`ETL_GET_LAST_WATERMARK`, `ETL_UPDATE_RUN_WATERMARK`) closely
     enough that any reasonable planner choice will pass review.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|--------------|-----------|---------|----------|
| PostgreSQL core function `hashtextextended(text, bigint)` | F04 lock-key derivation (D-15) | ✓ (verified live) | PostgreSQL 18.4 (`pg_catalog`, no extension) | — (core function, always present on any supported PostgreSQL version) |
| PostgreSQL core function `pg_advisory_lock(bigint)` | F04 `"wait"` mode (D-12/D-14) | ✓ (verified live) | PostgreSQL 18.4 (`pg_catalog`) | — |
| PostgreSQL core function `pg_try_advisory_lock(bigint)` | F04 `"skip"` mode (D-12/D-13) | ✓ (verified live) | PostgreSQL 18.4 (`pg_catalog`) | — |
| PostgreSQL core function `pg_advisory_unlock(bigint)` | F04 lock release (D-14 `finally`) | ✓ (verified live) | PostgreSQL 18.4 (`pg_catalog`) | — |
| Two live DB sessions/connections | Integration test for F04's held-lock path (a single test process needs to simulate two concurrent sessions) | ✓ (confirmed feasible — this session opened two `psql` connections directly; pycopg's `db.connect(autocommit=True)` can open a second connection identically from within one test process) | — | — |
| `PGDATABASE=pycopg_test3` | All DB/parity/coverage test runs (project memory: default `pycopg_test`/`pycopg_test2` broken by TimescaleDB `.so` drift) | ✓ (`pycopg_test3` confirmed present via `\l` in this session) | — | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none — every dependency for this phase is a core
PostgreSQL built-in already required by the project's existing supported-PostgreSQL floor.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7.0.0+ with pytest-asyncio (auto mode) and pytest-cov |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (line ~95) |
| Quick run command | `PGDATABASE=pycopg_test3 uv run pytest tests/test_etl.py -x -q -o addopts=""` |
| Full suite command | `PGDATABASE=pycopg_test3 uv run pytest` (runs the full `--cov-fail-under=95` gate) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ETL-INC-F01 | `initial_watermark` seeds the first run's floor; ignored after first success; construction guards (requires `incremental_column`, type/allowlist, composite length match) | unit (mock SQL-shape) + integration (live-DB two-run sequence) | `PGDATABASE=pycopg_test3 uv run pytest tests/test_etl.py -k initial_watermark -x -q -o addopts=""` | ❌ Wave 0 — new `TestPipeline` cases + new `TestInitialWatermark` integration class |
| ETL-INC-F02 | `incremental_inclusive=True` emits `>=`; `incremental_lookback` subtracts before binding but never regresses the recorded max; `str` watermark + lookback raises `ETLError` at runtime | unit (`_build_incremental_extract_sql` SQL-shape assertions) + integration (live-DB floor/record divergence check) | `PGDATABASE=pycopg_test3 uv run pytest tests/test_etl.py -k "inclusive or lookback" -x -q -o addopts=""` | ❌ Wave 0 — extend `TestBuildIncrementalExtractSql` + new integration class |
| ETL-INC-F03 | Composite `incremental_column` tuple produces `(c1,c2) > (%s,%s)`; recorded watermark is the true max ROW not per-column maxima; `"composite"` envelope round-trips; single-column path is byte-identical (regression) | unit (SQL-shape + envelope round-trip) + integration (multi-row DataFrame, verify correct row selected as max) | `PGDATABASE=pycopg_test3 uv run pytest tests/test_etl.py -k composite -x -q -o addopts=""` | ❌ Wave 0 — new `TestCompositeWatermark` class(es) |
| ETL-INC-F04 | `concurrency="wait"` serializes two overlapping runs; `concurrency="skip"` returns `status="skipped"`, `run_id=None`, writes no `pipeline_runs` row, when the lock is already held; lock is released even on an exception mid-run (crash-safety) | unit (SQL-shape for the three new `ETL_ADVISORY_*` constants) + integration (two real DB connections/sessions exercising the held-lock path, per Environment Availability) | `PGDATABASE=pycopg_test3 uv run pytest tests/test_etl.py -k advisory -x -q -o addopts=""` | ❌ Wave 0 — new `TestAdvisoryLock` class using two `db.connect(autocommit=True)` handles |
| Standing bar — sync/async parity | Every new `Pipeline` field is usable and behaviorally identical from both `db.etl.run()` and `async_db.etl.run()` | automated (existing generic parity test, no new registration needed since no new accessor method is added — only `Pipeline` fields) | `PGDATABASE=pycopg_test3 uv run pytest tests/test_parity.py -k etl -x -q -o addopts=""` | ✅ existing `test_accessor_parity`/`test_accessor_parameter_kind_parity` already parametrize over `(ETLAccessor, AsyncETLAccessor)` |
| Standing bar — injection safety | Every new/extended builder path (composite tuple compare, advisory-lock key bind, lookback bind) rejects a malicious identifier before any interpolation and never interpolates a bound value | unit (dedicated `InvalidIdentifierError` tests per new path, mirroring existing `test_invalid_column_raises` etc.) | `PGDATABASE=pycopg_test3 uv run pytest tests/test_etl.py -k invalid -x -q -o addopts=""` | ❌ Wave 0 — extend existing injection-test classes with composite/lock-key cases |
| Standing bar — mypy-strict | Widened `incremental_column`/`initial_watermark` unions and new `concurrency`/`incremental_lookback` fields produce 0 `mypy --strict` errors | automated static check | `uv run mypy pycopg` | ✅ existing config, no new file needed |
| Standing bar — coverage ratchet ≥95% | All new branches (seed fallback, lookback dispatch, composite tag, lock skip/wait paths) are exercised | automated (part of full suite run) | `PGDATABASE=pycopg_test3 uv run pytest` (reads `--cov-fail-under=95` from pyproject.toml) | ✅ existing gate |

### Sampling Rate

- **Per task commit:** `PGDATABASE=pycopg_test3 uv run pytest tests/test_etl.py -x -q -o addopts=""` (targeted, per project memory's flaky-full-suite note — avoids the known 2-3 pre-existing flaky DB tests unrelated to this phase)
- **Per wave merge:** `PGDATABASE=pycopg_test3 uv run pytest` (full suite, coverage gate)
- **Phase gate:** Full suite green + `uv run mypy pycopg` clean before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_etl.py::TestInitialWatermark` — new class covering F01 seed-floor construction guards + first-run/second-run sequence (mock + live-DB)
- [ ] `tests/test_etl.py::TestBuildIncrementalExtractSql` extensions — new cases for `incremental_inclusive=True` (`>=`) and lookback-adjusted floor SQL shape (F02)
- [ ] `tests/test_etl.py::TestCompositeWatermark` — new class: composite `_build_incremental_extract_sql` tuple-compare SQL shape, composite envelope encode/decode round-trip, and the "sorted last row, not per-column max" correctness case (F03)
- [ ] `tests/test_etl.py::TestAdvisoryLock` — new class: SQL-shape assertions for the three new `ETL_ADVISORY_*` constants, plus a live two-connection integration test exercising `"skip"` returning `status="skipped"` while a lock is held, and a `"wait"` serialization test (F04)
- [ ] Injection-test additions to existing classes — composite column list, advisory-lock name bind, lookback value bind (standing bar)
- [ ] No new test framework/config needed — pytest + pytest-asyncio + pytest-cov already fully wired

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|----------------|---------|-------------------|
| V2 Authentication | no | Not touched by this phase — no auth surface |
| V3 Session Management | no | Not applicable — "session" here means a raw DB connection, not a user session |
| V4 Access Control | no | Not touched — advisory locks are a concurrency primitive, not an authorization boundary |
| V5 Input Validation | yes | `validate_identifiers` (existing, `pycopg/utils.py:120`) applied to every composite column name before interpolation (D-09/D-10); every user-supplied value (watermark scalars, lookback amounts, pipeline name for the lock key) bound as `%s` — never f-string interpolated |
| V6 Cryptography | no | `hashtextextended` is a non-cryptographic hash used purely for lock-key derivation, not a security control — collision would only cause two differently-named pipelines to (rarely) share a lock, a correctness/perf concern, not a security one |

### Known Threat Patterns for pycopg (this stack: Python + psycopg + PostgreSQL)

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|-----------------------|
| SQL injection via a composite column name (F03) | Tampering | `validate_identifiers(*column)` on every element of the composite tuple before any string interpolation into the `(c1, c2) > (%s, %s)` clause — extends the existing pattern already used for the scalar `column` argument |
| SQL injection via the pipeline name used as the advisory-lock key (F04) | Tampering | Pipeline name is ALWAYS bound as `%s` to `hashtextextended(%s, 0)` — never string-interpolated into the SQL text (D-15 explicit requirement); `Pipeline.name` itself has no identifier-validation requirement today (it is never used as a raw SQL identifier, only as a bound value or as `pipeline_name` column data), so no NEW validation is needed beyond the existing bound-parameter discipline |
| Denial of service via an unreleased advisory lock (a crashed/killed process holding a lock forever) | Denial of Service | Session-scoped lock on a dedicated connection with `finally`-guaranteed unlock; empirically verified in this session that PostgreSQL auto-releases a session-scoped advisory lock immediately when the holding connection closes for ANY reason (including an ungraceful process kill) — this is a PostgreSQL server guarantee, not something pycopg must implement itself |
| Watermark tampering via a crafted `initial_watermark`/`incremental_lookback` causing an oversized re-scan (resource exhaustion) | Denial of Service (low severity) | Not a new attack surface beyond what `extract_limit` already exists to bound — `initial_watermark`/`incremental_lookback` are `Pipeline` construction-time values set by the pipeline's own operator/developer, not untrusted end-user input; no additional mitigation beyond the existing type/allowlist guards is warranted |

## Sources

### Primary (HIGH confidence)
- Live PostgreSQL 18.4 instance (`localhost`, via `psql`) — `\df hashtextextended`, `\df pg_advisory_lock`, `\df pg_try_advisory_lock`, `\df pg_advisory_unlock` — confirmed signatures and return types directly in this session.
- Live PostgreSQL 18.4 two-session empirical test (this session) — confirmed session-scoped advisory-lock mutual exclusion (`pg_try_advisory_lock` returns `false` while held) and confirmed auto-release on connection close (`pg_try_advisory_lock` returns `true` immediately after the holding session's connection ends).
- `/home/loc/workspace/pycopg/pycopg/etl.py` (read in full, 2179 lines, this session) — exact current shape of `Pipeline`, `__post_init__`, `_validate_incremental`, `RunResult`, `_build_incremental_extract_sql`, `_encode_watermark`/`_decode_watermark`, `_read_watermark` (sync+async), `_do_extract` (sync+async), `run()` (sync+async), `_end_run` (sync+async).
- `/home/loc/workspace/pycopg/pycopg/queries.py` (lines 300-404 read, this session) — exact current `ETL_INIT_PIPELINE_RUNS` status CHECK, `ETL_GET_LAST_WATERMARK`, `ETL_UPDATE_RUN_WATERMARK`.
- `/home/loc/workspace/pycopg/pycopg/exceptions.py` (read in full, this session) — confirmed `ETLError`/`ETLTransformError`/`ETLTargetNotFoundError` hierarchy; confirmed no new exception class is needed (D-06's runtime lookback-on-str guard and D-04's bool/float allowlist both already raise `ETLError`).
- `/home/loc/workspace/pycopg/pycopg/utils.py` (lines 120-136 read, this session) — exact current `validate_identifiers(*names: str)` signature.
- `/home/loc/workspace/pycopg/tests/test_etl.py` and `/home/loc/workspace/pycopg/tests/test_parity.py` (read, this session) — confirmed existing test structure, mock SQL-shape conventions, envelope round-trip test patterns, `ACCESSOR_PAIRS` registry already includes `(ETLAccessor, AsyncETLAccessor)`.
- `/home/loc/workspace/pycopg/pyproject.toml` (read, this session) — confirmed pytest/coverage/mypy configuration (`--cov-fail-under=95`, `mypy strict = true`).
- `.planning/phases/49-incremental-etl-follow-ups/49-CONTEXT.md`, `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/STATE.md` — read in full, this session.

### Secondary (MEDIUM confidence)
- None — every claim in this document was either directly verified against the live PostgreSQL instance/codebase in this session, or is explicitly logged in the Assumptions Log above.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new dependencies; every function used was confirmed live against PostgreSQL 18.4 in this session.
- Architecture: HIGH — every extension point (5 pure functions + `Pipeline.__post_init__`) was read in full from the actual current `etl.py`, not reconstructed from CONTEXT.md's line-number citations alone.
- Pitfalls: HIGH — all six pitfalls are grounded in specific, re-verified lines of the existing codebase (e.g. the bool-before-int trap, the `pd.isna()` guard ordering, the full sync/async duplication of `run()`) rather than generic ETL folklore.

**Research date:** 2026-07-03
**Valid until:** 30 days (stable internal-extension research; PostgreSQL advisory-lock semantics and `hashtextextended` are long-stable core features unlikely to change within the pycopg v1.1.0 development window)
