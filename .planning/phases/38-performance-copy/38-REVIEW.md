---
phase: 38-performance-copy
reviewed: 2026-06-26T00:00:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - pycopg/database.py
  - pycopg/async_database.py
  - pycopg/etl.py
  - tests/test_async_database.py
  - tests/test_database_integration.py
  - tests/test_database.py
  - tests/test_etl_accessor.py
findings:
  critical: 2
  warning: 3
  info: 2
  total: 7
status: resolved
resolved_in: 863e894
---

# Phase 38: Code Review Report

**Reviewed:** 2026-06-26
**Depth:** standard
**Files Reviewed:** 7
**Status:** resolved (fixes committed in 863e894)

## Resolution (2026-06-26 — commit 863e894)

| ID | Disposition |
|----|-------------|
| CR-01 | **FIXED** — `validate_identifiers(table, schema, *columns)` added inside both COPY helpers (the single chokepoint every caller funnels through), matching the `copy_insert` reference convention. Identifier *quoting* was intentionally **not** added: the codebase convention is validate-then-reject (mixed-case/reserved/space names raise `InvalidIdentifier` library-wide via `validate_identifier`), so the "mixed-case column" angle is a pre-existing trait shared by `copy_insert`/`insert_batch`, not a new regression — out of scope for this non-breaking perf phase. |
| CR-02 | **FIXED** — same helper-internal validation closes the ETL `append` (zero-validation) and `replace` (column-validation) regression, since both seam paths call the helper. |
| WR-01 | **FIXED** — `TestStreamDfCopyValidation` (sync) + `TestAsyncStreamDfCopyValidation` (async) assert an invalid table/column raises `InvalidIdentifier` before `cur.copy` is ever called. |
| WR-02 | **FIXED** — the ETL seam now consumes the helper's return value (`rows_loaded += _stream_df_copy(...)` / `await`), which additionally corrects a latent `rows_loaded` bug for empty `replace` (where `cur.rowcount` previously carried the preceding TRUNCATE). |
| WR-03 | **ACCEPTED (by design, D-04)** — the `replace` two-phase non-atomicity is an explicit, documented Phase 38 decision (CONTEXT.md D-04 + method docstring). A user-facing README note is deferred polish, not a code defect. |
| IN-01 | **FIXED** — helper docstrings updated to state they validate identifiers themselves. |
| IN-02 | **Acknowledged** — optional readability cleanup; no defect, no action. |

Verification: full suite **1402 passed**, 11 skipped, coverage **94.26%** (≥94 gate); ruff clean. The 3 `test_postgis_errors.py` failures are pre-existing PostGIS-not-installed env failures (not regressions).

---

## Summary

Phase 38 routes bulk-insert paths through PostgreSQL's COPY protocol via two new
private helpers (`_stream_df_copy` / `_async_stream_df_copy`), rewrites
`from_dataframe` to a Hybrid DDL(`head(0).to_sql`)+COPY strategy, switches the
ETL `append`/`replace` load seam to stream via COPY inline on the transaction
cursor, and hoists the `row_placeholders` constant out of the per-row loop in
`insert_batch`.

The sync/async parity is clean, the connection lifecycle in `from_dataframe` is
correct (no leaks), the COPY-runs-inline-on-the-txn-cursor seam invariant is
honored, and the `insert_batch` hoist is byte-exact. The NaN/NaT→NULL mask logic
and the `to_numpy(dtype=object)` type-fidelity reasoning are sound.

**However, the central builder-pur invariant is broken in both new helpers.**
The COPY SQL string interpolates table, schema, and **every column name** with
**zero `validate_identifiers` call** anywhere on the new code paths. This is both
a SQL-injection vector and a functional regression: the previous code paths
(`_build_insert_sql` for ETL append/replace; `copy_insert` for the pre-existing
COPY method) all validated identifiers before interpolation. This phase silently
dropped that protection. Two BLOCKERs below.

## Critical Issues

### CR-01: COPY helpers interpolate unvalidated identifiers — injection + builder-pur violation

**File:** `pycopg/database.py:115` and `pycopg/async_database.py:128`
(`_stream_df_copy` / `_async_stream_df_copy`)

