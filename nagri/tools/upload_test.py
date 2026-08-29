import os
import sys
from base64 import b64decode
import traceback

# Ensure project root is on sys.path and Django is configured
sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nagri.settings')
import django
django.setup()

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage


print('Starting upload test')

try:
    data = b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=')
    content = ContentFile(data)
    name = 'test_uploads/test.png'
    saved = default_storage.save(name, content)
    print('SAVED_NAME=', saved)
    try:
        url = default_storage.url(saved)
    except Exception as e:
        url = f'ERROR_GETTING_URL: {e}'
    print('URL=', url)
except Exception as e:
    print('ERROR during upload:', e)
    traceback.print_exc()
finally:
    try:
        if 'saved' in locals() and saved:
            default_storage.delete(saved)
            print('DELETED', saved)
    except Exception as e:
        print('ERROR during delete:', e)
        traceback.print_exc()
