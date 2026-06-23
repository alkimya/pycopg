# Phase 33: Release v0.8.0 - Context

**Gathered:** 2026-06-23
**Status:** Ready for planning

<domain>
## Phase Boundary

**Release-only phase.** All 11 v0.8.0 feature requirements (TS-ADV-01..10) are
already Complete + verified in Phases 30–32. The full 15-method `db.timescale.*`
surface (6 inherited from v0.6 + 9 new) ships in code with sync/async parity and
the coverage ratchet held at 95.11%.

Phase 33 delivers **REL-08 only**: docs (README + Sphinx + advanced section)
covering the 9 new methods, the `CHANGELOG [0.8.0]` Added entry, version bump in
both sources, the 4 quality gates, and the human-gated tag `v0.8.0` + OIDC publish
+ clean-venv install smoke.

**The 9 new methods being documented/released** (all on both `TimescaleAccessor`
and `AsyncTimescaleAccessor`):
- Chunk & dimension mgmt: `show_chunks`, `drop_chunks`, `add_dimension`, `add_reorder_policy`
- Continuous aggregate lifecycle: `create_continuous_aggregate`, `refresh_continuous_aggregate`, `add_continuous_aggregate_policy`
- Query helpers: `time_bucket`, `time_bucket_gapfill`

**No new feature code.** The only source change permitted is the version string in
`docs/conf.py` (and any docstring polish surfaced by the interrogate gate). Mirrors
the established release-phase shape (Phases 7/15/20/24/29).

</domain>

<decisions>
## Implementation Decisions

### Release mechanics (inherited from Phase 29 / v0.7.0 — LOCKED, do not re-litigate)
- **D-01:** Version bumped to `0.8.0` in BOTH sources — `pyproject.toml` (`version = "0.8.0"`, currently `0.7.0` at line 7) and `docs/conf.py` (`release = '0.8.0'`, currently `'0.7.0'` at line 17). These are the only two version sources.
- **D-02:** Four quality gates, run exactly as Phase 29 (see Gates section below). Produce a GATES.md record.
- **D-03:** Release is **human-gated**: final plan/wave is `autonomous: false`. Human creates tag `v0.8.0` + GitHub Release → triggers the existing OIDC `publish.yml` workflow (`release: published` event, NO API token). Then a clean-venv `pip install pycopg==0.8.0` import smoke against live PyPI. Produce a RELEASE-LOG.md.
- **D-04:** `uv lock --check` + `uv build` before tagging; commit all doc/version changes first.

### Docs structure (the real work of this phase)
- **D-05:** **Rewrite `docs/timescaledb.md` in place + add a new section.** The existing "Time Bucketing", "Gap Filling", and "Continuous Aggregates" sections currently show RAW SQL via `db.execute(...)` — rewrite them to use the new first-class methods (`db.timescale.time_bucket(...)`, `time_bucket_gapfill(...)`, `create_continuous_aggregate(...)` / `refresh_continuous_aggregate(...)` / `add_continuous_aggregate_policy(...)`). THEN add a new `## Advanced Chunk & Dimension Management` section covering `show_chunks` / `drop_chunks` / `add_dimension` / `add_reorder_policy`. Goal: no stale raw-SQL examples competing with the new API. This section satisfies REL-08's "docs/ time-series advanced section" requirement (a section within `timescaledb.md`, NOT a separate page).
- **D-06:** **Three docs surfaces must reflect the 9 new methods** (REL-08 says "README + Sphinx API docs cover the 9 new methods"):
  1. `docs/timescaledb.md` — narrative/examples (D-05).
  2. `docs/api-reference.md` — the **hand-written** "### TimescaleDB Methods" table (lines 184–193) currently lists only the 6 v0.6 methods → add 9 new rows (Method | Parameters | Returns).
  3. Sphinx autodoc (`docs/api-autodoc.md` `.. automodule:: pycopg.timescale`) auto-renders the 9 new methods from docstrings — **no manual listing needed there**, but the Sphinx `-W` build must pass clean over them (the interrogate gate already enforces docstrings exist).
- **D-07:** **README: update count + add compact examples.** Bump the accessor-table row `db.timescale.*` from "(6 methods)" to "(15 methods)" and update its example-name list. Add a compact block to the README TimescaleDB section showing 2–3 highlights (e.g. `time_bucket(..., into="df")`, `show_chunks`/`drop_chunks`, `create_continuous_aggregate`) + a pointer to the RTD advanced guide. Match the README's existing compact style — do NOT add full worked examples for all 9 (that lives in `docs/timescaledb.md`).

