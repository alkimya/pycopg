# pycopg Documentation

High-level Python API for PostgreSQL/PostGIS/TimescaleDB.

```{toctree}
:maxdepth: 2
:caption: Contents

getting-started
configuration
database
async-database
connection-pooling
migrations
postgis
timescaledb
roles-permissions
backup-restore
api-reference
```

## Features

- **Sync & Async**: Full async/await support with `AsyncDatabase`
- **Connection Pooling**: Built-in pooling with `PooledDatabase` and `AsyncPooledDatabase`
- **DataFrame Integration**: Seamless pandas/geopandas support
- **Migrations**: Simple SQL-based migration system
- **PostGIS**: Spatial data operations with GeoDataFrame support
- **TimescaleDB**: Hypertables, compression, and retention policies
- **Role Management**: Create roles, grant/revoke privileges
- **Backup/Restore**: pg_dump/pg_restore and CSV import/export

## Quick Example

```python
from pycopg import Database

# Connect from environment
db = Database.from_env()

# Explore
print(db.list_schemas())
print(db.list_tables("public"))
print(db.size())

# Query
users = db.execute("SELECT * FROM users WHERE active = %s", [True])

# Close
db.close()
```

## Installation

```bash
pip install pycopg

# With optional dependencies
pip install pycopg[dotenv]  # .env file support
pip install pycopg[geo]     # PostGIS/geopandas
pip install pycopg[all]     # All optional deps
```

## License

MIT License - Copyright (c) 2026 Loc Cosnier

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
