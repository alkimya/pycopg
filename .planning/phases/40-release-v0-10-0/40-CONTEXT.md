# Phase 40: Release v0.10.0 - Context

**Gathered:** 2026-06-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Ship **v0.10.0 "Durcissement & Performance"** to PyPI. This is the 7th release
phase in the project (v0.4.0 → v0.9.0 all shipped via the same flow) and the
release *mechanics* are fixed by precedent + REL-10:

- Bump the version in **three** canonical sources: `pyproject.toml`, `uv.lock`,
  `docs/conf.py` (`__version__` stays dynamic via `importlib.metadata`).
- Write the `[0.10.0]` CHANGELOG entry.
- Get the **4 gates** green: coverage ≥95% (ratchet now 95, measured 96.32%),
  interrogate 100%, Sphinx `-W` clean, `-W error::DeprecationWarning` green.
- Tag `v0.10.0`, publish wheel + sdist to PyPI via **OIDC trusted publishing**
  (human-gated, as every prior release), then run a **clean-venv smoke**
  confirming `__version__ == "0.10.0"`.

**What makes this release different — and the reason this discussion exists:**
v0.10.0 is the **first release with no new public API**. Every prior CHANGELOG
was an `### Added` list of methods. v0.10.0 ships internal hardening (debt,
audit), COPY-routed performance, and a 95% coverage ratchet — so the content
choices (CHANGELOG shape, how perf is documented, docs scope) are genuinely new.

**Non-breaking release → no MIGRATION guide** (unlike v0.7.0).

</domain>

<decisions>
## Implementation Decisions

### CHANGELOG structure (D-01)
- **D-01:** Use **strict Keep a Changelog** sections for `[0.10.0]` — `### Changed`
  + `### Fixed` only. **No** non-standard `Performance` section. The COPY
  performance work folds into `### Changed`.
  - `### Changed`: COPY routing for `from_dataframe` / ETL load (`append`/`replace`)
    / `insert_batch` placeholder hoist (all behavior-preserving, sync + async);
    coverage ratchet raised 94→95.
  - `### Fixed`: the 5 real BLOCKERs + debt cleared in Phase 37 — flaky tests
    (fixture isolation), ruff N818/W291/F841/E722, `TableNotFound` raise site in
    `truncate_table`, advisory warnings closed/justified.
  - The `validate_identifiers` regression caught and fixed in Phase 38's
    code-review gate (commit 863e894) is internal-to-this-milestone churn — it
    does **not** need its own Fixed line (the COPY rewrite that introduced it
    never shipped). Planner discretion on whether to mention.

### Benchmark / COPY-gains documentation (D-02)
- **D-02:** Document the COPY gains **qualitatively** in the CHANGELOG and point
  to `benchmarks/` for reproducible measurement. **No hardcoded speedup figures.**
  - Rationale: the `benchmarks/README.md` table is an *illustrative sample*, the
    suite has **no committed measured numbers** and **no timing assertion**
    (Phase 39 D-03), and results are env-dependent (need a live Postgres). A
    figure baked into a permanent changelog line can't be reproduced exactly and
    will drift.
  - This satisfies REL-10's "gains COPY documentés" — "documented" = described +
    reproducible-on-demand, not a frozen number.

### User-facing docs scope (D-03)
- **D-03:** **Minimal docs touch** — CHANGELOG + the three version strings only.
  No README / RTD *content* changes.
  - Rationale: no new methods → README "X methods" counts and api-reference rows
    are already accurate. `benchmarks/README.md` (shipped Phase 39) already
    documents the performance story. Least churn, lowest Sphinx `-W` risk.
  - Note for planner: README and `docs/conf.py` may still need the **version
    string** bumped where one appears — that's a version-source edit (D under
    domain), not a content change.

### v1.0.0 signaling (D-04)
- **D-04:** **Stay silent** about the upcoming v1.0.0 (spatial v2 + API freeze).
  v0.10.0 ships **no deprecations** and makes **no forward-looking commitments**
  in the CHANGELOG. Freeze messaging belongs in the v1.0.0 release notes.
  - This keeps Phase 40 tightly scoped to REL-10 and avoids net-new
    pre-freeze-deprecation scope (which is not in this milestone).

### Claude's Discretion
- Number/shape of plans (prior releases ran 2–3 plans: prep → publish). Planner
  decides; the human-gated OIDC publish should be its own terminal step.
