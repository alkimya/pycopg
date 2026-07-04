# Phase 51: Release v1.1.0 - Context

**Gathered:** 2026-07-04
**Status:** Ready for planning
**Source:** Orchestrator-captured (release phase — DOC-13 + REL-12 fully specified in REQUIREMENTS.md; no discuss-phase, research skipped per user)

<domain>
## Phase Boundary

Ship **pycopg v1.1.0** to PyPI: correct stable-1.x package metadata + docs (DOC-13),
version bump + Added CHANGELOG + 5 green release gates + annotated tag + human-gated
OIDC publish + clean-venv smoke (REL-12). This is the FINAL phase of the v1.1.0
milestone (Phases 48-50 already Complete). One robustness carry-forward (WR-01) is
folded in per user decision (D-05).

**In scope:** metadata/docs corrections, version sources, CHANGELOG, the WR-01
guard-order fix, running the release gates, tag + publish + smoke.

**Out of scope:** any new API surface, any feature work, MIGRATION churn (v1.1.0 is
purely additive under the frozen SemVer-1.0 API — no `DeprecationWarning`/breaking
changes introduced by this milestone).
</domain>

<decisions>
## Implementation Decisions

### D-01 — Version bump sources (REL-12)
Bump `1.0.0` → `1.1.0` in exactly two files:
- `pyproject.toml` line 7: `version = "1.1.0"`
- `docs/conf.py` line 17: `release = '1.1.0'`

`pycopg/__init__.py` resolves `__version__` via `importlib.metadata.version("pycopg")`
(installed metadata) — **no hardcoded version edit there**. `docs/stability.md`
("At **1.0.0** the public API is frozen") is a *historical* statement about the freeze
point — **leave unchanged**.

### D-02 — DOC-13: Development Status classifier
`pyproject.toml` line 25: `"Development Status :: 4 - Beta"` → `"Development Status :: 5 - Production/Stable"`.

### D-03 — DOC-13: api-reference deprecated exception names (GATE-CRITICAL)
In `docs/api-reference.md` "## Exceptions" import block (~lines 514-522), replace the
three deprecated aliases with their canonical `*Error` names and fix the trailing
`#` comments to line up:
- `ExtensionNotAvailable` → `ExtensionNotAvailableError`
- `TableNotFound`         → `TableNotFoundError`
- `InvalidIdentifier`     → `InvalidIdentifierError`

(`PycopgError`, `ConnectionError`, `ConfigurationError`, `MigrationError` in that block
are canonical class names — **not** deprecated — leave them.) These three aliases are
in `pycopg/exceptions.py::_DEPRECATED_NAMES` and emit `DeprecationWarning` via PEP-562
`__getattr__`. **This fix MUST land before the `-W error::DeprecationWarning` release
gate runs (D-08)** — otherwise a docs import example that is exercised would trip it.

### D-04 — DOC-13: CLAUDE.md Version line
`CLAUDE.md` line 13 currently reads `**pycopg v0.9.0**` (two versions stale). Update the
Version line to `**pycopg v1.1.0**` and refresh the adjacent one-line description if it
misstates the shipped surface. The `## Version` block near line 11 must reflect v1.1.0.

### D-05 — WR-01 fold-in: hoist time_bucket origin/offset guard (user decision)
The public `time_bucket` docstring (both classes) claims the `origin`+`offset`
mutual-exclusion `ValueError` is "raised before any DB round-trip (D-07, TSDB-F02)",
but today it fires inside `_build_time_bucket_sql` **after** `has_extension()` (a DB
round-trip). Hoist an explicit `if origin is not None and offset is not None: raise
ValueError(...)` to before the `has_extension()` call in **both**:
- sync `TimescaleAccessor.time_bucket` (concrete impl, `has_extension` at ~L1552)
- async `AsyncTimescaleAccessor.time_bucket` (concrete impl, `await has_extension` at ~L2882)

Maintain sync/async **KIND-parity** (edit BOTH classes — the recurring release-phase
lesson). The existing guard inside `_build_time_bucket_sql` stays as defense-in-depth.
Add a regression test asserting `ValueError` fires for `origin=... , offset=...`
**without** requiring a live TimescaleDB extension (i.e. before `has_extension`), on
both sync and async paths. Non-breaking: only changes *when* the identical `ValueError`
fires (earlier).

