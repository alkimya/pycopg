---
phase: 37-dette-audit
reviewed: 2026-06-26T00:00:00Z
depth: deep
files_reviewed: 17
files_reviewed_list:
  - pycopg/__init__.py
  - pycopg/exceptions.py
  - pycopg/config.py
  - pycopg/utils.py
  - pycopg/base.py
  - pycopg/queries.py
  - pycopg/database.py
  - pycopg/async_database.py
  - pycopg/admin.py
  - pycopg/schema.py
  - pycopg/maint.py
  - pycopg/backup.py
  - pycopg/etl.py
  - pycopg/migrations.py
  - pycopg/spatial.py
  - pycopg/timescale.py
  - pycopg/pool.py
findings:
  critical: 5
  warning: 6
  info: 0
  total: 11
status: dispositioned
dispositioned: 2026-06-26
decisions_journal: .planning/phases/37-dette-audit/37-DECISIONS.md
---

# Phase 37: Code Review Report — AUDIT-01 (Full Source)

**Reviewed:** 2026-06-26
**Depth:** deep (cross-file, call-chain, import-graph)
**Files Reviewed:** 17
**Status:** issues_found

## Summary

Full-source adversarial review of the entire `pycopg/` package at v0.9.0. The
identifier-validation discipline is consistently applied in the core read/write
paths and in the spatial, schema, admin, and timescale accessors. No injection
surface was found in parameterized user-value paths.

Five critical findings were identified, all involving unvalidated caller-
controlled strings reaching SQL or shell command surfaces:

- The `explain()` format parameter (maint.py) reaches SQL without a whitelist.
- `from_dataframe()` and `from_geodataframe()` (database.py + async_database.py)
  pass table/schema to SQLAlchemy without calling `validate_identifiers` first.
- `build_pg_dump_cmd()` and `build_pg_restore_cmd()` (base.py) pass tables,
  schemas, and exclude_tables to the pg_dump/pg_restore CLI without identifier
  validation.
- `backup.py pg_restore()` incorrectly routes a non-existent binary-format file
  to the plain-SQL psql path, causing binary content to be fed as SQL.

Six warnings cover a `connection_limit` integer-type assumption without
runtime guards, an `AsyncDatabase.stream()` session-mode divergence from its
sync counterpart, `copy_insert()` session bypass on both sync and async sides,
URL query-param values interpolated into the `options` libpq key without
sanitization, `TimescaleError` missing from `__all__`, and the `_decode_watermark`
unknown-tag silent fallback in etl.py.

## Structural Findings (fallow)

No structural pre-pass was provided for this review.

## Narrative Findings (AI reviewer)

---

## Critical Issues

### CR-01: `explain()` format parameter interpolated into SQL without whitelist

**File:** `pycopg/maint.py:186` (sync) and `pycopg/maint.py:355` (async)

**Issue:** The `format` parameter accepted by both `MaintAccessor.explain()` and
`AsyncMaintAccessor.explain()` is directly interpolated into the EXPLAIN statement
via `f"FORMAT {format.upper()}"` with no whitelist check. A caller supplying a
crafted string such as `"TEXT) SELECT 1; --"` will produce broken SQL that
PostgreSQL rejects outright, but values like `"TEXT, BUFFERS TRUE"` silently add
unexpected EXPLAIN options. More critically, there is no guard preventing
injection of planner option injection. The correct fix is a four-element whitelist
(text, json, xml, yaml) that matches the PostgreSQL-accepted EXPLAIN format
options.

**Fix:**
```python
_VALID_EXPLAIN_FORMATS = {"text", "json", "xml", "yaml"}

def explain(self, sql, params=None, analyze=False, format="text"):
    fmt = format.lower()
    if fmt not in _VALID_EXPLAIN_FORMATS:
        raise ValueError(
            f"explain(): format must be one of {sorted(_VALID_EXPLAIN_FORMATS)}, got {format!r}"
        )
    options = [f"FORMAT {fmt.upper()}"]
    if analyze:
        options.append("ANALYZE")
    result = self._db.execute(f"EXPLAIN ({', '.join(options)}) {sql}", params)
    return [r["QUERY PLAN"] for r in result]
```
Apply the identical fix to `AsyncMaintAccessor.explain()` at line 355.

