# Phase 27: Incremental ETL — Run-Log Integration - Research

**Researched:** 2026-06-20
**Domain:** Run-log persistence of incremental watermarks (pandas scalar coercion + psycopg3 JSONB round-trip + live-DB integration invariants)
**Confidence:** HIGH (every code claim cited to file:line; every type/round-trip claim verified by live experiment against `pycopg_test`)

## Summary

Phase 27 wires the Phase-26 typed watermark envelope through the sync run-log layer and proves four success-only persistence invariants against a real PostgreSQL DB. The pure encoder/decoder (`_encode_watermark`/`_decode_watermark`) already exist and are frozen [VERIFIED: etl.py:580,629]; the `watermark JSONB` column already exists and has been reserved-NULL since v0.5.0 [VERIFIED: queries.py:260]. So this phase is **three small, well-bounded additions**: (1) a `_read_watermark(name)` method mirroring the existing autocommit `dict_row` run-log pattern; (2) a watermark write on the **success path only** of `_end_run`; and (3) a minimal `max(col)` capture from the raw batch in sync `run()`, gated on `pipeline.incremental_column`, with a D-06 missing-column `ETLError`.

The central empirical question (D-07 type coercion) is **resolved by experiment** (see Code Examples §1). `df[col].max()` returns: `numpy.int64` for integer columns (**fails** the strict `{datetime, int, str}` allowlist — `isinstance(np.int64(5), int)` is `False`); `pandas.Timestamp` for datetime columns (**passes** — `Timestamp` is a `datetime` subclass); plain `str` for text columns on this pandas version (**passes**). Because the integer case fails and the others return non-plain subclasses that should not be persisted raw, the correct, minimal, frozen-contract-preserving fix is **call-site coercion** per column type before handing the value to `_encode_watermark` — exactly the D-07 "preferred direction." Do NOT re-open the Phase-26 encoder.

The JSONB write/read round-trip is **verified end-to-end against `pycopg_test`** (see Code Examples §2): bind `Jsonb(_encode_watermark(value))` as a `%s` param; the read side yields a plain Python `dict` straight from the JSONB column (no `json.loads`/`json.dumps` needed); datetime offset and microseconds survive intact. One subtlety surfaced: a timestamptz **read back through `to_dataframe`** is normalized to UTC by psycopg/pandas (offset `+00:00`), independent of the envelope — the envelope preserves whatever offset the Timestamp carries, so the round-trip test must assert against the *coerced* value, not a hand-written literal.

**Primary recommendation:** Add `_read_watermark` + a dedicated success-path UPDATE constant + a `_end_run(watermark=None)` keyword that binds `Jsonb(...)` only when non-None; capture `max(col)` right after extract at `etl.py:1108` with `int()/.to_pydatetime()/str()` coercion and a D-06 guard; prove the 4 invariants in `tests/test_etl_accessor.py` reusing the `db`/`cleanup_pipeline_runs`/`etl_table` fixtures. Keep WR-01/WR-02 decode-hardening **deferred to Phase 28** (rationale below).

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ETL-INC-02 | First run: full load + record `max(incremental_column)` as watermark on success | `max(col)` capture at `etl.py:1108` (Code Examples §1) + success-path `_end_run(watermark=)` (Code Examples §3); `_read_watermark` returns `None` first run (D-04) |
| ETL-INC-05 | Empty batch: `status='success'`, `rows_loaded=0`, prior watermark preserved (no NULL) | Empty-batch early-return at `etl.py:1138` passes **no** watermark; D-03 success-only read query auto-skips it. Pitfall 2 |
| ETL-INC-06 | Watermark read from last **successful** run; persisted only on success; failed run does not advance | New `ETL_GET_LAST_WATERMARK` (`status='success' AND watermark IS NOT NULL`); failed `_end_run` at `etl.py:1199` passes no watermark → column stays NULL. Pitfall 1 |
| ETL-INC-10 | Watermark round-trips through JSONB for timestamp/int/text, no type/tz drift, zero new deps | Verified live (Code Examples §2): `Jsonb(env)` write, plain-`dict` read, offset+µs preserved. Zero new deps (`psycopg.types.json.Jsonb` already shipped) |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `max(col)` compute + type coercion | Application (pandas, in `run()`) | — | High-water mark is a pure in-memory computation on the extracted DataFrame; D-02 fixes it *before* transforms |
| Watermark encode → JSONB bind | Application (psycopg adapter) | Database (storage) | `Jsonb()` is the psycopg3 write-side adapter; envelope is application-defined |
| Watermark read + decode | Database (JSONB read) | Application (decode) | DB returns a plain `dict`; app rebuilds the typed scalar |
| Success-only persistence invariant | Database (autocommit txn isolation) | Application (call-site gating) | The dedicated autocommit connection guarantees the run row commits independently of the load txn (existing pattern, `etl.py:762`) |

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01**: Pull a *minimal* happy-path `max(col)` + `_end_run(watermark=)` persist into sync `run()` this phase. Phase 27 still does a **full (unfiltered) load every run** — only the persist+read halves are wired.
- **D-02**: Watermark computed from the **RAW extracted batch, before the transform chain** — capture `df[col].max()` immediately after extract (`etl.py:1108`), before the transform loop at `etl.py:1113`.
- **D-03**: `_read_watermark` reads the last run that is `status='success'` AND `watermark IS NOT NULL`, newest-first. Failed runs and empty-batch successes are auto-skipped by the query — empty-batch-preserves falls out for free.
- **D-04**: `_read_watermark(name)` returns the decoded scalar or `None` (first run / never-succeeded-with-watermark). Consumed by the Phase-28 extract filter; in Phase 27 it exists, is tested, **not yet applied as a WHERE bound**.
- **D-05**: `Jsonb()` wrap at the write-site — `from psycopg.types.json import Jsonb` (NOT imported yet, `etl.py:35`). Success path binds `Jsonb(_encode_watermark(value))` as the new `watermark` `%s` param. Failed/empty run passes no watermark (column stays NULL).
- **D-06**: Raise a clear `ETLError` (not bare `KeyError`) when `incremental_column` is absent from the raw batch. Cheap, at the `df[col].max()` site. Applies only when `pipeline.incremental_column` is set.

