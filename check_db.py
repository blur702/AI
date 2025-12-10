import sqlite3
import json

# Connect to the database
conn = sqlite3.connect('api_gateway.db')
cursor = conn.cursor()

# Get all table names
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
tables = cursor.fetchall()

print("Tables in database:")
for table in tables:
    print(f"  - {table[0]}")
    
    # Get table schema
    cursor.execute(f"PRAGMA table_info({table[0]});")
    columns = cursor.fetchall()
    print(f"    Columns:")
    for col in columns:
        print(f"      - {col[1]} ({col[2]})")
    
    # Get row count
    cursor.execute(f"SELECT COUNT(*) FROM {table[0]};")
    count = cursor.fetchone()[0]
    print(f"    Row count: {count}")
    
    # If there are rows, show sample data
    if count > 0:
        cursor.execute(f"SELECT * FROM {table[0]} LIMIT 3;")
        rows = cursor.fetchall()
        print(f"    Sample data:")
        for row in rows:
            print(f"      {row}")
    print()

conn.close()