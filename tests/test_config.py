"""Tests for pycopg.config module."""

import os
import tempfile
from pathlib import Path

from pycopg import Config


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
        config = Config.from_url(
            "postgresql://user:pass@host/db?sslmode=require&connect_timeout=10"
        )
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


class TestConfigResilience:
    """Tests for Config resilience features (statement_timeout, default_batch_size)."""

    def test_config_statement_timeout_default(self):
        """Test statement_timeout defaults to None."""
        config = Config()
        assert config.statement_timeout is None

    def test_config_statement_timeout_in_connect_params(self):
        """Test statement_timeout appears in connect_params as options string."""
        config = Config(statement_timeout=30000)
        params = config.connect_params()
        assert "options" in params
        assert "-c statement_timeout=30000" in params["options"]

    def test_config_no_options_when_no_timeout(self):
        """Test connect_params has no options when statement_timeout is None."""
        config = Config()
        params = config.connect_params()
        assert "options" not in params

    def test_config_statement_timeout_with_existing_options(self):
        """Test statement_timeout combines with existing options."""
        config = Config(statement_timeout=5000, options={"work_mem": "256MB"})
        params = config.connect_params()
        assert "options" in params
        assert "-c statement_timeout=5000" in params["options"]
        assert "-c work_mem=256MB" in params["options"]

    def test_config_default_batch_size(self):
        """Test default_batch_size defaults to 1000."""
        config = Config()
        assert config.default_batch_size == 1000

    def test_config_custom_batch_size(self):
        """Test custom default_batch_size."""
        config = Config(default_batch_size=500)
        assert config.default_batch_size == 500

    def test_config_from_url_with_statement_timeout(self):
        """Test from_url parses statement_timeout from query parameters."""
        config = Config.from_url(
            "postgresql://user:pass@localhost/db?statement_timeout=10000"
        )
        assert config.statement_timeout == 10000

    def test_config_from_url_without_statement_timeout(self):
        """Test from_url without statement_timeout."""
        config = Config.from_url("postgresql://user:pass@localhost/db")
        assert config.statement_timeout is None

    def test_config_with_database_preserves_timeout(self):
        """Test with_database preserves statement_timeout and default_batch_size."""
        config = Config(statement_timeout=5000, default_batch_size=2000)
        new_config = config.with_database("other")
        assert new_config.statement_timeout == 5000
        assert new_config.default_batch_size == 2000

    def test_config_dsn_includes_options(self):
        """Test DSN includes options string when statement_timeout is set."""
        config = Config(statement_timeout=30000)
        dsn = config.dsn
        assert "options=" in dsn
        assert "-c statement_timeout=30000" in dsn

    def test_dsn_with_password(self):
        """Test DSN includes password field."""
        config = Config(
            host="localhost", database="db", user="user", password="secret123"
        )
        dsn = config.dsn
        assert "password=secret123" in dsn

    def test_dsn_with_statement_timeout(self):
        """Test DSN includes options string with statement_timeout."""
        config = Config(
            host="localhost", database="db", user="user", statement_timeout=15000
        )
        dsn = config.dsn
        assert "options=" in dsn
        assert "-c statement_timeout=15000" in dsn

    def test_dsn_with_custom_options(self):
        """Test DSN includes custom options."""
        config = Config(options={"work_mem": "256MB", "shared_buffers": "512MB"})
        dsn = config.dsn
        assert "options=" in dsn
        assert "-c work_mem=256MB" in dsn
        assert "-c shared_buffers=512MB" in dsn

    def test_url_property_basic(self):
        """Test URL generation for SQLAlchemy."""
        config = Config(
            host="testhost",
            port=5433,
            database="testdb",
            user="testuser",
            password="testpass",
        )
        url = config.url
        assert url == "postgresql+psycopg://testuser:testpass@testhost:5433/testdb"

    def test_url_with_sslmode_query_param(self):
        """Test URL includes sslmode query param."""
        config = Config(
            host="localhost",
            database="db",
            user="user",
            password="pass",
            sslmode="verify-full",
        )
        url = config.url
        assert "?sslmode=verify-full" in url

    def test_connect_params_basic(self):
        """Test connect_params() returns correct dict."""
        config = Config(
            host="testhost",
            port=5433,
            database="testdb",
            user="testuser",
            password="testpass",
        )
        params = config.connect_params()
        assert params["host"] == "testhost"
        assert params["port"] == 5433
        assert params["dbname"] == "testdb"
        assert params["user"] == "testuser"
        assert params["password"] == "testpass"

    def test_connect_params_with_statement_timeout_options(self):
        """Test connect_params includes options string with statement_timeout."""
        config = Config(statement_timeout=20000)
        params = config.connect_params()
        assert "options" in params
        assert "-c statement_timeout=20000" in params["options"]

    def test_with_database_basic(self):
        """Test with_database() creates new Config with different database."""
        config = Config(
            host="myhost",
            port=5432,
            database="original",
            user="admin",
            password="secret",
            sslmode="require",
        )
        new_config = config.with_database("target")
        assert new_config.database == "target"
        assert new_config.host == "myhost"
        assert new_config.port == 5432
        assert new_config.user == "admin"
        assert new_config.password == "secret"
        assert new_config.sslmode == "require"
        # Original unchanged
        assert config.database == "original"

    def test_with_database_preserves_statement_timeout_and_batch_size(self):
        """Test with_database preserves statement_timeout and default_batch_size."""
        config = Config(statement_timeout=10000, default_batch_size=500)
        new_config = config.with_database("other")
        assert new_config.statement_timeout == 10000
        assert new_config.default_batch_size == 500

    def test_default_batch_size_default_value(self):
        """Test default_batch_size defaults to 1000."""
        config = Config()
        assert config.default_batch_size == 1000

    def test_from_url_with_statement_timeout_query_param(self):
        """Test from_url parses statement_timeout from URL query params."""
        config = Config.from_url(
            "postgresql://user:pass@localhost/db?statement_timeout=25000"
        )
        assert config.statement_timeout == 25000