### Claude's Discretion
- **D-07**: Planner decides the coercion site after testing. Constraint: the value handed to `_encode_watermark` MUST satisfy `{datetime, int, str}`. Preferred direction: coerce at the `run()` call-site (`pd.Timestamp.to_pydatetime()`, `int(np_int)`) and leave the frozen Phase-26 helper untouched. **Do NOT re-open `_encode_watermark` unless call-site coercion proves insufficient.** → *Research finding: call-site coercion is sufficient and correct; see Code Examples §1.*
- `_read_watermark` placement: method on `ETLAccessor` vs helper — follow existing run-log method placement (`_start_run`/`_end_run`/`_fetch_run_result` are methods using a dedicated `db.connect(autocommit=True)`). → *Recommend: method on `ETLAccessor`.*
- Extend `ETL_UPDATE_RUN` to set `watermark` vs a dedicated success-path UPDATE constant — planner chooses. Constraint: the failed path must NOT touch `watermark`; success sets it only when a watermark exists. → *Recommend: dedicated constant; tradeoff in Architecture Patterns §Pattern 2.*
- Exact integration-test placement — `tests/test_etl_accessor.py` is the live-DB file; extend `test_run_writes_full_row` conventions.
- Docstring wording — numpydoc shallow, `interrogate ≥ 95`.

### Deferred Ideas (OUT OF SCOPE — Phase 28+)
- `WHERE incremental_column > last_watermark` extract wiring (ETL-INC-03).
- `RunResult.watermark_used` / `watermark_recorded` (ETL-INC-07) + `history()`/`last_run()` surfacing (ETL-INC-08). **`_row_to_result` keeps dropping `watermark`** (`etl.py:691`); leave `RunResult` unchanged.
- `dry_run` incremental support (ETL-INC-09).
- `AsyncETLAccessor` incremental mirror + `TestEtlParity` (ETL-INC-11). **Do not touch `AsyncETLAccessor`** (`etl.py:1214`).
- Incremental docs / backfill workflow (ETL-INC-12).
- *Formal* ETL-INC-04 missing-column treatment — Phase 28 owns it; Phase 27 ships only the minimal D-06 guard.
- `float` watermark support; naive-datetime rejection; `initial_watermark` (all deferred).

## Standard Stack

No new packages. Everything needed already ships.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `psycopg` (psycopg3) | 3.x (already a dep) | `psycopg.types.json.Jsonb` write adapter; plain-`dict` JSONB read | Native JSONB adaptation; no manual `json.dumps`/`json.loads` [VERIFIED live, Code Examples §2] |
| `pandas` | already a dep | `df[col].max()` high-water mark | Already the extract DataFrame type [VERIFIED: etl.py:34] |

**Installation:** None. ETL-INC-10 explicitly requires **zero new runtime dependencies** [CITED: REQUIREMENTS.md:42]. `from psycopg.types.json import Jsonb` is the only new import; psycopg is already pinned.

**Version verification:**
```
$ uv run python -c "import psycopg; print(psycopg.__version__)"
```
psycopg3 ships `psycopg.types.json.Jsonb` — confirmed importable and functional in the live experiment (Code Examples §2).

## Package Legitimacy Audit

No external packages are installed by this phase (zero-new-deps requirement). `Jsonb` is a submodule of the already-pinned `psycopg` distribution. **Slopcheck/registry audit N/A.**

## Architecture Patterns

### System Architecture Diagram

