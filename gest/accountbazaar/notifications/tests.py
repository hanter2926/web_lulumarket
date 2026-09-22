from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from .models import Notification


class NotificationTests(TestCase):
	def setUp(self):
		self.user = get_user_model().objects.create_user(username="notify-user", password="pass")

	def test_user_can_read_own_notification(self):
		notification = Notification.objects.create(
			recipient=self.user,
			title="Order update",
			body="Your order changed status.",
		)
		self.client.force_login(self.user)

		response = self.client.post(reverse("notifications:mark-read", args=(notification.id,)))

		self.assertRedirects(response, reverse("notifications:inbox"))
		notification.refresh_from_db()
		self.assertTrue(notification.is_read)
