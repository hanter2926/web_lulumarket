from django.contrib import admin
from .models import UserProfile
from .models import HomeSlider
from django.utils.html import format_html

admin.site.register(UserProfile)


@admin.register(HomeSlider)
class HomeSliderAdmin(admin.ModelAdmin):
	list_display = ('id', 'title', 'display_order', 'is_active', 'image_preview', 'created_at')
	list_filter = ('is_active', 'created_at')
	search_fields = ('title', 'subtitle', 'button_text')
	ordering = ('display_order',)

	readonly_fields = ('image_preview',)

	def image_preview(self, obj):
		if not obj.image:
			return '(no image)'
		# Use a safe URL lookup; some storage backends may not have url property until saved
		img_url = getattr(obj.image, 'url', None)
		if not img_url:
			return '(no url)'
		return format_html('<img src="{}" style="max-height:80px;" />', img_url)

	image_preview.short_description = 'Image'
