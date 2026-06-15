# Phase 19: Sync Runner & Query Surface - Context

**Gathered:** 2026-06-15
**Status:** Ready for planning

<domain>
## Phase Boundary

The **return/query surface** of the v0.5.0 sync ETL layer. Phases 16–18 shipped the
machinery: the pure `Pipeline`/builders (16), the run-tracking I/O foundation with
`init`/`_start_run`/`_end_run` on dedicated autocommit connections (17), and the real
`run()` body — extract → transform chain → mode-dispatched atomic load (18). Today
`ETLAccessor.run(pipeline) -> int` returns a bare `run_id`. Phase 19 puts the **user-facing
surface** on top of that machinery:

**In scope (Phase 19):**
- **`RunResult`** (ETL-10): a `@dataclass(frozen=True)` value object carrying the 8 SC-1
  fields — `run_id`, `pipeline_name`, `status`, `rows_extracted`, `rows_loaded`,
  `started_at`, `finished_at`, `error`.
- **`run()` upgrade** (ETL-10): change `run(pipeline) -> int` to `run(pipeline, dry_run=False)
  -> RunResult`. The extract→transform→load body and run-log isolation from Phase 18 stay
  intact; only the return value and the new `dry_run` branch change.
- **`history(name, limit=100)`** (ETL-11): list `RunResult` for a pipeline, newest-first
  (`started_at DESC`). Backed by the existing `ETL_LIST_RUNS` constant.
- **`last_run(name)`** (ETL-17): the most recent `RunResult`, or `None` when no runs exist —
  sugar over the query surface. Backed by the existing `ETL_GET_LAST_RUN` constant.
- **`dry_run=True`** (ETL-15): execute extract + transform, **skip load**, **write no
  `pipeline_runs` row**, and return `RunResult(status='dry_run', rows_loaded=0)`.

**Out of scope (later phases):**
- `AsyncETLAccessor`, lazy `async_db.etl` property, `TestEtlParity`, Sphinx docs, coverage
  gate ratchet, v0.5.0 PyPI release — all Phase 20 (ETL-12/13).
