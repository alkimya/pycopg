# Phase 49: Incremental ETL Follow-ups - Context

**Gathered:** 2026-07-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Give users precise control over the **boundaries and concurrency safety** of incremental
`Pipeline` runs — four additive, keyword-only, sync/async-parity follow-ups on `db.etl.*` /
`Pipeline` (ETL-INC-F01..F04). All non-breaking under the frozen SemVer 1.0 API, zero new
runtime dependencies. Every knob defaults to today's exact behavior (byte-identical when unset).

1. **F01** — `initial_watermark`: bound/seed the first incremental run instead of a full initial load.
2. **F02** — configurable boundary: inclusive `>=` and/or a lookback overlap, instead of only the fixed exclusive `>`.
3. **F03** — composite (multi-column) incremental watermark key.
4. **F04** — advisory-lock concurrency safety: serialize or refuse overlapping runs of the same pipeline, sync + async.

**NOT in scope** (roadmap-fixed, don't add): **CDC / WAL change capture (ETL-INC-F05 — deferred
2026-07-02, a large distinct subsystem)**, any new load mode, any change to the shipped
`load_mode="upsert"`-required rule for incremental, any breaking change to an existing signature,
streaming/`extract_batch_size`. SPAT-F01 (gridSize) and RASTER-F01 remain deferred to future cycles.
</domain>

<decisions>
## Implementation Decisions

### Carried forward from shipped v0.7.0 incremental ETL (LOCKED — do not reopen)
- **C-01:** Incremental **requires `load_mode="upsert"`** (v0.7.0 D-16) — `append`/`replace` rejected at construction. This idempotency is what makes every F02 `>=`/lookback replay and every F03 boundary re-read safe. All four features build on it.
- **C-02:** Watermark is a **typed JSONB envelope** `{"type": ..., "value": ...}`, allowlist exactly `{datetime, int, str}`; `bool` and `float` are rejected loud (`ETLError`). `bool` rejected before the `int` branch (subclass trap). Encode/decode helpers: `_encode_watermark` (etl.py:607), `_decode_watermark` (etl.py:656) — **frozen; extend by adding a new tag, never mutate the existing three.**
- **C-03:** High-water mark = `max(col)` of the **raw** batch *before* transforms; advances **only on a real load**; empty batch (0 rows) records **no** watermark and preserves the prior via `ETL_GET_LAST_WATERMARK`'s `status='success' AND watermark IS NOT NULL` predicate. Never NULL-overwrites.
- **C-04:** Builder-pur (`validate_identifiers` line 1, user values bound `%s`/`%(name)s`, never interpolated); full sync/async parity — **edit both `ETLAccessor` (etl.py:758) and `AsyncETLAccessor` (etl.py:1484) in the same commit**, register any new public method/param in `tests/test_parity.py`.

