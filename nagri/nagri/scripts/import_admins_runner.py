import os, traceback
os.environ.setdefault('DJANGO_SETTINGS_MODULE','nagri.settings')
import django
django.setup()
modules = ['accounts.admin','products.admin','orders.admin','cart.admin','wishlist.admin','unyan.admin']
for m in modules:
    try:
        __import__(m)
        print('OK', m)
    except Exception:
        print('ERR', m)
        traceback.print_exc()
print('DONE')
