# Phase 27: Incremental ETL — Run-Log Integration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-20
**Phase:** 27-incremental-etl-run-log-integration
**Areas discussed:** Scope boundary (SC-1 vs ETL-INC-03/04 sequencing), Watermark read query, JSONB binding, Missing column handling, max() type coercion

---

## Scope boundary — proving SC-1 without owning the extract wiring

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal max() in run() now | Pull minimal max(col)-from-raw-batch + `_end_run(watermark=)` persist into sync run() this phase; Phase 28 layers WHERE-filter + RunResult + async on top | ✓ |
| Helpers only, defer e2e proof | Build `_read_watermark` + `_end_run(watermark=)` + round-trip tests only, exercised directly; slide first-run-records-max e2e proof to Phase 28 | |
| Let researcher/planner decide | Capture tension in CONTEXT; planner picks the cut, constrained to "all 4 SCs proven by Phase 28 close" | |

**User's choice:** Minimal max() in run() now
**Notes:** SC-1 ("first run persists watermark = max of incremental column") is only provable end-to-end if run() actually computes and records a watermark. Phase 27 still does a full (unfiltered) load every run — only the persist + read halves of the loop are wired; the WHERE-filter extract (ETL-INC-03) stays in Phase 28. INC-04's full error-handling stays in 28 (except the minimal missing-column guard, see below).

---

## Watermark read query — identifying the "last successful watermark"

| Option | Description | Selected |
|--------|-------------|----------|
| Last success with non-NULL watermark | `WHERE status='success' AND watermark IS NOT NULL ORDER BY started_at DESC LIMIT 1` — empty/failed runs naturally skipped | ✓ |
| Last success (any watermark) | Filter `status='success'` only; requires empty-success runs to copy the prior watermark forward (not leave NULL) | |

**User's choice:** Last success with non-NULL watermark
**Notes:** Makes the empty-batch-preserves invariant fall out of the query — no copy-forward write needed. Failed runs (NULL watermark) and empty-batch successes (which preserve, never write) are automatically skipped.

---

## JSONB binding — what to pass as the %s param

| Option | Description | Selected |
|--------|-------------|----------|
| Jsonb() wrap at write-site | Import `psycopg.types.json.Jsonb`; wrap `_encode_watermark(value)` as `Jsonb(env)` on the UPDATE param; read side decodes the plain dict psycopg returns | ✓ |
| json.dumps() string | Serialize the envelope with `json.dumps` and let the JSONB column cast it; avoids the import but less idiomatic for psycopg 3 | |

**User's choice:** Jsonb() wrap at write-site
**Notes:** This is exactly the write-site concern Phase 26 D-05 deferred to Phase 27. `Jsonb` is NOT yet imported in etl.py — add it. Failed/empty runs pass no watermark (column stays NULL).

---

## Missing watermark column in the extract

| Option | Description | Selected |
|--------|-------------|----------|
| Raise clear ETLError now | Raise a clear ETL* error (not bare KeyError) the moment the watermark column is missing from the raw batch; Phase 28 reuses/refines | ✓ |
| Defer to Phase 28, allow KeyError interim | Keep 27 strictly to persist/read/round-trip; bare KeyError surfaces until Phase 28 wraps it (ETL-INC-04) | |

**User's choice:** Raise clear ETLError now
**Notes:** Cheap to do at the `df[col].max()` site and avoids a confusing KeyError leaking in the interim. Applies only when `pipeline.incremental_column` is set. Phase 28 owns the formal ETL-INC-04 requirement.

---

## max() type coercion (numpy/pandas → {datetime, int, str})

| Option | Description | Selected |
|--------|-------------|----------|
| Coerce to Python scalar in run() | Normalize at the run() call-site (`pd.Timestamp.to_pydatetime()`, `int(np_int)`) before `_encode_watermark`; keep the pure helper's strict allowlist intact | |
| Widen _encode_watermark allowlist | Teach `_encode_watermark` to accept numpy/pandas types directly; re-opens the Phase 26 frozen-helper contract | |
| Let planner decide after testing | Flag the coercion need in CONTEXT; planner picks the site after observing what pandas returns; constrain to: encoded value must satisfy {datetime, int, str} | ✓ |

**User's choice:** Let planner decide after testing
**Notes:** Constraint recorded: the value handed to `_encode_watermark` must satisfy the `{datetime, int, str}` allowlist. Preferred (non-mandated) direction is call-site coercion leaving the frozen Phase-26 helper untouched; don't re-open `_encode_watermark` unless call-site coercion proves insufficient.

---

## Claude's Discretion

- `_read_watermark` placement (method on `ETLAccessor` vs free helper) — follow existing run-log method placement.
- Whether to extend `ETL_UPDATE_RUN` to set `watermark` or add a dedicated success-path UPDATE constant — failed path must NOT touch `watermark`.
- Exact integration-test placement in `tests/test_etl_accessor.py` (extend `TestETLAccessorIntegration` / `TestRunPipelineIntegration` conventions).
- Exact `max()` type-coercion points (deferred to planner per the area above).
- Docstring wording — numpydoc shallow, `interrogate ≥ 95`.

## Deferred Ideas

- WHERE-filter extract wiring (ETL-INC-03) — Phase 28.
- `RunResult.watermark_used` / `watermark_recorded` (ETL-INC-07) + `history()`/`last_run()` surfacing (ETL-INC-08) — Phase 28.
- `dry_run` incremental support (ETL-INC-09) — Phase 28.
- `AsyncETLAccessor` mirror + `TestEtlParity` (ETL-INC-11) — Phase 28.
- Incremental docs / backfill-reset workflow (ETL-INC-12) — Phase 28.
- Formal ETL-INC-04 missing-column treatment — Phase 28.
- `float` watermark support — out of scope v0.7.0 (additive later).
- Naive-datetime rejection policy — not adopted (offset-preserving envelope + documented aware-only contract).
- `initial_watermark` first-run bound — deferred to v0.8.0 (ETL-INC-F01).
