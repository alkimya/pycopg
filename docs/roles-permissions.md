# Roles & Permissions

pycopg provides comprehensive role and permission management for PostgreSQL.

## Creating Roles

### Basic User

```python
# Create a user that can log in
db.create_role("appuser", password="secret123", login=True)
```

### With Options

```python
db.create_role(
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
db.create_role("readonly", login=False)

# Create user in the group
db.create_role("analyst", password="secret", login=True, in_roles=["readonly"])
```

## Managing Roles

### Alter Role

```python
# Change password
db.alter_role("appuser", password="newpassword")

# Change connection limit
db.alter_role("appuser", connection_limit=20)

# Disable login
db.alter_role("appuser", login=False)

# Rename role
db.alter_role("oldname", rename_to="newname")

# Multiple changes
db.alter_role(
    "appuser",
    password="newpass",
    connection_limit=50,
    valid_until="2025-06-30"
)
```

### Drop Role

```python
db.drop_role("olduser")
db.drop_role("olduser", if_exists=True)
```

### Check Role Exists

```python
if db.role_exists("appuser"):
    print("Role exists")
```

### List Roles

```python
roles = db.list_roles()
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
all_roles = db.list_roles(include_system=True)
```

## Role Membership

### Grant Role

```python
# Make 'analyst' a member of 'readonly'
db.grant_role("readonly", "analyst")

# With admin option (can grant role to others)
db.grant_role("admin", "lead_dev", with_admin=True)
```

### Revoke Role

```python
db.revoke_role("readonly", "analyst")
```

### List Role Members

```python
members = db.list_role_members("readonly")
# ['analyst', 'reporter', 'dashboard_user']
```

## Granting Privileges

### On Tables

```python
# Grant SELECT
db.grant("SELECT", "users", "readonly")

# Grant multiple privileges
db.grant(["SELECT", "INSERT", "UPDATE"], "orders", "appuser")

# Grant all privileges
db.grant("ALL", "products", "admin")
```

### On All Tables in Schema

```python
# Grant SELECT on all tables in public schema
db.grant("SELECT", "ALL TABLES", "readonly", schema="public")

# Grant all on all tables
db.grant("ALL", "ALL TABLES", "admin", schema="app")
```

### On Schemas

```python
# Grant USAGE (required to access objects in schema)
db.grant("USAGE", "app", "appuser", object_type="SCHEMA")

# Grant CREATE (can create objects in schema)
db.grant("CREATE", "app", "admin", object_type="SCHEMA")

# Grant all
db.grant("ALL", "app", "admin", object_type="SCHEMA")
```

### On Databases

```python
# Grant CONNECT
db.grant("CONNECT", "mydb", "appuser", object_type="DATABASE")

# Grant CREATE (can create schemas)
db.grant("CREATE", "mydb", "admin", object_type="DATABASE")
```

### With Grant Option

```python
# Allow grantee to grant to others
db.grant("SELECT", "users", "team_lead", with_grant_option=True)
```

## Revoking Privileges

### Basic Revoke

```python
db.revoke("INSERT", "users", "readonly")
db.revoke(["INSERT", "UPDATE", "DELETE"], "orders", "readonly")
```

### Cascade Revoke

```python
# Revoke from dependent grants too
db.revoke("ALL", "users", "admin", cascade=True)
```

### On Schemas and Databases

```python
db.revoke("USAGE", "app", "olduser", object_type="SCHEMA")
db.revoke("CONNECT", "mydb", "olduser", object_type="DATABASE")
```

## Listing Grants

```python
grants = db.list_role_grants("appuser")
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
db.create_role("readonly", login=False)
db.grant("USAGE", "public", "readonly", object_type="SCHEMA")
db.grant("SELECT", "ALL TABLES", "readonly", schema="public")

# Create read-only user
db.create_role("reader", password="secret", login=True, in_roles=["readonly"])
```

### Application User

```python
# Create role with typical app permissions
db.create_role("appuser", password="secret", login=True)
db.grant("USAGE", "public", "appuser", object_type="SCHEMA")
db.grant(["SELECT", "INSERT", "UPDATE", "DELETE"], "ALL TABLES", "appuser", schema="public")
db.grant(["USAGE", "SELECT"], "ALL SEQUENCES", "appuser", schema="public")
```

### Admin User

```python
db.create_role(
    "admin",
    password="secret",
    login=True,
    superuser=False,
    createdb=True,
    createrole=True,
)
db.grant("ALL", "ALL TABLES", "admin", schema="public")
db.grant("ALL", "public", "admin", object_type="SCHEMA")
```

### Team Hierarchy

```python
# Create team roles
db.create_role("engineering", login=False)
db.create_role("senior_engineers", login=False, in_roles=["engineering"])

# Grant permissions to groups
db.grant("SELECT", "ALL TABLES", "engineering", schema="public")
db.grant(["INSERT", "UPDATE"], "code_reviews", "engineering")
db.grant("DELETE", "code_reviews", "senior_engineers")

# Create users in teams
db.create_role("alice", password="secret", login=True, in_roles=["engineering"])
db.create_role("bob", password="secret", login=True, in_roles=["senior_engineers"])
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
db.create_role("read_access", login=False)
db.create_role("write_access", login=False, in_roles=["read_access"])
db.create_role("admin_access", login=False, in_roles=["write_access"])

# Users inherit from roles
db.create_role("alice", password="...", in_roles=["write_access"])
```

### 2. Principle of Least Privilege

```python
# Grant minimum required permissions
db.grant("SELECT", "users", "readonly")  # Not ALL

# Be specific about tables
db.grant("SELECT", "public_data", "readonly")  # Not ALL TABLES
```

### 3. Use Separate Roles for Apps

```python
# Each app gets its own role
db.create_role("webapp", password="...", login=True)
db.create_role("worker", password="...", login=True)
db.create_role("analytics", password="...", login=True)
```

### 4. Regular Audits

```python
# Review all roles
for role in db.list_roles():
    print(f"{role['name']}: login={role['login']}, super={role['superuser']}")
    grants = db.list_role_grants(role['name'])
    for g in grants:
        print(f"  - {g['privilege']} on {g['schema']}.{g['object_name']}")
```
