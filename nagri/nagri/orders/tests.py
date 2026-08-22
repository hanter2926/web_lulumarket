import hashlib
import hmac

from django.test import TestCase

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
