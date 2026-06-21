# Phase 28: Incremental ETL — Extract, RunResult & Async Parity - Context

**Gathered:** 2026-06-21
**Status:** Ready for planning

<domain>
## Phase Boundary

Close the incremental ETL loop **end-to-end**. Phases 26 (pure layer) and 27
(sync run-log persist + read) are done; the `WHERE col > watermark` filter is
built but **not yet applied**, the watermark is **not surfaced** on
`RunResult`, `dry_run` is **watermark-blind**, and the **async accessor has
zero watermark wiring**. Scope = **ETL-INC-03, -04, -07, -08, -09, -11, -12**.

Deliverables this phase:

1. **Wire the watermark filter into the sync `run()` extract** (ETL-INC-03) —
   call `_read_watermark(name)` before extract, feed the floor through
   `_build_incremental_extract_sql` (the Phase-26 builder that exists but is
   **currently never called**), so a subsequent run pulls only
   `col > last_watermark` as a `%s` param. First run / `watermark=None` →
   full unfiltered extract (builder already handles this, D-12).
2. **Formalize ETL-INC-04 missing-column handling** — the sync `max(col)`
   capture + `ETLError` missing-column guard + float/NaN/all-NULL guards
   already landed in Phase 27 (D-06 minimal pull-forward). This phase owns the
   formal requirement; the sync code is already compliant — refine only if a
   test gap surfaces. The async port must replicate these guards exactly.
3. **`RunResult.watermark_used` / `watermark_recorded`** (ETL-INC-07) —
   two new fields on the frozen dataclass; both `None` for non-incremental
   pipelines.
4. **`history()` / `last_run()` surface the watermark** (ETL-INC-08) —
   `_row_to_result` stops dropping `watermark` and maps it to
   `watermark_recorded`; `watermark_used` is `None` for stored rows (D-A1).
5. **Incremental `dry_run`** (ETL-INC-09) — reads the prior watermark, applies
   the filter, reports `watermark_used` + would-be `watermark_recorded`,
   writes no `pipeline_runs` row (D-A2).
6. **Full async parity** (ETL-INC-11) — port the ENTIRE Phase-27+28 stack into
   `AsyncETLAccessor` as a strict 1:1 behavioral mirror (D-A3).
7. **Docs** (ETL-INC-12) — a `## Incremental loading` section in
   `docs/etl.md`: contract + worked example + backfill/reset workflow (D-A4,
   D-A5).

**OUT of scope (do NOT pull forward):** `initial_watermark` first-run bound
(v0.8.0, ETL-INC-F01), configurable `>=` boundary (v0.8.0, ETL-INC-F02),
multi-column watermarks (ETL-INC-F03), any public reset/backfill **API**
(reset is documented manual SQL only — D-A5), the v0.7.0 release mechanics
(version bump / tag / PyPI — Phase 29, REL-07).

</domain>

<decisions>
## Implementation Decisions

### `RunResult` & `history()` / `last_run()` shape
- **D-A1: `watermark_used = None` for stored rows; no schema change.**
  `RunResult` gains exactly two fields: `watermark_recorded` (the new
  high-water mark persisted = the stored `pipeline_runs.watermark` column,
  decoded) and `watermark_used` (the filter floor applied THIS run = what
  `_read_watermark` returned before extract). `watermark_used` is a per-run
  **input** that is NOT stored anywhere, so `history()` / `last_run()` (which
  read old rows) populate `watermark_recorded` from the row and set
  `watermark_used = None`. **No new `pipeline_runs` column, no migration** —
  the v0.5.0-reserved single `watermark JSONB` column is sufficient. The
  "store watermark_used too" (extra column + SQL + migration) and "derive from
  prior row" (fragile, breaks on empty/failed runs) options were rejected.
- **D-A1a (mechanical, locked): non-incremental → both fields `None`
  everywhere.** Roadmap SC-3. The stored `watermark` is NULL for
  non-incremental runs, so `_row_to_result` must map NULL → `None` (decode
  only when the column is non-NULL). Applies to `run()`, `dry_run`,
  `history()`, `last_run()`.

