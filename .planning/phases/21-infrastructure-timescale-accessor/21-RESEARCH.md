# Phase 21: Infrastructure & Timescale Accessor - Research

**Researched:** 2026-06-17
**Domain:** Python decorator patterns, deprecation infrastructure, accessor refactoring
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `@deprecated_alias` takes a target path string (e.g. `"timescale.create_hypertable"`). At call time the decorator resolves `self.timescale` lazily, then calls the named method.
- **D-02:** Deprecated flat stubs are generic `(*args, **kwargs)` one-liners. The decorator does the warn + delegate.
- **D-03:** Sync and async variants of the decorator both exist (async variant `await`s the delegated accessor coroutine). Parity mandatory (D-SCOPE-4).
- **D-04:** DeprecationWarning message names the new path; `stacklevel` must point at the caller's line.
- **D-05:** Real implementation MOVES into the accessor. Flat `db.*` name becomes the thin deprecated alias.
- **D-06:** Move bodies verbatim, rewriting `self.*` → `self._db.*`. Keep inline f-string SQL. Do NOT extract pure SQL builders.
- **D-07:** New accessor classes live in `pycopg/timescale.py` (both sync + async). Lazy cached property on `Database`/`AsyncDatabase`.
- **D-08:** Migrate existing timescale test call-sites to `db.timescale.*` / `async_db.timescale.*`.
- **D-09:** Add dedicated alias test class asserting each of the 6 aliases warns AND delegates.
- **D-10:** Data-driven parity registry in `tests/test_parity.py` seeded with `(TimescaleAccessor, AsyncTimescaleAccessor)`.
- **D-SCOPE-1..4:** Strategy locked — alias + DeprecationWarning; real impl in accessor; 5 accessors total; sync/async parity mandatory.

### Claude's Discretion

- Exact decorator signature/internals beyond D-01..D-04 (e.g. `functools.wraps`, module placement).
- Exact placement/naming of registry list and alias test class.
- Whether `from __future__ import annotations` + `TYPE_CHECKING` guards are needed in `timescale.py` (follow `spatial.py`/`etl.py`).

### Deferred Ideas (OUT OF SCOPE)

- Pure SQL builders for timescale (`_build_*` functions) — intentionally NOT done.
- Folding `TestEtlParity` into the new registry — optional, only if zero-risk.
- The other 4 accessors (`admin`, `maint`, `backup`, `schema`) + spatial-index relocation — Phases 22–23.
- Public exports / README / Sphinx / CHANGELOG / MIGRATION / version bump / PyPI publish — Phase 24.
- Alias removal — v0.7.0.
- New TimescaleDB power (continuous aggregates, gapfill, chunks) — v0.8.0.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REORG-01 | `@deprecated_alias` decorator emits uniform DeprecationWarning (correct stacklevel) and delegates; sync and async variants exist | Footgun 1-3 resolved: use `pycopg/aliases.py`, `iscoroutinefunction` branch, `functools.wraps`, `stacklevel=2` |
| REORG-02 | Each migrated method keeps working flat alias on `db.*`/`async_db.*` — zero breaking change | Thin stubs with one-liner docstrings on `Database`/`AsyncDatabase` |
| REORG-03 | `test_parity` registers the timescale pair and verifies sync ↔ async surface parity | Parametrized registry seeded with `(TimescaleAccessor, AsyncTimescaleAccessor)` |
| REORG-04 | Coverage ≥94%; every alias tested for warn+delegate; no `-W error` noise | Migrate call-sites (D-08) + dedicated alias test class (D-09); no `filterwarnings` entry needed |
| TS-01 | `db.timescale.*` / `async_db.timescale.*` exposes 6 TimescaleDB methods; flat names remain as deprecated aliases | Bodies moved verbatim from `database.py:1648-1880` / `async_database.py:1220-1456` |
</phase_requirements>

---

## Summary

Phase 21 delivers two interrelated things: the `@deprecated_alias` decorator infrastructure (reused across all of v0.6.0) and the first concrete accessor (`db.timescale.*` with 6 methods). The pattern is a strict extension of the already-proven `db.spatial.*` and `db.etl.*` shape from v0.4.0/v0.5.0 — no new inventions, just a third iteration.

The codebase is in a clean state: current interrogate score is 100%, coverage gate is at 94%, no `filterwarnings` is configured in `pyproject.toml`, and the 6 timescale methods are fully documented and tested at their current flat-surface locations. The migration is a mechanical MOVE with a well-defined diff.

Three footguns from the CONTEXT.md were investigated in detail and each has a concrete, verified resolution. No surprises were found in the codebase that would complicate the plan.

**Primary recommendation:** create `pycopg/aliases.py` with a single `deprecated_alias(target_path)` decorator that branches on `inspect.iscoroutinefunction` and uses `stacklevel=2`. Each stub gets a one-line numpydoc docstring. No `filterwarnings` entry is needed if call-sites are migrated (D-08).

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `@deprecated_alias` decorator | Python module (`pycopg/aliases.py`) | — | Shared infra; imported at decoration time by `database.py` and `async_database.py` |
| TimescaleDB method logic | `pycopg/timescale.py` (TimescaleAccessor) | — | D-SCOPE-2: real impl lives in accessor |
| Deprecated flat stubs | `pycopg/database.py` / `pycopg/async_database.py` | — | Backwards-compat surface; thin delegators only |
| Lazy `db.timescale` property | `Database.__init__` + `@property` | `AsyncDatabase` mirror | Copies `_spatial`/`_etl` pattern exactly |
| Alias test coverage | `tests/test_timescale_aliases.py` (new) | `tests/test_parity.py` (registry) | D-09 and D-10 are separate concerns |
| Test call-site migration | `tests/test_database_integration.py`, `tests/test_async_database.py`, `tests/test_sql_injection.py` | — | D-08: existing tests migrate to `db.timescale.*` |

