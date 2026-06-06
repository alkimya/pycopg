# Deferred Items — Phase 09

## Pre-existing integration test failures (discovered by 09-02 CI run)

**CI run:** https://github.com/alkimya/pycopg/actions/runs/27070721343
**Discovered during:** Task 2 of plan 09-02 (CI validation)
**Scope:** Pre-existing — not caused by workflow changes

### Failures

7 tests in `tests/test_integration.py` and `tests/test_postgis_errors.py` fail because
the `test_schema.authors` table is not created in the CI database setup:

- `TestIntegration::test_authors_table` — `UndefinedTable: relation "test_schema.authors" does not exist`
- `TestIntegration::test_list_columns` — `AssertionError: assert 'id' in []`
- `TestIntegration::test_columns_with_types` — `KeyError: 'id'`
- `TestIntegration::test_transaction_rollback` — `UndefinedTable: relation "test_schema.authors" does not exist`
- `TestAsyncIntegration::test_async_transaction_fix` — `ProgrammingError: Explicit commit() forbidden within a Transaction context`
- `TestAsyncIntegration::test_async_list_columns` — `AssertionError: assert 'id' in []`
- `TestPostGISErrorHandling::test_create_spatial_index_name_parameter` — `UndefinedTable: relation "public.test_spatial_custom_name" does not exist`

### Impact

- Coverage gate passes (75.08% >= 70% required)
- Workflow configuration is correct (DB connected, PostGIS + TimescaleDB extensions loaded)
- These tests require additional DB schema setup beyond `CREATE DATABASE` + extensions

### Resolution

The integration tests need a fixtures SQL setup step that creates `test_schema`, the `authors` table,
and any test data. This is a pre-existing gap in the test infrastructure (no local CI setup existed before).
Resolution: Add a SQL fixtures step to `tests.yml` or create a `tests/fixtures.sql` file that sets up
the required test schema. Defer to a follow-up plan (outside Phase 09 scope which only adds the workflow).
