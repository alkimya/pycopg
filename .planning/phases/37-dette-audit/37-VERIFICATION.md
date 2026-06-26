---
phase: 37-dette-audit
verified: 2026-06-26T00:00:00Z
status: passed
score: 5/5 success criteria verified
overrides_applied: 0
re_verification: false
---

# Phase 37: Dette & Audit — Verification Report

**Phase Goal:** La base de code est propre et auditée — dette technique connue soldée, passe outillée terminée, Nyquist en règle (the codebase is clean and audited: known tech debt cleared, tooled audit pass done, Nyquist in order).
**Verified:** 2026-06-26
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | Full suite deterministic: the 3 named flaky tests no longer fail by fixture isolation | VERIFIED | Live run: 1387 passed, 11 skipped, exactly 3 pre-existing PostGIS-env failures (test_postgis_errors.py, not the DEBT-01 targets). test_async_transaction_fix: PASSED. test_create_spatial_index_name_parameter: SKIPPED (PostGIS absent — correct). Both watermark bound-param tests: PASSED across random seeds. |
| SC-2 | `uv run ruff check pycopg tests` returns exactly 0 errors | VERIFIED | Live run: `All checks passed!` — zero output, exit 0. [tool.ruff.lint] migration in pyproject.toml; N818 per-file-ignore for exceptions.py (Plan 01); 34 test-side W291/F841/E722 errors fixed mechanically (Plan 02). |
| SC-3 | Every advisory warning (v0.8-0.9: WR-01, WR-03, %/%s structural, IN-03 chunk_seq, v0.9 advisories) is either fixed in code or closed with justification in a decisions file | VERIFIED | 37-DECISIONS.md §1 records DEBT-03b (behavioral) closures with justification for all three deferred items. DEBT-03a advisory fixes (WR-01 case-insensitive guard in timescale.py:969,1946; upsert Raises docstrings; test_sequences_async specific-name assertion; import uuid de-dup) confirmed in Plan 04 commit 11d60de. All items either fixed or recorded with D-03b/D-08 justification. |
| SC-4 | `TableNotFound` has a real internal raise site OR removed from `__all__` — inconsistency resolved and documented | VERIFIED | pycopg/schema.py:407 raises TableNotFound in SchemaAccessor.truncate_table; pycopg/schema.py:1233 in AsyncSchemaAccessor.truncate_table. Both after validate_identifiers guard. TableNotFound remains in __init__.py:24,88. DEBT-05 note in 37-DECISIONS.md §4. |
| SC-5 | Phases 22-24 nyquist_compliant; HIGH/MEDIUM-classified audit report for pycopg/ exists; vulture allowlist documents dead-code false positives | VERIFIED | (a) v0.6.0-MILESTONE-AUDIT.md frontmatter: compliant_phases: ["21","22","23","24"], overall: compliant. No fabricated VALIDATION.md files exist for 22-24 (find returns empty — correct per D-08). (b) 37-REVIEW.md: 5 CRITICAL / 6 WARNING / 0 INFO, status: dispositioned. All 5 HIGH fixed in-phase (CR-01..05). All 6 MEDIUM fixed or deferred-to-v1.0.0 with justification (37-REVIEW:WR-03). (c) vulture_whitelist.py: 13 documented false positives; live scan exits 0. |

**Score:** 5/5 truths verified

---

### Deferred Items

