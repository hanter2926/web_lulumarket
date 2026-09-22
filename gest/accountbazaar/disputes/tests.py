from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from marketplace.models import Listing
from payments.services import create_order

from .models import Dispute, Report

class TrustSafetyFlowTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.buyer = user_model.objects.create_user(username="buyer", password="pass")
		self.seller = user_model.objects.create_user(username="seller", password="pass")
		self.other = user_model.objects.create_user(username="other", password="pass")
		self.listing = Listing.objects.create(
			seller=self.seller,
			category="gaming",
			title="Safe listing",
			description="A listing",
			price="10.00",
			is_verified=True,
		)
		self.order = create_order(buyer=self.buyer, listing=self.listing, provider="test")

	def test_only_participant_can_create_dispute(self):
		self.client.force_login(self.other)
		response = self.client.get(reverse("disputes:create", args=[self.order.id]))
		self.assertEqual(response.status_code, 403)

		self.client.force_login(self.buyer)
		response = self.client.post(reverse("disputes:create", args=[self.order.id]), {
			"reason": "HANDOFF",
			"description": "The handoff is delayed.",
		})
		self.assertRedirects(response, reverse("disputes:detail", args=[1]))
		self.assertEqual(Dispute.objects.get().opened_by, self.buyer)

	def test_reports_are_owned_by_reporter_and_moderation_is_staff_only(self):
		self.client.force_login(self.buyer)
		response = self.client.post(reverse("disputes:report", args=["listing", self.listing.id]), {
			"reason": "MISLEADING",
			"description": "The listing details need review.",
		})
		self.assertEqual(response.status_code, 302)
		self.assertEqual(Report.objects.get().reporter, self.buyer)

		self.assertEqual(self.client.get(reverse("disputes:moderation")).status_code, 403)
		self.buyer.is_staff = True
		self.buyer.save(update_fields=("is_staff",))
		self.assertEqual(self.client.get(reverse("disputes:moderation")).status_code, 200)

	def test_service_worker_endpoint_is_public_javascript(self):
		response = self.client.get(reverse("service-worker"))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response["Content-Type"], "application/javascript")
