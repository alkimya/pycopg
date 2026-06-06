---
phase: 09-migration-uv-outillage-projet
plan: "01"
subsystem: tooling
tags: [uv, pep735, dependency-groups, lockfile, pyproject]
dependency_graph:
  requires: []
  provides: [uv.lock, .python-version, "[dependency-groups].dev in pyproject.toml"]
  affects: [pyproject.toml, uv.lock, .python-version]
tech_stack:
  added: [uv, PEP 735 dependency-groups]
  patterns: [uv sync --all-extras --dev, uv lock, uv python pin]
key_files:
  created: [uv.lock, .python-version]
  modified: [pyproject.toml]
decisions:
  - "Deleted [project.optional-dependencies].dev entirely (D-02: no dual source of truth)"
  - "Added [dependency-groups].dev with same 5 tools and exact version specifiers"
  - "No [tool.uv] section added (Claude's Discretion, Open Question 3)"
  - "Python pinned to 3.12 to match RTD build and publish.yml"
metrics:
  duration: "~10 minutes"
  completed: "2026-06-06"
  tasks_completed: 3
  files_modified: 3
---

# Phase 09 Plan 01: pyproject.toml uv Migration + Lockfile Generation Summary

Migrated dev dependencies from `[project.optional-dependencies].dev` (published extra) to PEP 735 `[dependency-groups].dev` (local-only), generated `uv.lock` and `.python-version` — enabling one-command contributor setup via `uv sync --all-extras --dev`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Package legitimacy gate (auto-approved) | N/A | pyproject.toml (read-only verification) |
| 2 | Migrate pyproject.toml to PEP 735 [dependency-groups].dev | b5183e9 | pyproject.toml |
| 3 | Generate and commit uv.lock and .python-version | 62315a6 | uv.lock, .python-version |

## What Was Built

**pyproject.toml migration (Task 2):**
- Deleted the `dev = [...]` entry from `[project.optional-dependencies]` (D-02: clean removal, no dual source of truth)
- Added new top-level `[dependency-groups]` table with `dev` key containing the same 5 tools: `pytest>=7.0.0`, `pytest-cov>=4.0.0`, `pytest-asyncio>=0.23.0`, `black>=23.0.0`, `ruff>=0.1.0`
- User-facing extras (`dotenv`, `geo`, `timescale`, `all`) unchanged in `[project.optional-dependencies]`
- Coverage gate (`--cov-fail-under=70`), hatchling backend, all `[tool.*]` sections preserved exactly

**Lockfile artifacts (Task 3):**
- `uv python pin 3.12` created `.python-version` with content `3.12`
- `uv lock` resolved 36 packages into `uv.lock` (universal cross-platform lockfile)
- `uv sync --locked` exits 0 (lockfile is fresh)
- `uv sync --all-extras --dev` exits 0 and creates `.venv/` — full contributor environment (TOOL-01/D-03)

## Verification Results

All 7 verification checks passed:

| Check | Command | Result |
|-------|---------|--------|
| [dependency-groups] exists | `grep -q '^\[dependency-groups\]' pyproject.toml` | PASS |
| No dev= in optional-dependencies | `awk` slice check | PASS |
| Coverage gate intact | `grep -q -- '--cov-fail-under=70' pyproject.toml` | PASS |
| .python-version contains 3.12 | `cat .python-version` | PASS |
| uv.lock committed | `git ls-files uv.lock` | PASS |
| uv sync --locked exits 0 | `uv sync --locked` | PASS |
| uv sync --all-extras --dev exits 0 | `uv sync --all-extras --dev` | PASS |

## Requirements Satisfied

| Req ID | Description | Status |
|--------|-------------|--------|
| TOOL-01 | `uv sync --all-extras --dev` provisions full dev env | DONE |
| TOOL-02 | `uv.lock` and `.python-version` committed; `uv sync --locked` succeeds | DONE |

## Deviations from Plan

None — plan executed exactly as written.

Task 1 was auto-approved per orchestrator instructions: all five packages (pytest, pytest-cov, pytest-asyncio, black, ruff) were already present in the `[project.optional-dependencies].dev` block at lines 61-67. No new packages were introduced.

## Threat Surface Scan

No new network endpoints, auth paths, file access patterns, or schema changes introduced. The `uv lock` operation fetches package metadata from PyPI (trust boundary T-09-SC), mitigated by the Task 1 legitimacy gate confirming all five packages are industry-standard tools. The `uv.lock` pins exact versions and hashes after resolution.

## Known Stubs

None — no stub patterns detected in modified files.

## Self-Check

Files exist check:
- pyproject.toml: EXISTS (modified)
- uv.lock: EXISTS (created, 200KB, 36 packages)
- .python-version: EXISTS (content: `3.12`)

Commits exist check:
- b5183e9 (Task 2: pyproject.toml migration): EXISTS
- 62315a6 (Task 3: uv.lock + .python-version): EXISTS

## Self-Check: PASSED
