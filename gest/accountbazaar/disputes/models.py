from django.conf import settings
from django.db import models

from payments.models import Order


class Dispute(models.Model):
	class Status(models.TextChoices):
		OPEN = "OPEN", "Open"
		UNDER_REVIEW = "UNDER_REVIEW", "Under review"
		RESOLVED_REFUND = "RESOLVED_REFUND", "Resolved with refund"
		RESOLVED_RELEASE = "RESOLVED_RELEASE", "Resolved with release"

	order = models.OneToOneField(Order, on_delete=models.PROTECT, related_name="dispute")
	opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
	reason = models.TextField()
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
	resolution_note = models.TextField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	resolved_at = models.DateTimeField(null=True, blank=True)
