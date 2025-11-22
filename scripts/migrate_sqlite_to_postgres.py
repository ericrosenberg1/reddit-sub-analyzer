#!/usr/bin/env python3
"""
Migrate data from SQLite to PostgreSQL

This script migrates all data from the SQLite database to PostgreSQL while
preserving data integrity and relationships.

Usage:
    python scripts/migrate_sqlite_to_postgres.py

Before running:
    1. Install PostgreSQL and create a database
    2. Set environment variables:
       - POSTGRES_HOST (default: localhost)
       - POSTGRES_PORT (default: 5432)
       - POSTGRES_DB (required)
       - POSTGRES_USER (required)
       - POSTGRES_PASSWORD (required)
    3. Backup your SQLite database first!

Example:
    export POSTGRES_DB=subsearch
    export POSTGRES_USER=subsearch_user
    export POSTGRES_PASSWORD=secure_password
    python scripts/migrate_sqlite_to_postgres.py
"""

import os
import sys
import sqlite3
import psycopg2
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# SQLite database path
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "subsearch/data/subsearch.db")

# PostgreSQL connection parameters
PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
PG_DB = os.getenv("POSTGRES_DB")
PG_USER = os.getenv("POSTGRES_USER")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD")


def get_postgres_connection():
    """Create a connection to PostgreSQL."""
    if not all([PG_DB, PG_USER, PG_PASSWORD]):
        raise ValueError(
            "Missing required PostgreSQL environment variables: "
            "POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD"
        )

    return psycopg2.connect(
        host=PG_HOST,
        port=PG_PORT,
        database=PG_DB,
        user=PG_USER,
        password=PG_PASSWORD
    )


def get_sqlite_connection():
    """Create a connection to SQLite."""
    if not os.path.exists(SQLITE_DB_PATH):
        raise FileNotFoundError(f"SQLite database not found at: {SQLITE_DB_PATH}")
    return sqlite3.connect(SQLITE_DB_PATH)


def create_postgres_schema(pg_conn):
    """Create PostgreSQL schema matching the SQLite structure."""
    print("Creating PostgreSQL schema...")

    with pg_conn.cursor() as cur:
        # Drop existing tables (in reverse dependency order)
        cur.execute("DROP TABLE IF EXISTS volunteer_nodes CASCADE")
        cur.execute("DROP TABLE IF EXISTS query_runs CASCADE")
        cur.execute("DROP TABLE IF EXISTS subreddits CASCADE")

        # Create subreddits table
        cur.execute("""
            CREATE TABLE subreddits (
                id SERIAL PRIMARY KEY,
                name VARCHAR(128) UNIQUE NOT NULL,
                display_name VARCHAR(128),
                subscribers INTEGER DEFAULT 0,
                description TEXT,
                created_utc BIGINT,
                is_nsfw BOOLEAN DEFAULT FALSE,
                has_human_mod BOOLEAN DEFAULT FALSE,
                last_human_mod_activity_utc BIGINT,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                run_id INTEGER,
                job_id VARCHAR(64)
            )
        """)

        # Create indexes for subreddits
        cur.execute("CREATE INDEX idx_subreddits_name ON subreddits(name)")
        cur.execute("CREATE INDEX idx_subreddits_subscribers ON subreddits(subscribers)")
        cur.execute("CREATE INDEX idx_subreddits_nsfw ON subreddits(is_nsfw)")
        cur.execute("CREATE INDEX idx_subreddits_has_human_mod ON subreddits(has_human_mod)")
        cur.execute("CREATE INDEX idx_subreddits_run_id ON subreddits(run_id)")
        cur.execute("CREATE INDEX idx_subreddits_job_id ON subreddits(job_id)")

        # Create query_runs table
        cur.execute("""
            CREATE TABLE query_runs (
                id SERIAL PRIMARY KEY,
                job_id VARCHAR(64) UNIQUE NOT NULL,
                source VARCHAR(32) NOT NULL DEFAULT 'manual',
                started_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                keyword VARCHAR(128),
                limit_value INTEGER,
                unmoderated_only BOOLEAN NOT NULL DEFAULT TRUE,
                exclude_nsfw BOOLEAN NOT NULL DEFAULT FALSE,
                min_subscribers INTEGER NOT NULL DEFAULT 0,
                activity_mode VARCHAR(32),
                activity_threshold_utc BIGINT,
                file_name VARCHAR(256),
                result_count INTEGER DEFAULT 0,
                duration_ms INTEGER,
                error TEXT
            )
        """)

        # Create indexes for query_runs
        cur.execute("CREATE INDEX idx_query_runs_job_id ON query_runs(job_id)")
        cur.execute("CREATE INDEX idx_query_runs_source ON query_runs(source)")
        cur.execute("CREATE INDEX idx_query_runs_started_at ON query_runs(started_at DESC)")

        # Create volunteer_nodes table
        cur.execute("""
            CREATE TABLE volunteer_nodes (
                id SERIAL PRIMARY KEY,
                secret_token VARCHAR(128) UNIQUE NOT NULL,
                reddit_username VARCHAR(64),
                location VARCHAR(128),
                notes TEXT,
                health_status VARCHAR(32) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_check_in_at TIMESTAMP,
                email VARCHAR(128)
            )
        """)

        # Create indexes for volunteer_nodes
        cur.execute("CREATE INDEX idx_volunteer_nodes_secret_token ON volunteer_nodes(secret_token)")
        cur.execute("CREATE INDEX idx_volunteer_nodes_health_status ON volunteer_nodes(health_status)")

        pg_conn.commit()
    print("✓ PostgreSQL schema created")