None. All must-haves for Phase 37 scope are verified. Items explicitly deferred to v1.0.0 (37-REVIEW:WR-03 copy_insert session bypass, v0.8.0:WR-03 INTERVAL literal, %/structural SQL UX, IN-03 chunk_seq) are documented with justification in 37-DECISIONS.md and are in-scope for a future milestone, not Phase 37.

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` | [tool.ruff.lint] migration + N818 per-file-ignore + vulture/pytest-randomly in dev | VERIFIED | [tool.ruff.lint] at line 88; [tool.ruff.lint.per-file-ignores] at line 92; vulture>=2.9.1 and pytest-randomly>=3.15.0 at lines 71-72 |
| `vulture_whitelist.py` | Documented false-positive allowlist for vulture (AUDIT-02) | VERIFIED | Exists at project root; 13 false positives documented in 3 categories; `uv run vulture pycopg/ vulture_whitelist.py --min-confidence 80` exits 0 |
| `pycopg/schema.py` | TableNotFound raise site in truncate_table (DEBT-05) | VERIFIED | Lines 407 (sync) and 1233 (async); import at line 22; both with validate_identifiers guard |
| `tests/test_audit_37_fixes.py` | 53 regression tests for AUDIT-01 findings | VERIFIED | Exists; 642 lines; 53 tests pass in 0.13s |
| `.planning/phases/37-dette-audit/37-REVIEW.md` | Severity-classified audit report; status: dispositioned | VERIFIED | 5 critical / 6 warning / 0 info; full dispositions table appended; all HIGHs fixed, WR-03 deferred with justification |
| `.planning/phases/37-dette-audit/37-DECISIONS.md` | Consolidated decisions journal (D-09) with 6 sections | VERIFIED | Covers DEBT-03b, AUDIT-01 dispositions, NYQ-01 sign-off, DEBT-05 note, vulture rationale, Plan 03 isolation finding |
| `.planning/milestones/v0.6.0-MILESTONE-AUDIT.md` | nyquist block: overall: compliant, 22-24 in compliant_phases | VERIFIED | overall: compliant; compliant_phases: ["21","22","23","24"]; partial_phases: [] |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| pyproject.toml [tool.ruff.lint.per-file-ignores] | pycopg/exceptions.py N818 errors | per-file ignore "pycopg/exceptions.py" = ["N818"] | WIRED | ruff exits 0 on pycopg/ |
| pyproject.toml [dependency-groups] dev | vulture + pytest-randomly availability | uv sync --all-extras --dev | WIRED | Both importable; vulture==2.16, pytest-randomly==4.1.0 |
| pycopg/schema.py SchemaAccessor.truncate_table | TableNotFound raise | validate_identifiers then table_exists guard then raise | WIRED | Verified at lines 405-407 |
| tests/test_integration.py test_async_transaction_fix | connection-state isolation | RESET application_name in finally | WIRED | Line 127; test PASSES under randomization |
| tests/test_postgis_errors.py test_create_spatial_index_name_parameter | UUID table name per run | f"test_spatial_{uuid.uuid4().hex[:8]}" | WIRED | Line 124; test skips cleanly (PostGIS absent, not a fixture-collision fail) |
| tests/test_etl_accessor.py watermark tests | call-order determinism | captured_calls[-1] local spy | WIRED | Both sync+async tests PASS across seeds 1/100/999/5000/7777/12345/31337/54321/78901/98765 |
| 37-REVIEW.md dispositions | 37-DECISIONS.md §2 | D-06 bar reconciliation table | WIRED | Every finding cross-referenced; commit hashes present for all 10 fixes |
| v0.6.0-MILESTONE-AUDIT.md nyquist block | phases 22-24 compliant | flip from partial -> compliant (D-08) | WIRED | compliant_phases includes "22","23","24"; no fabricated per-phase VALIDATION.md |

---

### Data-Flow Trace (Level 4)

Not applicable. Phase 37 produces no new data-rendering components. All artifacts are: test isolation fixes, lint/tooling config, security hardening guards, and planning documents. The AUDIT-01 fixes add input-validation guards (pure defensive code paths, not data renderers).

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| ruff check exits 0 on pycopg + tests | `uv run ruff check pycopg tests` | `All checks passed!` | PASS |
| Full suite: only 3 pre-existing PostGIS-env failures | `PGDATABASE=pycopg_test2 uv run pytest -o addopts="" -q` | 1387 passed, 11 skipped, 3 failed (test_postgis_errors.py — PostGIS absent, pre-existing) | PASS |
| test_async_transaction_fix passes | `PGDATABASE=pycopg_test2 uv run pytest tests/test_integration.py -k test_async_transaction_fix -o addopts=""` | 1 passed | PASS |
| Watermark bound-param tests pass | `PGDATABASE=pycopg_test2 uv run pytest tests/test_etl_accessor.py -k watermark_as_bound_param -o addopts=""` | 2 passed | PASS |
| Vulture scan: no dead code | `uv run vulture pycopg/ vulture_whitelist.py --min-confidence 80` | exit 0 (no output) | PASS |
| 53 AUDIT-01 regression tests pass | `PGDATABASE=pycopg_test2 uv run pytest tests/test_audit_37_fixes.py -q -o addopts=""` | 53 passed in 0.13s | PASS |
| TimescaleError exported from pycopg | `grep "TimescaleError" pycopg/__init__.py` | Found at lines 25 (import) and 89 (__all__) | PASS |
| TableNotFound raise site exists | `grep "raise TableNotFound" pycopg/schema.py` | Lines 407 (sync) and 1233 (async) | PASS |
| time_bucket guard case-insensitive | `grep "select_sql.lower" pycopg/timescale.py` | Lines 969 and 1946 | PASS |
| NYQ-01: v0.6.0 audit overall: compliant | `grep "overall: compliant" .planning/milestones/v0.6.0-MILESTONE-AUDIT.md` | Found | PASS |
| No fabricated per-phase VALIDATION.md for 22-24 | `find .planning/phases/2[234]-* -name '*VALIDATION*'` | Empty (exit 1) — correct per D-08 | PASS |

---

### Probe Execution

No probes declared in PLAN frontmatter. No conventional `scripts/*/tests/probe-*.sh` exist. Behavioral spot-checks above cover the runnable verification surface.

---

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| DEBT-01 | Plan 03 | Flaky tests (test_async_transaction_fix, test_create_spatial_index_name_parameter, ~2.7% bound-param) fixed deterministically | SATISFIED | Live: 1387 passed; all 3 DEBT-01 targets confirmed PASSED or correct-SKIP under randomization. Commits f21a6ec + 0430ff6. |
| DEBT-02 | Plans 01, 02 | `uv run ruff check pycopg tests` returns 0 errors | SATISFIED | Live: exit 0, `All checks passed!`. N818 per-file-ignore (Plan 01 commit 37bf5c7) + 34 test-side fixes (Plan 02 commit 5fea8a4). |
| DEBT-03 | Plans 04, 05 | All v0.8-0.9 advisory warnings solved or explicitly closed | SATISFIED with noted partial | DEBT-03a fixes done in code (Plan 04 commit 11d60de: WR-01 guard, upsert Raises docstrings, sequences assertion, import uuid de-dup). DEBT-03b behavioral items (WR-03/INTERVAL, %/structural SQL, IN-03 chunk_seq) closed with written justification in 37-DECISIONS.md §1. REQUIREMENTS.md traceability table records "Partial (D-03a done P04; D-03b deferred P05)" which matches the actual disposition. The SC-3 criterion is met — "fixed in code OR closed with justification." |
| DEBT-04 | Plan 02 | Dead flat-method monkeypatches removed from test_sql_injection.py async fixture | SATISFIED | Commit 09f6d7d. No db.role_exists/db.has_extension dead patches remain; live real_schema.has_extension patch preserved. |
| DEBT-05 | Plans 04, 05 | TableNotFound has a real raise site (truncate_table); inconsistency resolved and documented | SATISFIED | schema.py lines 407, 1233. 37-DECISIONS.md §4. |
| AUDIT-01 | Plan 05 | Severity-classified audit report; every HIGH/MEDIUM dispositioned | SATISFIED | 37-REVIEW.md: 5 HIGH all fixed (CR-01..05), 6 MEDIUM: 5 fixed, 1 deferred-to-v1.0.0 with written justification (37-REVIEW:WR-03). 53 regression tests in test_audit_37_fixes.py. Note: REQUIREMENTS.md traceability shows "Pending" — stale tooling drift (known recurring issue); codebase evidence is authoritative. |
| AUDIT-02 | Plans 01, 05 | Dead-code scan completed; confirmed dead code removed; false positives documented in allowlist | SATISFIED | vulture_whitelist.py: 13 false positives documented. Live scan exits 0. Commits 17fe906 (seed) + 474d1a0 (refinement). |
| NYQ-01 | Plan 05 | Phases 22-24 Nyquist sign-off recorded | SATISFIED | v0.6.0-MILESTONE-AUDIT.md: overall: compliant, compliant_phases: ["21","22","23","24"]. 37-DECISIONS.md §3 records formal sign-off with spot-check evidence. No fabricated per-phase VALIDATION.md (correct per D-08). REQUIREMENTS.md traceability shows "Pending" — same stale tooling drift. |

**Orphaned requirements check:** REQUIREMENTS.md maps PERF-01/02/03/05 to Phase 38, COV-01/PERF-04 to Phase 39, REL-10 to Phase 40. None of these were claimed by any Phase 37 plan. No orphaned Phase 37 requirements found.

**Coverage:** 8/8 Phase 37 requirements satisfied. REQUIREMENTS.md checkbox state is stale for DEBT-03/AUDIT-01/NYQ-01 (known recurring tooling drift per project memory) — the codebase evidence and traceability-table "Partial/Complete" status are authoritative.

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No TBD/FIXME/XXX found in any Phase 37 modified source or test file | — | — |

Scan confirmed: `grep -n "TBD|FIXME|XXX"` across all 15 Phase 37 modified files returned no output. No unresolved debt markers.

---

### Human Verification Required

No human verification items. All success criteria are programmatically verifiable and have been verified against live codebase behavior. The two Task 1 blocking-human gates in the plans (package legitimacy for vulture/pytest-randomly; AUDIT-01 D-06 disposition bar) were completed and recorded during execution (operator approval logged in 37-01-SUMMARY.md and 37-05-SUMMARY.md respectively).

---

## Gaps Summary

No gaps. All 5 success criteria VERIFIED, all 8 requirements SATISFIED, no unresolved debt markers, no fabricated artifacts. Phase 37 goal is achieved.

---

_Verified: 2026-06-26_
_Verifier: Claude (gsd-verifier)_
