#!/usr/bin/env python3
"""
Step 1 of loading: turn ANY supplied dataset into the standard BoschCard ERD CSVs, using column_settings.json,
then run validate_data.py and save a readable validation_report.txt.

    python prepare_data.py source_dir [--settings column_settings.json] [--out prepared]

Exit code 0 = prepared and validated with no errors.
"""
import sys, json, re, subprocess
from decimal import Decimal, InvalidOperation
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
ERD = {"student": ["id_number","last_name","first_name","dob","gender","email","phone","address"],
       "vendor_type": ["type_id","name"], "vendor": ["vendor_id","name","address","gps","type_id"],
       "transaction": ["transaction_id","student_id","vendor_id","datetime","value","discount"]}

def _dec(x):
    try: return Decimal(str(x).strip())
    except (InvalidOperation, ValueError): return None

def prepare(src, settings_path, out):
    src, out = Path(src), Path(out); out.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(Path(settings_path).read_text(encoding="utf-8")); fmt = cfg["formats"]
    notes, ok = [], True
    for table, cols in ERD.items():
        f = src / cfg["files"][table]
        if not f.exists(): notes.append(f"[ERROR] {f.name}: file not found in {src}"); ok = False; continue
        df = pd.read_csv(f, dtype=str, keep_default_na=False, encoding="utf-8-sig"); df.columns = [c.strip() for c in df.columns]
        mapping = cfg["columns"][table]; missing = [v for k, v in mapping.items() if v not in df.columns]
        if missing:
            notes.append(f"[ERROR] {f.name}: column(s) {missing} named in column_settings.json were not found. Columns present: {list(df.columns)}")
            ok = False; continue
        df = df[[mapping[c] for c in cols]].copy(); df.columns = cols

        if table == "transaction":
            dtv = pd.to_datetime(df.datetime, format=fmt["datetime"], errors="coerce"); bad = int(dtv.isna().sum())
            if bad: notes.append(f"[WARNING] transaction.datetime: {bad} value(s) do not match '{fmt['datetime']}' and were left unchanged")
            df["datetime"] = dtv.dt.strftime("%Y-%m-%d %H:%M:%S").where(dtv.notna(), df.datetime)
            val, dis = df.value.map(_dec), df.discount.map(_dec)
            unit = Decimal(100) if fmt["money_unit"] == "cents" else Decimal(1)
            newv, newd, bad = [], [], 0
            for v, d, vs, ds in zip(val, dis, df.value, df.discount):
                if v is None or d is None: newv.append(vs); newd.append(ds); bad += 1; continue
                v = v / unit
                if fmt["discount_is"] == "amount": d = d / unit; gross = v + d if fmt["value_is"] == "net" else v
                else:
                    f_ = d / (Decimal(100) if fmt["discount_is"] == "percent" else Decimal(1))
                    gross = v / (1 - f_) if fmt["value_is"] == "net" else v; d = gross * f_
                newv.append(f"{gross.quantize(Decimal('0.01'))}"); newd.append(f"{d.quantize(Decimal('0.01'))}")
            if bad: notes.append(f"[WARNING] transaction: {bad} row(s) with non-numeric value/discount left unchanged")
            df["value"], df["discount"] = newv, newd
        if table == "student":
            dob = pd.to_datetime(df.dob, format=fmt["dob"], errors="coerce")
            if dob.isna().sum(): notes.append(f"[WARNING] student.dob: {int(dob.isna().sum())} value(s) do not match '{fmt['dob']}' and were left unchanged")
            df["dob"] = dob.dt.strftime("%Y-%m-%d").where(dob.notna(), df.dob)
        if table == "vendor":
            def fix(g):
                m = re.fullmatch(r"\s*\(?\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)?\s*", g)
                if not m: return g
                a, b = m.groups(); lng, lat = (a, b) if fmt["gps_order"] == "lng,lat" else (b, a)
                return f"({float(lng):.6f},{float(lat):.6f})"
            df["gps"] = df.gps.map(fix)
        df.to_csv(out / f"{table}.csv", index=False)
    report = ["BoschCard prepare + validate report", f"source: {src.resolve()}", f"settings: {Path(settings_path).resolve()}", ""] + notes
    if ok:
        r = subprocess.run([sys.executable, str(HERE / "validate_data.py"), str(out)], capture_output=True, text=True)
        report += ["", r.stdout.strip()]; ok = r.returncode == 0
    else: report.append("\nResult: FAIL (could not prepare; see errors above)")
    (out / "validation_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    return ok, "\n".join(report)

if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    def opt(name, default):
        return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default
    src = a[0] if a else "."
    settings = opt("--settings", str(HERE / "column_settings.json")); out = opt("--out", "prepared")
    ok, rep = prepare(src, settings, out); print(rep); sys.exit(0 if ok else 1)
