---
phase: 47-release-v1-0-0
type: context
source: inline mini-discuss (2026-07-02, post Phase 46 execution)
status: ready-to-plan
requirements: [REL-11]
---

# Phase 47 — Release v1.0.0: Context & Locked Decisions

Captured from an inline settlement session on 2026-07-02 (user chose to settle release-specific
decisions instead of a full `/gsd-discuss-phase 47`). Feeds `/gsd-plan-phase 47`.

## Phase shape (from ROADMAP REL-11)

Release phase — well-established repeatable shape (5 prior releases: v0.4/0.7/0.8/0.9/0.10):
version bump (all sources) → CHANGELOG `[1.0.0]` → MIGRATION final → 5 gates green → tag `v1.0.0`
+ human-gated OIDC PyPI publish → clean-venv smoke. **This is the FINAL phase of the last big milestone.**

**Entry state (verified at Phase 46 close, 2026-07-02):**
- Current version: `0.10.1` (pyproject.toml). Bump target: **1.0.0**.
- `## [Unreleased]` in CHANGELOG.md is **EMPTY** — the entire v1.0.0 milestone (Phases 41–46) is UNRECORDED.
- `uv run mypy pycopg/` → Success 0 errors/18 files (mypy-strict is now a BLOCKING CI gate — new 5th gate).
- Full suite 1736 passed @ 96.42% on `PGDATABASE=pycopg_test3` (NOT pycopg_test/pycopg_test2 — both broken; see project memory).

## Locked decisions (3)

### D-47-01 — CHANGELOG `[1.0.0]`: compose in this phase from the 6 per-phase SUMMARYs + PROJECT.md Validated
The `[Unreleased]` section is empty, so the whole milestone must be assembled. Structure:
- **Added** — Spatial v2: 12 methods (`db.spatial.*` 13→25) = processing 6 (union/difference/intersection/simplify/convex_hull/make_valid) + aggregates 3 (collect_geometries/union_aggregate/extent) + serialization 3 (as_geojson/as_text/as_mvt); TXN-01/02 (transaction isolation_level + savepoints); PARAM-01 (`%(name)s` dict params via `Params` widening); HEALTH-01 (`health()` ×4 classes); LOG-01 (`pycopg/logging.py` structured logging); complete `py.typed`.
- **Changed / Breaking** — spatial `where=`→`filter=`; 4 exceptions renamed to `*Error`; kw-only `*` enforcement (FREEZE-03); timescale `where=`→`filter=`; mypy-strict now blocking in CI.
- **Deprecated** — `where=`/`filter=` shims + the 4 exception aliases (removal scheduled 2.0).
- ⚠ **D-36-03 signature-drift guard**: use CODE-EXACT signatures — past releases drew CHANGELOG signature-drift warnings at code-review. Cross-check every signature against source.

### D-47-02 — MIGRATION guide: final-review pass only (already ~complete)
`MIGRATION.md` already has `# Migration Guide: v0.10.x → 1.0.0` covering all 4 breaking changes
(FREEZE-01 spatial where→filter, FREEZE-02 exception renames, FREEZE-03 kw-only, D3 timescale
where→filter) + Upgrade Checklist + Getting Help, built incrementally in Phases 41–45. Phase 47 only
needs to CONFIRM accuracy and optionally add a short note for consumers who type-check (mypy-strict/
py.typed now shipped). NOT a from-scratch build.

### D-47-03 — Debt triage: **DOCS/CORRECTNESS ONLY** in the 1.0 freeze window
Fix in 1.0 (docs/docstrings only — zero runtime risk, re-verify Sphinx `-W` + interrogate after):
- **22× `InvalidIdentifierErrorError`** double-suffix typos (all in `pycopg/spatial.py` docstring `Raises:` sections, P41 rename artifact) → `InvalidIdentifierError`. A non-existent class name must not be frozen into 1.0 docs.
- **`docs/api-reference.md` `where=`→`filter=`** for spatial helpers (~15 `where=` occurrences to AUDIT — spatial helpers should show `filter=`; the CRUD dict-equality `where=` is CORRECT and must be LEFT alone). Careful audit, not blind replace.
- **`as_text(max_decimal_digits=)` two-arg form** needs PostGIS 3.1 but docs state a 3.0 floor (P44 WR-01) → correct the support-matrix note (part of the frozen 1.0 contract).

Defer to 1.x (additive / non-blocking):
- IN-01 alias-import double-warning quirk (pre-existing, P46 review).
- Missing live `into="gdf"` integration tests for collect/union + all-NULL `extent(into="gdf")` (P43 WR) — coverage gap, not a bug; ratchet already ≥95%.

Handled elsewhere:
- WR-05 backup stderr disclosure (P45) → let `/gsd-secure-phase 45` dispose it.

## Pre-plan prerequisites (user-driven, before `/gsd-plan-phase 47`)
- `/gsd-secure-phase 46` and `/gsd-secure-phase 45` — both phases lack `*-SECURITY.md`; close the security gate BEFORE tagging 1.0 (cleaner than discovering it at release). P46 threats (T-46-SC/13/14) already substantively mitigated in-phase; P45 has the open WR-05.

## Gates for this phase (5 — mypy-strict is NEW)
1. coverage ≥95% (`PGDATABASE=pycopg_test3 uv run pytest`)
2. interrogate 100%
3. Sphinx `-W` clean
4. `-W error::DeprecationWarning` green
5. **`uv run mypy pycopg/` exit 0 (NEW — now blocking)**

## Notes
- Version bump touches 3 sources (D-36-01): `pyproject.toml` (canonical) + `uv.lock` + `docs/conf.py`; `__init__.py` stays dynamic via `importlib.metadata.version` (never hardcode).
- Publish is human-gated OIDC (`publish.yml` on `release: published`); tag `v1.0.0` + GitHub Release triggers it; then clean-venv smoke (`__version__ == "1.0.0"` + import a few 1.0 symbols).
- Sequential-on-main (established pycopg pattern; release phases are single/low-plan anyway).
