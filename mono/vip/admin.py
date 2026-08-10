from django.contrib import admin
from .models import (
    Product, Category, SubCategory, Color, Brand, Size, Order, OrderItem,
    Cart, CartItem, ProductImage, Profile, Wishlist, Coupon, Address, Wallet,
    CoinTransaction,
    ContactSubmission,
)
admin.site.register(Category)
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
    list_display = ('name', 'price', 'category', 'brand', 'stock_quantity')
    list_filter = ('category', 'brand')
    search_fields = ('name', 'description')

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


