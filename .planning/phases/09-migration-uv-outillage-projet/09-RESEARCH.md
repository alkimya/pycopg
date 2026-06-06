# Phase 9: Migration uv (outillage projet) — Research

**Researched:** 2026-06-06
**Domain:** Python project tooling — uv, PEP 735, GitHub Actions CI, Makefile
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** Migrate dev deps (pytest, pytest-cov, pytest-asyncio, black, ruff) from `[project.optional-dependencies].dev` to **PEP 735 `[dependency-groups].dev`**.
- **D-02:** Clean removal of `[project.optional-dependencies].dev` — no dual source of truth, no `pip install pycopg[dev]` compat.
- **D-03:** Contributor command = `uv sync --all-extras --dev`.
- **D-04:** **Create** `.github/workflows/tests.yml` (no existing test workflow — only publish.yml).
- **D-05:** CI Postgres service = `timescale/timescaledb-ha` image (PostGIS + TimescaleDB in one).
- **D-06:** Python matrix 3.11 / 3.12 / 3.13, interpreters via `uv python install`.
- **D-07:** Job runs `uv sync` then `uv run pytest`; coverage gate stays `--cov-fail-under=70`.
- **D-08:** Contributor doc artifacts = CLAUDE.md + README "Development" section + Makefile.
- **D-09:** Fix CLAUDE.md: stale path `solaris/pycopg` → `/home/loc/workspace/pycopg`; replace `pip install -e ".[all,dev]"` + `venv/` activation by uv commands; bump version mention.
- **D-10:** Makefile with uv targets (install, test, lint, format, build) — thin wrappers.
- **D-11:** README: add "Development" section (uv commands); keep "Installation" with `pip install pycopg`.
- **D-12:** Doc references only `uv sync` / `.venv/`; old `venv/` not forcibly deleted (gitignored).
- **D-13:** Replace `setup-python@v5` + `pip install build` + `python -m build` with `astral-sh/setup-uv` + `uv build` in publish.yml.
- **D-14:** `publish` job unchanged: `pypa/gh-action-pypi-publish@release/v1` + trusted publishing OIDC kept. Verify `uv build` produces valid wheel + sdist.
- **D-15:** GitHub Actions Node 20→24 bump **deferred to Phase 15**. Phase 9 uses recent action versions for new code only.

### Claude's Discretion

High autonomy on implementation details (precedent Phase 1 "autonomie max"). Autonomous on:
- `uv.lock` initial generation and exact content.
- `.python-version` value (default **3.12** to match RTD/publish).
- `[tool.uv]` section in pyproject if useful.
- Makefile targets and exact wording.
- Exact uv command wording in CLAUDE.md / README.
- Postgres service config details in tests.yml (healthcheck, env vars, DB creation, extension activation).
- GitHub Actions tag versions for new code.

### Deferred Ideas (OUT OF SCOPE)

- GitHub Actions Node 20→24 bump on existing workflows — planned Phase 15 (D-15).
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TOOL-01 | Contributor can set up dev env with `uv sync --all-extras --dev` (pyproject configured for uv) | PEP 735 `[dependency-groups]` syntax, D-01/D-02 migration pattern |
| TOOL-02 | Repository ships committed `uv.lock` and `.python-version` | uv lock semantics, .python-version pin, git commit strategy |
| TOOL-03 | CI test workflow runs under uv and passes | `.github/workflows/tests.yml` design: setup-uv + Postgres service + uv sync + uv run pytest |
| TOOL-04 | CI publish workflow builds via `uv build` (wheel + sdist), hatchling backend, trusted publishing kept | publish.yml build-job migration, uv build output compatibility |
| TOOL-05 | Contributor docs (CLAUDE.md, Makefile, Development section) use uv commands; end-user docs keep pip | CLAUDE.md rewrite, README Development section, Makefile thin wrappers |
</phase_requirements>

---

## Summary

Phase 9 is a pure tooling/CI/documentation phase — no `pycopg/*.py` source changes. It migrates the project management toolchain from classic `venv`/`pip install build` to `uv` across three surfaces: (1) the `pyproject.toml` dependency model, (2) a new CI test workflow, and (3) contributor documentation.

The central `pyproject.toml` change is moving dev deps from `[project.optional-dependencies].dev` (a published extra) into the PEP 735 `[dependency-groups].dev` table (a local-only dev concept). This is a clean break — the old `dev` extra is deleted entirely. uv natively understands both `[project.optional-dependencies]` (installable with `--all-extras`) and `[dependency-groups]` (installable with `--dev`), making `uv sync --all-extras --dev` the single contributor setup command.

