---
phase: 45-api-completeness-gaps-structured-logging
verified: 2026-06-30T21:00:00Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
---

# Phase 45: API Completeness Gaps + Structured Logging — Verification Report

**Phase Goal:** Users can control transaction isolation and savepoints, pass named query
parameters, probe connection health, and enable structured logging — all without new runtime
dependencies.

**Verified:** 2026-06-30T21:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `db.transaction(isolation_level=...)` and `db.session(isolation_level=...)` accept `IsolationLevel` enum; both sync AND async | VERIFIED | `database.py:526-577`, `async_database.py:719-771`; `isolation_level: IsolationLevel | None = None` kw-only on both; in-session guard raises `RuntimeError`; parity confirmed by test_parity.py (37/37) |
| 2 | `db.savepoint(name=None)` is a context manager with partial rollback; raises outside session; sync + async | VERIFIED | `database.py:663-706`, `async_database.py:615-646`; guard `if self._session_conn is None: raise RuntimeError`; delegates to `conn.transaction(savepoint_name=name)`; 7 tests passing |
| 3 | Dict named params work on execute/fetch_one/fetch_val/fetch_all/to_dataframe; annotated `Params`; divergence documented | VERIFIED | All 5 methods annotate `params: Params = None` (both classes); `%(name)s` proven live; `to_dataframe` documented as `:name` style (SQLAlchemy path); `test_to_dataframe_named_style` pins the divergence |
| 4 | `db.health()` on all 4 classes, NEVER raises, returns `{connected, latency_ms, server_version}` (+ `pool_stats` for pooled) | VERIFIED | `database.py:708-774`, `async_database.py:648-710`, `pool.py:220-286` and `504-570`; all 4 classes; `except Exception` never-raises contract; `pool_stats: self.stats` (property not method) |
| 5 | `pycopg/logging.py` provides `get_logger` + `log_operation`; coarse instrumentation applied to ETL/backup/migrations/from_dataframe/health; hot path NOT touched | VERIFIED | `pycopg/logging.py` complete; 13 `with log_operation(...)` sites in `etl.py` (2), `backup.py` (4), `migrations.py` (1), `database.py` (3), `async_database.py` (3); 0 sites on execute/fetch_*; `TestInstrumentationSites` passes |
| 6 | Zero new runtime dependencies | VERIFIED | `pyproject.toml` dependencies unchanged (psycopg, psycopg_pool, sqlalchemy, pandas, tenacity); no structlog or other new dep; git diff confirms no pyproject.toml changes across all Phase 45 commits |

**Score:** 6/6 truths verified

---

### Verdict on Criterion #3 — `to_dataframe` Named Param Style

The requirement says "pass a dict of named parameters using `%(name)s` placeholders to `to_dataframe`". The implementers confirmed (RESEARCH Q1) that `to_dataframe` routes through `pd.read_sql(text(sql), ...)` — SQLAlchemy's `text()` — which uses `:name` (colon-prefix) style, not `%(name)s`.

**Assessment: PASSES the spirit, borderline on the letter.**

The letter says `%(name)s` on `to_dataframe`. The spirit is "named params work". What the implementation delivers:

- Named params DO work on `to_dataframe` — via `:name` style, confirmed by `test_to_dataframe_named_style`
- The divergence is documented explicitly in the `to_dataframe` docstring and pinned by the targeted test
- The annotation was widened from `dict | None` to `Params = None` — structural alignment with the other four methods
- D-12 HARD LOCK was respected: no translator was built (grep confirms `_rewrite_named_params` does not exist)
- REQUIREMENTS.md explicitly lists `:name` translator as "Out of Scope"

