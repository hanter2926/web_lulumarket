from django.contrib import admin

from .models import AuditLog, Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
	list_display = ("recipient", "title", "is_read", "created_at")
	list_filter = ("is_read",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
	list_display = ("action", "object_type", "object_id", "actor", "created_at")
	list_filter = ("action", "object_type")
	search_fields = ("action", "object_type", "object_id", "actor__username")
	readonly_fields = ("actor", "action", "object_type", "object_id", "metadata", "created_at")
from django.contrib import admin

# Register your models here.
