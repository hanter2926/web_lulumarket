from django.conf import settings
from django.db import models
from django.utils import timezone
import secrets

from marketplace.models import Listing


def _order_id():
	return f"ORD-{secrets.token_hex(4).upper()}"


class Order(models.Model):
	class Status(models.TextChoices):
		PENDING_PAYMENT = "PENDING_PAYMENT", "Pending payment"
		PAID = "PAID", "Paid"
		IN_ESCROW = "IN_ESCROW", "In escrow"
		COMPLETED = "COMPLETED", "Completed"
		REFUNDED = "REFUNDED", "Refunded"
		DISPUTED = "DISPUTED", "Disputed"
		CANCELLED = "CANCELLED", "Cancelled"

	buyer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders")
	seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales")
	listing = models.ForeignKey(Listing, on_delete=models.PROTECT, related_name="orders")
	order_id = models.CharField(max_length=12, unique=True, default=_order_id, editable=False)
	amount = models.DecimalField(max_digits=12, decimal_places=2)
	currency = models.CharField(max_length=3, default="INR")
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_PAYMENT)
	payment_status = models.CharField(max_length=10, choices=(("PENDING", "Pending"), ("PAID", "Paid"), ("FAILED", "Failed"), ("REFUNDED", "Refunded")), default="PENDING")
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		constraints = [
			models.UniqueConstraint(
				fields=("listing",),
				condition=models.Q(status__in=("PENDING_PAYMENT", "PAID", "IN_ESCROW", "COMPLETED", "DISPUTED")),
				name="one_active_order_per_listing",
			),
		]

	def mark_paid(self):
		if self.status != self.Status.PENDING_PAYMENT:
			raise ValueError("Only pending orders can be paid.")
		self.status = self.Status.IN_ESCROW
		self.payment_status = "PAID"
		self.save(update_fields=("status", "payment_status", "updated_at"))
		self.escrow.hold()


class AccountTransfer(models.Model):
	class Status(models.TextChoices):
		AWAITING_SELLER = "AWAITING_SELLER", "Awaiting seller transfer"
		STARTED = "STARTED", "Handoff in progress"
		TRANSFERRED = "TRANSFERRED", "Transferred"
		RECEIVED = "RECEIVED", "Received"

	order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="transfer")
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.AWAITING_SELLER)
	handoff_started_at = models.DateTimeField(null=True, blank=True)
	seller_transferred_at = models.DateTimeField(null=True, blank=True)
	buyer_confirmed_at = models.DateTimeField(null=True, blank=True)
	transfer_note = models.TextField(blank=True)


class Payment(models.Model):
	class Status(models.TextChoices):
		CREATED = "CREATED", "Created"
		AUTHORIZED = "AUTHORIZED", "Authorized"
		CAPTURED = "CAPTURED", "Captured"
		FAILED = "FAILED", "Failed"
		REFUNDED = "REFUNDED", "Refunded"

	order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="payment")
	provider = models.CharField(max_length=40)
	provider_order_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
	provider_payment_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
	amount = models.DecimalField(max_digits=12, decimal_places=2)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
	provider_payload = models.JSONField(default=dict, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)


class Escrow(models.Model):
	class Status(models.TextChoices):
		PENDING = "PENDING", "Pending"
		HELD = "HELD", "Held"
		RELEASED = "RELEASED", "Released"
		REFUNDED = "REFUNDED", "Refunded"
		DISPUTED = "DISPUTED", "Disputed"

	order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="escrow")
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
	held_at = models.DateTimeField(null=True, blank=True)
	released_at = models.DateTimeField(null=True, blank=True)

	def hold(self):
		self.status = self.Status.HELD
		self.held_at = timezone.now()
		self.save(update_fields=("status", "held_at"))


class Refund(models.Model):
	class Status(models.TextChoices):
		REQUESTED = "REQUESTED", "Requested"
		PROCESSING = "PROCESSING", "Processing"
		COMPLETED = "COMPLETED", "Completed"
		FAILED = "FAILED", "Failed"

	order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="refund")
	amount = models.DecimalField(max_digits=12, decimal_places=2)
	reason = models.TextField()
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.REQUESTED)
	provider_refund_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)


class FeeConfiguration(models.Model):
	name = models.CharField(max_length=100, unique=True)
	percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
	fixed_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	currency = models.CharField(max_length=3, default="INR")
	is_active = models.BooleanField(default=True)
	updated_at = models.DateTimeField(auto_now=True)


class ComplianceCheck(models.Model):
	class Status(models.TextChoices):
		PASSED = "PASSED", "Passed"
		BLOCKED = "BLOCKED", "Blocked"

	order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="compliance_check")
	status = models.CharField(max_length=10, choices=Status.choices)
	buyer_email_verified = models.BooleanField(default=False)
	seller_kyc_approved = models.BooleanField(default=False)
	seller_verification_approved = models.BooleanField(default=False)
	reason = models.TextField(blank=True)
	checked_at = models.DateTimeField(auto_now_add=True)


class Settlement(models.Model):
	class Status(models.TextChoices):
		PENDING = "PENDING", "Pending"
		HELD = "HELD", "Held"
		ELIGIBLE = "ELIGIBLE", "Eligible"
		PROCESSING = "PROCESSING", "Processing"
		PAID = "PAID", "Paid"
		FAILED = "FAILED", "Failed"

	order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="settlement")
	seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="settlements")
	gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
	platform_fee = models.DecimalField(max_digits=12, decimal_places=2)
	net_amount = models.DecimalField(max_digits=12, decimal_places=2)
	status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
	provider_transfer_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
	paid_at = models.DateTimeField(null=True, blank=True)
