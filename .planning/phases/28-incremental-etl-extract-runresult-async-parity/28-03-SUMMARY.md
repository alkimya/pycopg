---
phase: 28-incremental-etl-extract-runresult-async-parity
plan: 03
subsystem: database
tags: [postgresql, etl, watermark, incremental, documentation, sphinx]

# Dependency graph
requires:
  - phase: 28-01
    provides: "RunResult.watermark_used/watermark_recorded fields; dry_run incremental semantics; sync watermark-filter behavior as shipped"
  - phase: 28-02
    provides: "async parity surface confirmed; ETL-INC-11 closed; async_db.etl.run watermark behavior identical to sync"
provides:
  - "docs/etl.md ## Incremental loading section (ETL-INC-12)"
  - "Watermark-column requirements documented (monotonic, aware-datetime/int/text, > exclusive, float rejected)"
  - "RunResult.watermark_used / watermark_recorded semantics documented (None for stored rows per D-A1)"
  - "dry_run incremental preview behavior documented (D-A2)"
  - "Backfill/reset manual SQL workflow documented (D-A5, no reset API)"
  - "initial_watermark v0.8.0 note documented"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sphinx -W gate: new RST note directive (.. note::) used in Markdown via MyST parser — clean with no warnings"

key-files:
  created: []
  modified:
    - "docs/etl.md"

key-decisions:
  - "D-A4 honored: ## Incremental loading covers all 7 required points (watermark requirements, upsert constraint, first-run/subsequent semantics, RunResult fields, dry_run preview, backfill workflow)"
  - "D-A5 honored: no reset_watermark() API documented; manual SQL only (UPDATE pipeline_runs SET watermark = NULL WHERE pipeline_name = %s)"
  - "Section placed after ### Dry runs and before ## Async Usage — logical flow: regular runs -> dry runs -> incremental -> async"
  - ".. note:: directive used for the v0.8.0 initial_watermark callout — Sphinx-clean RST in MyST context"

patterns-established:
  - "RST note directive (.. note::) in MyST Markdown docs: renders correctly, -W gate clean"

requirements-completed: [ETL-INC-12]

# Metrics
duration: 8min
completed: 2026-06-21
---

# Phase 28 Plan 03: Incremental loading docs — ## Incremental loading section in docs/etl.md closing ETL-INC-12

**`## Incremental loading` section added to `docs/etl.md` covering watermark-column requirements, upsert constraint, first-run vs subsequent-run semantics, `RunResult.watermark_used`/`watermark_recorded` field docs, `dry_run` preview behavior, and manual SQL backfill/reset workflow (D-A4, D-A5); Sphinx `-W` gate confirmed clean**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-06-21T17:40:00Z
- **Completed:** 2026-06-21T17:48:00Z
- **Tasks:** 1 completed
- **Files modified:** 1

## Accomplishments

- Added `## Incremental loading` section (136 lines) to `docs/etl.md` between `### Dry runs` and `## Async Usage`
- Section documents: worked `Pipeline(incremental_column="updated_at", load_mode="upsert", conflict_columns=[...])` example with both `db.etl.run` and `async_db.etl.run` parity note; watermark-column requirements (monotonic, aware-datetime/int/text, `>` exclusive, float rejected with `ETLError`); why upsert is required (append/replace forbidden at construction); first-run/subsequent-run semantics including advance-only-on-success, empty-batch preservation, and max-from-raw-batch-before-transforms; `watermark_used` / `watermark_recorded` field descriptions with `None` semantics for stored rows and non-incremental pipelines; `dry_run` filtered preview with honest `rows_extracted` count; manual SQL backfill/reset workflow with `initial_watermark` v0.8.0 note
- Sphinx `-W` build confirmed exit 0 (no new warnings) — Phase 29 gate passes
- All grep gate checks pass: `## Incremental loading`, `incremental_column`, `watermark_used`, `watermark_recorded`, `UPDATE pipeline_runs SET watermark = NULL`

## Task Commits

1. **Task 1: Write the Incremental loading docs section** - `e804278` (docs)

## Files Created/Modified

- `/home/loc/workspace/pycopg/docs/etl.md` — 136-line `## Incremental loading` section added covering all D-A4/D-A5 points

## Decisions Made

- Placed section after `### Dry runs` and before `## Async Usage` — logical reading flow from basic runs to incremental (a specialized run type), then async variants
- Used RST `.. note::` directive for the `initial_watermark` v0.8.0 callout — renders as a styled note box in Sphinx output, confirmed -W-clean
- Wrote `watermark_recorded` and `watermark_used` as definition-list-style entries with blank-line separation for clarity

## Deviations from Plan

None - plan executed exactly as written. The system-level `sphinx-build` binary had a missing `pygments` dependency, but `uv run python -m sphinx` (using the project venv after installing docs deps via `uv pip install`) ran cleanly. This is an environment issue, not a code deviation.

## Issues Encountered

- System `sphinx-build` at `/home/loc/.local/bin/sphinx-build` failed with `ModuleNotFoundError: No module named 'pygments'` — used `uv run python -m sphinx` after installing `sphinx myst-parser furo sphinx-copybutton` via `uv pip install`. The project's `docs/requirements.txt` lists all required deps; they were not in the uv project deps (`dev` group), so the venv needed them installed manually for this verification.

## Next Phase Readiness

- ETL-INC-12 closed — all 7 ETL-INC requirements now complete
- Phase 29 (Release v0.7.0) can proceed: Sphinx `-W` gate is clean, no CHANGELOG/MIGRATION/version-bump changes here
- The `## Incremental loading` section accurately describes what shipped in Plans 01+02

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. Documentation-only change. The documented `UPDATE pipeline_runs SET watermark = NULL WHERE pipeline_name = %s` snippet uses a `%s` placeholder for `pipeline_name` (parameterized) — T-28-D1 accepted disposition as specified in plan threat model.

## Self-Check: PASSED

- `docs/etl.md` contains `## Incremental loading` heading: confirmed (`grep -n '^##' docs/etl.md` line 212)
- Grep gate passes (`OK` printed): confirmed
- Sphinx `-W` build exits 0 (no warnings): confirmed (`La compilation a réussi.`)
- Commit `e804278` exists in git log: confirmed
- No pyproject.toml, docs/conf.py, CHANGELOG, MIGRATION changes: confirmed (only `docs/etl.md` modified)

---
*Phase: 28-incremental-etl-extract-runresult-async-parity*
*Completed: 2026-06-21*
