"""
Set N8N user role to global:owner.

This script directly modifies the N8N SQLite database to set the roleSlug
field to 'global:owner' for the admin user. This is useful when N8N's
web-based setup wizard fails or is bypassed.

Usage:
    python set_n8n_owner_role.py

Prerequisites:
    - N8N must be installed with database at ~/.n8n/database.sqlite
    - The admin@local.host user must already exist in the database

Note:
    This script modifies the database directly. Stop N8N before running
    to avoid potential conflicts.
"""
import sqlite3
import os


def set_owner_role() -> None:
    """
    Update the admin user's role to global:owner in N8N database.

    Connects to the N8N SQLite database, updates the roleSlug field
    for admin@local.host to 'global:owner', and verifies the change.

    Raises:
        sqlite3.Error: If database connection or update fails.
        FileNotFoundError: If the N8N database doesn't exist.
    """
    db_path = os.path.expanduser("~/.n8n/database.sqlite")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Update role to global:owner
    cursor.execute(
        "UPDATE user SET roleSlug = 'global:owner' WHERE email = 'admin@local.host'"
    )
    conn.commit()

    # Verify
    cursor.execute(
        "SELECT id, email, roleSlug FROM user WHERE email = 'admin@local.host'"
    )
    user = cursor.fetchone()
    print(f"User: {user}")

    conn.close()
    print("Done! Owner role set.")


if __name__ == "__main__":
    set_owner_role()