---

## Standard Stack

No new packages in this phase. All tooling is already installed.

### Tools in use [VERIFIED: pyproject.toml + .github/workflows/tests.yml]

| Tool | Version constraint | Purpose | Invocation |
|------|--------------------|---------|------------|
| `interrogate` | ≥1.7.0 | Docstring coverage gate (≥95%) | `uv run interrogate pycopg --fail-under 95 --quiet` |
| `sphinx-build` | via docs/requirements.txt | Sphinx -W build check | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` |
| `pytest` | ≥7.0.0 | Test suite | `uv run pytest` |
| `pytest-asyncio` | ≥0.23.0 | Async test support | `asyncio_mode = "auto"` in pyproject |

### Current baselines [VERIFIED: codebase + CI run]

| Gate | Current value | Phase 21 impact |
|------|---------------|-----------------|
| interrogate | 100.0% (350/350 documented) | Adds ~17 new items; all need docstrings |
| coverage | ≥94% gate | New lines (stubs + accessor) must be exercised by alias test class |
| filterwarnings | None configured in pyproject | D-08 migration keeps suite quiet; NO new filter needed |

---

## Package Legitimacy Audit

No new packages are installed in Phase 21. All code is pure-Python additions to the existing pycopg package.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

---

## Footgun Resolutions (the 3 open items from CONTEXT.md `<specifics>`)

### Footgun 1: `interrogate ≥95` + Sphinx `-W` vs. generic `(*args, **kwargs)` stubs

**Background:** `interrogate` counts every public method's `__doc__`. After decoration with `functools.wraps`, the wrapper gets `__doc__` from the STUB function (not from the accessor method). A stub with no docstring has `__doc__ = None`, which interrogate counts as undocumented.

**Quantified impact verified in this session:**
- Current total: 350 items, 100% documented.
- Phase 21 adds ~17 new interrogate-visible items (module docstring + 2 class docstrings + 12 method docstrings moved from database.py + 2 new `timescale` property docstrings).
- The 12 stubs (6 sync + 6 async) on `Database`/`AsyncDatabase` count as NEW items replacing the existing documented methods (net neutral on the database.py count since the old methods are removed).
- Without stub docstrings: ~96.7% — passes the 95% gate but drops from 100%.
- With stub docstrings: 100% maintained.
- Sphinx `-W` does NOT fail on `None` docstrings (autodoc handles them gracefully); however, a one-line summary docstring produces cleaner Sphinx output.

**Recommendation: Option (a) — one-line numpydoc docstring on each stub.** [VERIFIED: interrogate behaviour confirmed by local test run]

Pattern:
```python
@deprecated_alias("timescale.create_hypertable")
def create_hypertable(self, *args, **kwargs):
    """Deprecated: use ``db.timescale.create_hypertable`` instead."""
```

Why not option (b) (`functools.wraps` copying accessor's `__doc__` onto stub): the decorator runs at class-definition time. To look up the accessor method's docstring, the decorator would need a reference to `TimescaleAccessor` — creating a circular import between `database.py` and `timescale.py`. Option (a) avoids this entirely.

Why not option (c) (exclude stubs from interrogate target): `[tool.interrogate]` has no `ignore-regex` or `ignore-function` key. The only ignore options are structural (init-method, magic, private). Decorated stubs are public methods and will always be counted. There is no clean way to exclude them without adding interrogate configuration complexity.

**Boilerplate cost:** 12 one-liners across 2 files. Trivial. v0.7.0 deletion = delete the decorated stub block entirely.

---

### Footgun 2: `stacklevel` correctness through the decorator + lazy-property layers

**Call stack when `warnings.warn` executes inside the sync wrapper:**
```
Frame N   : user code — db.create_hypertable("events", "ts")    ← we want to point here
Frame N+1 : sync_wrapper (the decorated stub, living on Database)
Frame N+2 : warnings.warn(...)
```

`stacklevel=2` in `warnings.warn` means: "skip 2 frames above `warnings.warn`, point at frame N" — which IS the user's call site. [VERIFIED: confirmed with a live Python script in this session]

**Does resolving `self.timescale` (lazy property) add a frame?** No. The property getter executes as part of the wrapper body — it is an expression inside the wrapper function, not a call that appears on the Python call stack above `warnings.warn`. The property getter runs before `warnings.warn` is called; the frame above `warnings.warn` is still the wrapper itself. `stacklevel=2` is correct for BOTH sync and async variants.

**Async wrapper:** the async wrapper is `async def async_wrapper(self, *args, **kwargs)`. The call stack when `warnings.warn` executes:
```
Frame N   : user code — await db.create_hypertable("events", "ts")  ← target
Frame N+1 : async_wrapper (the coroutine body executing)
Frame N+2 : warnings.warn(...)
```
Same `stacklevel=2`. The `await` unwraps the coroutine — the awaiting frame IS the user's code.

**Test assertion technique — recommend asserting `w[0].filename` not just category/message:**

```python
import os
import warnings

