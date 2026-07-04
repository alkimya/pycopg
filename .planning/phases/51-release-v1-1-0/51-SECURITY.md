---
phase: 51
slug: release-v1-1-0
status: verified
threats_open: 0
asvs_level: 1
created: 2026-07-04
---

# Phase 51 — Release v1.1.0 — Security Verification

Audit of the plan-time threat register (12 threats across 51-01/02/03) against the
implemented + shipped code. Every declared mitigation was verified by direct grep/inspection
of the cited files; accepted risks are logged below. **Result: 12/12 CLOSED, 0 open.**

Implementation files were treated as READ-ONLY; only this SECURITY.md was written.

## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| caller → `db.timescale.time_bucket` | `origin`/`offset` are caller-supplied values crossing into SQL construction |
| repo docs/metadata → build artifact | `pyproject.toml` / `CLAUDE.md` / `docs/*` feed the published wheel + rendered docs |
| repo sources → build artifact | `pyproject.toml` / `uv.lock` feed the wheel the publish workflow builds |
| dependency lockfile → CI gate | `uv.lock` is validated by `uv lock --check` in `publish.yml` |
| release gates → publish authorization | green 5-gate run is the precondition 51-03 tags/publishes against |
| local repo → GitHub (tag push) | annotated tag crosses into the remote; the Release is created from it |
| GitHub Release event → PyPI | `release: published` triggers OIDC trusted publishing into the PyPI project |
| PyPI → end user (clean-venv smoke) | the published wheel is what a downstream `pip install` fetches |

## Threat Register

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-51-01 | Tampering | mitigate | CLOSED | Pure-Python guard `if origin is not None and offset is not None: raise ValueError` hoisted to `pycopg/timescale.py:1552` (sync, before `has_extension("timescaledb")` at :1558) and `:2888` (async, before `await ... has_extension` at :2894); defense-in-depth guard retained at `:271` immediately after `validate_identifiers(table, schema, time_column)` at `:270`. Guard count = 3. Zero new SQL/interpolation (origin/offset still bound `%s` / `%s::interval` inside `_build_time_bucket_sql`). Regression tests `test_time_bucket_origin_offset_no_extension_check` (tests/test_timescale.py:2579) + async `:2603` + strengthened `:2552` all assert `mock_schema.has_extension.assert_not_called()` with `has_extension` mocked to return `True`, proving the guard fires before the DB round-trip. |
| T-51-02 | Information Disclosure | accept | CLOSED | Pure documentation/metadata text edits, no runtime path or secret. See Accepted Risks Log AR-51-02. (Verified applied: pyproject classifier `5 - Production/Stable` at pyproject.toml:25; api-reference Exceptions block canonical names at docs/api-reference.md:518-520; CLAUDE.md Version `pycopg v1.1.0` at :13.) |
| T-51-03 | Tampering | mitigate | CLOSED | docs/api-reference.md Exceptions import block (:514-522) imports only canonical `*Error` names (`ExtensionNotAvailableError`/`TableNotFoundError`/`InvalidIdentifierError` at :518-520); bare deprecated aliases `ExtensionNotAvailable,` / `TableNotFound,` / `InvalidIdentifier,` all grep-count 0 in the import example. No exercised path imports a `DeprecationWarning`-emitting alias; gate #4 recorded green in 51-02-SUMMARY. |
| T-51-04 | Tampering | mitigate | CLOSED | uv.lock local `name = "pycopg"` block (:709-711) reads `version = "1.1.0"`; dependency set unchanged (pandas/psycopg/psycopg-pool/sqlalchemy — zero-deps bar held); `uv lock --check` exits 0 (re-run live during audit: "Resolved 48 packages", exit 0) → lockfile provably current for the published artifact. |
| T-51-05 | Repudiation | mitigate | CLOSED | Every name in CHANGELOG `[1.1.0]` resolves to a real `pycopg/` definition: TimescaleDB (`drop_continuous_aggregate`, `remove_continuous_aggregate_policy`, `compress_chunk`, `decompress_chunk`, `show_chunks` → timescale.py); ETL (`initial_watermark`, `incremental_inclusive`, `incremental_lookback`, `incremental_column`, `concurrency` → etl.py); CRUD (`where_sql`/`where_params`, `delete_where`, `update_where`, `paginate_page`, `paginate_keyset` → base/database/async_database.py; `Page` = database.py:136); introspection (`materialized_views`, `materialized_view_columns`, `describe` → schema.py; `TableDescription` = schema.py:38). No phantom/overstated surface. |
| T-51-06 | Elevation of Privilege / Tampering | mitigate | CLOSED | pyproject.toml `filterwarnings` list contains `"error::DeprecationWarning"` at :100 (config-default), so any exercised path importing a `DeprecationWarning`-emitting alias fails the build; explicit gate #4 (`-W error::DeprecationWarning`) recorded green in 51-02-SUMMARY. |
| T-51-07 | Information Disclosure | accept | CLOSED | Pure metadata/text (pyproject.toml `version = "1.1.0"` :7; docs/conf.py `release = '1.1.0'` :17; CHANGELOG) — no runtime code path or secret. See Accepted Risks Log AR-51-07. |
| T-51-08 | Spoofing / Elevation of Privilege | mitigate | CLOSED | .github/workflows/publish.yml: no PyPI token/secret (no `password:`, no `secrets.*` reference); OIDC trusted publishing via `pypa/gh-action-pypi-publish@release/v1` (:43) in a job scoped to `environment: pypi` (:32) with `permissions: id-token: write` only (:33-34); trigger is `release: [published]` (:4-5) — a human-published GitHub Release, so the executor cannot publish autonomously (confirmed by the human-gate checkpoint in 51-03). |
| T-51-09 | Tampering | mitigate | CLOSED | `git cat-file -t v1.1.0` = `tag` (annotated); `git rev-parse v1.1.0^{commit}` = `6e47cf766...` == `git rev-parse 6e47cf7` == the release HEAD whose 5 gates were green. Release created from that same tag (publish trigger `release: published`) → provenance chains commit → tag → release → PyPI. |
| T-51-10 | Tampering / Information Disclosure | mitigate | CLOSED | Clean-venv smoke (51-03-SUMMARY Task 3): `pip install --no-cache-dir pycopg==1.1.0` from real PyPI, asserted `__version__ == "1.1.0"`, `from pycopg import Page, TableDescription`, `hasattr(Database, "paginate_keyset")`, printed `smoke ok 1.1.0`. Corroborated live during audit: PyPI JSON API confirms `1.1.0` is published and is the latest version. |
| T-51-11 | Denial of Service | mitigate | CLOSED | 51-03 Task 1 verified no pre-existing `v1.1.0` tag before creating (SUMMARY: "No pre-existing tag collision"); `git tag -l v1.1.0` shows exactly one tag; PyPI immutable-version rule blocks any duplicate publish. |
| T-51-SC | Tampering (Package Legitimacy) | accept | CLOSED | The only install is `pip install pycopg==1.1.0` — the project's OWN just-published artifact, verified by the smoke assertions — not a third-party dependency. No `[ASSUMED]`/`[SUS]`/`[SLOP]` packages. See Accepted Risks Log AR-51-SC. |

