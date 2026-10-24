import os
import runpy
import sys
from pathlib import Path
from urllib.parse import urlsplit

import dj_database_url
from django.db import connections
from django.db.utils import load_backend
from django.test.runner import DiscoverRunner
from unittest.mock import patch

STAGING_PROJECT_REFERENCE = "gcvwmsrgdpcbmzjvhbww"
STAGING_DB_HOST_ALLOWLIST = {f"db.{STAGING_PROJECT_REFERENCE}.supabase.co"}
STAGING_DB_NAME_ALLOWLIST = {"postgres"}
STAGING_DB_PORT = 5432
TEST_DATABASE_NAME = "nagri_concurrency_test"
TEST_DB_ADVISORY_LOCK_KEY = (1312901714, 1230267731)
STAGING_TEST_DATABASE_URL_ENV = "NAGRI_STAGING_TEST_DATABASE_URL"
STAGING_TEST_OPT_IN_ENV = "NAGRI_ALLOW_STAGING_TEST_DB"
STAGING_TEST_OPT_IN_VALUE = "I_UNDERSTAND_THIS_IS_STAGING_ONLY"
ALLOWED_DATABASE_CONFIG_KEYS = {
    "ENGINE",
    "NAME",
    "USER",
    "PASSWORD",
    "HOST",
    "PORT",
    "CONN_MAX_AGE",
    "CONN_HEALTH_CHECKS",
    "OPTIONS",
}

if len(sys.argv) < 2 or sys.argv[1] != "test":
    raise RuntimeError("postgres_test_settings is only available to the test command.")
if any(argument == "--testrunner" or argument.startswith("--testrunner=") for argument in sys.argv[2:]):
    raise RuntimeError("The PostgreSQL test runner cannot be overridden.")
if any(
    argument in {"--keepdb", "--noinput", "--no-input", "--parallel"}
    or argument.startswith("--parallel=")
    for argument in sys.argv[2:]
):
    raise RuntimeError(
        "Keepdb, non-interactive, and parallel PostgreSQL test runs are not allowed."
    )

if os.environ.get(STAGING_TEST_OPT_IN_ENV) != STAGING_TEST_OPT_IN_VALUE:
    raise RuntimeError("PostgreSQL tests require explicit staging-only opt-in.")

database_url = os.environ.get(STAGING_TEST_DATABASE_URL_ENV, "").strip()
if not database_url:
    raise RuntimeError(
        f"Set {STAGING_TEST_DATABASE_URL_ENV} to the isolated staging connection."
    )
if any(character.isspace() or ord(character) < 32 for character in database_url):
    raise RuntimeError("The staging test database URL is invalid.")

try:
    parsed_url = urlsplit(database_url)
    database_host = (parsed_url.hostname or "").lower()
    database_port = parsed_url.port
except ValueError:
    raise RuntimeError("The staging test database URL is invalid.") from None

if parsed_url.scheme not in {"postgres", "postgresql"}:
    raise RuntimeError("The staging test database must use PostgreSQL.")
if database_host not in STAGING_DB_HOST_ALLOWLIST:
    raise RuntimeError("Database host is not the approved staging project.")
if database_port != STAGING_DB_PORT:
    raise RuntimeError("Database port is not approved for staging tests.")
if parsed_url.path != "/postgres":
    raise RuntimeError("Database name is not the approved staging database.")
if parsed_url.query or parsed_url.fragment:
    raise RuntimeError("URL query parameters and fragments are not allowed.")
if not parsed_url.username or not parsed_url.password:
    raise RuntimeError("Staging database credentials are required.")
if parsed_url.netloc.count("@") != 1:
    raise RuntimeError("The staging database authority is invalid.")

try:
    staging_database = dj_database_url.parse(database_url, conn_max_age=0)
except (TypeError, ValueError):
    raise RuntimeError("The staging test database configuration is invalid.") from None

if set(staging_database) - ALLOWED_DATABASE_CONFIG_KEYS:
    raise RuntimeError("The parsed staging database configuration is unsupported.")
if staging_database.get("ENGINE") != "django.db.backends.postgresql":
    raise RuntimeError("The staging test database must use Django's PostgreSQL backend.")
if staging_database.get("HOST", "").lower() not in STAGING_DB_HOST_ALLOWLIST:
    raise RuntimeError("Parsed database host does not match the approved staging project.")
if staging_database.get("NAME") not in STAGING_DB_NAME_ALLOWLIST:
    raise RuntimeError("Parsed database name does not match the approved staging database.")
