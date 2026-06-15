"""Tests for API parity between Database and AsyncDatabase.

TEST-06: Automated verification that all Database public methods exist in AsyncDatabase.
"""

import inspect

import pytest

from pycopg import AsyncDatabase, Database
from pycopg.etl import AsyncETLAccessor, ETLAccessor


class TestAsyncParity:
    """Test that AsyncDatabase maintains parity with Database API."""

    # Methods that are intentionally different between sync/async.
    # Phase 11 (PAR-01/02/03) closed the previous implementation gaps; the only
    # remaining sync-only member is the sync SQLAlchemy engine property.
    SYNC_ONLY_METHODS = {
        "engine",  # Sync-only SQLAlchemy engine (async side has async_engine)
    }

    ASYNC_ONLY_METHODS = {
        "async_engine",  # Async-only SQLAlchemy engine (sync side has engine)
        "listen",  # Async-only by design: a blocking sync LISTEN listener is an
        # anti-pattern, so listen has no sync twin (D-06).
    }

    # Known signature mismatches (parity bugs to be fixed).
    # Phase 11 (PAR-07/D-07) aligned create_schema/create_extension; none remain.
    KNOWN_SIGNATURE_MISMATCHES = set()

    def test_all_database_public_methods_exist_in_async(self):
        """Verify all Database methods (minus exceptions) exist in AsyncDatabase."""
        db_methods = set(
            name for name, _ in inspect.getmembers(Database) if not name.startswith("_")
        )
        async_methods = set(
            name
            for name, _ in inspect.getmembers(AsyncDatabase)
            if not name.startswith("_")
        )

        # Methods that should exist in AsyncDatabase
        expected_in_async = db_methods - self.SYNC_ONLY_METHODS

        # Find missing methods
        missing = expected_in_async - async_methods

        assert (
            not missing
        ), f"Methods in Database but missing in AsyncDatabase: {sorted(missing)}"

    def test_method_signatures_match(self):
        """For shared methods, verify parameter names match."""
        db_methods = {
            name: member
            for name, member in inspect.getmembers(Database)
            if not name.startswith("_") and callable(member)
        }
        async_methods = {
            name: member
            for name, member in inspect.getmembers(AsyncDatabase)
            if not name.startswith("_") and callable(member)
        }

        # Get shared methods (excluding known exceptions)
        shared_methods = (
            (set(db_methods.keys()) & set(async_methods.keys()))
            - self.SYNC_ONLY_METHODS
            - self.ASYNC_ONLY_METHODS
        )

        signature_mismatches = []
        known_mismatches = []

        for method_name in shared_methods:
            db_method = db_methods[method_name]
            async_method = async_methods[method_name]

            # Get signatures
            try:
                db_sig = inspect.signature(db_method)
                async_sig = inspect.signature(async_method)

                # Compare parameter names (order matters)
                db_params = list(db_sig.parameters.keys())
                async_params = list(async_sig.parameters.keys())

                if db_params != async_params:
                    mismatch_str = f"{method_name}: Database{db_params} != AsyncDatabase{async_params}"
                    if method_name in self.KNOWN_SIGNATURE_MISMATCHES:
                        known_mismatches.append(mismatch_str)
                    else:
                        signature_mismatches.append(mismatch_str)
            except (ValueError, TypeError):
                # Some methods may not have inspectable signatures (properties, etc.)
                continue

        # Report known mismatches as info (not failure)
        if known_mismatches:
            print(
                "\n\nKnown signature mismatches (tracked):\n"
                + "\n".join(known_mismatches)
            )

        # Fail on unexpected mismatches
        assert (
            not signature_mismatches
        ), "New signature mismatches found:\n" + "\n".join(signature_mismatches)

    def test_known_exceptions_documented(self):
        """Assert the exception lists are explicitly maintained."""
        db_methods = set(
            name for name, _ in inspect.getmembers(Database) if not name.startswith("_")
        )
        async_methods = set(
            name
            for name, _ in inspect.getmembers(AsyncDatabase)
            if not name.startswith("_")
        )

        # Find actual differences
        actual_sync_only = db_methods - async_methods
        actual_async_only = async_methods - db_methods

        # Check if our documented exceptions match reality
        unknown_sync_only = actual_sync_only - self.SYNC_ONLY_METHODS
        unknown_async_only = actual_async_only - self.ASYNC_ONLY_METHODS

        # Report unknown differences
        if unknown_sync_only or unknown_async_only:
            msg_parts = []
            if unknown_sync_only:
                msg_parts.append(
                    f"Unknown sync-only methods (add to SYNC_ONLY_METHODS): {sorted(unknown_sync_only)}"
                )
            if unknown_async_only:
                msg_parts.append(
                    f"Unknown async-only methods (add to ASYNC_ONLY_METHODS): {sorted(unknown_async_only)}"
                )
            pytest.fail("\n".join(msg_parts))

    def test_exception_lists_are_minimal(self):
        """Ensure we're not documenting methods that no longer differ."""
        db_methods = set(
            name for name, _ in inspect.getmembers(Database) if not name.startswith("_")
        )
        async_methods = set(
            name
            for name, _ in inspect.getmembers(AsyncDatabase)
            if not name.startswith("_")
        )

        # Find actual differences
        actual_sync_only = db_methods - async_methods
        actual_async_only = async_methods - db_methods

        # Check if we're documenting methods that now exist in both
        outdated_sync_only = self.SYNC_ONLY_METHODS - actual_sync_only
        outdated_async_only = self.ASYNC_ONLY_METHODS - actual_async_only

        if outdated_sync_only or outdated_async_only:
            msg_parts = []
            if outdated_sync_only:
                msg_parts.append(
                    f"Methods in SYNC_ONLY_METHODS but now exist in AsyncDatabase (remove from list): {sorted(outdated_sync_only)}"
                )
            if outdated_async_only:
                msg_parts.append(
                    f"Methods in ASYNC_ONLY_METHODS but now exist in Database (remove from list): {sorted(outdated_async_only)}"
                )
            pytest.fail("\n".join(msg_parts))


