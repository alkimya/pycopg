# Phase 41: API Homogenization — Research

**Researched:** 2026-06-28
**Domain:** Python API deprecation mechanics, PEP 562 `__getattr__`, keyword-only signatures, SemVer documentation
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Deprecated names removed only in 2.0 — strict SemVer. All of 1.x keeps aliases live.
- **D-02:** `docs/stability.md` publishes a full support matrix: Python versions, PostgreSQL/PostGIS ranges (floor 3.0 hard, 3.2 recommended), TimescaleDB ranges, per-API stable/experimental tier table. Concrete versions from `pyproject.toml` + PostGIS research floor.
- **D-03:** Enforce `*` in signatures. Rule: required args stay positional (`table`, `geom`); all optional/defaulted params become keyword-only (`filter=`, `into=`, `order_by=`, `limit=`, `schema=`, etc.). Apply across 7 accessors + flat core.
- **D-04:** `*`-enforcement ships as a clean 0.x→1.0 breaking change — NO transitional positional shim. Documented in MIGRATION + `docs/stability.md`.
- **D-05:** Audit-then-decide. Full inventory pass across all 7 accessors + flat core. User reviews inventory before any fixes land (review gate).
- **D-06:** Per-finding disposition: name renames get one-cycle deprecation alias; structural/positional/default changes ship as clean 1.0 breaks with MIGRATION entries.
- **D-07:** Exception aliases warn on import/access only via module-level `__getattr__` (PEP 562) on `pycopg/exceptions.py`. Old name resolves to the same class object so `except OldName:` still works.
- **D-08:** Success criterion #2 relaxed to "imported/accessed" — NO catch-time metaclass hack.
- **D-09:** Every `warnings.warn(...)` must use a `stacklevel` that points to the caller's file — verified by a test asserting warning location.
- **D-10:** `-W error::DeprecationWarning` CI gate must stay green: no internal `pycopg/` code routes through a deprecated path. Grep `pycopg/` for old names before shipping.
- **D-11:** Sync/async parity non-negotiable. `where=`→`filter=` rename and any audit fix lands identically on both accessors; `test_accessor_parity` stays green.

### Claude's Discretion

- Exact shim shape for `where=`→`filter=` (per-signature `filter=None, where=None` + runtime check vs a shared decorator/helper over the 11×2 sites), provided it satisfies D-09/D-10 and produces a clean frozen signature.
- Exact `docs/stability.md` section layout and precise version numbers in the support matrix.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope. Spatial v2 methods, transaction/isolation/savepoint gaps, named params, health, logging, and mypy-strict are all scheduled in Phases 42–46.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FREEZE-01 | Spatial `where=` renamed to `filter=` on all 11 spatial methods (both accessors + 11 builders + `_append_tail`); old `where=` keeps working one cycle with `DeprecationWarning` + MIGRATION | §Standard Stack, §Architecture Patterns, §Code Examples — shim shape, stacklevel mechanics, `_append_tail` choke-point |
| FREEZE-02 | 4 N818 exception renames → `*Error`; old names as deprecated aliases via PEP 562 `__getattr__`; internal raise sites updated; N818 suppression removed from `pyproject.toml` | §Architecture Patterns — PEP 562 mechanism; §Common Pitfalls — rename checklist; §Code Examples — concrete `__getattr__` shape |
| FREEZE-03 | Public API consistency audit + documented Stable API Contract (positional vs keyword-only) for every public method; audit-then-decide with user review gate before fixes land | §Architecture Patterns — FREEZE-03 audit dimensions; §Don't Hand-Roll — kw-only enforcement |
| FREEZE-04 | `docs/stability.md` published (SemVer + deprecation policy), linked from README; support matrix with concrete version numbers | §Standard Stack version floor table; §Code Examples — `docs/stability.md` outline |
</phase_requirements>

---

## Summary

Phase 41 is a pure API-surface refactoring phase with no new PostgreSQL/PostGIS functionality. The primary technical domain is Python's deprecation machinery (`warnings.warn`, PEP 562 module `__getattr__`, `stacklevel` counting), keyword-only enforcement (`*` separator in function signatures), and SemVer documentation. All code to be modified is in existing files; no new modules are created.

The most consequential decision already locked is D-07: the 4 exception renames use PEP 562 module `__getattr__` on `pycopg/exceptions.py` (not a `@deprecated_alias` decorator), and warn only on import/attribute access. This is the right choice because (a) it is the cleanest mechanism for module-level name aliasing, (b) the old name resolves to the identical class object so `except OldName:` keeps catching without modification, and (c) it avoids the fragile metaclass hack that would be needed for catch-time warning.

The `where=`→`filter=` rename is the largest mechanical footprint: 11 builders + 11 `SpatialAccessor` methods + 11 `AsyncSpatialAccessor` methods = 33 signature sites, plus `_append_tail` (the single internal choke-point). The recommended implementation is per-signature `filter=None, where=None` with a runtime check in each accessor method body (not in the builder), so the builder's frozen public signature is clean (`filter=`-only) while the accessor absorbs the backward-compat shim.

The FREEZE-03 consistency audit is a discovery phase: the findings table must be produced and reviewed before any fixes land (D-05). Research has identified the key dimensions to tabulate and the expected inconsistency categories — notably `schema=` default inconsistency across accessor families and `into=` routing semantics differences.

**Primary recommendation:** Implement in 4 waves — (1) exception rename + PEP 562 aliases, (2) `where=`→`filter=` shim on all 33 sites, (3) FREEZE-03 audit + user gate + kw-only enforcement, (4) `docs/stability.md` + MIGRATION. Add the `-W error::DeprecationWarning` pytest gate in Wave 1 so subsequent waves run under it automatically.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| `where=`→`filter=` shim | `pycopg/spatial.py` accessor methods | `_append_tail` internal function (receives renamed param) | Accessors are the public API boundary; builders remain internal and purely renamed |
| Exception PEP 562 alias | `pycopg/exceptions.py` module `__getattr__` | `pycopg/__init__.py` package `__getattr__` (re-export) | Aliases must live at the module that defines the class and at the package re-export surface |
| Keyword-only enforcement (`*`) | All 7 accessor files + `pycopg/database.py` / `pycopg/async_database.py` | — | Each file must add `*` at the right position in its own signatures |
| `-W error::DeprecationWarning` CI gate | `pyproject.toml` `[tool.pytest.ini_options]` | `tests.yml` step (optional, pytest config is sufficient) | pytest `filterwarnings` config propagates to all `uv run pytest` invocations |
| `docs/stability.md` | `docs/source/stability.md` (new file) | `docs/conf.py` toctree, `README.md` link | Sphinx builds from `docs/` with `-W` gate; README is the primary user entry point |
| MIGRATION guide section | `MIGRATION.md` new section `## v0.10.x → 1.0.0` | — | Existing file established in v0.6.0→v0.7.0 transition; same file, new section |

