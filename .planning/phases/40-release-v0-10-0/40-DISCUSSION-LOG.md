# Phase 40: Release v0.10.0 - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-26
**Phase:** 40-release-v0-10-0
**Areas discussed:** CHANGELOG structure, Benchmark numbers, User-facing docs scope, v1.0.0 signaling

---

## CHANGELOG structure

| Option | Description | Selected |
|--------|-------------|----------|
| Changed + Fixed (Keep a Changelog) | Strict KAC sections. Changed: COPY routing + ratchet 94→95. Fixed: flaky tests, ruff, TableNotFound, advisory warnings. Standard, tooling-friendly. | ✓ |
| Changed + Fixed + Performance | Adds a non-standard 'Performance' section to headline COPY gains separately. | |
| Narrative summary + sections | Lead with a prose summary then the sections. | |

**User's choice:** Changed + Fixed (Keep a Changelog)
**Notes:** COPY performance work folds into `### Changed`; no separate Performance section (not a KAC category). The absence of an `### Added` section is intentional for a no-new-API release.

---

## Benchmark numbers

| Option | Description | Selected |
|--------|-------------|----------|
| Qualitative + pointer to benchmarks/ | Describe the routing change, point to benchmarks/ for reproducible measurement. No hardcoded figures. | ✓ |
| Cite an order-of-magnitude range | Include a rough labeled figure (~10-20×). More compelling but drift-prone. | |
| Run benchmarks now, cite measured numbers | Execute the suite and quote actual speedups; bakes one machine's numbers into a permanent entry. | |

**User's choice:** Qualitative + pointer to benchmarks/
**Notes:** benchmarks/README.md numbers are illustrative; suite has no committed numbers and no timing assertion (Phase 39 D-03); results env-dependent. "Documented" = described + reproducible-on-demand, satisfies REL-10 without a frozen figure.

---

## User-facing docs scope

| Option | Description | Selected |
|--------|-------------|----------|
| Minimal: CHANGELOG + version strings only | No new API → README/RTD content already accurate; benchmarks/README documents perf. Least churn. | ✓ |
| Add a short performance note to README | Brief Performance line in README linking benchmarks/. | |
| Performance note in README + RTD page | README note plus a dedicated RTD page; most discoverable, more Sphinx -W surface. | |

**User's choice:** Minimal: CHANGELOG + version strings only
**Notes:** Version strings may still need bumping where they appear in README/conf.py — that's a version-source edit, not a content change.

---

## v1.0.0 signaling

| Option | Description | Selected |
|--------|-------------|----------|
| Stay silent — leave it for v1.0.0 | No deprecations, no API promises; freeze messaging belongs in v1.0.0 notes. | ✓ |
| One-line 'approaching 1.0' note in CHANGELOG | Forward-looking line noting spatial v2 + freeze. Soft commitment in a factual changelog. | |
| Audit for pre-freeze deprecations now | Mark anything to deprecate before the freeze. Net-new scope not in REL-10. | |

**User's choice:** Stay silent — leave it for v1.0.0
**Notes:** Keeps Phase 40 tightly scoped to REL-10; avoids pulling pre-freeze deprecation work into a release phase.

---

## Claude's Discretion

- Number/shape of plans (prior releases ran 2–3: prep → publish); human-gated OIDC publish kept as a terminal step.
- Exact bullet wording/granularity in the Changed/Fixed sections, drawn from Phase 37–39 artifacts.
- Whether to mention the Phase 38 `validate_identifiers` regression (internal-to-milestone churn; likely no Fixed line).
- Whether to re-run benchmarks locally as an author sanity check (does not feed CHANGELOG numbers).

## Deferred Ideas

- v1.0.0 freeze messaging + pre-freeze deprecation audit → v1.0.0 milestone (spatial v2 + API freeze).
- Citing measured benchmark numbers / a perf RTD page → future docs pass if a stable benchmark environment is established.
