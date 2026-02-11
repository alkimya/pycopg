# Phase 7: Documentation & Release - Research

**Researched:** 2026-02-11
**Domain:** Python package documentation, changelog management, version release, PyPI publishing
**Confidence:** HIGH

## Summary

This phase delivers updated documentation, a changelog, migration guide, and v0.3.0 release to PyPI for pycopg. The project already has Sphinx documentation infrastructure (MyST markdown, Furo theme, autodoc configured) and a GitHub Actions trusted publishing workflow. Research reveals the project needs: (1) a new CHANGELOG.md file following keepachangelog format, (2) a migration guide showing before/after examples for breaking changes, (3) updated README and Sphinx docs to reflect new async methods, (4) Sphinx rebuild with conf.py version bump, and (5) pyproject.toml version update triggering the existing CI publish workflow.

**Primary recommendation:** Create CHANGELOG.md with 0.3.0 entry listing breaking changes and all features from phases 1-6, write MIGRATION.md with before/after code examples for CRS validation breaking change and new async methods, update README with async parity feature sections, regenerate Sphinx docs with version 0.3.0, bump pyproject.toml version, and create git tag v0.3.0 to trigger trusted publishing workflow.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Sphinx | 7.x+ | Documentation generator | Industry standard for Python docs, supports autodoc, extensible |
| myst-parser | 2.x+ | Markdown support in Sphinx | Allows writing docs in Markdown instead of RST |
| sphinx-autodoc | Built-in | API reference from docstrings | Automatic API docs from code, stays in sync |
| furo | Latest | Sphinx theme | Modern, clean, mobile-friendly theme (already configured) |
| hatchling | Latest | Build backend | Modern PEP 517 build system (already used in pyproject.toml) |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sphinx-copybutton | Latest | Copy buttons for code blocks | Improves user experience (already configured) |
| keepachangelog | 2.x | CHANGELOG.md parser/validator | Optional - for automated changelog management |
| python-semantic-release | 10.x+ | Automated versioning | Optional - for automated releases (not needed for v0.3.0) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Sphinx | MkDocs | MkDocs simpler but Sphinx has better autodoc, already configured |
| keepachangelog format | Custom format | Keep a Changelog is community standard, easier for users to read |
| Manual version bump | python-semantic-release | Automation good for CI but manual control better for 0.3.0 release |

**Installation:**
Project already has Sphinx installed. No new dependencies needed.

## Architecture Patterns

### Recommended File Structure
```
pycopg/
├── README.md                 # Updated with v0.3.0 features
├── CHANGELOG.md              # NEW: keepachangelog format
├── MIGRATION.md              # NEW: 0.2.0 → 0.3.0 upgrade guide
├── pyproject.toml            # Version bumped to 0.3.0
├── docs/
│   ├── conf.py               # Version bumped to 0.3.0
│   ├── index.md              # Updated features list
│   ├── async-database.md     # NEW SECTIONS: async DataFrame, admin, PostGIS, TimescaleDB
│   ├── api-reference.md      # Updated with all async methods
│   └── _build/html/          # Rebuilt documentation
└── .github/workflows/
    └── publish.yml           # Existing trusted publishing workflow
```

