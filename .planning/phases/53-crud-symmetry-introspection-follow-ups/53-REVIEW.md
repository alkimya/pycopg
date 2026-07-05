---
phase: 53-crud-symmetry-introspection-follow-ups
reviewed: 2026-07-05T07:51:20Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - pycopg/database.py
  - pycopg/async_database.py
  - pycopg/queries.py
  - pycopg/schema.py
  - tests/test_database.py
  - tests/test_async_database.py
  - tests/test_sql_injection.py
  - tests/test_database_integration.py
  - tests/test_parity.py
  - docs/api-reference.md
findings:
  critical: 0
  warning: 3
  info: 2
  total: 5
status: issues_found
---

# Phase 53: Code Review Report

**Reviewed:** 2026-07-05T07:51:20Z
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Reviewed the diff `f9de0ac..HEAD` for Phase 53 (CRUD symmetry + introspection
follow-ups): `select_where`/`find`/`get`/`find_one` predicate reads, single-row
`insert`, and `column_exists`/`table_size` introspection, on both
`Database`/`AsyncDatabase` and `SchemaAccessor`/`AsyncSchemaAccessor`.

The core identifier-injection invariant holds: every new code path either
routes table/schema/column identifiers through `validate_identifiers`
(`_build_select_sql`, `_build_insert_sql`, `table_size`) or binds them as
`%s` values against `information_schema` (`column_exists`), never
string-interpolating untrusted identifiers. `where_sql`/`order_by`/
`on_conflict` raw-passthrough escape hatches are exactly where the design
says they should be, and are well covered by `tests/test_sql_injection.py`.
Sync/async KIND-parity holds by direct diff comparison — both classes are
structurally identical for every new method.

However, live-DB verification (against a real Postgres 18 instance, not just
mocks) found two real, previously-untested edge cases where the new methods
let a raw `psycopg` driver exception escape instead of failing cleanly or
behaving predictably, breaking parity with sibling methods (`paginate`/
`paginate_keyset`) that DO guard the equivalent input. A third finding is a
test-suite gap: the new `test_crud_v120_surface`'s docstring asserts KIND
parity is covered by `test_accessor_parameter_kind_parity`, but that test is
parametrized only over `ACCESSOR_PAIRS`, which excludes `(Database,
AsyncDatabase)` — so the flat-core methods added this phase actually have no
automated protection against exactly the class of regression
(sync/async keyword-only drift) the project's own history (Phase 41
FREEZE-03) calls out as a real recurring risk.

## Warnings

### WR-01: `insert()` with an empty row dict raises a raw Postgres `SyntaxError` instead of failing cleanly

**File:** `pycopg/database.py:1015-1055` (and identically `pycopg/async_database.py:2253-2296`)

**Issue:** `insert(table, row)` builds `columns = list(row.keys())` and passes it
straight to `_build_insert_sql` with no empty-row guard. When `row == {}`,
this emits `INSERT INTO <schema>.<table> () VALUES ()`, which is **not**
valid PostgreSQL syntax (the valid all-default form is
`INSERT INTO <table> DEFAULT VALUES`). Verified live against Postgres 18 via
the actual `psycopg` driver:

```
>>> db.insert("_review_probe_53", {})
psycopg.errors.SyntaxError: erreur de syntaxe sur ou près de « ) »
LINE 1: INSERT INTO public._review_probe_53 () VALUES () RETURNING *
```

Callers who accidentally pass an empty dict (e.g. a row assembled from a
dict comprehension that filtered everything out) get an opaque raw driver
`SyntaxError` from `_build_insert_sql`'s output rather than a clear
library-level error. `insert_many`/`upsert`/`upsert_many` guard the
list-level empty case (`if not rows: return 0`) but nothing in this new
code path guards the empty-dict case for the singular `insert`. Not covered
by any test in `tests/test_database.py`, `tests/test_async_database.py`, or
`tests/test_database_integration.py` (all `insert(...)` calls use non-empty
row dicts).

**Fix:**
```python
def insert(self, table, row, *, schema="public", on_conflict=None):
    if not row:
        raise ValueError("insert: 'row' must be a non-empty dict.")
    columns = list(row.keys())
    ...
```
Apply identically to `AsyncDatabase.insert`.

---

### WR-02: `select_where`/`find`/`get`/`find_one` accept negative `limit`/`offset` and let a raw Postgres error escape, unlike sibling `paginate`/`paginate_keyset`

**File:** `pycopg/database.py:1298-1382, 1440-1518` (and identically `pycopg/async_database.py:1147-1231, 1263-1341`); underlying builder `pycopg/base.py:248-297` (`_build_select_sql`, pre-existing but only exercised by these new callers)

**Issue:** `select_where`/`find`/`get`/`find_one` pass `limit`/`offset`
straight through to `_build_select_sql`, which does
`sql += f" LIMIT {int(limit)}"` / `f" OFFSET {int(offset)}"` with no range
check. `paginate`/`paginate_keyset` (existing sibling read methods,
`pycopg/database.py:2002-2003, 2142-2143`) explicitly guard this same input
shape:
```python
limit = int(limit)
if limit <= 0:
    raise ValueError("limit must be a positive integer")
```
before any DB round-trip (project convention IN-02, called out in
`paginate`/`paginate_keyset`'s own docstrings). The new methods have no such
guard, so a negative `limit`/`offset` reaches the server and surfaces as a
raw driver exception instead of a clean, predictable `ValueError`. Verified
live against Postgres 18 via `psycopg`:

```
>>> db.select_where("_review_probe_53", limit=-1)
psycopg.errors.InvalidRowCountInLimitClause: LIMIT ne doit pas être négative
```
(same for `offset=-1` → `InvalidRowCountInLimitClause`/`OFFSET ne doit pas
être négatif`). This is exactly the kind of new-code robustness gap the
project's own history flags (Phase 50 code-review found 3 analogous
`paginate` trim-path bugs — "new attack surface `paginate` never had"); here
the new attack surface is `select_where`/`get`'s `limit`/`offset`, and it
was not caught by the added test suite (`tests/test_database.py`,
`tests/test_database_integration.py` only exercise positive `limit`/
`offset`).

