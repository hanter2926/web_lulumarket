import os
import sys
import django

# Ensure project root is on sys.path so `import nagri.settings` works
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nagri.settings')

django.setup()
from django.template import Template

paths = [
    'nagri/templates/checkout/payment.html',
    'nagri/templates/checkout/order_review.html',
    'nagri/templates/payment/payment.html',
]

errors = []
for p in paths:
    try:
        with open(os.path.join(os.getcwd(), p), 'r', encoding='utf-8') as f:
            s = f.read()
        Template(s)
        print(f"OK: {p}")
    except Exception as e:
        print(f"ERROR: {p} -> {e}")
        errors.append((p, str(e)))

if errors:
    raise SystemExit(1)
