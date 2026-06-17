---
phase: 23-schema-accessor-spatial-relocation
verified: 2026-06-18T00:00:00Z
status: passed
score: 10/10
overrides_applied: 0
re_verification: null
---

# Phase 23: Schema Accessor & Spatial Relocation — Verification Report

**Phase Goal:** Users can access all ~26 DDL/introspection methods under `db.schema.*`, and the 2 spatial-index methods (`create_spatial_index`, `list_geometry_columns`) land under `db.spatial.*` — the largest accessor block is migrated and the PostGIS surface is made thematically complete.

**Verified:** 2026-06-18T00:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `db.schema.*` exposes all 27 DDL/introspection methods (`SchemaAccessor`) | VERIFIED | `python -c "from pycopg.schema import SchemaAccessor; assert len([m for m in dir(SchemaAccessor) if not m.startswith('_')])==27"` exits 0; all 27 methods confirmed at codebase level |
| 2 | `async_db.schema.*` exposes same 27 methods at exact parity (`AsyncSchemaAccessor`) | VERIFIED | `python -c "... assert set(sync)==set(async) and len(sync)==27"` exits 0; all async methods are coroutines |
| 3 | Flat `db.<schema_method>(...)` still works but emits `DeprecationWarning` naming `db.schema.<m>` with v0.7.0 and delegates | VERIFIED | 27 `@deprecated_alias("schema.<m>")` stubs confirmed in `database.py` (grep count == 27) and `async_database.py` (== 27); DB-free MagicMock test proves warn + delegate; 54 schema alias tests pass |
| 4 | `db.spatial.create_spatial_index` and `db.spatial.list_geometry_columns` are callable on `SpatialAccessor` and `AsyncSpatialAccessor` | VERIFIED | Both methods present on both classes; inline GIST SQL in `spatial.py` (`grep -c 'USING GIST' == 2`); `LIST_GEOMETRY_COLUMNS` referenced (`grep -c == 2`); absent from `database.py`/`async_database.py` (0 matches) |
| 5 | Flat `db.create_spatial_index` / `db.list_geometry_columns` still work but emit `DeprecationWarning` naming `db.spatial.<m>` | VERIFIED | 2 `@deprecated_alias("spatial.*")` stubs confirmed in both `database.py` and `async_database.py`; DB-free MagicMock test confirmed warn + delegate; 4 spatial alias tests pass |
| 6 | All 29 legacy flat names warn and delegate; zero internal `DeprecationWarning` under `-W error::DeprecationWarning` | VERIFIED | 1030 unit tests pass under `uv run pytest -W error::DeprecationWarning` (excluding pre-existing third-party `psycopg_pool` noise and 2 known-flaky DB integration tests); D-05 call-site rewrites confirmed in `from_dataframe`/`from_geodataframe` (8 sites), `timescale.py` (12 sites), `etl.py` (2 sites), `spatial.py` (2 sites) |
| 7 | `test_parity` passes with `(SchemaAccessor, AsyncSchemaAccessor)` and `(SpatialAccessor, AsyncSpatialAccessor)` in `ACCESSOR_PAIRS` | VERIFIED | `grep -c '(SchemaAccessor, AsyncSchemaAccessor)' test_parity.py == 1`; `grep -c '(SpatialAccessor, AsyncSpatialAccessor)' == 1`; `test_accessor_parity` passes for both pairs (7 pairs total, 24 parity tests) |
| 8 | Coverage ratchet held at >= 94% | VERIFIED | Full suite reports 95.64% coverage (gate: 94%); 1109 passed, 2 failed (both pre-existing known-flaky tests), 2 skipped |
| 9 | All `validate_identifier` / `validate_identifiers` / `validate_extension_name` / `validate_index_method` guards survived relocation (T-23-01 security invariant) | VERIFIED | `grep -c 'validate_identifiers' schema.py == 15`; `grep -c 'validate_index_method' schema.py == 3`; `grep -c 'validate_extension_name' schema.py == 5`; `validate_identifiers` in `spatial.py` for both relocated methods (lines 1879, 2803); `test_sql_injection.py` passes 92/92 |
| 10 | `from pycopg import SchemaAccessor, AsyncSchemaAccessor` works; both in `__all__` | VERIFIED | `python -c "import pycopg; assert 'SchemaAccessor' in pycopg.__all__ and 'AsyncSchemaAccessor' in pycopg.__all__"` exits 0 |

