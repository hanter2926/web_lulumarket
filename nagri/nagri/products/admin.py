from django.contrib import admin
from django.forms.models import BaseInlineFormSet
from django.core.exceptions import ValidationError

from .models import Category, Product, ProductImage, Inventory
 


class ProductImageInlineFormset(BaseInlineFormSet):
	def clean(self):
		super().clean()
		images = 0
		for form in self.forms:
			if form.cleaned_data and not form.cleaned_data.get('DELETE', False):
				images += 1

		if images > 12:
			raise ValidationError('You cannot upload more than 12 images for a product.')


class ProductImageInline(admin.TabularInline):
	model = ProductImage
	extra = 1
	max_num = 12
	formset = ProductImageInlineFormset
	fields = ('image', 'alt_text', 'display_order')


class ProductAdmin(admin.ModelAdmin):
	list_display = ('id', 'name', 'category', 'price', 'is_active')
	inlines = [ProductImageInline]


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = (
        'product',
        'stock_quantity',
        'low_stock_threshold',
        'last_updated',
    )

admin.site.register(Category)
try:
	admin.site.unregister(Product)
except Exception:
	# Product may not be registered yet; ignore
	pass
admin.site.register(Product, ProductAdmin)
