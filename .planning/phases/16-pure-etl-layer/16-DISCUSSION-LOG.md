# Phase 16: Pure ETL Layer - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-14
**Phase:** 16-Pure ETL Layer
**Areas discussed:** Pipeline API shape, Source disambiguation, ETL exceptions, extract_limit, load_mode values, Builder scope

---

## Pipeline API shape

| Option | Description | Selected |
|--------|-------------|----------|
| Flat (match roadmap SC) | Single flat dataclass exactly as roadmap SC #1; validation in one `__post_init__`; ExtractSpec/LoadSpec dropped | ✓ |
| Nested specs (research) | `Pipeline(extract=ExtractSpec, load=LoadSpec)`; contradicts locked roadmap SC | |
| Flat + internal specs | Flat public constructor, `__post_init__` derives internal specs | |

**User's choice:** Flat (match roadmap SC)
**Notes:** The ROADMAP success criterion #1 locks the flat signature; the ARCHITECTURE.md nested
design conflicted. User chose to honor the locked roadmap signature. Nested specs explicitly
rejected (recorded as a deferred/rejected idea so the planner doesn't resurrect it).

---

## Source disambiguation (SQL vs table)

| Option | Description | Selected |
|--------|-------------|----------|
| Heuristic on source string | Detect SQL by whitespace / leading SELECT/WITH; else table name; zero extra fields | ✓ |
| Explicit source_type field | Add `source_type: Literal['sql','table']`; unambiguous but extra field | |
| Defer to Phase 18 | Phase 16 stores opaque string; disambiguation entirely a Phase 18 concern | |

**User's choice:** Heuristic on source string
**Notes:** No `source_type` field added — keeps the dataclass to the roadmap's listed attributes.
Phase 16 stores `source` as a string; the heuristic fires at extract time (Phase 18). A small pure
helper (`_is_sql_source`) is allowed if it keeps the contract clean.

---

## ETL exceptions (placement + OD-2 strategy)

| Option | Description | Selected |
|--------|-------------|----------|
| Define all ETL exceptions now | Add ETLError base + ETLTransformError + ETLTargetNotFoundError now; OD-2 re-raise original otherwise | ✓ |
| Define only when first raised | Phase 16 adds only ValueError; others in Phase 18 | |
| Base now, leaves later | ETLError base now; subclasses in raising phases | |

**User's choice:** Define all ETL exceptions now
**Notes:** `exceptions.py` is the single home for ETL types. OD-2 locked: re-raise the original
exception for unknown errors (no `PipelineError` wrapper), domain exceptions for known cases. The
classes are *defined* in Phase 16; the *raising* happens in later phases.

---

## extract_limit

| Option | Description | Selected |
|--------|-------------|----------|
| Include extract_limit now | Add `extract_limit: int | None = None`; pure/free in Phase 16; Phase 18 wires LIMIT | ✓ |
| Defer entirely | Keep to roadmap-listed attributes only; add later if demand appears | |

**User's choice:** Include extract_limit now
**Notes:** Zero-cost in the pure layer (field + docstring memory contract). Default None = no limit.
Full `extract_batch_size` streaming stays deferred to v0.6.0.

---

## load_mode values

| Option | Description | Selected |
|--------|-------------|----------|
| append / replace / upsert | Roadmap user-facing words; 'replace' is the public name for truncate-load | ✓ |
| append / truncate / upsert | Research's 'truncate' wording; diverges from locked roadmap SC | |

**User's choice:** append / replace / upsert
**Notes:** `replace` is the public value (TRUNCATE+INSERT internally); `truncate` is NOT exposed
publicly despite the research example. Validator rejects other values with `ValueError`.

---

## Builder scope

| Option | Description | Selected |
|--------|-------------|----------|
| DDL + truncate only (minimal pure set) | `build_init_sql()` + `build_truncate_sql()`; all 5 ETL_* constants defined; other builders in owning phases | ✓ |
| All builders Phase 16 can write DB-free | Also pull forward build_insert_run_sql / build_list_runs_sql / build_get_last_run_sql | |

**User's choice:** DDL + truncate only (minimal pure set)
**Notes:** Phase 16 ships `build_init_sql()` + `build_truncate_sql()`, and defines **all five** ETL
SQL constants (`ETL_INIT_PIPELINE_RUNS`, `ETL_INSERT_RUN`, `ETL_UPDATE_RUN`, `ETL_LIST_RUNS`,
`ETL_GET_LAST_RUN`) so later phases consume rather than re-author them. Richer builders land in
Phases 17/18/19.

## Claude's Discretion

- Exact module layout within `etl.py` (helper naming, location of `_is_sql_source` if used).
- Whether `Pipeline` accepts a `list` and normalizes to `tuple`, or requires a tuple.
- Exact `pipeline_runs` column list/types beyond the locked constraints (reconciled with Phase 17 SC).
- Whether `extract_limit` validation (reject negatives) lives in `__post_init__`.

## Deferred Ideas

- Nested `ExtractSpec` / `LoadSpec` dataclasses — rejected in favor of flat `Pipeline`.
- `extract_batch_size` / streaming extract — v0.6.0.
- `pg_try_advisory_lock` concurrent-run guard — Phase 17 concern.
- GeoDataFrame-aware load, `schema='etl'` multi-tenant accessor, cross-DB / file source-sink,
  SQL-only transforms, scheduling/DAG — out of v0.5.0 scope.
