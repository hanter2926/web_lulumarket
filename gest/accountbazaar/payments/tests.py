from django.contrib.auth import get_user_model
from django.test import TestCase

from disputes.models import Dispute
from marketplace.models import Listing

from .models import Escrow, Order, Payment, Refund
from .services import create_order, open_dispute, record_payment_success, request_refund


class TransactionWorkflowTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.buyer = user_model.objects.create_user(username="buyer", password="pass")
		self.seller = user_model.objects.create_user(username="seller", password="pass")
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