def _uniq(prefix):
    import uuid

    return f"{prefix}_{uuid.uuid4().hex[:8]}"


class TestBehavioralParity:
    """PAR-08 / D-03: real-DB behavioral parity for the pairs touched in Phase 11.

    Each test runs the SAME operation on a sync ``Database`` and an async
    ``AsyncDatabase`` against ``pycopg_test`` and asserts identical observable
    results. Scope is limited to this phase's pairs (the 13 mirrored methods,
    C1, and the 4 PAR-07-aligned methods) — full-surface introspection lives in
    ``TestAsyncParity``.
    """

    # --- PAR-03: sync mirrors match their async twins -----------------------

    async def test_insert_many_round_trip_parity(self, db_config):
        """insert_many returns the same count and rows on sync and async."""
        sdb = Database(db_config)
        adb = AsyncDatabase(db_config)
        st = _uniq("par_im_sync")
        at = _uniq("par_im_async")
        rows = [{"id": 1, "v": "a"}, {"id": 2, "v": "b"}]
        try:
            sdb.execute(
                f'CREATE TABLE "{st}" (id INT PRIMARY KEY, v TEXT)', autocommit=True
            )
            await adb.execute(
                f'CREATE TABLE "{at}" (id INT PRIMARY KEY, v TEXT)', autocommit=True
            )
            sync_count = sdb.insert_many(st, rows)
            async_count = await adb.insert_many(at, rows)
            assert sync_count == async_count == 2
            sync_rows = sdb.execute(f'SELECT id, v FROM "{st}" ORDER BY id')
            async_rows = await adb.execute(f'SELECT id, v FROM "{at}" ORDER BY id')
            assert sync_rows == async_rows
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{st}" CASCADE', autocommit=True)
            await adb.execute(f'DROP TABLE IF EXISTS "{at}" CASCADE', autocommit=True)

    async def test_upsert_many_parity(self, db_config):
        """upsert_many yields the same final state on sync and async."""
        sdb = Database(db_config)
        adb = AsyncDatabase(db_config)
        st = _uniq("par_up_sync")
        at = _uniq("par_up_async")
        try:
            for db, t in ((sdb, st), (adb, at)):
                ddl = f'CREATE TABLE "{t}" (id INT PRIMARY KEY, v TEXT)'
                if t == st:
                    sdb.execute(ddl, autocommit=True)
                    sdb.insert_many(t, [{"id": 1, "v": "old"}])
                    sdb.upsert_many(t, [{"id": 1, "v": "new"}], conflict_columns=["id"])
                else:
                    await adb.execute(ddl, autocommit=True)
                    await adb.insert_many(t, [{"id": 1, "v": "old"}])
                    await adb.upsert_many(
                        t, [{"id": 1, "v": "new"}], conflict_columns=["id"]
                    )
            sync_rows = sdb.execute(f'SELECT v FROM "{st}" WHERE id = 1')
            async_rows = await adb.execute(f'SELECT v FROM "{at}" WHERE id = 1')
            assert sync_rows == async_rows == [{"v": "new"}]
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{st}" CASCADE', autocommit=True)
            await adb.execute(f'DROP TABLE IF EXISTS "{at}" CASCADE', autocommit=True)

    async def test_stream_parity(self, db_config):
        """stream yields identical rows on sync and async."""
        sdb = Database(db_config)
        adb = AsyncDatabase(db_config)
        st = _uniq("par_st_sync")
        at = _uniq("par_st_async")
        seed = [{"id": i, "v": str(i)} for i in range(1, 6)]
        try:
            sdb.execute(
                f'CREATE TABLE "{st}" (id INT PRIMARY KEY, v TEXT)', autocommit=True
            )
            await adb.execute(
                f'CREATE TABLE "{at}" (id INT PRIMARY KEY, v TEXT)', autocommit=True
            )
            sdb.insert_many(st, seed)
            await adb.insert_many(at, seed)
            sync_rows = list(
                sdb.stream(f'SELECT id, v FROM "{st}" ORDER BY id', batch_size=2)
            )
            async_rows = [
                r
                async for r in adb.stream(
                    f'SELECT id, v FROM "{at}" ORDER BY id', batch_size=2
                )
            ]
            assert sync_rows == async_rows
            assert len(sync_rows) == 5
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{st}" CASCADE', autocommit=True)
            await adb.execute(f'DROP TABLE IF EXISTS "{at}" CASCADE', autocommit=True)

    async def test_notify_parity_runs_both(self, db_config):
        """notify runs without error on both sync and async."""
        sdb = Database(db_config)
        adb = AsyncDatabase(db_config)
        sdb.notify("parity_chan", "payload")
        await adb.notify("parity_chan", "payload")

    # --- PAR-01/02: async mirrors match sync results ------------------------

    async def test_add_primary_key_parity(self, db_config):
        """add_primary_key produces a PK constraint on both sides."""
        sdb = Database(db_config)
        adb = AsyncDatabase(db_config)
        st = _uniq("par_pk_sync")
        at = _uniq("par_pk_async")

        def has_pk_sync(t):
            return bool(
                sdb.execute(
                    "SELECT 1 FROM information_schema.table_constraints "
                    "WHERE table_name = %s AND constraint_type = 'PRIMARY KEY'",
                    [t],
                )
            )

        try:
            sdb.execute(f'CREATE TABLE "{st}" (id INT, v TEXT)', autocommit=True)
            await adb.execute(f'CREATE TABLE "{at}" (id INT, v TEXT)', autocommit=True)
            sdb.add_primary_key(st, "id")
            await adb.add_primary_key(at, "id")
            sync_pk = has_pk_sync(st)
            async_pk = has_pk_sync(at)
            assert sync_pk == async_pk is True
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{st}" CASCADE', autocommit=True)
            await adb.execute(f'DROP TABLE IF EXISTS "{at}" CASCADE', autocommit=True)

    async def test_truncate_table_parity(self, db_config):
        """truncate_table leaves 0 rows on both sides."""
        sdb = Database(db_config)
        adb = AsyncDatabase(db_config)
        st = _uniq("par_tr_sync")
        at = _uniq("par_tr_async")
        try:
            for db, t in ((sdb, st), (adb, at)):
                if t == st:
                    sdb.execute(f'CREATE TABLE "{t}" (id INT)', autocommit=True)
                    sdb.execute(f'INSERT INTO "{t}" VALUES (1), (2)', autocommit=True)
                    sdb.truncate_table(t)
                else:
                    await adb.execute(f'CREATE TABLE "{t}" (id INT)', autocommit=True)
                    await adb.execute(
                        f'INSERT INTO "{t}" VALUES (1), (2)', autocommit=True
                    )
                    await adb.truncate_table(t)
            sync_n = sdb.execute(f'SELECT COUNT(*) AS n FROM "{st}"')[0]["n"]
            async_n = (await adb.execute(f'SELECT COUNT(*) AS n FROM "{at}"'))[0]["n"]
            assert sync_n == async_n == 0
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{st}" CASCADE', autocommit=True)
            await adb.execute(f'DROP TABLE IF EXISTS "{at}" CASCADE', autocommit=True)

    async def test_database_exists_parity(self, db_config):
        """database_exists returns the same truth value on both sides."""
        sdb = Database(db_config)
        adb = AsyncDatabase(db_config)
        assert sdb.database_exists("pycopg_test") == await adb.database_exists(
            "pycopg_test"
        )
        assert sdb.database_exists("nope_xyz") == await adb.database_exists("nope_xyz")

    async def test_list_databases_parity(self, db_config):
        """list_databases returns the same set of names on both sides."""
        sdb = Database(db_config)
        adb = AsyncDatabase(db_config)
        assert set(sdb.list_databases()) == set(await adb.list_databases())

    # --- C1 (PAR-04): from_dataframe applies primary_key on both sides ------

    async def test_from_dataframe_primary_key_parity(self, db_config):
        """C1: from_dataframe(primary_key=) produces a PK on both sync and async."""
        import pandas as pd

        sdb = Database(db_config)
        adb = AsyncDatabase(db_config)
        st = _uniq("par_df_sync")
        at = _uniq("par_df_async")
        df = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]})

        def has_pk(t):
            return bool(
                sdb.execute(
                    "SELECT 1 FROM information_schema.table_constraints "
                    "WHERE table_name = %s AND constraint_type = 'PRIMARY KEY'",
                    [t],
                )
            )

        try:
            sdb.from_dataframe(df, st, primary_key="id")
            await adb.from_dataframe(df, at, primary_key="id")
            assert has_pk(st) == has_pk(at) is True
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{st}" CASCADE', autocommit=True)
            await adb.execute(f'DROP TABLE IF EXISTS "{at}" CASCADE', autocommit=True)

    # --- PAR-07: aligned methods return identical fields/behaviour ----------

    async def test_table_info_field_parity(self, db_config):
        """table_info returns identical dict keys on sync and async."""
        sdb = Database(db_config)
        adb = AsyncDatabase(db_config)
        t = _uniq("par_ti")
        try:
            sdb.execute(
                f'CREATE TABLE "{t}" (id INT, name TEXT, created TIMESTAMP)',
                autocommit=True,
            )
            sync_info = sdb.table_info(t)
            async_info = await adb.table_info(t)
            assert [r["column_name"] for r in sync_info] == [
                r["column_name"] for r in async_info
            ]
            assert set(sync_info[0].keys()) == set(async_info[0].keys())
        finally:
            sdb.execute(f'DROP TABLE IF EXISTS "{t}" CASCADE', autocommit=True)

    async def test_list_roles_field_parity(self, db_config):
        """list_roles returns identical dict keys on sync and async."""
        sdb = Database(db_config)
        adb = AsyncDatabase(db_config)
        sync_roles = sdb.list_roles()
        async_roles = await adb.list_roles()
        assert {r["name"] for r in sync_roles} == {r["name"] for r in async_roles}
        if sync_roles and async_roles:
            assert set(sync_roles[0].keys()) == set(async_roles[0].keys())

    async def test_create_schema_owner_parity(self, db_config):
        """create_schema(owner=) behaves identically on both sides."""
        sdb = Database(db_config)
        adb = AsyncDatabase(db_config)
        ss = _uniq("par_cs_sync")
        as_ = _uniq("par_cs_async")
        try:
            sdb.create_schema(ss, owner=db_config.user)
            await adb.create_schema(as_, owner=db_config.user)
            assert sdb.schema_exists(ss) is True
            assert sdb.schema_exists(as_) is True
        finally:
            sdb.execute(f'DROP SCHEMA IF EXISTS "{ss}" CASCADE', autocommit=True)
            sdb.execute(f'DROP SCHEMA IF EXISTS "{as_}" CASCADE', autocommit=True)

    # --- D-02: create / create_from_env construct and connect --------------

    async def test_create_constructor_parity(self, db_config):
        """sync Database.create and async AsyncDatabase.create both create+connect."""
        sdb_target = _uniq("par_cdb_sync")
        adb_target = _uniq("par_cdb_async")
        admin_sync = Database(db_config)
        admin_async = AsyncDatabase(db_config)
        try:
            new_sync = Database.create(
                sdb_target,
                host=db_config.host,
                port=db_config.port,
                user=db_config.user,
                password=db_config.password,
                if_not_exists=True,
            )
            new_async = await AsyncDatabase.create(
                adb_target,
                host=db_config.host,
                port=db_config.port,
                user=db_config.user,
                password=db_config.password,
                if_not_exists=True,
            )
            assert new_sync.config.database == sdb_target
            assert new_async.config.database == adb_target
            sync_cur = new_sync.execute("SELECT current_database() AS db")[0]["db"]
            async_cur = (await new_async.execute("SELECT current_database() AS db"))[0][
                "db"
            ]
            assert sync_cur == sdb_target
            assert async_cur == adb_target
        finally:
            admin_sync.drop_database(sdb_target, if_exists=True)
            await admin_async.drop_database(adb_target, if_exists=True)


class TestEtlParity:
    """SC-4: verify full public-surface parity between ETLAccessor and AsyncETLAccessor.

    Uses ``inspect.getmembers`` to enumerate the public surface of both classes
    and asserts parity in both directions — no missing and no extra members on
    the async side.
    """

    def test_etl_accessor_public_methods_match(self):
        """ETLAccessor and AsyncETLAccessor expose identical public surfaces (SC-4).

        Checks both directions:
        - nothing in ETLAccessor is absent from AsyncETLAccessor
        - nothing in AsyncETLAccessor is absent from ETLAccessor
        """
        sync_methods = set(
            name
            for name, _ in inspect.getmembers(ETLAccessor)
            if not name.startswith("_")
        )
        async_methods = set(
            name
            for name, _ in inspect.getmembers(AsyncETLAccessor)
            if not name.startswith("_")
        )

        missing_in_async = sync_methods - async_methods
        assert not missing_in_async, (
            f"Members present in ETLAccessor but missing in AsyncETLAccessor: "
            f"{sorted(missing_in_async)}"
        )

        extra_in_async = async_methods - sync_methods
        assert not extra_in_async, (
            f"Members present in AsyncETLAccessor but absent from ETLAccessor: "
            f"{sorted(extra_in_async)}"
        )