---

### CR-02: `from_dataframe()` passes table/schema to SQLAlchemy without identifier validation

**File:** `pycopg/database.py:1233` (sync) and `pycopg/async_database.py:998` (async)

**Issue:** `Database.from_dataframe()` calls `df.to_sql(name=table, schema=schema,
...)` and `AsyncDatabase.from_dataframe()` calls the same via `conn.run_sync()`
without ever calling `validate_identifiers(table, schema)` first. SQLAlchemy
quotes identifiers via its own `quote_name` mechanism, but pycopg's identifier
invariant is that all table/schema inputs are validated at the pycopg boundary
before any downstream use. A caller passing a string that is not a valid
SQL identifier will bypass all security-relevant checks and reach SQLAlchemy
directly. If SQLAlchemy's quoting is overridden or bypassed by an edge case
(e.g., schema=None is passed as a literal string "None"), the result is
undefined behavior. Additionally, the `if_exists` argument is typed as
`Literal["fail", "replace", "append"]` but there is no runtime check — an
invalid value silently reaches `df.to_sql()`.

**Fix:**
```python
def from_dataframe(self, df, table, schema="public", if_exists="fail",
                   primary_key=None, index=False, dtype=None):
    validate_identifiers(table, schema)   # ADD THIS LINE
    df.to_sql(
        name=table,
        con=self.engine,
        schema=schema,
        if_exists=if_exists,
        index=index,
        dtype=dtype,
    )
    ...
```
Apply the same `validate_identifiers(table, schema)` call at the top of
`AsyncDatabase.from_dataframe()` (async_database.py:967), before the
`async_engine.connect()` block.

---

### CR-03: `from_geodataframe()` passes table/schema to GeoPandas without identifier validation

**File:** `pycopg/database.py:1350` (sync) and `pycopg/async_database.py:1127` (async)

**Issue:** `Database.from_geodataframe()` calls `gdf.to_postgis(name=table,
schema=schema, ...)` without any identifier validation. `AsyncDatabase.from_geodataframe()`
does the same inside a `run_sync` lambda. This is the same class of defect as
CR-02 but affecting the spatial write path. GeoPandas delegates to SQLAlchemy's
GeoAlchemy2 integration, which also provides quoting — but pycopg's security
boundary requires validation at the pycopg API surface before any downstream
library handles it.

**Fix:**
```python
def from_geodataframe(self, gdf, table, schema="public", if_exists="fail",
                       geometry_column="geometry", srid=4326, ...):
    validate_identifiers(table, schema)   # ADD THIS LINE
    gdf.to_postgis(
        name=table,
        con=self.engine,
        schema=schema,
        ...
    )
```
Apply identically to `AsyncDatabase.from_geodataframe()` (async_database.py:1058).

---

### CR-04: `build_pg_dump_cmd()` and `build_pg_restore_cmd()` pass tables/schemas to CLI without identifier validation

**File:** `pycopg/base.py:341-348` (pg_dump) and `pycopg/base.py:448-453` (pg_restore)

**Issue:** Both command builders accept `tables`, `exclude_tables`, and `schemas`
list arguments and expand them verbatim as `-t TABLE`, `-T TABLE`, and `-n SCHEMA`
CLI arguments:

```python
if tables:
    for table in tables:
        cmd.extend(["-t", table])        # no validate_identifier(table)
if exclude_tables:
    for table in exclude_tables:
        cmd.extend(["-T", table])        # no validate_identifier(table)
if schemas:
    for schema in schemas:
        cmd.extend(["-n", schema])       # no validate_identifier(schema)
```