---

## Standard Stack

### Core (no changes to runtime deps)

| Component | Version | Purpose | Why Standard |
|-----------|---------|---------|--------------|
| Python `warnings` stdlib | 3.11+ | `warnings.warn(msg, DeprecationWarning, stacklevel=N)` | PEP 565: DeprecationWarning shown by default in `__main__` and filtered in tests unless explicitly captured. The correct module for this phase. |
| Python `warnings.warn` | 3.11+ | stacklevel-counted deprecation emission | No external dep needed. |
| Python PEP 562 (`__getattr__`) | 3.7+ (module-level `__getattr__` standardized) | Module-level attribute alias with lazy warning emission | Cleaner than class-level alias for the exception rename case; works identically for `from pycopg.exceptions import OldName` and `pycopg.exceptions.OldName` access. |
| ruff N818 | (already in pyproject.toml ruff config) | Exception naming lint rule | Removing the `"pycopg/exceptions.py" = ["N818"]` per-file suppression is the acceptance signal for FREEZE-02. |

[ASSUMED] - versions above are from training knowledge / direct pyproject.toml read; all are standard Python stdlib behavior, not versioned packages.

### No New Dependencies

This phase adds zero runtime dependencies. The deprecation machinery is pure stdlib `warnings`. PEP 562 is a Python language feature, not a library.

---

## Package Legitimacy Audit

> Phase installs NO new external packages. Audit section not applicable.

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

---

## Architecture Patterns

### System Architecture Diagram

```
User code (import / call)
         |
         v
pycopg/__init__.py
  - re-exports exception names (direct import or __getattr__ for deprecated)
  - re-exports SpatialAccessor/AsyncSpatialAccessor
         |
         +---> pycopg/exceptions.py
         |       - New *Error canonical classes defined
         |       - module __getattr__ → warns + returns same class object for old names
         |
         +---> pycopg/spatial.py
         |       - SpatialAccessor: public methods with filter=None, where=None shim
         |       - AsyncSpatialAccessor: same shim, async def
         |       - build_*_sql builders: RENAMED to filter= only (clean frozen sig)
         |       - _append_tail: RENAMED to filter param internally
         |
         +---> pycopg/ (7 accessor files)
                 - keyword-only * enforcement added to all optional params
```

### Recommended Project Structure (Phase 41 touches)

```
pycopg/
├── exceptions.py          # 4 class renames + module __getattr__
├── spatial.py             # 33 signature sites + _append_tail param rename
├── utils.py               # raise InvalidIdentifier → raise InvalidIdentifierError (internal)
├── schema.py              # raise TableNotFound → raise TableNotFoundError (internal)
├── database.py            # raise DatabaseExists → raise DatabaseExistsError (internal); kw-only audit
├── async_database.py      # raise DatabaseExists → raise DatabaseExistsError (internal); kw-only audit
├── timescale.py           # raise ExtensionNotAvailable → raise ExtensionNotAvailableError (internal)
├── [all other accessors]  # kw-only * enforcement (FREEZE-03 audit outcome)
├── __init__.py            # Update exception re-exports: add *Error names + package __getattr__ for deprecated

docs/source/
└── stability.md           # NEW — SemVer policy + deprecation timeline + support matrix

MIGRATION.md               # New section: v0.10.x → 1.0.0 (filter=, *Error names, kw-only)
```

---

### Pattern 1: PEP 562 Module `__getattr__` for Exception Aliases (FREEZE-02)

**What:** Python 3.7+ supports a module-level `__getattr__(name)` function that is called when an attribute lookup on the module fails through the normal mechanism. This is the canonical approach for lazy imports and deprecated aliases at the module level.

**When to use:** When a class is renamed and the old name must warn on access but resolve to the same object. Works for both `from module import OldName` (calls `__getattr__` during import) and `module.OldName` (calls `__getattr__` on attribute access).

**Concrete shape for `pycopg/exceptions.py`:**

```python
# Source: PEP 562 (https://peps.python.org/pep-0562/) + Python docs [CITED]
import warnings

# --- Canonical new names (define these as the primary classes) ---
class ExtensionNotAvailableError(PycopgError):
    """Required extension is not installed."""
    pass

class TableNotFoundError(PycopgError):
    """Table does not exist."""
    pass

class InvalidIdentifierError(PycopgError):
    """Invalid SQL identifier (potential injection attempt)."""
    pass

class DatabaseExistsError(PycopgError):
    """Database already exists."""
    pass


# --- Deprecated aliases via PEP 562 ---
_DEPRECATED_EXCEPTION_ALIASES = {
    "ExtensionNotAvailable": "ExtensionNotAvailableError",
    "TableNotFound": "TableNotFoundError",
    "InvalidIdentifier": "InvalidIdentifierError",
    "DatabaseExists": "DatabaseExistsError",
}

def __getattr__(name: str) -> type:
    """Resolve deprecated exception names with a DeprecationWarning.

    Parameters
    ----------
    name : str
        Attribute name being accessed.

    Returns
    -------
    type
        The canonical *Error class.

    Raises
    ------
    AttributeError
        If the name is not a known deprecated alias.
    """
    if name in _DEPRECATED_EXCEPTION_ALIASES:
        new_name = _DEPRECATED_EXCEPTION_ALIASES[name]
        warnings.warn(
            f"{name} is deprecated and will be removed in pycopg 2.0. "
            f"Use {new_name} instead.",
            DeprecationWarning,
            stacklevel=2,  # points to the caller's file (the import site)
        )
        return globals()[new_name]
    raise AttributeError(f"module 'pycopg.exceptions' has no attribute {name!r}")
```

**Why `stacklevel=2` is correct here:** When `__getattr__` is called during `from pycopg.exceptions import OldName`, Python calls `exceptions.__getattr__("OldName")` from the import machinery. The call stack is:
1. Frame 0: `__getattr__` itself (inside `pycopg/exceptions.py`)
2. Frame 1: The import statement in the caller's file

`stacklevel=2` skips frame 0 and reports frame 1, pointing the warning at the user's `import` line. [ASSUMED — stacklevel=2 is the standard pattern; verify by running a test asserting the warning filename is the caller's file, per D-09]

**The same-class-object guarantee:** Because `__getattr__` returns `globals()[new_name]` — the actual class object — `except OldName:` is functionally identical to `except NewNameError:`. Python's exception matching uses `isinstance()` checks against the class object, so returning the same object makes the old name a perfect alias. [CITED: Python docs — exception matching semantics]

