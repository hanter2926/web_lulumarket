import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from decimal import Decimal

from accounts.models import Address
from cart.models import Cart, CartItem
from products.models import Category, Inventory, Product
from .models import Order, UpiPaymentSubmission
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
        self.category = Category.objects.create(name="Order Test Category", slug="order-test-category")

    def _create_product(self, *, slug="order-test-product", price="10.00", stock=10, compare_price="0.00"):
        product = Product.objects.create(
            name="Order Test Product",
            slug=slug,
            category=self.category,
            price=Decimal(price),
            compare_price=Decimal(compare_price),
        )
        inventory = Inventory.objects.get(product=product)
        inventory.stock_quantity = stock
        inventory.save(update_fields=["stock_quantity"])
        return product, inventory

    def _post_order_create(self, data):
        return self.client.post(
            "/orders/orders/create/",
            data,
            content_type="application/json",
        )

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_order_create_rejects_invalid_and_unbounded_quantities(self):
        product, inventory = self._create_product()
        self.client.force_login(self.user)
        original_order_count = Order.objects.count()
        for request_data in (
            {"product_id": product.pk, "quantity": 0},
            {"product_id": product.pk, "quantity": -1},
            {"product_id": product.pk},
            {"product_id": product.pk, "quantity": "many"},
            {"product_id": product.pk, "quantity": 1.5},
            {"product_id": product.pk, "quantity": True},
            {"product_id": product.pk, "quantity": 100},
        ):
            with self.subTest(quantity=request_data.get("quantity", "missing")):
                response = self._post_order_create(request_data)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), original_order_count)
        inventory.refresh_from_db()
        self.assertEqual(inventory.stock_quantity, 10)

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_order_create_accepts_quantity_boundaries_and_uses_server_prices(self):
        product, inventory = self._create_product(
            slug="order-test-boundary",
            price="12.50",
            stock=100,
            compare_price="15.00",
        )
        self.client.force_login(self.user)

        minimum_response = self._post_order_create({
            "product_id": product.pk,
            "quantity": 1,
            "total_amount": "0.01",
            "price": "0.01",
        })
        self.assertEqual(minimum_response.status_code, 200)
        minimum_order = Order.objects.get(pk=minimum_response.json()["order_id"])
        self.assertEqual(minimum_order.total_amount, Decimal("12.50"))
        self.assertEqual(minimum_order.subtotal, Decimal("15.00"))
        self.assertEqual(minimum_order.items.get().price, Decimal("12.50"))
        self.assertTrue(minimum_order.inventory_reserved)

        maximum_response = self._post_order_create({"product_id": product.pk, "quantity": 99})
        self.assertEqual(maximum_response.status_code, 200)
        maximum_order = Order.objects.get(pk=maximum_response.json()["order_id"])
        self.assertEqual(maximum_order.total_amount, Decimal("1237.50"))
        inventory.refresh_from_db()
        self.assertEqual(inventory.stock_quantity, 0)

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_order_create_rejects_unavailable_stock_without_creating_order(self):
        product, inventory = self._create_product(slug="order-test-low-stock", stock=2)
        self.client.force_login(self.user)
        response = self._post_order_create({"product_id": product.pk, "quantity": 3})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        inventory.refresh_from_db()
        self.assertEqual(inventory.stock_quantity, 2)

    @override_settings(RAZORPAY_KEY_ID="test_key", RAZORPAY_KEY_SECRET="test_secret")
    def test_order_create_rolls_back_stock_when_razorpay_order_creation_fails(self):
        product, inventory = self._create_product(slug="order-test-gateway-failure", stock=5)
        self.client.force_login(self.user)
        with patch("orders.views.razorpay.Client") as client:
            client.return_value.order.create.side_effect = RuntimeError("provider unavailable")
            response = self._post_order_create({"product_id": product.pk, "quantity": 2})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(Order.objects.count(), 0)
        inventory.refresh_from_db()
        self.assertEqual(inventory.stock_quantity, 5)

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_cancelling_reserved_order_releases_stock_only_once(self):
        product, inventory = self._create_product(slug="order-test-cancel-stock", stock=3)
        self.client.force_login(self.user)
        response = self._post_order_create({"product_id": product.pk, "quantity": 2})
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(pk=response.json()["order_id"])
        inventory.refresh_from_db()
        self.assertEqual(inventory.stock_quantity, 1)

        cancel_url = f"/orders/orders/{order.pk}/cancel/"
        response = self.client.patch(
            cancel_url,
            {"reason": "OTHER"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        inventory.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(inventory.stock_quantity, 3)
        self.assertFalse(order.inventory_reserved)

        self.client.patch(cancel_url, {"reason": "OTHER"}, content_type="application/json")
        inventory.refresh_from_db()
        self.assertEqual(inventory.stock_quantity, 3)

    def test_active_razorpay_order_cannot_be_cancelled_and_release_stock(self):
        product, inventory = self._create_product(slug="order-test-active-payment", stock=0)
        order = Order.objects.create(
            user=self.user,
            order_number="ORD-ACTIVE-PAYMENT-CANCEL",
            total_amount=Decimal("10.00"),
            status="pending",
            payment_method="razorpay",
            razorpay_order_id="order_active_payment",
            inventory_reserved=True,
        )
        from .models import OrderItem

        OrderItem.objects.create(order=order, product=product, quantity=1, price=product.price)
        self.client.force_login(self.user)

        response = self.client.patch(
            f"/orders/orders/{order.pk}/cancel/",
            {"reason": "OTHER"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        inventory.refresh_from_db()
        self.assertEqual(order.status, "pending")
        self.assertTrue(order.inventory_reserved)
        self.assertEqual(inventory.stock_quantity, 0)

    def test_manual_upi_approval_and_rejection_are_terminal_and_preserve_stock(self):
        from orders.admin import UpiPaymentSubmissionAdmin

        staff_user = get_user_model().objects.create_user(
            username="upi-review-admin", email="upi-review-admin@example.com", password="pass", is_staff=True
        )
        product, inventory = self._create_product(slug="order-test-upi-review", stock=3)

        approved_order = Order.objects.create(
            user=self.user,
            order_number="ORD-UPI-APPROVE-LOCK",
            total_amount=Decimal("10.00"),
            status="pending_verification",
            payment_method="upi",
            payment_provider="manual_upi",
            inventory_reserved=True,
        )
        from .models import OrderItem

        OrderItem.objects.create(
            order=approved_order, product=product, quantity=1, price=product.price
        )
        approved_submission = UpiPaymentSubmission.objects.create(
            order=approved_order,
            upi_id="customer@upi",
            amount=Decimal("10.00"),
        )
        admin_actions = UpiPaymentSubmissionAdmin(UpiPaymentSubmission, admin.site)
        request = SimpleNamespace(user=staff_user)

        admin_actions.approve_submission(
            request,
            UpiPaymentSubmission.objects.filter(pk=approved_submission.pk),
        )
        approved_order.refresh_from_db()
        approved_submission.refresh_from_db()
        self.assertTrue(approved_order.is_paid)
        self.assertEqual(approved_order.status, "paid")
        self.assertFalse(approved_order.inventory_reserved)
        self.assertEqual(approved_submission.status, "approved")

        rejected_order = Order.objects.create(
            user=self.user,
            order_number="ORD-UPI-REJECT-LOCK",
            total_amount=Decimal("10.00"),
            status="pending_verification",
            payment_method="upi",
            payment_provider="manual_upi",
            inventory_reserved=True,
        )
        OrderItem.objects.create(
            order=rejected_order, product=product, quantity=1, price=product.price
        )
        rejected_submission = UpiPaymentSubmission.objects.create(
            order=rejected_order,
            upi_id="customer@upi",
            amount=Decimal("10.00"),
        )
        inventory.stock_quantity = 1
        inventory.save(update_fields=["stock_quantity"])
        admin_actions.reject_submission(
            request,
            UpiPaymentSubmission.objects.filter(pk=rejected_submission.pk),
        )
        rejected_order.refresh_from_db()
        rejected_submission.refresh_from_db()
        inventory.refresh_from_db()
        self.assertFalse(rejected_order.is_paid)
        self.assertFalse(rejected_order.inventory_reserved)
        self.assertEqual(rejected_submission.status, "rejected")
        self.assertEqual(inventory.stock_quantity, 2)

        admin_actions.approve_submission(
            request,
            UpiPaymentSubmission.objects.filter(pk=rejected_submission.pk),
        )
        admin_actions.reject_submission(
            request,
            UpiPaymentSubmission.objects.filter(pk=approved_submission.pk),
        )
        rejected_order.refresh_from_db()
        approved_order.refresh_from_db()
        inventory.refresh_from_db()
        self.assertFalse(rejected_order.is_paid)
        self.assertTrue(approved_order.is_paid)
        self.assertEqual(inventory.stock_quantity, 2)

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_cart_order_create_validates_cart_quantity_and_reserves_stock(self):
        product, inventory = self._create_product(slug="order-test-cart", stock=4)
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=product, quantity=2)
        self.client.force_login(self.user)

        response = self._post_order_create({
            "cart_id": cart.pk,
            "total_amount": "0.01",
            "quantity": 0,
        })
        self.assertEqual(response.status_code, 200)
        order = Order.objects.get(pk=response.json()["order_id"])
        self.assertEqual(order.total_amount, Decimal("20.00"))
        self.assertEqual(order.items.get().quantity, 2)
        inventory.refresh_from_db()
        self.assertEqual(inventory.stock_quantity, 2)

        CartItem.objects.filter(cart=cart, product=product).update(quantity=100)
        response = self._post_order_create({"cart_id": cart.pk})
        self.assertEqual(response.status_code, 400)
        inventory.refresh_from_db()
        self.assertEqual(inventory.stock_quantity, 2)

    def test_checkout_order_uses_current_server_prices_and_preserves_cod_flow(self):
        product, inventory = self._create_product(
            slug="order-test-checkout",
            price="12.50",
            stock=3,
            compare_price="15.00",
        )
        cart = Cart.objects.create(user=self.user)
        CartItem.objects.create(cart=cart, product=product, quantity=2)
        address = Address.objects.create(
            user=self.user,
            full_name="Test Customer",
            phone="1234567890",
            address_line_1="1 Test Road",
            city="Test City",
            state="Test State",
            pincode="12345",
        )
        self.client.force_login(self.user)
        session = self.client.session
        session["checkout_address_id"] = address.pk
        session["checkout_delivery_method"] = "standard"
        session["checkout_payment_method"] = "cod"
        session.save()

        response = self.client.post(reverse("checkout_review"))
        order = Order.objects.get(user=self.user)
        self.assertRedirects(
            response,
            reverse("payment_success", args=[order.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(order.total_amount, Decimal("25.00"))
        self.assertEqual(order.subtotal, Decimal("30.00"))
        self.assertEqual(order.items.get().price, Decimal("12.50"))
        self.assertEqual(order.items.get().quantity, 2)
        self.assertTrue(order.inventory_reserved)
        self.assertFalse(cart.items.exists())
        inventory.refresh_from_db()
        self.assertEqual(inventory.stock_quantity, 1)

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

    def test_customer_order_api_cannot_set_paid_or_paid_status(self):
        order = Order.objects.create(
            user=self.user,
            order_number="ORD-API-PAYMENT-1",
            total_amount=Decimal("100.00"),
            status="pending",
            is_paid=False,
        )
        self.client.force_login(self.user)

        response = self.client.patch(
            f"/orders/orders/{order.id}/",
            data={
                "total_amount": "1.00",
                "razorpay_order_id": "order_tampered",
                "razorpay_payment_id": "pay_tampered",
                "razorpay_signature": "signature_tampered",
                "is_paid": True,
                "status": "paid",
                "tracking_status": "delivered",
                "tracking_code": "TRACK-TAMPERED",
                "payment_provider": "cash",
                "order_number": "ORD-TAMPERED",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.total_amount, Decimal("100.00"))
        self.assertIsNone(order.razorpay_order_id)
        self.assertIsNone(order.razorpay_payment_id)
        self.assertIsNone(order.razorpay_signature)
        self.assertFalse(order.is_paid)
        self.assertEqual(order.status, "pending")
        self.assertEqual(order.tracking_status, "processing")
        self.assertIsNone(order.tracking_code)
        self.assertEqual(order.payment_provider, "razorpay")
        self.assertEqual(order.order_number, "ORD-API-PAYMENT-1")

    def test_anonymous_and_other_customer_cannot_access_order_api(self):
        order = Order.objects.create(
            user=self.user,
            order_number="ORD-API-OWNERSHIP",
            total_amount=Decimal("100.00"),
            status="pending",
        )
        response = self.client.patch(
            f"/orders/orders/{order.id}/",
            data={"status": "paid"},
            content_type="application/json",
        )
        self.assertIn(response.status_code, (401, 403))

        other_user = get_user_model().objects.create_user(
            username="other-order-user", email="other-order@example.com", password=None
        )
        self.client.force_login(other_user)
        response = self.client.patch(
            f"/orders/orders/{order.id}/",
            data={"status": "paid"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)
        order.refresh_from_db()
        self.assertEqual(order.status, "pending")

    def test_staff_order_api_can_update_status_but_not_mark_order_paid(self):
        staff_user = get_user_model().objects.create_user(
            username="order-staff",
            email="order-staff@example.com",
            password="pass",
            is_staff=True,
        )
        order = Order.objects.create(
            user=self.user,
            order_number="ORD-API-PAYMENT-2",
            total_amount=Decimal("100.00"),
            status="pending",
            is_paid=False,
        )
        self.client.force_login(staff_user)

        response = self.client.patch(
            f"/orders/orders/{order.id}/",
            data={
                "total_amount": "1.00",
                "razorpay_order_id": "order_tampered",
                "razorpay_payment_id": "pay_tampered",
                "razorpay_signature": "signature_tampered",
                "is_paid": True,
                "status": "shipped",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.total_amount, Decimal("100.00"))
        self.assertIsNone(order.razorpay_order_id)
        self.assertIsNone(order.razorpay_payment_id)
        self.assertFalse(order.is_paid)
        self.assertEqual(order.status, "shipped")

    def _create_razorpay_order(self, *, order_id="order_server_123", amount=Decimal("100.00")):
        return Order.objects.create(
            user=self.user,
            order_number=f"ORD-{order_id}",
            total_amount=amount,
            status="pending",
            payment_method="razorpay",
            payment_provider="razorpay",
            razorpay_order_id=order_id,
            is_paid=False,
        )

    def _payment_verification_data(self, order, payment_id="pay_server_456"):
        secret = "test_secret"
        signature = hmac.new(
            secret.encode(),
            f"{order.razorpay_order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        return {
            "razorpay_order_id": order.razorpay_order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        }

    @override_settings(RAZORPAY_KEY_ID="test_key", RAZORPAY_KEY_SECRET="test_secret")
    def test_verify_payment_rejects_invalid_signature(self):
        order = self._create_razorpay_order()
        self.client.force_login(self.user)
        data = self._payment_verification_data(order)
        data["razorpay_signature"] = "invalid"
        with patch("orders.views.razorpay.Client") as client:
            response = self.client.post(reverse("verify_payment"), data, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        client.assert_not_called()
        order.refresh_from_db()
        self.assertFalse(order.is_paid)

    @override_settings(RAZORPAY_KEY_ID="test_key", RAZORPAY_KEY_SECRET="test_secret")
    def test_verify_payment_rejects_amount_mismatch(self):
        order = self._create_razorpay_order()
        self.client.force_login(self.user)
        data = self._payment_verification_data(order)
        with patch("orders.views.razorpay.Client") as client:
            client.return_value.payment.fetch.return_value = {
                "id": data["razorpay_payment_id"],
                "order_id": order.razorpay_order_id,
                "amount": 9999,
                "currency": "INR",
                "status": "captured",
            }
            response = self.client.post(reverse("verify_payment"), data, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertFalse(order.is_paid)

    @override_settings(RAZORPAY_KEY_ID="test_key", RAZORPAY_KEY_SECRET="test_secret")
    def test_verify_payment_rejects_altered_payment_id_from_provider(self):
        order = self._create_razorpay_order()
        self.client.force_login(self.user)
        data = self._payment_verification_data(order, payment_id="pay_altered")
        with patch("orders.views.razorpay.Client") as client:
            client.return_value.payment.fetch.return_value = {
                "id": "pay_original",
                "order_id": order.razorpay_order_id,
                "amount": 10000,
                "currency": "INR",
                "status": "captured",
            }
            response = self.client.post(reverse("verify_payment"), data, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertFalse(order.is_paid)

    @override_settings(RAZORPAY_KEY_ID="test_key", RAZORPAY_KEY_SECRET="test_secret")
    def test_verify_payment_rejects_other_customers_order(self):
        order = self._create_razorpay_order()
        other_user = get_user_model().objects.create_user(
            username="other-payment-user", email="other-payment@example.com", password=None
        )
        self.client.force_login(other_user)
        response = self.client.post(
            reverse("verify_payment"),
            self._payment_verification_data(order),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)

    @override_settings(RAZORPAY_KEY_ID="test_key", RAZORPAY_KEY_SECRET="test_secret")
    def test_anonymous_user_cannot_verify_payment(self):
        order = self._create_razorpay_order()
        response = self.client.post(
            reverse("verify_payment"),
            self._payment_verification_data(order),
            content_type="application/json",
        )
        self.assertIn(response.status_code, (401, 403))

    @override_settings(RAZORPAY_KEY_ID="test_key", RAZORPAY_KEY_SECRET="test_secret")
    def test_verify_payment_confirms_captured_amount_in_paise_and_marks_paid(self):
        order = self._create_razorpay_order()
        self.client.force_login(self.user)
        data = self._payment_verification_data(order)
        with patch("orders.views.razorpay.Client") as client:
            client.return_value.payment.fetch.return_value = {
                "id": data["razorpay_payment_id"],
                "order_id": order.razorpay_order_id,
                "amount": 10000,
                "currency": "INR",
                "status": "captured",
            }
            response = self.client.post(reverse("verify_payment"), data, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.status, "paid")
        self.assertEqual(order.razorpay_payment_id, data["razorpay_payment_id"])
        client.return_value.payment.fetch.assert_called_once_with(data["razorpay_payment_id"])

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook_secret")
    def test_payment_webhook_rejects_invalid_signature_and_amount_mismatch(self):
        order = self._create_razorpay_order()
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_webhook_123",
                        "order_id": order.razorpay_order_id,
                        "amount": 9999,
                        "currency": "INR",
                        "status": "captured",
                    }
                }
            },
        }
        raw_payload = json.dumps(payload).encode()
        valid_signature = hmac.new(
            b"webhook_secret", raw_payload, hashlib.sha256
        ).hexdigest()

        invalid_signature_response = self.client.post(
            reverse("payment_webhook"),
            raw_payload,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE="invalid",
        )
        self.assertEqual(invalid_signature_response.status_code, 400)
        valid_signature_response = self.client.post(
            reverse("payment_webhook"),
            raw_payload,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=valid_signature,
        )
        self.assertEqual(valid_signature_response.status_code, 400)
        order.refresh_from_db()
        self.assertFalse(order.is_paid)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="webhook_secret")
    def test_payment_webhook_confirms_valid_captured_payment(self):
        order = self._create_razorpay_order()
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_webhook_valid",
                        "order_id": order.razorpay_order_id,
                        "amount": 10000,
                        "currency": "INR",
                        "status": "captured",
                    }
                }
            },
        }
        raw_payload = json.dumps(payload).encode()
        signature = hmac.new(b"webhook_secret", raw_payload, hashlib.sha256).hexdigest()

        response = self.client.post(
            reverse("payment_webhook"),
            raw_payload,
            content_type="application/json",
            HTTP_X_RAZORPAY_SIGNATURE=signature,
        )
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.razorpay_payment_id, "pay_webhook_valid")

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
