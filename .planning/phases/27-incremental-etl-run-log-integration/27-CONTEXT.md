# Phase 27: Incremental ETL — Run-Log Integration - Context

**Gathered:** 2026-06-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Wire the watermark through the **run-log persistence layer** and prove the
success-only persistence invariants against a real database. Scope =
**ETL-INC-02, ETL-INC-05, ETL-INC-06, ETL-INC-10**.

Deliverables this phase (sync only):

1. **`_read_watermark(name)` helper** — reads and decodes the last
   **successful, non-NULL** watermark for a pipeline from `pipeline_runs`
   (returns the scalar, or `None` when there is no prior watermark).
2. **`_end_run(watermark=...)` success-only persist path** — extends the
   existing run-log writer to bind the typed JSONB envelope (via
   `Jsonb(...)`) on the success path; failed runs leave `watermark` NULL.
3. **Minimal `max(col)` capture in sync `run()`** (scoped pull-forward — see
   D-01) — compute the high-water mark from the **raw extracted batch**
   (before transforms), encode it, and persist it on success so the
   first-run / no-advance-on-failure / empty-batch invariants are provable
   end-to-end against a live DB.
4. **JSONB round-trip verification** — timestamp / integer / text watermarks
   survive a full `pipeline_runs.watermark JSONB` write→read with no type
   drift (ETL-INC-10), using the Phase-26 typed envelope.

**Explicitly OUT of this phase (Phase 28 per the traceability table — do NOT
pull forward):**
- The `WHERE incremental_column > last_watermark` extract wiring
  (ETL-INC-03) — Phase 27 still does a **full load every run**; the read of
  the prior watermark is implemented and tested, but it is not yet *applied*
  as an extract filter.
- `RunResult.watermark_used` / `watermark_recorded` fields (ETL-INC-07).
- `history()` / `last_run()` surfacing the watermark (ETL-INC-08).
- `dry_run` incremental support (ETL-INC-09).
- `AsyncETLAccessor` mirror + `TestEtlParity` extension (ETL-INC-11).
- Incremental usage docs / backfill workflow (ETL-INC-12).
- The *full* ETL-INC-04 treatment (missing-column handling is pulled into 27
  minimally per D-06; the formal requirement lands in 28).

</domain>

<decisions>
## Implementation Decisions

### Scope seam — how Phase 27 proves its invariants
- **D-01: Pull a minimal happy-path `max(col)` + `_end_run(watermark=)`
  persist into sync `run()` this phase.** Phase 27's SC-1 ("first run
  persists watermark = max of the incremental column") is only provable
  end-to-end if `run()` actually computes and records a watermark. So a
  *minimal* `max(col)`-from-raw-batch computation + success-path persist
  lands here. Phase 28 then layers the `WHERE`-filter extract (ETL-INC-03),
  `RunResult` fields (ETL-INC-07), `dry_run`, and the async mirror on top of
  this seam. **Constraint:** Phase 27 still does a full (unfiltered) load
  every run — only the *persist + read* halves of the loop are wired.
- **D-02: Watermark is computed from the RAW extracted batch, before the
  transform chain runs.** Locked milestone decision (cadrage 2026-06-19,
  REQUIREMENTS.md). In `run()` this means capturing `df[col].max()`
  immediately after extract (step 1), before the transform loop (step 2)
  mutates `df`.

### `_read_watermark` — reading the prior high-water mark
- **D-03: Read the last run that is `status='success'` AND
  `watermark IS NOT NULL`, newest-first.** New SQL constant (mirrors
  `ETL_GET_LAST_RUN` shape):
  `WHERE pipeline_name=%s AND status='success' AND watermark IS NOT NULL
  ORDER BY started_at DESC LIMIT 1`. Failed runs (NULL watermark) and
  empty-batch successes (which *preserve*, never *write*, per D-05) are
  automatically skipped — this makes the empty-batch-preserves invariant
  fall out of the query, with no copy-forward write needed.