pg_dump and pg_restore are spawned via `subprocess.run()` with a list argv (not
a shell string), so shell injection is not directly possible. However, a value
like `"--no-password"` or `"--schema-only"` in the tables list would be passed
as a `-t --no-password` argument, which pg_dump interprets as a table filter for
a literal option string, producing unexpected behavior. More critically, values
containing spaces or quoting special characters may be misinterpreted by pg_dump's
own pattern matching. The established pycopg invariant is that all identifiers
are validated before use. These functions violate that invariant.

**Fix:**
```python
from pycopg.utils import validate_identifier

if tables:
    for table in tables:
        validate_identifier(table)
        cmd.extend(["-t", table])
if exclude_tables:
    for table in exclude_tables:
        validate_identifier(table)
        cmd.extend(["-T", table])
if schemas:
    for schema in schemas:
        validate_identifier(schema)
        cmd.extend(["-n", schema])
```
Apply to both `build_pg_dump_cmd()` and `build_pg_restore_cmd()`.

---

### CR-05: `pg_restore()` routes non-existent binary-format file to psql path

**File:** `pycopg/backup.py:158` (sync) and `pycopg/backup.py:492` (async)

**Issue:** The routing condition is:

```python
if input_file.suffix == ".sql" or not input_file.exists():
    self._psql_restore(input_file)
    return
```

The `not input_file.exists()` branch was intended to handle missing plain-SQL
files gracefully, but it fires for *any* missing file — including missing
custom-format, directory-format, or tar-format pg_dump archives. When a caller
attempts to restore a non-existent `.dump` file, `_psql_restore()` is invoked
instead of reporting "file not found". psql will then attempt to interpret the
binary-format content as SQL (if the file exists with a different name) or will
fail with a psql error rather than a pg_restore error, masking the root cause.
The correct behavior for a non-`.sql` missing file is to raise `FileNotFoundError`
immediately.

**Fix:**
```python
input_file = Path(input_file)
if input_file.suffix == ".sql":
    self._psql_restore(input_file)
    return
if not input_file.exists():
    raise FileNotFoundError(f"Backup file not found: {input_file}")
# Proceed with pg_restore binary path
cmd = build_pg_restore_cmd(...)
```
Apply identically at async_database.py:492.

---

## Warnings

### WR-01: `connection_limit` interpolated without integer type guard

**File:** `pycopg/base.py:524`

**Issue:** `build_role_options()` interpolates `connection_limit` directly:

```python
if connection_limit != -1:
    options.append(f"CONNECTION LIMIT {connection_limit}")
```

The type signature declares `connection_limit: int = -1`, and mypy would catch
non-int callers statically. However, there is no runtime `isinstance(connection_limit, int)`
check. A caller passing `connection_limit="10 SUPERUSER"` (a string) would inject
arbitrary SQL into the role definition. All other numeric values in the codebase
(e.g., `number_partitions` in timescale.py:808) carry explicit `isinstance(bool)`
and `isinstance(int)` guards. This case should be consistent.

**Fix:**
```python
if connection_limit != -1:
    if not isinstance(connection_limit, int) or isinstance(connection_limit, bool):
        raise TypeError(
            f"connection_limit must be an int, got {type(connection_limit).__name__}."
        )
    options.append(f"CONNECTION LIMIT {connection_limit}")
```

---

### WR-02: `AsyncDatabase.stream()` bypasses session mode — sync/async parity divergence

**File:** `pycopg/async_database.py:1408-1416`

**Issue:** `Database.stream()` (sync) uses `self.cursor()` which respects the
session connection (`_session_conn`) when inside a `db.session()` block. The
async counterpart `AsyncDatabase.stream()` uses `async with self.connect() as conn:`
which always opens a new connection, bypassing session mode entirely. This is an
observable behavioral difference: code that relies on session-mode transaction
semantics (e.g., reading streaming results inside the same transaction as a prior
write) will silently operate on a different connection when using the async path.

**Fix:**
```python
async def stream(self, sql, params=None, batch_size=100):
    async with self.cursor() as cur:         # use cursor(), not connect()
        await cur.execute(sql, params)
        while True:
            batch = await cur.fetchmany(batch_size)
            if not batch:
                break
            for row in batch:
                yield row
```
Verify that `AsyncDatabase.cursor()` is an async context manager returning an
appropriate cursor (consistent with `Database.cursor()`).

