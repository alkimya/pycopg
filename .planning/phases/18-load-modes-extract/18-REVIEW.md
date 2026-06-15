---
phase: 18-load-modes-extract
reviewed: 2026-06-15T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - pycopg/etl.py
  - tests/test_etl_accessor.py
  - tests/test_etl.py
  - tests/test_sql_injection.py
findings:
  critical: 2
  warning: 5
  info: 4
  total: 11
status: issues_found
---

# Phase 18: Code Review Report

**Reviewed:** 2026-06-15
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the Phase 18 ETL `run()` body and the three new pure SQL builders
(`_build_insert_sql`, `_build_upsert_sql`, `_step_label`) in `pycopg/etl.py`,
plus the three test files. The SQL-injection defense for *identifier* surfaces
(table/schema/column/conflict/update columns) is solid: every f-string
interpolation in the builders and in the table-source extract path is preceded
by `validate_identifiers`, and the regression tests in
`tests/test_sql_injection.py::TestEtlIdentifierInjection` cover the payload set.
User *values* travel only as `%s`/`:lim` bound parameters. Transaction
atomicity for replace (TRUNCATE+INSERT inside one `db.transaction()`) and
run-log isolation (autocommit connections) are correctly structured and proven
by integration tests.

However, two correctness defects exist that produce wrong SQL / wrong recorded
metrics on legitimate, in-contract inputs, plus several robustness gaps in the
extract and load paths. Details below.

## Critical Issues

### CR-01: `_build_upsert_sql` emits invalid SQL when every column is a conflict column

**File:** `pycopg/etl.py:400-411`
**Issue:** `update_columns` defaults to all columns NOT in `conflict_columns`:
```python
columns = list(rows[0].keys())
if update_columns is None:
    update_columns = [c for c in columns if c not in conflict_columns]
```
When the extracted rows contain *only* the conflict-key columns (a common
single-key dedup case, e.g. `SELECT DISTINCT id FROM src` upserted on
`conflict_columns=["id"]`), `update_columns` is `[]`. Then:
```python
update_str = ", ".join(...)  # -> ""
on_conflict = f"({conflict_str}) DO UPDATE SET {update_str}"  # -> "(id) DO UPDATE SET "
```
This produces `... ON CONFLICT (id) DO UPDATE SET ` — a syntax error that
crashes at execute time inside the load transaction. The intended Postgres
form for "insert or ignore" is `ON CONFLICT (...) DO NOTHING`. There is no
guard and no test for the empty-`update_columns` case.

**Fix:**
```python
if update_columns is None:
    update_columns = [c for c in columns if c not in conflict_columns]

validate_identifiers(*conflict_columns)
validate_identifiers(*update_columns)

conflict_str = ", ".join(conflict_columns)
if update_columns:
    update_str = ", ".join(f"{c} = EXCLUDED.{c}" for c in update_columns)
    on_conflict = f"({conflict_str}) DO UPDATE SET {update_str}"
else:
    on_conflict = f"({conflict_str}) DO NOTHING"
```

### CR-02: `rows_loaded` is wrong for multi-row INSERT and is recorded as 0 on replace

**File:** `pycopg/etl.py:764-767`, `780`
**Issue:** Two related defects in the loaded-row accounting:

1. `cur.rowcount` after a single batched multi-row `INSERT ... VALUES (...),(...)`
   reflects the number of rows affected by that one statement. For the
   **replace** path, the `cur.execute(truncate_sql)` runs first; `TRUNCATE`
   sets `rowcount` to `-1` (no row count) on psycopg, but the subsequent
   `cur.execute(insert_sql, insert_params)` overwrites `rowcount`, so replace
   itself is fine. The real problem is the **append/upsert** vs **replace**
   asymmetry combined with the `+=` on a fresh `rows_loaded = 0`: the value is
   never reset between the build and the load, and on the **failure path**
   (`except` block, line 770-777) `_end_run(... rows_loaded=0 ...)` is always
   passed literal `0` even if the truncate succeeded — acceptable, but the
   success path relies entirely on `cur.rowcount`.

