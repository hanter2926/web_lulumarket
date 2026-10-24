import hashlib
import hmac
import json
import threading
import time
from queue import Queue
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, connections
from django.test import Client, TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import Address
from cart.models import Cart, CartItem
from orders.admin import UpiPaymentSubmissionAdmin
from orders.models import Order, OrderItem, UpiPaymentSubmission
from products.models import Category, Inventory, Product


class OrderConcurrencyTests(TransactionTestCase):
    reset_sequences = True
    lock_wait_timeout = 15
    observer_timeout = 10
    worker_cleanup_timeout = 45

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if connection.vendor != "postgresql":
            raise RuntimeError(
                "OrderConcurrencyTests must run with postgres_test_settings."
            )

    def setUp(self):
        user_model = get_user_model()
        self.customer = user_model.objects.create_user(
            username="concurrency-customer",
            email="concurrency-customer@example.com",
            password="test-password",
        )
        self.second_customer = user_model.objects.create_user(
            username="concurrency-second",
            email="concurrency-second@example.com",
            password="test-password",
        )
        self.staff = user_model.objects.create_user(
            username="concurrency-staff",
            email="concurrency-staff@example.com",
            password="test-password",
            is_staff=True,
        )
        self.category = Category.objects.create(
            name="Concurrency Test Category",
            slug="concurrency-test-category",
        )

    def _create_product(self, *, slug, stock):
        product = Product.objects.create(
            name="Concurrency Test Product",
            slug=slug,
            category=self.category,
            price="10.00",
        )
        inventory = Inventory.objects.get(product=product)
        inventory.stock_quantity = stock
        inventory.save(update_fields=["stock_quantity"])
        return product, inventory

    def _create_order(self, *, order_number, product, user=None, **overrides):
        fields = {
            "user": user or self.customer,
            "order_number": order_number,
            "total_amount": "10.00",
            "status": "pending",
            "payment_method": "razorpay",
            "payment_provider": "razorpay",
            "inventory_reserved": True,
        }
        fields.update(overrides)
        order = Order.objects.create(**fields)
        OrderItem.objects.create(
            order=order,
            product=product,
            quantity=1,
            price=product.price,
        )
        return order

    def _api_client(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _run_lock_contention(self, first_operation, second_operation, table_name):
        first_lock_acquired = threading.Event()
        second_lock_attempting = threading.Event()
        release_first = threading.Event()
        backend_pids = Queue()
        outcomes = Queue()

        def run_operation(role, operation):
            outcome = None
            try:
                close_old_connections()
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_backend_pid()")
                    backend_pids.put((role, cursor.fetchone()[0]))

                def observe_lock(execute, sql, params, many, context):
                    normalized_sql = " ".join(sql.lower().split())
                    if "for update" not in normalized_sql or table_name not in normalized_sql:
                        return execute(sql, params, many, context)

                    if role == "first" and not first_lock_acquired.is_set():
                        result = execute(sql, params, many, context)
                        first_lock_acquired.set()
                        if not release_first.wait(self.lock_wait_timeout):
                            raise RuntimeError("Timed out holding the first PostgreSQL row lock.")
                        return result

                    if role == "second" and not second_lock_attempting.is_set():
                        second_lock_attempting.set()
                    return execute(sql, params, many, context)

                with connection.execute_wrapper(observe_lock):
                    outcome = (True, operation())
            except BaseException as error:
                outcome = (False, error)
            finally:
                try:
                    connections["default"].close()
                except BaseException as error:
                    outcome = (False, error)
                try:
                    close_old_connections()
                except BaseException as error:
                    outcome = (False, error)
                outcomes.put((role, outcome))

        workers = []
        cleanup_exceeded_bound = False
        try:
            first_worker = threading.Thread(
                target=run_operation,
                args=("first", first_operation),
                name="nagri-order-concurrency-first",
            )
            first_worker.start()
            workers.append(first_worker)
            self.assertTrue(
                first_lock_acquired.wait(self.lock_wait_timeout),
                f"First operation did not acquire a FOR UPDATE lock on {table_name}.",
            )
            second_worker = threading.Thread(
                target=run_operation,
                args=("second", second_operation),
                name="nagri-order-concurrency-second",
            )
            second_worker.start()
            workers.append(second_worker)
            self.assertTrue(
                second_lock_attempting.wait(self.lock_wait_timeout),
                f"Second operation did not reach a FOR UPDATE lock on {table_name}.",
            )

            pids = dict(backend_pids.get(timeout=self.lock_wait_timeout) for _ in range(2))
            self.assertNotEqual(
                pids["first"],
                pids["second"],
                "Concurrent operations must use independent PostgreSQL connections.",
            )

            deadline = time.monotonic() + self.observer_timeout
            blocked_by_first = False
            while time.monotonic() < deadline:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_blocking_pids(%s)", [pids["second"]])
                    blockers = cursor.fetchone()[0]
                if pids["first"] in blockers:
                    blocked_by_first = True
                    break
                threading.Event().wait(0.01)

            self.assertTrue(
                blocked_by_first,
                "PostgreSQL did not report the second operation blocked by the first lock holder.",
            )
        finally:
            release_first.set()
            cleanup_deadline = time.monotonic() + self.worker_cleanup_timeout
            for worker in workers:
                worker.join(max(0, cleanup_deadline - time.monotonic()))
            active_workers = [worker for worker in workers if worker.is_alive()]
            if active_workers:
                cleanup_exceeded_bound = True
                for worker in active_workers:
                    worker.join()

        if cleanup_exceeded_bound:
            raise RuntimeError(
                "A worker exceeded the cleanup bound. It was joined before test teardown; "
                "Python threads cannot be safely force-stopped."
            )

        worker_outcomes = dict(outcomes.get_nowait() for _ in workers)
        results = []
        for role in ("first", "second"):
            if role not in worker_outcomes:
                continue
            succeeded, result = worker_outcomes[role]
            if not succeeded:
                raise result
            results.append(result)
        return tuple(results)

    def _checkout_client(self, user, address):
        client = Client()
        client.force_login(user)
        session = client.session
        session["checkout_address_id"] = address.pk
        session["checkout_delivery_method"] = "standard"
        session["checkout_payment_method"] = "cod"
        session.save()
        return client

    def _checkout_operation(self, user, address):
        return lambda: self._checkout_client(user, address).post(
            reverse("checkout_review")
        )

    @override_settings(RAZORPAY_KEY_ID="", RAZORPAY_KEY_SECRET="")
    def test_concurrent_api_reservations_cannot_oversell_last_unit(self):
        product, inventory = self._create_product(
            slug="concurrency-api-last-unit",
            stock=1,
        )
        url = "/orders/orders/create/"

        with patch("orders.views.razorpay_is_configured", return_value=False):
            responses = self._run_lock_contention(
                lambda: self._api_client(self.customer).post(
                    url,
                    {"product_id": product.pk, "quantity": 1},
                    format="json",
                ),
                lambda: self._api_client(self.second_customer).post(
                    url,
                    {"product_id": product.pk, "quantity": 1},
                    format="json",
                ),
                "products_product",
            )

        self.assertEqual(sorted(response.status_code for response in responses), [200, 400])
        self.assertEqual(
            sum(response.status_code == 200 for response in responses),
            1,
        )
        self.assertTrue(
            any(
                response.status_code == 400
                and "Insufficient stock" in response.json().get("detail", "")
                for response in responses
            )
        )
        inventory.refresh_from_db()
        self.assertEqual(inventory.stock_quantity, 0)
        self.assertGreaterEqual(inventory.stock_quantity, 0)
        self.assertEqual(
            Order.objects.filter(items__product=product).distinct().count(),
            1,
        )

    def test_concurrent_checkout_distinguishes_success_from_insufficient_stock(self):
        product, inventory = self._create_product(
            slug="concurrency-checkout-last-unit",
            stock=1,
        )
        addresses = []
        for user, suffix in (
            (self.customer, "one"),
            (self.second_customer, "two"),
        ):
            address = Address.objects.create(
                user=user,
                full_name=f"Customer {suffix}",
                phone="1234567890",
                address_line_1="1 Test Road",
                city="Test City",
                state="Test State",
                pincode="12345",
            )
            cart, _ = Cart.objects.get_or_create(user=user)
            CartItem.objects.create(cart=cart, product=product, quantity=1)
            addresses.append((user, address))

        first_response, second_response = self._run_lock_contention(
            self._checkout_operation(*addresses[0]),
            self._checkout_operation(*addresses[1]),
            "products_product",
        )

        orders = list(
            Order.objects.filter(items__product=product)
            .distinct()
            .prefetch_related("items")
        )
        self.assertEqual(len(orders), 1)
        success_location = reverse("payment_success", args=[orders[0].pk])
        insufficient_stock_location = reverse("checkout_review")
        locations = [first_response["Location"], second_response["Location"]]
        self.assertEqual(locations.count(success_location), 1)
        self.assertEqual(locations.count(insufficient_stock_location), 1)
        self.assertTrue(all(response.status_code == 302 for response in (first_response, second_response)))
        self.assertEqual(orders[0].payment_method, "cod")
        inventory.refresh_from_db()
        self.assertEqual(inventory.stock_quantity, 0)
        self.assertGreaterEqual(inventory.stock_quantity, 0)

    def test_concurrent_duplicate_cancellation_releases_stock_once(self):
        product, inventory = self._create_product(
            slug="concurrency-cancel-release",
            stock=0,
        )
        order = self._create_order(
            order_number="ORD-CONCURRENT-CANCEL",
            product=product,
            payment_method="cod",
        )
        url = f"/orders/orders/{order.pk}/cancel/"

        first_response, second_response = self._run_lock_contention(
            lambda: self._api_client(self.customer).patch(
                url,
                {"reason": "OTHER"},
                format="json",
            ),
            lambda: self._api_client(self.customer).patch(
                url,
                {"reason": "OTHER"},
                format="json",
            ),
            "orders_order",
        )

        self.assertEqual([first_response.status_code, second_response.status_code], [200, 200])
        order.refresh_from_db()
        inventory.refresh_from_db()
        self.assertEqual(order.status, "cancelled")
        self.assertFalse(order.inventory_reserved)
        self.assertEqual(inventory.stock_quantity, 1)

    def test_active_razorpay_order_cancellation_guard_preserves_reservation(self):
        product, inventory = self._create_product(
            slug="concurrency-cancel-payment-guard",
            stock=0,
        )
        order = self._create_order(
            order_number="ORD-ACTIVE-PAYMENT-GUARD",
            product=product,
            razorpay_order_id="order_active_payment_guard",
        )

        response = self._api_client(self.customer).patch(
            f"/orders/orders/{order.pk}/cancel/",
            {"reason": "OTHER"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        inventory.refresh_from_db()
        self.assertEqual(order.status, "pending")
        self.assertFalse(order.is_paid)
        self.assertTrue(order.inventory_reserved)
        self.assertEqual(inventory.stock_quantity, 0)

    @override_settings(RAZORPAY_KEY_ID="test_key", RAZORPAY_KEY_SECRET="test_secret")
    def test_payment_confirmation_serializes_before_active_payment_cancellation(self):
        product, inventory = self._create_product(
            slug="concurrency-payment-cancel-policy",
            stock=0,
        )
        payment_order_id = "order_concurrent_payment"
        payment_id = "pay_concurrent_payment"
        order = self._create_order(
            order_number="ORD-CONCURRENT-PAYMENT-CANCEL",
            product=product,
            razorpay_order_id=payment_order_id,
        )
        signature = hmac.new(
            b"test_secret",
            f"{payment_order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        verification_data = {
            "razorpay_order_id": payment_order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        }
        cancel_url = f"/orders/orders/{order.pk}/cancel/"

        with patch("orders.views.razorpay.Client") as razorpay_client:
            razorpay_client.return_value.payment.fetch.return_value = {
                "id": payment_id,
                "order_id": payment_order_id,
                "amount": 1000,
                "currency": "INR",
                "status": "captured",
            }
            payment_response, cancellation_response = self._run_lock_contention(
                lambda: self._api_client(self.customer).post(
                    reverse("verify_payment"),
                    verification_data,
                    format="json",
                ),
                lambda: self._api_client(self.customer).patch(
                    cancel_url,
                    {"reason": "OTHER"},
                    format="json",
                ),
                "orders_order",
            )

        self.assertEqual(payment_response.status_code, 200)
        self.assertEqual(cancellation_response.status_code, 400)
        order.refresh_from_db()
        inventory.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.status, "paid")
        self.assertFalse(order.inventory_reserved)
        self.assertEqual(inventory.stock_quantity, 0)

    @override_settings(RAZORPAY_KEY_ID="test_key", RAZORPAY_KEY_SECRET="test_secret")
    def test_duplicate_payment_verification_is_serialized_and_idempotent(self):
        product, inventory = self._create_product(
            slug="concurrency-duplicate-verification",
            stock=0,
        )
        payment_order_id = "order_duplicate_verification"
        payment_id = "pay_duplicate_verification"
        order = self._create_order(
            order_number="ORD-DUPLICATE-VERIFICATION",
            product=product,
            razorpay_order_id=payment_order_id,
        )
        signature = hmac.new(
            b"test_secret",
            f"{payment_order_id}|{payment_id}".encode(),
            hashlib.sha256,
        ).hexdigest()
        data = {
            "razorpay_order_id": payment_order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature,
        }

        with patch("orders.views.razorpay.Client") as razorpay_client:
            razorpay_client.return_value.payment.fetch.return_value = {
                "id": payment_id,
                "order_id": payment_order_id,
                "amount": 1000,
                "currency": "INR",
                "status": "captured",
            }
            first_response, second_response = self._run_lock_contention(
                lambda: self._api_client(self.customer).post(
                    reverse("verify_payment"),
                    data,
                    format="json",
                ),
                lambda: self._api_client(self.customer).post(
                    reverse("verify_payment"),
                    data,
                    format="json",
                ),
                "orders_order",
            )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        razorpay_client.return_value.payment.fetch.assert_called_once_with(payment_id)
        order.refresh_from_db()
        inventory.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.status, "paid")
        self.assertEqual(order.razorpay_payment_id, payment_id)
        self.assertFalse(order.inventory_reserved)
        self.assertEqual(inventory.stock_quantity, 0)

    @override_settings(RAZORPAY_WEBHOOK_SECRET="concurrency-webhook-secret")
    def test_duplicate_payment_webhooks_are_serialized_and_idempotent(self):
        product, inventory = self._create_product(
            slug="concurrency-duplicate-webhook",
            stock=0,
        )
        payment_order_id = "order_duplicate_webhook"
        payment_id = "pay_duplicate_webhook"
        order = self._create_order(
            order_number="ORD-DUPLICATE-WEBHOOK",
            product=product,
            razorpay_order_id=payment_order_id,
        )
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": payment_order_id,
                        "amount": 1000,
                        "currency": "INR",
                        "status": "captured",
                    }
                }
            },
        }
        raw_payload = json.dumps(payload).encode()
        signature = hmac.new(
            b"concurrency-webhook-secret",
            raw_payload,
            hashlib.sha256,
        ).hexdigest()

        def post_webhook():
            return Client().post(
                reverse("payment_webhook"),
                raw_payload,
                content_type="application/json",
                HTTP_X_RAZORPAY_SIGNATURE=signature,
            )

        first_response, second_response = self._run_lock_contention(
            post_webhook,
            post_webhook,
            "orders_order",
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        order.refresh_from_db()
        inventory.refresh_from_db()
        self.assertTrue(order.is_paid)
        self.assertEqual(order.status, "paid")
        self.assertEqual(order.razorpay_payment_id, payment_id)
        self.assertFalse(order.inventory_reserved)
        self.assertEqual(inventory.stock_quantity, 0)

    def _run_upi_review_contention(self, *, first_action, second_action, suffix):
        product, inventory = self._create_product(
            slug=f"concurrency-upi-{suffix}",
            stock=0,
        )
        order = self._create_order(
            order_number=f"ORD-CONCURRENT-UPI-{suffix.upper()}",
            product=product,
            payment_method="upi",
            payment_provider="manual_upi",
            status="pending_verification",
        )
        submission = UpiPaymentSubmission.objects.create(
            order=order,
            upi_id="customer@upi",
            amount=order.total_amount,
        )
        actions = UpiPaymentSubmissionAdmin(UpiPaymentSubmission, admin.site)
        request = SimpleNamespace(user=self.staff)

        def run_action(action_name):
            queryset = UpiPaymentSubmission.objects.filter(pk=submission.pk)
            if action_name == "approve":
                actions.approve_submission(request, queryset)
            else:
                actions.reject_submission(request, queryset)

        self._run_lock_contention(
            lambda: run_action(first_action),
            lambda: run_action(second_action),
            UpiPaymentSubmission._meta.db_table,
        )

        submission.refresh_from_db()
        order.refresh_from_db()
        inventory.refresh_from_db()
        self.assertEqual(submission.status, f"{first_action}d" if first_action == "approve" else "rejected")
        self.assertIsNotNone(submission.reviewed_at)
        self.assertEqual(submission.reviewed_by, self.staff)
        self.assertFalse(order.inventory_reserved)
        if first_action == "approve":
            self.assertTrue(order.is_paid)
            self.assertEqual(order.status, "paid")
            self.assertEqual(inventory.stock_quantity, 0)
        else:
            self.assertFalse(order.is_paid)
            self.assertEqual(order.status, "pending")
            self.assertEqual(inventory.stock_quantity, 1)

    def test_upi_approval_wins_when_it_acquires_submission_lock_first(self):
        self._run_upi_review_contention(
            first_action="approve",
            second_action="reject",
            suffix="approval-first",
        )

    def test_upi_rejection_wins_when_it_acquires_submission_lock_first(self):
        self._run_upi_review_contention(
            first_action="reject",
            second_action="approve",
            suffix="rejection-first",
        )

    @override_settings(RAZORPAY_KEY_ID="test_key", RAZORPAY_KEY_SECRET="test_secret")
    def test_gateway_failure_rolls_back_order_items_and_stock(self):
        product, inventory = self._create_product(
            slug="concurrency-gateway-failure",
            stock=5,
        )

        with patch("orders.views.razorpay.Client") as razorpay_client:
            razorpay_client.return_value.order.create.side_effect = RuntimeError(
                "simulated provider failure"
            )
            response = self._api_client(self.customer).post(
                "/orders/orders/create/",
                {"product_id": product.pk, "quantity": 2},
                format="json",
            )

        self.assertEqual(response.status_code, 502)
        self.assertFalse(Order.objects.filter(items__product=product).exists())
        self.assertFalse(OrderItem.objects.filter(product=product).exists())
        inventory.refresh_from_db()
        self.assertEqual(inventory.stock_quantity, 5)
