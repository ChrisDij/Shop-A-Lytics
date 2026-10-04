from flask import Blueprint, current_app, jsonify, request

from ..audit import record_access
from ..data.analytics import AnalyticsRepository, AnalyticsUnavailable
from ..security import current_vendor_id, login_required


search_blueprint = Blueprint("search", __name__)


@search_blueprint.get("/api/search")
@search_blueprint.get("/api/locations")
@login_required
def search_locations():
    vendor_id = current_vendor_id()
    query = request.args.get("q", "")[:120]
    repository = AnalyticsRepository(current_app.config["ANALYTICS_DB_PATH"])
    try:
        results = repository.search_location(vendor_id, query)
    except AnalyticsUnavailable as error:
        return jsonify(error=str(error), results=[]), 503
    record_access("search", "locations", vendor_id, {"query": query})
    return jsonify(query=query, results=results)
