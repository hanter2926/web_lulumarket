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

	def test_anonymous_users_are_redirected_to_login(self):
		response = self.client.get(reverse("marketplace:listings"))

		self.assertRedirects(
			response,
			"/accounts/login/?next=/marketplace/",
			fetch_redirect_response=False,
		)

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
