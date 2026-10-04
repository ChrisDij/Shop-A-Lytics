# Shop-A-Lytics

A subscription analytics dashboard that turns anonymised BoschCard student transaction data into retail insight for Stellenbosch retailers: spending over time, discounts, university-calendar context, promotion comparisons, and plain-language anomaly alerts.

> **Draft status:** lines marked **TODO** must be confirmed or completed by the team before submission (due 3 Nov). Delete this note and all TODO markers at the end.

## 1. What is in this repository

| Folder | Purpose |
|---|---|
| `backend/` | Flask API, business logic, privacy rules, tests |
| `frontend/` | React (Vite) dashboard with Recharts |
| `data_tools/` | Synthetic data generator, validator, column mapping and loaders |
| `data/` | Synthetic BoschCard CSVs, reference calendars, generated databases |
| `scripts/` | Database setup and other team utilities as they are added |
| `docs/` | BRD, adaptation document, decisions log, stack justification |

## 2. Technology stack

Python 3 + Flask (API), React + Vite + Recharts (UI), SQLite via SQLAlchemy (persistence), pandas (analytics), Flask sessions + Werkzeug password hashing (login), fpdf2 (PDF export), pytest (tests). All are free and open source. The full rationale is in `docs/stack justification/Shop-A-Lytics_Stack_Justification.pdf`.

## 3. Prerequisites

- Python 3.10 or newer
- Node.js 20.19 or newer and npm
- Git

No database server is needed: both databases are SQLite files created by the setup steps below.

## 4. Setup (from a fresh clone)

```bash
git clone <repo-url>
cd Shop-A-Lytics
cp .env.example .env        # then edit values if needed (see section 6)

# Python dependencies (the shared virtual environment lives at the repository root)
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r backend/requirements.txt

# JavaScript dependencies (run this at the repository root; npm manages frontend/ as a workspace)
npm install
```

## 5. Build the databases

The app uses **two** SQLite databases, deliberately separate (NFR 9):

- `data/analytics.sqlite`: BoschCard data only, privacy-safe, read-only for the app, rebuilt whenever new data arrives.
- `data/app.sqlite`: users, feedback, reports, audit log, calendar events. A data reload never touches it.

```bash
export BOSCHCARD_SALT="choose-a-long-random-string"   # Windows PowerShell: $env:BOSCHCARD_SALT="..."

# 1. Check the data fits the BoschCard data model (prints PASS/FAIL, exits non-zero on errors)
python data_tools/validate_data.py data/synthetic

# 2. Build the privacy-safe analytics database
python data_tools/load_analytics.py data/synthetic --out data/analytics.sqlite --prepared data/prepared

# 3. Application tables are created when the Flask app starts.
```

`load_analytics.py` removes names, emails, phone numbers, home addresses and exact birth dates; replaces student numbers with a salted pseudonym; stores money as integer cents; and keeps only age band, gender and residence type. Use the same `BOSCHCARD_SALT` every time, or pseudonyms change.

### Regenerating the synthetic data (optional)

The default dataset is already in `data/synthetic/`. To regenerate or enlarge it (seeded, so identical every time):

```bash
python data_tools/generate_boschcard_data.py data/synthetic 60000 5000
python data_tools/generate_boschcard_data.py data/synthetic_anomalies 200000 12000 --anomalies   # with planted unusual days
```

`ground_truth_promotions.csv` and `ground_truth_anomalies.csv` are answer keys for testing only; the application never reads them.

## 6. Configuration

Settings live in `.env` (see `.env.example`).

| Variable | Meaning |
|---|---|
| `ANALYTICS_DB_PATH` | Path to the read-only `analytics.sqlite` file |
| `DATABASE_URL` | SQLAlchemy URL for `app.sqlite` |
| `BOSCHCARD_SALT` | Secret used to pseudonymise student numbers (never commit it) |
| `SECRET_KEY` | Flask session secret |
| `MIN_GROUP_SIZE` | Minimum group size before a figure is shown (default 10) |
| `MIN_HISTORY_DAYS` | History needed before anomaly detection runs |
| `DEMO_VENDOR_ID` | Local-only vendor fallback until login integration is complete; remove in shared deployments |