**Issue:** Both helpers build the COPY statement by raw f-string interpolation of
`schema`, `table`, and the joined `columns` list:

```python
cols_str = ", ".join(columns)
with cur.copy(f"COPY {schema}.{table} ({cols_str}) FROM STDIN") as copy:
```

Neither helper calls `validate_identifier(s)`, and the docstring explicitly
disclaims responsibility ("never invokes `validate_identifiers` — those are the
caller's job"). The problem is the **callers do not validate columns** (see
CR-02), so column names — which are user-controlled (`df.columns`,
DataFrame column labels, or ETL extract column names) — reach SQL unescaped.

This violates the project's stated builder-pur invariant ("`validate_identifiers`
MUST run before any value is used; user values are never string-interpolated into
SQL") and is a SQL-injection surface. A column label such as
`"x); DROP TABLE users; --"` would be interpolated verbatim into the COPY DDL.

It is also a **functional** defect independent of injection: the DDL is created
by `to_sql`, which quotes identifiers (mixed-case, reserved words, spaces all
work). The COPY string emits the same names **unquoted**, so a perfectly valid
DataFrame with a column named `Select`, `My Col`, or any mixed-case label
produces broken COPY SQL (reserved-word / syntax error or wrong column) even
though the DDL phase succeeded. The two phases disagree on quoting.

**Fix:** Validate every identifier and quote it consistently with the DDL inside
the helper (defense-in-depth — the helper owns the SQL it emits):

```python
from pycopg.utils import validate_identifiers  # at module top

def _stream_df_copy(cur, df, table, schema, columns):
    if df.empty:
        return 0
    validate_identifiers(table, schema, *columns)
    cols_str = ", ".join(f'"{c}"' for c in columns)
    ...
    with cur.copy(f'COPY "{schema}"."{table}" ({cols_str}) FROM STDIN') as copy:
        ...
```

(Mirror in the async helper.) Note quoting via `"..."` matches `to_sql`'s default
behaviour and removes the DDL/COPY disagreement. If quoting is deferred to a
follow-up, at minimum restore `validate_identifiers(table, schema, *columns)` so
the security regression is closed.

### CR-02: ETL `append` load path lost all identifier validation (regression)

**File:** `pycopg/etl.py:1425-1428` (sync) and `pycopg/etl.py:2105-2108` (async)

**Issue:** Before this phase, the ETL `append` and `replace` paths built their
INSERT via `_build_insert_sql(...)`, whose first line is
`validate_identifiers(table, schema, *columns)` (see `pycopg/etl.py:449`). That
guaranteed the target table, schema, and **all column names** were validated
before any interpolation.

The rewrite removes `_build_insert_sql` from those paths and calls
`_stream_df_copy(cur, df, pipeline.target, pipeline.schema, columns)` directly.
Consequences:

- **`append` mode**: `pipeline.target`, `pipeline.schema`, and `columns` are now
  **never validated** anywhere on the path. `Pipeline.__post_init__`
  (`pycopg/etl.py:210`) does NOT call `validate_identifiers(target, schema)`, so
  these are unvalidated user input that flow straight into the COPY f-string in
  the helper.
- **`replace` mode**: `build_truncate_sql` (line 367) still validates
  `target`/`schema`, but `columns` are no longer validated at all.

This is a concrete security regression introduced by the diff: an ETL pipeline
configured with a crafted `target`/`schema` (append mode) or crafted extract
column names (append or replace) now reaches SQL unescaped.

**Fix:** Closing CR-01 in the helper (adding
`validate_identifiers(table, schema, *columns)` inside `_stream_df_copy` /
`_async_stream_df_copy`) fixes this path too, since every COPY caller goes
through the helper. Verify with a regression test that passes an invalid
column/target name through an `append`-mode pipeline and asserts
`InvalidIdentifier` is raised before any DB write.

## Warnings

### WR-01: No test covers the identifier-validation / injection contract

**File:** `tests/test_database_integration.py:337` (`TestFromDataframeCopy`),
`tests/test_etl_accessor.py` (COPY-path tests), `tests/test_database.py`,
`tests/test_async_database.py`

