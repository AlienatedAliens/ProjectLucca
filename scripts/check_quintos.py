import sqlite3
import os

db_path = "data/memory.sqlite"
if not os.path.exists(db_path):
    print("Database does not exist:", db_path)
    exit()

conn = sqlite3.connect(db_path)
c = conn.cursor()
tables = [t[0] for t in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("Tables in memory.sqlite:", tables)

for table in tables:
    try:
        cols = [col[1] for col in c.execute(f"PRAGMA table_info({table})").fetchall()]
        print(f"\nTable {table} columns:", cols)
        for col in cols:
            try:
                matches = c.execute(f"SELECT {col} FROM {table} WHERE CAST({col} AS TEXT) LIKE '%Quintos%' OR CAST({col} AS TEXT) LIKE '%Beverly%'").fetchall()
                if matches:
                    print(f"  MATCH in {table}.{col}: {len(matches)} rows")
                    for m in matches[:5]:
                        print("    ->", str(m[0])[:120])
            except Exception as e:
                pass
    except Exception as e:
        print(f"Error inspecting {table}: {e}")