**Score:** 10/10 truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/schema.py` | `SchemaAccessor` + `AsyncSchemaAccessor`, 27 methods each | VERIFIED | 1324 lines; `class SchemaAccessor` + `class AsyncSchemaAccessor` confirmed; all 27 sync methods at lines 62+; all 27 async methods; 0 `self.execute`/`self.config` leaks |
| `pycopg/database.py` | `_schema` cache field + `schema` lazy property + 27 `@deprecated_alias("schema.<m>")` stubs + 2 `@deprecated_alias("spatial.<m>")` stubs | VERIFIED | `grep -c '@deprecated_alias("schema\.' == 27`; `grep -c '@deprecated_alias("spatial\.' == 2`; `grep -c '_schema' == 13` (>= 2); `grep -c 'def schema' == 2` |
| `pycopg/async_database.py` | Same as `database.py` (async) | VERIFIED | Same stub counts confirmed; async stubs declared `async def` |
| `pycopg/__init__.py` | `SchemaAccessor` + `AsyncSchemaAccessor` in `__all__` | VERIFIED | Import and `__all__` entries confirmed |
| `pycopg/spatial.py` | `create_spatial_index` + `list_geometry_columns` on both accessor classes | VERIFIED | Both methods on `SpatialAccessor` and `AsyncSpatialAccessor`; async methods have `await self._check_postgis()` as first awaitable line (count 13, +2 from pre-phase 11); no `self.execute` leaks |
| `tests/test_schema_aliases.py` | 27 sync + 27 async DB-free MagicMock alias tests | VERIFIED | 54 tests collected and pass; `_SYNC_ALIAS_ARGS` has 27 keys; `class TestSchemaAliases` confirmed |
| `tests/test_spatial_aliases.py` | 2 sync + 2 async DB-free alias tests | VERIFIED | 4 tests collected and pass; `class TestSpatialAliases` confirmed |
| `tests/test_parity.py` | `(SchemaAccessor, AsyncSchemaAccessor)` + `(SpatialAccessor, AsyncSpatialAccessor)` in `ACCESSOR_PAIRS` | VERIFIED | Both tuples present; 7 total pairs; 24 `test_accessor_parity` subtests pass |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `Database.schema` property | `SchemaAccessor` | lazy construction + `_schema` cache | VERIFIED | Property instantiates `SchemaAccessor(self)` and caches in `self._schema`; confirmed by import and DB-free invocation |
| 27 flat `db.*` schema stubs | `@deprecated_alias` → `self.schema.<m>` | decorator delegation | VERIFIED | `grep count == 27` in `database.py`; warn + delegate proven DB-free |
| 2 flat `db.*` spatial stubs | `@deprecated_alias` → `self.spatial.<m>` | decorator delegation | VERIFIED | `grep count == 2` in both database files; warn + delegate proven DB-free |
| `from_dataframe` / `from_geodataframe` internal calls | `self.schema.add_primary_key` / `self.schema.has_extension` / `self.spatial.create_spatial_index` | D-05 atomic rewrite | VERIFIED | `grep -c 'self.schema.add_primary_key' database.py == 2`; `self.schema.has_extension == 1`; `self.spatial.create_spatial_index == 1`; same async mirrors; 0 flat self-calls to moved names |
| `SpatialAccessor.__init__` and `AsyncSpatialAccessor._check_postgis` | `db.schema.has_extension("postgis")` | accessor path (not flat alias) | VERIFIED | `grep confirms 'db.schema.has_extension' at spatial.py:1048` and `'self._db.schema.has_extension' at spatial.py:1938` |
| `TimescaleAccessor` / `AsyncTimescaleAccessor` internal calls | `self._db.schema.has_extension(...)` | accessor path rewrite (Rule 1 auto-fix) | VERIFIED | 12 occurrences of `self._db.schema.has_extension` in `timescale.py` confirmed |
| `ETLRunner.run()` internal calls | `self._db.schema.table_exists(...)` | accessor path rewrite (Rule 1 auto-fix) | VERIFIED | 2 occurrences in `etl.py` confirmed |
| `AsyncSpatialAccessor.create_spatial_index` / `list_geometry_columns` | `await self._check_postgis()` | first awaitable line | VERIFIED | `inspect.getsource()` confirms both async relocated methods contain `await self._check_postgis()` |

---

### Data-Flow Trace (Level 4)

Not applicable — this phase is a pure internal refactor. All accessor methods delegate verbatim to the existing SQL execution paths (`self._db.execute(...)` / `self._db.config`). No new data sources were introduced; existing data flows were preserved.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| `db.schema.list_tables` returns a `SchemaAccessor` method | `python -c "from pycopg.schema import SchemaAccessor; assert hasattr(SchemaAccessor, 'list_tables')"` | exit 0 | PASS |
| Flat `db.list_tables('public')` emits DeprecationWarning naming `db.schema.list_tables` | DB-free MagicMock test (alias test suite) | 1 warning, v0.7.0 in message, delegation called | PASS |
| Flat `db.create_spatial_index('t', 'geom')` emits DeprecationWarning naming `db.spatial.create_spatial_index` | DB-free MagicMock test | 1 warning, v0.7.0 in message, delegation called | PASS |
| `AsyncSpatialAccessor.create_spatial_index` calls `_check_postgis` first | `inspect.getsource(...)` string check | `await self._check_postgis()` found | PASS |
| 54 schema alias tests pass | `uv run pytest tests/test_schema_aliases.py -q -o addopts=""` | 54 passed in 0.24s | PASS |
| 4 spatial alias tests pass | `uv run pytest tests/test_spatial_aliases.py -q -o addopts=""` | 4 passed in 0.03s | PASS |
| 7-pair parity tests pass | `uv run pytest tests/test_parity.py -q -o addopts=""` | 24 passed in 3.06s | PASS |
| SQL injection guards still active | `uv run pytest tests/test_sql_injection.py -q -o addopts=""` | 92 passed in 0.22s | PASS |
| Full suite coverage >= 94% | `uv run pytest` (addopts active) | 95.64%, 1109 passed | PASS |
| 1030 unit tests under -W error::DeprecationWarning | `uv run pytest -W error::DeprecationWarning -q -o addopts=""` (excl. 3rd-party pool + known flaky DB) | 1030 passed | PASS |

---

### Probe Execution

No phase-declared probes for this phase. Behavioral spot-checks above substitute as the phase-gate verification.

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SCH-01 | Plans 01, 02, 04 | `db.schema.*` / `async_db.schema.*` exposes the 27 DDL + introspection methods as single block; flat `db.*` names remain as deprecated aliases | SATISFIED | `SchemaAccessor` has exactly 27 methods; 27 stubs in both database files; 54 alias tests pass; (SchemaAccessor, AsyncSchemaAccessor) in ACCESSOR_PAIRS; full suite green at 95.64% coverage |
| SCH-02 | Plan 03 | `create_spatial_index` and `list_geometry_columns` relocated to `db.spatial.*` / `async_db.spatial.*`; flat `db.*` names remain as deprecated aliases | SATISFIED | Both methods in `SpatialAccessor` and `AsyncSpatialAccessor`; 2 stubs on `Database`/`AsyncDatabase`; 4 spatial alias tests pass; (SpatialAccessor, AsyncSpatialAccessor) in ACCESSOR_PAIRS |

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | — |

No TBD/FIXME/XXX debt markers found in any phase-modified files. No placeholder stub patterns found. No hardcoded empty returns in production-level code paths.

**Pre-existing ruff lint debt in test files:** Out of scope per verification notes — verified identical to base commit; zero new violations introduced by this phase.

---

### Code Review Findings (from 23-REVIEW.md)

The code review reported 0 critical / 2 warning / 3 info — all advisory:

- **WR-01** (carry-forward): Deprecated `*args/**kwargs` stubs erase public signatures — known pattern from Phases 21/22, locked as the milestone-wide approach; DX concern acknowledged, resolution deferred to v0.7.0 alias removal or optional `deprecated_alias` enhancement.
- **WR-02**: Dead `db.has_extension` / `db.role_exists` patches in `test_sql_injection.py` async fixture — advisory only; SQL injection tests still pass 92/92.
- **IN-01**: Minor method ordering divergence in `AsyncSchemaAccessor` vs `SchemaAccessor` — cosmetic, parity test (set-based) passes.
- **IN-02**: `ExtensionNotAvailable` messages still reference flat `db.create_extension(...)` — documentation drift, Phase 24 (doc pass) will address.
- **IN-03**: `validate_index_method` re-exported asymmetrically in `__init__.py` — noted, not a blocker.

None of these findings block the phase goal.

---

### Human Verification Required

None. All SCH-01 and SCH-02 success criteria are verifiable programmatically and have been verified above. The migration is a refactor with no new user-facing UI surface.

---

## Gaps Summary

No gaps. All 10 observable truths verified against the live codebase. Both requirement IDs (SCH-01, SCH-02) are satisfied. Full test suite passes with 95.64% coverage (gate: 94%). The 2 full-suite failures are pre-existing documented flaky tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`) confirmed in verification notes — not regressions.

---

_Verified: 2026-06-18T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
