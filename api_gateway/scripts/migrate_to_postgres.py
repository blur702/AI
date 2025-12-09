#!/usr/bin/env python3
"""
Migration script to transfer data from SQLite to PostgreSQL.

Usage:
    python -m api_gateway.scripts.migrate_to_postgres [--dry-run]

Prerequisites:
    1. PostgreSQL server running
    2. Database created: CREATE DATABASE ai_gateway;
    3. User configured with permissions
    4. .env updated with POSTGRES_* settings

IMPORTANT: This script's DDL is tied to the ORM schema in api_gateway/models/database.py.
If the models change (columns, types, defaults, indexes), update the DDL here to match.
Tables: jobs, api_keys, todos, errors
Enums: job_status, todo_status, error_severity
"""

import argparse
import asyncio
import sqlite3
import sys
from pathlib import Path

import asyncpg

from api_gateway.config import settings


async def get_postgres_connection() -> asyncpg.Connection:
    """Create a direct asyncpg connection for migration."""
    return await asyncpg.connect(
        host=settings.POSTGRES_HOST,
        port=settings.POSTGRES_PORT,
        user=settings.POSTGRES_USER,
        password=settings.POSTGRES_PASSWORD,
        database=settings.POSTGRES_DB,
    )


def get_sqlite_connection() -> sqlite3.Connection:
    """Open the SQLite database.

    Looks for api_gateway.db in the project root (D:\\AI) when run via:
        python -m api_gateway.scripts.migrate_to_postgres
    """
    # When run as module, cwd should be project root
    sqlite_path = Path.cwd() / "api_gateway.db"
    if not sqlite_path.exists():
        # Fallback: relative to this script
        sqlite_path = Path(__file__).parent.parent.parent / "api_gateway.db"
    if not sqlite_path.exists():
        print(f"SQLite database not found at {sqlite_path}")
        return None
    return sqlite3.connect(sqlite_path)


async def create_tables(conn: asyncpg.Connection) -> None:
    """Create PostgreSQL tables."""
    # Create ENUM types (PostgreSQL doesn't support IF NOT EXISTS for types directly)
    await conn.execute("""
        DO $$ BEGIN
            CREATE TYPE job_status AS ENUM ('pending', 'running', 'completed', 'failed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    await conn.execute("""
        DO $$ BEGIN
            CREATE TYPE todo_status AS ENUM ('pending', 'in_progress', 'completed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    await conn.execute("""
        DO $$ BEGIN
            CREATE TYPE error_severity AS ENUM ('info', 'warning', 'error', 'critical');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id VARCHAR PRIMARY KEY,
            service VARCHAR NOT NULL,
            status job_status NOT NULL DEFAULT 'pending',
            request_data JSONB,
            result JSONB,
            error TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            timeout_seconds INTEGER NOT NULL DEFAULT 300
        );
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            key VARCHAR PRIMARY KEY,
            name VARCHAR NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            last_used_at TIMESTAMP,
            is_active BOOLEAN NOT NULL DEFAULT TRUE
        );
        CREATE INDEX IF NOT EXISTS idx_api_keys_key ON api_keys(key);
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS todos (
            id VARCHAR PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            status todo_status NOT NULL DEFAULT 'pending',
            priority INTEGER NOT NULL DEFAULT 0,
            due_date TIMESTAMP,
            tags JSONB,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMP
        );
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS errors (
            id VARCHAR PRIMARY KEY,
            service VARCHAR(100) NOT NULL,
            severity error_severity NOT NULL DEFAULT 'error',
            message TEXT NOT NULL,
            stack_trace TEXT,
            context JSONB,
            job_id VARCHAR,
            created_at TIMESTAMP NOT NULL DEFAULT NOW(),
            resolved BOOLEAN NOT NULL DEFAULT FALSE,
            resolved_at TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_errors_service ON errors(service);
        CREATE INDEX IF NOT EXISTS idx_errors_job_id ON errors(job_id);
        CREATE INDEX IF NOT EXISTS idx_errors_created_at ON errors(created_at);
    """)

    print("Tables created successfully")


async def migrate_jobs(sqlite_conn: sqlite3.Connection, pg_conn: asyncpg.Connection, dry_run: bool) -> int:
    """Migrate jobs table data."""
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT id, service, status, request_data, result, error, created_at, updated_at, timeout_seconds FROM jobs")
    rows = cursor.fetchall()

    if dry_run:
        print(f"  Would migrate {len(rows)} jobs")
        return len(rows)

    for row in rows:
        await pg_conn.execute("""
            INSERT INTO jobs (id, service, status, request_data, result, error, created_at, updated_at, timeout_seconds)
            VALUES ($1, $2, $3::job_status, $4::jsonb, $5::jsonb, $6, $7, $8, $9)
            ON CONFLICT (id) DO NOTHING
        """, *row)

    print(f"  Migrated {len(rows)} jobs")
    return len(rows)


async def migrate_api_keys(sqlite_conn: sqlite3.Connection, pg_conn: asyncpg.Connection, dry_run: bool) -> int:
    """Migrate api_keys table data."""
    cursor = sqlite_conn.cursor()
    cursor.execute("SELECT key, name, created_at, last_used_at, is_active FROM api_keys")
    rows = cursor.fetchall()

    if dry_run:
        print(f"  Would migrate {len(rows)} API keys")
        return len(rows)

    for row in rows:
        await pg_conn.execute("""
            INSERT INTO api_keys (key, name, created_at, last_used_at, is_active)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (key) DO NOTHING
        """, *row)

    print(f"  Migrated {len(rows)} API keys")
    return len(rows)


async def run_migration(dry_run: bool = False) -> bool:
    """Run the complete migration."""
    print("=" * 60)
    print("SQLite to PostgreSQL Migration")
    print("=" * 60)

    if dry_run:
        print("\n*** DRY RUN - No changes will be made ***\n")

    # Check SQLite database
    sqlite_conn = get_sqlite_connection()
    if sqlite_conn is None:
        print("\nNo SQLite database found - nothing to migrate.")
        print("Starting with fresh PostgreSQL database.")

        if not dry_run:
            pg_conn = await get_postgres_connection()
            await create_tables(pg_conn)
            await pg_conn.close()
            print("\nPostgreSQL tables created successfully.")

        return True

    try:
        # Connect to PostgreSQL
        print(f"\nConnecting to PostgreSQL at {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}...")
        pg_conn = await get_postgres_connection()
        print("Connected successfully.")

        # Create tables
        print("\nCreating tables...")
        if not dry_run:
            await create_tables(pg_conn)

        # Migrate data
        print("\nMigrating data...")
        total_migrated = 0

        print("  Jobs table:")
        total_migrated += await migrate_jobs(sqlite_conn, pg_conn, dry_run)

        print("  API Keys table:")
        total_migrated += await migrate_api_keys(sqlite_conn, pg_conn, dry_run)

        # Summary
        print("\n" + "=" * 60)
        if dry_run:
            print(f"DRY RUN COMPLETE - Would migrate {total_migrated} total records")
        else:
            print(f"MIGRATION COMPLETE - Migrated {total_migrated} total records")
        print("=" * 60)

        await pg_conn.close()
        sqlite_conn.close()

        return True

    except asyncpg.PostgresError as e:
        print(f"\nPostgreSQL error: {e}")
        return False
    except Exception as e:
        print(f"\nMigration error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite data to PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be migrated without making changes")
    args = parser.parse_args()

    success = asyncio.run(run_migration(dry_run=args.dry_run))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
