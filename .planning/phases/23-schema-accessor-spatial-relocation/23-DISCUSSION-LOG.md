# Phase 23: Schema Accessor & Spatial Relocation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-17
**Phase:** 23-Schema Accessor & Spatial Relocation
**Areas discussed:** Decomposition (schema vs spatial reloc), self.<attr> rewrite rule, stay-flat internal callers, PostGIS guard on relocated methods

---

## Decomposition — schema track vs spatial relocation

| Option | Description | Selected |
|--------|-------------|----------|
| Schema separate from spatial reloc | Treat schema-accessor creation (new module, mirroring Phase 22 3-wave) and the 2-method spatial relocation (edits existing `spatial.py` + existing tests) as cleanly-separated tracks. Lowest blast-radius; the odd-one-out reloc doesn't contaminate rote schema work. | ✓ |
| Fold spatial reloc into schema waves | One set of waves; spatial reloc rides along inside the same W1/W2/W3. Fewer plans, but mixes two different edit patterns per wave. | |

**User's choice:** Schema separate from spatial relocation.
**Notes:** Captured as D-02/D-03. The spatial reloc is the one structurally-novel move (edits an existing accessor + tests, changes the deprecated path's failure mode). Keeping it a distinct track keeps each plan's edit-pattern uniform. Shared edit of `from_dataframe`/`from_geodataframe` must be owned atomically by whichever plan touches those lines.

---

## Self-reference rewrite rule for the raw-psycopg database methods

| Option | Description | Selected |
|--------|-------------|----------|
| Generalize rewrite to any self.<attr> | Lock the rewrite rule to cover ALL `self.` references (methods AND attributes like `self.config`/`self.engine`), not just `self.execute`. Researcher enumerates + classifies every `self.X` in all 27 bodies. | ✓ |
| Move verbatim, fix only what breaks | Move bodies, run the suite, fix the AttributeErrors that surface. Relies on test coverage to catch the 3 raw-psycopg methods. | |

**User's choice:** Generalize the rewrite to any `self.<attr>`.
**Notes:** Captured as D-04. Driver: `create_database`/`drop_database`/`database_exists` call `self.config.with_database("postgres")` + raw `psycopg.connect(...)` — `self.config` → `self._db.config`. Scan found ZERO sibling-schema self-calls (Phase 22's hazard does not materialize), but the researcher must still re-verify exhaustively.

---

## Stay-flat internal callers (`from_dataframe` / `from_geodataframe`)

| Option | Description | Selected |
|--------|-------------|----------|
| Rewrite to accessor paths | Rewrite the 8 call-sites (4 sync + 4 async) to `self.schema.*` / `self.spatial.*`. Lock as an explicit must-do — guaranteed `-W error` failure if missed. | ✓ |
| Let researcher discover | Note the risk generally; let the researcher's self-call scan find them. | |

**User's choice:** Rewrite to accessor paths (locked as explicit must-do).
**Notes:** Captured as D-05. This is the Phase-23-only failure mode (no stay-flat caller of a moved method existed in 21/22). Exhaustively enumerated: `from_dataframe` (sync :1503, async :1479) and `from_geodataframe` (sync :1583/1619/1622, async :1568/1607/1610). `from_geodataframe` already guards `has_extension("postgis")` itself, so routing through the PostGIS-guarded `db.spatial` accessor is safe.

---

## PostGIS guard inherited by the relocated spatial methods

| Option | Description | Selected |
|--------|-------------|----------|
| Accept the guard (cleaner failure) | Relocated methods + their deprecated aliases now raise `ExtensionNotAvailable` early via the SpatialAccessor constructor guard, instead of a raw psycopg error. Strictly clearer + thematically correct. Note in CHANGELOG/MIGRATION. Zero extra code. | ✓ |
| Preserve old no-guard behavior | Bypass the constructor guard for these 2 to keep byte-for-byte identical behavior during the deprecation cycle. More code, defeats the thematic point. | |

**User's choice:** Accept the guard (cleaner failure).
**Notes:** Captured as D-06. The old flat `db.create_spatial_index`/`db.list_geometry_columns` had no PostGIS guard. After relocation the deprecated alias path delegates through `db.spatial`, triggering the constructor guard at `spatial.py:1047`. Documented as a minor behavior refinement on the deprecated path; CHANGELOG/MIGRATION note is Phase 24's.

---

## Claude's Discretion

- Exact per-track plan boundaries / number of plans (the schema-vs-spatial separation is locked; the precise cut is the planner's).
- `test_schema_aliases.py` as one parametrized module or split.
- Whether the 2 spatial alias tests get a new `test_spatial_aliases.py` or extend the existing spatial test module.
- `from __future__ import annotations` + `TYPE_CHECKING` guards in `schema.py` (follow precedent modules).
- Ordering of waves' internal work and of the two tracks (independent except the shared DataFrame-method edit).

## Deferred Ideas

- SQL treatment locked verbatim (D-07): do NOT conform the 2 relocated methods to the pure-builder/`_run` house style; do NOT extract new `queries.py` builders. Revisit only on spatial v2 (v1.0.0).
- Public exports / README / Sphinx / CHANGELOG / MIGRATION / version bump / PyPI publish → Phase 24 (REORG-05), including the D-06 behavior-refinement note and the cosmetic "~26"→"27" ROADMAP/SCOPE fix.
- Carving `db.meta.*` out of `db.schema.*` → v0.9.0 on a clean surface if it earns its keep.
- Alias removal → v0.7.0.
- New DDL/introspection/PostGIS power → v0.8.0+ (this milestone moves existing surface only).
