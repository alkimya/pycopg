# Phase 22: Admin, Maint & Backup Accessors - Context

**Gathered:** 2026-06-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Replicate the **already-proven Phase 21 pattern** across the three smaller accessors, in one phase:

- `db.admin.*` / `async_db.admin.*` — **11 methods** (roles & permissions)
- `db.maint.*` / `async_db.maint.*` — **6 methods** (size & maintenance)
- `db.backup.*` / `async_db.backup.*` — **4 methods** (dump/restore & CSV)

**Total = 21 flat names** moved into accessors, each leaving a thin deprecated alias on `db.*`.

The pattern is **locked** by Phase 21 (D-01..D-10 in `21-CONTEXT.md`): `@deprecated_alias` decorator (reused verbatim), one dedicated module per accessor, lazy-cached property on `Database`/`AsyncDatabase`, thin `@deprecated_alias`-decorated stubs with one-line "Deprecated: use ..." docstrings, DB-free MagicMock alias tests, and the data-driven `ACCESSOR_PAIRS` registry in `tests/test_parity.py`. **This phase does not invent anything new — it applies the proven pattern 21 more times.**

What "done" means (ROADMAP success criteria):
1. `db.admin.create_role(...)`, `db.maint.vacuum(...)`, `db.backup.pg_dump(...)` (and all remaining methods in the 3 accessors) return the same results as the old flat calls.
2. Each of the 21 legacy flat names still works and emits a `DeprecationWarning` naming the new accessor path.
3. `test_parity` passes with all three new accessors registered (sync + async) via `ACCESSOR_PAIRS`.
4. Coverage stays ≥ 94% with alias warn+delegate tests in place; no `-W error::DeprecationWarning` breakage.

**This milestone MOVES the existing surface; it adds no new power.** No new admin/maint/backup helpers.

### The 21 methods (verbatim from `pycopg/database.py` / `pycopg/async_database.py`)

**`db.admin.*` (11):** `create_role`, `drop_role`, `role_exists`, `list_roles`, `alter_role`, `grant_role`, `revoke_role`, `grant`, `revoke`, `list_role_members`, `list_role_grants`.
*(`grant`/`revoke` = object permissions; `grant_role`/`revoke_role` = role membership.)*

**`db.maint.*` (6):** `size`, `table_size`, `table_sizes`, `vacuum`, `analyze`, `explain`.

**`db.backup.*` (4):** `pg_dump`, `pg_restore`, `copy_to_csv`, `copy_from_csv`.

</domain>

<decisions>
## Implementation Decisions

> Phase 21's D-01..D-10 (decorator shape, verbatim-move + `self.`→`self._db.` rewrite, dedicated
> module per accessor, lazy cached property, DB-free MagicMock alias tests, `ACCESSOR_PAIRS`
> registry, one-line stub docstrings, `stacklevel=2`) are **LOCKED and carried forward**. They are
> not re-litigated here. The decisions below cover only what is specific to Phase 22.

