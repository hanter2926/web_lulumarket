from django.contrib import admin

from .models import Dispute, Report


@admin.register(Dispute)
class DisputeAdmin(admin.ModelAdmin):
	list_display = ("id", "order", "opened_by", "status", "created_at")
	list_filter = ("status",)
	search_fields = ("order__order_id", "opened_by__username", "reason")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
	list_display = ("id", "target_type", "target_id", "reporter", "status", "created_at")
	list_filter = ("target_type", "status")
	search_fields = ("reporter__username", "description", "reason")
