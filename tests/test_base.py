"""Tests for pycopg.base module."""

import pytest

from pycopg import Config
from pycopg.base import (
    DatabaseBase,
    QueryMixin,
    SessionMixin,
    build_pg_dump_cmd,
    build_pg_restore_cmd,
    build_role_options,
)
from pycopg.exceptions import InvalidIdentifier


class ConcreteDatabaseBase(DatabaseBase):
    """Concrete implementation for testing DatabaseBase."""
    pass


class TestDatabaseBase:
    """Tests for DatabaseBase class."""

    @pytest.fixture
    def config(self):
        """Create a test config."""
        return Config(
            host="localhost",
            port=5432,
            database="testdb",
            user="testuser",
            password="testpass",
        )

    def test_init_with_config(self, config):
        """Test initialization stores config."""
        db = ConcreteDatabaseBase(config)
        assert db.config == config

    def test_from_env(self, monkeypatch):
        """Test from_env class method."""
        # Use DATABASE_URL which takes precedence
        import os
        for key in list(os.environ.keys()):
            if key.startswith(("DB_", "PG", "DATABASE_")):
                monkeypatch.delenv(key, raising=False)

        monkeypatch.setenv("DATABASE_URL", "postgresql://envuser:envpass@envhost:5432/envdb")

        db = ConcreteDatabaseBase.from_env()
        assert db.config.host == "envhost"
        assert db.config.database == "envdb"

    def test_from_url(self):
        """Test from_url class method."""
        db = ConcreteDatabaseBase.from_url("postgresql://user:pass@host:5432/dbname")
        assert db.config.host == "host"
        assert db.config.database == "dbname"
        assert db.config.user == "user"
        assert db.config.password == "pass"

    def test_repr(self, config):
        """Test string representation."""
        db = ConcreteDatabaseBase(config)
        repr_str = repr(db)
        assert "ConcreteDatabaseBase" in repr_str
        assert "testdb" in repr_str
        assert "localhost" in repr_str
        assert "5432" in repr_str


