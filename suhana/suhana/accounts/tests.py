from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import PasswordResetChallenge, PendingSignup
from .utils import hash_otp, hash_user_password
from storage.models import UserStorage


User = get_user_model()


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class RegistrationApiTests(TestCase):
    def setUp(self):
        cache.clear()
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
        self.assertTrue(UserStorage.objects.filter(user=user).exists())

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

    def test_login_accepts_username_and_creates_session(self):
        user = User.objects.create_user(
            username="login-user",
            email="login@example.com",
            password="StrongPassword123!",
        )

        response = self.post_json(
            "/api/accounts/login/",
            {"identifier": user.username, "password": "StrongPassword123!"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], user.username)
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_login_accepts_email_case_insensitively(self):
        user = User.objects.create_user(
            username="email-login-user",
            email="login@example.com",
            password="StrongPassword123!",
        )

        response = self.post_json(
            "/api/accounts/login/",
            {"identifier": "LOGIN@EXAMPLE.COM", "password": "StrongPassword123!"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], user.username)

    def test_login_rejects_invalid_password(self):
        User.objects.create_user(
            username="login-user",
            email="login@example.com",
            password="StrongPassword123!",
        )

        response = self.post_json(
            "/api/accounts/login/",
            {"identifier": "login-user", "password": "wrong-password"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_rate_limit_allows_correct_credentials_after_failures(self):
        user = User.objects.create_user(
            username="throttled-user",
            email="throttled@example.com",
            password="StrongPassword123!",
        )

        for _ in range(4):
            response = self.post_json(
                "/api/accounts/login/",
                {"identifier": user.username, "password": "wrong-password"},
            )
            self.assertEqual(response.status_code, 401)

        response = self.post_json(
            "/api/accounts/login/",
            {"identifier": user.username, "password": "StrongPassword123!"},
        )
        self.assertEqual(response.status_code, 200)

    def test_login_rate_limit_blocks_repeated_failures(self):
        for _ in range(5):
            response = self.post_json(
                "/api/accounts/login/",
                {"identifier": "unknown-user", "password": "wrong-password"},
            )
            self.assertEqual(response.status_code, 401)

        response = self.post_json(
            "/api/accounts/login/",
            {"identifier": "unknown-user", "password": "wrong-password"},
        )
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "900")

    def test_login_requires_csrf(self):
        response = self.client.post(
            "/api/accounts/login/",
            {"identifier": "login-user", "password": "password"},
            content_type="application/json",
            HTTP_ORIGIN="http://localhost:5174",
        )

        self.assertEqual(response.status_code, 403)

    def test_logout_clears_session(self):
        user = User.objects.create_user(
            username="logout-user",
            password="StrongPassword123!",
        )
        self.client.force_login(user)

        response = self.post_json("/api/accounts/logout/", {})

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    @patch("accounts.views.send_password_reset_otp", return_value=1)
    def test_password_reset_changes_password_after_valid_otp(self, send_otp):
        user = User.objects.create_user(
            username="reset-user",
            email="reset@example.com",
            password="OldPassword123!",
        )

        response = self.post_json(
            "/api/accounts/password-reset/request/",
            {"email": user.email},
        )
        self.assertEqual(response.status_code, 200)
        challenge = PasswordResetChallenge.objects.get(email=user.email)
        otp = send_otp.call_args.args[1]

        response = self.post_json(
            "/api/accounts/password-reset/confirm/",
            {
                "email": user.email,
                "otp": otp,
                "password": "NewPassword123!",
            },
        )

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password("NewPassword123!"))
        self.assertFalse(PasswordResetChallenge.objects.filter(pk=challenge.pk).exists())

    def test_password_reset_does_not_reveal_unknown_email(self):
        response = self.post_json(
            "/api/accounts/password-reset/request/",
            {"email": "unknown@example.com"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(PasswordResetChallenge.objects.exists())

    @patch("accounts.views.send_password_reset_otp", return_value=1)
    def test_password_reset_request_is_throttled_without_enumeration(self, send_otp):
        user = User.objects.create_user(
            username="reset-throttled",
            email="reset-throttled@example.com",
            password="StrongPassword123!",
        )
        responses = [
            self.post_json(
                "/api/accounts/password-reset/request/",
                {"email": user.email},
            )
            for _ in range(4)
        ]

        self.assertEqual([response.status_code for response in responses], [200, 200, 200, 200])
        self.assertEqual(send_otp.call_count, 3)
        self.assertEqual(responses[-1].json(), responses[0].json())
