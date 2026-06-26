---
phase: 38
slug: performance-copy
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-26
---

# Phase 38 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `38-RESEARCH.md` § Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.0.0+ with pytest-asyncio 0.23.0+ |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `PGDATABASE=pycopg_test2 uv run pytest tests/test_parity.py tests/test_database_integration.py tests/test_etl_accessor.py -x -q -o addopts=""` |
| **Full suite command** | `PGDATABASE=pycopg_test2 uv run pytest` |
| **Estimated runtime** | ~30–90 seconds (real-DB integration suite) |

> **Real-DB note:** Use `PGDATABASE=pycopg_test2` — the default `pycopg_test` DB is broken since 2026-06-24 (TSDB catalog mismatch). 3 PostGIS env-failures are known non-regressions. Targeted runs use `-o addopts=""` to bypass the coverage gate.

---

## Sampling Rate

- **After every task commit:** `PGDATABASE=pycopg_test2 uv run pytest tests/test_parity.py tests/test_database_integration.py tests/test_etl_accessor.py -x -q -o addopts=""`
- **After every plan wave:** `PGDATABASE=pycopg_test2 uv run pytest`
- **Before `/gsd-verify-work`:** Full suite must be green (coverage ratchet held at 94)
- **Max feedback latency:** ~90 seconds

---

## Per-Task Verification Map

> Filled per-task by the planner. Requirement → test mapping seeded from research:

| Req ID | Behavior | Test Type | Automated Command | File Exists | Status |
|--------|----------|-----------|-------------------|-------------|--------|
| PERF-01 | `from_dataframe` routes data via COPY, not `to_sql` (spy: `to_sql` called once for head(0) DDL only) | unit+spy | `uv run pytest tests/test_database_integration.py -k "from_dataframe" -o addopts=""` | ❌ W0 | ⬜ pending |
| PERF-01 | `if_exists` fail/replace/append preserved | integration (real DB) | `uv run pytest tests/test_database_integration.py -k "from_dataframe" -o addopts=""` | ⚠️ partial | ⬜ pending |
| PERF-01 | `index=True` round-trip via `reset_index()` | integration (real DB) | included above | ❌ W0 | ⬜ pending |
| PERF-01 | `primary_key` post-load unchanged | integration (real DB) | `uv run pytest tests/test_parity.py -k from_dataframe_primary_key -o addopts=""` | ✅ | ⬜ pending |
| PERF-02 | ETL `append`/`replace` via COPY, same status/count | integration (real DB) | `uv run pytest tests/test_etl_accessor.py -k run -o addopts=""` | ⚠️ partial | ⬜ pending |
| PERF-02 | ETL `upsert` stays on INSERT ON CONFLICT | integration (real DB) | existing ETL suite | ✅ | ⬜ pending |
| PERF-02 | NaN/NaT/pd.NA → SQL NULL fidelity under COPY text | integration (real DB) | `uv run pytest tests/test_etl_accessor.py -k null -o addopts=""` | ❌ W0 | ⬜ pending |
| PERF-03 | `insert_batch` placeholder hoist — byte-exact non-regression | unit | `uv run pytest tests/test_database.py -k insert_batch -o addopts=""` | ⚠️ partial | ⬜ pending |
| PERF-05 | sync/async parity (`test_parity` / `test_accessor_parity`) green | unit | `uv run pytest tests/test_parity.py -x -o addopts=""` | ✅ | ⬜ pending |
| PERF-05 | dedicated async `from_dataframe` COPY behavioral test | unit+spy | `uv run pytest tests/test_async_database.py -k from_dataframe_copy -o addopts=""` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_database_integration.py` — `TestFromDataframeCopy`: COPY-path spy, `replace`/`append`, `index=True` round-trip, NaN/NaT → NULL in DB
- [ ] `tests/test_async_database.py` — dedicated async `from_dataframe` COPY behavioral test with spy (PERF-05 async)
- [ ] `tests/test_database.py` — `insert_batch` placeholder-hoist byte-exact non-regression test (PERF-03)
- [ ] `tests/test_etl_accessor.py` — extend for exact `rows_loaded` after COPY + NaN/NaT → NULL (PERF-02)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Throughput gain on ~100k rows | PERF-01/PERF-02 | Deferred to Phase 39 (PERF-04 benchmark suite); D-06 forbids timing-based assertions here | N/A in Phase 38 — behavior + assert-COPY-used only |

*Phase 38 asserts COPY is the path taken + contract preserved; numeric throughput is the Phase 39 benchmark suite.*

---

## Validation Sign-Off

> **`nyquist_compliant` / `wave_0_complete` are set to `true` POST-EXECUTION**, once the Wave 0 test files exist and the sign-off checklist below is verified green. Pre-execution they are `false` by design — structural Nyquist coverage is already sound (every task carries an `<automated>` verify, no watch-mode flags, no 3-consecutive unverified tasks).

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
