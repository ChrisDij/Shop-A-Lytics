# Swapping in the lecturer's dataset (target: under 15 minutes)

Requirements: Python 3.9+, `pandas`, `numpy` (`pip install pandas numpy`).

## Day-of steps
1. Put the four files in a folder, named exactly `student.csv`, `vendor_type.csv`, `vendor.csv`, `transaction.csv`.
2. Check compatibility: `python validate_data.py path/to/folder`
   - **ERROR** means it will break the system. Fix the data or adapt the loader (see "Common mismatches").
   - **WARNING** means it loads, but check it. **INFO** gives sizes and coverage.
3. Load: `python load_data.py path/to/folder boschcard.sqlite`
   - It validates first and refuses to load on errors.
   - PostgreSQL: use `schema_postgres.sql` with the same CSVs.
4. Re-tune settings that depend on data size: minimum group sizes, suppression thresholds, benchmark peer-group sizes.
5. Smoke-test each feature (every niche's views, the privacy rules, the promotion analysis).

## Common mismatches and fixes
| Symptom | Likely cause | Fix |
|---|---|---|
| gps "look like (lat,lng)" | Coordinates in the opposite order | Swap columns, or write "(lng,lat)" |
| datetime not in 'YYYY-MM-DD HH:MM:SS' | Different format | Convert in a pre-load step |
| Unknown vendor_type or FK errors | ID mismatch between files | Fix IDs in the source files |
| Vendor types differ from ours | Their own categories | Nothing in the code should hard-code type names, so map niches by the `vendor_type` table |
| Negative values | Refunds present (or not) | Handle refunds deliberately; they may be absent in their data |
| Much larger file | Real volume | Tested at 300,000 rows (30s to generate, 2s to validate, 3s to load in SQLite) |

## Practising the swap now
- Copy `vendor_list_template.csv`, fill in real vendors, then run
  `python generate_boschcard_data.py out_dir 60000 5000 my_vendors.csv`
  to regenerate transactions around your own vendor list. Vendor types matching a built-in niche reuse its pricing profile; other types get a generic profile.
- Test extremes: `python generate_boschcard_data.py big 300000 20000`.

## Do not depend on
- Our vendor IDs, vendor type names, niche list or promotion test cases (`ground_truth_promotions.csv` will not exist in their data).
- Refund rows, gym membership rows, or any specific date range.

## Added for the ITBA data-layer work

### Two-step load (use this for the real app)
1. Edit `column_settings.json` to describe the supplied data (file names, column names, datetime format, GPS order, money unit, how discount and value are defined).
2. `python load_analytics.py path/to/folder --out analytics.sqlite`
   - Runs `prepare_data.py` (maps to the standard ERD, validates, writes `prepared/validation_report.txt`) and stops on errors.
   - Builds `analytics.sqlite`: no names, emails, phones, addresses or exact birth dates; salted pseudonymous `student_hash`; age band, gender and residence type only; money in integer cents; numeric latitude/longitude; date, hour, weekday and month columns; and a `v_vendor_day` view.
   - **Salt:** set the `BOSCHCARD_SALT` environment variable, or let the script create `analytics_salt.txt`. Add `analytics_salt.txt` to `.gitignore`.
   - The API must still enforce minimum group sizes and small-cell suppression.
   - Raw ERD copy (for reference or Postgres): `load_data.py`.

### Planted unusual days
`python generate_boschcard_data.py out_dir 200000 12000 --anomalies` writes, besides the normal files:
- `ground_truth_anomalies.csv`: 8 unexplained spikes and 8 unexplained outages (`expected_alert = True`), plus holiday dips (`expected_alert = False`, explained by a public holiday).
- `calendar_public_holidays.csv`: SA public holidays in the data window (check against gov.za before citing). University term dates are not included; source them from the university.
- Use 200k+ rows: with fewer, daily counts per vendor are too small for anomalies to stand out. Outages (zero sales on a normally busy day) need a rule such as "zero or far below the usual count for that weekday"; a plain z-score barely detects them at this volume.
- Ready-made sample: `anomaly_demo/`.

### Tests
`pip install pytest` then `pytest -q test_etl.py` (12 tests: privacy of the analytics DB, hashing, money in cents, column-settings mapping on lecturer-style data, error handling, planted anomalies).
