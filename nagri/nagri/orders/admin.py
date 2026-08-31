from django.contrib import admin
from .models import Order, OrderItem

from .models import UpiPaymentSubmission
from django.utils import timezone
import logging


@admin.register(UpiPaymentSubmission)
class UpiPaymentSubmissionAdmin(admin.ModelAdmin):
	list_display = ("order", "amount", "upi_id", "status", "submitted_at", "reviewed_by")
	list_filter = ("status", "submitted_at")
	actions = ["approve_submission", "reject_submission"]

	def approve_submission(self, request, queryset):
		logger = logging.getLogger(__name__)
		for submission in queryset.filter(status="pending"):
			try:
				submission.status = "approved"
				submission.reviewed_by = request.user
				submission.reviewed_at = timezone.now()
				submission.save()
				# Mark order as paid
				order = submission.order
				order.is_paid = True
				order.status = "paid"
				order.payment_provider = "manual_upi"
				order.save(update_fields=["is_paid", "status", "payment_provider", "updated_at"])
			except Exception:
				logger.exception('Error approving UPI submission id=%s', getattr(submission, 'id', None))
	approve_submission.short_description = "Approve selected UPI submissions"

	def reject_submission(self, request, queryset):
		logger = logging.getLogger(__name__)
		for submission in queryset.filter(status="pending"):
			try:
				submission.status = "rejected"
				submission.reviewed_by = request.user
				submission.reviewed_at = timezone.now()
				submission.save()
			except Exception:
				logger.exception('Error rejecting UPI submission id=%s', getattr(submission, 'id', None))
	reject_submission.short_description = "Reject selected UPI submissions"


admin.site.register(Order)
admin.site.register(OrderItem)
