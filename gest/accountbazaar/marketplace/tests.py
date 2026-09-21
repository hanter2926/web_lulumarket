from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Listing


class ListingViewTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(
			username="seller",
			password="test-pass-123",
		)

	def test_anonymous_users_can_browse_listings(self):
		response = self.client.get(reverse("marketplace:listings"))

		self.assertEqual(response.status_code, 200)

	def test_search_and_category_filter_listings(self):
		Listing.objects.create(
			seller=self.user,
			category="gaming",
			title="Gaming account",
			description="Ranked profile",
			price="25.00",
		)
		Listing.objects.create(
			seller=self.user,
			category="software",
			title="Design tools",
			description="Creative suite",
			price="15.00",
		)

		response = self.client.get(
			reverse("marketplace:listings"),
			{"q": "Gaming", "category": "gaming"},
		)

		self.assertContains(response, "Gaming account")
		self.assertNotContains(response, "Design tools")

	def test_authenticated_user_can_create_listing(self):
		self.client.force_login(self.user)

		response = self.client.post(
			reverse("marketplace:listings"),
			{
				"category": "gaming",
				"title": "Starter account",
				"description": "Ready to use",
				"price": "25.00",
			},
		)

		self.assertRedirects(response, reverse("marketplace:listings"))
		listing = Listing.objects.get()
		self.assertEqual(listing.seller, self.user)
		self.assertEqual(listing.title, "Starter account")
