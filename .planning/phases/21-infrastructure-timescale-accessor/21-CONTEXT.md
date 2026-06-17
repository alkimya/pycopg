# Phase 21: Infrastructure & Timescale Accessor - Context

**Gathered:** 2026-06-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver the **reusable `@deprecated_alias` infrastructure** plus the **first accessor (`db.timescale.*` / `async_db.timescale.*`, 6 methods)** as the end-to-end pattern proof for the whole v0.6.0 réorganisation. After this phase, the alias + accessor pattern is established and every later phase (22–24) replicates it mechanically.

What "done" means (from ROADMAP success criteria):
1. `db.timescale.create_hypertable(...)` and all 6 timescale methods return the same results as before.
2. The old flat `db.create_hypertable(...)` still works **and** emits a `DeprecationWarning` naming `db.timescale.create_hypertable`.
3. `test_parity` passes with the timescale accessor registered (sync + async).
4. A dedicated test asserts each alias warns (correct message) **and** delegates; suite runs without DeprecationWarning noise breaking any `-W error` gate; coverage stays ≥ 94%.

**The 6 timescale methods** (move verbatim from `pycopg/database.py` / `pycopg/async_database.py`): `create_hypertable`, `enable_compression`, `add_compression_policy`, `add_retention_policy`, `list_hypertables`, `hypertable_info`.

**This milestone MOVES the existing surface; it adds no new power.** No new TimescaleDB helpers (continuous aggregates, gapfill, chunks) — those are explicitly deferred to v0.8.0.

</domain>

<decisions>
## Implementation Decisions

### Decorator shape (REORG-01)
- **D-01:** `@deprecated_alias` takes a **target path string** of the form `"timescale.create_hypertable"`. At call time the decorator resolves the lazy accessor on `self` (`self.timescale`), then calls the named method on it with the same args/kwargs. No hardcoded function references → robust to refactors, and v0.7.0 removal = delete the decorated stub.
- **D-02:** The deprecated flat stub uses a **generic `(*args, **kwargs)` passthrough** — a one-liner per alias. Minimal code, trivial to delete in v0.7.0. The decorator does the warn + delegate.
- **D-03:** Sync and async variants of the decorator both exist (the async variant `await`s the delegated accessor coroutine). Parity is mandatory (D-SCOPE-4).
- **D-04:** The `DeprecationWarning` message must name the **new path** (e.g. "use `db.timescale.create_hypertable` instead; the flat `db.create_hypertable` alias is deprecated and will be removed in v0.7.0"). `stacklevel` must point at the **caller's** line, not inside the decorator (verify the resolved stacklevel through the wrapper layers — this is a known footgun).

### Where the implementation lives (D-SCOPE-2)
- **D-05:** The real implementation **moves into the accessor** (`TimescaleAccessor` / `AsyncTimescaleAccessor`). The flat `db.*` name becomes the thin deprecated alias.
- **D-06:** **Move bodies verbatim**, rewriting `self.has_extension(...)` → `self._db.has_extension(...)` and `self.execute(...)` → `self._db.execute(...)`. **Keep the inline f-string SQL** (with existing `validate_identifiers` / `validate_interval` guards) — do **not** extract pure SQL builders for timescale. Rationale: lowest risk, smallest diff, behaviour provably identical; timescale SQL interpolates `INTERVAL` literals and `if_not_exists`/`migrate_data` flags that don't fit the `(sql, params)` `%s`-only builder shape used by spatial/etl as cleanly. (Departure from the spatial/etl pure-builder convention is intentional and scoped to timescale.)
- **D-07:** New accessor classes live in a **dedicated module `pycopg/timescale.py`** holding both `TimescaleAccessor` and `AsyncTimescaleAccessor`, mirroring `pycopg/spatial.py` and `pycopg/etl.py` exactly. Later phases add `admin.py`, `schema.py`, `maint.py`, `backup.py`. Accessor is a **lazy cached property** on `Database`/`AsyncDatabase` (instantiate + cache `TimescaleAccessor(self)` on first access of `db.timescale`), copying the existing `_spatial`/`_etl` pattern (see `database.py:231-271`, `async_database.py:97-131`).

### Test strategy for DeprecationWarning noise (REORG-04)
- **D-08:** **Migrate** existing timescale test call-sites to the new `db.timescale.*` / `async_db.timescale.*` paths (so the main suite stays quiet).
- **D-09:** **Add a dedicated alias test class** that, for each of the 6 flat aliases, asserts via `pytest.warns(DeprecationWarning, match=...)` that it **both warns (correct message) and delegates correctly** (same result as the accessor call). This keeps the thin alias stubs covered so the `--cov-fail-under=94` ratchet holds.

