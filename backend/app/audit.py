import json

from flask import current_app, session

from .extensions import db
from .models import AuditLog


def record_access(action, resource, vendor_id, details=None):
    if current_app.config.get("TESTING"):
        return
    entry = AuditLog(
        user_id=session.get("user_id"),
        vendor_id=vendor_id,
        action=action,
        resource=resource,
        details=json.dumps(details, sort_keys=True) if details else None,
    )
    db.session.add(entry)
    db.session.commit()