```
                 db.etl.run(pipeline)  [sync only]
                          │
                          ▼
                   _start_run(name) ──► pipeline_runs row (status='running')   [autocommit conn]
                          │
          ┌───────────────┴───────────────────────────────┐
          ▼                                                 │
   1. EXTRACT (full, unfiltered)                            │
      df = to_dataframe(source)                             │  on ANY exception
          │                                                 ▼
          ▼  ── if pipeline.incremental_column set:   _end_run(status='failed',     ──► watermark stays NULL
   ┌─────────────────────────────┐                          watermark NOT passed)        (no-advance-on-failure)
   │ if col not in df.columns:    │  D-06
   │     raise ETLError(...)      │
   │ raw_max = df[col].max()      │  D-02 (BEFORE transforms)
   │ wm = coerce(raw_max)         │  D-07  int()/.to_pydatetime()/str()
   └─────────────────────────────┘
          │
          ▼
   2. TRANSFORM CHAIN  (mutates df; raw_max already captured)
          │
          ▼
   3. rows = df → records
          │
     ┌────┴─── empty batch? ──► _end_run(success, rows_loaded=0,  ──► NO watermark passed
     │                            watermark NOT passed)                (D-03 read query skips it → prior preserved)
     ▼ non-empty
   4-6. existence check + build load SQL + ATOMIC LOAD (session+transaction)
          │
          ▼
   _end_run(status='success', watermark=Jsonb(_encode_watermark(wm)))  ──► watermark JSONB column set
                                                                            [autocommit conn]

   _read_watermark(name):   SELECT watermark FROM pipeline_runs
                            WHERE pipeline_name=%s AND status='success' AND watermark IS NOT NULL
                            ORDER BY started_at DESC LIMIT 1
                            → dict_row → _decode_watermark(row['watermark']) → scalar | None
                            (Phase 27: exists + tested; NOT yet applied as a filter)
```

### Component Responsibilities

| File | Change | Cite |
|------|--------|------|
| `pycopg/etl.py` (imports) | add `from psycopg.types.json import Jsonb` | `etl.py:35` (NOT present) |
| `pycopg/etl.py` `_end_run` | add `watermark: dict | None = None` kwarg; choose success-vs-update SQL; bind `Jsonb(watermark)` when non-None | `etl.py:794` |
| `pycopg/etl.py` `_read_watermark` (NEW method) | dedicated autocommit `dict_row` read + `_decode_watermark` | new, modeled on `last_run` `etl.py:902` |
| `pycopg/etl.py` `run()` | `max(col)` capture + D-07 coercion + D-06 guard after `rows_extracted = len(df)` at line 1108; pass `watermark=` to the success `_end_run` at line 1210 | `etl.py:1108`, `:1138`, `:1199`, `:1210` |
| `pycopg/queries.py` | new `ETL_GET_LAST_WATERMARK` + (recommended) `ETL_UPDATE_RUN_WATERMARK` | `queries.py:289` (shape to mirror) |
| `tests/test_etl_accessor.py` | 4 live-DB invariant tests | extend `TestRunPipelineIntegration` `:446` |
| `tests/test_etl.py` | (optional) DB-free coercion-helper unit if a helper is extracted | `:629` |

### Pattern 1: Dedicated autocommit `dict_row` read (template for `_read_watermark`)
**What:** A short-lived autocommit connection with the `dict_row` factory, independent of any load transaction.
**When to use:** Every run-log read/write — guarantees the watermark commits/reads independently of the load txn.
**Example:** Copy `last_run`'s body exactly, swap the query and add a decode:
```python
# Source: pycopg/etl.py:902-926 (last_run) — the verbatim template
def _read_watermark(self, name: str):
    with self._db.connect(autocommit=True) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(queries.ETL_GET_LAST_WATERMARK, [name])
            row = cur.fetchone()
    if row is None or row["watermark"] is None:
        return None
    return _decode_watermark(row["watermark"])
```
`row["watermark"]` is a plain Python `dict` (verified live — JSONB reads yield `dict`, Code Examples §2). `SELECT watermark` (not `SELECT *`) keeps the read narrow.

### Pattern 2: Success-only watermark UPDATE — dedicated constant (recommended)
**What:** Keep the existing `ETL_UPDATE_RUN` untouched for the failed/empty paths; add a parallel `ETL_UPDATE_RUN_WATERMARK` that also sets `watermark = %s`.
**Tradeoff:**
- *Dedicated constant (recommend):* The failed/empty UPDATE is **structurally incapable** of touching `watermark` — the no-advance-on-failure invariant is enforced by the SQL, not by a runtime branch. Cost: one extra constant + a branch in `_end_run`.
- *Extend `ETL_UPDATE_RUN` with a `watermark=%s`:* Single constant, but every caller (including failed/empty) must now pass an explicit `NULL`/value, and an accidental non-NULL on the failed path silently violates ETL-INC-06. More foot-gun.
**Recommendation:** Dedicated constant. In `_end_run`, branch: `watermark is None` → existing `ETL_UPDATE_RUN`; else `ETL_UPDATE_RUN_WATERMARK` binding `Jsonb(watermark)` as an extra trailing param before `run_id`.

