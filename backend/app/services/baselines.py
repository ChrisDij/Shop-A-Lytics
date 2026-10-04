from datetime import date
from statistics import mean


def compare_period(rows, start_date, end_date):
    """Compare a period with prior observations on matching weekdays."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    selected = [row for row in rows if start <= date.fromisoformat(row["date"]) <= end]
    weekdays = {date.fromisoformat(row["date"]).weekday() for row in selected}
    baseline = [
        row
        for row in rows
        if date.fromisoformat(row["date"]) < start
        and date.fromisoformat(row["date"]).weekday() in weekdays
    ][-max(len(selected) * 4, 1) :]
    if not selected or not baseline:
        return {
            "status": "not_assessed",
            "message": "Not assessed: insufficient comparable history.",
        }
    observed = mean(row["transactions"] for row in selected)
    expected = mean(row["transactions"] for row in baseline)
    change = ((observed - expected) / expected * 100) if expected else None
    return {
        "status": "ready",
        "observed_average": round(observed, 1),
        "baseline_average": round(expected, 1),
        "observed_change_percent": round(change, 1) if change is not None else None,
        "message": (
            "The selected period was associated with the observed change against "
            "matched historical weekdays. This comparison does not establish causation."
        ),
    }