### Pattern 1: CHANGELOG.md Structure (Keep a Changelog Format)
**What:** Structured changelog with versions, dates, and categorized changes
**When to use:** Every release, updated before version bump
**Example:**
```markdown
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-02-XX

### Added
- Retry/backoff with tenacity for connection failures (3 attempts, exponential backoff 1-10s)
- Async DataFrame methods: `to_dataframe()`, `from_dataframe()`, `to_geodataframe()`, `from_geodataframe()`
- Async admin methods: `create_table()`, `drop_table()`, `create_index()`, `vacuum()`, `analyze()`, `explain()`
- Async backup methods: `pg_dump()`, `pg_restore()`, `copy_to_csv()`, `copy_from_csv()`
- Async role management: `create_role()`, `grant()`, `revoke()`, `list_role_grants()`
- Async PostGIS methods: `create_spatial_index()`, `list_geometry_columns()`
- Async TimescaleDB methods: `create_hypertable()`, `enable_compression()`, `add_retention_policy()`
- Configurable `statement_timeout` in Config for query timeout protection
- Configurable `batch_size` for insert operations (default 1000)

### Changed
- **BREAKING:** `from_geodataframe()` now raises `ValueError` on unknown CRS instead of silently defaulting to SRID 4326

### Fixed
- Session cleanup now succeeds even if `close()` raises exception (prevents connection leaks)
- Session mode correctly detects implicit transactions for all `TransactionStatus` states
- Migration file parser logs skipped files at WARNING level instead of silent continue
- TimescaleDB methods validate extension exists before executing operations
- GeoDataFrame SRID inference raises clear error on unknown CRS with actionable message

### Improved
- Test coverage increased from ~50% to 72.76%
- Pool connection cycling and reconnection handling improved
- Error messages for PostGIS operations without extension installed

## [0.2.0] - 2026-01-XX

Initial release with sync/async Database, connection pooling, migrations, PostGIS, TimescaleDB.

[Unreleased]: https://github.com/alkimya/pycopg/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/alkimya/pycopg/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/alkimya/pycopg/releases/tag/v0.2.0
```

### Pattern 2: Migration Guide Structure
**What:** Before/after code examples showing how to upgrade
**When to use:** Any breaking change or major feature addition
**Example:**
```markdown
# Migration Guide: v0.2.0 → v0.3.0

This guide helps you upgrade from pycopg 0.2.0 to 0.3.0.

## Breaking Changes

### 1. GeoDataFrame CRS Validation

**What changed:** `from_geodataframe()` now raises `ValueError` on unknown CRS instead of silently defaulting to SRID 4326.

**Why:** Silent defaults hide configuration errors. Explicit errors prevent data corruption.

**Before (0.2.0):**
```python
gdf = gpd.read_file("data.geojson")  # Unknown CRS
db.from_geodataframe(gdf, "parcels")  # Silently used SRID 4326
```

**After (0.3.0):**
```python
gdf = gpd.read_file("data.geojson")
# Now raises: ValueError("GeoDataFrame CRS could not be converted to SRID...")

# Fix: Explicitly set CRS
gdf = gdf.set_crs("EPSG:4326")
db.from_geodataframe(gdf, "parcels")  # Works
```

## New Features

### Async DataFrame Operations

**What's new:** AsyncDatabase now has full DataFrame/GeoDataFrame support.

**Example:**
```python
from pycopg import AsyncDatabase

db = AsyncDatabase.from_env()

# Read table to DataFrame
df = await db.to_dataframe("users")

# Insert from DataFrame
await db.from_dataframe(df, "users_backup")

# Spatial data
gdf = await db.to_geodataframe("parcels")
await db.from_geodataframe(gdf, "parcels_copy", spatial_index=True)
```

### Retry/Backoff for Resilience

**What's new:** Automatic retry with exponential backoff for transient connection errors.

**Example:**
```python
from pycopg import Database

# Retry automatically enabled on connect()
db = Database.from_env()
# On connection failure: retries 3 times with exponential backoff (1-10s)
```

### Statement Timeout

**What's new:** Configurable query timeout to prevent runaway queries.

**Example:**
```python
from pycopg import Database, Config

config = Config.from_env()
config.statement_timeout = 30000  # 30 seconds
db = Database(config)

# Queries exceeding 30s will be cancelled
```
```

### Pattern 3: README Update Strategy
**What:** Reflect new features in Quick Start and Features sections
**When to use:** Every release with user-visible changes
**Example:**
```markdown
## Async Support

All Database operations available in AsyncDatabase:

```python
from pycopg import AsyncDatabase

db = AsyncDatabase.from_env()

# DataFrame operations (NEW in 0.3.0)
df = await db.to_dataframe("users")
await db.from_dataframe(df, "users_backup")

# Admin operations (NEW in 0.3.0)
await db.vacuum("users", analyze=True)
await db.create_index("users", "email", unique=True)

