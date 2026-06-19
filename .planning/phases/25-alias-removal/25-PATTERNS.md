# Phase 25: Alias Removal — Pattern Map

**Mapped:** 2026-06-19
**Files analyzed:** 12 (1 new, 6 deleted, 5 modified)
**Analogs found:** 5 / 5 relevant categories

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `tests/test_alias_removal.py` (NEW) | test | request-response | `tests/test_admin_aliases.py` | role-match (same fixture pattern, different assertion) |
| `pycopg/database.py` (MODIFY — stub deletion) | class | — | self (stub pattern extracted below) | exact |
| `pycopg/async_database.py` (MODIFY — stub deletion) | class | — | self (stub pattern extracted below) | exact |
| `pycopg/spatial.py` (MODIFY — IN-02) | service | — | `_POSTGIS_GUARD_MSG` at L965–967 | exact |
| `pycopg/timescale.py` (MODIFY — IN-02) | service | — | guard raises at L80 | exact |
| `MIGRATION.md` (MODIFY — add section) | doc | — | existing v0.5→v0.6 table at L81–L154 | exact |
| `CHANGELOG.md` (MODIFY — add entry) | doc | — | `[0.6.0]` section at L10–L44 | exact |
| `tests/test_{admin,maint,schema,backup,timescale,spatial}_aliases.py` (DELETE) | test | — | — | n/a (deleted) |
| `pycopg/aliases.py` (DELETE) | utility | — | — | n/a (deleted) |

---

## Pattern Assignments

### `tests/test_alias_removal.py` (NEW — test, parametrize + AttributeError proof)

**Analog:** `tests/test_admin_aliases.py` + `tests/conftest.py`

**Fixture pattern from `tests/conftest.py` (L32–L40):**
```python
@pytest.fixture
def config():
    """Create a test config."""
    return Config(
        host="localhost",
        port=5432,
        database="testdb",
        user="testuser",
        password="testpass",
    )
```

The `config` fixture (not `db_config`) is the DB-free fixture used in alias tests. No live
connection is needed — `Database(config)` constructs without connecting.

**Instance-construction pattern from `tests/test_admin_aliases.py` (L66–L79):**
```python
def test_sync_alias_warns_and_delegates(self, name, config):
    db = Database(config)
    mock_accessor = MagicMock(spec=AdminAccessor)
    db._admin = mock_accessor
    args = _SYNC_ALIAS_ARGS[name]
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        getattr(db, name)(*args)
    ...
    getattr(mock_accessor, name).assert_called_once_with(*args)
```

Key observation: `Database(config)` is constructed directly — **no psycopg patch needed** for
`AttributeError` tests because `getattr(db, name)` never reaches a connection; it raises
`AttributeError` at Python attribute lookup before any I/O. Do NOT add a `patch("pycopg.database.psycopg")` wrapper — the RESEARCH.md template included it but it is unnecessary for pure `AttributeError` assertions.

**Parametrize + pytest.raises idiom (analog from test_admin_aliases.py L65, adapted):**
```python
@pytest.mark.parametrize("name", REMOVED_FLAT_NAMES)
def test_removed_flat_name_raises_attribute_error_sync(name, config):
    db = Database(config)
    with pytest.raises(AttributeError):
        getattr(db, name)

@pytest.mark.parametrize("name", REMOVED_FLAT_NAMES)
def test_removed_flat_name_raises_attribute_error_async(name, config):
    db = AsyncDatabase(config)
    with pytest.raises(AttributeError):
        getattr(db, name)
```

**WR-01 verification pattern (from RESEARCH.md — no analog, but standard `inspect` idiom):**
```python
def test_no_varargs_on_database_public_surface():
    for name, member in inspect.getmembers(Database, predicate=callable):
        if name.startswith('_'):
            continue
        try:
            params = inspect.signature(member).parameters.values()
            for p in params:
                assert p.kind not in (
                    inspect.Parameter.VAR_POSITIONAL,
                    inspect.Parameter.VAR_KEYWORD,
                ), f"Database.{name} still has *args/**kwargs"
        except (ValueError, TypeError):
            pass
```

