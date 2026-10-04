import csv
import sqlite3
from datetime import date, timedelta

import pytest

from app import create_app


@pytest.fixture()
def analytics_database(tmp_path):
    database_path = tmp_path / "analytics.sqlite"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE vendor_type (
            type_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE TABLE vendor (
            vendor_id INTEGER PRIMARY KEY,
            type_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            address TEXT,
            latitude REAL,
            longitude REAL
        );
        CREATE TABLE "transaction" (
            transaction_id INTEGER PRIMARY KEY,
            student_hash TEXT NOT NULL,
            vendor_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            month TEXT NOT NULL,
            value_cents INTEGER NOT NULL,
            discount_cents INTEGER NOT NULL,
            is_refund INTEGER NOT NULL DEFAULT 0
        );
        CREATE VIEW v_vendor_day AS
        SELECT vendor_id, date,
               COUNT(*) AS transactions,
               COUNT(DISTINCT student_hash) AS students,
               SUM(value_cents) AS spend_cents,
               SUM(discount_cents) AS discount_cents
        FROM "transaction"
        WHERE is_refund = 0
        GROUP BY vendor_id, date;
        """
    )
    connection.execute("INSERT INTO vendor_type VALUES (1, 'Food and drink')")
    connection.executemany(
        "INSERT INTO vendor VALUES (?, 1, ?, ?, ?, ?)",
        [
            (1, "Campus Cafe", "10 University Road", -33.9, 18.8),
            (2, "Other Vendor", "99 Private Lane", -33.91, 18.81),
        ],
    )

    transaction_id = 1
    start = date(2026, 1, 1)
    for offset in range(105):
        day = start + timedelta(days=offset)
        vendor_one_count = 30 if offset == 104 else 5
        for vendor_id, count in ((1, vendor_one_count), (2, 3)):
            for sequence in range(count):
                connection.execute(
                    'INSERT INTO "transaction" VALUES (?, ?, ?, ?, ?, ?, ?, 0)',
                    (
                        transaction_id,
                        f"student-{vendor_id}-{sequence}",
                        vendor_id,
                        day.isoformat(),
                        day.strftime("%Y-%m"),
                        1_000,
                        50,
                    ),
                )
                transaction_id += 1
    connection.commit()
    connection.close()
    return database_path


@pytest.fixture()
def calendar_files(tmp_path):
    holiday_path = tmp_path / "public_holidays.csv"
    university_path = tmp_path / "university_calendar.csv"
    with holiday_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["date", "name"])
        writer.writeheader()
    with university_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=["start_date", "end_date", "type", "name"]
        )
        writer.writeheader()
    return holiday_path, university_path


@pytest.fixture()
def app(analytics_database, calendar_files):
    holiday_path, university_path = calendar_files
    return create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret",
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "ANALYTICS_DB_PATH": str(analytics_database),
            "PUBLIC_HOLIDAYS_PATH": str(holiday_path),
            "UNIVERSITY_CALENDAR_PATH": str(university_path),
            "MIN_HISTORY_DAYS": 42,
            "DEMO_VENDOR_ID": 1,
        }
    )


@pytest.fixture()
def client(app):
    return app.test_client()
