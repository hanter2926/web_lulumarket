from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Account, AccountMembership


class AccountFlowTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(
			username="account-owner",
			password="Strong-pass-123",
		)

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
		response = self.client.post(
			reverse("accounts:login"),
			{"username": "account-owner", "password": "Strong-pass-123"},
		)

		self.assertRedirects(response, "/")

	def test_user_can_switch_between_member_accounts(self):
		account = Account.objects.create(owner=self.user, name="Second account")
		AccountMembership.objects.create(account=account, user=self.user)
		self.client.force_login(self.user)

		response = self.client.post(reverse("accounts:switch-account", args=(account.id,)))

		self.assertRedirects(response, reverse("marketplace:listings"))
		self.assertEqual(self.client.session["active_account_id"], account.id)
