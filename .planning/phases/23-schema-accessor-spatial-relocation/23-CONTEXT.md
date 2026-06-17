# Phase 23: Schema Accessor & Spatial Relocation - Context

**Gathered:** 2026-06-17
**Status:** Ready for planning

<domain>
## Phase Boundary

The **third (and largest) application of the twice-proven Phase 21/22 accessor pattern**, plus a
**structurally novel sub-task — relocating 2 methods into an *existing* accessor**:

- **`db.schema.*` / `async_db.schema.*` — 27 methods** (DDL + introspection + extensions +
  schemas + tables/columns + constraints/index, **one single block**). New module `pycopg/schema.py`
  (`SchemaAccessor` / `AsyncSchemaAccessor`), exactly like `admin.py`/`maint.py`/`backup.py`.
- **`db.spatial.*` / `async_db.spatial.*` — 2 relocated methods** (`create_spatial_index`,
  `list_geometry_columns`) moved into the **already-existing** `SpatialAccessor`/`AsyncSpatialAccessor`
  in `pycopg/spatial.py` (thematic PostGIS coherence, SCH-02). **Not** a new module.

**Total = 29 flat names** moved, each leaving a thin `@deprecated_alias` stub on `db.*` / `async_db.*`.

What "done" means (ROADMAP success criteria):
1. `db.schema.create_database(...)`, `db.schema.list_tables()`, `db.schema.create_index(...)` (and all
   27 schema methods) return the same results as the old flat calls.
2. `db.spatial.create_spatial_index(...)` / `db.spatial.list_geometry_columns()` work; the old flat
   `db.create_spatial_index(...)` / `db.list_geometry_columns()` still work and emit a
   `DeprecationWarning` pointing to `db.spatial.*`.
