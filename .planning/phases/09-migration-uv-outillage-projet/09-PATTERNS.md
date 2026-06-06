# Phase 9: Migration uv (outillage projet) — Pattern Map

**Mapped:** 2026-06-06
**Files analyzed:** 8 (3 created, 5 modified)
**Analogs found:** 5 / 8 (3 have no codebase analog — net-new artifact types)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pyproject.toml` (MODIFY) | config | transform | itself (existing `[project.optional-dependencies]` + `[tool.*]` tables) | exact |
| `uv.lock` (CREATE) | lockfile | — | none | no analog |
| `.python-version` (CREATE) | config | — | none | no analog |
| `.github/workflows/tests.yml` (CREATE) | CI workflow | request-response | `.github/workflows/publish.yml` | role-match |
| `.github/workflows/publish.yml` (MODIFY) | CI workflow | request-response | itself (current build job) | exact |
| `CLAUDE.md` (MODIFY) | docs | — | itself (current stale content) | exact |
| `README.md` (MODIFY) | docs | — | itself (existing section structure, lines 1-24) | exact |
| `Makefile` (CREATE) | config/utility | — | none | no analog |

---

## Pattern Assignments

### `pyproject.toml` — MODIFY (config, transform)

**Analog:** itself — `/home/loc/workspace/pycopg/pyproject.toml`

**Current `[project.optional-dependencies]` block to split** (lines 45–67):
```toml
[project.optional-dependencies]
dotenv = [
    "python-dotenv>=1.0.0",
]
geo = [
    "geopandas>=0.14.0",
    "geoalchemy2>=0.14.0",
    "shapely>=2.0.0",
]
timescale = []  # No additional deps, just PostgreSQL extension
all = [
    "python-dotenv>=1.0.0",
    "geopandas>=0.14.0",
    "geoalchemy2>=0.14.0",
    "shapely>=2.0.0",
]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "pytest-asyncio>=0.23.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
]
```

**After migration — keep user-facing extras, remove `dev` extra, add `[dependency-groups]`:**
```toml
# KEEP — user-facing extras (published to PyPI, unchanged):
[project.optional-dependencies]
dotenv = ["python-dotenv>=1.0.0"]
geo = ["geopandas>=0.14.0", "geoalchemy2>=0.14.0", "shapely>=2.0.0"]
timescale = []
all = ["python-dotenv>=1.0.0", "geopandas>=0.14.0", "geoalchemy2>=0.14.0", "shapely>=2.0.0"]

# ADD after [project.optional-dependencies] — dev deps NOT published to PyPI (PEP 735):
[dependency-groups]
dev = [
    "pytest>=7.0.0",
    "pytest-cov>=4.0.0",
    "pytest-asyncio>=0.23.0",
    "black>=23.0.0",
    "ruff>=0.1.0",
]
```

**Existing `[tool.pytest.ini_options]` to preserve unchanged** (lines 84–87):
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --cov=pycopg --cov-report=term-missing --cov-report=html --cov-fail-under=70"
asyncio_mode = "auto"
```

**Coverage gate stays at 70** — do NOT change `--cov-fail-under=70` (Phase 10 ratchet).

**Existing `[tool.coverage.*]` to preserve unchanged** (lines 89–100):
```toml
[tool.coverage.run]
source = ["pycopg"]
omit = ["*/tests/*", "*/venv/*"]

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "if TYPE_CHECKING:",
    "raise AssertionError",
    "raise NotImplementedError",
]
```

**No `[tool.uv]` section needed** — Claude's Discretion: start without it.

---

### `uv.lock` — CREATE (lockfile)

**No codebase analog.** Generated artifact — do not hand-author.

**Generation command (run locally after pyproject.toml changes):**
```bash
cd /home/loc/workspace/pycopg
uv lock
git add uv.lock
```

**Constraints:**
- Universal/cross-platform lockfile (all Python markers in one file)
- Must be committed — CI uses `uv sync --locked` which fails if absent
- Never edit by hand

