# Phase 46: mypy Strict + py.typed Gate - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-01
**Phase:** 46-mypy-strict-py-typed-gate
**Areas discussed:** Escape-hatch policy, `@overload` typed surface, generic precision, gate configuration

---

## Escape-hatch policy (`# type: ignore`)

| Option | Description | Selected |
|--------|-------------|----------|
| Narrow justified ignores OK | Fix real issues; narrow code-specific `# type: ignore[code]` + one-line justification only at unstubbed third-party edges; `warn_unused_ignores` stays on | ✓ |
| Zero ignores (purist) | Ban `# type: ignore` entirely across `pycopg/` | |
| Ignores OK, must be tracked | Allow ignores but require a tracking marker linking to 1.x follow-up | |

**User's choice:** Narrow justified ignores OK
**Notes:** Pragmatism over purism on mature/frozen code; stale-ignore detection still enforced by strict.

---

## `@overload` typed surface for `into=`

| Option | Description | Selected |
|--------|-------------|----------|
| Literal @overload, all into= methods | `Literal` overloads on every spatial + timescale `into=` method; keep union as runtime-variable fallback; sync+async both | ✓ |
| Overload only what strict flags | Add overloads only where strict errors; leave rest as unions | |
| No overloads — precise unions only | Skip `@overload`, just make union returns precise | |

**User's choice:** Literal @overload, all into= methods
**Notes:** Frozen 1.0 typed contract — downstream `mypy --strict` should get precise (not `Any`) return types on `into=` calls. Must land in both sync and async classes (KIND-parity).

---

## `[type-arg]` generic precision (244-error bulk)

| Option | Description | Selected |
|--------|-------------|----------|
| Pragmatic Any where dynamic | Concrete where known; `Any`-parameterize genuinely-dynamic edges; consistent with existing `Params` alias | ✓ |
| Maximally precise | TypedDicts for row shapes, precise param unions everywhere | |

**User's choice:** Pragmatic Any where dynamic
**Notes:** Follows the `Params = Sequence[Any] | Mapping[str, Any] | None` precedent; avoids churn/regression risk on frozen API.

---

## Gate configuration beyond `--strict`

| Option | Description | Selected |
|--------|-------------|----------|
| strict=true + warn_unreachable, config source of truth | Add `warn_unreachable=true`; config drives CI (`uv run mypy pycopg/`); verify/remove sqlalchemy/psycopg overrides only if clean | ✓ |
| Exactly --strict, nothing extra | `strict=true` only; keep all overrides | |
| Let planner decide the knobs | Lock only "blocking strict over pycopg/" | |

**User's choice:** strict=true + warn_unreachable, config is source of truth
**Notes:** Config as single source of truth keeps the CI invocation trivial and un-drifting.

---

## Claude's Discretion

- Plan structure and fix ordering (roadmap: bottom-up — foundation modules → accessors → database/async_database).
- Exact stub version floors (default to research `STACK.md` pins).

## Deferred Ideas

- Extending the strict gate to `tests/` and `benchmarks/` — 1.x hardening candidate.
- Maximally-precise row typing (TypedDicts) — revisit in 1.x only on concrete need.
