from django.contrib import admin
from django.utils.html import format_html

from .models import DeliveryAssignment, DeliveryWorker, SellerApplication, Shopkeeper, Store


@admin.register(Shopkeeper)
class ShopkeeperAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "owner", "status", "shop_name", "created_at")
    list_filter = ("status", "owner")
    search_fields = ("user__email", "shop_name", "phone")


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "shopkeeper", "city", "is_active")
    list_filter = ("is_active", "shopkeeper")
    search_fields = ("name", "slug", "city")


@admin.register(DeliveryWorker)
class DeliveryWorkerAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "shopkeeper", "store", "status", "is_available")
    list_filter = ("status", "is_available", "shopkeeper")
    search_fields = ("user__email", "phone")


@admin.register(DeliveryAssignment)
class DeliveryAssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "store", "shopkeeper", "worker", "status", "assigned_at")
    list_filter = ("status", "shopkeeper", "store")
    search_fields = ("order__order_number", "worker__user__email")


@admin.register(SellerApplication)
class SellerApplicationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "email", "status", "submitted_at", "created_at")
    list_filter = ("status", "created_at")
    readonly_fields = ("submitted_at", "created_at", "updated_at", "otp_last_sent_at", "otp_created_at", "otp_expires_at")
    search_fields = ("user__email", "email", "aadhaar_number", "pan_number")

    fieldsets = (
        (None, {"fields": ("user", "email", "status")}),
        ("OTP", {"fields": ("otp_last_sent_at", "otp_created_at", "otp_expires_at", "otp_attempts")}),
        ("Application", {"fields": ("aadhaar_number", "pan_number", "pan_card_image", "passport_photo", "selected_categories")}),
        ("Review", {"fields": ("reviewed_by", "reviewed_at", "review_notes")}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser or request.user.is_staff:
            return qs
        # Non-staff should not see these in admin
        return qs.none()
