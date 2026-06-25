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

PRIMARY_KEY = """
    SELECT
        c.conname AS constraint_name,
        a.attname AS column_name
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(conkey_element, ord)
        ON true
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.conkey_element
    WHERE n.nspname = %s AND t.relname = %s
    AND c.contype = 'p'
    ORDER BY k.ord
"""

FOREIGN_KEYS = """
    SELECT
        c.conname AS constraint_name,
        a_local.attname AS column_name,
        t_ref.relname AS referenced_table,
        a_ref.attname AS referenced_column
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    JOIN pg_class t_ref ON t_ref.oid = c.confrelid
    JOIN LATERAL unnest(c.conkey, c.confkey) WITH ORDINALITY AS k(local_num, ref_num, ord)
        ON true
    JOIN pg_attribute a_local ON a_local.attrelid = c.conrelid AND a_local.attnum = k.local_num
    JOIN pg_attribute a_ref ON a_ref.attrelid = c.confrelid AND a_ref.attnum = k.ref_num
    WHERE n.nspname = %s AND t.relname = %s
    AND c.contype = 'f'
    ORDER BY c.conname, k.ord
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
        hypertable_size(format('%%I.%%I', %s::text, %s::text)) AS total_size,
        hypertable_detailed_size(format('%%I.%%I', %s::text, %s::text)) AS detailed_size
"""

# TSDB_SHOW_CHUNKS — list chunks for a hypertable, optionally filtered by
# older_than / newer_than bounds (appended by the builder at call time).
#
# JOIN key uses format('%%I.%%I', ...) — the double %% is required because
# psycopg eats a single % in query strings; the result is the literal SQL
# format('%I.%I', ...) which PostgreSQL then interprets as a quoted-identifier
# cast to regclass.  Same convention as HYPERTABLE_INFO / TABLE_SIZES above.
#
# The {schema}.{table} and the optional bound fragments are interpolated by
# the builder in timescale.py after validate_identifiers().  Runtime VALUES
# (older_than / newer_than) are bound as %s / %s::interval — never
# interpolated into the SQL string.
#
# Ordering is range_start ASC (oldest first per D-05).  Lexicographic sort on
# chunk names is intentionally AVOIDED (_hyper_N_10 sorts before _hyper_N_2).
TSDB_SHOW_CHUNKS = (
    "SELECT c.chunk_schema || '.' || c.chunk_name AS chunk_name "
    "FROM show_chunks('{schema}.{table}'{older_arg}{newer_arg}) AS sc "
    "JOIN timescaledb_information.chunks c "
    "  ON format('%%I.%%I', c.chunk_schema, c.chunk_name)::regclass = sc "
    "ORDER BY c.range_start ASC"
)

# TSDB_DROP_CHUNKS — side-effecting call issued AFTER the preview list has
# been captured via TSDB_SHOW_CHUNKS.  The schema/table and bound fragments
# are interpolated identically; runtime VALUES bind as %s / %s::interval.
TSDB_DROP_CHUNKS = (
    "SELECT drop_chunks('{schema}.{table}'{older_arg}{newer_arg})"
)

# =============================================================================
# ETL QUERIES
# =============================================================================

ETL_INIT_PIPELINE_RUNS = """
    CREATE TABLE IF NOT EXISTS pipeline_runs (
        run_id BIGSERIAL PRIMARY KEY,
        pipeline_name TEXT NOT NULL,
        started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        finished_at TIMESTAMPTZ,
        status TEXT NOT NULL CHECK (status IN ('running','success','failed')),
        rows_extracted BIGINT,
        rows_loaded BIGINT,
        error_message TEXT,
        error_traceback TEXT,
        watermark JSONB
    )
"""

ETL_INSERT_RUN = """
    INSERT INTO pipeline_runs (pipeline_name, status, started_at)
    VALUES (%s, %s, %s)
    RETURNING run_id
"""

ETL_UPDATE_RUN = """
    UPDATE pipeline_runs
    SET status = %s,
        finished_at = %s,
        rows_extracted = %s,
        rows_loaded = %s,
        error_message = %s,
        error_traceback = %s
    WHERE run_id = %s
"""

ETL_LIST_RUNS = """
    SELECT *
    FROM pipeline_runs
    WHERE pipeline_name = %s
    ORDER BY started_at DESC
    LIMIT %s
"""

ETL_GET_LAST_RUN = """
    SELECT *
    FROM pipeline_runs
    WHERE pipeline_name = %s
    ORDER BY started_at DESC
    LIMIT 1
"""

ETL_GET_RUN = """
    SELECT *
    FROM pipeline_runs
    WHERE run_id = %s
"""

ETL_GET_LAST_WATERMARK = """
    SELECT watermark
    FROM pipeline_runs
    WHERE pipeline_name = %s
      AND status = 'success'
      AND watermark IS NOT NULL
    ORDER BY started_at DESC
    LIMIT 1
"""

ETL_UPDATE_RUN_WATERMARK = """
    UPDATE pipeline_runs
    SET status = %s,
        finished_at = %s,
        rows_extracted = %s,
        rows_loaded = %s,
        error_message = %s,
        error_traceback = %s,
        watermark = %s
    WHERE run_id = %s
"""