2. More concretely: for an **upsert** that updates existing rows,
   `ON CONFLICT DO UPDATE` reports each affected row, but a `DO NOTHING`
   (after CR-01 fix) reports only the inserted rows — so `rows_loaded` will
   silently under-count. The recorded metric is therefore mode-dependent and
   undocumented. Given `rows_loaded` is the headline run-log metric (asserted
   in `test_rows_extracted_recorded`), an incorrect count is a data-integrity
   defect for the tracking table.

   The most defensible behavior is to record the number of rows the pipeline
   *intended* to load (`len(rows)`), which is deterministic and matches
   `rows_extracted` semantics, rather than the driver-reported `rowcount`
   that varies by mode and conflict outcome.

**Fix:**
```python
with self._db.session():
    with self._db.transaction() as conn:
        with conn.cursor() as cur:
            if pipeline.load_mode == "replace":
                cur.execute(truncate_sql)
            cur.execute(insert_sql, insert_params)
rows_loaded = len(rows)  # deterministic; independent of ON CONFLICT outcome
```
(If driver `rowcount` semantics are genuinely desired, document the
mode-dependence explicitly and add tests for the upsert-update and
DO-NOTHING cases.)

## Warnings

### WR-01: Failed run row hard-codes `rows_loaded=0`, masking a partially-applied replace count

**File:** `pycopg/etl.py:769-778`
**Issue:** On any exception the run row is finalized with `rows_loaded=0`.
Because the load is atomic this is *usually* correct (the txn rolled back), but
the `_end_run` call itself runs on a dedicated autocommit connection and can
raise (e.g. transient connection loss). If `_end_run` raises inside the
`except`, the original exception is masked by the `_end_run` failure and the
`raise` at line 778 never executes — the caller sees a connection error, not
the real ETL failure, and no `failed` row is recorded.

**Fix:** Wrap the run-log finalization so the original error is always
re-raised even if logging fails:
```python
except Exception:
    try:
        self._end_run(run_id, "failed", rows_extracted, 0,
                      error_message=str(exc), error_traceback=traceback.format_exc())
    except Exception:
        logger.exception("failed to record failed run row for run_id=%s", run_id)
    raise
```

### WR-02: `_build_upsert_sql` assumes `rows` is non-empty (`rows[0]`) with no guard

**File:** `pycopg/etl.py:400`
**Issue:** `columns = list(rows[0].keys())` raises `IndexError` on an empty
`rows` list. `run()` guards this at line 708 (`if not rows: ... return`), but
`_build_upsert_sql` and `_build_insert_sql` are documented module-level
builders that are independently unit-tested and may be reused. `_build_insert_sql`
degrades to `VALUES ` (empty) on empty rows — also invalid SQL — while
`_build_upsert_sql` raises `IndexError`. Neither has a guard or a test for the
empty-rows case.

**Fix:** Add an explicit guard at the top of each builder:
```python
if not rows:
    raise ValueError("rows must be non-empty")
```

### WR-03: Conflict columns are not verified to be a subset of the row columns

**File:** `pycopg/etl.py:741-747`, `400-409`
**Issue:** `_build_upsert_sql` validates that each `conflict_column` is a legal
identifier but never checks it is actually present in `rows[0].keys()`. A
conflict column absent from the extracted columns (typo or schema drift)
produces `ON CONFLICT (missing_col) ...` that fails at execute time with a
confusing Postgres error rather than a clear pipeline-level message. This is a
correctness/usability gap given `conflict_columns` is user-supplied at
`Pipeline` construction and not cross-checked against the extract.

**Fix:** After deriving `columns`, validate membership:
```python
missing = [c for c in conflict_columns if c not in columns]
if missing:
    raise ValueError(f"conflict_columns not present in extracted rows: {missing}")
```

### WR-04: SQL-source extract wraps arbitrary user SQL with no statement-shape check

