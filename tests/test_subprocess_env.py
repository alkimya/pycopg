"""
Regression test for B5 (SEC-04): subprocess env construction in backup/restore methods.

Bug B5: pg_dump(), pg_restore() and _psql_restore() previously built the child
process environment using `{**subprocess.os.environ, **env}`.  `subprocess.os` is
an undocumented re-export of the `os` module and can be absent depending on the
Python implementation or runtime configuration, causing AttributeError.

Fix (Task 1, decision D-04): replaced with `{**os.environ, **env}` using the
module-level `import os` already used on the async side.

Test form chosen per D-06: targeted mock — the defect is env construction, not real
subprocess I/O, so patching `subprocess.run` is precise and avoids requiring
pg_dump/pg_restore/psql binaries.  Because `subprocess` is locally imported inside
each method (not at pycopg.database module level), we patch `subprocess.run` at the
`subprocess` module itself.

RED->GREEN proof: the `test_subprocess_os_independence_*` tests temporarily remove
the `os` attribute from the `subprocess` module (simulating runtimes where it is
absent) and assert the methods still succeed.  On the **buggy** code
(`subprocess.os.environ`) this raises AttributeError.  On the **fixed** code
(`os.environ` from a module-level import) it succeeds regardless.
To verify manually: revert Task 1 (restore `subprocess.os.environ` at the 3 sites
and remove top-level `import os`) and confirm these tests fail with AttributeError.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from pycopg import Config, Database

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config_with_password():
    """Config with a non-empty password so PGPASSWORD is merged into env."""
    return Config(
        host="localhost",
        port=5432,
        database="testdb",
        user="testuser",
        password="s3cr3t",
    )


@pytest.fixture
def config_no_password():
    """Config with no password so the env merge uses only os.environ."""
    return Config(
        host="localhost",
        port=5432,
        database="testdb",
        user="testuser",
        password=None,
    )


def _mock_result():
    """Return a mock subprocess.CompletedProcess-like object."""
    r = MagicMock()
    r.returncode = 0
    r.stderr = ""
    r.stdout = ""
    return r


# ---------------------------------------------------------------------------
# env inheritance + PGPASSWORD merge — pg_dump
# ---------------------------------------------------------------------------


class TestPgDumpEnv:
    """Verify env passed to subprocess.run for pg_dump."""

    def test_env_inherits_os_environ(self, config_with_password):
        """The env passed to subprocess.run must contain keys from os.environ."""
        with patch("subprocess.run", return_value=_mock_result()) as mock_run:
            db = Database(config_with_password)
            db.pg_dump("/tmp/backup.dump")

        env = mock_run.call_args.kwargs["env"]
        assert "PATH" in env, "env must contain PATH (inherited from os.environ)"

    def test_env_merges_pgpassword(self, config_with_password):
        """PGPASSWORD from config must be merged into the subprocess env."""
        with patch("subprocess.run", return_value=_mock_result()) as mock_run:
            db = Database(config_with_password)
            db.pg_dump("/tmp/backup.dump")

        env = mock_run.call_args.kwargs["env"]
        assert env.get("PGPASSWORD") == "s3cr3t"

    def test_env_no_pgpassword_empty_value_when_no_config_password(self, config_no_password):
        """When config.password is falsy, our code must not inject empty PGPASSWORD."""
        with patch("subprocess.run", return_value=_mock_result()) as mock_run:
            db = Database(config_no_password)
            db.pg_dump("/tmp/backup.dump")

        env = mock_run.call_args.kwargs["env"]
        # Must still inherit process env (PATH check)
        assert "PATH" in env
        # Our code must not inject an empty string as PGPASSWORD
        assert env.get("PGPASSWORD") != ""

    def test_subprocess_os_independence(self, monkeypatch, config_with_password):
        """
        RED->GREEN proof for B5 (pg_dump path).

        Temporarily removing the `os` attribute from the subprocess module
        (simulating runtimes or configurations where subprocess.os is absent)
        must NOT break pg_dump.

        On the buggy code (`subprocess.os.environ`): AttributeError is raised
        because the locally-imported subprocess module no longer has `.os`.
        On the fixed code (module-level `os.environ`): the method succeeds
        because it uses pycopg.database's own `os` import, not subprocess.os.
        """
        # Remove subprocess.os to simulate its absence
        monkeypatch.delattr(subprocess, "os", raising=False)

        with patch("subprocess.run", return_value=_mock_result()) as mock_run:
            db = Database(config_with_password)
            # Must NOT raise AttributeError (would fail on buggy code)
            db.pg_dump("/tmp/backup.dump")

        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# env inheritance + PGPASSWORD merge — pg_restore
# ---------------------------------------------------------------------------


class TestPgRestoreEnv:
    """Verify env passed to subprocess.run for pg_restore."""

    def test_env_inherits_os_environ(self, tmp_path, config_with_password):
        """The env passed to subprocess.run must contain keys from os.environ."""
        # Create a dummy .dump file so pg_restore takes the pg_restore path (not psql)
        dump_file = tmp_path / "backup.dump"
        dump_file.write_bytes(b"\x50\x47\x44\x4d\x50")  # dummy content

        with patch("subprocess.run", return_value=_mock_result()) as mock_run:
            db = Database(config_with_password)
            db.pg_restore(str(dump_file))

        env = mock_run.call_args.kwargs["env"]
        assert "PATH" in env

    def test_env_merges_pgpassword(self, tmp_path, config_with_password):
        """PGPASSWORD from config must be merged into the subprocess env."""
        dump_file = tmp_path / "backup.dump"
        dump_file.write_bytes(b"\x50\x47\x44\x4d\x50")

        with patch("subprocess.run", return_value=_mock_result()) as mock_run:
            db = Database(config_with_password)
            db.pg_restore(str(dump_file))

        env = mock_run.call_args.kwargs["env"]
        assert env.get("PGPASSWORD") == "s3cr3t"

    def test_subprocess_os_independence(self, monkeypatch, tmp_path, config_with_password):
        """
        RED->GREEN proof for B5 (pg_restore path).

        Removing subprocess.os must NOT cause AttributeError on the fixed code.
        On the buggy `subprocess.os.environ` code this would raise; on the fixed
        `os.environ` code it succeeds.
        """
        dump_file = tmp_path / "backup.dump"
        dump_file.write_bytes(b"\x50\x47\x44\x4d\x50")
        monkeypatch.delattr(subprocess, "os", raising=False)

        with patch("subprocess.run", return_value=_mock_result()) as mock_run:
            db = Database(config_with_password)
            db.pg_restore(str(dump_file))

        mock_run.assert_called_once()


# ---------------------------------------------------------------------------
# env inheritance + PGPASSWORD merge — _psql_restore
# ---------------------------------------------------------------------------


class TestPsqlRestoreEnv:
    """Verify env passed to subprocess.run for _psql_restore."""

    def test_env_inherits_os_environ(self, tmp_path, config_with_password):
        """The env passed to subprocess.run must contain keys from os.environ."""
        sql_file = tmp_path / "restore.sql"
        sql_file.write_text("SELECT 1;")

        with patch("subprocess.run", return_value=_mock_result()) as mock_run:
            db = Database(config_with_password)
            db._psql_restore(sql_file)

        env = mock_run.call_args.kwargs["env"]
        assert "PATH" in env

    def test_env_merges_pgpassword(self, tmp_path, config_with_password):
        """PGPASSWORD from config must be merged into the subprocess env."""
        sql_file = tmp_path / "restore.sql"
        sql_file.write_text("SELECT 1;")

        with patch("subprocess.run", return_value=_mock_result()) as mock_run:
            db = Database(config_with_password)
            db._psql_restore(sql_file)

        env = mock_run.call_args.kwargs["env"]
        assert env.get("PGPASSWORD") == "s3cr3t"

    def test_subprocess_os_independence(self, monkeypatch, tmp_path, config_with_password):
        """
        RED->GREEN proof for B5 (_psql_restore path).

        Removing subprocess.os must NOT cause AttributeError on the fixed code.
        On the buggy `subprocess.os.environ` code this would raise; on the fixed
        `os.environ` code it succeeds.
        """
        sql_file = tmp_path / "restore.sql"
        sql_file.write_text("SELECT 1;")
        monkeypatch.delattr(subprocess, "os", raising=False)

        with patch("subprocess.run", return_value=_mock_result()) as mock_run:
            db = Database(config_with_password)
            db._psql_restore(sql_file)

        mock_run.assert_called_once()
