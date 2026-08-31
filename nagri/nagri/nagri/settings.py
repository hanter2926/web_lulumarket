from datetime import timedelta
from pathlib import Path
import os
from dotenv import load_dotenv
#hosting
import dj_database_url

# ============================================================
# BASE DIRECTORY
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")



# ============================================================
# SECURITY
# ============================================================

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-change-this-secret-key"
)

DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

ALLOWED_HOSTS = [
    "web-lulumarket.onrender.com",
    ".onrender.com",
    "127.0.0.1",
    "localhost",
    "testserver",
    "*",
]


# ============================================================
# APPLICATIONS
# ============================================================

INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "nagri",
    "unyan",
    # Real-time / WebSockets
    "channels",
    # CORS
    "corsheaders",
    # API
    "rest_framework",
    "rest_framework_simplejwt",
    # Custom Apps
    "accounts",
    "products.apps.ProductsConfig",
    "orders",
    "cart",
    "wishlist",
    'cloudinary',
    'cloudinary_storage',
]


# ============================================================
# MIDDLEWARE
# ============================================================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "nagri.middleware.AdminSafetyMiddleware",
    # WhiteNoise for Static Files Deployment
    "whitenoise.middleware.WhiteNoiseMiddleware",
    # CORS
    "corsheaders.middleware.CorsMiddleware",

    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# ============================================================
# URL CONFIGURATION
# ============================================================

ROOT_URLCONF = "nagri.urls"


# ============================================================
# TEMPLATES
# ============================================================

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


# ============================================================
# WSGI & ASGI
# ============================================================

WSGI_APPLICATION = "nagri.wsgi.application"

ASGI_APPLICATION = "nagri.asgi.application"


# ============================================================
# DATABASE
# ============================================================

USE_SQLITE = os.environ.get("USE_SQLITE", "True").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# if USE_SQLITE:
#     DATABASES = {
#         "default": {
#             "ENGINE": "django.db.backends.sqlite3",
#             "NAME": BASE_DIR / "db.sqlite3",
#         }
#     }
# else:
# DATABASES = {
#         "default": {
#             "ENGINE": "django.db.backends.mysql",
#             "NAME": os.environ.get("DB_NAME", "unyan"),
#             "USER": os.environ.get("DB_USER", "root"),
#             "PASSWORD": os.environ.get("DB_PASSWORD", "Vikram12345"),
#             "HOST": os.environ.get("DB_HOST", "localhost"),
#             "PORT": os.environ.get("DB_PORT", "3306"),
#         }
# }


DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    # Parse the DATABASE_URL (e.g. postgres://user:pass@host:port/dbname)
    # Use sensible defaults for production: persistent connections and SSL when not in DEBUG
    db_config = dj_database_url.parse(DATABASE_URL, conn_max_age=600)
    # Enforce ssl when not debugging (Render provides SSL-enabled Postgres)
    if not DEBUG:
        # Some engines expect sslmode in OPTIONS
        db_config.setdefault('OPTIONS', {})
        db_config['OPTIONS'].setdefault('sslmode', 'require')
    DATABASES = {
        'default': db_config
    }
else:
    # Local computer SQLite
    
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# ============================================================
# PASSWORD VALIDATION
# ============================================================

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
        "OPTIONS": {
            "min_length": 8,
        },
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


# ============================================================
# LANGUAGE / TIME ZONE
# ============================================================

LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Kolkata"

USE_I18N = True

USE_TZ = True


# ============================================================
# STATIC FILES
# ============================================================

STATIC_URL = "/static/"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATIC_ROOT = BASE_DIR / "staticfiles"

# WhiteNoise storage configuration
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# ============================================================
# MEDIA FILES
# ============================================================

MEDIA_URL = "/media/"

MEDIA_ROOT = BASE_DIR / "media"
# MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


# ============================================================
# DEFAULT PRIMARY KEY
# ============================================================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ============================================================
# LOGIN / LOGOUT
# ============================================================

LOGIN_URL = "login_page"

LOGIN_REDIRECT_URL = "/"

LOGOUT_REDIRECT_URL = "/"

AUTH_USER_MODEL = "accounts.CustomUser"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(days=7),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "AUTH_HEADER_TYPES": ("Bearer",),
}


# ============================================================
# SESSIONS
# ============================================================

SESSION_COOKIE_AGE = 1209600

SESSION_SAVE_EVERY_REQUEST = True




# ============================================================
# MESSAGES
# ============================================================

from django.contrib.messages import constants as message_constants

MESSAGE_TAGS = {
    message_constants.DEBUG: "secondary",
    message_constants.INFO: "info",
    message_constants.SUCCESS: "success",
    message_constants.WARNING: "warning",
    message_constants.ERROR: "danger",
}


# ============================================================
# CORS
# ============================================================

CORS_ALLOW_ALL_ORIGINS = True


# ============================================================
# CHANNEL LAYERS
# ============================================================

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}


# ============================================================
# EMAIL
# ============================================================

# Choose email backend via env. For local development you can set
# EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)

EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() == "true"

EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")

DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER)
# ============================================================
# SECURITY - DEVELOPMENT
# ============================================================

CSRF_COOKIE_SECURE = False

SESSION_COOKIE_SECURE = False


# ============================================================
# LOGGING
# ============================================================

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}


RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")

# Manual UPI configuration for an owner-provided QR/payment id
MANUAL_UPI_ID = os.environ.get("MANUAL_UPI_ID", "")

CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")

# Cloudinary storage configuration: use Cloudinary if all credentials present
CLOUDINARY_STORAGE = {
    'CLOUD_NAME': CLOUDINARY_CLOUD_NAME,
    'API_KEY': CLOUDINARY_API_KEY,
    'API_SECRET': CLOUDINARY_API_SECRET,
}

HAS_CLOUDINARY_CONFIG = all(CLOUDINARY_STORAGE.values())

STORAGES = {
    'default': {
        'BACKEND': (
            'cloudinary_storage.storage.MediaCloudinaryStorage'
            if HAS_CLOUDINARY_CONFIG
            else 'django.core.files.storage.FileSystemStorage'
        ),
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# Use Cloudinary as Django's default file storage when credentials are present
if HAS_CLOUDINARY_CONFIG:
    DEFAULT_FILE_STORAGE = 'cloudinary_storage.storage.MediaCloudinaryStorage'