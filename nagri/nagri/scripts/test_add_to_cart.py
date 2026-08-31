import os
import sys
import django
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nagri.settings')
django.setup()
from django.contrib.auth import get_user_model
from django.test import Client
from products.models import Product
from cart.models import Cart, CartItem
from decimal import Decimal
User = get_user_model()
# Create test user
user, created = User.objects.get_or_create(email='test_addcart@example.com', defaults={'username':'test_addcart'})
if created:
    user.set_password('testpass')
    user.save()
# Use an existing product
product = Product.objects.filter(is_active=True).first()
if not product:
    raise SystemExit('No active product found to test add to cart')
# Create inventory related if needed
c = Client()
c.force_login(user)
resp = c.post('/cart/add/', data='{"product_id": %d, "quantity": 2}' % product.id, content_type='application/json')
print('STATUS', resp.status_code)
print(resp.content)
# Check cart
cart = Cart.objects.filter(user=user).first()
print('CART', cart)
if cart:
    print('ITEMS', list(cart.items.all().values('product_id','quantity')))
