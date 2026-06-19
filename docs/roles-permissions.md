# Roles & Permissions

pycopg provides a `db.admin.*` (and `async_db.admin.*`) accessor namespace for
comprehensive role and permission management for PostgreSQL.

## Access Pattern

```python
from pycopg import Database

db = Database.from_env()

# Sync: db.admin is initialized lazily on first access
db.admin.create_role("appuser", password="secret123", login=True)
```

```python
from pycopg import AsyncDatabase

async_db = AsyncDatabase.from_env()

# Async: async_db.admin mirrors the sync API with awaited methods
await async_db.admin.create_role("appuser", password="secret123", login=True)
```

> **Note:** The flat `db.*` methods (e.g. `db.create_role`) were removed in v0.7.0.
> Use `db.admin.*` instead.
> See [MIGRATION.md](https://github.com/alkimya/pycopg/blob/main/MIGRATION.md) for the complete name mapping.

## Creating Roles

### Basic User

```python
# Create a user that can log in
db.admin.create_role("appuser", password="secret123", login=True)
```

### With Options

```python
db.admin.create_role(
    "admin",
    password="secret",
    login=True,
    superuser=True,           # Full privileges
    createdb=True,            # Can create databases
    createrole=True,          # Can create other roles
    inherit=True,             # Inherit privileges from member roles
    replication=False,        # Can initiate replication
    connection_limit=10,      # Max concurrent connections (-1 = unlimited)
    valid_until="2025-12-31", # Password expiration
    if_not_exists=True,       # Don't error if exists
)
```

### Group Roles

Group roles don't log in but grant permissions to members.

```python
# Create a group role
db.admin.create_role("readonly", login=False)

# Create user in the group
db.admin.create_role("analyst", password="secret", login=True, in_roles=["readonly"])
```

## Managing Roles

### Alter Role

```python
# Change password
db.admin.alter_role("appuser", password="newpassword")

# Change connection limit
db.admin.alter_role("appuser", connection_limit=20)

# Disable login
db.admin.alter_role("appuser", login=False)

# Rename role
db.admin.alter_role("oldname", rename_to="newname")

# Multiple changes
db.admin.alter_role(
    "appuser",
    password="newpass",
    connection_limit=50,
    valid_until="2025-06-30"
)
```

### Drop Role

```python
db.admin.drop_role("olduser")
db.admin.drop_role("olduser", if_exists=True)
```

### Check Role Exists

```python
if db.admin.role_exists("appuser"):
    print("Role exists")
```

### List Roles

```python
roles = db.admin.list_roles()
# [
#     {
#         'name': 'admin',
#         'superuser': True,
#         'createrole': True,
#         'createdb': True,
#         'login': True,
#         'replication': False,
#         'connection_limit': -1,
#         'valid_until': None
#     },
#     ...
# ]

# Include system roles (pg_*)
all_roles = db.admin.list_roles(include_system=True)
```

## Role Membership

### Grant Role

```python
# Make 'analyst' a member of 'readonly'
db.admin.grant_role("readonly", "analyst")

# With admin option (can grant role to others)
db.admin.grant_role("admin", "lead_dev", with_admin=True)
```

### Revoke Role

```python
db.admin.revoke_role("readonly", "analyst")
```

### List Role Members

```python
members = db.admin.list_role_members("readonly")
# ['analyst', 'reporter', 'dashboard_user']
```

## Granting Privileges

### On Tables

```python
# Grant SELECT
db.admin.grant("SELECT", "users", "readonly")

# Grant multiple privileges
db.admin.grant(["SELECT", "INSERT", "UPDATE"], "orders", "appuser")

# Grant all privileges
db.admin.grant("ALL", "products", "admin")
```

### On All Tables in Schema

```python
# Grant SELECT on all tables in public schema
db.admin.grant("SELECT", "ALL TABLES", "readonly", schema="public")

# Grant all on all tables
db.admin.grant("ALL", "ALL TABLES", "admin", schema="app")
```

### On Schemas

```python
# Grant USAGE (required to access objects in schema)
db.admin.grant("USAGE", "app", "appuser", object_type="SCHEMA")

# Grant CREATE (can create objects in schema)
db.admin.grant("CREATE", "app", "admin", object_type="SCHEMA")

# Grant all
db.admin.grant("ALL", "app", "admin", object_type="SCHEMA")
```

### On Databases

```python
# Grant CONNECT
db.admin.grant("CONNECT", "mydb", "appuser", object_type="DATABASE")

# Grant CREATE (can create schemas)
db.admin.grant("CREATE", "mydb", "admin", object_type="DATABASE")
```

### With Grant Option

```python
# Allow grantee to grant to others
db.admin.grant("SELECT", "users", "team_lead", with_grant_option=True)
```

## Revoking Privileges

### Basic Revoke

```python
db.admin.revoke("INSERT", "users", "readonly")
db.admin.revoke(["INSERT", "UPDATE", "DELETE"], "orders", "readonly")
```

### Cascade Revoke

```python
# Revoke from dependent grants too
db.admin.revoke("ALL", "users", "admin", cascade=True)
```

### On Schemas and Databases

```python
db.admin.revoke("USAGE", "app", "olduser", object_type="SCHEMA")
db.admin.revoke("CONNECT", "mydb", "olduser", object_type="DATABASE")
```

## Listing Grants

```python
grants = db.admin.list_role_grants("appuser")
# [
#     {'schema': 'public', 'object_name': 'users', 'privilege': 'SELECT'},
#     {'schema': 'public', 'object_name': 'users', 'privilege': 'INSERT'},
#     {'schema': 'public', 'object_name': 'orders', 'privilege': 'SELECT'},
#     ...
# ]
```

## Common Patterns

### Read-Only User

```python
# Create read-only role
db.admin.create_role("readonly", login=False)
db.admin.grant("USAGE", "public", "readonly", object_type="SCHEMA")
db.admin.grant("SELECT", "ALL TABLES", "readonly", schema="public")

# Create read-only user
db.admin.create_role("reader", password="secret", login=True, in_roles=["readonly"])
```

### Application User

```python
# Create role with typical app permissions
db.admin.create_role("appuser", password="secret", login=True)
db.admin.grant("USAGE", "public", "appuser", object_type="SCHEMA")
db.admin.grant(["SELECT", "INSERT", "UPDATE", "DELETE"], "ALL TABLES", "appuser", schema="public")
db.admin.grant(["USAGE", "SELECT"], "ALL SEQUENCES", "appuser", schema="public")
```

### Admin User

```python
db.admin.create_role(
    "admin",
    password="secret",
    login=True,
    superuser=False,
    createdb=True,
    createrole=True,
)
db.admin.grant("ALL", "ALL TABLES", "admin", schema="public")
db.admin.grant("ALL", "public", "admin", object_type="SCHEMA")
```

### Team Hierarchy

```python
# Create team roles
db.admin.create_role("engineering", login=False)
db.admin.create_role("senior_engineers", login=False, in_roles=["engineering"])

# Grant permissions to groups
db.admin.grant("SELECT", "ALL TABLES", "engineering", schema="public")
db.admin.grant(["INSERT", "UPDATE"], "code_reviews", "engineering")
db.admin.grant("DELETE", "code_reviews", "senior_engineers")

# Create users in teams
db.admin.create_role("alice", password="secret", login=True, in_roles=["engineering"])
db.admin.create_role("bob", password="secret", login=True, in_roles=["senior_engineers"])
```

## Row-Level Security

For fine-grained access control, use PostgreSQL's RLS.

```python
# Enable RLS on table
db.execute("ALTER TABLE orders ENABLE ROW LEVEL SECURITY")

# Create policy for users to see only their orders
db.execute("""
    CREATE POLICY orders_user_policy ON orders
    FOR ALL
    TO appuser
    USING (user_id = current_setting('app.current_user_id')::integer)
""")

# Force RLS for table owner too
db.execute("ALTER TABLE orders FORCE ROW LEVEL SECURITY")
```

## Best Practices

### 1. Use Role Hierarchy

```python
# Don't grant directly to users
# Instead, create role groups

# Base roles
db.admin.create_role("read_access", login=False)
db.admin.create_role("write_access", login=False, in_roles=["read_access"])
db.admin.create_role("admin_access", login=False, in_roles=["write_access"])

# Users inherit from roles
db.admin.create_role("alice", password="...", in_roles=["write_access"])
```

### 2. Principle of Least Privilege

```python
# Grant minimum required permissions
db.admin.grant("SELECT", "users", "readonly")  # Not ALL

# Be specific about tables
db.admin.grant("SELECT", "public_data", "readonly")  # Not ALL TABLES
```

### 3. Use Separate Roles for Apps

```python
# Each app gets its own role
db.admin.create_role("webapp", password="...", login=True)
db.admin.create_role("worker", password="...", login=True)
db.admin.create_role("analytics", password="...", login=True)
```

### 4. Regular Audits

```python
# Review all roles
for role in db.admin.list_roles():
    print(f"{role['name']}: login={role['login']}, super={role['superuser']}")
    grants = db.admin.list_role_grants(role['name'])
    for g in grants:
        print(f"  - {g['privilege']} on {g['schema']}.{g['object_name']}")
```
