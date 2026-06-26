---
phase: 37-dette-audit
plan: 05
subsystem: testing
tags: [code-review, audit, vulture, nyquist, sql-injection, identifier-validation, sync-async-parity, decisions-journal]

# Dependency graph
requires:
  - phase: 37-01
    provides: vulture + pytest-randomly in dev-group; ruff config migrated to [tool.ruff.lint]
  - phase: 37-02
    provides: tests/ ruff-clean baseline (DEBT-04 dead monkeypatches removed)
  - phase: 37-03
    provides: 3 flaky tests root-cause fixed; full suite deterministic under pytest-randomly
  - phase: 37-04
    provides: TableNotFound raise site in truncate_table (DEBT-05); DEBT-03a advisory fixes
provides:
  - 37-REVIEW.md (AUDIT-01 severity-classified report) with a Dispositions section
  - 10 AUDIT-01 fixes applied with full sync/async parity (5 BLOCKERS + 5 warnings); 1 warning deferred
  - 53 regression tests in tests/test_audit_37_fixes.py (one or more per fixed finding)
  - vulture_whitelist.py refined (AUDIT-02 — 13 documented false positives, no dead code)
  - v0.6.0-MILESTONE-AUDIT.md nyquist block flipped partial->compliant for 22-24 (NYQ-01)
  - 37-DECISIONS.md (D-09 consolidated decisions journal)
affects: [phase-38-onwards, v1.0.0-api-freeze]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CLI flag-injection guard: _validate_cli_pattern() rejects '-'-prefixed and control-char values for pg_dump/restore -t/-T/-n patterns (wildcards still allowed)"
    - "libpq options sanitization: _validate_libpq_option() rejects unsafe GUC keys/values before interpolating the options string"
    - "Format whitelist sentinel: module-level _VALID_EXPLAIN_FORMATS set checked case-insensitively before building SQL"
    - "Surviving-authority sign-off: edit the milestone-audit doc (not fabricate per-phase VALIDATION.md) to record retroactive nyquist compliance"

key-files:
  created:
    - tests/test_audit_37_fixes.py
    - .planning/phases/37-dette-audit/37-DECISIONS.md
  modified:
    - pycopg/maint.py
    - pycopg/database.py
    - pycopg/async_database.py
    - pycopg/base.py
    - pycopg/backup.py
    - pycopg/config.py
    - pycopg/__init__.py
    - pycopg/etl.py
    - .planning/phases/37-dette-audit/37-REVIEW.md
    - .planning/milestones/v0.6.0-MILESTONE-AUDIT.md
    - .planning/STATE.md

key-decisions:
  - "D-06 bar applied: 5 BLOCKERS (CR-01..05) + 5 warnings (37-REVIEW:WR-01/02/04/05/06) FIXED in-phase; 37-REVIEW:WR-03 (copy_insert session bypass) DEFERRED to v1.0.0 with justification"
  - "CR-04 nuance: pg_dump -t accepts PATTERNS (wildcards, schema.table) so strict validate_identifier is wrong; minimum guard rejects '-'-prefixed and control-char values only"
  - "WR-04 uses ConfigurationError (exceptions.py has no imports -> no circular dep) not ValueError"
  - "NYQ-01 (D-08): editing v0.6.0-MILESTONE-AUDIT.md IS the legitimate sign-off; fabricating backdated VALIDATION.md for 22-24 rejected as false history"
  - "ID-collision discipline: 37-REVIEW:WR-0x (audit) qualified distinctly from v0.8.0:WR-xx (DEBT-03b) throughout 37-DECISIONS.md"

patterns-established:
  - "Per-finding regression test grouped by audit ID in a single test module (TestCR0x / TestWR0x classes)"
  - "Consolidated decisions journal (D-09) as the single verifier-checkable authority for closures/sign-offs"

requirements-completed: [AUDIT-01, AUDIT-02, NYQ-01, DEBT-03]

# Metrics
duration: 90min
completed: 2026-06-26
---

# Phase 37 Plan 05: Tooled Audit Pass + Consolidated Decisions Journal Summary

**Applied 10 of 11 AUDIT-01 findings with full sync/async parity + 53 regression tests (5 SQL/CLI-injection BLOCKERS hardened, 1 copy_insert session bypass deferred), refined the vulture allowlist (no dead code), retroactively signed off phases 22-24 to nyquist_compliant via the surviving milestone-audit doc, and consolidated every closure into 37-DECISIONS.md (D-09)**

## Performance

