#!/usr/bin/env python3
"""
BoschCard data compatibility check. Run this on ANY dataset (ours or the lecturer's) before loading it.

    python validate_data.py [data_dir]        # data_dir holds student.csv, vendor_type.csv, vendor.csv, transaction.csv

Exit code 0 = no ERRORS (warnings allowed), 1 = at least one ERROR.
ERROR   = the data does not fit the ERD / would break the system.
WARNING = loadable, but check it (formats, odd values, thin data).
INFO    = facts worth knowing (sizes, coverage).
"""
import sys, re
from pathlib import Path
import pandas as pd

D = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
FILES = {
    "student": ["id_number", "last_name", "first_name", "dob", "gender", "email", "phone", "address"],
    "vendor_type": ["type_id", "name"],
    "vendor": ["vendor_id", "name", "address", "gps", "type_id"],
    "transaction": ["transaction_id", "student_id", "vendor_id", "datetime", "value", "discount"],
}
MIN_VENDOR_TXNS = 30                                  # thin-data warning threshold
LAT_RANGE, LNG_RANGE = (-34.10, -33.80), (18.70, 19.05)   # rough Stellenbosch box

errors, warnings, infos = [], [], []
E = lambda m: errors.append(m); W = lambda m: warnings.append(m); I = lambda m: infos.append(m)

