# Phase 46: mypy Strict + py.typed Gate - Context

**Gathered:** 2026-07-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Flip `mypy --strict` from advisory (`continue-on-error: true`) to a **blocking CI gate**
over `pycopg/`, and complete the `py.typed` typed surface so the frozen 1.0 API ships
fully type-checkable for downstream consumers. This is the LAST pre-release phase
(REQUIREMENTS FREEZE-05); Phase 47 only tags/publishes.

**Measured baseline (roadmap "measure first"):** `mypy --strict pycopg/` →
**328 errors / 15 files**. Breakdown: **244 `[type-arg]`** (bare `list`/`dict` without
params), 24 `[no-untyped-def]`, 18 `[no-any-return]`, 10 `[return-value]`, 10 `[arg-type]`,
8 `[misc]`, 4 `[import-untyped]` (all pandas), 3 `[var-annotated]`, 3 `[index]`,
2 `[no-redef]`, 1 each `[unused-coroutine]`/`[call-overload]`. Hotspots: spatial.py (104),
etl.py (37), database.py (37), async_database.py (37), timescale.py (24), pool.py (22),
schema.py (20), base.py (17).

**In scope:** strict gate over `pycopg/`; 3 dev-only stubs; `@overload` on `into=` methods;
`__all__` where `--no-implicit-reexport` requires it; annotate/parameterize to zero strict
errors; flip CI to blocking; hold coverage ratchet ≥95%.

**Out of scope:** typing `tests/` or `benchmarks/` under strict (gate = `pycopg/` only —
1.x if ever); any signature/behavior change beyond annotations (1.0 is frozen); pyright as
a second checker (REQUIREMENTS explicitly rejects it — `mypy --strict` is sufficient).

</domain>

<decisions>
## Implementation Decisions

### Escape-hatch policy (reaching zero strict errors)
- **D-01:** **Narrow justified ignores allowed.** Fix real type issues to real annotations,
  but a narrow, code-specific `# type: ignore[code]` carrying a one-line justification is
  acceptable **only at genuinely-unstubbed third-party edges** (e.g. geoalchemy2, tenacity,
  or any sqlalchemy/psycopg internal that lacks usable inline types). No blanket file-level
  or bare `# type: ignore`. Strict's `warn_unused_ignores` stays on, so stale ignores fail
  the gate too. NOT the purist zero-ignore bar — pragmatism wins on mature/frozen code.

### `@overload` typed surface for `into=` polymorphism
- **D-02:** **Add `@overload` with `Literal` on ALL `into=` methods** so callers get precise
  return types on the frozen 1.0 API:
  - spatial (~6 helpers, e.g. `spatial.py:2183–2619`): `Literal["rows"]` → `list[dict[str, Any]]`,
    `Literal["gdf"]` → `gpd.GeoDataFrame`.
  - timescale (`timescale.py:1210–2317`): `Literal["df"]` → `pd.DataFrame`,
    `Literal["rows"]` → `list[dict[str, Any]]`.
  - **Keep the union as the runtime-variable fallback overload** — when `into` is a plain
    non-Literal `str`, the return type is the union (`list[dict] | GeoDataFrame`, etc.).
  - **Both sync AND async classes** get the overloads (KIND-parity — carried from P41).
  - Runtime `_check_into` validators (`spatial.py:2100`, `timescale.py:161`) stay — overloads
    are the static complement, not a replacement.

### `[type-arg]` generic precision (the 244-error bulk)
- **D-03:** **Pragmatic `Any` where the value is genuinely dynamic.** Use concrete args where
  known (row dicts → `dict[str, Any]`, result lists → `list[dict[str, Any]]`), but
  `Any`-parameterize genuinely-dynamic edges (SQL params, arbitrary result values, `_run`
  helper params). Consistent with the existing `Params = Sequence[Any] | Mapping[str, Any] | None`
  alias (`base.py:18`) — that is the precedent to follow. **No** TypedDicts for row shapes,
  **no** maximal-precision push; that churn/regression risk isn't worth it on a frozen API.

