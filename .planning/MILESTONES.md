# Milestones

## v0.8.0 TimescaleDB avancé (Shipped: 2026-06-23)

**Phases completed:** 4 phases (30–33), 11 plans, 29 tasks

**Delivered:** A purely-additive TimescaleDB release that grows the `db.timescale.*` accessor surface from 6 to 15 methods (full sync/async parity). Three feature families: chunk management & partitioning (`show_chunks`, `drop_chunks` with both-None `ValueError` safety + `dry_run`, `add_dimension` by_hash/by_range, `add_reorder_policy`); the full continuous-aggregate lifecycle (`create`/`refresh` via the `connect(autocommit=True)` seam that bypasses an enclosing `db.session()`, plus `add_continuous_aggregate_policy`); and time-series query helpers (`time_bucket`, `time_bucket_gapfill` with `into="df"/"rows"` routing). Community/TSL-only operations (caggs, gapfill, reorder) tested two-layer — mock-authoritative SQL-shape + Apache-license-tolerant live integration. Shipped to PyPI under the held ≥94% coverage ratchet, zero new runtime dependencies.

**Key accomplishments:**

- TimescaleError exception + TSDB_SHOW_CHUNKS SQL constant (%%I.%%I regclass JOIN, range_start ASC) + tests/test_timescale.py with ts_db/async_ts_db skip-fixtures and 19 xfail Wave 0 stubs.
- show_chunks + drop_chunks on TimescaleAccessor + AsyncTimescaleAccessor with capture-before-drop, type-driven %s cast, both-None ValueError guard, and two-layer mock+live test coverage.
- add_dimension (by_hash/by_range D-06, construction-time ValueError D-07, dup-dim->TimescaleError D-08) + add_reorder_policy (mock-authoritative SQL + Apache-tolerant live test D-12) on both accessors; 46/46 test_timescale.py green; TS-ADV-10 parity confirmed.
- `create_continuous_aggregate` (sync + async) via `connect(autocommit=True)` seam with `time_bucket(` heuristic guard, mock-authoritative SQL-shape tests, and license-tolerant live integration tests.
- `refresh_continuous_aggregate` (sync + async) via `connect(autocommit=True)` seam with `datetime|None` type guard, `[None,None]`=full-refresh params, mock-authoritative SQL-shape tests, and license-tolerant live integration tests proving the seam bypasses an enclosing `db.session()`.
- `add_continuous_aggregate_policy` (sync + async) via plain `self._db.execute` (D-01) with `_check_offset_ordering` best-effort guard, `NULL`-for-None offsets, mock-authoritative SQL-shape tests, license-tolerant live integration tests, and the final 3-method `test_accessor_parity` confirmation.
- Sync + async `db.timescale.time_bucket` and `time_bucket_gapfill` query helpers with `into="df"/"rows"` routing, module-level pure SQL builders (fixed `AS bucket` alias, gapfill double-binding `start`/`finish`), and full TS-ADV-10 sync/async parity.
- Two-layer test coverage (mock SQL-shape + live integration) for `time_bucket` / `time_bucket_gapfill` plus an explicit 9-name v0.8.0 timescale surface parity assertion, holding the coverage ratchet at 95.11%.
- Version bumped to 0.8.0 in both canonical sources; CHANGELOG [0.8.0] Added-only entry written covering 9 new TimescaleDB methods grouped by the three feature families; lockfile regenerated.
- Rewrote timescaledb.md raw-SQL blocks to first-class `db.timescale.*` calls, added Advanced Chunk & Dimension Management section, extended api-reference.md with 9 new method rows, and bumped README to (15 methods) with compact v0.8.0 highlights.
- 4 quality gates green (coverage 95.11%, interrogate 100%, Sphinx -W clean, import green), 0.8.0 sdist+wheel built, OIDC publish to PyPI succeeded in 32s via human-gated GitHub Release, clean-venv smoke confirmed `__version__ == 0.8.0`

**Stats:**

- Lines changed: ~16,242 insertions, ~11,348 deletions across 124 files (incl. `.planning/`)
- Codebase: ~15,112 LOC lib (`pycopg/`)
- Timeline: 2026-06-22 → 2026-06-23 (~2 days), 99 commits in window, 13 `feat(` commits
- Gates at ship: coverage 95.11% (ratchet ≥94 held), interrogate 100%, Sphinx `-W` clean, zero DeprecationWarnings on import
- Git range: `v0.7.0` → tag `v0.8.0`

