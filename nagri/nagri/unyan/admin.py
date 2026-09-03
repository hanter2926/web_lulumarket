from django.contrib import admin
from django.utils.html import format_html
from .models import HomeSlider


@admin.register(HomeSlider)
class HomeSliderAdmin(admin.ModelAdmin):
    """Admin interface for managing homepage sliders."""
    
    list_display = [
        'title_display',
        'display_order',
        'active_status',
        'image_preview',
        'created_at_short',
    ]
    
    list_filter = [
        'is_active',
        'created_at',
        'updated_at',
    ]
    
    search_fields = [
        'title',
        'subtitle',
        'button_text',
    ]
    
    list_editable = [
        'display_order',
    ]
    
    readonly_fields = [
        'image_preview_large',
        'mobile_image_preview',
        'created_at',
        'updated_at',
    ]
    
    fieldsets = (
        ('Slider Content', {
            'fields': ('title', 'subtitle', 'button_text', 'button_link'),
        }),
        ('Images', {
            'fields': ('image', 'image_preview_large', 'mobile_image', 'mobile_image_preview'),
            'description': 'Desktop image recommended: 1200x400px. Mobile image (optional) recommended: 600x400px.',
        }),
        ('Display Settings', {
            'fields': ('display_order', 'is_active'),
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    ordering = ('display_order', 'created_at')
    
    def title_display(self, obj):
        """Display title with truncation."""
        return obj.title[:50] + ('...' if len(obj.title) > 50 else '')
    title_display.short_description = 'Title'
    
    def active_status(self, obj):
        """Display active status as colored indicator."""
        if obj.is_active:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ Active</span>'
            )
        return format_html(
            '<span style="color: gray;">○ Inactive</span>'
        )
    active_status.short_description = 'Status'
    
    def image_preview(self, obj):
        """Display small image preview in list view."""
        if obj.image:
            return format_html(
                '<img src="{}" style="max-width: 100px; max-height: 50px; border-radius: 4px;" />',
                obj.image.url
            )
        return 'No image'
    image_preview.short_description = 'Image'
    
    def image_preview_large(self, obj):
        """Display large image preview in detail view."""
        if obj.image:
            return format_html(
                '<img src="{}" style="max-width: 400px; max-height: 300px; border-radius: 4px; margin-top: 10px;" />',
                obj.image.url
            )
        return 'No image uploaded'
    image_preview_large.short_description = 'Desktop Image Preview'
    
    def mobile_image_preview(self, obj):
        """Display mobile image preview in detail view."""
        if obj.mobile_image:
            return format_html(
                '<img src="{}" style="max-width: 300px; max-height: 400px; border-radius: 4px; margin-top: 10px;" />',
                obj.mobile_image.url
            )
        return 'No mobile image uploaded (optional)'
    mobile_image_preview.short_description = 'Mobile Image Preview'
    
    def created_at_short(self, obj):
        """Display created date in short format."""
        return obj.created_at.strftime('%Y-%m-%d %H:%M')
    created_at_short.short_description = 'Created'
    
    def save_model(self, request, obj, form, change):
        """Save model with validation."""
        try:
            super().save_model(request, obj, form, change)
            self.message_user(request, 'Slider saved successfully.', level='success')
        except Exception as e:
            self.message_user(request, f'Error saving slider: {str(e)}', level='error')
            raise
