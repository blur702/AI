import sqlite3
import os

DB_PATH = os.path.expanduser("~/.n8n/database.sqlite")

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Update role to global:owner
cursor.execute("UPDATE user SET roleSlug = 'global:owner' WHERE email = 'admin@local.host'")
conn.commit()

# Verify
cursor.execute("SELECT id, email, roleSlug FROM user WHERE email = 'admin@local.host'")
user = cursor.fetchone()
print(f"User: {user}")

conn.close()
print("Done! Owner role set.")
