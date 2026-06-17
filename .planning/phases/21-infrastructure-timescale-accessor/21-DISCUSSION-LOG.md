# Phase 21: Infrastructure & Timescale Accessor - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-17
**Phase:** 21-Infrastructure & Timescale Accessor
**Areas discussed:** Decorator shape, Where impl lives, Test warning noise, Parity registration

---

## Area selection

| Option | Description | Selected |
|--------|-------------|----------|
| Decorator shape | How `@deprecated_alias` finds the new path & delegates; sync vs async variants (REORG-01) | ✓ |
| Where impl lives | Move bodies verbatim vs extract pure SQL builders to match spatial/etl | ✓ |
| Test warning noise | Migrate call-sites vs filterwarnings ignore (REORG-04) | ✓ |
| Parity registration | One-off TestTimescaleParity vs data-driven registry | ✓ |

**User's choice:** All four areas.

---

## Decorator shape

### Delegation mechanism
| Option | Description | Selected |
|--------|-------------|----------|
| Target path string | `@deprecated_alias("timescale.create_hypertable")` — resolve lazy accessor at call time, call named method | ✓ |
| Bind accessor + method | Pass accessor attr + method name as separate args | |
| You decide | Defer to research/planning | |

**User's choice:** Target path string (with a stated lean toward it in the question).

### Stub signature
| Option | Description | Selected |
|--------|-------------|----------|
| Generic *args/**kwargs | One-liner stub, decorator forwards everything; trivial v0.7.0 deletion | ✓ |
| Preserve full signature | Keep real params + docstring on each stub; deprecated path stays fully typed | |
| You decide | Defer | |

**User's choice:** Generic `*args/**kwargs`.
**Notes:** Flagged for research — interrogate ≥ 95 / Sphinx `-W` handling for signature-less stubs (one-line docstring vs `functools.wraps` metadata copy vs interrogate exclusion). Also: verify `stacklevel` correctness and async `await` delegation.

---

## Where impl lives

### Move style
| Option | Description | Selected |
|--------|-------------|----------|
| Move verbatim, self→self._db | Relocate bodies unchanged, keep inline SQL; lowest risk, behaviour-identical | ✓ |
| Extract pure builders too | Mirror spatial/etl with `_build_*` pure functions | |
| You decide | Per-method judgement | |

**User's choice:** Move verbatim, `self`→`self._db`.
**Notes:** Departure from spatial/etl pure-builder convention is intentional and scoped to timescale (interpolated INTERVAL literals / boolean flags don't fit the `%s`-only builder shape cleanly).

### Module placement
| Option | Description | Selected |
|--------|-------------|----------|
| One module per accessor | `pycopg/timescale.py` (sync + async), mirroring spatial.py/etl.py | ✓ |
| One shared accessors module | `pycopg/accessors.py` with all 5 pairs | |
| You decide | Defer (lean: one-per-accessor) | |

**User's choice:** One module per accessor.

---

## Test warning noise

| Option | Description | Selected |
|--------|-------------|----------|
| Migrate existing tests + dedicated alias tests | Move call-sites to `db.timescale.*`; add per-alias `pytest.warns` warn+delegate tests | ✓ |
| filterwarnings ignore, keep old call-sites | Targeted filterwarnings, defer real migration to v0.7.0 | |
| You decide | Defer | |

**User's choice:** Migrate existing tests + dedicated alias tests.
**Notes:** Satisfies REORG-04's explicit per-alias warn+delegate coverage requirement and keeps the ratchet (≥94%) green.

---

## Parity registration

| Option | Description | Selected |
|--------|-------------|----------|
| Data-driven registry | Parametrized test fed by list of (Sync, Async) accessor pairs; Phases 22-23 append | ✓ |
| One-off TestTimescaleParity | Copy the TestEtlParity shape per accessor | |
| You decide | Defer (lean: registry) | |

**User's choice:** Data-driven registry.
**Notes:** Aligns with D-SCOPE-3 "replicate mechanically". Folding the existing one-off `TestEtlParity` into the registry is optional cleanup, only if zero-risk — not forced into Phase 21 scope.

---

## Claude's Discretion

- Exact decorator internals beyond the locked behaviour (incl. whether to use `functools.wraps`).
- Placement/naming of the registry list and the alias test class.
- `from __future__ import annotations` / `TYPE_CHECKING` guards in `timescale.py` (follow spatial.py/etl.py).

## Deferred Ideas

- Pure SQL builders for timescale — not this phase; possible revisit at v0.8.0.
- Folding `TestEtlParity` into the registry — optional, zero-risk only.
- Other 4 accessors + spatial-index relocation — Phases 22-23.
- Exports / README / Sphinx / CHANGELOG / MIGRATION / version bump / PyPI — Phase 24 (REORG-05).
- Alias removal — v0.7.0. New TimescaleDB power — v0.8.0.
