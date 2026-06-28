# Phase 41: API Homogenization - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-28
**Phase:** 41-API Homogenization
**Areas discussed:** Deprecation timeline, Keyword-only contract, Consistency-pass scope, Exception alias mechanism

---

## Deprecation timeline

### Q1 — When does a deprecated name get removed?

| Option | Description | Selected |
|--------|-------------|----------|
| Remove in 2.0 (SemVer-pure) | Deprecated names introduced in 1.0 live through ALL of 1.x; removed only in next MAJOR | ✓ |
| Remove in a future 1.x minor | Faster cleanup, but removing a public name in a minor IS a SemVer break | |
| Keep indefinitely / soft-deprecate | Warn forever, never remove; aliases linger permanently | |

**User's choice:** Remove in 2.0 (SemVer-pure)
**Notes:** Matches the "frozen 1.0 under SemVer" promise — no breaking change in a 1.x minor.

### Q2 — Should docs/stability.md publish a concrete support matrix?

| Option | Description | Selected |
|--------|-------------|----------|
| Full support matrix | Python + PG/PostGIS (3.0 hard / 3.2 rec) + TimescaleDB ranges + stable/experimental API tier table | ✓ |
| Policy only | SemVer rules + deprecation timeline only; defer version matrices to README/pyproject | |
| You decide | Let Claude pick the altitude when writing | |

**User's choice:** Full support matrix
**Notes:** Strongest contract for a 1.0 freeze.

---

## Keyword-only contract

### Q1 — Enforce `*` in signatures or document-only?

| Option | Description | Selected |
|--------|-------------|----------|
| Enforce `*` on optional params | Required args positional; all optional/defaulted params become keyword-only | ✓ |
| Document-only contract | stability.md table only; signatures unchanged | |
| Enforce, but conservatively | Add `*` only on the clearest-misuse params; document the rest | |

**User's choice:** Enforce `*` on optional params
**Notes:** 1.0 is the only non-breaking window to add `*`.

### Q2 — How to ship the `*` enforcement?

| Option | Description | Selected |
|--------|-------------|----------|
| Clean break at 0.x→1.0 | Documented breaking change in MIGRATION + stability.md, no transitional shim | ✓ |
| Transitional positional shim | Accept positional for one cycle + warn; fragile *args detection on every signature | |

**User's choice:** Clean break at 0.x→1.0
**Notes:** A positional→kw-only change can't be deprecation-aliased cleanly; the deprecation-cycle rule applies to name renames, not the freeze boundary; keeps signatures clean for mypy-strict.

---

## Consistency-pass scope

### Q1 — How aggressive beyond the locked renames?

| Option | Description | Selected |
|--------|-------------|----------|
| Audit-then-decide | Full inventory across 7 accessors + flat core; findings table reviewed before fixes land | ✓ |
| Moderate (cheap wins only) | Fix clearly-divergent param names/order + trivial into= defaults; document the rest | |
| Minimal (locked scope only) | Only locked renames + `*` + documentation pass; no new renames | |

**User's choice:** Audit-then-decide
**Notes:** Matches "homogénéiser à fond" + the last non-breaking window; user reviews the inventory before fixes; per-finding disposition follows established rules.

---

## Exception alias mechanism

### Q1 — How should old exception names behave?

| Option | Description | Selected |
|--------|-------------|----------|
| Warn on import only | New *Error canonical; old name via `__getattr__` warns on import/access; same object so `except OldName` still catches | ✓ |
| Metaclass catch-warning | Custom metaclass to warn on `except`; fragile, risky to freeze | |
| Silent alias | old = new, no warning; -W error gate can't detect lingering usage | |

**User's choice:** Warn on import only
**Notes:** Relaxes ROADMAP success criterion #2 from "imported or caught" to "imported/accessed" — catch-time warning intentionally not implemented.

---

## Claude's Discretion

- Exact shim shape for `where=`→`filter=` (per-signature kwarg vs shared decorator over the 11×2 sites).
- Exact `docs/stability.md` layout and the precise version numbers in the support matrix.

## Deferred Ideas

None — discussion stayed within phase scope.
