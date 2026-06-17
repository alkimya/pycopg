---
phase: 21-infrastructure-timescale-accessor
reviewed: 2026-06-17T00:00:00Z
depth: standard
files_reviewed: 10
files_reviewed_list:
  - pycopg/aliases.py
  - pycopg/timescale.py
  - pycopg/database.py
  - pycopg/async_database.py
  - pycopg/__init__.py
  - tests/test_timescale_aliases.py
  - tests/test_parity.py
  - tests/test_async_database.py
  - tests/test_database_integration.py
  - tests/test_sql_injection.py
findings:
  critical: 0
  warning: 4
  info: 3
  total: 7
status: issues_found
---

# Phase 21: Code Review Report

**Reviewed:** 2026-06-17
**Depth:** standard
**Files Reviewed:** 10
**Status:** issues_found

## Summary

Phase 21 introduces the `deprecated_alias` decorator (`aliases.py`), the
`TimescaleAccessor` / `AsyncTimescaleAccessor` classes (`timescale.py`), the
lazy `timescale` property on both database classes, and replaces the 12 flat
TimescaleDB methods with thin `@deprecated_alias` stubs. The core mechanics are
sound:

- The sync/async branch in the decorator is correct (`inspect.iscoroutinefunction`
  reliably detects the `async def` stubs; verified at runtime).
- `stacklevel=2` is correct — the warning is anchored at the caller, proven by
  the alias tests.
- The accessor methods are a faithful verbatim move: the SQL-injection guards
  (`validate_identifiers`, `validate_identifier`, `validate_interval`) and their
  ordering relative to the `has_extension` check are preserved exactly. The SQL
  injection regression suite (92 tests) passes against the new `db.timescale.*`
  paths.
- Lazy caching mirrors the established `_spatial` / `_etl` pattern; no circular
  import despite `timescale.py` doing `from pycopg import queries` (matches `etl.py`).
- Full suite: 994 passed, 2 pre-existing flaky DB failures
  (`test_integration.py::...test_async_transaction_fix`,
  `test_postgis_errors.py::...test_create_spatial_index_name_parameter`) that do
  not reference timescale/aliases and are documented in project memory as
  environmental flakes — not regressions from this phase.

No BLOCKER-level correctness or security defects were found. The findings below
concern the "zero breaking change" contract degrading at the tooling/typing/docs
layer, plus minor consistency issues.

## Warnings

### WR-01: Flat-alias signatures collapse to `(*args, **kwargs)` — breaks static typing on a `py.typed` package

**File:** `pycopg/aliases.py:46-63`, `pycopg/database.py` (12 stubs), `pycopg/async_database.py` (12 stubs)
**Issue:** The package ships `pycopg/py.typed` (PEP 561 — it advertises a typed
API), but the flat stubs are now `def create_hypertable(self, *args, **kwargs)`.
`functools.wraps` copies `__wrapped__` from the stub, so
`inspect.signature(db.create_hypertable)` resolves to `(*args, **kwargs)` and the
rich parameter list is gone (verified at runtime). For a `py.typed` library this
is a real regression: a type-checker that previously flagged
`db.create_hypertable(table=123)` or a missing required `time_column` now sees a
catch-all signature and reports nothing. The contract claims "zero breaking
change", but static type-safety of the legacy call-path is broken even though
runtime behaviour is preserved.
**Fix:** Give the flat stubs their real signatures instead of `*args, **kwargs`
(the decorator can still delegate positionally/by keyword), e.g.:
```python
@deprecated_alias("timescale.create_hypertable")
def create_hypertable(
    self,
    table: str,
    time_column: str,
    schema: str = "public",
    chunk_time_interval: str = "1 day",
    if_not_exists: bool = True,
    migrate_data: bool = True,
) -> None:
    """Deprecated: use ``db.timescale.create_hypertable`` instead."""
```
The wrapper already forwards `*args, **kwargs`, so this only restores the
public-facing signature/typing without changing delegation. Alternatively ship a
`.pyi` stub. If intentionally deferred, document it as accepted tech debt for the
v0.6.0 migration.

### WR-02: README and docs still present the deprecated flat API as the recommended usage