### F01 — first-run seed (`initial_watermark`)
- **D-01:** **Seed-floor-only semantics.** When NO stored watermark exists (true first run), use `initial_watermark` as the `WHERE col > initial_watermark` floor — turning the first full-load into a bounded incremental load. Once the first successful run records `max(col)`, `initial_watermark` is **never consulted again**. Implemented as the value returned by `_read_watermark` when the stored watermark is absent — falls straight out of the existing `_read_watermark(None)` → full-load path (etl.py:1007 / :1722). NOT a persistent clamp; no `max(initial, stored)` on every run.
- **D-02:** **New frozen `Pipeline` field** `initial_watermark: datetime | int | str | Sequence[...] | None = None`, next to `incremental_column`. Validated in `__post_init__` (etl.py:211): **requires `incremental_column` set** (else `ValueError`, same shape as the D-16 guard); scalar type checked against the `{datetime, int, str}` allowlist (reuse `_encode_watermark`'s guard rationale — `bool`/`float` rejected). NOT a `run()` param — declarative + inspectable, consistent with the existing `incremental_column`.
- **D-03:** **Empty first (seeded) batch → record nothing, re-seed next run.** No special-casing: no watermark is stored (C-03), so the next run again finds no stored watermark and re-applies `initial_watermark`. Preserves the "advance only on a real load" invariant.
- **D-04 (composite interaction, links F03):** For a **composite** `incremental_column`, `initial_watermark` must be a **matching-length sequence** of scalars (one per key column). Validated at construction: `len(initial_watermark) == len(incremental_column tuple)` else `ValueError`; each element type-checked against the allowlist.

### F02 — boundary knobs (`>=` and/or lookback)
- **D-05:** **Two orthogonal keyword-only frozen `Pipeline` fields:** `incremental_inclusive: bool = False` (`>=` vs `>`) and `incremental_lookback: timedelta | int | None = None`. Either, both, or neither. Default `(False, None)` = today's exact SQL, byte-identical. Each independently testable. NOT a single boundary-mode enum.
- **D-06:** **Lookback typed `timedelta | int`, subtracted in Python before binding.** The effective read floor is computed in Python — `datetime floor − timedelta`, `int floor − int` — then bound as the usual `%s`. NOT a SQL `%s::interval` (keeps the pure builder simple and covers the int case). A `str`-typed watermark + a set `incremental_lookback` → **`ETLError` at run time** (can't subtract from a str); the type is only known once the watermark is read, so this is a runtime guard, not a construction guard. Reuses the `{datetime,int,str}` type dispatch already in `run()` (etl.py:1315-1347).
- **D-07:** **The RECORDED high-water mark is always the true `max(col)`** — lookback only *widens the read window*, it never regresses the stored watermark. (floor=100, lookback=10 → read `WHERE col > 90`, but still record `max(col)`≈137.) Combined form: `WHERE col >= (floor − lookback)`.
- **D-08:** **Accept + document the boundary/overlap replay.** Inclusive `>=` (and lookback) re-read and re-process the boundary row / overlap window every run; this is an idempotent no-op ON CONFLICT (C-01). Document in the docstring ("inclusive/lookback re-scan overlaps every run; safe because incremental requires upsert"). **No dedup machinery.**

### F03 — composite (multi-column) watermark
- **D-09:** **Widen the existing field:** `incremental_column: str | Sequence[str] | None`. A `str` stays single-column (byte-identical, back-compat); a sequence declares a composite key. **Normalized internally to a `tuple[str, ...]`** in `__post_init__` — exactly how `conflict_columns` already coerces list→tuple (etl.py:241). One declarative knob; NO second field, NO mutual-exclusion guard. `validate_identifiers` runs over every element.
- **D-10:** **Row-value comparison + true max-row (per-column is a correctness trap).** SQL: `WHERE (c1, c2) > (%s, %s)` — Postgres lexicographic tuple comparison (`>=` when `incremental_inclusive`), each value a bound `%s`. Recorded watermark = the actual greatest **row**: sort the raw batch by the key columns and take that row's tuple (e.g. `df.sort_values(cols).iloc[-1][cols]`). **NOT** `WHERE c1>%s AND c2>%s` with per-column `(max(c1), max(c2))` — that fabricates a tuple no row has and silently skips rows whose `c1` advanced but `c2` didn't. Extend `_build_incremental_extract_sql` (etl.py:539) for the tuple form (SQL-string source → wrap subquery then `WHERE (c1,c2) > (%s,%s)`; table source → append the clause).
- **D-11:** **New `"composite"` envelope tag; the shipped single-scalar shape is untouched.** Single-column keeps `{"type":"int"|"datetime"|"str","value":...}` verbatim → **zero migration**, old rows read exactly as before. Composite uses a new tagged shape `{"type":"composite","columns":[...],"values":[{scalar-envelope}, ...]}`. `_decode_watermark` dispatches on the `type` tag — `"composite"` joins the existing three; `_encode` reuses the per-scalar encoder for each element (`bool`/`float` still rejected loud). Decoded composite = an ordered tuple of scalars fed to the `(c1,c2) > (%s,%s)` builder.

### F04 — advisory-lock concurrency
- **D-12:** **Opt-in Pipeline field** `concurrency: Literal["wait", "skip"] | None = None`. `None` (default) = no lock, byte-identical to today (opt-in, **NOT always-on** — no extra round-trip unless requested). `"wait"` = `pg_advisory_lock` (block until the other run finishes → serialize). `"skip"` = `pg_try_advisory_lock` (refuse to overlap). Declarative + inspectable, consistent with D-02/D-05/D-09. **Available to ALL pipelines**, not just incremental (concurrent `replace`/`append` race too), though incremental is the primary motivation.
- **D-13:** **`concurrency="skip"` + lock already held → transient `'skipped'` RunResult.** Return `RunResult(status="skipped", run_id=None, rows_extracted=0, rows_loaded=0)` and write **NO** `pipeline_runs` row — mirrors the `dry_run` precedent (etl.py:1211). Scheduler-friendly (inspect `result.status`, no `try/except` per tick). **Needs NO change to the `pipeline_runs.status` CHECK constraint** (`'running','success','failed'` — queries.py:335) because a skipped run is never persisted. `'skipped'` is a documented transient status value only (like `'dry_run'`). NOT a raised exception.
- **D-14:** **Session-scoped lock on a dedicated connection, released in `finally`.** Acquire a SESSION-scoped `pg_advisory_lock` / `pg_try_advisory_lock` on a dedicated connection opened first thing in `run()`, held for the **entire** read→extract→load→record span (which crosses the separate autocommit run-log writes AND the load transaction), released in a `finally` (`pg_advisory_unlock`, and closing the connection auto-releases even on crash → no orphaned locks). NOT `pg_advisory_xact_lock` — a transaction-scoped lock only guards the load txn, leaving the watermark-read/extract race (the exact race F04 targets) open.
- **D-15:** **DB-side key derivation:** `SELECT pg_try_advisory_lock(hashtextextended(%s, 0))` (or `pg_advisory_lock(...)` for `"wait"`), pipeline name bound as `%s`. Deterministic server-side, identical for every client/process — the correct property for cross-process mutual exclusion. **NOT** a Python-side `hash()` (salted by `PYTHONHASHSEED` → different key per process → lock does not serialize). Name is bound, never interpolated.

### Standing bar (from REQUIREMENTS.md cross-cutting acceptance criteria)
- Sync/async parity — every new field/param/method on BOTH `ETLAccessor` and `AsyncETLAccessor`, enforced by `test_accessor_parity` / `test_accessor_parameter_kind_parity`; async mirrors sync 1:1 (`await` every DB call, `asyncio.to_thread` transforms).
- Builder-pur + injection safety — `validate_identifiers` line 1 of every new/extended SQL builder, user values bound `%s`, dedicated injection test per new builder path (composite tuple compare, seed floor, lookback, advisory-lock key).
- Additive/non-breaking — all new params keyword-only, no `DeprecationWarning`, defaults reproduce current behavior exactly.
- Zero new runtime deps; `mypy --strict` 0 errors (blocking gate — widen `incremental_column` / `initial_watermark` union types and add `@overload` stubs where a return type branches); `interrogate` 100%; coverage ratchet ≥95% (baseline 96.37% at Phase 48); Sphinx `-W` clean.

### Claude's Discretion (resolve during research/planning against the live DB)
- Exact new SQL constant names/placement in `queries.py` (e.g. an advisory-lock statement pair) — follow existing `ETL_*` style.
- `hashtextextended` availability confirmation (it is core PostgreSQL since 9.x, no extension) and the precise `pg_try_advisory_lock` return-handling.
- Whether the composite max-row is computed via `sort_values`/`nlargest` or an equivalent — any approach that yields the true lexicographic max **row tuple** (not per-column maxes) satisfies D-10.
- Test layering: mock SQL-shape unit tests (both accessors) + live-DB integration; advisory-lock integration likely needs two connections/sessions to exercise the held-lock path.
- New `RunResult` field additions, if any — none decided as required; keep the 10-field shape unless a knob demands surfacing (e.g. lookback-applied floor). If added, mirror the `watermark_used`/`watermark_recorded` optional-default pattern (etl.py:318).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` — Phase 49 goal + 4 success criteria (the scope anchor); milestone standing bar
- `.planning/REQUIREMENTS.md` — ETL-INC-F01..F04 wording + the cross-cutting acceptance criteria (standing bar); Out-of-Scope table (ETL-INC-F05 CDC deferral)

### Code to extend (both accessors live in one file)
- `pycopg/etl.py` — the whole incremental machinery:
  - `Pipeline` dataclass (:116) + `__post_init__` (:211) + `_validate_incremental` (:81) — add `initial_watermark` (D-02), `incremental_inclusive`/`incremental_lookback` (D-05), `concurrency` (D-12); widen `incremental_column` (D-09); new validation (D-04/D-06 construction parts)
  - `RunResult` (:273) — `'skipped'` transient status (D-13); optional field additions if any
  - `_build_incremental_extract_sql` (:539) — extend for `>=`/lookback (D-05..D-07) and composite tuple compare (D-10)
  - `_encode_watermark` (:607) / `_decode_watermark` (:656) — add the `"composite"` tag (D-11), keep the three scalar tags frozen
  - `_read_watermark` sync (:1007) / async (:1722) — seed fallback (D-01), composite decode
  - `_do_extract` sync (:1047) — filtered extract seam
  - `run()` sync (:1132) / async (:1843) — max-row capture (:1315), lookback floor arithmetic, `'skipped'` fork, advisory-lock acquire/finally (D-13/D-14)
  - `_end_run` sync (:840) / async (:1565) — watermark persist (composite envelope)
- `pycopg/queries.py` — ETL SQL constants: `ETL_INIT_PIPELINE_RUNS` (:329, the `status` CHECK — do NOT need to touch per D-13), `ETL_GET_LAST_WATERMARK` (:383), `ETL_UPDATE_RUN_WATERMARK` (:393). Add any new advisory-lock statement here following `ETL_*` style.
- `pycopg/validators.py` — `validate_identifiers` (line-1 of every builder)
- `pycopg/exceptions.py` — `ETLError` (lookback-on-str D-06; float/bool guards), `ETLTransformError`, `ETLTargetNotFoundError` families

### Test patterns
- `tests/test_etl.py` (+ any `test_etl_*` incremental files) — mock SQL-shape unit-test structure, watermark envelope round-trip tests, `dry_run` precedent (model for the `'skipped'` transient result), injection-test conventions
- `tests/test_parity.py` — `test_accessor_parity` + `test_accessor_parameter_kind_parity` (register new params/methods)

### Prior-milestone decisions (locked, carry forward — do not re-derive)
- `.planning/milestones/v0.7.0-ROADMAP.md` / `v0.7.0-REQUIREMENTS.md` — incremental ETL D-14..D-17 (upsert-required, `>` exclusive, `max(col)`-before-transforms, empty-batch preservation, JSONB envelope). These are C-01..C-04 above.
- `.planning/phases/48-timescaledb-follow-ups/48-CONTEXT.md` — immediate-prior follow-up phase; same house pattern (guards before DB round-trip, keyword-only additive params, both-accessors-same-commit, sequential-on-main).
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_build_incremental_extract_sql` (etl.py:539): the single extract-SQL builder for both accessors and both the `dry_run` and real paths — the extension point for `>=`/lookback (D-05) and composite tuple compare (D-10). Already `validate_identifiers`-first, already dispatches SQL-string vs table source, already binds the watermark as `%s`.
- `_encode_watermark`/`_decode_watermark` (etl.py:607/:656): frozen tag-dispatched envelope codec — add the `"composite"` tag alongside the three scalars (D-11); the per-scalar branch is reused element-wise.
- `dry_run` early fork in `run()` (etl.py:1211): the precedent for a transient RunResult that writes no `pipeline_runs` row — the exact model for the `concurrency="skip"` `'skipped'` result (D-13).
- `conflict_columns` list→tuple normalization in `__post_init__` (etl.py:241): the precedent for widening `incremental_column` to `str | Sequence[str]` and normalizing to a tuple (D-09).
- The raw-batch max capture block (etl.py:1315-1347, mirrored in dry-run :1226-1250): the type-dispatch (`pd.Timestamp`/`str`/`is_float`-reject/`int`) that the composite max-row (D-10) and lookback (D-06) extend.

### Established Patterns
- Guards fire **before any DB round-trip** — construction-time `ValueError` (D-02/D-04/D-05) and the runtime `ETLError` for lookback-on-str (D-06). Matches Phase 48 D-07 and the v0.7.0 incremental guards.
- Run-log writes stay on **dedicated autocommit connections**, independent of the load transaction (v0.5.0 ETL-09 isolation seam) — the advisory-lock connection (D-14) is a *third* dedicated connection wrapping the whole run.
- Both sync and async accessors edited in the same file/commit; new params registered in `test_parity` (v1.0.0 Phase 41 KIND-parity lesson).
- `@overload` stubs kept in sync+async KIND-parity for mypy-strict (v1.0.0 Phase 46) — preserve when touching any `into=`/return-branching signature.

### Integration Points
- The four knobs **compose**: `initial_watermark` seeds the floor → `incremental_lookback` widens it → `incremental_inclusive` picks `>`/`>=` → composite makes floor/compare/record a tuple → `concurrency` wraps the whole run in an advisory lock. Ordering is fixed by that data flow (floor resolved first, lock outermost).
- Composite (D-09/D-10/D-11) touches the most surfaces (field, builder, codec, max-capture, read) — likely the largest single plan.
- Local test env (from project memory): run DB/parity/coverage tests with `PGDATABASE=pycopg_test3` (default `pycopg_test`/`pycopg_test2` broken by TSDB `.so` drift); the ETL/advisory-lock tests are plain PostgreSQL (no TSL gating). Advisory-lock integration needs two live sessions to exercise the held-lock path.
</code_context>

<specifics>
## Specific Ideas

- F02 lookback: `floor=100, lookback=10 → WHERE col > 90`, recorded wm still `max(col)`≈137 (widen read, never regress record).
- F03 composite SQL: `WHERE (day, seq) > (%s, %s)`; envelope `{"type":"composite","columns":["day","seq"],"values":[{"type":"int","value":5},{"type":"int","value":40}]}`; single stays `{"type":"int","value":137}`.
- F04 key: `pg_try_advisory_lock(hashtextextended('nightly', 0))` — same key in every process; skip → `RunResult(status='skipped', run_id=None)`.
- F01 seed: `run 1 (no stored wm): WHERE col > initial_watermark` → `run 2 (stored=X): WHERE col > X` (initial ignored thereafter).
</specifics>

<deferred>
## Deferred Ideas

- **ETL-INC-F05 (CDC / WAL change capture)** — logical replication slots + output-plugin decoding; a large distinct subsystem, deferred 2026-07-02 to keep v1.1.0 a coherent additive set. Don't re-litigate.
- **Cross-pipeline / global advisory locks** — F04 is per-pipeline (keyed on `pipeline.name`); a shared-resource lock across different pipelines is a future ergonomic if requested.
- **`concurrency` on a `run()` override** — decided as a Pipeline field (D-12); a per-call override could be a future additive convenience.
- **Surfacing the lookback-applied floor / seed on `RunResult`** — only if a concrete need appears; kept to Claude's Discretion above.
- Milestone-level deferrals already recorded (don't re-litigate): SPAT-F01 (gridSize), RASTER-F01 (raster).

*None raised during discussion that aren't already tracked above.*
</deferred>

---

*Phase: 49-incremental-etl-follow-ups*
*Context gathered: 2026-07-03*
