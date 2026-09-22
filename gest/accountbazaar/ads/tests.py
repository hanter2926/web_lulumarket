from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import AdCampaign, AdPlacement


class OwnerDashboardTests(TestCase):
	def test_owner_sees_only_their_campaign_metrics(self):
		user_model = get_user_model()
		owner = user_model.objects.create_user(username="owner", password="pass")
		other = user_model.objects.create_user(username="other", password="pass")
		placement = AdPlacement.objects.create(name="Header", location="home")
		AdCampaign.objects.create(owner=owner, placement=placement, name="Owner campaign", impressions=100, clicks=10)
		AdCampaign.objects.create(owner=other, placement=placement, name="Other campaign", impressions=900, clicks=90)
		self.client.force_login(owner)

		response = self.client.get(reverse("owner-dashboard"))

		self.assertContains(response, "Owner campaign")
		self.assertNotContains(response, "Other campaign")
		self.assertContains(response, "10.0%")
