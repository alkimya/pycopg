---
phase: 45
slug: api-completeness-gaps-structured-logging
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-30
---

# Phase 45 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `45-RESEARCH.md` §Validation Architecture (line 663+).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (uv run pytest) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest` (coverage gate ≥95%, baseline 96.18% @ P44) |
| **Estimated runtime** | ~90s quick · ~3–4 min full suite |

> Some TXN-02 savepoint behaviors and the LOG-01 instrumentation-site smoke tests need a live DB
> (`PGDATABASE=pycopg_test2` per the broken-default-DB note). TXN-01 isolation-guard, HEALTH-01
> (mocked conn), PARAM-01 alias, and LOG-01 pure-unit tests run without a live DB.

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest`
- **Before `/gsd-verify-work`:** Full suite must be green (incl. `test_parity.py` parity guards)
- **Max feedback latency:** ~120 seconds

---

## Per-Task Verification Map

> Task IDs assigned at plan time; rows below are keyed by requirement and will be reconciled to
> `{45-PP-TT}` task IDs during planning/execution. All test files are NEW (Wave 0 gap → ❌ W0).

| Req | Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-----|----------|------------|-----------------|-----------|-------------------|-------------|--------|
| TXN-01 | `transaction(isolation_level=SERIALIZABLE)` sets isolation outside session | — | N/A | unit | `uv run pytest tests/test_transaction_isolation.py -x -q` | ❌ W0 | ⬜ pending |
| TXN-01 | `transaction(isolation_level=)` inside `db.session()` raises clear error (D-03) | — | fail-closed, no silent ignore | unit | `uv run pytest tests/test_transaction_isolation.py::test_isolation_inside_session_raises -x` | ❌ W0 | ⬜ pending |
| TXN-01 | `session(isolation_level=REPEATABLE_READ)` sets level on session connection | — | N/A | unit | `uv run pytest tests/test_transaction_isolation.py::test_session_isolation -x` | ❌ W0 | ⬜ pending |
| TXN-02 | `transaction(savepoint_name="sp1")` + partial rollback to savepoint | — | N/A | integration | `uv run pytest tests/test_savepoints.py -x -q` | ❌ W0 | ⬜ pending |
| TXN-02 | `db.savepoint(name=None)` auto-names; inner exc rolls back only the savepoint | — | N/A | integration | `uv run pytest tests/test_savepoints.py::test_savepoint_autoname -x` | ❌ W0 | ⬜ pending |
| PARAM-01 | `execute/fetch_one/fetch_val/fetch_all` accept `%(name)s` dict params | — | psycopg native binding (no parser) | unit | `uv run pytest tests/test_named_params.py -x -q` | ❌ W0 | ⬜ pending |
| PARAM-01 | `to_dataframe()` named-param style confirmed (SQLAlchemy `:name` caveat) | — | documented divergence | unit | `uv run pytest tests/test_named_params.py::test_to_dataframe_named_style -x` | ❌ W0 | ⬜ pending |
| PARAM-01 | `Params` alias exported in `pycopg.__all__` | — | N/A | unit | `uv run pytest tests/test_named_params.py::test_params_alias_exported -x` | ❌ W0 | ⬜ pending |
| HEALTH-01 | `db.health()` returns `{connected,latency_ms,server_version}` when up | — | N/A | unit (mock) | `uv run pytest tests/test_health.py::test_health_connected -x` | ❌ W0 | ⬜ pending |
| HEALTH-01 | `db.health()` never raises → `{connected:False, error:...}` on failure (D-05) | — | fail-open monitoring probe | unit | `uv run pytest tests/test_health.py::test_health_never_raises -x` | ❌ W0 | ⬜ pending |
| HEALTH-01 | `server_version` int → dotted string (160001 → '16.1') (D-06) | — | N/A | unit | `uv run pytest tests/test_health.py::test_server_version_decode -x` | ❌ W0 | ⬜ pending |
| HEALTH-01 | Pooled `health()` adds `pool_stats` from existing `.stats` property (D-07) | — | reuse, no new pool plumbing | unit | `uv run pytest tests/test_health.py::test_pooled_health_stats -x` | ❌ W0 | ⬜ pending |
| LOG-01 | `get_logger()` returns `pycopg` logger with `NullHandler` default (D-08) | — | silent-by-default | unit | `uv run pytest tests/test_logging_module.py::test_get_logger -x` | ❌ W0 | ⬜ pending |
| LOG-01 | `log_operation` emits DEBUG record w/ `extra={operation,duration_ms,rows}` (D-10) | — | N/A | unit | `uv run pytest tests/test_logging_module.py::test_log_operation_extra -x` | ❌ W0 | ⬜ pending |
| LOG-01 | Coarse instrumentation sites wrapped (etl/backup/restore/migrate/COPY/health) (D-09) | — | no hot-path per-query timing | integration | `uv run pytest tests/test_logging_module.py::test_instrumentation_sites -x` | ❌ W0 | ⬜ pending |
| ALL | Sync/async parity (methods + signatures + param-kind) holds | — | N/A | unit | `uv run pytest tests/test_parity.py -x -q` | ✅ existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_transaction_isolation.py` — TXN-01 (isolation set + in-session guard; unit, no live DB)
- [ ] `tests/test_savepoints.py` — TXN-02 (named + auto-named savepoint partial rollback; integration, live DB)
- [ ] `tests/test_named_params.py` — PARAM-01 (`%(name)s` dict on 4 methods + `to_dataframe` style + `Params` export)
- [ ] `tests/test_health.py` — HEALTH-01 (shape, never-raises, version decode, pooled stats; unit w/ mocked conn)
- [ ] `tests/test_logging_module.py` — LOG-01 (`get_logger`, `log_operation` extra, NullHandler silence, instrumentation smoke)

> Existing `tests/test_parity.py` (`TestDatabaseAsyncParity`) covers sync/async method, signature, and
> parameter-kind parity automatically — no new parity test code needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| `interrogate` 100% public-docstring coverage on new symbols | ALL | doc-coverage gate, not a behavior test | `uv run interrogate -f 95 pycopg` (expect 100% on `health`/`savepoint`/`get_logger`/`log_operation`/`Params`) |
| `-W error::DeprecationWarning` stays green (no deprecated path touched) | ALL | CI gate | full suite under `-W error::DeprecationWarning` |

*All core phase behaviors have automated verification; the above are gate checks, not feature behaviors.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (5 new test files above)
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