### Anti-Patterns to Avoid
- **Computing `max(col)` after transforms.** D-02 forbids it — the transform chain (`etl.py:1113`) may rename/drop the column. Capture at `etl.py:1108`.
- **Passing the raw `numpy.int64` to `_encode_watermark`.** It raises `ETLError('unsupported watermark type int64')` [VERIFIED live, Code Examples §1]. Coerce with `int()` first.
- **`json.dumps`-ing the envelope before `Jsonb()`.** Double-encoding — `Jsonb` adapts the dict itself; the column then stores a JSON *string*, not an object. [VERIFIED: live round-trip needs no manual json, Code Examples §2].
- **Touching `_row_to_result` / `RunResult`.** That is ETL-INC-07 (Phase 28). `_row_to_result` deliberately drops `watermark` [VERIFIED: etl.py:691].
- **Touching `AsyncETLAccessor`** (`etl.py:1214`) — ETL-INC-11, Phase 28.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Serialize dict → JSONB param | `json.dumps(env)` + manual cast | `Jsonb(env)` from `psycopg.types.json` | psycopg3 adapts it natively; manual dumps double-encodes [VERIFIED live] |
| Read JSONB → dict | `json.loads(row[...])` | direct `row["watermark"]` | JSONB already comes back as `dict` with `dict_row` [VERIFIED live] |
| datetime ISO serialization | strftime/strptime | existing `_encode_watermark`/`_decode_watermark` | Frozen, tested, offset+µs preserving [VERIFIED: etl.py:617,652] |
| Run-log txn isolation | new connection mgmt | existing `db.connect(autocommit=True)` + `dict_row` pattern | Proven; commits independently of load txn [VERIFIED: etl.py:762] |

**Key insight:** Phase 27 is almost entirely *composition of existing, tested parts*. The only genuinely new logic is (a) the 3-line per-type coercion and (b) one SQL predicate. Resist building anything else.

## Runtime State Inventory

> Rename/refactor section — **not applicable** (greenfield additive feature, no renames). The `watermark JSONB` column already exists and has been reserved-NULL since v0.5.0 [VERIFIED: queries.py:260], so there is **no data migration**: pre-existing `pipeline_runs` rows keep `watermark = NULL`, which the D-03 read query correctly treats as "no prior watermark." **None — verified by reading `ETL_INIT_PIPELINE_RUNS` (column present, nullable, no default).**

## Common Pitfalls

### Pitfall 1: Failed run advances the watermark
**What goes wrong:** A failed load records a watermark, so the next run skips re-extracting rows that never actually loaded → silent data loss.
**Why it happens:** Reusing `ETL_UPDATE_RUN` with a watermark param, or computing/persisting the watermark before the load succeeds.
**How to avoid:** The failed `_end_run` call-site at `etl.py:1199-1208` must pass **no** watermark. With the dedicated-constant pattern, the failed path physically cannot set the column. Capture `max(col)` early (D-02) but persist it only in the **success** `_end_run` at `etl.py:1210`.
**Warning signs:** Integration test SC-2 finds a non-NULL watermark on a `status='failed'` row.

### Pitfall 2: Empty batch writes NULL and triggers a full reload
**What goes wrong:** An empty incremental batch overwrites the prior watermark with NULL → next run does a full reload.
**Why it happens:** Passing a watermark (or an explicit NULL via a shared UPDATE) on the empty-batch early-return.
**How to avoid:** The empty-batch early-return at `etl.py:1138-1140` already calls `self._end_run(run_id, "success", rows_extracted, 0)` with **no** watermark — leave it. Combined with D-03's `watermark IS NOT NULL` read predicate, the prior watermark is preserved with zero copy-forward write.
**Warning signs:** SC-3 finds the empty run's row has `watermark IS NULL` AND a *prior* success row's watermark is no longer the newest qualifying row. (Order by `started_at DESC` + `watermark IS NOT NULL` makes the prior row win — verify the prior watermark is what `_read_watermark` returns after the empty run.)

### Pitfall 3: `numpy.int64` rejected by the strict encoder
**What goes wrong:** `df[col].max()` on an integer column yields `numpy.int64`; `_encode_watermark` raises `ETLError('unsupported watermark type int64')`.
**Why it happens:** `isinstance(numpy.int64(5), int)` is **`False`** [VERIFIED live]; the encoder's strict allowlist correctly rejects it.
**How to avoid:** `int(raw_max)` at the call-site. (datetime: `.to_pydatetime()`; text: `str(...)`.) See Code Examples §1 for the copy-ready dispatch.
**Warning signs:** First-run integration test (SC-1) raises `ETLError` instead of persisting a watermark.