### CHANGELOG framing
- **D-08:** `CHANGELOG [0.8.0]` has **`### Added` ONLY — no `### Breaking`**. v0.8.0 is purely additive (the breaking alias removal was v0.7.0; nothing is removed this cycle). Date it on tag day. Replace `## [Unreleased]` placeholder appropriately.
- **D-09:** **Group the Added entry by feature family** (matches the milestone phase structure):
  - Chunk & dimension management (4): `show_chunks`, `drop_chunks`, `add_dimension`, `add_reorder_policy`
  - Continuous aggregate lifecycle (3): `create_continuous_aggregate`, `refresh_continuous_aggregate`, `add_continuous_aggregate_policy`
  - Query helpers (2): `time_bucket`, `time_bucket_gapfill`
- **D-10:** **Scope-fence grep** — the CHANGELOG (and docs) must NOT claim any deferred/out-of-scope capability. Ban keywords: `initial_watermark`, CDC / WAL, `drop_continuous_aggregate`, `remove_continuous_aggregate_policy`, `compress_chunk` / `decompress_chunk`, `origin` / `offset` alignment, `created_before` / `created_after`. (These are TSDB-F01..F04 + ETL-INC-F01..F05, explicitly out of this milestone.) A plan-time grep gate should enforce this, mirroring Phase 29's `### Added` scope fence.
- **D-11:** **No MIGRATION.md entry.** `MIGRATION.md` exists (v0.6→v0.7 + v0.5→v0.6 guides) but v0.8.0 has zero breaking changes — no new migration section needed. State this explicitly so the planner doesn't invent one.

