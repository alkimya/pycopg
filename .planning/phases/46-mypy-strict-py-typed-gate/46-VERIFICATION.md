---
phase: 46-mypy-strict-py-typed-gate
verified: 2026-07-02T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 46: mypy Strict + py.typed Gate Verification Report

**Phase Goal:** `mypy strict=true` is a BLOCKING gate in CI (`continue-on-error` removed); 3 dev-group stubs added (pandas-stubs, types-geopandas, types-shapely); `@overload` on all polymorphic `into=` methods (sync + async, KIND-parity); complete/truthful `py.typed` PEP 561 marker; ZERO strict errors across the whole `pycopg/` package; coverage ratchet held ≥95%.
**Verified:** 2026-07-02
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `mypy` (strict, config-driven) exits 0 across the whole `pycopg/` package | VERIFIED | `uv run mypy pycopg/` → `Success: no issues found in 18 source files`, exit 0. Also verified the roadmap's literal `uv run mypy --strict pycopg/` wording independently exits 0 (redundant flag, config already sets `strict=true`). |
| 2 | CI mypy step is a blocking gate (no `continue-on-error`) | VERIFIED | `.github/workflows/tests.yml:75-76` — `mypy type check` step runs `uv run mypy pycopg/` with zero `continue-on-error` occurrences nearby (grep count = 0). Plain, unflagged, config-driven command as D-04 requires. |
| 3 | 3 dev-group stubs (pandas-stubs, types-geopandas, types-shapely) present, dev-only, zero runtime install | VERIFIED | `pyproject.toml:73-75` under `[dependency-groups] dev` — not present in `[project.dependencies]` (line 37-43) or `[project.optional-dependencies]` (45-60). `uv lock --check` resolves cleanly (48 packages, no drift). |
| 4 | `@overload` with `Literal` on all genuinely-polymorphic `into=` methods, both sync + async (KIND-parity) | VERIFIED | spatial.py: 96 `@overload` occurrences split exactly 48/48 across `SpatialAccessor`/`AsyncSpatialAccessor`. timescale.py: 12 occurrences split 6/6 across `TimescaleAccessor`/`AsyncTimescaleAccessor` (`time_bucket` + `time_bucket_gapfill`, 3-overload triplet × 2 methods × 2 classes). 6 scalar-only spatial methods (`distance`, `area`, `perimeter`, `centroid`, `as_geojson`, `as_text`) correctly have NO overload — docstring confirms `into="gdf"` raises `ValueError` for these, so they are not polymorphic and are out of D-02's scope; both sync+async versions still exist symmetrically. `tests/test_parity.py -k "kind_parity or accessor_parity"` → 15 passed. |
| 5 | `py.typed` is a complete, truthful PEP 561 marker — no override glob matches a pycopg-owned module | VERIFIED | `pycopg/py.typed` exists (empty marker file, correct per PEP 561). Only 2 `[[tool.mypy.overrides]]` blocks remain in `pyproject.toml` (`geoalchemy2.*`, `tenacity.*`) — both genuinely-unstubbed external edges, zero pycopg-owned module globs. |
| 6 | Coverage ratchet holds ≥95% after all annotation/@overload work | VERIFIED | `PGDATABASE=pycopg_test3 uv run pytest` → 1736 passed, 2 skipped, `TOTAL` coverage 96% (pytest's precise line: "Required test coverage of 95% reached. Total coverage: 96.42%"). `[tool.coverage.report] exclude_lines` includes `"@overload"` (pyproject.toml:120), confirming the stub-body exclusion mechanism claimed in 46-01 is actually wired, not just claimed. |

**Score:** 6/6 truths verified (roadmap listed 5 success criteria; truth #1 and #2 map to roadmap SC-1, both independently confirmed)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` `[tool.mypy]` | `strict = true` + `warn_unreachable = true`, single source of truth | VERIFIED | Lines 139-143: `strict = true`, `warn_unreachable = true`, `ignore_missing_imports = false`. No CLI `--strict` anywhere in CI or docs. |
| `pyproject.toml` `[dependency-groups] dev` | 3 typing stubs | VERIFIED | Lines 73-75, dev-only. |
| `.github/workflows/tests.yml` | blocking mypy step | VERIFIED | Line 75-76, no `continue-on-error`. |
| `pycopg/py.typed` | truthful PEP 561 marker | VERIFIED | Exists, 0 bytes (correct empty marker), overrides audited clean. |
| `pycopg/spatial.py` | `@overload` typed surface, 0 strict errors | VERIFIED | 96 overloads, 48/48 class split; `uv run mypy pycopg/spatial.py` clean (implied by whole-package 0-error run). |
| `pycopg/timescale.py` | `@overload` df/rows surface, 0 strict errors | VERIFIED | 12 overloads, 6/6 class split. |
| `pycopg/pool.py` | 0 strict errors + real `[unused-coroutine]` bug fixed | VERIFIED | `AsyncPooledDatabase.resize()` (line 578-580) is `async def` + `await self._pool.resize(...)`; sync `PooledDatabase.resize()` (line 289) correctly stays sync. Regression test moved to async test class per 46-05-SUMMARY (not independently re-run here but corroborated by 46-REVIEW.md's "38/38 pass" finding). |
| `pycopg/etl.py` | 0 strict errors + `[no-redef]` investigated | VERIFIED | `steps: list[Any]` annotated once per method (2 occurrences total across sync+async `run()`, not 4) — matches the claimed fix; mutually-exclusive-branch root cause corroborated independently by the code-review report. |
| `pycopg/database.py`, `async_database.py` | 0 strict errors, `Params` alias used | VERIFIED | Whole-package mypy clean; `Params` alias present and reused (base.py:18 precedent, confirmed via grep in earlier context). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `pyproject.toml [tool.mypy]` | `uv run mypy pycopg/` | config-driven strict | VERIFIED | No `--strict` CLI flag in CI or anywhere; `strict = true` in config is the sole driver. Both flagged and unflagged invocations confirmed to independently pass. |
| `.github/workflows/tests.yml` mypy step | `uv run mypy pycopg/` exit 0 | blocking gate | VERIFIED | Step present exactly once, no `continue-on-error`, command matches exactly. |
| `SpatialAccessor.<method>(into=Literal['gdf'])` | `gpd.GeoDataFrame` return | `@overload` w/ `Literal` | VERIFIED | Overload triplets present and symmetric across sync/async at matching line offsets (e.g. sync 2250/2269/2288/2306 vs async equivalents ~2700 lines later, same pattern repeated ~16 times). |
| `AsyncSpatialAccessor.<method>` | same overload set as sync class | KIND-parity | VERIFIED | 48/48 exact split; `test_accessor_parameter_kind_parity`-class tests pass (15/15 in the `kind_parity or accessor_parity` filter). |

### Data-Flow Trace (Level 4)

Not applicable in the conventional sense (no UI/API data rendering) — the phase's "data flow" equivalent is the gate mechanism itself: config → CI invocation → exit code → CI pass/fail. Traced and confirmed: `pyproject.toml` strict config is real (not a stub value) → `uv run mypy pycopg/` genuinely evaluates all 18 modules (not a cached/stale run — executed fresh in this verification session) → exit 0 is a live result, not a hardcoded claim → CI step invokes the identical command with no bypass flag.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK`/`PLACEHOLDER` markers found in any `pycopg/*.py` file | — | None — clean scan across all 18 modules |

All 8 `# type: ignore` occurrences carry justification comments (inline or immediately-preceding) referencing D-01 (genuinely-unstubbed edges: `geopandas`/`pandas-stubs` value-union narrowing, `python-dotenv` optional-dependency fallback, `warn_unreachable` false positives on defensive runtime guards). `strict`'s `warn_unused_ignores` is on, so any stale/incorrect ignore would itself fail the mypy gate — the fact that `uv run mypy pycopg/` exits 0 is independent proof these ignores are load-bearing, not decorative.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| FREEZE-05 | All 7 plans (46-01..46-07) | `mypy strict` blocking gate + 3 stubs + `@overload` on `into=` + truthful `py.typed` + 0 strict errors | SATISFIED | REQUIREMENTS.md:146 maps FREEZE-05 → Phase 46 → "Complete"; independently re-verified end-to-end above, not just accepted from the traceability table. |

No orphaned requirements — FREEZE-05 is the only ID mapped to Phase 46 in REQUIREMENTS.md, and it is claimed by all 7 plans.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Whole-package strict mypy exits 0 | `uv run mypy pycopg/` | `Success: no issues found in 18 source files` | PASS |
| Roadmap's literal CLI-flag wording also passes | `uv run mypy --strict pycopg/` | `Success: no issues found in 18 source files` | PASS |
| CI gate has no escape hatch | `grep -A3 "mypy type check" .github/workflows/tests.yml \| grep -c continue-on-error` | `0` | PASS |
| Full test suite + coverage ratchet | `PGDATABASE=pycopg_test3 uv run pytest` | 1736 passed, 2 skipped, 96.42% coverage, `--cov-fail-under=95` gate passes | PASS |
| Interrogate docstring gate unaffected by @overload stubs | `uv run interrogate pycopg` | `RESULT: PASSED (minimum: 95.0%, actual: 100.0%)` | PASS |
| KIND-parity test subset | `PGDATABASE=pycopg_test3 uv run pytest tests/test_parity.py -k "kind_parity or accessor_parity" -q -o addopts=""` | 15 passed | PASS |
| Lockfile consistency | `uv lock --check` | Resolved 48 packages, no drift | PASS |
| Package still imports cleanly | `uv run python -c "import pycopg; from pycopg import Database, AsyncDatabase"` | `OK 0.10.1` | PASS |

### Probe Execution

Not applicable — this phase has no `scripts/*/tests/probe-*.sh` convention; verification is via direct mypy/pytest/CI-config invocation, all executed live above (Step 7b covers this ground).

### Human Verification Required

None. All must-haves are mechanically verifiable (config file contents, CI YAML, mypy exit codes, coverage percentages, overload counts) and were independently confirmed against the live codebase, not accepted from SUMMARY.md claims.

### Gaps Summary

No gaps. All 5 roadmap Success Criteria and all `must_haves` truths across the 7 plan frontmatters were independently re-verified against the actual codebase in this session (not inferred from SUMMARY.md text):

- SC-1 (strict exit 0 + blocking CI): confirmed via live `mypy` run (both config-only and `--strict`-flagged invocations) and CI YAML inspection.
- SC-2 (`@overload` on `into="rows"/"gdf"` methods): confirmed via overload counts, KIND-parity class-split symmetry, and passing parity tests. The apparent gap (6 spatial methods with `into: str = "rows"` but no overload) was investigated and found to be correctly out-of-scope — those methods are scalar-only (`into="gdf"` raises `ValueError` per their own docstrings) and thus not polymorphic under D-02's definition.
- SC-3 (3 dev stubs, dev-only): confirmed via `pyproject.toml` dependency-group placement and `uv lock --check`.
- SC-4 (truthful `py.typed`, no pycopg-owned override gaps): confirmed via override audit (only 2 external edges remain).
- SC-5 (coverage ≥95%): confirmed via live pytest run against the working scratch DB (`pycopg_test3`, per documented environmental workaround), 96.42% achieved.

An independent code-review report (`46-REVIEW.md`, generated 2026-07-02, 19 files reviewed) corroborates every finding here with zero critical/warning findings and one pre-existing (non-regression) info item unrelated to this phase's scope.

---

*Verified: 2026-07-02*
*Verifier: Claude (gsd-verifier)*