### Pitfall 4: timestamptz read-back UTC-normalization confuses the round-trip assertion
**What goes wrong:** A timestamptz column extracted via `to_dataframe` comes back as a UTC-normalized `Timestamp` (offset `+00:00`), not the original `+02:00` [VERIFIED live]. A test that asserts the decoded watermark equals a hand-written `+02:00` literal fails — but the *envelope* is faithful.
**Why it happens:** psycopg/pandas normalizes timestamptz to UTC on read; this is upstream of the envelope, which preserves whatever offset its input carries.
**How to avoid:** In the round-trip test, assert the decoded value equals the **coerced `max()` output** (`raw_max.to_pydatetime()`), not an independent literal. The envelope's job (ETL-INC-10) is "no drift through JSONB," and that holds exactly [VERIFIED live: `+02:00` and µs survive when the input carries them].
**Warning signs:** SC-4 timestamp assertion fails on offset mismatch while int/text pass.

### Pitfall 5: 2-3 pre-existing flaky DB tests in the local full suite
**What goes wrong:** A full `uv run pytest tests/` shows `test_async_transaction_fix`, `test_create_spatial_index_name_parameter` (and sometimes `test_create_constructor_parity`) failing — **not** Phase-27 regressions.
**Why it happens:** Fixture/teardown isolation bug, pre-existing [CITED: STATE.md:78; memory pycopg-flaky-db-tests].
**How to avoid:** For targeted Phase-27 runs use `uv run pytest tests/test_etl_accessor.py tests/test_etl.py -o addopts="" -x -q`. The `-o addopts=""` drops the subset coverage-ratchet false-fail.
**Warning signs:** These three named tests fail; ignore for Phase-27 verification (confirm green in isolation).

## Code Examples

### §1 — D-07 type coercion (VERIFIED by experiment)

Experiment run with the project venv:
```
$ uv run python -c "import pandas as pd, numpy as np; from datetime import datetime, timezone, timedelta
df_i = pd.DataFrame({'id':[1,5,3]}); mi=df_i['id'].max()
print(type(mi).__name__, isinstance(mi,int))            # -> int64 False
print(int(mi), type(int(mi)).__name__)                  # -> 5 int
tz=timezone(timedelta(hours=2))
md=pd.DataFrame({'ts':[datetime(2026,1,2,12,0,0,123456,tzinfo=tz)]})['ts'].max()
print(type(md).__name__, isinstance(md,datetime))       # -> Timestamp True
print(md.to_pydatetime().isoformat())                   # -> 2026-01-02T12:00:00.123456+02:00
mt=pd.DataFrame({'n':['a','c','b']})['n'].max()
print(type(mt).__name__, isinstance(mt,str))            # -> str True
print(isinstance(np.int64(5), int))                     # -> False
"
```
Output (verbatim):
```
int64 False
5 int
Timestamp True
2026-01-02T12:00:00.123456+02:00
str True
False
```

