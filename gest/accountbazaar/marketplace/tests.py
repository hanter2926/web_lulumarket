from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from base64 import b64decode

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

	def test_price_filter_and_sort_are_server_side(self):
		Listing.objects.create(
			seller=self.user,
			category="gaming",
			title="Budget account",
			description="Affordable",
			price="10.00",
		)
		Listing.objects.create(
			seller=self.user,
			category="gaming",
			title="Premium account",
			description="Premium",
			price="100.00",
		)

		response = self.client.get(reverse("marketplace:listings"), {"min_price": "50", "sort": "price_high"})

		self.assertContains(response, "Premium account")
		self.assertNotContains(response, "Budget account")

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

	def test_authenticated_user_can_create_listing_with_image(self):
		self.client.force_login(self.user)
		image = SimpleUploadedFile(
			"account.png",
			b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="),
			content_type="image/png",
		)

		response = self.client.post(
			reverse("marketplace:listings"),
			{
				"category": "gaming",
				"title": "Visual account",
				"description": "Ready to use",
				"price": "35.00",
				"image": image,
			},
		)

		self.assertRedirects(response, reverse("marketplace:listings"))
		self.assertTrue(Listing.objects.get().image.name.startswith("listings/"))

	def test_listing_image_rejects_unsupported_type(self):
		form_data = {
			"category": "gaming",
			"title": "Unsafe file",
			"description": "Not an image",
			"price": "35.00",
		}
		file_data = SimpleUploadedFile("script.exe", b"not an image", content_type="application/octet-stream")

		from .forms import ListingForm
		form = ListingForm(form_data, {"image": file_data})

		self.assertFalse(form.is_valid())
		self.assertIn("image", form.errors)