class TestQueryMixin:
    """Tests for QueryMixin class."""

    def test_build_insert_sql_basic(self):
        """Test basic INSERT SQL generation."""
        sql, cols = QueryMixin._build_insert_sql(
            "users",
            ["name", "email"],
        )
        assert "INSERT INTO public.users" in sql
        assert "name, email" in sql
        assert "%s, %s" in sql
        assert cols == "name, email"

    def test_build_insert_sql_with_schema(self):
        """Test INSERT SQL with custom schema."""
        sql, cols = QueryMixin._build_insert_sql(
            "users",
            ["name"],
            schema="app",
        )
        assert "INSERT INTO app.users" in sql

    def test_build_insert_sql_with_on_conflict(self):
        """Test INSERT SQL with ON CONFLICT clause."""
        sql, cols = QueryMixin._build_insert_sql(
            "users",
            ["id", "name"],
            on_conflict="(id) DO UPDATE SET name = EXCLUDED.name",
        )
        assert "ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name" in sql

    def test_build_insert_sql_validates_identifiers(self):
        """Test that invalid identifiers are rejected."""
        with pytest.raises(InvalidIdentifier):
            QueryMixin._build_insert_sql("users;drop", ["name"])

        with pytest.raises(InvalidIdentifier):
            QueryMixin._build_insert_sql("users", ["bad;column"])

    def test_build_batch_insert_sql(self):
        """Test batch INSERT SQL generation."""
        rows = [
            {"name": "Alice", "email": "alice@example.com"},
            {"name": "Bob", "email": "bob@example.com"},
        ]
        sql, params = QueryMixin._build_batch_insert_sql(
            "users",
            ["name", "email"],
            rows,
        )
        assert "INSERT INTO public.users" in sql
        assert "VALUES (%s, %s), (%s, %s)" in sql
        assert params == ["Alice", "alice@example.com", "Bob", "bob@example.com"]

    def test_build_batch_insert_sql_with_on_conflict(self):
        """Test batch INSERT SQL with ON CONFLICT."""
        rows = [{"name": "Alice"}]
        sql, params = QueryMixin._build_batch_insert_sql(
            "users",
            ["name"],
            rows,
            on_conflict="DO NOTHING",
        )
        assert "ON CONFLICT DO NOTHING" in sql

    def test_build_select_sql_basic(self):
        """Test basic SELECT SQL generation."""
        sql = QueryMixin._build_select_sql("users")
        assert sql == "SELECT * FROM public.users"

    def test_build_select_sql_with_columns(self):
        """Test SELECT SQL with specific columns."""
        sql = QueryMixin._build_select_sql("users", columns=["id", "name"])
        assert "SELECT id, name FROM public.users" in sql

    def test_build_select_sql_with_where(self):
        """Test SELECT SQL with WHERE clause."""
        sql = QueryMixin._build_select_sql("users", where="active = true")
        assert "WHERE active = true" in sql

    def test_build_select_sql_with_order_by(self):
        """Test SELECT SQL with ORDER BY clause."""
        sql = QueryMixin._build_select_sql("users", order_by="name ASC")
        assert "ORDER BY name ASC" in sql

    def test_build_select_sql_with_limit_offset(self):
        """Test SELECT SQL with LIMIT and OFFSET."""
        sql = QueryMixin._build_select_sql("users", limit=10, offset=20)
        assert "LIMIT 10" in sql
        assert "OFFSET 20" in sql

    def test_build_select_sql_full(self):
        """Test SELECT SQL with all options."""
        sql = QueryMixin._build_select_sql(
            "users",
            columns=["id", "name"],
            schema="app",
            where="active = true",
            order_by="id DESC",
            limit=5,
            offset=10,
        )
        assert "SELECT id, name FROM app.users WHERE active = true ORDER BY id DESC LIMIT 5 OFFSET 10" == sql

    def test_build_select_sql_validates_identifiers(self):
        """Test that invalid identifiers are rejected."""
        with pytest.raises(InvalidIdentifier):
            QueryMixin._build_select_sql("users;drop")

        with pytest.raises(InvalidIdentifier):
            QueryMixin._build_select_sql("users", columns=["bad;col"])


class TestSessionMixin:
    """Tests for SessionMixin class."""

    def test_initial_state(self):
        """Test initial session state."""
        mixin = SessionMixin()
        assert mixin._session_connection is None
        assert mixin._in_session is False

    def test_get_session_connection_not_in_session(self):
        """Test get_session_connection when not in session."""
        mixin = SessionMixin()
        assert mixin._get_session_connection() is None

    def test_get_session_connection_in_session(self):
        """Test get_session_connection when in session."""
        mixin = SessionMixin()
        mixin._in_session = True
        mixin._session_connection = "mock_connection"
        assert mixin._get_session_connection() == "mock_connection"

    def test_is_in_session(self):
        """Test _is_in_session method."""
        mixin = SessionMixin()
        assert mixin._is_in_session() is False

        mixin._in_session = True
        assert mixin._is_in_session() is True


# Common connection kwargs reused across builder tests (DB-free).
_CONN = {"host": "h", "port": 5432, "user": "u", "database": "d"}


