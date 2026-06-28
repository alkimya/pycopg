# Phase 41: API Homogenization - Context

**Gathered:** 2026-06-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Make the public surface **consistent and frozen** ahead of the 1.0 freeze: `where=` means
dict-equality everywhere, `filter=` means a raw SQL fragment in spatial, domain exceptions
follow the N818 `*Error` convention, every public method has a stable positional-vs-keyword-only
contract, and the SemVer stability policy is published. This is the FIRST phase of v1.0.0 and runs
**before** any Spatial v2 builder is written (so new builders adopt `filter=` from day one) and
**before** mypy-strict (Phase 46) freezes the type surface.

**In scope (locked by ROADMAP / REQUIREMENTS — not re-litigated):**
- **FREEZE-01:** `where=`→`filter=` rename on all 11 spatial methods (`contains`, `within`,
  `intersects`, `dwithin`, `distance`, `nearest`, `area`, `perimeter`, `centroid`, `buffer`,
  `transform` — both `SpatialAccessor` and `AsyncSpatialAccessor`, plus the module-level
  `build_*_sql` builders + `_append_tail`). Old `where=` keeps working one cycle with
  `DeprecationWarning` + MIGRATION.
- **FREEZE-02:** 4 N818 exception renames → `ExtensionNotAvailableError`, `TableNotFoundError`,
  `InvalidIdentifierError`, `DatabaseExistsError`; old names kept as deprecated aliases; internal
  raise sites use the new names; remove the `N818` suppression in `pyproject.toml`.
- **FREEZE-03:** Public API consistency pass + documented Stable API Contract (positional vs
  keyword-only) for every public method.
- **FREEZE-04:** `docs/stability.md` published (SemVer + deprecation policy), linked from README.
- MIGRATION guide sections for every renamed name.

**Out of scope (deferred to later v1.0.0 phases — do NOT pull in):**
- Any new spatial method (Phases 42–44). New builders only set the `filter=` precedent.
- `db.transaction(isolation_level=)`, savepoints, `%(name)s` named params, `db.health()`,
  structured logging (Phase 45).
- `mypy --strict` blocking + `@overload` + py.typed (FREEZE-05, Phase 46).
</domain>

<decisions>
## Implementation Decisions

### Deprecation timeline & stability contract (FREEZE-04)
- **D-01:** Deprecated names (the `where=` alias, the 4 old exception names, and any new aliases
  the audit produces) are removed **only in 2.0** — strict SemVer. They live through ALL of 1.x;
  no public name is removed in a 1.x minor. `docs/stability.md` states this explicitly.
- **D-02:** `docs/stability.md` publishes a **full support matrix** as part of the frozen 1.0
  contract: supported Python versions, PostgreSQL/PostGIS ranges (**floor 3.0 hard, 3.2
  recommended** — `ST_MakeValid method=structure` needs 3.2), TimescaleDB ranges, **plus a
  per-API stable/experimental tier table**. Ground concrete versions in current `pyproject.toml`
  + the PostGIS research floor. Doc must define "what counts as a breaking change" and be linked
  from README.

### Stable API Contract — keyword-only enforcement (FREEZE-03)
- **D-03:** **Enforce `*` in signatures** (not document-only). Rule: **required args stay
  positional** (e.g. `table`, `geom`); **all optional/defaulted params become keyword-only**
  (`filter=`, `into=`, `order_by=`, `limit=`, `schema=`, etc.). Apply across the 7 accessors +
  flat core.
- **D-04:** `*`-enforcement ships as a **clean breaking change at the 0.x→1.0 boundary** — NO
  transitional positional-accepting shim. Documented in MIGRATION + `docs/stability.md`.
  Rationale: a positional→keyword-only change cannot be served by a clean `DeprecationWarning`
  alias, the 0.x→1.0 boundary is exactly when SemVer permits unguarded breaks, and keeping the
  signatures shim-free keeps them clean for the Phase 46 mypy-strict / `@overload` work. The
  milestone's "every break gets a deprecation cycle" rule applies to **name renames**, not to
  this one-time freeze-boundary signature tightening.

