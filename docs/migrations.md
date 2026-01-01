# Migrations

pycopg includes a simple SQL-based migration system for managing database schema changes.

## Quick Start

### 1. Create Migration Directory

```bash
mkdir migrations
```

### 2. Create Migration Files

```sql
-- migrations/001_create_users.sql

-- UP
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- DOWN
DROP TABLE users;
```

### 3. Run Migrations

```python
from pycopg import Database, Migrator

db = Database.from_env()
migrator = Migrator(db, "migrations/")

# Check status
status = migrator.status()
print(f"Applied: {status['applied_count']}, Pending: {status['pending_count']}")

# Run pending migrations
applied = migrator.migrate()
for m in applied:
    print(f"Applied: {m}")
```

## Migration File Format

### File Naming

Migration files must follow this naming convention:

```
NNN_description.sql
```

- `NNN`: Version number (1, 01, 001, etc.)
- `description`: Snake_case description
- `.sql`: Required extension

Examples:
- `001_create_users.sql`
- `002_add_email_column.sql`
- `003_create_orders.sql`

### File Structure

Migrations can have optional UP and DOWN sections:

```sql
-- Migration: create_users
-- Created: 2024-01-15

-- UP
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);

-- DOWN
DROP TABLE users;
```

If no UP/DOWN sections are present, the entire file is treated as the UP migration.

## Migrator API

### Creating a Migrator

```python
from pycopg import Database, Migrator

db = Database.from_env()
migrator = Migrator(db, "migrations/")

# With custom tracking table
migrator = Migrator(db, "migrations/", table="my_migrations")
```

### Checking Status

```python
status = migrator.status()
# {
#     'applied_count': 5,
#     'pending_count': 2,
#     'applied': [
#         {'version': 1, 'name': 'create_users', 'applied_at': datetime(...)},
#         ...
#     ],
#     'pending': [
#         {'version': 6, 'name': 'add_audit_log'},
#         {'version': 7, 'name': 'create_reports'},
#     ]
# }
```

### Running Migrations

```python
# Run all pending migrations
applied = migrator.migrate()
for m in applied:
    print(f"Applied migration: {m.version:03d}_{m.name}")

# Run up to a specific version
applied = migrator.migrate(target=5)
```

### Rolling Back

```python
# Rollback last migration
rolled_back = migrator.rollback()

# Rollback last 3 migrations
rolled_back = migrator.rollback(steps=3)

for info in rolled_back:
    print(f"Rolled back: {info['version']:03d}_{info['name']}")
```

### Creating New Migrations

```python
# Create a new migration file
path = migrator.create("add_orders_table")
print(f"Created: {path}")
# Created: migrations/006_add_orders_table.sql
```

The created file includes a template:

```sql
-- Migration: add_orders_table
-- Created: 2024-01-15T10:30:00

-- UP
-- Write your migration SQL here


-- DOWN
-- Write your rollback SQL here (optional)

```

### Listing Migrations

```python
# Get pending migrations
pending = migrator.pending()
for m in pending:
    print(f"Pending: {m.version:03d}_{m.name}")

# Get applied migrations
applied = migrator.applied()
for info in applied:
    print(f"Applied: {info['version']:03d}_{info['name']} at {info['applied_at']}")
```

## Migration Tracking

Migrations are tracked in a database table (default: `schema_migrations`):

```sql
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

## Examples

### Creating Tables

```sql
-- 001_create_users.sql

-- UP
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_username ON users(username);

-- DOWN
DROP TABLE users;
```

### Adding Columns

```sql
-- 002_add_user_profile.sql

-- UP
ALTER TABLE users ADD COLUMN full_name TEXT;
ALTER TABLE users ADD COLUMN avatar_url TEXT;
ALTER TABLE users ADD COLUMN bio TEXT;

-- DOWN
ALTER TABLE users DROP COLUMN bio;
ALTER TABLE users DROP COLUMN avatar_url;
ALTER TABLE users DROP COLUMN full_name;
```

### Creating Relations

```sql
-- 003_create_orders.sql

-- UP
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    total_amount DECIMAL(10, 2) NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_orders_user_id ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status);

-- DOWN
DROP TABLE orders;
```

### Data Migrations

```sql
-- 004_backfill_user_slugs.sql

-- UP
ALTER TABLE users ADD COLUMN slug TEXT;

UPDATE users SET slug = LOWER(REPLACE(username, ' ', '-'));

ALTER TABLE users ALTER COLUMN slug SET NOT NULL;
CREATE UNIQUE INDEX idx_users_slug ON users(slug);

-- DOWN
DROP INDEX idx_users_slug;
ALTER TABLE users DROP COLUMN slug;
```

### Complex Migrations

```sql
-- 005_restructure_permissions.sql

-- UP
-- Create new tables
CREATE TABLE roles (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    permissions JSONB DEFAULT '[]'
);

CREATE TABLE user_roles (
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    role_id INTEGER REFERENCES roles(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, role_id)
);

-- Migrate existing data
INSERT INTO roles (name, permissions)
SELECT DISTINCT role, '[]'::jsonb
FROM users
WHERE role IS NOT NULL;

INSERT INTO user_roles (user_id, role_id)
SELECT u.id, r.id
FROM users u
JOIN roles r ON u.role = r.name
WHERE u.role IS NOT NULL;

-- Remove old column
ALTER TABLE users DROP COLUMN role;

-- DOWN
ALTER TABLE users ADD COLUMN role TEXT;

UPDATE users SET role = (
    SELECT r.name FROM roles r
    JOIN user_roles ur ON r.id = ur.role_id
    WHERE ur.user_id = users.id
    LIMIT 1
);

DROP TABLE user_roles;
DROP TABLE roles;
```

## Error Handling

```python
from pycopg.exceptions import MigrationError

try:
    migrator.migrate()
except MigrationError as e:
    print(f"Migration failed: {e}")
    # The failed migration is not marked as applied
    # Fix the issue and run again
```

## Best Practices

### 1. Make Migrations Idempotent

```sql
-- Good: Use IF NOT EXISTS
CREATE TABLE IF NOT EXISTS users (...);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Bad: Will fail if run twice
CREATE TABLE users (...);
```

### 2. Always Include DOWN Migrations

```sql
-- UP
ALTER TABLE users ADD COLUMN phone TEXT;

-- DOWN
ALTER TABLE users DROP COLUMN phone;
```

### 3. Keep Migrations Small and Focused

```
001_create_users.sql       # One table
002_create_orders.sql      # One table
003_add_user_email_index.sql  # One index
```

### 4. Never Modify Applied Migrations

Once a migration is applied, create a new migration for changes:

```
001_create_users.sql          # Original
002_fix_users_email.sql       # Fix instead of modifying 001
```

### 5. Test Migrations Both Directions

```python
# Apply
migrator.migrate()

# Rollback
migrator.rollback()

# Re-apply
migrator.migrate()
```
