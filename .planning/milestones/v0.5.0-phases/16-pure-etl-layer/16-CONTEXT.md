# Phase 16: Pure ETL Layer - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning

<domain>
## Phase Boundary

The pure, DB-free foundation of the v0.5.0 ETL layer. This phase delivers the
**public `Pipeline` dataclass** (the declarative object users write), the **ETL
SQL constants** in `queries.py`, the **pure SQL builder functions**, and the
**ETL exception hierarchy** — all unit-testable with **no database connection**.

**In scope:**
- `Pipeline` frozen dataclass: inspectable, validated at construction (`__post_init__`).
- ETL SQL constants in `queries.py` (`%s` placeholders, no f-string identifier interpolation).
- Pure SQL builders that return parameterized SQL and call `validate_identifiers`.
- ETL exception classes in `exceptions.py`.

**Out of scope (later phases):**
- Run-tracking I/O / `pipeline_runs` writes (Phase 17).
- Extract, load modes, transform execution (Phase 18).
- `run()`, `history()`, `last_run()`, `dry_run` runner surface (Phase 19).
- `AsyncETLAccessor`, lazy `db.etl` wiring, `TestEtlParity`, docs, release (Phase 20).

Mirrors `spatial.py` exactly: pure module-level builders + dataclasses, shared
byte-identical between the (future) sync and async accessors.
</domain>

<decisions>
## Implementation Decisions

### Pipeline API shape
- **D-01:** **Flat `Pipeline` dataclass** matching ROADMAP success criterion #1 —
  `Pipeline(name=..., source=..., target=..., load_mode=..., conflict_columns=..., schema=..., transform=..., extract_limit=...)`.
  The nested `ExtractSpec`/`LoadSpec` design from `ARCHITECTURE.md` is **rejected** —
  it contradicts the locked roadmap signature. A single flat dataclass with one
  `__post_init__` is the public API. No internal spec dataclasses unless the planner
  finds them necessary for the builders (not required by this decision).
- **D-02:** `@dataclass(frozen=True)`. Per `ARCHITECTURE.md` Pattern 2: frozen for
  idempotency safety; `conflict_columns` is a `tuple[str, ...]` (frozen dataclasses
  cannot have mutable list defaults). Accept a `list` at the call site if ergonomic,
  but store/normalize as tuple.
- **D-03:** All listed attributes are **readable** (roadmap SC-1): `name`, `source`,
  `target`, `load_mode`, `conflict_columns`, `schema` — plus `transform` and
  `extract_limit` (see D-09).

### source disambiguation (SQL vs table)
- **D-04:** Flat single `source=` field. The SQL-query-vs-table-name distinction uses a
  **heuristic on the source string** (e.g. presence of whitespace / leading `SELECT`/`WITH`
  → treat as SQL; otherwise a table name). **No `source_type` field** is added.
- **D-05:** In Phase 16 the `Pipeline` simply **stores `source` as a string**. The
  heuristic logic itself is *exercised* at extract time (Phase 18), but the decision
  to use a heuristic (not an explicit field) is locked **now** because it determines
  that no extra dataclass field exists. Phase 16 may include a small pure helper
  (e.g. `_is_sql_source(source) -> bool`) if it keeps the builder/extract contract clean.

### load_mode values
- **D-06:** Public `load_mode` value set is **`append` / `replace` / `upsert`** (roadmap
  wording). `replace` is the user-facing name for the TRUNCATE+INSERT (truncate-load)
  behavior — do **not** expose `truncate` as the public value, despite the research
  example using it. The validator rejects any other value with `ValueError` at construction.
- **D-07:** `load_mode='upsert'` **without** `conflict_columns` raises **`ValueError`**
  at construction time, before any DB interaction (roadmap SC-2). This validation lives
  in `Pipeline.__post_init__`.

### Exceptions (OD-2)
- **D-08:** **Define the full ETL exception hierarchy now**, in `exceptions.py`, even
  though most are raised in later phases:
  - `ETLError(PycopgError)` — base for all ETL errors.
  - `ETLTransformError(ETLError)` — raised on transform failure (Phase 18 raises it).
  - `ETLTargetNotFoundError(ETLError)` — raised when an append target is missing (Phase 18).
  `exceptions.py` is the single home for ETL types; downstream phases import, not redefine.