**Package `__init__.py` `__getattr__` for re-export:** `pycopg/__init__.py` currently does direct `from pycopg.exceptions import DatabaseExists, ...`. After the rename, the import statement must be updated to import the new `*Error` names. For the old names to warn when accessed via `import pycopg; pycopg.DatabaseExists`, the package also needs a `__getattr__`. However, `from pycopg import DatabaseExists` triggers `pycopg.exceptions.__getattr__` first (through the import chain), so the package `__getattr__` is only needed for `pycopg.DatabaseExists` direct attribute access. Add it for completeness:

```python
# pycopg/__init__.py addition
_DEPRECATED_PACKAGE_ALIASES = {
    "ExtensionNotAvailable": "ExtensionNotAvailableError",
    "TableNotFound": "TableNotFoundError",
    "InvalidIdentifier": "InvalidIdentifierError",
    "DatabaseExists": "DatabaseExistsError",
}

def __getattr__(name: str):
    if name in _DEPRECATED_PACKAGE_ALIASES:
        import warnings
        from pycopg import exceptions as _exc
        new_name = _DEPRECATED_PACKAGE_ALIASES[name]
        warnings.warn(
            f"{name} is deprecated and will be removed in pycopg 2.0. "
            f"Use {new_name} instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(_exc, new_name)
    raise AttributeError(f"module 'pycopg' has no attribute {name!r}")
```

[ASSUMED — package-level __getattr__ interaction with explicit imports needs test verification; the stacklevel=2 may need adjustment depending on the actual import path depth]

---

### Pattern 2: Per-Signature `filter=`/`where=` Shim in Accessor Methods (FREEZE-01)

**What:** Each accessor method (not the builder) accepts both `filter=None` and `where=None`. The accessor body emits the deprecation warning if `where` is supplied and then forwards `filter` to the builder. The builder signature is updated to `filter=` only.

**Why per-signature over a shared decorator:**
- A decorator approach would require wrapping every method, adding an indirection layer that complicates stacklevel counting (the warning would be 3+ frames deep instead of 2).
- Per-signature makes the frozen API explicit and readable — a reader of `SpatialAccessor.contains` sees `filter=None` in the signature directly.
- The kw-only enforcement (D-03) is naturally expressed per-signature with `*`.
- D-10 requires no internal code routes through the deprecated path: with a per-signature shim, the builder directly uses `filter=` and the shim only fires when `where=` is passed externally.

**Concrete shape for a spatial accessor method:**

```python
# Source: analysis of spatial.py + Python warnings docs [VERIFIED: codebase read]
def contains(
    self,
    table: str,
    geom: str = "geometry",
    *,                                    # keyword-only boundary (D-03)
    point: tuple[float, float] | None = None,
    wkt: str | None = None,
    geojson: dict | None = None,
    ref: tuple[str, str] | None = None,
    srid: int = 4326,
    into: str = "rows",
    columns: list[str] | None = None,
    filter: str | None = None,           # canonical new name
    where: str | None = None,            # deprecated shim
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict] | gpd.GeoDataFrame:
    if where is not None:
        warnings.warn(
            "The 'where' keyword argument is deprecated and will be removed in "
            "pycopg 2.0. Use 'filter=' instead.",
            DeprecationWarning,
            stacklevel=2,  # points to the caller's line, not pycopg/spatial.py
        )
        if filter is None:
            filter = where
    _check_into(into, "contains")
    sql, params = build_contains_sql(
        table,
        geom,
        schema=schema,                    # schema moved to keyword-only too
        point=point, wkt=wkt, geojson=geojson, ref=ref,
        srid=srid, columns=columns,
        filter=filter,                    # builder already uses filter=
        order_by=order_by, limit=limit,
    )
    return self._run(sql, params, into, geom)
```

**Note on `schema=` position:** Current signatures have `schema: str = "public"` as the 3rd positional arg. Under D-03, `schema` becomes keyword-only (it has a default). The kw-only boundary `*` goes after `geom`. This is a clean 1.0 break per D-04.

**The builder and `_append_tail`:** The 11 `build_*_sql` functions rename `where` to `filter` in their signatures and forward `filter` to `_append_tail`. `_append_tail` itself renames its `where` parameter to `filter`. Because `_append_tail` is an internal function (single underscore prefix), this is not a public API change — it is a pure internal rename with no deprecation wrapper needed.

**Correct `stacklevel` for accessor method:** The call stack when a user calls `db.spatial.contains(table, where="...")` is:
1. Frame 0: `warnings.warn` inside `contains` (in `pycopg/spatial.py`)
2. Frame 1: The user's call site

`stacklevel=2` points at frame 1 — the user's file. This is the correct value for a non-nested method. [ASSUMED — verify with a test asserting `warning.filename` ends with the test file name, not `spatial.py`, per D-09]

**D-10 guarantee:** Internally, all 11 `build_*_sql` functions and all internal callers only receive `filter=`. The `where=` parameter in each accessor method only exists to catch external legacy calls. Grep `pycopg/` (excluding tests) for `where=` before shipping to confirm zero internal leakage.

**AsyncSpatialAccessor (D-11):** The async accessor receives identical signature treatment. The `async def` wrapper is byte-for-byte identical to the sync version except for `await self._run(...)`. The builder is shared (no async/sync distinction for builders).

---

### Pattern 3: FREEZE-03 Consistency Audit Methodology

**Audit dimensions to tabulate across 7 accessors + flat core:**

| Dimension | Description | Example Inconsistency Found |
|-----------|-------------|----------------------------|
| `schema=` default | `"public"` vs `None` vs absent | `db.schema.describe()` may differ from `db.spatial.contains()` |
| `into=` routing | `"rows"/"gdf"/"df"` values; whether the accessor supports it at all | `db.timescale.*` uses `"df"` for DataFrame, `db.spatial.*` uses `"gdf"` — different values for conceptually analogous output |
| Required vs optional positional args | `table` always required? `geom` default `"geometry"`? | Verify uniformity across all spatial methods |
| Keyword-only boundary position | After which positional arg does `*` go? | Some methods may have 1 positional, others 3 |
| Return shape | `list[dict]` / `int` / `None` / `gpd.GeoDataFrame` — documented or not | Batch methods: `insert_batch` returns `int`; is this consistent with CRUD helpers? |
| `order_by=` / `limit=` presence | Not all accessors expose these | `db.spatial.*` has them; `db.schema.*` does not — intentional? |
| Error types | Which exceptions are raised for which violations | Uniformity across identically named error conditions |

**Inventory output format** (what the user reviews before any fixes land):

