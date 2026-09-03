from django.contrib import admin
from .models import UserProfile
from .models import HomeSlider
from django.utils.html import format_html

admin.site.register(UserProfile)


@admin.register(HomeSlider)
class HomeSliderAdmin(admin.ModelAdmin):
	list_display = ('__str__', 'display_order', 'is_active', 'created_at')
	list_filter = ('is_active',)
	search_fields = ('title', 'subtitle', 'button_text')
	ordering = ('display_order',)

	readonly_fields = ('image_preview',)

	def image_preview(self, obj):
		if not obj.image:
			return '(no image)'
		return format_html('<img src="{}" style="max-height:80px;" />', obj.image.url)

	image_preview.short_description = 'Image'
