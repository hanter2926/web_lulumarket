from nagri.settings import *

# Temporary test settings for local dev server when optional packages
# like cloudinary are not installed. This file is intentionally minimal
# and should NOT be used in production.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

INSTALLED_APPS = [app for app in INSTALLED_APPS if app not in ('cloudinary', 'cloudinary_storage')]

# Use simple staticfiles storage to avoid ManifestStaticFilesStorage requirements
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'

# Ensure debug for local testing
DEBUG = True
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
