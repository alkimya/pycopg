# Phase 26: Incremental ETL — Pure Layer - Context

**Gathered:** 2026-06-20
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the **pure, DB-free foundation** of incremental ETL — everything unit-testable without a database connection. Three deliverables, scoped to **ETL-INC-01 only**:

1. **`Pipeline.incremental_column` field + construction validation** — new optional field on the frozen `Pipeline` dataclass; `__post_init__` validates the identifier and rejects forbidden `load_mode` combinations.
2. **Pure watermark-filter SQL builder** — produces the `WHERE col > %s` filtered extract SQL for both SQL-string sources (subquery wrap) and table sources (WHERE append).
3. **`_encode_watermark` / `_decode_watermark`** — the typed JSONB-envelope serializer/deserializer, verified for `datetime` (tz-aware), `int`, and `str` by DB-free unit tests.

**Explicitly OUT of this phase (deferred to 27/28 per the traceability table):** reading the last watermark from `pipeline_runs` (DB), the `_end_run(watermark=)` success-only persist path, the no-advance-on-failure invariant, computing `max(col)` from a live batch (ETL-INC-04 → Phase 28), wiring the filter into `run()`, `RunResult.watermark_used/recorded`, `dry_run`, `AsyncETLAccessor` mirror, `TestEtlParity`, and incremental docs. **Do not pull any of these forward.** This phase only touches code paths that need no DB.

</domain>

<decisions>
## Implementation Decisions

