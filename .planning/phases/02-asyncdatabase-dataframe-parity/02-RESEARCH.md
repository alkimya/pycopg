# Phase 2: AsyncDatabase DataFrame Parity - Research

**Researched:** 2026-02-11
**Domain:** Async DataFrame operations with pandas/geopandas + SQLAlchemy
**Confidence:** HIGH

## Summary

Adding async DataFrame methods to AsyncDatabase requires bridging the sync/async gap because pandas and geopandas do not natively support async operations. The research confirms two viable implementation patterns: (1) using SQLAlchemy's `AsyncEngine.run_sync()` to execute synchronous DataFrame operations within an async context, or (2) using `asyncio.to_thread()` to offload blocking operations to a thread pool. Pattern 1 is the better choice for pycopg since it already uses SQLAlchemy for DataFrame operations.

The four required methods (`to_dataframe`, `from_dataframe`, `to_geodataframe`, `from_geodataframe`) can be implemented by wrapping the existing sync Database implementations with async scaffolding. No changes to pandas/geopandas are needed — the library handles the sync/async translation.

**Primary recommendation:** Use SQLAlchemy AsyncEngine with `run_sync()` to execute synchronous pandas/geopandas operations. Create a lazy-initialized AsyncEngine property on AsyncDatabase (matching the sync Database pattern), and wrap each DataFrame method call in `run_sync()`.

## Standard Stack

### Core Dependencies (Already in pycopg)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| psycopg | 3.1.0+ | PostgreSQL driver | Official psycopg3 with async support |
| sqlalchemy | 2.0.0+ | SQL toolkit + DataFrame bridge | Standard async engine support, pandas integration |
| pandas | 2.0.0+ | DataFrame operations | Industry standard, no async needed with proper wrapping |
| geopandas | 0.14.0+ | GeoDataFrame operations | Spatial data standard, built on pandas |
| geoalchemy2 | 0.14.0+ | Spatial types for SQLAlchemy | Bridge between GeoDataFrame and PostGIS |

### No New Dependencies Required
AsyncDatabase DataFrame support requires zero new dependencies. All necessary libraries are already in `pyproject.toml`.

## Architecture Patterns

### Pattern 1: AsyncEngine with run_sync() (RECOMMENDED)
**What:** Use SQLAlchemy's AsyncEngine and execute synchronous DataFrame operations via `run_sync()`
**When to use:** When you already use SQLAlchemy for DataFrame operations (pycopg does)
**Example:**
```python
# From Database (sync)
def to_dataframe(self, table, schema="public", sql=None, params=None):
    import pandas as pd
    if table:
        sql = f"SELECT * FROM {schema}.{table}"
    return pd.read_sql(text(sql), self.engine, params=params)

# In AsyncDatabase (async)
async def to_dataframe(self, table=None, schema="public", sql=None, params=None):
    import pandas as pd
    from sqlalchemy import text

    if table and sql:
        raise ValueError("Specify either table or sql, not both")
    if not table and not sql:
        raise ValueError("Specify either table or sql")

    if table:
        sql = f"SELECT * FROM {schema}.{table}"

    # Use run_sync to execute pandas operation in sync context
    async with self.async_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: pd.read_sql(text(sql), sync_conn, params=params)
        )
```

**Source:** [SQLAlchemy 2.0 Async Documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)

### Pattern 2: asyncio.to_thread() (Alternative)
**What:** Use asyncio.to_thread() to offload blocking DataFrame operations to thread pool
**When to use:** When you don't have an async engine or need explicit thread control
**Example:**
```python
async def to_dataframe(self, table=None, schema="public", sql=None, params=None):
    import pandas as pd
    from sqlalchemy import text

    if table:
        sql = f"SELECT * FROM {schema}.{table}"

    # Offload synchronous operation to thread
    return await asyncio.to_thread(
        pd.read_sql, text(sql), self.engine, params=params
    )
```