# Backup operations (NEW in 0.3.0)
await db.pg_dump("backup.dump")
await db.copy_to_csv("users", "users.csv")

# Role management (NEW in 0.3.0)
await db.create_role("analyst", password="secret")
await db.grant("SELECT", "users", "analyst")
```

## Resilience (NEW in 0.3.0)

Automatic retry with exponential backoff for transient connection failures:

```python
from pycopg import Database, Config

# Connection retries automatically (3 attempts, 1-10s backoff)
db = Database.from_env()

# Configure statement timeout to prevent runaway queries
config = Config.from_env()
config.statement_timeout = 30000  # 30 seconds
db = Database(config)
```
```

### Pattern 4: Sphinx Documentation Update
**What:** Update conf.py version, rebuild docs, update content with new features
**When to use:** Every release
**Example:**
```python
# docs/conf.py
project = 'pycopg'
release = '0.3.0'  # Update this

# Rebuild docs
# cd docs && make clean && make html
```

### Pattern 5: Version Bump and Tagging
**What:** Update version in pyproject.toml, commit, tag, push
**When to use:** Final step before release
**Example:**
```bash
# 1. Update pyproject.toml
sed -i 's/version = "0.2.0"/version = "0.3.0"/' pyproject.toml

# 2. Update docs/conf.py
sed -i "s/release = '0.2.0'/release = '0.3.0'/" docs/conf.py

# 3. Rebuild Sphinx docs
cd docs && make clean && make html && cd ..

# 4. Commit all changes
git add pyproject.toml docs/conf.py CHANGELOG.md MIGRATION.md README.md docs/
git commit -m "chore: release v0.3.0"

# 5. Create and push tag
git tag -a v0.3.0 -m "Release v0.3.0: Async parity, resilience, bug fixes"
git push origin main
git push origin v0.3.0  # Triggers GitHub publish workflow
```

### Anti-Patterns to Avoid
- **Incomplete breaking change documentation:** Every breaking change MUST have before/after examples in MIGRATION.md
- **Missing version bumps:** Must update BOTH pyproject.toml and docs/conf.py, not just one
- **Vague changelog entries:** "Various fixes" is useless - list specific changes with issue/PR references
- **Stale API reference:** Sphinx autodoc won't catch methods not documented - verify all new async methods appear
- **Forgetting to rebuild docs:** HTML must be regenerated, not just markdown updated

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Changelog parsing | Custom parser | keepachangelog format | Standard format, tools exist, readable |
| Version bumping | Bash scripts | hatch version or manual | hatchling already used, simple manual process |
| API documentation | Custom HTML generator | Sphinx autodoc | Extracts from docstrings, stays in sync |
| PyPI publishing | Manual twine upload | GitHub Actions trusted publishing | No secrets, audit trail, already configured |
| Migration guide automation | Custom differ | Manual before/after examples | Users need human explanation, not diffs |

**Key insight:** Documentation and release workflows benefit from standards over automation. Users need clarity and correctness more than automation speed.

## Common Pitfalls

### Pitfall 1: Forgetting to Create _static Directory for Sphinx
**What goes wrong:** Sphinx build fails with "WARNING: html_static_path entry '_static' does not exist"
**Why it happens:** conf.py references `html_static_path = ['_static']` but directory doesn't exist
**How to avoid:** Create `docs/_static/` directory (can be empty) before building
**Warning signs:** Sphinx build warnings about missing _static path

### Pitfall 2: Version Mismatch Between pyproject.toml and conf.py
**What goes wrong:** PyPI package shows different version than documentation
**Why it happens:** Updating one file but forgetting the other
**How to avoid:** Update both files in same commit, verify with `grep -n "version\|release" pyproject.toml docs/conf.py`
**Warning signs:** Documentation footer shows old version after release