def migrate_table(sqlite_conn, pg_conn, table_name, transform_row=None):
    """Migrate a single table from SQLite to PostgreSQL.

    Args:
        sqlite_conn: SQLite connection
        pg_conn: PostgreSQL connection
        table_name: Name of the table to migrate
        transform_row: Optional function to transform each row before inserting
    """
    print(f"\nMigrating table: {table_name}")

    sqlite_cur = sqlite_conn.cursor()
    pg_cur = pg_conn.cursor()

    # Get column names from SQLite
    sqlite_cur.execute(f"SELECT * FROM {table_name} LIMIT 0")
    columns = [desc[0] for desc in sqlite_cur.description]

    # Exclude 'id' from insert columns (PostgreSQL auto-generates it)
    insert_columns = [col for col in columns if col != 'id']

    # Count total rows
    sqlite_cur.execute(f"SELECT COUNT(*) FROM {table_name}")
    total_rows = sqlite_cur.fetchone()[0]
    print(f"  Total rows to migrate: {total_rows}")

    if total_rows == 0:
        print(f"  ✓ No data to migrate for {table_name}")
        return

    # Fetch all rows from SQLite
    sqlite_cur.execute(f"SELECT * FROM {table_name}")

    batch_size = 1000
    rows_migrated = 0
    batch = []

    for row in sqlite_cur:
        row_dict = dict(zip(columns, row))

        # Transform row if needed
        if transform_row:
            row_dict = transform_row(row_dict)

        # Build row for insertion (excluding id)
        row_values = [row_dict.get(col) for col in insert_columns]
        batch.append(row_values)

        if len(batch) >= batch_size:
            # Insert batch
            placeholders = ','.join(['%s'] * len(insert_columns))
            query = f"INSERT INTO {table_name} ({','.join(insert_columns)}) VALUES ({placeholders})"

            try:
                pg_cur.executemany(query, batch)
                pg_conn.commit()
                rows_migrated += len(batch)
                print(f"  Migrated {rows_migrated}/{total_rows} rows...", end='\r')
                batch = []
            except Exception as e:
                print(f"\n  Error inserting batch: {e}")
                pg_conn.rollback()
                raise

    # Insert remaining rows
    if batch:
        placeholders = ','.join(['%s'] * len(insert_columns))
        query = f"INSERT INTO {table_name} ({','.join(insert_columns)}) VALUES ({placeholders})"
        try:
            pg_cur.executemany(query, batch)
            pg_conn.commit()
            rows_migrated += len(batch)
        except Exception as e:
            print(f"\n  Error inserting final batch: {e}")
            pg_conn.rollback()
            raise

    print(f"  ✓ Migrated {rows_migrated}/{total_rows} rows successfully")


