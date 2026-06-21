# Phase 28: Incremental ETL — Extract, RunResult & Async Parity - Pattern Map

**Mapped:** 2026-06-21
**Files analyzed:** 7 (4 code/doc modified, 3 test modified)
**Analogs found:** 11 / 11 (all in-codebase — this is an integration/parity phase, every new symbol mirrors an existing sync block)

> **Nature of this phase:** Almost nothing is net-new. The work is (a) *wiring* three already-built, unit-tested primitives together in sync `run()`, and (b) porting the resulting sync stack 1:1 into `AsyncETLAccessor`. The highest-value mapping below is therefore **sync→async analog pairs** plus the **exact existing blocks to copy/mirror**, with verified `file:line` anchors.

---

## Line-number drift audit

I read the actual current `pycopg/etl.py` (1803 lines) at every site CONTEXT.md cites. **Verdict: CONTEXT.md anchors are accurate.** Confirmed exact matches:

| Symbol | CONTEXT.md says | Actual (verified) | Drift |
|--------|-----------------|-------------------|-------|
| `RunResult` dataclass | 260 | 260 (fields at 286–293) | none |
| `_build_incremental_extract_sql` | 513 | 513 | none |
| `_encode_watermark` | 581 | 581 | none (Phase-27 ctx said 580 — 1-line, harmless) |
| `_decode_watermark` | 630 | referenced, frozen | none |
| `_row_to_result` | 688 | 688 (body 704–713) | none |
| sync `_end_run` | 795 | 795 (body 853–882, `Jsonb` at 878) | none |
| sync `history` / `last_run` | 905 / 934 | 905 / 934 | none |
| sync `_read_watermark` | 960 | 960 (body 992–998) | none |
| sync `run` | 1000 | 1000 | none |
| sync dry-run extract | 1083–1108 | 1083–1108 | none |
| sync real extract | 1152–1178 | 1152–1178 | none |
| sync `max(col)` guard block | 1191–1223 | 1191–1223 | none |
| sync success `_end_run` call | 1330 | 1329–1330 (`wm_env` built at 1329) | none |
| `AsyncETLAccessor` | 1334 | 1334 | none |
| async `_end_run` | 1412 | 1412 (body 1447–1460, **no `watermark=`**) | none |
| async `_read_watermark` | "~1462 area, does NOT exist" | confirmed absent (1462 is async `_fetch_run_result`) | none |
| async `run` | 1536 | 1536 (ends 1802) | none |
| async dry-run extract | 1603–1628 | 1602–1628 | none |
| async real extract | (real path) | 1672–1698 | — |
| async success `_end_run` call | "to add" | 1802 (no `watermark=`) | none |

Confirmed in sibling files:
- `pycopg/queries.py`: `ETL_LIST_RUNS` (281), `ETL_GET_LAST_RUN` (289), `ETL_GET_LAST_WATERMARK` (303), `ETL_UPDATE_RUN_WATERMARK` (313) — all exist.
- `pycopg/exceptions.py`: `ETLError` (54), `ETLTransformError` (60), `ETLTargetNotFoundError` (66).
- `tests/test_parity.py`: `ACCESSOR_PAIRS` (24) with `(ETLAccessor, AsyncETLAccessor)` (26); `test_accessor_parity` (36); `# TestEtlParity removed` comment (516–517). **Confirms the CONTEXT.md "fact correction": do NOT restore a `TestEtlParity` class.**
- `tests/test_etl_accessor.py`: `TestRunResultSurface` (1062), `TestAsyncRunResultSurface` (1728), and the Phase-27 watermark tests (1378, 1593, 1598, 1613, …).

---

## File Classification

| Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------|------|-----------|----------------|---------------|
| `pycopg/etl.py` — `RunResult` (260) | model (frozen dataclass) | transform | itself (add 2 fields + docstring) | self / additive |
| `pycopg/etl.py` — `_row_to_result` (688) | utility (pure mapper) | transform | itself (stop dropping `watermark`) | self / additive |
| `pycopg/etl.py` — sync `run()` (1000) | service (orchestrator) | batch / request-response | itself (wire read→filter→record + dry-run branch) | self / additive |
| `pycopg/etl.py` — async `_end_run` (1412) | service (run-log writer) | CRUD | **sync `_end_run` (795)** | exact mirror |
| `pycopg/etl.py` — async `_read_watermark` (net-new, after 1534) | service (run-log reader) | CRUD | **sync `_read_watermark` (960)** | exact mirror |
| `pycopg/etl.py` — async `run()` (1536) | service (orchestrator) | batch | **sync `run()` (1000)** post-Phase-28 | strict 1:1 mirror |
| `pycopg/queries.py` | config (SQL constants) | — | none new — **reuse** `ETL_GET_LAST_WATERMARK` (303) + `ETL_UPDATE_RUN_WATERMARK` (313) | reuse-only |
| `pycopg/exceptions.py` | model (exception) | — | `ETLError` (54) — **reuse**, no new subclass | reuse-only |
| `docs/etl.md` | doc | — | existing `### Dry runs` / `## history` section style | role-match |
| `tests/test_etl_accessor.py` | test (live-DB integration) | — | `TestRunResultSurface` (1062) / `TestAsyncRunResultSurface` (1728) + Phase-27 watermark tests | exact |
| `tests/test_etl.py` | test (DB-free) | — | `TestEncodeDecodeWatermark` / builder tests | role-match |
| `tests/test_parity.py` | test (structural parity) | — | `test_accessor_parity` (36) — **no edit needed**, auto-covers new surface | reuse-only |

---

## Pattern Assignments

### 1. `RunResult` dataclass — add 2 fields (`pycopg/etl.py:260`)

**Analog:** itself. Frozen dataclass, currently **8 fields** (verified 286–293), no watermark. Add `watermark_used` and `watermark_recorded`, update the numpydoc `Parameters` block (260–284).

**Current field block (286–293):**
```python
    run_id: int | None
    pipeline_name: str
    status: str
    rows_extracted: int
    rows_loaded: int
    started_at: datetime
    finished_at: datetime
    error: str | None
```

**Add (D-A1):** two new fields. Both `None` for non-incremental pipelines and for all stored-row surfaces (`watermark_used` is never persisted). Type per the watermark scalar union already used by `_read_watermark`'s signature (`datetime | int | str | None`). Give defaults (`= None`) so every existing `RunResult(...)` call-site that does not yet pass them still constructs — note there are call-sites that construct positionally (dry-run forks at 1132 and 1652) and via `_row_to_result` (704). Defaulting avoids touching the dry-run forks unless the planner chooses to populate them there.

---

### 2. `_row_to_result` — stop dropping `watermark` (`pycopg/etl.py:688`)

**Analog:** itself. Feeds `history()` (905), `last_run()` (934) and `_fetch_run_result` (883) — **all three surfaces gain the field for free** once this maps the column. `ETL_LIST_RUNS` / `ETL_GET_LAST_RUN` / `ETL_GET_RUN` are `SELECT *`, so `row` already carries `watermark`.

**Current body (704–713):**
```python
    return RunResult(
        run_id=row["run_id"],
        pipeline_name=row["pipeline_name"],
        status=row["status"],
        rows_extracted=row["rows_extracted"],
        rows_loaded=row["rows_loaded"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        error=row["error_message"],
    )
```

**Change (D-A1 / D-A1a):** map `row["watermark"]` → `watermark_recorded` with **NULL → None** (decode only when non-NULL), and set `watermark_used=None` (it is a per-run input, never stored). The NULL→decode guard mirrors the exact pattern already in sync `_read_watermark` (996–998):
```python
        if row is None or row["watermark"] is None:
            return None
        return _decode_watermark(row["watermark"])
```
Apply the same `None`-check before `_decode_watermark` here (inline, or via the tiny guarded helper allowed by CONTEXT.md "Claude's Discretion"). Also update the docstring at 692 which currently says "drops `error_traceback` and `watermark` (D-10)".

