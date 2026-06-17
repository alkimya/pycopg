---
phase: 23
slug: schema-accessor-spatial-relocation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-17
---

# Phase 23 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (pytest-asyncio, `asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` (`addopts = "... --cov-fail-under=94"`, `-W error::DeprecationWarning` family of gates) |
| **Quick run command** | `uv run pytest tests/test_schema_aliases.py tests/test_spatial.py tests/test_parity.py -x -q -o addopts=""` |
| **Full suite command** | `uv run pytest` |
| **Estimated runtime** | ~60–120 seconds (full suite); alias/parity subset ~5–15s |

---

## Sampling Rate

- **After every task commit:** Run the quick run command (DB-free alias tests + parity + spatial run with no coverage gate).
- **After every plan wave:** Run the full suite command (enforces `--cov-fail-under=94` + the `-W error::DeprecationWarning` gate that catches missed internal self/caller rewrites).
- **Before `/gsd-verify-work`:** Full suite must be green (mind the 2 pre-existing flaky DB tests — `test_async_transaction_fix`, `test_create_spatial_index_name_parameter`; use `-o addopts=""` for targeted runs and confirm the spatial relocation does not change the latter's pre-existing flakiness profile).
- **Max feedback latency:** ~15 seconds (alias/parity subset).

---

## Per-Task Verification Map

> Plan/task IDs are the planner's call (D-02/D-03 separate schema track from spatial-reloc track). The map below is keyed by capability; the planner binds each row to concrete task IDs.

| Capability | Track | Requirement | Test Type | Automated Command | Secure/Correct Behavior |
|------------|-------|-------------|-----------|-------------------|-------------------------|
| `SchemaAccessor`/`AsyncSchemaAccessor` module created, 27 bodies moved verbatim (D-04 `self.X`→`self._db.X` rewrite) | schema | SCH-01 | unit | `uv run pytest tests/test_parity.py -q -o addopts=""` | All 27 methods present in both classes; `self.config`→`self._db.config` in the 3 DB-level methods |
| 27 lazy `db.schema.*` / `async_db.schema.*` properties + `_schema` cache + 27 `@deprecated_alias("schema.<m>")` stubs | schema | SCH-01 | unit | `uv run pytest tests/test_schema_aliases.py -q -o addopts=""` | Each stub emits `DeprecationWarning` at caller `stacklevel=2` and delegates to `db.schema.<m>` |
| `(SchemaAccessor, AsyncSchemaAccessor)` appended to `ACCESSOR_PAIRS` | schema | SCH-01 | unit | `uv run pytest tests/test_parity.py::test_accessor_parity -q -o addopts=""` | Sync/async accessor surfaces match |
| 2 spatial methods moved into `SpatialAccessor`/`AsyncSpatialAccessor` verbatim (D-07); async adds `await self._check_postgis()` (research finding #4) | spatial | SCH-02 | unit | `uv run pytest tests/test_spatial.py -q -o addopts=""` | `db.spatial.create_spatial_index` / `db.spatial.list_geometry_columns` work; D-06 guard semantics accepted |
| 2 `@deprecated_alias("spatial.<m>")` stubs on `db.*`/`async_db.*` | spatial | SCH-02 | unit | `uv run pytest tests/test_spatial.py -q -o addopts=""` (or `test_spatial_aliases.py`) | Old flat `db.create_spatial_index`/`db.list_geometry_columns` warn + delegate to `db.spatial.*` |
| `(SpatialAccessor, AsyncSpatialAccessor)` ADDED to `ACCESSOR_PAIRS` (research finding #3 — NOT already present) | spatial | SCH-02 | unit | `uv run pytest tests/test_parity.py::test_accessor_parity -q -o addopts=""` | Spatial pair now parity-checked |
| 8 stay-flat DataFrame call-sites rewritten to accessor paths (D-05) | both | SCH-01/SCH-02 | gate | `uv run pytest -W error::DeprecationWarning -q` | `from_dataframe`/`from_geodataframe` emit ZERO internal `DeprecationWarning` |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_schema_aliases.py` — DB-free MagicMock alias tests for all 27 schema stubs (warn + caller stacklevel + delegate), mirroring `tests/test_timescale_aliases.py` / `test_admin_aliases.py`.
- [ ] 2 spatial alias tests — extend `tests/test_spatial.py` or add `tests/test_spatial_aliases.py` (planner's call; follow existing spatial layout).
- [ ] No new framework install — pytest + pytest-asyncio already configured.

*Existing infrastructure (pytest, `ACCESSOR_PAIRS`, MagicMock alias template) covers all phase requirements; only the new test files above are needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| — | — | — | — |

*All phase behaviors have automated verification (alias tests, parity test, `-W error` gate, coverage ratchet).*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (new alias test files)
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s (alias/parity subset)
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
