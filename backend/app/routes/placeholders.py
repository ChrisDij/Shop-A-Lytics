from flask import Blueprint, jsonify

placeholder_blueprint = Blueprint("placeholders", __name__)


def not_implemented():
    return jsonify(error="Endpoint owner has not implemented this route yet."), 501


for rule, methods in [
    ("/api/session", ["GET"]),
    ("/api/login", ["POST"]),
    ("/api/register", ["POST"]),
    ("/api/logout", ["POST"]),
    ("/api/password", ["POST"]),
    ("/api/team", ["GET", "POST"]),
    ("/api/locations", ["GET"]),
    ("/api/alerts", ["GET"]),
    ("/api/meta", ["GET"]),
    ("/api/feedback", ["GET", "POST"]),
    ("/api/summary", ["GET"]),
    ("/api/details", ["GET"]),
    ("/api/report", ["GET"]),
]:
    placeholder_blueprint.add_url_rule(
        rule,
        endpoint=f"placeholder_{rule.replace('/', '_')}",
        view_func=not_implemented,
        methods=methods,
    )

