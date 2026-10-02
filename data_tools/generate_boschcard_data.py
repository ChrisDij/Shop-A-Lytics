#!/usr/bin/env python3
"""
BoschCard synthetic data generator, v2 (niche-aware). All data is fictional. Reproducible via SEED.

Tables follow the project ERD: Student, Vendor_Type, Vendor, Transaction.
Extra file (NOT part of the ERD): ground_truth_promotions.csv -- the promotions injected into the data,
for testing "correlation is not causation" features.

Usage:  python generate_boschcard_data.py [output_dir] [n_transactions] [n_students] [vendor_list.csv] [--anomalies]

--anomalies plants unusual vendor-days (spikes, outages) plus public-holiday dips and writes ground_truth_anomalies.csv
and calendar_public_holidays.csv. Row count then differs slightly from n_transactions. Use 200k+ rows so signals stand out.

Optional vendor_list.csv (real vendors): columns name, address, gps, type  (+ optional: popularity, mode).
  gps as "(lng,lat)". Vendor types matching a built-in niche name reuse its pricing profile; unknown types get a generic profile.

To change or add a niche, edit the NICHES list below. Two niches (Gym & Fitness, Cafe & Coffee Shop)
are PLACEHOLDERS for the two groups whose niches were not yet confirmed.
"""
import sys, csv, math, sqlite3, datetime as dt
from pathlib import Path
import numpy as np

SEED = 2026
ARGS = [x for x in sys.argv[1:] if not x.startswith("--")]
PLANT = "--anomalies" in sys.argv          # plant unusual days (see ground_truth_anomalies.csv)
OUT = Path(ARGS[0]) if len(ARGS) > 0 else Path(".")
N_TXN = int(ARGS[1]) if len(ARGS) > 1 else 60_000
N_STUDENTS = int(ARGS[2]) if len(ARGS) > 2 else 5_000
START, END = dt.date(2025, 2, 3), dt.date(2026, 9, 27)
PRICE_RISE_DATE, PRICE_RISE = dt.date(2026, 3, 1), 1.06     # annual menu/price increase
ZERO_DISCOUNT_P = 0.08                                       # card presented, offer not applicable
REFUND_SHARE = 0.006                                         # share of all rows that are reversals

