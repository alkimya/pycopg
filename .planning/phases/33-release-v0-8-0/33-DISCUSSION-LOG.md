# Phase 33: Release v0.8.0 - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-23
**Phase:** 33-Release v0.8.0
**Areas discussed:** Area selection, Docs structure, README depth, CHANGELOG framing, Gate deltas

---

## Area Selection (which gray areas to discuss)

| Option | Description | Selected |
|--------|-------------|----------|
| Docs placement & scope | 9 new methods undocumented; extend timescaledb.md vs new page; README depth | ✓ |
| CHANGELOG framing | Added-only (no Breaking); grouping; deferred-keyword scope fence | ✓ |
| Gate deltas from v0.7.0 | Whether any of the 4 gates change for v0.8.0 | ✓ |
| Inherit Phase 29 as-is | Record that mechanics mirror Phase 29 exactly, no per-area discussion | ✓ |

**User's choice:** All four (multiSelect). Interpreted as: inherit the Phase 29 release mechanics unchanged, AND refine the three open areas (docs, CHANGELOG, gates) on top of that baseline.
**Notes:** Release-only phase; all 11 feature reqs (TS-ADV-01..10) shipped + verified in Phases 30–32. REL-08 is the only requirement.

---

## Docs structure

| Option | Description | Selected |
|--------|-------------|----------|
| Rewrite in place + new section | Update existing raw-SQL sections (Time Bucketing / Gap Filling / Continuous Aggregates) to use new methods, AND add new "Advanced Chunk & Dimension Management" section | ✓ |
| New dedicated page | Add separate docs/timescaledb-advanced.md; leave old raw-SQL examples in place | |
| Append-only section | Add one "Advanced (v0.8.0)" section at bottom; don't touch existing examples | |

**User's choice:** Rewrite in place + new section.
**Notes:** Key finding driving the question — docs/timescaledb.md already shows Time Bucketing / Gap Filling / Continuous Aggregates as RAW SQL via db.execute(), which the 9 new typed methods now replace. Rewriting avoids two competing ways to do the same thing. The "Advanced Chunk & Dimension Management" section satisfies REL-08's "docs/ time-series advanced section" as a section within timescaledb.md, not a new page.

---

## README depth

| Option | Description | Selected |
|--------|-------------|----------|
| Update count + compact examples | Bump "(6 methods)" → "(15 methods)", add 2–3 highlight examples + RTD pointer | ✓ |
| Count bump + pointer only | Just fix the count + one-line pointer; no examples in README | |
| Full examples in README | Full worked examples for all 9 methods in README | |

**User's choice:** Update count + compact examples.
**Notes:** Matches README's existing compact style; full examples stay in docs/timescaledb.md. README's db.timescale.* accessor-table row currently reads "(6 methods)".

---

## CHANGELOG framing

| Option | Description | Selected |
|--------|-------------|----------|
| Added-only, grouped, fenced | ### Added ONLY (no Breaking); grouped by 3 feature families; grep-ban deferred keywords | ✓ |
| Added-only, flat list | Single flat bullet list of 9 methods, no sub-grouping | |
| Add a Notes/compat subsection | Added (grouped) + a TSDB-2.x / Community-license note | |

**User's choice:** Added-only, grouped, fenced.
**Notes:** v0.8.0 is purely additive (alias removal was v0.7.0). Scope-fence grep bans TSDB-F01..F04 + ETL-INC-F01..F05 keywords (initial_watermark, CDC, drop_continuous_aggregate, compress_chunk, origin/offset, created_before). The Community/TSL license nuance still gets documented — placed in the advanced docs section (D-14) rather than the CHANGELOG.

---

## Gate deltas from v0.7.0

| Option | Description | Selected |
|--------|-------------|----------|
| Keep all 4 unchanged | cov ≥94 / interrogate ≥95 / Sphinx -W / -W error::DeprecationWarning (now a no-op regression guard) | ✓ |
| Drop the DeprecationWarning gate | Remove it since no deprecated stubs remain after v0.7.0 | |
| Add a 'new-method docs present' gate | Keep 4 + grep that all 9 method names appear in docs/README | |

**User's choice:** Keep all 4 unchanged.
**Notes:** The -W error::DeprecationWarning gate stays as a green regression guard (proves nothing reintroduced a deprecation). interrogate ≥95 + Sphinx -W already enforce the 9 new docstrings exist and render clean — no extra docs-grep gate needed; keeps the gate set identical to v0.7.0 for clean baseline comparison.

---

## Claude's Discretion

- Exact prose/wording of doc examples; the specific 2–3 README highlights chosen.
- GATES.md / RELEASE-LOG.md record format.
- Whether docs work splits across 1 vs 2 plans (planning call).

## Deferred Ideas

- TSDB-F01..F04 and ETL-INC-F01..F05 — out of v0.8.0 scope; banned from CHANGELOG/docs (D-10).
- CLAUDE.md "Version" line stale (reads v0.5.0) — cosmetic, not a release-gated source; optional one-line fix.
- Recurring STATE.md drift after phase.complete — tooling issue, not a deliverable.
- 2 pre-existing flaky DB tests — env-only; must not block gates.