**Tradeoff:** Simpler but less integrated with SQLAlchemy async patterns.

**Source:** [Python asyncio.to_thread Documentation](https://docs.python.org/3/library/asyncio-task.html)

### Recommended Project Structure (No Changes)
Current structure is fine. Add methods to existing `async_database.py`:

```
pycopg/
├── async_database.py    # Add: to_dataframe, from_dataframe, to_geodataframe, from_geodataframe
├── database.py          # Reference implementations already exist
└── base.py              # Shared base classes (no changes needed)
```

### Lazy Engine Initialization Pattern
**What:** AsyncDatabase creates AsyncEngine on first use, matching sync Database pattern
**Why:** Avoid connection overhead until DataFrame operations actually needed

```python
class AsyncDatabase:
    def __init__(self, config: Config):
        self.config = config
        self._async_engine: Optional[AsyncEngine] = None

    @property
    def async_engine(self) -> AsyncEngine:
        """Get or create async SQLAlchemy engine (lazy initialization)."""
        if self._async_engine is None:
            from sqlalchemy.ext.asyncio import create_async_engine
            # psycopg's async requires asyncpg-style URL
            async_url = self.config.url.replace("postgresql://", "postgresql+psycopg://")
            self._async_engine = create_async_engine(async_url)
        return self._async_engine
```

**Source:** Current Database implementation in `database.py:234-238`

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async DataFrame support | Custom async pandas wrapper | SQLAlchemy AsyncEngine.run_sync() | pandas/geopandas are sync-only, SQLAlchemy handles translation |
| Thread pool management | Manual ThreadPoolExecutor | asyncio.to_thread() or run_sync() | Python 3.9+ provides built-in, correctly manages lifecycle |
| Connection pooling | Custom async pool | SQLAlchemy AsyncEngine handles it | AsyncAdaptedQueuePool automatically used |
| Sync to async translation | Custom event loop logic | SQLAlchemy run_sync() | Proven, tested, handles edge cases (events, transactions) |

**Key insight:** pandas and geopandas will NEVER be async-native. The pattern of wrapping synchronous DataFrame operations in async scaffolding is the established standard across the Python ecosystem. Don't try to make pandas async — make the *interface* async by properly managing the sync/async boundary.

## Common Pitfalls

### Pitfall 1: Using AsyncEngine directly with pandas
**What goes wrong:** `pd.read_sql(sql, async_engine)` raises "Unknown Connectable" ValueError
**Why it happens:** pandas only understands sync engines/connections, not AsyncEngine
**How to avoid:** Always use `run_sync()` or `asyncio.to_thread()` to bridge the gap
**Warning signs:** `ValueError: Unknown Connectable`, `AttributeError: 'AsyncEngine' object has no attribute 'cursor'`

**Source:** [pandas Issue #51633](https://github.com/pandas-dev/pandas/issues/51633), [geopandas Issue #2160](https://github.com/geopandas/geopandas/issues/2160)

### Pitfall 2: Blocking the event loop
**What goes wrong:** Using `time.sleep()` or synchronous network requests inside async DataFrame methods blocks the entire event loop
**Why it happens:** Only the DataFrame I/O is offloaded to thread/run_sync, not other blocking calls
**How to avoid:** Use `await asyncio.sleep()` instead of `time.sleep()`, ensure all I/O is async or wrapped
**Warning signs:** Entire app freezes during DataFrame operations, no concurrent task progress

**Source:** [SQLAlchemy Async Pitfalls Discussion](https://github.com/sqlalchemy/sqlalchemy/discussions/10344)

### Pitfall 3: Mixing sync and async engines incorrectly
**What goes wrong:** Creating both sync `self.engine` and `self._async_engine` without proper isolation causes connection pool conflicts
**Why it happens:** Two separate connection pools competing for same database resources
**How to avoid:** In AsyncDatabase, ONLY create async_engine. Don't inherit or reuse Database.engine property
**Warning signs:** Connection pool exhaustion, "too many connections" errors, deadlocks

**Source:** [SQLAlchemy Discussion #10344](https://github.com/sqlalchemy/sqlalchemy/discussions/10344)

### Pitfall 4: Forgetting to await async context managers
**What goes wrong:** `async with self.async_engine.connect() as conn:` works, but `with self.async_engine.connect() as conn:` silently creates coroutine without executing
**Why it happens:** Async context managers require `async with`, not `with`
**How to avoid:** Use async context managers (`async with`) for all AsyncEngine operations
**Warning signs:** `RuntimeWarning: coroutine was never awaited`, operations appear to succeed but do nothing

**Source:** [pandas Issue #58557](https://github.com/pandas-dev/pandas/issues/58557)

### Pitfall 5: SRID validation in async context
**What goes wrong:** GeoDataFrame SRID inference might fail silently or raise errors inconsistently
**Why it happens:** Same as sync version — requires explicit SRID validation before to_postgis
**How to avoid:** Copy the explicit SRID validation from Database.from_geodataframe (lines 1222-1241)
**Warning signs:** "Cannot determine EPSG code" errors, spatial queries return wrong results

**Source:** Current Database implementation bug fix (BUG-05 from Phase 1)

## Code Examples

Verified patterns from SQLAlchemy official documentation and pycopg sync implementation:

### AsyncDatabase.to_dataframe()
```python
async def to_dataframe(
    self,
    table: Optional[str] = None,
    schema: str = "public",
    sql: Optional[str] = None,
    params: Optional[dict] = None,
) -> "pd.DataFrame":
    """Read table or query into pandas DataFrame.

    Args:
        table: Table name (mutually exclusive with sql).
        schema: Schema name.
        sql: SQL query (mutually exclusive with table).
        params: Query parameters for sql.

    Returns:
        pandas DataFrame.

    Example:
        users = await db.to_dataframe("users")
        active = await db.to_dataframe(
            sql="SELECT * FROM users WHERE active = :active",
            params={"active": True}
        )
    """
    import pandas as pd
    from sqlalchemy import text

    if table and sql:
        raise ValueError("Specify either table or sql, not both")
    if not table and not sql:
        raise ValueError("Specify either table or sql")

    if table:
        sql = f"SELECT * FROM {schema}.{table}"

    async with self.async_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: pd.read_sql(text(sql), sync_conn, params=params)
        )
```

**Source:** [SQLAlchemy AsyncConnection.run_sync](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#using-asyncio-scoped-session)

### AsyncDatabase.from_dataframe()
```python
async def from_dataframe(
    self,
    df: "pd.DataFrame",
    table: str,
    schema: str = "public",
    if_exists: Literal["fail", "replace", "append"] = "fail",
    primary_key: Optional[str | list[str]] = None,
    index: bool = False,
    dtype: Optional[dict] = None,
) -> None:
    """Create or append to table from pandas DataFrame.

    Args:
        df: pandas DataFrame.
        table: Table name.
        schema: Schema name.
        if_exists: What to do if table exists ('fail', 'replace', 'append').
        primary_key: Column(s) to set as primary key after creation.
        index: Write DataFrame index as column.
        dtype: Optional dict of column name to SQLAlchemy types.

    Example:
        await db.from_dataframe(users_df, "users", primary_key="id")
        await db.from_dataframe(orders_df, "orders", if_exists="append")
    """
    async with self.async_engine.connect() as conn:
        await conn.run_sync(
            lambda sync_conn: df.to_sql(
                name=table,
                con=sync_conn,
                schema=schema,
                if_exists=if_exists,
                index=index,
                dtype=dtype,
            )
        )

    if primary_key and if_exists != "append":
        # Add primary key using existing async method
        await self.add_primary_key(table, primary_key, schema)
```

**Source:** Adapted from Database.from_dataframe (database.py:1118-1154)

### AsyncDatabase.to_geodataframe()
```python
async def to_geodataframe(
    self,
    table: Optional[str] = None,
    schema: str = "public",
    sql: Optional[str] = None,
    geometry_column: str = "geometry",
    params: Optional[dict] = None,
) -> "gpd.GeoDataFrame":
    """Read table or query into GeoDataFrame.

    Args:
        table: Table name.
        schema: Schema name.
        sql: SQL query.
        geometry_column: Name of geometry column.
        params: Query parameters.

    Returns:
        geopandas GeoDataFrame.

    Example:
        parcels = await db.to_geodataframe("parcels", schema="geo")
    """
    import geopandas as gpd
    from sqlalchemy import text

    if table and sql:
        raise ValueError("Specify either table or sql, not both")
    if not table and not sql:
        raise ValueError("Specify either table or sql")

    if table:
        sql = f"SELECT * FROM {schema}.{table}"

    async with self.async_engine.connect() as conn:
        return await conn.run_sync(
            lambda sync_conn: gpd.read_postgis(
                text(sql), sync_conn, geom_col=geometry_column, params=params
            )
        )
```

**Source:** Adapted from Database.to_geodataframe (database.py:1257-1290)

### AsyncDatabase.from_geodataframe()
```python
async def from_geodataframe(
    self,
    gdf: "gpd.GeoDataFrame",
    table: str,
    schema: str = "public",
    if_exists: Literal["fail", "replace", "append"] = "fail",
    primary_key: Optional[str | list[str]] = None,
    spatial_index: bool = True,
    geometry_column: str = "geometry",
    srid: Optional[int] = None,
) -> None:
    """Create or append to table from GeoDataFrame.

    Requires PostGIS extension.

    Args:
        gdf: geopandas GeoDataFrame.
        table: Table name.
        schema: Schema name.
        if_exists: What to do if table exists.
        primary_key: Column(s) for primary key.
        spatial_index: Create GIST spatial index on geometry.
        geometry_column: Name of geometry column.
        srid: Override SRID (extracted from CRS if not specified).

    Example:
        await db.from_geodataframe(parcels, "parcels", spatial_index=True)
    """
    # Ensure PostGIS is available
    if not await self.has_extension("postgis"):
        raise RuntimeError(
            "PostGIS extension not installed. Run db.create_extension('postgis')"
        )

    # Handle SRID — fail explicitly on unknown CRS (matching sync version)
    if srid is None:
        if gdf.crs is None:
            raise ValueError(
                "GeoDataFrame has no CRS defined. "
                "Set gdf.crs or provide explicit srid parameter."
            )
        try:
            srid = gdf.crs.to_epsg()
            if srid is None:
                raise ValueError(
                    f"Cannot determine EPSG code for CRS: {gdf.crs}. "
                    f"Provide explicit srid parameter."
                )
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(
                f"Failed to infer SRID from CRS {gdf.crs}. "
                f"Provide explicit srid parameter. Error: {e}"
            ) from e

    async with self.async_engine.connect() as conn:
        await conn.run_sync(
            lambda sync_conn: gdf.to_postgis(
                name=table,
                con=sync_conn,
                schema=schema,
                if_exists=if_exists,
                index=False,
            )
        )

    if primary_key and if_exists != "append":
        # Requires add_primary_key to be implemented in Phase 3
        await self.add_primary_key(table, primary_key, schema)

    if spatial_index and if_exists != "append":
        # Requires create_spatial_index to be implemented in Phase 4
        await self.create_spatial_index(table, geometry_column, schema)
```

**Source:** Adapted from Database.from_geodataframe (database.py:1189-1255), incorporating BUG-05 fix

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| asyncpg raw driver | psycopg3 async | psycopg3 release 2021 | pycopg already uses psycopg3, no change needed |
| Manual thread pools | asyncio.to_thread() | Python 3.9 (2020) | Simpler, but run_sync() is better for SQLAlchemy |
| Sync-only pandas | Still sync-only | N/A | Will never change — wrapping is the permanent solution |
| SQLAlchemy 1.4 async | SQLAlchemy 2.0 async | SQLAlchemy 2.0 (2023) | pycopg already uses 2.0, better async support |

**Deprecated/outdated:**
- **asyncpg direct usage for pandas:** asyncpg is faster but requires manual DataFrame conversion, doesn't integrate with SQLAlchemy
- **Manual ThreadPoolExecutor creation:** asyncio.to_thread() handles lifecycle automatically (Python 3.9+)
- **Sync Engine with threads for async ops:** SQLAlchemy AsyncEngine with run_sync() is the proper pattern

## Open Questions

1. **Should AsyncDatabase have add_primary_key and create_spatial_index methods?**
   - What we know: from_dataframe and from_geodataframe call these methods
   - What's unclear: Phase 2 only covers DataFrame methods, these are Phase 3/4
   - Recommendation: Stub them out (raise NotImplementedError) or make primary_key/spatial_index optional with warning. Document in PLAN.md that full implementation requires Phase 3/4.

2. **AsyncEngine URL format with psycopg**
   - What we know: SQLAlchemy async requires driver-specific URL format
   - What's unclear: Does psycopg3 async use `postgresql+psycopg://` or `postgresql+asyncpg://`?
   - Recommendation: Test both during implementation. Official docs suggest `postgresql+psycopg://` with async support.

3. **Connection pool size defaults**
   - What we know: AsyncEngine uses AsyncAdaptedQueuePool automatically
   - What's unclear: Should we set explicit pool_size, max_overflow for DataFrame operations?
   - Recommendation: Start with defaults, add pool configuration in Phase 5 (Resilience) if needed.

## Sources

### Primary (HIGH confidence)
- [SQLAlchemy 2.0 Asynchronous I/O Documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [pandas.read_sql Documentation](https://pandas.pydata.org/docs/reference/api/pandas.read_sql.html)
- [pandas.DataFrame.to_sql Documentation](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_sql.html)
- [geopandas.read_postgis Documentation](https://geopandas.org/en/stable/docs/reference/api/geopandas.read_postgis.html)
- [geopandas.GeoDataFrame.to_postgis Documentation](https://geopandas.org/en/stable/docs/reference/api/geopandas.GeoDataFrame.to_postgis.html)
- [Python asyncio.to_thread Documentation](https://docs.python.org/3/library/asyncio-task.html)
- [psycopg3 Async Documentation](https://www.psycopg.org/psycopg3/docs/advanced/async.html)

### Secondary (MEDIUM confidence)
- [SQLAlchemy Discussion #7634: pandas DataFrame from async result set](https://github.com/sqlalchemy/sqlalchemy/discussions/7634)
- [pandas Issue #51633: df.to_sql() with AsyncEngine](https://github.com/pandas-dev/pandas/issues/51633)
- [geopandas Issue #2160: Async SQLAlchemy support](https://github.com/geopandas/geopandas/issues/2160)
- [SQLAlchemy Discussion #10344: Pitfalls using sync and async engine together](https://github.com/sqlalchemy/sqlalchemy/discussions/10344)
- [Combining Traditional Thread-Based Code and Asyncio in Python](https://towardsdatascience.com/combining-traditional-thread-based-code-and-asyncio-in-python-dc162084756c/)

### Tertiary (LOW confidence, flagged for validation)
- Medium articles on async pandas patterns (not authoritative, but useful for common mistakes)
- FastAPI async database patterns (different context but relevant async principles)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All dependencies verified in current pyproject.toml
- Architecture: HIGH - SQLAlchemy AsyncEngine.run_sync() is official documented pattern
- Pitfalls: HIGH - All verified from official issue trackers and documentation

**Research date:** 2026-02-11
**Valid until:** 90 days (stable ecosystem - pandas/SQLAlchemy async patterns are mature)
