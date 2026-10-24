from datetime import timedelta
from email.utils import formataddr
import os
from pathlib import Path

from dotenv import load_dotenv

try:
    import dj_database_url
except Exception:
    dj_database_url = None

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

from nagri.common_settings import build_common_settings

globals().update(
    build_common_settings(
        BASE_DIR,
        phase="before_database",
    )
)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if DATABASE_URL:
    if dj_database_url is None:
        raise RuntimeError(
            "Install dj-database-url to use PostgreSQL"
        )

    db_config = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
    )

    if not DEBUG:
        db_config.setdefault("OPTIONS", {})
        db_config["OPTIONS"].setdefault(
            "sslmode", "require"
        )

    DATABASES = {
        "default": db_config
    }

else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

globals().update(
    build_common_settings(
        BASE_DIR,
        phase="after_database",
    )
)