rng = np.random.default_rng(SEED)
OUT.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------ niche configuration
# lines: (label, price_lo, price_hi, prob_included, max_qty, discountable)   -> prices are per unit, VAT incl.
# discount: ("pct", (lo,hi)) or ("offpeak", (peak_lo,peak_hi), (off_lo,off_hi)); rates are fractions of discountable value
WK_MON_WED = lambda t: t.weekday() <= 2
NICHES = [
 dict(name="Restaurant", kind="basket", share=17, party={1:.30,2:.42,3:.14,4:.10,5:.04},
  lines=[("main",65,150,1,1,True),("starter",35,75,.35,1,True),("drink",25,55,.65,2,True),("dessert",40,80,.22,1,True)],
  hours={12:3,13:4,14:2,17:1,18:3,19:5,20:4,21:2}, dow=[.8,.8,.9,1,1.4,1.5,1.0],
  discount=("offpeak",(.08,.12),(.15,.25)), offpeak=WK_MON_WED,
  streets=["Dorp St","Church St","Plein St","Andringa St","Bird St"],
  vendors=["Oak & Vine Bistro","Die Eetkamer","Rozendal Grill","Spice Route Kitchen","Kloof Street Trattoria","The Pepper Pot",
           "Bosveld Braai House","Umami Stellenbosch","Casa Vinho","Ons Plek Kombuis","Vinehouse Steakery","Lemon & Thyme",
           "Kaya Kitchen","Sakura Sushi Bar","Karoo Table","Tapas Cellar"]),
 dict(name="Nightclub & Bar", kind="basket", share=15, party={1:.40,2:.32,3:.18,4:.10},
  lines=[("cover",40,100,.55,1,False),("drink",28,65,1,3,True),("shots",20,45,.30,4,True),("food",45,95,.12,1,True)],
  hours={17:1,18:2,19:3,20:4,21:5,22:6,23:6,24:5,25:3}, dow=[.3,.4,.7,1.6,2.2,2.2,.5],
  discount=("offpeak",(.05,.10),(.20,.30)), offpeak=lambda t: t.hour < 21 or t.weekday() <= 2,
  streets=["Andringa St","Bird St","Victoria St","Dorp St"],
  vendors=["Neon Cellar","The Tap Room","Fuse Nightclub","Hop & Barrel","Shebeen 7600","The Blue Door Lounge","Rooftop Sundowner",
           "Zest Cocktail Bar","Vault Live Music Venue","Tequila Trail"]),
 dict(name="Transport", kind="transport", share=10, party={1:1},
  lines=[], hours={6:1,7:3,8:3,9:1,12:1,13:1,16:2,17:2,18:2,19:2,20:2,21:3,22:5,23:6,24:6,25:4,26:2,27:1},
  dow=[.9,.9,1,1.2,1.7,1.8,1.1], discount=("pct",(.08,.15)),
  streets=["Merriman Ave","Adam Tas Rd","Plein St","Andringa St"],
  vendors=[("RideStel",{"mode":"ehail"}),("Stellies Cabs",{"mode":"ehail"}),("Eikestad E-Hail",{"mode":"ehail"}),
           ("Night Owl Safe Rides",{"mode":"ehail"}),("Winelands Airport Shuttle",{"mode":"shuttle"}),("Scoot Stellies",{"mode":"scooter"})]),
 dict(name="Pharmacy", kind="pharmacy", share=8, party={1:1},
  lines=[("main",30,120,1,1,True),("extra",25,90,.5,2,True),("vitamin",60,180,.2,1,True)],
  hours={8:3,9:4,10:4,11:4,12:4,13:3,14:3,15:3,16:3,17:2,18:1}, dow=[1.2,1.2,1.1,1.1,1.2,.8,.3],
  discount=("pct",(.05,.10)), streets=["Dorp St","Merriman Ave","Plein St","Ryneveld St"],
  vendors=["Eikestad Pharmacy","Dorp Street Dispensary","Campus Health Pharmacy","Rozendal Clinic Pharmacy","Bosman Pharmacy",
           "Green Cross Pharmacy","Victoria Chemist","Kloof Pharmacy"]),
 dict(name="Retail", kind="basket", share=14, party={1:1}, vscale=True,
  lines=[("main",79,350,1,1,True),("item",39,199,.45,2,True),("accessory",29,129,.25,1,True)],
  hours={10:2,11:3,12:3,13:3,14:3,15:3,16:2,17:1}, dow=[.6,.6,.7,.9,1.3,2.0,1.0],
  discount=("pct",(.08,.15)), streets=["Andringa St","Dorp St","Plein St","Ryneveld St","Neethling St"],
  vendors=["Thread & Needle","Urban Stellies Apparel","Thrift Society","Sole Kicks Sneakers","Campus Threads","Bosman Books",
           "Study Hub Stationery","TechMart Electronics","Paper Trail Bookshop","Cape Gadget Hub","Denim District",
           "Fresh Basket Market","Living Space Homeware","Bargain Barn"]),
 dict(name="Cinema & Theatre", kind="basket", share=7, party={1:.30,2:.50,3:.12,4:.08},
  lines=[("ticket",55,260,1,1,True),("snack",45,95,.4,1,False)],
  hours={13:1,14:1,15:2,16:2,17:3,18:4,19:6,20:5,21:3}, dow=[.5,1.2,.8,.9,1.6,1.9,1.3],
  discount=("offpeak",(.10,.15),(.30,.50)), offpeak=lambda t: t.weekday() in (1, 2, 3) or t.hour < 17,
  streets=["Merriman Ave","Victoria St","Bird St","Church St"],
  vendors=[("Starlight Cinema",{"bands":{"ticket":(70,95)}}),("Eikestad Bioscope",{"bands":{"ticket":(65,90)}}),
           ("Open Air Movie Nights",{"bands":{"ticket":(55,80)}}),("Rozendal Theatre",{"bands":{"ticket":(140,260)}}),
           ("Kampus Playhouse",{"bands":{"ticket":(90,160)}}),("Cellar Comedy Club",{"bands":{"ticket":(100,180)}})]),
 # ---- PLACEHOLDER niches (replace when the remaining two groups confirm theirs) ----
 dict(name="Gym & Fitness", kind="basket", share=4, party={1:.85,2:.15}, membership=(280, 620),
  lines=[("day_pass",40,90,1,1,True),("drink",25,60,.35,1,True),("class",60,120,.25,1,True)],
  hours={5:2,6:5,7:5,8:3,12:2,16:3,17:5,18:5,19:3,20:1}, dow=[1.4,1.3,1.3,1.2,1,.7,.6],
  discount=("pct",(.10,.20)), streets=["Merriman Ave","Adam Tas Rd","Neethling St","Banghoek Rd"],
  vendors=["IronWorks Gym","FlexZone Fitness","Pulse Studio Yoga","Peak Performance Crossfit","Aqua Active Pool","Kampus Climbing Wall"]),
 dict(name="Cafe & Coffee Shop", kind="basket", share=21, party={1:.75,2:.20,3:.05},
  lines=[("drink",28,48,1,1,True),("food",30,75,.45,1,True)],
  hours={7:2,8:4,9:5,10:5,11:4,12:4,13:3,14:3,15:2,16:1}, dow=[1.3,1.3,1.3,1.2,1.1,.9,.6],
  discount=("pct",(.05,.10)), streets=["Dorp St","Plein St","Church St","Andringa St","Bird St"],
  vendors=["Bean There Coffee","The Daily Grind","Koffiehuis Dorp","Flat White Lab","Plein Street Roasters","Crumbs & Co",
           "Cortado Corner","The Reading Room Cafe","Sunrise Bakery & Deli","Matcha Moment","Bru & Brew","Stellenbosch Tea House"]),
]
STREETS = {  # approximate centre points (lat, lng)
 "Andringa St":(-33.9325,18.8610),"Dorp St":(-33.9349,18.8590),"Bird St":(-33.9338,18.8623),"Church St":(-33.9345,18.8598),
 "Plein St":(-33.9352,18.8604),"Ryneveld St":(-33.9331,18.8580),"Merriman Ave":(-33.9298,18.8618),"Adam Tas Rd":(-33.9375,18.8545),
 "Victoria St":(-33.9370,18.8650),"Neethling St":(-33.9412,18.8640),"Banghoek Rd":(-33.9255,18.8735),"Helshoogte Rd":(-33.9210,18.8800)}

