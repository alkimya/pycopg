---
phase: 53-crud-symmetry-introspection-follow-ups
slug: crud-symmetry-introspection-follow-ups
status: verified
threats_total: 9
threats_closed: 9
threats_open: 0
asvs_level: 1
created: 2026-07-05
audited: 2026-07-05
---

# Phase 53 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register authored at plan time (union across 53-01/53-02/53-03 PLAN.md `<threat_model>` blocks). This audit **verifies each declared mitigation exists in the implemented code** — it does not scan blindly for new vulnerabilities.
>
> **Note on Threat IDs:** each of the 3 plans in this phase independently numbered its threats starting at `T-53-01`, so the raw IDs collide across plans. This register disambiguates by prefixing the originating plan (`53-01`/`53-02`/`53-03`) — e.g. `53-01/T-53-01` vs `53-02/T-53-01` are distinct threats covering distinct code paths (predicate reads vs. single-row insert).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|----------------|
| caller -> select_where/find/get/find_one SQL | table/schema/columns identifiers + dict-where keys are untrusted identifiers; where values/where_params are untrusted values; where_sql/order_by are caller-owned raw SQL text (trusted by contract) | identifiers (strings), bound values, raw SQL fragments |
| caller -> insert SQL | table/schema identifiers + row keys (column identifiers) are untrusted; row values are untrusted values; on_conflict is a caller-owned raw SQL fragment (trusted by contract, mirrors insert_many) | identifiers (strings), bound values, raw SQL fragment |
| caller -> column_exists / table_size | table/schema/column names are untrusted identifiers; column_exists binds them as %s values against information_schema.columns (no identifier interpolation); table_size validates name/schema then binds the qualified name as a %s text arg | identifiers (strings), bound values |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| 53-01/T-53-01 | Tampering | table/schema/columns identifiers on `select_where`/`find`/`get`/`find_one` | mitigate | `validate_identifiers` runs first inside `_build_select_sql` before any SQL executes | closed |
| 53-01/T-53-02 | Tampering | dict-where values + `where_params` on the reads | mitigate | user values bound as positional `%s` via `_resolve_predicate` -> `fetch_all`/`fetch_one`, never interpolated | closed |
| 53-01/T-53-03 | Tampering | `order_by`/`where_sql` raw-SQL escape hatches | accept | caller-owned raw SQL by design (same trust model as shipped `where_sql` on `count`/`delete_where`); documented in docstrings; dedicated non-rejection test proves the hatch is intentional | closed (accepted) |
| 53-02/T-53-01 | Tampering | table/schema/row-key (column) identifiers on `insert` | mitigate | `validate_identifiers` runs inside `_build_insert_sql` before any SQL executes | closed |
| 53-02/T-53-02 | Tampering | inserted row values | mitigate | values bound as positional `%s` in `row.keys()` order via `cursor.execute(sql, params)`, never interpolated | closed |
| 53-02/T-53-03 | Tampering | `on_conflict` raw-SQL passthrough | accept | caller-owned raw SQL by design (same trust model as `insert_many`/`upsert`'s `on_conflict`, D-06); documented in docstring | closed (accepted) |
| 53-03/T-53-01 | Tampering | table/schema/column identifiers on `column_exists` and `table_size` | mitigate | `column_exists` binds 3 values as `%s` vs `information_schema.columns` (never interpolated); `table_size` runs `validate_identifiers(name, schema)` first, then binds the qualified name as `%s` | closed |
| 53-03/T-53-02 | Tampering | bound catalog-query values | mitigate | all values passed as positional `%s` via `self._db.execute(CONST, [...])`, never interpolated | closed |
| 53-03/T-53-01b | Information Disclosure | `table_size` leaking psycopg `UndefinedTable` on a missing table | mitigate | existence guard raises the library's `TableNotFoundError` with a clean `'schema.table'` message before the size query runs — never leaks the raw driver error, never silently returns `0` | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Verification Evidence

| Threat ID | Evidence |
|-----------|----------|
| 53-01/T-53-01 | `pycopg/base.py:281-283` — `_build_select_sql` calls `validate_identifiers(table, schema)` then `validate_identifiers(*columns)` before building any SQL string; `select_where`/`get` (`pycopg/database.py:1393`/`:1527`, async mirrors `pycopg/async_database.py:1229`/`:1363`) delegate to it, `find`/`find_one` delegate to `select_where`/`get`. Test evidence: `tests/test_sql_injection.py:262` `TestSelectWhereFindIdentifierInjection` (table/schema/columns, sync+async) and `:313` `TestGetFindOneIdentifierInjection` (table/schema/columns, sync+async) — all parametrized over `EVIL_IDENTIFIERS`, all assert `InvalidIdentifierError`. |
| 53-01/T-53-02 | `pycopg/database.py:1306`/`1392`/`1526` (and async mirrors) — `frag, pred_params = self._resolve_predicate(where, where_sql, where_params)` then `self.fetch_all(sql, pred_params)` / `self.fetch_one(sql, pred_params)`; `_resolve_predicate` (`pycopg/base.py:329`) delegates dict-where to `_build_where_dict` (bound `%s` per key) and treats `where_sql`/`where_params` as verbatim fragment + bound values. Test evidence: `tests/test_sql_injection.py:565` `test_select_where_where_sql_params_bound_sync/_async` and `:602` `test_get_where_sql_params_bound_sync/_async` — assert the evil payload reaches `params` list, not the SQL text (`evil not in sql`). |
| 53-01/T-53-03 | `pycopg/database.py:1357-1361` (select_where docstring) and `:1505-1508` (get docstring) explicitly document `order_by` as a caller-owned raw-SQL escape hatch not run through `validate_identifiers`, mirroring the pre-existing `where_sql` trust model. Test evidence: `tests/test_sql_injection.py:639` `TestOrderByEscapeHatch` — `test_select_where_multi_column_order_by_not_rejected_sync/_async` and `test_get_multi_column_order_by_not_rejected_sync` prove `"a DESC, b ASC"` passes through verbatim (SQL text asserted byte-exact), demonstrating the hatch is intentional, not an oversight. |
| 53-02/T-53-01 | `pycopg/base.py:169-193` — `_build_insert_sql` calls `validate_identifiers(table, schema, *columns)` as its first statement (columns here = `row.keys()`, i.e. row-key identifiers). `insert` (`pycopg/database.py:1060`, async mirror `pycopg/async_database.py:2307`) calls `_build_insert_sql` before any `cursor.execute`. Test evidence: `tests/test_sql_injection.py:364` `TestInsertIdentifierInjection` — `test_insert_table_sync/_async`, `test_insert_schema_sync/_async`, `test_insert_row_key_sync/_async`, all parametrized over `EVIL_IDENTIFIERS`, all assert `InvalidIdentifierError`. |
| 53-02/T-53-02 | `pycopg/database.py:1062` (`params = [row[c] for c in columns]`) then `cur.execute(sql, params)` at `:1065`; identical shape async (`pycopg/async_database.py:2309`/`:2312`). Test evidence: `tests/test_database.py:966` `test_insert_returns_row` asserts `sql == "INSERT INTO public.t (a, b) VALUES (%s, %s) RETURNING *"` and `params == [1, 2]` — values never appear in the SQL text, only as bound params. |
| 53-02/T-53-03 | `pycopg/database.py:1039-1041` (insert docstring) documents `on_conflict` as threaded verbatim, mirroring `insert_many`'s trust model (D-06). Test evidence: `tests/test_database.py:980` `test_insert_threads_on_conflict` asserts the raw string `"DO NOTHING"` is threaded into the SQL text verbatim — an intentional escape hatch, proven by test not just claimed. `test_insert_no_conflict_columns_computed`/`test_insert_source_has_no_conflict_column_computation` (`:994`/`:1004`) additionally assert the source contains no `conflict_columns`/`update_columns` computation, confirming `on_conflict` is raw passthrough, not upsert-style column derivation. |
| 53-03/T-53-01 | `column_exists`: `pycopg/schema.py:371` (`result = self._db.execute(queries.COLUMN_EXISTS, [schema, table, column])`) — 3 positional binds, no string interpolation, mirrors `table_exists`'s pattern exactly; async mirror `pycopg/schema.py:1330`. `table_size`: `pycopg/schema.py:531` (`validate_identifiers(name, schema)`) runs before `table_exists` check and the size query; async mirror `pycopg/schema.py:1441`. Test evidence: `tests/test_sql_injection.py:404` `TestColumnExistsValueInjection` (asserts `evil not in sql` and `params == [...]` for table/schema/column positions, sync+async) and `:485` `TestTableSizeIdentifierInjection` (asserts `InvalidIdentifierError` for name/schema, sync+async). |
| 53-03/T-53-02 | Same call sites as above — `pycopg/queries.py:63-66` `COLUMN_EXISTS` constant uses 3 `%s` placeholders against `information_schema.columns`; `pycopg/queries.py:306-308` `TABLE_SIZE` (reused, not duplicated) uses 1 `%s` placeholder for the qualified `schema.name` string. Confirmed no duplicate size constant was added (`grep -c "^TABLE_SIZE " pycopg/queries.py` == 1 definition, `TABLE_SIZE_PRETTY`/`TABLE_SIZES` are pre-existing siblings, unrelated to this phase). |
| 53-03/T-53-01b | `pycopg/schema.py:531-535` — `table_size` guard: `validate_identifiers(name, schema)`; `if not self.table_exists(name, schema=schema): raise TableNotFoundError(f"Table '{schema}.{name}' does not exist.")`, guard runs strictly before `self._db.execute(queries.TABLE_SIZE, ...)`; async mirror `pycopg/schema.py:1441-1445`. Test evidence: `tests/test_database_integration.py:2248` `test_table_size_missing_raises_table_not_found` and `:2300` `_async` — live-DB proof that a nonexistent table raises the library's `TableNotFoundError`, not a raw psycopg `UndefinedTable`, and does not silently return `0`. |

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|--------------|------|
| AR-53-01 | 53-01/T-53-03 | `order_by`/`where_sql` on `select_where`/`find`/`get`/`find_one` are documented, intentional, caller-owned raw-SQL escape hatches — identical trust model to the pre-existing `where_sql` on `count`/`delete_where` (established Phase 50). Not run through `validate_identifiers` by design (multi-column `ORDER BY` syntax cannot otherwise be expressed). Disclosed in numpydoc docstrings on all 4 methods (sync+async) and proven non-accidental by a dedicated `TestOrderByEscapeHatch` test class that asserts the hatch is NOT rejected. | User (via plan-time threat register, 53-01 `<threat_model>`) | 2026-07-05 |
| AR-53-02 | 53-02/T-53-03 | `insert`'s `on_conflict=` is a documented, caller-owned raw-SQL passthrough — identical trust model to the shipped `insert_many`/`upsert` `on_conflict` parameter (established Phase 33/50). Values inside a `DO UPDATE` clause remain the caller's own responsibility to parameterize. Disclosed in numpydoc docstring and proven intentional (not accidental) by `test_insert_threads_on_conflict`. | User (via plan-time threat register, 53-02 `<threat_model>`) | 2026-07-05 |

*Accepted risks do not resurface in future audit runs.*

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|----------------|--------|------|--------|
| 2026-07-05 | 9 | 9 | 0 | gsd-security-auditor |

---

## Unregistered Flags

None. All 3 phase summaries (`53-01-SUMMARY.md`, `53-02-SUMMARY.md`, `53-03-SUMMARY.md`) report `## Threat Flags: None` — each executor confirmed the plan-time threat register fully covered the new surface it implemented, with no new trust boundary introduced beyond what was anticipated at plan time. Verified directly by reading each SUMMARY's `## Threat Flags` section, not taken on faith from the register note.

Additional note (informational, not a gap): `insert` carries a `ValueError` guard for an empty `row` dict (WR-01, `pycopg/database.py:1057-1058`) and `select_where`/`find` carry `ValueError` guards for negative `limit`/`offset` (WR-02, `pycopg/database.py:1384-1391`) — both are pre-existing code-review fixes (not part of the plan-time STRIDE register) that hedge against malformed-input footguns rather than injection; they don't require a new threat entry since they are not tampering/injection vectors, but are noted here for completeness.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-07-05
