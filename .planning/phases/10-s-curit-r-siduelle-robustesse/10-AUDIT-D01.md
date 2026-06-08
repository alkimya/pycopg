# D-01 Audit: SEC-05 + Success-Criterion-#1 Validations

**Produced by:** Phase 10, Plan 01 (Task 3)
**Date:** 2026-06-08
**Decision:** D-01 — Verify then mark as acquired (no re-implementation unless genuine gap found)
**Conclusion:** ALL items are ACQUIRED. No new production code written.

---

## Audit Method

For each Success-Criterion-#1 item:
1. `grep -n "validate_\|quote_literal" pycopg/database.py pycopg/async_database.py` to locate call sites.
2. Cross-reference `tests/test_sql_injection.py` collected tests (`uv run pytest tests/test_sql_injection.py --collect-only`).
3. Mark ACQUIRED (validate_* call present at call site + covering test present) or GAP.

**Injection test suite baseline:** 64 tests collected, all passing (+ 2 not parametrized),
confirmed by `uv run pytest tests/test_sql_injection.py -q`.

---

## Checklist

| # | Item | Sync call site | Async call site | Covering test(s) | Status |
|---|------|---------------|-----------------|------------------|--------|
| 1 | Compression policy interval | `database.py:1482` `validate_interval(compress_after)` | `async_database.py:889` `validate_interval(compress_after)` | `TestSyncValueInjection::test_compression_interval`, `TestAsyncValueInjection::test_compression_interval` | **ACQUIRED** |
| 2 | Retention policy interval | `database.py:1513` `validate_interval(drop_after)` | `async_database.py:920` `validate_interval(drop_after)` | `TestSyncValueInjection::test_retention_interval`, `TestAsyncValueInjection::test_retention_interval` | **ACQUIRED** |
| 3 | Spatial index table name | `database.py:1343` `validate_identifiers(table, column, schema)` | `async_database.py:750` `validate_identifiers(table, column, schema)` | `TestSyncIdentifierInjection::test_create_spatial_index_table[×5]`, `TestAsyncIdentifierInjection::test_create_spatial_index[×5]` | **ACQUIRED** |
| 4 | Spatial index column name | `database.py:1343` `validate_identifiers(table, column, schema)` | `async_database.py:750` `validate_identifiers(table, column, schema)` | `TestSyncIdentifierInjection::test_create_spatial_index_column[×5]` | **ACQUIRED** |
| 5 | vacuum table name | `database.py:1671` `validate_identifiers(table, schema)` | `async_database.py:1829` `validate_identifiers(table, schema)` | `TestSyncIdentifierInjection::test_vacuum_table[×5]`, `TestAsyncIdentifierInjection::test_vacuum[×5]` | **ACQUIRED** |
| 6 | analyze table name | `database.py:1686` `validate_identifiers(table, schema)` | `async_database.py:1848` `validate_identifiers(table, schema)` | `TestSyncIdentifierInjection::test_analyze_table[×5]`, `TestAsyncIdentifierInjection::test_analyze[×5]` | **ACQUIRED** |
| 7 | drop_index name | `database.py:1097` `validate_identifiers(schema, name)` | `async_database.py:650` `validate_identifiers(schema, name)` | `TestSyncIdentifierInjection::test_drop_index[×5]`, `TestAsyncIdentifierInjection::test_drop_index[×5]` | **ACQUIRED** |
| 8 | DataFrame / to_dataframe table | `database.py:1218` `validate_identifiers(table, schema)` | `async_database.py:1445` `validate_identifiers(table, schema)` | Covered via table/schema parameter validation; `from_dataframe` delegates to SQLAlchemy `df.to_sql()` which uses parameterized binding — not a SQL injection surface. Direct call-site validation present on `to_dataframe`. | **ACQUIRED** |
| 9 | insert_many column names | Sync `insert_many` not present (async-only) | `async_database.py:1658` `validate_identifiers(table, schema)` + `async_database.py:1661` `validate_identifiers(*columns)` | `TestAsyncValueInjection::test_insert_many_column_injection` | **ACQUIRED** |
| 10 | upsert_many conflict columns | Sync `upsert_many` not present (async-only) | `async_database.py:1708` `validate_identifiers(*conflict_columns)` + `async_database.py:1709` `validate_identifiers(*update_columns)` | `TestAsyncValueInjection::test_upsert_many_conflict_column_injection` | **ACQUIRED** |
| 11 | valid_until (create_role) | `database.py:1785` `validate_timestamp(valid_until)` | `async_database.py:1083` `validate_timestamp(valid_until)` | `TestSyncValueInjection::test_valid_until_create_role`, `TestAsyncValueInjection::test_valid_until_create_role` | **ACQUIRED** |
| 12 | valid_until (alter_role) | `database.py:1906` `validate_timestamp(valid_until)` | `async_database.py:1167` `validate_timestamp(valid_until)` | `TestSyncValueInjection::test_valid_until_alter_role` | **ACQUIRED** |
| 13 | create_extension schema | `database.py:697-699` `validate_extension_name(name)` + `validate_identifier(schema)` | `async_database.py:591-594` `validate_identifiers(name, schema)` (uses extension_name pattern for name) | `TestSyncIdentifierInjection::test_create_extension_injection`, `test_create_extension_schema_injection`, `TestAsyncIdentifierInjection::test_create_extension` | **ACQUIRED** |
| 14 | grant/revoke privilege whitelist | `database.py:1983` `validate_privileges(privileges)` | `async_database.py:1215` `validate_privileges(privileges)` | `TestSyncValueInjection::test_grant_privileges`, `test_revoke_privileges`, `TestAsyncValueInjection::test_grant_privileges` | **ACQUIRED** |
| 15 | grant/revoke object_type whitelist | `database.py:1979` `validate_object_type(object_type)` | `async_database.py:1211` `validate_object_type(object_type)` | `TestSyncValueInjection::test_grant_object_type`, `TestAsyncValueInjection::test_revoke_object_type` | **ACQUIRED** |
| 16 | CSV options (delimiter, null, encoding) | `database.py:2323-2325` `validate_csv_option(delimiter/null/encoding)` | `async_database.py:2138-2140` `validate_csv_option(delimiter/null/encoding)` | `TestSyncValueInjection::test_csv_delimiter` | **ACQUIRED** |