def charm(x, style):
    step = 2.5 if x < 50 else 5
    b = max(step, round(x / step) * step)
    return round(b - 0.10, 2) if style else round(b, 2)
def rate_pick(lohi):
    return max(.05, round(round(float(rng.uniform(*lohi)) / .05) * .05, 2))

GENERIC = dict(kind="basket", share=8, party={1:.6,2:.3,3:.1}, lines=[("main",40,200,1,1,True),("extra",20,100,.4,2,True)],
  hours={9:2,10:3,11:3,12:4,13:3,14:3,15:3,16:3,17:3,18:3,19:2}, dow=[1,1,1,1,1.1,1.1,.7], discount=("pct",(.05,.15)))
def load_vendor_list(path):
    """Replace the built-in fictional vendors with a supplied list, keeping niche pricing profiles where type names match."""
    by_type = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            r = {k.strip().lower(): (v or "").strip() for k, v in r.items()}
            t = r.get("type") or r.get("type_name") or r.get("vendor_type")
            by_type.setdefault(t, []).append(r)
    known = {n["name"].lower(): n for n in NICHES}
    out = []
    for t, rs in by_type.items():
        nc = dict(known.get(t.lower(), GENERIC)); nc["name"] = t; nc["streets"] = nc.get("streets") or list(STREETS)
        nc["vendors"] = [(r["name"], {"addr": r.get("address") or None, "gps": r.get("gps") or None,
                                      "pop": float(r["popularity"]) if r.get("popularity") else None,
                                      "mode": r.get("mode") or ("ehail" if nc["kind"] == "transport" else None)}) for r in rs]
        out.append(nc)
    return out
VENDORS_CSV = ARGS[3] if len(ARGS) > 3 else None
if VENDORS_CSV: NICHES = load_vendor_list(VENDORS_CSV)
NI_GYM = next((i for i, n in enumerate(NICHES) if "membership" in n), None)

