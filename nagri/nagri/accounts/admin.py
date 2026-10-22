from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm
from .models import CustomUser, UserProfile
from .models import HomeSlider
from django.utils.html import format_html

admin.site.register(UserProfile)


class CustomUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ("email", "username", "account_status")


class CustomUserChangeForm(UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = CustomUser
        fields = "__all__"


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    fieldsets = UserAdmin.fieldsets + (
        ("Account status", {"fields": ("account_status",)}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "username",
                    "password1",
                    "password2",
                    "account_status",
                ),
            },
        ),
    )
    list_display = UserAdmin.list_display + ("account_status",)

    def save_model(self, request, obj, form, change):
        obj.is_active = obj.account_status == CustomUser.AccountStatus.ACTIVE
        super().save_model(request, obj, form, change)


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
