---
phase: 16-pure-etl-layer
verified: 2026-06-14T00:00:00Z
status: passed
score: 4/4
overrides_applied: 0
re_verification: null
---

# Phase 16: Pure ETL Layer — Verification Report

**Phase Goal:** Users can define a `Pipeline` dataclass that is inspectable and validated at construction time — all ETL SQL constants and pure DB-free builder functions exist and are unit-testable without any database connection.
**Verified:** 2026-06-14
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `Pipeline(name=..., source=..., target=..., load_mode=...)` can be instantiated and all attributes (`name`, `source`, `target`, `load_mode`, `conflict_columns`, `schema`, `transform`, `extract_limit`) are readable | VERIFIED | `pycopg/etl.py` line 61-143: `@dataclass(frozen=True)` with 8 fields. Runtime check confirmed all 8 attributes readable. |
| 2 | Constructing `Pipeline(load_mode='upsert')` without `conflict_columns` raises `ValueError` at construction time, before any DB interaction | VERIFIED | `pycopg/etl.py` lines 172-175: `__post_init__` raises `ValueError("load_mode='upsert' requires conflict_columns to be non-empty (D-07)")`. Runtime confirmed; `pytest.raises(ValueError, match="upsert")` in test_etl.py line 51. |
| 3 | All ETL SQL constants (`ETL_INIT_PIPELINE_RUNS`, `ETL_INSERT_RUN`, `ETL_UPDATE_RUN`, `ETL_LIST_RUNS`, `ETL_GET_LAST_RUN`) exist in `queries.py` and contain no f-string identifier interpolation | VERIFIED | `pycopg/queries.py` lines 249-295: all 5 constants present. ETL section grep confirms zero f-strings. `ETL_INIT_PIPELINE_RUNS` contains `CREATE TABLE IF NOT EXISTS`, `watermark JSONB`, `BIGSERIAL`, and `TEXT NOT NULL CHECK` (not ENUM). |
| 4 | Pure builder functions (`build_init_sql()`, `build_truncate_sql()`) are importable and return parameterized SQL strings in unit tests that require no DB fixture | VERIFIED | `pycopg/etl.py` lines 220-279: both functions present. `build_truncate_sql('events')` returns `('TRUNCATE TABLE public.events', [])`. `build_init_sql()` returns `(queries.ETL_INIT_PIPELINE_RUNS, [])`. 33 tests pass in `uv run pytest tests/test_etl.py -o addopts=""` (0.04s, no DB). |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/etl.py` | Pipeline frozen dataclass + build_init_sql + build_truncate_sql (D-01..D-15) | VERIFIED | 279 lines (min_lines: 80 met); contains `@dataclass(frozen=True)`, `class Pipeline`, `build_init_sql`, `build_truncate_sql`, `_validate_load_mode`, `_VALID_LOAD_MODES`, `_is_sql_source` |
| `pycopg/exceptions.py` | ETL exception hierarchy (D-08) | VERIFIED | Lines 54-69: `ETLError(PycopgError)`, `ETLTransformError(ETLError)`, `ETLTargetNotFoundError(ETLError)`. Two-level hierarchy confirmed. No `PipelineError` wrapper (D-09 honored). |
| `pycopg/queries.py` | 5 ETL SQL constants (D-10/D-12/D-14) | VERIFIED | Lines 249-295: all 5 constants in `# ETL QUERIES` section with `%s` placeholders, no f-string interpolation. `ETL_INIT_PIPELINE_RUNS` is idempotent DDL with TEXT+CHECK status, BIGSERIAL PK, nullable `watermark JSONB`. |
| `pycopg/__init__.py` | Top-level exports of ETL exception classes | VERIFIED | Lines 14-16: `ETLError`, `ETLTargetNotFoundError`, `ETLTransformError` imported from `pycopg.exceptions`. Lines 57-59: all three in `__all__`. Import confirmed via runtime check. |
| `tests/test_etl.py` | DB-free unit tests for Pipeline + builders (ROADMAP SC-4) | VERIFIED | 232 lines; 33 tests across `TestPipeline`, `TestBuilders`, `TestIsSqlSource`, `TestValidateLoadMode`. Zero DB fixture, zero `db.execute`, zero connection usage. All pass in 0.04s. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `pycopg/__init__.py` | `pycopg/exceptions.py` | `from pycopg.exceptions import (... ETLError, ETLTargetNotFoundError, ETLTransformError ...)` | WIRED | `__init__.py` lines 14-16 confirm the import; `'ETLError' in pycopg.__all__` confirmed runtime. |
| `pycopg/etl.py` | `pycopg.exceptions` | `from pycopg.exceptions import ETLTargetNotFoundError, ETLTransformError` | WIRED | `etl.py` line 31. ETL exception classes imported (noqa: F401 — imported for stable re-export to downstream phases 18+). |
| `pycopg/etl.py` | `pycopg.queries.ETL_INIT_PIPELINE_RUNS` | `build_init_sql` returns the DDL constant | WIRED | `etl.py` line 30 imports `from pycopg import queries`; line 279: `return queries.ETL_INIT_PIPELINE_RUNS, []`. Runtime confirmed. |
| `pycopg/etl.py` | `pycopg.utils.validate_identifiers` | every builder validates identifiers before interpolation (D-13) | WIRED | `etl.py` line 32: `from pycopg.utils import validate_identifiers`; line 248: `validate_identifiers(table, schema)` called before f-string interpolation in `build_truncate_sql`. |

