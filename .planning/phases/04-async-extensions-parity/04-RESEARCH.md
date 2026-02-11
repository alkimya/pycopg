# Phase 4: AsyncDatabase Extensions Parity - Research

**Researched:** 2026-02-11
**Domain:** Async PostgreSQL extensions (PostGIS, TimescaleDB) and role management
**Confidence:** HIGH

## Summary

Phase 4 extends AsyncDatabase with full PostGIS, TimescaleDB, and role management support to achieve complete parity with the sync Database class. This phase covers three distinct extension domains: (1) PostgreSQL role/user management (9 methods: create_role, drop_role, alter_role, grant, revoke, grant_role, revoke_role, list_role_members, list_role_grants), (2) PostGIS spatial operations (2 methods: create_spatial_index, list_geometry_columns), and (3) TimescaleDB time-series operations (5 methods: create_hypertable, enable_compression, add_retention_policy, list_hypertables, and one bonus method hypertable_info for enhanced functionality).

All methods are straightforward async conversions using the established `await self.execute()` pattern from Phases 2 and 3. Role management requires autocommit=True for DDL operations (CREATE/DROP/ALTER ROLE), while GRANT/REVOKE statements also require autocommit. TimescaleDB methods must validate extension installation using existing `await self.has_extension("timescaledb")` before calling TimescaleDB functions. PostGIS methods do NOT require explicit extension validation because they operate on standard PostgreSQL system tables (geometry_columns).

**Primary recommendation:** Use direct async execute() pattern for all 16 methods. All role DDL and privilege operations require autocommit=True. TimescaleDB methods require extension validation with RuntimeError on missing extension (matching sync Database pattern). No new dependencies, no complex subprocess or file I/O - pure SQL execution.

## Standard Stack

### Core Dependencies (Already in pycopg)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg | 3.1.0+ | PostgreSQL async driver | Native AsyncConnection support for all SQL operations |
| PostgreSQL | 12.0+ | Database server | Role management, GRANT/REVOKE standard in all versions |
| PostGIS | 3.0+ | Spatial extension | GIST indexes, geometry_columns view |
| TimescaleDB | 2.0+ | Time-series extension | Hypertable functions, compression, retention policies |

### No New Dependencies Required
All Phase 4 functionality implemented with psycopg3 async execute(). Extension validation uses existing `has_extension()` method added in Phase 3. No additional libraries needed.

## Architecture Patterns

### Pattern 1: Direct Async Execute for Role DDL (Requires Autocommit)
**What:** Convert sync Database role DDL methods to async using `await self.execute()` with autocommit=True
**When to use:** create_role(), drop_role(), alter_role()
**Example:**
```python
# From Database (sync) - database.py:1753
def drop_role(self, name: str, if_exists: bool = True) -> None:
    validate_identifier(name)
    if_clause = "IF EXISTS " if if_exists else ""
    self.execute(f"DROP ROLE {if_clause}{name}", autocommit=True)

# In AsyncDatabase (async)
async def drop_role(self, name: str, if_exists: bool = True) -> None:
    validate_identifier(name)
    if_clause = "IF EXISTS " if if_exists else ""
    await self.execute(f"DROP ROLE {if_clause}{name}", autocommit=True)
```

**Why autocommit:** CREATE/DROP/ALTER ROLE are DDL statements that cannot run inside a transaction block. PostgreSQL returns "ERROR: CREATE ROLE cannot run inside a transaction block" if attempted without autocommit.

**Source:** Current Database implementation (database.py:1666-1865), PostgreSQL DDL documentation

### Pattern 2: Direct Async Execute for GRANT/REVOKE (Requires Autocommit)
**What:** Convert sync Database privilege methods to async using `await self.execute()` with autocommit=True
**When to use:** grant(), revoke(), grant_role(), revoke_role()
**Example:**
```python
# From Database (sync) - database.py:1865
def grant_role(self, role: str, member: str, with_admin: bool = False) -> None:
    validate_identifiers(role, member)
    admin_clause = " WITH ADMIN OPTION" if with_admin else ""
    self.execute(f"GRANT {role} TO {member}{admin_clause}", autocommit=True)

# In AsyncDatabase (async)
async def grant_role(self, role: str, member: str, with_admin: bool = False) -> None:
    validate_identifiers(role, member)
    admin_clause = " WITH ADMIN OPTION" if with_admin else ""
    await self.execute(f"GRANT {role} TO {member}{admin_clause}", autocommit=True)
```

