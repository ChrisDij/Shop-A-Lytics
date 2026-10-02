#!/usr/bin/env python3
"""
Privacy-safe loader: builds the ANALYTICS database the application should read.

    python load_analytics.py source_dir [--settings column_settings.json] [--out analytics.sqlite] [--prepared prepared]

What it does:
  1. prepare_data.py: maps/normalises the source data and validates it (refuses to continue on errors).
  2. Drops every direct identifier: names, email, phone, home address and exact date of birth never enter the analytics DB.
  3. Replaces the student number with a salted HMAC-SHA256 pseudonym (salt from env var or a local salt file; never commit it).
  4. Coarsens attributes: age band, gender, residence type (residence / off-campus).
  5. Stores money as integer cents, GPS as numeric latitude/longitude, and adds date/hour/weekday/month columns.
Minimum group sizes / small-cell suppression remain the API's job (see README_data_swap.md).
"""
import sys, json, re, hmac, hashlib, os, secrets, sqlite3, datetime as dt
from decimal import Decimal
from pathlib import Path
import pandas as pd
from prepare_data import prepare

HERE = Path(__file__).resolve().parent
a = [x for x in sys.argv[1:] if not x.startswith("--")]
def opt(name, default): return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default
SRC = a[0] if a else "."
SETTINGS = opt("--settings", str(HERE / "column_settings.json")); OUT = Path(opt("--out", "analytics.sqlite")); PREP = Path(opt("--prepared", "prepared"))

ok, report = prepare(SRC, SETTINGS, PREP); print(report)
if not ok: sys.exit("\nAnalytics load aborted: fix the ERRORS above.")
cfg = json.loads(Path(SETTINGS).read_text(encoding="utf-8"))["privacy"]

# --- salt (never stored in the database)
salt = os.environ.get(cfg["salt_env_var"])
if not salt:
    sf = Path(cfg["salt_file"])
    if not sf.exists(): sf.write_text(secrets.token_hex(32)); print(f"\nCreated {sf}: keep it OUT of Git (add to .gitignore). Losing it means pseudonyms change on the next load.")
    salt = sf.read_text().strip()
pseudo = lambda sid: hmac.new(salt.encode(), str(sid).encode(), hashlib.sha256).hexdigest()[:16]

rd = lambda t: pd.read_csv(PREP / f"{t}.csv", dtype=str, keep_default_na=False)
stu, ven, vt, tx = rd("student"), rd("vendor"), rd("vendor_type"), rd("transaction")

# --- transactions
when = pd.to_datetime(tx.datetime)
cents = lambda s: s.map(lambda x: int((Decimal(x) * 100).quantize(Decimal(1))))
T = pd.DataFrame({"transaction_id": tx.transaction_id.astype(int), "student_hash": tx.student_id.map({i: pseudo(i) for i in stu.id_number.unique()}),
    "vendor_id": tx.vendor_id.astype(int), "datetime": tx.datetime, "date": when.dt.strftime("%Y-%m-%d"), "hour": when.dt.hour,
    "weekday": when.dt.weekday, "month": when.dt.strftime("%Y-%m"), "value_cents": cents(tx.value), "discount_cents": cents(tx.discount)})
T["is_refund"] = (T.value_cents < 0).astype(int)
# --- students: pseudonym + coarse attributes only
ref = when.max().date() if cfg["reference_date"] == "latest_transaction" else dt.date.fromisoformat(cfg["reference_date"])
dob = pd.to_datetime(stu.dob, errors="coerce"); age = ((pd.Timestamp(ref) - dob).dt.days // 365.25)
e = cfg["age_band_edges"]
def band(x):
    if pd.isna(x): return "unknown"
    return f"under {e[0]}" if x < e[0] else next((f"{e[i]}-{e[i+1]-1}" for i in range(len(e) - 1) if e[i] <= x < e[i + 1]), f"{e[-1]}+")
pat = re.compile(cfg["residence_pattern"])
S = pd.DataFrame({"student_hash": stu.id_number.map(pseudo), "age_band": age.map(band),
    "gender": stu.gender.replace("", "unknown"),
    "residence_type": stu.address.map(lambda x: "unknown" if not x else "residence" if pat.search(x) else "off-campus")})
# --- vendors
g = ven.gps.str.extract(r"\(?\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)?")
V = pd.DataFrame({"vendor_id": ven.vendor_id.astype(int), "name": ven.name, "address": ven.address,
                  "latitude": g[1].astype(float), "longitude": g[0].astype(float), "type_id": ven.type_id.astype(int)})
VT = pd.DataFrame({"type_id": vt.type_id.astype(int), "name": vt.name})

if OUT.exists(): OUT.unlink()
con = sqlite3.connect(OUT); con.execute("PRAGMA foreign_keys=ON")
con.executescript("""
CREATE TABLE vendor_type(type_id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE vendor(vendor_id INTEGER PRIMARY KEY, name TEXT NOT NULL, address TEXT, latitude REAL, longitude REAL,
  type_id INTEGER NOT NULL REFERENCES vendor_type(type_id));
CREATE TABLE student(student_hash TEXT PRIMARY KEY, age_band TEXT, gender TEXT, residence_type TEXT);
CREATE TABLE "transaction"(transaction_id INTEGER PRIMARY KEY, student_hash TEXT NOT NULL REFERENCES student(student_hash),
  vendor_id INTEGER NOT NULL REFERENCES vendor(vendor_id), datetime TEXT NOT NULL, date TEXT NOT NULL, hour INTEGER NOT NULL,
  weekday INTEGER NOT NULL, month TEXT NOT NULL, value_cents INTEGER NOT NULL, discount_cents INTEGER NOT NULL, is_refund INTEGER NOT NULL);
CREATE INDEX idx_txn_vendor_date ON "transaction"(vendor_id, date);
CREATE INDEX idx_txn_student ON "transaction"(student_hash);
CREATE TABLE load_info(key TEXT PRIMARY KEY, value TEXT);
CREATE VIEW v_vendor_day AS SELECT vendor_id, date, COUNT(*) AS transactions, COUNT(DISTINCT student_hash) AS students,
  SUM(value_cents) AS spend_cents, SUM(discount_cents) AS discount_cents FROM "transaction" WHERE is_refund = 0 GROUP BY vendor_id, date;
""")
ins = lambda t, df: con.executemany(f'INSERT INTO {t} VALUES ({",".join("?"*len(df.columns))})', df.itertuples(index=False, name=None))
ins("vendor_type", VT); ins("vendor", V); ins("student", S); ins('"transaction"', T)
con.executemany("INSERT INTO load_info VALUES (?,?)", [("loaded_at", dt.datetime.now().isoformat(timespec="seconds")), ("source", str(Path(SRC).resolve())),
    ("age_reference_date", str(ref)), ("salt_fingerprint", hashlib.sha256(salt.encode()).hexdigest()[:8]),
    ("rows_transaction", str(len(T))), ("rows_student", str(len(S))), ("rows_vendor", str(len(V)))])
con.commit(); con.close()
print(f"\nAnalytics database ready: {OUT}  (students: {len(S)}, vendors: {len(V)}, transactions: {len(T)})")
