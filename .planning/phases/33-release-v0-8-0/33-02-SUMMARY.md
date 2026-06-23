---
phase: 33-release-v0-8-0
plan: "02"
subsystem: docs
tags: [docs, timescaledb, release, v0.8.0]
dependency_graph:
  requires: ["33-01"]
  provides: ["docs coverage for 9 new TimescaleDB methods", "REL-08 docs surfaces"]
  affects: ["docs/timescaledb.md", "docs/api-reference.md", "README.md"]
tech_stack:
  added: []
  patterns: ["rewrite-in-place doc sections", "D-10 scope-fence grep"]
key_files:
  created: []
  modified:
    - docs/timescaledb.md
    - docs/api-reference.md
    - README.md
decisions:
  - "D-05: Three raw-SQL sections rewritten to db.timescale.* first-class calls; Advanced Chunk & Dimension Management section added in-place"
  - "D-06: api-reference.md TimescaleDB Methods table extended from 6 to 15 rows (9 new)"
  - "D-07: README accessor row updated to (15 methods); compact highlights block added with 4 new methods + RTD pointer"
  - "D-14: Community/TSL license note added in the Advanced section for gapfill and cagg methods"
  - "D-10: All three docs files pass scope-fence grep with zero banned deferred-capability keywords"
metrics:
  duration: "~6 minutes"
  completed: "2026-06-23T16:35:00Z"
  tasks_completed: 3
  files_modified: 3
---

# Phase 33 Plan 02: Documentation Rewrite Summary

**One-liner:** Rewrote timescaledb.md raw-SQL blocks to first-class `db.timescale.*` calls, added Advanced Chunk & Dimension Management section, extended api-reference.md with 9 new method rows, and bumped README to (15 methods) with compact v0.8.0 highlights.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Rewrite timescaledb.md sections + add Advanced section | f6b7817 | docs/timescaledb.md |
| 2 | Extend api-reference.md TimescaleDB Methods table with 9 rows | 3df42cd | docs/api-reference.md |
| 3 | Update README accessor count + compact highlights | a77cd77 | README.md |

## What Was Built

### Task 1 — docs/timescaledb.md

- **Time Bucketing** section rewritten from raw `db.execute("""SELECT time_bucket...""")` to `db.timescale.time_bucket("events", "time", "1 hour", aggregates=..., into="df")` with a note on structural SQL safety.
- **Gap Filling** section rewritten from raw `db.execute("""SELECT time_bucket_gapfill...""")` to `db.timescale.time_bucket_gapfill(..., start=..., finish=..., aggregates="device_id, locf(AVG(temperature)) AS temperature")` with the explicit `start`/`finish` requirement documented.
- **Continuous Aggregates** section rewritten from raw `db.execute("""CREATE MATERIALIZED VIEW...""")` to `db.timescale.create_continuous_aggregate(...)` + `db.timescale.refresh_continuous_aggregate(...)` + `db.timescale.add_continuous_aggregate_policy(...)`.
- **New `## Advanced Chunk & Dimension Management` section** with:
  - `show_chunks` — listing chunks with `older_than`/`newer_than` (str or datetime).
  - `drop_chunks` — DESTRUCTIVE/IRREVERSIBLE warning, `dry_run=True` preview, both-`None` `ValueError` documented.
  - `add_dimension` — hash/range partition, `number_partitions`/`chunk_interval` mutual-exclusivity.
  - `add_reorder_policy` — index-based reorder.
  - Community/TSL license note (D-14) for `time_bucket_gapfill` and cagg methods.

### Task 2 — docs/api-reference.md

- 9 new rows appended to the `### TimescaleDB Methods` table (lines after `hypertable_info`):
  - `show_chunks`, `drop_chunks`, `add_dimension`, `add_reorder_policy`
  - `create_continuous_aggregate`, `refresh_continuous_aggregate`, `add_continuous_aggregate_policy`
  - `time_bucket`, `time_bucket_gapfill` (with `DataFrame | list[dict]` return type)
- All 6 original rows preserved; Spatial Helpers table untouched.
- Table now has 15 rows total (6 original + 9 new).

### Task 3 — README.md

- `db.timescale.*` accessor row updated from `(6 methods)` to `(15 methods)` with example names updated to include `time_bucket` and `show_chunks`.
- New **v0.8.0 Highlights** compact block added after the existing TimescaleDB example, showing:
  - `db.timescale.time_bucket(...)` with `into="df"` (DataFrame return).
  - `db.timescale.show_chunks(...)` and `db.timescale.drop_chunks(..., dry_run=True)` operational pair.
  - `db.timescale.create_continuous_aggregate(...)` + `add_continuous_aggregate_policy(...)` lifecycle.
- Pointer to RTD `timescaledb.html` advanced guide added.
- All 4 target methods (`time_bucket`, `show_chunks`, `drop_chunks`, `create_continuous_aggregate`) appear in the highlights block.

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

- `docs/timescaledb.md`: all 9 method names present, `## Advanced Chunk & Dimension Management` heading present, `Community` and `FeatureNotSupported` present (D-14), `drop_chunks` text mentions `dry_run` and `ValueError`, D-10 scope-fence clean.
- `docs/api-reference.md`: 9 new rows + 6 original all present in `### TimescaleDB Methods` table, Spatial table diff shows no change.
- `README.md`: `(15 methods)` present, `(6 methods)` absent from `db.timescale.*` row, 4/4 highlight methods present, D-10 scope-fence clean.
- Task 1 automated verify: `OK`.
- Task 2 automated verify: `OK`.
- Task 3 automated verify: `OK (count=4)`.

## Known Stubs

None. All documentation is grounded in already-shipped methods in `pycopg/timescale.py`.

## Threat Flags

None. Documentation-only edits; no new network surface, no new code paths.

## Self-Check: PASSED

- `docs/timescaledb.md` — FOUND (modified in commit f6b7817)
- `docs/api-reference.md` — FOUND (modified in commit 3df42cd)
- `README.md` — FOUND (modified in commit a77cd77)
- Commits f6b7817, 3df42cd, a77cd77 — all present in git log
