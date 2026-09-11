from django.contrib import admin

from .models import MysteryRewardClaim, MysteryRewardConfig, MysteryRewardType


@admin.register(MysteryRewardConfig)
class MysteryRewardConfigAdmin(admin.ModelAdmin):
    list_display = ("display_title", "is_enabled", "claim_expiry_days", "updated_at")

    def has_add_permission(self, request):
        return not MysteryRewardConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MysteryRewardType)
class MysteryRewardTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "reward_kind", "reward_label", "weight", "is_active", "display_order")
    list_filter = ("reward_kind", "is_active")
    search_fields = ("name", "description")
    ordering = ("display_order", "name")


@admin.register(MysteryRewardClaim)
class MysteryRewardClaimAdmin(admin.ModelAdmin):
    list_display = ("reward_code", "user", "reward_type", "claimed_date", "claimed_at", "expires_at", "is_used", "is_active")
    list_filter = ("is_used", "is_active", "claimed_date", "reward_type__reward_kind")
    search_fields = ("reward_code", "user__email", "user__username", "reward_type__name")
    readonly_fields = ("reward_code", "claimed_date", "claimed_at", "expires_at", "used_at")
