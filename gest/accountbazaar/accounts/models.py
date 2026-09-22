import secrets

from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.timezone import now


def _account_id():
    return f"acc_{secrets.token_urlsafe(9)}"


def _merchant_id():
    return f"mid_{secrets.token_urlsafe(9)}"


# -------------------------------------------------------------------
# 1. Custom User Model (Core Account Security & Core Info)
# -------------------------------------------------------------------
class User(AbstractUser):
    # Contact Info & Verifications
    phone_number = models.CharField(max_length=15, unique=True, null=True, blank=True)
    is_email_verified = models.BooleanField(default=False)
    is_phone_verified = models.BooleanField(default=False)
    
    # Account Types
    is_seller = models.BooleanField(default=False)
    
    # Advanced Security Features
    is_2fa_enabled = models.BooleanField(default=False)
    failed_login_attempts = models.PositiveIntegerField(default=0)
    account_locked_until = models.DateTimeField(null=True, blank=True)
    password_changed_at = models.DateTimeField(default=now)

    def is_account_locked(self):
        if self.account_locked_until and now() < self.account_locked_until:
            return True
        return False


class Account(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="owned_accounts")
    name = models.CharField(max_length=120, default="My Account")
    account_id = models.CharField(max_length=32, unique=True, default=_account_id, editable=False)
    merchant_id = models.CharField(max_length=32, unique=True, default=_merchant_id, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class AccountMembership(models.Model):
    account = models.ForeignKey(Account, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="account_memberships")
    role = models.CharField(max_length=30, default="member")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("account", "user"), name="unique_account_membership"),
        ]


# -------------------------------------------------------------------
# 2. Email & Phone OTP/Token Verification
# -------------------------------------------------------------------
class VerificationToken(models.Model):
    class TokenType(models.TextChoices):
        EMAIL_VERIFY = 'EMAIL', 'Email Verification'
        PHONE_OTP = 'PHONE', 'Phone OTP'
        PASSWORD_RESET = 'RESET', 'Password Reset'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='verification_tokens')
    token_type = models.CharField(max_length=10, choices=TokenType.choices)
    code = models.CharField(max_length=6)  # OTP code or hashed token string
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    def is_valid(self):
        return not self.is_used and now() < self.expires_at


# -------------------------------------------------------------------
# 3. KYC Verification (General Users)
# -------------------------------------------------------------------
class UserKYC(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='kyc')
    id_type = models.CharField(max_length=50)  # Passport, Aadhaar, Driving License
    id_number = models.CharField(max_length=100)
    document_front = models.ImageField(upload_to='kyc/documents/')
    document_back = models.ImageField(upload_to='kyc/documents/', null=True, blank=True)
    selfie_image = models.ImageField(upload_to='kyc/selfies/')
    
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)


# -------------------------------------------------------------------
# 4. Seller Verification (For E-Commerce / Marketplace platform)
# -------------------------------------------------------------------
class SellerVerification(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='seller_profile')
    business_name = models.CharField(max_length=255)
    business_tax_id = models.CharField(max_length=100)  # GST, Tax ID, SSN
    business_address = models.TextField()
    tax_document = models.FileField(upload_to='seller/docs/')
    bank_account_number = models.CharField(max_length=50)
    bank_routing_code = models.CharField(max_length=50)  # IFSC/IBAN/Routing
    
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True, null=True)
    applied_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)


# -------------------------------------------------------------------
# 5. Login History & Suspicious Login Detection
# -------------------------------------------------------------------
class LoginHistory(models.Model):
    class Status(models.TextChoices):
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'
        BLOCKED = 'BLOCKED', 'Blocked'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='login_history', null=True, blank=True)
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField()  # Browser/Device info
    location = models.CharField(max_length=255, null=True, blank=True)  # GeoIP location (City/Country)
    status = models.CharField(max_length=10, choices=Status.choices)
    is_suspicious = models.BooleanField(default=False)
    suspicious_reason = models.CharField(max_length=255, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)