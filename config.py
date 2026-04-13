import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")

_DEFAULT_SQLITE = "sqlite:///" + os.path.join(BASE_DIR, "instance", "club.db").replace("\\", "/")


def _normalize_database_url(uri: str) -> str:
    """Render/Heroku às vezes enviam postgres://; SQLAlchemy usa postgresql://."""
    if uri.startswith("postgres://"):
        return uri.replace("postgres://", "postgresql://", 1)
    return uri


def _database_uri() -> str:
    raw = os.environ.get("DATABASE_URL")
    if raw:
        return _normalize_database_url(raw.strip())
    return _DEFAULT_SQLITE


def _env_flag(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _url_prefix() -> str:
    """Ex.: /portal — app atende em https://host/portal/... (vazio = raiz)."""
    raw = (os.environ.get("URL_PREFIX") or "").strip()
    if not raw:
        return ""
    if not raw.startswith("/"):
        raw = "/" + raw
    return raw.rstrip("/") or ""


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "troque-esta-chave-em-producao")
    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.path.join(INSTANCE_DIR, "uploads")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
    DEBUG = _env_flag("FLASK_DEBUG", default=False)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_flag("SESSION_COOKIE_SECURE", default=False)
    PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME", "http").strip().lower()
    URL_PREFIX = _url_prefix()