def transform_subreddit_row(row):
    """Transform subreddit row data types for PostgreSQL."""
    # Convert boolean integers to actual booleans
    if 'is_nsfw' in row and row['is_nsfw'] is not None:
        row['is_nsfw'] = bool(row['is_nsfw'])
    if 'has_human_mod' in row and row['has_human_mod'] is not None:
        row['has_human_mod'] = bool(row['has_human_mod'])

    # Convert indexed_at from text to timestamp
    if 'indexed_at' in row and row['indexed_at']:
        # SQLite stores as ISO string, PostgreSQL needs timestamp
        # Keep as-is, PostgreSQL will parse it
        pass

    return row


def transform_query_run_row(row):
    """Transform query_run row data types for PostgreSQL."""
    # Convert boolean integers to actual booleans
    if 'unmoderated_only' in row and row['unmoderated_only'] is not None:
        row['unmoderated_only'] = bool(row['unmoderated_only'])
    if 'exclude_nsfw' in row and row['exclude_nsfw'] is not None:
        row['exclude_nsfw'] = bool(row['exclude_nsfw'])

    # Convert timestamp strings
    for field in ['started_at', 'completed_at']:
        if field in row and row[field]:
            # Keep as-is, PostgreSQL will parse ISO strings
            pass

    return row


def transform_volunteer_node_row(row):
    """Transform volunteer_node row data types for PostgreSQL."""
    # Convert timestamp strings
    for field in ['created_at', 'updated_at', 'last_check_in_at']:
        if field in row and row[field]:
            # Keep as-is, PostgreSQL will parse ISO strings
            pass

    return row


def verify_migration(sqlite_conn, pg_conn):
    """Verify that the migration was successful by comparing row counts."""
    print("\n" + "="*60)
    print("Verifying migration...")

    sqlite_cur = sqlite_conn.cursor()
    pg_cur = pg_conn.cursor()

    tables = ['subreddits', 'query_runs', 'volunteer_nodes']
    all_match = True

    for table in tables:
        # Count rows in SQLite
        sqlite_cur.execute(f"SELECT COUNT(*) FROM {table}")
        sqlite_count = sqlite_cur.fetchone()[0]

        # Count rows in PostgreSQL
        pg_cur.execute(f"SELECT COUNT(*) FROM {table}")
        pg_count = pg_cur.fetchone()[0]

        match = "✓" if sqlite_count == pg_count else "✗"
        print(f"  {match} {table}: SQLite={sqlite_count}, PostgreSQL={pg_count}")

        if sqlite_count != pg_count:
            all_match = False

    if all_match:
        print("\n✓ Migration verified successfully!")
    else:
        print("\n✗ Migration verification failed - row counts don't match")

    return all_match


def main():
    """Main migration function."""
    print("="*60)
    print("SQLite to PostgreSQL Migration")
    print("="*60)

    print(f"\nSQLite database: {SQLITE_DB_PATH}")
    print(f"PostgreSQL target: {PG_USER}@{PG_HOST}:{PG_PORT}/{PG_DB}")

    # Confirm before proceeding
    print("\n⚠️  WARNING: This will DROP all existing tables in PostgreSQL!")
    response = input("Continue? (yes/no): ")
    if response.lower() != 'yes':
        print("Migration cancelled.")
        return

    # Connect to databases
    print("\nConnecting to databases...")
    try:
        sqlite_conn = get_sqlite_connection()
        pg_conn = get_postgres_connection()
        print("✓ Connected to both databases")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return

    try:
        # Create PostgreSQL schema
        create_postgres_schema(pg_conn)

        # Migrate tables
        print("\n" + "="*60)
        print("Migrating data...")

        migrate_table(sqlite_conn, pg_conn, 'subreddits', transform_subreddit_row)
        migrate_table(sqlite_conn, pg_conn, 'query_runs', transform_query_run_row)
        migrate_table(sqlite_conn, pg_conn, 'volunteer_nodes', transform_volunteer_node_row)

        # Verify migration
        verify_migration(sqlite_conn, pg_conn)

        print("\n" + "="*60)
        print("✓ Migration complete!")
        print("\nNext steps:")
        print("1. Update your .env file with PostgreSQL connection details")
        print("2. Set DB_TYPE=postgres in your .env")
        print("3. Restart your application")
        print("4. Backup your SQLite database for safekeeping")

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
