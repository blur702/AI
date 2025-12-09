#!/usr/bin/env python3
"""
Rollback script to restore SQLite configuration if PostgreSQL migration fails.

Usage:
    python -m api_gateway.scripts.rollback_to_sqlite [--export-data]

This script:
1. Exports data from PostgreSQL (if --export-data is specified)
2. Restores SQLite database URL in config
3. Provides instructions for reverting code changes
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path


async def export_postgres_data(output_dir: Path) -> bool:
    """Export data from PostgreSQL to JSON files for backup."""
    import asyncpg

    from api_gateway.config import settings

    print("\nExporting PostgreSQL data...")

    try:
        conn = await asyncpg.connect(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
        )

        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Export jobs
        rows = await conn.fetch("SELECT * FROM jobs")
        jobs_file = output_dir / f"jobs_backup_{timestamp}.json"
        with open(jobs_file, "w") as f:
            json.dump([dict(row) for row in rows], f, indent=2, default=str)
        print(f"  Exported {len(rows)} jobs to {jobs_file}")

        # Export api_keys
        rows = await conn.fetch("SELECT * FROM api_keys")
        keys_file = output_dir / f"api_keys_backup_{timestamp}.json"
        with open(keys_file, "w") as f:
            json.dump([dict(row) for row in rows], f, indent=2, default=str)
        print(f"  Exported {len(rows)} API keys to {keys_file}")

        # Export todos (if table exists)
        try:
            rows = await conn.fetch("SELECT * FROM todos")
            todos_file = output_dir / f"todos_backup_{timestamp}.json"
            with open(todos_file, "w") as f:
                json.dump([dict(row) for row in rows], f, indent=2, default=str)
            print(f"  Exported {len(rows)} todos to {todos_file}")
        except asyncpg.UndefinedTableError:
            print("  No todos table to export")

        # Export errors (if table exists)
        try:
            rows = await conn.fetch("SELECT * FROM errors")
            errors_file = output_dir / f"errors_backup_{timestamp}.json"
            with open(errors_file, "w") as f:
                json.dump([dict(row) for row in rows], f, indent=2, default=str)
            print(f"  Exported {len(rows)} errors to {errors_file}")
        except asyncpg.UndefinedTableError:
            print("  No errors table to export")

        await conn.close()
        print(f"\nData exported to: {output_dir}")
        return True

    except Exception as e:
        print(f"  Export failed: {e}")
        return False


def generate_rollback_instructions():
    """Print instructions for rolling back the migration."""
    print("\n" + "=" * 60)
    print("ROLLBACK INSTRUCTIONS")
    print("=" * 60)

    print("""
To rollback to SQLite, follow these steps:

1. UPDATE .env FILE:
   Set DATABASE_URL back to SQLite:

   DATABASE_URL=sqlite+aiosqlite:///./api_gateway.db

   Or remove DATABASE_URL and POSTGRES_* variables entirely.

2. REVERT requirements.txt:
   Replace 'asyncpg' and 'psycopg2-binary' with 'aiosqlite':

   pip uninstall asyncpg psycopg2-binary
   pip install aiosqlite

3. REVERT database.py (if needed):
   Remove PostgreSQL-specific connection pool settings.

4. RESTORE DATA (if exported):
   Use the JSON backup files to restore data to SQLite.

5. RESTART API GATEWAY:
   python -m api_gateway.main

6. VERIFY:
   Check that the API gateway starts without errors.
""")

    print("=" * 60)


def create_env_rollback_snippet():
    """Create a snippet for reverting .env configuration."""
    print("\n.env SQLITE CONFIGURATION:")
    print("-" * 40)
    print("""
# Revert to SQLite (comment out PostgreSQL settings)
DATABASE_URL=sqlite+aiosqlite:///./api_gateway.db

# Comment out these PostgreSQL settings:
# POSTGRES_HOST=localhost
# POSTGRES_PORT=5432
# POSTGRES_USER=ai_gateway
# POSTGRES_PASSWORD=your_password
# POSTGRES_DB=ai_gateway
""")
    print("-" * 40)


async def run_rollback(export_data: bool = False):
    """Run the rollback process."""
    print("=" * 60)
    print("PostgreSQL to SQLite Rollback")
    print("=" * 60)

    if export_data:
        # When run as module from project root, use cwd; fallback to relative path
        backup_dir = Path.cwd() / "data" / "postgres_backup"
        if not backup_dir.parent.exists():
            backup_dir = Path(__file__).parent.parent.parent / "data" / "postgres_backup"
        success = await export_postgres_data(backup_dir)
        if not success:
            print("\nWarning: Data export failed, but continuing with rollback instructions.")

    generate_rollback_instructions()
    create_env_rollback_snippet()

    return True


def main():
    parser = argparse.ArgumentParser(description="Rollback PostgreSQL migration to SQLite")
    parser.add_argument(
        "--export-data",
        action="store_true",
        help="Export PostgreSQL data to JSON before rollback",
    )
    args = parser.parse_args()

    success = asyncio.run(run_rollback(export_data=args.export_data))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
