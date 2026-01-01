"""Tests for pycopg.config module."""

import os
import tempfile
from pathlib import Path

import pytest

from pycopg import Config
from pycopg.exceptions import ConfigurationError


class TestConfig:
    """Tests for Config class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = Config()
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.database == "postgres"
        assert config.user == "postgres"
        assert config.password == ""
        assert config.sslmode is None

    def test_custom_values(self):
        """Test custom configuration values."""
        config = Config(
            host="myhost",
            port=5433,
            database="mydb",
            user="myuser",
            password="mypass",
            sslmode="require",
        )
        assert config.host == "myhost"
        assert config.port == 5433
        assert config.database == "mydb"
        assert config.user == "myuser"
        assert config.password == "mypass"
        assert config.sslmode == "require"

    def test_from_url_basic(self):
        """Test creating config from URL."""
        config = Config.from_url("postgresql://user:pass@host:5433/mydb")
        assert config.host == "host"
        assert config.port == 5433
        assert config.database == "mydb"
        assert config.user == "user"
        assert config.password == "pass"

    def test_from_url_postgres_scheme(self):
        """Test postgres:// scheme is supported."""
        config = Config.from_url("postgres://user:pass@host/db")
        assert config.host == "host"
        assert config.user == "user"

    def test_from_url_asyncpg_scheme(self):
        """Test postgresql+asyncpg:// scheme is normalized."""
        config = Config.from_url("postgresql+asyncpg://user:pass@host/db")
        assert config.host == "host"
        assert config.user == "user"

    def test_from_url_with_sslmode(self):
        """Test URL with sslmode query param."""
        config = Config.from_url("postgresql://user:pass@host/db?sslmode=require")
        assert config.sslmode == "require"

    def test_from_url_with_options(self):
        """Test URL with additional query params."""
        config = Config.from_url("postgresql://user:pass@host/db?sslmode=require&connect_timeout=10")
        assert config.sslmode == "require"
        assert config.options.get("connect_timeout") == "10"

    def test_from_url_defaults(self):
        """Test URL with missing components uses defaults."""
        config = Config.from_url("postgresql:///mydb")
        assert config.host == "localhost"
        assert config.port == 5432
        assert config.user == "postgres"
        assert config.database == "mydb"

    def test_from_env_individual_vars(self, env_vars, monkeypatch):
        """Test loading from individual environment variables."""
        # Clear DATABASE_URL if set to ensure individual vars are used
        monkeypatch.delenv("DATABASE_URL", raising=False)
        # Skip loading .env file to use only monkeypatched env vars
        config = Config.from_env(load_dotenv_file=False)
        assert config.host == "envhost"
        assert config.port == 5433
        assert config.database == "envdb"
        assert config.user == "envuser"
        assert config.password == "envpass"

    def test_from_env_database_url(self, database_url_env):
        """Test DATABASE_URL takes precedence."""
        config = Config.from_env()
        assert config.host == "urlhost"
        assert config.port == 5434
        assert config.database == "urldb"
        assert config.user == "urluser"
        assert config.password == "urlpass"

    def test_from_env_pg_vars(self, monkeypatch):
        """Test PG* environment variables as fallback."""
        # Clear all DB-related vars to ensure clean test
        for key in list(os.environ.keys()):
            if key.startswith(("DB_", "PG", "DATABASE_")):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("PGHOST", "pghost")
        monkeypatch.setenv("PGPORT", "5435")
        monkeypatch.setenv("PGDATABASE", "pgdb")
        monkeypatch.setenv("PGUSER", "pguser")
        monkeypatch.setenv("PGPASSWORD", "pgpass")

        # Skip loading .env file to use only monkeypatched env vars
        config = Config.from_env(load_dotenv_file=False)
        assert config.host == "pghost"
        assert config.port == 5435
        assert config.database == "pgdb"
        assert config.user == "pguser"
        assert config.password == "pgpass"

    def test_from_env_dotenv_file(self, monkeypatch):
        """Test loading from .env file."""
        # Clear existing env vars that might interfere
        for key in list(os.environ.keys()):
            if key.startswith(("DB_", "PG", "DATABASE_")):
                monkeypatch.delenv(key, raising=False)

        with tempfile.TemporaryDirectory() as tmpdir:
            env_file = Path(tmpdir) / ".env"
            env_file.write_text("""
DB_HOST=dotenvhost
DB_PORT=5436
DB_NAME=dotenvdb
DB_USER=dotenvuser
DB_PASSWORD=dotenvpass
""")
            config = Config.from_env(str(env_file))
            assert config.host == "dotenvhost"
            assert config.port == 5436
            assert config.database == "dotenvdb"

    def test_dsn_property(self):
        """Test DSN string generation."""
        config = Config(
            host="myhost",
            port=5432,
            database="mydb",
            user="myuser",
            password="mypass",
        )
        dsn = config.dsn
        assert "host=myhost" in dsn
        assert "port=5432" in dsn
        assert "dbname=mydb" in dsn
        assert "user=myuser" in dsn
        assert "password=mypass" in dsn

    def test_dsn_without_password(self):
        """Test DSN without password."""
        config = Config(host="localhost", database="db", user="user")
        dsn = config.dsn
        assert "password" not in dsn

    def test_dsn_with_sslmode(self):
        """Test DSN with SSL mode."""
        config = Config(host="localhost", database="db", user="user", sslmode="require")
        dsn = config.dsn
        assert "sslmode=require" in dsn

    def test_url_property(self):
        """Test URL generation for SQLAlchemy."""
        config = Config(
            host="myhost",
            port=5432,
            database="mydb",
            user="myuser",
            password="mypass",
        )
        url = config.url
        assert url == "postgresql+psycopg://myuser:mypass@myhost:5432/mydb"

    def test_url_with_sslmode(self):
        """Test URL with SSL mode."""
        config = Config(
            host="localhost",
            database="db",
            user="user",
            password="pass",
            sslmode="require",
        )
        url = config.url
        assert "?sslmode=require" in url

    def test_connect_params(self):
        """Test connect_params dict generation."""
        config = Config(
            host="myhost",
            port=5433,
            database="mydb",
            user="myuser",
            password="mypass",
            sslmode="require",
        )
        params = config.connect_params()
        assert params["host"] == "myhost"
        assert params["port"] == 5433
        assert params["dbname"] == "mydb"
        assert params["user"] == "myuser"
        assert params["password"] == "mypass"
        assert params["sslmode"] == "require"

    def test_connect_params_minimal(self):
        """Test connect_params with minimal config."""
        config = Config(host="localhost", database="db", user="user")
        params = config.connect_params()
        assert "password" not in params
        assert "sslmode" not in params

    def test_with_database(self):
        """Test creating config for different database."""
        config = Config(
            host="myhost",
            port=5432,
            database="admin",
            user="admin",
            password="secret",
            sslmode="require",
        )
        new_config = config.with_database("myapp")
        assert new_config.database == "myapp"
        assert new_config.host == "myhost"
        assert new_config.user == "admin"
        assert new_config.password == "secret"
        assert new_config.sslmode == "require"
        # Original unchanged
        assert config.database == "admin"

    def test_repr(self):
        """Test string representation."""
        config = Config(host="myhost", port=5432, database="mydb", user="myuser")
        repr_str = repr(config)
        assert "myhost" in repr_str
        assert "5432" in repr_str
        assert "mydb" in repr_str
        assert "myuser" in repr_str
        # Password should not be in repr
        assert "password" not in repr_str.lower() or "mypass" not in repr_str