**Fix:** Add the same `IN-02` guard used by `paginate`/`paginate_keyset`
before calling `_build_select_sql`, in both `select_where`/`get` (both
classes):
```python
if limit is not None:
    limit = int(limit)
    if limit < 0:
        raise ValueError("limit must not be negative")
if offset is not None:
    offset = int(offset)
    if offset < 0:
        raise ValueError("offset must not be negative")
```

---

### WR-03: `test_crud_v120_surface` docstring claims KIND-parity coverage that does not exist for the new flat-core methods

**File:** `tests/test_parity.py:157-186` (new `test_crud_v120_surface`); the referenced test is `tests/test_parity.py:632-633` (`test_accessor_parameter_kind_parity`)

**Issue:** The new `test_crud_v120_surface` docstring states: "Per-method
signature parity is covered by
:func:`test_accessor_parameter_kind_parity`." However,
`test_accessor_parameter_kind_parity` is declared as
`@pytest.mark.parametrize("sync_cls, async_cls", ACCESSOR_PAIRS)`, and
`ACCESSOR_PAIRS` (`tests/test_parity.py:24-32`) only lists accessor pairs
(`TimescaleAccessor`/`AsyncTimescaleAccessor`, ..., `SchemaAccessor`/
`AsyncSchemaAccessor`) — it does **not** include `(Database, AsyncDatabase)`.
So the five new flat-core methods this phase adds directly to `Database`/
`AsyncDatabase` (`select_where`, `find`, `get`, `find_one`, `insert`) have
**no** automated per-parameter-kind (positional-or-keyword vs. keyword-only)
parity check. `test_method_signatures_match`
(`tests/test_parity.py:481-537`, the only Database/AsyncDatabase-level
parity check that runs) only compares `list(sig.parameters.keys())` —
parameter *names and order* — not `Parameter.kind`, so it would silently
pass even if, say, someone later added an `AsyncDatabase.select_where`
missing the `*` keyword-only boundary that `Database.select_where` has.
This is precisely the CR-01 class of regression the project's own comments
(`test_accessor_parameter_kind_parity`'s docstring, referencing "Phase 41
FREEZE-03 gap") say it exists specifically to catch — but the new flat-core
surface added this phase sits entirely outside that safety net. The current
code is correct today (verified by direct diff comparison: sync/async
signatures are structurally identical), but the claimed protection is
inaccurate and the gap is real for future changes.

**Fix:** Either extend `ACCESSOR_PAIRS`-style coverage to include
`(Database, AsyncDatabase)` in a parametrization that
`test_accessor_parameter_kind_parity` (or a sibling test) actually consumes,
or correct the `test_crud_v120_surface` docstring to stop claiming coverage
that doesn't apply, and add an explicit kind-parity assertion for these five
methods (mirroring the `p.kind` comparison logic already implemented in
`test_accessor_parameter_kind_parity`).

## Info

### IN-01: `insert()`'s docstring omits a `Raises` section

**File:** `pycopg/database.py:1015-1048` (and `pycopg/async_database.py:2253-2286`)

**Issue:** `select_where`/`find`/`get`/`find_one`'s docstrings all document
a `Raises` section covering `ValueError` (D-02/D-03/D-04) and
`InvalidIdentifierError`. `insert()`'s docstring has no `Raises` section at
all, despite `_build_insert_sql` → `validate_identifiers` being able to
raise `InvalidIdentifierError` for an invalid `table`/`schema`/column key
(exercised by `tests/test_sql_injection.py::TestInsertIdentifierInjection`).
Minor documentation-consistency gap versus its new sibling methods in the
same phase.

**Fix:** Add a `Raises` section documenting `InvalidIdentifierError` (and,
if WR-01 is fixed, the new empty-row `ValueError`).

### IN-02: Two independently-named `table_size` methods with different return semantics

**File:** `pycopg/schema.py:501-535, 1411-1445` (new `SchemaAccessor.table_size`/
`AsyncSchemaAccessor.table_size`) vs. `pycopg/maint.py:73-98, 252-...`
(pre-existing `MaintAccessor.table_size`)

**Issue:** `db.schema.table_size(name)` returns a raw `int` byte count and
raises `TableNotFoundError` on a missing table; `db.maint.table_size(table,
pretty=True)` returns a pretty string by default and has no existence
guard. Both are reachable as `db.schema.table_size(...)` vs.
`db.maint.table_size(...)` with very similar names but different
signatures/return types/error behavior. This is already called out via a
`See Also` cross-reference in both docstrings and in
`docs/api-reference.md`, so it's a documented, intentional design choice —
flagging only as a low-severity API-discoverability nit (a caller who
autocompletes `.table_size(` on the wrong accessor gets a different return
type with no exception, not a crash).

**Fix:** No action required if the design choice is intentional (it
appears to be, given the explicit cross-referencing); consider a follow-up
naming pass in a future minor version if user confusion reports arrive.

---

_Reviewed: 2026-07-05T07:51:20Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