## 7. Run the application

```bash
# Terminal 1: backend (from the repository root)
npm run start:backend                # http://localhost:5000

# Terminal 2: frontend (from the repository root)
npm run dev                          # Vite prints the local URL, normally http://localhost:5173
```

Open the frontend URL in a browser.

### Demo accounts  **TODO: fill in after the seed script exists**

| Role | Email | Password |
|---|---|---|
| Owner (Admin) | | |
| Member | | |

## 8. Using a different dataset (the lecturer's data)

1. Put the four CSVs (`student`, `vendor_type`, `vendor`, `transaction`) in a folder.
2. Edit `data_tools/column_settings.json` so it describes that data: file and column names, datetime format, GPS order (`lng,lat` or `lat,lng`), money unit (rand or cents), whether `discount` is an amount, percent or fraction, and whether `value` is before or after discount.
3. Run `python data_tools/load_analytics.py <folder> --out data/analytics.sqlite --prepared data/prepared`.
4. Read `data/prepared/validation_report.txt`. Errors stop the load; warnings are loaded but need checking.
5. Restart the backend. It reads the rebuilt analytics database without changing the application database.

Nothing in the application depends on specific vendor IDs, vendor type names or date ranges. On start-up the app checks how much data it has; if history is too short, anomaly flags show "Not assessed: insufficient history" and thin segments show a "not enough data" screen.

## 9. Tests

```bash
npm test                             # backend and data-tool tests
npm run test:backend                 # API, readiness, anomaly rules and vendor isolation
npm run test:data                    # loaders, privacy and column mapping
```

## 10. Privacy, fairness and causal safeguards

Concrete mechanisms currently implemented:

| Requirement | Mechanism | Where |
|---|---|---|
| Students never identifiable (NFR 2) | Direct identifiers never enter the analytics database; salted pseudonym only; age band instead of date of birth | `data_tools/load_analytics.py` |
| Minimum group size (NFR 3) | Required for grouped dashboard and export figures; integration is owned by the privacy/frontend slices | `MIN_GROUP_SIZE` configuration |
| Competitor confidentiality (NFR 4) | Analytics queries derive vendor scope from the session (or the explicit local demo setting), never a request parameter | `backend/app/data/analytics.py`, `backend/tests/test_vendor_isolation.py` |
| Role-based access (NFR 4) | Shared route guards and password helpers are ready for the authentication slice | `backend/app/security.py` |
| Audit trail (NFR 5) | Access to business information is logged | `backend/app/models/app_models.py` |
| Anomalies are not accusations (NFR 6) | Wording: "unusual activity requiring investigation" | `backend/app/services/anomaly.py` |
| Association, not causation (NFR 7) | Promotion views compare against a stated baseline and say "observed", never "caused" | `backend/app/services/baselines.py` |
| Insufficient history (NFR 10) | "Not assessed: insufficient history" instead of a flag | `backend/app/data/readiness.py`, `backend/app/services/anomaly.py` |

## 11. Known limitations

- "Transaction activity" is a proxy for BoschCard customer activity, not physical foot traffic.
- Promotions are not identifiable in the data; discount amount is used as a rough proxy.
- Product, brand, stock and basket-level insights are out of scope: the data model has no such fields.
- Billing, real-time data and non-Stellenbosch markets are out of scope.
- The synthetic data is fictional. Names, emails and phone numbers do not belong to real people.
- Authentication screens and session-creation routes are being integrated by their assigned owner. Until then, `DEMO_VENDOR_ID` provides an explicit local development scope only.

## 12. Documents and team

See `docs/` for the BRD, adaptation document and decisions log.

Team: Nkazimulo (ITBA), Iman (Project Manager), Christiaan (Lead Developer), Bourgeoise (QA).

Clients: Kayla, Tendekai, Carel and Tinashe.
