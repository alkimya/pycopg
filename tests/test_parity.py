"""Tests for API parity between Database and AsyncDatabase.

TEST-06: Automated verification that all Database public methods exist in AsyncDatabase.
"""

import inspect

import pytest

from pycopg import AsyncDatabase, Database


class TestAsyncParity:
    """Test that AsyncDatabase maintains parity with Database API."""

    # Methods that are intentionally different between sync/async
    SYNC_ONLY_METHODS = {
        "engine",  # Sync-only SQLAlchemy engine
        "create",  # Class method alternative constructor (not in AsyncDatabase)
        "create_from_env",  # Class method alternative constructor (not in AsyncDatabase)
        "add_foreign_key",  # Not yet implemented in AsyncDatabase
        "add_primary_key",  # Not yet implemented in AsyncDatabase
        "add_unique_constraint",  # Not yet implemented in AsyncDatabase
        "database_exists",  # Not yet implemented in AsyncDatabase
        "drop_extension",  # Not yet implemented in AsyncDatabase
        "list_databases",  # Not yet implemented in AsyncDatabase
        "truncate_table",  # Not yet implemented in AsyncDatabase
    }

    ASYNC_ONLY_METHODS = {
        "async_engine",  # Async-only SQLAlchemy engine
        "insert_many",  # Async-specific batch operation
        "listen",  # Async-specific PostgreSQL LISTEN
        "notify",  # Async-specific PostgreSQL NOTIFY
        "stream",  # Async-specific streaming operation
        "upsert_many",  # Async-specific batch operation
    }

    # Known signature mismatches (parity bugs to be fixed)
    KNOWN_SIGNATURE_MISMATCHES = {
        "create_schema",  # Database has 'owner' param, AsyncDatabase doesn't
        "create_extension",  # Database has 'schema' param, AsyncDatabase doesn't
    }

    def test_all_database_public_methods_exist_in_async(self):
        """Verify all Database methods (minus exceptions) exist in AsyncDatabase."""
        db_methods = set(
            name for name, _ in inspect.getmembers(Database) if not name.startswith("_")
        )
        async_methods = set(
            name for name, _ in inspect.getmembers(AsyncDatabase) if not name.startswith("_")
        )

        # Methods that should exist in AsyncDatabase
        expected_in_async = db_methods - self.SYNC_ONLY_METHODS

        # Find missing methods
        missing = expected_in_async - async_methods

        assert not missing, f"Methods in Database but missing in AsyncDatabase: {sorted(missing)}"

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
            set(db_methods.keys()) & set(async_methods.keys())
        ) - self.SYNC_ONLY_METHODS - self.ASYNC_ONLY_METHODS

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
                    mismatch_str = (
                        f"{method_name}: Database{db_params} != AsyncDatabase{async_params}"
                    )
                    if method_name in self.KNOWN_SIGNATURE_MISMATCHES:
                        known_mismatches.append(mismatch_str)
                    else:
                        signature_mismatches.append(mismatch_str)
            except (ValueError, TypeError):
                # Some methods may not have inspectable signatures (properties, etc.)
                continue

        # Report known mismatches as info (not failure)
        if known_mismatches:
            print(f"\n\nKnown signature mismatches (tracked):\n" + "\n".join(known_mismatches))

        # Fail on unexpected mismatches
        assert (
            not signature_mismatches
        ), f"New signature mismatches found:\n" + "\n".join(signature_mismatches)

    def test_known_exceptions_documented(self):
        """Assert the exception lists are explicitly maintained."""
        db_methods = set(
            name for name, _ in inspect.getmembers(Database) if not name.startswith("_")
        )
        async_methods = set(
            name for name, _ in inspect.getmembers(AsyncDatabase) if not name.startswith("_")
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
            name for name, _ in inspect.getmembers(AsyncDatabase) if not name.startswith("_")
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
