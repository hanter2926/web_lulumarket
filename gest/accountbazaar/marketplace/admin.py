from django.contrib import admin

from .models import Listing


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
	list_display = ("title", "category", "seller", "price", "status", "is_verified", "created_at")
	list_filter = ("category", "status", "is_verified")
	search_fields = ("title", "game_name", "game_id", "website_name", "app_name", "seller__username")
	readonly_fields = ("created_at",)
	fieldsets = (
		("Listing", {"fields": ("seller", "category", "title", "description", "price", "status", "is_verified", "image")}),
		("Game information", {"fields": ("game_name", "game_id", "game_level", "game_rank")}),
		("Website information", {"fields": ("website_name", "website_url")}),
		("App information", {"fields": ("app_name", "app_url", "platform", "features")}),
		("Other public details", {"fields": ("public_details", "created_at")}),
	)