**REMOVED_FLAT_NAMES list** (56 names, hardcoded — do not derive at runtime):
Copied verbatim from RESEARCH.md §1. The list is the same set as the stub `def` names in
`database.py` L859–L1329.

---

### `pycopg/database.py` / `pycopg/async_database.py` (stub deletion)

**What a stub looks like** — the DELETE target (`database.py` L859–L861, L863–L865):
```python
@deprecated_alias("schema.create_database")
def create_database(self, *args, **kwargs):
    """Deprecated: use ``db.schema.create_database`` instead."""

@deprecated_alias("schema.drop_database")
def drop_database(self, *args, **kwargs):
    """Deprecated: use ``db.schema.drop_database`` instead."""
```

Each stub is **exactly 3 lines**: decorator + `def` line + one-line docstring. There is no
`return` or `pass` — the body IS the docstring (Python treats a bare string literal as the
body). Delete all 3 lines per stub.

**What a real method looks like** — the PRESERVE target (`database.py` L987–, exact form):
```python
def from_dataframe(
    self,
    df: "pd.DataFrame",
    table: str,
    ...
) -> int:
    """Load a pandas DataFrame into a PostgreSQL table.

    Parameters
    ----------
    ...
    """
```

Real methods have typed signatures, multi-line docstrings, and actual bodies. A real method
is never decorated with `@deprecated_alias`.

**Import line to delete** — `database.py:29` and `async_database.py:28`:
```python
from pycopg.aliases import deprecated_alias
```

**Section headers that become empty and must be deleted** (from RESEARCH.md §Pitfall 4):
In `database.py`: `# DATABASE ADMINISTRATION`, `# EXTENSIONS`, `# SCHEMAS & TABLES`,
`# CONSTRAINTS & INDEXES`, `# POSTGIS SPATIAL OPERATIONS`, `# TIMESCALEDB OPERATIONS`,
`# MAINTENANCE & STATS`, `# ROLES & USERS`, `# ROLE MANAGEMENT`, `# BACKUP & RESTORE`.

**Section header that MUST be kept**: `# DATAFRAME OPERATIONS` (contains real methods).

---

### `pycopg/spatial.py` / `pycopg/database.py` / `pycopg/async_database.py` (IN-02 PostGIS)

**Current form** (`pycopg/spatial.py` L964–967):
```python
#: Exact PostGIS guard message (mirrors ``from_geodataframe``).
_POSTGIS_GUARD_MSG = (
    "PostGIS extension not installed. Run db.create_extension('postgis')"
)
```

**Current form** (`pycopg/database.py` L1108, `pycopg/async_database.py` L1119 — same string):
```python
"PostGIS extension not installed. Run db.create_extension('postgis')"
```

**Corrected form** (all 3 sites):
```python
"PostGIS extension not installed. Run db.schema.create_extension('postgis')"
```

### `pycopg/timescale.py` (IN-02 TimescaleDB — 12 sites)

**Current form** (representative: `timescale.py` L79–81):
```python
raise ExtensionNotAvailable(
    "TimescaleDB extension not installed. Run db.create_extension('timescaledb')"
)
```

**Corrected form** (all 12 sites — identical substitution):
```python
raise ExtensionNotAvailable(
    "TimescaleDB extension not installed. Run db.schema.create_extension('timescaledb')"
)
```

Single `sed` covers all 15 sites across both files:
```bash
sed -i "s/Run db\.create_extension/Run db.schema.create_extension/g" \
    pycopg/spatial.py pycopg/database.py pycopg/async_database.py pycopg/timescale.py
```

---

### `MIGRATION.md` (add v0.6→v0.7 section)

**Existing v0.5→v0.6 table structure to mirror** (`MIGRATION.md` L81–L154):