if str(staging_database.get("PORT")) != str(STAGING_DB_PORT):
    raise RuntimeError("Parsed database port does not match the approved staging port.")
if not staging_database.get("USER") or not staging_database.get("PASSWORD"):
    raise RuntimeError("Parsed staging database credentials are required.")
if staging_database.get("OPTIONS"):
    raise RuntimeError("Unexpected parsed PostgreSQL connection options are not allowed.")

staging_database["CONN_MAX_AGE"] = 0
staging_database["OPTIONS"] = {
    "sslmode": "require",
    "connect_timeout": 10,
    "options": "-c statement_timeout=30000 -c lock_timeout=20000",
}
staging_database["TEST"] = {"NAME": TEST_DATABASE_NAME}

os.environ["DATABASE_URL"] = ""
_base_settings = runpy.run_path(str(Path(__file__).with_name("settings.py")))

for _setting_name, _setting_value in _base_settings.items():
    if _setting_name.isupper() and not _setting_name.startswith("DATABASE"):
        globals()[_setting_name] = _setting_value

DATABASES = {"default": staging_database}
TEST_RUNNER = "nagri.postgres_test_settings.FailClosedPostgresTestRunner"


class FailClosedPostgresTestRunner(DiscoverRunner):
    def setup_databases(self, *args, **kwargs):
        default_connection = connections["default"]
        configured = default_connection.settings_dict

        if self.keepdb or self.parallel not in (0, 1) or not self.interactive:
            raise RuntimeError(
                "Keepdb, non-interactive, and parallel PostgreSQL test runs are not allowed."
            )
        if default_connection.vendor != "postgresql":
            raise RuntimeError("The concurrency test runner requires PostgreSQL.")
        if configured.get("HOST", "").lower() not in STAGING_DB_HOST_ALLOWLIST:
            raise RuntimeError("The active database host is not the approved staging project.")
        if configured.get("NAME") not in STAGING_DB_NAME_ALLOWLIST:
            raise RuntimeError("The active base database is not approved for staging tests.")
        if configured.get("PORT") != str(STAGING_DB_PORT):
            raise RuntimeError("The active database port is not approved for staging tests.")
        test_settings = configured.get("TEST", {})
        if test_settings.get("NAME") != TEST_DATABASE_NAME or test_settings.get("MIRROR"):
            raise RuntimeError("The disposable test database configuration is invalid.")

        guard_connection = None
        advisory_lock_acquired = False
        setup_result = None
        failure_message = None
        try:
            backend = load_backend(configured["ENGINE"])
            guard_connection = backend.DatabaseWrapper(
                dict(configured),
                alias="nagri_test_database_guard",
            )
            guard_connection.ensure_connection()
            with guard_connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_lock(%s, %s)",
                    TEST_DB_ADVISORY_LOCK_KEY,
                )
            advisory_lock_acquired = True

            with guard_connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_database(), "
                    "EXISTS (SELECT 1 FROM pg_database WHERE datname = %s)",
                    [TEST_DATABASE_NAME],
                )
                active_database, test_database_exists = cursor.fetchone()
            if active_database not in STAGING_DB_NAME_ALLOWLIST:
                failure_message = (
                    "The active PostgreSQL database is not the approved staging base."
                )
            if test_database_exists:
                failure_message = (
                    "The disposable PostgreSQL test database already exists; refusing reuse."
                )
            if failure_message is None:
                try:
                    with patch("builtins.input", return_value="no"):
                        setup_result = super().setup_databases(*args, **kwargs)
                except Exception:
                    failure_message = (
                        "Test database setup failed; inspect the disposable test database "
                        "manually. It was not automatically dropped."
                    )
        except Exception:
            failure_message = (
                "Unable to acquire the staging test guard or verify the PostgreSQL test target."
            )
        finally:
            unlock_failed = False
            if advisory_lock_acquired:
                try:
                    with guard_connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_advisory_unlock(%s, %s)",
                            TEST_DB_ADVISORY_LOCK_KEY,
                        )
                        lock_released = cursor.fetchone()[0]
                    if not lock_released:
                        unlock_failed = True
                except Exception:
                    unlock_failed = True
            try:
                if guard_connection is not None:
                    guard_connection.close()
            except Exception:
                unlock_failed = True
            if unlock_failed:
                raise RuntimeError(
                    "Unable to safely release the PostgreSQL test guard connection."
                ) from None

        if failure_message is not None:
            raise RuntimeError(failure_message) from None
        return setup_result