### `dry_run` incremental semantics
- **D-A2: `dry_run` = faithful filtered preview.** On an incremental
  pipeline, `dry_run` reads `_read_watermark(name)`, applies
  `WHERE col > wm` to the extract (identical filter to a real run), sets
  `watermark_used` = that floor and `watermark_recorded` = `max(col)` of the
  **filtered raw batch** (or `None` if the filtered batch is empty / all-NULL),
  and writes **no** `pipeline_runs` row (`status='dry_run'`, `run_id=None`).
  `rows_extracted` therefore reflects the **real would-be pull**. The
  "unfiltered + computed marks" option (misleading row counts) was rejected.
- **D-A2a (consequence, planner-facing): single filtered-extract path.**
  Because both the `dry_run` fork and the real path must apply the *same*
  watermark filter, the watermark read + filtered extract should be factored
  so the two paths cannot drift (today they duplicate the unfiltered extract
  block). **Exact factoring is planner discretion** (extract helper vs inline
  in both forks) — the locked contract is only that both forks read the
  watermark and apply `_build_incremental_extract_sql` identically.

### Async parity port
- **D-A3: `AsyncETLAccessor` is a strict 1:1 behavioral mirror.** Async
  currently has ZERO watermark wiring (Phase 27 deliberately skipped it —
  verified: no `watermark` references at/after line 1334, `_end_run` still
  uses `ETL_UPDATE_RUN` without a `watermark=` param, no async
  `_read_watermark`). Phase 28 ports the **entire** stack: async
  `_read_watermark`, `_end_run(watermark=)` switching to
  `ETL_UPDATE_RUN_WATERMARK` + `Jsonb()` wrap, the raw-batch `max(col)`
  capture, the WHERE-filter extract, the `RunResult` fields, and incremental
  `dry_run`. **Guard semantics and `ETLError` message text must be
  byte-for-byte equivalent** to sync: missing-column → `ETLError` (same
  message shape, names the column + lists extracted columns + cites
  ETL-INC-04); float dtype → `ETLError` (same message, names the column,
  points to INTEGER/TIMESTAMP, lists `_WATERMARK_SUPPORTED`); NaN/NaT /
  all-NULL / empty batch → preserve prior watermark (no NULL write). Only
  mechanical differences allowed: `await` on DB calls, `asyncio.to_thread`
  for transform steps (existing SC-2 pattern). The "async-idiomatic messages
  OK" option was rejected — Core Value is strict parity.

### Docs (ETL-INC-12)
- **D-A4: `docs/etl.md` = contract + worked example.** New
  `## Incremental loading` section covering: a worked
  `Pipeline(incremental_column="updated_at", load_mode="upsert", ...)`
  example; watermark-column requirements (monotonic, non-decreasing,
  aware-datetime, `>` exclusive, single-column); why `upsert` is required
  (append/replace forbidden at construction); the new
  `watermark_used` / `watermark_recorded` `RunResult` fields; the `dry_run`
  preview behavior; and the backfill/reset workflow. Covers ETL-INC-12 fully
  without a full multi-run tutorial (the "minimal contract only" and "full
  tutorial" options were both rejected).
- **D-A5: backfill/reset = documented manual SQL (no new API).** There is no
  public reset API and `initial_watermark` is deferred to v0.8.0, so the docs
  prescribe the only available mechanism: to force a full reload, the operator
  neutralizes the last successful watermark directly, e.g.
  `UPDATE pipeline_runs SET watermark = NULL WHERE pipeline_name = %s` (or
  DELETE the run rows). The next `run()` then reads `None` → full extract →
  records a fresh watermark. The docs should note that an `initial_watermark`
  first-run bound is coming in v0.8.0. Adding a `db.etl.reset_watermark()`
  helper this phase was explicitly rejected as scope creep (not in any
  ETL-INC-* requirement; would need sync+async+parity+tests).

### Claude's Discretion
- Exact factoring of the shared filtered-extract path (D-A2a) — helper method
  vs inline mirror in both the dry-run fork and the real path; follow the
  existing extract-block style in `run()`.
- Whether `_row_to_result` decodes the watermark inline or via a tiny guarded
  helper (NULL → `None`, else `_decode_watermark`).
- Exact integration-test placement and fixture reuse — extend the existing
  Phase-27 incremental test classes (`TestRunResultSurface` /
  `TestAsyncRunResultSurface` and the watermark tests around
  `tests/test_etl_accessor.py:1378`) following their cleanup conventions.
- Exact docstring wording — numpydoc shallow style, `interrogate ≥ 95`.
- Whether the async incremental integration tests reuse the sync test
  fixtures or define async mirrors — follow the existing
  `TestAsyncRunResultSurface` precedent.

### Fact correction for downstream agents
- **The roadmap SC-5 phrase "`TestEtlParity` passes with incremental methods
  included" is STALE.** `TestEtlParity` was **removed** —
  `tests/test_parity.py:516` documents that ETL parity is now covered by the
  generic `test_accessor_parity` over the `ACCESSOR_PAIRS` registry
  (`(ETLAccessor, AsyncETLAccessor)` entry, `test_parity.py:24-36`). That test
  compares the **public method surface** of the two classes, so the new
  incremental surface is parity-checked automatically once both accessors
  expose the same public methods. Behavioral incremental parity is covered by
  the async integration tests mirroring the sync ones (NOT by a `TestEtlParity`
  class). Downstream: do NOT create/restore a `TestEtlParity` class; satisfy
  SC-5 via `test_accessor_parity` (structural) + async integration tests
  (behavioral).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope (LOCKED — read first)
- `.planning/REQUIREMENTS.md` — v0.7.0 requirements. **In scope this phase:
  ETL-INC-03, -04, -07, -08, -09, -11, -12.** The "Locked scope decisions
  (cadrage 2026-06-19)" block is binding (`max(col)` from raw batch before
  transforms; read from last *successful* run; advance only on success; empty
  batch preserves; `>` exclusive; upsert-only; full sync/async parity). The
  **Out of Scope** table is binding (`initial_watermark`, `>=` boundary,
  multi-column, CDC, reset API are all deferred/excluded).
