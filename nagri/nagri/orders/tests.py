import hashlib
import hmac

from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from decimal import Decimal

from .models import Order
from .views import verify_razorpay_signature


class OrderTests(TestCase):
    def test_razorpay_signature_verification(self):
        order_id = "order_test_123"
        payment_id = "pay_test_456"
        secret = "test_secret"
        generated = hmac.new(
            secret.encode(),
            f"{order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()

        self.assertTrue(verify_razorpay_signature(order_id, payment_id, generated, secret))
        self.assertFalse(verify_razorpay_signature(order_id, payment_id, "bad_signature", secret))

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username='testuser', email='test@example.com', password='pass')

    def test_online_order_starts_unpaid_and_payment_page_does_not_mark_paid(self):
        order = Order.objects.create(user=self.user, order_number='ORD-TEST-1', total_amount=Decimal('100.00'), status='pending', payment_method='razorpay', is_paid=False)
        self.client.login(email='test@example.com', password='pass')
        resp = self.client.get(reverse('payment_page', args=[order.id]))
        self.assertEqual(resp.status_code, 200)
        order.refresh_from_db()
        self.assertFalse(order.is_paid)

    def test_cod_shows_order_placed_but_not_paid(self):
        order = Order.objects.create(user=self.user, order_number='ORD-COD-1', total_amount=Decimal('150.00'), status='confirmed', payment_method='cod', is_paid=False)
        self.client.login(email='test@example.com', password='pass')
        resp = self.client.get(reverse('payment_success', args=[order.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Order Successfully Placed')
        self.assertContains(resp, 'Payment will be collected on delivery')
        self.assertContains(resp, 'Paid Amount')
        self.assertContains(resp, '0.00')

    def test_payment_success_view_blocked_for_unpaid(self):
        order = Order.objects.create(user=self.user, order_number='ORD-TEST-2', total_amount=Decimal('50.00'), status='pending', payment_method='razorpay', is_paid=False)
        self.client.login(email='test@example.com', password='pass')
        resp = self.client.get(reverse('payment_success', args=[order.id]))
        # Should redirect back to payment page
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('payment_page', args=[order.id]), resp['Location'])

    @override_settings(RAZORPAY_KEY_ID='', RAZORPAY_KEY_SECRET='')
    def test_payment_page_handles_missing_razorpay_config(self):
        order = Order.objects.create(user=self.user, order_number='ORD-TEST-3', total_amount=Decimal('120.00'), status='pending', payment_method='razorpay', is_paid=False)
        self.client.login(email='test@example.com', password='pass')
        resp = self.client.get(reverse('payment_page', args=[order.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context.get('gateway_error'))

    def test_order_created_unpaid(self):
        order = Order.objects.create(user=self.user, order_number='ORD-T1', total_amount=Decimal('100.00'), status='pending', is_paid=False)
        self.assertFalse(order.is_paid)
        self.assertEqual(order.status, 'pending')

    def test_opening_payment_page_does_not_mark_paid(self):
        order = Order.objects.create(user=self.user, order_number='ORD-T2', total_amount=Decimal('200.00'), status='pending', is_paid=False)
        self.client.login(email='test@example.com', password='pass')
        resp = self.client.get(reverse('payment_page', args=[order.id]))
        order.refresh_from_db()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(order.is_paid)

    def test_payment_success_view_requires_paid(self):
        order = Order.objects.create(user=self.user, order_number='ORD-T3', total_amount=Decimal('300.00'), status='pending', is_paid=False)
        self.client.login(email='test@example.com', password='pass')
        resp = self.client.get(reverse('payment_success', args=[order.id]))
        # Should redirect to payment page
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('payment_page', args=[order.id]), resp.url)