---

### 3. Watermark-filtered extract — wire `_build_incremental_extract_sql` into the 4 extract blocks

**Builder (the asset to finally call) — `pycopg/etl.py:513`:**
```python
def _build_incremental_extract_sql(source, column, schema="public", watermark=None) -> tuple[str, list]:
    ...
    # watermark is None  -> full SELECT, [] params (first run, D-12)
    # SQL source + wm     -> SELECT * FROM (<clean>) _pycopg_inc WHERE col > %s, [wm]
    # table source + wm   -> SELECT * FROM schema.source WHERE col > %s, [wm]
```
Returns a `(sql, params)` 2-tuple that plugs straight into `to_dataframe(sql=…, params=…)`. **`watermark=None` ⇒ full unfiltered SELECT, so first-run needs no caller branch.**

**The 4 inline `to_dataframe` blocks it replaces** (all verified identical in shape; differ only by `await` and dry/real context):

| Block | Location | Notes |
|-------|----------|-------|
| sync dry-run extract | `etl.py:1083–1108` | |
| sync real extract | `etl.py:1152–1178` | |
| async dry-run extract | `etl.py:1602–1628` | `await self._db.to_dataframe(...)` |
| async real extract | `etl.py:1672–1698` | `await self._db.to_dataframe(...)` |

Each currently branches on `_is_sql_source` × `extract_limit` and calls `to_dataframe` with an f-string LIMIT subquery or `table=`. **Integration concern (CONTEXT.md):** the `extract_limit` `LIMIT :lim` handling must compose with the new `WHERE col > %s` filter — the builder does NOT emit LIMIT, so the planner must wrap/compose (LIMIT on the filtered subquery). `extract_limit` already uses a bound `:lim` param; the watermark is a positional `%s` from the builder — the planner must reconcile the two param styles (named dict vs positional list) in `to_dataframe`.

**D-A2a (locked):** both the `dry_run` fork and the real path must read the watermark + apply the builder **identically** so they cannot drift. Exact factoring (shared helper vs inline-mirror in both forks) is planner discretion; follow the existing extract-block style.

**Pre-extract watermark read** — call `self._read_watermark(name)` (sync) / `await self._read_watermark(name)` (async) before each extract, pass the result as the builder's `watermark=`. First run returns `None` → full extract.

---

### 4. `max(col)` capture + guard block — COPY VERBATIM into async (`pycopg/etl.py:1191–1223`)

**Analog:** sync `run()` capture block (1191–1223). This is the Phase-27 logic (incl. the WR-02 bug-fix) that the async port must replicate **byte-for-byte** (D-A3 — guard semantics + `ETLError` message text must be equivalent). **Currently absent in async `run()`.**

**Exact block to mirror (1191–1223):**
```python
            raw_watermark = None
            col = pipeline.incremental_column
            if col is not None:
                if col not in df.columns:
                    raise ETLError(
                        f"incremental_column {col!r} not found in extracted batch "
                        f"columns {list(df.columns)} (ETL-INC-04)"
                    )  # D-06 — clear ETLError, not a bare KeyError
                if len(df):  # guard: max() on empty df is NaN
                    m = df[col].max()
                    if pd.isna(m):                       # <-- MUST precede is_float (NaN is a float; WR-02)
                        raw_watermark = None
                    elif isinstance(m, pd.Timestamp):
                        raw_watermark = m.to_pydatetime()
                    elif isinstance(m, str):
                        raw_watermark = str(m)
                    elif pd.api.types.is_float(m):
                        raise ETLError(
                            f"incremental_column {col!r} has float dtype; float "
                            f"watermarks are not supported (cast to INTEGER or "
                            f"TIMESTAMP). Supported types are {_WATERMARK_SUPPORTED}"
                        )
                    else:
                        raw_watermark = int(m)  # numpy.int64 → plain int
```