---

### WR-03: `copy_insert()` always opens a new connection, bypassing session mode

**File:** `pycopg/database.py:1037` (sync) and `pycopg/async_database.py:678` (async)

**Issue:** Both `Database.copy_insert()` and `AsyncDatabase.copy_insert()` use
`with self.connect() as conn:` / `async with self.connect() as conn:` rather than
the session-aware cursor path. If a caller wraps a COPY operation inside a
`db.session()` block expecting it to participate in the same transaction, the
COPY executes on an independent connection and is committed separately. This is a
silent atomicity violation — no error is raised, the data is committed regardless
of the surrounding session.

This is the same pattern as WR-02 but applies symmetrically to both sync and
async paths.

**Fix:** Route `copy_insert()` through the session connection when inside a
session context, consistent with how `execute()` behaves. The COPY API in
psycopg3 supports the same connection object, so there is no technical barrier.

---

### WR-04: URL query-param values interpolated into libpq `options` string without sanitization

**File:** `pycopg/config.py:170` (dsn property) and `pycopg/config.py:238` (connect_params)

**Issue:** The `Config.dsn` property and `Config.connect_params()` both iterate
over `self.options` (a dict populated from URL query parameters in `from_url()`)
and construct:

```python
for key, value in self.options.items():
    options_parts.append(f"-c {key}={value}")
```

Neither `key` nor `value` is validated or sanitized. A URL such as
`postgres://host/db?statement_timeout=1000%20options%3Dother` could inject
additional `-c` flags into the libpq options string. While libpq itself will
reject unknown option strings with a connection error, a value containing a space
and `-c` prefix would allow injection of additional GUC settings. This is not
direct SQL injection but is an options-injection surface that should be guarded.

**Fix:** Validate keys against a known-safe GUC allowlist, or at minimum strip
characters that are special in the libpq options string (space, single-quote,
backslash):
```python
_SAFE_OPTION_RE = re.compile(r"^[a-z_][a-z0-9_.]*$", re.IGNORECASE)
for key, value in self.options.items():
    if not _SAFE_OPTION_RE.match(key):
        raise ConfigurationError(f"Unsafe option key: {key!r}")
    if " " in value or "'" in value or "\\" in value:
        raise ConfigurationError(f"Unsafe option value for {key!r}")
    options_parts.append(f"-c {key}={value}")
```

---

### WR-05: `TimescaleError` defined in `exceptions.py` but not exported from `__init__.py`

**File:** `pycopg/__init__.py` and `pycopg/exceptions.py`

**Issue:** `TimescaleError` is defined in `pycopg/exceptions.py` and is used by
`timescale.py` (wrapped around `DatabaseError` in `add_dimension()`). However
it is absent from `__all__` in `__init__.py`. Callers who want to catch
`TimescaleError` by name must import it from `pycopg.exceptions` directly:
`from pycopg.exceptions import TimescaleError`. The library documents catching
this exception in the `add_dimension` docstring without noting the unusual import
path. Every other user-facing exception (`ConnectionError`, `ConfigurationError`,
`ExtensionNotAvailable`, `TableNotFound`, `InvalidIdentifier`, `MigrationError`,
`DatabaseExists`, `ETLError`, etc.) is in `__all__` and importable from `pycopg`.

**Fix:**
```python
# pycopg/__init__.py — add to __all__ and import list
from pycopg.exceptions import (
    ...
    TimescaleError,   # ADD
    ...
)
__all__ = [
    ...
    "TimescaleError",   # ADD
    ...
]
```

---

### WR-06: `_decode_watermark()` silently returns raw value for unknown type tags

**File:** `pycopg/etl.py` (approximately line 670)

