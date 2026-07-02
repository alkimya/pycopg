---
phase: 48
slug: timescaledb-follow-ups
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-02
---

# Phase 48 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml (`[tool.pytest.ini_options]`) |
| **Quick run command** | `PGDATABASE=pycopg_test3 uv run pytest tests/test_timescale.py tests/test_parity.py -x -q` |
| **Full suite command** | `PGDATABASE=pycopg_test3 uv run pytest` |
| **Estimated runtime** | ~90 seconds |

---

## Sampling Rate

- **After every task commit:** Run `PGDATABASE=pycopg_test3 uv run pytest tests/test_timescale.py tests/test_parity.py -x -q`
- **After every plan wave:** Run `PGDATABASE=pycopg_test3 uv run pytest`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 90 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 48-01-01 | 01 | 1 | TSDB-F01 | T-48-01 / — | Cagg teardown SQL binds view name via validate_identifiers; injection string rejected | unit | `PGDATABASE=pycopg_test3 uv run pytest tests/test_timescale.py -k continuous_aggregate -q` | ✅ | ⬜ pending |
| 48-02-01 | 02 | 1 | TSDB-F02 | T-48-02 / — | origin/offset bound as params; both-set raises ValueError before DB round-trip | unit | `PGDATABASE=pycopg_test3 uv run pytest tests/test_timescale.py -k time_bucket -q` | ✅ | ⬜ pending |
| 48-03-01 | 03 | 1 | TSDB-F03 | T-48-03 / — | chunk bound as `%s::regclass`; injection string not interpolated | unit | `PGDATABASE=pycopg_test3 uv run pytest tests/test_timescale.py -k compress -q` | ✅ | ⬜ pending |
| 48-04-01 | 04 | 1 | TSDB-F04 | — | show_chunks physical-time (datetime) filter verified + documented | unit | `PGDATABASE=pycopg_test3 uv run pytest tests/test_timescale.py -k show_chunks -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.* (`tests/test_timescale.py` + `tests/test_parity.py` already exist; new tests extend them in-place. No new framework install.)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| TSL-gated live compress/decompress + cagg drop success path | TSDB-F01, TSDB-F03 | Local build is Apache 2.28 → TSL functions raise `FeatureNotSupported`; success path only observable on a TSL/Community build | On a TSL build: create hypertable + cagg, call `compress_chunk`/`drop_continuous_aggregate`, assert no error; on Apache assert `FeatureNotSupported` propagates |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
