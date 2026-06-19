# Phase 24: Exports, Docs & Release v0.6.0 - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-19
**Phase:** 24-Exports, Docs & Release v0.6.0
**Areas discussed:** README accessor presentation, Per-topic Sphinx docs depth, MIGRATION.md structure, Release mechanics & smoke test (+ CHANGELOG granularity)

---

## README accessor presentation

| Option | Description | Selected |
|--------|-------------|----------|
| Rewrite examples + add overview | Rewrite existing section examples to accessor paths AND add a consolidated 'Namespaces / accessors' overview table near the top. README becomes the canonical surface map. | ✓ |
| Overview table only | Add a namespace table but leave flat-method examples as-is (with a deprecated note). | |
| Rewrite examples only | Rewrite in-section examples to accessor paths, no separate overview table. | |

**User's choice:** Rewrite examples + add overview
**Notes:** Transactional core (execute, insert_batch, session, DataFrame ops) stays shown flat — not moving. → D-01

---

## Per-topic Sphinx docs depth

| Option | Description | Selected |
|--------|-------------|----------|
| Autodoc modules + rewrite prose | Add the 5 accessor modules to api-autodoc.md automodule list AND rewrite the prose examples in roles-permissions/backup-restore/timescaledb/database.md to accessor paths. | ✓ |
| Autodoc modules + deprecation note | Autodoc the 5 modules but leave prose mostly flat with a top-of-page admonition. | |
| Autodoc modules only | Just add the 5 modules to autodoc; no prose edits. | |

**User's choice:** Autodoc modules + rewrite prose
**Notes:** Consistent with the README rewrite. `-W` warnings-as-error stays the hard gate (D-03 vigilance). → D-02

---

## MIGRATION.md structure

| Option | Description | Selected |
|--------|-------------|----------|
| Prepend v0.6 section, full table | Prepend a v0.5→v0.6 section at the top of the existing MIGRATION.md (keeping v0.2→v0.3 below) with a COMPLETE flat-name → accessor-path table for all deprecated names + removal-in-v0.7.0 notice + D-06 PostGIS-guard note. | ✓ |
| Prepend v0.6 section, per-accessor | Summarize per-accessor rather than a full table. | |
| Rename file as primary v0.6 guide | Restructure so v0.5→v0.6 is primary, archive v0.2→v0.3 to appendix. | |

**User's choice:** Prepend v0.6 section, full table
**Notes:** Full table = all 56 deprecated names (timescale 6 / admin 11 / schema 27 / maint 6 / backup 4 / spatial 2), generated from the live `@deprecated_alias` stubs, not the stale SCOPE counts. → D-04

---

## Release mechanics & smoke test

| Option | Description | Selected |
|--------|-------------|----------|
| Manual release-checklist step | Document the clean-venv `pip install` + import smoke test as a manual post-publish verification step (matches v0.3/v0.4/v0.5). | ✓ |
| Automated import smoke test in suite | Add a gated import test to the suite PLUS the manual check. | |
| Skip explicit smoke test | Rely on existing import coverage; treat install verification as implicit. | |

**User's choice:** Manual release-checklist step
**Notes:** Same hands-on flow as the three prior PyPI releases; no new CI to maintain. → D-06

---

## CHANGELOG granularity (sub-question of Release mechanics)

| Option | Description | Selected |
|--------|-------------|----------|
| Per-accessor + Deprecated + Changed | Added: 5 accessor namespaces with method counts (not every method). Deprecated: one entry, removal v0.7.0, point to MIGRATION.md. Changed: D-06 PostGIS-guard refinement. Keep-a-Changelog shape, matches v0.5.0 entry. | ✓ |
| Per-method exhaustive | Enumerate every moved method (~57 lines). | |
| Minimal summary | One Added + one Deprecated line + the D-06 Changed note. | |

**User's choice:** Per-accessor + Deprecated + Changed
**Notes:** → D-05

---

## Claude's Discretion

- Exact wording/layout of the README "Namespaces" overview (table vs nested list).
- Whether autodoc additions go as more automodule blocks or a grouped sub-section in api-autodoc.md.
- Per-plan decomposition (docs plan + release plan, or finer).
- Whether accessor topics need new docs/index.md toctree entries (keep `-W` green).
- Release date string in CHANGELOG/MIGRATION (stamp at release time).
- Standard release tail: version bump in pyproject.toml + docs/conf.py, build, twine/PyPI, git tag,
  RTD rebuild (D-07 informational — mechanical, by precedent).

## Deferred Ideas

- Alias removal — v0.7.0.
- New helpers (CRUD, advanced TimescaleDB, spatial v2, enriched introspection, db.meta.* carve-out) — v0.8.0+.
- Conforming the 2 relocated spatial methods to pure-builder/`_run` house style — spatial v2 (v1.0.0).
- Automated install/import smoke test in CI — could be promoted from manual in a future hardening pass.
- ETL incremental (watermarks) — separate candidate.
