import uuid

from django.conf import settings
from django.db import models


class ComparisonReport(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    first_name = models.CharField(max_length=255)
    second_name = models.CharField(max_length=255)
    comparison_type = models.CharField(max_length=30)
    result = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.first_name} vs {self.second_name}"


class ComparisonQueueControl(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)


class ComparisonJob(models.Model):
    class Type(models.TextChoices):
        COMPARISON = "compare", "Comparison"
        COMPRESSION = "compress", "Compression"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    job_type = models.CharField(
        max_length=12,
        choices=Type.choices,
        default=Type.COMPARISON,
    )
    first_name = models.CharField(max_length=255)
    second_name = models.CharField(max_length=255)
    first_content_type = models.CharField(max_length=150)
    second_content_type = models.CharField(max_length=150)
    requester_key = models.CharField(max_length=64)
    access_token_hash = models.CharField(max_length=64)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    cancel_requested = models.BooleanField(default=False)
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)
    report_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["owner", "status"]),
            models.Index(fields=["requester_key", "status"]),
            models.Index(fields=["expires_at"]),
        ]
        ordering = ["created_at"]

    def __str__(self):
        return f"Comparison job {self.id} ({self.status})"
