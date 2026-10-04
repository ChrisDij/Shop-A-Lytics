from flask import Blueprint, current_app, jsonify, request

from ..audit import record_access
from ..data.analytics import AnalyticsRepository
from ..data.calendar import CalendarContext
from ..data.readiness import assess_dataset
from ..security import current_vendor_id, login_required
from ..services.anomaly import detect_anomalies


alerts_blueprint = Blueprint("alerts", __name__)


@alerts_blueprint.get("/api/alerts")
@login_required
def alerts():
    vendor_id = current_vendor_id()
    repository = AnalyticsRepository(current_app.config["ANALYTICS_DB_PATH"])
    readiness = assess_dataset(
        repository, current_app.config["MIN_HISTORY_DAYS"], vendor_id
    )
    if not readiness["ready"]:
        return jsonify({**readiness, "alerts": []})
    calendar = CalendarContext(
        current_app.config["PUBLIC_HOLIDAYS_PATH"],
        current_app.config["UNIVERSITY_CALENDAR_PATH"],
    )
    result = detect_anomalies(
        repository.daily_activity(vendor_id),
        calendar,
        current_app.config["MIN_HISTORY_DAYS"],
    )
    requested_limit = request.args.get("limit", default=50, type=int)
    limit = min(max(requested_limit or 50, 1), 200)
    result["alerts"] = result["alerts"][:limit]
    result["vendor"] = repository.vendor(vendor_id)
    result["readiness"] = readiness
    record_access("view", "alerts", vendor_id, {"limit": limit})
    return jsonify(result)
