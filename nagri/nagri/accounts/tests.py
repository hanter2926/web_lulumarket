from django.test import TestCase, Client
from django.urls import reverse

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

        response = self.client.post(reverse("email_login"), {"email": "pending@example.com", "password": "StrongPass123"})

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

        response = self.client.post(reverse("email_login"), {"email": "verified@example.com", "password": "StrongPass123"})

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("dashboard_page"), response.url)


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

    def test_login_redirects_by_role(self):
        resp = self.client.post(reverse("email_login"), {"email": "seller@example.com", "password": "pass123"})
        # Should redirect to seller dashboard
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("sellers:dashboard"), resp.url)

        resp = self.client.post(reverse("email_login"), {"email": "owner@example.com", "password": "pass123"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("sellers:owner_dashboard"), resp.url)

        resp = self.client.post(reverse("email_login"), {"email": "cust@example.com", "password": "pass123"})
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse("dashboard_page"), resp.url)