- `.planning/ROADMAP.md` §"Phase 28: Incremental ETL — Extract, RunResult &
  Async Parity" — Goal + 5 Success Criteria. **Note SC-5's `TestEtlParity`
  reference is stale — see the "Fact correction" decision above.**
- `.planning/PROJECT.md` §"Current Milestone: v0.7.0" — milestone goal and
  locked scope summary. **Core Value: strict sync/async parity.**

### Upstream phase context (what this integrates)
- `.planning/phases/27-incremental-etl-run-log-integration/27-CONTEXT.md` —
  D-01..D-07. Most relevant: D-01 (the minimal sync `max(col)` + persist
  pulled forward — Phase 28 layers the WHERE-filter, RunResult, dry_run, and
  the async mirror on this seam), D-07 (call-site coercion — frozen
  `_encode_watermark`, do NOT reopen).
- `.planning/phases/26-incremental-etl-pure-layer/26-CONTEXT.md` —
  D-01..D-17. Most relevant: the typed-envelope contract (D-01..D-05),
  `_build_incremental_extract_sql` builder spec (D-06..D-13) — **this is the
  builder Phase 28 finally wires into `run()`**, and D-12 (`watermark=None` →
  full unfiltered SELECT, so first-run needs no caller branch).

### Code to read & extend (`pycopg/etl.py`, 1803 lines)
- `RunResult` dataclass (line 260) — currently **8 fields, no watermark**;
  gains `watermark_used` + `watermark_recorded` (D-A1). Update the docstring
  Parameters block.
- `_build_incremental_extract_sql` (line 513) — the Phase-26 builder, **built
  and unit-tested but NEVER called**; Phase 28 wires it into both `run()`
  extract paths. `watermark=None` → full SELECT; else
  `... WHERE col > %s` with the value as the sole `%s` param.
- `_encode_watermark` (line 581) / `_decode_watermark` (line 630) — **frozen**
  (Phase 26). Used for the recorded value round-trip; do NOT reopen.
- `_row_to_result` (line 688) — currently **drops `watermark`** (the Phase-27
  comment says "drops … watermark (D-10)"); Phase 28 maps `row["watermark"]`
  → `watermark_recorded` (NULL → `None`), sets `watermark_used=None` (D-A1).
- `ETLAccessor._read_watermark` (line 960) — exists, tested, **currently
  unused**; Phase 28 calls it before extract in `run()` (and `dry_run`).
- `ETLAccessor._end_run` (line 795) — already has `watermark=` param +
  `ETL_UPDATE_RUN_WATERMARK` + `Jsonb()` (Phase 27). Sync side done; the
  **async `_end_run` (line 1412) does NOT** — it must gain this.
