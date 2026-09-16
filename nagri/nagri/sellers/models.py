import hashlib
import os
import re
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import models, transaction
from django.utils import timezone
from uuid import uuid4

from products.models import Category


def seller_document_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    name = uuid.uuid4().hex
    return os.path.join("seller_documents", f"{name}.{ext}")


def _hash_otp(otp, salt):
    return hashlib.sha256((otp + salt).encode()).hexdigest()


def _hash_token(token, salt):
    return hashlib.sha256((token + salt).encode()).hexdigest()


def validate_seller_password(password, user=None):
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", password):
        raise ValidationError("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        raise ValidationError("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        raise ValidationError("Password must contain at least one number.")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValidationError("Password must contain at least one special character.")
    try:
        validate_password(password, user)
    except ValidationError as exc:
        raise ValidationError(exc.messages[0])


class Area(models.Model):
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=50, unique=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20, blank=True)
    description = models.TextField(blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["city", "name"]
        indexes = [models.Index(fields=["city", "state", "is_active"])]

    def __str__(self):
        return f"{self.name}, {self.city}"


class Shopkeeper(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("active", "Active"),
        ("inactive", "Inactive"),
        ("suspended", "Suspended"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="shopkeeper_profile")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="managed_shopkeepers")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    shop_name = models.CharField(max_length=150, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    pincode = models.CharField(max_length=20, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.shop_name or self.user.get_full_name() or self.user.email


class Store(models.Model):
    shopkeeper = models.ForeignKey(Shopkeeper, on_delete=models.CASCADE, related_name="stores")
    area = models.ForeignKey("Area", on_delete=models.SET_NULL, null=True, blank=True, related_name="stores")
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    pincode = models.CharField(max_length=20, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class DeliveryWorker(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("inactive", "Inactive"),
        ("on_leave", "On Leave"),
        ("suspended", "Suspended"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="delivery_worker_profile")
    shopkeeper = models.ForeignKey(Shopkeeper, on_delete=models.CASCADE, related_name="delivery_workers")
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="delivery_workers")
    area = models.ForeignKey("Area", on_delete=models.SET_NULL, null=True, blank=True, related_name="delivery_workers")
    phone = models.CharField(max_length=20)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    is_available = models.BooleanField(default=True)
    current_latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    current_longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_mobile_verified(self):
        profile = getattr(self.user, "profile", None)
        if profile is not None:
            return bool(profile.is_phone_verified)
        return bool(self.user.phone and self.user.phone == self.phone)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.store_id and self.shopkeeper_id and self.store.shopkeeper_id != self.shopkeeper_id:
            raise ValidationError({"store": "This store does not belong to the selected shopkeeper."})
        if self.area_id and self.store_id and self.store.area_id and self.store.area_id != self.area_id:
            raise ValidationError({"area": "This area does not match the worker's store area."})

    def __str__(self):
        return self.user.get_full_name() or self.user.email


class DeliveryAssignment(models.Model):
    STATUS_CHOICES = [
        ("assigned", "Assigned"),
        ("accepted", "Accepted"),
        ("picked_up", "Picked Up"),
        ("out_for_delivery", "Out for Delivery"),
        ("delivered", "Delivered"),
        ("delayed", "Delayed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="delivery_assignments")
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="delivery_assignments")
    shopkeeper = models.ForeignKey(Shopkeeper, on_delete=models.CASCADE, related_name="delivery_assignments")
    worker = models.ForeignKey(DeliveryWorker, on_delete=models.CASCADE, related_name="assignments")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="assigned")
    assigned_at = models.DateTimeField(auto_now_add=True)
    picked_up_at = models.DateTimeField(blank=True, null=True)
    delivered_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True)

    VALID_TRANSITIONS = {
        "assigned": {"accepted", "cancelled"},
        "accepted": {"picked_up", "cancelled", "delayed"},
        "picked_up": {"out_for_delivery", "delayed", "cancelled"},
        "out_for_delivery": {"delivered", "delayed", "failed"},
        "delayed": {"accepted", "picked_up", "out_for_delivery", "failed", "cancelled"},
        "failed": {"assigned", "accepted", "cancelled"},
        "delivered": set(),
        "cancelled": set(),
    }

    class Meta:
        ordering = ["-assigned_at"]

    def clean(self):
        if self.store_id and self.shopkeeper_id and self.store.shopkeeper_id != self.shopkeeper_id:
            raise ValidationError({"store": "This store does not belong to the selected shopkeeper."})
        if self.worker_id and self.shopkeeper_id and self.worker.shopkeeper_id != self.shopkeeper_id:
            raise ValidationError({"worker": "This worker does not belong to the selected shopkeeper."})
        if self.worker_id and self.store_id and self.worker.store_id != self.store_id:
            raise ValidationError({"worker": "This worker is not assigned to this store."})

    def can_transition_to(self, new_status):
        return new_status in self.VALID_TRANSITIONS.get(self.status, set())

    def __str__(self):
        return f"Assignment for {self.order.order_number}"


class DeliveryIncident(models.Model):
    INCIDENT_TYPES = [
        ("road_blocked", "Road Blocked"),
        ("accident", "Accident"),
        ("waterlogging", "Waterlogging/Flood"),
        ("traffic", "Traffic"),
        ("vehicle_problem", "Vehicle Problem"),
        ("weather_problem", "Weather Problem"),
        ("safety_problem", "Safety Problem"),
        ("other", "Other"),
    ]
    SEVERITY_CHOICES = [(value, label) for value, label in (("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical"))]
    STATUS_CHOICES = [
        ("reported", "Reported"),
        ("acknowledged", "Acknowledged"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
        ("rejected", "Rejected"),
    ]
    client_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    area = models.ForeignKey("Area", on_delete=models.PROTECT, related_name="incidents")
    delivery_assignment = models.ForeignKey(DeliveryAssignment, on_delete=models.SET_NULL, null=True, blank=True, related_name="incidents")
    reported_by = models.ForeignKey(DeliveryWorker, on_delete=models.PROTECT, related_name="reported_incidents")
    incident_type = models.CharField(max_length=30, choices=INCIDENT_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default="medium")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="reported")
    occurred_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["area", "status"]), models.Index(fields=["severity", "created_at"])]

    def clean(self):
        if self.delivery_assignment_id:
            assignment = self.delivery_assignment
            if assignment.worker_id != self.reported_by_id:
                raise ValidationError({"delivery_assignment": "The assignment must belong to the reporting worker."})
            if assignment.store.area_id and assignment.store.area_id != self.area_id:
                raise ValidationError({"area": "The incident area must match the assignment store area."})
        if self.reported_by_id and self.reported_by.area_id and self.reported_by.area_id != self.area_id:
            raise ValidationError({"area": "The incident area must match the worker area."})

    def __str__(self):
        return self.title


class RouteIssue(models.Model):
    ISSUE_TYPES = [
        ("road_closed", "Road Closed"),
        ("bad_road", "Bad Road"),
        ("heavy_traffic", "Heavy Traffic"),
        ("construction", "Construction"),
        ("waterlogging", "Waterlogging"),
        ("accident", "Accident"),
        ("unsafe_route", "Unsafe Route"),
        ("weather", "Weather"),
        ("other", "Other"),
    ]
    SEVERITY_CHOICES = DeliveryIncident.SEVERITY_CHOICES
    STATUS_CHOICES = [("active", "Active"), ("monitoring", "Monitoring"), ("resolved", "Resolved"), ("expired", "Expired")]
    area = models.ForeignKey("Area", on_delete=models.PROTECT, related_name="route_issues")
    title = models.CharField(max_length=200)
    description = models.TextField()
    issue_type = models.CharField(max_length=30, choices=ISSUE_TYPES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default="medium")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    reported_by = models.ForeignKey(DeliveryWorker, on_delete=models.SET_NULL, null=True, blank=True, related_name="reported_route_issues")
    delivery_assignment = models.ForeignKey(DeliveryAssignment, on_delete=models.SET_NULL, null=True, blank=True, related_name="route_issues")
    starts_at = models.DateTimeField(default=timezone.now)
    expected_end_at = models.DateTimeField(blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["area", "status"]), models.Index(fields=["severity", "created_at"])]

    def clean(self):
        if self.delivery_assignment_id and self.reported_by_id and self.delivery_assignment.worker_id != self.reported_by_id:
            raise ValidationError({"reported_by": "The route issue reporter must own the assignment."})
        if self.delivery_assignment_id and self.delivery_assignment.store.area_id and self.delivery_assignment.store.area_id != self.area_id:
            raise ValidationError({"area": "The route issue area must match the assignment store area."})

    def __str__(self):
        return self.title