**Findings:**
- **Integer column** → `numpy.int64`. `isinstance(np.int64, int)` is **False** → encoder **rejects** it. **Must coerce: `int(raw_max)`.**
- **datetime column** → `pandas.Timestamp`, which **is** a `datetime` subclass → encoder accepts it AND emits a correct ISO string with offset [VERIFIED: `_encode_watermark(Timestamp(...))` → `{'type':'datetime','value':'2026-01-02T12:00:00.123456+02:00'}`]. **`Timestamp.to_pydatetime()` preserves the tz offset** [VERIFIED]. Recommend `.to_pydatetime()` to hand the frozen helper a *plain* `datetime` (cleanest; avoids persisting a pandas subtype's repr quirks).
- **text column** → plain `str` on this pandas (`str` dtype) → encoder accepts as-is. (Defensive `str()` is harmless and future-proofs against an `object`-dtype column yielding `numpy.str_`; `numpy.str_` *is* a `str` subclass and json-serializes fine, but `str()` normalizes it.)

**Copy-ready coercion dispatch (call-site, frozen encoder untouched):**
```python
# In run(), immediately after `rows_extracted = len(df)` at etl.py:1108,
# BEFORE the transform loop (D-02). Only when incremental_column is set (D-06).
raw_watermark = None
col = pipeline.incremental_column
if col is not None:
    if col not in df.columns:
        raise ETLError(
            f"incremental_column {col!r} not found in extracted batch "
            f"columns {list(df.columns)} (ETL-INC-04)"
        )  # D-06 — clear ETLError, not a bare KeyError
    if len(df):                       # guard: max() on empty df is NaN
        m = df[col].max()
        if isinstance(m, pd.Timestamp):
            raw_watermark = m.to_pydatetime()      # plain datetime, offset preserved
        elif isinstance(m, str):
            raw_watermark = str(m)                 # normalize numpy.str_ → str
        else:
            raw_watermark = int(m)                 # numpy.int64 → plain int
```
Then at the **success** `_end_run` (etl.py:1210):
```python
wm_env = _encode_watermark(raw_watermark) if raw_watermark is not None else None
self._end_run(run_id, "success", rows_extracted, rows_loaded, watermark=wm_env)
```
*Note:* the empty-batch path (`if not rows:` at etl.py:1138) and the failed path (etl.py:1199) pass **no** watermark — leave them untouched.

**Coercion-insufficiency check (D-07 escape hatch):** Not triggered. Call-site coercion fully satisfies the `{datetime, int, str}` allowlist for all three target types; the Phase-26 encoder stays frozen. [VERIFIED]

### §2 — JSONB write/read round-trip (VERIFIED live against `pycopg_test`)

```python
# Verified end-to-end: write Jsonb(env), read back plain dict, decode.
from psycopg.types.json import Jsonb
from pycopg.etl import _encode_watermark, _decode_watermark
# write:
cur.execute("INSERT INTO t (wm) VALUES (%s) RETURNING id", [Jsonb(_encode_watermark(val))])
# read (dict_row):
cur.execute("SELECT wm FROM t WHERE id=%s", [rid])
read = cur.fetchone()["wm"]          # -> a plain Python dict, NO json.loads needed
decoded = _decode_watermark(read)    # -> exact original scalar
```
Observed (verbatim):
```
datetime: read={'type':'datetime','value':'2026-01-02T12:00:00.123456+02:00'}
   decoded=datetime(...,tzinfo=timezone(timedelta(seconds=7200)))  equal=True  tz=UTC+02:00
int:      read={'type':'int','value':12345}        decoded=12345   equal=True
str:      read={'type':'str','value':'zeta'}       decoded='zeta'  equal=True
```
No `json.dumps`/`json.loads` anywhere; `Jsonb` is the only adapter; tz offset (+02:00) and microseconds (.123456) survive intact. **ETL-INC-10 satisfied with zero new deps.**

### §3 — `_end_run(watermark=)` success path

```python
# pycopg/queries.py — new constant (mirrors ETL_UPDATE_RUN + watermark)
ETL_UPDATE_RUN_WATERMARK = """
    UPDATE pipeline_runs
    SET status = %s, finished_at = %s, rows_extracted = %s,
        rows_loaded = %s, error_message = %s, error_traceback = %s,
        watermark = %s
    WHERE run_id = %s
"""

# pycopg/etl.py _end_run (etl.py:794) — add kwarg + branch
def _end_run(self, run_id, status, rows_extracted, rows_loaded,
             error_message=None, error_traceback=None, watermark=None):
    with self._db.connect(autocommit=True) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            if watermark is None:
                cur.execute(queries.ETL_UPDATE_RUN,
                    [status, datetime.now(UTC), rows_extracted, rows_loaded,
                     error_message, error_traceback, run_id])
            else:
                cur.execute(queries.ETL_UPDATE_RUN_WATERMARK,
                    [status, datetime.now(UTC), rows_extracted, rows_loaded,
                     error_message, error_traceback, Jsonb(watermark), run_id])
```
`watermark` is the **already-encoded `dict`** (envelope); `_end_run` wraps it in `Jsonb(...)` at the binding site (D-05). Failed/empty callers pass nothing → `watermark is None` → original SQL → column stays NULL.

### §4 — `ETL_GET_LAST_WATERMARK` (D-03)
```python
# pycopg/queries.py — mirrors ETL_GET_LAST_RUN (queries.py:289) + success/non-null predicate
ETL_GET_LAST_WATERMARK = """
    SELECT watermark
    FROM pipeline_runs
    WHERE pipeline_name = %s
      AND status = 'success'
      AND watermark IS NOT NULL
    ORDER BY started_at DESC
    LIMIT 1
"""
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual `json.dumps`/cast for JSONB | `psycopg.types.json.Jsonb(obj)` adapter | psycopg3 | No manual serialization; pass the dict, read a dict [VERIFIED live] |
| text column → `numpy.str_` (object dtype) | text column → `str` dtype yields plain `str` | recent pandas | `str()` coercion now mostly a no-op, but keep it defensive [VERIFIED: this env] |

**Deprecated/outdated:** none relevant to this phase.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The local `pycopg_test` DB auto-creates `pipeline_runs` via `db.etl.init()`/`run()` (no manual DDL needed in tests). | Validation Architecture | LOW — `run()` calls `self.init()` (etl.py:1071) which `CREATE TABLE IF NOT EXISTS`; existing integration tests rely on this [VERIFIED: etl.py:1071, queries.py:249] → effectively verified, listed for completeness. |
| A2 | A `load_mode="upsert"` Pipeline against a non-existent or wrong-shaped target raises mid-load, giving a deterministic `status='failed'` for SC-2. | Validation Architecture / Pitfall 1 | LOW — `ETLTargetNotFoundError` fires for missing upsert targets (etl.py:1150); the `except` at etl.py:1199 records `failed`. A target with a NOT-NULL/constraint mismatch also fails deterministically inside the load txn. |

*All other claims are VERIFIED (live experiment) or CITED (file:line). The two items above are LOW-risk and effectively verified; no user confirmation required.*

## Open Questions

1. **WR-01 / WR-02 decode-hardening — IN or OUT of Phase 27?** *(planner decision — recommend OUT)*
   - **What we know:** Phase 27 is the first phase to exercise the `_decode_watermark` READ path against persisted data. WR-01 — `_decode_watermark` permissively coerces any unknown `type` tag to `str` (`etl.py:655` falls through to `return str(value)`) while encode is strict-allowlist. WR-02 — `tag = envelope["type"]` (`etl.py:649`) raises an opaque `KeyError` on a malformed/empty envelope rather than a domain `ETLError`. Both confirmed by reading the code. **CONTEXT.md does NOT mention WR-01/WR-02** — this is a gap surfaced here.
   - **What's unclear:** whether hardening is in scope now that the read path is live.
   - **Recommendation: DEFER to Phase 28.** Rationale tied to locked scope: in Phase 27 every persisted envelope is written by *this code* through the *strict* `_encode_watermark`, so the data `_read_watermark` reads back is provably well-formed — the permissive/opaque paths are **unreachable with Phase-27-produced data**. Hardening them adds no invariant Phase 27 must prove (none of SC-1..SC-4 exercise a malformed envelope) and would expand scope. Phase 28, which introduces user-facing `RunResult.watermark_*` surfacing (ETL-INC-08 reads *arbitrary historical* rows via `history()`/`last_run()`), is the correct home: that is where an externally-mutated or legacy envelope could realistically reach the decoder. **Flag for the planner to confirm**, but the scope boundary clearly favors deferral. (Carry-forward note for Phase 28: harden `_decode_watermark` — `ETLError` on missing/unknown `type` tag — when `history()`/`last_run()` start surfacing watermarks.)

2. **`history()`/`last_run()` watermark surfacing** — explicitly Phase 28 (ETL-INC-08). `_read_watermark` is a *new private* method (D-04), **not** a change to `history()`/`last_run()`/`_row_to_result`. Confirmed out of scope.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PostgreSQL (`pycopg_test`) | live-DB integration tests + round-trip | ✓ | reachable | — |
| psycopg3 + `psycopg.types.json.Jsonb` | JSONB bind | ✓ | already pinned | — |
| pandas | `max(col)` | ✓ | already pinned | — |
| `uv` | test runner | ✓ | — | — |

**Missing dependencies with no fallback:** none. **Missing with fallback:** none. All live experiments in this research ran successfully against `pycopg_test`.

## Validation Architecture

> nyquist_validation is enabled (config `workflow` has no `nyquist_validation: false`; absent ⇒ enabled).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (+ `pytest-cov`, ratchet ≥ 94) |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]` addopts carry `--cov-fail-under`) |
| Quick run command | `uv run pytest tests/test_etl_accessor.py tests/test_etl.py -o addopts="" -x -q` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map
| Req ID / SC | Behavior | Test Type | Automated Command | File Exists? |
|-------------|----------|-----------|-------------------|-------------|
| SC-1 / ETL-INC-02 | First run persists `watermark = max(col)` (non-NULL JSONB) | integration | `uv run pytest tests/test_etl_accessor.py -k first_run_records_watermark -o addopts="" -x` | ❌ Wave 0 |
| SC-2 / ETL-INC-06 | Failed run → `status='failed'` AND `watermark IS NULL`; subsequent `_read_watermark` returns the **prior** success watermark, not the failed run's | integration | `... -k failed_run_does_not_advance_watermark ...` | ❌ Wave 0 |
| SC-3 / ETL-INC-05 | Empty batch → `status='success'`, `rows_loaded=0`, prior watermark preserved (no NULL written) | integration | `... -k empty_batch_preserves_watermark ...` | ❌ Wave 0 |
| SC-4 / ETL-INC-10 | Round-trip no-drift for timestamp / int / text (offset + µs intact) | integration | `... -k watermark_jsonb_roundtrip ...` | ❌ Wave 0 |
| D-04 | `_read_watermark` returns `None` when no qualifying success row | integration | `... -k read_watermark_none_first_run ...` | ❌ Wave 0 |
| D-06 | Missing incremental column raises `ETLError` (not `KeyError`) | integration | `... -k incremental_column_missing_raises_etlerror ...` | ❌ Wave 0 |