The biggest new artifact is `.github/workflows/tests.yml`: the project has no CI test coverage today. This workflow must wire up a `timescale/timescaledb-ha` Postgres service container, create the `pycopg_test` database and its extensions via a `psql` step, install the project via `uv sync --locked --all-extras --dev`, and run `uv run pytest`. The `publish.yml` build job gets a simpler change: swap `setup-python + pip install build + python -m build` for `astral-sh/setup-uv + uv build`.

**One critical version correction:** CONTEXT.md D-13 references `astral-sh/setup-uv@v6`. This tag **does not exist**. The action is at v8.2.0 (released 2026-06-03) and stopped publishing major/minor floating tags at v8.0.0. Use a full-version tag (`@v8.2.0`) or commit SHA.

**Primary recommendation:** Follow the exact patterns below — PEP 735 `[dependency-groups]`, `uv sync --locked --all-extras --dev` in CI, pinned `astral-sh/setup-uv@v8.2.0`, and `psql` step for DB/extension setup.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Dev environment setup | Local (contributor machine) | — | `uv sync --all-extras --dev` runs locally |
| Dependency resolution / lockfile | uv (pyproject.toml + uv.lock) | — | uv owns the lock; hatchling owns the build |
| CI test execution | GitHub Actions runner | Postgres service container | Runner runs uv/pytest; service provides real PG |
| CI build (wheel + sdist) | GitHub Actions runner (uv build) | — | uv invokes hatchling backend |
| CI publish | GitHub Actions runner (pypa/gh-action-pypi-publish) | — | Trusted publishing OIDC kept unchanged |
| Postgres + PostGIS + TimescaleDB (CI) | Docker service container | — | `timescale/timescaledb-ha` provides all three |
| Contributor commands | Makefile (thin wrapper) | CLAUDE.md / README (docs) | Make targets delegate to `uv run` |

---

## Standard Stack

### Core Tools

| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| uv | 0.9.26 (installed locally) | Project manager: venv, deps, lock, build | Canonical uv per astral-sh; replaces pip+venv+build |
| hatchling | (keep current) | Build backend | Locked decision — uv-compatible, trusted-publishing-wired |
| PEP 735 `[dependency-groups]` | — | Dev-only dependency table | Standard spec accepted in Python 3.13+, supported by uv 0.4.27+ |

### Dev Dependencies (migrating to `[dependency-groups].dev`)

Current versions verified against PyPI 2026-06-06:

| Package | Current spec | Latest | Notes |
|---------|-------------|--------|-------|
| pytest | >=7.0.0 | 9.0.3 | [VERIFIED: PyPI] Keep `>=7.0.0` specifier or tighten to `>=8.0` |
| pytest-cov | >=4.0.0 | 7.1.0 | [VERIFIED: PyPI] |
| pytest-asyncio | >=0.23.0 | 1.4.0 | [VERIFIED: PyPI] `asyncio_mode = "auto"` still works in 1.4.0 |
| black | >=23.0.0 | 26.5.1 | [VERIFIED: PyPI] |
| ruff | >=0.1.0 | 0.15.16 | [VERIFIED: PyPI] |

### GitHub Actions

| Action | Pinned Version | Purpose |
|--------|---------------|---------|
| actions/checkout | @v4 | Checkout repo |
| astral-sh/setup-uv | @v8.2.0 | Install uv, manage Python, cache |
| actions/upload-artifact | @v4 | Upload dist/ |
| actions/download-artifact | @v4 | Download dist/ |
| pypa/gh-action-pypi-publish | @release/v1 | Trusted publishing (unchanged) |

**Warning — D-13 version correction:** `astral-sh/setup-uv@v6` referenced in CONTEXT.md D-13 **does not exist**. The action moved from v7.x to v8.x (March 2026), stopped publishing floating major/minor tags at v8.0.0. The latest stable full-version tag is `v8.2.0` (2026-06-03). [VERIFIED: github.com/astral-sh/setup-uv/tags]

### CI Service Image

| Image | Tag pattern | Includes | Notes |
|-------|------------|---------|-------|
| timescale/timescaledb-ha | `pg17` (latest stable PG17) | PostgreSQL + TimescaleDB + PostGIS + Patroni | [CITED: github.com/timescale/timescaledb-docker-ha] |

---

## Package Legitimacy Audit

> slopcheck was unavailable on this machine (pip/pip3 not on PATH). All packages below are tagged `[ASSUMED]` by provenance rule. The packages are all well-established PyPI packages with multi-year history — risk is negligible, but the planner must gate each install behind a `checkpoint:human-verify` task before committing.

