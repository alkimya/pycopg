---
phase: 11
slug: parit-sync-async-compl-te
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-09
---

# Phase 11 — Validation Strategy

> Per-phase validation contract. Reconstructed from artifacts (State B) after
> phase completion. All 9 requirements (PAR-01..PAR-09) have automated,
> real-DB verification; one Nyquist gap (the `drop_extension` injection guard
> added during this session's security review) was filled during this audit.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 (+ pytest-asyncio 1.4.0, pytest-cov 7.1.0) |
| **Config file** | `pyproject.toml` (`[tool.pytest.ini_options]`, `asyncio_mode = "auto"`) |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest` (enforces `--cov-fail-under=90`) |
| **Estimated runtime** | ~25 seconds (full suite, real `pycopg_test` DB) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd-verify-work`:** Full suite green; coverage ≥ 90
- **Max feedback latency:** ~25 seconds

---

## Per-Requirement Verification Map

All requirements are verified against the real `pycopg_test` PostgreSQL/PostGIS/TimescaleDB
instance (no skips — CI service from Phase 9). Introspection parity tests remain as the
full-surface guard alongside behavioral assertions.

| Requirement | Plan | Behavior Verified | Test Type | Automated Command | Status |
|-------------|------|-------------------|-----------|-------------------|--------|
| PAR-01 (4 async DDL) | 03 | add_primary_key / add_foreign_key / add_unique_constraint / truncate_table apply real constraints (FK cascade, unique-rejects-dup, invalid-action raises) | integration (real DB) | `uv run pytest tests/test_async_database.py::TestAsyncDatabaseConstraintsIntegration` | ✅ green |
| PAR-02 (async admin + ctors) | 04 | drop_extension / database_exists / list_databases + async create / create_from_env classmethods | integration (real DB) | `uv run pytest tests/test_async_database.py::TestAsyncDatabaseAdminIntegration` | ✅ green |
| PAR-03 (4 sync methods) | 02 | insert_many / upsert_many / stream / notify (pg_notify); listen correctly absent (D-06) | integration + unit | `uv run pytest tests/test_database_integration.py::TestDatabaseBatchStreamNotify tests/test_database.py::TestDatabaseBatchStreamNotify` | ✅ green |
| PAR-04 (C1) | 05 | async from_dataframe / from_geodataframe actually apply primary_key (warning removed) | unit (mock) + integration | `uv run pytest tests/test_async_database.py::TestAsyncDatabaseCorrectnessFixes` | ✅ green |
| PAR-05 (C2) | 05 | async close() disposes engine + nulls reference; idempotent | unit | `uv run pytest tests/test_async_database.py::TestAsyncDatabaseCorrectnessFixes` | ✅ green |
| PAR-06 (C3) | 01 | Config.async_url emits postgresql+psycopg_async://; async_engine built from it | unit (no DB) | `uv run pytest tests/test_config.py` | ✅ green |
| PAR-07 (signatures) | 05 | create_extension(schema) / create_schema(owner) match sync; table_info / list_roles field-parity | introspection + integration | `uv run pytest tests/test_parity.py::TestAsyncParity::test_method_signatures_match` | ✅ green |
| PAR-08 (parity tests) | 06 | real-DB sync==async assertions for this phase's pairs; minimized allow-lists; KNOWN_SIGNATURE_MISMATCHES empty | introspection + behavioral (real DB) | `uv run pytest tests/test_parity.py` | ✅ green |
| PAR-09 (coverage ratchet) | 07 | --cov-fail-under raised 80→90 after measuring 91.61% (D-08) | gate | `uv run pytest` ("Required test coverage of 90% reached") | ✅ green |

**Security-mitigation guard (filled this audit):**

| Behavior | Threat Ref | Test Type | Automated Command | Status |
|----------|------------|-----------|-------------------|--------|
| sync + async `drop_extension` reject a malicious extension name before SQL (`validate_extension_name`) | T-11-07 | unit (mocked driver — true regression guard) | `uv run pytest tests/test_sql_injection.py -k drop_extension` | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. pytest + pytest-asyncio + the
`pycopg_test` real-DB fixtures (`tests/conftest.py`) and `tests/test_parity.py` allow-list
harness were all in place before Phase 11. No new framework or stub scaffolding was needed.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

Two pre-existing test failures are **out of scope** for Phase 11 (not regressions, not
manual-only items for this phase — tracked for separate remediation):

| Failing test | Origin | Why out of scope |
|--------------|--------|------------------|
| `test_integration.py::TestAsyncIntegration::test_async_transaction_fix` | v0.2.0 | psycopg behavior change ("Explicit commit() forbidden within a Transaction context"); file not touched in Phase 11. |
| `test_postgis_errors.py::TestPostGISErrorHandling::test_create_spatial_index_name_parameter` | Phase 06 | references a table absent from the test DB (test-data/setup issue); file not touched in Phase 11. |

The 90% coverage gate passes both with and without these two (91.62% / 91.11%).

---

## Validation Audit 2026-06-09

| Metric | Count |
|--------|-------|
| Requirements audited | 9 |
| COVERED (pre-existing) | 9 |
| Gaps found | 1 (drop_extension injection guard, T-11-07) |
| Resolved (tests added) | 1 |
| Escalated / manual-only | 0 |

**Detail:** Reconstructed from 7 SUMMARY files + VERIFICATION.md (State B). All 9
requirements were already COVERED by 387 green real-DB/introspection tests. The single gap
— the `validate_extension_name(name)` guard added to sync + async `drop_extension` during
this session's `/gsd-secure-phase` review (T-11-07) — had no automated regression test
(its twin `create_extension` did). Added 3 tests to `tests/test_sql_injection.py`
(`test_drop_extension_injection`, `test_drop_extension_hyphen_ok`, async `test_drop_extension`),
mirroring the existing create_extension injection pattern. Full suite: **655 passed**
(+3), coverage **91.62%** ≥ 90.

---

## Validation Sign-Off

- [x] All requirements have automated verification (real-DB + introspection)
- [x] Sampling continuity: no 3 consecutive requirements without automated verify
- [x] Wave 0 covers all MISSING references (none — existing infra sufficient)
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-06-09
