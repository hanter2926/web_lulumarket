from datetime import timedelta
import json
import smtplib

from anymail.exceptions import AnymailRequestsAPIError
from django.core import mail
from django.core.mail import EmailMessage
from django.db import OperationalError
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.hashers import check_password
from unittest.mock import Mock, patch
from urllib.parse import urlencode, urlparse
import re
from requests import Response, Timeout

from .email_otp import verify_email_otp
from .email_delivery import (
    BrevoAPIError,
    EmailDeliveryConfigurationError,
    classify_email_delivery_error,
    send_account_email,
)
from .models import (
    Address,
    CustomUser,
    EmailOTPChallenge,
    EmailOTPThrottle,
    UserProfile,
)
from .utils import generate_otp, normalize_phone_number
from .utils import send_otp_via_console


class AccountTests(TestCase):
    def test_profile_and_address_models_support_delivery_data(self):
        user = CustomUser.objects.create_user(
            email="test@example.com",
            username="testuser",
            password="StrongPass123",
            first_name="Test",
            last_name="User",
            phone="9123456789",
        )
        profile = UserProfile.objects.create(
            user=user,
            full_name="Test User",
            phone="9123456789",
            delivery_location="Bengaluru",
        )
        address = Address.objects.create(
            user=user,
            profile=profile,
            label="Home",
            full_name="Test User",
            phone="9123456789",
            address_line_1="12 MG Road",
            city="Bengaluru",
            state="Karnataka",
            country="India",
            pincode="560001",
            is_default=True,
        )

        self.assertEqual(profile.delivery_location, "Bengaluru")
        self.assertTrue(address.is_default)
        self.assertEqual(address.label, "Home")

    def test_generate_otp_returns_six_digit_code(self):
        otp = generate_otp()
        self.assertEqual(len(otp), 6)
        self.assertTrue(otp.isdigit())

    def test_console_sms_backend_never_logs_otp_or_claims_delivery(self):
        code = "123456"
        with self.assertLogs("accounts.utils", level="WARNING") as captured:
            result = send_otp_via_console("+919876543210", code)

        self.assertEqual(result["status"], "failed")
        self.assertNotIn(code, "\n".join(captured.output))

    def test_profile_supports_phone_otp_verification(self):
        user = CustomUser.objects.create_user(
            email="otp@example.com",
            username="otpuser",
            password="StrongPass123",
            phone="9876543210",
        )
        profile = UserProfile.objects.create(
            user=user,
            full_name="OTP User",
            phone="9876543210",
            otp="123456",
            is_phone_verified=False,
        )

        self.assertEqual(profile.otp, "123456")
        self.assertFalse(profile.is_phone_verified)

    def test_normalize_phone_number_standardizes_indian_formats(self):
        self.assertEqual(normalize_phone_number("9876543210"), "+919876543210")
        self.assertEqual(normalize_phone_number("+91 98765 43210"), "+919876543210")
        self.assertEqual(normalize_phone_number("919876543210"), "+919876543210")
        self.assertEqual(normalize_phone_number("09876543210"), "+919876543210")

    @patch("accounts.views.send_otp_to_phone", return_value={"status": "sent"})
    def test_request_otp_requires_phone_without_email_and_finds_existing_user(self, send_otp):
        user = CustomUser.objects.create_user(
            email="phone-login@example.com",
            username="phone-login-user",
            password="StrongPass123",
            phone="+919876543210",
        )
        UserProfile.objects.get_or_create(user=user, defaults={"full_name": user.get_full_name() or user.email})

        response = self.client.post("/accounts/request-otp/", {"phone": "9876543210"}, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertIn("OTP sent successfully", response.json()["detail"])
        send_otp.assert_called_once()

    def test_request_otp_for_unregistered_phone_returns_clear_error(self):
        response = self.client.post("/accounts/request-otp/", {"phone": "9999999999"}, content_type="application/json")
        self.assertEqual(response.status_code, 404)
        self.assertIn("No account found with this phone number. Please register first.", response.json()["detail"])

    @patch("accounts.views.send_otp_to_phone", return_value={"status": "sent"})
    def test_browser_request_redirects_to_masked_otp_page(self, send_otp):
        user = CustomUser.objects.create_user(
            email="browser-otp@example.com",
            username="browser-otp-user",
            password="StrongPass123",
            phone="+919876543210",
        )
        UserProfile.objects.get_or_create(user=user)

        response = self.client.post(
            reverse("accounts:request_otp"),
            urlencode({"phone": "9876543210"}),
            content_type="application/x-www-form-urlencoded",
            HTTP_ACCEPT="text/html",
        )

        self.assertRedirects(response, reverse("accounts:otp_login_page"))
        page = self.client.get(reverse("accounts:otp_login_page"))
        self.assertContains(page, "OTP Sent Successfully!")
        self.assertContains(page, "+91 987*****210")
        self.assertNotContains(page, "+919876543210")
        send_otp.assert_called_once()

    @patch("accounts.views.send_otp_to_phone", side_effect=RuntimeError("Twilio unavailable"))
    def test_browser_request_does_not_show_success_when_delivery_fails(self, send_otp):
        user = CustomUser.objects.create_user(
            email="failed-otp@example.com",
            username="failed-otp-user",
            password="StrongPass123",
            phone="+919876543211",
        )
        UserProfile.objects.get_or_create(user=user)

        response = self.client.post(
            reverse("accounts:request_otp"),
            urlencode({"phone": "9876543211"}),
            content_type="application/x-www-form-urlencoded",
            HTTP_ACCEPT="text/html",
        )

        self.assertEqual(response.status_code, 500)
        self.assertContains(response, "Unable to send OTP right now", status_code=500)
        self.assertNotIn("OTP Sent Successfully!", response.content.decode())
        profile = UserProfile.objects.get(user=user)
        self.assertFalse(profile.otp)
        self.assertIsNone(profile.otp_expires_at)
        send_otp.assert_called_once()


class PhoneOTPAPISecurityTests(TestCase):
    otp = "642951"

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="phone-api@example.com",
            username="phone-api-user",
            password="StrongPass123!",
            phone="+919876543210",
            is_active=True,
        )
        self.profile = UserProfile.objects.create(
            user=self.user,
            phone=self.user.phone,
            otp=self.otp,
            otp_expires_at=timezone.now() + timedelta(minutes=5),
            is_phone_verified=True,
        )

    def _assert_otp_not_serialized(self, payload):
        self.assertNotIn(self.otp, json.dumps(payload))

        def assert_no_otp_field(value):
            if isinstance(value, dict):
                self.assertNotIn("otp", value)
                self.assertNotIn("otp_expires_at", value)
                for nested_value in value.values():
                    assert_no_otp_field(nested_value)
            elif isinstance(value, list):
                for nested_value in value:
                    assert_no_otp_field(nested_value)

        assert_no_otp_field(payload)

    def test_public_registration_responses_do_not_expose_phone_otp(self):
        registration_payloads = (
            (
                reverse("accounts:users-register"),
                {
                    "email": "router-registration@example.com",
                    "username": "router-registration",
                    "password": "StrongPass123!",
                    "phone": "+919876543211",
                },
            ),
            (
                reverse("accounts:signup_submit"),
                {
                    "email": "signup-registration@example.com",
                    "password": "StrongPass123!",
                    "phone": "9876543212",
                    "full_name": "Signup Registration",
                },
            ),
        )

        with patch("accounts.views.generate_otp", return_value=self.otp), patch(
            "accounts.views.send_otp_to_phone", return_value={"status": "sent"}
        ):
            for endpoint, payload in registration_payloads:
                with self.subTest(endpoint=endpoint):
                    response = self.client.post(
                        endpoint, payload, content_type="application/json"
                    )

                    self.assertEqual(response.status_code, 201)
                    self._assert_otp_not_serialized(response.json())

    def test_user_and_profile_api_responses_do_not_expose_phone_otp(self):
        self.client.force_login(self.user)
        responses = [
            self.client.get(reverse("accounts:users-me")),
            self.client.get(reverse("accounts:users-list")),
            self.client.get(
                reverse("accounts:users-detail", kwargs={"pk": self.user.pk})
            ),
            self.client.get(reverse("accounts:profiles-list")),
            self.client.get(
                reverse("accounts:profiles-detail", kwargs={"pk": self.profile.pk})
            ),
            self.client.patch(
                reverse("accounts:profiles-update-profile"),
                {"full_name": "Updated name"},
                content_type="application/json",
            ),
        ]

        for response in responses:
            with self.subTest(path=response.wsgi_request.path):
                self.assertEqual(response.status_code, 200)
                self._assert_otp_not_serialized(response.json())

    def test_public_login_response_does_not_expose_phone_otp(self):
        response = self.client.post(
            reverse("accounts:users-login"),
            {"email": self.user.email, "password": "StrongPass123!"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self._assert_otp_not_serialized(response.json())

    def test_phone_otp_requires_a_non_expired_expiry_timestamp(self):
        for expires_at in (None, timezone.now() - timedelta(seconds=1)):
            with self.subTest(expires_at=expires_at):
                self.profile.otp = self.otp
                self.profile.otp_expires_at = expires_at
                self.profile.save(update_fields=["otp", "otp_expires_at", "updated_at"])

                response = self.client.post(
                    reverse("accounts:verify_otp"),
                    {"phone": self.user.phone, "otp": self.otp},
                    content_type="application/json",
                )

                self.assertEqual(response.status_code, 400)
                self.assertIn("expired", response.json()["detail"].lower())
                self.profile.refresh_from_db()
                self.assertTrue(self.profile.is_phone_verified)

    def test_phone_otp_is_expired_at_the_exact_expiry_time(self):
        expires_at = timezone.now()
        self.profile.otp_expires_at = expires_at
        self.profile.save(update_fields=["otp_expires_at", "updated_at"])

        with patch("accounts.views.timezone.now", return_value=expires_at):
            response = self.client.post(
                reverse("accounts:users-phone-login"),
                {"phone": self.user.phone, "otp": self.otp},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("expired", response.json()["detail"].lower())

    def test_phone_otp_cannot_be_reused_after_successful_verification(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active", "updated_at"])
        self.profile.is_phone_verified = False
        self.profile.otp_expires_at = timezone.now() + timedelta(minutes=5)
        self.profile.save(update_fields=["is_phone_verified", "otp_expires_at", "updated_at"])

        first_response = self.client.post(
            reverse("accounts:verify_otp"),
            {"phone": self.user.phone, "otp": self.otp},
            content_type="application/json",
        )
        second_response = self.client.post(
            reverse("accounts:users-phone-login"),
            {"phone": self.user.phone, "otp": self.otp},
            content_type="application/json",
        )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 400)
        self.assertEqual(second_response.json()["detail"], "Invalid OTP.")
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.profile.is_phone_verified)
        self.assertFalse(self.profile.otp)

    def test_phone_otp_cannot_reactivate_inactive_phone_verified_account(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active", "updated_at"])
        self.profile.otp_expires_at = timezone.now() + timedelta(minutes=5)
        self.profile.save(update_fields=["otp_expires_at", "updated_at"])

        for endpoint in (
            reverse("accounts:verify_otp"),
            reverse("accounts:users-phone-login"),
        ):
            with self.subTest(endpoint=endpoint):
                response = self.client.post(
                    endpoint,
                    {"phone": self.user.phone, "otp": self.otp},
                    content_type="application/json",
                )

                self.assertEqual(response.status_code, 403)
                self.user.refresh_from_db()
                self.profile.refresh_from_db()
                self.assertFalse(self.user.is_active)
                self.assertTrue(self.profile.is_phone_verified)
                self.assertEqual(self.profile.otp, self.otp)

    @patch("accounts.views.send_otp_to_phone", return_value={"status": "sent"})
    def test_request_otp_does_not_clear_disabled_users_phone_verification(self, send_otp):
        self.user.is_active = False
        self.user.save(update_fields=["is_active", "updated_at"])

        response = self.client.post(
            reverse("accounts:request_otp"),
            {"phone": self.user.phone},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        send_otp.assert_not_called()
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.is_phone_verified)
        self.assertEqual(self.profile.otp, self.otp)


class AccountSecurityTests(TestCase):
    def test_unverified_user_cannot_log_in_with_email_and_password(self):
        user = CustomUser.objects.create_user(
            email="pending@example.com",
            username="pending-user",
            password="StrongPass123",
            phone="+919876543210",
            is_active=True,
        )
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.full_name = "Pending User"
        profile.phone = user.phone
        profile.is_phone_verified = False
        profile.save(update_fields=["full_name", "phone", "is_phone_verified", "updated_at"])

        response = self.client.post(reverse("accounts:email_login"), {"email": "pending@example.com", "password": "StrongPass123"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Verify your email or phone number before logging in",
        )
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_verified_user_can_log_in_with_email_and_password(self):
        user = CustomUser.objects.create_user(
            email="verified@example.com",
            username="verified-user",
            password="StrongPass123",
            phone="+919876543211",
            is_active=True,
        )
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.phone = user.phone
        profile.is_phone_verified = True
        profile.save(update_fields=["phone", "is_phone_verified", "updated_at"])

        response = self.client.post(reverse("accounts:email_login"), {"email": "verified@example.com", "password": "StrongPass123"})

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:dashboard_page"), response.url)

    def test_verified_user_can_log_in_with_case_variant_email(self):
        user = CustomUser.objects.create_user(
            email="case@example.com",
            username="case-user",
            password="StrongPass123",
            is_active=True,
        )
        UserProfile.objects.create(user=user, phone="+919876543212", is_phone_verified=True)

        response = self.client.post(
            reverse("accounts:email_login"),
            {"email": "CASE@EXAMPLE.COM", "password": "StrongPass123"},
        )

        self.assertRedirects(response, reverse("accounts:dashboard_page"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_login_honors_safe_next_parameter(self):
        user = CustomUser.objects.create_user(
            email="next@example.com",
            username="next-user",
            password="StrongPass123",
            is_active=True,
        )
        UserProfile.objects.create(user=user, phone="+919876543213", is_phone_verified=True)

        response = self.client.post(
            f"{reverse('accounts:email_login')}?next=/cart/",
            {"email": user.email, "password": "StrongPass123", "next": "/cart/"},
        )

        self.assertRedirects(response, "/cart/", status_code=302, target_status_code=200)

    def test_login_rejects_external_next_parameter(self):
        user = CustomUser.objects.create_user(
            email="redirect@example.com",
            username="redirect-user",
            password="StrongPass123",
            is_active=True,
        )
        UserProfile.objects.create(user=user, phone="+919876543214", is_phone_verified=True)

        response = self.client.post(
            reverse("accounts:email_login"),
            {
                "email": user.email,
                "password": "StrongPass123",
                "next": "https://attacker.example/",
            },
        )

        self.assertRedirects(response, reverse("accounts:dashboard_page"))

    def test_inactive_user_cannot_log_in(self):
        user = CustomUser.objects.create_user(
            email="inactive@example.com",
            username="inactive-user",
            password="StrongPass123",
            is_active=False,
        )
        UserProfile.objects.create(user=user, phone="+919876543215", is_phone_verified=True)

        response = self.client.post(
            reverse("accounts:email_login"),
            {"email": user.email, "password": "StrongPass123"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your account is inactive")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_verified_user_with_wrong_password_cannot_log_in(self):
        user = CustomUser.objects.create_user(
            email="wrong-password@example.com",
            username="wrong-password-user",
            is_active=True,
            is_email_verified=True,
        )
        user.set_password("CorrectPassword123!")
        user.save(update_fields=["password"])
        UserProfile.objects.create(user=user, is_phone_verified=False)

        response = self.client.post(
            reverse("accounts:email_login"),
            {"email": user.email, "password": "NotTheCorrectPassword123!"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid email or password.")
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_login_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        response = csrf_client.post(
            reverse("accounts:email_login"),
            {"email": "unknown@example.com", "password": "StrongPass123"},
        )

        self.assertEqual(response.status_code, 403)

    def test_login_session_survives_follow_up_request(self):
        user = CustomUser.objects.create_user(
            email="session@example.com",
            username="session-user",
            password="StrongPass123",
            is_active=True,
        )
        UserProfile.objects.create(user=user, phone="+919876543216", is_phone_verified=True)

        login_response = self.client.post(
            reverse("accounts:email_login"),
            {"email": user.email, "password": "StrongPass123", "remember": "on"},
        )

        self.assertEqual(login_response.status_code, 302)
        dashboard_response = self.client.get(reverse("accounts:dashboard_page"))
        self.assertEqual(dashboard_response.status_code, 200)


@override_settings(
    EMAIL_PROVIDER="smtp",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@example.com",
    DEBUG=True,
)
class SignupFlowTests(TestCase):
    signup_data = {
        "full_name": "New Customer",
        "email": "new-customer@example.com",
        "phone": "9876543210",
        "password": "StrongSignupPass123!",
        "confirm_password": "StrongSignupPass123!",
        "terms": "on",
    }

    def test_signup_page_loads(self):
        response = self.client.get(reverse("accounts:signup_form"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Create Account")

    @patch("accounts.views.send_otp_to_phone")
    def test_valid_signup_sends_email_otp_and_verifies_account(self, send_otp):
        response = self.client.post(reverse("accounts:signup_form"), self.signup_data)

        self.assertRedirects(
            response,
            reverse("accounts:signup_email_verify"),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.signup_data["email"], mail.outbox[0].to)
        self.assertIn("verify your email address", mail.outbox[0].body)
        user = CustomUser.objects.get(email=self.signup_data["email"])
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_email_verified)
        self.assertTrue(user.check_password(self.signup_data["password"]))
        self.assertNotEqual(user.password, self.signup_data["password"])
        profile = UserProfile.objects.get(user=user)
        self.assertFalse(profile.is_phone_verified)
        self.assertEqual(profile.phone, "+919876543210")
        send_otp.assert_not_called()

        code = re.search(r"\b(\d{6})\b", mail.outbox[0].body).group(1)
        response = self.client.post(
            reverse("accounts:signup_email_verify"),
            {"email": self.signup_data["email"], "code": code},
        )

        self.assertRedirects(response, reverse("accounts:dashboard_page"))
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_email_verified)
        self.assertFalse(UserProfile.objects.get(user=user).is_phone_verified)

        self.client.get(reverse("accounts:logout_page"))
        response = self.client.post(
            reverse("accounts:email_login"),
            {
                "email": self.signup_data["email"],
                "password": self.signup_data["password"],
            },
        )
        self.assertRedirects(response, reverse("accounts:dashboard_page"))

    @override_settings(
        DEBUG=False,
        EMAIL_BACKEND="anymail.backends.brevo.EmailBackend",
        EMAIL_PROVIDER="brevo",
        BREVO_API_KEY="mock-api-key",
        BREVO_SENDER_EMAIL="sender@example.com",
        BREVO_SENDER_NAME="NAGRI",
    )
    @patch(
        "accounts.email_delivery.requests.post",
        return_value=Mock(
            status_code=201,
            json=lambda: {"messageId": "mock-message-id"},
        ),
    )
    def test_signup_delivers_email_otp_through_brevo(self, post):
        response = self.client.post(
            reverse("accounts:signup_form"),
            self.signup_data,
        )

        self.assertRedirects(
            response,
            reverse("accounts:signup_email_verify"),
            fetch_redirect_response=False,
        )
        post.assert_called_once()
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["to"], [{"email": self.signup_data["email"]}])
        self.assertEqual(payload["sender"]["email"], "sender@example.com")
        self.assertRegex(payload["textContent"], r"verify your email address is \d{6}")
        user = CustomUser.objects.get(email=self.signup_data["email"])
        self.assertFalse(user.is_active)
        challenge = EmailOTPChallenge.objects.get(
            user=user,
            purpose=EmailOTPChallenge.Purpose.SIGNUP,
        )
        self.assertIsNone(challenge.consumed_at)

    @override_settings(
        DEBUG=False,
        EMAIL_BACKEND="anymail.backends.brevo.EmailBackend",
        EMAIL_PROVIDER="brevo",
        BREVO_API_KEY="mock-api-key",
        BREVO_SENDER_EMAIL="sender@example.com",
        BREVO_SENDER_NAME="NAGRI",
    )
    @patch(
        "accounts.email_delivery.requests.post",
        return_value=Mock(
            status_code=401,
            json=lambda: {"message": "must not be logged"},
        ),
    )
    def test_signup_brevo_failure_is_logged_safely_and_not_shown_as_success(
        self,
        post,
    ):
        with self.assertLogs("accounts.views", level="ERROR") as captured:
            response = self.client.post(
                reverse("accounts:signup_form"),
                self.signup_data,
            )

        self.assertRedirects(
            response,
            reverse("accounts:signup_email_verify"),
            fetch_redirect_response=False,
        )
        post.assert_called_once()
        output = "\n".join(captured.output)
        self.assertIn("provider=brevo", output)
        self.assertIn("failure_class=brevo_authentication", output)
        self.assertIn("status_code=401", output)
        self.assertNotIn(self.signup_data["email"], output)
        self.assertNotIn("mock-api-key", output)
        self.assertNotIn("must not be logged", output)

        page = self.client.get(reverse("accounts:signup_email_verify"))
        self.assertContains(page, "Unable to send the verification email right now")
        self.assertNotContains(page, "A verification code has been sent")
        user = CustomUser.objects.get(email=self.signup_data["email"])
        self.assertFalse(user.is_active)
        challenge = EmailOTPChallenge.objects.get(
            user=user,
            purpose=EmailOTPChallenge.Purpose.SIGNUP,
        )
        self.assertIsNotNone(challenge.consumed_at)

    @patch(
        "accounts.email_otp.EmailOTPThrottle.objects.get_or_create",
        side_effect=OperationalError("table does not exist"),
    )
    @patch("accounts.email_otp.send_account_email")
    def test_signup_database_failure_is_categorized_and_skips_delivery(
        self,
        send_email,
        get_or_create,
    ):
        with self.assertLogs("accounts.views", level="ERROR") as captured:
            response = self.client.post(
                reverse("accounts:signup_form"),
                self.signup_data,
            )

        self.assertRedirects(
            response,
            reverse("accounts:signup_email_verify"),
            fetch_redirect_response=False,
        )
        get_or_create.assert_called_once()
        send_email.assert_not_called()
        output = "\n".join(captured.output)
        self.assertIn("failure_class=database_operational", output)
        self.assertNotIn("table does not exist", output)
        page = self.client.get(reverse("accounts:signup_email_verify"))
        self.assertContains(page, "Unable to send the verification email right now")
        self.assertNotContains(page, "A verification code has been sent")
        user = CustomUser.objects.get(email=self.signup_data["email"])
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_email_verified)

    def test_signup_can_resend_email_verification_code(self):
        self.client.post(reverse("accounts:signup_form"), self.signup_data)
        self.assertEqual(len(mail.outbox), 1)

        response = self.client.post(reverse("accounts:signup_email_verify_resend"))

        self.assertRedirects(
            response,
            reverse("accounts:signup_email_verify"),
            fetch_redirect_response=False,
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertContains(self.client.get(reverse("accounts:signup_email_verify")), "Please wait")

    def test_duplicate_email_is_rejected_with_login_guidance(self):
        CustomUser.objects.create_user(
            email=self.signup_data["email"], username="existing", password="StrongPass123!"
        )

        response = self.client.post(reverse("accounts:signup_form"), self.signup_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This email is already registered. Please login or use Forgot Password.")
        self.assertEqual(CustomUser.objects.filter(email=self.signup_data["email"]).count(), 1)

    def test_signup_rejects_invalid_email_and_password_mismatch(self):
        invalid_email = {**self.signup_data, "email": "not-an-email"}
        response = self.client.post(reverse("accounts:signup_form"), invalid_email)
        self.assertContains(response, "Enter a valid email address.")

        mismatch = {**self.signup_data, "confirm_password": "DifferentPass123!"}
        response = self.client.post(reverse("accounts:signup_form"), mismatch)
        self.assertContains(response, "The two password fields")
        self.assertContains(response, "didn")

    def test_signup_rejects_invalid_password_and_missing_required_fields(self):
        weak_password = {**self.signup_data, "password": "short", "confirm_password": "short"}
        response = self.client.post(reverse("accounts:signup_form"), weak_password)
        self.assertContains(response, "This password is too short")

        missing_terms = {key: value for key, value in self.signup_data.items() if key != "terms"}
        response = self.client.post(reverse("accounts:signup_form"), missing_terms)
        self.assertContains(response, "This field is required.")


@override_settings(
    EMAIL_PROVIDER="smtp",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@example.com",
    SITE_URL="https://web-lulumarket.onrender.com",
    DEBUG=True,
)
class PasswordResetFlowTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="reset@example.com",
            username="reset-user",
            password="OldStrongPass123!",
            is_active=True,
        )
        UserProfile.objects.create(
            user=self.user,
            phone="+919876543210",
            is_phone_verified=True,
        )

    def test_password_reset_page_loads(self):
        response = self.client.get(reverse("accounts:password_reset"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Send reset link")

    def test_existing_user_gets_one_reset_email_with_production_link(self):
        response = self.client.post(
            reverse("accounts:password_reset"), {"email": self.user.email}
        )

        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        reset_match = re.search(
            r"https://web-lulumarket\.onrender\.com/accounts/reset/[^\s]+", body
        )
        self.assertIsNotNone(reset_match)
        self.reset_path = urlparse(reset_match.group(0)).path
        self.assertIn("/accounts/reset/", self.reset_path)

    @override_settings(
        DEBUG=False,
        EMAIL_BACKEND="anymail.backends.brevo.EmailBackend",
        EMAIL_PROVIDER="brevo",
        BREVO_API_KEY="brevo-test-key",
        BREVO_SENDER_EMAIL="sender@example.com",
        BREVO_SENDER_NAME="NAGRI",
    )
    @patch(
        "accounts.email_delivery.requests.post",
        return_value=Mock(status_code=201, json=lambda: {"messageId": "test-message-id"}),
    )
    def test_password_reset_uses_brevo_with_https_reset_url(self, post):
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": self.user.email},
        )

        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        post.assert_called_once()
        url = post.call_args.args[0]
        headers = post.call_args.kwargs["headers"]
        payload = post.call_args.kwargs["json"]
        self.assertEqual(url, "https://api.brevo.com/v3/smtp/email")
        self.assertEqual(headers["api-key"], "brevo-test-key")
        self.assertEqual(payload["sender"]["email"], "sender@example.com")
        self.assertEqual(payload["to"], [{"email": self.user.email}])
        self.assertIn(
            f"https://web-lulumarket.onrender.com/accounts/reset/",
            payload["textContent"],
        )

    def test_reset_token_sets_new_password_and_old_password_fails(self):
        self.client.post(reverse("accounts:password_reset"), {"email": self.user.email})
        body = mail.outbox[0].body
        reset_url = re.search(
            r"https://web-lulumarket\.onrender\.com/accounts/reset/[^\s]+", body
        ).group(0)
        reset_path = urlparse(reset_url).path
        follow_redirect = self.client.get(reset_path)
        confirm_path = follow_redirect.url

        response = self.client.post(
            confirm_path,
            {
                "new_password1": "NewStrongPass456!",
                "new_password2": "NewStrongPass456!",
            },
        )
        self.assertRedirects(response, reverse("accounts:email_login"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewStrongPass456!"))

        old_login = self.client.post(
            reverse("accounts:email_login"),
            {"email": self.user.email, "password": "OldStrongPass123!"},
        )
        self.assertContains(old_login, "Invalid email or password.")
        new_login = self.client.post(
            reverse("accounts:email_login"),
            {"email": self.user.email, "password": "NewStrongPass456!"},
        )
        self.assertRedirects(new_login, reverse("accounts:dashboard_page"))

    def test_unknown_email_does_not_reveal_account_or_send_email(self):
        response = self.client.post(
            reverse("accounts:password_reset"), {"email": "unknown@example.com"}
        )

        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_inactive_user_does_not_receive_reset_email(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        response = self.client.post(
            reverse("accounts:password_reset"), {"email": self.user.email}
        )

        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_malformed_email_is_rejected_without_sending_email(self):
        response = self.client.post(
            reverse("accounts:password_reset"), {"email": "not-an-email"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a valid email address.")
        self.assertEqual(len(mail.outbox), 0)

    def test_delivery_failure_is_logged_safely_and_keeps_generic_response(self):
        failure_detail = "credential-sentinel reset-token-sentinel"
        with self.assertLogs("accounts.views", level="ERROR") as captured:
            with patch(
                "accounts.forms.SafePasswordResetForm.send_mail",
                side_effect=RuntimeError(failure_detail),
            ):
                response = self.client.post(
                    reverse("accounts:password_reset"),
                    {"email": self.user.email},
                )

        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        done_response = self.client.get(response.url)
        self.assertContains(
            done_response,
            "If an account with that email exists and email delivery is available",
        )
        log_output = "\n".join(captured.output)
        self.assertIn("error_type=RuntimeError", log_output)
        self.assertNotIn(self.user.email, log_output)
        self.assertNotIn(failure_detail, log_output)

    def test_invalid_reset_token_is_rejected(self):
        response = self.client.get(
            reverse(
                "accounts:password_reset_confirm",
                kwargs={"uidb64": "invalid", "token": "invalid-token"},
            )
        )
        self.assertContains(response, "invalid or expired", status_code=200)

    def test_expired_reset_token_is_rejected(self):
        self.client.post(
            reverse("accounts:password_reset"),
            {"email": self.user.email},
        )
        reset_url = re.search(
            r"https://web-lulumarket\.onrender\.com/accounts/reset/[^\s]+",
            mail.outbox[0].body,
        ).group(0)
        with override_settings(PASSWORD_RESET_TIMEOUT=-1):
            response = self.client.get(urlparse(reset_url).path)
        self.assertContains(response, "invalid or expired", status_code=200)

    @override_settings(
        DEBUG=False,
        EMAIL_PROVIDER="smtp",
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_HOST_USER="",
        EMAIL_HOST_PASSWORD="",
        DEFAULT_FROM_EMAIL="",
    )
    def test_missing_smtp_configuration_logs_safely_and_keeps_generic_response(self):
        with self.assertLogs("accounts.views", level="ERROR") as captured:
            response = self.client.post(
                reverse("accounts:password_reset"),
                {"email": self.user.email},
            )
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)
        log_output = "\n".join(captured.output)
        self.assertIn("EmailDeliveryConfigurationError", log_output)
        self.assertNotIn(self.user.email, log_output)


@override_settings(
    EMAIL_PROVIDER="smtp",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@example.com",
    DEBUG=True,
)
class EmailOTPFlowTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="email-otp@example.com",
            username="email-otp-user",
            password="EmailOtpStrongPass123!",
            is_active=True,
        )
        UserProfile.objects.create(
            user=self.user,
            phone="+919876543220",
            is_phone_verified=True,
        )

    def _request_code(self, url_name):
        response = self.client.post(
            reverse(url_name),
            {"email": self.user.email},
        )
        self.assertRedirects(
            response,
            reverse(
                "accounts:email_otp_login_verify"
                if url_name == "accounts:email_otp_login"
                else "accounts:password_reset_otp_verify"
            ),
        )
        self.assertEqual(len(mail.outbox), 1)
        code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group(0)
        challenge = EmailOTPChallenge.objects.latest("created_at")
        self.assertNotEqual(challenge.code_hash, code)
        self.assertTrue(check_password(code, challenge.code_hash))
        return code

    def test_email_otp_generation_and_successful_login_rotate_session(self):
        session = self.client.session
        session["existing"] = "session"
        session.save()
        previous_session_key = session.session_key
        code = self._request_code("accounts:email_otp_login")

        response = self.client.post(
            reverse("accounts:email_otp_login_verify"),
            {"email": self.user.email, "code": code},
        )
        self.assertRedirects(response, reverse("accounts:dashboard_page"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertNotEqual(self.client.session.session_key, previous_session_key)
        self.assertIsNotNone(
            EmailOTPChallenge.objects.latest("created_at").consumed_at
        )
        self.assertIsNone(
            verify_email_otp(
                self.user.email,
                code,
                EmailOTPChallenge.Purpose.LOGIN,
            )
        )

    def test_unknown_and_inactive_accounts_receive_no_email_or_account_specific_response(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        response = self.client.post(
            reverse("accounts:email_otp_login"),
            {"email": self.user.email},
        )
        self.assertRedirects(response, reverse("accounts:email_otp_login_verify"))
        self.assertEqual(len(mail.outbox), 0)
        page = self.client.get(response.url)
        self.assertContains(page, "If an eligible account exists")
        self.assertNotContains(page, "inactive")

        self.client.post(
            reverse("accounts:email_otp_login"),
            {"email": "unknown@example.com"},
        )
        self.assertEqual(len(mail.outbox), 0)

    def test_email_otp_rejects_incorrect_expired_and_reused_codes(self):
        code = self._request_code("accounts:email_otp_login")
        challenge = EmailOTPChallenge.objects.latest("created_at")
        challenge.expires_at = timezone.now() - timedelta(seconds=1)
        challenge.save(update_fields=["expires_at"])
        self.assertIsNone(
            verify_email_otp(
                self.user.email,
                code,
                EmailOTPChallenge.Purpose.LOGIN,
            )
        )

        throttle = EmailOTPThrottle.objects.get(
            purpose=EmailOTPThrottle.Purpose.LOGIN
        )
        throttle.last_requested_at = timezone.now() - timedelta(seconds=61)
        throttle.save(update_fields=["last_requested_at"])
        self.client.post(
            reverse("accounts:email_otp_login"),
            {"email": self.user.email},
        )
        new_code = re.search(r"\b\d{6}\b", mail.outbox[-1].body).group(0)
        self.assertIsNone(
            verify_email_otp(
                self.user.email,
                "wrong!",
                EmailOTPChallenge.Purpose.LOGIN,
            )
        )
        self.assertEqual(
            verify_email_otp(
                self.user.email,
                new_code,
                EmailOTPChallenge.Purpose.LOGIN,
            ),
            self.user,
        )
        self.assertIsNone(
            verify_email_otp(
                self.user.email,
                new_code,
                EmailOTPChallenge.Purpose.LOGIN,
            )
        )

    def test_email_otp_locks_after_five_incorrect_attempts(self):
        code = self._request_code("accounts:email_otp_login")
        for _ in range(5):
            self.assertIsNone(
                verify_email_otp(
                    self.user.email,
                    "incorrect",
                    EmailOTPChallenge.Purpose.LOGIN,
                )
            )
        challenge = EmailOTPChallenge.objects.latest("created_at")
        self.assertEqual(challenge.attempts, 5)
        self.assertIsNotNone(challenge.consumed_at)
        self.assertIsNone(
            verify_email_otp(
                self.user.email,
                code,
                EmailOTPChallenge.Purpose.LOGIN,
            )
        )

    def test_email_otp_enforces_resend_cooldown_and_hourly_limit(self):
        self._request_code("accounts:email_otp_login")
        response = self.client.post(
            reverse("accounts:email_otp_login"),
            {"email": self.user.email},
        )
        self.assertRedirects(response, reverse("accounts:email_otp_login_verify"))
        self.assertEqual(len(mail.outbox), 1)

        throttle = EmailOTPThrottle.objects.get(
            purpose=EmailOTPThrottle.Purpose.LOGIN
        )
        throttle.request_count = 5
        throttle.last_requested_at = timezone.now() - timedelta(seconds=61)
        throttle.save(update_fields=["request_count", "last_requested_at"])
        self.client.post(
            reverse("accounts:email_otp_login"),
            {"email": self.user.email},
        )
        self.assertEqual(len(mail.outbox), 1)

    def test_email_otp_delivery_error_is_generic_and_logged_without_secrets(self):
        with self.assertLogs("accounts.views", level="ERROR") as captured:
            with patch(
                "accounts.email_delivery.send_mail",
                side_effect=RuntimeError("otp-secret-token-secret"),
            ):
                response = self.client.post(
                    reverse("accounts:email_otp_login"),
                    {"email": self.user.email},
                )
        self.assertRedirects(response, reverse("accounts:email_otp_login_verify"))
        self.assertEqual(len(mail.outbox), 0)
        output = "\n".join(captured.output)
        self.assertIn("error_type=RuntimeError", output)
        self.assertNotIn(self.user.email, output)
        self.assertNotIn("otp-secret-token-secret", output)

    @override_settings(
        DEBUG=True,
        EMAIL_PROVIDER="brevo",
        EMAIL_BACKEND="anymail.backends.test.EmailBackend",
        ANYMAIL={
            "BREVO_API_KEY": "brevo-test-key",
            "SEND_DEFAULTS": {"reply_to": ["vikrampal505@yahoo.com"]},
        },
        BREVO_API_KEY="brevo-test-key",
        BREVO_SENDER_EMAIL="sender@example.com",
        DEFAULT_FROM_EMAIL="NAGRI <sender@example.com>",
    )
    def test_account_email_uses_brevo_compatible_backend_and_defaults(self):
        send_account_email("subject", "body", "recipient@example.com")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].anymail_test_params["from"].addr_spec,
            "sender@example.com",
        )
        self.assertEqual(
            mail.outbox[0].anymail_test_params["from"].display_name,
            "NAGRI",
        )
        self.assertEqual(
            mail.outbox[0].anymail_test_params["reply_to"][0].addr_spec,
            "vikrampal505@yahoo.com",
        )

    @override_settings(
        DEBUG=False,
        EMAIL_PROVIDER="brevo",
        EMAIL_BACKEND="anymail.backends.brevo.EmailBackend",
        ANYMAIL={"BREVO_API_KEY": "brevo-test-key"},
        DEFAULT_FROM_EMAIL="NAGRI <sender@example.com>",
    )
    @patch("requests.Session.request")
    def test_django_email_uses_brevo_https_api(self, request):
        response = Response()
        response.status_code = 201
        response._content = b'{"messageId":"mock-message-id"}'
        request.return_value = response

        message = EmailMessage(
            "subject",
            "body",
            "NAGRI <sender@example.com>",
            ["recipient@example.com"],
        )

        self.assertEqual(message.send(), 1)
        request_args = request.call_args.kwargs
        self.assertEqual(request_args["method"], "POST")
        self.assertTrue(request_args["url"].startswith("https://api.brevo.com/"))
        self.assertEqual(request_args["headers"]["api-key"], "brevo-test-key")
        self.assertEqual(
            json.loads(request_args["data"])["sender"]["email"],
            "sender@example.com",
        )

    @override_settings(
        DEBUG=False,
        EMAIL_PROVIDER="brevo",
        EMAIL_BACKEND="anymail.backends.brevo.EmailBackend",
        ANYMAIL={"BREVO_API_KEY": "brevo-test-key"},
        DEFAULT_FROM_EMAIL="NAGRI <sender@example.com>",
    )
    @patch("requests.Session.request")
    def test_django_email_api_rejection_raises_instead_of_reporting_success(
        self,
        request,
    ):
        response = Response()
        response.status_code = 401
        response.reason = "Unauthorized"
        response._content = b'{"message":"invalid key"}'
        request.return_value = response

        message = EmailMessage(
            "subject",
            "body",
            "NAGRI <sender@example.com>",
            ["recipient@example.com"],
        )

        with self.assertRaises(AnymailRequestsAPIError):
            message.send()

        request.assert_called_once()

    @override_settings(
        DEBUG=False,
        EMAIL_BACKEND="anymail.backends.brevo.EmailBackend",
        EMAIL_PROVIDER="brevo",
        BREVO_API_KEY="brevo-test-key",
        BREVO_SENDER_EMAIL="sender@example.com",
        BREVO_SENDER_NAME="NAGRI",
    )
    @patch(
        "accounts.email_delivery.requests.post",
        return_value=Mock(status_code=201, json=lambda: {"messageId": "test-message-id"}),
    )
    def test_email_otp_uses_brevo_api(self, post):
        response = self.client.post(
            reverse("accounts:email_otp_login"),
            {"email": self.user.email},
        )

        self.assertRedirects(response, reverse("accounts:email_otp_login_verify"))
        post.assert_called_once()
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["sender"], {
            "email": "sender@example.com",
            "name": "NAGRI",
        })
        self.assertEqual(payload["to"], [{"email": self.user.email}])
        self.assertRegex(payload["textContent"], r"code to sign in is \d{6}")

    @override_settings(
        DEBUG=False,
        EMAIL_BACKEND="anymail.backends.brevo.EmailBackend",
        EMAIL_PROVIDER="brevo",
        BREVO_API_KEY="brevo-test-key",
        BREVO_SENDER_EMAIL="sender@example.com",
    )
    @patch(
        "accounts.email_delivery.requests.post",
        return_value=Mock(status_code=401, json=lambda: {"message": "secret response"}),
    )
    def test_brevo_authentication_failure_does_not_fallback_to_smtp(self, post):
        with patch("accounts.email_delivery.send_mail") as smtp_send:
            with self.assertRaises(BrevoAPIError) as raised:
                send_account_email("subject", "body", "recipient@example.com")
        self.assertEqual(raised.exception.failure_class, "brevo_authentication")
        self.assertEqual(raised.exception.status_code, 401)
        post.assert_called_once()
        smtp_send.assert_not_called()

    @override_settings(
        DEBUG=False,
        EMAIL_BACKEND="anymail.backends.brevo.EmailBackend",
        EMAIL_PROVIDER="brevo",
        BREVO_API_KEY="brevo-test-key",
        BREVO_SENDER_EMAIL="sender@example.com",
    )
    @patch(
        "accounts.email_delivery.requests.post",
        return_value=Mock(status_code=201, json=lambda: {"unexpected": "shape"}),
    )
    def test_brevo_malformed_success_response_is_rejected(self, post):
        with self.assertRaises(BrevoAPIError) as raised:
            send_account_email("subject", "body", "recipient@example.com")
        self.assertEqual(raised.exception.failure_class, "brevo_malformed_response")
        self.assertEqual(raised.exception.status_code, 201)
        post.assert_called_once()

    @override_settings(
        DEBUG=False,
        EMAIL_BACKEND="anymail.backends.brevo.EmailBackend",
        EMAIL_PROVIDER="brevo",
        BREVO_API_KEY="brevo-test-key",
        BREVO_SENDER_EMAIL="sender@example.com",
    )
    @patch("accounts.email_delivery.requests.post", side_effect=Timeout())
    def test_brevo_timeout_is_classified_without_smtp_fallback(self, post):
        with patch("accounts.email_delivery.send_mail") as smtp_send:
            with self.assertRaises(Timeout):
                send_account_email("subject", "body", "recipient@example.com")
        self.assertEqual(
            classify_email_delivery_error(Timeout())[0],
            "brevo_timeout",
        )
        post.assert_called_once()
        smtp_send.assert_not_called()

    def test_smtp_authentication_failure_logs_only_safe_class_and_code(self):
        failure = smtplib.SMTPAuthenticationError(
            535,
            b"password-secret and reset-token-secret",
        )
        failure.smtp_code = 535
        with self.assertLogs("accounts.views", level="ERROR") as captured:
            with patch(
                "accounts.email_delivery.send_mail",
                side_effect=failure,
            ):
                response = self.client.post(
                    reverse("accounts:email_otp_login"),
                    {"email": self.user.email},
                )

        self.assertRedirects(response, reverse("accounts:email_otp_login_verify"))
        output = "\n".join(captured.output)
        self.assertIn("failure_class=smtp_authentication", output)
        self.assertIn("status_code=535", output)
        self.assertNotIn(self.user.email, output)
        self.assertNotIn("password-secret", output)
        self.assertNotIn("reset-token-secret", output)

    @override_settings(
        DEBUG=False,
        EMAIL_PROVIDER="smtp",
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
    )
    def test_production_console_backend_is_rejected_before_fake_success(self):
        with self.assertRaises(EmailDeliveryConfigurationError):
            send_account_email("Test", "Test", "recipient@example.com")

    def test_email_otp_password_recovery_resets_password_after_verification(self):
        code = self._request_code("accounts:password_reset_otp")
        response = self.client.post(
            reverse("accounts:password_reset_otp_verify"),
            {"email": self.user.email, "code": code},
        )
        self.assertRedirects(response, reverse("accounts:password_reset_otp_new"))

        response = self.client.post(
            reverse("accounts:password_reset_otp_new"),
            {
                "new_password1": "RecoveredStrongPass456!",
                "new_password2": "RecoveredStrongPass456!",
            },
        )
        self.assertRedirects(response, reverse("accounts:email_login"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("RecoveredStrongPass456!"))
        self.assertFalse(response.wsgi_request.user.is_authenticated)


class RoleBasedNavbarTests(TestCase):
    def setUp(self):
        self.client = self.client
        # Create users
        self.customer = CustomUser.objects.create_user(email="cust@example.com", password="pass123", username="cust")
        self.customer.is_active = True
        self.customer.save()
        UserProfile.objects.get_or_create(user=self.customer, defaults={"full_name": "Customer", "phone": "+919000000001", "is_phone_verified": True})

        self.seller = CustomUser.objects.create_user(email="seller@example.com", password="pass123", username="seller")
        self.seller.is_vendor = True
        self.seller.is_active = True
        self.seller.save()
        UserProfile.objects.get_or_create(user=self.seller, defaults={"full_name": "Seller", "phone": "+919000000002", "is_phone_verified": True})

        self.owner = CustomUser.objects.create_user(email="owner@example.com", password="pass123", username="owner")
        self.owner.is_owner = True
        self.owner.is_active = True
        self.owner.save()
        UserProfile.objects.get_or_create(user=self.owner, defaults={"full_name": "Owner", "phone": "+919000000003", "is_phone_verified": True})

    def _login(self, user):
        # Use force_login to avoid authentication backend differences in tests
        self.client.force_login(user)

    def test_customer_sees_become_seller(self):
        self._login(self.customer)
        resp = self.client.get(reverse("home"))
        self.assertContains(resp, "Become a Seller")

    def test_seller_sees_seller_dashboard(self):
        self._login(self.seller)
        resp = self.client.get(reverse("home"))
        self.assertContains(resp, "Seller Dashboard")
        self.assertNotContains(resp, "Become a Seller")

    def test_owner_sees_owner_dashboard(self):
        self._login(self.owner)
        resp = self.client.get(reverse("home"))
        self.assertContains(resp, "Owner Dashboard")

    def test_anonymous_user_sees_sign_in_without_logout(self):
        resp = self.client.get(reverse("home"))
        self.assertContains(resp, "Sign In")
        self.assertNotContains(resp, "Logout")

    def test_authenticated_roles_see_account_menu_and_logout(self):
        for user in (self.customer, self.seller, self.owner):
            with self.subTest(user=user.email):
                self._login(user)
                resp = self.client.get(reverse("home"))
                for menu_item in ("My Account", "My Orders", "Wishlist", "Saved Addresses", "Settings", "Logout"):
                    self.assertContains(resp, menu_item)
                self.assertContains(resp, reverse("accounts:logout_page"))
                self.client.logout()

    def test_logout_clears_session_and_protects_dashboard(self):
        self._login(self.customer)

        response = self.client.get(reverse("accounts:logout_page"))

        self.assertRedirects(response, reverse("home"))
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        dashboard_response = self.client.get(reverse("accounts:dashboard_page"))
        self.assertRedirects(
            dashboard_response,
            f"{reverse('accounts:login_page')}?next={reverse('accounts:dashboard_page')}",
        )

    def test_login_redirects_by_role(self):
        resp = self.client.post(reverse("accounts:email_login"), {"email": "seller@example.com", "password": "pass123"})
        # Should redirect to seller dashboard
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("sellers:dashboard"), resp.url)

        resp = self.client.post(reverse("accounts:email_login"), {"email": "owner@example.com", "password": "pass123"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("sellers:owner_dashboard"), resp.url)

        resp = self.client.post(reverse("accounts:email_login"), {"email": "cust@example.com", "password": "pass123"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("accounts:dashboard_page"), resp.url)
