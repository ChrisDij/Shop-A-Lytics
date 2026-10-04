from flask import Blueprint, current_app, jsonify

from ..data.analytics import AnalyticsRepository
from ..data.readiness import assess_dataset
from ..security import current_vendor_id, login_required


meta_blueprint = Blueprint("meta", __name__)


@meta_blueprint.get("/api/meta")
@login_required
def meta():
    repository = AnalyticsRepository(current_app.config["ANALYTICS_DB_PATH"])
    return jsonify(
        assess_dataset(
            repository,
            current_app.config["MIN_HISTORY_DAYS"],
            current_vendor_id(),
        )
    )
