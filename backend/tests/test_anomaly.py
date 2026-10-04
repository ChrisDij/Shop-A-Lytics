from datetime import date, timedelta

from app.services.anomaly import detect_anomalies


class NormalCalendar:
    def describe(self, _day):
        return {"key": "normal", "name": None, "explains_variation": False}


class ExplainedLastDayCalendar:
    def __init__(self, explained_day):
        self.explained_day = explained_day

    def describe(self, day):
        if day == self.explained_day:
            return {
                "key": "normal",
                "name": "University event",
                "explains_variation": True,
            }
        return {"key": "normal", "name": None, "explains_variation": False}


def activity_rows(final_count=40):
    start = date(2026, 1, 1)
    rows = []
    for offset in range(50):
        day = start + timedelta(days=offset)
        rows.append(
            {
                "date": day.isoformat(),
                "transactions": final_count if offset == 49 else 5,
                "students": 5,
                "spend_cents": 5_000,
                "discount_cents": 0,
            }
        )
    return rows


def test_day_under_review_does_not_define_its_own_baseline():
    result = detect_anomalies(
        activity_rows(), NormalCalendar(), minimum_history_days=35
    )

    assert result["alerts"][0]["expected_transactions"] == 5.0
    assert result["alerts"][0]["actual_transactions"] == 40


def test_calendar_explained_activity_is_not_flagged():
    rows = activity_rows()
    final_day = date.fromisoformat(rows[-1]["date"])

    result = detect_anomalies(
        rows,
        ExplainedLastDayCalendar(final_day),
        minimum_history_days=35,
    )

    assert result["alerts"] == []
