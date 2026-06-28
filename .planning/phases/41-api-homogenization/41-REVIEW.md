---
phase: 41-api-homogenization
reviewed: 2026-06-28T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - pycopg/__init__.py
  - pycopg/exceptions.py
  - pycopg/spatial.py
  - pycopg/timescale.py
  - pycopg/database.py
  - pycopg/async_database.py
  - pycopg/schema.py
  - pycopg/etl.py
  - pycopg/admin.py
  - pycopg/maint.py
  - pycopg/backup.py
  - pycopg/base.py
  - pycopg/utils.py
findings:
  critical: 1
  warning: 3
  info: 1
  total: 5
status: resolved
resolution:
  CR-01: fixed (92018dd) — async kw-only parity + structural parity test
  WR-03: fixed (a42ad16) — single authored alias map
  IN-01: fixed (e9dc3da) — docstring Raises use canonical *Error names
  WR-01: deferred — validate_identifiers None-skip is a behavior change at the SQL boundary; required-identifier callers never pass None; needs its own per-caller analysis
  WR-02: deferred — reviewer states no code change required for correctness (nearest KNN owns ordering); doc-only suggestion
---

> **RESOLUTION (2026-06-28):** CR-01 (BLOCKER), WR-03, and IN-01 fixed and verified
> (full suite 1491 passed, 96.09% cov; 0 sync/async signature divergence; structural
> `test_accessor_parameter_kind_parity` added to prevent recurrence). WR-01 and WR-02
> deferred with justification (see frontmatter `resolution`).

# Phase 41: Code Review Report

**Reviewed:** 2026-06-28
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Phase 41 (API homogenization for the v1.0.0 freeze) applies three surface changes:
the keyword-only `*` boundary across all 7 accessor families + flat core, the
spatial/timescale `where=`→`filter=` deprecation shims, and the PEP 562 exception
alias shims. The deprecation machinery (spatial 22 methods + timescale 2 methods +
exception `__getattr__` in both `exceptions.py` and `__init__.py`) is **correct**:
`stacklevel=2` is used everywhere, the both-old-and-new case raises `TypeError`
before any work, the warning fires only when the old kwarg is supplied, and the
alias resolves to the same class object. SQL injection guards are **intact** — every
spatial builder still calls `validate_identifiers` before interpolation, and no
internal caller routes through a deprecated `where=` path (the
`-W error::DeprecationWarning` gate is safe).

However, the kw-only freeze commit (`d2eee0d`, "FREEZE-03") that claims
"async_database.py: identical parity (D-11)" and "(sync+async)" for backup/etl
**only edited the sync half** of every accessor whose async class lives in the
same module file as its sync class. The result is a systematic sync/async
signature divergence in `schema.py`, `maint.py`, `etl.py`, and `backup.py`. For an
API-*freeze* milestone this is a BLOCKER: the async surface would freeze at 1.0
with positional `schema=`/`if_exists=`/`limit=`/`dry_run=` arguments that can never
be tightened to keyword-only without a 2.0 breaking change — the exact homogenization
this phase exists to deliver. `async_database.py` (a separate file) was correctly
updated; the four in-file async accessors were missed.

## Structural Findings (fallow)

No structural findings block was provided for this review.

## Critical Issues

### CR-01: kw-only `*` boundary applied to sync accessors but NOT their in-file async mirrors (freeze-permanent API asymmetry)

**File:** `pycopg/schema.py` (17 async methods), `pycopg/maint.py:222,247,274,292,326`, `pycopg/etl.py:1635,1808`, `pycopg/backup.py:390,459,580,666`

**Issue:** Commit `d2eee0d` ("apply kw-only * across all 7 accessor families + flat core") moved the keyword-only boundary on the **sync** accessor methods but did not touch the **async** accessor classes that live in the same `.py` files. `async_database.py` (separate file) got correct parity (11 `*` insertions + internal caller fixes), masking the gap. The divergence is verifiable by diffing sync vs async signatures:

- **schema.py — `AsyncSchemaAccessor` (worst):** sync `def list_tables(self, *, schema="public")` vs async `async def list_tables(self, schema="public")`. The same positional-vs-kw-only split exists for `drop_database`, `create_schema`, `drop_schema`, `list_tables`, `table_exists`, `list_columns`, `columns_with_types`, `table_info`, `row_count`, `drop_table`, `list_indexes`, `list_constraints`, `primary_key`, `foreign_keys`, `sequences`, `views`, `describe` (~17 methods). Sync `columns_with_types(self, table, *, schema=...)` vs async `columns_with_types(self, table, schema=...)` is a representative pair.
- **maint.py — `AsyncMaintAccessor`:** sync `size(self, *, pretty=True)` / `table_size(self, table, *, schema=..., pretty=...)` / `table_sizes(self, *, schema=..., limit=...)` / `vacuum(self, *, ...)` / `analyze(self, *, ...)` vs async equivalents with NO `*` (lines 222, 247, 274, 292, 326). (async `explain` correctly keeps `params` positional, matching the sync carve-out.)
- **etl.py — `AsyncETLAccessor`:** sync `history(self, name, *, limit=100)` / `run(self, pipeline, *, dry_run=False)` vs async `history(self, name, limit=100)` (line 1635) / `run(self, pipeline, dry_run=False)` (line 1808). The commit message explicitly lists these as "(sync+async)".
- **backup.py — `AsyncBackupAccessor`:** sync `pg_dump` / `pg_restore` / `copy_to_csv` / `copy_from_csv` all have `*` after the required positional(s); async versions (lines 390, 459, 580, 666) have NO `*` — every option is positional. The backup.py diff in `d2eee0d` added exactly 4 `*` lines, all to the sync class.

Impact: this is the central deliverable of an API-freeze phase. Shipping it means the async API freezes at 1.0 with a permanently looser calling convention than the sync API — callers can pass `await db.schema.list_tables("myschema")` positionally on async but not on sync, and post-1.0 the only way to fix it is a 2.0 breaking change. It also breaks the sync/async parity invariant the codebase relies on (the parity test suite did not catch this, so coverage of the signature contract is incomplete).

**Fix:** Apply the same `*` boundary to every async method that its sync mirror received, in the four in-file async accessors. For example in `schema.py`:
```python
# AsyncSchemaAccessor — mirror the sync boundary
async def list_tables(self, *, schema: str = "public") -> list[str]:
async def table_exists(self, name: str, *, schema: str = "public") -> bool:
async def columns_with_types(self, table: str, *, schema: str = "public") -> list[tuple[str, str]]:
async def drop_database(self, name: str, *, if_exists: bool = True) -> None:
async def create_schema(self, name: str, *, if_not_exists: bool = True, owner: str | None = None) -> None:
async def drop_schema(self, name: str, *, if_exists: bool = True, cascade: bool = False) -> None:
async def drop_table(self, name: str, *, schema: str = "public", if_exists: bool = True, cascade: bool = False) -> None:
# ...and the remaining list_*/primary_key/foreign_keys/sequences/views/describe/table_info/row_count
```
```python
# maint.py AsyncMaintAccessor
async def size(self, *, pretty: bool = True) -> str | int:
async def table_size(self, table: str, *, schema: str = "public", pretty: bool = True) -> str | int:
async def table_sizes(self, *, schema: str = "public", limit: int = 20) -> list[dict]:
async def vacuum(self, *, table=None, schema="public", analyze=True, full=False) -> None:
async def analyze(self, *, table: str | None = None, schema: str = "public") -> None:
```
```python
# etl.py AsyncETLAccessor
async def history(self, name: str, *, limit: int = 100) -> list[RunResult]:
async def run(self, pipeline: Pipeline, *, dry_run: bool = False) -> RunResult:
```
```python
# backup.py AsyncBackupAccessor — add * after the required positional file arg
async def pg_dump(self, output_file, *, format=..., ...) -> ...:
async def pg_restore(self, input_file, *, clean=False, ...) -> ...:
async def copy_to_csv(self, table, output_file, *, schema="public", ...) -> ...:
async def copy_from_csv(self, table, input_file, *, schema="public", ...) -> ...:
```
Add a parity test that asserts, for each sync/async method pair across all accessors, that the keyword-only parameter sets are identical (e.g. via `inspect.signature(...).parameters` kind comparison) so this class of drift is caught structurally rather than per-method.

