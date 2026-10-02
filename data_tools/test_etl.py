"""
pytest tests for the data layer (generator, prepare_data, load_analytics).   Run:  pytest -q test_etl.py
"""
import os, sqlite3, subprocess, sys, json
from decimal import Decimal
from pathlib import Path
import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
PY = sys.executable
FORBIDDEN = {"last_name", "first_name", "dob", "email", "phone", "id_number"}

def run(*args, env=None, check=True):
    r = subprocess.run([PY, *map(str, args)], capture_output=True, text=True, cwd=HERE, env={**os.environ, **(env or {})})
    if check: assert r.returncode == 0, r.stdout + r.stderr
    return r

@pytest.fixture(scope="module")
def src(tmp_path_factory):
    d = tmp_path_factory.mktemp("src"); run("generate_boschcard_data.py", d, 3000, 400); return d

def build(src, tmp, salt="test-salt-1", settings=None, name="an.sqlite"):
    out = tmp / name
    args = ["load_analytics.py", src, "--out", out, "--prepared", tmp / ("prep_" + name)]
    if settings: args += ["--settings", settings]
    run(*args, env={"BOSCHCARD_SALT": salt}); return out

@pytest.fixture(scope="module")
def analytics(src, tmp_path_factory):
    return build(src, tmp_path_factory.mktemp("an"))

def rd(src, t): return pd.read_csv(Path(src) / f"{t}.csv", dtype=str, keep_default_na=False)

# ------------------------------------------------------------------ privacy-safe loader
def test_no_personal_columns_in_analytics(analytics):
    con = sqlite3.connect(analytics)
    for (t,) in con.execute("select name from sqlite_master where type in ('table','view')"):
        cols = {r[1] for r in con.execute(f'pragma table_info("{t}")')}
        assert not (cols & FORBIDDEN), f"{t} exposes {cols & FORBIDDEN}"
    assert {r[1] for r in con.execute("pragma table_info(student)")} == {"student_hash", "age_band", "gender", "residence_type"}

def test_no_personal_values_anywhere_in_file(src, analytics):
    blob = Path(analytics).read_bytes(); stu = rd(src, "student")
    for col in ("id_number", "email", "last_name", "phone"):
        leaked = [v for v in stu[col].head(150) if v.encode() in blob and col != "last_name"]
        assert not leaked, f"{col} values found in analytics file: {leaked[:3]}"
    assert not any(a.encode() in blob for a in stu.address.head(50) if a.startswith("Room"))

def test_hash_is_stable_salted_and_not_the_id(src, tmp_path):
    a1, a2, b = build(src, tmp_path, "salt-A", name="a1.sqlite"), build(src, tmp_path, "salt-A", name="a2.sqlite"), build(src, tmp_path, "salt-B", name="b.sqlite")
    h = lambda p: {r[0] for r in sqlite3.connect(p).execute("select student_hash from student")}
    assert h(a1) == h(a2), "same salt must give same pseudonyms"
    assert not (h(a1) & h(b)), "different salt must change pseudonyms"
    assert all(len(x) == 16 for x in h(a1)) and not (h(a1) & set(rd(src, "student").id_number))

def test_counts_foreign_keys_and_money(src, analytics):
    con = sqlite3.connect(analytics); tx = rd(src, "transaction")
    assert con.execute('select count(*) from "transaction"').fetchone()[0] == len(tx)
    assert con.execute("select count(*) from student").fetchone()[0] == len(rd(src, "student"))
    assert con.execute("pragma foreign_key_check").fetchall() == []
    assert con.execute('select sum(value_cents) from "transaction"').fetchone()[0] == sum(int(Decimal(v) * 100) for v in tx.value)
    assert con.execute('select sum(discount_cents) from "transaction"').fetchone()[0] == sum(int(Decimal(v) * 100) for v in tx.discount)
    assert con.execute('select count(*) from "transaction" where typeof(value_cents)!="integer"').fetchone()[0] == 0

def test_refunds_flagged_and_bands_valid(src, analytics):
    con = sqlite3.connect(analytics)
    assert con.execute('select sum(is_refund) from "transaction"').fetchone()[0] == int((pd.to_numeric(rd(src, "transaction").value) < 0).sum())
    assert {r[0] for r in con.execute("select distinct age_band from student")} <= {"under 20", "20-21", "22-23", "24+", "unknown"}

def test_gps_split_matches_source(src, analytics):
    v = rd(src, "vendor").iloc[0]; lng, lat = [float(x) for x in v.gps.strip("()").split(",")]
    r = sqlite3.connect(analytics).execute("select latitude, longitude from vendor where vendor_id=?", (int(v.vendor_id),)).fetchone()
    assert abs(r[0] - lat) < 1e-6 and abs(r[1] - lng) < 1e-6 and r[0] < 0 < r[1]

