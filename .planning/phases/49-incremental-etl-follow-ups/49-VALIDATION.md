---
phase: 49
slug: incremental-etl-follow-ups
status: approved
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-03
---

# Phase 49 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`) |
| **Quick run command** | `PGDATABASE=pycopg_test3 uv run pytest tests/test_etl.py tests/test_parity.py -x -q -o addopts=""` |
| **Full suite command** | `PGDATABASE=pycopg_test3 uv run pytest` |
| **Estimated runtime** | ~90 seconds (full suite) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command (etl + parity)
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green + `mypy --strict` 0 errors + `interrogate` 100% + coverage ≥95%
- **Max feedback latency:** ~90 seconds

---

## Per-Task Verification Map

*Populated during execution. Every task that ships a Pipeline field, SQL builder change, or watermark codec change gets an automated verify row here.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 49-XX-XX | XX | X | ETL-INC-F0X | T-49-XX / — | user values bound `%s`, never interpolated | unit + integration | `PGDATABASE=pycopg_test3 uv run pytest tests/test_etl.py -k <feature> -q -o addopts=""` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] New/extended tests in `tests/test_etl.py` (or a `tests/test_etl_incremental_*.py` sibling) — stubs for ETL-INC-F01..F04
- [ ] Injection test per new builder path: composite tuple-compare, seed floor, lookback, advisory-lock key
- [ ] Parity registration confirmed in `tests/test_parity.py` (`ACCESSOR_PAIRS` already covers `(ETLAccessor, AsyncETLAccessor)` — verify new Pipeline fields need no extra registration)

*Existing pytest infrastructure covers the framework; no install needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Cross-process advisory-lock serialization (`concurrency="wait"`/`"skip"`) | ETL-INC-F04 | Requires two concurrent live DB sessions holding the same session-scoped lock | Integration test opens two connections; session A acquires `pg_advisory_lock(hashtextextended(name,0))`, session B's `pg_try_advisory_lock` returns false while held, then true after A closes |

*All other phase behaviors have automated verification (mock SQL-shape assertions + live-DB integration).*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (confirmed by plan-checker across 49-01..49-05)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (no unresolved MISSING references)
- [x] No watch-mode flags
- [x] Feedback latency < 90s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-07-03 (plan-checker VERIFICATION PASSED)
