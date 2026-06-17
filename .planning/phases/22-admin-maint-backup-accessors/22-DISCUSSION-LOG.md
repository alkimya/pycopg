# Phase 22: Admin, Maint & Backup Accessors - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-17
**Phase:** 22-Admin, Maint & Backup Accessors
**Areas discussed:** Admin method count, Intra-accessor cross-calls, Phase/plan decomposition, Verbatim vs queries.py builders

---

## Admin method count

| Option | Description | Selected |
|--------|-------------|----------|
| Lock 11/21, note the typo | CONTEXT.md records 11 admin methods, 21 total. Flag the ROADMAP "12 methods / 22 names" as a stale off-by-one so the verifier checks against 21. | ✓ |
| Re-verify against source first | Double-check there isn't a 12th admin method missed before locking. | |

**User's choice:** Lock 11/21, note the typo
**Notes:** Live source (`pycopg/database.py`) and `REQUIREMENTS.md` ADM-01 both enumerate exactly 11 admin methods. The ROADMAP "12 + 6 + 4 / 22 names" goal text is a stale off-by-one. Captured as D-01; verifier validates against 21.

---

## Intra-accessor cross-calls

| Option | Description | Selected |
|--------|-------------|----------|
| Sibling via self._db.admin.X | Rewrite intra-accessor calls (`role_exists`, `grant_role` inside `create_role`) to call the accessor method directly. Avoids internal DeprecationWarnings. | ✓ |
| Keep self._db.X (flat) | Let moved bodies call the deprecated flat alias — simplest rewrite but triggers internal DeprecationWarnings, breaking the -W error gate. | |

**User's choice:** Sibling via self._db.admin.X
**Notes:** This is the one substantive departure from the timescale phase (timescale had no intra-family cross-calls). `create_role` calls `self.role_exists(...)` and `self.grant_role(...)`. Captured as D-02/D-03 with a general rewrite rule: sibling-accessor calls → `self._db.<accessor>.X`; core-flat calls → `self._db.X`. Researcher must scan all 21 bodies (sync + async) for self-calls.

---

## Phase/plan decomposition

| Option | Description | Selected |
|--------|-------------|----------|
| 3 waves like Phase 21 | W1 modules; W2 lazy properties + stubs + exports; W3 alias tests + ACCESSOR_PAIRS + call-site migration + gates. Mirrors Phase 21 exactly. | ✓ |
| One plan per accessor | 3 plans, each end-to-end for one accessor — more parallelizable but repeats shared touch-points (3-way merge friction). | |
| You decide / let planner choose | Leave decomposition to the planner. | |

**User's choice:** 3 waves like Phase 21
**Notes:** Captured as D-04/D-05. Shared touch-points (`__init__.py`, `ACCESSOR_PAIRS`, `__init__` cache fields/properties) concentrated in single waves to avoid 3-way merge friction; the 3 accessors parallelize within each wave.

---

## Verbatim vs queries.py builders

| Option | Description | Selected |
|--------|-------------|----------|
| Verbatim, constants travel | Move bodies verbatim (D-06 precedent); existing queries.py constant references travel unchanged; extract no new builders. | ✓ |
| Opportunistic extraction | Extract inline SQL into queries.py builders where easy — cleaner but expands diff/risk, blurs the move-don't-improve boundary. | |

**User's choice:** Verbatim, constants travel
**Notes:** Milestone MOVES the existing surface, it does not refactor. Lowest risk, smallest diff, behaviour provably identical. Captured as D-06.

---

## Claude's Discretion

- Exact per-accessor test-module naming/layout (follow `test_timescale_aliases.py`); 3 files vs one parametrized module.
- Order of the 3 accessors within each wave (independent).
- `from __future__ import annotations` + `TYPE_CHECKING` guards in the new modules (follow existing accessor modules).

## Deferred Ideas

- `db.schema.*` + spatial-index relocation → Phase 23.
- Public exports hardening / README / Sphinx / CHANGELOG / MIGRATION / version bump / PyPI publish → Phase 24.
- Opportunistic queries.py builder extraction — out of scope (D-06).
- Cosmetic ROADMAP "12/22" → "11/21" text fix — ride along in Phase 24 doc pass.
- Alias removal → v0.7.0.
