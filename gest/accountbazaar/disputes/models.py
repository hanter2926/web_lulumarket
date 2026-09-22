from django.conf import settings
from django.db import models

from payments.models import Order


class Dispute(models.Model):
	class Status(models.TextChoices):
		OPEN = "OPEN", "Open"
		UNDER_REVIEW = "UNDER_REVIEW", "Under review"
		WAITING_BUYER = "WAITING_BUYER", "Waiting for buyer"
		WAITING_SELLER = "WAITING_SELLER", "Waiting for seller"
		RESOLVED_REFUND = "RESOLVED_REFUND", "Resolved with refund"
		RESOLVED_RELEASE = "RESOLVED_RELEASE", "Resolved with release"
		REJECTED = "REJECTED", "Rejected"
		CLOSED = "CLOSED", "Closed"

	order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="dispute")
	opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
	reason = models.TextField()
	description = models.TextField(blank=True)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
	resolution_note = models.TextField(blank=True)
	evidence = models.FileField(upload_to="disputes/evidence/%Y/%m/", blank=True, null=True)
	created_at = models.DateTimeField(auto_now_add=True)
	resolved_at = models.DateTimeField(null=True, blank=True)


class Report(models.Model):
	class Status(models.TextChoices):
		OPEN = "OPEN", "Open"
		INVESTIGATING = "INVESTIGATING", "Investigating"
		ACTION_REQUIRED = "ACTION_REQUIRED", "Action required"
		RESOLVED = "RESOLVED", "Resolved"
		DISMISSED = "DISMISSED", "Dismissed"

	reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reports_made")
	target_type = models.CharField(max_length=20)
	target_id = models.PositiveBigIntegerField()
	reason = models.CharField(max_length=40)
	description = models.TextField()
	evidence = models.FileField(upload_to="reports/evidence/%Y/%m/", blank=True, null=True)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
	moderator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="moderated_reports", null=True, blank=True)
	resolution = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)