# ------------------------------------------------------------------ vendor types and vendors
vendor_types = [(i + 1, n["name"]) for i, n in enumerate(NICHES)]
vendors, v_meta = [], {}
vid = 0
for ni, nc in enumerate(NICHES):
    for k, entry in enumerate(nc["vendors"]):
        name, extra = (entry, {}) if isinstance(entry, str) else entry
        vid += 1
        street = str(rng.choice(nc["streets"])); lat, lng = STREETS[street]
        lat += rng.normal(0, .0007); lng += rng.normal(0, .0007)
        vendors.append((vid, name, extra.get("addr") or f"{int(rng.integers(1,160))} {street}, Stellenbosch, 7600", extra.get("gps") or f"({lng:.6f},{lat:.6f})", ni + 1))
        pop = float(extra["pop"]) if extra.get("pop") else float(rng.lognormal(0, .6)) * (0.08 if (k == len(nc["vendors"]) - 1 and not VENDORS_CSV) else 1.0)   # last built-in vendor per niche is tiny (small-cell demo)
        m = dict(ni=ni, pop=pop, mode=extra.get("mode"), prices=[])
        vscale = float(rng.lognormal(0, .4)) if nc.get("vscale") else 1.0
        for (label, lo, hi, *_r) in nc["lines"]:
            lo2, hi2 = extra.get("bands", {}).get(label, (lo * vscale, hi * vscale))
            p0, style = float(rng.uniform(lo2, hi2)), rng.random() < .5
            m["prices"].append((charm(p0, style), charm(p0 * PRICE_RISE, style)))
        d = nc["discount"]; m["rate"] = rate_pick(d[1]); m["rate_off"] = rate_pick(d[2]) if d[0] == "offpeak" else None
        if m["mode"] == "ehail":   m.update(base=float(rng.uniform(14, 28)), per_km=float(rng.uniform(8, 11.5)))
        if m["mode"] == "shuttle": p0, st = float(rng.uniform(160, 320)), rng.random() < .5; m["fare"] = (charm(p0, st), charm(p0 * PRICE_RISE, st))
        if "membership" in nc:
            p0, st = float(rng.uniform(*nc["membership"])), rng.random() < .5; m["fee"] = (charm(p0, st), charm(p0 * PRICE_RISE, st))
        v_meta[vid] = m
vids_by_niche = {ni: [v for v in v_meta if v_meta[v]["ni"] == ni] for ni in range(len(NICHES))}

# ------------------------------------------------------------------ students (fictional)
FEM = "Aisha Amahle Anele Anri Bianca Buhle Carmen Chanel Chloe Dineo Elri Emma Faith Fatima Gugu Hannah Imaan Jana Karabo Kayla Lerato Lindiwe Liezl Maya Megan Naledi Nomsa Olivia Palesa Precious Reanette Sarah Thandi Tumelo Zinhle Zanele Zoe".split()
MALE = "Andile Ashwin Bheki Brandon Callum Christiaan Daniel Deon Ethan Francois Fikile Gareth Hendrik Ian Jaco Jason Kabelo Kagiso Liam Lungile Mandla Mpho Neo Nkosana Pieter Riaan Rohan Sibusiso Siya Thabo Themba Tiaan Tshepo Wian Xolani Yusuf Zakhele".split()
NEUT = "Alex Ari Jordan Kai Robin Sam Taylor Tumi Riley Noa".split()
LAST = ["Adams","Botha","Booysen","Brits","Cele","Coetzee","Dlamini","Du Plessis","Engelbrecht","Fourie","Govender","Hendricks","Jacobs","Jansen",
        "Khumalo","Kruger","Le Roux","Lombard","Maharaj","Malan","Mahlangu","Mbeki","Meyer","Mokoena","Molefe","Naidoo","Ndlovu","Nel","Nkosi",
        "Olivier","Pather","Petersen","Pillay","Pretorius","Radebe","Sithole","Smit","Steyn","Swanepoel","Tshabalala","Van der Merwe","Van Wyk",
        "Venter","Visser","Williams","Xaba","Zulu"]
RES = ["Lentelus House","Kruispad Hall","Bergzicht Residence","Eikestad House","Oude Molen Hall","Rozendal Lodge","Pniel Court","Simonsberg House"]
BYEARS = [2000,2001,2002,2003,2004,2005,2006,2007,2008]
BYW = np.array([2,4,6,10,16,22,22,16,4], float); BYW /= BYW.sum()
slug = lambda s: "".join(c for c in s.lower() if c.isalpha())

used, used_emails, students = set(), set(), []
while len(students) < N_STUDENTS:
    sid = str(int(rng.integers(20000000, 27999999)))
    if sid in used: continue
    used.add(sid)
    gender = str(rng.choice(["Female","Male","Non-binary","Prefer not to say"], p=[.52,.45,.02,.01]))
    pool = FEM if gender == "Female" else MALE if gender == "Male" else NEUT + FEM[:10] + MALE[:10]
    first, last = str(rng.choice(pool)), str(rng.choice(LAST))
    dob = dt.date(int(rng.choice(BYEARS, p=BYW)), 1, 1) + dt.timedelta(days=int(rng.integers(0, 365)))
    if dob > dt.date(2008, 9, 1): dob = dt.date(2008, 9, 1) - dt.timedelta(days=int(rng.integers(0, 200)))
    email = f"{slug(first)}.{slug(last)}{sid[-4:]}@student.example.ac.za"
    if email in used_emails: email = f"{slug(first)}.{slug(last)}{sid}@student.example.ac.za"   # keep emails unique at large scale
    used_emails.add(email)
    phone = f"0{int(rng.choice([60,71,72,73,76,78,79,81,82,83,84]))} 555 {int(rng.integers(0,10000)):04d}"
    if rng.random() < .45: addr = f"Room {int(rng.integers(101,420))}, {rng.choice(RES)}, Stellenbosch, 7600"
    else:
        flat = f"Flat {int(rng.integers(1,30))}, " if rng.random() < .4 else ""
        addr = f"{flat}{int(rng.integers(1,160))} {rng.choice(list(STREETS))}, Stellenbosch, 7600"
    students.append((sid, last, first, dob.isoformat(), gender, email, phone, addr))