### Method count (resolved)
- **D-01 [informational]:** Admin has **11 methods**, not 12. The ROADMAP Phase 22 goal text ("12 + 6 + 4 methods", "the 22 legacy flat names") is a **stale off-by-one** — both the live source (`pycopg/database.py`) and `REQUIREMENTS.md` ADM-01 enumerate exactly 11 admin methods. The real phase total is **21 flat names** (11 + 6 + 4). Planner and verifier MUST validate against **21**, not 22. (Cosmetic ROADMAP text fix is optional and can ride along in Phase 24's doc pass; do not let "find the 12th method" become phantom scope.)
  - *Tagged `[informational]`: this is an anti-scope guard on the method count, not a citable feature. It is satisfied structurally — all 3 plans validate against 21/11 and 22-02 says "not 22" explicitly (plan-checker Dim. 1 & 7 confirmed). Excluded from the decision-coverage gate by design.*

### Intra-accessor cross-calls (correctness — the one real departure from timescale)
- **D-02:** Unlike the 6 timescale methods (which had no intra-family cross-calls), `create_role`'s body calls **`self.role_exists(...)`** and **`self.grant_role(...)`** — both *also* admin methods being deprecated. When moving the body into `AdminAccessor`, rewrite these sibling calls to **`self._db.admin.role_exists(...)`** / **`self._db.admin.grant_role(...)`** — i.e. call the *accessor* method directly, **NOT** the deprecated flat alias (`self._db.role_exists(...)` would emit an internal `DeprecationWarning` and break the `-W error` gate / pollute output).
- **D-03:** The general rewrite rule for moved bodies: `self.X(...)` where `X` is **a sibling method of the same accessor** → `self._db.<accessor>.X(...)`; `self.Y(...)` where `Y` stays flat on `db.*` (core transactional: `execute`, `connect`, `cursor`, `transaction`, `session`, etc.) → `self._db.Y(...)`. The researcher must **scan all 21 bodies (sync + async)** for self-calls and classify each, because a missed sibling-call is a latent internal-warning bug. (Known instance: the two in `create_role`; verify there are no others across maint/backup.)

### Decomposition (3 waves, mirroring Phase 21)
- **D-04 [informational]:** Structure the phase as **3 plans / 3 waves**, exactly like Phase 21:
  *(Tagged `[informational]`: this is the decomposition of the plans themselves, not a feature any single plan cites by id. Satisfied structurally — exactly 3 PLAN.md files at waves 1/2/3, depends_on chained. Excluded from the decision-coverage gate by design.)*
  - **Wave 1** — create `pycopg/admin.py`, `pycopg/maint.py`, `pycopg/backup.py` (and their `Async*Accessor`), moving the 21 method bodies verbatim with the `self.`→`self._db.` rewrite (D-02/D-03).
  - **Wave 2** *(blocked on W1)* — wire `db.admin`/`maint`/`backup` lazy cached properties (sync + async, mirror `_timescale`), replace the 21 flat method defs with `@deprecated_alias("<accessor>.<method>")` thin stubs, add `__init__.py` exports for the 6 new accessor classes.
  - **Wave 3** *(blocked on W2)* — add DB-free alias tests (`test_admin_aliases.py` / `test_maint_aliases.py` / `test_backup_aliases.py`, mirroring `test_timescale_aliases.py`), append the 3 pairs to `ACCESSOR_PAIRS`, migrate existing call-sites to the new paths, and hold the gates (full suite, `-W error::DeprecationWarning`, coverage ≥ 94%).
- **D-05:** Within each wave the 3 accessors can be done in parallel (independent modules/stubs/tests). Touch-points that **all 3 share** — `__init__.py` `__all__`, `ACCESSOR_PAIRS`, the `Database`/`AsyncDatabase` `__init__` cache fields and property blocks — are concentrated in single waves (W2/W3) to avoid 3-way merge friction. (This is why "3 waves" was chosen over "one plan per accessor".)

### SQL treatment (move, don't improve)
- **D-06:** **Move bodies verbatim** (D-06 precedent from Phase 21). Existing `queries.py` constant references (~10 across these bodies) **travel with the code unchanged**; extract **no new builders**. The milestone MOVES the existing surface, it does not refactor it. Lowest risk, smallest diff, behaviour provably identical. (Opportunistic `queries.py` extraction is explicitly out of scope — defer to a later milestone if ever.)

### Claude's Discretion
- Exact per-accessor test-module naming/layout (follow `test_timescale_aliases.py`).
- Whether the 3 alias test modules are 3 files or one parametrized module — follow whatever keeps coverage clean and mirrors Phase 21 most closely.
- Order of the 3 accessors within each wave (independent; pick any).
- `from __future__ import annotations` + `TYPE_CHECKING` import guards in the new modules — follow `timescale.py`/`spatial.py`/`etl.py`.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope & locked decisions
- `.planning/v0.6.0-SCOPE.md` — D-SCOPE-1..4 (LOCKED); method→accessor mapping; vigilance points (coverage ratchet, `test_parity`, filterwarnings, naming consistency). Note: the SCOPE doc lists the admin block without a hard count — the authoritative count is **11** (see D-01).
- `.planning/phases/21-infrastructure-timescale-accessor/21-CONTEXT.md` — **the locked pattern (D-01..D-10)**: decorator shape, verbatim-move rule, dedicated module per accessor, lazy property, DB-free alias tests, `ACCESSOR_PAIRS` registry, one-line stub docstrings, `stacklevel` footgun. Phase 22 replicates this; read it first.
- `.planning/PROJECT.md` § "Current Milestone: v0.6.0" — locked decisions + resolved open questions (schema = one block; DataFrame stays flat; spatial-index → `db.spatial.*`, which is Phase 23 not here).
- `.planning/ROADMAP.md` § "Phase 22" — goal + 4 success criteria + requirement IDs. ⚠ Its "12 + 6 + 4 / 22 names" wording is a stale off-by-one; the real total is **21** (D-01).
- `.planning/REQUIREMENTS.md` — ADM-01, MNT-01, BKP-01 acceptance text (ADM-01 enumerates the 11 admin methods authoritatively).

### The proven precedent to mirror (the template — read these as the pattern source)
- `pycopg/aliases.py` — the `@deprecated_alias(target_path)` decorator. **Reuse verbatim**, no changes needed; it already branches sync/async via `iscoroutinefunction`, resolves `<accessor>.<method>` lazily on `self`, and emits the v0.7.0-removal message at `stacklevel=2`.
- `pycopg/timescale.py` — `TimescaleAccessor` / `AsyncTimescaleAccessor`: exact module/class shape to copy for `admin.py`/`maint.py`/`backup.py` (`__init__(self, db)` storing `self._db`, methods calling `self._db.execute(...)`, `TYPE_CHECKING` imports, numpydoc docstrings).
- `pycopg/database.py:88` (`self._timescale: TimescaleAccessor | None = None`), `:276-292` (lazy `timescale` property), `:1669-1690` (the 6 `@deprecated_alias` stubs) — replicate for admin/maint/backup.
- `pycopg/async_database.py` — async `_timescale` init + lazy property + the async deprecated stubs (parity mirror).
- `pycopg/__init__.py` — `__all__` exports for `SpatialAccessor`/`ETLAccessor`/`TimescaleAccessor` + async variants; add the 6 new accessor classes alongside.
- `tests/test_parity.py:12,19-26` — `ACCESSOR_PAIRS` registry + `test_accessor_parity` parametrized test (seeded with the timescale pair; append admin/maint/backup pairs). Note `TestEtlParity` was folded out (`:506`).
- `tests/test_timescale_aliases.py` — the DB-free MagicMock alias test pattern (asserts warn + `stacklevel=2` caller location + delegation, no live DB). Template for the 3 new alias test modules.

### Source of the methods being moved
- `pycopg/database.py` — admin `:1854-2227` (`create_role` 1854, `drop_role` 1928, `role_exists` 1942, `list_roles` 1958, `alter_role` 1974, `grant_role` 2043, `revoke_role` 2059, `grant` 2072, `revoke` 2133, `list_role_members` 2193, `list_role_grants` 2209); maint `:1697-1853` (`size` 1697, `table_size` 1720, `table_sizes` 1747, `vacuum` 1769, `analyze` 1803, `explain` 1818); backup `:2228-2540` (`pg_dump` 2228, `pg_restore` 2291, `copy_to_csv` 2395, `copy_from_csv` 2469).
- `pycopg/async_database.py` — the async equivalents (counts verified: admin 11, maint 6, backup 4 — full parity).
- `pycopg/queries.py` — SQL constants referenced by these bodies (~10 refs; travel unchanged, D-06).
- `pycopg/utils.py` — `validate_identifier`/`validate_identifiers`/etc. guards used by the moved bodies; they travel with the code.
- `pycopg/exceptions.py` — domain exceptions raised by these methods.

### Tests / gates
- `pyproject.toml [tool.pytest.ini_options]` — `addopts = "... --cov-fail-under=94"`, `asyncio_mode = "auto"`. Any `filterwarnings` added must be **targeted** to pycopg's own `DeprecationWarning` (SCOPE vigilance note).
- Call-sites to migrate to the new accessor paths: `tests/test_database.py`, `tests/test_async_database.py`, `tests/test_database_integration.py`, `tests/test_sql_injection.py`, `tests/test_subprocess_env.py` (grep for admin/maint/backup flat method names).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`@deprecated_alias` decorator** (`pycopg/aliases.py`) — reused as-is across all 21 stubs; zero changes.
- **Lazy accessor pattern** (`database.py:88,276-292`, async mirror) — copy verbatim three times (`_admin`/`_maint`/`_backup` cache fields + lazy properties).
- **`timescale.py` module shape** — direct template for `admin.py`/`maint.py`/`backup.py` (both sync + async accessor in one module).
- **`ACCESSOR_PAIRS` + `test_accessor_parity`** (`tests/test_parity.py`) — append 3 tuples; the parity engine already exists.
- **`test_timescale_aliases.py`** — DB-free MagicMock template for the 3 new alias test modules (warn + stacklevel + delegate).
- **`queries.py` constants** — the ~10 SQL constants these bodies use travel unchanged (D-06).

### Established Patterns
- **One module per accessor domain** — `spatial.py`/`etl.py`/`timescale.py` → add `admin.py`/`maint.py`/`backup.py`.
- **numpydoc docstrings, shallow, no Examples**; `interrogate ≥ 95` (gate ≥ 95, currently 100%). Moved methods keep their docstrings; flat stubs use the one-line "Deprecated: use ``db.<accessor>.<method>`` instead." form proven in Phase 21 (keeps interrogate happy and Sphinx `-W` green).
- **Coverage ratchet `--cov-fail-under=94`** — every thin alias must be exercised by the DB-free alias tests, or the gate drops.
- **`self.`→`self._db.` rewrite on move** — plus the sibling-call refinement (D-02/D-03).

### Integration Points
- `Database`/`AsyncDatabase` `__init__` — add `_admin`/`_maint`/`_backup` cache fields (mirror `_timescale`).
- `Database`/`AsyncDatabase` — add 3 lazy `@property` blocks each (sync + async).
- The 21 flat method defs in `database.py` / `async_database.py` → replaced by `@deprecated_alias("<accessor>.<method>")` stubs.
- `tests/test_parity.py` `ACCESSOR_PAIRS` — append `(AdminAccessor, AsyncAdminAccessor)`, `(MaintAccessor, AsyncMaintAccessor)`, `(BackupAccessor, AsyncBackupAccessor)`.
- `pycopg/__init__.py` `__all__` — surface the 6 new accessor classes (formal README/Sphinx export hardening remains Phase 24).
- Existing test call-sites migrated to `db.admin.*` / `db.maint.*` / `db.backup.*`.

</code_context>

<specifics>
## Specific Ideas

- **The intra-accessor cross-call is the ONLY substantive difference from Phase 21.** Timescale had zero sibling cross-calls; `AdminAccessor.create_role` has two (`role_exists`, `grant_role`). The researcher must enumerate every self-call across the 21 bodies (sync + async) and classify it (sibling-accessor vs core-flat) per D-03 — a missed sibling call is a latent `-W error` failure that won't show up until the gate runs.
- **Favour the simplest correct replication** that matches Phase 21 line-for-line. This phase is the second application of a pattern designed to be applied ~50 times by rote; cleverness or divergence from the timescale precedent is a smell.
- **Validate against 21, not 22** (D-01) — guard against the ROADMAP off-by-one becoming phantom scope.

</specifics>

<deferred>
## Deferred Ideas

- **`db.schema.*` (~26 methods) + spatial-index relocation** (`create_spatial_index`/`list_geometry_columns` → `db.spatial.*`) — **Phase 23**.
- **Public exports hardening / README / Sphinx / CHANGELOG / MIGRATION / version bump / PyPI publish** — **Phase 24** (REORG-05). This phase adds the `__init__.py` `__all__` entries as the pattern dictates, but the formal doc/release work is Phase 24's.
- **Opportunistic `queries.py` builder extraction** for admin/maint/backup SQL — intentionally NOT done (D-06: move, don't improve). Revisit only on a clean future surface if ever.
- **Cosmetic ROADMAP Phase 22 "12/22" → "11/21" text fix** — can ride along in Phase 24's doc pass; not blocking.
- **Alias removal** — v0.7.0.
- **New admin/maint/backup power** — not this milestone (moves existing surface only).

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 22-Admin, Maint & Backup Accessors*
*Context gathered: 2026-06-17*
