import os, sys
# Ensure outer project root on sys.path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nagri.settings')
import django
django.setup()

from products.models import Product
from decimal import Decimal

p = Product.objects.first()
if not p:
    raise SystemExit('No Product found in DB to test')

for q in (1, 2):
    try:
        orig_price = p.compare_price if (p.compare_price and p.compare_price > p.price) else p.price
    except Exception:
        orig_price = p.price
    original_subtotal = (orig_price or Decimal(0)) * q
    discounted_subtotal = (p.price or Decimal(0)) * q
    discount_amount = (original_subtotal - discounted_subtotal) if original_subtotal > discounted_subtotal else Decimal(0)
    discount_percent = (discount_amount / original_subtotal * Decimal(100)) if original_subtotal and original_subtotal > 0 else Decimal(0)
    print('Product', p.id, 'price', p.price, 'compare_price', p.compare_price)
    print('Quantity', q)
    print('Original subtotal:', original_subtotal)
    print('Discounted subtotal:', discounted_subtotal)
    print('Discount amount:', discount_amount)
    print('Discount percent:', round(discount_percent,2))
    print('Final payable (no delivery):', discounted_subtotal)
    print('---')
