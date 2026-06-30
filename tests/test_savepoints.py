"""TXN-02: savepoint() standalone context manager — integration tests.

These tests require a live database. Run with PGDATABASE=pycopg_test2.

Covers:
- Named savepoint partial rollback (outer session survives)
- Auto-named savepoint partial rollback
- savepoint() outside session raises RuntimeError (no live DB needed)
- transaction(savepoint_name=) — second savepoint surface (D-02)
- Async mirrors for the above
"""

from __future__ import annotations

import uuid

import pytest

from pycopg import AsyncDatabase, Database

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_table(prefix: str = "sp_test") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Guard tests (no live DB needed)
# ---------------------------------------------------------------------------


def test_savepoint_requires_session(config):
    """db.savepoint() outside a session raises RuntimeError immediately."""
    db = Database(config)
    with pytest.raises(RuntimeError, match="db.session"):
        with db.savepoint():
            pass  # pragma: no cover


@pytest.mark.asyncio
async def test_async_savepoint_requires_session(config):
    """async db.savepoint() outside a session raises RuntimeError immediately."""
    db = AsyncDatabase(config)
    with pytest.raises(RuntimeError, match="db.session"):
        async with db.savepoint():
            pass  # pragma: no cover


# ---------------------------------------------------------------------------
# Integration tests — named savepoint partial rollback
# ---------------------------------------------------------------------------
# Note: We use regular (non-TEMP) tables so we avoid ON COMMIT DELETE ROWS
# semantics interfering with the cursor-level auto-commit in db.execute().
# Each table is uniquely named and dropped in the finally block.
# ---------------------------------------------------------------------------


def test_savepoint_named_partial_rollback(db_config):
    """Named savepoint: inner rollback preserves outer work.

    Insert row A into a table, then open savepoint sp1 and insert row B.
    Force a rollback inside sp1. Assert row A persists, row B does not.
    """
    db = Database(db_config)
    table = _unique_table("sp_named")
    db.execute(f'CREATE TABLE "{table}" (id INT)', autocommit=True)
    try:
        with db.session():
            # Row A: inserted in outer session, should survive
            db.execute(f'INSERT INTO "{table}" VALUES (1)')

            # Row B: inside savepoint, gets rolled back
            try:
                with db.savepoint(name="sp1"):
                    db.execute(f'INSERT INTO "{table}" VALUES (2)')
                    raise RuntimeError("trigger rollback")
            except RuntimeError:
                pass  # rollback to sp1; outer session still alive

            rows = db.execute(f'SELECT id FROM "{table}" ORDER BY id')

        # After session commits: row A persists, row B was rolled back
        assert rows == [{"id": 1}], f"Expected only row 1, got {rows}"
    finally:
        db.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE', autocommit=True)


def test_savepoint_autoname(db_config):
    """Auto-named savepoint (name=None) also supports partial rollback."""
    db = Database(db_config)
    table = _unique_table("sp_auto")
    db.execute(f'CREATE TABLE "{table}" (id INT)', autocommit=True)
    try:
        with db.session():
            db.execute(f'INSERT INTO "{table}" VALUES (10)')

            try:
                with db.savepoint():  # name=None — psycopg auto-generates
                    db.execute(f'INSERT INTO "{table}" VALUES (20)')
                    raise RuntimeError("trigger rollback")
            except RuntimeError:
                pass

            rows = db.execute(f'SELECT id FROM "{table}" ORDER BY id')

        assert rows == [{"id": 10}], f"Expected only row 10, got {rows}"
    finally:
        db.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE', autocommit=True)


def test_transaction_savepoint_name_kwarg(db_config):
    """transaction(savepoint_name='sp2') opens a named savepoint (second surface, D-02)."""
    db = Database(db_config)
    table = _unique_table("sp_txn_kw")
    db.execute(f'CREATE TABLE "{table}" (id INT)', autocommit=True)
    try:
        with db.session():
            db.execute(f'INSERT INTO "{table}" VALUES (100)')

            try:
                with db.transaction(savepoint_name="sp2"):
                    db.execute(f'INSERT INTO "{table}" VALUES (200)')
                    raise RuntimeError("trigger rollback via transaction kwarg")
            except RuntimeError:
                pass

            rows = db.execute(f'SELECT id FROM "{table}" ORDER BY id')

        assert rows == [{"id": 100}], f"Expected only row 100, got {rows}"
    finally:
        db.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE', autocommit=True)


# ---------------------------------------------------------------------------
# Async integration mirrors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_savepoint_named_partial_rollback(db_config):
    """Async named savepoint: inner rollback preserves outer work."""
    db = AsyncDatabase(db_config)
    table = _unique_table("sp_async_named")
    await db.execute(f'CREATE TABLE "{table}" (id INT)', autocommit=True)
    try:
        async with db.session():
            await db.execute(f'INSERT INTO "{table}" VALUES (1)')

            try:
                async with db.savepoint(name="sp1"):
                    await db.execute(f'INSERT INTO "{table}" VALUES (2)')
                    raise RuntimeError("trigger async rollback")
            except RuntimeError:
                pass

            rows = await db.execute(f'SELECT id FROM "{table}" ORDER BY id')

        assert rows == [{"id": 1}], f"Expected only row 1 (async), got {rows}"
    finally:
        await db.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE', autocommit=True)


@pytest.mark.asyncio
async def test_async_savepoint_autoname(db_config):
    """Async auto-named savepoint (name=None) supports partial rollback."""
    db = AsyncDatabase(db_config)
    table = _unique_table("sp_async_auto")
    await db.execute(f'CREATE TABLE "{table}" (id INT)', autocommit=True)
    try:
        async with db.session():
            await db.execute(f'INSERT INTO "{table}" VALUES (10)')

            try:
                async with db.savepoint():
                    await db.execute(f'INSERT INTO "{table}" VALUES (20)')
                    raise RuntimeError("trigger async autoname rollback")
            except RuntimeError:
                pass

            rows = await db.execute(f'SELECT id FROM "{table}" ORDER BY id')

        assert rows == [{"id": 10}], f"Expected only row 10 (async), got {rows}"
    finally:
        await db.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE', autocommit=True)
