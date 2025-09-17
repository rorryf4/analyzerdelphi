from pathlib import Path
import sqlite3, pandas as pd

DB_PATH = Path(r"C:\Users\rorry\OneDrive\Desktop\delphi scraper\delphi-edge-scraper\data\delphi_edge.db")

print(">>> analyzer smoke test...")
with sqlite3.connect(DB_PATH) as conn:
    df = pd.read_sql_query("SELECT id,title,source,tags,published_at,fetched_at,url FROM articles ORDER BY id DESC LIMIT 10", conn)
print("rows:", len(df))
print(df[["title","source"]].head(5).to_string(index=False))