student_ids = [s[0] for s in students]
activity = rng.lognormal(0, 1.1, N_STUDENTS); activity /= activity.sum()
niche_share = np.array([n["share"] for n in NICHES], float)
affinity = rng.lognormal(0, .5, (N_STUDENTS, len(NICHES)))
all_vids = list(v_meta)
vw = np.array([v_meta[v]["pop"] * niche_share[v_meta[v]["ni"]] for v in all_vids]); vw /= vw.sum()
favs = [set(int(x) for x in rng.choice(all_vids, 4, replace=False, p=vw)) for _ in range(N_STUDENTS)]

# ------------------------------------------------------------------ calendar model
DAYS = [START + dt.timedelta(d) for d in range((END - START).days + 1)]
def season(d, ni):
    m, day, f = d.month, d.day, 1.0
    if (m == 12 and day >= 8) or (m == 1 and day <= 25): f = .25          # summer break
    elif (m == 6 and day <= 20) or (m == 11 and day <= 25): f = .7        # exams
    elif m == 7 and day <= 18: f = .5                                     # winter recess
    elif (m == 2 and day >= 3) or (m == 3 and day <= 10): f = 1.3         # start of year
    if day >= 25 or day <= 3: f *= 1.15                                   # allowance / payday
    n = NICHES[ni]["name"]
    if n == "Retail" and ((m == 11 and day >= 22) or (m == 12 and day <= 1)): f *= 1.6   # Black Friday week
    if n == "Pharmacy" and m in (6, 7, 8): f *= 1.25                                     # flu season
    return f
day_p = []
for ni in range(len(NICHES)):
    w = np.array([NICHES[ni]["dow"][d.weekday()] * season(d, ni) for d in DAYS]); day_p.append(w / w.sum())
hour_vals = [np.array(list(n["hours"])) for n in NICHES]
hour_p = [np.array(list(n["hours"].values()), float) / sum(n["hours"].values()) for n in NICHES]
def draw_dt(ni, day=None):
    if day is None: day = DAYS[int(rng.choice(len(DAYS), p=day_p[ni]))]
    return dt.datetime.combine(day, dt.time()) + dt.timedelta(hours=int(rng.choice(hour_vals[ni], p=hour_p[ni])), minutes=int(rng.integers(0, 60)))

# ------------------------------------------------------------------ transaction value / discount model
promo_by_vendor = {}
def promo_rate(v, when):
    for ps, pe, pr in promo_by_vendor.get(v, []):
        if ps <= when.date() <= pe: return pr
    return None

def make_txn(v, when):
    m = v_meta[v]; nc = NICHES[m["ni"]]; late = when.date() >= PRICE_RISE_DATE; ix = 1 if late else 0
    total = dbase = 0.0
    if nc["kind"] == "transport":
        if m["mode"] == "ehail":
            km = float(np.clip(rng.lognormal(math.log(3.5), .7), .8, 25))
            if rng.random() < .04: km = float(rng.uniform(25, 55))               # airport / Cape Town trips
            h, wd = when.hour, when.weekday()
            surge = (float(rng.uniform(1.1, 1.6)) if wd in (0, 3, 4, 5, 6) else 1.05) if (h >= 22 or h < 4) else 1.1 if 7 <= h <= 8 else 1.0
            total = max(35.0, (m["base"] + m["per_km"] * km) * surge * (PRICE_RISE if late else 1))
        elif m["mode"] == "shuttle":
            total = m["fare"][ix] * int(rng.choice([1, 2, 3], p=[.6, .3, .1]))
        else:
            total = (10 + 2.6 * float(np.clip(rng.lognormal(math.log(9), .5), 2, 60))) * (PRICE_RISE if late else 1)
        total = round(total, 2); dbase = total
    elif nc["kind"] == "pharmacy" and rng.random() < .18:                          # dispensing: regulated pricing, not discounted
        total = round(float(rng.lognormal(math.log(230), .55)), 2); dbase = 0.0
    else:
        sizes = list(nc["party"]); n = int(rng.choice(sizes, p=np.array(list(nc["party"].values())) / sum(nc["party"].values())))
        for _ in range(n):
            for li, (label, lo, hi, p, qmax, disc) in enumerate(nc["lines"]):
                if rng.random() < p:
                    amt = (1 if qmax == 1 else int(rng.integers(1, qmax + 1))) * m["prices"][li][ix]
                    total += amt; dbase += amt if disc else 0
        if total == 0:
            total = dbase = m["prices"][0][ix]
        total, dbase = round(total, 2), round(dbase, 2)
    rate = promo_rate(v, when)
    if rate is None:
        rate = m["rate_off"] if (m["rate_off"] is not None and nc["offpeak"](when)) else m["rate"]
    disc = 0.0 if rng.random() < ZERO_DISCOUNT_P else round(dbase * rate, 2)
    return total, min(disc, total)