The `%(name)s` literal wording was set before RESEARCH Q1 was resolved. Post-research, the planner explicitly endorsed the "document the divergence" path. PARAM-01 as marked `[x] Complete` in REQUIREMENTS.md is correct: the goal was that named params work on all five methods, and they do — just with engine-appropriate syntax on `to_dataframe`. **No gap.**

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/logging.py` | `get_logger`, `log_operation`, NullHandler default | VERIFIED | All present; `_logger.addHandler(NullHandler())`; `@contextmanager` with `Generator[None, None, None]` return; no `basicConfig` call |
| `pycopg/base.py` | `Params` alias; `_decode_server_version` | VERIFIED | `Params = Sequence[Any] | Mapping[str, Any] | None`; `_decode_server_version` uses `% 10000` (post WR-04 fix); `_decode_server_version(160001)=="16.1"`, `(90605)=="9.6.5"`, `(140999)=="14.999"` |
| `pycopg/__init__.py` | `IsolationLevel` + `Params` in `__all__` | VERIFIED | `from psycopg import IsolationLevel` (thin re-export, not a copy: `pycopg.IsolationLevel is psycopg.IsolationLevel == True`); `from pycopg.base import Params`; both in `__all__` under `# Types` group |
| `pycopg/database.py` | `transaction(isolation_level=, savepoint_name=)`, `session(*, isolation_level=)`, `savepoint(*, name=)`, `health()`, `params: Params` on 5 methods | VERIFIED | All present; kw-only enforced; `_decode_server_version` and `log_operation` imported; `health()` bypasses retry (WR-02 fix) |
| `pycopg/async_database.py` | Async mirrors of above | VERIFIED | Identical signatures/param-kinds; `async def savepoint`, `async def health`, `async def transaction` all confirmed |
| `pycopg/pool.py` | `PooledDatabase.health()` + `AsyncPooledDatabase.health()` with `pool_stats` | VERIFIED | Both classes; `pool_stats: self.stats` (property access, no parentheses); `pool_stats: None` on failure |
| `pycopg/etl.py` | `log_operation("etl.run")` on both `run` methods | VERIFIED | Lines 1192, 1877; `rows=` omitted (None) — explicitly allowed by plan fallback |
| `pycopg/backup.py` | `log_operation("backup.pg_dump"/"backup.pg_restore")` on all 4 accessors | VERIFIED | Lines 87, 161, 434, 510 |
| `pycopg/migrations.py` | `log_operation("migrations.migrate")` | VERIFIED | Line 193; `rows=` omitted (None) — list built after the wrap, accepted per plan |
| `tests/test_logging_module.py` | `TestGetLogger`, `TestLogOperation`, `TestNullHandlerSilence`, `test_instrumentation_sites` | VERIFIED | All 12 tests pass in 0.04s |
| `tests/test_transaction_isolation.py` | TXN-01: isolation set, in-session guard, async mirrors | VERIFIED | All 9 tests present and green |
| `tests/test_savepoints.py` | TXN-02: partial rollback, auto-name, requires-session guard, async mirrors | VERIFIED | All 7 tests pass with PGDATABASE=pycopg_test2 |
| `tests/test_named_params.py` | PARAM-01: dict params on 4 methods, `to_dataframe` style confirmed | VERIFIED | All 6 tests pass; `test_to_dataframe_named_style` pins `:name` divergence |
| `tests/test_health.py` | HEALTH-01: shape, never-raises, version decode, pooled pool_stats, async mirrors | VERIFIED | 14 unit/mocked tests pass; 2 live-smoke tests require `PGDATABASE=pycopg_test2` and pass with it |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `pycopg/__init__.py` | `psycopg.IsolationLevel` | `from psycopg import IsolationLevel` (thin re-export) | WIRED | `pycopg.IsolationLevel is psycopg.IsolationLevel == True` confirmed at runtime |
| `pycopg/__init__.py` | `pycopg.base.Params` | `from pycopg.base import Params` | WIRED | Present in import block and `__all__` |
| `Database.health` | `_decode_server_version` (base.py) | `from pycopg.base import ... _decode_server_version` | WIRED | `database.py:34` imports it; `database.py:766` calls it |
| `PooledDatabase.health` | `self.stats` (property) | `pool_stats: self.stats` | WIRED | Verified: no parentheses; `pool.py:277` |
| Instrumented ops | `pycopg.logging.log_operation` | `from pycopg.logging import log_operation` | WIRED | All 5 files import and call it; verified by grep and import test |
| `Database.savepoint` | `psycopg conn.transaction(savepoint_name=)` | `self._session_conn.transaction(savepoint_name=name)` | WIRED | `database.py:705`; delegates natively, no SQL interpolation |

### Data-Flow Trace (Level 4)