**CRITICAL ordering invariant (Phase-27 WR-02 fix):** the `pd.isna(m)` branch MUST come **before** `pd.api.types.is_float(m)` — `NaN` is itself a float, so checking float first would mis-route an all-NULL column into the float-reject raise instead of preserving the prior watermark. Preserve this exact order in the async copy.

**Placement (D-02):** insert in async `run()` **right after** `rows_extracted = len(df)` (1700) and **before** the transform chain (1706) — same relative position as sync (after 1180, before 1228).

**Success-path encode + record (sync 1329–1330):**
```python
        wm_env = _encode_watermark(raw_watermark) if raw_watermark is not None else None
        self._end_run(run_id, "success", rows_extracted, rows_loaded, watermark=wm_env)
```
Mirror at async 1802 (currently `await self._end_run(run_id, "success", rows_extracted, rows_loaded)` — no watermark). The empty-batch early return (sync 1257–1259 / async 1731–1733) and the `failed` path (sync 1318–1327 / async 1791–1800) MUST pass **no** watermark (column stays NULL — no-advance / preserve invariants).

---

### 5. async `_end_run` — add `watermark=` (`pycopg/etl.py:1412`)

**Analog:** sync `_end_run` (795), body 853–882. The async version (1412, body 1447–1460) has **no `watermark` param** and always uses `ETL_UPDATE_RUN`.

**Sync template to mirror (853–882):**
```python
        with self._db.connect(autocommit=True) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if watermark is None:
                    cur.execute(queries.ETL_UPDATE_RUN, [status, datetime.now(UTC),
                        rows_extracted, rows_loaded, error_message, error_traceback, run_id])
                else:
                    cur.execute(queries.ETL_UPDATE_RUN_WATERMARK, [status, datetime.now(UTC),
                        rows_extracted, rows_loaded, error_message, error_traceback,
                        Jsonb(watermark), run_id])
```

**Async port:** add `watermark: dict | None = None` to the signature (1412–1420), and switch the body (1447–1460) to the same `if watermark is None: ETL_UPDATE_RUN else: ETL_UPDATE_RUN_WATERMARK + Jsonb(watermark)` fork, using `await cur.execute(...)`. Reuse the existing `ETL_UPDATE_RUN_WATERMARK` constant (queries.py:313) and the already-imported `Jsonb`. Only mechanical diffs: `async with` / `await`.

---

### 6. async `_read_watermark` — NET-NEW, mirror sync (`pycopg/etl.py:960` → new method after 1534)

**Analog:** sync `_read_watermark` (960), body 992–998. **Async does not exist** (verified: 1462 is async `_fetch_run_result`). Place the new async method alongside the other async run-log readers (e.g. after `last_run` at 1534, before `run` at 1536).

**Sync template to mirror (992–998):**
```python
        with self._db.connect(autocommit=True) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(queries.ETL_GET_LAST_WATERMARK, [name])
                row = cur.fetchone()
        if row is None or row["watermark"] is None:
            return None
        return _decode_watermark(row["watermark"])
```

**Async port** (follows the exact async run-log isolation pattern already used by async `last_run` at 1530–1534):
```python
        async with self._db.connect(autocommit=True) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(queries.ETL_GET_LAST_WATERMARK, [name])
                row = await cur.fetchone()
        if row is None or row["watermark"] is None:
            return None
        return _decode_watermark(row["watermark"])
```
Reuse `ETL_GET_LAST_WATERMARK` (queries.py:303) and the frozen `_decode_watermark`. Signature `-> datetime | int | str | None` mirrors sync (960).

---

### 7. Incremental `dry_run` branch (sync 1078–1141 / async 1598–1661)