```
| Accessor        | Method          | Param          | Current          | Canonical         | Fix Type    |
|-----------------|-----------------|----------------|------------------|-------------------|-------------|
| SchemaAccessor  | describe        | schema=        | str = "public"   | str = "public"    | —           |
| SchemaAccessor  | tables          | schema=        | str | None = None| str = "public"    | CLEAN BREAK |
| SpatialAccessor | contains        | where=         | str | None       | filter= (FREEZE-01)| DEPRECATED |
| (flat core)     | insert          | schema=        | str = "public"   | str = "public"    | —           |
```

Fix types:
- `—` : No change needed
- `DEPRECATED` : Name rename, add DeprecationWarning alias (D-06)
- `CLEAN BREAK` : Structural/default/positional change, MIGRATION entry only (D-04/D-06)

**User review gate:** The audit task produces the table. A `checkpoint:human-review` task follows before any fix tasks run. This is non-optional per D-05.

---

### Pattern 4: Keyword-Only Enforcement with `*` (D-03/D-04)

**Rule:** Required arguments stay positional. Optional/defaulted arguments become keyword-only.

**For spatial methods:** `table` (required, str) stays positional. `geom` currently has a default (`"geometry"`) — under D-03 it becomes keyword-only. `schema` has a default (`"public"`) — keyword-only. All other params are already keyword-only (they follow `*` in the existing signatures).

Wait — checking the actual code: `contains(self, table: str, geom: str = "geometry", schema: str = "public", *, ...)` already has `geom` and `schema` as positional-with-default before the `*`. Under D-03, the `*` boundary moves earlier:

```python
# BEFORE (current):
def contains(self, table: str, geom: str = "geometry", schema: str = "public", *, ...)

# AFTER (D-03 + filter= rename):
def contains(self, table: str, *, geom: str = "geometry", schema: str = "public", filter: str | None = None, ...)
```

This means anyone currently calling `db.spatial.contains("my_table", "my_geom", "my_schema", ...)` positionally will get a `TypeError` in 1.0. This is the clean break per D-04. MIGRATION must document it.

**For non-spatial accessors:** The planner must apply D-03 consistently. For each accessor family, the boundary is: any required identifier args stay positional, all defaulted params become keyword-only.

**Phase 46 interaction (D-04):** The keyword-only freeze makes the mypy-strict Phase 46 work cleaner — `@overload` stubs only need to cover the keyword-only surface, not multiple positional arities.

---

### Pattern 5: `-W error::DeprecationWarning` CI Gate (D-10)

**Current state:** The gate does NOT currently exist in the codebase. `pyproject.toml` `[tool.pytest.ini_options]` has no `filterwarnings` entry. CI `tests.yml` has no `-W` pytest flag. [VERIFIED: codebase read — no filterwarnings anywhere]

**What this means for planning:** Adding the gate is a DELIVERABLE of Wave 1, not a pre-existing condition. The gate must be added before any deprecation wrappers are committed, so subsequent commits run under it.

**Implementation:**

```toml
# pyproject.toml [tool.pytest.ini_options]
filterwarnings = [
    "error::DeprecationWarning",          # turn DeprecationWarning into test failure
]
```

**Scope of impact:** Every test that currently triggers a `DeprecationWarning` (from pycopg internals or third-party libraries) will fail under this gate. Before adding it, a sweep of the current test suite is needed to confirm zero existing DeprecationWarnings from pycopg code. Third-party DeprecationWarnings (e.g., from psycopg, geopandas, pandas) must be selectively ignored:

```toml
filterwarnings = [
    "error::DeprecationWarning",
    "ignore::DeprecationWarning:psycopg",      # third-party
    "ignore::DeprecationWarning:geopandas",    # third-party
    "ignore::DeprecationWarning:pandas",       # third-party
]
```

[ASSUMED — the exact set of third-party DeprecationWarning sources is unknown until the suite runs under the gate; the planner must include a task to discover and suppress third-party warnings before locking the gate]

---

### Anti-Patterns to Avoid

- **`@deprecated_alias` decorator for exception renames:** This pattern was used in v0.6.0 for method renames on accessor objects. It is wrong for module-level exception class aliases. The v0.6.0 `@deprecated_alias` is already hard-removed (v0.7.0). Use PEP 562 `__getattr__` instead.
- **Metaclass `__instancecheck__` for catch-time warning:** D-08 explicitly forbids this. It is fragile, surprising, and incompatible with mypy-strict. Do not implement it.
- **`stacklevel=1` (the default):** Always emit with explicit `stacklevel=2` (or higher if the warning is nested in a helper). The default stacklevel=1 points at the pycopg source file, not the user's code — useless for a user trying to find which of their imports to fix.
- **Both `where=` and `filter=` accepted silently:** If a caller passes BOTH, the accessor must prefer `filter=` and ignore `where=` (or raise a clear `TypeError` about the conflict). Do not silently use `where=` when both are supplied.
- **Renaming only the accessor method but not the builder:** `build_contains_sql` must also rename its `where` param to `filter`. The builder is part of the public API (module-level function, exported) and must be clean.
- **Internal pycopg call sites using the old `where=` keyword:** After the rename, ALL internal calls to `build_*_sql` must pass `filter=`. Grep `pycopg/` for `where=` and `build_.*sql.*where=` before shipping.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Module-level name alias with warning | A class-based proxy or `__class_getitem__` hack | PEP 562 `__getattr__` on `pycopg/exceptions.py` | Pythonic, well-specified (PEP 562), supported since Python 3.7, works for both `import` and attribute access |
| Catching deprecated warning in tests | Custom warning filter context manager | `pytest.warns(DeprecationWarning, match=...)` | Built-in pytest API; handles stacklevel checking implicitly when combined with `recwarn` fixture |
| Stacklevel verification | Manual frame inspection | `warnings.catch_warnings()` + `assert warning.filename` in tests | stdlib `warnings.catch_warnings` is the standard mechanism; no third-party needed |
| SemVer policy document template | Invent a format | Reference Python packaging SemVer guidance + `keepachangelog.com` conventions | Established conventions users recognize |

**Key insight:** The entire phase's deprecation machinery is stdlib `warnings` + Python language features (PEP 562, `*` keyword-only separator). No external library is needed or appropriate.

---

## Common Pitfalls

### Pitfall 1: Wrong `stacklevel` in `warnings.warn`
**What goes wrong:** Warning points at `pycopg/spatial.py` line N instead of the user's file. `-W error::DeprecationWarning` turns CI red because internal code triggers the warning at the wrong level. Users can't find which of their imports to fix.

**Why it happens:** `stacklevel=1` (default) points to the frame where `warnings.warn` is called. For a method call, that's inside `pycopg/spatial.py`. The correct stacklevel for a non-nested method is `stacklevel=2`.

