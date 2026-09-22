from django.db import models
from django.conf import settings


class AdPlacement(models.Model):
	name = models.CharField(max_length=100)
	location = models.CharField(max_length=100)
	is_active = models.BooleanField(default=True)
	code = models.TextField(blank=True)

	def __str__(self):
		return self.name


class AdCampaign(models.Model):
	class Status(models.TextChoices):
		DRAFT = "DRAFT", "Draft"
		ACTIVE = "ACTIVE", "Active"
		PAUSED = "PAUSED", "Paused"
		COMPLETED = "COMPLETED", "Completed"

	owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ad_campaigns")
	placement = models.ForeignKey(AdPlacement, on_delete=models.PROTECT, related_name="campaigns")
	name = models.CharField(max_length=150)
	budget = models.DecimalField(max_digits=12, decimal_places=2, default=0)
	status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
	impressions = models.PositiveIntegerField(default=0)
	clicks = models.PositiveIntegerField(default=0)
	created_at = models.DateTimeField(auto_now_add=True)


class AdEvent(models.Model):
	campaign = models.ForeignKey(AdCampaign, on_delete=models.CASCADE, related_name="events")
	event_type = models.CharField(max_length=20, choices=(("impression", "Impression"), ("click", "Click")))
	created_at = models.DateTimeField(auto_now_add=True)
