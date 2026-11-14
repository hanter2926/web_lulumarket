from django.contrib import admin
from django.db import transaction
from .models import Order, OrderItem, OrderRefund, OrderRefundItem
from rewards.utils import mark_reward_claim_used_for_order

from .models import UpiPaymentSubmission
import logging
from .services import complete_order_stock, complete_refund_and_restock, release_order_stock
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone


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
					complete_order_stock(order, actor=request.user)
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
						release_order_stock(order, reason="payment_rejected", actor=request.user)
						order.inventory_reserved = False
						order.status = "pending"
						order.save(update_fields=["inventory_reserved", "status", "updated_at"])
			except Exception:
				logger.exception('Error rejecting UPI submission id=%s', candidate.pk)
	reject_submission.short_description = "Reject selected UPI submissions"


class OrderAdminForm(forms.ModelForm):
	class Meta:
		model = Order
		fields = "__all__"

	def clean(self):
		cleaned_data = super().clean()
		status = cleaned_data.get("status")
		payment_method = cleaned_data.get("payment_method")
		if status in {"paid", "shipped", "completed"} and not self.instance.is_paid and payment_method != "cod":
			raise ValidationError("Online orders must be verified as paid before advancing their status.")
		return cleaned_data


class OrderItemInline(admin.TabularInline):
	model = OrderItem
	extra = 0
	can_delete = False
	readonly_fields = (
		"product", "variant", "quantity", "price", "regular_price",
		"sku_snapshot", "variant_attributes_snapshot", "tax_rate_snapshot",
		"tax_amount_snapshot",
	)
	fields = readonly_fields + ("fulfillment_status",)

	def has_add_permission(self, request, obj=None):
		return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
	form = OrderAdminForm
	list_display = ("order_number", "user", "status", "is_paid", "inventory_reserved", "cancellation_reason", "created_at")
	list_filter = ("status", "payment_method", "is_paid", "cancellation_reason", "created_at")
	search_fields = ("order_number", "user__email", "cancellation_comment", "cancelled_by__email")
	readonly_fields = (
		"subtotal", "discount_amount", "delivery_charge", "total_amount",
		"coupon_code", "is_paid", "inventory_reserved", "payment_provider",
		"razorpay_order_id", "razorpay_payment_id", "razorpay_signature",
		"cancelled_at", "cancelled_by",
	)
	inlines = (OrderItemInline,)

	def save_model(self, request, obj, form, change):
		if change:
			previous = Order.objects.get(pk=obj.pk)
			if obj.status == "cancelled" and previous.status != "cancelled" and previous.inventory_reserved:
				release_order_stock(previous, reason="order_cancelled", actor=request.user)
				obj.inventory_reserved = False
			if obj.status == "cancelled" and previous.status != "cancelled":
				obj.cancelled_at = timezone.now()
				obj.cancelled_by = request.user
				if not obj.cancellation_reason:
					obj.cancellation_reason = "OTHER"
			elif obj.payment_method == "cod" and obj.status == "completed":
				if previous.inventory_reserved:
					complete_order_stock(previous, actor=request.user)
					obj.inventory_reserved = False
				obj.is_paid = True
		super().save_model(request, obj, form, change)


class OrderRefundItemInline(admin.TabularInline):
	model = OrderRefundItem
	extra = 0


class RefundActionForm(admin.helpers.ActionForm):
	provider_refund_id = forms.CharField(
		required=False,
		max_length=255,
		label="Payment provider refund ID",
	)


@admin.register(OrderRefund)
class OrderRefundAdmin(admin.ModelAdmin):
	action_form = RefundActionForm
	list_display = ("id", "order", "amount", "status", "provider_refund_id", "stock_restocked_at", "created_at")
	list_filter = ("status", "created_at")
	search_fields = ("order__order_number", "provider_refund_id")
	readonly_fields = (
		"status", "reviewed_by", "reviewed_at", "stock_restocked_at",
		"created_at", "updated_at",
	)
	inlines = (OrderRefundItemInline,)
	actions = ("approve_refunds", "reject_refunds", "complete_refunds")
	fieldsets = (
		("Refund", {"fields": ("order", "amount", "status", "notes")}),
		("Provider", {"fields": ("provider_refund_id",)}),
		("Review", {"fields": ("reviewed_by", "reviewed_at", "stock_restocked_at", "created_at", "updated_at")}),
	)

	def save_model(self, request, obj, form, change):
		obj.full_clean()
		super().save_model(request, obj, form, change)

	@admin.action(description="Approve selected refund requests")
	def approve_refunds(self, request, queryset):
		count = 0
		for refund in queryset.filter(status="requested"):
			with transaction.atomic():
				refund = OrderRefund.objects.select_for_update().get(pk=refund.pk)
				refund.status = "approved"
				refund.reviewed_by = request.user
				refund.reviewed_at = timezone.now()
				refund.full_clean()
				for refund_item in refund.items.select_related("order_item"):
					refund_item.full_clean()
				refund.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
			count += 1
		self.message_user(request, f"{count} refund(s) approved.")

	@admin.action(description="Reject selected refund requests")
	def reject_refunds(self, request, queryset):
		count = queryset.filter(status__in=("requested", "approved")).update(
			status="rejected",
			reviewed_by=request.user,
			reviewed_at=timezone.now(),
		)
		self.message_user(request, f"{count} refund(s) rejected.")

	@admin.action(description="Complete approved refunds and restore eligible stock")
	def complete_refunds(self, request, queryset):
		provider_refund_id = request.POST.get("provider_refund_id", "").strip()
		approved_refunds = queryset.filter(status="approved").order_by("pk")
		if not provider_refund_id and approved_refunds.filter(order__payment_method__in=("razorpay", "netbanking", "upi", "wallet")).exists():
			self.message_user(
				request,
				"Enter the provider refund ID after confirming the external refund.",
				level="error",
			)
			return
		if approved_refunds.count() > 1 and provider_refund_id:
			self.message_user(request, "Complete each provider refund separately so its ID is recorded correctly.", level="error")
			return
		count = 0
		for refund in approved_refunds:
			complete_refund_and_restock(
				refund.pk,
				actor=request.user,
				provider_refund_id=provider_refund_id,
			)
			count += 1
		self.message_user(request, f"{count} refund(s) completed and eligible stock restored.")
