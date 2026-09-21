from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AccountFlowTests(TestCase):
	def test_register_creates_user_and_logs_them_in(self):
		response = self.client.post(
			reverse("accounts:register"),
			{
				"username": "new-seller",
				"email": "seller@example.com",
				"phone_number": "9876543210",
				"password": "Strong-pass-123",
				"password_confirmation": "Strong-pass-123",
			},
		)

		self.assertRedirects(response, reverse("marketplace:listings"))
		self.assertTrue(response.wsgi_request.user.is_authenticated)
		self.assertTrue(get_user_model().objects.filter(username="new-seller").exists())

	def test_user_can_log_in(self):
		get_user_model().objects.create_user(
			username="seller",
			password="Strong-pass-123",
		)

		response = self.client.post(
			reverse("accounts:login"),
			{"username": "seller", "password": "Strong-pass-123"},
		)

		self.assertRedirects(response, "/")