## Accepted Risks Log

| ID | Threat | Rationale (plan-time) | Verification |
|----|--------|-----------------------|--------------|
| AR-51-02 | T-51-02 — docs/api-reference.md, CLAUDE.md, pyproject.toml classifier edits | Pure documentation/metadata text edits; no runtime code path, no secrets, no attack surface. | Edits confirmed applied and inert: pyproject.toml:25 classifier, docs/api-reference.md:518-520 import block, CLAUDE.md:13 version line. Accepted. |
| AR-51-07 | T-51-07 — version/CHANGELOG/docs metadata edits | Pure metadata/text; no runtime code path or secret. | pyproject.toml:7, docs/conf.py:17, CHANGELOG `[1.1.0]` confirmed; no executable surface. Accepted. |
| AR-51-SC | T-51-SC — pip install (Package Legitimacy Gate) | Only install is the project's own just-published `pycopg==1.1.0`, verified by smoke assertions; not a third-party dependency; no suspicious/assumed/slop packages. | Smoke installed `pycopg==1.1.0` from PyPI (self-artifact); live PyPI check confirms the version. Accepted. |

## Unregistered Flags

None. No 51-* SUMMARY declares a `## Threat Flags` section; no new attack surface appeared during
implementation without a mapping. The plan-time register (`register_authored_at_plan_time: true`)
is complete and every threat resolved.

## Informational (out of threat scope, non-blocking)

- docs/api-reference.md:273 contains a prose (English-sentence, backtick-quoted) mention of the
  deprecated name `ExtensionNotAvailable` — "raises `ExtensionNotAvailable` if PostGIS is not
  installed." This is descriptive markdown text, NOT a Python `import`, so it does not trigger the
  PEP-562 `__getattr__` `DeprecationWarning` and does not affect the `-W error::DeprecationWarning`
  pytest gate (gate #4 recorded green). T-51-03's mitigation target (the import example block) is
  correct. Flagged only as a documentation-freshness nit; not a security finding and not blocking.

## Security Audit Trail

| Date | Auditor | Action | Result |
|------|---------|--------|--------|
| 2026-07-04 | gsd-security-auditor | Verified all 12 plan-time threats (T-51-01..11 + T-51-SC) by direct grep/inspection of cited files; corroborated tag provenance (`v1.1.0` → 6e47cf7), publish.yml OIDC config, uv.lock currency, CHANGELOG name resolution, and PyPI 1.1.0 publication. | 12/12 CLOSED; 0 open; 0 unregistered flags. |

## Sign-Off

- ASVS Level: 1
- Threats total: 12 | Closed: 12 (9 mitigate verified: T-51-01/03/04/05/06/08/09/10/11 + 3 accept logged: T-51-02/07/SC) | Open: 0
- Unregistered flags: 0
- Status: **verified** — Phase 51 (Release v1.1.0) mitigations are present in the shipped
  implementation and provenance chain. No BLOCKER, no WARNING. Safe from a threat-mitigation standpoint.
