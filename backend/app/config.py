import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_local_env():
    """Load simple KEY=VALUE entries without adding another dependency."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _path_from_env(name, default):
    path = Path(os.environ.get(name, default)).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def _application_database_uri():
    configured = os.environ.get("DATABASE_URL")
    if configured and not configured.startswith("sqlite:///"):
        return configured
    relative = configured.removeprefix("sqlite:///") if configured else "data/app.sqlite"
    path = Path(relative).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{path}"


def build_config():
    _load_local_env()
    return {
        "DEBUG": os.environ.get("FLASK_DEBUG", "0") == "1",
        "SECRET_KEY": os.environ.get("SECRET_KEY", "local-development-only"),
        "SQLALCHEMY_DATABASE_URI": _application_database_uri(),
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
        "ANALYTICS_DB_PATH": str(
            _path_from_env("ANALYTICS_DB_PATH", "data/analytics.sqlite")
        ),
        "PUBLIC_HOLIDAYS_PATH": str(
            _path_from_env(
                "PUBLIC_HOLIDAYS_PATH",
                "data/reference/public_holidays/public_holidays.csv",
            )
        ),
        "UNIVERSITY_CALENDAR_PATH": str(
            _path_from_env(
                "UNIVERSITY_CALENDAR_PATH",
                "data/reference/university_calendar/university_calendar.csv",
            )
        ),
        "MIN_GROUP_SIZE": int(os.environ.get("MIN_GROUP_SIZE", "10")),
        "MIN_HISTORY_DAYS": int(os.environ.get("MIN_HISTORY_DAYS", "90")),
        "DEMO_VENDOR_ID": int(os.environ["DEMO_VENDOR_ID"])
        if os.environ.get("DEMO_VENDOR_ID")
        else None,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
    }
