"""
Centralized SQL queries for pycopg.

Contains SQL query constants used across Database and AsyncDatabase.
This reduces duplication and makes queries easier to maintain.
"""

# =============================================================================
# SCHEMA QUERIES
# =============================================================================

LIST_SCHEMAS = """
    SELECT schema_name
    FROM information_schema.schemata
    WHERE schema_name NOT LIKE 'pg_%'
    AND schema_name != 'information_schema'
    ORDER BY schema_name
"""

SCHEMA_EXISTS = """
    SELECT 1 FROM information_schema.schemata WHERE schema_name = %s
"""

# =============================================================================
# TABLE QUERIES
# =============================================================================

LIST_TABLES = """
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = %s
    AND table_type = 'BASE TABLE'
    ORDER BY table_name
"""

TABLE_EXISTS = """
    SELECT 1 FROM information_schema.tables
    WHERE table_schema = %s AND table_name = %s
"""

TABLE_INFO = """
    SELECT
        column_name,
        data_type,
        is_nullable,
        column_default,
        ordinal_position,
        character_maximum_length,
        numeric_precision,
        numeric_scale
    FROM information_schema.columns
    WHERE table_schema = %s AND table_name = %s
    ORDER BY ordinal_position
"""

GET_COLUMNS = """
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_schema = %s AND table_name = %s
    ORDER BY ordinal_position
"""

# Simplified version for AsyncDatabase
TABLE_INFO_SIMPLE = """
    SELECT
        column_name,
        data_type,
        is_nullable,
        column_default,
        ordinal_position
    FROM information_schema.columns
    WHERE table_schema = %s AND table_name = %s
    ORDER BY ordinal_position
"""

ROW_COUNT = """
    SELECT reltuples::bigint AS count
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = %s AND c.relname = %s
"""

# =============================================================================
# DATABASE QUERIES
# =============================================================================

LIST_DATABASES = """
    SELECT datname FROM pg_database
    WHERE datistemplate = false
    ORDER BY datname
"""

DATABASE_EXISTS = """
    SELECT 1 FROM pg_database WHERE datname = %s
"""

DATABASE_SIZE_PRETTY = """
    SELECT pg_size_pretty(pg_database_size(%s)) AS size
"""

DATABASE_SIZE = """
    SELECT pg_database_size(%s) AS size
"""

# =============================================================================
# EXTENSION QUERIES
# =============================================================================

LIST_EXTENSIONS = """
    SELECT e.extname, e.extversion, n.nspname
    FROM pg_extension e
    JOIN pg_namespace n ON e.extnamespace = n.oid
    ORDER BY e.extname
"""

EXTENSION_EXISTS = """
    SELECT 1 FROM pg_extension WHERE extname = %s
"""

# =============================================================================
# INDEX QUERIES
# =============================================================================

LIST_INDEXES = """
    SELECT
        i.relname AS index_name,
        am.amname AS index_type,
        pg_get_indexdef(i.oid) AS index_def
    FROM pg_index idx
    JOIN pg_class t ON t.oid = idx.indrelid
    JOIN pg_class i ON i.oid = idx.indexrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    JOIN pg_am am ON am.oid = i.relam
    WHERE n.nspname = %s AND t.relname = %s
    ORDER BY i.relname
"""

# =============================================================================
# CONSTRAINT QUERIES
# =============================================================================

LIST_CONSTRAINTS = """
    SELECT
        c.conname AS constraint_name,
        c.contype AS constraint_type,
        pg_get_constraintdef(c.oid) AS constraint_def
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = %s AND t.relname = %s
    ORDER BY c.conname
"""

# =============================================================================
# ROLE QUERIES
# =============================================================================

ROLE_EXISTS = """
    SELECT 1 FROM pg_roles WHERE rolname = %s
"""

LIST_ROLES = """
    SELECT
        rolname AS name,
        rolsuper AS superuser,
        rolcreaterole AS createrole,
        rolcreatedb AS createdb,
        rolcanlogin AS login,
        rolreplication AS replication,
        rolconnlimit AS connection_limit,
        rolvaliduntil AS valid_until
    FROM pg_roles
    {where_clause}
    ORDER BY rolname
"""

# Simplified version for AsyncDatabase
LIST_ROLES_SIMPLE = """
    SELECT
        rolname AS name,
        rolsuper AS superuser,
        rolcreaterole AS createrole,
        rolcreatedb AS createdb,
        rolcanlogin AS login
    FROM pg_roles
    {where_clause}
    ORDER BY rolname
"""

LIST_ROLE_MEMBERS = """
    SELECT m.rolname AS member
    FROM pg_auth_members am
    JOIN pg_roles r ON r.oid = am.roleid
    JOIN pg_roles m ON m.oid = am.member
    WHERE r.rolname = %s
    ORDER BY m.rolname
"""

LIST_ROLE_GRANTS = """
    SELECT
        table_schema AS schema,
        table_name AS object_name,
        privilege_type AS privilege
    FROM information_schema.role_table_grants
    WHERE grantee = %s
    ORDER BY table_schema, table_name, privilege_type
"""

# =============================================================================
# SIZE QUERIES
# =============================================================================

TABLE_SIZE_PRETTY = """
    SELECT pg_size_pretty(pg_total_relation_size(%s)) AS size
"""

TABLE_SIZE = """
    SELECT pg_total_relation_size(%s) AS size
"""

TABLE_SIZES = """
    SELECT
        t.tablename AS table_name,
        pg_size_pretty(pg_total_relation_size(format('%%I.%%I', t.schemaname, t.tablename))) AS total_size,
        pg_size_pretty(pg_relation_size(format('%%I.%%I', t.schemaname, t.tablename))) AS data_size,
        pg_size_pretty(pg_indexes_size(format('%%I.%%I', t.schemaname, t.tablename))) AS index_size
    FROM pg_tables t
    WHERE t.schemaname = %s
    ORDER BY pg_total_relation_size(format('%%I.%%I', t.schemaname, t.tablename)) DESC
    LIMIT %s
"""

# =============================================================================
# POSTGIS QUERIES
# =============================================================================

LIST_GEOMETRY_COLUMNS = """
    SELECT
        f_table_schema AS schema,
        f_table_name AS table_name,
        f_geometry_column AS column_name,
        coord_dimension AS dimensions,
        srid,
        type AS geometry_type
    FROM geometry_columns
    {where_clause}
    ORDER BY f_table_schema, f_table_name
"""

# =============================================================================
# TIMESCALEDB QUERIES
# =============================================================================

LIST_HYPERTABLES = """
    SELECT
        hypertable_schema AS schema,
        hypertable_name AS table_name,
        num_dimensions,
        num_chunks,
        compression_enabled
    FROM timescaledb_information.hypertables
    ORDER BY hypertable_schema, hypertable_name
"""

HYPERTABLE_INFO = """
    SELECT
        hypertable_size(format('%I.%I', %s, %s)) AS total_size,
        hypertable_detailed_size(format('%I.%I', %s, %s)) AS detailed_size
"""
