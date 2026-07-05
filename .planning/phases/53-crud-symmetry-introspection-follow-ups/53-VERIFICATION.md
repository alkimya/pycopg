---
phase: 53-crud-symmetry-introspection-follow-ups
verified: 2026-07-05T08:12:06Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 53: CRUD Symmetry + Introspection Follow-ups Verification Report

**Phase Goal:** The flat transactional core gains its missing predicate-read and single-row-insert siblings, and `db.schema.*` completes its existence-check and size-introspection families.
**Verified:** 2026-07-05T08:12:06Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can read rows by predicate via `select_where`/`find` returning `list[dict]`, accepting dict-equality WHERE and raw `where_sql`/`where_params` escape hatch through `QueryMixin._resolve_predicate` | ✓ VERIFIED | `pycopg/database.py:1314` (`select_where`), `:1404` (`find`, real concrete delegating def); identical async mirrors at `pycopg/async_database.py:1150`/`:1240`. Body composes `_resolve_predicate` → `_build_select_sql` → `fetch_all` exactly as specified. Live-DB tests pass: `test_select_where_dict_filters`, `test_select_where_no_predicate_returns_all_rows`, `test_select_where_order_by_limit_offset`, `test_select_where_via_where_sql` (+ async mirrors) — all green under `PGDATABASE=pycopg_test3`. |
| 2 | User can read a single matching row via `get`/`find_one` returning `dict \| None`, same predicate surface, forced server-side `LIMIT 1`, no raise on >1 match | ✓ VERIFIED | `pycopg/database.py:1462` (`get`), `:1538` (`find_one`); async mirrors `async_database.py:1298`/`:1374`. `limit=1, offset=None` hardcoded into `_build_select_sql` call; no `limit`/`offset` params in signature (D-05 confirmed by source inspection). Live-DB test `test_get_multi_match_returns_one_no_exception` (+ async) seeds 3 matching rows and asserts exactly one returned, no exception, deterministic via `order_by`. |
| 3 | Single-row insert helper (CRUD-F06) lands on both Database and AsyncDatabase with `RETURNING *` → `dict \| None` and raw-passthrough `on_conflict` | ✓ VERIFIED | `pycopg/database.py:1015` `insert`, `pycopg/async_database.py:2262` `async insert`. Body: `_build_insert_sql` + `RETURNING *` + `cursor.execute`/`fetchone`, no conflict-column computation (grep confirms no `conflict_columns`/`update_columns` in `insert`'s body). Empty-row guard (`if not row: raise ValueError`) present per WR-01 fix. Live-DB tests: `test_insert_returns_row_dict`, `test_insert_on_conflict_do_nothing_conflicting_row_returns_none` (asserts `None` + pre-existing row untouched), `test_insert_on_conflict_do_nothing_non_conflicting_row_returns_dict` (+ async mirrors) all pass. |
| 4 | `db.schema.*` gains `column_exists` + `table_size` on both `SchemaAccessor` and `AsyncSchemaAccessor` | ✓ VERIFIED | `pycopg/schema.py:354` `column_exists` (mirrors `table_exists`, binds 3 values as `%s`, no `validate_identifiers` call — safe by parameterization, D-08), `:501` `table_size` (guards via `validate_identifiers` + `table_exists` check, raises `TableNotFoundError`, reuses `queries.TABLE_SIZE` — no duplicate constant; `grep -c "TABLE_SIZE = "` confirms 1 definition). Async mirrors at `:1311`/`:1411`. New `queries.COLUMN_EXISTS` constant at `queries.py:63` (3-value bind, no identifier interpolation). Live-DB tests: `test_column_exists_true/false`, `test_table_size_positive_for_populated_table`, `test_table_size_missing_raises_table_not_found` (+ async mirrors) all pass. |
| 5 | KIND-parity (sync/async), `validate_identifiers` on all identifiers, zero new external deps, all standing-bar gates green | ✓ VERIFIED | `test_crud_v120_surface` + `test_crud_v120_kind_parity` (added per WR-03 fix, `tests/test_parity.py:158/195`) and `test_schema_v120_surface` (`:316`) all pass (3/3 `-k v120`). Full suite: 2406 passed/2 skipped @ 96.83% coverage (>=95% ratchet) under `PGDATABASE=pycopg_test3`. `mypy --strict`: 0 errors/18 files. `ruff check pycopg tests`: clean. `interrogate`: 100%. `sphinx-build -W`: clean. No new dependencies added (grep of diffs shows stdlib/psycopg only). |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pycopg/database.py` | `select_where`, `find`, `get`, `find_one`, `insert` | ✓ VERIFIED | All 5 present, substantive (full docstrings + logic), wired to `_resolve_predicate`/`_build_select_sql`/`_build_insert_sql`/`fetch_all`/`fetch_one`/`cursor()`. |
| `pycopg/async_database.py` | async mirrors of all 5 | ✓ VERIFIED | Byte-for-byte structural mirror of sync (`await` variants), confirmed by direct read. |
| `pycopg/schema.py` | `column_exists`, `table_size` on `SchemaAccessor`/`AsyncSchemaAccessor` | ✓ VERIFIED | All 4 present (2 sync-class methods × sync/async accessor), wired to `queries.COLUMN_EXISTS`/`queries.TABLE_SIZE` + `TableNotFoundError` guard. |
| `pycopg/queries.py` | `COLUMN_EXISTS` constant | ✓ VERIFIED | Present at line 63, 3-value `%s` bind against `information_schema.columns`; no duplicate `TABLE_SIZE` constant added (still exactly 1 definition). |
| `tests/test_sql_injection.py` | identifier + where_sql + order_by + insert + column_exists/table_size injection tests | ✓ VERIFIED | `TestSelectWhereFindIdentifierInjection`, `TestGetFindOneIdentifierInjection`, `TestInsertIdentifierInjection`, `TestColumnExistsValueInjection`, `TestTableSizeIdentifierInjection`, `TestOrderByEscapeHatch` all present and passing (153/153 in targeted run). |
| `tests/test_database_integration.py` | live-DB behavioral tests for all 5 phase requirements | ✓ VERIFIED | `TestSelectWhereGetIntegration`, `TestInsertSingleRowIntegration`, `TestColumnExistsTableSizeIntegration` — 29/29 passing under `PGDATABASE=pycopg_test3`. |
| `tests/test_parity.py` | `test_crud_v120_surface`, `test_crud_v120_kind_parity`, `test_schema_v120_surface` | ✓ VERIFIED | All 3 present and passing; full parity suite 44/44 passing. |
| `docs/api-reference.md` + `README.md` | doc rows for all 7 new symbols | ✓ VERIFIED | `select_where`/`column_exists`/`table_size`/`insert` all present in api-reference.md CRUD/Introspection v1.2.0 tables; README usage examples added. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `database.py::select_where` | `_resolve_predicate` + `_build_select_sql` + `fetch_all` | compose then delegate | ✓ WIRED | Source confirms exact composition chain, both sync + async. |
| `database.py::get` | `_build_select_sql(limit=1)` + `fetch_one` | forced LIMIT 1 | ✓ WIRED | `limit=1, offset=None` hardcoded, `fetch_one` called. |
| `database.py::insert` | `_build_insert_sql` + `RETURNING *` + `cursor.fetchone` | build, append, bind, fetchone | ✓ WIRED | Confirmed; no `conflict_columns`/`update_columns` (correctly skipped per D-06). |
| `schema.py::column_exists` | `queries.COLUMN_EXISTS` | `self._db.execute(...); len(result) > 0` | ✓ WIRED | Confirmed exact pattern. |
| `schema.py::table_size` | `table_exists` guard + `queries.TABLE_SIZE` | raise `TableNotFoundError` if missing; execute; `int(result[0]["size"])` | ✓ WIRED | Confirmed exact pattern, both sync + async. |

### Behavioral Spot-Checks / Live Execution

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full quick suite (unit + injection + parity) | `PGDATABASE=pycopg_test3 uv run pytest tests/test_database.py tests/test_async_database.py tests/test_sql_injection.py tests/test_parity.py -q -o addopts=""` | 825 passed | ✓ PASS |
| Full suite w/ coverage | `PGDATABASE=pycopg_test3 uv run pytest -q` | 2406 passed, 2 skipped, cov 96.83% | ✓ PASS |
| mypy strict | `uv run mypy pycopg` | 0 errors/18 files | ✓ PASS |
| ruff | `uv run ruff check pycopg tests` | clean | ✓ PASS |
| interrogate | `uv run interrogate -c pyproject.toml pycopg` | 100.0% | ✓ PASS |
| Sphinx | `uv run sphinx-build -W -b html docs docs/_build/html` | clean build | ✓ PASS |
| Targeted live-DB integration (3 phase-53 test classes) | `PGDATABASE=pycopg_test3 uv run pytest tests/test_database_integration.py -q -o addopts="" -k "TestSelectWhereGetIntegration or TestInsertSingleRowIntegration or TestColumnExistsTableSizeIntegration"` | 29 passed | ✓ PASS |
| WR-01/WR-02 review-fix regression tests | `-k "test_insert_empty_row_raises_before_db_round_trip or negative_limit or negative_offset"` | 12 passed | ✓ PASS |

Note: the default `pycopg_test`/`pycopg_test2` databases are known-broken (TimescaleDB `.so` drift, documented project issue) — running without `PGDATABASE=pycopg_test3` produces 38 unrelated failures/4 errors in pre-existing (non-Phase-53) tests. This is expected per project memory and not a Phase 53 regression; all Phase 53-relevant tests pass cleanly under the documented `PGDATABASE=pycopg_test3` convention.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| CRUD-F04 | 53-01 | `select_where`/`find` predicate reads | ✓ SATISFIED | Verified above (Truth 1) |
| CRUD-F05 | 53-01 | `get`/`find_one` single-row reads | ✓ SATISFIED | Verified above (Truth 2) |
| CRUD-F06 | 53-02 | single-row `insert` | ✓ SATISFIED | Verified above (Truth 3) |
| INTRO-F03 | 53-03 | `column_exists` | ✓ SATISFIED | Verified above (Truth 4) |
| INTRO-F04 | 53-03 | `table_size` | ✓ SATISFIED | Verified above (Truth 4) |

No orphaned requirements — REQUIREMENTS.md maps exactly these 5 IDs to Phase 53, all present in plan frontmatter, all marked Complete in REQUIREMENTS.md and confirmed here.

### Anti-Patterns Found

None. Scanned `pycopg/database.py`, `pycopg/async_database.py`, `pycopg/schema.py`, `pycopg/queries.py` (all phase-53-modified source files) for `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER`/"not yet implemented" — zero matches. Code-review (53-REVIEW.md) found 0 critical, 3 warnings (all fixed and verified via passing regression tests: WR-01 empty-row guard, WR-02 negative limit/offset guard, WR-03 kind-parity test), 2 info (both explicitly out-of-scope/acceptable design notes, not defects).

### Minor Documentation Note (non-blocking)

`.planning/ROADMAP.md` line 30 still shows the Phase 53 milestone-overview checkbox as `- [ ]` (unchecked) despite all 3 sub-plans being checked (`[x]`) and the phase-status table (line 127) correctly showing "Complete 3/3". This is the known recurring STATE/ROADMAP hand-enrichment drift documented in project memory (not a functional gap) — cosmetic only, does not affect goal achievement.

### Human Verification Required

None. All must-haves are verified programmatically via live-DB execution, unit tests, injection tests, parity tests, and direct source inspection.

### Gaps Summary

No gaps. All 5 roadmap success criteria are implemented, substantive (not stubs), fully wired to existing shared infrastructure (`_resolve_predicate`, `_build_select_sql`, `_build_insert_sql`, `validate_identifiers`), covered by passing live-DB integration tests (not just mocks), and documented. The 3 code-review warnings raised during the phase (empty-row insert guard, negative limit/offset guard, kind-parity test gap) were fixed in-phase and their fixes are independently verified here by re-running the regression tests they added. Standing-bar gates (coverage, mypy strict, ruff, interrogate, Sphinx, parity) are all green when run directly by this verifier, not merely claimed in SUMMARY.md.

---

*Verified: 2026-07-05T08:12:06Z*
*Verifier: Claude (gsd-verifier)*