- **Duration:** ~90 min (Pass A fixes + Pass B Tasks 3/4/SUMMARY)
- **Started:** 2026-06-26T08:15:00Z
- **Completed:** 2026-06-26T09:45:00Z
- **Tasks:** 4 (Task 1 vulture, Task 2 review+fixes, Task 3 NYQ-01, Task 4 decisions journal)
- **Files modified:** 11 (8 source + 3 planning) + 2 created

## Accomplishments

- **AUDIT-01 (Task 2):** ran `/gsd-code-review` over `pycopg/` -> `37-REVIEW.md` (5 critical / 6 warning / 0 info). Applied the D-06 disposition bar: every HIGH (BLOCKER) fixed in-phase, every MEDIUM (WARNING) fixed in-phase except one deferred-to-v1.0.0 with justification. All 10 fixes carry full sync/async parity and ≥1 regression test each (53 total in `tests/test_audit_37_fixes.py`).
  - **BLOCKERS fixed:** CR-01 (explain() format whitelist), CR-02/CR-03 (from_dataframe/from_geodataframe identifier validation), CR-04 (pg_dump/restore CLI flag-injection guard), CR-05 (pg_restore FileNotFoundError routing).
  - **Warnings fixed:** 37-REVIEW:WR-01 (connection_limit int guard), WR-02 (async stream() session parity), WR-04 (libpq option sanitization), WR-05 (TimescaleError export), WR-06 (_decode_watermark unknown-tag ETLError).
  - **Warning deferred:** 37-REVIEW:WR-03 (copy_insert session bypass) — consistent sync+async semantics; joining db.session() is a behavioral change needing v1.0.0 design review.
- **AUDIT-02 (Task 1):** vulture scan at `--min-confidence 80` found no dead code; 13 false positives documented in `vulture_whitelist.py` (4 public exceptions + 3 CM-protocol params × 4 sites + 1 dotenv stub param).
- **NYQ-01 (Task 3):** spot-checked all 5 v0.6.0 accessor reqs (ADM-01/MNT-01/BKP-01/SCH-01/SCH-02) still hold in v0.9.0; flipped `v0.6.0-MILESTONE-AUDIT.md` nyquist block to `compliant_phases: ["21","22","23","24"]`, `partial_phases: []`, `overall: compliant`. No fabricated VALIDATION.md (D-08 verified).
- **D-09 (Task 4):** created `37-DECISIONS.md` consolidating DEBT-03b closures, AUDIT-01 dispositions, NYQ-01 sign-off, DEBT-05 note, vulture rationale, and the "no new isolation finding from Plan 03" statement; rolled up into STATE.md Deferred Items.

## Task Commits

1. **Task 1: vulture scan + allowlist (AUDIT-02)** - `474d1a0` (chore)
2. **Task 2: AUDIT-01 review + 10 fixes (Pass A)** — committed in logical groups:
   - CR-01 explain() format whitelist - `0321b85` (fix)
   - CR-02/CR-03 from_dataframe/from_geodataframe validation - `1118a60` (fix; includes WR-02 async stream parity)
   - CR-04 CLI flag-injection guard + WR-01 connection_limit guard - `6dc326b` (fix)
   - CR-05 pg_restore FileNotFoundError - `ede7210` (fix)
   - WR-04 libpq option sanitization - `e46ab2d` (fix)
   - WR-05 TimescaleError export - `b9bed80` (fix)
   - WR-06 _decode_watermark ETLError - `a081b0e` (fix)
3. **Task 3: NYQ-01 promote 22-24 to nyquist_compliant** - `18a958f` (docs)
4. **Task 4 + SUMMARY: 37-DECISIONS.md (D-09) + 37-REVIEW dispositions + STATE roll-up + SUMMARY** - committed as the plan-completion commit below.

**Plan metadata:** see plan-completion commit (`docs(37-05): complete tooled audit pass + consolidated decisions journal`).

_Note: Pass A (the 10 fixes, 8 commits) and Pass B (Tasks 3/4/SUMMARY) were run as two sequential passes on main per the coordinator split._

## Files Created/Modified

**Source (8, all sync/async parity):**
- `pycopg/maint.py` — CR-01 `_VALID_EXPLAIN_FORMATS` + format whitelist in both explain() methods
- `pycopg/database.py` — CR-02/CR-03 `validate_identifiers` in from_dataframe/from_geodataframe
- `pycopg/async_database.py` — CR-02/CR-03 async twins + WR-02 stream() switched to session-aware cursor()
- `pycopg/base.py` — CR-04 `_validate_cli_pattern()` for pg_dump/restore; WR-01 connection_limit int guard
- `pycopg/backup.py` — CR-05 FileNotFoundError routing (sync + async pg_restore)
- `pycopg/config.py` — WR-04 `_validate_libpq_option()` in dsn + connect_params
- `pycopg/__init__.py` — WR-05 TimescaleError in import block + `__all__`
- `pycopg/etl.py` — WR-06 _decode_watermark raises ETLError for unknown tags