```markdown
## Complete Flat-Name → Accessor-Path Table

| Flat name (deprecated) | Accessor path (use this) |
| ---------------------- | ------------------------ |
| `db.add_compression_policy` | `db.timescale.add_compression_policy` |
| `db.add_retention_policy`   | `db.timescale.add_retention_policy` |
...
| `db.list_geometry_columns` | `db.spatial.list_geometry_columns` |

**Total: 56 deprecated names** (timescale 6 / admin 11 / backup 4 / maint 6 / schema 27 / spatial 2).
All `async_db.*` flat names are identical (same 56, same accessor paths with `async_db` prefix).
```

The v0.6→v0.7 section reuses this table verbatim, reframed: "Removed in v0.7.0" heading,
note that accessing these names now raises `AttributeError` (no warning, no delegation).
Source of truth for the 56-name list: MIGRATION.md L96–L152 (already generated and verified).

---

### `CHANGELOG.md` (add `[0.7.0]` Breaking entry)

**Existing `[0.6.0]` section structure to clone** (`CHANGELOG.md` L10–L44):

```markdown
## [0.6.0] - 2026-06-19

### Added
- `db.timescale.*` / `async_db.timescale.*` namespace: ...

### Deprecated
- All 56 legacy flat names on `db.*` / `async_db.*` ...
  Scheduled for removal in **v0.7.0**. See [MIGRATION.md](MIGRATION.md) ...

### Changed
- ...
```

The `[0.7.0]` entry goes ABOVE `[0.6.0]`, replacing or following `[Unreleased]` (currently
empty at L8). It needs only a `### Breaking` subsection — no `### Added` (no new features
in Phase 25). Date placeholder: leave as `[0.7.0] - TBD` until Phase 29 sets the version.

```markdown
## [0.7.0] - TBD

### Breaking

- **Removed:** All 56 flat aliases on `Database` and `AsyncDatabase` that were deprecated
  in v0.6.0 are now permanently removed. Accessing any removed name raises `AttributeError`.
  See the [Migration Guide v0.6.0 → v0.7.0](MIGRATION.md#migration-guide-v060--v070) for
  the complete flat-name → accessor-path replacement table.
```

---

## Shared Patterns

### DB-free test instance construction
**Source:** `tests/conftest.py` L32–40 (`config` fixture) + `tests/test_admin_aliases.py` L66–67
**Apply to:** `tests/test_alias_removal.py`

`Database(config)` and `AsyncDatabase(config)` can be instantiated with the bare `config`
fixture (no mock patch, no live DB) because `AttributeError` is raised at attribute lookup,
before any connection attempt. This is the pattern used throughout all alias test files.

### pytest.mark.parametrize over a name list
**Source:** `tests/test_admin_aliases.py` L65, L131
**Apply to:** `tests/test_alias_removal.py`

```python
@pytest.mark.parametrize("name", list(_SYNC_ALIAS_ARGS.keys()))
def test_sync_alias_warns_and_delegates(self, name, config):
```

New test uses the same idiom over `REMOVED_FLAT_NAMES` (a module-level list constant).

### pytest.raises(AttributeError)
**Source:** Standard pytest; no existing `pytest.raises(AttributeError)` in the alias files
(they test warnings, not errors). The pattern IS used in other pycopg tests but this is
standard enough to not require a codebase analog — copy from RESEARCH.md template directly.

---

## No Analog Found

| File | Role | Reason |
|------|------|--------|
| `pycopg/aliases.py` (DELETE) | utility | Whole-file deletion; no analog needed |
| `tests/test_{admin,maint,schema,backup,timescale,spatial}_aliases.py` (DELETE x6) | test | Whole-file deletion; no analog needed |

---

## Metadata

**Analog search scope:** `tests/`, `pycopg/`, `MIGRATION.md`, `CHANGELOG.md`
**Files read:** `conftest.py`, `test_admin_aliases.py`, `database.py` (L855–884), `spatial.py` (L960–967), `timescale.py` (L76–84), `MIGRATION.md` (L75–163), `CHANGELOG.md` (L1–60)
**Pattern extraction date:** 2026-06-19