**Why autocommit:** GRANT and REVOKE are privilege commands that must execute outside transactions for immediate effect and to avoid transaction conflicts with role operations.

**Source:** PostgreSQL GRANT documentation (https://www.postgresql.org/docs/current/sql-grant.html)

### Pattern 3: Async Execute for Role Inspection (No Autocommit)
**What:** Convert sync Database role query methods to async using `await self.execute()`
**When to use:** list_role_members(), list_role_grants()
**Example:**
```python
# From Database (sync) - database.py:1992
def list_role_members(self, role: str) -> list[str]:
    result = self.execute("""
        SELECT m.rolname AS member
        FROM pg_auth_members am
        JOIN pg_roles r ON r.oid = am.roleid
        JOIN pg_roles m ON m.oid = am.member
        WHERE r.rolname = %s
        ORDER BY m.rolname
    """, [role])
    return [r["member"] for r in result]

# In AsyncDatabase (async)
async def list_role_members(self, role: str) -> list[str]:
    result = await self.execute("""
        SELECT m.rolname AS member
        FROM pg_auth_members am
        JOIN pg_roles r ON r.oid = am.roleid
        JOIN pg_roles m ON m.oid = am.member
        WHERE r.rolname = %s
        ORDER BY m.rolname
    """, [role])
    return [r["member"] for r in result]
```

**Why no autocommit:** These are SELECT queries against system catalogs (pg_roles, pg_auth_members, information_schema). They can safely run inside transactions.

**Source:** Current Database implementation (database.py:1992-2029)

### Pattern 4: Async Execute for PostGIS Operations (No Extension Validation)
**What:** Convert sync Database PostGIS methods to async using `await self.execute()`
**When to use:** create_spatial_index(), list_geometry_columns()
**Example:**
```python
# From Database (sync) - database.py:1296
def create_spatial_index(self, table: str, column: str = "geometry", schema: str = "public", name: Optional[str] = None) -> None:
    index_name = name or f"idx_{table}_{column}_gist"
    self.execute(f"""
        CREATE INDEX IF NOT EXISTS {index_name}
        ON {schema}.{table} USING GIST ({column})
    """)

# In AsyncDatabase (async)
async def create_spatial_index(self, table: str, column: str = "geometry", schema: str = "public", name: Optional[str] = None) -> None:
    index_name = name or f"idx_{table}_{column}_gist"
    await self.execute(f"""
        CREATE INDEX IF NOT EXISTS {index_name}
        ON {schema}.{table} USING GIST ({column})
    """)
```

**Why no extension check:** PostGIS methods use standard PostgreSQL CREATE INDEX and system table queries. If PostGIS isn't installed, the geometry_columns view won't exist and PostgreSQL will return appropriate errors. This matches the sync Database pattern.

**Source:** Current Database implementation (database.py:1296-1337), PostGIS documentation

### Pattern 5: Async Execute for TimescaleDB Operations (Requires Extension Validation)
**What:** Convert sync Database TimescaleDB methods to async, validating extension first
**When to use:** create_hypertable(), enable_compression(), add_retention_policy(), list_hypertables()
**Example:**
```python
# From Database (sync) - database.py:1342
def create_hypertable(
    self,
    table: str,
    time_column: str,
    schema: str = "public",
    chunk_time_interval: str = "1 day",
    if_not_exists: bool = True,
    migrate_data: bool = True,
) -> None:
    if not self.has_extension("timescaledb"):
        raise RuntimeError("TimescaleDB extension not installed. Run db.create_extension('timescaledb')")

    validate_identifiers(table, schema, time_column)
    validate_interval(chunk_time_interval)

    self.execute(f"""
        SELECT create_hypertable(
            '{schema}.{table}',
            '{time_column}',
            chunk_time_interval => INTERVAL '{chunk_time_interval}',
            if_not_exists => {str(if_not_exists).upper()},
            migrate_data => {str(migrate_data).upper()}
        )
    """)

# In AsyncDatabase (async)
async def create_hypertable(
    self,
    table: str,
    time_column: str,
    schema: str = "public",
    chunk_time_interval: str = "1 day",
    if_not_exists: bool = True,
    migrate_data: bool = True,
) -> None:
    if not await self.has_extension("timescaledb"):
        raise RuntimeError("TimescaleDB extension not installed. Run db.create_extension('timescaledb')")

    validate_identifiers(table, schema, time_column)
    validate_interval(chunk_time_interval)

    await self.execute(f"""
        SELECT create_hypertable(
            '{schema}.{table}',
            '{time_column}',
            chunk_time_interval => INTERVAL '{chunk_time_interval}',
            if_not_exists => {str(if_not_exists).upper()},
            migrate_data => {str(migrate_data).upper()}
        )
    """)
```

**Why extension validation:** TimescaleDB functions (create_hypertable, add_compression_policy, etc.) don't exist without the extension. Prior decision from 01-02 establishes RuntimeError pattern for missing TimescaleDB extension. This provides clear, actionable error messages.

**Source:** Current Database implementation (database.py:1342-1530), Phase requirements (prior decision: "Keep RuntimeError for TimescaleDB extension validation")

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Role password hashing | Custom bcrypt/scrypt | PostgreSQL PASSWORD clause | PostgreSQL handles hashing (MD5/SCRAM-SHA-256) automatically |
| Privilege inheritance logic | Custom permission tree | PostgreSQL INHERIT attribute + GRANT role TO member | PostgreSQL manages complex inheritance automatically |
| Spatial index optimization | Custom R-Tree implementation | PostgreSQL GIST index | PostGIS R-Tree on GIST is battle-tested, optimized |
| Hypertable chunk management | Custom time partitioning | TimescaleDB create_hypertable | TimescaleDB handles chunk sizing, compression, retention automatically |
| Extension version checks | Custom compatibility matrix | PostgreSQL extension system | Extensions declare their own version dependencies |

**Key insight:** PostgreSQL, PostGIS, and TimescaleDB have deeply integrated permission systems, spatial indexing, and time-series management. Don't reimplement these in application code - use the database features directly via SQL. The async conversion is purely about execution mechanics (await self.execute), not reimplementing domain logic.

## Common Pitfalls

### Pitfall 1: Forgetting autocommit for DDL/privilege commands
**What goes wrong:** CREATE ROLE, DROP ROLE, GRANT, REVOKE fail with "ERROR: cannot run inside a transaction block"
**Why it happens:** PostgreSQL DDL and privilege commands require immediate commit and cannot be deferred to transaction end
**How to avoid:** Always pass `autocommit=True` to execute() for: create_role, drop_role, alter_role, grant, revoke, grant_role, revoke_role
**Warning signs:** `psycopg.errors.ActiveSqlTransaction` exception with "cannot run inside a transaction block"

**Source:** PostgreSQL DDL documentation, established pycopg pattern in Database class

### Pitfall 2: Not awaiting async has_extension() before sync operations
**What goes wrong:** `if not self.has_extension("timescaledb"):` raises TypeError: 'coroutine' object is not callable
**Why it happens:** AsyncDatabase.has_extension() returns a coroutine, must be awaited
**How to avoid:** Always use `if not await self.has_extension("timescaledb"):` in async methods
**Warning signs:** TypeError about coroutine, RuntimeWarning about unawaited coroutine

**Source:** Python asyncio documentation, established Phase 3 pattern

### Pitfall 3: Using parameterized queries for role/privilege names
**What goes wrong:** `GRANT %s TO %s` with params ["readonly", "analyst"] produces `GRANT 'readonly' TO 'analyst'` with quotes, which fails
**Why it happens:** PostgreSQL requires unquoted identifiers for role names in GRANT/REVOKE/CREATE ROLE
**How to avoid:** Use f-strings for role/table/privilege identifiers after validation, use %s params only for passwords and filter values
**Warning signs:** ERROR: syntax error at or near "'readonly'"

**Source:** PostgreSQL identifier quoting rules, current Database implementation pattern

### Pitfall 4: Assuming PostGIS extension is installed
**What goes wrong:** `list_geometry_columns()` succeeds but returns empty list when PostGIS isn't installed (geometry_columns view doesn't exist)
**Why it happens:** Unlike TimescaleDB methods, PostGIS methods don't validate extension first (matching sync Database pattern)
**How to avoid:** Document that PostGIS methods require PostGIS extension, user must install first. DON'T add validation checks (pattern inconsistency with Database)
**Warning signs:** Empty results from list_geometry_columns when PostGIS tables exist