### Concrete runnable assertions per Success Criterion

- **SC-1 (first run persists max):** build an `etl_src` with rows whose `incremental_column` (e.g. `id INTEGER`) has a known max; `Pipeline(incremental_column="id", load_mode="upsert", conflict_columns=["id"], ...)`; `result = db.etl.run(p)`; then
  ```python
  row = db.execute("SELECT watermark FROM pipeline_runs WHERE run_id=%s", [result.run_id])[0]
  assert row["watermark"] == {"type": "int", "value": <known_max>}      # plain dict from JSONB
  assert db.etl._read_watermark("name") == <known_max>
  ```
- **SC-2 (no-advance-on-failure):** (a) run a successful incremental load to seed a prior watermark `W0`; (b) induce a deterministic failure — `Pipeline(incremental_column="id", load_mode="upsert", conflict_columns=["id"])` against a target whose shape forces a constraint error inside the load txn, OR reuse the proven `_start_run`+`db.transaction()`+forced-`RuntimeError` harness from `test_failed_run_commits_despite_load_rollback` (`tests/test_etl_accessor.py:259`); assert:
  ```python
  frow = db.execute("SELECT status, watermark FROM pipeline_runs WHERE run_id=%s", [failed_id])[0]
  assert frow["status"] == "failed" and frow["watermark"] is None
  assert db.etl._read_watermark("name") == W0          # still the prior success
  ```