### Parity registration (REORG-03)
- **D-10:** Build a **data-driven parity registry** in `tests/test_parity.py`: a list of `(SyncAccessor, AsyncAccessor)` class pairs feeding a single parametrized test (`inspect.getmembers` diff in both directions, as `TestEtlParity` does today). Phase 21 seeds it with the `(TimescaleAccessor, AsyncTimescaleAccessor)` pair; Phases 22–23 just **append** their pairs. This realises the D-SCOPE-3 "replicate mechanically" intent with no per-accessor copy-paste.
  - *Optional cleanup (not required this phase):* the existing one-off `TestEtlParity` (`tests/test_parity.py:466`) could fold into the registry. Leave it if folding adds risk — don't expand scope.

### Claude's Discretion
- Exact decorator signature/internals beyond D-01..D-04 (e.g. whether to use `functools.wraps` to carry metadata onto the generic stub — see open item below).
- Exact placement/naming of the registry list and the alias test class within `tests/test_parity.py` / a new test module.
- Whether `from __future__ import annotations` + `TYPE_CHECKING` import guards are needed in `timescale.py` (follow `spatial.py`/`etl.py`).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope & locked decisions
- `.planning/v0.6.0-SCOPE.md` — D-SCOPE-1..4 (LOCKED — do not re-litigate); method→accessor mapping; the 6 timescale methods; what stays flat on `db.*`; vigilance points (coverage ratchet, test_parity, filterwarnings, naming consistency).
- `.planning/PROJECT.md` § "Current Milestone: v0.6.0" — locked decisions + the 3 resolved open questions (schema = one block; DataFrame stays flat; spatial-index → `db.spatial.*`).
- `.planning/ROADMAP.md` § "Phase 21" — goal, the 4 success criteria, requirement IDs.
- `.planning/REQUIREMENTS.md` — REORG-01..05, TS-01 acceptance text (REORG-01/02/03/04 + TS-01 land in Phase 21).

