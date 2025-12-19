"""Create N8N owner user directly in database."""

import os
import sqlite3
import uuid
from datetime import datetime

# N8N database path
DB_PATH = os.path.expanduser("~/.n8n/database.sqlite")

# Owner credentials
EMAIL = "admin@local.host"
PASSWORD = "admin123"
FIRST_NAME = "Admin"
LAST_NAME = "User"


def generate_password_hash(password: str) -> str:
    """Generate bcrypt-compatible hash for N8N."""
    try:
        import bcrypt

        salt = bcrypt.gensalt(rounds=10)
        return bcrypt.hashpw(password.encode(), salt).decode()
    except ImportError:
        print("Installing bcrypt...")
        os.system("pip install bcrypt -q")
        import bcrypt

        salt = bcrypt.gensalt(rounds=10)
        return bcrypt.hashpw(password.encode(), salt).decode()


def create_owner():
    """Create owner user in N8N database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if user already exists
    cursor.execute("SELECT id FROM user WHERE email = ?", (EMAIL,))
    if cursor.fetchone():
        print(f"User {EMAIL} already exists!")
        conn.close()
        return

    # Generate user ID and password hash
    user_id = str(uuid.uuid4())
    password_hash = generate_password_hash(PASSWORD)
    now = datetime.utcnow().isoformat() + "Z"

    # Check table structure
    cursor.execute("PRAGMA table_info(user)")
    columns = [col[1] for col in cursor.fetchall()]
    print(f"User table columns: {columns}")

    # Insert user - adjust based on actual schema
    try:
        # Try newer schema first
        cursor.execute(
            """
            INSERT INTO user (id, email, firstName, lastName, password, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (user_id, EMAIL, FIRST_NAME, LAST_NAME, password_hash, now, now),
        )

        # Check if there's a role table or column
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%role%'")
        role_tables = cursor.fetchall()
        print(f"Role tables: {role_tables}")

        # Try to set as owner via role table if exists
        if role_tables:
            # Check for user_role or similar
            for table in role_tables:
                cursor.execute(f"PRAGMA table_info({table[0]})")
                cols = cursor.fetchall()
                print(f"Table {table[0]} columns: {cols}")

        conn.commit()
        print("Owner user created successfully!")
        print(f"Email: {EMAIL}")
        print(f"Password: {PASSWORD}")

    except Exception as e:
        print(f"Error: {e}")
        # Try to show existing data for debugging
        cursor.execute("SELECT * FROM user LIMIT 1")
        print(f"Sample user row: {cursor.fetchone()}")
        conn.rollback()

    conn.close()


if __name__ == "__main__":
    create_owner()
