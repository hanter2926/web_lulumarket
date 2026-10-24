import os
from datetime import timedelta
from email.utils import formataddr


def build_common_settings(
    base_dir,
    *,
    include_external_services=True,
    phase="all",
):
    if phase not in {"all", "before_database", "after_database"}:
        raise ValueError("Unknown common settings phase.")

    debug = os.environ.get("DEBUG", "False").lower() == "true"
    site_url = os.environ.get("SITE_URL") or (
        "https://web-lulumarket.onrender.com" if not debug else "http://localhost:8000"
    )
    secret_key = (
        os.environ.get(
            "DJANGO_SECRET_KEY",
            "django-insecure-change-this-secret-key",
        )
        if include_external_services
        else "django-insecure-postgres-concurrency-test-only"
    )

    installed_apps = [
        "django.contrib.admin",
        "django.contrib.auth",
        "django.contrib.contenttypes",
        "django.contrib.sessions",
        "django.contrib.messages",
        "django.contrib.staticfiles",
        "anymail",
        "nagri",
        "unyan",
        "channels",
        "corsheaders",
        "rest_framework",
        "rest_framework_simplejwt",
        "accounts",
        "sellers",
        "products.apps.ProductsConfig",
        "orders",
        "cart",
        "wishlist",
        "rewards",
    ]
    try:
        import cloudinary
        import cloudinary_storage  # noqa: F401

        installed_apps += ["cloudinary", "cloudinary_storage"]
    except Exception:
        pass

    settings = {
        "BASE_DIR": base_dir,
        "SECRET_KEY": secret_key,
        "DEBUG": debug,
        "SITE_URL": site_url,
        "CSRF_TRUSTED_ORIGINS": [site_url.rstrip("/")] if site_url.startswith("https://") else [],
        "SECURE_PROXY_SSL_HEADER": ("HTTP_X_FORWARDED_PROTO", "https"),
        "ALLOWED_HOSTS": [
            "web-lulumarket.onrender.com",
            ".onrender.com",
            "127.0.0.1",
            "localhost",
            "testserver",
            "*",
        ],
        "INSTALLED_APPS": installed_apps,
        "MIDDLEWARE": [
            "django.middleware.security.SecurityMiddleware",
            "nagri.middleware.AdminSafetyMiddleware",
            "whitenoise.middleware.WhiteNoiseMiddleware",
            "corsheaders.middleware.CorsMiddleware",
            "django.contrib.sessions.middleware.SessionMiddleware",
            "django.middleware.common.CommonMiddleware",
            "django.middleware.csrf.CsrfViewMiddleware",
            "django.contrib.auth.middleware.AuthenticationMiddleware",
            "django.contrib.messages.middleware.MessageMiddleware",
            "django.middleware.clickjacking.XFrameOptionsMiddleware",
        ],
        "ROOT_URLCONF": "nagri.urls",
        "TEMPLATES": [
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "DIRS": [base_dir / "templates"],
                "APP_DIRS": True,
                "OPTIONS": {
                    "context_processors": [
                        "django.template.context_processors.request",
                        "django.contrib.auth.context_processors.auth",
                        "django.contrib.messages.context_processors.messages",
                        "products.context_processors.nav_categories",
                    ],
                },
            },
        ],
        "WSGI_APPLICATION": "nagri.wsgi.application",
        "ASGI_APPLICATION": "nagri.asgi.application",
        "AUTH_PASSWORD_VALIDATORS": [
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
                "OPTIONS": {"min_length": 8},
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
        ],
        "LANGUAGE_CODE": "en-us",
        "TIME_ZONE": "Asia/Kolkata",
        "USE_I18N": True,
        "USE_TZ": True,
        "STATIC_URL": "/static/",
        "STATICFILES_DIRS": [base_dir / "static"],
        "STATIC_ROOT": base_dir / "staticfiles",
        "STATICFILES_STORAGE": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        "STORAGES": {},
        "MEDIA_URL": "/media/",
        "MEDIA_ROOT": base_dir / "media",
        "DEFAULT_AUTO_FIELD": "django.db.models.BigAutoField",
        "LOGIN_URL": "accounts:email_login",
        "LOGIN_REDIRECT_URL": "/",
        "LOGOUT_REDIRECT_URL": "/",
        "AUTH_USER_MODEL": "accounts.CustomUser",
        "REST_FRAMEWORK": {
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
        },
        "SIMPLE_JWT": {
            "ACCESS_TOKEN_LIFETIME": timedelta(days=7),
            "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
            "AUTH_HEADER_TYPES": ("Bearer",),
        },
        "SESSION_COOKIE_AGE": 1209600,
        "SESSION_SAVE_EVERY_REQUEST": True,
        "CORS_ALLOW_ALL_ORIGINS": True,
        "CHANNEL_LAYERS": {
            "default": {
                "BACKEND": "channels.layers.InMemoryChannelLayer",
            },
        },
        "CSRF_COOKIE_SECURE": not debug,
        "SESSION_COOKIE_SECURE": not debug,
    }

    early_setting_names = {
        "BASE_DIR",
        "SECRET_KEY",
        "DEBUG",
        "SITE_URL",
        "CSRF_TRUSTED_ORIGINS",
        "SECURE_PROXY_SSL_HEADER",
        "ALLOWED_HOSTS",
        "INSTALLED_APPS",
        "MIDDLEWARE",
        "ROOT_URLCONF",
        "TEMPLATES",
        "WSGI_APPLICATION",
        "ASGI_APPLICATION",
    }
    if phase == "before_database":
        return {
            name: value
            for name, value in settings.items()
            if name in early_setting_names
        }

    from django.contrib.messages import constants as message_constants

    settings["MESSAGE_TAGS"] = {
        message_constants.DEBUG: "secondary",
        message_constants.INFO: "info",
        message_constants.SUCCESS: "success",
        message_constants.WARNING: "warning",
        message_constants.ERROR: "danger",
    }

    import sys

    if any("test" in str(argument) for argument in sys.argv):
        settings["STATICFILES_STORAGE"] = (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
        staticfiles_storage_config = settings["STORAGES"].get("staticfiles") or {}
        staticfiles_storage_config.setdefault(
            "BACKEND",
            "django.contrib.staticfiles.storage.StaticFilesStorage",
        )
        settings["STORAGES"]["staticfiles"] = staticfiles_storage_config
        try:
            from django.contrib.staticfiles.storage import ManifestFilesMixin

            ManifestFilesMixin.manifest_strict = False
        except Exception:
            pass
        try:
            from django.contrib.staticfiles.storage import (
                StaticFilesStorage,
                staticfiles_storage,
            )

            staticfiles_storage._wrapped = StaticFilesStorage()
        except Exception:
            pass

    if include_external_services:
        brevo_api_key = os.getenv("BREVO_API_KEY", "").strip()
        brevo_sender_email = os.getenv("BREVO_SENDER_EMAIL", "").strip()
        brevo_sender_name = os.getenv("BREVO_SENDER_NAME", "NAGRI").strip()
        default_reply_to_email = os.getenv(
            "DEFAULT_REPLY_TO_EMAIL",
            "vikrampal505@yahoo.com",
        ).strip()
        email_backend = (
            "django.core.mail.backends.console.EmailBackend"
            if debug and not brevo_api_key
            else "anymail.backends.brevo.EmailBackend"
        )
        settings.update(
            {
                "EMAIL_PROVIDER": "brevo",
                "BREVO_API_KEY": brevo_api_key,
                "BREVO_SENDER_EMAIL": brevo_sender_email,
                "BREVO_SENDER_NAME": brevo_sender_name,
                "DEFAULT_FROM_EMAIL": (
                    formataddr((brevo_sender_name or "NAGRI", brevo_sender_email))
                    if brevo_sender_email
                    else ""
                ),
                "DEFAULT_REPLY_TO_EMAIL": default_reply_to_email,
                "EMAIL_BACKEND": email_backend,
                "ANYMAIL": {
                    "BREVO_API_KEY": brevo_api_key,
                    "SEND_DEFAULTS": {
                        "reply_to": [default_reply_to_email]
                        if default_reply_to_email
                        else [],
                    },
                },
                "EMAIL_TIMEOUT": 15,
                "TWILIO_ACCOUNT_SID": os.getenv("TWILIO_ACCOUNT_SID", "").strip(),
                "TWILIO_AUTH_TOKEN": os.getenv("TWILIO_AUTH_TOKEN", "").strip(),
                "TWILIO_PHONE_NUMBER": os.getenv("TWILIO_PHONE_NUMBER", "").strip(),
                "RAZORPAY_KEY_ID": os.environ.get("RAZORPAY_KEY_ID", ""),
                "RAZORPAY_KEY_SECRET": os.environ.get("RAZORPAY_KEY_SECRET", ""),
                "MANUAL_UPI_ID": os.environ.get("MANUAL_UPI_ID", ""),
                "CLOUDINARY_CLOUD_NAME": os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
                "CLOUDINARY_API_KEY": os.environ.get("CLOUDINARY_API_KEY", ""),
                "CLOUDINARY_API_SECRET": os.environ.get("CLOUDINARY_API_SECRET", ""),
            }
        )
        cloudinary_storage_config = {
            "CLOUD_NAME": settings["CLOUDINARY_CLOUD_NAME"],
            "API_KEY": settings["CLOUDINARY_API_KEY"],
            "API_SECRET": settings["CLOUDINARY_API_SECRET"],
        }
        try:
            import cloudinary
            import cloudinary_storage  # noqa: F401

            cloudinary_available = True
        except Exception:
            cloudinary_available = False
        has_cloudinary_config = (
            all(cloudinary_storage_config.values()) and cloudinary_available
        )
        settings.update(
            {
                "CLOUDINARY_STORAGE": cloudinary_storage_config,
                "CLOUDINARY_AVAILABLE": cloudinary_available,
                "HAS_CLOUDINARY_CONFIG": has_cloudinary_config,
                "STORAGES": {
                    "default": {
                        "BACKEND": (
                            "cloudinary_storage.storage.MediaCloudinaryStorage"
                            if has_cloudinary_config
                            else "django.core.files.storage.FileSystemStorage"
                        ),
                    },
                    "staticfiles": {
                        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
                    },
                },
                "DEFAULT_FILE_STORAGE": (
                    "cloudinary_storage.storage.MediaCloudinaryStorage"
                    if has_cloudinary_config
                    else "django.core.files.storage.FileSystemStorage"
                ),
            }
        )
        import logging

        logger = logging.getLogger(__name__)
        logger.info(
            "Email configuration loaded: provider=%s backend=%s api_key_configured=%s "
            "sender_configured=%s",
            settings["EMAIL_PROVIDER"],
            settings["EMAIL_BACKEND"],
            bool(settings["BREVO_API_KEY"]),
            bool(settings["BREVO_SENDER_EMAIL"]),
        )
        try:
            logger.info(
                "Twilio configuration presence: "
                "account_sid_present=%s auth_token_present=%s phone_number_present=%s",
                bool(settings["TWILIO_ACCOUNT_SID"]),
                bool(settings["TWILIO_AUTH_TOKEN"]),
                bool(settings["TWILIO_PHONE_NUMBER"]),
            )
        except Exception:
            logger.exception("Error while logging Twilio configuration presence")
    else:
        settings.update(
            {
                "EMAIL_PROVIDER": "test",
                "BREVO_API_KEY": "",
                "BREVO_SENDER_EMAIL": "",
                "BREVO_SENDER_NAME": "NAGRI",
                "DEFAULT_FROM_EMAIL": "",
                "DEFAULT_REPLY_TO_EMAIL": "",
                "EMAIL_BACKEND": "django.core.mail.backends.console.EmailBackend",
                "ANYMAIL": {"BREVO_API_KEY": "", "SEND_DEFAULTS": {"reply_to": []}},
                "EMAIL_TIMEOUT": 15,
                "TWILIO_ACCOUNT_SID": "",
                "TWILIO_AUTH_TOKEN": "",
                "TWILIO_PHONE_NUMBER": "",
                "RAZORPAY_KEY_ID": "",
                "RAZORPAY_KEY_SECRET": "",
                "MANUAL_UPI_ID": "",
                "CLOUDINARY_CLOUD_NAME": "",
                "CLOUDINARY_API_KEY": "",
                "CLOUDINARY_API_SECRET": "",
                "CLOUDINARY_STORAGE": {
                    "CLOUD_NAME": "",
                    "API_KEY": "",
                    "API_SECRET": "",
                },
                "CLOUDINARY_AVAILABLE": False,
                "HAS_CLOUDINARY_CONFIG": False,
                "STORAGES": {
                    "default": {
                        "BACKEND": "django.core.files.storage.FileSystemStorage",
                    },
                    "staticfiles": {
                        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
                    },
                },
                "DEFAULT_FILE_STORAGE": "django.core.files.storage.FileSystemStorage",
            }
        )

    if any("test" in str(argument) for argument in sys.argv):
        settings["STATICFILES_STORAGE"] = (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
        settings["STORAGES"]["staticfiles"] = {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        }
        if include_external_services and settings["HAS_CLOUDINARY_CONFIG"]:
            settings["STORAGES"]["default"] = {
                "BACKEND": "django.core.files.storage.FileSystemStorage",
            }
            settings["DEFAULT_FILE_STORAGE"] = (
                "django.core.files.storage.FileSystemStorage"
            )

    if phase == "after_database":
        return {
            name: value
            for name, value in settings.items()
            if name not in early_setting_names
        }
    return settings
