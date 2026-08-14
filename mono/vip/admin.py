from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Product, Category, SubCategory, Color, Brand, Size, Order, OrderItem,
    Cart, CartItem, ProductImage, Profile, Wishlist, Coupon, Address, Wallet,
    CoinTransaction, ContactSubmission, SiteSettings,
)


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ('site_name', 'active', 'logo_preview', 'favicon_preview')
    list_filter = ('active',)
    search_fields = ('site_name',)
    readonly_fields = (
        'logo_preview', 'favicon_preview', 'default_image_preview',
        'hero_banner_preview', 'hero_background_preview'
    )

    def logo_preview(self, obj):
        if obj.logo:
            return format_html('<img src="{}" style="max-height:60px; max-width:120px; object-fit:contain;" />', obj.logo.url)
        return '—'
    logo_preview.short_description = 'Logo preview'

    def favicon_preview(self, obj):
        if obj.favicon:
            return format_html('<img src="{}" style="max-height:32px; max-width:32px; object-fit:contain;" />', obj.favicon.url)
        return '—'
    favicon_preview.short_description = 'Favicon preview'

    def default_image_preview(self, obj):
        if obj.default_image:
            return format_html('<img src="{}" style="max-height:80px; max-width:140px; object-fit:cover;" />', obj.default_image.url)
        return '—'
    default_image_preview.short_description = 'Default image preview'

    def hero_banner_preview(self, obj):
        if obj.hero_banner:
            return format_html('<img src="{}" style="max-height:80px; max-width:160px; object-fit:cover;" />', obj.hero_banner.url)
        return '—'
    hero_banner_preview.short_description = 'Hero banner preview'

    def hero_background_preview(self, obj):
        if obj.hero_background:
            return format_html('<img src="{}" style="max-height:80px; max-width:160px; object-fit:cover;" />', obj.hero_background.url)
        return '—'
    hero_background_preview.short_description = 'Hero background preview'


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active', 'icon_preview', 'image_preview')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    readonly_fields = ('icon_preview', 'image_preview')

    def icon_preview(self, obj):
        if obj.icon:
            return format_html('<img src="{}" style="max-height:40px; max-width:40px; object-fit:contain;" />', obj.icon.url)
        return '—'
    icon_preview.short_description = 'Icon preview'

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height:60px; max-width:100px; object-fit:cover;" />', obj.image.url)
        return '—'
    image_preview.short_description = 'Image preview'


admin.site.register(SubCategory)
admin.site.register(Brand)
admin.site.register(Color)
admin.site.register(Size)
admin.site.register(CartItem)
admin.site.register(Cart)
admin.site.register(ProductImage)
admin.site.register(Profile)
admin.site.register(Wishlist)
admin.site.register(Coupon)
admin.site.register(Address)
admin.site.register(Wallet)
admin.site.register(CoinTransaction)

@admin.register(ContactSubmission)
class ContactSubmissionAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'created_at', 'resolved')
    list_filter = ('resolved', 'created_at')
    search_fields = ('name', 'email', 'message')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'price', 'category', 'brand', 'stock_quantity', 'is_active', 'image_preview')
    list_filter = ('category', 'brand', 'is_active')
    search_fields = ('name', 'description')
    readonly_fields = ('image_preview',)

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" style="max-height:80px; max-width:120px; object-fit:cover;" />', obj.image.url)
        return '—'
    image_preview.short_description = 'Image preview'

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ('product', 'quantity', 'price')

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'total', 'payment_method', 'payment_status', 'created_at', 'status')
    list_filter = ('status', 'payment_method', 'created_at')
    search_fields = ('user__username', 'id')
    inlines = [OrderItemInline]


