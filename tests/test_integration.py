import pytest
from pycopg import Database, AsyncDatabase
from pycopg.exceptions import PycopgError

# Mark all tests in this file as integration tests
pytestmark = pytest.mark.integration

class TestIntegration:
    def test_connection(self, db_config):
        """Test basic connection to real DB."""
        db = Database(db_config)
        # Execute simple query
        result = db.execute("SELECT 1 as val")
        assert len(result) == 1
        assert result[0]["val"] == 1

    def test_authors_table(self, db_config):
        """Test interaction with authors table (3NF, identity)."""
        import uuid
        email = f"dave_{uuid.uuid4()}@example.com"
        db = Database(db_config)
        
        # Insert new author using execute (returns dict)
        rows = db.execute("INSERT INTO test_schema.authors (name, email) VALUES (%s, %s) RETURNING id", ["Dave", email])
        new_id = rows[0]["id"]
        
        # Select
        authors = db.execute("SELECT * FROM test_schema.authors WHERE name = %s AND email = %s", ["Dave", email])
        assert len(authors) == 1
        assert authors[0]["id"] == new_id
        assert isinstance(authors[0]["id"], int) # smallint mapped to int in python

    def test_list_columns(self, db_config):
        """Test list_columns on real table."""
        db = Database(db_config)
        cols = db.list_columns("authors", schema="test_schema")
        assert "id" in cols
        assert "name" in cols
        assert "email" in cols
        assert cols[:3] == ["id", "name", "email"] # Check order

    def test_columns_with_types(self, db_config):
        """Test columns_with_types on real table."""
        db = Database(db_config)
        cols = db.columns_with_types("authors", schema="test_schema")
        # id is smallint, name/email text
        # psycopg mapping might return 'smallint' or 'int2' depending on driver/backend, 
        # usually information_schema returns standard SQL types 'smallint', 'text'
        
        col_dict = dict(cols)
        assert col_dict["id"] == "smallint"
        assert col_dict["name"] == "text" 
        assert col_dict["email"] == "text"

    def test_transaction_rollback(self, db_config):
        """Test transaction rollback on error."""
        import uuid
        email = f"eve_{uuid.uuid4()}@example.com"
        db = Database(db_config)
        initial_count = db.execute("SELECT count(*) as c FROM test_schema.authors")[0]["c"]
        
        try:
            with db.transaction() as conn:
                # Use connection from transaction context!
                with conn.cursor() as cur:
                     cur.execute("INSERT INTO test_schema.authors (name, email) VALUES (%s, %s)", ["Eve", email])
                raise Exception("Rollback this")
        except Exception as e:
            assert str(e) == "Rollback this"
        
        final_count = db.execute("SELECT count(*) as c FROM test_schema.authors")[0]["c"]
        assert final_count == initial_count

@pytest.mark.asyncio
class TestAsyncIntegration:
    async def test_async_connection(self, db_config):
        db = AsyncDatabase(db_config)
        result = await db.execute("SELECT 1 as val")
        assert result[0]["val"] == 1

    async def test_async_transaction_fix(self, db_config):
        """Test the transaction reuse fix on a real DB."""
        db = AsyncDatabase(db_config)
        
        # Test session reuse
        async with db.session() as session:
            # We are in a session
            # Start a transaction inside the session
            async with session.transaction():
                 # This should reuse the session connection
                 # To verify, we can set a session variable
                 await session.execute("SET application_name = 'pycopg_test_trans'")
            
            # Check if variable persisted (it should if connection was reused)
            res = await session.execute("SHOW application_name")
            assert res[0]["application_name"] == 'pycopg_test_trans'
            
    async def test_async_list_columns(self, db_config):
        db = AsyncDatabase(db_config)
        cols = await db.list_columns("articles", schema="test_schema")
        assert "id" in cols
        assert "author_id" in cols