**File:** `README.md:325-332`, `README.md:542-552`, `docs/timescaledb.md:43` (and likely more)
**Issue:** All user-facing documentation still shows `db.create_hypertable(...)`,
`db.enable_compression(...)`, `db.add_compression_policy(...)`,
`db.add_retention_policy(...)`, `db.list_hypertables()` as the primary API. After
this phase those calls emit `DeprecationWarning`. Users copying the docs will
write code that warns on every call and breaks under `-W error` /
`filterwarnings = error`. This is doc drift introduced by the change: the
migration moved the canonical API to `db.timescale.*` but left the docs pointing
at the deprecated path. (README.md/docs were outside the reviewed file list but
are directly invalidated by this change.)
**Fix:** Update README.md and `docs/timescaledb.md` to use `db.timescale.*` as the
documented API, optionally with a one-line note that the flat names remain as
deprecated aliases until v0.7.0.

### WR-03: Async deprecation warning message says `db.` but the call site is `async_db.`

**File:** `pycopg/aliases.py:37-41`
**Issue:** The warning message is built from `target_path` as
`"use \`db.{target_path}\` instead; the flat \`db.{fn.__name__}\` alias is
deprecated..."`. For async stubs the docstring correctly says
`use \`\`async_db.timescale.X\`\``, but the emitted runtime warning still says
`db.timescale.X` / `db.X`. Minor, but the message is inconsistent for async users
and the test (`test_async_alias_warns_and_delegates`) only asserts the substring
`db.timescale.{name}` so it passes despite the mismatch. Not a correctness bug,
but a UX defect in the deprecation message that the test does not catch.
**Fix:** Either accept `db.`/`async_db.` neutrally (e.g. phrase as
`use the \`timescale.{method}\` accessor (\`db.timescale.{method}\`) instead`), or
pass the prefix into the decorator so async stubs render `async_db.`.

### WR-04: `deprecated_alias` performs no validation of `target_path`, failing only at call time

**File:** `pycopg/aliases.py:42`
**Issue:** `accessor_name, method_name = target_path.split(".", 1)` will raise
`ValueError: not enough values to unpack` only if `target_path` has no dot, and a
typo'd accessor/method name (`"timescale.creat_hypertable"`) is not detected until
the alias is actually invoked at runtime (`getattr(accessor, method_name)` raises
`AttributeError`). Since this decorator is the shared foundation for migration
phases 22-24, a typo in any future `@deprecated_alias("...")` ships silently and
only surfaces when a user hits that specific deprecated path. The accessor-parity
test guards the accessor surface but not the alias target strings.
**Fix:** Validate the dotted form at decoration time and consider an
import-time/test-time check that every `target_path` resolves to a real accessor
method. Minimal guard:
```python
if "." not in target_path:
    raise ValueError(
        f"target_path must be '<accessor>.<method>', got {target_path!r}"
    )
accessor_name, method_name = target_path.split(".", 1)
```

## Info

### IN-01: Inconsistent guard ordering between accessor methods (carried over verbatim)

**File:** `pycopg/timescale.py:78-84` & `:330-336` vs `:172-178` & `:209-215` (and async twins)
**Issue:** `create_hypertable` and `enable_compression` check `has_extension`
*before* `validate_*`, while `add_compression_policy` and `add_retention_policy`
validate *before* the extension check. The behaviour is correct in all cases
(both eventually validate), and this ordering was moved verbatim from the
originals, so it is not a regression. Noting only for consistency: a malicious
interval passed to `create_hypertable` triggers the extension error first, whereas
the same payload to `add_compression_policy` triggers `InvalidIdentifier` first.
**Fix:** Optional — standardise to validate-then-extension-check across all six
methods for predictable error precedence. Out of scope for a verbatim-move phase.

### IN-02: Duplicated extension-guard error string across 12 methods

**File:** `pycopg/timescale.py` (every method) — `"TimescaleDB extension not installed. Run db.create_extension('timescaledb')"`
**Issue:** The `ExtensionNotAvailable` message and the `has_extension("timescaledb")`
guard are copy-pasted in all 12 accessor methods. The `create_hypertable` variant
even differs in whitespace (single-line string at lines 79-81/331-333 vs the
two-line concatenation everywhere else), purely a verbatim-move artifact.
**Fix:** Optional — extract a small private helper
(`self._require_timescaledb()`) to centralise the guard and message. Low priority;
keeps the verbatim-move auditable as-is.

### IN-03: Async accessor guard message references `db.` not `async_db.`

**File:** `pycopg/timescale.py:332`, `:374`, etc.
**Issue:** The async accessor's `ExtensionNotAvailable` message says
`Run db.create_extension('timescaledb')` even though the async call would be
`await async_db.create_extension(...)`. Verbatim-moved, harmless, but slightly
misleading in async context. Same family as WR-03.
**Fix:** Optional — neutralise the message wording.

---

_Reviewed: 2026-06-17_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