**How to avoid:** For each `warnings.warn` call: count the call stack depth from the warn call to the user's code. In a directly called accessor method: stacklevel=2. In a helper called from the accessor: stacklevel=3. Add a test asserting `w.filename` ends with the test file name (not `spatial.py` or `exceptions.py`). Per D-09.

**Warning signs:** `w.filename` in a `pytest.warns` capture ends with `.../pycopg/spatial.py` — that is wrong.

---

### Pitfall 2: Package `__init__.py` direct import overrides `__getattr__`
**What goes wrong:** `pycopg/__init__.py` currently does `from pycopg.exceptions import DatabaseExists`. After renaming `DatabaseExists` to `DatabaseExistsError`, if the `__init__.py` import is not updated, it will fail at import time with `ImportError`. The PEP 562 `__getattr__` on `exceptions.py` only fires for attribute access AFTER the module is imported — not for explicit `from X import Y` during package init.

**Why it happens:** `from pycopg.exceptions import DatabaseExists` in `__init__.py` runs at package import time. If `DatabaseExists` is not a real name in `exceptions.py` (only accessible via `__getattr__`), this raises `ImportError` immediately — before any user code runs.

**How to avoid:** Update `pycopg/__init__.py` import block to use the NEW `*Error` names. Add the old names to `__all__` via a separate section (or handle via package `__getattr__`). Do NOT keep `from pycopg.exceptions import DatabaseExists` in `__init__.py` after the rename — the new name is `DatabaseExistsError`.

**Warning signs:** `import pycopg` raises `ImportError: cannot import name 'DatabaseExists' from 'pycopg.exceptions'`.

---

### Pitfall 3: `test_accessor_parity` fails because accessor gains `filter=` but async does not (or vice versa)
**What goes wrong:** `SpatialAccessor.contains` gets `filter=` added; `AsyncSpatialAccessor.contains` keeps only `where=`. `test_accessor_parity` checks method existence (names), not signatures — so parity by name passes, but signatures diverge invisibly.

**How to avoid:** Apply the signature change to both accessor classes in the same commit. After the commit, verify by running `inspect.signature(SpatialAccessor.contains).parameters` == `inspect.signature(AsyncSpatialAccessor.contains).parameters`. The test suite does not currently check signature parity for existing methods (only for new Spatial v2 methods added in Phase 42+). This is a manual check at commit time for Phase 41.

---

### Pitfall 4: `-W error::DeprecationWarning` gate immediately breaks the suite from third-party warnings
**What goes wrong:** Adding `filterwarnings = ["error::DeprecationWarning"]` to `pyproject.toml` causes 50+ test failures from pandas/geopandas/psycopg deprecation warnings unrelated to pycopg.

**How to avoid:** Before committing the gate, run `uv run pytest -W error::DeprecationWarning 2>&1 | grep -A2 "DeprecationWarning"` and collect all non-pycopg warning sources. Add `ignore::DeprecationWarning:MODULE` suppressions for each third-party source. Only then commit the gate with the suppressions in place.

---

