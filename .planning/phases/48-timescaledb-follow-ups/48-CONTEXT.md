# Phase 48: TimescaleDB Follow-ups - Context

**Gathered:** 2026-07-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Complete the `db.timescale.*` surface opened in v0.8.0 with four additive, keyword-only,
sync/async-parity follow-ups (TSDB-F01..F04) — all non-breaking under the frozen SemVer 1.0
API, zero new runtime dependencies:

1. **F01** — continuous-aggregate teardown: `drop_continuous_aggregate` + `remove_continuous_aggregate_policy` (completes the cagg lifecycle whose create/refresh/add-policy shipped in v0.8.0).
2. **F02** — custom bucket alignment: keyword-only `origin=`/`offset=` on `time_bucket`.
3. **F03** — per-chunk compression: `compress_chunk` / `decompress_chunk`.
4. **F04** — physical-time chunk filter on `show_chunks` — **already delivered in v0.8.0** (see D-01); this phase verifies + documents it rather than building it.

**NOT in scope** (roadmap-fixed, don't add): new cagg query surface, compression *policy* changes
(already shipped), retention changes, any breaking change to an existing signature, CDC/raster/gridSize
(deferred to a later 1.x per the milestone scope call).
</domain>

<decisions>
## Implementation Decisions

### F04 — show_chunks physical-time filter (already shipped)
- **D-01:** TSDB-F04 is **already implemented and tested** in the shipped v0.8.0 code and requires **no new API**. `db.timescale.show_chunks(table, *, older_than=, newer_than=, schema=)` already accepts both interval-`str` (e.g. `"30 days"`, rendered `%s::interval`) and absolute `datetime` (physical time, rendered bare `%s`), sync + async, via the shared `_build_chunk_bound_fragments` helper (timescale.py:33). Existing tests cover it: `test_show_chunks_sql_shape_str_older_than`, `test_show_chunks_sql_shape_datetime_older_than`, `test_show_chunks_params_order_older_then_newer`, and the async mirrors (`tests/test_timescale.py:142–248`).
- **D-02:** Phase work for F04 = **verify + document only**. Confirm the requirement in phase verification, ensure `docs/` surfaces the `older_than=`/`newer_than=` filter with a physical-time (datetime) example, and — for symmetry with the existing `older_than`-datetime test — optionally add a single `newer_than`-datetime SQL-shape test (the only micro-gap; the fragment builder is already symmetric). Mark TSDB-F04 done in traceability.

### F01 — continuous-aggregate teardown
- **D-03:** Surface = `drop_continuous_aggregate(view_name, *, cascade=False, if_exists=False)` and `remove_continuous_aggregate_policy(view_name, *, if_exists=True)`. `cascade` maps to `DROP MATERIALIZED VIEW ... CASCADE`; `if_exists` gives idempotent teardown. The policy remover defaults `if_exists=True` (symmetric with `add_continuous_aggregate_policy`'s `if_not_exists=True`); the drop defaults `if_exists=False` (destructive op should be explicit). All params keyword-only.
- **D-04:** Naming pairs with the shipped v0.8.0 lifecycle (`create_continuous_aggregate` / `refresh_continuous_aggregate` / `add_continuous_aggregate_policy`). `remove_continuous_aggregate_policy` mirrors TimescaleDB's own `remove_continuous_aggregate_policy(cagg, if_exists => bool)`.
- **D-05 (research question, NOT locked):** Whether `DROP MATERIALIZED VIEW` on a cagg must run on the `connect(autocommit=True)` seam (like `create`/`refresh`, D-02 in v0.8.0) or can run inside the normal transaction. Research to confirm against TSDB 2.28; default assumption is it can run in a normal transaction, but verify. License errors (`FeatureNotSupported`/`0A000` on Apache) propagate — no swallow (v0.8.0 D-09).

### F02 — time_bucket custom origin/offset
- **D-06:** Add keyword-only `origin: datetime | None = None` (absolute alignment anchor) and `offset: str | None = None` (interval literal shift) to `time_bucket` on both accessors. Types follow the codebase's str-interval-vs-datetime-absolute convention. `origin` binds as a typed `%s`; `offset` binds as `%s::interval`.
- **D-07:** `origin` and `offset` are **mutually exclusive** in TimescaleDB → guard **client-side**: raise `ValueError` before any DB round-trip when both are non-`None`. Matches existing guards (`add_dimension` D-07 mutual-exclusion, `drop_chunks` both-None). Both `None` (default) = current behavior, unchanged.
- **D-08:** Extend the existing `_build_time_bucket_sql` builder (timescale.py:214) — `validate_identifiers` stays line 1, new values bound as params, injection test for the new origin/offset path. Keep the `@overload` `into=` stubs in KIND-parity across sync + async (v1.0.0 mypy-strict pattern). `time_bucket_gapfill` is **out of scope** for origin/offset unless trivially free (requirement names `time_bucket` only).

### F03 — per-chunk compress / decompress
- **D-09:** Surface = `compress_chunk(chunk, *, if_not_compressed=True)` and `decompress_chunk(chunk, *, if_compressed=True)`. Idempotency flags **exposed, default `True`** — re-(de)compressing is a no-op/warning, not an error (ergonomic for scripted/repeated runs). Both return **`None`** (void), consistent with the compression family (`enable_compression`, `add_compression_policy`, `add_reorder_policy` all return `None`).
- **D-10:** `chunk` is the fully-qualified chunk name as returned by `show_chunks` (e.g. `_timescaledb_internal._hyper_1_2_chunk`), bound safely as `%s::regclass` — NOT string-interpolated. SQL shape: `SELECT compress_chunk(%s::regclass, if_not_compressed => %s)` / `SELECT decompress_chunk(%s::regclass, if_compressed => %s)`. Because the chunk name is a bound value, injection safety is met by binding; still front the builder with `validate_identifiers` per the standing bar and add a dedicated injection test.
- **D-11 (research question):** Confirm the exact `if_not_compressed`/`if_compressed` argument names + availability on TSDB 2.28 (Apache build — `compress_chunk` is TSL/Community-gated; expect `FeatureNotSupported` on the local Apache install, tolerate like caggs). Confirm `ExtensionNotAvailableError` guard fires first (consistent with the accessor's other methods).

### Standing bar (applies to every new method/param — from REQUIREMENTS.md cross-cutting criteria)
- Sync/async parity: every new method/param on BOTH `TimescaleAccessor` and `AsyncTimescaleAccessor`, enforced by `test_accessor_parity` + `test_accessor_parameter_kind_parity` (edit both classes in the same file — v1.0.0 Phase 41 lesson).
- Builder-pur + injection safety: `validate_identifiers` line 1 of every new builder, user values bound `%s`/`%(name)s`, dedicated injection test per builder.
- Additive/non-breaking: keyword-only new params, no `DeprecationWarning`, no behavior change to existing signatures.
- Zero new runtime deps; `mypy --strict` 0 errors (blocking gate — add `@overload` stubs where `into=`/return types branch); `interrogate` 100%; coverage ratchet ≥95% (baseline 96.45%); Sphinx `-W` clean.

### Claude's Discretion
- D-05 (autocommit seam for drop) and D-11 (exact compression arg names/availability) resolved by researcher/planner against live TSDB 2.28.
- Test layering (mock SQL-shape unit tests + optional live-DB integration guarded by TSL availability) follows the established `tests/test_timescale.py` structure.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` — Phase 48 goal + 4 success criteria (the scope anchor)
- `.planning/REQUIREMENTS.md` — TSDB-F01..F04 wording + the cross-cutting acceptance criteria (standing bar)

### Code to extend (both classes live in one file)
- `pycopg/timescale.py` — `TimescaleAccessor` (sync, from :329) and `AsyncTimescaleAccessor` (async, from :1475). Key reuse points: `_build_chunk_bound_fragments` (:33, F04 reference), `_build_time_bucket_sql` (:214, extend for F02), `create_continuous_aggregate`/`refresh_continuous_aggregate` autocommit seam (:927/:1008, F01 pattern), `add_continuous_aggregate_policy` (:1094, F01 naming/pairing), `enable_compression`/`add_compression_policy` (:400/:455, F03 family/return convention), `time_bucket` `@overload` block (:1207–1325, F02 KIND-parity)
- `pycopg/queries.py` — SQL constants (`TSDB_SHOW_CHUNKS`, `TSDB_DROP_CHUNKS`, time_bucket templates); add any new cagg-drop / compress constants here following existing style
- `pycopg/exceptions.py` — `ExtensionNotAvailableError` (guard) + `TimescaleError`

### Test patterns
- `tests/test_timescale.py` — mock SQL-shape unit-test structure (sync + async), F04 existing coverage (:111–265), builder TypeError tests, injection-test conventions
- `tests/test_parity.py` — `test_accessor_parity` method list (add the 4 new methods) + `test_accessor_parameter_kind_parity`

### Prior-milestone decisions (locked, carry forward)
- `milestones/v0.8.0-ROADMAP.md` / `milestones/v0.8.0-REQUIREMENTS.md` — v0.8.0 `db.timescale.*` decisions D-01..D-09 (autocommit seam, str-vs-datetime bounds, guards-before-DB, license-error propagation)
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_build_chunk_bound_fragments` (timescale.py:33): already delivers F04's physical-time filtering; the model for str-interval-vs-datetime dispatch + param ordering.
- `_build_time_bucket_sql` (timescale.py:214): the F02 extension point — add origin/offset params here, keep `validate_identifiers` first.
- `connect(autocommit=True)` seam (used by create/refresh cagg): the candidate F01 drop path if research confirms a txn-block restriction.
- Compression family (`enable_compression`, `add_compression_policy`): sets the F03 `None`-return + `ExtensionNotAvailableError`-guard convention.

### Established Patterns
- Guards fire before any DB round-trip (drop_chunks both-None, add_dimension mutual-exclusion) → F02 origin/offset guard (D-07) and F01 explicit-drop default follow this.
- `@overload` `into=` stubs mirrored sync+async for mypy-strict (v1.0.0 Phase 46) → preserve when touching `time_bucket` overloads.
- Both sync and async accessors edited in the same file, same commit, to keep parity tests green (v1.0.0 Phase 41 lesson).

### Integration Points
- New methods register in `tests/test_parity.py` method list.
- Chunk names for F03 come from `show_chunks` output — the two features compose (show_chunks → compress_chunk).
- Local test env: TSDB 2.28 **Apache** build → cagg + per-chunk-compression are TSL/Community-gated; expect `FeatureNotSupported`/`0A000` and tolerate like existing cagg tests. Run DB tests with the working test DB (currently `pycopg_test3`; earlier ones broken — see project memory).
</code_context>

<specifics>
## Specific Ideas

- F02: `origin` binds as typed `%s` (datetime), `offset` binds as `%s::interval` (str) — mirrors the `_build_chunk_bound_fragments` interval-cast idiom.
- F03: exact SQL is `SELECT compress_chunk(%s::regclass, if_not_compressed => %s)` — chunk as a bound value, never interpolated.
- F01: `remove_continuous_aggregate_policy` maps to `SELECT remove_continuous_aggregate_policy('schema.view', if_exists => %s)`; `drop_continuous_aggregate` maps to `DROP MATERIALIZED VIEW [IF EXISTS] schema.view [CASCADE]`.
</specifics>

<deferred>
## Deferred Ideas

- **`time_bucket_gapfill` origin/offset** — requirement names `time_bucket` only; add to gapfill only if trivially free during F02, else leave to a future follow-up.
- **F03 batch/multi-chunk compress** (compress all chunks matching a bound, like `drop_chunks`) — not in the requirement (which is explicitly *per-chunk*); a natural future ergonomic if requested.
- Milestone-level deferrals already recorded (don't re-litigate): ETL-INC-F05 (CDC/WAL), SPAT-F01 (gridSize), RASTER-F01 (raster).

*None raised during discussion that aren't already tracked above.*
</deferred>

---

*Phase: 48-timescaledb-follow-ups*
*Context gathered: 2026-07-02*
