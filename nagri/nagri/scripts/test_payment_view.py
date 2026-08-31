import os
import sys
import django
# Ensure project root is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
INNER = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if INNER not in sys.path:
    sys.path.insert(0, INNER)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nagri.settings')
django.setup()
from django.contrib.auth import get_user_model
from orders.models import Order
from decimal import Decimal
from django.test import Client

User = get_user_model()
user, created = User.objects.get_or_create(email='test_payment@example.com', defaults={'username':'test_payment','password':'testpass'})
if created:
    user.set_password('testpass')
    user.save()

# create order
order, created = Order.objects.get_or_create(order_number='TEST-PAY-1', defaults={
    'user': user,
    'subtotal': Decimal('100.00'),
    'discount_amount': Decimal('0.00'),
    'delivery_charge': Decimal('0.00'),
    'total_amount': Decimal('100.00'),
    'delivery_method': 'standard',
    'payment_method': 'razorpay',
    'status': 'pending',
    'is_paid': False,
})

c = Client()
c.force_login(user)
resp = c.get(f'/orders/payment/{order.id}/')
print('STATUS', resp.status_code)
if resp.status_code != 200:
    print(resp.content.decode('utf-8')[:2000])
else:
    print('OK')