**Tests (1 created):**
- `tests/test_audit_37_fixes.py` — 53 regression tests across 10 TestCR0x/TestWR0x classes

**Planning (3 + 1 created):**
- `.planning/phases/37-dette-audit/37-REVIEW.md` — status -> dispositioned; Dispositions section added
- `.planning/phases/37-dette-audit/37-DECISIONS.md` (NEW) — D-09 consolidated journal
- `.planning/milestones/v0.6.0-MILESTONE-AUDIT.md` — nyquist block + body flipped to compliant
- `.planning/STATE.md` — Deferred Items roll-up referencing 37-DECISIONS.md

## Decisions Made

1. **CR-04 pattern-vs-identifier nuance:** pg_dump `-t` accepts shell-glob PATTERNS and `schema.table` forms, so applying strict `validate_identifier` would break legitimate usage. The guard rejects only `-`-prefixed values (flag injection) and control characters — the minimum that closes the injection surface while preserving pattern support.
2. **WR-04 exception choice:** used `ConfigurationError` (not `ValueError`); `pycopg/exceptions.py` has no imports so importing it into `config.py` introduces no circular dependency.
3. **NYQ-01 sign-off mechanism (D-08):** edited the surviving `v0.6.0-MILESTONE-AUDIT.md` rather than fabricating backdated per-phase VALIDATION.md files — the latter would be false history. The milestone audit IS the authoritative nyquist record for the milestone.
4. **37-REVIEW:WR-03 deferral:** `copy_insert()` opens its own connection in BOTH sync and async (consistent), so COPY-as-its-own-transaction is the current intentional semantics; making it join `db.session()` is a behavioral/atomicity change requiring design review — deferred to v1.0.0.

## Deviations from Plan

None of the Rule 1-4 auto-deviation kind. Two structural notes:

- **Plan/coordinator split:** the coordinator split Plan 05 execution into Pass A (the 10 audit fixes) and Pass B (Tasks 3/4 + SUMMARY). This SUMMARY documents both. Task 2's human checkpoint was APPROVED before Pass B began.
- **WR-02 commit grouping:** the async `stream()` session-parity fix (37-REVIEW:WR-02) landed inside the CR-02/CR-03 commit `1118a60` because all `async_database.py` edits were staged together; the change is intact and tested (`TestWR02AsyncStreamSessionParity`).

---

**Total deviations:** 0 auto-fixed deviations (the 10 fixes ARE the planned Task 2 work).
**Impact on plan:** plan executed as specified under the approved dispositions; no scope creep.

## Issues Encountered

- **CR-03 test mocking:** `db.schema` is a read-only lazy property, so tests inject the mock via the backing `db._schema` cache (with a `spec=SchemaAccessor`/`AsyncSchemaAccessor` mock) rather than assigning `db.schema`. Resolved; all 4 CR-03 tests pass.
- **3 pre-existing PostGIS-env failures** in `tests/test_postgis_errors.py` remain (PostGIS absent in `pycopg_test2`) — pre-existing, environment-specific, logged in 37-DECISIONS.md §6. Not introduced by this plan.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 37 dette/audit work is complete: ruff 0, full suite green except the 3 known PostGIS-env failures, AUDIT-01 dispositioned, AUDIT-02 allowlist clean, NYQ-01 signed off, D-09 journal written.
- v1.0.0 API-freeze carries the deferred behavioral items: 37-REVIEW:WR-03 (copy_insert session semantics), v0.8.0:WR-03 (INTERVAL `%s`), `%`-in-structural-SQL UX, IN-03 chunk_seq helper — all justified in 37-DECISIONS.md.
- Phase 38 (PERF) can proceed on this hardened, ruff-clean baseline.

## Self-Check

- [x] `tests/test_audit_37_fixes.py` exists (53 tests)
- [x] `.planning/phases/37-dette-audit/37-DECISIONS.md` exists (D-09, all 6 sections)
- [x] `.planning/phases/37-dette-audit/37-05-SUMMARY.md` exists
- [x] Commits 0321b85, 1118a60, 6dc326b, ede7210, e46ab2d, b9bed80, a081b0e (fixes) + 18a958f (NYQ-01) all present
- [x] `v0.6.0-MILESTONE-AUDIT.md` nyquist `overall: compliant`, 22-24 in compliant_phases
- [x] STATE.md Deferred Items references 37-DECISIONS.md

## Self-Check: PASSED

---
*Phase: 37-dette-audit*
*Completed: 2026-06-26*