### Consistency-pass scope (FREEZE-03)
- **D-05:** **Audit-then-decide.** Run a full inventory pass across all 7 accessors + the flat
  core — param **names**, param **order**, `into=` **defaults**, and **return shapes** — and
  produce a findings table. The user **reviews the inventory before any fixes land** (review gate).
- **D-06:** Per-finding disposition follows the established milestone rules: **name renames** get a
  one-cycle deprecation alias (`DeprecationWarning` + MIGRATION, removed in 2.0 per D-01);
  **structural / positional / default changes** (return shape, `into=` default, kw-only) ship as
  **clean 1.0 breaks** with MIGRATION entries (same justification as D-04). The audit MAY surface
  new renames — that is expected and acceptable within this phase since 1.0 is the last
  non-breaking window.

### Exception alias mechanism (FREEZE-02)
- **D-07:** **Warn on import only.** The new `*Error` class is canonical; each old name is
  resolved through a module-level `__getattr__` (PEP 562) on `pycopg/exceptions.py` (and
  re-exported through the package `__getattr__` if needed) that emits a `DeprecationWarning` on
  import / attribute access. The old name resolves to the **same class object** as the new one,
  so `except TableNotFound:` keeps catching identically — only the no-warning-at-catch-time case
  changes.
- **D-08:** This **relaxes the ROADMAP Phase 41 success criterion #2** ("...when imported *or
  caught*") to "...when **imported / accessed**". Catch-time warning is intentionally NOT
  implemented — a metaclass `__instancecheck__`/`__subclasscheck__` hack would be fragile,
  surprising, and risky to freeze under SemVer + mypy-strict for the whole 1.x lifetime. Record
  this relaxation in the VERIFICATION/MIGRATION notes so it isn't read as a gap.

### Cross-cutting mechanics (apply to all deprecations in this phase)
- **D-09:** Every deprecation `warnings.warn(...)` must use a **`stacklevel` that points to the
  caller's file, not `pycopg/`** — verified by a test asserting the warning location (Pitfall 6).
  The `where=` shim and the exception `__getattr__` both need correct stacklevel.
- **D-10:** The `-W error::DeprecationWarning` CI gate must stay green: **no internal `pycopg/`
  code may route through a deprecated path** (use `filter=` and the new `*Error` names
  everywhere internally); grep `pycopg/` for old names before shipping. Deprecation behavior is
  exercised only in dedicated `pytest.warns(...)` tests.
- **D-11:** Sync/async parity is non-negotiable — the `where=`→`filter=` rename and any audit fix
  land identically on both accessors; `test_accessor_parity` must stay green.

### Claude's Discretion
- Exact shim shape for `where=`→`filter=` (per-signature `filter=None, where=None` + runtime
  check vs a shared decorator/helper over the 11×2 sites) is left to research/planning, provided
  it satisfies D-09/D-10 and produces a clean frozen signature.
- Exact `docs/stability.md` section layout and the precise version numbers in the support matrix
  (grounded in `pyproject.toml` + PostGIS 3.0/3.2 floor).
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope & requirements
- `.planning/REQUIREMENTS.md` §FREEZE-01..04 (and §142–146 traceability) — the locked
  requirements this phase satisfies; line 57 = "every break served via a deprecation cycle + MIGRATION"
  baseline rule (D-04/D-06 carve the freeze-boundary exception).