- `ETLAccessor.run` (line 1000) — sync. The dry-run fork (lines 1078–1141)
  and real path (lines 1148–1331). Real path already captures `max(col)` with
  float/NaN/missing-col guards (lines 1191–1223) and persists via
  `_end_run(..., watermark=)` (line 1330). **Phase 28 adds:** the
  `_read_watermark` call + filtered extract (replace the inline
  `to_dataframe` blocks at 1083–1108 and 1152–1178 with the
  `_build_incremental_extract_sql` path), the dry-run incremental branch, and
  the `RunResult` field population.
- `AsyncETLAccessor` (line 1334) — **ZERO watermark wiring**. async
  `_read_watermark` (line ~1462 area) does NOT exist; `_end_run` (line 1412)
  has no `watermark=`; async `run()` (line 1536) has no capture/filter. This
  is the bulk of the phase (D-A3, strict mirror).
- `pycopg/queries.py` §ETL constants — `ETL_GET_LAST_WATERMARK` (line 303),
  `ETL_UPDATE_RUN_WATERMARK` (line 313) both exist (Phase 27); async reuses
  them. `ETL_LIST_RUNS` / `ETL_GET_LAST_RUN` use `SELECT *` so the row dict
  already carries `watermark` for `_row_to_result` to map.
- `pycopg/exceptions.py` §`ETLError` (line 54) — base for the missing-column
  / float-dtype guards (sync already raises it; async mirrors).

### Tests
- `tests/test_etl_accessor.py` — live-DB integration. Existing Phase-27
  incremental tests to extend/mirror: `test_first_run_records_watermark`
  (1378), `test_failed_run_does_not_advance_watermark` (1409),
  `test_empty_batch_preserves_watermark` (1466),
  `test_watermark_jsonb_roundtrip` (1537),
  `test_read_watermark_none_first_run` (1593),
  `test_incremental_column_missing_raises_etlerror` (1598),
  `test_float_incremental_column_raises_etlerror` (1613),
  `test_all_null_incremental_column_preserves_watermark` (1636).
  `TestRunResultSurface` (1062) and `TestAsyncRunResultSurface` (1728) are the
  seams for the new `watermark_used`/`watermark_recorded` surface +
  filtered-extract + dry-run + async-parity behavioral tests.
- `tests/test_etl.py` — DB-free builder/encode/decode tests
  (`TestEncodeDecodeWatermark`); add DB-free coverage only for any new pure
  logic (e.g. exercising `_build_incremental_extract_sql` wiring is mostly
  integration).
- `tests/test_parity.py` — `ACCESSOR_PAIRS` registry (line 24) +
  `test_accessor_parity` (line 36); the comment at line 516 records that
  `TestEtlParity` was removed. **This is how SC-5 structural parity is met.**

### Docs
- `docs/etl.md` (7279 bytes) — headings at `## Access Pattern`,
  `## Defining a Pipeline`, `## run`, `## history`, `## last_run`,
  `### Dry runs`, `## Async Usage`, `## Security`. Add `## Incremental
  loading` (D-A4) and ensure Sphinx `-W` stays clean (Phase 29 gate).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`_build_incremental_extract_sql`** (`etl.py:513`): the Phase-26 builder,
  fully unit-tested, that Phase 28 finally calls. Handles both source kinds
  (SQL subquery wrap / table WHERE-append) and `watermark=None` → full SELECT.
  The `(sql, params)` 2-tuple plugs straight into a `to_dataframe(sql=…,
  params=…)` call.
- **`_read_watermark`** (`etl.py:960`, sync): exists + tested; just needs to
  be *called* before extract. Async equivalent must be written.
- **Phase-27 sync `run()` capture block** (`etl.py:1191–1223`): the exact
  `max(col)` + float/NaN/all-NULL/missing-col guard logic to **copy verbatim**
  into async (D-A3). `pd.isna(m)` precedes the `is_float` branch (NaN is a
  float — Phase 27 bug-fix WR-02, preserve this ordering).
- **Sync `_end_run(watermark=)` + `Jsonb()` write-site** (`etl.py:795`):
  the template the async `_end_run` must replicate (switch to
  `ETL_UPDATE_RUN_WATERMARK`, wrap with `Jsonb(watermark)`).
