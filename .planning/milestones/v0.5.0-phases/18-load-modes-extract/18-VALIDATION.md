---
phase: 18
slug: load-modes-extract
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-15
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `18-RESEARCH.md` §"Validation Architecture". The planner refines the
> Per-Task Verification Map with real task IDs.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x (+ pytest-cov) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `addopts` at line ~90, `--cov-fail-under=94`) |
| **Quick run command** | `uv run pytest tests/test_etl.py tests/test_etl_accessor.py tests/test_sql_injection.py -x -q -o addopts=""` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~30–90 seconds (DB integration tests against real `pycopg_test`) |

> **DB fixture:** `db` (from `db_config`) → real `pycopg_test`; pattern in
> `tests/test_etl_accessor.py:18-32`. ETL load/extract is I/O-heavy — test against real PG,
> not mocks (Pitfall 12). Coverage gate stays at **94** this phase (no ratchet).
> 3 full-suite DB tests are pre-existing flaky in the local env — use targeted `-o addopts=""`
> runs for focused work; not a Phase 18 regression.

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_etl.py tests/test_etl_accessor.py tests/test_sql_injection.py -x -q -o addopts=""`
- **After every plan wave:** Run `uv run pytest -o addopts=""` (targeted full; skip known flaky via `-k` as needed)
- **Before `/gsd-verify-work`:** Full suite `uv run pytest` green (incl. `--cov-fail-under=94`); `uv run ruff check pycopg tests`; `uv run black --check pycopg tests`
- **Max feedback latency:** ~90 seconds

---

## Per-Task Verification Map

> Planner fills Task IDs once plans exist. Behaviors below are the Nyquist-required samples
> from `18-RESEARCH.md` §"Phase Requirements → Test Map".

| Behavior | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists |
|----------|-------------|------------|-----------------|-----------|-------------------|-------------|
| extract SQL source → DataFrame | ETL-02 | — | N/A | integration | `pytest tests/test_etl_accessor.py -k extract_sql -x` | ❌ W0 |
| extract table source + `extract_limit` LIMIT | ETL-02 | T-18 (limit bind) | LIMIT bound, never interpolated | integration | `pytest tests/test_etl_accessor.py -k extract_table_limit -x` | ❌ W0 |
| transform single callable applied | ETL-03 | — | N/A | integration | `pytest tests/test_etl_accessor.py -k transform_single -x` | ❌ W0 |
| transform raises → `ETLTransformError` + failed-run row | ETL-03 | — | N/A | integration | `pytest tests/test_etl_accessor.py -k transform_error_failed_run -x` | ❌ W0 |
| transform list in sequence; error names which step | ETL-16 | — | N/A | unit/integration | `pytest tests/test_etl.py -k transform_chain_step_index -x` | ❌ W0 |
| append re-run doubles row count | ETL-04 | — | N/A | integration | `pytest tests/test_etl_accessor.py -k append_double_count -x` | ❌ W0 |
| append missing target → `ETLTargetNotFoundError` | ETL-04 | — | N/A | integration | `pytest tests/test_etl_accessor.py -k append_missing_target -x` | ❌ W0 |
| replace re-run = latest only | ETL-05 | — | N/A | integration | `pytest tests/test_etl_accessor.py -k replace_latest_only -x` | ❌ W0 |
| **replace mid-load error leaves ORIGINAL rows intact (atomic)** | ETL-05 | — | atomic TRUNCATE+INSERT | integration | `pytest tests/test_etl_accessor.py -k replace_atomic_rollback -x` | ❌ W0 |
| replace auto-creates missing target (zero-row frame) | ETL-05 | — | N/A | integration | `pytest tests/test_etl_accessor.py -k replace_creates_missing -x` | ❌ W0 |
| upsert re-run updates + inserts, no duplicates | ETL-06 | — | N/A | integration | `pytest tests/test_etl_accessor.py -k upsert_no_duplicates -x` | ❌ W0 |
| upsert missing target → `ETLTargetNotFoundError` | ETL-06 | — | N/A | integration | `pytest tests/test_etl_accessor.py -k upsert_missing_target -x` | ❌ W0 |
| failed load rolls back; run-log row still committed | ETL-09 (regress guard) | — | load txn isolated from run-log | integration | adapt `test_failed_run_commits_despite_load_rollback` + `run()`-level variant | ✅ adapt |
| injection via `target` / `conflict_columns` rejected | ETL-16 / SC-6 | T-18 (V5 input validation) | `validate_identifiers` before interpolation | unit | `pytest tests/test_sql_injection.py -k etl -x` | ❌ W0 |
| NaN/NaT cell → SQL NULL (not float-NaN) | D-07 | — | N/A | integration | `pytest tests/test_etl_accessor.py -k nan_to_null -x` | ❌ W0 |

> **Critical atomicity test (`replace_atomic_rollback`):** seed target with baseline rows → run a
> replace pipeline that fails mid-INSERT → assert target STILL contains baseline rows (NOT empty).
> With the broken session-only seam the target is `[]`; with the correct yielded-conn seam it
> preserves `[1]`. **Highest-value test of the phase** (catches the Q1 landmine in RESEARCH.md).

---

## Wave 0 Requirements

- [ ] Extend `_FakeDatabase` in `tests/test_etl_accessor.py` for `cursor()`/`session()`/`transaction()`/`table_exists()`, OR test `run()` exclusively against real PG.
- [ ] New integration cases per the map above (all `❌ W0`).
- [ ] ETL injection cases in `tests/test_sql_injection.py` (malicious `target`/`conflict_columns` via `db.etl.run(Pipeline(...))`) — follow `EVIL_IDENTIFIERS` parametrize pattern.
- [ ] Migrate Phase 17 tests calling `db.etl.run("string")` → `db.etl.run(Pipeline(...))` (`test_first_run_auto_creates`, `test_run_writes_full_row`) — `run()` signature change (Q5).
- [ ] NaN→NULL and (documented) tz-naive behavior tests (D-07).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| tz-naive `datetime64` → `TIMESTAMPTZ` silent shift is the user's responsibility | D-07 | Behavior is "do nothing / document"; no coercion to assert | Confirm docstring documents tz-localization as caller's responsibility (matches `from_dataframe`); a passing automated test would only assert the *absence* of coercion — covered by `nan_to_null` test scope + docstring review |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