- **D-04: `_read_watermark(name)` returns the decoded scalar or `None`.**
  Reads the JSONB column (psycopg yields a plain `dict`), passes it to the
  Phase-26 `_decode_watermark`, returns the typed scalar. `None` when no
  qualifying row exists (first run / never-succeeded-with-watermark). The
  return value is *consumed* by the Phase-28 extract filter; in Phase 27 it
  exists, is unit/integration-tested, and is simply not yet applied as a
  WHERE bound.

### JSONB binding (closing Phase-26 D-05)
- **D-05: `Jsonb()` wrap at the write-site.** Import
  `from psycopg.types.json import Jsonb` in `etl.py` (it is NOT imported
  yet — confirmed at `etl.py` top, line ~35). On the success path,
  `_end_run` binds `Jsonb(_encode_watermark(value))` as the new `watermark`
  `%s` param. Read side: psycopg returns a plain `dict` from a JSONB column,
  fed straight to `_decode_watermark`. This is exactly the write-site concern
  Phase 26 D-05 deferred to Phase 27. A failed/empty run passes no watermark
  (column stays NULL).

### Missing watermark column in the extract
- **D-06: Raise a clear `ETLError` now when the incremental column is absent
  from the raw batch — not a bare `KeyError`.** Cheap to do at the
  `df[col].max()` site and avoids a confusing `KeyError` leaking in the
  interim before Phase 28's formal ETL-INC-04 treatment. Message names the
  missing column. Phase 28 reuses/refines this (it owns the formal
  requirement). Applies only when `pipeline.incremental_column` is set.

### Type coercion of `max()` output → Claude's Discretion
- **D-07: planner decides the coercion site after testing.** `df[col].max()`
  may yield numpy/pandas types (`numpy.int64`, `pandas.Timestamp`) rather
  than plain `int`/`datetime`, and the Phase-26 `_encode_watermark` allowlist
  is exactly `{datetime, int, str}` with `bool` rejected — numpy types would
  hit its unsupported-type raise. **Constraint:** the value handed to
  `_encode_watermark` MUST satisfy the `{datetime, int, str}` allowlist.
  Preferred direction (not mandated): coerce at the `run()` call-site
  (`pd.Timestamp.to_pydatetime()`, `int(np_int)`) and leave the frozen
  Phase-26 helper untouched. The planner picks the exact coercion points
  after observing what pandas actually returns for the test columns; do NOT
  re-open the Phase-26 `_encode_watermark` contract unless coercion at the
  call-site proves insufficient.

### Claude's Discretion (general)
- Whether `_read_watermark` lives as a method on `ETLAccessor` or as a
  helper — follow the existing run-log method placement (`_start_run` /
  `_end_run` / `_fetch_run_result` are all methods on `ETLAccessor` using a
  dedicated `db.connect(autocommit=True)`).
- Whether to extend `ETL_UPDATE_RUN` to set `watermark` or add a dedicated
  success-path UPDATE constant — the planner chooses; constraint is the
  failed path must NOT touch `watermark` (leave it NULL) and the success path
  must set it only when a watermark exists.
- Exact integration-test placement — `tests/test_etl_accessor.py` is the
  live-DB integration file (`TestETLAccessorIntegration` /
  `TestRunPipelineIntegration`); the existing
  `test_run_writes_full_row` already asserts `watermark IS NULL` for
  non-incremental runs — extend the same fixture/cleanup conventions.
- Exact docstring wording — numpydoc shallow style, `interrogate ≥ 95`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope (LOCKED — read first)
- `.planning/REQUIREMENTS.md` — v0.7.0 requirements. **In scope this phase:
  ETL-INC-02, ETL-INC-05, ETL-INC-06, ETL-INC-10.** The "Locked scope
  decisions (cadrage 2026-06-19)" block is binding (max-from-raw-batch
  before transforms; read from last *successful* run; advance only on
  success; empty batch preserves prior, never writes NULL; `>` exclusive;
  upsert-only). The **Out of Scope** table is binding.