def test_create_hypertable_alias_points_at_caller(self, db):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        db.create_hypertable("events", "ts")  # this line
    assert len(w) == 1
    assert w[0].category is DeprecationWarning
    # Warning must point at THIS test file, not inside pycopg/database.py
    assert os.path.basename(w[0].filename).startswith("test_")
    assert "database.py" not in w[0].filename
    assert "aliases.py" not in w[0].filename
```

Checking `w[0].filename` contains a test file name (not `database.py` or `aliases.py`) is more robust than checking an exact line number (which shifts with edits). [VERIFIED: technique confirmed with a live Python script in this session]

---

### Footgun 3: Async `await` delegation in the decorator

**The wrong pattern (sync wrapper returning a coroutine):**
```python
# WRONG: sync wrapper that returns the coroutine without awaiting
def wrapper(self, *args, **kwargs):
    warnings.warn(...)  # warning emitted here, before the coroutine runs
    return getattr(accessor, method)(*args, **kwargs)  # returns unawaited coroutine
```
This technically works (warning fires at call time) but: (a) `inspect.iscoroutinefunction(wrapper)` returns `False`, which would break `test_parity`'s method-type checks and potentially any caller that inspects method types, and (b) it's semantically surprising — the method looks synchronous but returns a coroutine.

**The correct pattern — `async def` wrapper with `iscoroutinefunction` branch:** [VERIFIED: confirmed with live Python script]

```python
if inspect.iscoroutinefunction(fn):
    @functools.wraps(fn)
    async def async_wrapper(self, *args, **kwargs):
        warnings.warn(msg, DeprecationWarning, stacklevel=2)
        accessor = getattr(self, accessor_name)
        return await getattr(accessor, method_name)(*args, **kwargs)
    return async_wrapper
```

This produces a wrapper where `inspect.iscoroutinefunction(async_wrapper)` returns `True` (because the wrapper itself is `async def`). `functools.wraps` copies `__name__`, `__doc__`, `__qualname__`, `__annotations__`, and `__module__` from the stub — it does NOT affect `iscoroutinefunction` status (that comes from `CO_COROUTINE` bytecode flag on the wrapper itself, not from the wrapped function).

**Verification of `functools.wraps` interaction:**
- `async_wrapper.__name__` → `"create_hypertable"` (from stub via `functools.wraps`)
- `async_wrapper.__doc__` → one-liner docstring (from stub via `functools.wraps`)
- `inspect.iscoroutinefunction(async_wrapper)` → `True` (from `async def` keyword)
- `inspect.iscoroutinefunction(sync_wrapper)` → `False` (from `def` keyword)

The `iscoroutinefunction` branch in the decorator is the correct mechanism. Two separate decorator factories (one for sync, one for async) are NOT needed — one factory with a branch is cleaner and Phases 22-24 use the identical decorator without modification.

**Warning timing:** The `warnings.warn` call is BEFORE the `await`, so the warning is emitted when the coroutine body starts executing (i.e., when the user `await`s the stub). This is the correct behaviour — the warning fires at the same conceptual moment as the sync variant.

---

## Architecture Patterns

### System Architecture Diagram

```
User code
    │
    ├── db.timescale.create_hypertable(...)     [new path — direct]
    │       │
    │       └── TimescaleAccessor.create_hypertable(self, ...)
    │               │  self._db.has_extension("timescaledb")
    │               │  validate_identifiers(...) / validate_interval(...)
    │               └── self._db.execute(f"SELECT create_hypertable(...)")
    │
    └── db.create_hypertable(...)               [deprecated alias — warns + delegates]
            │  warnings.warn("use db.timescale.create_hypertable ...", DeprecationWarning, stacklevel=2)
            │  accessor = self.timescale         [lazy property — creates+caches TimescaleAccessor(self)]
            └── accessor.create_hypertable(*args, **kwargs)   [same body as above]
```

### Recommended Project Structure

```
pycopg/
├── aliases.py          # NEW: deprecated_alias() decorator (reused by phases 22-24)
├── timescale.py        # NEW: TimescaleAccessor + AsyncTimescaleAccessor
├── database.py         # EDIT: add _timescale field + timescale property + 6 thin stubs
├── async_database.py   # EDIT: add _timescale field + timescale property + 6 thin stubs
└── __init__.py         # EDIT: add TimescaleAccessor, AsyncTimescaleAccessor to __all__

tests/
├── test_timescale_aliases.py   # NEW: dedicated alias warn+delegate tests (D-09)
├── test_parity.py              # EDIT: data-driven registry seeded with timescale pair (D-10)
├── test_database_integration.py # EDIT: migrate 5 call-sites to db.timescale.* (D-08)
├── test_async_database.py       # EDIT: migrate ~18 call-sites to db.timescale.* (D-08)
└── test_sql_injection.py        # EDIT: migrate 4 call-sites to db.timescale.* (D-08)
```

### Pattern 1: `deprecated_alias` decorator (complete implementation)

```python
# pycopg/aliases.py
"""Deprecated alias decorator for the v0.6.0 accessor reorganisation."""