**Issue:** The new tests cover the happy path (row counts, NaN/NaT→NULL,
index=True, replace/append semantics, byte-exact hoist) but none assert that an
invalid table/schema/column name is rejected. Because the production code dropped
validation (CR-01/CR-02), there is no test that would have caught it — the
builder-pur invariant is now untested on the COPY paths, whereas the old
`_build_insert_sql` paths were guarded by identifier-validation tests.

**Fix:** Add tests asserting `InvalidIdentifier` (or post-fix, correct quoting)
for: `from_dataframe` with a column whose label is a reserved word / contains
special chars; an `append`-mode ETL pipeline with an invalid `target`. Pin the
quoting behaviour for mixed-case column names round-tripping correctly.

### WR-02: `_stream_df_copy` return value is dead — `rows_loaded` re-reads `cur.rowcount`

**File:** `pycopg/etl.py:1426-1429` (sync), `pycopg/etl.py:2106-2109` (async);
helper returns at `pycopg/database.py:124` / `pycopg/async_database.py:137`

**Issue:** The helper computes and returns `cur.rowcount`, but the ETL seam
ignores the return value and immediately re-reads `cur.rowcount` itself
(`rows_loaded += cur.rowcount`). Two reads of the same mutable cursor attribute
with the return value silently discarded is a maintenance hazard: a future
change to what the helper returns (e.g. filtering, or returning `len(df)` for
robustness against psycopg's COPY `rowcount` quirks the docstring warns about)
would have no effect on `rows_loaded`, masking the bug.

**Fix:** Use the helper's return value as the single source of truth:
`rows_loaded += _stream_df_copy(cur, df, pipeline.target, pipeline.schema, columns)`
(and `await` for the async variant). Then the docstring's "read rowcount after
the block closes" contract lives in exactly one place.

### WR-03: `from_dataframe` `replace` two-phase non-atomicity is documented but not guarded

**File:** `pycopg/database.py:1324-1339`, `pycopg/async_database.py` (mirror)

**Issue:** The docstring (D-04) acknowledges that for `if_exists='replace'` the
DDL commits (table dropped + recreated empty) before the COPY load, so a COPY
failure leaves an empty table. This is called out as intentional and matching
prior semantics — accepted. The residual risk: the DDL connection (engine) and
the COPY connection (`self.connect()`) are two independent connections/txns, so
there is genuinely no rollback path if COPY raises. This is fine for
`from_dataframe`'s documented contract, but it differs from the ETL seam, which
takes care to run COPY inline on the transaction cursor for atomicity. Worth an
explicit note in the public docs (not just the code docstring) so callers relying
on `from_dataframe` for replace understand the empty-table-on-failure window.

**Fix:** Surface the "replace is non-atomic across DDL/COPY; a COPY failure
leaves an empty table" caveat in the user-facing README/API docs, or wrap the
COPY in a try/except that re-raises with a clear message about the table state.

## Info

### IN-01: Helper docstring overstates the validation contract

**File:** `pycopg/database.py:71-74`, `pycopg/async_database.py:84-88`

**Issue:** The docstrings assert that omitting validation is correct because
"those are the caller's job (builder-pur invariant)" — but as CR-01/CR-02 show,
no caller actually validates columns. The docstring documents a contract that the
codebase does not uphold, which is misleading for maintainers.

**Fix:** After moving validation into the helper (recommended), update the
docstring to state the helper validates and quotes identifiers itself.

### IN-02: `columns` local in upsert branch could be implicit

**File:** `pycopg/etl.py:1369` / `pycopg/etl.py:2049` (`columns = list(df.columns)`)

**Issue:** Minor: `columns` is derived once and used by both the upsert SQL
builder and the COPY helper, which is fine. No defect — noting only that the
`rows = []  # unused for append/replace` sentinel relies on the downstream
branch never reading `rows` for non-upsert modes; it currently holds, but a
single-source dispatch (compute `rows` only inside the upsert branch and assert)
would make the invariant harder to break.

**Fix:** Optional readability cleanup; no action required for correctness.

---

_Reviewed: 2026-06-26_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
