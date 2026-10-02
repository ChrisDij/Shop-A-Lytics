#!/usr/bin/env python3
"""
Rebuild the BoschCard SQLite database from the four ERD CSVs (drops and recreates all tables).

    python load_data.py [data_dir] [db_path] [--skip-check]

Runs validate_data.py first and refuses to load if it reports ERRORS (unless --skip-check).
For PostgreSQL use schema_postgres.sql instead (same CSVs, same column names).
"""
import sys, sqlite3, subprocess
from pathlib import Path
import pandas as pd

args = [a for a in sys.argv[1:] if not a.startswith("--")]
D = Path(args[0]) if args else Path(".")
DB = Path(args[1]) if len(args) > 1 else D / "boschcard.sqlite"

if "--skip-check" not in sys.argv:
    r = subprocess.run([sys.executable, str(Path(__file__).with_name("validate_data.py")), str(D)])
    if r.returncode != 0:
        sys.exit("\nLoad aborted: fix the ERRORS above (or use --skip-check at your own risk).")

DDL = """
DROP TABLE IF EXISTS "transaction"; DROP TABLE IF EXISTS student; DROP TABLE IF EXISTS vendor; DROP TABLE IF EXISTS vendor_type;
CREATE TABLE vendor_type(type_id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE vendor(vendor_id INTEGER PRIMARY KEY, name TEXT NOT NULL, address TEXT, gps TEXT, type_id INTEGER NOT NULL REFERENCES vendor_type(type_id));
CREATE TABLE student(id_number TEXT PRIMARY KEY, last_name TEXT, first_name TEXT, dob TEXT, gender TEXT, email TEXT, phone TEXT, address TEXT);
CREATE TABLE "transaction"(transaction_id INTEGER PRIMARY KEY, student_id TEXT NOT NULL REFERENCES student(id_number),
  vendor_id INTEGER NOT NULL REFERENCES vendor(vendor_id), datetime TEXT NOT NULL, value NUMERIC NOT NULL, discount NUMERIC NOT NULL);
CREATE INDEX idx_txn_vendor_time ON "transaction"(vendor_id, datetime);
CREATE INDEX idx_txn_student ON "transaction"(student_id);
"""
con = sqlite3.connect(DB); con.execute("PRAGMA foreign_keys=ON"); con.executescript(DDL)
for table, cols in [("vendor_type", ["type_id","name"]), ("vendor", ["vendor_id","name","address","gps","type_id"]),
                    ("student", ["id_number","last_name","first_name","dob","gender","email","phone","address"]),
                    ("transaction", ["transaction_id","student_id","vendor_id","datetime","value","discount"])]:
    df = pd.read_csv(D / f"{table}.csv", dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df.columns = [c.strip().lower() for c in df.columns]; df = df[cols]
    q = f'"{table}"' if table == "transaction" else table
    con.executemany(f"INSERT INTO {q} ({','.join(cols)}) VALUES ({','.join('?'*len(cols))})", df.itertuples(index=False, name=None))
    print(f"loaded {table}: {len(df)} rows")
con.commit(); con.close(); print(f"Database ready: {DB}")