from __future__ import annotations

import functools
import inspect
import warnings


def deprecated_alias(target_path: str):
    """Decorate a flat stub to warn and delegate to an accessor method.

    Parameters
    ----------
    target_path : str
        Dotted path of the form ``"<accessor>.<method>"`` — e.g.
        ``"timescale.create_hypertable"``.  Resolved lazily on ``self``
        at call time so no hard reference is needed at decoration time.

    Returns
    -------
    Callable
        A decorator that replaces the stub with warn-then-delegate logic.
        The wrapper is ``async def`` when the stub is a coroutine function,
        ``def`` otherwise.
    """

    def decorator(fn):
        msg = (
            f"use `db.{target_path}` instead; "
            f"the flat `db.{fn.__name__}` alias is deprecated "
            "and will be removed in v0.7.0"
        )
        accessor_name, method_name = target_path.split(".", 1)

        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def async_wrapper(self, *args, **kwargs):
                warnings.warn(msg, DeprecationWarning, stacklevel=2)
                accessor = getattr(self, accessor_name)
                return await getattr(accessor, method_name)(*args, **kwargs)
            return async_wrapper
        else:
            @functools.wraps(fn)
            def sync_wrapper(self, *args, **kwargs):
                warnings.warn(msg, DeprecationWarning, stacklevel=2)
                accessor = getattr(self, accessor_name)
                return getattr(accessor, method_name)(*args, **kwargs)
            return sync_wrapper

    return decorator
```

### Pattern 2: `timescale.py` module boilerplate

Mirror `etl.py` and `spatial.py` exactly:
- `from __future__ import annotations` at top [VERIFIED: both etl.py and async_database.py use it]
- `TYPE_CHECKING` guard for parent class imports [VERIFIED: etl.py lines 41-43]
- Module-level docstring (required by interrogate — `ignore-init-module = false`)
- Both `TimescaleAccessor` and `AsyncTimescaleAccessor` in the same module
- `__init__(self, db: Database) -> None` / `__init__(self, db: AsyncDatabase) -> None`

```python
# pycopg/timescale.py
"""TimescaleDB accessor classes for db.timescale.* / async_db.timescale.*."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pycopg import queries
from pycopg.exceptions import ExtensionNotAvailable
from pycopg.utils import validate_identifier, validate_identifiers, validate_interval

if TYPE_CHECKING:
    from pycopg.async_database import AsyncDatabase
    from pycopg.database import Database


class TimescaleAccessor:
    """TimescaleDB helper namespace exposed as ``db.timescale``.

    Methods are moved verbatim from ``Database``. The extension guard
    (``has_extension("timescaledb")``) is checked inside each method,
    not at construction, consistent with the ETL accessor pattern.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    # ... 6 methods moved verbatim, s/self\./self._db\./g ...


class AsyncTimescaleAccessor:
    """Async TimescaleDB helper namespace exposed as ``async_db.timescale``.

    Mirrors :class:`TimescaleAccessor` exactly with ``await`` calls.
    """

    def __init__(self, db: AsyncDatabase) -> None:
        self._db = db

    # ... 6 async methods moved verbatim ...
```

### Pattern 3: Lazy `timescale` property on `Database`

Exact copy of `etl` property at `database.py:253-271`:

```python
# In Database.__init__ (at database.py:85-86 area):
self._timescale: TimescaleAccessor | None = None

# TYPE_CHECKING block at database.py:54-59 area — add:
if TYPE_CHECKING:
    from pycopg.timescale import TimescaleAccessor  # add this line

# New property after the etl property:
@property
def timescale(self) -> TimescaleAccessor:
    """Get or create the TimescaleDB accessor (lazy initialization).

    Returns
    -------
    TimescaleAccessor
        TimescaleDB helper namespace bound to this database.
    """
    if self._timescale is None:
        from pycopg.timescale import TimescaleAccessor

        self._timescale = TimescaleAccessor(self)
    return self._timescale
```

(Mirror identically in `async_database.py` using `AsyncTimescaleAccessor`.)

### Pattern 4: Thin deprecated stubs on `Database`

```python
# In database.py, REPLACE the full create_hypertable body with:
from pycopg.aliases import deprecated_alias  # at module top

@deprecated_alias("timescale.create_hypertable")
def create_hypertable(self, *args, **kwargs):
    """Deprecated: use ``db.timescale.create_hypertable`` instead."""

# Repeat for all 6 methods
```

The `pass` body is NOT needed because the decorator replaces the entire function with the wrapper. The stub body (`pass`) is never executed; only the docstring is preserved via `functools.wraps`.

### Pattern 5: Data-driven parity registry (`test_parity.py`)

Replace the single `TestEtlParity` class structure with a parametrized approach:

```python
# In tests/test_parity.py — add after existing imports:
from pycopg.timescale import AsyncTimescaleAccessor, TimescaleAccessor

# Registry: list of (SyncAccessor, AsyncAccessor) pairs
# Phases 22-24 APPEND to this list — no other changes needed
ACCESSOR_PAIRS = [
    (TimescaleAccessor, AsyncTimescaleAccessor),
]

