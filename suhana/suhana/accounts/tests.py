from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import PendingSignup
from .utils import hash_otp, hash_user_password


User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RegistrationApiTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        csrf_response = self.client.get("/api/accounts/csrf/")
        self.csrf_token = csrf_response.json()["csrfToken"]

    def post_json(self, url, payload):
        return self.client.post(
            url,
            payload,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=self.csrf_token,
            HTTP_ORIGIN="http://localhost:5174",
        )

    @patch("accounts.views.send_signup_otp", return_value=1)
    def test_registration_creates_pending_signup_without_user(self, send_otp):
        response = self.post_json(
            "/api/accounts/register/",
            {
                "username": "new-user",
                "email": "new@example.com",
                "password": "StrongPassword123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="new-user").exists())
        self.assertTrue(PendingSignup.objects.filter(email="new@example.com").exists())
        send_otp.assert_called_once()

    @patch("accounts.views.send_signup_otp", return_value=1)
    def test_invalid_otp_does_not_create_user(self, send_otp):
        self.post_json(
            "/api/accounts/register/",
            {
                "username": "new-user",
                "email": "new@example.com",
                "password": "StrongPassword123!",
            },
        )

        response = self.post_json(
            "/api/accounts/verify-otp/",
            {"email": "new@example.com", "otp": "000000"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.exists())
        self.assertEqual(response.json()["attempts_remaining"], 4)

    def test_successful_otp_creates_account_and_removes_pending_signup(self):
        PendingSignup.objects.create(
            username="verified-user",
            email="verified@example.com",
            password_hash=hash_user_password("StrongPassword123!"),
            otp_hash=hash_otp("123456"),
            otp_expiry=timezone.now() + timedelta(minutes=10),
        )

        response = self.post_json(
            "/api/accounts/verify-otp/",
            {"email": "verified@example.com", "otp": "123456"},
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username="verified-user")
        self.assertTrue(user.check_password("StrongPassword123!"))
        self.assertFalse(
            PendingSignup.objects.filter(email="verified@example.com").exists()
        )

    def test_resend_obeys_cooldown(self):
        PendingSignup.objects.create(
            username="pending-user",
            email="pending@example.com",
            password_hash=hash_user_password("StrongPassword123!"),
            otp_hash=hash_otp("123456"),
            otp_expiry=timezone.now() + timedelta(minutes=10),
        )

        response = self.post_json(
            "/api/accounts/resend-otp/",
            {"email": "pending@example.com"},
        )

        self.assertEqual(response.status_code, 429)
        self.assertGreater(response.json()["wait_seconds"], 0)
        self.assertEqual(len(mail.outbox), 0)

    def test_csrf_is_required_for_registration(self):
        response = self.client.post(
            "/api/accounts/register/",
            {},
            content_type="application/json",
            HTTP_ORIGIN="http://localhost:5174",
        )

        self.assertEqual(response.status_code, 403)
