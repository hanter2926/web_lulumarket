from datetime import timedelta
import json
import os
import smtplib

from anymail.exceptions import AnymailRequestsAPIError
from django.contrib import admin
from django.core import mail
from django.core.mail import EmailMessage
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import TestCase, Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.hashers import check_password
from unittest.mock import Mock, patch
from urllib.parse import urlencode, urlparse
import re
from requests import ConnectionError as RequestConnectionError
from requests import Response, Timeout

from .email_otp import request_email_otp, verify_email_otp
from .email_delivery import (
    BrevoAPIError,
    EmailDeliveryConfigurationError,
    classify_email_delivery_error,
    send_account_email,
    validate_email_delivery_configuration,
)
from .models import (
    Address,
    CustomUser,
    EmailOTPChallenge,
    EmailOTPThrottle,
    PendingSignup,
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


class AccountStatusAdminTests(TestCase):
    def test_admin_status_changes_keep_is_active_in_sync(self):
        user = CustomUser.objects.create_user(
            email="admin-status@example.com",
            username="admin-status",
            password="StrongPass123!",
        )
        user_admin = admin.site._registry[CustomUser]
        request = RequestFactory().post("/admin/accounts/customuser/")

        user.account_status = CustomUser.AccountStatus.ADMIN_DISABLED
        user_admin.save_model(request, user, form=None, change=True)
        user.refresh_from_db()
        self.assertFalse(user.is_active)

        user.account_status = CustomUser.AccountStatus.ACTIVE
        user_admin.save_model(request, user, form=None, change=True)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_create_admin_command_marks_account_status_active(self):
        with patch.dict(
            os.environ,
            {
                "ADMIN_EMAIL": "managed-admin@example.com",
                "ADMIN_PASSWORD": "StrongAdminPass123!",
                "ADMIN_USERNAME": "managed-admin",
            },
        ):
            call_command("create_admin", stdout=Mock())

        user = CustomUser.objects.get(email="managed-admin@example.com")
        self.assertTrue(user.is_active)
        self.assertEqual(user.account_status, CustomUser.AccountStatus.ACTIVE)

    def test_create_admin_refuses_to_reactivate_existing_disabled_account(self):
        user = CustomUser.objects.create_user(
            email="disabled-admin@example.com",
            username="disabled-admin",
            password="OriginalPass123!",
            is_active=False,
            is_staff=False,
            is_superuser=False,
            account_status=CustomUser.AccountStatus.ADMIN_DISABLED,
        )
        original_password = user.password

        with patch.dict(
            os.environ,
            {
                "ADMIN_EMAIL": user.email,
                "ADMIN_PASSWORD": "NewPass123!ShouldNotApply",
                "ADMIN_USERNAME": "managed-admin",
            },
        ):
            with self.assertRaises(CommandError):
                call_command("create_admin", stdout=Mock())

        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertEqual(user.account_status, CustomUser.AccountStatus.ADMIN_DISABLED)
        self.assertEqual(user.password, original_password)

    def test_admin_add_and_change_pages_sync_status_with_is_active(self):
        admin_user = CustomUser.objects.create_superuser(
            email="account-admin@example.com",
            username="account-admin",
            password="AdminPass123!",
        )
        self.client.force_login(admin_user)

        add_url = reverse("admin:accounts_customuser_add")
        self.assertEqual(self.client.get(add_url).status_code, 200)
        add_response = self.client.post(
            add_url,
            {
                "email": "created-disabled@example.com",
                "username": "created-disabled",
                "password1": "NewUserPass123!",
                "password2": "NewUserPass123!",
                "account_status": CustomUser.AccountStatus.ADMIN_DISABLED,
            },
        )
        self.assertEqual(add_response.status_code, 302)
        user = CustomUser.objects.get(email="created-disabled@example.com")
        self.assertFalse(user.is_active)
        self.assertEqual(user.account_status, CustomUser.AccountStatus.ADMIN_DISABLED)

        change_url = reverse(
            "admin:accounts_customuser_change", kwargs={"object_id": user.pk}
        )
        change_form_response = self.client.get(change_url)
        self.assertEqual(change_form_response.status_code, 200)
        date_joined = timezone.localtime(user.date_joined)
        change_response = self.client.post(
            change_url,
            {
                "username": user.username,
                "first_name": "",
                "last_name": "",
                "email": user.email,
                "date_joined_0": date_joined.strftime("%Y-%m-%d"),
                "date_joined_1": date_joined.strftime("%H:%M:%S"),
                "is_active": "on",
                "is_staff": "on",
                "is_superuser": "on",
                "account_status": CustomUser.AccountStatus.ACTIVE,
                "groups": [],
                "user_permissions": [],
            },
        )
        self.assertEqual(change_response.status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertEqual(user.account_status, CustomUser.AccountStatus.ACTIVE)


class PhoneOTPAPISecurityTests(TestCase):
    otp = "642951"

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            email="phone-api@example.com",
            username="phone-api-user",
            password="StrongPass123!",
            phone="+919876543210",
            is_active=True,
            is_email_verified=True,
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
                self.assertNotIn("pending_phone_otp", value)
                self.assertNotIn("pending_phone_otp_expires_at", value)
                for nested_value in value.values():
                    assert_no_otp_field(nested_value)
            elif isinstance(value, list):
                for nested_value in value:
                    assert_no_otp_field(nested_value)

        assert_no_otp_field(payload)

    @override_settings(
        EMAIL_PROVIDER="smtp",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
        DEBUG=True,
    )
    @patch("accounts.views.send_otp_to_phone")
    def test_public_registration_sends_email_otp_without_phone_otp(self, send_sms):
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

        for endpoint, payload in registration_payloads:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(
                    endpoint, payload, content_type="application/json"
                )

                self.assertEqual(response.status_code, 201)
                result = response.json()
                self._assert_otp_not_serialized(result)
                self.assertTrue(result["email_verification_required"])
                self.assertEqual(
                    result["verify_endpoint"],
                    reverse("accounts:signup_email_otp_verify"),
                )
                self.assertFalse(
                    CustomUser.objects.filter(email=payload["email"]).exists()
                )
                pending = PendingSignup.objects.get(email=payload["email"])
                self.assertTrue(
                    check_password(payload["password"], pending.password_hash)
                )

        self.assertEqual(len(mail.outbox), 2)
        send_sms.assert_not_called()

    @override_settings(
        EMAIL_PROVIDER="smtp",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
        DEBUG=True,
    )
    def test_api_signup_email_verification_activates_only_matching_user(self):
        payload = {
            "email": "verified-api-signup@example.com",
            "username": "verified-api-signup",
            "password": "StrongPass123!",
            "phone": "+919876543217",
        }
        response = self.client.post(
            reverse("accounts:users-register"),
            payload,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)

        self.assertFalse(
            CustomUser.objects.filter(email=payload["email"]).exists()
        )
        code = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        response = self.client.post(
            reverse("accounts:signup_email_otp_verify"),
            {"email": payload["email"], "code": code},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        user = CustomUser.objects.get(email=payload["email"])
        user.refresh_from_db()
        self.assertTrue(user.is_email_verified)
        self.assertTrue(user.is_active)
        self.assertEqual(user.account_status, CustomUser.AccountStatus.ACTIVE)

        other = CustomUser.objects.create_user(
            email="unrelated-pending@example.com",
            username="unrelated-pending",
            password="StrongPass123!",
            is_active=False,
            is_email_verified=False,
            account_status=CustomUser.AccountStatus.PENDING_VERIFICATION,
        )
        self.assertFalse(other.is_active)
        self.assertFalse(other.is_email_verified)

        response = self.client.post(
            reverse("accounts:signup_email_otp_verify"),
            {"email": other.email, "code": code},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        other.refresh_from_db()
        self.assertFalse(other.is_active)
        self.assertFalse(other.is_email_verified)

    @override_settings(
        EMAIL_PROVIDER="smtp",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
        DEBUG=True,
    )
    def test_duplicate_pending_signup_cannot_replace_staged_password(self):
        payload = {
            "email": "staged-password@example.com",
            "username": "staged-password",
            "password": "OriginalStrongPass123!",
            "phone": "+919876543216",
        }
        response = self.client.post(
            reverse("accounts:users-register"),
            payload,
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        pending = PendingSignup.objects.get(email=payload["email"])
        original_password_hash = pending.password_hash

        duplicate_response = self.client.post(
            reverse("accounts:users-register"),
            {
                **payload,
                "password": "AttackerChosenPass123!",
                "phone": "+919876543215",
            },
            content_type="application/json",
        )
        self.assertEqual(duplicate_response.status_code, 409)
        pending.refresh_from_db()
        self.assertEqual(pending.password_hash, original_password_hash)
        self.assertEqual(len(mail.outbox), 1)
        self.assertFalse(
            CustomUser.objects.filter(email=payload["email"]).exists()
        )

        code = re.search(r"\b(\d{6})\b", mail.outbox[0].body).group(1)
        verify_response = self.client.post(
            reverse("accounts:signup_email_otp_verify"),
            {"email": payload["email"], "code": code},
            content_type="application/json",
        )
        self.assertEqual(verify_response.status_code, 200)
        user = CustomUser.objects.get(email=payload["email"])
        self.assertTrue(user.check_password("OriginalStrongPass123!"))
        self.assertFalse(user.check_password("AttackerChosenPass123!"))

    @override_settings(
        EMAIL_PROVIDER="smtp",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
        DEBUG=True,
    )
    def test_signup_submit_email_otp_must_be_verified_before_activation(self):
        email = "signup-submit-verification@example.com"
        response = self.client.post(
            reverse("accounts:signup_submit"),
            {
                "email": email,
                "password": "StrongPass123!",
                "phone": "9876543219",
                "full_name": "Signup Submit",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(CustomUser.objects.filter(email=email).exists())
        PendingSignup.objects.get(email=email)
        code = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        wrong_code = "000000" if code != "000000" else "000001"

        response = self.client.post(
            reverse("accounts:signup_email_otp_verify"),
            {"email": email, "code": wrong_code},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CustomUser.objects.filter(email=email).exists())

        response = self.client.post(
            reverse("accounts:signup_email_otp_verify"),
            {"email": email, "code": code},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        user = CustomUser.objects.get(email=email)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_email_verified)
        self.assertEqual(user.account_status, CustomUser.AccountStatus.ACTIVE)

    def test_api_registration_rejects_missing_or_invalid_phone_before_creating_user(self):
        initial_count = CustomUser.objects.count()
        payloads = (
            {
                "email": "missing-phone@example.com",
                "username": "missing-phone",
                "password": "StrongPass123!",
            },
            {
                "email": "invalid-phone@example.com",
                "username": "invalid-phone",
                "password": "StrongPass123!",
                "phone": "not-a-phone",
            },
            {
                "email": "not-an-email",
                "password": "StrongPass123!",
                "phone": "+919876543214",
            },
        )

        for payload in payloads:
            with self.subTest(email=payload["email"]):
                response = self.client.post(
                    reverse("accounts:users-register"),
                    payload,
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertFalse(
                    CustomUser.objects.filter(email=payload["email"]).exists()
                )

        self.assertEqual(CustomUser.objects.count(), initial_count)

    def test_signup_submit_rejects_invalid_email_before_staging(self):
        response = self.client.post(
            reverse("accounts:signup_submit"),
            {
                "email": "invalid-email",
                "password": "StrongPass123!",
                "phone": "+919876543214",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Enter a valid email address.")
        self.assertFalse(PendingSignup.objects.exists())
        self.assertFalse(CustomUser.objects.filter(email="invalid-email").exists())

    @override_settings(
        EMAIL_PROVIDER="smtp",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
        DEBUG=True,
    )
    def test_api_signup_email_delivery_failure_keeps_retryable_pending_account(self):
        email = "retryable-signup@example.com"
        phone = "+919876543211"
        with patch(
            "accounts.email_otp.send_account_email",
            side_effect=RuntimeError("mail provider unavailable"),
        ):
            with self.assertLogs("accounts.views", level="ERROR"):
                response = self.client.post(
                    reverse("accounts:users-register"),
                    {
                        "email": email,
                        "username": "retryable-signup",
                        "password": "StrongPass123!",
                        "phone": phone,
                    },
                    content_type="application/json",
                )

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["resend_endpoint"],
            reverse("accounts:signup_email_otp_resend"),
        )
        self.assertFalse(CustomUser.objects.filter(email=email).exists())
        self.assertTrue(PendingSignup.objects.filter(email=email).exists())

        throttle = EmailOTPThrottle.objects.get(
            purpose=EmailOTPThrottle.Purpose.SIGNUP,
        )
        throttle.last_requested_at = timezone.now() - timedelta(seconds=11)
        throttle.save(update_fields=["last_requested_at"])
        retry_response = self.client.post(
            reverse("accounts:signup_email_otp_resend"),
            {"email": email},
            content_type="application/json",
        )
        self.assertEqual(retry_response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(
        EMAIL_PROVIDER="smtp",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
        DEBUG=True,
    )
    def test_legacy_signup_resend_route_does_not_send_phone_otp(self):
        email = "legacy-resend@example.com"
        phone = "+919876543211"
        user = CustomUser.objects.create_user(
            email=email,
            username="legacy-resend",
            password="StrongPass123!",
            phone=phone,
            is_active=False,
            is_email_verified=False,
            account_status=CustomUser.AccountStatus.PENDING_VERIFICATION,
        )
        UserProfile.objects.create(user=user, phone=phone)

        with patch("accounts.views.send_otp_to_phone") as send_sms:
            response = self.client.post(
                reverse("accounts:signup_phone_otp_resend"),
                {"email": email, "phone": phone},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("may be sent", response.json()["detail"])
        send_sms.assert_not_called()
        self.assertEqual(len(mail.outbox), 1)

    def test_phone_otp_cannot_activate_pending_email_unverified_signup(self):
        user = CustomUser.objects.create_user(
            email="phone-cannot-activate@example.com",
            username="phone-cannot-activate",
            password="StrongPass123!",
            phone="+919876543218",
            is_active=False,
            is_email_verified=False,
            account_status=CustomUser.AccountStatus.PENDING_VERIFICATION,
        )
        profile = UserProfile.objects.create(
            user=user,
            phone=user.phone,
            otp=self.otp,
            otp_expires_at=timezone.now() + timedelta(minutes=5),
        )
        response = self.client.post(
            reverse("accounts:verify_otp"),
            {"phone": user.phone, "otp": self.otp},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        user.refresh_from_db()
        profile.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_email_verified)
        self.assertEqual(
            user.account_status,
            CustomUser.AccountStatus.PENDING_VERIFICATION,
        )
        self.assertFalse(profile.is_phone_verified)

    @override_settings(
        EMAIL_PROVIDER="smtp",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
        DEBUG=True,
    )
    def test_api_password_login_requires_email_verification_but_not_phone_verification(self):
        self.profile.is_phone_verified = False
        self.profile.save(update_fields=["is_phone_verified", "updated_at"])
        wrong_password_response = self.client.post(
            reverse("accounts:users-login"),
            {"email": self.user.email, "password": "wrong-password"},
            content_type="application/json",
        )
        self.assertEqual(wrong_password_response.status_code, 401)

        response = self.client.post(
            reverse("accounts:users-login"),
            {"email": self.user.email, "password": "StrongPass123!"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())

        self.user.is_email_verified = False
        self.user.save(update_fields=["is_email_verified", "updated_at"])
        response = self.client.post(
            reverse("accounts:users-login"),
            {"email": self.user.email, "password": "StrongPass123!"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("Verify your email", response.json()["detail"])

        self.user.is_email_verified = True
        self.user.is_active = False
        self.user.account_status = CustomUser.AccountStatus.ADMIN_DISABLED
        self.user.save(
            update_fields=["is_email_verified", "is_active", "account_status"]
        )
        response = self.client.post(
            reverse("accounts:users-login"),
            {"email": self.user.email, "password": "StrongPass123!"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("inactive", response.json()["detail"])


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

    def test_shared_phone_otp_attempt_limit_applies_to_both_verification_routes(self):
        endpoints = (
            reverse("accounts:verify_otp"),
            reverse("accounts:users-phone-login"),
        )
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                self.profile.otp = self.otp
                self.profile.otp_expires_at = timezone.now() + timedelta(minutes=5)
                self.profile.otp_attempts = 0
                self.profile.save(
                    update_fields=[
                        "otp",
                        "otp_expires_at",
                        "otp_attempts",
                        "updated_at",
                    ]
                )

                for attempt in range(5):
                    response = self.client.post(
                        endpoint,
                        {"phone": self.user.phone, "otp": "000000"},
                        content_type="application/json",
                    )
                    self.assertEqual(
                        response.status_code,
                        429 if attempt == 4 else 400,
                    )

                self.profile.refresh_from_db()
                self.assertEqual(self.profile.otp_attempts, 5)
                self.assertFalse(self.profile.otp)
                locked_response = self.client.post(
                    endpoint,
                    {"phone": self.user.phone, "otp": self.otp},
                    content_type="application/json",
                )
                self.assertEqual(locked_response.status_code, 429)
                self.profile.refresh_from_db()
                self.assertTrue(self.profile.is_phone_verified)

    @patch("accounts.views.send_otp_to_phone", return_value={"status": "sent"})
    def test_phone_otp_request_cooldown_is_enforced_atomically(self, send_otp):
        now = timezone.now()
        with patch("accounts.views.timezone.now", return_value=now):
            first_response = self.client.post(
                reverse("accounts:request_otp"),
                {"phone": self.user.phone},
                content_type="application/json",
            )
            second_response = self.client.post(
                reverse("accounts:request_otp"),
                {"phone": self.user.phone},
                content_type="application/json",
            )

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 429)
        self.assertIn("wait", second_response.json()["detail"].lower())
        send_otp.assert_called_once()

    @patch("accounts.views.send_otp_to_phone", return_value={"status": "sent"})
    def test_phone_otp_hourly_request_limit_and_cooldown(self, send_otp):
        start = timezone.now()
        with patch(
            "accounts.views.timezone.now",
            side_effect=lambda: start
            + timedelta(seconds=61 * send_otp.call_count),
        ):
            for _ in range(5):
                response = self.client.post(
                    reverse("accounts:request_otp"),
                    {"phone": self.user.phone},
                    content_type="application/json",
                )
                self.assertEqual(response.status_code, 200)

            limited_response = self.client.post(
                reverse("accounts:request_otp"),
                {"phone": self.user.phone},
                content_type="application/json",
            )

        self.assertEqual(limited_response.status_code, 429)
        self.assertIn("hourly", limited_response.json()["detail"].lower())
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.otp_request_count, 5)
        self.assertEqual(send_otp.call_count, 5)

    @patch("accounts.views.send_otp_to_phone", return_value={"status": "sent"})
    def test_new_phone_otp_resets_failed_attempts(self, send_otp):
        self.profile.otp_attempts = 4
        self.profile.last_otp_sent_at = timezone.now() - timedelta(seconds=61)
        self.profile.save(
            update_fields=["otp_attempts", "last_otp_sent_at", "updated_at"]
        )

        response = self.client.post(
            reverse("accounts:request_otp"),
            {"phone": self.user.phone},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.otp_attempts, 0)
        send_otp.assert_called_once()

    def test_phone_login_cannot_activate_pending_signup(self):
        self.user.is_active = False
        self.user.account_status = CustomUser.AccountStatus.PENDING_VERIFICATION
        self.profile.is_phone_verified = False
        self.profile.otp_expires_at = timezone.now() + timedelta(minutes=5)
        self.profile.save(
            update_fields=["is_phone_verified", "otp_expires_at", "updated_at"]
        )
        self.user.save(
            update_fields=["account_status", "is_active", "updated_at"]
        )

        response = self.client.post(
            reverse("accounts:users-phone-login"),
            {"phone": self.user.phone, "otp": self.otp},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(
            self.user.account_status,
            CustomUser.AccountStatus.PENDING_VERIFICATION,
        )

    def test_phone_otp_cannot_reactivate_inactive_phone_verified_account(self):
        self.user.is_active = False
        self.user.account_status = CustomUser.AccountStatus.ADMIN_DISABLED
        self.user.save(update_fields=["account_status", "is_active", "updated_at"])
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
        self.user.account_status = CustomUser.AccountStatus.ADMIN_DISABLED
        self.user.save(update_fields=["account_status", "is_active", "updated_at"])

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

    @patch("accounts.views.send_otp_to_phone", return_value={"status": "sent"})
    def test_phone_change_keeps_old_verified_number_until_new_number_is_confirmed(
        self, send_otp
    ):
        self.client.force_login(self.user)
        new_phone = "+919876543211"
        with patch("accounts.views.generate_otp", return_value=self.otp):
            response = self.client.post(
                reverse("accounts:users-phone-change-request"),
                {"phone": new_phone},
                content_type="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self._assert_otp_not_serialized(response.json())
        send_otp.assert_called_once_with(new_phone, self.otp)
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.user.phone, "+919876543210")
        self.assertEqual(self.profile.phone, "+919876543210")
        self.assertTrue(self.profile.is_phone_verified)
        self.assertEqual(self.profile.pending_phone, new_phone)
        self.assertEqual(self.profile.pending_phone_otp, self.otp)

    @patch("accounts.views.send_otp_to_phone", return_value={"status": "sent"})
    def test_phone_change_verification_promotes_new_number_and_consumes_code(
        self, send_otp
    ):
        self.client.force_login(self.user)
        new_phone = "+919876543211"
        with patch("accounts.views.generate_otp", return_value=self.otp):
            request_response = self.client.post(
                reverse("accounts:users-phone-change-request"),
                {"phone": new_phone},
                content_type="application/json",
            )
        self.assertEqual(request_response.status_code, 200)

        response = self.client.post(
            reverse("accounts:users-phone-change-verify"),
            {"otp": self.otp},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self._assert_otp_not_serialized(response.json())
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.user.phone, new_phone)
        self.assertEqual(self.profile.phone, new_phone)
        self.assertTrue(self.profile.is_phone_verified)
        self.assertIsNone(self.profile.pending_phone)
        self.assertIsNone(self.profile.pending_phone_otp)
        self.assertIsNone(self.profile.pending_phone_otp_expires_at)

    def test_invalid_or_expired_phone_change_code_preserves_old_verified_number(self):
        self.client.force_login(self.user)
        self.profile.pending_phone = "+919876543211"
        self.profile.pending_phone_otp = self.otp
        self.profile.pending_phone_otp_expires_at = timezone.now() + timedelta(minutes=5)
        self.profile.save(
            update_fields=[
                "pending_phone",
                "pending_phone_otp",
                "pending_phone_otp_expires_at",
                "updated_at",
            ]
        )

        invalid_response = self.client.post(
            reverse("accounts:users-phone-change-verify"),
            {"otp": "000000"},
            content_type="application/json",
        )
        self.assertEqual(invalid_response.status_code, 400)

        self.profile.pending_phone_otp_expires_at = timezone.now() - timedelta(seconds=1)
        self.profile.save(update_fields=["pending_phone_otp_expires_at", "updated_at"])
        expired_response = self.client.post(
            reverse("accounts:users-phone-change-verify"),
            {"otp": self.otp},
            content_type="application/json",
        )

        self.assertEqual(expired_response.status_code, 400)
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.user.phone, "+919876543210")
        self.assertEqual(self.profile.phone, "+919876543210")
        self.assertTrue(self.profile.is_phone_verified)
        self.assertEqual(self.profile.pending_phone, "+919876543211")

    def test_phone_change_verification_rejects_a_number_claimed_after_request(self):
        self.client.force_login(self.user)
        new_phone = "+919876543211"
        self.profile.pending_phone = new_phone
        self.profile.pending_phone_otp = self.otp
        self.profile.pending_phone_otp_expires_at = timezone.now() + timedelta(minutes=5)
        self.profile.save(
            update_fields=[
                "pending_phone",
                "pending_phone_otp",
                "pending_phone_otp_expires_at",
                "updated_at",
            ]
        )
        CustomUser.objects.create_user(
            email="claimed-phone@example.com",
            username="claimed-phone",
            password="StrongPass123!",
            phone=new_phone,
        )

        response = self.client.post(
            reverse("accounts:users-phone-change-verify"),
            {"otp": self.otp},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.user.phone, "+919876543210")
        self.assertEqual(self.profile.phone, "+919876543210")
        self.assertTrue(self.profile.is_phone_verified)
        self.assertEqual(self.profile.pending_phone, new_phone)

    def test_phone_change_otp_locks_after_five_incorrect_attempts(self):
        self.client.force_login(self.user)
        self.profile.pending_phone = "+919876543211"
        self.profile.pending_phone_otp = self.otp
        self.profile.pending_phone_otp_expires_at = timezone.now() + timedelta(minutes=5)
        self.profile.pending_phone_otp_attempts = 0
        self.profile.save(
            update_fields=[
                "pending_phone",
                "pending_phone_otp",
                "pending_phone_otp_expires_at",
                "pending_phone_otp_attempts",
                "updated_at",
            ]
        )

        for attempt in range(5):
            response = self.client.post(
                reverse("accounts:users-phone-change-verify"),
                {"otp": "000000"},
                content_type="application/json",
            )
            expected_status = 429 if attempt == 4 else 400
            self.assertEqual(response.status_code, expected_status)

        correct_code_response = self.client.post(
            reverse("accounts:users-phone-change-verify"),
            {"otp": self.otp},
            content_type="application/json",
        )
        self.assertEqual(correct_code_response.status_code, 429)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.pending_phone_otp_attempts, 5)
        self.assertIsNone(self.profile.pending_phone_otp)
        self.assertEqual(self.profile.phone, "+919876543210")
        self.assertTrue(self.profile.is_phone_verified)

    def test_profile_and_user_apis_cannot_bypass_phone_verification(self):
        new_phone = "+919876543211"
        self.client.force_login(self.user)
        user_response = self.client.patch(
            reverse("accounts:users-detail", kwargs={"pk": self.user.pk}),
            {"phone": new_phone},
            content_type="application/json",
        )
        profile_response = self.client.patch(
            reverse("accounts:profiles-update-profile"),
            {"phone": new_phone},
            content_type="application/json",
        )

        self.assertEqual(user_response.status_code, 200)
        self.assertEqual(profile_response.status_code, 200)
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.user.phone, "+919876543210")
        self.assertEqual(self.profile.phone, "+919876543210")
        self.assertTrue(self.profile.is_phone_verified)
        self.assertIsNone(self.profile.pending_phone)

    @patch("accounts.views.send_otp_to_phone", side_effect=RuntimeError("otp-secret failure"))
    def test_phone_change_delivery_error_does_not_log_otp_or_exception_text(self, send_otp):
        self.client.force_login(self.user)
        with patch("accounts.views.generate_otp", return_value=self.otp):
            with self.assertLogs("accounts.views", level="ERROR") as captured:
                response = self.client.post(
                    reverse("accounts:users-phone-change-request"),
                    {"phone": "+919876543211"},
                    content_type="application/json",
                )

        self.assertEqual(response.status_code, 500)
        log_output = "\n".join(captured.output)
        self.assertNotIn(self.otp, log_output)
        self.assertNotIn("otp-secret failure", log_output)
        send_otp.assert_called_once()

    def test_admin_disabled_account_cannot_be_activated_by_phone_otp(self):
        self.user.is_active = False
        self.user.account_status = CustomUser.AccountStatus.ADMIN_DISABLED
        self.profile.is_phone_verified = False
        self.profile.save(update_fields=["is_phone_verified", "updated_at"])
        self.user.save(update_fields=["account_status", "is_active", "updated_at"])

        response = self.client.post(
            reverse("accounts:verify_otp"),
            {"phone": self.user.phone, "otp": self.otp},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(
            self.user.account_status,
            CustomUser.AccountStatus.ADMIN_DISABLED,
        )

    def test_pending_signup_account_cannot_be_activated_by_phone_otp(self):
        self.user.is_active = False
        self.user.is_email_verified = False
        self.user.account_status = CustomUser.AccountStatus.PENDING_VERIFICATION
        self.profile.is_phone_verified = False
        self.profile.save(update_fields=["is_phone_verified", "updated_at"])
        self.user.save(
            update_fields=[
                "account_status",
                "is_active",
                "is_email_verified",
                "updated_at",
            ]
        )

        response = self.client.post(
            reverse("accounts:verify_otp"),
            {"phone": self.user.phone, "otp": self.otp},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertFalse(self.user.is_email_verified)
        self.assertEqual(
            self.user.account_status,
            CustomUser.AccountStatus.PENDING_VERIFICATION,
        )
        self.assertFalse(self.profile.is_phone_verified)


class AccountSecurityTests(TestCase):
    @override_settings(
        EMAIL_PROVIDER="smtp",
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        DEFAULT_FROM_EMAIL="noreply@example.com",
        DEBUG=True,
    )
    @patch("accounts.views.send_otp_to_phone")
    def test_password_login_rejects_unverified_users_without_requesting_login_otp(
        self, send_sms
    ):
        user = CustomUser.objects.create_user(
            email="contact-flow@example.com",
            username="contact-flow-user",
            password="StrongPass123",
            phone="+919876543217",
            is_active=True,
        )
        UserProfile.objects.create(
            user=user,
            phone=user.phone,
            is_phone_verified=False,
        )

        response = self.client.post(
            reverse("accounts:email_login"),
            {
                "email": user.email,
                "password": "StrongPass123",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Verify your email before logging in.")
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertEqual(len(mail.outbox), 0)
        send_sms.assert_not_called()
        user.refresh_from_db()
        profile = UserProfile.objects.get(user=user)
        self.assertFalse(user.is_email_verified)
        self.assertFalse(profile.is_phone_verified)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_legacy_contact_verification_url_does_not_send_email_otp(self):
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

        response = self.client.get(reverse("accounts:verify_contacts"))

        self.assertRedirects(response, reverse("accounts:email_login"))
        self.assertEqual(len(mail.outbox), 0)

    def test_verified_user_can_log_in_with_email_and_password(self):
        user = CustomUser.objects.create_user(
            email="verified@example.com",
            username="verified-user",
            password="StrongPass123",
            phone="+919876543211",
            is_active=True,
            is_email_verified=True,
        )
        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.phone = user.phone
        profile.is_phone_verified = True
        profile.save(update_fields=["phone", "is_phone_verified", "updated_at"])

        response = self.client.post(reverse("accounts:email_login"), {"email": "verified@example.com", "password": "StrongPass123"})

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:dashboard_page"), response.url)
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_pending_signup_with_correct_password_is_sent_to_email_verification(self):
        user = CustomUser.objects.create_user(
            email="pending-signup@example.com",
            username="pending-signup",
            password="StrongPass123",
            is_active=False,
            is_email_verified=False,
            account_status=CustomUser.AccountStatus.PENDING_VERIFICATION,
        )

        response = self.client.post(
            reverse("accounts:email_login"),
            {"email": user.email, "password": "StrongPass123"},
        )

        self.assertRedirects(
            response,
            reverse("accounts:signup_email_verify"),
            fetch_redirect_response=False,
        )
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertEqual(
            self.client.session["signup_email_verification_email"],
            user.email,
        )

    def test_verified_user_can_log_in_with_case_variant_email(self):
        user = CustomUser.objects.create_user(
            email="case@example.com",
            username="case-user",
            password="StrongPass123",
            is_active=True,
            is_email_verified=True,
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
            is_email_verified=True,
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
            is_email_verified=True,
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
            is_email_verified=True,
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

    def test_generic_user_create_requires_email_verification(self):
        email = "generic-user-create@example.com"
        response = self.client.post(
            reverse("accounts:users-list"),
            {
                "email": email,
                "username": "generic-user-create",
                "password": "StrongSignupPass123!",
                "phone": "9876543218",
                "full_name": "Generic User",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["email_verification_required"])
        self.assertFalse(CustomUser.objects.filter(email=email).exists())
        PendingSignup.objects.get(email=email)

        login_response = self.client.post(
            reverse("accounts:email_login"),
            {"email": email, "password": "StrongSignupPass123!"},
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertContains(login_response, "Invalid email or password.")
        self.assertFalse(login_response.wsgi_request.user.is_authenticated)

        code = re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)
        verify_response = self.client.post(
            reverse("accounts:signup_email_otp_verify"),
            {"email": email, "code": code},
            content_type="application/json",
        )
        self.assertEqual(verify_response.status_code, 200)
        user = CustomUser.objects.get(email=email)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_email_verified)
        self.assertEqual(user.account_status, CustomUser.AccountStatus.ACTIVE)

    def test_login_page_has_one_registration_option_and_no_otp_login_link(self):
        response = self.client.get(reverse("accounts:login_page"))

        self.assertContains(response, "Create an account")
        self.assertNotContains(response, "Login with Email OTP")
        self.assertNotContains(response, 'data-auth-panel="register"')
        self.assertNotContains(response, "data-auth-switch=\"register\"")

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
        self.assertFalse(
            CustomUser.objects.filter(email=self.signup_data["email"]).exists()
        )
        pending = PendingSignup.objects.get(email=self.signup_data["email"])
        self.assertTrue(
            check_password(self.signup_data["password"], pending.password_hash)
        )
        self.assertNotEqual(pending.password_hash, self.signup_data["password"])
        send_otp.assert_not_called()

        code = re.search(r"\b(\d{6})\b", mail.outbox[0].body).group(1)
        response = self.client.post(
            reverse("accounts:signup_email_verify"),
            {"email": self.signup_data["email"], "code": code},
        )

        self.assertRedirects(
            response,
            reverse("accounts:dashboard_page"),
            fetch_redirect_response=False,
        )
        user = CustomUser.objects.get(email=self.signup_data["email"])
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.is_email_verified)
        self.assertEqual(user.account_status, CustomUser.AccountStatus.ACTIVE)
        self.assertFalse(UserProfile.objects.get(user=user).is_phone_verified)
        self.assertTrue(response.wsgi_request.user.is_authenticated)
        self.assertEqual(
            self.client.session.get("_auth_user_id"),
            str(user.pk),
        )

        self.client.get(reverse("accounts:logout_page"))
        mail.outbox.clear()
        response = self.client.post(
            reverse("accounts:email_login"),
            {
                "email": self.signup_data["email"],
                "password": self.signup_data["password"],
            },
        )
        self.assertRedirects(response, reverse("accounts:dashboard_page"))
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(
        DEBUG=False,
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
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
        self.assertFalse(
            CustomUser.objects.filter(email=self.signup_data["email"]).exists()
        )
        challenge = EmailOTPChallenge.objects.get(
            purpose=EmailOTPChallenge.Purpose.SIGNUP,
            user__isnull=True,
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
            status_code=403,
            json=lambda: {
                "code": "unauthorized",
                "message": (
                    "Invalid API key mock-api-key for user@example.com. "
                    "OTP 123456; Authorization: Bearer secret-token"
                ),
            },
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
        self.assertIn("failure_class=brevo_forbidden", output)
        self.assertIn("safe_detail=Brevo returned HTTP 403 Forbidden", output)
        self.assertIn("status_code=403", output)
        self.assertIn("brevo_error_code=unauthorized", output)
        self.assertIn("brevo_error_message=", output)
        self.assertNotIn(self.signup_data["email"], output)
        self.assertNotIn("mock-api-key", output)
        self.assertNotIn("user@example.com", output)
        self.assertNotIn("123456", output)
        self.assertNotIn("secret-token", output)
        self.assertIn("[redacted]", output)
        payload = post.call_args.kwargs["json"]
        self.assertNotIn(payload["textContent"], output)
        otp = re.search(r"\b\d{6}\b", payload["textContent"]).group(0)
        self.assertNotIn(otp, output)

        page = self.client.get(reverse("accounts:signup_email_verify"))
        self.assertContains(page, "Unable to send the verification email right now")
        self.assertNotContains(page, "A verification code has been sent")
        self.assertFalse(
            CustomUser.objects.filter(email=self.signup_data["email"]).exists()
        )
        self.assertTrue(
            PendingSignup.objects.filter(email=self.signup_data["email"]).exists()
        )
        challenge = EmailOTPChallenge.objects.get(
            purpose=EmailOTPChallenge.Purpose.SIGNUP,
            user__isnull=True,
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
        self.assertFalse(
            CustomUser.objects.filter(email=self.signup_data["email"]).exists()
        )
        self.assertTrue(
            PendingSignup.objects.filter(email=self.signup_data["email"]).exists()
        )

    @patch(
        "accounts.email_otp.EmailOTPChallenge.objects.select_for_update",
        side_effect=OperationalError(
            "Database detail: private@example.com OTP 123456 password secret"
        ),
    )
    def test_signup_verification_database_failure_is_logged_without_sensitive_data(
        self,
        select_for_update,
    ):
        email = "private@example.com"
        code = "123456"
        self.client.raise_request_exception = False
        session = self.client.session
        session["signup_email_verification_email"] = email
        session.save()

        with self.assertLogs("accounts.views", level="ERROR") as captured:
            response = self.client.post(
                reverse("accounts:signup_email_verify"),
                {"email": email, "code": code},
            )

        self.assertEqual(response.status_code, 500)
        select_for_update.assert_called_once()
        output = "\n".join(captured.output)
        self.assertIn("Signup email verification request failed", output)
        self.assertIn("OperationalError", output)
        self.assertNotIn(email, output)
        self.assertNotIn(code, output)
        self.assertNotIn("password secret", output)
        self.assertTrue(
            self.client.session.get("signup_email_verification_email")
        )
        self.assertFalse(CustomUser.objects.filter(email=email).exists())

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

    def test_email_signup_otp_cannot_activate_admin_disabled_account(self):
        user = CustomUser.objects.create_user(
            email="disabled-signup@example.com",
            username="disabled-signup",
            password="StrongSignupPass123!",
            is_active=False,
            account_status=CustomUser.AccountStatus.PENDING_VERIFICATION,
        )
        request_email_otp(user.email, EmailOTPChallenge.Purpose.SIGNUP)
        code = re.search(r"\b\d{6}\b", mail.outbox[-1].body).group(0)

        user.account_status = CustomUser.AccountStatus.ADMIN_DISABLED
        user.is_active = False
        user.save(update_fields=["account_status", "is_active", "updated_at"])

        result = verify_email_otp(
            user.email,
            code,
            EmailOTPChallenge.Purpose.SIGNUP,
        )

        self.assertIsNone(result)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(
            user.account_status,
            CustomUser.AccountStatus.ADMIN_DISABLED,
        )


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
            is_email_verified=True,
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
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
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
@override_settings(
    DEBUG=True,
    EMAIL_PROVIDER="smtp",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@example.com",
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

    def _request_code(self):
        response = self.client.post(
            reverse("accounts:password_reset_otp"),
            {"email": self.user.email},
        )
        self.assertRedirects(response, reverse("accounts:password_reset_otp_verify"))
        self.assertEqual(len(mail.outbox), 1)
        code = re.search(r"\b\d{6}\b", mail.outbox[0].body).group(0)
        challenge = EmailOTPChallenge.objects.latest("created_at")
        self.assertNotEqual(challenge.code_hash, code)
        self.assertTrue(check_password(code, challenge.code_hash))
        return code

    def test_email_delivery_error_classification_covers_supported_errors(self):
        cases = (
            (BrevoAPIError(403, "brevo_forbidden"), "brevo_forbidden", 403),
            (Timeout(), "brevo_timeout", None),
            (RequestConnectionError(), "brevo_connection", None),
            (OperationalError(), "database_operational", None),
            (smtplib.SMTPAuthenticationError(535, b"auth"), "smtp_authentication", 535),
            (smtplib.SMTPConnectError(421, b"connect"), "smtp_connection", 421),
            (smtplib.SMTPServerDisconnected("disconnected"), "smtp_disconnected", None),
            (
                smtplib.SMTPRecipientsRefused(
                    {"recipient@example.com": (550, b"rejected")}
                ),
                "smtp_recipient_rejected",
                None,
            ),
            (
                smtplib.SMTPSenderRefused(550, b"rejected", "sender@example.com"),
                "smtp_sender_rejected",
                550,
            ),
            (smtplib.SMTPResponseException(451, b"response"), "smtp_response", 451),
            (TimeoutError(), "network_or_timeout", None),
            (OSError(), "network_or_timeout", None),
            (EmailDeliveryConfigurationError(), "email_configuration", None),
            (RuntimeError(), "email_backend", None),
        )

        for error, expected_class, expected_code in cases:
            with self.subTest(error=type(error).__name__):
                self.assertEqual(
                    classify_email_delivery_error(error),
                    (expected_class, expected_code),
                )

    @override_settings(
        DEBUG=False,
        EMAIL_PROVIDER="brevo",
        BREVO_API_KEY="brevo-test-key",
        BREVO_SENDER_EMAIL="sender@example.com",
    )
    def test_brevo_configuration_validation_accepts_complete_configuration(self):
        validate_email_delivery_configuration()

    def test_brevo_configuration_validation_rejects_missing_credentials(self):
        for configuration in (
            {
                "EMAIL_PROVIDER": "brevo",
                "BREVO_API_KEY": "",
                "BREVO_SENDER_EMAIL": "sender@example.com",
            },
            {
                "EMAIL_PROVIDER": "brevo",
                "BREVO_API_KEY": "brevo-test-key",
                "BREVO_SENDER_EMAIL": "",
            },
            {
                "EMAIL_PROVIDER": "unsupported",
                "BREVO_API_KEY": "brevo-test-key",
                "BREVO_SENDER_EMAIL": "sender@example.com",
            },
        ):
            with self.subTest(provider=configuration["EMAIL_PROVIDER"]):
                with override_settings(**configuration):
                    with self.assertRaises(EmailDeliveryConfigurationError):
                        validate_email_delivery_configuration()

    def test_email_otp_login_routes_are_disabled(self):
        response = self.client.post(
            reverse("accounts:email_otp_login"),
            {"email": self.user.email},
        )
        self.assertRedirects(response, reverse("accounts:email_login"))
        self.assertEqual(len(mail.outbox), 0)

        response = self.client.post(reverse("accounts:email_otp_login_verify"))
        self.assertRedirects(response, reverse("accounts:email_login"))
        self.assertEqual(len(mail.outbox), 0)

        with self.assertRaises(ValueError):
            request_email_otp(self.user.email, "login")

    @override_settings(
        DEBUG=False,
        EMAIL_PROVIDER="brevo",
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        BREVO_API_KEY="brevo-test-key",
        BREVO_SENDER_EMAIL="sender@example.com",
        BREVO_SENDER_NAME="NAGRI",
    )
    @patch("accounts.email_delivery.send_mail")
    @patch(
        "accounts.email_delivery.requests.post",
        return_value=Mock(
            status_code=201,
            json=lambda: {"messageId": "mock-message-id"},
        ),
    )
    def test_production_brevo_uses_custom_api_without_anymail_backend(
        self,
        post,
        smtp_send,
    ):
        send_account_email("subject", "body", "recipient@example.com")

        post.assert_called_once()
        self.assertEqual(
            post.call_args.args[0],
            "https://api.brevo.com/v3/smtp/email",
        )
        self.assertEqual(
            post.call_args.kwargs["json"]["sender"],
            {"email": "sender@example.com", "name": "NAGRI"},
        )
        self.assertEqual(
            post.call_args.kwargs["headers"]["api-key"],
            "brevo-test-key",
        )
        self.assertEqual(post.call_args.kwargs["timeout"], (5, 30))
        self.assertFalse(post.call_args.kwargs["allow_redirects"])
        smtp_send.assert_not_called()

    @override_settings(
        DEBUG=False,
        EMAIL_PROVIDER="brevo",
        EMAIL_BACKEND="anymail.backends.brevo.EmailBackend",
        BREVO_API_KEY="brevo-test-key",
        BREVO_SENDER_EMAIL="sender@example.com",
        BREVO_SENDER_NAME="NAGRI",
        ANYMAIL={"REQUESTS_TIMEOUT": (5, 30)},
    )
    @patch(
        "accounts.email_delivery.requests.post",
        return_value=Mock(
            status_code=201,
            json=lambda: {"messageId": "mock-message-id"},
        ),
    )
    def test_brevo_html_email_includes_html_content(self, post):
        send_account_email(
            "subject",
            "plain text",
            "recipient@example.com",
            html_body="<p>HTML message</p>",
        )

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["textContent"], "plain text")
        self.assertEqual(payload["htmlContent"], "<p>HTML message</p>")

    @override_settings(
        DEBUG=False,
        EMAIL_PROVIDER="brevo",
        EMAIL_BACKEND="anymail.backends.brevo.EmailBackend",
        ANYMAIL={
            "BREVO_API_KEY": "brevo-test-key",
            "REQUESTS_TIMEOUT": (5, 30),
            "DEBUG_API_REQUESTS": False,
        },
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
        self.assertEqual(
            request_args["url"],
            "https://api.brevo.com/v3/smtp/email",
        )
        self.assertEqual(request_args["headers"]["api-key"], "brevo-test-key")
        self.assertEqual(request_args["timeout"], (5, 30))
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
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
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
            reverse("accounts:password_reset_otp"),
            {"email": self.user.email},
        )

        self.assertRedirects(response, reverse("accounts:password_reset_otp_verify"))
        post.assert_called_once()
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["sender"], {
            "email": "sender@example.com",
            "name": "NAGRI",
        })
        self.assertEqual(payload["to"], [{"email": self.user.email}])
        self.assertRegex(
            payload["textContent"],
            r"code to reset your password is \d{6}",
        )

    @override_settings(
        DEBUG=False,
        EMAIL_BACKEND="anymail.backends.brevo.EmailBackend",
        EMAIL_PROVIDER="brevo",
        BREVO_API_KEY="brevo-test-key",
        BREVO_SENDER_EMAIL="sender@example.com",
        BREVO_SENDER_NAME="NAGRI",
        ANYMAIL={
            "BREVO_API_KEY": "brevo-test-key",
            "REQUESTS_TIMEOUT": (5, 30),
            "DEBUG_API_REQUESTS": False,
        },
    )
    @patch("accounts.email_delivery.requests.post", side_effect=Timeout())
    def test_brevo_timeout_is_not_retried_and_keeps_otp_usable(self, post):
        with self.assertRaises(Timeout):
            request_email_otp(
                self.user.email,
                EmailOTPChallenge.Purpose.PASSWORD_RESET,
            )

        post.assert_called_once()
        self.assertEqual(post.call_args.kwargs["timeout"], (5, 30))
        payload = post.call_args.kwargs["json"]
        code = re.search(r"\b(\d{6})\b", payload["textContent"]).group(1)
        challenge = EmailOTPChallenge.objects.get(
            user=self.user,
            purpose=EmailOTPChallenge.Purpose.PASSWORD_RESET,
        )
        self.assertIsNone(challenge.consumed_at)
        self.assertIsNotNone(
            verify_email_otp(
                self.user.email,
                code,
                EmailOTPChallenge.Purpose.PASSWORD_RESET,
            )
        )

    @override_settings(
        DEBUG=False,
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_PROVIDER="brevo",
        BREVO_API_KEY="brevo-test-key",
        BREVO_SENDER_EMAIL="sender@example.com",
    )
    @patch("accounts.email_delivery.send_mail")
    @patch("accounts.email_delivery.requests.post")
    def test_brevo_authorization_failures_do_not_fallback_to_smtp(
        self,
        post,
        smtp_send,
    ):
        for status_code, expected_failure in (
            (401, "brevo_unauthorized"),
            (403, "brevo_forbidden"),
        ):
            with self.subTest(status_code=status_code):
                post.reset_mock()
                post.return_value = Mock(
                    status_code=status_code,
                    json=lambda: {"message": "must not be logged"},
                )
                with self.assertRaises(BrevoAPIError) as raised:
                    send_account_email(
                        "subject",
                        "body",
                        "recipient@example.com",
                    )
                self.assertEqual(
                    raised.exception.failure_class,
                    expected_failure,
                )
                self.assertEqual(raised.exception.status_code, status_code)
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
        return_value=Mock(status_code=400, json=lambda: {"message": "unsafe detail"}),
    )
    def test_brevo_api_rejection_uses_safe_failure_class(self, post):
        with self.assertRaises(BrevoAPIError) as raised:
            send_account_email("subject", "body", "recipient@example.com")

        self.assertEqual(raised.exception.status_code, 400)
        self.assertEqual(raised.exception.failure_class, "brevo_api_rejected")
        self.assertEqual(str(raised.exception), "brevo_api_rejected")
        post.assert_called_once()

    @override_settings(
        DEBUG=False,
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_PROVIDER="brevo",
        BREVO_API_KEY="brevo-test-key",
        BREVO_SENDER_EMAIL="sender@example.com",
    )
    @patch("accounts.email_delivery.send_mail")
    @patch(
        "accounts.email_delivery.requests.post",
        return_value=Mock(status_code=201, json=lambda: {"unexpected": "shape"}),
    )
    def test_brevo_malformed_success_response_is_rejected(
        self,
        post,
        smtp_send,
    ):
        with self.assertRaises(BrevoAPIError) as raised:
            send_account_email("subject", "body", "recipient@example.com")
        self.assertEqual(raised.exception.failure_class, "brevo_malformed_response")
        self.assertEqual(raised.exception.status_code, 201)
        post.assert_called_once()
        smtp_send.assert_not_called()

    @override_settings(
        DEBUG=False,
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_PROVIDER="brevo",
        BREVO_API_KEY="brevo-test-key",
        BREVO_SENDER_EMAIL="sender@example.com",
    )
    @patch("accounts.email_delivery.send_mail")
    @patch(
        "accounts.email_delivery.requests.post",
        return_value=Mock(
            status_code=201,
            json=Mock(side_effect=ValueError("sensitive response body")),
        ),
    )
    def test_brevo_invalid_json_response_is_rejected_without_smtp_fallback(
        self,
        post,
        smtp_send,
    ):
        with self.assertRaises(BrevoAPIError) as raised:
            send_account_email("subject", "body", "recipient@example.com")

        self.assertEqual(raised.exception.failure_class, "brevo_malformed_response")
        self.assertEqual(raised.exception.status_code, 201)
        post.assert_called_once()
        smtp_send.assert_not_called()

    @override_settings(
        DEBUG=False,
        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
        EMAIL_PROVIDER="brevo",
        BREVO_API_KEY="brevo-test-key",
        BREVO_SENDER_EMAIL="sender@example.com",
    )
    @patch("accounts.email_delivery.send_mail")
    @patch("accounts.email_delivery.requests.post", side_effect=Timeout())
    def test_brevo_timeout_is_classified_without_smtp_fallback(
        self,
        post,
        smtp_send,
    ):
        with self.assertRaises(Timeout):
            send_account_email("subject", "body", "recipient@example.com")
        self.assertEqual(
            classify_email_delivery_error(Timeout())[0],
            "brevo_timeout",
        )
        post.assert_called_once()
        smtp_send.assert_not_called()

    def test_brevo_requires_api_key_and_sender_in_production(self):
        invalid_configurations = (
            {"BREVO_API_KEY": "", "BREVO_SENDER_EMAIL": "sender@example.com"},
            {"BREVO_API_KEY": "brevo-test-key", "BREVO_SENDER_EMAIL": ""},
        )
        with patch("accounts.email_delivery.requests.post") as post:
            for configuration in invalid_configurations:
                with self.subTest(configuration=configuration):
                    with override_settings(
                        DEBUG=False,
                        EMAIL_PROVIDER="brevo",
                        EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
                        **configuration,
                    ):
                        with self.assertRaises(EmailDeliveryConfigurationError):
                            send_account_email(
                                "subject",
                                "body",
                                "recipient@example.com",
                            )
        post.assert_not_called()

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
                    reverse("accounts:password_reset_otp"),
                    {"email": self.user.email},
                )

        self.assertRedirects(response, reverse("accounts:password_reset_otp_verify"))
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
        code = self._request_code()
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
        self.customer = CustomUser.objects.create_user(email="cust@example.com", password="pass123", username="cust", is_email_verified=True)
        self.customer.is_active = True
        self.customer.save()
        UserProfile.objects.get_or_create(user=self.customer, defaults={"full_name": "Customer", "phone": "+919000000001", "is_phone_verified": True})

        self.seller = CustomUser.objects.create_user(email="seller@example.com", password="pass123", username="seller", is_email_verified=True)
        self.seller.is_vendor = True
        self.seller.is_active = True
        self.seller.save()
        UserProfile.objects.get_or_create(user=self.seller, defaults={"full_name": "Seller", "phone": "+919000000002", "is_phone_verified": True})

        self.owner = CustomUser.objects.create_user(email="owner@example.com", password="pass123", username="owner", is_email_verified=True)
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
