import csv
from datetime import date
from pathlib import Path


class CalendarContext:
    def __init__(self, public_holidays_path, university_calendar_path):
        self.holidays = self._holidays(public_holidays_path)
        self.periods = self._periods(university_calendar_path)

    @staticmethod
    def _holidays(path):
        source = Path(path)
        if not source.exists():
            return {}
        with source.open(encoding="utf-8-sig", newline="") as stream:
            return {row["date"]: row["name"] for row in csv.DictReader(stream)}

    @staticmethod
    def _periods(path):
        source = Path(path)
        if not source.exists():
            return []
        with source.open(encoding="utf-8-sig", newline="") as stream:
            rows = []
            for row in csv.DictReader(stream):
                if not row.get("start_date") or not row.get("end_date"):
                    continue
                rows.append(
                    {
                        **row,
                        "start": date.fromisoformat(row["start_date"]),
                        "end": date.fromisoformat(row["end_date"]),
                    }
                )
            return rows

    def describe(self, day):
        key = day.isoformat()
        if key in self.holidays:
            return {
                "key": "public_holiday",
                "name": self.holidays[key],
                "explains_variation": True,
            }
        for period in self.periods:
            if period["start"] <= day <= period["end"]:
                return {
                    "key": period.get("type") or "university_event",
                    "name": period.get("name") or "University calendar event",
                    "explains_variation": True,
                }
        return {"key": "normal", "name": None, "explains_variation": False}