- **`test_accessor_parity`** (`test_parity.py:36`): structural surface parity
  is automatic once both accessors expose identical public methods — no
  per-method parity test to write.

### Established Patterns
- **`%s`-only values, identifiers validated first** — the watermark filter
  value is a `%s` param via the builder; never interpolated.
- **Dedicated autocommit connection per run-log read/write** (`_read_watermark`
  / `_start_run` / `_end_run`) — the async ports use
  `async with self._db.connect(autocommit=True)` + `dict_row`, independent of
  the load txn (no-advance-on-failure invariant).
- **Watermark from the RAW batch before transforms** (D-02, Phase 27) — the
  capture point is right after extract, before the transform loop; the
  filtered extract narrows what "raw batch" means for incremental runs but the
  before-transform timing is unchanged.
- **numpydoc shallow docstrings**, `interrogate ≥ 95`, **coverage ratchet
  ≥ 94** must hold (Phase 29 gate is `-W`-clean Sphinx too).

### Integration Points
- `run()` extract (sync 1083–1108 dry / 1152–1178 real; async 1603–1628 dry /
  real path) — the four inline `to_dataframe` blocks become watermark-aware
  via `_build_incremental_extract_sql`. The `extract_limit` LIMIT handling
  must compose with the filter (planner decides ordering — LIMIT on the
  filtered subquery).
- `_end_run` success call-sites (sync 1330 done; async equivalent to add) —
  pass the encoded watermark only on success; failed/empty pass none.
- `_row_to_result` (688) feeds `history()` (905) / `last_run()` (934) and
  `_fetch_run_result` (883) — once it maps `watermark` → `watermark_recorded`,
  all three surfaces gain the field for free.
- `AsyncETLAccessor` (1334+) — the entire watermark surface is net-new here;
  this is the largest single chunk of the phase.

</code_context>

<specifics>
## Specific Ideas

- The `_build_incremental_extract_sql` builder has sat **built-but-unwired**
  since Phase 26 specifically so this phase could plug it in once the read
  (`_read_watermark`, Phase 27) and the write (`_end_run(watermark=)`,
  Phase 27) halves existed. Phase 28 is the "connect the three" phase: read →
  filter-extract → record.
- User preference carried from Phases 26/27: aware datetimes, offset preserved
  via `isoformat()` (no UTC coercion). The dry-run preview and async port must
  not introduce any tz normalization; the round-trip tests should assert a
  tz-aware timestamp returns with its offset intact (mirror the Phase-27
  round-trip test).
- The `dry_run` filtered-preview decision (D-A2) was chosen over an unfiltered
  preview specifically so `rows_extracted` is an honest "what would a real run
  pull" number for incremental pipelines — the whole point of a dry run.

</specifics>

<deferred>
## Deferred Ideas

- **`initial_watermark` first-run bound** — v0.8.0 (ETL-INC-F01). Avoids a
  full-table scan on the first incremental run of a huge source. Documented as
  "coming in v0.8.0" in the backfill section (D-A5).
- **Configurable `>=` boundary / late-data lookback** — v0.8.0 (ETL-INC-F02);
  `>` exclusive is the v0.7.0 contract.
- **Multi-column / composite watermarks** — deferred (ETL-INC-F03).
- **Public `db.etl.reset_watermark()` helper** — rejected as scope creep
  (D-A5); reset is documented manual SQL in v0.7.0. Revisit if a real
  operator need appears in a later milestone.
- **`float` watermark support** — out of scope for v0.7.0 (not in
  ETL-INC-10); the sync (and now async) `run()` raises a clear `ETLError` for
  float incremental columns.
- **Storing `watermark_used` in `pipeline_runs`** (extra column) — rejected
  (D-A1); `watermark_used` stays a per-run input, `None` for stored rows. A
  full audit-trail column could be revisited later if users need historical
  filter floors, but it costs a schema change.
- **v0.7.0 release mechanics** (version bump, CHANGELOG/MIGRATION finalize,
  tag, PyPI) — Phase 29 (REL-07).

None of these scope-creep beyond the milestone — they are the explicitly
roadmapped v0.8.0 follow-ups or the Phase 29 release.

</deferred>

---

*Phase: 28-incremental-etl-extract-runresult-async-parity*
*Context gathered: 2026-06-21*
