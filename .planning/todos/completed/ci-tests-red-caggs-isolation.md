---
title: Investigate & green the CI test suite (caggs live + integration isolation)
status: resolved
priority: high
created: 2026-06-26
resolved: 2026-06-27
resolution: "Fixed in v0.10.1 (PR #1 + release 924279e). 1 real lib bug (caggs refresh full-refresh NULL-typing) + 3 test/CI gaps fixed; tests.yml now GREEN across 3.11/3.12/3.13. v0.10.1 shipped to PyPI."
source: v0.10.0 release (Phase 40) — user flagged red CI on the release push
relates_to: [REL-10]
---

> **RESOLVED 2026-06-27 in v0.10.1.** `tests.yml` is now green on main. The caggs
> `IndeterminateDatatype` was a real bug in `refresh_continuous_aggregate` (full-refresh
> sent untyped NULL params) — fixed via literal-NULL rendering. The policy `run_job`,
> `test_schema` CI seed, and PostGIS TEMP-table issues were test/CI gaps, all fixed.
> See memory `ci-publish-decoupling-gate-fidelity.md`. (mypy stays continue-on-error.)

## Context

pycopg 0.10.0 shipped to PyPI cleanly (publish.yml green, clean-venv smoke OK),
but `tests.yml` was RED on the release push (run 28269612978) across 3.11/3.12/3.13.
`publish.yml` is decoupled from `tests.yml` (it only runs `uv lock --check` + `uv build`
+ OIDC publish), so the red test job did not block the release. The Tests job has been
chronically red on `main` (v0.9.0 push failed identically and is fine on PyPI), so this
is pre-existing debt, NOT a v0.10.0 package regression. See memory
`ci-publish-decoupling-gate-fidelity.md`.

The package itself is correct — failures are live-DB integration/isolation tests.

## What to investigate (tomorrow)

1. **TimescaleDB continuous-aggregate LIVE tests (4) — likely a REAL but narrow TSL-only bug.**
   - `test_refresh_continuous_aggregate_live` → `psycopg.errors.IndeterminateDatatype:
     could not determine data type of parameter $1`. Look at how `refresh_continuous_aggregate`
     binds its window-bound params (NULL $1 needs an explicit cast, e.g. `$1::timestamptz`).
   - `test_add_continuous_aggregate_policy_live` → `ActiveSqlTransaction:
     refresh_continuous_aggregate() cannot run inside a transaction block` — confirm the
     autocommit seam engages on this path.
   - These are masked LOCALLY (Apache TSDB → FeatureNotSupported) and only surface against
     CI's full-TSL TimescaleDB. Decide: real fix → **v0.10.1**, or test-only fix.

2. **Integration test-isolation failures (5).** `UndefinedTable: test_schema.authors`,
   `assert 'id' in []`, `KeyError: 'id'` in test_integration.py — order-dependent fixture
   setup, amplified by `pytest-randomly` (added Phase 37). Make each test class self-contained
   (create/teardown its own schema+tables) so it passes under any seed.

3. **Known PostGIS flaky (1).** `test_create_spatial_index_name_parameter` — already tracked
   (memory `pycopg-flaky-db-tests`). Confirm whether the Phase 37 de-flake holds in CI.

## Definition of done

`tests.yml` green on `main` across 3.11/3.12/3.13, OR each remaining failure explicitly
xfail/skip-marked with a documented environment reason. If a real caggs bug is confirmed,
cut v0.10.1 with the fix.