### D-06 — CHANGELOG `[1.1.0]` content (REL-12)
Promote `[Unreleased]` → `## [1.1.0] - 2026-07-04` (Keep-a-Changelog). Body is
**code-exact** against the shipped surface of Phases 48-50:
- **### Added** — TSDB follow-ups (cagg teardown, `time_bucket` origin/offset,
  per-chunk compress/decompress), ETL-INC follow-ups (`initial_watermark`,
  `incremental_inclusive`/`incremental_lookback`, composite watermark,
  `concurrency=wait/skip`), CRUD/introspection follow-ups (raw-SQL `where_sql`/
  `where_params`, `Page` keyset/offset pagination, matview introspection,
  `describe(into=...)` + `TableDescription`). Signatures must match the code exactly.
- **### Fixed** — one entry for WR-01 (D-05): `time_bucket` now raises the
  `origin`/`offset` mutual-exclusion `ValueError` before any DB round-trip.

**Consequence of D-05:** success-criterion #3's "Added-only" is relaxed to
"Added + one Fixed (WR-01)" — the honest Keep-a-Changelog classification for a
behavior fix. Everything else in `[1.1.0]` is Added-only.

### D-07 — Publish mechanism (REL-12)
Mirror Phase 47: annotated tag `v1.1.0` → GitHub Release `published` → `publish.yml`
OIDC trusted publishing (`uv build`, no tests in publish). **Human-gated**: the user
creates the GitHub Release; the plan stops at a checkpoint and does not publish
autonomously. Clean-venv smoke AFTER publish: fresh venv, `pip install pycopg==1.1.0`,
assert `__version__ == "1.1.0"` + a trivial import of a Phase 48-50 symbol.

### D-08 — The 5 release gates (verification contract, REL-12)
All must be green before tag/publish:
1. coverage ≥ 95%
2. interrogate 100%
3. Sphinx `-W` (zero warnings)
4. `-W error::DeprecationWarning` (suite clean) — **depends on D-03 landing first**
5. `mypy --strict` → 0 errors

**Sequencing:** DOC-13 corrections (D-02/D-03/D-04) + WR-01 (D-05) land FIRST → then
version bump (D-01) + CHANGELOG (D-06) → then run all 5 gates → then tag + human-gated
publish (D-07) + smoke.

### Claude's Discretion
Plan file count/wave assignment (prior release phases used ~3 plans: corrections →
bump+CHANGELOG+gates → tag+publish+smoke); exact CHANGELOG wording so long as it is
code-exact; test file/location for the WR-01 regression test.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements & roadmap
- `.planning/REQUIREMENTS.md` — DOC-13 + REL-12 exact acceptance text; cross-cutting bar (parity, validate_identifiers, zero-deps, mypy-strict, cov≥95%)
- `.planning/ROADMAP.md` — Phase 51 goal + 4 success criteria + Depends-on 48/49/50

### DOC-13 / REL-12 edit targets
- `pyproject.toml` — version (L7), classifier (L25), the `-W error::DeprecationWarning` filter config
- `docs/conf.py` — `release` (L17)
- `docs/api-reference.md` — "## Exceptions" block (~L514-522)
- `CLAUDE.md` — Version block (~L11-13)
- `CHANGELOG.md` — `[Unreleased]` → `[1.1.0]`

### WR-01 (D-05)
- `pycopg/timescale.py` — sync `time_bucket` (concrete impl ~L1469-1567), async `time_bucket` (concrete impl ~L2799-2890), `_build_time_bucket_sql` guard (~L271-276)
- `pycopg/exceptions.py` — `_DEPRECATED_NAMES` (L81-86), canonical `*Error` classes

### Release mechanics precedent
- `.github/workflows/publish.yml` — OIDC trusted publishing on `release: published` (runs `uv lock --check` + `uv build`, NOT tests)
- Phase 47 release pattern: version bump (3 sources → here 2), Added CHANGELOG, 5 gates, tag + human-gated publish + clean-venv smoke

### Tests
- `tests/` — run all DB/parity/coverage tests with `PGDATABASE=pycopg_test3` (default `pycopg_test`/`pycopg_test2` are broken by TSDB `.so` drift). KIND-parity enforced by `test_accessor_parity` + `test_accessor_parameter_kind_parity`.
</canonical_refs>

<specifics>
## Specific Ideas

- The `-W error::DeprecationWarning` gate is the reason D-03 is gate-critical and must
  be sequenced before gate execution.
- `docs/stability.md`'s "At 1.0.0 the public API is frozen" is intentionally NOT bumped
  (historical freeze-point statement, not a current-version marker).
- No new deps, no MIGRATION.md entry (purely additive milestone).
</specifics>

<deferred>
## Deferred Ideas

- CDC/ETL-INC-F05, SPAT-F01, RASTER-F01 — user chose to defer to a later additive 1.x
  (do not re-litigate). Not part of Phase 51.
</deferred>

---

*Phase: 51-release-v1-1-0*
*Context gathered: 2026-07-04 via orchestrator capture (no discuss-phase)*