**Issue:** The `_decode_watermark()` function dispatches on a `{"type": ...,
"value": ...}` JSONB envelope. For unknown type tags it falls through to a silent
`return str(value)` path rather than raising `ETLError` or `ValueError`. A
watermark written with a correct type tag that is later corrupted in the JSONB
column (e.g., type changed from `"datetime"` to `"datetimetz"` by an external
tool) will silently return a raw string instead of a typed value. Downstream
code performing watermark comparisons (`>=`, `<=`) will then compare a string
against a datetime, producing a runtime `TypeError` with a confusing traceback
pointing into the ETL load logic rather than the watermark decode.

**Fix:**
```python
def _decode_watermark(envelope: dict):
    wtype = envelope.get("type")
    value = envelope.get("value")
    if wtype == "datetime":
        return datetime.fromisoformat(value)
    elif wtype == "int":
        return int(value)
    elif wtype == "float":
        return float(value)
    elif wtype == "str":
        return str(value)
    else:
        raise ETLError(
            f"Unknown watermark type tag {wtype!r} in envelope {envelope!r}. "
            "Watermark envelope may be corrupted."
        )
```

---

_Reviewed: 2026-06-26_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: deep_

---

## Dispositions (D-06 disposition bar — applied 2026-06-26, Phase 37 Plan 05)

Every finding in this report is now dispositioned. The Task 2 human checkpoint was
APPROVED with the dispositions below. Full per-finding fix detail, commit SHAs, and the
single deferral justification live in the consolidated decisions journal:
**`.planning/phases/37-dette-audit/37-DECISIONS.md` (§2 AUDIT-01 dispositions).**

> ⚠ ID-collision note: the `WR-0x` warning IDs in this report are LOCAL to this audit
> (qualify as **37-REVIEW:WR-0x**). They are unrelated to the historical v0.8.0-review
> `WR-xx` series tracked under DEBT-03b — see 37-DECISIONS.md §1.

| Finding | Severity | Disposition | Evidence |
|---------|----------|-------------|----------|
| CR-01 explain() format whitelist | HIGH (BLOCKER) | **FIXED in-phase** | commit `0321b85` |
| CR-02 from_dataframe() validate_identifiers | HIGH | **FIXED in-phase** | commit `1118a60` |
| CR-03 from_geodataframe() validate_identifiers | HIGH | **FIXED in-phase** | commit `1118a60` |
| CR-04 pg_dump/restore CLI flag-injection guard | HIGH | **FIXED in-phase** | commit `6dc326b` |
| CR-05 pg_restore() FileNotFoundError routing | HIGH | **FIXED in-phase** | commit `ede7210` |
| 37-REVIEW:WR-01 connection_limit int guard | MEDIUM (WARNING) | **FIXED in-phase** | commit `6dc326b` |
| 37-REVIEW:WR-02 async stream() session parity | MEDIUM | **FIXED in-phase** | commit `1118a60` |
| 37-REVIEW:WR-03 copy_insert() session bypass | MEDIUM | **DEFERRED to v1.0.0** (justified) | 37-DECISIONS.md §2 |
| 37-REVIEW:WR-04 libpq option sanitization | MEDIUM | **FIXED in-phase** | commit `e46ab2d` |
| 37-REVIEW:WR-05 TimescaleError export | MEDIUM | **FIXED in-phase** | commit `b9bed80` |
| 37-REVIEW:WR-06 _decode_watermark unknown tag | MEDIUM | **FIXED in-phase** | commit `a081b0e` |

**Bar satisfied:** every HIGH (BLOCKER) is fixed in-phase; every MEDIUM (WARNING) is fixed
in-phase except 37-REVIEW:WR-03 which is deferred-to-v1.0.0 with written justification; no
LOW/INFO findings were surfaced (0 INFO). After all fixes, `uv run ruff check pycopg tests`
exits 0 and `PGDATABASE=pycopg_test2 uv run pytest` is green except the 3 known pre-existing
PostGIS-env failures (PostGIS absent in `pycopg_test2`). 53 new regression tests added in
`tests/test_audit_37_fixes.py` (one or more per fixed finding).

_Dispositioned: 2026-06-26 (Phase 37 Plan 05)_