3. All ~29 legacy flat names warn and delegate; no existing caller silently broken.
4. `test_parity` passes with the schema accessor registered (sync + async) via `ACCESSOR_PAIRS`;
   coverage stays ≥ 94%. *(SpatialAccessor is already in `ACCESSOR_PAIRS`; relocating 2 methods into it
   doesn't add a pair — but the parity test must still pass for the 2 newly-added spatial methods.)*

**This milestone MOVES the existing surface; it adds no new power.** No new DDL/introspection/PostGIS
helpers (CRUD, enriched introspection, `db.meta.*` carve-out → v0.9.0; spatial v2 → v1.0.0).

### The 27 schema methods (verbatim from `pycopg/database.py` / `pycopg/async_database.py`)

Verified count is **27**, not "~26" (ROADMAP/SCOPE wording). Authoritative source enumeration below
(sync line / async line):

- **Databases (4):** `create_database` (840/1740), `drop_database` (865/1769), `database_exists`
  (892/1798), `list_databases` (911/1819).
- **Extensions (4):** `create_extension` (926/1188), `drop_extension` (949/1221), `list_extensions`
  (970/1211), `has_extension` (980/1172).
- **Schemas (4):** `create_schema` (1000/739), `drop_schema` (1021/870), `list_schemas` (1040/712),
  `schema_exists` (1051/723).
- **Tables (6):** `list_tables` (1071/760), `table_exists` (1087/776), `drop_table` (1143/889),
  `truncate_table` (1168/914), `table_info` (1186/832), `row_count` (1204/850).
- **Columns (2):** `list_columns` (1105/794), `columns_with_types` (1123/812).
- **Constraints/index (7):** `add_primary_key` (1228/936), `add_foreign_key` (1260/968),
  `add_unique_constraint` (1331/1039), `create_index` (1362/1070), `drop_index` (1408/1116),
  `list_indexes` (1426/1134), `list_constraints` (1443/1151).

### The 2 relocated spatial-index methods (move INTO `pycopg/spatial.py`)

- `create_spatial_index` — sync `database.py:1671`, async `async_database.py:1246`. Inline f-string
  `CREATE INDEX … USING GIST`, `validate_identifiers`-guarded, calls `self.execute(...)`.
- `list_geometry_columns` — sync `database.py:1700`, async `async_database.py:1275`.
  `queries.LIST_GEOMETRY_COLUMNS.format(where_clause=…)`, calls `self.execute(...)`.

</domain>

<decisions>
## Implementation Decisions

> **LOCKED and carried forward — NOT re-litigated here:** the entire Phase 21 pattern
> (`21-CONTEXT.md` D-01..D-10: `@deprecated_alias` target-path decorator reused verbatim from
> `pycopg/aliases.py`; one dedicated module per *new* accessor; lazy-cached property mirroring
> `_timescale`/`_spatial`; generic `(*args, **kwargs)` thin stubs with one-line
> "Deprecated: use ``db.schema.<m>`` instead." docstrings; `stacklevel=2`; DB-free MagicMock alias
> tests asserting warn + caller stacklevel + delegate; data-driven `ACCESSOR_PAIRS` registry) and
> Phase 22's refinements (`22-CONTEXT.md` D-02/D-03 self-call rewrite rule; D-04 3-wave decomposition;
> D-06 move-don't-improve, extract no new builders). The decisions below cover only what is **specific
> to Phase 23**.

### Method count (resolved)
- **D-01 [informational]:** The schema block is **27 methods**, not "~26" (ROADMAP Phase 23 goal and
  `v0.6.0-SCOPE.md` say "≈26"). All 27 verified present in both `database.py` and `async_database.py`
  (line numbers in `<domain>`). The phase total is **29 flat names** (27 schema + 2 spatial-reloc).
  Planner and verifier MUST validate against **27 / 29**, not 26/28. Cosmetic ROADMAP/SCOPE text fix
  can ride along in Phase 24's doc pass; do not let "find the 26th vs 27th method" become phantom scope.
  *(Tagged `[informational]`: anti-scope guard on the count, not a citable feature. Excluded from the
  decision-coverage gate by design.)*

### Decomposition — schema track SEPARATE from the spatial relocation (resolved)
- **D-02:** Keep the **27-method schema-accessor track** (new module + wiring + tests, mirroring the
  Phase 22 3-wave shape) **cleanly separated** from the **2-method spatial relocation** track. Rationale:
  the spatial relocation is structurally unlike everything in Phases 21–22 — it **edits an existing
  module (`spatial.py`) and an existing test surface** rather than creating new ones, and it touches the
  existing `SpatialAccessor` constructor-guard semantics (see D-05). Keeping it a distinct plan/track
  stops that odd-one-out work from contaminating the rote schema replication and keeps each plan's
  edit-pattern uniform.
- **D-03 [informational]:** Concrete shape — mirror Phase 22's 3 waves for the **schema track**
  (W1: create `pycopg/schema.py` with `SchemaAccessor`/`AsyncSchemaAccessor`, 27 bodies moved verbatim
  with the rewrite of D-04; W2: lazy `db.schema`/`async_db.schema` cached properties + `_schema` cache
  field + 27 `@deprecated_alias("schema.<m>")` stubs (sync+async) + `__init__.py` export of the 2 new
  classes; W3: DB-free `test_schema_aliases.py` + append `(SchemaAccessor, AsyncSchemaAccessor)` to
  `ACCESSOR_PAIRS` + migrate schema call-sites + hold gates). The **spatial-relocation track** is its
  own plan: move the 2 bodies into `spatial.py`, leave 2 `@deprecated_alias("spatial.<m>")` stubs on
  `db.*`/`async_db.*`, add 2 alias tests + 2 call-site rewrites in `from_geodataframe`. Plan-level
  dependency: the spatial-reloc track's `from_geodataframe` rewrite also touches a *schema* method
  (`has_extension`, `add_primary_key`) — see D-06 — so sequence so that whichever plan touches the two
  DataFrame methods owns BOTH rewrites atomically (avoid a 2-way edit of the same lines). Final exact
  plan boundaries are the planner's call.
  *(Tagged `[informational]`: decomposition of the plans themselves, satisfied structurally; excluded
  from the decision-coverage gate.)*

### Self-reference rewrite rule — generalize beyond `self.execute` (resolved)
- **D-04:** The D-03(P22) rewrite rule is **generalized to cover every `self.<X>` reference — methods
  AND attributes**, not just `self.execute`. Driver: 3 schema methods bypass `self.execute()` and use
  raw psycopg against an admin connection: `create_database`/`drop_database`/`database_exists` each call
  `self.config.with_database("postgres")` then `psycopg.connect(**…)`. After the move, `self.config`
  has no meaning on the accessor — it must become **`self._db.config`**. Rule for moved bodies:
  - `self.<core-flat-method>(...)` (e.g. `execute`) → `self._db.<method>(...)`.
  - `self.<sibling-schema-method>(...)` → `self._db.schema.<method>(...)` (call the accessor, never the
    deprecated flat alias). **Scan found ZERO sibling-schema self-calls across all 27 bodies** — the
    only intra-family risk Phase 22 flagged does not materialize here — but the researcher MUST re-verify
    (a missed one is a latent `-W error` failure).
  - `self.<attr>` (`self.config`, `self.engine`, …) → `self._db.<attr>`.
  - Researcher MUST enumerate **every** `self.X` in all 27 sync + 27 async bodies and classify it; do
    not assume "only `self.execute`" (true for 24 of 27, false for the 3 database-level methods).

### Internal callers that STAY flat must be rewritten too (resolved — Phase-23-only surface)
- **D-05:** Two **stay-flat DataFrame methods** internally call methods being moved this phase. If left
  as `self.X(...)`, after the move they hit the **deprecated flat alias** and emit an internal
  `DeprecationWarning`, breaking the `-W error::DeprecationWarning` gate. These are NOT in scope to move
  (DataFrame stays flat, PROJECT.md), but their call-sites MUST be rewritten to the accessor paths.
  Exact, exhaustive surface (already scanned — 8 sites, 4 sync + 4 async):
  - `from_dataframe`: sync `database.py:1503`, async `async_database.py:1479` →
    `self.add_primary_key(...)` becomes `self.schema.add_primary_key(...)`.
  - `from_geodataframe`: sync `database.py:1583/1619/1622`, async `async_database.py:1568/1607/1610` →
    `self.has_extension("postgis")` → `self.schema.has_extension(...)`;
    `self.add_primary_key(...)` → `self.schema.add_primary_key(...)`;
    `self.create_spatial_index(...)` → `self.spatial.create_spatial_index(...)`.
  This is a **Phase-23-only failure mode** (no stay-flat caller of a moved method existed in 21/22).
  Lock it as an explicit must-do; do not rely on tests alone to catch it. (Note: `from_geodataframe`
  already guards `has_extension("postgis")` itself, so routing its `create_spatial_index` through the
  PostGIS-guarded `db.spatial` accessor is safe — D-06.)

### Spatial relocation inherits the SpatialAccessor PostGIS guard — ACCEPTED (resolved)
- **D-06:** Relocating `create_spatial_index`/`list_geometry_columns` into `SpatialAccessor` means they
  inherit its **constructor guard** (`spatial.py:1047` — `db.spatial` raises `ExtensionNotAvailable` if
  PostGIS is absent). The old flat methods had **no guard** (they'd fail with a raw psycopg error if
  PostGIS were missing). **Accept the changed failure mode**: the deprecated alias path now raises
  `ExtensionNotAvailable` early (via `self.spatial` construction) instead of a raw error. It is a
  strictly clearer failure and thematically correct (these ARE PostGIS methods). **Note it in
  CHANGELOG/MIGRATION (Phase 24)** as a minor behavior refinement on the deprecated path. **No extra code
  to bypass the guard** — that would defeat the thematic point and add risk.

### SQL treatment — move verbatim, do NOT conform the 2 relocated methods to the builder house style
- **D-07:** `create_spatial_index` (inline f-string) and `list_geometry_columns`
  (`queries.LIST_GEOMETRY_COLUMNS.format(...)`) currently call `self.execute(...)` directly and do **not**
  use `SpatialAccessor`'s pure-builder + `_run(into=…)` routing convention. **Move them verbatim**
  (rewriting `self.execute` → `self._db.execute` per D-04), keeping their existing inline SQL shape — do
  **NOT** refactor them into pure builders or route them through `_run`. This follows the locked D-06(P21)/
  D-06(P22) "move, don't improve / extract no new builders" precedent. Conforming them to the house style
  is scope creep, risks behavior drift, and is explicitly deferred to spatial v2 (v1.0.0) if ever. The
  ~14 `queries.py` SQL constants used across all moved bodies travel **unchanged**.

### Claude's Discretion
- Exact per-track plan boundaries / number of plans (the D-02/D-03 separation is locked; the precise
  cut is the planner's call within it).
- Whether `test_schema_aliases.py` is one parametrized module or split — follow whatever keeps coverage
  clean and mirrors Phase 21/22 most closely.
- Whether the 2 spatial alias tests live in a new `test_spatial_aliases.py` or extend the existing
  spatial test module — follow the existing spatial test layout.
- `from __future__ import annotations` + `TYPE_CHECKING` import guards in `schema.py` — follow
  `timescale.py`/`admin.py`/`spatial.py`.
- Order of waves' internal work; order of the schema track vs spatial-reloc track (independent except
  for the shared `from_geodataframe`/`from_dataframe` edit — see D-03/D-05).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope & locked decisions
- `.planning/v0.6.0-SCOPE.md` — D-SCOPE-1..4 (LOCKED); method→accessor mapping (its schema block lists
  "≈26" — authoritative count is **27**, see D-01); vigilance points (coverage ratchet, `test_parity`,
  targeted `filterwarnings`, naming consistency).
- `.planning/phases/21-infrastructure-timescale-accessor/21-CONTEXT.md` — **the locked pattern
  (D-01..D-10)**: decorator shape, verbatim-move rule, dedicated module per accessor, lazy property,
  DB-free alias tests, `ACCESSOR_PAIRS` registry, one-line stub docstrings, `stacklevel` footgun. Read first.
- `.planning/phases/22-admin-maint-backup-accessors/22-CONTEXT.md` — the 3-wave decomposition shape
  (D-04) and the **self-call rewrite rule (D-02/D-03)** that Phase 23 generalizes (see D-04 here).
- `.planning/PROJECT.md` § "Current Milestone: v0.6.0" — locked decisions + resolved open questions
  (schema = one block; DataFrame stays flat on `db.*`; spatial-index → `db.spatial.*`).
- `.planning/ROADMAP.md` § "Phase 23" — goal + 4 success criteria + requirement IDs. ⚠ "~26 methods"
  wording is approximate; real count is **27** (D-01).
- `.planning/REQUIREMENTS.md` — SCH-01 (enumerates the schema methods authoritatively) and SCH-02
  (the 2 spatial-index relocations) acceptance text.

### The proven precedent to mirror (the template — read these as the pattern source)
- `pycopg/aliases.py` — `@deprecated_alias(target_path)` decorator. **Reuse verbatim**; branches
  sync/async via `iscoroutinefunction`, resolves `<accessor>.<method>` lazily on `self`, emits the
  v0.7.0-removal message at `stacklevel=2`.
- `pycopg/timescale.py` + `pycopg/admin.py` / `pycopg/maint.py` / `pycopg/backup.py` — exact module/class
  shape to copy for `pycopg/schema.py` (`__init__(self, db)` storing `self._db`, methods calling
  `self._db.execute(...)`, `TYPE_CHECKING` imports, numpydoc docstrings, both sync + async accessor in
  one module).
- `pycopg/spatial.py:1023` (`SpatialAccessor`) / `:1859`-ish (`AsyncSpatialAccessor`) — the **existing**
  accessor the 2 relocated methods move INTO. Note the **constructor PostGIS guard** at `spatial.py:1047`
  (`if not db.has_extension("postgis"): raise ExtensionNotAvailable(...)`) — relevant to D-06.
- `pycopg/database.py` lazy `_timescale`/`_admin`/`_maint`/`_backup` properties + `__init__` cache fields
  — replicate for `_schema`. `pycopg/async_database.py` — async mirror.
- `pycopg/__init__.py` — `__all__` exports for the existing accessor classes; add `SchemaAccessor` /
  `AsyncSchemaAccessor` alongside (formal README/Sphinx export hardening is Phase 24).
- `tests/test_parity.py` — `ACCESSOR_PAIRS` registry + `test_accessor_parity`; append
  `(SchemaAccessor, AsyncSchemaAccessor)`. SpatialAccessor pair is already registered — the relocated
  methods must keep that pair's parity test green.
- `tests/test_timescale_aliases.py` (+ the admin/maint/backup alias test modules from Phase 22) — the
  DB-free MagicMock alias-test template (warn + caller stacklevel + delegate). Template for
  `test_schema_aliases.py` and the 2 spatial alias tests.

### Source of the methods being moved
- `pycopg/database.py` — the 27 schema method bodies (line numbers enumerated in `<domain>`); the 2
  spatial-reloc bodies at `:1671` (`create_spatial_index`) and `:1700` (`list_geometry_columns`); the 2
  stay-flat DataFrame callers `from_dataframe` (`:1503`) and `from_geodataframe` (`:1583/1619/1622`)
  whose call-sites must be rewritten (D-05).
- `pycopg/async_database.py` — async equivalents (parity verified; the 8 internal-caller sites are at
  `:1479` and `:1568/1607/1610`).
- `pycopg/queries.py` — ~14 SQL constants referenced by these bodies (`LIST_DATABASES`,
  `DATABASE_EXISTS`, `LIST_EXTENSIONS`, `EXTENSION_EXISTS`, `LIST_SCHEMAS`, `SCHEMA_EXISTS`,
  `LIST_TABLES`, `TABLE_EXISTS`, `GET_COLUMNS`, `TABLE_INFO`, `ROW_COUNT`, `LIST_INDEXES`,
  `LIST_CONSTRAINTS`, `LIST_GEOMETRY_COLUMNS`); they **travel unchanged** (D-07).
- `pycopg/utils.py` — `validate_identifier`/`validate_identifiers`/`validate_extension_name` guards used
  by the moved bodies; they travel with the code.
- `pycopg/exceptions.py` — `ExtensionNotAvailable` (the SpatialAccessor guard, D-06) and any domain
  exceptions raised by schema methods.

### Tests / gates
- `pyproject.toml [tool.pytest.ini_options]` — `addopts = "... --cov-fail-under=94"`,
  `asyncio_mode = "auto"`. Any `filterwarnings` added must be **targeted** to pycopg's own
  `DeprecationWarning` (SCOPE vigilance note).
- Call-sites to migrate to the new schema paths: grep schema/spatial-reloc flat method names across
  `tests/test_database.py`, `tests/test_async_database.py`, `tests/test_database_integration.py`,
  `tests/test_sql_injection.py`, `tests/test_subprocess_env.py`, and the existing spatial test module(s).
- Known env note: 2 pre-existing flaky full-suite DB tests (`test_async_transaction_fix`,
  `test_create_spatial_index_name_parameter`) — UndefinedTable fixture-isolation, NOT v0.6.0 code; use
  `-o addopts=""` for targeted runs. (`test_create_spatial_index_name_parameter` touches a method being
  relocated this phase — confirm the relocation doesn't change its pre-existing flakiness profile.)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **`@deprecated_alias` decorator** (`pycopg/aliases.py`) — reused as-is across all 29 stubs; zero changes.
- **Lazy accessor pattern** (`database.py` `_timescale`/`_admin`/… cache fields + lazy properties, async
  mirror) — copy verbatim once for `_schema`. The spatial relocation needs **no new** property/cache field
  (`db.spatial` already exists).
- **`admin.py`/`maint.py`/`backup.py`/`timescale.py` module shape** — direct template for `pycopg/schema.py`.
- **Existing `SpatialAccessor` / `AsyncSpatialAccessor`** (`pycopg/spatial.py`) — the 2 relocated methods
  are added as plain `self._db.execute(...)` methods (verbatim move, D-07); they do **not** need the
  pure-builder/`_run` treatment the other spatial helpers use.
- **`ACCESSOR_PAIRS` + `test_accessor_parity`** (`tests/test_parity.py`) — append one tuple
  `(SchemaAccessor, AsyncSchemaAccessor)`; the SpatialAccessor pair already exists.
- **`test_timescale_aliases.py` family** — DB-free MagicMock template for `test_schema_aliases.py` and the
  2 spatial alias tests.
- **~14 `queries.py` constants** — travel unchanged (D-07).

### Established Patterns
- **One module per *new* accessor domain** — add `pycopg/schema.py`. The spatial relocation breaks the
  "new module" symmetry: it edits an existing module — hence the D-02 track separation.
- **numpydoc docstrings, shallow, no Examples**; `interrogate ≥ 95` (currently 100%). Moved methods keep
  their docstrings; flat stubs use the one-line "Deprecated: use ``db.<accessor>.<method>`` instead." form.
- **Coverage ratchet `--cov-fail-under=94`** — every thin alias must be exercised by the DB-free alias
  tests, or the gate drops.
- **Generalized `self.`→`self._db.` rewrite on move** — methods, sibling-accessor calls, AND attributes
  (`self.config`), per D-04.

### Integration Points
- `Database`/`AsyncDatabase` `__init__` — add a single `_schema` cache field (mirror `_timescale`).
- `Database`/`AsyncDatabase` — add one lazy `@property def schema` block each (sync + async).
- The 27 flat schema method defs + the 2 flat spatial-index defs in `database.py`/`async_database.py` →
  replaced by `@deprecated_alias(...)` stubs (`"schema.<m>"` / `"spatial.<m>"`).
- `from_dataframe` / `from_geodataframe` (stay flat) — 8 internal call-sites rewritten to accessor paths
  (D-05).
- `tests/test_parity.py` `ACCESSOR_PAIRS` — append `(SchemaAccessor, AsyncSchemaAccessor)`.
- `pycopg/__init__.py` `__all__` — surface `SchemaAccessor`/`AsyncSchemaAccessor` (formal README/Sphinx is
  Phase 24).
- Existing test call-sites migrated to `db.schema.*` and `db.spatial.create_spatial_index`/
  `db.spatial.list_geometry_columns`.

</code_context>

<specifics>
## Specific Ideas

- **The spatial relocation is the one structurally-novel move of the whole milestone** — it edits an
  *existing* accessor + *existing* tests and changes the deprecated path's failure mode (PostGIS guard,
  D-06). Keep it a separate, clearly-scoped track (D-02) so it doesn't leak into the rote 27-method work.
- **The real correctness risk is the 8 stay-flat caller rewrites (D-05), not sibling calls.** Phase 22's
  hazard was intra-accessor sibling calls; the scan found **zero** of those among the 27 schema bodies.
  The Phase-23 analogue is `from_dataframe`/`from_geodataframe` calling moved methods from code that
  stays flat — a guaranteed `-W error` failure if missed. Already enumerated exhaustively (8 sites).
- **Validate against 27/29, not 26/28** (D-01) — guard against the ROADMAP/SCOPE "~26" wording becoming
  a phantom missing-method hunt.
- **Favour the simplest correct replication line-for-line with Phases 21/22.** Third application of a
  pattern built to be applied by rote; divergence (e.g. "improving" the 2 relocated methods into builder
  shape) is a smell — D-07 forbids it.

</specifics>

<deferred>
## Deferred Ideas

- **Public exports hardening / README / Sphinx / CHANGELOG / MIGRATION / version bump / PyPI publish** —
  **Phase 24** (REORG-05). This phase adds the `__init__.py` `__all__` entry for the 2 new schema classes
  as the pattern dictates; the formal doc/release work (including documenting the D-06 PostGIS-guard
  behavior refinement and the cosmetic "~26"→"27" ROADMAP/SCOPE fix) is Phase 24's.
- **Conforming the 2 relocated spatial methods to the pure-builder/`_run` house style** — intentionally
  NOT done (D-07: move, don't improve). Revisit only on the clean spatial v2 surface (v1.0.0) if ever.
- **Opportunistic `queries.py` builder extraction** for schema SQL — intentionally NOT done (D-07).
- **Carving `db.meta.*` out of `db.schema.*`** (DDL vs introspection split) — tranché at scoping: one
  single block this milestone; eventual carve reported to v0.9.0 on a clean surface if it earns its keep.
- **Alias removal** — v0.7.0.
- **New DDL/introspection/PostGIS power** (CRUD, enriched introspection, spatial v2) — not this milestone
  (moves existing surface only); v0.8.0+.

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 23-Schema Accessor & Spatial Relocation*
*Context gathered: 2026-06-17*