**File:** `pycopg/etl.py:650-660`
**Issue:** When `_is_sql_source(pipeline.source)` is true and `extract_limit`
is set, the source is interpolated as
`SELECT * FROM ({pipeline.source}) AS _etl_sub LIMIT :lim`. The `source` is
documented as caller-provided SQL, so this is not an external-injection
vector. However, `_is_sql_source` is a *heuristic* (any string containing a
space is treated as SQL — see `test_string_with_whitespace_is_sql`). A table
name that legitimately contains a space-like payload, or a malformed source,
silently becomes a subquery. More importantly, a multi-statement source
(`"SELECT 1; DROP TABLE x"`) would be wrapped into an invalid subquery rather
than rejected — the failure mode is opaque. Consider validating that the
source is a single SELECT/WITH statement, or documenting that `source` is a
trusted/privileged input.

**Fix:** Document the trust boundary on `Pipeline.source` explicitly, and/or
reject sources containing `;` outside string literals before wrapping.

### WR-05: `to_dataframe`/`from_dataframe` extract+autocreate run on the SQLAlchemy engine, outside the load session

**File:** `pycopg/etl.py:651-676`, `727-732`, `761-762`
**Issue:** The atomic load block opens `db.session()` + `db.transaction()` so
TRUNCATE+INSERT share one connection. But the **extract** (`to_dataframe`),
the **existence check** (`table_exists` -> `self.execute`), and the **replace
auto-create** (`from_dataframe`, line 727) all run on the SQLAlchemy engine /
fresh pooled connections *before and outside* that session. For the replace
path this means the auto-created empty table is committed on a separate
connection before the load transaction begins; if the subsequent load
transaction fails, the empty table is left behind (a side effect the run-log
will report as `failed`). This is arguably acceptable per D-03a, but it is an
externally visible state mutation that is NOT covered by the atomicity
guarantee advertised in the `run()` docstring ("makes the replace
TRUNCATE+INSERT atomic"). The auto-create is outside that boundary.

**Fix:** Either move the auto-create inside the load transaction (using a
builder-produced CREATE TABLE), or document that replace auto-create of a
missing target is a non-transactional precursor step.

## Info

### IN-01: `traceback.format_exc()` stored verbatim into the run log

**File:** `pycopg/etl.py:776`
**Issue:** Full tracebacks (which can include local file paths, and in some
deployments fragments of values) are persisted to `pipeline_runs.error_traceback`.
This is intended (D-14) but worth flagging: the run-log table inherits the
data-sensitivity of whatever the pipeline processes. No action required unless
the table is exposed to lower-privilege readers.

### IN-02: `_step_label` docstring says "callable" but annotates `fn: object`

**File:** `pycopg/etl.py:414`, `428`
**Issue:** The signature is `_step_label(fn: object)` while the Parameters
section documents `fn : callable`. Minor doc/annotation mismatch. Prefer
`fn: Callable` for consistency with the rest of the module.
**Fix:** Change annotation to `Callable` (already imported).

### IN-03: `# noqa: F401` re-export of `ETLTransformError`/`ETLTargetNotFoundError`

**File:** `pycopg/etl.py:37`
**Issue:** Both exceptions are imported with `noqa: F401`; `ETLTargetNotFoundError`
and `ETLTransformError` are both actually raised in `run()`, so the `F401`
suppression for the *raised* ones is unnecessary noise. Only genuinely
re-exported-but-unused names need the suppression.
**Fix:** Drop `# noqa: F401` if both names are used in-module (they are).

### IN-04: Test fake `_FakeDatabase` does not model `commit`, so run-log isolation is only proven by live DB tests

**File:** `tests/test_etl_accessor.py:42-89`
**Issue:** The unit-level `_FakeDatabase` records `execute` calls but its fake
connection/cursor `__exit__` are no-ops with no commit modeling. The critical
ETL-08/ETL-09 isolation invariant is therefore exercised only by the
integration tests (`test_failed_run_commits_inside_session`), which require a
live Postgres. This is acceptable but means a CI run without a database gives
false confidence on the isolation property. No code change required; noted for
test-strategy awareness.

---

_Reviewed: 2026-06-15_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