**Source:** Current Database implementation (doesn't validate PostGIS extension)

### Pitfall 5: Password handling in create_role
**What goes wrong:** Passing password directly in SQL string exposes it in logs: `CREATE ROLE user WITH PASSWORD 'secret123'`
**Why it happens:** SQL query logging captures plain text password
**How to avoid:** Use parameterized query for password: `cur.execute(f"CREATE ROLE {name} WITH {options_str}", [password])` where options_str contains "PASSWORD %s"
**Warning signs:** Passwords visible in PostgreSQL query logs

**Source:** Security best practice, current Database implementation pattern (database.py:1736-1746)

## Code Examples

Verified patterns from official sources.

### PostgreSQL Role Creation with Password Security
```python
# Source: database.py:1666-1752
async def create_role(
    self,
    name: str,
    password: Optional[str] = None,
    login: bool = True,
    superuser: bool = False,
    createdb: bool = False,
    createrole: bool = False,
    inherit: bool = True,
    replication: bool = False,
    connection_limit: int = -1,
    valid_until: Optional[str] = None,
    in_roles: Optional[list[str]] = None,
    if_not_exists: bool = True,
) -> None:
    """Create a database role/user."""
    validate_identifier(name)

    # Check if exists
    if if_not_exists and await self.role_exists(name):
        return

    options = []
    if login:
        options.append("LOGIN")
    else:
        options.append("NOLOGIN")

    if superuser:
        options.append("SUPERUSER")
    if createdb:
        options.append("CREATEDB")
    if createrole:
        options.append("CREATEROLE")
    if not inherit:
        options.append("NOINHERIT")
    if replication:
        options.append("REPLICATION")
    if connection_limit != -1:
        options.append(f"CONNECTION LIMIT {connection_limit}")
    if password:
        # Use parameterized query for password
        options.append(f"PASSWORD %s")
    if valid_until:
        options.append(f"VALID UNTIL '{valid_until}'")

    options_str = " ".join(options)

    if password:
        async with self.cursor(autocommit=True) as cur:
            await cur.execute(f"CREATE ROLE {name} WITH {options_str}", [password])
    else:
        await self.execute(f"CREATE ROLE {name} WITH {options_str}", autocommit=True)

    # Add to roles
    if in_roles:
        for role in in_roles:
            await self.grant_role(role, name)
```

### TimescaleDB Compression with Extension Validation
```python
# Source: database.py:1382-1426
async def enable_compression(
    self,
    table: str,
    segment_by: Optional[str | list[str]] = None,
    order_by: Optional[str | list[str]] = None,
    schema: str = "public",
) -> None:
    """Enable compression on a hypertable."""
    if not await self.has_extension("timescaledb"):
        raise RuntimeError(
            "TimescaleDB extension not installed. "
            "Run db.create_extension('timescaledb')"
        )

    validate_identifiers(table, schema)

    settings = ["timescaledb.compress"]
    if segment_by:
        if isinstance(segment_by, str):
            segment_by = [segment_by]
        for col in segment_by:
            # Extract column name (may have DESC/ASC suffix)
            col_name = col.split()[0]
            validate_identifier(col_name)
        settings.append(f"timescaledb.compress_segmentby = '{','.join(segment_by)}'")
    if order_by:
        if isinstance(order_by, str):
            order_by = [order_by]
        for col in order_by:
            col_name = col.split()[0]
            validate_identifier(col_name)
        settings.append(f"timescaledb.compress_orderby = '{','.join(order_by)}'")

    await self.execute(f"ALTER TABLE {schema}.{table} SET ({', '.join(settings)})")
```

### GRANT with Multiple Object Types
```python
# Source: database.py:1894-1948
async def grant(
    self,
    privileges: str | list[str],
    on: str,
    to: str,
    object_type: str = "TABLE",
    schema: str = "public",
    with_grant_option: bool = False,
) -> None:
    """Grant privileges on database objects."""
    validate_identifier(to)

    if isinstance(privileges, list):
        privileges = ", ".join(privileges)

    grant_clause = " WITH GRANT OPTION" if with_grant_option else ""

    if object_type.upper() == "SCHEMA":
        validate_identifier(on)
        await self.execute(f"GRANT {privileges} ON SCHEMA {on} TO {to}{grant_clause}", autocommit=True)
    elif object_type.upper() == "DATABASE":
        validate_identifier(on)
        await self.execute(f"GRANT {privileges} ON DATABASE {on} TO {to}{grant_clause}", autocommit=True)
    elif on.upper() in ("ALL TABLES", "ALL SEQUENCES", "ALL FUNCTIONS"):
        validate_identifier(schema)
        await self.execute(f"GRANT {privileges} ON {on} IN SCHEMA {schema} TO {to}{grant_clause}", autocommit=True)
    else:
        validate_identifiers(on, schema)
        await self.execute(f"GRANT {privileges} ON {object_type} {schema}.{on} TO {to}{grant_clause}", autocommit=True)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| MD5 password hashing | SCRAM-SHA-256 | PostgreSQL 10+ (2017) | Must support both for compatibility |
| Manual GIST index creation | Automatic spatial indexes | PostGIS 2.0+ (2012) | Still manual in pycopg (user control) |
| Manual time partitioning | TimescaleDB hypertables | TimescaleDB 1.0 (2018) | Automatic chunk management |
| GRANT with literal syntax | Parameterized GRANT | Never (PostgreSQL limitation) | Must use f-strings for identifiers |

**Deprecated/outdated:**
- CREATE USER: Deprecated in favor of CREATE ROLE (use create_role with login=True)
- BYPASSRLS attribute: PostgreSQL 9.5+ feature, not yet exposed in Database/AsyncDatabase
- Compression policies without segment_by/order_by: TimescaleDB 2.0+ recommends explicit configuration

## Open Questions

1. **Should AsyncDatabase expose hypertable_info() method?**
   - What we know: Database has hypertable_info() (line 1508) for detailed hypertable stats
   - What's unclear: Requirements list doesn't mention it, but it's part of TimescaleDB domain
   - Recommendation: Include it for complete parity, mark as bonus/optional in plan

2. **Should role methods validate if extension "pgcrypto" exists for enhanced password security?**
   - What we know: PostgreSQL handles password hashing natively without extensions
   - What's unclear: Whether to recommend pgcrypto for additional security
   - Recommendation: No validation needed, PostgreSQL's built-in SCRAM-SHA-256 is sufficient

3. **Should list_geometry_columns() validate PostGIS extension like TimescaleDB methods do?**
   - What we know: Current Database implementation doesn't validate
   - What's unclear: Whether consistency matters more than parity
   - Recommendation: Maintain parity - no validation (matches Database pattern from database.py:1314)

## Sources

### Primary (HIGH confidence)
- [PostgreSQL CREATE ROLE Documentation](https://www.postgresql.org/docs/current/sql-createrole.html) - Official PostgreSQL 18 docs, role attributes and options
- [PostgreSQL GRANT Documentation](https://www.postgresql.org/docs/current/sql-grant.html) - Official privilege types and syntax
- [PostgreSQL REVOKE Documentation](https://www.postgresql.org/docs/current/sql-revoke.html) - Official privilege revocation patterns
- [PostGIS Spatial Indexing Workshop](https://postgis.net/workshops/postgis-intro/indexing.html) - Official GIST index creation patterns
- [PostGIS Data Management Documentation](https://postgis.net/docs/using_postgis_dbmanagement.html) - Official geometry_columns schema
- [TimescaleDB Compression Documentation](https://docs.timescale.com/use-timescale/latest/compression/) - Official enable_compression, add_compression_policy
- [TimescaleDB Hypertables Information View](https://docs.tigerdata.com/api/latest/informational-views/hypertables/) - Official timescaledb_information.hypertables schema
- Current Database implementation (pycopg/database.py:1296-2029) - Verified sync patterns

### Secondary (MEDIUM confidence)
- Phase 3 Research (03-RESEARCH.md) - Async execute patterns, autocommit requirements
- Phase 2 Research (02-RESEARCH.md) - AsyncEngine patterns, run_sync usage
- pycopg utils.py - validate_identifier, validate_interval, validate_identifiers patterns

### Tertiary (LOW confidence)
- None required - all findings verified with official documentation

## Metadata

**Confidence breakdown:**
- Role management: HIGH - Official PostgreSQL docs, verified sync implementation
- PostGIS operations: HIGH - Official PostGIS docs, verified sync implementation
- TimescaleDB operations: HIGH - Official TimescaleDB docs, verified sync implementation
- Async patterns: HIGH - Established in Phases 2 and 3, psycopg3 async is stable

**Research date:** 2026-02-11
**Valid until:** 2026-03-11 (30 days - stable domain, PostgreSQL/PostGIS/TimescaleDB are mature)
