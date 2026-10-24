from django.contrib import admin
from django.db import transaction
from .models import Order, OrderItem
from rewards.utils import mark_reward_claim_used_for_order

from .models import UpiPaymentSubmission
from django.utils import timezone
import logging
from products.models import Inventory


@admin.register(UpiPaymentSubmission)
class UpiPaymentSubmissionAdmin(admin.ModelAdmin):
	list_display = ("order", "amount", "upi_id", "status", "submitted_at", "reviewed_by")
	list_filter = ("status", "submitted_at")
	actions = ["approve_submission", "reject_submission"]

	def approve_submission(self, request, queryset):
		logger = logging.getLogger(__name__)
		for candidate in queryset.filter(status="pending").iterator():
			try:
				with transaction.atomic():
					submission = UpiPaymentSubmission.objects.select_for_update().get(pk=candidate.pk)
					if submission.status != "pending":
						continue
					order = Order.objects.select_for_update().get(pk=submission.order_id)
					if order.is_paid or order.status != "pending_verification":
						continue
					if submission.amount != order.total_amount:
						logger.warning(
							"Refusing UPI approval for submission %s: amount does not match order %s",
							submission.pk,
							order.pk,
						)
						continue

					submission.status = "approved"
					submission.reviewed_by = request.user
					submission.reviewed_at = timezone.now()
					submission.save(update_fields=["status", "reviewed_by", "reviewed_at"])
					order.is_paid = True
					order.status = "paid"
					order.payment_provider = "manual_upi"
					order.inventory_reserved = False
					order.save(update_fields=["is_paid", "status", "payment_provider", "inventory_reserved", "updated_at"])
				mark_reward_claim_used_for_order(order)
			except Exception:
				logger.exception('Error approving UPI submission id=%s', candidate.pk)
	approve_submission.short_description = "Approve selected UPI submissions"

	def reject_submission(self, request, queryset):
		logger = logging.getLogger(__name__)
		for candidate in queryset.filter(status="pending").iterator():
			try:
				with transaction.atomic():
					submission = UpiPaymentSubmission.objects.select_for_update().get(pk=candidate.pk)
					if submission.status != "pending":
						continue
					order = Order.objects.select_for_update().get(pk=submission.order_id)
					if order.is_paid:
						continue

					submission.status = "rejected"
					submission.reviewed_by = request.user
					submission.reviewed_at = timezone.now()
					submission.save(update_fields=["status", "reviewed_by", "reviewed_at"])
					if order.inventory_reserved and not order.is_paid:
						for item in order.items.all().order_by("product_id"):
							inventory = Inventory.objects.select_for_update().filter(product_id=item.product_id).first()
							if inventory is not None:
								inventory.stock_quantity += item.quantity
								inventory.save(update_fields=["stock_quantity", "last_updated"])
						order.inventory_reserved = False
						order.status = "pending"
						order.save(update_fields=["inventory_reserved", "status", "updated_at"])
			except Exception:
				logger.exception('Error rejecting UPI submission id=%s', candidate.pk)
	reject_submission.short_description = "Reject selected UPI submissions"


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
	list_display = ("order_number", "user", "status", "is_paid", "cancellation_reason", "cancelled_at", "cancelled_by")
	list_filter = ("status", "payment_method", "is_paid", "cancellation_reason", "cancelled_at")
	search_fields = ("order_number", "user__email", "cancellation_comment", "cancelled_by__email")
	readonly_fields = ("cancelled_at", "cancelled_by")


admin.site.register(OrderItem)
