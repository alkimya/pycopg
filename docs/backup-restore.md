# Backup & Restore

pycopg provides convenient wrappers around PostgreSQL's backup and restore tools.

## pg_dump

### Full Database Backup

```python
# Custom format (compressed, recommended)
db.pg_dump("backup.dump")

# Plain SQL format
db.pg_dump("backup.sql", format="plain")

# Directory format (for parallel backup)
db.pg_dump("backup_dir", format="directory")

# Tar format
db.pg_dump("backup.tar", format="tar")
```

### Backup Options

```python
db.pg_dump(
    "backup.dump",
    format="custom",      # 'plain', 'custom', 'directory', 'tar'
    schema_only=False,    # Only schema, no data
    data_only=False,      # Only data, no schema
    tables=None,          # List of tables to include
    exclude_tables=None,  # List of tables to exclude
    schemas=None,         # List of schemas to include
    compress=6,           # Compression level (0-9, custom format)
    jobs=1,               # Parallel jobs (directory format)
)
```

### Schema Only

```python
# Export only table definitions
db.pg_dump("schema.sql", format="plain", schema_only=True)
```

### Data Only

```python
# Export only data (for tables that already exist)
db.pg_dump("data.dump", data_only=True)
```

### Specific Tables

```python
# Backup specific tables
db.pg_dump("users.dump", tables=["users", "user_profiles", "user_settings"])

# Exclude tables
db.pg_dump("backup.dump", exclude_tables=["logs", "sessions", "temp_data"])
```

### Specific Schemas

```python
# Backup specific schemas
db.pg_dump("app.dump", schemas=["app", "auth"])
```

### Parallel Backup

```python
# Use directory format with multiple jobs
db.pg_dump("backup_dir", format="directory", jobs=4)
```

## pg_restore

### Full Restore

```python
# Restore from custom format
db.pg_restore("backup.dump")

# From directory format
db.pg_restore("backup_dir")
```

### Restore Options

```python
db.pg_restore(
    "backup.dump",
    clean=False,           # Drop objects before recreating
    if_exists=True,        # Use IF EXISTS with clean
    create=False,          # Create database before restoring
    data_only=False,       # Restore only data
    schema_only=False,     # Restore only schema
    tables=None,           # Only restore these tables
    schemas=None,          # Only restore these schemas
    jobs=1,                # Parallel jobs
    no_owner=False,        # Don't restore ownership
    no_privileges=False,   # Don't restore privileges
)
```

### Clean Restore

```python
# Drop and recreate all objects
db.pg_restore("backup.dump", clean=True, if_exists=True)
```

### Parallel Restore

```python
# Restore with multiple jobs
db.pg_restore("backup_dir", jobs=4)
```

### Restore Specific Tables

```python
# Restore only certain tables
db.pg_restore("backup.dump", tables=["users", "orders"])
```

### Restore Without Ownership

```python
# Useful when restoring to a different environment
db.pg_restore("backup.dump", no_owner=True, no_privileges=True)
```

### Plain SQL Restore

For plain SQL backups, pycopg uses psql automatically.

```python
db.pg_restore("backup.sql")  # Automatically uses psql for .sql files
```

## CSV Export/Import

### Export to CSV

```python
# Basic export
rows = db.copy_to_csv("users", "users.csv")
print(f"Exported {rows} rows")

# With options
db.copy_to_csv(
    "users",
    "users.csv",
    schema="public",
    columns=["id", "name", "email"],  # Specific columns
    delimiter=",",
    header=True,
    null_string="",
    encoding="UTF8",
)
```

### Import from CSV

```python
# Basic import
rows = db.copy_from_csv("users", "users.csv")
print(f"Imported {rows} rows")

# With options
db.copy_from_csv(
    "users",
    "users.csv",
    schema="public",
    columns=["id", "name", "email"],  # Map to specific columns
    delimiter=",",
    header=True,
    null_string="",
    encoding="UTF8",
)
```

## Complete Backup Strategy

### Development Backup

```python
from pycopg import Database
from datetime import datetime

db = Database.from_env()

# Daily backup with timestamp
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
db.pg_dump(f"backups/dev_{timestamp}.dump")

# Keep only schema in version control
db.pg_dump("migrations/schema.sql", format="plain", schema_only=True)

db.close()
```

