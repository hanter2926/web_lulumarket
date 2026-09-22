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

	def test_active_listing_shows_buy_now_to_anonymous_visitors(self):
		listing = Listing.objects.create(
			seller=self.user,
			category="gaming",
			title="Verified account",
			description="Ready to buy",
			price="50.00",
			is_verified=True,
		)

		response = self.client.get(reverse("marketplace:listings"))
		detail_response = self.client.get(reverse("marketplace:listing-detail", args=[listing.pk]))

		self.assertContains(response, "Buy Now")
		self.assertContains(response, reverse("payments:checkout-start", args=[listing.pk]))
		self.assertContains(detail_response, "Buy Now")

	def test_anonymous_buy_now_redirects_to_login_with_purchase_return(self):
		listing = Listing.objects.create(
			seller=self.user,
			category="gaming",
			title="Verified account",
			description="Ready to buy",
			price="50.00",
			is_verified=True,
		)

		response = self.client.post(reverse("payments:checkout-start", args=[listing.pk]))

		self.assertEqual(response.status_code, 302)
		self.assertIn(reverse("accounts:login"), response["Location"])
		self.assertIn("next=", response["Location"])

	def test_logged_in_buyer_reaches_order_summary_from_buy_now(self):
		buyer = get_user_model().objects.create_user(username="buyer", password="pass")
		listing = Listing.objects.create(
			seller=self.user,
			category="gaming",
			title="Verified account",
			description="Ready to buy",
			price="50.00",
			is_verified=True,
		)
		self.client.force_login(buyer)

		response = self.client.post(reverse("payments:checkout-start", args=[listing.pk]))

		self.assertRedirects(response, reverse("payments:order-summary", args=[1]))

	def test_seller_sees_your_listing_instead_of_buy_now(self):
		listing = Listing.objects.create(
			seller=self.user,
			category="gaming",
			title="My verified account",
			description="Seller listing",
			price="50.00",
			is_verified=True,
		)
		self.client.force_login(self.user)

		response = self.client.get(reverse("marketplace:listings"))
		detail_response = self.client.get(reverse("marketplace:listing-detail", args=[listing.pk]))

		self.assertContains(response, "Your Listing")
		self.assertNotContains(response, "Buy Now")
		self.assertContains(detail_response, "Your Listing")
		self.assertNotContains(detail_response, "Buy Now")

	def test_sold_and_inactive_listings_do_not_show_buy_now(self):
		for status, label in (("sold", "Sold"), ("inactive", "Inactive")):
			listing = Listing.objects.create(
				seller=self.user,
				category="gaming",
				title=f"{label} account",
				description="Unavailable",
				price="50.00",
				status=status,
				is_verified=True,
			)
			response = self.client.get(reverse("marketplace:listing-detail", args=[listing.pk]))
			self.assertContains(response, label)
			self.assertNotContains(response, "Buy Now")

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
