---
phase: 37-dette-audit
plan: 01
subsystem: tooling
tags: [ruff, vulture, pytest-randomly, lint, dead-code, uv, pyproject]

# Dependency graph
requires:
  - phase: 36-release-v0.9.0
    provides: clean v0.9.0 baseline (94.11% coverage, 4 ruff N818 errors, accessor-only surface)
provides:
  - "[tool.ruff.lint] modern config layout (no deprecation warning)"
  - "N818 per-file-ignore for pycopg/exceptions.py (DEBT-02 pycopg/ half)"
  - "vulture + pytest-randomly installed in dev-group (AUDIT-02 tooling)"
  - "vulture_whitelist.py seed allowlist at project root"
affects: [37-02, 37-03, 37-04, 37-05]

# Tech tracking
tech-stack:
  added: [vulture>=2.9.1, pytest-randomly>=3.15.0]
  patterns:
    - "Ruff per-file-ignore for breaking-to-rename public exception names (D-01a)"
    - "vulture .py whitelist file form over config (Claude's discretion, D-07)"

key-files:
  created:
    - vulture_whitelist.py
  modified:
    - pyproject.toml
    - uv.lock

key-decisions:
  - "N818 suppressed via per-file-ignore, NOT renamed — exception names are public (__all__), renaming is breaking, deferred to v1.0.0 API freeze (D-01a)"
  - "vulture allowlist as a .py whitelist file (not config) — standard form for this codebase size (D-07/Claude's discretion)"
  - "Seed allowlist lists only the 4 confirmed public-exception false positives; scan-driven refinement deferred to Plan 05"

patterns-established:
  - "Ruff config migration: select/ignore live under [tool.ruff.lint]; per-file-ignores under [tool.ruff.lint.per-file-ignores]"
  - "Dev-only tooling additions go to [dependency-groups] dev; zero runtime-dep impact"

requirements-completed: [DEBT-02, AUDIT-02]

# Metrics
duration: 8min
completed: 2026-06-26
---

# Phase 37 Plan 01: Tooling & Lint-Config Foundation Summary

**Migrated ruff to the modern `[tool.ruff.lint]` layout with a documented N818 per-file-ignore for the public exceptions, and installed `vulture` + `pytest-randomly` in the dev-group with a seeded dead-code allowlist.**

## Performance

- **Duration:** ~8 min (execution after checkpoint approval)
- **Started:** 2026-06-26T06:52:16Z (plan execution start)
- **Completed:** 2026-06-26T06:57:56Z
- **Tasks:** 3 (Task 1 = approved package-legitimacy checkpoint; Tasks 2-3 = auto)
- **Files modified:** 3 (pyproject.toml, uv.lock, vulture_whitelist.py)

## Accomplishments

- Migrated the deprecated top-level `[tool.ruff]` `select`/`ignore` keys to `[tool.ruff.lint]`, eliminating the ruff deprecation warning.
- Added `[tool.ruff.lint.per-file-ignores]` with `"pycopg/exceptions.py" = ["N818"]` and an explanatory comment — `uv run ruff check pycopg` now exits 0 (was 4 N818 errors + 1 deprecation warning).
- Added `vulture>=2.9.1` and `pytest-randomly>=3.15.0` to `[dependency-groups] dev` and refreshed `uv.lock` (installed `vulture==2.16`, `pytest-randomly==4.1.0`).
- Created `vulture_whitelist.py` at the project root — a documented false-positive allowlist seeding the 4 public exceptions; consumable by `uv run vulture pycopg/ vulture_whitelist.py --min-confidence 80`.

## Task Commits

1. **Task 1: Package-legitimacy checkpoint** — no commit (blocking-human gate; operator confirmed `vulture` (Jendrik Seipp) and `pytest-randomly` (adamchainz / pytest-dev) canonical on PyPI, typed "approved")
2. **Task 2: Migrate ruff config + dev-group tooling** — `37bf5c7` (chore)
3. **Task 3: Seed vulture allowlist** — `17fe906` (chore)

## Files Created/Modified

- `pyproject.toml` — `[tool.ruff.lint]` migration + `[tool.ruff.lint.per-file-ignores]` N818 entry + `vulture`/`pytest-randomly` in dev-group
- `uv.lock` — refreshed by `uv sync --all-extras --dev`
- `vulture_whitelist.py` (NEW) — documented dead-code false-positive allowlist seed

## Decisions Made

- **N818 = suppression, not rename (D-01a):** the 4 exception names (`ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier`, `DatabaseExists`) are exported in `__all__`; renaming to add an `Error` suffix is a breaking public-API change, deferred to the v1.0.0 API freeze. Per-file-ignore is the correct mechanism.
- **vulture allowlist as a `.py` whitelist file (D-07/Claude's discretion):** standard form for a ~15.4k-LOC codebase; references names via empty attribute access.
- **Seed-only allowlist:** only the 4 confirmed public-exception false positives are listed. The live scan surfaces additional candidates (e.g. `__exit__` `exc_type`/`exc_val`/`exc_tb`); per the plan these are deferred to Plan 05's scan-driven refinement and were NOT added to the seed.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. Verifications passed first time:

- `uv run ruff check pycopg` → `All checks passed!` (exit 0, no deprecation warning)
- `uv run python -c "import vulture; import pytest_randomly"` → exit 0
- `grep -c 'cov-fail-under=94' pyproject.toml` → 1 (ratchet unchanged)
- `uv run vulture pycopg/ vulture_whitelist.py --min-confidence 80` → exit 3 (real findings reported for Plan 05; no import/parse error on the whitelist file)

## User Setup Required

None - dev-only tooling, no external service configuration required.

## Next Phase Readiness

- Wave 2 (Plan 02+) can now rely on `pytest-randomly` being installed for flaky-determinism enforcement (DEBT-01).
- Wave 3 (Plan 05) can run the live vulture scan and refine `vulture_whitelist.py`; the seed is in place and consumable.
- DEBT-02 `pycopg/` half is complete; the `tests/` half (31 W291/F841/E722 errors) remains for a later plan in this phase.

## Self-Check: PASSED

- FOUND: vulture_whitelist.py
- FOUND: .planning/phases/37-dette-audit/37-01-SUMMARY.md
- FOUND commit: 37bf5c7 (Task 2)
- FOUND commit: 17fe906 (Task 3)

---
*Phase: 37-dette-audit*
*Completed: 2026-06-26*