### Production Backup Script

```python
from pycopg import Database
from datetime import datetime
from pathlib import Path
import os

def backup_database():
    db = Database.from_env()

    # Create backup directory
    backup_dir = Path("backups")
    backup_dir.mkdir(exist_ok=True)

    # Generate filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = backup_dir / f"prod_{timestamp}.dump"

    # Full backup (parallel for speed)
    db.pg_dump(
        str(backup_file),
        format="custom",
        compress=9,
    )

    # Verify backup size
    size = backup_file.stat().st_size
    print(f"Backup created: {backup_file} ({size / 1024 / 1024:.1f} MB)")

    # Clean old backups (keep last 7 days)
    cutoff = datetime.now().timestamp() - (7 * 24 * 60 * 60)
    for old_backup in backup_dir.glob("prod_*.dump"):
        if old_backup.stat().st_mtime < cutoff:
            old_backup.unlink()
            print(f"Deleted old backup: {old_backup}")

    db.close()

if __name__ == "__main__":
    backup_database()
```

### Migration with Backup

```python
from pycopg import Database, Migrator
from datetime import datetime

def safe_migrate():
    db = Database.from_env()
    migrator = Migrator(db, "migrations/")

    # Check for pending migrations
    pending = migrator.pending()
    if not pending:
        print("No pending migrations")
        return

    print(f"Found {len(pending)} pending migrations")

    # Backup before migration
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"backups/pre_migration_{timestamp}.dump"
    print(f"Creating backup: {backup_file}")
    db.pg_dump(backup_file)

    # Run migrations
    try:
        applied = migrator.migrate()
        for m in applied:
            print(f"Applied: {m}")
        print("Migration successful!")
    except Exception as e:
        print(f"Migration failed: {e}")
        print(f"Restore from: {backup_file}")
        raise

    db.close()
```

### Clone Database

```python
from pycopg import Database
import tempfile
import os

def clone_database(source_url: str, target_url: str):
    source_db = Database.from_url(source_url)
    target_db = Database.from_url(target_url)

    # Create temporary backup
    with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as f:
        backup_file = f.name

    try:
        # Backup source
        print("Backing up source database...")
        source_db.pg_dump(backup_file)

        # Restore to target (clean = drop existing objects)
        print("Restoring to target database...")
        target_db.pg_restore(backup_file, clean=True, no_owner=True)

        print("Clone complete!")
    finally:
        os.unlink(backup_file)
        source_db.close()
        target_db.close()
```

## Error Handling

```python
try:
    db.pg_dump("backup.dump")
except RuntimeError as e:
    print(f"Backup failed: {e}")
    # Handle error (e.g., retry, alert)

try:
    db.pg_restore("backup.dump")
except RuntimeError as e:
    print(f"Restore failed: {e}")
    # Handle error
```

## Best Practices

### 1. Use Custom Format for Production

```python
# Custom format is compressed and supports parallel restore
db.pg_dump("backup.dump", format="custom")
```

### 2. Test Restores Regularly

```python
# Create test database
db.create_database("test_restore")

# Restore to test
test_db = Database(db.config.with_database("test_restore"))
test_db.pg_restore("backup.dump")

# Verify data
users = test_db.execute("SELECT COUNT(*) FROM users")
print(f"Users: {users[0]['count']}")

# Cleanup
test_db.close()
db.drop_database("test_restore")
```

### 3. Include Backup in CI/CD

```yaml
# GitHub Actions example
- name: Backup before deploy
  run: |
    python -c "
    from pycopg import Database
    db = Database.from_env()
    db.pg_dump('pre_deploy_backup.dump')
    "
```

### 4. Monitor Backup Size

```python
from pathlib import Path

backup_file = Path("backup.dump")
db.pg_dump(str(backup_file))

size_mb = backup_file.stat().st_size / 1024 / 1024
print(f"Backup size: {size_mb:.1f} MB")

# Alert if size changed significantly
if size_mb < expected_min_size:
    raise ValueError("Backup too small - possible data loss!")
```