### Pitfall 3: Breaking Changes Without Migration Examples
**What goes wrong:** Users upgrade and code breaks with no clear fix
**Why it happens:** Changelog lists breaking change but no upgrade path
**How to avoid:** Every breaking change MUST have before/after code in MIGRATION.md
**Warning signs:** GitHub issues asking "how do I migrate from X to Y?"

### Pitfall 4: Incomplete Async Method Documentation
**What goes wrong:** New async methods exist in code but missing from docs
**Why it happens:** Assuming autodoc catches everything automatically
**How to avoid:** Manually verify all new methods appear in built HTML docs, check `docs/_build/html/api-reference.html`
**Warning signs:** Methods exist in code but not in search index or API reference

### Pitfall 5: Publishing Without Rebuilding Sphinx Docs
**What goes wrong:** ReadTheDocs or hosted docs show old API reference
**Why it happens:** Updated markdown but didn't run `make html`
**How to avoid:** Always rebuild with `cd docs && make clean && make html` before committing
**Warning signs:** API reference missing new methods after deployment

### Pitfall 6: Forgetting to Push Git Tags
**What goes wrong:** GitHub Actions workflow doesn't trigger, no PyPI release
**Why it happens:** `git push` without `--tags` or explicit tag push
**How to avoid:** Use `git push origin v0.3.0` explicitly or `git push --follow-tags`
**Warning signs:** Tag exists locally (`git tag -l`) but not on GitHub

### Pitfall 7: CHANGELOG Date Placeholder
**What goes wrong:** Release published with "YYYY-MM-DD" in changelog
**Why it happens:** Forgot to replace date placeholder before release
**How to avoid:** Final release checklist step: verify changelog date is actual release date
**Warning signs:** Published changelog shows "TBD" or placeholder dates

### Pitfall 8: Trusted Publishing Not Configured on PyPI
**What goes wrong:** GitHub Actions publish job fails with authentication error
**Why it happens:** PyPI project doesn't have GitHub publisher configured
**How to avoid:** Configure trusted publisher on PyPI before first automated release
**Warning signs:** Workflow error: "Trusted publishing exchange failure"

## Code Examples

Verified patterns from official sources:

### Sphinx Autodoc Configuration (Already Configured)
```python
# Source: https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html
# docs/conf.py (existing, verified correct)

import sys
import os
sys.path.insert(0, os.path.abspath('..'))

extensions = [
    'myst_parser',
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
    'sphinx.ext.napoleon',
    'sphinx.ext.intersphinx',
    'sphinx_copybutton',
]

autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'show-inheritance': True,
}
```

### Keep a Changelog Format Header
```markdown
# Source: https://keepachangelog.com/en/1.1.0/

# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-02-XX

### Added
- New features

### Changed
- **BREAKING:** Breaking changes with bold marker

### Fixed
- Bug fixes

### Deprecated
- Soon-to-be removed features

### Removed
- Removed features

### Security
- Security fixes
```

### Trusted Publishing Workflow (Already Configured, Verified)
```yaml
# Source: https://docs.pypi.org/trusted-publishers/using-a-publisher/
# .github/workflows/publish.yml (existing, verified correct)

name: Publish to PyPI

on:
  release:
    types: [published]
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install build dependencies
        run: pip install build
      - name: Build package
        run: python -m build
      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/

  publish:
    needs: build
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write  # REQUIRED for trusted publishing
    steps:
      - name: Download artifacts
        uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

### Hatchling Version Bump Commands
```bash
# Source: https://hatch.pypa.io/1.16/version/
# Manual version bump (recommended for controlled releases)

# Option 1: Direct edit
sed -i 's/version = "0.2.0"/version = "0.3.0"/' pyproject.toml

# Option 2: Hatch CLI (if installed)
hatch version minor  # 0.2.0 → 0.3.0
hatch version patch  # 0.3.0 → 0.3.1
hatch version major  # 0.3.0 → 1.0.0

# Verify version
grep "^version" pyproject.toml
```

### Migration Guide Template
```markdown
# Source: https://github.com/openai/openai-python/discussions/742
# MIGRATION.md

# Migration Guide: v0.2.0 → v0.3.0