class TestBuildPgDumpCmd:
    """DB-free unit tests for build_pg_dump_cmd (pure argv builder)."""

    def test_leading_connection_args(self):
        """Leading argv is pg_dump + connection params."""
        cmd = build_pg_dump_cmd(**_CONN, output_file="out.dump")
        assert cmd[:9] == [
            "pg_dump",
            "-h",
            "h",
            "-p",
            "5432",
            "-U",
            "u",
            "-d",
            "d",
        ]

    @pytest.mark.parametrize(
        "fmt,flag",
        [("plain", "p"), ("custom", "c"), ("directory", "d"), ("tar", "t")],
    )
    def test_format_maps_to_format_flag(self, fmt, flag):
        """Each format value maps to its -F flag."""
        cmd = build_pg_dump_cmd(**_CONN, output_file="out", format=fmt)
        assert "-F" in cmd
        assert cmd[cmd.index("-F") + 1] == flag

    def test_schema_only_flag(self):
        """schema_only adds --schema-only."""
        cmd = build_pg_dump_cmd(**_CONN, output_file="out", schema_only=True)
        assert "--schema-only" in cmd

    def test_data_only_flag(self):
        """data_only adds --data-only."""
        cmd = build_pg_dump_cmd(**_CONN, output_file="out", data_only=True)
        assert "--data-only" in cmd

    def test_compress_applied_only_for_custom(self):
        """compress applies for custom format, not for others."""
        custom = build_pg_dump_cmd(
            **_CONN, output_file="out", format="custom", compress=9
        )
        assert "-Z" in custom and custom[custom.index("-Z") + 1] == "9"
        plain = build_pg_dump_cmd(
            **_CONN, output_file="out", format="plain", compress=9
        )
        assert "-Z" not in plain

    def test_compress_zero_not_applied(self):
        """compress=0 is falsy, so no -Z even for custom."""
        cmd = build_pg_dump_cmd(
            **_CONN, output_file="out", format="custom", compress=0
        )
        assert "-Z" not in cmd

    def test_jobs_applied_only_for_directory(self):
        """jobs>1 applies for directory format only."""
        directory = build_pg_dump_cmd(
            **_CONN, output_file="out", format="directory", jobs=4
        )
        assert "-j" in directory and directory[directory.index("-j") + 1] == "4"
        custom = build_pg_dump_cmd(
            **_CONN, output_file="out", format="custom", jobs=4
        )
        assert "-j" not in custom

    def test_jobs_one_not_applied(self):
        """jobs=1 (default) adds no -j even for directory."""
        cmd = build_pg_dump_cmd(
            **_CONN, output_file="out", format="directory", jobs=1
        )
        assert "-j" not in cmd

    def test_tables_repeated_t(self):
        """tables produce repeated -t flags."""
        cmd = build_pg_dump_cmd(**_CONN, output_file="out", tables=["a", "b"])
        assert cmd.count("-t") == 2
        idxs = [i for i, x in enumerate(cmd) if x == "-t"]
        assert [cmd[i + 1] for i in idxs] == ["a", "b"]

    def test_exclude_tables_repeated_exclude_flag(self):
        """exclude_tables produce repeated -T flags."""
        cmd = build_pg_dump_cmd(
            **_CONN, output_file="out", exclude_tables=["x", "y"]
        )
        assert cmd.count("-T") == 2

    def test_schemas_repeated_n(self):
        """schemas produce repeated -n flags."""
        cmd = build_pg_dump_cmd(
            **_CONN, output_file="out", schemas=["public", "geo"]
        )
        assert cmd.count("-n") == 2

    def test_output_file_trailing_f(self):
        """output_file is the trailing -f argument."""
        cmd = build_pg_dump_cmd(**_CONN, output_file="dir/out.dump")
        assert cmd[-2] == "-f"
        assert cmd[-1] == "dir/out.dump"


