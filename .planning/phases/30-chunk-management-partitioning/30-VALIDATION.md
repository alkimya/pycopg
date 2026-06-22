---
phase: 30
slug: chunk-management-partitioning
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-22
---

# Phase 30 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `30-RESEARCH.md` §"Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (+ pytest-asyncio, `asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml` (coverage ratchet gate ≥94%) |
| **Quick run command** | `uv run pytest tests/test_timescale.py -x -q` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~60–120 seconds (full suite) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_timescale.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/test_timescale.py tests/test_parity.py -q`
- **Before `/gsd-verify-work`:** Full `uv run pytest` green + coverage ratchet ≥94% held
- **Max feedback latency:** ~120 seconds

---

## Per-Task Verification Map

| Req ID | Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|--------|----------|------------|-----------------|-----------|-------------------|-------------|--------|
| TS-ADV-04 | `show_chunks` oldest-first, fully-qualified `list[str]`; `older_than`/`newer_than` filter | — | identifiers via `validate_identifiers`; bounds bound as `%s`/`%s::interval` (no raw interpolation of values) | unit (mock SQL) + integration (live) | `uv run pytest tests/test_timescale.py -k show_chunks` | ❌ W0 (new file) | ⬜ pending |
| TS-ADV-05 | `drop_chunks` dry_run preview + both-None `ValueError` before round-trip; DESTRUCTIVE | — | both-None guard prevents full-table wipe; `dry_run` short-circuits before drop | unit + integration | `uv run pytest tests/test_timescale.py -k drop_chunks` | ❌ W0 | ⬜ pending |
| TS-ADV-08 | `add_dimension` `by_hash`/`by_range`; construction `ValueError` on type/param mismatch; dup-dimension → `TimescaleError` (D-08 reshaped) | — | construction-time `ValueError` before round-trip; identifiers validated; dup-dim wrapped | unit + integration | `uv run pytest tests/test_timescale.py -k add_dimension` | ❌ W0 | ⬜ pending |
| TS-ADV-09 | `add_reorder_policy` SQL shape (mock authoritative); live test tolerates `FeatureNotSupported` (D-12) | — | identifiers validated; license tolerance keeps suite green | unit (mock) + integration (license-tolerant) | `uv run pytest tests/test_timescale.py -k reorder` | ❌ W0 | ⬜ pending |
| TS-ADV-10 | sync/async parity for all 4 methods | — | parity enforced via `ACCESSOR_PAIRS` | unit | `uv run pytest tests/test_parity.py -k accessor_parity` | ✅ (auto) | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_timescale.py` — new file; covers TS-ADV-04/05/08/09 (sync + async). Port the
      `ts_db` skip-fixture from `tests/test_database_integration.py:839` (create-extension-or-skip);
      add an async-equivalent fixture.
- [ ] Mock SQL-shape unit tests (`mock_schema.has_extension` style, see `tests/test_async_database.py`)
      for all 4 methods — the **authoritative** assertion for `add_reorder_policy` (Apache license).
- [ ] License tolerance: `from psycopg.errors import FeatureNotSupported` `try/except` in the live
      reorder test (mirror `tests/test_database_integration.py:866–878`).
- No framework install needed (pytest + pytest-asyncio already present; `asyncio_mode = "auto"` set).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `add_reorder_policy` real job-row + `CALL run_job(job_id)` | TS-ADV-09 | Requires a Community/`timescale`-licensed TimescaleDB; local/CI is Apache-licensed (`FeatureNotSupported`) | On a Community build: `add_reorder_policy(t, idx)`, assert a row in `timescaledb_information.jobs`, then `CALL run_job(job_id)` completes |

*All other phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have automated verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (new `tests/test_timescale.py`)
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter (set by planner once tasks map cleanly)

**Approval:** pending