def load(name):
    p = D / f"{name}.csv"
    if not p.exists():
        E(f"{name}.csv is missing"); return None
    try:
        df = pd.read_csv(p, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except Exception as ex:
        E(f"{name}.csv cannot be parsed: {ex}"); return None
    df.columns = [c.strip().lower() for c in df.columns]
    miss = [c for c in FILES[name] if c not in df.columns]
    extra = [c for c in df.columns if c not in FILES[name]]
    if miss: E(f"{name}.csv missing columns: {miss}")
    if extra: W(f"{name}.csv has extra columns (ignored): {extra}")
    if len(df) == 0: E(f"{name}.csv has no rows")
    return None if miss else df

def blanks(df, name, cols):
    for c in cols:
        n = int((df[c].str.strip() == "").sum())
        if n: E(f"{name}.{c}: {n} blank value(s)")

def dupes(df, name, col):
    n = int(df[col].duplicated().sum())
    if n: E(f"{name}.{col}: {n} duplicate key(s)")

T = {k: load(k) for k in FILES}
st, vt, vd, tx = T["student"], T["vendor_type"], T["vendor"], T["transaction"]

# ---- keys, blanks, integer ids
if vt is not None:
    blanks(vt, "vendor_type", ["type_id", "name"]); dupes(vt, "vendor_type", "type_id")
    if not vt.type_id.str.fullmatch(r"\d+").all(): E("vendor_type.type_id must be integers")
    if vt.name.str.lower().duplicated().any(): W("vendor_type.name has duplicate names")
if vd is not None:
    blanks(vd, "vendor", ["vendor_id", "name", "type_id"]); dupes(vd, "vendor", "vendor_id")
    for c in ("vendor_id", "type_id"):
        if not vd[c].str.fullmatch(r"\d+").all(): E(f"vendor.{c} must be integers")
    if vt is not None and not vd.type_id.isin(vt.type_id).all():
        E(f"vendor.type_id: {int((~vd.type_id.isin(vt.type_id)).sum())} vendor(s) reference an unknown vendor_type")
    if vd.name.str.lower().duplicated().any(): W("vendor.name has duplicate vendor names")
    # gps: expect "(lng,lat)"
    bad, swapped, outside = 0, 0, 0
    for g in vd.gps:
        m = re.fullmatch(r"\s*\(?\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)?\s*", g)
        if not m: bad += 1; continue
        a, b = float(m.group(1)), float(m.group(2))
        if LNG_RANGE[0] <= a <= LNG_RANGE[1] and LAT_RANGE[0] <= b <= LAT_RANGE[1]: continue
        if LAT_RANGE[0] <= a <= LAT_RANGE[1] and LNG_RANGE[0] <= b <= LNG_RANGE[1]: swapped += 1
        else: outside += 1
    if bad: E(f"vendor.gps: {bad} value(s) not parseable as a point like (18.86,-33.93)")
    if swapped: E(f"vendor.gps: {swapped} value(s) look like (lat,lng); the ERD point convention here is (lng,lat)")
    if outside: W(f"vendor.gps: {outside} point(s) fall outside the Stellenbosch area")
if st is not None:
    blanks(st, "student", ["id_number"]); dupes(st, "student", "id_number")
    dob = pd.to_datetime(st.dob, errors="coerce", format="%Y-%m-%d")
    if dob.isna().any(): W(f"student.dob: {int(dob.isna().sum())} value(s) not in YYYY-MM-DD format")
    age = (pd.Timestamp("2026-09-30") - dob).dt.days / 365.25
    if ((age < 16) | (age > 60)).any(): W(f"student.dob: {int(((age < 16) | (age > 60)).sum())} implausible age(s) (<16 or >60)")
    if st.email.str.lower().duplicated().any(): W("student.email has duplicates")
    I(f"students: {len(st)}; gender values: {sorted(st.gender.unique())[:8]}")

# ---- transactions
if tx is not None:
    blanks(tx, "transaction", ["transaction_id", "student_id", "vendor_id", "datetime", "value", "discount"]); dupes(tx, "transaction", "transaction_id")
    if st is not None and not tx.student_id.isin(st.id_number).all():
        E(f"transaction.student_id: {int((~tx.student_id.isin(st.id_number)).sum())} row(s) reference an unknown student")
    if vd is not None and not tx.vendor_id.isin(vd.vendor_id).all():
        E(f"transaction.vendor_id: {int((~tx.vendor_id.isin(vd.vendor_id)).sum())} row(s) reference an unknown vendor")
    when = pd.to_datetime(tx.datetime, errors="coerce", format="%Y-%m-%d %H:%M:%S")
    if when.isna().any():
        alt = pd.to_datetime(tx.datetime, errors="coerce")
        E(f"transaction.datetime: {int(when.isna().sum())} value(s) not in 'YYYY-MM-DD HH:MM:SS'"
          + (" (parseable in another format; convert them)" if alt.notna().all() else ""))
    val = pd.to_numeric(tx.value, errors="coerce"); dis = pd.to_numeric(tx.discount, errors="coerce")
    if val.isna().any(): E(f"transaction.value: {int(val.isna().sum())} non-numeric value(s)")
    if dis.isna().any(): E(f"transaction.discount: {int(dis.isna().sum())} non-numeric value(s)")
    ok = val.notna() & dis.notna()
    if (dis[ok].abs() > val[ok].abs()).any(): E(f"discount exceeds value in {int((dis[ok].abs() > val[ok].abs()).sum())} row(s)")
    if ((val[ok] > 0) & (dis[ok] < 0)).any() or ((val[ok] < 0) & (dis[ok] > 0)).any(): E("value and discount have opposite signs in some rows")
    if (val[ok] == 0).any(): W(f"{int((val[ok] == 0).sum())} zero-value transaction(s)")
    neg = int((val[ok] < 0).sum())
    if neg: I(f"{neg} negative-value rows (refunds/reversals): analytics must handle these deliberately")
    dec = tx.value.str.extract(r"\.(\d+)$")[0].str.len().fillna(0)
    if (dec > 2).any(): W(f"value has more than 2 decimals in {int((dec > 2).sum())} row(s)")
    fully_dup = tx.duplicated(["student_id", "vendor_id", "datetime", "value"]).sum()
    if fully_dup: W(f"{int(fully_dup)} transaction(s) duplicate another on student, vendor, time and value")
    if when.notna().any():
        I(f"transaction period: {when.min():%Y-%m-%d} to {when.max():%Y-%m-%d}; rows: {len(tx)}")
        if (when > pd.Timestamp.now()).any(): W("some transactions are dated in the future")
        if not (when.is_monotonic_increasing): W("transactions are not sorted by datetime (fine, but do not rely on order)")
    if vd is not None and vt is not None:
        m = tx.merge(vd[["vendor_id", "type_id"]], on="vendor_id", how="left").merge(vt.rename(columns={"name": "type"}), on="type_id", how="left")
        cnt = m.groupby("type").size().sort_values(ascending=False)
        I("transactions per vendor type: " + "; ".join(f"{k}={v}" for k, v in cnt.items()))
        empty = sorted(set(vt.name) - set(cnt.index))
        if empty: W(f"vendor types with NO transactions: {empty}")
        per_v = tx.vendor_id.value_counts()
        none = int((~vd.vendor_id.isin(per_v.index)).sum())
        if none: W(f"{none} vendor(s) have no transactions")
        thin = int((per_v < MIN_VENDOR_TXNS).sum())
        I(f"vendors with < {MIN_VENDOR_TXNS} transactions (small-cell candidates): {thin} of {len(vd)}; median per vendor: {int(per_v.median())}")
    if st is not None:
        per_s = tx.student_id.value_counts()
        I(f"active students: {tx.student_id.nunique()} of {len(st)}; median transactions per student: {int(per_s.median())}; max: {int(per_s.max())}")

# ---- report
print(f"BoschCard data check: {D.resolve()}\n")
for label, items in (("ERROR", errors), ("WARNING", warnings), ("INFO", infos)):
    for m in items: print(f"[{label}] {m}")
print(f"\nResult: {'FAIL' if errors else 'PASS'}  ({len(errors)} error(s), {len(warnings)} warning(s))")
sys.exit(1 if errors else 0)