- Exact wording/bullet granularity inside the Changed/Fixed sections, drawn from
  the Phase 37–39 artifacts (see canonical refs).
- Whether to re-run `benchmarks/` locally during release for the author's own
  sanity check (does **not** feed numbers into the CHANGELOG per D-02).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirement & roadmap (what to ship)
- `.planning/REQUIREMENTS.md` — **REL-10** is the single requirement for this
  phase; line ~43 has the exact deliverable (3 version sources, CHANGELOG,
  4 gates, tag, OIDC, smoke).
- `.planning/ROADMAP.md` § "Phase 40: Release v0.10.0" — goal + 4 success criteria.

### Release surfaces to edit
- `pyproject.toml` — version source (currently `version = "0.9.0"`, line 7) → `0.10.0`.
- `uv.lock` — version source (pycopg entry `version = "0.9.0"`, ~line 698) → `0.10.0`
  (**new third source vs prior releases**, per REL-10; regenerate via `uv lock`).
- `docs/conf.py` — version source (`release = '0.9.0'`, line 17) → `0.10.0`.
- `CHANGELOG.md` — extend with `[0.10.0]` under `[Unreleased]`; follow the
  existing Keep a Changelog format (see `[0.9.0]`/`[0.8.0]` entries for style).

### Milestone content sources (what to write into the CHANGELOG)
- `.planning/phases/37-dette-audit/37-DECISIONS.md` — debt/audit dispositions
  (the 5 BLOCKERs, ruff fixes, TableNotFound, advisory-warning closures) → Fixed.
- `.planning/phases/38-performance-copy/` — COPY routing (from_dataframe Hybrid
  DDL+COPY, ETL load seam, insert_batch hoist) → Changed.
- `.planning/phases/39-couverture-benchmarks/` — coverage 94→95 ratchet + the
  `benchmarks/` suite → Changed + the qualitative perf note.
- `benchmarks/README.md` — the doc the CHANGELOG points to for reproducible
  COPY measurement (D-02). Sample numbers there are illustrative only.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **The established release flow** — 6 prior release phases (Phase 36 = v0.9.0 is
  the most recent template) executed: version bump → CHANGELOG → 4 gates → tag →
  human-gated OIDC publish → clean-venv smoke. Reuse verbatim.
- **OIDC trusted-publishing GitHub workflow** already exists and has succeeded
  6×; no new CI authoring needed.
- **`__version__` is dynamic** via `importlib.metadata` — no source edit needed
  beyond the version strings; the clean-venv smoke reads it post-install.

### Established Patterns
- **4-gate green-before-ship** is wired in CI (coverage `--cov-fail-under=95`
  set in Phase 39, interrogate ≥95/100% measured, Sphinx `-W`, `-W error::DeprecationWarning`).
- **CHANGELOG = Keep a Changelog + SemVer**, declared at the top of `CHANGELOG.md`;
  `[Unreleased]` section sits above the newest dated entry.
- **Human-gated publish**: the actual PyPI push is a deliberate manual approval
  step every release — keep it terminal and explicit in the plan.

### Integration Points
- Version strings flow into the installed package metadata → the smoke test's
  `__version__ == "0.10.0"` assertion is the end-to-end check that all three
  sources agree.

</code_context>

<specifics>
## Specific Ideas

- CHANGELOG entry should read as a coherent "hardening + performance, no API
  changes" release — the absence of an `### Added` section is intentional and
  correct, not an omission.
- "Documented COPY gains" = prose + a pointer to `benchmarks/`, deliberately
  number-free (D-02).

</specifics>

<deferred>
## Deferred Ideas

- **v1.0.0 freeze messaging + pre-freeze deprecation audit** — surfaced under the
  v1.0.0-signaling area; decided OUT of v0.10.0 (D-04). Belongs to the v1.0.0
  milestone (spatial v2 + API freeze), where deprecations and freeze notes are
  in scope.
- **Citing measured benchmark numbers / a perf RTD page** — considered under the
  benchmark-numbers and docs-scope areas; deferred. If a stable benchmark
  environment is ever set up, a future docs pass could publish reproducible
  figures. Not for v0.10.0.

None lost — discussion otherwise stayed within phase scope.

</deferred>

---

*Phase: 40-release-v0-10-0*
*Context gathered: 2026-06-26*