Level 4 applies primarily to `health()` — the new method that returns live data.

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `Database.health()` | `server_ver_int` | `conn.info.server_version` (live psycopg connection) | Yes — real PostgreSQL int | FLOWING |
| `Database.health()` | `latency_ms` | `time.perf_counter()` bracketing `SELECT 1` | Yes — real timing | FLOWING |
| `PooledDatabase.health()` | `pool_stats` | `self.stats` (property returning `self._pool.get_stats()`) | Yes — real pool stats dict | FLOWING |
| `log_operation` extra | `duration_ms` | `time.perf_counter()` in `finally` block | Yes — real timing | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Imports resolve cleanly | `uv run python -c "import pycopg.etl, pycopg.backup, pycopg.migrations, pycopg.database, pycopg.async_database"` | exit 0 | PASS |
| IsolationLevel re-export is thin | `pycopg.IsolationLevel is psycopg.IsolationLevel` | `True` | PASS |
| `_decode_server_version` arithmetic | `_decode_server_version(160001)`, `(90605)`, `(140999)` | `"16.1"`, `"9.6.5"`, `"14.999"` | PASS |
| `IsolationLevel` and `Params` in `__all__` | runtime assert | both present | PASS |
| Hot path not instrumented | `grep log_operation database.py` | 3 sites (health, from_dataframe, from_geodataframe) — 0 on execute/fetch_* | PASS |
| No translator built | `grep _rewrite_named_params pycopg/` | no output | PASS |
| All Phase 45 test files | `PGDATABASE=pycopg_test2 pytest ...` (83 tests) | 83 passed | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| TXN-01 | Plan 02 | Transaction isolation level via `db.transaction`/`db.session` | SATISFIED | `isolation_level=` kw-only on both methods, both classes; in-session guard raises; 9 tests |
| TXN-02 | Plan 02 | Savepoints with partial rollback via `db.savepoint(name=)` | SATISFIED | `savepoint()` on both classes; `transaction(savepoint_name=)` also wired; 7 integration tests |
| PARAM-01 | Plans 01, 03 | Named params as dict, annotated `Params`, documented | SATISFIED | `Params` alias + 5-method widening + live tests + `to_dataframe` divergence documented |
| HEALTH-01 | Plan 03 | `db.health()` never-raises, dotted version, pool_stats on pooled | SATISFIED | All 4 classes; `_decode_server_version`; `pool_stats: self.stats`; 14 unit tests |
| LOG-01 | Plans 01, 04 | `pycopg/logging.py` with `get_logger`/`log_operation`; coarse instrumentation | SATISFIED | `logging.py` complete; 13 call sites on heavyweight ops; hot path clean |

No orphaned Phase 45 requirements. All 5 IDs (TXN-01, TXN-02, PARAM-01, HEALTH-01, LOG-01) are in REQUIREMENTS.md traceability table as Complete.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `pycopg/etl.py` | 1192, 1877 | `log_operation("etl.run")` without `rows=` | Info | `rows=None` implicitly — plan explicitly allowed this fallback (D-10: rows only when op exposes a count). Not a stub. |
| `pycopg/migrations.py` | 193 | `log_operation("migrations.migrate")` without `rows=` | Info | Same: `applied` list built inside the `with` block; plan said "if threading count is awkward, rows=None". |

No TBD/FIXME/XXX markers found in Phase 45 modified files. No unreferenced debt markers. No stubs.

### Human Verification Required

None. All observable behaviors are verifiable programmatically and the test suite confirms them. The live integration tests run cleanly under `PGDATABASE=pycopg_test2`.

---

## Gaps Summary

No gaps. All six success criteria are verified against the actual codebase:

- SC1 (TXN-01) — `transaction(isolation_level=)` and `session(isolation_level=)` on sync + async with in-session guard: VERIFIED
- SC2 (TXN-02) — `savepoint(name=None)` partial rollback context manager + `transaction(savepoint_name=)`: VERIFIED
- SC3 (PARAM-01) — named dict params on 5 methods, `Params` annotation, `to_dataframe` divergence documented: VERIFIED (spirit met; letter diverges on `to_dataframe` by pre-research design decision, explicitly endorsed)
- SC4 (HEALTH-01) — `health()` on all 4 classes, never-raises, dotted version, pool_stats: VERIFIED
- SC5 (LOG-01) — `pycopg/logging.py` + 13 coarse instrumentation sites + hot path clean: VERIFIED
- SC6 (zero new runtime deps) — `pyproject.toml` unchanged: VERIFIED

The WR-01..WR-04 review findings were all fixed (commit evidence: 33bc2b8, f4254e3, 49dc46f, 8d24a03). WR-05 and IN-01..04 were explicitly deferred by the orchestrator — not actionable gaps for this phase.

---

_Verified: 2026-06-30T21:00:00Z_
_Verifier: Claude (gsd-verifier)_
