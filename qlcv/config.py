import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent


def settings():
    values = {**dotenv_values(ROOT / ".env"), **os.environ}
    names = {
        "PGHOST": "host", "PGPORT": "port", "PGDATABASE": "dbname",
        "PGUSER": "user", "PGPASSWORD": "password", "PGSSLMODE": "sslmode",
        "PGCONNECT_TIMEOUT": "connect_timeout", "PGAPPNAME": "application_name",
    }
    pg = {dest: values[src] for src, dest in names.items() if values.get(src)}
    if not all(pg.get(k) for k in ("host", "dbname", "user", "password")):
        raise RuntimeError("Thiếu cấu hình PostgreSQL trong .env. Xem .env.example.")
    pg.setdefault("connect_timeout", "10")
    instance = ROOT / "instance"
    instance.mkdir(exist_ok=True)
    key = values.get("SECRET_KEY")
    if not key:
        path = instance / "secret_key"
        try:
            with path.open("x", encoding="utf-8") as stream:
                stream.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        key = path.read_text(encoding="utf-8").strip()
    return {
        "SECRET_KEY": key,
        "PG_CONFIG": pg,
        "UPLOAD_FOLDER": str(instance / "uploads"),
        "MAX_CONTENT_LENGTH": 25 * 1024 * 1024,
        "SESSION_COOKIE_HTTPONLY": True,
        "SESSION_COOKIE_SAMESITE": "Lax",
        "SESSION_COOKIE_SECURE": values.get("SESSION_COOKIE_SECURE") == "1",
        "PERMANENT_SESSION_LIFETIME": timedelta(hours=8),
        "WTF_CSRF_TIME_LIMIT": 8 * 60 * 60,
    }
