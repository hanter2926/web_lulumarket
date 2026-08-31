"""
WSGI config for nagri project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nagri.settings')

# Attempt to run migrations at startup to avoid "no such table" errors
# (controlled by AUTO_RUN_MIGRATIONS env var; default: true)
try:
	run_migrations = os.environ.get('AUTO_RUN_MIGRATIONS', 'true').lower() in ('1', 'true', 'yes')
	if run_migrations:
		# Import here to avoid Django setup before setting DJANGO_SETTINGS_MODULE
		from django.core.management import call_command
		from django.db.utils import OperationalError
		import logging

		logger = logging.getLogger(__name__)
		try:
			# Run migrations non-interactively
			call_command('migrate', '--noinput')
			logger.info('Applied migrations at startup')
		except OperationalError:
			# Database may not be ready; log and continue — WSGI will still start
			logger.exception('OperationalError while running migrations at startup')
		except Exception:
			logger.exception('Unexpected error while running migrations at startup')
except Exception:
	# If anything goes wrong setting up migrations, log via print as fallback
	try:
		import logging
		logging.getLogger(__name__).exception('Failed to initialize startup migration runner')
	except Exception:
		print('Failed to initialize startup migration runner')

application = get_wsgi_application()