### Existing accessor pattern to mirror (the proven precedent — read these as the template)
- `pycopg/spatial.py:1023` (`SpatialAccessor`) and `:1859` (`AsyncSpatialAccessor`) — `__init__(self, db)` storing `self._db`, methods calling `self._db.execute(...)`, PostGIS guard pattern.
- `pycopg/etl.py` (`ETLAccessor` / `AsyncETLAccessor`) — second instance of the same lazy-accessor shape.
- `pycopg/database.py:231-271` — lazy cached `spatial`/`etl` properties + `self._spatial`/`self._etl` init at `:85-86`. Replicate for `timescale`.
- `pycopg/async_database.py:97-131` — async lazy `spatial`/`etl` properties + init at `:84-85`.
- `pycopg/__init__.py:10,26,40-55` — `__all__` exports for `SpatialAccessor`/`AsyncSpatialAccessor`/`ETLAccessor`/`AsyncETLAccessor`. (Note: REORG-05 / public exports are formally **Phase 24**; expose the new classes here as the precedent dictates, but the README/Sphinx/CHANGELOG export work is Phase 24's.)

### Source of the methods being moved
- `pycopg/database.py:1648-1869` — the 6 sync timescale method bodies (`create_hypertable` at 1648, `enable_compression` 1699, `add_compression_policy` 1753, `add_retention_policy` 1790, `list_hypertables` 1827, `hypertable_info` 1848).
- `pycopg/async_database.py` — the async equivalents (parity already verified by sample in SCOPE doc).
- `pycopg/utils.py` — `validate_identifiers`, `validate_interval` (guards used by the timescale methods; keep them in the moved bodies).
- `pycopg/exceptions.py` — `ExtensionNotAvailable` (raised when timescaledb extension absent).

### Tests
- `tests/test_parity.py:466-512` (`TestEtlParity`) — the `inspect.getmembers` parity pattern to generalise into the registry.
- Existing timescale tests (grep `create_hypertable` / `hypertable` under `tests/`) — call-sites to migrate to `db.timescale.*`.
- `pyproject.toml [tool.pytest.ini_options]` — `addopts = "... --cov-fail-under=94"`, `asyncio_mode = "auto"`. No `filterwarnings` configured today; if any is added it must be **targeted** (pycopg's own DeprecationWarning), per the SCOPE vigilance note.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Lazy accessor pattern** (`database.py:231-271`, `async_database.py:97-131`): copy verbatim for `timescale`. Add `self._timescale: TimescaleAccessor | None = None` in `__init__`, a `@property def timescale` that lazily constructs + caches, and the `TYPE_CHECKING` import.
- **`SpatialAccessor.__init__(self, db)` storing `self._db`** — exact shape for `TimescaleAccessor.__init__`.
- **`validate_identifiers` / `validate_interval`** (`pycopg/utils.py`) — already used by the timescale bodies; they travel with the moved code unchanged.
- **`ExtensionNotAvailable`** (`pycopg/exceptions.py`) — keep the `if not self._db.has_extension("timescaledb"): raise ExtensionNotAvailable(...)` guard at the top of each moved method.
- **`inspect.getmembers` parity check** (`TestEtlParity`) — the engine for the new data-driven registry.

### Established Patterns
- **One module per accessor domain** — `spatial.py`, `etl.py` → add `timescale.py`. Both sync + async accessor in the same module.
- **numpydoc docstrings, shallow (Summary/Parameters/Returns/Raises), no Examples**, `interrogate ≥ 95` enforced in CI. New accessor methods carry the moved docstrings; the generic flat-alias stubs need a docstring strategy (see open item).
- **Coverage ratchet `--cov-fail-under=94`** — every line added (incl. each thin alias) must be exercised; the dedicated alias test class (D-09) supplies that coverage.

### Integration Points
- `Database` / `AsyncDatabase` `__init__` (accessor cache field) + new `@property` (lazy construction).
- The 6 flat method definitions in `database.py` / `async_database.py` get **replaced** by `@deprecated_alias("timescale.<method>")`-decorated thin stubs that delegate to `db.timescale.*`.
- `tests/test_parity.py` registry seeded with the timescale pair.
- `pycopg/__init__.py` `__all__` — surface the new accessor classes (formal export/docs hardening is Phase 24).

</code_context>

<specifics>
## Specific Ideas

- The decorator is the **single source of truth** for the warn+delegate behaviour: "supprimer la dette en v0.7.0 = effacer un bloc d'alias" (SCOPE D-SCOPE-2). Design it so the v0.7.0 cleanup is a mechanical delete of decorated stubs + the registry/alias-test entries, with no logic change.
- Phase 21 is explicitly the **pattern proof** — favour the simplest correct implementation that Phases 22–24 can replicate ~50 times by rote, over cleverness.

### Open items flagged for the researcher / planner
- **interrogate ≥ 95 vs. generic `*args/**kwargs` stubs:** generic one-line stubs have no real signature. Decide how to keep `interrogate` happy and Sphinx `-W` green — either (a) keep a one-line numpydoc docstring on each stub, (b) have the decorator (via `functools.wraps`) copy the accessor method's `__doc__`/metadata onto the stub, or (c) exclude the deprecated aliases from the interrogate target. Research the cleanest option; (b) is the current lean.
- **`stacklevel` correctness through the decorator + lazy-property layers** — verify the emitted warning points at the user's call site. Add a test asserting the warning's location, not just its category/message.
- **Async `await` delegation** — the async decorator variant must `await` the accessor coroutine; confirm the wrapper is itself `async def` (not a sync wrapper returning a coroutine that drops the warning's stacklevel).

</specifics>

<deferred>
## Deferred Ideas

- **Pure SQL builders for timescale** (extracting `_build_*` functions like spatial/etl) — intentionally NOT done this phase (D-06: move verbatim). Could be revisited when v0.8.0 adds advanced TimescaleDB helpers on the clean surface.
- **Folding `TestEtlParity` into the new registry** — optional cleanup, only if zero-risk; not required for Phase 21.
- **The other 4 accessors** (`admin`, `maint`, `backup`, `schema`) + spatial-index relocation — Phases 22–23.
- **Public exports / README / Sphinx / CHANGELOG / MIGRATION / version bump / PyPI publish** — Phase 24 (REORG-05).
- **Alias removal** — v0.7.0.
- **New TimescaleDB power** (continuous aggregates, gapfill, chunks) — v0.8.0.

*Discussion stayed within phase scope — no scope creep surfaced.*

</deferred>

---

*Phase: 21-Infrastructure & Timescale Accessor*
*Context gathered: 2026-06-17*
