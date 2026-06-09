---
phase: 11-parit-sync-async-compl-te
plan: 01
subsystem: database
tags: [sqlalchemy, psycopg, async, config, connection-url]

requires:
  - phase: 10-s-curit-r-siduelle-robustesse
    provides: hardened sync/async connection + session handling
provides:
  - Config.async_url property emitting postgresql+psycopg_async:// driver scheme
  - AsyncDatabase.async_engine wired to the async driver URL (C3 / PAR-06 fix)
affects: [11-03, 11-04, 11-05, async DataFrame operations]

tech-stack:
  added: []
  patterns:
    - "Async driver URL derived from the same config fields as the sync url, differing only in scheme"

key-files:
  created: []
  modified:
    - pycopg/config.py
    - pycopg/async_database.py

key-decisions:
  - "D-04: async_url is a separate property mirroring url exactly except for the +psycopg_async scheme"
  - "D-07: Config.url is left byte-for-byte unchanged (sync +psycopg) — zero sync breaking change"

patterns-established:
  - "Pattern: async engine construction reuses config.async_url; sync engine keeps config.url"

requirements-completed: [PAR-06]

duration: 8min
completed: 2026-06-09
---

# Phase 11 / Plan 01: Async Engine Driver URL Fix Summary

**Async SQLAlchemy engine now builds from the async psycopg driver URL instead of the sync one — closing the C3 driver-mismatch bug.**

## Performance

- **Duration:** ~8 min
- **Completed:** 2026-06-09
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- Added `Config.async_url` property that emits `postgresql+psycopg_async://...`, mirroring `Config.url` exactly (auth, host, port, database, optional `?sslmode=`) but for the async driver (D-04).
- Rewired `AsyncDatabase.async_engine` to `create_async_engine(self.config.async_url)` so async operations use the correct async driver (C3 / PAR-06).
- Left `Config.url` and the sync `engine` property untouched — no sync breaking change (D-07).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add Config.async_url property (D-04)** — `06a9ced` (feat)
2. **Task 2: Rewire async_engine to use config.async_url (C3 / PAR-06)** — `af8156e` (fix)

## Files Created/Modified
- `pycopg/config.py` — added `async_url` property (after `url`); `url` unchanged.
- `pycopg/async_database.py` — `async_engine` now uses `config.async_url`.

## Verification
- `Config(...).async_url == 'postgresql+psycopg_async://u:p@h:5432/d'` ✓
- `Config(...).url == 'postgresql+psycopg://u:p@h:5432/d'` (unchanged) ✓
- `AsyncDatabase(...).async_engine.url` contains `psycopg_async` ✓
- `sslmode` set → `async_url` appends `?sslmode=...` ✓
- `tests/test_config.py`: 42 passed ✓
- ruff: no new errors introduced (3 pre-existing `X | None` findings on file unrelated to this change); black: new `async_url` region conforms.

## Notes / Deviations
- None. Mechanical change exactly as planned.
- Coverage gate (`--cov-fail-under=80`) intentionally not evaluated per-file; full-suite coverage is handled by Plan 11-07.

## Self-Check: PASSED