class SellerAuditLog(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="seller_audit_logs")
    seller_application = models.ForeignKey("SellerApplication", on_delete=models.CASCADE, related_name="audit_logs", null=True, blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="seller_audit_actions")
    event = models.CharField(max_length=64)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event} ({self.user or self.seller_application})"


class SellerPasswordChangeEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="password_change_events")
    changed_at = models.DateTimeField(default=timezone.now)
    event_type = models.CharField(max_length=50, choices=[("manual_change", "Manual Change"), ("password_reset", "Password Reset")], default="manual_change")

    class Meta:
        ordering = ["-changed_at"]


class SellerOrderNotification(models.Model):
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="seller_notifications")
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seller_order_notifications")
    event_type = models.CharField(max_length=50, default="order_created")
    sent_at = models.DateTimeField(auto_now_add=True)
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["order", "seller", "event_type"], name="unique_seller_order_notification")]
        ordering = ["-sent_at"]


class SellerApplication(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("email_verified", "Email Verified"),
        ("documents_submitted", "Documents Submitted"),
        ("pending_review", "Pending Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("suspended", "Suspended"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="seller_application")
    email = models.EmailField()
    email_verified = models.BooleanField(default=False)
    seller_id = models.CharField(max_length=100, blank=True, null=True, unique=True)

    # OTP storage (hashed)
    otp_salt = models.CharField(max_length=64, blank=True, null=True)
    otp_hash = models.CharField(max_length=128, blank=True, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)
    otp_expires_at = models.DateTimeField(blank=True, null=True)
    otp_attempts = models.PositiveIntegerField(default=0)
    otp_last_sent_at = models.DateTimeField(blank=True, null=True)

    activation_token_salt = models.CharField(max_length=64, blank=True, null=True)
    activation_token_hash = models.CharField(max_length=128, blank=True, null=True)
    activation_token_expires_at = models.DateTimeField(blank=True, null=True)
    activation_token_used_at = models.DateTimeField(blank=True, null=True)
    activation_requested_at = models.DateTimeField(blank=True, null=True)
    activation_email_sent_at = models.DateTimeField(blank=True, null=True)
    activation_completed_at = models.DateTimeField(blank=True, null=True)

    password_reset_token_salt = models.CharField(max_length=64, blank=True, null=True)
    password_reset_token_hash = models.CharField(max_length=128, blank=True, null=True)
    password_reset_token_expires_at = models.DateTimeField(blank=True, null=True)
    password_reset_requested_at = models.DateTimeField(blank=True, null=True)
    password_reset_used_at = models.DateTimeField(blank=True, null=True)

    # Sensitive application fields
    aadhaar_number = models.CharField(max_length=20, blank=True, null=True)
    pan_number = models.CharField(max_length=20, blank=True, null=True)
    pan_card_image = models.FileField(upload_to=seller_document_upload_path, blank=True, null=True)
    passport_photo = models.FileField(upload_to=seller_document_upload_path, blank=True, null=True)

    selected_categories = models.ManyToManyField(Category, blank=True, related_name="seller_applications")

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="draft")
    submitted_at = models.DateTimeField(blank=True, null=True)
    reviewed_at = models.DateTimeField(blank=True, null=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="seller_reviews")
    review_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"SellerApplication({self.user.email})"

    def log_event(self, event, details="", actor=None):
        SellerAuditLog.objects.create(
            seller_application=self,
            user=self.user,
            actor=actor,
            event=event,
            details=details,
        )

    def validate_seller_id(self, value):
        if not value:
            raise ValidationError("Seller ID is required.")
        normalized = str(value).strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{3,30}", normalized):
            raise ValidationError("Seller ID must be 3-30 characters using letters, numbers, underscore or hyphen.")

        User = get_user_model()
        application_exists = SellerApplication.objects.filter(seller_id__iexact=normalized).exclude(pk=self.pk).exists()
        username_exists = User.objects.filter(username__iexact=normalized).exists()
        if application_exists or username_exists:
            raise ValidationError("This Seller ID is already in use.")
        return normalized

    def generate_and_send_otp(self, send_callable, ttl_minutes=10, resend_cooldown_seconds=60):
        now = timezone.now()
        if self.otp_last_sent_at and (now - self.otp_last_sent_at).total_seconds() < resend_cooldown_seconds:
            raise ValidationError(f"Please wait {resend_cooldown_seconds} seconds before requesting another OTP.")

        otp = str(secrets.randbelow(10 ** 6)).zfill(6)
        salt = secrets.token_hex(16)
        self.otp_salt = salt
        self.otp_hash = _hash_otp(otp, salt)
        self.otp_created_at = now
        self.otp_expires_at = now + timedelta(minutes=ttl_minutes)
        self.otp_attempts = 0
        self.otp_last_sent_at = None

        try:
            with transaction.atomic():
                self.save(update_fields=["otp_salt", "otp_hash", "otp_created_at", "otp_expires_at", "otp_attempts", "otp_last_sent_at", "updated_at"])
            send_callable(self.email, otp)
            with transaction.atomic():
                self.otp_last_sent_at = timezone.now()
                self.save(update_fields=["otp_last_sent_at", "updated_at"])
        except Exception:
            with transaction.atomic():
                self.otp_salt = None
                self.otp_hash = None
                self.otp_created_at = None
                self.otp_expires_at = None
                self.otp_attempts = 0
                self.otp_last_sent_at = None
                self.save(update_fields=["otp_salt", "otp_hash", "otp_created_at", "otp_expires_at", "otp_attempts", "otp_last_sent_at", "updated_at"])
            raise

    def verify_otp(self, candidate, max_attempts=5):
        if not (self.otp_hash and self.otp_salt and self.otp_expires_at):
            return False, "no_otp"
        if timezone.now() > self.otp_expires_at:
            return False, "expired"
        if self.otp_attempts >= max_attempts:
            return False, "attempts_exceeded"

        candidate_hash = _hash_otp(str(candidate), self.otp_salt)
        self.otp_attempts = models.F('otp_attempts') + 1
        self.save(update_fields=["otp_attempts"])
        self.refresh_from_db()

        if secrets.compare_digest(candidate_hash, self.otp_hash):
            self.otp_hash = None
            self.otp_salt = None
            self.otp_expires_at = None
            self.otp_created_at = None
            self.otp_attempts = 0
            self.email_verified = True
            self.status = "email_verified"
            self.save()
            return True, "verified"

        return False, "invalid"

    def generate_activation_token(self, ttl_minutes=60 * 24 * 7):
        raw = secrets.token_urlsafe(32)
        salt = secrets.token_hex(16)
        self.activation_token_salt = salt
        self.activation_token_hash = _hash_token(raw, salt)
        self.activation_token_expires_at = timezone.now() + timedelta(minutes=ttl_minutes)
        self.activation_token_used_at = None
        self.activation_requested_at = timezone.now()
        self.activation_token_hash = _hash_token(raw, salt)
        self.save(update_fields=["activation_token_salt", "activation_token_hash", "activation_token_expires_at", "activation_token_used_at", "activation_requested_at", "updated_at"])
        return raw

    def verify_activation_token(self, raw_token):
        if not raw_token:
            return False, "invalid"
        if not self.activation_token_hash or not self.activation_token_salt or not self.activation_token_expires_at:
            return False, "invalid"
        if self.activation_token_used_at:
            return False, "used"
        if timezone.now() > self.activation_token_expires_at:
            return False, "expired"
        if secrets.compare_digest(_hash_token(str(raw_token), self.activation_token_salt), self.activation_token_hash):
            self.activation_token_used_at = timezone.now()
            self.save(update_fields=["activation_token_used_at", "updated_at"])
            return True, "valid"
        return False, "invalid"

    def approve_application(self, admin_user, review_notes=""):
        if not admin_user or not (admin_user.is_staff or admin_user.is_superuser):
            raise PermissionError("Only staff or superusers can approve seller applications.")

        with transaction.atomic():
            self.review_notes = review_notes or self.review_notes
            self.reviewed_by = admin_user
            self.reviewed_at = timezone.now()
            self.status = "approved"
            self.email = self.email or self.user.email
            self.save(update_fields=["review_notes", "reviewed_by", "reviewed_at", "status", "email", "updated_at"])
            token = self.generate_activation_token()
            self.activation_email_sent_at = timezone.now()
            self.save(update_fields=["activation_email_sent_at", "updated_at"])
            self.log_event("approved", f"Approved by {admin_user.email}", actor=admin_user)
            self.log_event("activation_email_sent", f"Activation email sent to {self.email}", actor=admin_user)
            send_mail(
                "Your seller application has been approved",
                f"Your seller application has been approved.\n\nClick the secure link below to activate your seller account:\n\n{settings.SITE_URL}/sellers/activate/{token}/\n\nThis link is one-time use and expires soon.",
                settings.DEFAULT_FROM_EMAIL,
                [self.email],
                fail_silently=True,
            )
            return token

    def reject_application(self, admin_user, review_notes=""):
        with transaction.atomic():
            self.status = "rejected"
            self.reviewed_by = admin_user
            self.reviewed_at = timezone.now()
            self.review_notes = review_notes or self.review_notes
            self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_notes", "updated_at"])
            self.log_event("rejected", review_notes or "Rejected by admin", actor=admin_user)
            return True

    def suspend_application(self, admin_user, review_notes=""):
        with transaction.atomic():
            self.status = "suspended"
            self.reviewed_by = admin_user
            self.reviewed_at = timezone.now()
            self.review_notes = review_notes or self.review_notes
            self.user.is_vendor = False
            self.user.save(update_fields=["is_vendor", "updated_at"])
            self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_notes", "updated_at"])
            self.log_event("suspended", review_notes or "Seller account suspended", actor=admin_user)
            return True

    def reactivate_application(self, admin_user, review_notes=""):
        with transaction.atomic():
            self.status = "approved"
            self.reviewed_by = admin_user
            self.reviewed_at = timezone.now()
            self.review_notes = review_notes or self.review_notes
            self.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_notes", "updated_at"])
            self.log_event("reactivated", review_notes or "Seller reactivated", actor=admin_user)
            return True

    def activate_account(self, raw_token, seller_id, password):
        normalized = str(seller_id).strip()
        if normalized != self.user.username:
            normalized = self.validate_seller_id(seller_id)
        valid, reason = self.verify_activation_token(raw_token)
        if not valid:
            if reason == "expired":
                raise ValidationError("This activation link has expired.")
            if reason == "used":
                raise ValidationError("This activation link has already been used.")
            raise ValidationError("Invalid activation token.")

        try:
            validate_seller_password(password, self.user)
        except ValidationError as exc:
            raise ValidationError(exc.messages[0])

        with transaction.atomic():
            self.seller_id = normalized
            self.status = "approved"
            self.user.username = normalized
            self.user.set_password(password)
            self.user.is_vendor = True
            self.user.is_customer = False
            self.user.save(update_fields=["username", "password", "is_vendor", "is_customer", "updated_at"])
            self.activation_token_used_at = timezone.now()
            self.activation_completed_at = timezone.now()
            self.activation_token_hash = None
            self.activation_token_salt = None
            self.activation_token_expires_at = None
            self.save(update_fields=["seller_id", "status", "activation_token_used_at", "activation_completed_at", "activation_token_hash", "activation_token_salt", "activation_token_expires_at", "updated_at"])
            self.log_event("activated", f"Seller activated with ID {normalized}", actor=self.user)
            return True, "activated"

    def request_password_reset(self):
        now = timezone.now()
        if self.password_reset_requested_at and (now - self.password_reset_requested_at).total_seconds() < 300:
            return False, "Rate limit exceeded. Please wait a few minutes before requesting another password reset."

        raw = secrets.token_urlsafe(32)
        salt = secrets.token_hex(16)
        self.password_reset_token_salt = salt
        self.password_reset_token_hash = _hash_token(raw, salt)
        self.password_reset_token_expires_at = now + timedelta(minutes=30)
        self.password_reset_requested_at = now
        self.password_reset_used_at = None
        self.save(update_fields=["password_reset_token_salt", "password_reset_token_hash", "password_reset_token_expires_at", "password_reset_requested_at", "password_reset_used_at", "updated_at"])
        send_mail(
            "Seller password reset",
            f"Use this secure link to reset your seller password:\n\n{settings.SITE_URL}/accounts/password-reset/confirm?token={raw}\n\nIf you did not request this, please ignore this email.",
            settings.DEFAULT_FROM_EMAIL,
            [self.email],
            fail_silently=True,
        )
        self.log_event("password_reset_requested", "Seller requested password reset", actor=self.user)
        return True, "Reset email sent."

    def reset_password_with_token(self, raw_token, new_password):
        if not raw_token:
            raise ValidationError("Password reset token is required.")
        if not self.password_reset_token_hash or not self.password_reset_token_salt or not self.password_reset_token_expires_at:
            raise ValidationError("Invalid reset token.")
        if timezone.now() > self.password_reset_token_expires_at:
            raise ValidationError("This password reset link has expired.")
        if self.password_reset_used_at:
            raise ValidationError("This password reset link has already been used.")
        if not secrets.compare_digest(_hash_token(str(raw_token), self.password_reset_token_salt), self.password_reset_token_hash):
            raise ValidationError("Invalid reset token.")

        try:
            validate_seller_password(new_password, self.user)
        except ValidationError as exc:
            raise ValidationError(exc.messages[0])

        with transaction.atomic():
            self.user.set_password(new_password)
            self.user.save(update_fields=["password", "updated_at"])
            self.password_reset_token_hash = None
            self.password_reset_token_salt = None
            self.password_reset_token_expires_at = None
            self.password_reset_used_at = timezone.now()
            self.save(update_fields=["password_reset_token_hash", "password_reset_token_salt", "password_reset_token_expires_at", "password_reset_used_at", "updated_at"])
            SellerPasswordChangeEvent.objects.create(user=self.user, event_type="password_reset")
            self.log_event("password_reset_completed", "Seller password reset completed", actor=self.user)
            return True, "Password reset complete."

    def clean(self):
        if self.aadhaar_number:
            digits = ''.join([c for c in self.aadhaar_number if c.isdigit()])
            if len(digits) != 12:
                raise ValidationError({"aadhaar_number": "Aadhaar must be 12 digits."})

        if self.pan_number:
            pan = (self.pan_number or "").strip().upper()
            if not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', pan):
                raise ValidationError({"pan_number": "PAN must match format (e.g. ABCDE1234F)."})

        for field_name in ["pan_card_image", "passport_photo"]:
            f = getattr(self, field_name)
            if f:
                if hasattr(f, 'size') and f.size > 5 * 1024 * 1024:
                    raise ValidationError({field_name: "File size must be <= 5MB."})


def send_seller_order_notifications(order):
    from orders.models import OrderItem

    grouped = {}
    for item in OrderItem.objects.filter(order=order).select_related("product", "product__seller"):
        seller = item.product.seller
        if not seller:
            continue
        grouped.setdefault(seller.id, {"seller": seller, "items": []})["items"].append(item)

    for entry in grouped.values():
        seller = entry["seller"]
        notification, created = SellerOrderNotification.objects.get_or_create(
            order=order,
            seller=seller,
            event_type="order_created",
            defaults={"payload": {"order_number": order.order_number, "status": order.status, "payment_method": order.payment_method}},
        )
        if not created:
            continue

        lines = []
        subtotal = 0
        for item in entry["items"]:
            qty = item.quantity
            amount = item.price * qty
            subtotal += amount
            lines.append(f"- {item.product.name} x {qty} = ₹{amount}")
        message = (
            f"You have a new order from Nagri.\n\n"
            f"Order: {order.order_number}\n"
            f"Payment Method: {order.payment_method}\n"
            f"Payment Status: {'Paid' if order.is_paid else 'Pending'}\n"
            f"Order Status: {order.status}\n\n"
            f"Items:\n" + "\n".join(lines) + f"\n\nTotal: ₹{subtotal}"
        )
        send_mail("New seller order notification", message, settings.DEFAULT_FROM_EMAIL, [seller.email], fail_silently=True)
        notification.payload = {"order_number": order.order_number, "status": order.status, "payment_method": order.payment_method, "items": [item.product.name for item in entry["items"]]}
        notification.save(update_fields=["payload", "sent_at"])
