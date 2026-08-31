from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    avatar = models.ImageField(upload_to="profiles/", blank=True, null=True)
    is_vendor = models.BooleanField(default=False)
    is_customer = models.BooleanField(default=True)
    is_owner = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def __str__(self):
        return self.email or self.username

    def can_change_password(self):
        from sellers.models import SellerPasswordChangeEvent

        all_events = SellerPasswordChangeEvent.objects.filter(
            user=self,
            event_type="manual_change",
        ).order_by("changed_at")

        recent_events = all_events.filter(changed_at__gte=timezone.now() - timedelta(days=30))

        if recent_events.count() < 3:
            next_available = all_events[0].changed_at + timedelta(days=30) if all_events.exists() else None
            return True, next_available

        oldest_recent = recent_events[0]
        next_available = oldest_recent.changed_at + timedelta(days=30)
        return False, next_available

    def change_password(self, current_password, new_password):
        from sellers.models import SellerPasswordChangeEvent

        allowed, next_available = self.can_change_password()
        if not allowed:
            if next_available:
                return False, f"You have reached the maximum password change limit of 3 password changes within 30 days. Next change available on {next_available.strftime('%Y-%m-%d')}."
            return False, "You have reached the maximum password change limit of 3 password changes within 30 days."

        try:
            validate_password(new_password, self)
        except ValidationError as exc:
            return False, exc.messages[0]

        self.set_password(new_password)
        self.save(update_fields=["password", "updated_at"])
        SellerPasswordChangeEvent.objects.create(user=self, event_type="manual_change")
        return True, "success"


class UserProfile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE, related_name="profile")
    full_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    avatar = models.ImageField(upload_to="profiles/", blank=True, null=True)
    delivery_location = models.CharField(max_length=200, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    pincode = models.CharField(max_length=20, blank=True, null=True)
    otp = models.CharField(max_length=6, blank=True, null=True)
    otp_expires_at = models.DateTimeField(blank=True, null=True)
    is_phone_verified = models.BooleanField(default=False)
    last_otp_sent_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.full_name or self.user.email


class Address(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="addresses")
    profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE, related_name="addresses", null=True, blank=True)
    label = models.CharField(max_length=50, default="Home")
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default="India")
    pincode = models.CharField(max_length=20)
    landmark = models.CharField(max_length=200, blank=True, null=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"{self.label}: {self.city}"


class PaymentMethod(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="payment_methods")
    card_holder_name = models.CharField(max_length=150)
    card_last4 = models.CharField(max_length=4)
    card_brand = models.CharField(max_length=50, default="Visa")
    expiry_month = models.CharField(max_length=2)
    expiry_year = models.CharField(max_length=4)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]

    def __str__(self):
        return f"{self.card_brand} ending {self.card_last4}"