| Package | Registry | Notes | slopcheck | Disposition |
|---------|----------|-------|-----------|-------------|
| pytest | PyPI | 9+ years, 200M+ downloads/month | unavailable | `[ASSUMED]` — industry standard |
| pytest-cov | PyPI | 10+ years, coverage plugin | unavailable | `[ASSUMED]` — industry standard |
| pytest-asyncio | PyPI | 7+ years, asyncio plugin | unavailable | `[ASSUMED]` — industry standard |
| black | PyPI | PSF-maintained formatter | unavailable | `[ASSUMED]` — industry standard |
| ruff | PyPI | astral-sh, Rust linter | unavailable | `[ASSUMED]` — industry standard |
| uv | not PyPI | Installed as binary from astral-sh | unavailable | `[ASSUMED]` — project already uses it |

**Packages removed due to [SLOP]:** none
**Packages flagged [SUS]:** none (all well-known tools, risk is the missing slopcheck verification)

*All packages above tagged `[ASSUMED]` — planner inserts `checkpoint:human-verify` before install. In practice these are all industry-standard tools and the checkpoint is a formality.*

---

## Architecture Patterns

### System Architecture Diagram

```
Contributor
    │
    ├── uv sync --all-extras --dev
    │       │
    │       └── resolves [project.optional-dependencies] (dotenv/geo/all)
    │               + [dependency-groups].dev (pytest/pytest-cov/ruff/black/...)
    │               └── writes .venv/  (gitignored)
    │
    └── make test / make lint / make build
            │
            └── delegates to: uv run pytest / uv run ruff / uv build
                                    │                           │
                                    └── uses .venv              └── writes dist/


CI (tests.yml)                              CI (publish.yml)
    │                                           │
    ├── services:                               ├── astral-sh/setup-uv@v8.2.0
    │   └── postgres: timescaledb-ha:pg17       │       └── uv build
    │                                           │               └── dist/*.whl + dist/*.tar.gz
    ├── strategy.matrix: [3.11, 3.12, 3.13]    │
    │                                           └── pypa/gh-action-pypi-publish
    ├── astral-sh/setup-uv@v8.2.0                  (trusted publishing OIDC, unchanged)
    │       python-version: ${{ matrix.python-version }}
    │       enable-cache: true
    │
    ├── psql step: CREATE DATABASE pycopg_test
    │             CREATE EXTENSION postgis
    │             CREATE EXTENSION timescaledb
    │
    └── uv sync --locked --all-extras --dev
            └── uv run pytest
                    └── pyproject.toml addopts: --cov-fail-under=70 honored automatically
```

### Recommended Project Structure (new files)

```
/
├── .python-version          # NEW — pins local dev Python (3.12)
├── uv.lock                  # NEW — universal lockfile, committed
├── Makefile                 # NEW — thin uv wrappers
├── pyproject.toml           # MODIFIED — add [dependency-groups], remove [opt-deps].dev
├── CLAUDE.md                # MODIFIED — fix path, version, commands
├── README.md                # MODIFIED — add Development section
└── .github/
    └── workflows/
        ├── tests.yml        # NEW — CI test workflow under uv
        └── publish.yml      # MODIFIED — build job uses uv build
```

### Pattern 1: PEP 735 `[dependency-groups]` in pyproject.toml

**What:** Dev deps table that is NOT published in the wheel/sdist metadata. Purely local.
**When to use:** Any deps only needed by contributors, not by library users.

```toml
# Source: peps.python.org/pep-0735 + docs.astral.sh/uv
[dependency-groups]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "pytest-asyncio>=0.23.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
]
```

**Critical:** Remove `[project.optional-dependencies].dev` entirely. They are mutually exclusive conceptually (D-02). Build backends (hatchling) MUST NOT include `[dependency-groups]` in wheel metadata — this is guaranteed by PEP 735 spec. [CITED: peps.python.org/pep-0735]

**How uv resolves both:**
- `--all-extras` installs all `[project.optional-dependencies]` (dotenv, geo, timescale, all)
- `--dev` installs `[dependency-groups].dev`
- Combined: `uv sync --all-extras --dev` = full contributor environment [CITED: docs.astral.sh/uv/concepts/projects/dependencies]

### Pattern 2: uv.lock and .python-version

**`uv.lock`:**
- Generated by `uv lock` (or implicitly by `uv sync`)
- Universal/cross-platform: captures all markers (os, arch, python version) in one file
- Must be committed to git
- In CI, use `uv sync --locked` (fails if lockfile is out of date) rather than `uv sync --frozen` (silently uses stale lockfile) [CITED: docs.astral.sh/uv/concepts/projects/sync]

