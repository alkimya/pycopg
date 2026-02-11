"""
Configuration management for pycopg.

Loads database credentials from environment variables or .env file.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

# python-dotenv is optional
try:
    from dotenv import load_dotenv
    HAS_DOTENV = True
except ImportError:
    HAS_DOTENV = False

    def load_dotenv(dotenv_path=None, *, override: bool = False, **kwargs):
        """No-op when python-dotenv is not installed."""
        pass


@dataclass
class Config:
    """Database connection configuration.

    Can be created from:
    - Individual parameters
    - DATABASE_URL environment variable
    - .env file

    Examples:
        # From individual params
        config = Config(host="localhost", database="mydb", user="postgres", password="secret")

        # From DATABASE_URL
        config = Config.from_url("postgresql://user:pass@localhost:5432/mydb")

        # From environment
        config = Config.from_env()

        # From .env file
        config = Config.from_env("/path/to/.env")
    """

    host: str = "localhost"
    port: int = 5432
    database: str = "postgres"
    user: str = "postgres"
    password: str = ""
    sslmode: Optional[str] = None
    options: dict = field(default_factory=dict)
    statement_timeout: Optional[int] = None
    default_batch_size: int = 1000

    @classmethod
    def from_url(cls, url: str) -> "Config":
        """Create config from a database URL.

        Args:
            url: PostgreSQL connection URL.
                 Formats supported:
                 - postgresql://user:pass@host:port/dbname
                 - postgresql+asyncpg://user:pass@host:port/dbname
                 - postgres://user:pass@host:port/dbname

        Returns:
            Config instance.

        Example:
            config = Config.from_url("postgresql://admin:secret@db.example.com:5432/myapp")
        """
        # Normalize URL scheme
        url = url.replace("postgresql+asyncpg://", "postgresql://")
        url = url.replace("postgres://", "postgresql://")

        parsed = urlparse(url)

        # Extract query params as options
        options = {}
        if parsed.query:
            for param in parsed.query.split("&"):
                if "=" in param:
                    key, value = param.split("=", 1)
                    options[key] = value

        # Extract statement_timeout from query params
        statement_timeout_str = options.pop("statement_timeout", None)
        statement_timeout = int(statement_timeout_str) if statement_timeout_str else None

        return cls(
            host=parsed.hostname or "localhost",
            port=parsed.port or 5432,
            database=parsed.path.lstrip("/") if parsed.path else "postgres",
            user=parsed.username or "postgres",
            password=parsed.password or "",
            sslmode=options.pop("sslmode", None),
            options=options,
            statement_timeout=statement_timeout,
        )

    @classmethod
    def from_env(
        cls,
        dotenv_path: Optional[str | Path] = None,
        *,
        load_dotenv_file: bool = True,
    ) -> "Config":
        """Create config from environment variables.

        Looks for DATABASE_URL first, then individual variables:
        - DATABASE_URL: Full connection URL
        - DB_HOST, PGHOST: Database host
        - DB_PORT, PGPORT: Database port
        - DB_NAME, PGDATABASE: Database name
        - DB_USER, PGUSER: Database user
        - DB_PASSWORD, PGPASSWORD: Database password

        Args:
            dotenv_path: Optional path to .env file. If None, searches
                        current directory and parents.
            load_dotenv_file: Whether to load .env file. Set to False to
                            only use existing environment variables.

        Returns:
            Config instance.

        Example:
            # Load from .env in current directory
            config = Config.from_env()

            # Load from specific .env file
            config = Config.from_env("/home/user/project/.env")

            # Only use existing env vars, skip .env file
            config = Config.from_env(load_dotenv_file=False)
        """
        if load_dotenv_file:
            if dotenv_path:
                # When explicit path is given, override existing env vars
                load_dotenv(dotenv_path, override=True)
            else:
                load_dotenv()

        # Try DATABASE_URL first
        database_url = os.getenv("DATABASE_URL")
        if database_url:
            return cls.from_url(database_url)

        # Fall back to individual env vars
        return cls(
            host=os.getenv("DB_HOST") or os.getenv("PGHOST") or "localhost",
            port=int(os.getenv("DB_PORT") or os.getenv("PGPORT") or "5432"),
            database=os.getenv("DB_NAME") or os.getenv("PGDATABASE") or "postgres",
            user=os.getenv("DB_USER") or os.getenv("PGUSER") or "postgres",
            password=os.getenv("DB_PASSWORD") or os.getenv("PGPASSWORD") or "",
            sslmode=os.getenv("DB_SSLMODE") or os.getenv("PGSSLMODE"),
        )

    @property
    def dsn(self) -> str:
        """Generate psycopg-compatible DSN string.

        Returns:
            Connection string for psycopg.

        Example:
            >>> config = Config(host="localhost", database="mydb", user="admin", password="secret")
            >>> config.dsn
            'host=localhost port=5432 dbname=mydb user=admin password=secret'
        """
        parts = [
            f"host={self.host}",
            f"port={self.port}",
            f"dbname={self.database}",
            f"user={self.user}",
        ]
        if self.password:
            parts.append(f"password={self.password}")
        if self.sslmode:
            parts.append(f"sslmode={self.sslmode}")

        # Add options string if statement_timeout or options are set
        options_parts = []
        if self.statement_timeout is not None:
            options_parts.append(f"-c statement_timeout={self.statement_timeout}")
        for key, value in self.options.items():
            options_parts.append(f"-c {key}={value}")
        if options_parts:
            parts.append(f"options={' '.join(options_parts)}")

        return " ".join(parts)

    @property
    def url(self) -> str:
        """Generate SQLAlchemy-compatible URL using psycopg v3.

        Returns:
            PostgreSQL URL for SQLAlchemy with psycopg driver.

        Example:
            >>> config = Config(host="localhost", database="mydb", user="admin", password="secret")
            >>> config.url
            'postgresql+psycopg://admin:secret@localhost:5432/mydb'
        """
        auth = f"{self.user}:{self.password}" if self.password else self.user
        # Use postgresql+psycopg for psycopg v3 (not psycopg2)
        base = f"postgresql+psycopg://{auth}@{self.host}:{self.port}/{self.database}"
        if self.sslmode:
            base += f"?sslmode={self.sslmode}"
        return base

    def connect_params(self) -> dict:
        """Get connection parameters as dict for psycopg.connect().

        Returns:
            Dict with host, port, dbname, user, password.

        Example:
            config = Config.from_env()
            conn = psycopg.connect(**config.connect_params())
        """
        params = {
            "host": self.host,
            "port": self.port,
            "dbname": self.database,
            "user": self.user,
        }
        if self.password:
            params["password"] = self.password
        if self.sslmode:
            params["sslmode"] = self.sslmode

        # Add PostgreSQL options string if needed
        options_parts = []
        if self.statement_timeout is not None:
            options_parts.append(f"-c statement_timeout={self.statement_timeout}")
        for key, value in self.options.items():
            options_parts.append(f"-c {key}={value}")
        if options_parts:
            params["options"] = " ".join(options_parts)

        return params

    def with_database(self, database: str) -> "Config":
        """Create a new config pointing to a different database.

        Args:
            database: Target database name.

        Returns:
            New Config instance with updated database.

        Example:
            admin_config = Config.from_env()
            app_config = admin_config.with_database("myapp")
        """
        return Config(
            host=self.host,
            port=self.port,
            database=database,
            user=self.user,
            password=self.password,
            sslmode=self.sslmode,
            options=self.options.copy(),
            statement_timeout=self.statement_timeout,
            default_batch_size=self.default_batch_size,
        )

    def __repr__(self) -> str:
        return f"Config(host={self.host!r}, port={self.port}, database={self.database!r}, user={self.user!r})"
