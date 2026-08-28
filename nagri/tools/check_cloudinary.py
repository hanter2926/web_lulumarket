import os
import sys

# Ensure project root is on sys.path
sys.path.insert(0, os.getcwd())

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nagri.settings')

import django

django.setup()

from django.conf import settings

print('DEFAULT_FILE_STORAGE=', getattr(settings, 'DEFAULT_FILE_STORAGE', None))
print('HAS_CLOUDINARY_CONFIG=', getattr(settings, 'HAS_CLOUDINARY_CONFIG', None))
