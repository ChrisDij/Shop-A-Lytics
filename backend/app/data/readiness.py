from datetime import date

from .analytics import AnalyticsUnavailable


def assess_dataset(repository, minimum_history_days, vendor_id=None):
    try:
        summary = repository.dataset_summary()
    except (AnalyticsUnavailable, OSError) as error:
        return {
            "ready": False,
            "status": "not_assessed",
            "message": str(error),
        }
    if not summary["transactions"]:
        return {
            **summary,
            "ready": False,
            "status": "not_assessed",
            "message": "Not assessed: the analytics database contains no transactions.",
        }
    first = date.fromisoformat(summary["first_date"])
    last = date.fromisoformat(summary["last_date"])
    history_days = (last - first).days + 1
    vendor = repository.vendor(vendor_id) if vendor_id else None
    if vendor_id and not vendor:
        return {
            **summary,
            "history_days": history_days,
            "ready": False,
            "status": "not_assessed",
            "message": "Not assessed: the selected vendor is not present in the dataset.",
        }
    ready = history_days >= minimum_history_days
    return {
        **summary,
        "history_days": history_days,
        "ready": ready,
        "status": "ready" if ready else "not_assessed",
        "message": (
            "Dataset is ready for assessment."
            if ready
            else "Not assessed: insufficient history."
        ),
    }