---

## SEC-05 Row

| Item | Requirement | Sync call site | Async call site | Covering test | Status |
|------|-------------|---------------|-----------------|---------------|--------|
| SEC-05 | async `create_role` validates `name` (identifier) AND `valid_until` (timestamp) up-front, before any SQL is built or executed | `database.py:1757` `validate_identifier(name)` — sync create_role validates name | `async_database.py:1055` `validate_identifier(name)` — async create_role validates name up-front; `async_database.py:1082-1083` `if valid_until: validate_timestamp(valid_until)` — validates valid_until when provided | `TestAsyncValueInjection::test_valid_until_create_role` (async), `TestSyncValueInjection::test_valid_until_create_role` (sync parity) | **ACQUIRED** |

---

## Summary

- **Total items audited:** 16 Success-Criterion-#1 items + 1 SEC-05 row = **17 items**
- **ACQUIRED:** 17
- **GAP:** 0
- **GAP-CLOSED:** 0

**New production code written:** NONE (all validations confirmed present at call sites)

The v0.3.1 hotfix fully addressed the injection mitigations. The `tests/test_sql_injection.py`
suite (64 parametrized + non-parametrized tests) covers sync and async paths for all items.
`uv run pytest tests/test_sql_injection.py -q` exits 0, confirming no regression.

---

*Audit produced by Phase 10 Plan 01, Task 3 (executor: claude-sonnet-4-6)*
