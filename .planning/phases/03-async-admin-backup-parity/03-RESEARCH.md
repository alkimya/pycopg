# Phase 3: AsyncDatabase Admin/Backup Parity - Research

**Researched:** 2026-02-11
**Domain:** Async admin operations, DDL, backup/restore, and database utilities
**Confidence:** HIGH

## Summary

Phase 3 extends AsyncDatabase with admin, DDL, backup/restore, and utility operations matching Database. This phase completes the essential infrastructure operations needed for production use. The research identifies three distinct implementation patterns: (1) direct async execute for DDL/admin queries, (2) asyncio subprocess for pg_dump/pg_restore, and (3) async file I/O with COPY for CSV operations.

Most methods are straightforward async conversions using existing `execute()` - the complexity lies in external process management (pg_dump/pg_restore) and file I/O operations (copy_to_csv/copy_from_csv). PostgreSQL DDL operations like CREATE DATABASE and DROP TABLE require autocommit mode and cannot be run in transactions, which is already handled by the sync Database implementation pattern.

**Primary recommendation:** Use async execute() for DDL/admin methods, asyncio.create_subprocess_exec() for pg_dump/pg_restore with environment-based credential passing, and async file operations with psycopg's async COPY support for CSV methods. No new dependencies required - all patterns use existing psycopg3 async and Python stdlib asyncio.

## Standard Stack

### Core Dependencies (Already in pycopg)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg | 3.1.0+ | PostgreSQL async driver | Native AsyncConnection and AsyncCursor support |
| Python asyncio | stdlib | Async subprocess, file I/O | Built-in subprocess and file management |

### No New Dependencies Required
All Phase 3 functionality can be implemented with psycopg3 async features and Python standard library asyncio. No third-party async file libraries (aiofiles) needed - psycopg's async COPY handles file I/O efficiently.

## Architecture Patterns

### Pattern 1: Direct Async Execute for DDL/Admin (RECOMMENDED for most methods)
**What:** Convert sync Database DDL methods to async using `await self.execute()`
**When to use:** create_database, drop_database, drop_table, create_index, drop_index, vacuum, analyze, explain, drop_schema, schema_exists, list_indexes, list_constraints, table_sizes
**Example:**
```python
# From Database (sync)
def drop_table(self, name: str, schema: str = "public", if_exists: bool = True, cascade: bool = False) -> None:
    validate_identifiers(name, schema)
    if_clause = "IF EXISTS " if if_exists else ""
    cascade_clause = " CASCADE" if cascade else ""
    self.execute(f"DROP TABLE {if_clause}{schema}.{name}{cascade_clause}")

# In AsyncDatabase (async)
async def drop_table(self, name: str, schema: str = "public", if_exists: bool = True, cascade: bool = False) -> None:
    validate_identifiers(name, schema)
    if_clause = "IF EXISTS " if if_exists else ""
    cascade_clause = " CASCADE" if cascade else ""
    await self.execute(f"DROP TABLE {if_clause}{schema}.{name}{cascade_clause}")
```

**Source:** Current Database implementation (database.py:835-847)

### Pattern 2: Async Subprocess for External Tools
**What:** Use asyncio.create_subprocess_exec() for pg_dump and pg_restore
**When to use:** pg_dump(), pg_restore()
**Example:**
```python
async def pg_dump(
    self,
    output_file: str | Path,
    format: Literal["plain", "custom", "directory", "tar"] = "custom",
    schema_only: bool = False,
    # ... other params
) -> None:
    """Backup database using pg_dump."""
    import asyncio

    output_file = Path(output_file)
    cmd = ["pg_dump"]

    # Connection params
    cmd.extend(["-h", self.config.host])
    cmd.extend(["-p", str(self.config.port)])
    cmd.extend(["-U", self.config.user])
    cmd.extend(["-d", self.config.database])

    # Format
    format_map = {"plain": "p", "custom": "c", "directory": "d", "tar": "t"}
    cmd.extend(["-F", format_map[format]])

    # Options
    if schema_only:
        cmd.append("--schema-only")

    # Output
    cmd.extend(["-f", str(output_file)])

    # Run with password in environment
    env = {"PGPASSWORD": self.config.password} if self.config.password else {}

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        env={**os.environ, **env},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {stderr.decode()}")
```