- **SC-3 (empty batch preserves):** seed prior watermark `W0`; run a pipeline whose source returns **0 rows** (e.g. `source="SELECT 1 AS id WHERE false"`) with `incremental_column="id"`; assert:
  ```python
  erow = db.execute("SELECT status, rows_loaded, watermark FROM pipeline_runs WHERE run_id=%s", [empty_id])[0]
  assert erow["status"] == "success" and erow["rows_loaded"] == 0 and erow["watermark"] is None
  assert db.etl._read_watermark("name") == W0          # prior preserved, no reload
  ```
- **SC-4 (round-trip no-drift):** parametrize over `(timestamp tz-aware, integer, text)` source columns; for each, run an incremental pipeline and assert the decoded read-back equals the **coerced** `max()` (per Pitfall 4 — compare to `m.to_pydatetime()` for datetime, not a hand literal); assert the persisted `watermark` dict's `type` tag matches and (datetime case) the ISO string retains its offset and microseconds.

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_etl_accessor.py tests/test_etl.py -o addopts="" -x -q`
- **Per wave merge:** `uv run pytest -o addopts=""` for the etl test modules + coverage spot-check on `etl.py`/`queries.py`.
- **Phase gate:** full suite green (modulo the 3 named pre-existing flakies — Pitfall 5) before `/gsd-verify-work`; `interrogate ≥ 95`; coverage ratchet ≥ 94 held; `ruff check` + `black` clean.

### Wave 0 Gaps
- [ ] `tests/test_etl_accessor.py` — add the 6 incremental integration tests above (extend `TestRunPipelineIntegration`, reuse `db`/`cleanup_pipeline_runs`/`etl_table`/`etl_src` fixtures `:422-444`).
- [ ] (optional) `tests/test_etl.py::TestEncodeDecodeWatermark` (`:629`) — only if a pure coercion helper is extracted; otherwise coercion is covered by the integration tests. No new fixtures or framework install needed.
- Framework install: **none** — pytest + live DB already in place.

## Sources

### Primary (HIGH confidence)
- Live experiments against `pycopg_test` via `uv run python` — pandas `max()` types, strict-encoder behavior on pandas/numpy scalars, full `Jsonb()` JSONB write/read round-trip for datetime/int/str (offset + µs preserved), timestamptz UTC-normalization on `to_dataframe` read. (Commands + verbatim output in Code Examples §1–§2, Pitfall 4.)
- `pycopg/etl.py` — `_encode_watermark`/`_decode_watermark` (:580/:629), run-log writers (:766/:794/:851), `last_run` (:902), `run()` extract/transform/empty/fail/success seams (:1108/:1138/:1199/:1210), imports (:35), `_row_to_result` drops watermark (:691).
- `pycopg/queries.py` — `ETL_INIT_PIPELINE_RUNS` watermark col (:260), `ETL_UPDATE_RUN` (:270), `ETL_GET_LAST_RUN` (:289).
- `pycopg/exceptions.py` — `ETLError` base (:54).
- `tests/test_etl_accessor.py` — fixtures (:20/:27/:422/:434), `test_run_writes_full_row` watermark-NULL assertion (:257), failure-injection harness (:259).
- `.planning/` — 27-CONTEXT.md (D-01..D-07), 26-CONTEXT.md (D-04/D-05), REQUIREMENTS.md (locked scope, zero-new-deps), ROADMAP.md (Phase 27/28 SCs), STATE.md (flaky tests).

### Secondary (MEDIUM confidence)
- Memory: `pycopg-flaky-db-tests` (the 3 pre-existing local failures).

### Tertiary (LOW confidence)
- none.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new deps; `Jsonb` round-trip verified live.
- Architecture: HIGH — direct composition of existing, cited patterns; new code is one method + one SQL constant + a 3-branch coercion.
- Pitfalls: HIGH — each pitfall is grounded in a live experiment or a cited line.
- Type coercion (D-07): HIGH — resolved empirically, frozen contract preserved.
- WR-01/WR-02 scope call: MEDIUM — recommendation is reasoned but flagged as a planner decision (CONTEXT.md silent).

**Research date:** 2026-06-20
**Valid until:** 2026-07-20 (stable; pandas-version-dependent text-dtype detail is the only fast-moving item and is defensively handled).
