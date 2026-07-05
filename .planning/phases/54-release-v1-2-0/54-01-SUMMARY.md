---
phase: 54-release-v1-2-0
plan: 01
subsystem: release-hygiene
tags: [vulture, ci, docs, dead-code, makefile]

# Dependency graph
requires:
  - phase: 53-crud-symmetry-introspection
    provides: CRUD-F04..F06 + INTRO-F03/F04 shipped, milestone surface complete before release
provides:
  - "docs/spatial.md and docs/api-reference.md corrected to ExtensionNotAvailableError (DOC-14)"
  - "make deadcode target wired to canonical vulture command + CI quality-gate step (TOOL-01, settles AUDIT-02)"
  - "vulture_whitelist.py documents the 2 Hashable false positives (cast() string annotation)"
affects: [54-release-v1-2-0 remaining plans (54-02 CHANGELOG, 54-03 tag/publish)]

# Tech tracking
tech-stack:
  added: []
  patterns: ["CI quality-gate steps run without a DB env block when the tool needs no database (mirrors interrogate/Sphinx/mypy steps)"]

key-files:
  created: []
  modified:
    - docs/spatial.md
    - docs/api-reference.md
    - Makefile
    - .github/workflows/tests.yml
    - vulture_whitelist.py

key-decisions:
  - "Task 1 (DOC-14) had already been executed and committed in a prior session (f3b4c13) before this run started; verified correctness and proceeded directly to Task 2."
  - "Makefile deadcode target + .PHONY entry were already present as an uncommitted working-tree edit from a prior interrupted session; kept as-is (matches plan exactly) and folded into the Task 2 commit alongside the CI step and whitelist entry."
  - "Whitelisted Hashable rather than removing the import: it is load-bearing inside cast(\"dict[Hashable, Any] | None\", dtype) string-literal annotations at database.py:2299/async_database.py:1941, invisible to vulture's AST scan but required by mypy --strict."

patterns-established:
  - "Dead-code scanning (vulture) is now a permanent CI gate, run immediately after mypy type check, using the exact command documented at the top of vulture_whitelist.py."

requirements-completed: [DOC-14, TOOL-01]

# Metrics
duration: ~16min
completed: 2026-07-05
---

# Phase 54 Plan 01: DOC-14 + TOOL-01 (Release Hygiene) Summary

**Corrected the two remaining `ExtensionNotAvailable` doc-prose residues to `ExtensionNotAvailableError` and wired `vulture` into `make deadcode` + CI, whitelisting the 2 confirmed `Hashable` false positives so the scan runs clean on every push.**

## Performance

- **Duration:** ~16 min (Task 2 work; Task 1 was completed and committed in a prior session)
- **Started:** 2026-07-05T20:10:13+02:00 (Task 1 commit, prior session)
- **Completed:** 2026-07-05T20:26:01+02:00 (Task 2 commit)
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- `docs/spatial.md:30` and `docs/api-reference.md:331` now read `ExtensionNotAvailableError`; `docs/stability.md`'s 4 intentional mentions and `docs/api-reference.md:586` (already correct) left untouched
- `make deadcode` target (+ `deadcode` on `.PHONY`) runs the canonical `uv run vulture pycopg/ vulture_whitelist.py --min-confidence 80` and exits 0
- `.github/workflows/tests.yml` runs the same vulture command as a CI quality-gate step immediately after `mypy type check`, on every push/PR, with no DB env block needed
- `vulture_whitelist.py` documents the 2 `Hashable` false positives (load-bearing inside a `cast()` string-literal annotation) with a rationale comment mirroring the file's existing style; both imports remain intact
- `uv run mypy pycopg/` still reports "Success: no issues found in 18 source files" — confirms no import was deleted

## Task Commits

Each task was committed atomically:

1. **Task 1: DOC-14 — correct bare `ExtensionNotAvailable` prose residues** - `f3b4c13` (docs) — committed in a prior session before this execution run began; verified correct, no rework needed.
2. **Task 2: TOOL-01 — wire vulture into make deadcode + CI, whitelist Hashable false positives** - `7234ce7` (chore)

## Files Created/Modified
- `docs/spatial.md` - `ExtensionNotAvailable` -> `ExtensionNotAvailableError` at line 30
- `docs/api-reference.md` - `ExtensionNotAvailable` -> `ExtensionNotAvailableError` at line 331 (line 586 untouched, already correct)
- `Makefile` - added `deadcode` target + `.PHONY` entry
- `.github/workflows/tests.yml` - added "Dead-code scan (vulture)" step after "mypy type check"
- `vulture_whitelist.py` - new documented section whitelisting `Hashable` (cast() string-annotation false positive)

## Decisions Made
- Kept the plan's exact canonical vulture command (`uv run vulture pycopg/ vulture_whitelist.py --min-confidence 80`) in both the Makefile target and the CI step, verbatim, to guarantee `make deadcode` and CI never drift from each other.
- Confirmed both `Hashable` findings are false positives (not real dead code) before whitelisting per the plan's threat mitigation (T-54-01/T-54-02): imports remain present, mypy --strict still 0/18.

## Deviations from Plan

None — plan executed exactly as written. Task 1 was found already complete (committed in a prior session, `f3b4c13`) and Task 2's Makefile edit was found as an uncommitted carry-over from a prior interrupted session; both were verified against the plan's exact acceptance criteria before proceeding, and no plan requirement was skipped or altered.

## Issues Encountered
None — `make deadcode` reported exactly the 2 expected `Hashable` findings on first run, matching the plan's `<read_first>` prediction; both were whitelisted and the re-run exited 0.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Both DOC-14 and TOOL-01 requirements are fully shipped; `make deadcode` and CI are green; mypy --strict remains 0/18.
- Ready for 54-02 (CHANGELOG [1.2.0] entry) and 54-03 (version bump, annotated tag, release).

---
*Phase: 54-release-v1-2-0*
*Completed: 2026-07-05*