## Overview

Version 0.3.0 achieves full async/sync parity, adds resilience features, and includes one breaking change.

## Breaking Changes

### [Breaking Change Title]

**Impact:** [Who is affected]

**Before (0.2.0):**
```python
# Old code that breaks
```

**After (0.3.0):**
```python
# New code that works
```

**Why this changed:** [Rationale]

## New Features

### [Feature Name]

**What it does:** [Description]

**Example:**
```python
# Code example
```

## Deprecations

None in 0.3.0.

## Upgrade Checklist

- [ ] Review breaking changes above
- [ ] Update code using `from_geodataframe()` to handle CRS explicitly
- [ ] Test async DataFrame/admin methods if using AsyncDatabase
- [ ] Optional: Configure `statement_timeout` for query protection
- [ ] Run test suite to verify compatibility
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual API docs in RST | Sphinx autodoc with type hints | ~2020 | Docs stay in sync with code |
| Token-based PyPI publishing | Trusted publishing (OIDC) | 2023 | No secrets, better security |
| reStructuredText (.rst) docs | Markdown with MyST parser | ~2021 | More readable, GitHub compatible |
| Freeform changelogs | Keep a Changelog format | ~2017 | Structured, parseable, consistent |
| Manual version bumping | Semantic release automation | ~2022 | Optional - manual still common for libraries |

**Deprecated/outdated:**
- **setup.py builds**: Replaced by PEP 517 build backends (hatchling, flit)
- **Manual twine upload**: Replaced by GitHub Actions trusted publishing
- **Read the Docs custom build configs**: .readthedocs.yaml v2 is standard

## Open Questions

1. **ReadTheDocs integration status**
   - What we know: pyproject.toml lists `Documentation = "https://pycopg.readthedocs.io"`
   - What's unclear: Is project actually connected to ReadTheDocs? Need to verify or update URL
   - Recommendation: Verify ReadTheDocs connection before release, update URL in pyproject.toml if needed

2. **PyPI trusted publisher configuration**
   - What we know: Workflow configured for trusted publishing with `id-token: write`
   - What's unclear: Is pycopg project on PyPI configured with GitHub as trusted publisher?
   - Recommendation: Verify PyPI settings at https://pypi.org/manage/project/pycopg/settings/publishing/ before release

3. **Release date for 0.3.0**
   - What we know: All code complete, tests pass
   - What's unclear: Target release date for changelog
   - Recommendation: Set date when creating CHANGELOG.md, coordinate with project owner

## Sources

### Primary (HIGH confidence)
- [Sphinx autodoc documentation](https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html) - Autodoc configuration
- [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) - Changelog format standard
- [PyPI Trusted Publishing docs](https://docs.pypi.org/trusted-publishers/using-a-publisher/) - OIDC publishing setup
- [Python Packaging User Guide - Publishing with GitHub Actions](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/) - Workflow patterns
- [Semantic Versioning 2.0.0](https://semver.org/) - Version numbering standard
- [Hatch documentation](https://hatch.pypa.io/1.16/version/) - Version management with hatchling

### Secondary (MEDIUM confidence)
- [Read the Docs - Deploying Sphinx](https://docs.readthedocs.com/platform/stable/intro/sphinx.html) - RTD integration (if needed)
- [Python Package Guide - Creating New Versions](https://www.pyopensci.org/python-package-guide/package-structure-code/python-package-versions.html) - Version bump workflow
- [Inventive HQ - Python PyPI Publishing Guide](https://inventivehq.com/blog/python-pypi-publishing-guide) - Trusted publishing examples

### Tertiary (LOW confidence)
- Migration guide examples from various projects (OpenAI, Django, Deepgram) - Patterns for before/after examples

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All tools already configured, just need content updates
- Architecture: HIGH - Patterns verified from official docs and existing project structure
- Pitfalls: HIGH - Common issues well-documented in Sphinx/PyPI communities

**Research date:** 2026-02-11
**Valid until:** 60 days - Documentation tooling stable, changelog format unchanging