@pytest.mark.parametrize("sync_cls, async_cls", ACCESSOR_PAIRS)
def test_accessor_parity(sync_cls, async_cls):
    """Verify public surface parity for each accessor pair (D-10)."""
    sync_methods = {
        name for name, _ in inspect.getmembers(sync_cls) if not name.startswith("_")
    }
    async_methods = {
        name for name, _ in inspect.getmembers(async_cls) if not name.startswith("_")
    }
    missing_in_async = sync_methods - async_methods
    assert not missing_in_async, (
        f"{sync_cls.__name__} has members absent from {async_cls.__name__}: "
        f"{sorted(missing_in_async)}"
    )
    extra_in_async = async_methods - sync_methods
    assert not extra_in_async, (
        f"{async_cls.__name__} has extra members absent from {sync_cls.__name__}: "
        f"{sorted(extra_in_async)}"
    )
```

Note: the CONTEXT.md says folding `TestEtlParity` into the registry is optional and only if zero-risk. Given the ETL pair can simply be appended to `ACCESSOR_PAIRS`, folding is low-risk and keeps the registry coherent — but leave the decision to the planner.

### Pattern 6: Dedicated alias test class

```python
# tests/test_timescale_aliases.py (new file)
"""Tests that deprecated flat aliases warn and delegate (REORG-04, D-09)."""

import os
import warnings

import pytest

from pycopg.timescale import TimescaleAccessor  # import for isinstance checks


class TestTimescaleAliases:
    """Each flat db.* alias must warn AND delegate to db.timescale.*."""

    _ALIASES = [
        "create_hypertable",
        "enable_compression",
        "add_compression_policy",
        "add_retention_policy",
        "list_hypertables",
        "hypertable_info",
    ]

    @pytest.fixture
    def mock_ts_db(self, mocker, db):
        """db with mocked timescale accessor so no real DB is needed."""
        mock_accessor = mocker.MagicMock(spec=TimescaleAccessor)
        mocker.patch.object(type(db), "timescale", new_callable=lambda: property(lambda self: mock_accessor))
        return db, mock_accessor

    def test_create_hypertable_warns_and_delegates(self, mock_ts_db):
        db, acc = mock_ts_db
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            db.create_hypertable("events", "ts")
        assert len(w) == 1
        assert w[0].category is DeprecationWarning
        assert "db.timescale.create_hypertable" in str(w[0].message)
        assert "v0.7.0" in str(w[0].message)
        # Warning must point at THIS file, not inside pycopg internals
        assert "test_" in os.path.basename(w[0].filename)
        acc.create_hypertable.assert_called_once_with("events", "ts")

    # ... repeat for each of the 6 aliases ...