### Pitfall 5: `where=` in builder signature causes `build_contains_sql(table, ..., where="x")` to silently pass
**What goes wrong:** After the rename, someone calls `build_contains_sql("tbl", where="status='active'")` (old kwarg) and it silently fails because `where` is no longer a recognized parameter — Python will raise `TypeError: unexpected keyword argument 'where'`. This is correct behavior (the builder's old interface is gone), but it means internal callers using the old kwarg name will break immediately.

**How to avoid:** Update ALL internal callers of `build_*_sql` to use `filter=` before removing `where=` from the builder. Do this in one atomic commit to avoid a window where builders accept neither kwarg.

---

### Pitfall 6: `__all__` in `exceptions.py` not updated
**What goes wrong:** `exceptions.py` may have an `__all__` list. After the rename, `__all__` still contains only `ExtensionNotAvailable` etc. New `*Error` names must be added; old names should be kept in `__all__` with a comment marking them deprecated (for `from pycopg.exceptions import *` consumers).

**Actual check:** The current `exceptions.py` (inspected) does NOT have an explicit `__all__`. [VERIFIED: codebase read] The `pycopg/__init__.py` does have `__all__` and lists the old exception names. Both files need updating.

---

## Code Examples

### FREEZE-02: Minimal PEP 562 `__getattr__` in exceptions.py
```python
# Source: PEP 562 specification + Python 3.11 docs [CITED: peps.python.org/pep-0562/]
import warnings as _warnings

_DEPRECATED_NAMES: dict[str, str] = {
    "ExtensionNotAvailable": "ExtensionNotAvailableError",
    "TableNotFound": "TableNotFoundError",
    "InvalidIdentifier": "InvalidIdentifierError",
    "DatabaseExists": "DatabaseExistsError",
}

def __getattr__(name: str) -> type:
    if name in _DEPRECATED_NAMES:
        new = _DEPRECATED_NAMES[name]
        _warnings.warn(
            f"pycopg.exceptions.{name} is deprecated and will be removed in "
            f"pycopg 2.0. Use {new} instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return globals()[new]
    raise AttributeError(f"module 'pycopg.exceptions' has no attribute {name!r}")
```

### FREEZE-02: Internal raise site update pattern (utils.py example)
```python
# BEFORE:
from pycopg.exceptions import InvalidIdentifier
raise InvalidIdentifier("Identifier cannot be empty")

# AFTER:
from pycopg.exceptions import InvalidIdentifierError
raise InvalidIdentifierError("Identifier cannot be empty")
```

### FREEZE-01: `_append_tail` parameter rename
```python
# BEFORE:
def _append_tail(sql: str, where: str | None, order_by: str | None, limit: int | None, has_where: bool) -> str:
    if where:
        sql += f" AND ({where})" if has_where else f" WHERE {where}"
    ...

# AFTER (internal rename only — no deprecation wrapper needed, it's private):
def _append_tail(sql: str, filter: str | None, order_by: str | None, limit: int | None, has_where: bool) -> str:
    if filter:
        sql += f" AND ({filter})" if has_where else f" WHERE {filter}"
    ...
```

### FREEZE-01: `build_contains_sql` builder signature rename
```python
# BEFORE:
def build_contains_sql(table, geom="geometry", schema="public", *, ..., where: str | None = None, ...) -> tuple[str, list]:

# AFTER (clean frozen signature, no deprecated alias in builders):
def build_contains_sql(table, geom="geometry", schema="public", *, ..., filter: str | None = None, ...) -> tuple[str, list]:
    # internal call to _append_tail uses filter=:
    sql = _append_tail(sql, filter, order_by, limit, has_where=True)
```

### FREEZE-03: pytest `filterwarnings` gate addition
```toml
# pyproject.toml — [tool.pytest.ini_options] addition
filterwarnings = [
    "error::DeprecationWarning",
    # Third-party suppressions (expand after discovery run):
    "ignore::DeprecationWarning:psycopg",
    "ignore::DeprecationWarning:geopandas",
    "ignore::DeprecationWarning:pandas",
]
```

### FREEZE-01: Test for correct stacklevel (D-09)
```python
# tests/test_deprecations.py
import warnings
import pytest
from pycopg.spatial import SpatialAccessor
from unittest.mock import MagicMock

def test_where_deprecation_points_to_caller():
    """DeprecationWarning from where= must point to THIS file, not spatial.py."""
    db = MagicMock()
    db.schema.has_extension.return_value = True
    db.execute.return_value = []
    accessor = SpatialAccessor(db)
    with pytest.warns(DeprecationWarning) as record:
        accessor.contains("tbl", point=(0, 0), where="id > 0")
    assert len(record) == 1
    w = record[0]
    assert "filter" in str(w.message)
    # stacklevel=2 must point at this test file, not pycopg/spatial.py:
    assert w.filename.endswith("test_deprecations.py"), (
        f"Warning pointed at {w.filename!r}, expected test file"
    )
```

### FREEZE-02: Test for exception alias same-object identity
```python
# tests/test_deprecations.py
import warnings
from pycopg import exceptions

def test_exception_alias_same_object():
    """Old name resolves to the identical class object."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        OldName = exceptions.InvalidIdentifier
    assert OldName is exceptions.InvalidIdentifierError

def test_exception_alias_warns_on_access():
    """Accessing old exception name emits DeprecationWarning pointing to this file."""
    with pytest.warns(DeprecationWarning) as record:
        _ = exceptions.InvalidIdentifier
    w = record[0]
    assert "InvalidIdentifierError" in str(w.message)
    assert w.filename.endswith("test_deprecations.py")

def test_old_exception_name_still_catchable():
    """except OldName: catches the error raised with NewNameError."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        OldName = exceptions.InvalidIdentifier
    with pytest.raises(OldName):
        raise exceptions.InvalidIdentifierError("test")
```

### `docs/stability.md` outline
```markdown
# API Stability

## SemVer Contract

pycopg follows Semantic Versioning 2.0.0. At 1.0.0 the public API is frozen.

### Breaking vs Non-Breaking

| Change | Classification |
|--------|---------------|
| Removing a public method or parameter | BREAKING (major version) |
| Renaming a parameter (without alias) | BREAKING (major version) |
| Adding an optional parameter with a default | Non-breaking (minor version) |
| Changing a parameter default value | BREAKING (major version) |
| Changing a return type | BREAKING (major version) |
| Changing an exception type | BREAKING (major version) |
| Bug fix that changes behavior | Patch (with note in CHANGELOG) |

## Deprecation Policy

Deprecated names are kept for the entirety of 1.x. They are removed only in 2.0.

A deprecated name emits `DeprecationWarning` on every use. Users must:
1. Read the warning message (it names the replacement)
2. Update their code before upgrading to pycopg 2.0

## Stable API Contract

[Table: every public method with positional vs keyword-only parameter classification]

## Supported Versions

| Component | Floor | Recommended |
|-----------|-------|-------------|
| Python | 3.11 | 3.12+ |
| PostgreSQL | 13 | 16+ |
| PostGIS | 3.0 | 3.2+ |
| TimescaleDB | 2.0 | 2.10+ |
| psycopg | 3.1.0 | latest |
| psycopg_pool | 3.2.0 | latest |

## API Stability Tiers

| API | Tier |
|-----|------|
| `Database.*` flat core | Stable |
| `AsyncDatabase.*` flat core | Stable |
| `db.spatial.*` | Stable |
| `db.schema.*` | Stable |
| `db.timescale.*` | Stable |
| `db.etl.*` | Stable |
| `db.admin.*` | Stable |
| `db.maint.*` | Stable |
| `db.backup.*` | Stable |
| Module-level `build_*_sql` builders | Stable |
| `pycopg.exceptions.*Error` | Stable |
| Internal `_*` names | Private — no stability guarantee |
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `warnings.warn` with no explicit stacklevel | Always specify `stacklevel=N` explicitly | Python 3.7 best practices | Without explicit stacklevel, warning points at the wrapper, not the caller |
| Module attribute aliasing via `sys.modules` replacement | PEP 562 `__getattr__` | Python 3.7 (PEP 562 merged) | `__getattr__` is the standard, well-supported way; `sys.modules` hack is fragile |
| `@deprecated_alias` decorator (pycopg v0.6.0) | PEP 562 for module-level aliases | v0.7.0 removed decorators | The v0.6.0 decorator worked for accessor method aliases; PEP 562 is correct for module-level (exception class) aliases |

**Deprecated/outdated:**
- `@deprecated_alias` decorator: hard-removed in v0.7.0; do not recreate; not applicable to exception renames
- Any approach that involves keeping the old class name as a literal class definition (subclassing trick): creates two distinct class objects, breaking `except OldName:` catch semantics

---

## FREEZE-03 Consistency Audit: Detailed Inventory Guidance

The planner must create a dedicated task that reads every public method across all 7 accessors + flat core and produces the findings table below. This is the "audit" in "audit-then-decide" (D-05).

**The 7 accessors:**
1. `SpatialAccessor` / `AsyncSpatialAccessor` (`pycopg/spatial.py`)
2. `SchemaAccessor` / `AsyncSchemaAccessor` (`pycopg/schema.py`)
3. `TimescaleAccessor` / `AsyncTimescaleAccessor` (`pycopg/timescale.py`)
4. `ETLAccessor` / `AsyncETLAccessor` (`pycopg/etl.py`)
5. `AdminAccessor` / `AsyncAdminAccessor` (`pycopg/admin.py`)
6. `MaintAccessor` / `AsyncMaintAccessor` (`pycopg/maint.py`)
7. `BackupAccessor` / `AsyncBackupAccessor` (`pycopg/backup.py`)

**Flat core:**
- `Database` (sync, `pycopg/database.py`) — public methods not on accessors
- `AsyncDatabase` (async, `pycopg/async_database.py`)

**Anticipated findings based on codebase read:**
- `schema=` parameter: Some methods use `str = "public"`, others use `str | None = None` — this inconsistency should be captured and dispositioned.
- `into=` parameter: `db.spatial.*` uses `"rows"/"gdf"`; `db.timescale.*` query helpers may use `"df"` for DataFrame (pandas, not geopandas). These are actually different return types and the different values may be intentional — the audit must flag for user decision.
- Positional args: Current spatial signatures expose `geom` and `schema` as positional-with-default before `*`. Under D-03, these become keyword-only.

**Kw-only enforcement scope:** D-03 says "apply across 7 accessors + flat core." The flat core (`Database` / `AsyncDatabase`) has methods like `execute(self, sql, params=None)` — `params` has a default and should become keyword-only. The planner must scope this carefully: enforcing kw-only on `execute()` changes how `db.execute(query, [1,2,3])` is called — a common pattern. The audit must flag such cases for explicit user sign-off.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `stacklevel=2` is correct for accessor methods and module `__getattr__` calls (one frame: the warning call site; pointing at the user's call/import) | §Pattern 1, §Pattern 2 | Warning points at wrong line; tests checking `w.filename` would catch this |
| A2 | Package-level `__getattr__` needed for `pycopg.OldName` attribute access (not just `from pycopg import OldName`) | §Pattern 1 | Old names accessible only via direct import, not via attribute access on package; lower impact than A1 |
| A3 | The exact set of third-party DeprecationWarning sources requires a discovery run before the `-W error` gate can be finalized | §Pattern 5, §Pitfall 4 | Gate breaks on unrelated warnings; must be discovered and suppressed at Wave 1 time |
| A4 | `db.spatial.*` `within()` method has `left_table`, `right_table`, `left_geom`, `right_geom` as positional args (distinct from the standard `table`/`geom` form seen in other methods) — kw-only enforcement for `within` may need a different boundary | §Pattern 4 | `within()` kw-only enforcement may be more complex than the other 10 methods |
| A5 | `pycopg/exceptions.py` currently has no explicit `__all__` | §Pitfall 6 | If an `__all__` exists and is not updated, star imports may silently omit new `*Error` names |
| A6 | Internal `timescale.py` has ~14 `raise ExtensionNotAvailable(...)` sites — this is the largest single-file raise-site count | §Don't Hand-Roll | If count is higher, the N818 rename task is larger than estimated |
| A7 | `stacklevel=2` in `exceptions.py.__getattr__` points at the `from pycopg.exceptions import OldName` line, not at an intermediate import frame | §Pattern 1 | If Python's import machinery introduces extra frames, stacklevel needs to be higher |

**If this table is empty:** All claims in this research were verified or cited — no user confirmation needed. (Table is not empty — see above.)

---

## Open Questions

1. **`within()` keyword-only boundary**
   - What we know: `within(self, left_table, left_geom, right_table, right_geom, schema="public", *, ...)` has 4 required positional args before `schema`.
   - What's unclear: Does D-03 move `schema=` to keyword-only here too? That would give 4 positional args (`left_table`, `left_geom`, `right_table`, `right_geom`) then `*`. This is different from the 1-arg pattern of the other 10 spatial methods.
   - Recommendation: Yes, apply D-03 consistently — `schema=` becomes keyword-only on `within` too. Flag in the FREEZE-03 findings table for user acknowledgment.

2. **Both `filter=` and `where=` supplied simultaneously**
   - What we know: D says "use filter if filter is not None".
   - What's unclear: Should passing BOTH raise `TypeError` or silently prefer `filter`?
   - Recommendation: Raise `TypeError("Cannot specify both 'filter' and 'where'; use 'filter' only.")` — this makes the transition explicit and avoids silent behavior.

3. **`-W error::DeprecationWarning` scope: whether to add to CI step or only pyproject.toml**
   - What we know: `pyproject.toml` `filterwarnings` applies to all `uv run pytest` invocations.
   - What's unclear: Does the CI step `uv run pytest` pick up the `pyproject.toml` filterwarnings?
   - Recommendation: Yes, pytest reads `pyproject.toml` `[tool.pytest.ini_options]` automatically. Adding it to pyproject.toml is sufficient; no CI step change needed.

4. **`docs/stability.md` Sphinx toctree**
   - What we know: `docs/conf.py` uses `master_doc = 'index'`; existing docs use MyST Markdown files under `docs/source/`.
   - What's unclear: The Sphinx `-W` gate will fail if `stability.md` is created but not added to the toctree.
   - Recommendation: Add `stability` to the toctree in `docs/source/index.md` as part of the same commit that creates the file.

---

## Environment Availability

> Step 2.6: All changes are code/config edits within the existing Python environment. No new external tools, services, or CLI utilities are needed beyond what's already installed.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `uv` | All test/lint commands | ✓ | confirmed in CI | — |
| `pytest` | Test suite | ✓ | ≥7.0.0 (pyproject.toml) | — |
| `ruff` | Linting N818 check | ✓ | ≥0.1.0 (pyproject.toml) | — |
| `sphinx-build` | Sphinx `-W` docs gate | ✓ | installed via docs/requirements.txt in CI | — |
| Python 3.11+ | PEP 562 `__getattr__` | ✓ | 3.11/3.12/3.13 matrix | — |

**Missing dependencies with no fallback:** None.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest ≥7.0.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_deprecations.py tests/test_exceptions.py -x -q` |
| Full suite command | `uv run pytest` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FREEZE-01 | `where=` on spatial accessor emits DeprecationWarning | unit | `uv run pytest tests/test_deprecations.py::test_where_deprecation_warns -x` | ❌ Wave 0 — create `tests/test_deprecations.py` |
| FREEZE-01 | DeprecationWarning points to caller's file (stacklevel) | unit | `uv run pytest tests/test_deprecations.py::test_where_deprecation_points_to_caller -x` | ❌ Wave 0 |
| FREEZE-01 | `filter=` produces identical result to former `where=` | unit | `uv run pytest tests/test_deprecations.py::test_filter_equivalent_to_where -x` | ❌ Wave 0 |
| FREEZE-01 | Internal pycopg/ code does NOT trigger DeprecationWarning (D-10) | integration | `uv run pytest -W error::DeprecationWarning` (entire suite) | ❌ Gate must be added to pyproject.toml Wave 0 |
| FREEZE-01 | `test_accessor_parity` passes with new `filter=` on both accessors | parity | `uv run pytest tests/test_parity.py -x` | ✅ existing |
| FREEZE-01 | Builder `build_*_sql` no longer accepts `where=` kwarg (TypeError) | unit | `uv run pytest tests/test_spatial.py::*where*` (update existing tests) | ✅ existing — must be updated |
| FREEZE-02 | `from pycopg.exceptions import InvalidIdentifier` emits DeprecationWarning | unit | `uv run pytest tests/test_deprecations.py::test_exception_alias_warns_on_access -x` | ❌ Wave 0 |
| FREEZE-02 | Old exception name `is` new `*Error` class (same object) | unit | `uv run pytest tests/test_deprecations.py::test_exception_alias_same_object -x` | ❌ Wave 0 |
| FREEZE-02 | `except OldName:` catches exception raised with `NewNameError` | unit | `uv run pytest tests/test_deprecations.py::test_old_exception_name_still_catchable -x` | ❌ Wave 0 |
| FREEZE-02 | N818 ruff check passes (no suppression in pyproject.toml) | lint | `uv run ruff check pycopg/exceptions.py` | ✅ (after suppression removed) |
| FREEZE-02 | Internal raise sites use `*Error` names (grep check) | static | `grep -r "raise ExtensionNotAvailable\|raise TableNotFound\|raise InvalidIdentifier[^E]\|raise DatabaseExists[^E]" pycopg/ | wc -l` → must be 0 | manual — add as CI step or pre-ship check |
| FREEZE-03 | Kw-only enforcement: calling optional params positionally raises TypeError | unit | `uv run pytest tests/test_deprecations.py::test_kw_only_enforcement_*` | ❌ Wave 0 |
| FREEZE-03 | FREEZE-03 findings table exists and has been reviewed | process | `checkpoint:human-review` task | N/A — process gate |
| FREEZE-04 | `docs/stability.md` exists and is valid Sphinx/MyST | docs | `uv run sphinx-build -W --keep-going -b html docs docs/_build/html` | ❌ Wave 0 — file does not exist |
| FREEZE-04 | `docs/stability.md` linked from README | docs | `grep "stability" README.md` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_deprecations.py tests/test_exceptions.py -x -q`
- **Per wave merge:** `uv run pytest` (full suite under `-W error::DeprecationWarning` gate)
- **Phase gate:** Full suite green + `uv run ruff check pycopg/` + Sphinx `-W` build + grep for old names returning 0 hits before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_deprecations.py` — covers FREEZE-01 (filter=/where= shim tests) + FREEZE-02 (exception alias tests) + FREEZE-03 (kw-only TypeError tests)
- [ ] `pyproject.toml` `filterwarnings` gate — add `error::DeprecationWarning` with third-party suppressions
- [ ] `docs/source/stability.md` — new file (created in FREEZE-04 task, not Wave 0; Wave 0 gap is that the file doesn't exist and would fail toctree validation if toctree references it before creation)
- [ ] Update `tests/test_spatial.py` — existing tests that pass `where=` to builders must be updated to pass `filter=` after the builder rename

*(Wave 0 = first implementation task's setup before functional code lands)*

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes (partial) | `validate_identifiers` — must not be dropped during signature refactoring (the v0.10.0 COPY lesson) |
| V6 Cryptography | no | — |

### Known Threat Patterns for This Phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Removing `validate_identifiers` during signature refactoring | Tampering | Treat every builder signature change as a trigger to re-verify `validate_identifiers` is still the first call |
| Internal call sites accidentally calling deprecated `where=` path | Elevation | `-W error::DeprecationWarning` CI gate; grep pre-ship check |

**Security note:** This phase does not add new SQL builders. The existing `validate_identifiers` guards in `build_*_sql` functions are preserved — parameter renames (`where`→`filter`) do not touch the validation logic. The N818 exception renames do not affect validation logic. The kw-only enforcement (`*`) does not affect validation — it is purely a call convention change.

---

## Sources

### Primary (HIGH confidence)

- `pycopg/spatial.py` — direct read: 11 builder signatures with `where: str | None = None`, `_append_tail` signature, `SpatialAccessor.contains` (~line 1079), `AsyncSpatialAccessor.contains` (~line 1970); confirmed 33 rename sites + 1 `_append_tail` [VERIFIED: codebase read]
- `pycopg/exceptions.py` — direct read: 4 classes confirmed (`ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier`, `DatabaseExists`); no `__all__`; no existing `__getattr__` [VERIFIED: codebase read]
- `pyproject.toml` — direct read: N818 suppression at lines 93-96 confirmed; no `filterwarnings` in `[tool.pytest.ini_options]`; `-W error::DeprecationWarning` gate does NOT currently exist [VERIFIED: codebase read]
- `pycopg/__init__.py` — direct read: 4 exception names in `__all__` confirmed; direct import pattern confirmed [VERIFIED: codebase read]
- `.github/workflows/tests.yml` — direct read: no `filterwarnings` or `-W error` gate in CI [VERIFIED: codebase read]
- `tests/test_parity.py` — direct read: `test_accessor_parity` checks method NAME sets only, not signatures [VERIFIED: codebase read]
- `.planning/phases/41-api-homogenization/41-CONTEXT.md` — D-01 through D-11 locked decisions [VERIFIED: direct read]
- `.planning/REQUIREMENTS.md` — FREEZE-01..04 requirements confirmed; line 57 "every break served via a deprecation cycle + MIGRATION" rule [VERIFIED: direct read]
- `.planning/research/PITFALLS.md` — Pitfall 6 (stacklevel), Pitfall 7 (where= inconsistency), Pitfall 8 (N818 checklist) [VERIFIED: direct read]
- `.planning/research/SUMMARY.md` — Phase 41 section; build order rationale [VERIFIED: direct read]

### Secondary (MEDIUM confidence)

- PEP 562 (`__getattr__` for module attributes) — Python 3.7+; the `stacklevel=2` behavior for `from module import name` invocations is inferred from PEP semantics + training knowledge. [CITED: peps.python.org/pep-0562/] [ASSUMED — exact stacklevel for import-time __getattr__ should be verified with a test]
- Raise site counts: `ExtensionNotAvailable` (~15 sites in timescale.py + spatial.py + async_database.py), `TableNotFound` (~2 sites in schema.py), `InvalidIdentifier` (~15 sites in utils.py), `DatabaseExists` (~2 sites in database.py + async_database.py) — counted from grep output [VERIFIED: codebase grep]
- Test exception references: `InvalidIdentifier` in ~162 test file lines, `ExtensionNotAvailable`+`TableNotFound`+`DatabaseExists` in ~57 test file lines — scope for test update task [VERIFIED: codebase grep]

### Tertiary (LOW confidence — see Assumptions Log)

- Third-party DeprecationWarning sources that must be suppressed when adding the gate — unknown until discovery run [ASSUMED — A3]
- Exact stacklevel for package `__getattr__` re-export path [ASSUMED — A2, A7]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — pure stdlib; no external packages; all mechanics verified against Python docs and codebase
- Architecture: HIGH — all files read directly; raise-site counts from grep; existing patterns inspected
- Pitfalls: HIGH — grounded in pycopg's own history (v0.10.0 COPY rewrite precedent) + Python docs stacklevel semantics
- Validation architecture: HIGH — test commands verified against existing test structure

**Research date:** 2026-06-28
**Valid until:** 2026-09-01 (stable Python/stdlib mechanics; no external version dependencies in this phase)