- Finalizing public `__init__.py` exports of `Pipeline`/`RunResult` — pull forward only if a
  Phase 19 test needs it; otherwise Phase 20 finalizes the export surface (matches Phase 18
  Claude's-discretion note). Decide per-test, don't pre-export speculatively.
- Incremental watermarks (the `pipeline_runs.watermark` JSONB column) — v0.6.0. Stays always
  NULL; **not** surfaced on `RunResult` this phase (see D-04).
- Concurrency guards, COPY/streaming, GeoDataFrame routing — still deferred (Phase 18 list).

**Requirements covered:** ETL-10, ETL-11, ETL-15, ETL-17.
(Inherited invariants that must NOT regress: Phase 17 run-log isolation — run-log writes on a
dedicated autocommit connection; Phase 18 load atomicity seam — replace TRUNCATE+INSERT on one
transactional connection. Phase 19 changes only the *return* layer, not these write paths.)
</domain>

<decisions>
## Implementation Decisions

### RunResult value object
- **D-01:** `RunResult` is a **`@dataclass(frozen=True)`**, mirroring `Pipeline` (`etl.py:70`).
  A result is an immutable snapshot of what happened — freezing prevents accidental mutation
  and signals "snapshot, not handle". (Chosen over a plain mutable `@dataclass` like `Config`.)
- **D-02:** `RunResult` carries **exactly the 8 SC-1 fields and no more**: `run_id`,
  `pipeline_name`, `status`, `rows_extracted`, `rows_loaded`, `started_at`, `finished_at`,
  `error`. No speculative fields.
- **D-03:** **`error` is the message string only** — `error: str | None`, populated from the
  `pipeline_runs.error_message` column (`None` on success/dry_run). The `error_traceback`
  column stays in the DB row for forensics (queryable) but is **not** a `RunResult` field.
  Rationale: matches SC-1's single `error` field literally; keeps the object and its repr
  clean for the common case (`print(result.error)`). (Chosen over carrying both columns or
  wrapping in an exception-like object.)
- **D-04:** **No `watermark` field on `RunResult` this phase.** The column exists in
  `pipeline_runs` and is always NULL in v0.5.0; surfacing a perpetually-`None` field is noise.
  It is added in v0.6.0 alongside the feature that fills it. (No speculative generality.)
- **D-05:** **`run_id` is `int | None`** (not a plain `int`) — because a `dry_run` `RunResult`
  has no DB row and therefore no id (D-08). For real runs it is the `BIGSERIAL` id; for dry
  runs it is `None`.

### history() / last_run() query surface
- **D-06:** **`history(name: str, limit: int = 100) -> list[RunResult]`**. The existing
  `ETL_LIST_RUNS` constant already has a `LIMIT %s`, so a value is always bound; `limit=100` is
  a safe default cap that a caller can raise (echoes the `default_batch_size=1000` safe-default
  instinct in `Config`). Newest-first (`started_at DESC`) is already locked in the constant —
  do not re-author the SQL. (Chosen over `limit=None` "all rows" or a hidden fixed cap.)
- **D-07:** **`last_run(name: str) -> RunResult | None`** is sugar over the query surface
  (ETL-17): returns the most recent `RunResult`, or `None` when no runs exist for that name
  (SC-3). Backed by the existing `ETL_GET_LAST_RUN` constant (`LIMIT 1`). Whether it delegates
  to `history(name, limit=1)[0]` or runs `ETL_GET_LAST_RUN` directly is **Claude's discretion**
  (both correct; pick the clearer/cheaper one — likely the dedicated constant since it exists).

### dry_run semantics
- **D-08:** With `dry_run=True`: run extract + transform, **skip the load entirely**, **write
  no `pipeline_runs` row** (no `init`/`_start_run`/`_end_run`), and return a `RunResult` built
  **in-memory** with: `status='dry_run'`, `rows_loaded=0`, **`run_id=None`** (no DB row → no id;
  `None` honestly signals "not persisted"), `rows_extracted=len(df)` after extract+transform
  (the work that DID happen — a meaningful "how many rows would this pull?" preview),
  `started_at`/`finished_at` = the in-memory run window (`datetime.now(UTC)` bracketing the
  dry run), `error=None`, `pipeline_name=pipeline.name`. (Chosen over a sentinel `run_id` and
  over a minimal zeros-only result.)
- **D-09:** Because a dry run touches no run-log connection, it cannot leave a `'running'` row
  behind and cannot fail a `_end_run` — the dry-run branch is a clean early path that never
  enters the Phase 18 run-log/load bracketing.

### RunResult construction seam (how run/history/last_run share code)
- **D-10:** **Single source of truth = the DB row, single mapper.** A module-level pure
  function `_row_to_result(row: dict) -> RunResult` (next to the existing module-level builders
  `_build_insert_sql`/`_build_upsert_sql`/`_step_label` in `etl.py`) maps a `dict_row` from
  `pipeline_runs` to a `RunResult`: maps `error_message → error`, drops `error_traceback` and
  `watermark`. Pure and unit-testable without a DB (feed it a dict). (Chosen over a method on
  `ETLAccessor` or a `RunResult.from_row` classmethod — the latter would leak DB column names
  like `error_message`/`watermark` into the public dataclass.)
- **D-11:** **`run()` (non-dry) returns by re-SELECTing the row it just wrote**, by `run_id`,
  after `_end_run`, then mapping it through `_row_to_result`. One source of truth (the DB row),
  one mapper shared with `history`/`last_run`, guaranteed-consistent values. Cost is one extra
  SELECT per run — negligible against the load. (Chosen over assembling the `RunResult`
  in-memory from values `run()` already holds, which risks drift between the Python-side values
  and what the DB actually stored, and creates a second construction path to keep in sync.)
- **D-12:** `history()` and `last_run()` build their `RunResult`(s) from `pipeline_runs` rows
  via the **same** `_row_to_result` mapper. Only `dry_run` builds a `RunResult` outside the
  mapper (in-memory, D-08) — and that is acceptable because a dry run has no row to map.

### Claude's Discretion
- Whether `last_run` delegates to `history(name, limit=1)` or runs `ETL_GET_LAST_RUN` directly
  (D-07).
- The SELECT-by-`run_id` query `run()` uses for its re-SELECT (D-11). **Note for
  researcher/planner:** the existing `ETL_LIST_RUNS`/`ETL_GET_LAST_RUN` filter by
  `pipeline_name`, **not** `run_id` — a new small constant (e.g. `ETL_GET_RUN = SELECT * FROM
  pipeline_runs WHERE run_id = %s`) is likely needed, OR `run()` may reuse `ETL_GET_LAST_RUN`
  by `pipeline_name` (correct only if no concurrent run for the same name could interleave —
  Phase 17 D-06 accepts a left-`running` row, so prefer a `run_id`-keyed SELECT for
  correctness). Planner decides; lean toward a `run_id`-keyed constant.
- Whether `Pipeline`/`RunResult` are exported in `__init__.py` now (only if a Phase 19 test
  imports `RunResult` from the package root) or deferred to Phase 20.
- Field ordering inside the `RunResult` dataclass and exact type hints for timestamps
  (`datetime`) — match what `dict_row` returns from `TIMESTAMPTZ` columns.
- The status literal type — whether `status` is a plain `str` or a `Literal['running',
  'success','failed','dry_run']` annotation (the latter is nice but introduces a 4th value
  beyond the DB's 3-valued CHECK; keep `dry_run` as a RunResult-only status — never persisted).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope (authoritative)
- `.planning/ROADMAP.md` §"Phase 19: Sync Runner & Query Surface" — Goal + 4 success criteria
  (SC-1 `RunResult` fields; SC-2 `history` newest-first + two-runs-two-entries; SC-3 `last_run`
  most-recent-or-`None`; SC-4 `dry_run` extract+transform, skip load, no row, `status='dry_run'`,
  `rows_loaded=0`).
- `.planning/REQUIREMENTS.md` — **ETL-10** (`run` returns `RunResult` with the 8 fields),
  **ETL-11** (`history` newest-first), **ETL-15** (`dry_run` skips load + writes no record),
  **ETL-17** (`last_run` most-recent-or-`None`, sugar over `history`). Plus the "Out of Scope"
  table (no DAG/scheduling, no new runtime deps) and the watermark Future Requirement.
- `.planning/PROJECT.md` §"Current Milestone: v0.5.0" — milestone goal + locked constraints
  (zero new runtime deps, mirror `spatial.py`, same-DB only, watermarks deferred to v0.6.0
  with the `pipeline_runs` table designed for additive slot-in).

### Prior phase context (decisions that flow into this phase)
- `.planning/phases/18-load-modes-extract/18-CONTEXT.md` — the `run()` body Phase 19 wraps:
  the extract→transform→load seam, the load-atomicity session/transaction seam (D-01/D-02),
  and the explicit deferral of `RunResult`/`history`/`last_run`/`dry_run` to **this** phase
  ("Phase 18's `run()` returns a minimal value Phase 19 upgrades"). Phase 19 must NOT change
  the load write paths — only the return layer.
- `.planning/phases/17-run-tracking-foundation/17-CONTEXT.md` — **run-log isolation contract**
  (run-log writes on a dedicated autocommit connection; must not regress) and the locked
  decision that **`dry_run` is never persisted** and `RunResult(status='dry_run')` is a
  transient object outside the 3-valued status CHECK (`running`/`success`/`failed`). The
  `pipeline_runs` column shape and the `ETL_LIST_RUNS`/`ETL_GET_LAST_RUN` ordering originate here.
- `.planning/phases/16-pure-etl-layer/16-CONTEXT.md` — `Pipeline` field semantics and the
  pure-builder/module-function pattern `_row_to_result` should mirror (D-10). Do not re-author.

### Codebase precedent (the methods/symbols to compose)
- `pycopg/etl.py` — `ETLAccessor.run` (lines ~579–781, currently `-> int`; upgrade return +
  add `dry_run` branch), `init`/`_start_run`/`_end_run` (run-log I/O, unchanged), the
  module-level pure builders `_build_insert_sql`/`_build_upsert_sql`/`build_truncate_sql`/
  `_step_label` (the pattern `_row_to_result` joins). `Pipeline` `@dataclass(frozen=True)`
  (line ~70) is the style precedent for `RunResult`.
- `pycopg/queries.py` §"ETL QUERIES" (lines ~246–295) — `ETL_LIST_RUNS` (`WHERE pipeline_name
  = %s ORDER BY started_at DESC LIMIT %s` → backs `history`), `ETL_GET_LAST_RUN`
  (`… LIMIT 1` → backs `last_run`), and the `pipeline_runs` column list from
  `ETL_INIT_PIPELINE_RUNS`. **A `run_id`-keyed SELECT constant likely needs adding** for D-11
  (the two existing constants filter by `pipeline_name`, not `run_id`).
- `pycopg/config.py` §`Config` (line ~25) — the mutable-`@dataclass` style we explicitly did
  NOT pick for `RunResult` (D-01 chose frozen).
- `pycopg/__init__.py` — current exports (3 ETL exceptions only; `Pipeline`/`ETLAccessor` not
  yet exported). `RunResult` export decision is Claude's discretion / Phase 20.
- `psycopg.rows.dict_row` — already imported in `etl.py`; the row factory whose dicts
  `_row_to_result` consumes.

### Tests
- `tests/` ETL integration tests (real `pycopg_test` PG, not mocks — I/O-heavy paths, Phase 18
  precedent) must gain: `run()` returns `RunResult` (SC-1 fields); `history` newest-first +
  two-entries (SC-2); `last_run` most-recent + `None`-when-empty (SC-3); `dry_run` skips load,
  writes no row, returns `status='dry_run'`/`rows_loaded=0`/`run_id=None` (SC-4). Plus a pure
  unit test for `_row_to_result` (feed it a dict, no DB).
- ⚠ Known local-env flaky DB tests exist (see memory `pycopg-flaky-db-tests`) — for targeted
  runs use `-o addopts=""`. Coverage gate stays **94** this phase (measure before any ratchet).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ETL_LIST_RUNS` / `ETL_GET_LAST_RUN` — already authored (Phase 16), correct ordering and
  filtering; `history`/`last_run` bind params to them, no new SQL for the query surface.
- The `dict_row` cursor pattern (`etl.py:491,515,565`) — `history`/`last_run` reuse it to get
  dict rows that `_row_to_result` maps.
- The module-level pure-builder pattern (`_build_insert_sql`, `_step_label`) — `_row_to_result`
  slots in as a peer (pure, DB-free unit-testable).
- `Pipeline`'s `@dataclass(frozen=True)` — the exact style precedent for `RunResult`.

### Established Patterns
- Run-log writes stay isolated on a dedicated autocommit connection (Phase 17); the load stays
  atomic on one transactional connection (Phase 18). **Phase 19 touches neither write path** —
  it adds a return-value re-SELECT (D-11), reads (`history`/`last_run`), and a no-write dry-run
  branch (D-08). No new write semantics.
- `%s`-only parameterization; `validate_identifiers` before any identifier interpolation. The
  Phase 19 reads filter `pipeline_runs` by `pipeline_name`/`run_id` (bound params, no
  user-supplied identifiers) — no new injection surface, but keep the param discipline.
- Safe defaults (cf. `default_batch_size=1000`) → `history(limit=100)` (D-06).

### Integration Points
- `pycopg/etl.py` `ETLAccessor` gains: `RunResult` dataclass, `_row_to_result` helper,
  `run(..., dry_run=False) -> RunResult` (return upgrade + dry-run branch + re-SELECT),
  `history(name, limit=100) -> list[RunResult]`, `last_run(name) -> RunResult | None`.
- `pycopg/queries.py` likely gains one `run_id`-keyed SELECT constant for D-11 (planner's call).
- No `async_database.py` changes (async is Phase 20). No load-path changes.
- Coverage: measure against real `pycopg_test`; gate stays 94 this phase.

</code_context>

<specifics>
## Specific Ideas

- The throughline: Phase 19 is a **thin, honest return/query layer** over machinery that
  already works — change the return *type*, add reads, add a no-write dry-run path; do not
  touch the hardened write seams from Phases 17/18. Same "compose, don't re-author" instinct
  the user carried through Phase 18.
- **One source of truth, one mapper** (D-10/D-11): every `RunResult` from a *persisted* run is
  built from the DB row via `_row_to_result`, so `run`, `history`, and `last_run` can never
  drift. The single accepted exception is `dry_run`, which has no row to map (D-08/D-12).
- **`run_id=None` for dry runs** was chosen as the honest signal over a magic sentinel — a dry
  run genuinely has no id, and `if result.run_id is None` is a clean dry-run check.
- **`error` = message string only** (D-03) keeps the everyday `result.error` ergonomic; the
  full traceback lives in the DB for when you actually need to dig.

</specifics>

<deferred>
## Deferred Ideas

- **`watermark` on `RunResult`** — v0.6.0, alongside incremental-watermark support. The column
  stays always-NULL in v0.5.0; not surfaced now (D-04).
- **`Literal` status type / 4th persisted status** — `dry_run` stays a RunResult-only status,
  never written to `pipeline_runs` (3-valued CHECK preserved, Phase 17). A typed `Literal`
  annotation is optional polish, not required.
- **Public `__init__.py` export of `Pipeline`/`RunResult`/`ETLAccessor`** — Phase 20 finalizes
  the export surface; pull forward in Phase 19 only if a test imports from the package root.
- **`AsyncETLAccessor` parity** (`async_db.etl.run`/`history`/`last_run`/`dry_run` returning the
  same `RunResult`), `TestEtlParity`, Sphinx docs, coverage ratchet, v0.5.0 release — Phase 20
  (ETL-12/13).
- **Paging beyond `history(limit=)`** (cursor/offset pagination, `history` filters by status or
  time range) — not requested for v0.5.0; revisit if real usage needs it.

### Reviewed Todos (not folded)
None — no pending todos existed to review (STATE.md "Pending Todos: None").

</deferred>

---

*Phase: 19-sync-runner-query-surface*
*Context gathered: 2026-06-15*
