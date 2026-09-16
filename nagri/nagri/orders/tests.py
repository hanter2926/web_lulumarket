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

    def _create_cancellable_order(self, number="ORD-CANCEL-1", status="pending", is_paid=False):
        return Order.objects.create(
            user=self.user,
            order_number=number,
            total_amount=Decimal("100.00"),
            status=status,
            payment_method="razorpay",
            is_paid=is_paid,
        )

    def test_customer_cancel_requires_reason_and_saves_comment(self):
        order = self._create_cancellable_order()
        self.client.force_login(self.user)
        response = self.client.patch(f"/orders/orders/{order.id}/cancel/", data={}, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, "pending")

        response = self.client.patch(
            f"/orders/orders/{order.id}/cancel/",
            data={"reason": "CHANGE_ADDRESS", "comment": "I entered the wrong address."},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.status, "cancelled")
        self.assertEqual(order.cancellation_reason, "CHANGE_ADDRESS")
        self.assertEqual(order.cancellation_comment, "I entered the wrong address.")
        self.assertEqual(order.cancelled_by_id, self.user.id)

    def test_customer_cancel_rejects_invalid_reason_and_long_comment(self):
        order = self._create_cancellable_order(number="ORD-CANCEL-2")
        self.client.force_login(self.user)
        response = self.client.patch(
            f"/orders/orders/{order.id}/cancel/",
            data={"reason": "NOT_A_REASON", "comment": ""},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(
            f"/orders/orders/{order.id}/cancel/",
            data={"reason": "OTHER", "comment": "x" * 501},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, "pending")

    def test_customer_can_cancel_address_mobile_and_other_reasons(self):
        self.client.force_login(self.user)
        for index, reason in enumerate(("CHANGE_ADDRESS", "CHANGE_MOBILE", "OTHER"), start=3):
            order = self._create_cancellable_order(number=f"ORD-CANCEL-{index}")
            response = self.client.patch(
                f"/orders/orders/{order.id}/cancel/",
                data={"reason": reason},
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 200)
            order.refresh_from_db()
            self.assertEqual(order.cancellation_reason, reason)

    def test_cancel_is_owned_authenticated_and_idempotent(self):
        order = self._create_cancellable_order(number="ORD-CANCEL-6", is_paid=True)
        another_user = get_user_model().objects.create_user(username="other", email="other@example.com", password="pass")
        self.client.force_login(another_user)
        response = self.client.patch(
            f"/orders/orders/{order.id}/cancel/",
            data={"reason": "OTHER"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

        self.client.force_login(self.user)
        response = self.client.patch(
            f"/orders/orders/{order.id}/cancel/",
            data={"reason": "OTHER"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        response = self.client.patch(
            f"/orders/orders/{order.id}/cancel/",
            data={"reason": "PAYMENT_ISSUE"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.cancellation_reason, "OTHER")
        self.assertTrue(order.is_paid)

        response = self.client.patch(
            f"/orders/orders/{order.id}/",
            data={"cancellation_reason": "PAYMENT_ISSUE", "cancellation_comment": "tamper"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.cancellation_reason, "OTHER")
        self.assertEqual(order.cancellation_comment, "")

    def test_anonymous_and_non_cancellable_orders_are_rejected(self):
        order = self._create_cancellable_order(number="ORD-CANCEL-7", status="shipped")
        response = self.client.patch(
            f"/orders/orders/{order.id}/cancel/",
            data={"reason": "OTHER"},
            content_type="application/json",
        )
        self.assertIn(response.status_code, (302, 403))
        self.client.force_login(self.user)
        response = self.client.patch(
            f"/orders/orders/{order.id}/cancel/",
            data={"reason": "OTHER"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, "shipped")

    def test_order_pages_expose_cancellation_flow_and_history(self):
        order = self._create_cancellable_order(number="ORD-CANCEL-8")
        self.client.force_login(self.user)
        response = self.client.get(reverse("order_detail", args=[order.id]))
        self.assertContains(response, "Why do you want to cancel this order?")
        self.assertContains(response, "Please select a reason for cancelling your order.")
        self.client.patch(
            f"/orders/orders/{order.id}/cancel/",
            data={"reason": "DELIVERY_DELAY", "comment": "Too slow"},
            content_type="application/json",
        )
        response = self.client.get(reverse("order_detail", args=[order.id]))
        self.assertContains(response, "Order Cancelled")
        self.assertContains(response, "Cancellation reason: Delivery is taking too long")
        self.assertContains(response, "Too slow")
