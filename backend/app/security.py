from functools import wraps

from flask import current_app, jsonify, session
from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(password):
    return generate_password_hash(password)


def verify_password(password_hash, password):
    return check_password_hash(password_hash, password)


def current_vendor_id():
    return session.get("vendor_id") or current_app.config.get("DEMO_VENDOR_ID")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id") and not current_app.config.get("DEMO_VENDOR_ID"):
            return jsonify(error="Authentication is required."), 401
        if current_vendor_id() is None:
            return jsonify(error="No vendor is assigned to this account."), 403
        return view(*args, **kwargs)

    return wrapped


def owner_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "owner":
            return jsonify(error="Owner access is required."), 403
        return view(*args, **kwargs)

    return wrapped