---

### `.python-version` — CREATE (config)

**No codebase analog.** Single-line file.

**Content:**
```
3.12
```

**Generation command:**
```bash
uv python pin 3.12
```

**Rationale:** Matches RTD Python version (`.readthedocs.yaml`) and the `publish.yml` `python-version: "3.12"` value. CI matrix overrides this per-job via `setup-uv` `python-version` input.

---

### `.github/workflows/tests.yml` — CREATE (CI workflow, request-response)

**Analog:** `/home/loc/workspace/pycopg/.github/workflows/publish.yml`

**Structural pattern from analog** (lines 1–10 of publish.yml — top-level structure):
```yaml
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
```

**New workflow — full pattern to copy:**
```yaml
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

**Key constraints (from `tests/conftest.py` analysis):**
- Tests connect via `PGHOST`, `PGUSER`, `PGPASSWORD`, `PGPORT` env vars — all four required
- Database name `pycopg_test` must be created explicitly via `psql` step (not via `POSTGRES_DB`)
- `timescale/timescaledb-ha:pg17` — DO NOT mount scripts to `/docker-entrypoint-initdb.d/`; use the separate `psql` step instead
- `uv run pytest` (no extra flags) — picks up `addopts` including `--cov-fail-under=70` automatically from pyproject.toml
- `uv sync --locked` not `--frozen` (fails fast if lockfile out of date)
- Action version: `astral-sh/setup-uv@v8.2.0` — `@v6` tag does NOT exist

---

### `.github/workflows/publish.yml` — MODIFY (CI workflow, request-response)

**Analog:** itself — `/home/loc/workspace/pycopg/.github/workflows/publish.yml`

**Current build job to replace** (lines 9–30):
```yaml
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
```

**After migration — only the build job changes:**
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

**Publish job to keep exactly unchanged** (lines 31–46):
```yaml
  publish:
    needs: build
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write
    steps:
      - name: Download artifacts
        uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

**Node 20→24 bump on existing actions is DEFERRED to Phase 15** — do not bump `actions/checkout`, `actions/upload-artifact`, `actions/download-artifact` versions in this phase.

---

### `CLAUDE.md` — MODIFY (docs)

**Analog:** itself — `/home/loc/workspace/pycopg/CLAUDE.md`

**Current stale content to replace** (lines 12–25 — the three stale sections):
```markdown
## Version

**pycopg v0.2.0** - PostgreSQL API

## Environnement

```bash
cd /home/loc/workspace/solaris/pycopg && source venv/bin/activate

# Tests
pytest tests/ -v

# Install en mode dev
pip install -e ".[all,dev]"
```
```

**After migration — corrected content:**
```markdown
## Version

**pycopg v0.3.1** - PostgreSQL API

## Environnement

```bash
cd /home/loc/workspace/pycopg

# Install dev environment (first time or after pyproject.toml changes)
uv sync --all-extras --dev

# Tests (quick)
uv run pytest tests/ -x -q

# Tests (full suite with coverage gate)
uv run pytest

# Lint
uv run ruff check pycopg tests

# Format
uv run black pycopg tests
```
```

**Constraints:**
- Fix path: `solaris/pycopg` → `/home/loc/workspace/pycopg` (no `cd` + `source venv/activate`)
- Bump version: `v0.2.0` → `v0.3.1`
- Replace `pip install -e ".[all,dev]"` with `uv sync --all-extras --dev`
- No `pip install pycopg[dev]` anywhere in the file after edit

---

### `README.md` — MODIFY (docs)

**Analog:** itself — `/home/loc/workspace/pycopg/README.md`

**Existing "Installation" section to preserve unchanged** (lines 10–24):
```markdown
## Installation

```bash
# Basic installation
pip install pycopg

# With .env file support
pip install pycopg[dotenv]

# With PostGIS support
pip install pycopg[geo]

# Full installation (all optional dependencies)
pip install pycopg[all]
```
```