### Gate configuration (beyond bare `--strict`)
- **D-04:** `strict = true` **plus `warn_unreachable = true`** in `[tool.mypy]`. **Config is
  the single source of truth** — CI runs plain `uv run mypy pycopg/` (drop `continue-on-error`,
  no CLI `--strict` flag). Add the 3 stubs to the dev group; **remove** the
  pandas/geopandas/shapely `ignore_missing_imports` overrides. For sqlalchemy/psycopg/
  psycopg_pool overrides: **verify whether native inline stubs run clean and remove only if
  so; otherwise keep** (don't let override cleanup surface a new error swarm).

### Claude's Discretion
- Plan structure / fix ordering: roadmap says **fix bottom-up** — leaf/foundation modules
  (`base.py`, `config.py`, `exceptions.py`) first, then accessors (spatial/timescale/schema/
  etl/pool), then `database.py`/`async_database.py`. One-vs-many plans is planner's call.
- Exact stub version floors: take from research `STACK.md` (`pandas-stubs>=2.0.0`,
  `types-geopandas>=0.14.0`, `types-shapely>=2.0.0`) unless a newer pin is needed.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase spec & requirements
- `.planning/ROADMAP.md` — Phase 46 line (strict blocking, 3 stubs, `@overload` on `into=`,
  measure-first, zero strict errors over `pycopg/`, coverage ≥95%).
- `.planning/REQUIREMENTS.md` — **FREEZE-05** (the gate requirement, verbatim scope) and
  **REL-11** (Phase 47 release gate requires `mypy --strict` exit 0).

### Research (implementation-ready guidance — already done)
- `.planning/research/STACK.md` §3 (mypy strict for a py.typed lib) — the 13 flags `--strict`
  enables, recommended `[tool.mypy]` config, py.typed completeness rules (`__all__`,
  `@overload`, `TYPE_CHECKING`), CI integration. **Primary implementation reference.**
- `.planning/research/STACK.md` §1–2 — stub package names, version floors, why they're
  dev-only (never runtime deps).

### Code to modify (targets)
- `pyproject.toml` `[tool.mypy]` (~lines 133–175) — current non-strict config + overrides to replace.
- `.github/workflows/tests.yml` (mypy step ~lines 75–77) — flip `continue-on-error: true` → gate.
- `pycopg/spatial.py` — `into=` helpers (~2183–2619), `_check_into` (2100); 104 errors, biggest hotspot.
- `pycopg/timescale.py` — `into=` helpers (~1210–2317), `_check_into` (161); `_run` (1174).
- `pycopg/base.py` — `Params` alias (line 18): the pragmatic-`Any` precedent for D-03.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Params = Sequence[Any] | Mapping[str, Any] | None` (`base.py:18`, added P45 PARAM-01) —
  the template for D-03's pragmatic-Any generics; already threaded through `execute`/`fetch_*`.
- `_check_into()` runtime validators (`spatial.py:2100`, `timescale.py:161`) — pair with the
  new `@overload` static signatures; do not remove.
- `pycopg/py.typed` marker already present — the gate just has to make it truthful.

### Established Patterns
- **Sync/async parity (KIND-parity guard, P41):** every `into=` method exists in both the
  sync and async accessor class in the same file — overloads MUST be added to both, or the
  parity guard/test fails. Edit both classes in the same pass.
- Only `pycopg/__init__.py` currently declares `__all__` (17/18 modules lack it). Strict's
  `--no-implicit-reexport` means imported-but-not-`__all__`'d names stop re-exporting — this
  can break internal `from pycopg.X import Y` imports. **Research/planner must audit which
  modules need `__all__` and which internal cross-imports break.**

### Integration Points
- CI gate lives in `.github/workflows/tests.yml`; dev stubs go in the `pyproject.toml` dev
  dependency group (not runtime deps — end users never install them).

### Watch-items (downstream — not user decisions)
- **Coverage ratchet ≥95%:** `@overload` stub bodies (`...`) may be counted by coverage.py —
  may need `# pragma: no cover` on overload signatures or an `exclude_lines` rule to hold the
  ratchet (v0.10.0 introduced the first `pragma: no cover` use; precedent exists).
- 4 `[import-untyped]` errors are all `pandas` → resolved by `pandas-stubs`. pandas 2.1+ ships
  `py.typed` natively but stubs give better strict coverage (research §2).
- `[no-redef]` at `etl.py:2025` (`steps` redefined) and `[unused-coroutine]` are likely real
  latent bugs, not just annotation gaps — flag during fix.

</code_context>

<specifics>
## Specific Ideas

- The frozen 1.0 typed contract is the deliverable: after this phase, `import pycopg` under a
  downstream project's `mypy --strict` must give precise return types on `into=` calls, not
  `Any`. That's the DX bar D-02 is chasing.
- Verify (don't assume) that psycopg3 / SQLAlchemy 2.0 inline stubs run clean before removing
  their overrides — research flags both as "likely unnecessary" but says verify first.

</specifics>

<deferred>
## Deferred Ideas

- Extending the strict gate to `tests/` and `benchmarks/` — out of scope (gate = `pycopg/`
  only). Candidate for a 1.x hardening pass if desired.
- Maximally-precise row typing (TypedDicts per result shape) — rejected for 1.0 (D-03);
  revisit only if a concrete consumer need arises in 1.x.

</deferred>

---

*Phase: 46-mypy-strict-py-typed-gate*
*Context gathered: 2026-07-01*
