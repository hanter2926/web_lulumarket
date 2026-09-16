from django.core import mail
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from unittest.mock import patch
from urllib.parse import urlparse
import re

from .models import Address, CustomUser, UserProfile
from .utils import generate_otp, normalize_phone_number


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

    def test_request_otp_requires_phone_without_email_and_finds_existing_user(self):
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

    def test_request_otp_for_unregistered_phone_returns_clear_error(self):
        response = self.client.post("/accounts/request-otp/", {"phone": "9999999999"}, content_type="application/json")
        self.assertEqual(response.status_code, 404)
        self.assertIn("No account found with this phone number. Please register first.", response.json()["detail"])


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
        self.assertContains(response, "Verify your phone number before logging in")
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

    @patch("accounts.views.send_otp_to_phone", return_value={"status": "sent"})
    def test_valid_signup_creates_hashed_user_and_profile_and_starts_otp_flow(self, send_otp):
        response = self.client.post(reverse("accounts:signup_form"), self.signup_data)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Account created. OTP sent to your phone.")
        user = CustomUser.objects.get(email=self.signup_data["email"])
        self.assertFalse(user.is_active)
        self.assertTrue(user.check_password(self.signup_data["password"]))
        self.assertNotEqual(user.password, self.signup_data["password"])
        profile = UserProfile.objects.get(user=user)
        self.assertFalse(profile.is_phone_verified)
        self.assertEqual(profile.phone, "+919876543210")
        send_otp.assert_called_once()

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
        self.assertContains(response, "The two password fields didn't match.")

    def test_signup_rejects_invalid_password_and_missing_required_fields(self):
        weak_password = {**self.signup_data, "password": "short", "confirm_password": "short"}
        response = self.client.post(reverse("accounts:signup_form"), weak_password)
        self.assertContains(response, "This password is too short")

        missing_terms = {key: value for key, value in self.signup_data.items() if key != "terms"}
        response = self.client.post(reverse("accounts:signup_form"), missing_terms)
        self.assertContains(response, "This field is required.")


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@example.com",
    SITE_URL="https://web-lulumarket.onrender.com",
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

    def test_reset_token_sets_new_password_and_old_password_fails(self):
        self.client.post(reverse("accounts:password_reset"), {"email": self.user.email})
        body = mail.outbox[0].body
        reset_url = re.search(
            r"https://web-lulumarket\.onrender\.com/accounts/reset/[^\s]+", body
        ).group(0)
        reset_path = urlparse(reset_url).path

        response = self.client.post(
            reset_path,
            {
                "new_password1": "NewStrongPass456!",
                "new_password2": "NewStrongPass456!",
            },
        )
        self.assertRedirects(response, reverse("accounts:password_reset_complete"))
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

    def test_invalid_reset_token_is_rejected(self):
        response = self.client.get(
            reverse(
                "accounts:password_reset_confirm",
                kwargs={"uidb64": "invalid", "token": "invalid-token"},
            )
        )
        self.assertContains(response, "invalid or expired", status_code=200)


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
