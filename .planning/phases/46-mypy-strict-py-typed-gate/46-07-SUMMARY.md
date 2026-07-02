---
phase: 46-mypy-strict-py-typed-gate
plan: 07
subsystem: infra
tags: [mypy, mypy-strict, typing, py-typed, ci, coverage, interrogate, github-actions]

# Dependency graph
requires:
  - phase: 46-mypy-strict-py-typed-gate
    provides: "46-01..46-06: strict config as source of truth, 3 dev stubs, package-wide annotation burn-down (356 -> 0 errors across all 18 modules), @overload triplets on all into= methods, __all__ audit"
provides:
  - "Confirmed whole-package `uv run mypy pycopg/` exits 0 across 18 source files (config-driven strict, no CLI --strict)"
  - "Confirmed py.typed is a complete/truthful PEP 561 marker — zero override globs match a pycopg-owned module; only 2 genuinely-unstubbed external edges (geoalchemy2, tenacity) retain overrides"
  - "Confirmed coverage ratchet holds at 96.45% (>=95% gate) after all annotation + @overload work, on the working scratch DB pycopg_test3"
  - "Confirmed interrogate docstring coverage at 100% (>=95% gate), overloaded functions correctly ignored"
  - "Confirmed uv.lock is clean (uv lock --check passes) — 3 dev stubs correctly pinned"
  - "CI mypy step flipped from advisory (continue-on-error: true) to a BLOCKING gate (D-04) — FREEZE-05 complete"
affects: [47-release]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CI gate flip ordered strictly after whole-package local verification (Task 2 before Task 3) so the blocking gate lands green on first run, never red"

key-files:
  created: []
  modified:
    - .github/workflows/tests.yml

key-decisions:
  - "Task 2 required zero code changes — pyproject.toml was already fully configured by 46-01 and the annotation work by 46-02..46-06 already reduced the package to 0 strict errors; this plan's Task 2 is pure verification (confirmed by clean `git status --short` after running all checks)"
  - "D-04 CI gate: removed only the `continue-on-error: true` line from the mypy step; run command stays exactly `uv run mypy pycopg/` (config-driven, no CLI --strict flag) — no other CI step touched"
  - "Verified per project memory that PGDATABASE=pycopg_test2 (named in the plan body) is broken; used the working scratch DB PGDATABASE=pycopg_test3 for the coverage-ratchet run instead, per CLAUDE.md/STATE.md operational guidance"

patterns-established: []

requirements-completed: [FREEZE-05]

# Metrics
duration: 12min
completed: 2026-07-02
---

# Phase 46 Plan 07: mypy Strict + py.typed Gate — Terminal Verification + CI Blocking Flip Summary

**Confirmed whole-package `mypy --strict` (config-driven) exits 0 across all 18 pycopg modules, coverage ratchet holds at 96.45%, interrogate at 100%, py.typed truthful with only 2 external unstubbed-edge overrides remaining, then flipped the CI mypy step from advisory to a blocking gate — closing FREEZE-05 and completing Phase 46.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-02T10:12:00Z (approx, continuation after Task 1 checkpoint approval)
- **Completed:** 2026-07-02T10:24:00Z (approx)
- **Tasks:** 3 (Task 1 checkpoint pre-approved by user before this continuation; Tasks 2-3 executed here)
- **Files modified:** 1 (`.github/workflows/tests.yml`)

## Accomplishments

- **Task 1 (checkpoint, pre-approved):** Package-legitimacy verification for the 3 dev-only typing stubs (`pandas-stubs`, `types-geopandas`, `types-shapely`) — confirmed typeshed/official provenance, dev-only placement, lockfile-pinned. User responded "approved". No commit (verification-only task).
- **Task 2 (verification, no code changes needed):**
  - `uv run mypy pycopg/` → `Success: no issues found in 18 source files`, exit 0
  - `uv run mypy pycopg/ 2>&1 | grep -c "error:"` → `0`
  - `pycopg/py.typed` exists; zero override globs match a pycopg-owned module (`grep ... 'module = "pycopg' | wc -l` → `0`) — only `geoalchemy2.*` and `tenacity.*` overrides remain, both genuinely-unstubbed external edges per D-01
  - `PGDATABASE=pycopg_test3 uv run pytest` → 1736 passed, 2 skipped, TOTAL coverage 96%, "Required test coverage of 95% reached. Total coverage: 96.45%" — pytest exit 0, `--cov-fail-under=95` gate passes
  - `uv run interrogate pycopg` → `RESULT: PASSED (minimum: 95.0%, actual: 100.0%)`
  - `uv lock --check` → resolves cleanly, no changes needed
  - No files required modification — `git status --short` was empty after all Task 2 checks, confirming this was pure verification (46-01 through 46-06 already did the real work)
