from datetime import date
from math import sqrt
from statistics import median


def _variation(values, centre):
    deviations = [abs(value - centre) for value in values]
    mad = median(deviations)
    robust_sigma = 1.4826 * mad
    return max(2.0, robust_sigma, sqrt(max(centre, 1)))


def detect_anomalies(rows, calendar, minimum_history_days, minimum_samples=6):
    if not rows:
        return {
            "status": "not_assessed",
            "message": "Not assessed: no daily activity is available.",
            "alerts": [],
            "assessed_days": 0,
        }

    prepared = []
    for row in rows:
        day = date.fromisoformat(row["date"])
        prepared.append(
            {
                **row,
                "day": day,
                "context": calendar.describe(day),
            }
        )

    alerts = []
    assessed_days = 0
    skipped_days = 0
    first_day = prepared[0]["day"]
    for index, current in enumerate(prepared):
        history_depth = (current["day"] - first_day).days
        if history_depth < minimum_history_days:
            skipped_days += 1
            continue
        baseline = [
            previous["transactions"]
            for previous in prepared[:index]
            if previous["day"].weekday() == current["day"].weekday()
            and previous["context"]["key"] == current["context"]["key"]
        ]
        if len(baseline) < minimum_samples:
            skipped_days += 1
            continue
        assessed_days += 1
        expected = float(median(baseline))
        variation = _variation(baseline, expected)
        actual = int(current["transactions"])
        high = actual > expected + (3 * variation)
        low = actual < max(0, expected - (3 * variation))
        outage = actual == 0 and expected >= 3
        if not (high or low or outage):
            continue
        if current["context"]["explains_variation"]:
            continue
        direction = "above" if high else "below"
        difference = actual - expected
        alerts.append(
            {
                "date": current["date"],
                "kind": "spike" if high else "outage" if outage else "dip",
                "severity": "high" if abs(difference) >= max(8, expected) else "moderate",
                "actual_transactions": actual,
                "expected_transactions": round(expected, 1),
                "difference": round(difference, 1),
                "calendar_context": current["context"]["name"],
                "message": (
                    f"Transaction activity was {direction} the usual range for a "
                    f"{current['day'].strftime('%A')}. This is unusual activity "
                    "requiring investigation, not evidence of fraud or misuse."
                ),
            }
        )

    status = "ready" if assessed_days else "not_assessed"
    return {
        "status": status,
        "message": (
            "Assessment complete."
            if assessed_days
            else "Not assessed: insufficient comparable history."
        ),
        "alerts": sorted(alerts, key=lambda item: item["date"], reverse=True),
        "assessed_days": assessed_days,
        "not_assessed_days": skipped_days,
    }
