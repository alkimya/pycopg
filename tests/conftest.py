"""Pytest fixtures for pycopg tests."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pycopg import Config


@pytest.fixture
def config():
    """Create a test config."""
    return Config(
        host="localhost",
        port=5432,
        database="testdb",
        user="testuser",
        password="testpass",
    )


@pytest.fixture
def mock_connection():
    """Create a mock psycopg connection."""
    conn = MagicMock()
    cursor = MagicMock()

    # Setup cursor context manager
    cursor.__enter__ = MagicMock(return_value=cursor)
    cursor.__exit__ = MagicMock(return_value=False)

    # Setup connection context manager
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    conn.cursor.return_value = cursor

    return conn, cursor


@pytest.fixture
def temp_migrations_dir():
    """Create a temporary migrations directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        migrations_path = Path(tmpdir) / "migrations"
        migrations_path.mkdir()
        yield migrations_path


@pytest.fixture
def sample_migrations(temp_migrations_dir):
    """Create sample migration files."""
    migrations = [
        ("001_create_users.sql", """-- UP
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);

-- DOWN
DROP TABLE users;
"""),
        ("002_add_email.sql", """-- UP
ALTER TABLE users ADD COLUMN email TEXT;

-- DOWN
ALTER TABLE users DROP COLUMN email;
"""),
        ("003_create_orders.sql", """-- UP
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id)
);

-- DOWN
DROP TABLE orders;
"""),
    ]

    for filename, content in migrations:
        (temp_migrations_dir / filename).write_text(content)

    return temp_migrations_dir


@pytest.fixture
def env_vars(monkeypatch):
    """Set up test environment variables."""
    # Clear any existing DB vars first
    for key in list(os.environ.keys()):
        if key.startswith(("DB_", "PG", "DATABASE_")):
            monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("DB_HOST", "envhost")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("DB_NAME", "envdb")
    monkeypatch.setenv("DB_USER", "envuser")
    monkeypatch.setenv("DB_PASSWORD", "envpass")
    yield


@pytest.fixture
def database_url_env(monkeypatch):
    """Set up DATABASE_URL environment variable."""
    # Clear any existing DB vars first
    for key in list(os.environ.keys()):
        if key.startswith(("DB_", "PG")):
            monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("DATABASE_URL", "postgresql://urluser:urlpass@urlhost:5434/urldb")
    yield