**Known deferred items at close:** 2 pre-existing flaky full-suite DB tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter` — fixture-isolation, not v0.8.0 code); stale `pycopg.aliases` Sphinx cross-reference in accessor docstrings (IN-01/IN-02 carry-forward, cosmetic); code-review warnings deferred across phases (WR-01 case-sensitive `time_bucket(` guard, WR-03 INTERVAL-literal-vs-`%s`, `%`-in-structural-SQL); TimescaleDB follow-ups TSDB-F01..F04 (cagg/policy removal, time_bucket origin/offset, compress/decompress, physical-time chunk filters) and incremental-ETL follow-ups ETL-INC-F01..F05 deferred to future milestones.

---

## v0.7.0 Alias Removal + Incremental ETL (Shipped: 2026-06-22)

**Phases completed:** 5 phases (25–29), 13 plans, 20 tasks

**Delivered:** A breaking-plus-additive release — the 56 deprecated flat aliases (one deprecation cycle served in v0.6.0) hard-removed from both `Database`/`AsyncDatabase` so the public surface is accessor-only, plus watermark-based incremental ETL via the new `Pipeline.incremental_column` field, wiring the `pipeline_runs.watermark JSONB` column reserved since v0.5.0 (no breaking migration). First run = full load + record `max(col)`; subsequent runs apply exclusive `WHERE col > watermark`; advances only on success, never writes NULL; full sync/async parity. Shipped to PyPI under the held ≥94% coverage ratchet, zero new runtime dependencies.

**Key accomplishments:**

- Hard-delete `pycopg/aliases.py` and 6 warn+delegate alias test files; add 114-test `test_alias_removal.py` proving all 56 removed flat names raise `AttributeError` on Database/AsyncDatabase plus WR-01 inspect assertions.
- Closed remaining IN-02 sites — 13 guard strings in spatial.py (1) and timescale.py (12) now reference `db.schema.create_extension`, and the stale alias-routing comment in test_sql_injection.py is corrected.
- MIGRATION.md v0.6→v0.7 section with 56-row removal table + CHANGELOG [0.7.0] Breaking entry + 10 stale flat-name code examples and 4 deprecation notes corrected across docs/
- DB-free incremental-ETL foundation in pycopg/etl.py: a validated `Pipeline.incremental_column` field, the `_build_incremental_extract_sql` watermark-filter builder (subquery-wrap or WHERE-append, watermark always a `%s` param), and the typed-JSONB-envelope `_encode_watermark`/`_decode_watermark` serializers — 5 new symbols, 34 co-located unit tests, zero new deps.
- Watermark persistence wired through sync run-log: _read_watermark + _end_run(watermark=) + max(col) capture with JSONB roundtrip proven for int/str/datetime via 6 live-DB tests
- Watermark filter loop closed sync-side: `_read_watermark` + `_build_incremental_extract_sql` + `_end_run(watermark=)` finally connected via shared `_do_extract()` helper; `RunResult` gains `watermark_used`/`watermark_recorded`; incremental `dry_run` applies identical filter and reports both fields without writing a run row
- Full async incremental watermark surface ported 1:1 from sync: `_read_watermark` + `_do_extract` + verbatim capture block + `dry_run` watermark fields, closing ETL-INC-11 (sync/async parity); `test_accessor_parity` green and unmodified
- `## Incremental loading` section added to `docs/etl.md` covering watermark-column requirements, upsert constraint, first-run vs subsequent-run semantics, `RunResult.watermark_used`/`watermark_recorded` field docs, `dry_run` preview behavior, and manual SQL backfill/reset workflow (D-A4, D-A5); Sphinx `-W` gate confirmed clean
- All 4 v0.7.0 quality gates green — pytest 95.11% coverage, interrogate 100%, Sphinx -W clean, zero DeprecationWarnings on import.
- pycopg 0.7.0 tagged, published to PyPI via OIDC trusted publishing, and verified via clean-venv pip install — REL-07 and Success Criterion 1 satisfied

**Stats:**

- Lines changed: ~2,860 insertions, ~1,959 deletions across ~31 code files (excl. `.planning/`)
- Codebase: ~13,327 LOC lib + ~15,690 LOC tests
- Timeline: 2026-06-19 → 2026-06-22 (~3 days), 96 commits in window
- Gates at ship: coverage 95.11% (ratchet ≥94 held), interrogate 100%, Sphinx `-W` clean, `-W error::DeprecationWarning` green
- Git range: `v0.6.0` → tag `v0.7.0`

**Known deferred items at close:** 2 pre-existing flaky full-suite DB tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter` — fixture-isolation, not v0.7.0 code) + one ~2.7% flaky bound-param test surfaced in Phase 28; Nyquist VALIDATION.md left `draft` for phases 22–24 (verified PASSED via VERIFICATION.md); incremental ETL follow-ups ETL-INC-F01..F05 (`initial_watermark`, configurable boundary, multi-column, advisory-lock concurrency, CDC) deferred to v0.8.0+. See STATE.md → Deferred Items.

---

## v0.6.0 Réorganisation en accessors (Shipped: 2026-06-19)

**Phases completed:** 4 phases (21–24), 13 plans, 24 tasks

**Delivered:** A pure internal refactor that regrouped ~56 flat methods on `Database`/`AsyncDatabase` into 5 new lazy accessors — `db.timescale.*`, `db.admin.*`, `db.maint.*`, `db.backup.*`, `db.schema.*` — and relocated the 2 spatial-index methods to `db.spatial.*`. Every old flat name keeps working as a backward-compatible deprecated alias (removal scheduled v0.7.0); zero breaking change. Shipped to PyPI under the held ≥94% coverage ratchet with full sync/async parity.

**Key accomplishments:**

- `@deprecated_alias` decorator (`pycopg/aliases.py`, sync + async) — the single shared warn-and-delegate mechanism for the whole deprecation cycle, making v0.7.0 alias removal a one-block deletion (D-SCOPE-2).
- 5 new lazy accessors carved from the monolith (`timescale` 6, `admin` 11, `maint` 6, `backup` 4, `schema` 27 methods) with all SQL bodies moved verbatim and security validators preserved; `create_spatial_index`/`list_geometry_columns` relocated to `db.spatial.*` for PostGIS thematic coherence.
- 56 backward-compatible flat aliases on each of `Database`/`AsyncDatabase` (112 stubs total) — zero breaking change for existing callers, all internal call-sites rewritten to route through accessors (no spurious user-facing warnings).
- Full sync/async parity enforced via a 7-pair `ACCESSOR_PAIRS` registry in `test_parity.py`; coverage held at 95.64% with per-alias warn+delegate tests and a green `-W error::DeprecationWarning` gate at 1030+ unit tests.
- Release wiring complete: 10 accessor classes in `__all__`, README Accessor Namespaces table, 5 Sphinx automodule blocks (green `-W` build), CHANGELOG `[0.6.0]`, 56-row v0.5→v0.6 MIGRATION guide; v0.6.0 tagged and published to PyPI via GitHub OIDC, clean-venv install smoke-tested.

**Known deferred items at close:** Nyquist VALIDATION.md left in `draft` (`nyquist_compliant: false`) for phases 22–24 (verified PASSED via VERIFICATION.md regardless — missing formal sign-off, not a coverage gap); carry-forward WR-01 (deprecated `*args/**kwargs` stubs erase IDE signatures — accepted milestone-wide, self-resolves at v0.7.0 alias removal). See STATE.md → Deferred Items.

---

## v0.5.0 ETL Pipeline Runner (Shipped: 2026-06-15)

**Phases completed:** 5 phases (16–20), 13 plans, 18 tasks

**Delivered:** A high-level ETL pipeline runner under `db.etl.*` / `async_db.etl.*` — inspectable `Pipeline` dataclass, run-tracking via `pipeline_runs`, three load modes, transform chains, a `RunResult` query surface, and full sync/async parity — shipped to PyPI under the held ≥94% coverage ratchet.

**Key accomplishments:**

- **Pure ETL layer (Phase 16):** `Pipeline` frozen dataclass with construction-time validation (D-01..D-11) + DB-free pure SQL builders (`build_init_sql`/`build_truncate_sql`) gated by `validate_identifiers`, mirroring `spatial.py`; ETL exception hierarchy (`ETLError`/`ETLTransformError`/`ETLTargetNotFoundError`) + 5 SQL constants; 31 DB-free tests.
- **Run-tracking foundation (Phase 17):** `ETLAccessor` (`init`/`run`/run-log helpers) wired as the lazy `db.etl` property; structural run-log isolation via a dedicated `db.connect(autocommit=True)` per write — run rows commit independently of the load transaction on every path, including an active `db.session()`.
- **Load modes & extract (Phase 18):** `append`/`replace`/`upsert` load modes with atomic loads, SQL-string and table-name sources, and single/list/None transform chains; failed transforms raise `ETLTransformError` and record a failed run.
- **Query surface (Phase 19):** `run()` returns an 8-field `RunResult` (via re-SELECT); `dry_run=True` runs extract+transform but writes no `pipeline_runs` row; `history()` and `last_run()` added as autocommit dict_row reads.
- **Async parity & release (Phase 20):** `AsyncETLAccessor` async mirror with transforms dispatched via `asyncio.to_thread`; lazy `async_db.etl` property; `TestEtlParity` enumerates the sync/async surface via `inspect.getmembers`; `docs/etl.md`; v0.5.0 tagged + published to PyPI via OIDC.

**Stats:**

- Lines changed: 15,458 insertions, 82 deletions across 69 files
- Timeline: 2026-06-14 → 2026-06-15 (~1.2 days), 22 feat/test commits
- Gates at ship: coverage 94.26% (ratchet ≥94 held), interrogate 100%, Sphinx `-W` clean
- Git range: feat(16-01) → tag v0.5.0

**Known deferred items:** 2 pre-existing flaky full-suite DB tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter` — `UndefinedTable` fixture-isolation in the spatial/integration suites, not ETL code; see STATE.md). Did not affect the coverage threshold.

---

## v0.4.0 Quality & Spatial Helpers (Shipped: 2026-06-14)

**Phases completed:** 7 phases (9–15), 36 plans, 62 tasks

**Delivered:** Full sync/async parity, PostGIS spatial helpers (`db.spatial.*`), numpydoc docs with an interrogate gate, residual security fixes, and a uv-based toolchain — shipped to PyPI + ReadTheDocs under a 94% coverage ratchet.

**Key accomplishments:**

- **uv toolchain (Phase 9):** PEP 735 dev groups + committed `uv.lock`/`.python-version`; CI test matrix (3.11/3.12/3.13) and publish both run under uv (`uv build`), hatchling backend + OIDC trusted publishing preserved.
- **Residual security & robustness (Phase 10):** closed B1 (pool commit-before-return), B2 (session close-on-commit-failure), B3 (atomic migration apply/rollback), B5 (os.environ), each with a red→green regression test; coverage ratchet → 80.
- **Full sync/async parity (Phase 11):** AsyncDatabase gained 9 missing methods (DDL constraints, admin, create/create_from_env); Database gained insert_many/upsert_many/stream/notify; C1/C2/C3 fixed; `test_parity` extended to real-DB behavior; ratchet → 90.
- **Refactoring — wired abstractions (Phase 12):** `Database`/`AsyncDatabase` now inherit `DatabaseBase`+`QueryMixin`; ~25 inline SQL strings replaced by `queries.py` constants; pure DB-free builders extracted; ratchet honestly flipped 90→92 (95 stretch deferred).
- **Documentation quality (Phase 13):** all public docstrings migrated to numpydoc; interrogate gate (≥95) + mypy in CI; real exception types (ExtensionNotAvailable/DatabaseExists); `__version__` via importlib.metadata.
- **Spatial helpers (Phase 14):** `pycopg/spatial.py` with geometry resolver + 11 pure PostGIS SQL builders + `SpatialAccessor`/`AsyncSpatialAccessor` at parity; PostGIS guard + `%s` parameterization; ratchet → 94.
- **Release (Phase 15):** Sphinx spatial docs + RTD green; CHANGELOG/MIGRATION/version bump 0.4.0; Node 24 CI action bumps; tag `v0.4.0` + PyPI publish via OIDC.

**Stats:**

- Codebase: 10,528 LOC Python (lib) + 11,228 LOC tests
- Coverage ratchet: 70 → 80 → 90 → 92 → 94 (measured 94.09%)
- Timeline: 9 days (2026-06-06 → 2026-06-14)
- Commits: ~163 in window; Git range: chore(09-01) → docs(audit) v0.4.0
- Audit: PASSED (46/46 requirements, 7/7 phases, 14/14 integration, 4/4 E2E flows)

---

## v0.3.0 Consolidation Release (Shipped: 2026-02-11)

**Phases completed:** 7 phases, 14 plans, 20 tasks

**Delivered:** Full AsyncDatabase/Database feature parity, critical bug fixes, production resilience, 72.76% test coverage, and complete documentation for pycopg v0.3.0.

**Key accomplishments:**

- Fixed 5 critical bugs: session cleanup leaks, transaction detection, migration logging, TimescaleDB validation, SRID inference
- Full AsyncDatabase parity: 30+ async methods (DataFrame, Admin, Backup, Roles, PostGIS, TimescaleDB)
- Production resilience: retry/backoff with tenacity, statement_timeout, configurable batch sizes, pool reconnection
- Test coverage from 23% to 72.76%: 60+ new tests including edge cases, pool stress, and automated parity verification
- Complete documentation: CHANGELOG, MIGRATION guide, updated README, rebuilt Sphinx API reference
- Version bumped to 0.3.0 across pyproject.toml and Sphinx configuration

**Stats:**

- Lines changed: 17,706 insertions, 38 deletions across 71 files
- Codebase: 13,648 LOC Python
- Timeline: 42 days (2026-01-01 → 2026-02-11)
- Commits: 77
- Git range: feat(01-01) → docs(phase-07)

---
