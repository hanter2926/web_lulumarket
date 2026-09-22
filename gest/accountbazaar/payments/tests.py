import hashlib
import hmac
import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from disputes.models import Dispute
from marketplace.models import Listing

from .models import AccountTransfer, ComplianceCheck, Escrow, FeeConfiguration, Order, Payment, Refund, Settlement
from .services import create_order, open_dispute, record_payment_success, request_refund


class TransactionWorkflowTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.buyer = user_model.objects.create_user(username="buyer", password="pass")
		self.seller = user_model.objects.create_user(username="seller", password="pass")
		self.other_buyer = user_model.objects.create_user(username="other-buyer", password="pass")
		self.listing = Listing.objects.create(
			seller=self.seller,
			category="gaming",
			title="Verified account",
			description="Ready to transfer",
			price="100.00",
			is_verified=True,
		)

	def test_payment_success_moves_order_into_escrow(self):
		order = create_order(buyer=self.buyer, listing=self.listing, provider="test")

		record_payment_success(order=order, provider_payment_id="pay_123")
		order.refresh_from_db()

		self.assertEqual(order.status, Order.Status.IN_ESCROW)
		self.assertEqual(order.payment.status, Payment.Status.CAPTURED)
		self.assertEqual(order.escrow.status, Escrow.Status.HELD)

		record_payment_success(order=order, provider_payment_id="pay_123")
		self.assertEqual(Payment.objects.count(), 1)

	def test_refund_request_and_dispute_are_separate_paths(self):
		order = create_order(buyer=self.buyer, listing=self.listing, provider="test")
		record_payment_success(order=order, provider_payment_id="pay_456")

		refund = request_refund(order=order, reason="Not as described")
		self.assertEqual(refund.status, Refund.Status.REQUESTED)

		dispute = open_dispute(order=order, opened_by=self.buyer, reason="Need review")
		order.refresh_from_db()
		self.assertEqual(dispute.status, Dispute.Status.OPEN)
		self.assertEqual(order.status, Order.Status.DISPUTED)

	def test_fee_is_recorded_and_settlement_is_held_after_payment(self):
		FeeConfiguration.objects.create(
			name="standard",
			percentage="5.00",
			fixed_amount="2.00",
		)
		order = create_order(buyer=self.buyer, listing=self.listing, provider="test")

		self.assertEqual(order.settlement.platform_fee, 7)
		self.assertEqual(order.settlement.net_amount, 93)
		self.assertEqual(order.compliance_check.status, ComplianceCheck.Status.BLOCKED)

		record_payment_success(order=order, provider_payment_id="pay_fee")
		order.refresh_from_db()
		self.assertEqual(order.settlement.status, Settlement.Status.HELD)

	def test_buyer_can_view_listing_and_start_checkout(self):
		self.client.force_login(self.buyer)

		self.assertEqual(self.client.get(reverse("marketplace:listing-detail", args=[self.listing.id])).status_code, 200)
		response = self.client.post(reverse("payments:checkout-start", args=[self.listing.id]))

		self.assertRedirects(response, reverse("payments:order-summary", args=[1]))
		self.assertEqual(Order.objects.get().amount, Decimal("100.00"))

	def test_unauthenticated_buy_now_returns_to_login(self):
		response = self.client.post(reverse("payments:checkout-start", args=[self.listing.id]))

		self.assertEqual(response.status_code, 302)
		self.assertIn(reverse("accounts:login"), response["Location"])
		self.assertIn("next=", response["Location"])

	def test_seller_cannot_buy_own_listing(self):
		self.client.force_login(self.seller)

		response = self.client.post(reverse("payments:checkout-start", args=[self.listing.id]))

		self.assertEqual(response.status_code, 400)
		self.assertEqual(Order.objects.count(), 0)

	def test_inactive_and_sold_listings_cannot_be_purchased(self):
		self.client.force_login(self.buyer)
		for status in ("inactive", "sold"):
			self.listing.status = status
			self.listing.save(update_fields=("status",))
			response = self.client.post(reverse("payments:checkout-start", args=[self.listing.id]))
			self.assertEqual(response.status_code, 400)

	def test_second_buyer_cannot_create_duplicate_purchase(self):
		first_order = create_order(buyer=self.buyer, listing=self.listing, provider="test")

		with self.assertRaisesMessage(ValueError, "already has a purchase"):
			create_order(buyer=self.other_buyer, listing=self.listing, provider="test")
		self.assertEqual(Order.objects.count(), 1)
		self.assertEqual(first_order.amount, Decimal("100.00"))

	def test_browser_cannot_manipulate_listing_price(self):
		self.client.force_login(self.buyer)
		response = self.client.post(
			reverse("payments:checkout-start", args=[self.listing.id]),
			{"amount": "0.01"},
		)

		self.assertEqual(response.status_code, 302)
		self.assertEqual(Order.objects.get().amount, 100)

	def test_verified_demo_payment_marks_order_and_listing_sold(self):
		self.client.force_login(self.buyer)
		self.client.post(reverse("payments:checkout-start", args=[self.listing.id]))
		order = Order.objects.get()

		response = self.client.post(reverse("payments:demo-payment", args=[order.id]))

		self.assertRedirects(response, reverse("payments:payment-success-page", args=[order.id]))
		order.refresh_from_db()
		self.listing.refresh_from_db()
		self.assertEqual(order.payment_status, "PAID")
		self.assertEqual(order.status, Order.Status.IN_ESCROW)
		self.assertEqual(self.listing.status, "sold")
		self.assertEqual(AccountTransfer.objects.get(order=order).status, AccountTransfer.Status.AWAITING_SELLER)

	def test_failed_demo_payment_does_not_mark_order_paid(self):
		self.client.force_login(self.buyer)
		self.client.post(reverse("payments:checkout-start", args=[self.listing.id]))
		order = Order.objects.get()

		self.client.post(reverse("payments:demo-payment-failed", args=[order.id]))
		order.refresh_from_db()
		self.assertEqual(order.payment_status, "FAILED")
		self.assertNotEqual(order.status, Order.Status.IN_ESCROW)
		self.assertEqual(self.listing.__class__.objects.get(pk=self.listing.pk).status, "pending")

	def test_buyer_cannot_view_another_buyers_order(self):
		order = create_order(buyer=self.buyer, listing=self.listing, provider="test")
		self.client.force_login(self.other_buyer)

		response = self.client.get(reverse("payments:order-detail", args=[order.id]))

		self.assertEqual(response.status_code, 403)

	def test_seller_orders_only_show_that_sellers_sales(self):
		other_seller = get_user_model().objects.create_user(username="other-seller", password="pass")
		other_listing = Listing.objects.create(
			seller=other_seller,
			category="software",
			title="Other listing",
			description="Other account",
			price="50.00",
			is_verified=True,
		)
		create_order(buyer=self.buyer, listing=self.listing, provider="test")
		create_order(buyer=self.other_buyer, listing=other_listing, provider="test")
		self.client.force_login(self.seller)

		response = self.client.get(reverse("payments:seller-orders"))

		self.assertContains(response, self.listing.title)
		self.assertNotContains(response, other_listing.title)

	def test_transfer_confirmation_completes_order_without_credentials(self):
		order = create_order(buyer=self.buyer, listing=self.listing, provider="test")
		record_payment_success(order=order, provider_payment_id="pay_transfer")
		self.client.force_login(self.seller)
		self.client.post(reverse("payments:transfer-start", args=[order.id]))
		self.assertEqual(AccountTransfer.objects.get(order=order).status, AccountTransfer.Status.STARTED)
		self.client.post(reverse("payments:transfer-sent", args=[order.id]), {"note": "Secure handoff reference"})
		self.client.force_login(self.buyer)

		response = self.client.post(reverse("payments:transfer-received", args=[order.id]))

		self.assertRedirects(response, reverse("payments:order-detail", args=[order.id]))
		order.refresh_from_db()
		self.assertEqual(order.status, Order.Status.COMPLETED)
		self.assertEqual(order.escrow.status, Escrow.Status.RELEASED)
		self.assertEqual(order.settlement.status, Settlement.Status.ELIGIBLE)

	def test_provider_amount_mismatch_cannot_capture_payment(self):
		order = create_order(buyer=self.buyer, listing=self.listing, provider="razorpay")
		with self.assertRaisesMessage(ValueError, "provider amount"):
			record_payment_success(
				order=order,
				provider_payment_id="pay_wrong_amount",
				amount="0.01",
			)
		order.refresh_from_db()
		self.assertEqual(order.payment.status, Payment.Status.CREATED)

	@override_settings(RAZORPAY_WEBHOOK_SECRET="webhook-secret")
	def test_signed_razorpay_webhook_captures_payment(self):
		order = create_order(buyer=self.buyer, listing=self.listing, provider="razorpay")
		order.payment.provider_order_id = "order_123"
		order.payment.save(update_fields=("provider_order_id",))
		body = json.dumps({
			"event": "payment.captured",
			"payload": {"payment": {"entity": {"order_id": "order_123", "id": "pay_123"}}},
		}).encode()
		signature = hmac.new(b"webhook-secret", body, hashlib.sha256).hexdigest()

		response = self.client.post(
			reverse("payments:razorpay-webhook"),
			data=body,
			content_type="application/json",
			HTTP_X_RAZORPAY_SIGNATURE=signature,
		)

		self.assertEqual(response.status_code, 200)
		order.refresh_from_db()
		self.assertEqual(order.status, Order.Status.IN_ESCROW)