```

### Anti-Patterns to Avoid

- **Circular import via accessor docstring copying at decoration time:** Option (b) requires the decorator to look up the accessor's `__doc__` by importing `TimescaleAccessor`. Since `database.py` imports from `timescale.py`, and `timescale.py` imports from `database.py` via `TYPE_CHECKING`, any non-`TYPE_CHECKING` import would create a circular dependency. The one-liner docstring avoids this entirely.
- **Sync wrapper returning an async coroutine:** Makes `inspect.iscoroutinefunction(stub)` return `False`, which breaks parity checks and is surprising to callers. Always use an `async def` wrapper for async stubs.
- **`stacklevel=1` in warnings.warn:** Points at the wrapper function body (inside `aliases.py`), not at the user's call site. Always use `stacklevel=2`.
- **`filterwarnings = ["ignore::DeprecationWarning"]` in pyproject.toml:** Would silently swallow ALL DeprecationWarnings, hiding issues from callers. The correct fix is D-08: migrate test call-sites.
- **Lazy property resolving `self.timescale` inside `warnings.warn` (before it fires):** This does NOT happen — the property is resolved AFTER `warnings.warn` returns, in the next statement of the wrapper. No frame-counting concern.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Warn + delegate wrapper | N unique wrappers per alias | `@deprecated_alias` decorator | Uniform message, correct stacklevel, trivial v0.7.0 deletion |
| Async-detection in decorator | Two separate decorator factories | `inspect.iscoroutinefunction` branch | Standard Python stdlib, no deps |
| Metadata preservation | Manually copy `__name__`/`__doc__` | `functools.wraps` | Handles `__name__`, `__doc__`, `__qualname__`, `__module__`, `__annotations__`, `__wrapped__` |
| Parity testing per accessor | N copies of parity test | Parametrized `ACCESSOR_PAIRS` registry | Phases 22-24 just append, no logic duplication |

---

## Existing Code — Precise Edit Map

### `pycopg/database.py` — exact edits

1. **Add import at module top** (after existing imports):
   ```python
   from pycopg.aliases import deprecated_alias
   ```

2. **Add `TYPE_CHECKING` import** (in the `if TYPE_CHECKING:` block at line 54-59):
   ```python
   from pycopg.timescale import TimescaleAccessor
   ```

3. **Add `_timescale` field in `__init__`** (at line 85-86, after `self._etl: ETLAccessor | None = None`):
   ```python
   self._timescale: TimescaleAccessor | None = None
   ```

4. **Add `timescale` property** (after the `etl` property at line 253-271, same docstring structure):
   ```python
   @property
   def timescale(self) -> TimescaleAccessor:
       """Get or create the TimescaleDB accessor (lazy initialization). ..."""
       if self._timescale is None:
           from pycopg.timescale import TimescaleAccessor
           self._timescale = TimescaleAccessor(self)
       return self._timescale
   ```

5. **Replace the TIMESCALEDB OPERATIONS block** (lines 1645-1880) with 6 thin stubs:
   ```python
   # TIMESCALEDB OPERATIONS (deprecated aliases — real impl in db.timescale.*)
   @deprecated_alias("timescale.create_hypertable")
   def create_hypertable(self, *args, **kwargs):
       """Deprecated: use ``db.timescale.create_hypertable`` instead."""

   # ... 5 more stubs ...
   ```

### `pycopg/async_database.py` — mirror of above

1. Add `from pycopg.aliases import deprecated_alias`
2. Add `from pycopg.timescale import AsyncTimescaleAccessor` in `TYPE_CHECKING` block (line 50-55 area, following spatial.py/etl.py pattern)
3. Add `self._timescale: AsyncTimescaleAccessor | None = None` in `__init__` (line 84-85 area)
4. Add `timescale` property (after `etl` property at line 114-131)
5. Replace async TIMESCALEDB OPERATIONS block (lines 1220-1456) with 6 async thin stubs

### `pycopg/__init__.py` — add two exports

In the imports and `__all__`:
```python
from pycopg.timescale import AsyncTimescaleAccessor, TimescaleAccessor
# In __all__:
"TimescaleAccessor",
"AsyncTimescaleAccessor",
```
(Formal Phase 24 docs/README wiring — but the export itself must land in Phase 21 per the CONTEXT.md canonical refs.)

---

## Existing Test Call-Sites to Migrate (D-08)

### `tests/test_database_integration.py` — 5 call-sites [VERIFIED: grep]

| Line | Current | Migrate To |
|------|---------|-----------|
| 858 | `ts_db.create_hypertable(t, "ts", ...)` | `ts_db.timescale.create_hypertable(t, "ts", ...)` |
| 860 | `ts_db.hypertable_info(t)` | `ts_db.timescale.hypertable_info(t)` |
| 863 | `ts_db.list_hypertables()` | `ts_db.timescale.list_hypertables()` |
| 872 | `ts_db.enable_compression(t, ...)` | `ts_db.timescale.enable_compression(t, ...)` |
| 873-874 | `ts_db.add_compression_policy(...)` / `ts_db.add_retention_policy(...)` | prefix with `.timescale` |
| 883 | `db.create_hypertable(t, "ts")` (extension-absent test) | `db.timescale.create_hypertable(t, "ts")` |

Note: line 883 tests `ExtensionNotAvailable` from `db.create_hypertable` — after migration this should call `db.timescale.create_hypertable` (the guard is in the accessor, so same result).

### `tests/test_async_database.py` — 18 call-sites [VERIFIED: grep]

All in `TestAsyncDatabaseTimescaleDB` class (lines 2224-2397) plus 3 at lines 2847-2850. Pattern: `await db.create_hypertable(...)` → `await db.timescale.create_hypertable(...)` etc. These tests mock `db.has_extension` and `db.execute` directly — mocks still work because the accessor routes through `self._db`.

### `tests/test_sql_injection.py` — 4 call-sites [VERIFIED: grep]

| Line | Current | Migrate To |
|------|---------|-----------|
| 124 | `sync_db.add_compression_policy("events", ...)` | `sync_db.timescale.add_compression_policy(...)` |
| 130 | `sync_db.add_retention_policy("logs", ...)` | `sync_db.timescale.add_retention_policy(...)` |
| 200 | `await async_db.add_compression_policy(...)` | `await async_db.timescale.add_compression_policy(...)` |
| 205 | `await async_db.add_retention_policy(...)` | `await async_db.timescale.add_retention_policy(...)` |

**Total call-sites to migrate: 27** (5 + 18 + 4)

---

## `pycopg/timescale.py` Module Boilerplate

Based on direct inspection of `etl.py` and `spatial.py` [VERIFIED: both files read]:

```python
"""TimescaleDB accessor classes for db.timescale.* / async_db.timescale.*."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pycopg import queries
from pycopg.exceptions import ExtensionNotAvailable
from pycopg.utils import validate_identifier, validate_identifiers, validate_interval

if TYPE_CHECKING:
    from pycopg.async_database import AsyncDatabase
    from pycopg.database import Database
```

`from __future__ import annotations` is needed because `Database` and `AsyncDatabase` are used as type annotations in `__init__` but imported only under `TYPE_CHECKING`. Both `etl.py` (line 25) and `async_database.py` (line 7) use this pattern. `spatial.py` does not (it uses `geopandas` type annotations differently). Follow `etl.py` as the closer precedent.

---

## Common Pitfalls

### Pitfall 1: forgetting `async def` wrapper for async stubs

**What goes wrong:** A sync wrapper that returns a coroutine from the accessor passes functionality but fails `inspect.iscoroutinefunction()` checks (returns `False` on the stub). This can break `test_parity` if it checks coroutine status, and is confusing for tools and callers.

**Why it happens:** The obvious pattern `def wrapper(...): return accessor_method(...)` is sync even when `accessor_method` is async.

**How to avoid:** The `iscoroutinefunction(fn)` branch in `deprecated_alias` ensures the stub's async nature is preserved in the wrapper.

**Warning signs:** `inspect.iscoroutinefunction(db.create_hypertable)` returns `False` for async database.

### Pitfall 2: `stacklevel=1` emits warning inside `aliases.py`

**What goes wrong:** The warning's `filename` and `lineno` in `w[0]` point to `aliases.py` (the decorator internals), not the user's code. Pytest `-W error::DeprecationWarning` still fires, but the traceback is confusing.

**How to avoid:** Always `stacklevel=2` in the wrapper body.

**Warning signs:** `w[0].filename` contains `"aliases.py"` instead of the test file.

### Pitfall 3: `self.has_extension` instead of `self._db.has_extension` in accessor bodies

**What goes wrong:** The moved method bodies reference `self.has_extension(...)` (from the old `Database.has_extension` method). Inside the accessor, `self` is the accessor, not the database.

**How to avoid:** D-06: replace ALL `self.execute(...)` → `self._db.execute(...)` and `self.has_extension(...)` → `self._db.has_extension(...)` when moving bodies.

**Warning signs:** `AttributeError: 'TimescaleAccessor' object has no attribute 'has_extension'`

### Pitfall 4: `validate_interval(chunk_time_interval)` call without import in `timescale.py`

**What goes wrong:** The moved method bodies call `validate_identifiers`, `validate_identifier`, `validate_interval` — these are in `pycopg.utils`. They must be imported at the top of `timescale.py`.

**How to avoid:** Include all three in the module-level imports (see boilerplate above).

### Pitfall 5: Circular import if `timescale.py` imports `database.py` unconditionally

**What goes wrong:** `database.py` imports `timescale.py` (for the `timescale` property's lazy import), and `timescale.py` needs `Database`/`AsyncDatabase` type annotations. An unconditional import creates a circular dependency at module load time.

**How to avoid:** Use `if TYPE_CHECKING:` guard for the parent class imports in `timescale.py` (same as `etl.py` pattern). The lazy `from pycopg.timescale import TimescaleAccessor` inside the property body avoids the import cycle at runtime.

### Pitfall 6: Not migrating sql-injection tests causes `DeprecationWarning` noise

**What goes wrong:** `test_sql_injection.py` calls `sync_db.add_compression_policy(...)` directly. After Phase 21, these calls go through the deprecated alias and emit a `DeprecationWarning`. If any CI config adds `-W error::DeprecationWarning` in the future, the injection tests break.

**How to avoid:** Migrate all 27 call-sites listed above (D-08) in the same PR as the alias introduction. The alias test class (D-09) is the ONLY place that should call the flat deprecated names.

---

## Code Examples

### Concrete deprecated alias stub in `database.py`

```python
# Source: D-02 decision + verified pattern
from pycopg.aliases import deprecated_alias

@deprecated_alias("timescale.create_hypertable")
def create_hypertable(self, *args, **kwargs):
    """Deprecated: use ``db.timescale.create_hypertable`` instead."""

@deprecated_alias("timescale.enable_compression")
def enable_compression(self, *args, **kwargs):
    """Deprecated: use ``db.timescale.enable_compression`` instead."""

@deprecated_alias("timescale.add_compression_policy")
def add_compression_policy(self, *args, **kwargs):
    """Deprecated: use ``db.timescale.add_compression_policy`` instead."""

@deprecated_alias("timescale.add_retention_policy")
def add_retention_policy(self, *args, **kwargs):
    """Deprecated: use ``db.timescale.add_retention_policy`` instead."""

@deprecated_alias("timescale.list_hypertables")
def list_hypertables(self, *args, **kwargs):
    """Deprecated: use ``db.timescale.list_hypertables`` instead."""

@deprecated_alias("timescale.hypertable_info")
def hypertable_info(self, *args, **kwargs):
    """Deprecated: use ``db.timescale.hypertable_info`` instead."""
```

### TimescaleDB extension guard in accessor

```python
# Source: database.py:1681-1684 verbatim, s/self\./self._db\./
def create_hypertable(self, table, time_column, schema="public",
                      chunk_time_interval="1 day", if_not_exists=True, migrate_data=True):
    """Convert a table to a TimescaleDB hypertable.
    ... (existing numpydoc docstring, moved verbatim) ...
    """
    if not self._db.has_extension("timescaledb"):
        raise ExtensionNotAvailable(
            "TimescaleDB extension not installed. Run db.create_extension('timescaledb')"
        )
    validate_identifiers(table, schema, time_column)
    validate_interval(chunk_time_interval)
    self._db.execute(f"""
        SELECT create_hypertable(
            '{schema}.{table}',
            '{time_column}',
            chunk_time_interval => INTERVAL '{chunk_time_interval}',
            if_not_exists => {str(if_not_exists).upper()},
            migrate_data => {str(migrate_data).upper()}
        )
    """)
```

---

## Environment Availability

This phase is purely code changes with no external tool or service dependencies beyond the existing dev stack.

| Dependency | Available | Version | Notes |
|------------|-----------|---------|-------|
| `uv` | Yes | (in PATH) | Dev environment manager |
| `interrogate` | Yes | ≥1.7.0 | `uv run interrogate pycopg` — currently 100% |
| `pytest` + `pytest-asyncio` | Yes | ≥7.0.0, ≥0.23.0 | `asyncio_mode = "auto"` configured |
| TimescaleDB (local) | Yes | (CI: `timescale/timescaledb-ha:pg17`) | Needed only for integration tests (already in CI) |

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_timescale_aliases.py tests/test_parity.py -x -q -o addopts=""` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | File | Automated Command |
|--------|----------|-----------|------|-------------------|
| REORG-01 | decorator emits DeprecationWarning, correct stacklevel | unit | `tests/test_timescale_aliases.py` (new) | `uv run pytest tests/test_timescale_aliases.py -x -q -o addopts=""` |
| REORG-02 | flat alias still delegates correctly | unit | `tests/test_timescale_aliases.py` (new) | same |
| REORG-03 | sync/async parity for TimescaleAccessor | unit | `tests/test_parity.py` | `uv run pytest tests/test_parity.py -x -q -o addopts=""` |
| REORG-04 | no DeprecationWarning noise in main suite | integration | all migrated tests | `uv run pytest -W error::DeprecationWarning -x -q -o addopts=""` |
| TS-01 | accessor methods return same results | integration | `tests/test_database_integration.py` (migrated) | `uv run pytest tests/test_database_integration.py::TestDatabaseTimescaleCoverage -x -q -o addopts=""` |

### Wave 0 Gaps

- [ ] `pycopg/aliases.py` — new module, does not exist yet
- [ ] `pycopg/timescale.py` — new module, does not exist yet
- [ ] `tests/test_timescale_aliases.py` — new test file (D-09)

---

## Security Domain

This phase is a pure internal refactor — it moves existing, already-security-reviewed code (SQL injection-protected via `validate_identifiers`/`validate_interval` which travel with the moved bodies). No new input paths, no new SQL construction, no new external calls. The `validate_*` guards are part of the moved bodies and remain in effect.

No new ASVS considerations beyond what is already in place.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Stubs without docstrings score 96.7% (passes 95% gate) | Footgun 1 | Low — calculated from actual interrogate total of 350; the exact count may vary by ±5 if some items were miscounted, but the margin is large enough | 
| A2 | `Sphinx -W` does not fail on `None` docstrings for autodoc | Footgun 1 | Low — standard Sphinx behaviour; if Sphinx build is failing for another reason, investigate separately |
| A3 | The existing async timescale mocked tests work after migration (mocks on `db.has_extension` / `db.execute` are still effective) | Test migration | Medium — confirmed by reading the accessor pattern (accessor routes through `self._db`), but not live-tested |

**All other claims in this research were VERIFIED by direct code inspection or live Python execution in this session.**

---

## Open Questions

1. **Should `TestEtlParity` be folded into the new `ACCESSOR_PAIRS` registry?**
   - What we know: `TestEtlParity` (test_parity.py:466) does the same `inspect.getmembers` check that the new parametrized test would do.
   - What's unclear: whether folding adds any risk (it shouldn't — the logic is identical).
   - Recommendation: fold it in the same PR. Append `(ETLAccessor, AsyncETLAccessor)` to `ACCESSOR_PAIRS`. Mark the old `TestEtlParity` class as removed. Net change: -30 lines, +1 list entry.

2. **`pycopg/aliases.py` name vs. `pycopg/utils.py`?**
   - Recommendation: `pycopg/aliases.py` for clean separation. Phases 22-24 import from the same file. The validator functions in `utils.py` are all about input validation, which is a different concern.

---

## Sources

### Primary (HIGH confidence)

- `pycopg/database.py` lines 1-100, 228-271, 1645-1880 — verified lazy-property pattern, timescale method bodies
- `pycopg/async_database.py` lines 1-50, 80-132, 1220-1456 — verified async mirror pattern, async timescale bodies
- `pycopg/etl.py` lines 1-50 — module boilerplate template (`from __future__ import annotations`, `TYPE_CHECKING` pattern)
- `pycopg/spatial.py` lines 1023-1080, 1859-1920 — `SpatialAccessor`/`AsyncSpatialAccessor` `__init__` and `_db` pattern
- `pycopg/__init__.py` — `__all__` export pattern for accessor classes
- `pyproject.toml` — interrogate config (`fail-under = 95`, `ignore-init-method = true`), pytest addopts (`--cov-fail-under=94`), no filterwarnings
- `.github/workflows/tests.yml` — CI interrogate invocation (`uv run interrogate pycopg --fail-under 95 --quiet`), Sphinx `-W` invocation

### Secondary (MEDIUM confidence)

- Live Python execution in this session: `stacklevel=2` correctness verified, async wrapper `iscoroutinefunction` verified, `functools.wraps` docstring propagation verified

### Tertiary (LOW confidence — see Assumptions Log)

- Sphinx `-W` behaviour with `None` docstrings: not live-tested but standard documented behaviour

---

## Metadata

**Confidence breakdown:**
- Decorator mechanics: HIGH — live-verified with Python scripts
- Interrogate impact: HIGH — live-verified with `uv run interrogate pycopg`
- Call-site migration list: HIGH — verified with grep across all test files
- Sphinx -W docstring behaviour: MEDIUM — training knowledge, standard Sphinx behaviour, not live-tested

**Research date:** 2026-06-17
**Valid until:** 2026-07-17 (stable domain — decorator/warnings stdlib, no fast-moving dependencies)