## Warnings

### WR-01: `validate_identifiers` silently skips `None` — masks programming errors at the SQL boundary

**File:** `pycopg/utils.py:120-122`
**Issue:** `validate_identifiers` iterates and calls `validate_identifier(name)` only `if name is not None`. A `None` identifier therefore passes validation silently and is later interpolated into SQL as the literal string `None` (e.g. `FROM public.None`), turning what should be an immediate `InvalidIdentifierError` into a confusing downstream SQL syntax error. This is defensive only for callers that pass optional identifiers, but the spatial/timescale/schema builders pass required identifiers (`table`, `geom`, `schema`) that should never be `None`. The skip hides a real bug class.
**Fix:** Either validate `None` as invalid (`raise InvalidIdentifierError` for `None`), or document the skip narrowly and have callers that pass genuinely-optional identifiers filter them before the call. Preferred:
```python
def validate_identifiers(*names: str) -> None:
    for name in names:
        validate_identifier(name)  # let None/"" raise via validate_identifier
```
(`validate_identifier(None)` would then need an explicit `None` check raising `InvalidIdentifierError`.)

### WR-02: spatial `nearest` builder ignores `order_by`/`limit` while sibling builders honor them — silent parameter drop

**File:** `pycopg/spatial.py:578-645` (`build_nearest_sql`) and accessor `nearest` (lines 1543, 2614)
**Issue:** `build_nearest_sql` hard-codes `ORDER BY <knn> LIMIT %s` and accepts only `filter=` — it does not accept `order_by=`/`limit=`, which is defensible since KNN owns the ordering. But the accessor `nearest()` methods (sync 1543, async 2614) also omit `order_by`/`limit` from their signatures, so there is no silent-drop at the accessor layer. This is consistent. The residual risk: `nearest` is the only spatial helper without `order_by`/`limit`, an asymmetry a caller migrating from `distance(order_by="distance", limit=k)` may not expect.
**Fix:** No code change required for correctness; document in the `nearest` docstring that ordering/limit are fixed by the KNN semantics (k) and `order_by`/`limit` are intentionally unavailable, to pre-empt confusion at the freeze.

### WR-03: duplicate exception-alias map maintained in two modules — drift risk at the freeze

**File:** `pycopg/exceptions.py:80-85` (`_DEPRECATED_NAMES`) and `pycopg/__init__.py:50-55` (`_DEPRECATED_PACKAGE_ALIASES`)
**Issue:** The same four alias→canonical mappings are hand-duplicated in two `__getattr__` shims. They are currently identical, but freezing 1.0 with two sources of truth invites silent divergence if one is edited (e.g. adding a 5th alias) and the other is not — a caller would then get a `DeprecationWarning` at the package level but `AttributeError` at the module level, or vice versa.
**Fix:** Have `__init__.py` import the single map from `exceptions`:
```python
# __init__.py
from pycopg.exceptions import _DEPRECATED_NAMES as _DEPRECATED_PACKAGE_ALIASES
```
or expose a small public-internal helper in `exceptions` that both shims call.

## Info

### IN-01: numpydoc "Raises" sections reference the deprecated exception names

**File:** `pycopg/spatial.py:111,245,325,394,472,558,632,694,756,814,942`; `pycopg/database.py:909,948,1249`
**Issue:** Numerous `Raises\n------\nInvalidIdentifier` docstring sections name the **deprecated** alias `InvalidIdentifier` rather than the canonical `InvalidIdentifierError`. Generated API docs at the 1.0 freeze will advertise the soon-to-be-removed name as the exception contract. (The runtime `:exc:` cross-references in the timescale docstrings already use `*Error` names, so this is inconsistent within the codebase.)
**Fix:** Replace `InvalidIdentifier` with `InvalidIdentifierError` in these docstring Raises blocks before the docs freeze.

---

_Reviewed: 2026-06-28_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