**`.python-version`:**
- Contains a single Python version string, e.g. `3.12`
- Created by `uv python pin 3.12`
- Sets the default Python for `uv sync` / `uv run` on the developer machine
- In CI, the matrix `python-version` input to `astral-sh/setup-uv` **overrides** `.python-version` per job
- Should be committed [CITED: docs.astral.sh/uv/concepts/python-versions]
- Value: **3.12** (matches RTD build, publish.yml, Claude's Discretion)

### Pattern 3: `.github/workflows/tests.yml` structure

**Key constraints derived from conftest.py + setup_test_db.py:**
- Tests connect via `PGHOST`, `PGUSER`, `PGPASSWORD`, `PGPORT` env vars
- Database name is hardcoded: `pycopg_test`
- Database must be created explicitly (not via `POSTGRES_DB`) — `setup_test_db.py` runs `CREATE DATABASE pycopg_test`
- PostGIS tests check `has_postgis()` at runtime and skip gracefully if absent
- TimescaleDB tests in `test_async_database.py` use mocks — no real extension needed for most; `test_postgis_errors.py` skips if PostGIS absent

```yaml
# Source: docs.astral.sh/uv/guides/integration/github + docs.github.com (service containers)
name: Tests

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]

    services:
      postgres:
        image: timescale/timescaledb-ha:pg17
        env:
          POSTGRES_PASSWORD: postgres
          POSTGRES_USER: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v8.2.0
        with:
          python-version: ${{ matrix.python-version }}
          enable-cache: true

      - name: Install dependencies
        run: uv sync --locked --all-extras --dev

      - name: Set up test database
        env:
          PGPASSWORD: postgres
        run: |
          psql -h localhost -U postgres -c "CREATE DATABASE pycopg_test;"
          psql -h localhost -U postgres -d pycopg_test -c "CREATE EXTENSION IF NOT EXISTS postgis;"
          psql -h localhost -U postgres -d pycopg_test -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"

      - name: Run tests
        env:
          PGHOST: localhost
          PGUSER: postgres
          PGPASSWORD: postgres
          PGPORT: "5432"
        run: uv run pytest
```

**Why `timescale/timescaledb-ha:pg17`:** The `-ha` variant ships PostGIS + TimescaleDB + Patroni in one image, confirmed by official repo. Tag `pg17` pins PostgreSQL 17 (latest stable). [CITED: github.com/timescale/timescaledb-docker-ha]

### Pattern 4: publish.yml build job migration

**Before (current):**
```yaml
- uses: actions/setup-python@v5
  with:
    python-version: "3.12"
- run: pip install build
- run: python -m build
```

**After (D-13):**
```yaml
- uses: astral-sh/setup-uv@v8.2.0
- run: uv build
```

`uv build` with hatchling backend produces both `dist/*.whl` and `dist/*.tar.gz` by default. Output directory is `dist/` — same path that the existing `actions/upload-artifact` step already references. The `publish` job (`pypa/gh-action-pypi-publish@release/v1`) downloads from `dist/` — unchanged. [CITED: docs.astral.sh/uv/concepts/projects/build]

### Pattern 5: Makefile thin wrappers

```makefile
.PHONY: install test lint format build

install:
	uv sync --all-extras --dev

test:
	uv run pytest

lint:
	uv run ruff check pycopg tests

format:
	uv run black pycopg tests
	uv run ruff check --fix pycopg tests

build:
	uv build
```

Conventions: `.PHONY` for all action targets, TAB indentation required, thin delegation — no logic in Makefile. [ASSUMED based on Python Makefile conventions]

### Anti-Patterns to Avoid

- **`uv sync --frozen` in CI:** Silently uses stale lockfile if out of date. Use `--locked` instead (fails fast on mismatch). [CITED: docs.astral.sh/uv]
- **`pip install pycopg[dev]` in contributor docs:** Invalid after D-02 removes the `dev` extra. Replace with `uv sync --all-extras --dev`.
- **Mounting scripts to `/docker-entrypoint-initdb.d/` in CI:** The `timescaledb-ha` image may overwrite or conflict with custom init scripts in that directory. Use a separate `psql` step after the service is healthy instead. [CITED: github.com/timescale/timescaledb-docker-ha issues]
- **Dual source of truth for dev deps:** Keeping both `[project.optional-dependencies].dev` AND `[dependency-groups].dev`. D-02 mandates clean removal of the former.
- **`@v6` for astral-sh/setup-uv:** Tag does not exist. Use `@v8.2.0` or a commit SHA.
- **Using `uv python install` as a separate step when setup-uv handles it:** The `python-version` input to `astral-sh/setup-uv` installs the Python version automatically; no separate `uv python install` step needed.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Lockfile generation | Custom lock scripts | `uv lock` | uv produces a cross-platform universal lockfile |
| Python version management in CI | Custom pyenv/asdf scripts | `astral-sh/setup-uv` `python-version` input | Action installs + configures uv Python automatically |
| Wheel + sdist packaging | Custom setup.py scripts | `uv build` (delegates to hatchling) | Handles build isolation, both formats, correct metadata |
| Dev dep isolation from package metadata | `[project.optional-dependencies]` for dev | `[dependency-groups]` (PEP 735) | Optional deps are published to PyPI; dependency groups are not |

**Key insight:** uv is both the package manager and the build frontend. Using it consistently across local dev and CI eliminates the matrix of tools (venv + pip + build + pip-tools) that existed before.

---

## Common Pitfalls

### Pitfall 1: `astral-sh/setup-uv@v6` Does Not Exist

**What goes wrong:** Workflow fails with "action not found" or resolves to an unexpected version.
**Why it happens:** CONTEXT.md D-13 references `@v6`. The action went from v7.x to v8.x in March 2026 and simultaneously stopped publishing floating major/minor tags. There is no `v6` tag on the repository.
**How to avoid:** Use `astral-sh/setup-uv@v8.2.0` (the latest full-version tag as of 2026-06-06).
**Warning signs:** `Error: Unable to resolve action astral-sh/setup-uv@v6` in GitHub Actions log.
[VERIFIED: github.com/astral-sh/setup-uv/tags]

### Pitfall 2: timescaledb-ha CI Startup Issues

**What goes wrong:** The timescaledb-ha image has had known startup panics in GitHub Actions environments (`timescaledb-tune` panic: "bytes must be at least 1 byte (got 0)") in specific versions.
**Why it happens:** `timescaledb-tune` reads system memory; GitHub-hosted runners may return unexpected values. Affects some `-ha` versions with pg15/pg16.
**How to avoid:** Pin to the `pg17` tag (latest; the pg16 issue was in `pg16.3-ts2.15.2`, not in pg17 series). If pg17 causes issues, fallback: pin to a specific version tag like `pg17-ts2.19.0-oss` or switch to `timescale/timescaledb:latest-pg17` (lighter, but confirm PostGIS inclusion separately).
**Warning signs:** Container health check never passes; logs show panic in timescaledb-tune.

### Pitfall 3: Mounting initdb.d Scripts Breaks the HA Image

**What goes wrong:** Custom SQL initialization scripts mounted to `/docker-entrypoint-initdb.d/` can overwrite or displace the TimescaleDB init scripts, preventing extension installation.
**Why it happens:** The HA image copies its own scripts to that directory during initialization; a volume mount can replace them.
**How to avoid:** Do not mount init scripts via Docker volumes. Instead, add a separate step after the healthcheck passes that runs `psql` commands directly: `CREATE DATABASE pycopg_test; CREATE EXTENSION IF NOT EXISTS postgis; CREATE EXTENSION IF NOT EXISTS timescaledb;`
**Warning signs:** `ERROR: extension "timescaledb" does not exist` in tests.

### Pitfall 4: `dev` Extra Still Referenced After Removal

**What goes wrong:** CLAUDE.md or README still shows `pip install pycopg[dev]` or `uv pip install pycopg[dev]`, which fails after D-02 removes the extra.
**Why it happens:** Stale contributor docs.
**How to avoid:** D-09 rewrites CLAUDE.md entirely; D-11 adds a fresh Development section. Grep all docs for `[dev]` before closing the phase.
**Warning signs:** `ERROR: No such extra 'dev'` when a contributor follows old docs.

### Pitfall 5: `uv sync --frozen` vs `--locked` in CI

**What goes wrong:** CI installs from a stale lockfile without failing.
**Why it happens:** `--frozen` skips lockfile validation. A committed but outdated `uv.lock` silently installs wrong versions.
**How to avoid:** Always use `uv sync --locked` in CI. This fails if `uv.lock` would change.
**Warning signs:** CI green but tests fail locally; `uv lock` generates a diff on the lockfile.

### Pitfall 6: `--cov-fail-under=70` in `addopts` Already in pyproject.toml

**What goes wrong:** Some CI setups pass explicit `pytest` flags that override or duplicate `addopts`.
**Why it happens:** Misunderstanding that `uv run pytest` respects `[tool.pytest.ini_options]` in `pyproject.toml`.
**How to avoid:** `uv run pytest` (with no extra flags in the workflow step) automatically picks up `addopts = "-v --cov=pycopg --cov-report=term-missing --cov-report=html --cov-fail-under=70"` from `pyproject.toml`. No extra CI flags needed.
[CITED: docs.astral.sh/uv — uv run respects pyproject config]

### Pitfall 7: uv.lock Not Committed

**What goes wrong:** CI runs `uv sync --locked` but no `uv.lock` exists → error.
**Why it happens:** `uv.lock` is generated locally but not committed.
**How to avoid:** Generate `uv.lock` locally with `uv lock` after the pyproject.toml changes, then commit both `pyproject.toml` and `uv.lock` together.
**Warning signs:** `error: No lockfile found` in CI.

---

## Code Examples

### pyproject.toml after migration (relevant sections)

```toml
# Source: peps.python.org/pep-0735 + docs.astral.sh/uv

# REMOVE entirely:
# [project.optional-dependencies]
# dev = [...]

# KEEP (these are user-facing extras, published to PyPI):
[project.optional-dependencies]
dotenv = ["python-dotenv>=1.0.0"]
geo = ["geopandas>=0.14.0", "geoalchemy2>=0.14.0", "shapely>=2.0.0"]
timescale = []
all = ["python-dotenv>=1.0.0", "geopandas>=0.14.0", "geoalchemy2>=0.14.0", "shapely>=2.0.0"]

# ADD — dev deps, NOT published:
[dependency-groups]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "pytest-asyncio>=0.23.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
]
```

### uv lock + python-version generation

```bash
# Run once after pyproject.toml changes:
uv lock                    # generates uv.lock
uv python pin 3.12         # creates .python-version with "3.12"
git add uv.lock .python-version pyproject.toml
git commit -m "chore: migrate to uv tooling (TOOL-01, TOOL-02)"
```

### publish.yml build job (after D-13)

```yaml
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v8.2.0

      - name: Build package
        run: uv build

      - name: Upload artifacts
        uses: actions/upload-artifact@v4
        with:
          name: dist
          path: dist/
```

The `publish` job below it stays completely unchanged.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `venv/` + `pip install -e ".[dev]"` | `uv sync --all-extras --dev` + `.venv/` | uv ≥0.1 (2024) | Single command, lockfile-backed |
| `[project.optional-dependencies].dev` | `[dependency-groups].dev` (PEP 735) | uv 0.4.27 (Oct 2024), pip 25.1 (Apr 2025) | Dev deps not published to PyPI |
| `pip install build` + `python -m build` | `uv build` | uv ≥0.3 (2024) | No separate install step |
| Floating action tags (`@v6`) | Full-version tags (`@v8.2.0`) | astral-sh/setup-uv v8.0.0 (Mar 2026) | Security; supply chain hardening |
| `setup-python` + manual Python install | `astral-sh/setup-uv` with `python-version` | 2024 | uv manages Python; no setup-python needed |

**Deprecated / outdated:**
- `astral-sh/setup-uv@v6`: Tag never existed; v7 and v8 are current.
- `pip install build`: Still works but uv build is the idiomatic uv-project path.
- `[project.optional-dependencies].dev` for dev-only deps: Superseded by PEP 735 `[dependency-groups]`.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `timescale/timescaledb-ha:pg17` includes PostGIS by default | Standard Stack, CI pattern | PostGIS tests skip in CI; spatial phase blocked |
| A2 | `timescale/timescaledb-ha:pg17` accepts `POSTGRES_PASSWORD` env var for initialization | CI pattern | Postgres service fails to start; CI blocked |
| A3 | `timescale/timescaledb-ha:pg17` does not have the startup panic issue seen in pg15/pg16 variants | Pitfall 2 | CI Postgres never becomes healthy |
| A4 | `CREATE EXTENSION IF NOT EXISTS timescaledb;` works via psql step after container is healthy | CI pattern | TimescaleDB extension tests fail |
| A5 | Makefile thin-wrapper conventions (targets, .PHONY) are correct for the project | Makefile pattern | Minor — easy to fix |
| A6 | All five dev packages (pytest, pytest-cov, pytest-asyncio, black, ruff) are well-known and safe | Package audit | Negligible — all industry standard |

---

## Open Questions (RESOLVED — recommendations adopted and implemented in plans 09-01/09-02)

1. **timescaledb-ha pg17 startup reliability in GitHub-hosted runners** [RESOLVED — mitigated via workflow_dispatch validation task in 09-02]
   - What we know: The pg15/pg16 versions had a documented `timescaledb-tune` panic. pg17 has not been flagged.
   - What's unclear: Whether pg17 is definitively clean on ubuntu-latest runners.
   - Recommendation: The planner should add a validation task that runs the workflow via `workflow_dispatch` before relying on a tag push (mirrors D-14 risk mitigation). If pg17 fails, fallback tag: a pinned version like `pg17-ts2.19.0-oss` or switch to `timescale/timescaledb:latest-pg17`.

2. **`uv sync --locked` vs `uv sync --frozen` naming**
   - What we know: `--locked` = fail if lockfile outdated; `--frozen` = use lockfile as-is.
   - What's unclear: The distinction is subtle; the planner and implementer must pick `--locked` for CI (see Pitfall 5).
   - Recommendation: Document in CLAUDE.md dev commands section with `--frozen` for offline use and `--locked` for CI.

3. **Whether `[tool.uv]` section is needed in pyproject.toml**
   - What we know: No `[tool.uv]` is currently in pyproject.toml. Claude has discretion on this.
   - What's unclear: Whether any uv settings (e.g., `managed = true`, index configuration) are useful for this project.
   - Recommendation: Start without `[tool.uv]`; it can be added later if needed. The planner should not plan any `[tool.uv]` tasks unless a specific need emerges.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| uv | All TOOL-0X | ✓ | 0.9.26 | — |
| Python 3.12 | Local dev (.python-version) | ✓ (uv managed) | 3.12.12 | — |
| psql client | CI DB setup step | Available on ubuntu-latest | — | Use `docker exec` to run init SQL |
| GitHub Actions | TOOL-03, TOOL-04 | ✓ | — | — |
| timescale/timescaledb-ha | TOOL-03 | To be pulled at CI runtime | pg17 | timescale/timescaledb:latest-pg17 |

**Missing dependencies with no fallback:** None blocking.
**Missing dependencies with fallback:** `timescale/timescaledb-ha:pg17` (fallback: pinned version or lighter image if startup fails).

---

## Validation Architecture

> `workflow.nyquist_validation` is absent from config.json — treated as enabled.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (already configured in pyproject.toml) |
| Config file | `pyproject.toml` — `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest` (picks up full `addopts` including `--cov-fail-under=70`) |

### Phase Requirements → Observability Map

| Req ID | Behavior to Observe | Verification Method | Automated? |
|--------|--------------------|--------------------|------------|
| TOOL-01 | `uv sync --all-extras --dev` succeeds from clean state | Run command; assert exit code 0; `.venv/` created | Yes — shell command |
| TOOL-01 | `[dependency-groups].dev` exists; `[project.optional-dependencies].dev` absent | `grep` / TOML parse | Yes — shell |
| TOOL-02 | `uv.lock` exists and is committed | `git ls-files uv.lock` returns path | Yes — shell |
| TOOL-02 | `.python-version` contains `3.12` | `cat .python-version` | Yes — shell |
| TOOL-02 | `uv sync --locked` succeeds (lockfile up to date) | Exit code 0 | Yes — shell |
| TOOL-03 | tests.yml CI workflow exists and passes | GitHub Actions green badge | Yes — CI |
| TOOL-03 | Matrix 3.11/3.12/3.13 all green | All 3 matrix jobs green | Yes — CI |
| TOOL-04 | publish.yml build job uses `uv build`, produces wheel + sdist | `dist/` contains `*.whl` and `*.tar.gz` | Yes — CI artifact |
| TOOL-04 | Trusted publishing OIDC unchanged | `pypa/gh-action-pypi-publish` present; `id-token: write` permission present | Yes — grep |
| TOOL-05 | CLAUDE.md has no `solaris/pycopg` path | `grep -c "solaris/pycopg" CLAUDE.md` = 0 | Yes — shell |
| TOOL-05 | CLAUDE.md has no `pip install -e ".[all,dev]"` | grep check | Yes — shell |
| TOOL-05 | README has "Development" section with uv commands | grep "## Development" README.md | Yes — shell |
| TOOL-05 | Makefile exists with `install`, `test`, `lint`, `format`, `build` targets | `make --dry-run install test lint format build` | Yes — shell |
| TOOL-05 | No `pip install pycopg[dev]` in any contributor doc | grep across CLAUDE.md + README.md | Yes — shell |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/ -x -q` (quick sanity; no DB required for unit tests)
- **Per wave merge:** `uv run pytest` (full suite with coverage gate)
- **Phase gate:** Full suite green + CI tests.yml green before `/gsd-verify-work`

### Wave 0 Gaps

- None in test framework — pytest + pyproject.toml config already exist.
- New artifact: `.github/workflows/tests.yml` — not testable locally without GitHub Actions; use `workflow_dispatch` as the validation method (mirrors D-14 risk mitigation).
- TOOL-01/02/05 verifications are shell commands, not pytest tests — list them as manual verification steps in PLAN.md rather than test files.

---

## Security Domain

> `security_enforcement` absent from config.json — treated as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Tooling phase, no auth changes |
| V3 Session Management | No | Tooling phase, no session changes |
| V4 Access Control | No | Tooling phase |
| V5 Input Validation | No | No user input in this phase |
| V6 Cryptography | No | No crypto in this phase |
| V14 Configuration | Yes (partial) | OIDC trusted publishing kept; no secrets added to CI |

### Known Threat Patterns for GitHub Actions / CI

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Supply chain via unpinned action tags | Tampering | Pin to full-version tags (`@v8.2.0`) or commit SHA |
| Secrets leaking via env vars | Information Disclosure | `PGPASSWORD` in step env only; no secret stored in repo |
| Dependency confusion / slopquatting | Tampering | All dev packages are well-known; slopcheck unavailable — planner adds human-verify checkpoint |

**Note:** This phase adds no new secrets. The Postgres service uses a hardcoded test password (`postgres`) — acceptable for ephemeral CI containers. PyPI trusted publishing (OIDC, D-14) continues without changes.

---

## Sources

### Primary (HIGH confidence)
- [peps.python.org/pep-0735](https://peps.python.org/pep-0735/) — PEP 735 syntax, include-group directive, build backend exclusion guarantee
- [docs.astral.sh/uv/concepts/projects/dependencies](https://docs.astral.sh/uv/concepts/projects/dependencies/) — `[dependency-groups]` in uv, `--dev` / `--all-extras` interaction
- [docs.astral.sh/uv/concepts/projects/sync](https://docs.astral.sh/uv/concepts/projects/sync/) — `--locked` vs `--frozen` semantics
- [docs.astral.sh/uv/concepts/projects/build](https://docs.astral.sh/uv/concepts/projects/build/) — `uv build` output, hatchling as build frontend delegate
- [docs.astral.sh/uv/concepts/python-versions](https://docs.astral.sh/uv/concepts/python-versions/) — `.python-version` file behavior, CI override
- [docs.astral.sh/uv/guides/integration/github](https://docs.astral.sh/uv/guides/integration/github/) — Full CI workflow pattern with matrix, `--locked`, caching
- [github.com/astral-sh/setup-uv/tags](https://github.com/astral-sh/setup-uv/tags) — Version tag audit: no v6, latest v8.2.0
- [github.com/timescale/timescaledb-docker-ha](https://github.com/timescale/timescaledb-docker-ha) — PostGIS + TimescaleDB inclusion confirmed
- [docs.github.com — Creating PostgreSQL service containers](https://docs.github.com/en/actions/use-cases-and-examples/using-containerized-services/creating-postgresql-service-containers) — Service YAML syntax, healthcheck, localhost + port mapping

### Secondary (MEDIUM confidence)
- [github.com/astral-sh/setup-uv/releases](https://github.com/astral-sh/setup-uv/releases) — v8.0.0 immutable release, floating tags removed
- [pydevtools.com — upgrade setup-uv v7 to v8](https://pydevtools.com/handbook/how-to/how-to-upgrade-setup-uv-from-v7-to-v8/) — Breaking change confirmation
- [github.com/timescale/timescaledb-docker-ha/issues/476](https://github.com/timescale/timescaledb-docker-ha/issues/476) — timescaledb-tune panic in CI with pg15/pg16
- PyPI package versions: `pytest 9.0.3`, `pytest-cov 7.1.0`, `pytest-asyncio 1.4.0`, `black 26.5.1`, `ruff 0.15.16` (verified via PyPI API 2026-06-06)

### Tertiary (LOW confidence)
- Makefile conventions — general Python community patterns [ASSUMED]
- `timescale/timescaledb-ha:pg17` startup reliability in GitHub-hosted runners — inferred from absence of pg17 issues in issue tracker; not directly confirmed [ASSUMED]

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — uv docs + PyPI verified + action tag confirmed
- Architecture patterns: HIGH — official docs for all key patterns
- CI workflow: MEDIUM-HIGH — patterns confirmed via docs; timescaledb-ha CI behavior partially assumed for pg17
- Pitfalls: HIGH — D-13 version issue is VERIFIED; timescaledb-ha issue is CITED
- Makefile: MEDIUM — conventions from community patterns

**Research date:** 2026-06-06
**Valid until:** 2026-12-06 (uv moves fast; re-verify action versions before any new workflow)