- `.planning/ROADMAP.md` §"Phase 27: Incremental ETL — Run-Log Integration"
  — Goal + 4 Success Criteria. **Also read the Phase 28 entry** — it defines
  what is explicitly NOT this phase (extract filter, RunResult fields,
  dry_run, async, docs).
- `.planning/PROJECT.md` §"Current Milestone: v0.7.0" — milestone goal and
  locked scope summary.

### Upstream phase context (the pure layer this integrates)
- `.planning/phases/26-incremental-etl-pure-layer/26-CONTEXT.md` — D-01..D-17.
  Most relevant: **D-05** (encode returns a BARE dict; the `Jsonb()` wrap is
  a Phase-27 write-site concern → resolved here as this phase's D-05), and
  the deferred-ideas list (`max()` helper + missing-column→ETLError belong to
  27/28, per the user's explicit boundary).

### Code to read & extend
- `pycopg/etl.py` — the target module. Key landmarks:
  - `_encode_watermark` (line 580) / `_decode_watermark` (line 629) — the
    Phase-26 typed-envelope helpers this phase round-trips through `Jsonb()`.
  - `ETLAccessor._start_run` (line 766), `_end_run` (line 794),
    `_fetch_run_result` (line 851), `history` (line 873), `last_run`
    (line 902) — the run-log writers; `_end_run` gains the `watermark=`
    success path; the dedicated `db.connect(autocommit=True)` isolation
    pattern is reused for `_read_watermark`.
  - `ETLAccessor.run` (line 928) — extract at lines 1080–1106 (capture
    `max(col)` right after, before the transform loop at 1113); empty-batch
    early-return at line 1138–1140 (must preserve prior watermark);
    success `_end_run` at line 1210; failed `_end_run` at lines 1199–1208
    (must leave watermark NULL).
  - `_row_to_result` (line 687) — currently DROPS `watermark` (D-10);
    Phase 27 does NOT need to surface it on `RunResult` (that is ETL-INC-07,
    Phase 28) — leave `RunResult` unchanged.
  - Import block (top, ~line 35) — `Jsonb` is NOT imported yet; add it.
- `pycopg/queries.py` §ETL constants (lines 249–301):
  - `ETL_INIT_PIPELINE_RUNS` (line 249) — `watermark JSONB` column (line
    260), reserved & always-NULL until now.
  - `ETL_UPDATE_RUN` (line 270) — the success/failed UPDATE; does NOT set
    `watermark` today.
  - `ETL_GET_LAST_RUN` (line 289) — the shape `_read_watermark`'s new
    success-only query mirrors.
- `pycopg/exceptions.py` §`ETLError` (line 54) — base for the missing-column
  raise (D-06).

### Tests
- `tests/test_etl_accessor.py` — live-DB integration tests
  (`TestETLAccessorIntegration` line 191, `TestRunPipelineIntegration` line
  446). `test_run_writes_full_row` (line 231) asserts `watermark IS NULL`
  for non-incremental runs — the conventions to extend for the incremental
  first-run / failure / empty-batch / round-trip invariants.
- `tests/test_etl.py` — DB-free builder/encode/decode tests
  (`TestEncodeDecodeWatermark` line 629) — extend here only for any new
  pure helper logic; the run-log invariants are integration tests.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`_encode_watermark` / `_decode_watermark`** (`etl.py:580,629`): shipped
  in Phase 26, DB-free and fully tested. Phase 27 only adds the `Jsonb()`
  wrap on write and feeds the read-back `dict` straight into `_decode`.
- **Run-log isolation pattern** (`_start_run`/`_end_run`/`_fetch_run_result`
  via `with self._db.connect(autocommit=True)`): the exact template for
  `_read_watermark` — a short-lived dedicated autocommit connection with the
  `dict_row` factory, independent of any load transaction.
- **`ETL_GET_LAST_RUN`** (`queries.py:289`): the SQL shape the new
  success-only watermark query mirrors (add the `status='success' AND
  watermark IS NOT NULL` predicate).
- **Empty-batch early return** (`run()` line 1138–1140): already records
  `success` + `rows_loaded=0` and returns before the load — the natural seam
  to ensure NO watermark is written for empty batches (D-03 read query makes
  this preserve the prior automatically).

### Established Patterns
- **Dedicated autocommit connection per run-log read/write** — guarantees the
  run row (and now the watermark) commits independently of the load txn, so a
  failed/rolled-back load still records `status='failed'` with NULL
  watermark (ETL-08/09, the no-advance-on-failure invariant).
- **`%s`-only values, identifiers validated first** — the watermark value is
  always a `%s` param wrapped in `Jsonb(...)`, never interpolated.
- **`dict_row` row factory** on run-log connections so the JSONB column comes
  back as a plain Python `dict` ready for `_decode_watermark`.
- **numpydoc shallow docstrings**, `interrogate ≥ 95` gate; **coverage
  ratchet ≥ 94** must hold.

### Integration Points
- `_end_run` success call-site (`run()` line 1210) — passes the encoded
  watermark; the failed call-site (lines 1199–1208) and the empty-batch
  call-site (line 1139) pass none.
- `run()` extract→transform boundary (lines 1108–1113) — the capture point
  for `max(col)` from the raw batch (D-02), and the D-06 missing-column
  guard.
- The async mirror (`AsyncETLAccessor`, line 1214 onward) is intentionally
  NOT touched this phase — parity lands in Phase 28 (ETL-INC-11).

</code_context>

<specifics>
## Specific Ideas

- The scope-seam decision (D-01) was deliberately surfaced: Phase 27's SC-1
  cannot be proven end-to-end without `run()` actually persisting a
  watermark, yet the *full* extract-filter loop (ETL-INC-03/04) is Phase 28.
  Resolution: pull a **minimal** persist+read into 27, keep the WHERE-filter
  and RunResult surface in 28. This keeps each phase's success criteria
  honestly provable while respecting the roadmap's requirement-to-phase map.
- User preference carried from Phase 26: dislikes mixing naive/aware
  datetimes and uses aware datetimes; the typed envelope preserves the offset
  via `isoformat()` (no UTC coercion) — Phase 27's round-trip test should
  verify a tz-aware timestamp comes back with its offset intact.

</specifics>

<deferred>
## Deferred Ideas

- **`WHERE incremental_column > last_watermark` extract wiring (ETL-INC-03)**
  — Phase 28. Phase 27 reads the prior watermark but does not yet apply it
  as a filter (full load every run).
- **`RunResult.watermark_used` / `watermark_recorded` (ETL-INC-07)** + their
  surfacing in `history()` / `last_run()` (ETL-INC-08) — Phase 28;
  `_row_to_result` keeps dropping `watermark` for now.
- **`dry_run` incremental support (ETL-INC-09)** — Phase 28.
- **`AsyncETLAccessor` incremental mirror + `TestEtlParity` (ETL-INC-11)** —
  Phase 28.
- **Incremental docs / backfill-reset workflow (ETL-INC-12)** — Phase 28.
- **Formal ETL-INC-04 missing-column treatment** — Phase 28 owns the
  requirement; Phase 27 ships only the minimal `ETLError` guard (D-06).
- **`float` watermark support** — out of scope for v0.7.0 (not in
  ETL-INC-10); additive later.
- **Naive-datetime rejection policy** — not adopted; offset-preserving
  envelope + documented aware-only contract instead (carried from Phase 26).
- **`initial_watermark` first-run bound** — deferred to v0.8.0
  (ETL-INC-F01).

None of these scope-creep beyond the milestone — they are the explicitly
roadmapped Phase 28 follow-ups.

</deferred>

---

*Phase: 27-incremental-etl-run-log-integration*
*Context gathered: 2026-06-20*
