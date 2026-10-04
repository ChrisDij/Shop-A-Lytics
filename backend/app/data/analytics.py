import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path


class AnalyticsUnavailable(RuntimeError):
    pass


class AnalyticsRepository:
    def __init__(self, database_path):
        self.path = Path(database_path)

    @contextmanager
    def connect(self):
        if not self.path.exists():
            raise AnalyticsUnavailable(
                "The analytics database has not been built. Run data_tools/load_analytics.py."
            )
        uri = f"file:{self.path.resolve()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()

    def dataset_summary(self):
        with self.connect() as connection:
            row = connection.execute(
                'SELECT COUNT(*) AS transactions, COUNT(DISTINCT vendor_id) AS vendors, '
                'COUNT(DISTINCT student_hash) AS students, MIN(date) AS first_date, '
                'MAX(date) AS last_date FROM "transaction"'
            ).fetchone()
        return dict(row)

    def vendor(self, vendor_id):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT v.vendor_id, v.name, v.address, v.latitude, v.longitude, "
                "vt.name AS vendor_type FROM vendor v JOIN vendor_type vt "
                "ON vt.type_id = v.type_id WHERE v.vendor_id = ?",
                (vendor_id,),
            ).fetchone()
        return dict(row) if row else None

    def search_location(self, vendor_id, query):
        query = query.strip().lower()
        vendor = self.vendor(vendor_id)
        if not vendor:
            return []
        haystack = " ".join(
            str(vendor.get(key) or "") for key in ("name", "address", "vendor_type")
        ).lower()
        return [vendor] if not query or query in haystack else []

    def daily_activity(self, vendor_id):
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT date, transactions, students, spend_cents, discount_cents "
                "FROM v_vendor_day WHERE vendor_id = ? ORDER BY date",
                (vendor_id,),
            ).fetchall()
            limits = connection.execute(
                'SELECT MIN(date), MAX(date) FROM "transaction"'
            ).fetchone()
        if not limits or not limits[0]:
            return []
        by_date = {row["date"]: dict(row) for row in rows}
        cursor = date.fromisoformat(limits[0])
        end = date.fromisoformat(limits[1])
        result = []
        while cursor <= end:
            key = cursor.isoformat()
            result.append(
                by_date.get(
                    key,
                    {
                        "date": key,
                        "transactions": 0,
                        "students": 0,
                        "spend_cents": 0,
                        "discount_cents": 0,
                    },
                )
            )
            cursor += timedelta(days=1)
        return result

    def spend_series(self, vendor_id, grain="month"):
        expressions = {
            "day": "date",
            "week": "strftime('%Y-W%W', date)",
            "month": "month",
        }
        if grain not in expressions:
            raise ValueError("grain must be day, week or month")
        period = expressions[grain]
        with self.connect() as connection:
            rows = connection.execute(
                f'SELECT {period} AS period, COUNT(*) AS transactions, '
                'COUNT(DISTINCT student_hash) AS students, SUM(value_cents) AS spend_cents, '
                'SUM(discount_cents) AS discount_cents FROM "transaction" '
                'WHERE vendor_id = ? AND is_refund = 0 GROUP BY period ORDER BY period',
                (vendor_id,),
            ).fetchall()
        return [dict(row) for row in rows]