- **D-09 (OD-2 strategy):** On load/run failure: **re-raise the original exception** for
  unknown errors (preserve stack trace; no wrapping in a generic `PipelineError`); raise
  the **domain exceptions** (`ETLTransformError`, `ETLTargetNotFoundError`) for the known
  cases. No `PipelineError` wrapper is introduced. (The actual raising happens in later
  phases — Phase 16 only *defines* the classes and locks the strategy.)

### Pure builder surface
- **D-10:** Phase 16 ships the **minimal pure builder set**: `build_init_sql()`
  (the `pipeline_runs` DDL) and `build_truncate_sql()` (for `replace` mode). Builders that
  need richer column/value knowledge (insert-run, update-run, upsert, list/get-last-run)
  are written in their owning phases (17/18/19). **However**, Phase 16 still defines **all
  five ETL SQL constants** in `queries.py` so later phases consume them, not re-author them:
  `ETL_INIT_PIPELINE_RUNS`, `ETL_INSERT_RUN`, `ETL_UPDATE_RUN`, `ETL_LIST_RUNS`,
  `ETL_GET_LAST_RUN` (roadmap SC-3).
- **D-11 (extract_limit):** **Include `extract_limit: int | None = None`** on the `Pipeline`
  dataclass now — it is zero-cost in the pure layer (a field + a docstring memory contract).
  Default `None` = no limit. Phase 18 wires it into the extract SQL (`LIMIT %s`). Full
  `extract_batch_size` streaming stays deferred to v0.6.0.

### Locked invariants carried into this phase (not re-litigated)
- **D-12:** SQL constants use `%s` placeholders; **no f-string identifier interpolation**
  in constants or builders (roadmap SC-3/SC-4; v0.3.1 security invariant).
- **D-13:** Every builder calls `validate_identifiers(...)` on table/schema/conflict-column
  identifiers **before** any string interpolation (security invariant, mirrors `spatial.py`).
- **D-14:** `pipeline_runs` schema reserves a nullable **`watermark JSONB`** column (OD-1),
  always NULL in v0.5.0; `status` is **`TEXT ... CHECK (status IN (...))`**, not a PG ENUM
  (avoids `ALTER TYPE` in v0.6.0); BIGSERIAL/identity PK. The DDL lives in
  `ETL_INIT_PIPELINE_RUNS` / `build_init_sql()`.
- **D-15:** `pipeline_runs` init strategy (OD-3) is **both** lazy auto-create
  (`CREATE TABLE IF NOT EXISTS`) and an explicit `init()` — the **idempotent DDL** authored
  in this phase must be safe to call repeatedly. (The `init()`/auto-create *call sites* are
  Phase 17; Phase 16 just makes the DDL idempotent.)

### Claude's Discretion
- Exact module layout within `etl.py` (helper naming, where `_is_sql_source` lives if used).
- Whether `Pipeline` accepts a `list` and normalizes to `tuple`, or requires a tuple.
- Exact column list/types in the `pipeline_runs` DDL beyond the locked constraints (D-14),
  to be reconciled with Phase 17's success criteria (`run_id`, `pipeline_name`, `started_at`,
  `finished_at`, `status`, `rows_extracted`, `rows_loaded`, error fields, `watermark`).
- Whether `extract_limit` validation (e.g. reject negatives) lives in `__post_init__`.

### Folded Todos
None — no pending todos matched this phase.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & scope (authoritative)
- `.planning/ROADMAP.md` §"Phase 16: Pure ETL Layer" — Goal + 4 success criteria (the flat
  `Pipeline` signature, construction-time `ValueError`, the 5 ETL SQL constants, pure builders).