# ------------------------------------------------------------------ gym memberships (recurring monthly debit orders)
rows = []   # [student_id, vendor_id, datetime, value, discount, source]
n_members = max(5, int(N_TXN * 0.005)) if NI_GYM is not None else 0
for _ in range(n_members):
    sid = student_ids[int(rng.integers(N_STUDENTS))]
    g = int(rng.choice(vids_by_niche[NI_GYM], p=np.array([v_meta[x]["pop"] for x in vids_by_niche[NI_GYM]]) / sum(v_meta[x]["pop"] for x in vids_by_niche[NI_GYM])))
    join = START + dt.timedelta(int(rng.integers(0, (END - START).days - 30))); bill_day = min(join.day, 28)
    rate = v_meta[g]["rate"]
    for k in range(int(rng.integers(3, 16))):
        y, mth = divmod(join.month - 1 + k, 12); day = dt.date(join.year + y, mth + 1, bill_day)
        if day > END: break
        fee = v_meta[g]["fee"][1 if day >= PRICE_RISE_DATE else 0]
        rows.append([sid, g, dt.datetime.combine(day, dt.time(2, int(rng.integers(0, 30)))), fee, round(fee * rate, 2), "member"])
n_member_rows = len(rows)

# ------------------------------------------------------------------ promotions (ground truth)
peak_days = [d for d in DAYS if (d.month == 2 and d.day >= 3) or (d.month == 3 and d.day <= 3)]
calm_days = [d for d in DAYS if d.month in (4, 5, 8, 9, 10) and d < END - dt.timedelta(22)]
promos, extras_total = [], 0
pid = 0
for ni in range(len(NICHES)):
    for j, v in enumerate(rng.choice(vids_by_niche[ni], min(3, len(vids_by_niche[ni])), replace=False)):
        pid += 1; v = int(v)
        s = (peak_days if j == 0 else calm_days)[int(rng.integers(len(peak_days if j == 0 else calm_days)))]   # first promo per niche is confounded with seasonal peak
        e = s + dt.timedelta(int(rng.integers(7, 22))); pr = float(rng.choice([.25, .30, .35]))
        n = int(rng.integers(max(5, N_TXN // 1000), max(6, N_TXN // 500) + 1))
        promos.append((pid, v, s, e, pr, n, j == 0)); promo_by_vendor.setdefault(v, []).append((s, e, pr)); extras_total += n
n_ref = int(round(N_TXN * REFUND_SHARE)) if any(n["name"] in ("Retail", "Pharmacy") for n in NICHES) else 0
n_base = N_TXN - n_member_rows - extras_total - n_ref

# ------------------------------------------------------------------ base + promo transactions
draws = rng.choice(N_STUDENTS, size=n_base + extras_total, p=activity); di = 0
def pick_vendor(si, ni):
    vs = vids_by_niche[ni]; w = np.array([v_meta[x]["pop"] * (5 if x in favs[si] else 1) for x in vs]); return int(rng.choice(vs, p=w / w.sum()))
for _ in range(n_base):
    si = int(draws[di]); di += 1
    tw = niche_share * affinity[si]; ni = int(rng.choice(len(NICHES), p=tw / tw.sum()))
    v = pick_vendor(si, ni); when = draw_dt(ni); val, disc = make_txn(v, when)
    rows.append([student_ids[si], v, when, val, disc, "base"])
for (_, v, s, e, pr, n, _c) in promos:
    ni = v_meta[v]["ni"]; span = (e - s).days + 1
    for _ in range(n):
        si = int(draws[di]); di += 1
        when = draw_dt(ni, s + dt.timedelta(int(rng.integers(0, span)))); val, disc = make_txn(v, when)
        rows.append([student_ids[si], v, when, val, disc, "promo"])

# ------------------------------------------------------------------ planted unusual days (opt-in)
# South African public holidays in the data window (verify against gov.za before quoting). (date, name, note)
PUBLIC_HOLIDAYS = [
 ("2025-03-21","Human Rights Day",""),("2025-04-18","Good Friday",""),("2025-04-21","Family Day",""),
 ("2025-04-27","Freedom Day","falls on a Sunday"),("2025-04-28","Freedom Day (observed)","Monday after Sunday holiday"),
 ("2025-05-01","Workers' Day",""),("2025-06-16","Youth Day",""),("2025-08-09","National Women's Day","falls on a Saturday"),
 ("2025-09-24","Heritage Day",""),("2025-12-16","Day of Reconciliation",""),("2025-12-25","Christmas Day",""),("2025-12-26","Day of Goodwill",""),
 ("2026-01-01","New Year's Day",""),("2026-03-21","Human Rights Day","falls on a Saturday"),("2026-04-03","Good Friday",""),
 ("2026-04-06","Family Day",""),("2026-04-27","Freedom Day",""),("2026-05-01","Workers' Day",""),("2026-06-16","Youth Day",""),
 ("2026-08-09","National Women's Day","falls on a Sunday"),("2026-08-10","National Women's Day (observed)","Monday after Sunday holiday"),
 ("2026-09-24","Heritage Day",""),
]
HOLIDAYS = {dt.date.fromisoformat(d): n for d, n, _ in PUBLIC_HOLIDAYS}
anomaly_log = []
if PLANT:
    from collections import Counter, defaultdict
    ra = np.random.default_rng(SEED + 7)
    # 1) explained: public-holiday dips in some niches (expected_alert = False: calendar explains them)
    HOL_DROP = {"Retail": .8, "Pharmacy": .8, "Gym & Fitness": .8, "Restaurant": .4, "Cafe & Coffee Shop": .4}
    before, after, drop = Counter(), Counter(), set()
    for i, r in enumerate(rows):
        d = r[2].date(); nm = NICHES[v_meta[r[1]]["ni"]]["name"]
        if r[5] in ("base", "promo") and d in HOLIDAYS and nm in HOL_DROP:
            before[(nm, d)] += 1
            if ra.random() < HOL_DROP[nm]: drop.add(i)
            else: after[(nm, d)] += 1
    rows = [r for i, r in enumerate(rows) if i not in drop]
    for (nm, d), b in sorted(before.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        anomaly_log.append(("", "", nm, d.isoformat(), "holiday_dip", b, after[(nm, d)], f"public holiday: {HOLIDAYS[d]}", False))
    # 2) unexplained: one spike and one outage per niche (expected_alert = True)
    idx = defaultdict(list)
    for i, r in enumerate(rows):
        if r[5] in ("base", "promo"): idx[(r[1], r[2].date())].append(i)
    vol = Counter(r[1] for r in rows if r[5] in ("base", "promo"))
    allcnt = Counter((r[1], r[2].date()) for r in rows if r[3] > 0)     # includes recurring membership debits
    used, drop2, new_rows = set(), set(), []
    for ni, nc in enumerate(NICHES):
        top = sorted(vids_by_niche[ni], key=lambda v: -vol[v])
        for kind, v in (("spike", top[0]), ("outage", top[1] if len(top) > 1 else top[0])):
            if kind == "spike":
                days = [d for d in DAYS if season(d, ni) >= 1 and d not in HOLIDAYS and (v, d) not in used and d < END]
                d = days[int(ra.integers(len(days)))]; b = allcnt[(v, d)]
                extra = max(12, int(round(vol[v] / len(DAYS) * float(ra.uniform(4, 8)))))
                for _ in range(extra):
                    when = draw_dt(ni, d); val, disc = make_txn(v, when)
                    new_rows.append([student_ids[int(ra.choice(N_STUDENTS, p=activity))], v, when, val, disc, "planted"])
                a_, story = b + sum(1 for r in new_rows[-extra:] if r[2].date() == d), "unexplained surge (unannounced event or viral promotion)"
            else:
                cands = [d for (vv, d), l in idx.items() if vv == v and len(l) >= 4 and d not in HOLIDAYS and (v, d) not in used]
                if not cands: continue
                d = sorted(cands)[int(ra.integers(len(cands)))]; b = allcnt[(v, d)]; drop2.update(idx[(v, d)])
                a_, story = b - len(idx[(v, d)]), "unexplained outage (power cut, system failure or unannounced closure)"
            used.add((v, d)); anomaly_log.append((v, vname_tmp := next(x[1] for x in vendors if x[0] == v), nc["name"], d.isoformat(), kind, b, a_, story, True))
    rows = [r for i, r in enumerate(rows) if i not in drop2] + new_rows

# ------------------------------------------------------------------ refunds / reversals (retail, pharmacy)
elig = [i for i, r in enumerate(rows) if r[5] in ("base", "promo") and NICHES[v_meta[r[1]]["ni"]]["name"] in ("Retail", "Pharmacy")
        and r[3] > 0 and r[2].date() <= END - dt.timedelta(15)]
w = np.array([3.5 if NICHES[v_meta[rows[i][1]]["ni"]]["name"] == "Retail" else 1.0 for i in elig]); w /= w.sum()
for i in rng.choice(elig, n_ref, replace=False, p=w):
    sid, v, when, val, disc, _ = rows[int(i)]
    rows.append([sid, v, when + dt.timedelta(days=int(rng.integers(1, 15)), minutes=int(rng.integers(-90, 90))), -val, -disc, "refund"])

rows.sort(key=lambda r: r[2])
transactions = [(i, r[0], r[1], r[2].strftime("%Y-%m-%d %H:%M:%S"), f"{r[3]:.2f}", f"{r[4]:.2f}") for i, r in enumerate(rows, 1)]

# ------------------------------------------------------------------ write outputs
def write(name, header, data):
    with open(OUT / name, "w", newline="", encoding="utf-8") as f:
        w_ = csv.writer(f); w_.writerow(header); w_.writerows(data)
write("vendor_type.csv", ["type_id", "name"], vendor_types)
write("vendor.csv", ["vendor_id", "name", "address", "gps", "type_id"], vendors)
write("student.csv", ["id_number","last_name","first_name","dob","gender","email","phone","address"], students)
write("transaction.csv", ["transaction_id","student_id","vendor_id","datetime","value","discount"], transactions)
vname = {v[0]: v[1] for v in vendors}
write("ground_truth_promotions.csv",
      ["promo_id","vendor_id","vendor_name","start_date","end_date","discount_rate","injected_extra_transactions","start_in_seasonal_peak"],
      [(p, v, vname[v], s, e, pr, n, c) for (p, v, s, e, pr, n, c) in promos])

if PLANT:
    write("ground_truth_anomalies.csv", ["vendor_id","vendor_name","niche","date","kind","rows_before","rows_after","explained_by","expected_alert"],
          [(a,b,c,d,e,f,g,h,i) for (a,b,c,d,e,f,g,h,i) in anomaly_log])
    write("calendar_public_holidays.csv", ["date","name","note"], PUBLIC_HOLIDAYS)
db = OUT / "boschcard.sqlite"
if db.exists(): db.unlink()
con = sqlite3.connect(db); con.execute("PRAGMA foreign_keys=ON")
con.executescript("""
CREATE TABLE vendor_type(type_id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE vendor(vendor_id INTEGER PRIMARY KEY, name TEXT NOT NULL, address TEXT, gps TEXT, type_id INTEGER NOT NULL REFERENCES vendor_type(type_id));
CREATE TABLE student(id_number TEXT PRIMARY KEY, last_name TEXT, first_name TEXT, dob TEXT, gender TEXT, email TEXT, phone TEXT, address TEXT);
CREATE TABLE "transaction"(transaction_id INTEGER PRIMARY KEY, student_id TEXT NOT NULL REFERENCES student(id_number),
  vendor_id INTEGER NOT NULL REFERENCES vendor(vendor_id), datetime TEXT NOT NULL, value NUMERIC NOT NULL, discount NUMERIC NOT NULL);
""")
con.executemany("INSERT INTO vendor_type VALUES (?,?)", vendor_types)
con.executemany("INSERT INTO vendor VALUES (?,?,?,?,?)", vendors)
con.executemany("INSERT INTO student VALUES (?,?,?,?,?,?,?,?)", students)
con.executemany('INSERT INTO "transaction" VALUES (?,?,?,?,?,?)', [(a, b, c, d, float(e), float(f)) for a, b, c, d, e, f in transactions])
con.commit(); con.close()
print(f"students={len(students)} vendors={len(vendors)} types={len(vendor_types)} transactions={len(transactions)} "
      f"(base={n_base}, promo={extras_total}, membership={n_member_rows}, refunds={n_ref})")