- `.planning/ROADMAP.md` "Phase 41: API Homogenization" — goal + 5 success criteria (criterion
  #2 relaxed per D-08).

### Research (HIGH confidence, this milestone)
- `.planning/research/SUMMARY.md` §"Phase 41" + §"build order" — why homogenization is first;
  files touched; the where=→filter= seam as "the most critical homogenization decision".
- `.planning/research/PITFALLS.md` Pitfall 6 (deprecation cycle / stacklevel / `-W error`),
  Pitfall 7 (where= raw-fragment-vs-dict inconsistency), Pitfall 8 (N818 deferred decision +
  the 6-step rename checklist) — directly drive D-07..D-10.
- `.planning/research/FEATURES.md` — feature-level detail on the homogenization surface.

### Source to modify
- `pycopg/spatial.py` — `_append_tail` (line ~150), the 11 `build_*_sql` builders and the 11
  `SpatialAccessor` + 11 `AsyncSpatialAccessor` methods all carry `where: str | None = None`
  (line ~1024 `class SpatialAccessor`, line ~1909 `class AsyncSpatialAccessor`). Module docstring
  line ~21 documents `where=` as a raw SQL fragment — update to `filter=`.
- `pycopg/exceptions.py` — the 4 classes to rename (`ExtensionNotAvailable`, `TableNotFound`,
  `InvalidIdentifier`, `DatabaseExists`); add module `__getattr__` for deprecated aliases.
- `pyproject.toml` lines 93–96 — the `"pycopg/exceptions.py" = ["N818"]` per-file suppression to
  remove once renames land.

### Codebase maps (consult during audit)
- `.planning/codebase/CONVENTIONS.md`, `.planning/codebase/ARCHITECTURE.md`,
  `.planning/codebase/STRUCTURE.md` — for the FREEZE-03 consistency inventory across the 7
  accessors + flat core.

### Project memory (historical mechanism)
- `@deprecated_alias` pattern was established in v0.6.0 and hard-removed in v0.7.0 (`aliases.py`
  deleted) — it solved old-flat-name→accessor-path, a DIFFERENT shape than this phase's
  same-accessor param/exception renames (Pitfall 6). Do not assume it still exists in the tree.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `validate_identifiers` / injection-test convention — every builder validates identifiers line-1;
  reuse unchanged (no new builders this phase, but audit fixes must not drop it — the v0.10.0 COPY
  lesson).
- `_append_tail(sql, where, order_by, limit, has_where=...)` in `spatial.py` is the single
  choke-point through which all 11 spatial methods route their `where`/`order_by`/`limit` — the
  cleanest place to rename `where`→`filter` once.
- `_build_where_dict` (v0.9.0 CRUD) defines the dict-equality `where=` convention that wins the
  homogenization (the reason spatial's raw fragment must vacate the `where=` name).

### Established Patterns
- Pure-builder + thin-accessor split: module-level `build_*_sql` functions are pure; accessors
  call them. Rename must hit both layers + the module docstring.
- Sync/async mirror: `SpatialAccessor` (~line 1024) and `AsyncSpatialAccessor` (~line 1909) are
  1:1; `test_accessor_parity` enforces it.
- Coverage ratchet ≥95% (baseline measured 96.32% at v0.10.0); `pragma: no cover` allowed only
  with em-dash justification.

### Integration Points
- `docs/stability.md` is NEW and must be linked from README + (likely) the Sphinx toctree
  (Sphinx `-W` gate is clean-or-fail).
- MIGRATION guide gains a Phase-41 section (where=→filter=, 4 exception renames, kw-only break,
  any audit-surfaced renames).
- CI gate `-W error::DeprecationWarning` constrains the implementation (D-10).
</code_context>

<specifics>
## Specific Ideas

- User framing for the milestone: "homogénéiser à fond" — hence the audit-then-decide breadth
  (D-05) rather than a minimal pass.
- The freeze-boundary carve-out (D-04/D-06): the "every break gets a deprecation cycle" rule is a
  *rename* rule; one-time signature tightening at 0.x→1.0 is explicitly allowed to ship clean.
</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. (Spatial v2 methods, transaction/isolation/savepoint
gaps, named params, health, logging, and mypy-strict are all already scheduled in Phases 42–46,
not deferrals.)

</deferred>

---

*Phase: 41-API Homogenization*
*Context gathered: 2026-06-28*