# ------------------------------------------------------------------ column settings: lecturer-style data
def lecturer_style(src, dst, variant):
    dst.mkdir(exist_ok=True)
    s, v, vt, t = (rd(src, x) for x in ("student", "vendor", "vendor_type", "transaction"))
    s.rename(columns={"id_number": "StudentNo", "last_name": "Surname", "first_name": "Name", "dob": "BirthDate"}).assign(
        BirthDate=lambda d: pd.to_datetime(d.BirthDate).dt.strftime("%d/%m/%Y")).to_csv(dst / "students.csv", index=False)
    vt.rename(columns={"type_id": "TypeID", "name": "TypeName"}).to_csv(dst / "vendor_types.csv", index=False)
    v.assign(gps=lambda d: d.gps.map(lambda g: ",".join(reversed(g.strip("()").split(","))))).rename(
        columns={"vendor_id": "VendorID", "name": "BusinessName", "address": "Addr", "gps": "Coordinates", "type_id": "TypeID"}).to_csv(dst / "vendors.csv", index=False)
    val, dis = t.value.map(Decimal), t.discount.map(Decimal)
    if variant == "gross_percent_cents":
        f = [(d / v_).quantize(Decimal("0.000001")) * 100 if v_ != 0 else Decimal(0) for v_, d in zip(val, dis)]
        tt = t.assign(value=[int(x * 100) for x in val], discount=[str(x) for x in f]); cfgf = dict(money_unit="cents", discount_is="percent", value_is="gross")
    else:
        tt = t.assign(value=[str(a - b) for a, b in zip(val, dis)], discount=[str(x) for x in dis]); cfgf = dict(money_unit="rand", discount_is="amount", value_is="net")
    tt.assign(datetime=lambda d: pd.to_datetime(d.datetime).dt.strftime("%d/%m/%Y %H:%M")).rename(columns={
        "transaction_id": "TxnID", "student_id": "StudentNo", "vendor_id": "VendorID", "datetime": "When", "value": "Amount", "discount": "Disc"}).to_csv(dst / "txns.csv", index=False)
    cfg = json.loads((HERE / "column_settings.json").read_text())
    cfg["files"] = dict(student="students.csv", vendor_type="vendor_types.csv", vendor="vendors.csv", transaction="txns.csv")
    cfg["columns"] = dict(student=dict(id_number="StudentNo", last_name="Surname", first_name="Name", dob="BirthDate", gender="gender", email="email", phone="phone", address="address"),
        vendor_type=dict(type_id="TypeID", name="TypeName"), vendor=dict(vendor_id="VendorID", name="BusinessName", address="Addr", gps="Coordinates", type_id="TypeID"),
        transaction=dict(transaction_id="TxnID", student_id="StudentNo", vendor_id="VendorID", datetime="When", value="Amount", discount="Disc"))
    cfg["formats"].update(datetime="%d/%m/%Y %H:%M", dob="%d/%m/%Y", gps_order="lat,lng", **cfgf)
    (dst / "settings.json").write_text(json.dumps(cfg)); return dst / "settings.json"

@pytest.mark.parametrize("variant", ["gross_percent_cents", "net_amount_rand"])
def test_settings_file_maps_lecturer_style_data_back_to_standard(src, tmp_path, variant):
    settings = lecturer_style(src, tmp_path / "lect", variant)
    out = tmp_path / "prep"; run("prepare_data.py", tmp_path / "lect", "--settings", settings, "--out", out)
    assert "Result: PASS" in (out / "validation_report.txt").read_text()
    a, b = rd(src, "transaction"), pd.read_csv(out / "transaction.csv", dtype=str)
    assert (a.datetime == b.datetime).all()
    assert (pd.to_numeric(a.value) - pd.to_numeric(b.value)).abs().max() <= 0.02
    assert (pd.to_numeric(a.discount) - pd.to_numeric(b.discount)).abs().max() <= 0.02
    va, vb = rd(src, "vendor"), pd.read_csv(out / "vendor.csv", dtype=str)
    assert (va.gps.map(lambda g: [round(float(x), 5) for x in g.strip("()").split(",")]) == vb.gps.map(lambda g: [round(float(x), 5) for x in g.strip("()").split(",")])).all()

def test_prepare_reports_missing_column_clearly(src, tmp_path):
    d = tmp_path / "bad"; d.mkdir()
    for t in ("student", "vendor_type", "vendor", "transaction"): rd(src, t).to_csv(d / f"{t}.csv", index=False)
    pd.read_csv(d / "transaction.csv", dtype=str).drop(columns=["discount"]).to_csv(d / "transaction.csv", index=False)
    r = run("prepare_data.py", d, "--out", tmp_path / "p", check=False)
    assert r.returncode != 0 and "discount" in r.stdout and "FAIL" in r.stdout
    assert not (tmp_path / "bad_db.sqlite").exists()

def test_loader_refuses_invalid_data(src, tmp_path):
    d = tmp_path / "bad2"; d.mkdir()
    for t in ("student", "vendor_type", "vendor", "transaction"): rd(src, t).to_csv(d / f"{t}.csv", index=False)
    t = pd.read_csv(d / "transaction.csv", dtype=str); t.loc[0, "vendor_id"] = "99999"; t.to_csv(d / "transaction.csv", index=False)
    out = tmp_path / "x.sqlite"; r = run("load_analytics.py", d, "--out", out, "--prepared", tmp_path / "p2", env={"BOSCHCARD_SALT": "s"}, check=False)
    assert r.returncode != 0 and not out.exists()

# ------------------------------------------------------------------ planted unusual days
def test_planted_anomalies_are_in_the_data(tmp_path):
    run("generate_boschcard_data.py", tmp_path, 40000, 3000, "--anomalies")
    g = pd.read_csv(tmp_path / "ground_truth_anomalies.csv"); t = pd.read_csv(tmp_path / "transaction.csv", dtype={"student_id": str})
    t["d"] = t.datetime.str[:10]; t = t[t.value > 0]
    assert g.expected_alert.sum() >= 14 and set(g.kind) == {"holiday_dip", "spike", "outage"}
    for _, r in g[g.expected_alert].iterrows():
        n = int(((t.vendor_id == r.vendor_id) & (t.d == r.date)).sum())
        assert n == r.rows_after, (r.kind, r.date, n, r.rows_after)
        if r.kind == "outage": assert n <= 2   # only recurring gym debit orders can remain
        else: assert n >= r.rows_before + 6   # late-night rows can spill past midnight onto the next calendar date
    assert (tmp_path / "calendar_public_holidays.csv").exists()
    run("validate_data.py", tmp_path)

def test_default_generation_has_no_planted_files(src):
    assert not (Path(src) / "ground_truth_anomalies.csv").exists()
