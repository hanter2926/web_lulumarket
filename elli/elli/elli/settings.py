from pathlib import Path
import os
from dotenv import load_dotenv


# =========================================================
# BASE DIRECTORY
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent


# =========================================================
# ENVIRONMENT VARIABLES
# =========================================================

load_dotenv(BASE_DIR / ".env")


# =========================================================
# SECURITY
# =========================================================

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-change-this-in-production"
)

DEBUG = os.environ.get(
    "DEBUG",
    "True"
).lower() == "true"


# =========================================================
# ALLOWED HOSTS
# =========================================================

ALLOWED_HOSTS = os.environ.get(
    "ALLOWED_HOSTS",
    "127.0.0.1,localhost"
).split(",")


# =========================================================
# INSTALLED APPS
# =========================================================

INSTALLED_APPS = [

    # Django Apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third Party Apps
    "rest_framework",
    "corsheaders",

    # Local Apps
    "videos",
    "accounts",
]


# =========================================================
# MIDDLEWARE
# =========================================================

MIDDLEWARE = [

    "django.middleware.security.SecurityMiddleware",

    # WhiteNoise
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",

    # CORS
    "corsheaders.middleware.CorsMiddleware",

    "django.middleware.common.CommonMiddleware",

    "django.middleware.csrf.CsrfViewMiddleware",

    "django.contrib.auth.middleware.AuthenticationMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",

    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# =========================================================
# URL CONFIGURATION
# =========================================================

ROOT_URLCONF = "elli.urls"


# =========================================================
# TEMPLATES
# =========================================================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",

        "DIRS": [
            BASE_DIR / "templates",
        ],

        "APP_DIRS": True,

        "OPTIONS": {
            "context_processors": [

                "django.template.context_processors.request",

                "django.contrib.auth.context_processors.auth",

                "django.contrib.messages.context_processors.messages",

            ],
        },
    },
]


# =========================================================
# WSGI
# =========================================================

WSGI_APPLICATION = "elli.wsgi.application"


# =========================================================
# ASGI
# =========================================================

ASGI_APPLICATION = "elli.asgi.application"


# =========================================================
# DATABASE
# =========================================================

DATABASES = {

    "default": {

        "ENGINE": os.environ.get(
            "DB_ENGINE",
            "django.db.backends.sqlite3"
        ),

        "NAME": os.environ.get(
            "DB_NAME",
            BASE_DIR / "db.sqlite3"
        ),

        "USER": os.environ.get(
            "DB_USER",
            ""
        ),

        "PASSWORD": os.environ.get(
            "DB_PASSWORD",
            ""
        ),

        "HOST": os.environ.get(
            "DB_HOST",
            ""
        ),

        "PORT": os.environ.get(
            "DB_PORT",
            ""
        ),
    }
}


# =========================================================
# PASSWORD VALIDATION
# =========================================================

AUTH_PASSWORD_VALIDATORS = [

    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },

    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },

    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },

    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


# =========================================================
# INTERNATIONALIZATION
# =========================================================

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Kolkata"

USE_I18N = True

USE_TZ = True


# =========================================================
# STATIC FILES
# =========================================================

STATIC_URL = "/static/"

STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]


# =========================================================
# WHITENOISE
# =========================================================

STORAGES = {

    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage."
            "CompressedManifestStaticFilesStorage"
        ),
    },

}


# =========================================================
# MEDIA FILES
# =========================================================

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"


# =========================================================
# FILE UPLOAD SETTINGS
# =========================================================

# Maximum video upload size
DATA_UPLOAD_MAX_MEMORY_SIZE = 500 * 1024 * 1024

FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024


# =========================================================
# DJANGO REST FRAMEWORK
# =========================================================

REST_FRAMEWORK = {

    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],

}


# =========================================================
# CORS SETTINGS
# =========================================================

CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://127.0.0.1:8000,http://localhost:8000"
).split(",")


# =========================================================
# CSRF SETTINGS
# =========================================================

CSRF_TRUSTED_ORIGINS = os.environ.get(
    "CSRF_TRUSTED_ORIGINS",
    ""
).split(",")

CSRF_TRUSTED_ORIGINS = [
    origin for origin in CSRF_TRUSTED_ORIGINS
    if origin
]


# =========================================================
# CELERY SETTINGS
# =========================================================

CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL",
    "redis://127.0.0.1:6379/0"
)

CELERY_RESULT_BACKEND = os.environ.get(
    "CELERY_RESULT_BACKEND",
    "redis://127.0.0.1:6379/0"
)

CELERY_ACCEPT_CONTENT = [
    "json"
]

CELERY_TASK_SERIALIZER = "json"

CELERY_RESULT_SERIALIZER = "json"

CELERY_TIMEZONE = "Asia/Kolkata"


# =========================================================
# OPENAI / AI API
# =========================================================

OPENAI_API_KEY = os.environ.get(
    "OPENAI_API_KEY",
    ""
)


# =========================================================
# VIDEO PROCESSING
# =========================================================

FFMPEG_PATH = os.environ.get(
    "FFMPEG_PATH",
    "ffmpeg"
)


# =========================================================
# WHISPER SETTINGS
# =========================================================

WHISPER_MODEL = os.environ.get(
    "WHISPER_MODEL",
    "small"
)


# =========================================================
# TRANSLATION / TTS PROVIDERS
# =========================================================

TRANSLATION_PROVIDER = os.environ.get(
    "TRANSLATION_PROVIDER",
    "openai"
)

OPENAI_API_KEY = os.environ.get(
    "OPENAI_API_KEY",
    ""
)


TTS_PROVIDER = os.environ.get(
    "TTS_PROVIDER",
    "azure"
)

TTS_API_KEY = os.environ.get(
    "TTS_API_KEY",
    ""
)

TTS_REGION = os.environ.get(
    "TTS_REGION",
    ""
)

TTS_VOICE = os.environ.get(
    "TTS_VOICE",
    "hi-IN-NeerjaNeural"
)

# Max upload size (MB)
MAX_UPLOAD_SIZE_MB = int(os.environ.get('MAX_UPLOAD_SIZE_MB', 500))


# =========================================================
# LOGIN SETTINGS
# =========================================================

LOGIN_URL = "/accounts/login/"

LOGIN_REDIRECT_URL = "/"

LOGOUT_REDIRECT_URL = "/"


# =========================================================
# DEFAULT PRIMARY KEY
# =========================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"