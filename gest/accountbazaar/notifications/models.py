from django.db import models
from django.conf import settings


class Notification(models.Model):
	recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
	title = models.CharField(max_length=150)
	body = models.TextField()
	link = models.CharField(max_length=255, blank=True)
	is_read = models.BooleanField(default=False)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ("-created_at",)


class AuditLog(models.Model):
	actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="audit_events")
	action = models.CharField(max_length=80)
	object_type = models.CharField(max_length=40)
	object_id = models.CharField(max_length=80)
	metadata = models.JSONField(default=dict, blank=True)
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ("-created_at",)
