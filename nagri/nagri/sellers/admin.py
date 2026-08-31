from django.contrib import admin
from django.utils.html import format_html

from .models import SellerApplication


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
