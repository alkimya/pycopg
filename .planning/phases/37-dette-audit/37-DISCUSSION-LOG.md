# Phase 37: Dette & Audit - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-25
**Phase:** 37-dette-audit
**Areas discussed:** N818 fix vs non-breaking, TableNotFound fork, Audit tooling + dead-code, Disposition policy + log

---

## N818 fix vs non-breaking (DEBT-02)

Context surfaced before asking: `uv run ruff check pycopg tests` reports **35 errors** across 4 rule codes (not 4 errors). They split cleanly — `pycopg/`: 4× N818 only (public exceptions lacking `Error` suffix); `tests/`: F841×21, W291×5, E722×5 (all trivial mechanical fixes). Renaming the exceptions breaks the public API (forbidden this milestone).

| Option | Description | Selected |
|--------|-------------|----------|
| Per-file ruff ignore | `[tool.ruff.lint.per-file-ignores]` `"pycopg/exceptions.py" = ["N818"]` + comment; centralized, documented, N818 stays enforced elsewhere | ✓ |
| Per-line `# noqa: N818` | One suppression comment per class line; 4 scattered comments | |
| Rename + deprecation aliases | Rename to `*Error`, keep old names as aliases; heavyweight, adds churn, against debt-phase spirit | |

**User's choice:** Per-file ruff ignore (Recommended)
**Notes:** Test errors (F841/W291/E722) are fixed mechanically, not suppressed.

---

## TableNotFound fork (DEBT-05)

| Option | Description | Selected |
|--------|-------------|----------|
| Add a real raise site | schema introspection raises `TableNotFound` on missing table; additive, keeps export, makes it honest | ✓ |
| Remove from `__all__` | Drop the export; itself a public-surface change (breaks existing imports), discards a useful exception | |
| You decide | Pick whichever fits cleanest after checking current missing-table behavior | |

**User's choice:** Add a real raise site (Recommended)
**Notes:** Researcher pins the exact site (candidate `table_info`/`describe`) and must confirm current missing-table behavior isn't a documented contract before raising.

---

## Audit tooling + dead-code (AUDIT-01/02, DEBT-01)

| Option | Description | Selected |
|--------|-------------|----------|
| vulture + pytest-randomly | vulture for dead-code (+ allowlist); pytest-randomly to randomize CI order and prove DEBT-01 determinism | ✓ |
| vulture only | dead-code tool; fix flaky by fixtures, verify determinism manually | |
| Coverage-only, no new dev deps | dead code via coverage; verify flaky by repeated runs; leanest, weaker guard | |

**User's choice:** vulture + pytest-randomly (Recommended)
**Notes:** Both go in `[dependency-groups] dev` (no runtime deps). `/gsd-code-review` handles the AUDIT-01 report regardless. Randomization may surface other latent isolation bugs — in-scope discovery, but a large new unrelated bug is logged for disposition.

---

## Disposition policy + log (AUDIT-01 / DEBT-03 / NYQ-01)

### Disposition bar

| Option | Description | Selected |
|--------|-------------|----------|
| HIGH in-phase; MEDIUM fix-or-defer w/ justification; LOW logged | Bounded debt phase; risky behavioral fixes may defer to v1.0.0 | ✓ |
| Fix all HIGH + MEDIUM in-phase | Only LOW defers; larger/less predictable scope | |
| Fix everything (HIGH/MEDIUM/LOW) | Maximal cleanliness; highest scope-creep risk | |

**User's choice:** HIGH in-phase; MEDIUM fix-or-defer w/ justification (Recommended)

### DEBT-03 fix-vs-close split

| Option | Description | Selected |
|--------|-------------|----------|
| Fix cheap/cosmetic; close behavioral w/ justification | Fix guard case-insensitivity, test assertion, docstring, dedup; close WR-03 / %-structural / IN-03 | ✓ |
| Fix all advisory including behavioral | Also change INTERVAL handling, %-structural path, chunk_seq now; regression risk | |
| Close all with justification, fix none | Document only; leaves trivial wins on the table | |

**User's choice:** Fix cheap/cosmetic; close behavioral w/ justification (Recommended)

### NYQ-01 sign-off approach

| Option | Description | Selected |
|--------|-------------|----------|
| Formal sign-off citing VERIFICATION.md + spot-check | Flip 22-24 to PASSED referencing existing evidence; low effort, honest | ✓ |
| Re-run gsd-validate-phase / nyquist-auditor | Regenerate evidence per phase; more rigorous, more effort | |
| Close with justification (no re-validation) | Document waiver; doesn't satisfy PASSED spirit | |

**User's choice:** Formal sign-off citing VERIFICATION.md + spot-check (Recommended)
**Notes:** Discovery during context-gathering: the 22-24 VALIDATION.md/VERIFICATION.md files **no longer exist on disk** (v0.6.0 phase dirs weren't archived with per-phase artifacts). Surviving evidence is `v0.6.0-MILESTONE-AUDIT.md`. The chosen approach adapts: sign off against that audit's req-coverage evidence rather than editing non-existent draft files.

### Decision-log location

| Option | Description | Selected |
|--------|-------------|----------|
| One `37-DECISIONS.md` in the phase dir | Consolidated justification log + roll-up into STATE.md; co-located, verifier-friendly | ✓ |
| Append to STATE.md + PROJECT.md only | No new file; mixes phase rationale into milestone docs | |
| Per-area decision files | Granular; more files to track | |

**User's choice:** One 37-DECISIONS.md in the phase dir (Recommended)

---

## Claude's Discretion

- Exact internal raise site for `TableNotFound` (researcher/planner; lean `table_info`/`describe`).
- Exact form of the vulture allowlist (whitelist `.py` file vs config).

## Deferred Ideas

- Rename exceptions to `*Error` suffix — reconsider at v1.0.0 API freeze under deprecation policy.
- Behavioral hardening WR-03 / %-in-structural-SQL / IN-03 `chunk_seq` — deferred to v1.0.0 (logged in 37-DECISIONS.md).
- COV-01 (95% ratchet) → Phase 39; PERF-01..05 → Phases 38–39; REL-10 → Phase 40.
- Any new large isolation bug surfaced by pytest-randomly beyond the 3 known → log for disposition, don't expand Phase 37.