### Watermark JSONB envelope (`_encode_watermark` / `_decode_watermark`)
- **D-01: Typed envelope.** Store `{"type": "datetime"|"int"|"str", "value": <scalar>}`. Self-describing — `_decode` reconstructs the exact Python type from the `type` tag. A datetime stored as an ISO string is never confused with a genuine text watermark (the disambiguation that a raw JSON scalar can't provide).
- **D-02: datetime serialization = `isoformat()` / `fromisoformat()`.** Lossless (microseconds + offset preserved), stdlib-only. **No UTC normalization** — the stored offset matches what `SELECT max(col)` returns. Aware-vs-naive is NOT mutated or rejected in this pure layer.
- **D-03: Aware-only is a documented contract, enforced later.** "Use aware, monotonic, non-decreasing watermark columns" goes in docstrings (the doc requirement ETL-INC-12 lands in Phase 28). Any naive-datetime rejection policy belongs to the live-extract phase (27/28), not to `_encode_watermark`. Rationale: the user prefers not to mix naive/aware datetime formats; preserving the offset (rather than coercing to UTC) honors that without baking a value-policy into a pure serializer.
- **D-04: Strict type allowlist with fail-fast.** Supported set is exactly `{datetime, int, str}`. **`bool` is excluded** (it is a subclass of `int` — same trap already guarded for `extract_limit` at `etl.py:188`). Any unsupported type (`bool`, `float`, `Decimal`, etc.) raises a **clear `ETLError`** naming the unsupported type and listing the supported set. `float` is deliberately NOT supported in v0.7.0 (not in ETL-INC-10; float JSON precision is a separate concern).
- **D-05: `_encode_watermark` returns a bare `dict`** — fully DB-free and trivially unit-testable. The `psycopg.types.json.Jsonb(...)` adapter wrap happens at the run-log **write-site in Phase 27**, not here. `_decode_watermark` accepts the plain `dict` that psycopg returns when reading a JSONB column. (A bare dict does NOT auto-adapt as a `%s` param — but that binding is a Phase-27 concern.)

### Watermark-filter SQL builder
- **D-06: SQL-string source → subquery wrap.** `SELECT * FROM (<user sql>) _pycopg_inc WHERE col > %s`. PostgreSQL requires the subquery alias.
- **D-07: Fixed reserved alias `_pycopg_inc`.** Deterministic, greppable in logs, collision-safe by underscore-prefix convention. The watermark column is referenced unqualified (`col > %s`).
- **D-08: SQL hygiene = right-strip trailing whitespace + a single trailing `;` before wrapping.** Handles the common case safely with **no SQL parser**. Trailing line-comments (`-- ...`) are documented as the caller's responsibility; emitting the wrap with a newline before `WHERE` is a free hardening the planner may apply, but the *contract* does not promise to neutralize comments.
- **D-09: Table source → `SELECT * FROM schema.table WHERE col > %s`.** Identifiers (`schema`, `table`, `col`) validated via `validate_identifiers`; watermark value as `%s`. No pointless subquery nesting (the spec separates the two source kinds).
- **D-10: Watermark column emitted BARE (validated), not double-quoted.** Matches every existing builder in `etl.py` (e.g. `build_truncate_sql` interpolates bare validated identifiers). Mixed-case/reserved-word column quoting is deliberately NOT introduced here — would be an inconsistent special case. The value is always a `%s` param, never interpolated.
- **D-11: One dispatching builder `_build_incremental_extract_sql(source, column, schema, watermark)`** using the existing `_is_sql_source` internally to pick wrap-vs-append. Single entry point; callers don't pre-classify.
- **D-12: `watermark=None` → full unfiltered SELECT (`[]` params).** Same code path covers first run and subsequent runs — first-run "no filter" is handled by the builder, not by a branch in the (Phase 27/28) caller.
- **D-13: Private `_`-prefixed tier; `(sql, params)` 2-tuple return.** `_build_incremental_extract_sql`, `_encode_watermark`, `_decode_watermark` are all internal helpers (like `_build_insert_sql`/`_build_upsert_sql`), NOT part of the user-facing API. Uniform `(sql, list)` contract; the watermark value is the only param.

### Construction validation (`Pipeline.__post_init__`)
- **D-14: Module-level `_validate_incremental(incremental_column, load_mode)` helper**, mirroring the existing `_validate_load_mode` pattern — pure and independently unit-testable.
- **D-15: The helper owns BOTH checks**, in order: (1) forbidden-combo `ValueError` (intent error), then (2) `validate_identifiers(column)` (syntax error). `incremental_column is None` short-circuits early (non-incremental pipelines skip both).
- **D-16: Forbidden combo = `load_mode` ∈ {`append`, `replace`}** → `ValueError`. Incremental requires `upsert`. Message explains the fix and the why and cites the requirement, e.g.: `"incremental_column requires load_mode='upsert' (got {load_mode!r}); 'append' and 'replace' are forbidden with incremental loads because upsert guarantees idempotency (ETL-INC-01)"`.
- **D-17: Call order in `__post_init__`** — insert `_validate_incremental(...)` **after** `_validate_load_mode(self.load_mode)` (so a garbage `load_mode` reports "must be one of ..." first), and **before** the upsert-requires-conflict_columns and `extract_limit` checks. Final sequence: bare-string check → normalize conflict_columns → `_validate_load_mode` → **`_validate_incremental`** → upsert-requires-conflict_columns → extract_limit.

### Claude's Discretion
- Exact docstring wording for the new `incremental_column` Parameter entry and the watermark-column requirements note (aware/monotonic/non-decreasing) — follow the existing numpydoc shallow style in `etl.py`; full incremental usage docs are Phase 28 (ETL-INC-12).
- Whether `_build_incremental_extract_sql` emits the wrap on one line or multi-line (D-08 hardening) — formatting detail.
- Unit-test file placement (extend `tests/test_etl.py` vs a new module) — follow the existing DB-free builder-test pattern already in `test_etl.py`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope (LOCKED — read first)
- `.planning/REQUIREMENTS.md` — v0.7.0 requirements; **ETL-INC-01** is the only requirement in scope this phase. The "Locked scope decisions (cadrage 2026-06-19)" block and the **Out of Scope** table (append/replace forbidden, `>` exclusive, single-column, no `initial_watermark`) are binding.
- `.planning/ROADMAP.md` §"Phase 26: Incremental ETL — Pure Layer" — Goal + 4 Success Criteria; and the Phase 27/28 entries that define what is explicitly NOT this phase.
- `.planning/PROJECT.md` §"Current Milestone: v0.7.0" — milestone goal and locked scope summary.

### Code to read & extend
- `pycopg/etl.py` — the target module. Key landmarks:
  - `_validate_load_mode` (line 52) + `_VALID_LOAD_MODES` (line 49) — the helper pattern `_validate_incremental` mirrors (D-14).
  - `Pipeline` dataclass + `__post_init__` (lines 72–201) — where `incremental_column` and its guard slot in (D-17). Note the existing `bool`-is-int guard at line 188 (D-04 precedent).
  - `_is_sql_source` (line 241) — reused by the dispatching builder (D-11).
  - `build_truncate_sql` (line 268), `_build_insert_sql` (line 330), `_build_upsert_sql` (line 395) — the `(sql, params)` 2-tuple + bare-validated-identifier convention the new builder follows (D-09, D-10, D-13).
- `pycopg/queries.py` §`ETL_INIT_PIPELINE_RUNS` (line 249) — the `watermark JSONB` column (line 260) the envelope round-trips through; reserved & always-NULL until now.
- `pycopg/utils.py` §`validate_identifiers` (line 107) — identifier validator used by D-09/D-10/D-15.
- `pycopg/exceptions.py` §`ETLError` (line 54) and subclasses (`ETLTransformError`, `ETLTargetNotFoundError`) — base for the unsupported-type raise in D-04. (Planner decides whether a new `ETLError` subclass is warranted or the base class suffices.)

### Tests
- `tests/test_etl.py` — existing DB-free builder/validation tests; extend here for `incremental_column` validation, the SQL builder, and encode/decode round-trips.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`_validate_load_mode` / `_VALID_LOAD_MODES`** (`etl.py:49,52`): direct template for `_validate_incremental` — same module-level, pure, raises `ValueError`, called from `__post_init__`.
- **`_is_sql_source`** (`etl.py:241`): existing source classifier — the new builder dispatches on it (no new classification logic).
- **`validate_identifiers`** (`utils.py:107`): the identifier gate already used throughout `etl.py` builders; reused for both the `incremental_column` field check and the in-SQL column/table emit.
- **`build_truncate_sql` / `_build_insert_sql` / `_build_upsert_sql`**: the `(sql, list)` 2-tuple return + bare-validated-identifier + `%s`-only-values conventions to copy.
- **`bool`-as-`int` guard** (`etl.py:188`, in the `extract_limit` validation): the exact pattern for D-04's `bool` exclusion in `_encode_watermark`.

### Established Patterns
- **Frozen dataclass + `__post_init__` validation** with `object.__setattr__` for normalization (e.g. `conflict_columns`). The new field is a plain optional `str | None`; no normalization needed, only validation.
- **Decision-tag in error messages** (e.g. `(D-07)` for the upsert/conflict_columns rule) — D-16 follows this by citing `ETL-INC-01`.
- **Pure builder = no `self`, no I/O, no DB connection**, returns `(sql, params)` — explicitly stated in `_build_insert_sql`'s docstring. All three Phase-26 helpers honor this.
- **numpydoc shallow docstrings** (no `Examples` beyond the dataclass), `interrogate ≥ 95` gate.

### Integration Points
- The `watermark JSONB` column in `pipeline_runs` (`queries.py:260`) is the round-trip target for the envelope — but the actual write/read is Phase 27. Phase 26 only produces/consumes the bare dict.
- The new builder will be called from `run()`'s extract path in Phase 28; Phase 26 leaves it unwired and unit-tested in isolation.

</code_context>

<specifics>
## Specific Ideas

- User preference (drove D-02/D-03): dislikes mixing naive and aware datetime formats; tends to use only **aware** datetimes. Resolution: preserve the offset exactly via `isoformat()` (no UTC coercion) and document the aware-only expectation rather than enforcing it in the pure layer.
- Envelope shape chosen with a concrete eye to ETL-INC-10 (the Phase-27 JSONB round-trip requirement): the typed tag is what makes datetime/int/str round-trip unambiguously with zero new deps.

</specifics>

<deferred>
## Deferred Ideas

- **`max(incremental_column)` extraction helper** — belongs to Phase 28 (ETL-INC-04), including the "watermark column absent from extract → clear `ETL*` error (not bare `KeyError`)" path. User explicitly chose to keep it out of Phase 26 to hold the roadmap's phase boundary.
- **`float` watermark support** — out of scope for v0.7.0 (not in ETL-INC-10); additive/non-breaking to add later if a real serial/epoch use case appears.
- **Mixed-case / reserved-word column quoting** in builders — would be a module-wide convention change; revisit globally if ever needed, not as a one-off here.
- **`initial_watermark` first-run bound** — deferred to v0.8.0 (ETL-INC-F01) per REQUIREMENTS.md Future Requirements.
- **Naive-datetime rejection policy** — if wanted, lands in the live-extract phase (27/28), not in `_encode_watermark`.

</deferred>

---

*Phase: 26-incremental-etl-pure-layer*
*Context gathered: 2026-06-20*