- **Task 3 (CI gate flip):**
  - Removed `continue-on-error: true` from the `mypy type check` step in `.github/workflows/tests.yml`
  - Run command unchanged: `uv run mypy pycopg/` (config-driven, no CLI `--strict`)
  - All acceptance checks passed: `continue-on-error` count 0, run-cmd count 1, `--strict` CLI flag count 0, YAML valid (verified via `uv run --with pyyaml python -c "import yaml; yaml.safe_load(...)"` since PyYAML is not a project or system dependency), local `uv run mypy pycopg/` exits 0

## Task Commits

Each task was committed atomically:

1. **Task 1: Package legitimacy checkpoint** - no commit (verification-only checkpoint, approved by user in prior session)
2. **Task 2: Whole-package strict verification + py.typed completeness + coverage ratchet hold** - no commit (pure verification, zero files changed — confirmed via `git status --short`)
3. **Task 3: Flip the CI mypy step to a blocking gate (D-04)** - `b53581c` (feat)

**Plan metadata:** (pending — final docs commit below)

## Files Created/Modified

- `.github/workflows/tests.yml` - `mypy type check` step: removed `continue-on-error: true`, now a blocking gate; run command unchanged (`uv run mypy pycopg/`)

## External mypy Overrides Retained (2 of original 7)

| Override | Justification |
|----------|----------------|
| `geoalchemy2.*` | No typeshed/PyPI stubs exist for geoalchemy2 (D-01 unstubbed-edge policy). Confirmed load-bearing under full strict mode in 46-01 (mypy no longer flags it as an "unused section" the way the earlier non-strict baseline misleadingly did). |
| `tenacity.*` | Same as above — no usable inline types or third-party stub package exists; confirmed load-bearing under strict in 46-01. |

Overrides removed in earlier plans (for context, not re-verified here — already confirmed clean by 46-01): `sqlalchemy.*`, `psycopg.*`, `psycopg_pool.*` (verified to ship usable inline types natively), `geopandas.*` and `shapely.*` (superseded by the `types-geopandas`/`types-shapely` dev stubs).

## Coverage After All Annotation Work

**96.45%** (`TOTAL` line: 4051 statements, 144 missed, 96% displayed; pytest's coverage-fail-under summary reports the more precise 96.45%), against a `--cov-fail-under=95` gate. 1736 tests passed, 2 skipped, 0 failed. Run against the working scratch database `PGDATABASE=pycopg_test3` (the plan-specified `pycopg_test2` remains broken per project memory — TimescaleDB `.so` version drift).

## Decisions Made

- Confirmed via `uv run --with pyyaml python -c "import yaml; ..."` (ephemeral dependency, not added to the project) rather than adding PyYAML as a dev dependency just for a one-off CI YAML syntax check — the acceptance criterion's intent (valid YAML) was met without adding unneeded project dependencies.
- Used `PGDATABASE=pycopg_test3` instead of the plan-specified `pycopg_test2` per CLAUDE.md/STATE.md operational guidance — `pycopg_test2` has been broken since a TimescaleDB catalog version mismatch; `pycopg_test3` is the confirmed-working scratch DB used by 46-02 through 46-06.

## Deviations from Plan

None (functional) - Task 2 and Task 3 both executed exactly as specified in the plan's acceptance criteria; the only substitution was the test database name (`pycopg_test3` for `pycopg_test2`), which is a pre-existing, documented environmental workaround (not a plan deviation in the Rule 1-4 sense — it's the standing project convention recorded in CLAUDE.md/STATE.md/project memory).

## Issues Encountered

- System `python3` (both the OS interpreter and the project venv's) lacks PyYAML, so the plan's literal `python -c "import yaml; ..."` acceptance command as written would fail with `ModuleNotFoundError`. Resolved by running the same check via `uv run --with pyyaml python -c "..."`, which satisfies the acceptance criterion's actual intent (validate the YAML) without polluting the project's dependency surface.

## Next Phase Readiness

- **FREEZE-05 is complete**: whole-package `mypy --strict` exits 0 (18/18 modules), `py.typed` is a truthful PEP 561 marker with only 2 justified external overrides, coverage ratchet holds at 96.45% (>=95%), interrogate at 100% (>=95%), lockfile clean, and the CI mypy step is now a **blocking** gate (no `continue-on-error`).
- Phase 46 (mypy Strict + py.typed Gate) is now fully complete — 7/7 plans done.
- Phase 47 (Release v1.0.0) can now rely on REL-11 (mypy --strict exit 0 as a release gate) being enforced continuously in CI, not just locally at release time.
- No blockers for Phase 47.

---
*Phase: 46-mypy-strict-py-typed-gate*
*Completed: 2026-07-02*

## Self-Check: PASSED

- FOUND: .github/workflows/tests.yml (modified, continue-on-error removed)
- FOUND: b53581c (Task 3 commit)
- FOUND: .planning/phases/46-mypy-strict-py-typed-gate/46-07-SUMMARY.md