- `.planning/REQUIREMENTS.md` — **ETL-01** (Phase 16's sole requirement) + the
  "Open Design Decisions" table (OD-1/OD-2/OD-3) and "Out of Scope" table (no DAG/scheduler
  fields, no SQL-only transforms, no new deps).
- `.planning/PROJECT.md` §"Current Milestone: v0.5.0" — milestone goal, locked constraints
  (zero new runtime deps, mirror `spatial.py`, watermark deferred additively).

### ETL research (HIGH confidence, read source directly)
- `.planning/research/SUMMARY.md` — synthesis; Phase A == this phase; OD-1/OD-2/OD-3
  recommendations; `extract_limit` gap note.
- `.planning/research/ARCHITECTURE.md` §"Pattern 2: Frozen Dataclass Pipeline Descriptor"
  (lines ~124–176) — dataclass shape reference. **NOTE:** its *nested* `ExtractSpec`/`LoadSpec`
  example is **superseded by D-01 (flat)**; use it only for the `frozen=True` / `tuple`
  conventions, not the nesting.
- `.planning/research/FEATURES.md` — ETL-01 acceptance phrasing; exception names
  (`ETLTransformError`, `ETLTargetNotFoundError`).
- `.planning/research/PITFALLS.md` — Pitfall 3 (identifier injection in load builders),
  Pitfall 6 (`pipeline_runs` schema must not use ENUM; TEXT+CHECK + JSONB watermark).
- `.planning/research/STACK.md` — zero-new-deps confirmation; `dataclasses`/`typing` only.

### Codebase precedent (the template to mirror)
- `pycopg/spatial.py` — **the** architectural template: pure module-level builders returning
  `(sql, params)`, security invariants in the module docstring, lazy accessor pattern.
- `pycopg/queries.py` — SQL constant section style; add a new `# ETL QUERIES` section here.
- `pycopg/exceptions.py` — `PycopgError` base + existing domain exceptions; add ETL hierarchy here.
- `pycopg/utils.py` §`validate_identifier`/`validate_identifiers` — the validation gate every
  builder must call.
- `pycopg/__init__.py` — export surface; Phase 20 wires ETL exports, but Phase 16 should ensure
  new exception classes are exportable (planner decides if exports land now or in Phase 20).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `spatial.py` pure-builder convention: stateless module-level `build_*_sql(...) -> (sql, params)`
  functions, `validate_identifiers(...)` first, `%s` placeholders, SRID/int the only direct
  interpolation. ETL builders copy this shape exactly.
- `validate_identifiers(*names)` in `utils.py` — the injection gate; already used throughout
  `spatial.py`. ETL builders reuse it verbatim.
- `queries.py` sectioning (`# ===== X QUERIES =====` banners, triple-quoted constants with `%s`).
  Append an `# ETL QUERIES` section in the same style.
- `exceptions.py` `PycopgError` base — `ETLError` subclasses it; mirrors `ExtensionNotAvailable`,
  `TableNotFound`, etc.

### Established Patterns
- Frozen dataclasses for immutable descriptors (research recommendation; no existing dataclass
  in the lib, but `Config` is a dataclass-style factory in `config.py` — style reference).
- Lazy accessor properties (`db.spatial`, lines ~229–249 of `database.py`) — Phase 16 does **not**
  wire these (that's Phase 20), but the `Pipeline`/builder API must be consumable by that pattern.

### Integration Points
- New `etl.py` module (created this phase) holding `Pipeline` + pure builders.
- `queries.py` gains the 5 ETL constants.
- `exceptions.py` gains `ETLError` + 2 subclasses; `__init__.py` may gain exports.
- No wiring into `database.py`/`async_database.py` this phase (deferred to Phase 20).

</code_context>

<specifics>
## Specific Ideas

- User explicitly chose to **honor the roadmap's locked flat signature over the research's
  nested design** when the two conflicted — flat API is the deliberate choice, not an oversight.
- User wants the **full ETL exception set defined up front** in Phase 16 (single home), even
  though the exceptions fire in later phases — avoids scattering type definitions.
- User opted to **pull `extract_limit` forward** as a cheap pure field rather than defer it,
  accepting the small now-cost for the OOM-guard ergonomics later.

</specifics>

<deferred>
## Deferred Ideas

- **Nested `ExtractSpec` / `LoadSpec` dataclasses** (from `ARCHITECTURE.md`) — rejected in favor
  of the flat `Pipeline`. Not a future phase; recorded so the planner doesn't resurrect it.
- **`extract_batch_size` / streaming extract** — v0.6.0 (only `extract_limit` lands now).
- **`pg_try_advisory_lock` concurrent-run guard** (PITFALLS.md) — a Phase 17 (run-tracking)
  concern, not the pure layer.
- **GeoDataFrame-aware load**, **multi-tenant `schema='etl'` accessor**, **cross-DB / file
  source-sink**, **SQL-only transforms**, **scheduling/DAG** — all explicitly out of v0.5.0 scope
  (REQUIREMENTS.md "Out of Scope" / "Future Requirements").

</deferred>

---

*Phase: 16-Pure ETL Layer*
*Context gathered: 2026-06-14*