**Analog:** the existing dry-run forks (sync 1078–1141, async 1598–1661) + the real-path capture block (#4 above).

**D-A2 contract:** on an incremental pipeline, `dry_run` must (a) read `_read_watermark(name)`, (b) apply the **same** `WHERE col > wm` filter (the shared factored path from #3), (c) set `watermark_used` = that floor, (d) set `watermark_recorded` = `max(col)` of the **filtered raw batch** (or `None` if empty/all-NULL — reuse the #4 guard logic), and (e) write **no** `pipeline_runs` row (`status='dry_run'`, `run_id=None`, unchanged). `rows_extracted` therefore reflects the real would-be pull. Populate the two new `RunResult` fields in the dry-run `RunResult(...)` constructions (sync 1132–1141, async 1652–1661).

---

## Shared Patterns

### Run-log connection isolation (apply to async `_read_watermark` + async `_end_run`)
**Source:** sync `_read_watermark` (992), sync `_end_run` (853), async `_start_run` (1404), async `last_run` (1530).
```python
async with self._db.connect(autocommit=True) as conn:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(<CONST>, [<params>])
        row = await cur.fetchone()
```
Dedicated short-lived autocommit connection, independent of the load txn — preserves no-advance-on-failure.

### `%s`-only watermark value
**Source:** builder (513), `_end_run` `Jsonb(watermark)` bind (878).
The watermark value is **always** a `%s` param (positional from the builder, or `Jsonb`-wrapped at the write-site) — never f-string interpolated. Identifiers (`column`, `schema`, `source`) are validated via `validate_identifiers` before any interpolation.

### NULL → decode guard
**Source:** sync `_read_watermark` (996–998).
`if row[...] is None: return None / None` then `_decode_watermark(...)`. Reuse identically in `_row_to_result` (#2) and async `_read_watermark` (#6).

### Strict sync↔async parity (D-A3)
Only mechanical differences allowed between sync and async: `async with` / `await` on DB calls, `await asyncio.to_thread(step, df)` for transform steps (already at async 1643/1716). **`ETLError` message text and guard ordering must be byte-for-byte identical** to sync (#4). Structural surface parity is auto-verified by `test_accessor_parity` (test_parity.py:36) once both accessors expose the same public methods — `_read_watermark` is private so it does not affect that test; the new public surface (`run`/`history`/`last_run` already paired) stays balanced.

---

## No Analog Found

None. Every new/modified symbol mirrors an existing in-codebase block. This is a pure integration/parity phase.

| Net-new symbol | Why no external analog needed |
|----------------|-------------------------------|
| async `_read_watermark` | exact mirror of sync (960) + async run-log read pattern (1530) |
| `RunResult.watermark_used/recorded` | additive fields on existing frozen dataclass |
| incremental `dry_run` branch | reuses existing dry-run forks + #4 capture block |

---

## Test Pattern Map

| New test surface | Analog / seam | Location |
|------------------|---------------|----------|
| `watermark_used`/`watermark_recorded` on `run()` result | extend `TestRunResultSurface` | test_etl_accessor.py:1062 |
| filtered-extract / second-run-pulls-only-new / dry-run preview (sync) | new tests in `TestRunResultSurface` + Phase-27 watermark tests | 1062, 1378, 1466 |
| missing-col / float-col / all-NULL guards (async) | **mirror** sync `test_incremental_column_missing_raises_etlerror` (1598), `test_float_incremental_column_raises_etlerror` (1613), `test_all_null...preserves_watermark` (1636) into async | 1598/1613/1636 → `TestAsyncRunResultSurface` (1728) |
| async parity behavioral tests | `TestAsyncRunResultSurface` | 1728 |
| structural parity | `test_accessor_parity` — **no edit** (auto-covers) | test_parity.py:36 |
| DB-free (only if new pure logic) | `TestEncodeDecodeWatermark` / builder tests | test_etl.py |

**Do NOT** create/restore a `TestEtlParity` class (test_parity.py:516 documents its removal; SC-5 is met structurally by `test_accessor_parity` + behaviorally by the async integration mirrors).

---

## Metadata

**Analog search scope:** `pycopg/etl.py` (1803 lines, all relevant sections read non-overlapping), `pycopg/queries.py` (ETL constants), `pycopg/exceptions.py` (ETLError hierarchy), `tests/test_parity.py`, `tests/test_etl_accessor.py` (seams).
**Files scanned:** 5
**Pattern extraction date:** 2026-06-21
