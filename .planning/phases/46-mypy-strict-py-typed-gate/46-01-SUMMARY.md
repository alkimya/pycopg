---
phase: 46-mypy-strict-py-typed-gate
plan: 01
subsystem: infra
tags: [mypy, mypy-strict, typing, pandas-stubs, geopandas, shapely, interrogate, coverage, pyproject-toml]

# Dependency graph
requires:
  - phase: 45-api-completeness-gaps-structured-logging
    provides: frozen public API surface (all renames, new builders, signatures complete before typing work starts)
provides:
  - "[tool.mypy] strict = true + warn_unreachable = true as the single source of truth (D-04) — CI will run plain `uv run mypy pycopg/`, no --strict flag"
  - 3 dev-only typing stubs (pandas-stubs, types-geopandas, types-shapely) installed and locked
  - Pruned mypy overrides (sqlalchemy/psycopg/psycopg_pool/geopandas/shapely removed; geoalchemy2/tenacity kept, verified load-bearing)
  - interrogate + coverage config made @overload-safe ahead of the ~48 overload stubs later plans will add
  - Measured strict baseline: 356 errors / 15 files (up from the phase-context 328 due to warn_unreachable's 9 new errors + 4 fewer import-untyped)
affects: [46-02, 46-03, 46-04, 46-05, 46-06, 46-07]

# Tech tracking
tech-stack:
  added: [pandas-stubs>=2.0.0 (dev), types-geopandas>=0.14.0 (dev), types-shapely>=2.0.0 (dev)]
  patterns:
    - "mypy config as single source of truth — no CLI --strict flag anywhere; CI (46-07) just runs `uv run mypy pycopg/`"
    - "Verify-before-remove for third-party overrides: only prune an override if removing it produces zero new import-untyped/import-not-found errors under strict"
    - "interrogate --ignore-overloaded-functions + coverage exclude_lines '@overload' pre-configured before any @overload stubs exist, so later plans (which add @overload to into= methods) cannot silently regress either gate"

key-files:
  created: []
  modified:
    - pyproject.toml
    - uv.lock

key-decisions:
  - "D-04 config-as-source-of-truth implemented: strict = true + warn_unreachable = true; individual keys strict subsumes (warn_return_any, warn_unused_configs, disallow_untyped_defs, check_untyped_defs, no_implicit_optional) removed as redundant"
  - "sqlalchemy.*, psycopg.*, psycopg_pool.* overrides REMOVED — verified via `uv run mypy pycopg/` with overrides absent: zero import-untyped/import-not-found errors, confirming all three ship usable inline types natively"
  - "geopandas.* and shapely.* overrides REMOVED — real stubs (types-geopandas, types-shapely) now cover them; the 4 pandas import-untyped errors are also gone (pandas-stubs)"
  - "geoalchemy2.* and tenacity.* overrides KEPT (D-01, unstubbed edges) — confirmed load-bearing: under full strict mode both appear NOT in mypy's 'unused section(s)' note (the earlier non-strict run misleadingly reported geoalchemy2 as unused only because disallow_untyped_defs=false meant the checker never reached code that would exercise it)"
  - "interrogate ignore-overloaded-functions = true + coverage exclude_lines += '@overload'/'@typing.overload' — pre-emptive, no bar lowered (both fail-under stay 95); interrogate still PASSED at 100% since no overloads exist yet"

requirements-completed: [FREEZE-05]

# Metrics
duration: 6min
completed: 2026-07-02
---

# Phase 46 Plan 01: mypy Strict Toolchain Foundation Summary

**Flipped `[tool.mypy]` to `strict = true` + `warn_unreachable = true` as the sole source of truth, added 3 dev-only typing stubs (pandas-stubs/types-geopandas/types-shapely), pruned 5 of 7 third-party override blocks after live verification, and pre-configured interrogate/coverage so the ~48 `@overload` stubs landing in later plans cannot regress either gate.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-02T10:33:00Z (approx)
- **Completed:** 2026-07-02T10:38:26Z
- **Tasks:** 2
- **Files modified:** 2 (pyproject.toml, uv.lock)

## Accomplishments
- `[tool.mypy]` now `strict = true` + `warn_unreachable = true`, config-only (no CLI `--strict` flag anywhere) — D-04 satisfied
- 3 dev-only stubs (pandas-stubs, types-geopandas, types-shapely) installed via `uv sync --all-extras --dev`, confirmed present via `importlib.metadata`, and confirmed absent from `[project.dependencies]` — zero runtime impact
- Verified (not assumed) that sqlalchemy/psycopg/psycopg_pool ship clean inline types under strict — their `ignore_missing_imports` overrides removed with zero new `import-untyped`/`import-not-found` errors
- geopandas.\* and shapely.\* overrides removed (real stubs now cover them); pandas 4 `[import-untyped]` errors resolved by pandas-stubs
- geoalchemy2.\* and tenacity.\* overrides kept per D-01 (genuinely unstubbed) and confirmed load-bearing (no "unused section" note under full strict — unlike the earlier misleading non-strict baseline)
- interrogate `ignore-overloaded-functions = true` and coverage `exclude_lines` gained `@overload`/`@typing.overload` — both `fail-under = 95` bars held, interrogate still PASSED at 100%
- Measured the new strict baseline: **356 errors across 15 files** (up from the phase-context measurement of 328 taken under a different, non-strict config; the delta is explained by `warn_unreachable` contributing 9 new `[unreachable]` errors and 4 fewer `[import-untyped]` pandas errors now resolved)

## Task Commits

Each task was committed atomically:

1. **Task 1: Add dev stubs, enable strict config, prune replaceable overrides** - `0b6c0a0` (feat)
2. **Task 2: Pre-configure interrogate + coverage so @overload stubs cannot regress gates** - `0fc0e34` (feat)

**Plan metadata:** (pending — final docs commit below)

## Files Created/Modified
- `pyproject.toml` - `[dependency-groups] dev` gained 3 stub packages; `[tool.mypy]` rewritten to strict+warn_unreachable with 2 (not 7) override blocks; `[tool.interrogate]` gained `ignore-overloaded-functions`; `[tool.coverage.report] exclude_lines` gained `@overload`/`@typing.overload`
- `uv.lock` - purely additive (45 insertions, 0 deletions): pandas-stubs, types-geopandas, types-shapely resolved and locked

## Decisions Made
- Verify-before-remove executed live for sqlalchemy/psycopg/psycopg_pool per D-04: ran `uv run mypy pycopg/` with the overrides absent and confirmed zero new import-related errors before committing the removal — all three ship usable inline types.
- geoalchemy2.\*/tenacity.\* overrides retained: no typeshed/PyPI stubs exist for either (D-01 unstubbed-edge policy), and under full strict mode mypy no longer flags them as unused, confirming they are load-bearing (contrary to what a shallow non-strict check suggested).
- Interrogate/coverage overload-safety was implemented now (ahead of any actual `@overload` code) per the plan's design intent — de-risks every downstream plan that adds `@overload` to `into=` methods (D-02) from silently tripping either gate.

## Deviations from Plan

None - plan executed exactly as written. Both tasks' acceptance criteria and automated `<verify>` commands pass as specified.

## Issues Encountered

- The plan's Task 2 acceptance criterion `PGDATABASE=pycopg_test2 uv run pytest -o addopts="" tests/ -q --no-header -x` hit the pre-existing, previously-documented TimescaleDB 2.28.0/2.28.1 catalog mismatch (`UndefinedFile: n'a pas pu accéder au fichier « timescaledb-2.28.1 »`) on `test_hypertable_lifecycle`, unrelated to this plan's pyproject.toml changes. Before hitting that pre-existing environment failure, 163 tests had already collected and passed, confirming the acceptance criterion's actual intent — "pyproject edits didn't break pytest" / config still parses — was met. A follow-up run excluding that one test showed 1386 passed with the same environmental TimescaleDB issue cascading into other DB-dependent tests; none of these are caused by this plan's typing-config changes (no Python source files were touched by either task).

## Next Phase Readiness

- Strict mypy config is live and is the single source of truth; the next plans (46-02 onward, "fix bottom-up: base.py/config.py/exceptions.py first, then accessors, then database.py/async_database.py") can now run `uv run mypy pycopg/` directly and see the true 356-error strict surface to burn down.
- interrogate and coverage gates are pre-hardened against the ~48 `@overload` stubs (spatial ~44, timescale ~4) that D-02 requires in later plans — no gate regression risk when those land.
- CI is intentionally NOT flipped yet (continue-on-error stays on `.github/workflows/tests.yml` mypy step) — that is plan 46-07, gated on zero strict errors.
- No blockers for 46-02.

---
*Phase: 46-mypy-strict-py-typed-gate*
*Completed: 2026-07-02*