class TestBuildPgRestoreCmd:
    """DB-free unit tests for build_pg_restore_cmd (pure argv builder)."""

    def test_leading_connection_args(self):
        """Leading argv is pg_restore + connection params."""
        cmd = build_pg_restore_cmd(**_CONN, input_file="in.dump")
        assert cmd[:9] == [
            "pg_restore",
            "-h",
            "h",
            "-p",
            "5432",
            "-U",
            "u",
            "-d",
            "d",
        ]

    def test_default_if_exists_present(self):
        """if_exists defaults True -> --if-exists present."""
        cmd = build_pg_restore_cmd(**_CONN, input_file="in")
        assert "--if-exists" in cmd

    def test_if_exists_false_absent(self):
        """if_exists False -> no --if-exists."""
        cmd = build_pg_restore_cmd(**_CONN, input_file="in", if_exists=False)
        assert "--if-exists" not in cmd

    @pytest.mark.parametrize(
        "kwarg,flag",
        [
            ("clean", "--clean"),
            ("create", "--create"),
            ("data_only", "--data-only"),
            ("schema_only", "--schema-only"),
            ("no_owner", "--no-owner"),
            ("no_privileges", "--no-privileges"),
        ],
    )
    def test_boolean_flags_toggle(self, kwarg, flag):
        """Each boolean flag, when True, appears in the argv."""
        cmd = build_pg_restore_cmd(**_CONN, input_file="in", **{kwarg: True})
        assert flag in cmd
        off = build_pg_restore_cmd(**_CONN, input_file="in")
        assert flag not in off

    def test_jobs_gt_one(self):
        """jobs>1 adds -j; jobs=1 does not."""
        cmd = build_pg_restore_cmd(**_CONN, input_file="in", jobs=3)
        assert "-j" in cmd and cmd[cmd.index("-j") + 1] == "3"
        one = build_pg_restore_cmd(**_CONN, input_file="in", jobs=1)
        assert "-j" not in one

    def test_tables_repeated_t(self):
        """tables produce repeated -t flags."""
        cmd = build_pg_restore_cmd(**_CONN, input_file="in", tables=["a", "b"])
        assert cmd.count("-t") == 2

    def test_schemas_repeated_n(self):
        """schemas produce repeated -n flags."""
        cmd = build_pg_restore_cmd(**_CONN, input_file="in", schemas=["p"])
        assert cmd.count("-n") == 1

    def test_input_file_is_trailing_arg(self):
        """input_file is the final positional argument."""
        cmd = build_pg_restore_cmd(**_CONN, input_file="dir/in.dump")
        assert cmd[-1] == "dir/in.dump"


class TestBuildRoleOptions:
    """DB-free unit tests for build_role_options (pure option builder)."""

    def test_login_true_adds_login(self):
        """login True -> LOGIN."""
        assert "LOGIN" in build_role_options(login=True)

    def test_login_false_adds_nologin(self):
        """login False -> NOLOGIN."""
        opts = build_role_options(login=False)
        assert "NOLOGIN" in opts
        assert "LOGIN" not in opts

    def test_superuser_flag(self):
        """superuser -> SUPERUSER."""
        assert "SUPERUSER" in build_role_options(superuser=True)

    def test_createdb_flag(self):
        """createdb -> CREATEDB."""
        assert "CREATEDB" in build_role_options(createdb=True)

    def test_createrole_flag(self):
        """createrole -> CREATEROLE."""
        assert "CREATEROLE" in build_role_options(createrole=True)

    def test_inherit_false_adds_noinherit(self):
        """inherit False -> NOINHERIT; inherit True -> no NOINHERIT."""
        assert "NOINHERIT" in build_role_options(inherit=False)
        assert "NOINHERIT" not in build_role_options(inherit=True)

    def test_replication_flag(self):
        """replication -> REPLICATION."""
        assert "REPLICATION" in build_role_options(replication=True)

    def test_connection_limit_set(self):
        """connection_limit != -1 -> CONNECTION LIMIT n."""
        assert "CONNECTION LIMIT 5" in build_role_options(connection_limit=5)

    def test_connection_limit_default_absent(self):
        """connection_limit == -1 (default) -> no CONNECTION LIMIT."""
        opts = build_role_options(connection_limit=-1)
        assert not any(o.startswith("CONNECTION LIMIT") for o in opts)

    def test_password_placeholder_not_value(self):
        """Truthy password -> 'PASSWORD %s' placeholder; real value absent (D-04/T-12-02)."""
        secret = "s3cr3t-do-not-leak"
        opts = build_role_options(password=secret)
        assert "PASSWORD %s" in opts
        assert all(secret not in opt for opt in opts)

    def test_password_falsy_absent(self):
        """Falsy password -> no PASSWORD token."""
        opts = build_role_options(password=None)
        assert "PASSWORD %s" not in opts

    def test_valid_until_present(self):
        """valid_until -> VALID UNTIL '...'."""
        opts = build_role_options(valid_until="2025-12-31")
        assert "VALID UNTIL '2025-12-31'" in opts

    def test_valid_until_rejects_malformed(self):
        """Malformed valid_until is rejected by validate_timestamp."""
        with pytest.raises(Exception):  # noqa: B017 - validate_timestamp raises
            build_role_options(valid_until="not-a-timestamp; DROP TABLE x")
