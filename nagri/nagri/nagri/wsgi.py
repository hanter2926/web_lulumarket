"""
WSGI config for nagri project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nagri.settings')

# WSGI application should only configure settings and expose the application callable.
# Do NOT run migrations or any management commands during WSGI import/startup —
# running migrations at import time causes AppRegistryNotReady errors and unexpected
# side effects in production. Any automatic migration logic was removed per request.
application = get_wsgi_application()