### Data-Flow Trace (Level 4)

Not applicable. This phase delivers pure, DB-free builders and dataclasses. There is no dynamic data rendering — only construction-time validation and SQL string generation. The builders return static or identifier-interpolated strings with no live DB query.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Pipeline attributes readable (SC-1) | `uv run python -c "from pycopg.etl import Pipeline; p = Pipeline(name='x', source='t', target='u', load_mode='upsert', conflict_columns=['id']); assert p.conflict_columns == ('id',)"` | exit 0 | PASS |
| ValueError at construction without conflict_columns (SC-2) | `uv run python -c "from pycopg.etl import Pipeline; Pipeline(name='x', source='t', target='u', load_mode='upsert')"` | ValueError raised | PASS |
| All 5 SQL constants exist, DDL is idempotent | `uv run python -c "from pycopg import queries as q; [getattr(q, n) for n in ('ETL_INIT_PIPELINE_RUNS','ETL_INSERT_RUN','ETL_UPDATE_RUN','ETL_LIST_RUNS','ETL_GET_LAST_RUN')]; assert 'CREATE TABLE IF NOT EXISTS' in q.ETL_INIT_PIPELINE_RUNS"` | exit 0 | PASS |
| DB-free test suite | `uv run pytest tests/test_etl.py -q -o addopts=""` | 33 passed in 0.04s | PASS |
| Builders return parameterized tuples | `uv run python -c "from pycopg.etl import build_init_sql, build_truncate_sql; assert build_truncate_sql('events') == ('TRUNCATE TABLE public.events', [])"` | exit 0 | PASS |
| InvalidIdentifier for bad identifier | `uv run python -c "from pycopg.etl import build_truncate_sql; build_truncate_sql('bad-name')"` | InvalidIdentifier raised | PASS |

### Probe Execution

No phase-declared probes. `scripts/*/tests/probe-*.sh` not applicable (this is a pure Python library phase, not a migration/tooling phase).

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ETL-01 | 16-01, 16-02 | User can define `Pipeline(name=..., source=..., target=..., load_mode=...)`; object is inspectable (`name`, `source`, `target`, `load_mode`, `conflict_columns`, `schema` readable) | SATISFIED | `pycopg/etl.py` Pipeline dataclass with all required attributes; runtime and test suite confirm. REQUIREMENTS.md traceability table marks ETL-01 Phase 16 as "Complete". |

No orphaned requirements detected. ETL-02 through ETL-17 are mapped to Phases 17-20 and are not in scope for Phase 16.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `pycopg/exceptions.py` | 24, 30, 36, 48 | N818: pre-existing exception names without `Error` suffix (`ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier`, `DatabaseExists`) | Info (pre-existing) | None — not introduced by Phase 16. All 3 new ETL classes end in `Error` and are N818-compliant. |

No `TBD`, `FIXME`, `XXX`, or `TODO` markers in any Phase 16 files.

No stub patterns found. `return null`, `return {}`, empty handlers — none present in `etl.py`, `queries.py`, or `test_etl.py`.

No f-string identifier interpolation in the `# ETL QUERIES` section of `queries.py`. All ETL constants use `%s` placeholders exclusively (D-12 honored).

`build_truncate_sql` f-string interpolates only post-`validate_identifiers`-validated identifiers — not a D-12 violation (user values are never interpolated; only validated `table`/`schema` identifiers).

### Human Verification Required

None. All success criteria are mechanically verifiable (imports, attribute access, ValueError/InvalidIdentifier raises, SQL string assertions, pytest pass/fail). No visual, real-time, or external-service behavior involved.

### Gaps Summary

No gaps. All 4 observable truths verified. All 5 required artifacts exist, are substantive (not stubs), and are wired. ETL-01 requirement satisfied. Anti-pattern scan clean (4 pre-existing N818 in untouched code, none from Phase 16). 33 DB-free tests pass in under 0.1 seconds.

---

_Verified: 2026-06-14T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
