---
phase: 09-migration-uv-outillage-projet
plan: "04"
subsystem: contributor-docs
tags: [docs, makefile, uv, TOOL-05]
dependency_graph:
  requires: ["09-01"]
  provides: [TOOL-05]
  affects: [contributor-onboarding, docs]
tech_stack:
  added: []
  patterns: [uv-thin-wrapper-makefile, user-contributor-doc-boundary]
key_files:
  created:
    - Makefile
  modified:
    - README.md
    - CLAUDE.md  # gitignored — modified on disk, not tracked in git
decisions:
  - "D-08: Contributor doc artifacts = CLAUDE.md + README Development section + Makefile"
  - "D-09: CLAUDE.md: stale path solaris/pycopg removed; v0.2.0 → v0.3.1; pip commands → uv"
  - "D-10: Makefile with five thin uv wrapper targets (install/test/lint/format/build)"
  - "D-11: README Installation (pip) preserved exactly; Development section (uv) added before Quick Start"
  - "D-12: CLAUDE.md pycopg/venv/ rule mention left as-is (not forcibly removed); no new activation commands added"
metrics:
  duration: "1m 43s"
  completed: "2026-06-06T18:58:36Z"
  tasks_completed: 3
  files_changed: 3
---

# Phase 09 Plan 04: Contributor Documentation (uv) Summary

Migrated all contributor-facing documentation to uv toolchain. Created `Makefile` with thin uv wrappers, updated `CLAUDE.md` with correct path/version/commands, and added a `## Development` section to `README.md` while keeping the user-facing `## Installation` section on `pip install pycopg` unchanged.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Create Makefile with thin uv wrapper targets | 1d6437c | Makefile (created) |
| 2 | Rewrite CLAUDE.md contributor commands to uv | (disk only — gitignored) | CLAUDE.md |
| 3 | Add README Development section (keep pip Installation) | 34b32d8 | README.md |

## Artifacts

### Makefile (created)

Five `.PHONY` targets delegating to uv:
- `install` → `uv sync --all-extras --dev`
- `test` → `uv run pytest`
- `lint` → `uv run ruff check pycopg tests`
- `format` → `uv run black pycopg tests` + `uv run ruff check --fix pycopg tests`
- `build` → `uv build`

TAB-indented recipe lines (Make requirement). `make -n install test lint format build` exits 0.

### CLAUDE.md (modified on disk)

- Version bumped: `v0.2.0` → `v0.3.1`
- Stale path removed: `solaris/pycopg` → `/home/loc/workspace/pycopg` (no venv activation)
- Commands replaced: `pip install -e ".[all,dev]"` → `uv sync --all-extras --dev`
- Added: `uv run pytest tests/ -x -q` (quick), `uv run pytest` (full), `uv run ruff check`, `uv run black`
- No `pip install pycopg[dev]` remains (Pitfall 4 guard)

### README.md (modified)

- Added `## Development` section between `## Installation` and `## Quick Start`
- Contributor commands: clone → `uv sync --all-extras --dev` → pytest / ruff / black / uv build
- Link to https://docs.astral.sh/uv/
- `## Installation` section preserved exactly: `pip install pycopg` / `[dotenv]` / `[geo]` / `[all]`
- Hard user/contributor boundary maintained

## Deviations from Plan

### Auto-noted: CLAUDE.md is gitignored

**Found during:** Task 2

**Issue:** `CLAUDE.md` is listed in `.gitignore` (line 67: `CLAUDE.md`) and has never been tracked in git. `git add CLAUDE.md` fails with "path is ignored by .gitignore".

**Fix:** The file was successfully modified on disk with all required changes. The modification satisfies the plan's deliverable. Force-adding a gitignored file (`git add -f`) was intentionally avoided — the gitignore rule is a deliberate user choice to keep Claude-specific files out of project history.

**Impact:** CLAUDE.md changes are functional (on disk, readable by Claude, usable by contributors) but not tracked in git history. This is the expected behavior per the project's `.gitignore` convention.

**No other deviations.** All other plan instructions executed exactly as written.

## Verification Results

All success criteria verified:

```
grep -c 'solaris/pycopg' CLAUDE.md    → 0         PASS
! grep -q 'pip install -e' CLAUDE.md  →            PASS
grep -q '## Development' README.md    →            PASS
make -n install test lint format build → exit 0   PASS
grep -q 'pip install pycopg' README.md →           PASS
! grep -q 'pip install pycopg[dev]'   →            PASS (both files)
grep -q 'v0.3.1' CLAUDE.md            →            PASS
! grep -q 'v0.2.0' CLAUDE.md          →            PASS
```

## Known Stubs

None. All files contain real commands that delegate to functional uv targets established by plan 09-01.

## Threat Flags

No new network endpoints, auth paths, file access patterns, or schema changes introduced. Docs-only changes. No new threat surface beyond what was declared in the plan's `<threat_model>`.

T-09-DOC (stale-instruction tampering): mitigated — grep gates confirmed no `pip install pycopg[dev]`, no `pip install -e`, no `solaris/pycopg` in any contributor doc.

T-09-DOC-BND (user/contributor boundary): mitigated — `pip install pycopg` in Installation; `uv sync` in Development; no mixing.

## Self-Check: PASSED

- Makefile exists: `test -f Makefile` → PASS
- Makefile commit 1d6437c exists: `git log --oneline` → PASS
- README.md commit 34b32d8 exists: `git log --oneline` → PASS
- CLAUDE.md on disk: modified with uv commands, no stale content → PASS