**New "Development" section to add** (insert after "Installation", before "Quick Start" or at end — planner decides position):
```markdown
## Development

Contributors use [uv](https://docs.astral.sh/uv/) for project management.

```bash
# Clone and set up dev environment
git clone https://github.com/alkimya/pycopg.git
cd pycopg
uv sync --all-extras --dev

# Run tests
uv run pytest

# Lint
uv run ruff check pycopg tests

# Format
uv run black pycopg tests

# Build wheel + sdist
uv build
```
```

**Boundary to maintain:** Installation section = `pip install pycopg` (end users). Development section = `uv` (contributors). Never mix the two.

---

### `Makefile` — CREATE (utility/config)

**No codebase analog.** Follows standard Python project Makefile conventions.

**Full content pattern:**
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

**Critical convention:** Indentation MUST be TAB characters (not spaces) — Make requirement.

---

## Shared Patterns

### uv as the single contributor entrypoint
**Applies to:** CLAUDE.md, README.md Development section, Makefile
**Command:** `uv sync --all-extras --dev` (combines `--all-extras` for user-facing extras + `--dev` for `[dependency-groups].dev`)
**Rule:** No `pip install`, no `source venv/activate`, no `python -m ...` in contributor docs.

### astral-sh/setup-uv@v8.2.0 as the CI uv installer
**Source:** RESEARCH.md §Standard Stack / §Pattern 3 and §Pattern 4
**Applies to:** `.github/workflows/tests.yml` (new), `.github/workflows/publish.yml` (modified)
**Critical:** `@v6` does not exist. Use `@v8.2.0` (full-version tag, immutable).
```yaml
- name: Install uv
  uses: astral-sh/setup-uv@v8.2.0
  with:
    python-version: ${{ matrix.python-version }}  # tests.yml only
    enable-cache: true                             # tests.yml only
```

### `--locked` in CI sync
**Applies to:** `.github/workflows/tests.yml`
**Rule:** Always `uv sync --locked` (not `--frozen`) so CI fails fast if `uv.lock` is stale.

### `[dependency-groups]` vs `[project.optional-dependencies]` boundary
**Applies to:** `pyproject.toml`
**Rule:** User-facing extras (`dotenv`, `geo`, `timescale`, `all`) stay in `[project.optional-dependencies]` — they are published to PyPI. Dev deps (`pytest`, `ruff`, etc.) go in `[dependency-groups].dev` — NOT published. Never put dev tools in `[project.optional-dependencies]`.

### Postgres service env vars (from conftest.py)
**Applies to:** `.github/workflows/tests.yml`
**Required env vars for test run step:** `PGHOST=localhost`, `PGUSER=postgres`, `PGPASSWORD=postgres`, `PGPORT=5432`
**Required DB setup:** `CREATE DATABASE pycopg_test` + `CREATE EXTENSION IF NOT EXISTS postgis` + `CREATE EXTENSION IF NOT EXISTS timescaledb` via `psql` step (not init scripts).

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `uv.lock` | lockfile | — | No lockfile in repo today; generated artifact, committed but never hand-authored |
| `.python-version` | config | — | No Python version pin file exists; one-line generated file (`uv python pin 3.12`) |
| `Makefile` | utility | — | No Makefile in repo today; net-new, follows Python community conventions |

**Planner action for these files:** Use the patterns from RESEARCH.md §Pattern 2 (uv.lock / .python-version) and §Pattern 5 (Makefile) — reproduced verbatim in the assignments above.

---

## Metadata

**Analog search scope:** `/home/loc/workspace/pycopg/.github/workflows/`, `/home/loc/workspace/pycopg/pyproject.toml`, `/home/loc/workspace/pycopg/CLAUDE.md`, `/home/loc/workspace/pycopg/README.md`
**Files scanned:** 4 (publish.yml, pyproject.toml, CLAUDE.md, README.md)
**Pattern extraction date:** 2026-06-06
