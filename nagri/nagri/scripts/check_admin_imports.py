modules = ['accounts.admin','products.admin','orders.admin','cart.admin','wishlist.admin','unyan.admin']
import importlib, traceback
for m in modules:
    try:
        importlib.import_module(m)
        print('OK', m)
    except Exception:
        print('ERR', m)
        traceback.print_exc()
print('DONE')
