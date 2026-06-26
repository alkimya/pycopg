import os

import psycopg

# Try to connect to default postgres db to create the test db
# This assumes local dev environment with standard credentials or trust auth
# Allow override via env vars
HOST = os.getenv("PGHOST", "localhost")
USER = os.getenv("PGUSER", "postgres")
PASSWORD = os.getenv("PGPASSWORD", "postgres")
PORT = os.getenv("PGPORT", "5432")

DSN_ADMIN = f"host={HOST} port={PORT} user={USER} password={PASSWORD} dbname=postgres"


def setup_db():
    print("Connecting to admin DB to create pycopg_test...")
    try:
        conn = psycopg.connect(DSN_ADMIN, autocommit=True)
    except Exception as e:
        print(f"Failed to connect with password: {e}")
        # Try without password (trust auth)
        try:
            dsn_no_pass = f"host={HOST} port={PORT} user={USER} dbname=postgres"
            conn = psycopg.connect(dsn_no_pass, autocommit=True)
            global PASSWORD
            PASSWORD = ""  # It worked without password
        except Exception as e2:
            print(f"Could not connect to postgres: {e2}")
            return False

    # Create database pycopg_test if not exists
    try:
        conn.execute("CREATE DATABASE pycopg_test")
        print("Created database pycopg_test")
    except psycopg.errors.DuplicateDatabase:
        print("Database pycopg_test already exists")
    except Exception as e:
        print(f"Error creating database: {e}")

    conn.close()

    # Now connect to pycopg_test
    if PASSWORD:
        test_dsn = f"host={HOST} port={PORT} user={USER} password={PASSWORD} dbname=pycopg_test"
    else:
        test_dsn = f"host={HOST} port={PORT} user={USER} dbname=pycopg_test"

    print(f"Connecting to {test_dsn}...")
    conn = psycopg.connect(test_dsn, autocommit=True)

    # Create schema
    conn.execute("DROP SCHEMA IF EXISTS test_schema CASCADE")
    conn.execute("CREATE SCHEMA test_schema")

    # Create tables
    # Authors: 3NF, smallint identity
    print("Creating table authors...")
    conn.execute("""
        CREATE TABLE test_schema.authors (
            id smallint generated always as identity primary key,
            name text not null,
            email text unique not null,
            created_at timestamptz default now()
        )
    """)

    # Categories
    print("Creating table categories...")
    conn.execute("""
        CREATE TABLE test_schema.categories (
            id smallint generated always as identity primary key,
            name text not null unique
        )
    """)

    # Articles: FK to authors
    print("Creating table articles...")
    conn.execute("""
        CREATE TABLE test_schema.articles (
            id smallint generated always as identity primary key,
            title text not null,
            author_id smallint references test_schema.authors(id),
            content text,
            published_date date,
            is_published boolean default false
        )
    """)

    # Articles_Categories: Many-to-Many
    print("Creating table article_categories...")
    conn.execute("""
        CREATE TABLE test_schema.article_categories (
            article_id smallint references test_schema.articles(id) ON DELETE CASCADE,
            category_id smallint references test_schema.categories(id) ON DELETE CASCADE,
            PRIMARY KEY (article_id, category_id)
        )
    """)

    # Insert data
    print("Inserting data...")
    conn.execute("""
        INSERT INTO test_schema.authors (name, email)
        VALUES
            ('Alice', 'alice@example.com'),
            ('Bob', 'bob@example.com'),
            ('Charlie', 'charlie@example.com')
    """)

    conn.execute("""
        INSERT INTO test_schema.categories (name)
        VALUES ('Tech'), ('Life'), ('Science')
    """)

    conn.execute("""
        INSERT INTO test_schema.articles (title, author_id, content, published_date, is_published)
        VALUES
            ('My First Post', 1, 'Hello world', '2023-01-01', true),
            ('Python Tips', 1, 'Use pycopg', '2023-01-02', true),
            ('Bob''s Thoughts', 2, 'Thinking...', '2023-01-03', false)
    """)

    # Link categories
    # Alice's first post -> Tech
    conn.execute("INSERT INTO test_schema.article_categories VALUES (1, 1)")
    # Alice's second post -> Tech, Science
    conn.execute("INSERT INTO test_schema.article_categories VALUES (2, 1), (2, 3)")

    print("Test database setup complete.")
    conn.close()
    return True


if __name__ == "__main__":
    setup_db()
