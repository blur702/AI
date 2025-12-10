"""Database inspection utility for api_gateway.db."""

import logging
import re
import sqlite3
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Strict identifier regex for SQL injection prevention
SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Database path
DB_PATH = Path(__file__).parent.parent.parent / "api_gateway.db"


def validate_identifier(name: str) -> bool:
    """Validate that a name is a safe SQL identifier."""
    return bool(SAFE_IDENTIFIER_RE.match(name))


def escape_identifier(name: str) -> str:
    """Escape an identifier for safe inclusion in SQL (double-quote style)."""
    # Replace any internal " with ""
    return '"' + name.replace('"', '""') + '"'


def get_tables(cursor: sqlite3.Cursor) -> list[str]:
    """Get list of table names from the database."""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [row[0] for row in cursor.fetchall()]


def get_table_info(cursor: sqlite3.Cursor, table_name: str) -> list[tuple]:
    """Get column info for a table with SQL injection protection."""
    if not validate_identifier(table_name):
        logger.warning("Skipping invalid table name: %r", table_name)
        return []

    safe_name = escape_identifier(table_name)
    cursor.execute(f"PRAGMA table_info({safe_name})")
    return cursor.fetchall()


def get_row_count(cursor: sqlite3.Cursor, table_name: str) -> int:
    """Get row count for a table with SQL injection protection."""
    if not validate_identifier(table_name):
        logger.warning("Skipping invalid table name for count: %r", table_name)
        return -1

    safe_name = escape_identifier(table_name)
    cursor.execute(f"SELECT COUNT(*) FROM {safe_name}")
    result = cursor.fetchone()
    return result[0] if result else 0


def main() -> int:
    """Main entry point for database inspection."""
    conn: sqlite3.Connection | None = None

    try:
        logger.info("Connecting to database: %s", DB_PATH)
        conn = sqlite3.connect(str(DB_PATH))
        cursor: sqlite3.Cursor = conn.cursor()

        # Get all tables
        tables = get_tables(cursor)
        logger.info("Found %d tables", len(tables))

        for table_name in tables:
            if not validate_identifier(table_name):
                logger.error("Invalid table name detected: %r - skipping", table_name)
                continue

            logger.info("Table: %s", table_name)

            # Get column info
            columns = get_table_info(cursor, table_name)
            for col in columns:
                # col: (cid, name, type, notnull, default_value, pk)
                col_name = col[1]
                col_type = col[2]
                not_null = "NOT NULL" if col[3] else ""
                pk = "PRIMARY KEY" if col[5] else ""
                logger.debug(
                    "  Column: %s %s %s %s", col_name, col_type, not_null, pk
                )

            # Get row count
            count = get_row_count(cursor, table_name)
            logger.info("  Row count: %d", count)

        logger.info("Database inspection complete")
        return 0

    except sqlite3.Error as exc:
        logger.error("SQLite error: %s", exc, exc_info=True)
        raise
    except Exception as exc:
        logger.error("Unexpected error: %s", exc, exc_info=True)
        return 1
    finally:
        if conn is not None:
            conn.close()
            logger.debug("Database connection closed")


if __name__ == "__main__":
    sys.exit(main())