### Gates (deltas from v0.7.0 baseline)
- **D-12:** **Keep all 4 gates unchanged** from Phase 29:
  1. `uv run pytest` — coverage ratchet ≥94 (wired via `--cov-fail-under=94` in addopts; measured 95.11% at Phase 32).
  2. `uv run interrogate` — docstring coverage ≥95 (already enforces the 9 new methods' docstrings exist).
  3. `uv run sphinx-build -W` — clean (warnings-as-errors; covers the rewritten + new doc sections).
  4. `uv run python -W error::DeprecationWarning -c "import pycopg"` — green. This is now a **no-op regression guard** (all alias stubs were removed in v0.7.0); it stays to prove nothing reintroduced a deprecation. NOT dropped.
- **D-13:** No new gate added. (Considered a "9-method-names-present-in-docs" grep but interrogate + Sphinx `-W` + the D-05/06/07 doc edits already cover REL-08's doc requirement; keep the gate set identical to v0.7.0 for a clean baseline comparison.)

### License nuance to surface in docs (not a gate)
- **D-14:** `time_bucket_gapfill` (and `locf`/`interpolate`) and the continuous-aggregate methods require a **Community/TSL-licensed** TimescaleDB build; on Apache-licensed builds they raise `FeatureNotSupported` (surfaced live in Phases 31–32 against local Apache 2.28). The advanced docs section SHOULD note this license requirement so users on Apache builds aren't surprised. This is documentation, not a behavioral change.

### Claude's Discretion
- Exact wording/prose of doc examples, the specific 2–3 README highlights chosen, and the GATES.md / RELEASE-LOG.md record format are the planner/executor's to decide within the decisions above.
- Whether docs work splits across 1 vs 2 plans (e.g. timescaledb.md rewrite vs api-reference.md + README) is a planning call; the milestone-standard shape is version+CHANGELOG → docs → gates → human-gated publish.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirement & milestone scope
- `.planning/REQUIREMENTS.md` — REL-08 is the single requirement for this phase (the precise deliverable list: README + Sphinx + advanced section + CHANGELOG + version + 4 gates + human-gated publish). The "Out of Scope" + "Future Requirements" tables define the D-10 scope-fence keywords.
- `.planning/ROADMAP.md` §"Phase 33" — one-line goal; §Phases 30–32 detail the 9 methods + their license/parity constraints.

### Release-phase analog (the template to mirror)
- Memory `phase29-planned` / `phase29-v070-shipped` (in `/home/loc/.claude/projects/-home-loc-workspace-pycopg/memory/`) — the v0.7.0 release phase: 3 plans / 3 sequential waves, version×2 + CHANGELOG + gates + human-gated OIDC publish + clean-venv smoke. Phase 33 mirrors this shape with v0.8.0's additive (no-Breaking) CHANGELOG.

### Files this phase edits (verified present)
- `pyproject.toml` line 7 — `version = "0.7.0"` → `0.8.0` (D-01).
- `docs/conf.py` line 17 — `release = '0.7.0'` → `'0.8.0'` (D-01; only source-tree code change).
- `CHANGELOG.md` — `## [Unreleased]` placeholder + `## [0.7.0]` precedent (Keep-a-Changelog format) (D-08/09/10).
- `docs/timescaledb.md` (405 lines) — raw-SQL sections to rewrite + new advanced section (D-05); license note (D-14).
- `docs/api-reference.md` lines 184–193 — hand-written "### TimescaleDB Methods" table to extend with 9 rows (D-06).
- `docs/api-autodoc.md` line 15 — `.. automodule:: pycopg.timescale` auto-renders new methods (D-06; no edit, but Sphinx `-W` must pass).
- `README.md` — accessor table row "(6 methods)" → "(15 methods)" + TimescaleDB section compact examples (D-07).
- `MIGRATION.md` — exists; **no edit** this phase (D-11).
- `.github/workflows/publish.yml` — existing OIDC trusted-publishing workflow triggered by `release: published` (D-03).
- `pycopg/timescale.py` — 15 public methods confirmed (`grep` count); source of truth for method signatures in the api-reference table.

### Known environment caveats
- Memory `pycopg-execute-phase-infra` / `pycopg-flaky-db-tests` — local main runs far ahead of origin/main → execute sequential-on-main (no worktrees), set `USE_WORKTREES_FOR_PLAN=false`. 2 named pre-existing flaky DB tests (`test_async_transaction_fix`, `test_create_spatial_index_name_parameter`) fail in isolation too; use `-o addopts=""` for targeted runs.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **Phase 29 release plan shape** — version-bump plan → gates plan → human-gated tag/OIDC/smoke plan. Directly reusable; only the CHANGELOG content (additive, grouped) and docs targets differ.
- **`.github/workflows/publish.yml`** — OIDC trusted publishing already wired and proven for v0.5.0/v0.6.0/v0.7.0; no token, fires on GitHub Release `published`.
- **Sphinx `automodule` autodoc** — `pycopg.timescale` already auto-documented; the 9 new methods' docstrings auto-surface, so the Sphinx API-doc half of REL-08 is largely free (gated by `-W`).

### Established Patterns
- **Two version sources, never more** — `pyproject.toml` + `docs/conf.py`. Confirmed by grep; CLAUDE.md's "Version" line is intentionally NOT a release-gated source (it's project-instruction prose, carried stale by design — see Deferred).
- **Keep-a-Changelog format** — `## [X.Y.Z] - DATE` with `### Breaking` / `### Added` subsections; v0.8.0 uses `### Added` only.
- **interrogate ≥95 + Sphinx `-W`** already enforce docstring presence/correctness for all public methods — the docs gate work is narrative/example coverage, not docstring authoring.

### Integration Points
- The rewritten `docs/timescaledb.md` examples become the canonical "how to use the new methods" reference linked from README (D-07 pointer) and reflected in the api-reference table (D-06).

</code_context>

<specifics>
## Specific Ideas

- The new advanced docs section is named **"Advanced Chunk & Dimension Management"** and lives inside `docs/timescaledb.md` (not a new page).
- README highlight examples should favor the highest-value new methods: `time_bucket(..., into="df")` (returns a DataFrame), `show_chunks` / `drop_chunks` (operational), and `create_continuous_aggregate` (lifecycle).
- CHANGELOG `### Added` groups exactly mirror the three milestone phase families (chunk/dimension, cagg lifecycle, query helpers).
- Document the Community/TSL license requirement for gapfill + caggs in the advanced section (D-14).

</specifics>

<deferred>
## Deferred Ideas

- **TSDB-F01..F04** (`drop_continuous_aggregate` / `remove_continuous_aggregate_policy`, `time_bucket` `origin`/`offset`, `compress_chunk`/`decompress_chunk`, `show_chunks` `created_before`/`created_after`) — out of v0.8.0 scope; CHANGELOG/docs must not claim them (D-10).
- **ETL-INC-F01..F05** (`initial_watermark`, configurable `>=` boundary, multi-column watermarks, advisory-lock concurrency, CDC/WAL) — deferred to a future ETL milestone; banned from v0.8.0 CHANGELOG (D-10).
- **`CLAUDE.md` "Version" line stale** (reads v0.5.0; actual will be v0.8.0) — cosmetic project-instruction lag, carried since v0.6.0; NOT a release-gated version source. Optional one-line fix, not required by REL-08.
- **Recurring STATE.md drift after `phase.complete`** — operational tooling issue (hand-fixed 6+ times); not a phase deliverable.
- **2 pre-existing flaky DB tests** — env/fixture-isolation bug, not v0.8.0 code; do not let them block the gates (use `-o addopts=""` for targeted runs).

### Reviewed Todos (not folded)
None — no pending todos matched this phase (STATE.md "Pending Todos: None").

</deferred>

---

*Phase: 33-Release v0.8.0*
*Context gathered: 2026-06-23*
