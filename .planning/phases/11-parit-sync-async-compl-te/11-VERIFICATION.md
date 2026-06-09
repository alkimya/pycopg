---
status: passed
phase: 11-parit-sync-async-compl-te
verified: 2026-06-09
method: goal-backward (codebase + test execution)
requirements_verified: [PAR-01, PAR-02, PAR-03, PAR-04, PAR-05, PAR-06, PAR-07, PAR-08, PAR-09]
requirements_total: 9
requirements_met: 9
---

# Phase 11 Verification — Parité sync/async complète

**Goal:** Restaurer la valeur cœur du projet — 0 méthode divergente non documentée ;
cliquet coverage → 90.

**Verdict: PASSED.** All 9 requirements (PAR-01..PAR-09) are delivered and verified against
the live codebase, not merely claimed in summaries.

## Success Criteria (from ROADMAP)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | AsyncDatabase implements add_primary_key/add_foreign_key/add_unique_constraint/truncate_table/drop_extension/database_exists/list_databases/create/create_from_env | ✅ | `hasattr` check on all 9 passes; real-DB tests in TestAsyncDatabaseConstraintsIntegration + TestAsyncDatabaseAdminIntegration |
| 2 | Database implements insert_many/upsert_many/stream/notify | ✅ | `hasattr` check passes; `listen` correctly absent (D-06); tests in TestDatabaseBatchStreamNotify |
| 3 | C1/C2/C3 fixed (async primary_key applied, close() disposes engine, psycopg_async driver) | ✅ | source contains `await self.add_primary_key(...)` (no warning), `dispose()`+`_async_engine=None` in close(), `config.async_url` (psycopg_async) in async_engine |
| 4 | Signatures aligned: create_extension(schema), create_schema(owner), table_info/list_roles semantics | ✅ | `inspect.signature` equality sync==async; table_info/list_roles field-parity tests pass |
| 5 | test_parity.py extended to return fields + real-DB behavior (D-03) | ✅ | TestBehavioralParity (line 182), 13 real-DB sync==async assertions; 17 parity tests pass |
| 6 | Coverage gate raised to 90 (ratchet) | ✅ | `--cov-fail-under=90`; full suite reports "Required test coverage of 90% reached. Total coverage: 91.61%" |

## Requirement-by-requirement (goal-backward, against codebase)

- **PAR-01** ✅ — 4 async DDL methods present and apply real constraints (FK cascade, unique-rejects-dup verified on real DB).
- **PAR-02** ✅ — drop_extension/database_exists/list_databases + async create/create_from_env classmethods present and functional.
- **PAR-03** ✅ — sync insert_many/upsert_many/stream/notify present; listen intentionally async-only (D-06).
- **PAR-04 (C1)** ✅ — async from_dataframe/from_geodataframe call add_primary_key; warning string removed.
- **PAR-05 (C2)** ✅ — async close() disposes the engine + nulls the reference; idempotent.
- **PAR-06 (C3)** ✅ — Config.async_url emits postgresql+psycopg_async://; async_engine built from it.
- **PAR-07** ✅ — create_extension(schema)/create_schema(owner) signatures match sync; table_info/list_roles fields identical.
- **PAR-08** ✅ — test_parity asserts results/fields/behavior on the real DB for this phase's pairs; introspection retained as full-surface guard; KNOWN_SIGNATURE_MISMATCHES emptied; ASYNC_ONLY_METHODS = {async_engine, listen}.
- **PAR-09** ✅ — measured 91.61% (≥90), gate flipped 80→90, suite passes the gate (D-08 ordering honored).

## Test execution
- `uv run pytest`: **652 passed, 2 skipped, 2 failed**. Coverage **91.61%** — gate (90) reached.
- Parity suite: 17/17 pass. Async suite: full pass. Sync suite: full pass.

## Known pre-existing failures (out of phase scope — NOT regressions)
1. `tests/test_integration.py::TestAsyncIntegration::test_async_transaction_fix` — psycopg version
   behavior change ("Explicit commit() forbidden within a Transaction context"). File last modified
   at v0.2.0, NOT touched in Phase 11.
2. `tests/test_postgis_errors.py::TestPostGISErrorHandling::test_create_spatial_index_name_parameter`
   — references a table that doesn't exist in the test DB (test-data/setup issue). File last modified
   in Phase 06, NOT touched in Phase 11.

Both were explicitly anticipated in the phase plan as pre-existing and confirmed via git history to
predate Phase 11. The 90% coverage gate passes both with and without these 2 tests (91.61% / 91.11%),
so they do not affect the ratchet.

## Code review
`11-REVIEW.md`: status **clean** — 0 critical, 0 warning, 1 info (drop_extension name validation,
a pre-existing pattern, optional Phase-12 hardening).

## Deviations recorded during execution
- Worktree/permission infra: phase executed inline on main (background subagents lacked Bash
  permission and a stale `origin/main` caused worktree base mismatches — fixed by pushing 43
  unpushed commits before falling back to inline execution).
- 3 latent source bugs fixed in passing (notify pg_notify in 11-02; copy_to_csv memoryview +
  hypertable_info %I/type in 11-07), each applied to BOTH sync and async to preserve parity.

## Conclusion
Phase 11 achieves its goal: sync/async parity is restored (0 undocumented divergent method —
only `engine`/`async_engine` and the by-design async-only `listen` remain as documented
exceptions), the 3 correctness bugs are closed, and the coverage ratchet is locked at 90. PASSED.