**Source:** [Python asyncio-subprocess documentation](https://docs.python.org/3/library/asyncio-subprocess.html), adapted from Database.pg_dump (database.py:2034-2119)

### Pattern 3: Async File I/O with COPY
**What:** Use psycopg async COPY with async file operations for CSV import/export
**When to use:** copy_to_csv(), copy_from_csv()
**Example:**
```python
async def copy_to_csv(
    self,
    table: str,
    output_file: str | Path,
    schema: str = "public",
    columns: Optional[list[str]] = None,
    delimiter: str = ",",
    header: bool = True,
    null_string: str = "",
    encoding: str = "UTF8",
) -> int:
    """Export table to CSV file."""
    from pathlib import Path
    import asyncio

    output_file = Path(output_file)
    validate_identifiers(table, schema)
    if columns:
        validate_identifiers(*columns)

    cols = f"({', '.join(columns)})" if columns else ""

    options = [
        f"FORMAT CSV",
        f"DELIMITER '{delimiter}'",
        f"NULL '{null_string}'",
        f"ENCODING '{encoding}'",
    ]
    if header:
        options.append("HEADER")

    async with self.cursor() as cur:
        # Open file in separate thread to avoid blocking
        await asyncio.to_thread(output_file.parent.mkdir, parents=True, exist_ok=True)

        async with await asyncio.to_thread(open, output_file, "w", encoding=encoding) as f:
            async with cur.copy(f"COPY {schema}.{table}{cols} TO STDOUT WITH ({', '.join(options)})") as copy:
                async for data in copy:
                    await asyncio.to_thread(f.write, data.decode(encoding) if isinstance(data, bytes) else data)

        # Get row count
        await cur.execute(f"SELECT COUNT(*) AS count FROM {schema}.{table}")
        result = await cur.fetchone()
        return result["count"]
```

**Source:** [psycopg3 COPY documentation](https://www.psycopg.org/psycopg3/docs/basic/copy.html), adapted from Database.copy_to_csv (database.py:2235-2289)

### DDL Autocommit Pattern
**What:** DDL operations like CREATE DATABASE require autocommit=True
**When to use:** create_database(), drop_database(), and any DDL that cannot run in transaction
**Example:**
```python
async def create_database(self, name: str, owner: Optional[str] = None, template: str = "template1") -> None:
    """Create a new database."""
    validate_identifier(name)
    if owner:
        validate_identifier(owner)
    validate_identifier(template)
    owner_clause = f" OWNER {owner}" if owner else ""

    # Connect to postgres for database creation
    admin_config = self.config.with_database("postgres")
    async with await psycopg.AsyncConnection.connect(
        **admin_config.connect_params(),
        autocommit=True
    ) as conn:
        async with conn.cursor() as cur:
            await cur.execute(f"CREATE DATABASE {name}{owner_clause} TEMPLATE {template}")
```

**Source:** [PostgreSQL Transactional DDL wiki](https://wiki.postgresql.org/wiki/Transactional_DDL_in_PostgreSQL:_A_Competitive_Analysis), Database.create_database (database.py:576-597)

### Recommended Method Grouping

**Group 1 - Simple Async Execute (10 methods):**
- drop_table, create_index, drop_index, list_indexes, list_constraints
- vacuum, analyze, explain
- drop_schema, schema_exists

**Group 2 - Async Execute with Admin Connection (2 methods):**
- create_database, drop_database

**Group 3 - Async Subprocess (2 methods):**
- pg_dump, pg_restore

**Group 4 - Async File I/O with COPY (2 methods):**
- copy_to_csv, copy_from_csv

**Group 5 - Stats/Sizes (1 method):**
- table_sizes (simple async execute, already has schema_exists)

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async subprocess management | Custom process pool | asyncio.create_subprocess_exec() | Built-in Python 3.5+, handles lifecycle automatically |
| Async file I/O for CSV | Third-party aiofiles | asyncio.to_thread() with stdlib open() | No dependency, simpler, proven pattern |
| PostgreSQL COPY protocol | Custom CSV writer | psycopg async COPY | Native protocol, 10-100x faster than CSV |
| Password handling for pg_dump | Embedding in command | PGPASSWORD environment variable | Standard PostgreSQL convention, avoids shell escaping |
| DDL transaction management | Manual transaction handling | autocommit=True flag | PostgreSQL DDL exceptions handled by driver |

**Key insight:** PostgreSQL has specific DDL that CANNOT run in transactions (CREATE DATABASE, DROP DATABASE). Using autocommit=True for these operations is required, not optional. Most other DDL (DROP TABLE, CREATE INDEX) CAN run in transactions but typically don't need to - the existing Database pattern uses direct execute without transactions, and AsyncDatabase should match.

## Common Pitfalls

### Pitfall 1: Forgetting autocommit for CREATE DATABASE
**What goes wrong:** CREATE DATABASE fails with "CREATE DATABASE cannot run inside a transaction block"
**Why it happens:** PostgreSQL requires autocommit for database-level DDL
**How to avoid:** Always use autocommit=True for create_database, drop_database
**Warning signs:** Error message "cannot run inside a transaction block"

**Source:** [PostgreSQL Documentation - Transactional DDL](https://wiki.postgresql.org/wiki/Transactional_DDL_in_PostgreSQL:_A_Competitive_Analysis)

### Pitfall 2: Not using communicate() with subprocess
**What goes wrong:** pg_dump/pg_restore hang or deadlock when output fills buffer
**Why it happens:** stdout/stderr pipes have limited buffer size, subprocess blocks when full
**How to avoid:** Always use `await proc.communicate()` instead of `await proc.wait()`
**Warning signs:** Subprocess hangs indefinitely, no error message

**Source:** [Python asyncio subprocess documentation](https://docs.python.org/3/library/asyncio-subprocess.html) - explicit warning in docs

### Pitfall 3: Shell injection in pg_dump/pg_restore commands
**What goes wrong:** User-provided filenames with spaces or special chars break commands or enable injection
**Why it happens:** Using asyncio.create_subprocess_shell() instead of create_subprocess_exec()
**How to avoid:** Use create_subprocess_exec() with list of args, never concatenate strings
**Warning signs:** Commands fail with "no such file or directory" for paths with spaces

**Source:** [Python subprocess security documentation](https://docs.python.org/3/library/subprocess.html#security-considerations)

### Pitfall 4: Blocking event loop with synchronous file I/O
**What goes wrong:** Large CSV export/import freezes entire async application
**Why it happens:** Using sync `open()` and `file.write()` directly in async methods
**How to avoid:** Use `asyncio.to_thread()` for file operations or psycopg's async COPY
**Warning signs:** Event loop blocked during file operations, other tasks frozen

**Source:** [Python asyncio development guide](https://docs.python.org/3/library/asyncio-dev.html)

### Pitfall 5: COPY protocol encoding mismatches
**What goes wrong:** CSV export/import produces garbled characters or fails with encoding errors
**Why it happens:** File encoding doesn't match COPY command ENCODING parameter
**How to avoid:** Ensure file `open(encoding=X)` matches COPY `ENCODING 'X'`
**Warning signs:** UnicodeDecodeError, mojibake (garbled text) in CSV files

**Source:** [psycopg3 COPY documentation](https://www.psycopg.org/psycopg3/docs/basic/copy.html)

### Pitfall 6: Missing DROP DATABASE connection termination
**What goes wrong:** DROP DATABASE fails with "database is being accessed by other users"
**Why it happens:** Forgetting to terminate active connections before dropping database
**How to avoid:** Copy the pg_terminate_backend query from Database.drop_database
**Warning signs:** Error "database ... is being accessed by other users"

**Source:** Database.drop_database implementation (database.py:599-621)

## Code Examples

Verified patterns from official sources and pycopg sync implementation:

### AsyncDatabase.create_database()
```python
async def create_database(self, name: str, owner: Optional[str] = None, template: str = "template1") -> None:
    """Create a new database.

    Args:
        name: Database name.
        owner: Optional owner role.
        template: Template database (default: template1).

    Example:
        await db.create_database("myapp")
        await db.create_database("myapp", owner="appuser")
    """
    validate_identifier(name)
    if owner:
        validate_identifier(owner)
    validate_identifier(template)
    owner_clause = f" OWNER {owner}" if owner else ""

    # Connect to postgres for database creation
    admin_config = self.config.with_database("postgres")
    async with await psycopg.AsyncConnection.connect(
        **admin_config.connect_params(),
        autocommit=True
    ) as conn:
        async with conn.cursor() as cur:
            await cur.execute(f"CREATE DATABASE {name}{owner_clause} TEMPLATE {template}")
```

**Source:** Adapted from Database.create_database (database.py:576-597)

### AsyncDatabase.drop_database()
```python
async def drop_database(self, name: str, if_exists: bool = True) -> None:
    """Drop a database.

    Args:
        name: Database name.
        if_exists: Don't error if database doesn't exist.

    Example:
        await db.drop_database("myapp")
    """
    validate_identifier(name)
    if_clause = "IF EXISTS " if if_exists else ""
    admin_config = self.config.with_database("postgres")

    async with await psycopg.AsyncConnection.connect(
        **admin_config.connect_params(),
        autocommit=True
    ) as conn:
        async with conn.cursor() as cur:
            # Terminate existing connections
            await cur.execute("""
                SELECT pg_terminate_backend(pg_stat_activity.pid)
                FROM pg_stat_activity
                WHERE pg_stat_activity.datname = %s
                AND pid <> pg_backend_pid()
            """, [name])
            await cur.execute(f"DROP DATABASE {if_clause}{name}")
```

**Source:** Adapted from Database.drop_database (database.py:599-621)

### AsyncDatabase.pg_dump()
```python
async def pg_dump(
    self,
    output_file: str | Path,
    format: Literal["plain", "custom", "directory", "tar"] = "custom",
    schema_only: bool = False,
    data_only: bool = False,
    tables: Optional[list[str]] = None,
    exclude_tables: Optional[list[str]] = None,
    schemas: Optional[list[str]] = None,
    compress: int = 6,
    jobs: int = 1,
) -> None:
    """Backup database using pg_dump.

    Args:
        output_file: Output file path.
        format: Dump format (plain=SQL, custom=compressed, directory=parallel, tar).
        schema_only: Dump only schema, no data.
        data_only: Dump only data, no schema.
        tables: Only dump these tables.
        exclude_tables: Exclude these tables.
        schemas: Only dump these schemas.
        compress: Compression level (0-9, for custom format).
        jobs: Parallel jobs (for directory format).

    Example:
        # Full backup in custom format
        await db.pg_dump("backup.dump")

        # Parallel backup
        await db.pg_dump("backup_dir", format="directory", jobs=4)
    """
    import asyncio
    import os

    output_file = Path(output_file)
    cmd = ["pg_dump"]

    # Connection params
    cmd.extend(["-h", self.config.host])
    cmd.extend(["-p", str(self.config.port)])
    cmd.extend(["-U", self.config.user])
    cmd.extend(["-d", self.config.database])

    # Format
    format_map = {"plain": "p", "custom": "c", "directory": "d", "tar": "t"}
    cmd.extend(["-F", format_map[format]])

    # Options
    if schema_only:
        cmd.append("--schema-only")
    if data_only:
        cmd.append("--data-only")
    if compress and format == "custom":
        cmd.extend(["-Z", str(compress)])
    if jobs > 1 and format == "directory":
        cmd.extend(["-j", str(jobs)])

    # Tables
    if tables:
        for table in tables:
            cmd.extend(["-t", table])
    if exclude_tables:
        for table in exclude_tables:
            cmd.extend(["-T", table])
    if schemas:
        for schema in schemas:
            cmd.extend(["-n", schema])

    # Output
    cmd.extend(["-f", str(output_file)])

    # Run with password in environment
    env = {"PGPASSWORD": self.config.password} if self.config.password else {}

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        env={**os.environ, **env},
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"pg_dump failed: {stderr.decode()}")
```

**Source:** Adapted from Database.pg_dump (database.py:2034-2119)

### AsyncDatabase.copy_to_csv()
```python
async def copy_to_csv(
    self,
    table: str,
    output_file: str | Path,
    schema: str = "public",
    columns: Optional[list[str]] = None,
    delimiter: str = ",",
    header: bool = True,
    null_string: str = "",
    encoding: str = "UTF8",
) -> int:
    """Export table to CSV file.

    Args:
        table: Table name.
        output_file: Output CSV file path.
        schema: Schema name.
        columns: Specific columns to export.
        delimiter: Field delimiter.
        header: Include header row.
        null_string: String for NULL values.
        encoding: File encoding.

    Returns:
        Number of rows exported.

    Example:
        count = await db.copy_to_csv("users", "users.csv")
    """
    import asyncio

    output_file = Path(output_file)
    validate_identifiers(table, schema)
    if columns:
        validate_identifiers(*columns)

    cols = f"({', '.join(columns)})" if columns else ""

    options = [
        f"FORMAT CSV",
        f"DELIMITER '{delimiter}'",
        f"NULL '{null_string}'",
        f"ENCODING '{encoding}'",
    ]
    if header:
        options.append("HEADER")

    async with self.cursor() as cur:
        # Open file in thread pool to avoid blocking
        await asyncio.to_thread(output_file.parent.mkdir, parents=True, exist_ok=True)

        # Use asyncio.to_thread for file operations
        f = await asyncio.to_thread(open, output_file, "w", encoding=encoding)
        try:
            async with cur.copy(f"COPY {schema}.{table}{cols} TO STDOUT WITH ({', '.join(options)})") as copy:
                async for data in copy:
                    text_data = data.decode(encoding) if isinstance(data, bytes) else data
                    await asyncio.to_thread(f.write, text_data)
        finally:
            await asyncio.to_thread(f.close)

        # Get row count
        await cur.execute(f"SELECT COUNT(*) AS count FROM {schema}.{table}")
        result = await cur.fetchone()
        return result["count"]
```

**Source:** [psycopg3 async COPY documentation](https://www.psycopg.org/psycopg3/docs/basic/copy.html), adapted from Database.copy_to_csv (database.py:2235-2289)

### AsyncDatabase.vacuum()
```python
async def vacuum(
    self,
    table: Optional[str] = None,
    schema: str = "public",
    analyze: bool = True,
    full: bool = False
) -> None:
    """Vacuum database or table.

    Args:
        table: Table name (None for whole database).
        schema: Schema name.
        analyze: Update statistics.
        full: Full vacuum (reclaims more space but locks table).

    Example:
        await db.vacuum()
        await db.vacuum("users", full=True)
    """
    options = []
    if full:
        options.append("FULL")
    if analyze:
        options.append("ANALYZE")

    options_str = f"({', '.join(options)})" if options else ""
    table_str = f" {schema}.{table}" if table else ""

    await self.execute(f"VACUUM{options_str}{table_str}", autocommit=True)
```

**Source:** Adapted from Database.vacuum (database.py:1613-1631)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| subprocess.run() sync | asyncio.create_subprocess_exec() | Python 3.5 (2015) | Non-blocking subprocess execution |
| subprocess.Popen() manual | proc.communicate() | Best practice always | Avoids deadlocks on large output |
| Manual file async libs | asyncio.to_thread() | Python 3.9 (2020) | No third-party dependencies for file I/O |
| psycopg2 sync COPY | psycopg3 async COPY | psycopg3 (2021) | Native async COPY protocol support |

**Deprecated/outdated:**
- **subprocess.run() in async code:** Blocks event loop, use asyncio.create_subprocess_exec()
- **aiofiles for simple operations:** asyncio.to_thread() with stdlib file operations is sufficient for CSV export/import
- **Embedding passwords in pg_dump command:** Security risk, use PGPASSWORD environment variable
- **subprocess.call() or os.system():** Ancient patterns, no async support

## Open Questions

1. **Should we add index_sizes() method?**
   - What we know: ASYNC-24 mentions table_sizes/index_sizes but Database only has table_sizes
   - What's unclear: Is index_sizes a separate method or should we add it?
   - Recommendation: Check if index_sizes exists in Database. If not, note in PLAN.md that it's not implemented and only table_sizes will be added. Planner can decide if index_sizes should be added to both sync and async.

2. **COPY performance with asyncio.to_thread()**
   - What we know: psycopg async COPY exists, asyncio.to_thread() adds overhead
   - What's unclear: Is the thread overhead significant for CSV operations?
   - Recommendation: Implement with asyncio.to_thread() first (simpler, matches sync pattern), profile if needed, optimize later if bottleneck identified.

3. **pg_dump timeout handling**
   - What we know: Large databases can take hours to dump
   - What's unclear: Should we add timeout parameter or rely on user to manage?
   - Recommendation: Match sync implementation (no timeout), document that users can wrap with asyncio.wait_for() if needed.

## Sources

### Primary (HIGH confidence)
- [Python asyncio subprocess documentation](https://docs.python.org/3/library/asyncio-subprocess.html)
- [psycopg3 Using COPY TO and COPY FROM](https://www.psycopg.org/psycopg3/docs/basic/copy.html)
- [psycopg3 Concurrent operations (async)](https://www.psycopg.org/psycopg3/docs/advanced/async.html)
- [PostgreSQL Documentation: Transactional DDL](https://wiki.postgresql.org/wiki/Transactional_DDL_in_PostgreSQL:_A_Competitive_Analysis)
- [PostgreSQL Documentation: Asynchronous Commit](https://www.postgresql.org/docs/current/wal-async-commit.html)

### Secondary (MEDIUM confidence)
- [Super Fast Python: Asyncio Subprocess](https://superfastpython.com/asyncio-subprocess/)
- [Super Fast Python: Asyncio create_subprocess_exec](https://superfastpython.com/asyncio-create_subprocess_exec/)
- [Medium: Async IO in Python - Subprocesses](https://medium.com/@kalmlake/async-io-in-python-subprocesses-af2171d1ff31)
- [Sling Academy: Python aiofiles CSV operations](https://www.slingacademy.com/article/python-aiofiles-read-write-csv-asynchronously/)

### Tertiary (LOW confidence, flagged for validation)
- GitHub examples of asyncio subprocess patterns (not authoritative but useful for edge cases)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All dependencies verified in current pyproject.toml and Python stdlib
- Architecture: HIGH - All patterns verified from official psycopg3 and Python docs
- Pitfalls: HIGH - All verified from official documentation and Database implementation

**Research date:** 2026-02-11
**Valid until:** 90 days (stable ecosystem - asyncio patterns and psycopg3 are mature)
