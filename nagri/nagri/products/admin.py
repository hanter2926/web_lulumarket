from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet
from django.forms import ModelForm
from django.db.models import F, Q

from .forms import ProductForm
from .inventory import adjust_available_stock
from .models import (
    Category,
    Inventory,
    MeasurementRequirement,
    MeasurementFields,
    Product,
    ProductAttributeDefinition,
    ProductAttributeValue,
    ProductImage,
    ProductMeasurement,
    ProductPriceHistory,
    ProductVariant,
    StockMovement,
    SubCategory,
    VariantAttributeDefinition,
    VariantInventory,
    VariantMeasurement,
)


class ProductActionForm(admin.helpers.ActionForm):
    rejection_reason = forms.CharField(
        required=False,
        max_length=2000,
        label="Rejection reason",
        widget=forms.TextInput(attrs={"size": "50"}),
    )


class ProductImageInlineFormset(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        image_count = sum(
            1
            for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE", False)
            and form.cleaned_data.get("image")
        )
        if image_count > 12:
            raise ValidationError("You cannot upload more than 12 images for a product.")


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    verbose_name = "Product image"
    verbose_name_plural = "Product Gallery"
    extra = 1
    max_num = 12
    formset = ProductImageInlineFormset
    fields = ("image", "alt_text", "display_order")


class LowStockFilter(admin.SimpleListFilter):
    title = "stock level"
    parameter_name = "low_stock"

    def lookups(self, request, model_admin):
        return (("low", "Low stock"), ("ok", "Above threshold"))

    def queryset(self, request, queryset):
        if self.value() == "low":
            return queryset.filter(stock_quantity__lte=F("low_stock_threshold"))
        if self.value() == "ok":
            return queryset.filter(stock_quantity__gt=F("low_stock_threshold"))
        return queryset


class InventoryInline(admin.StackedInline):
    model = Inventory
    verbose_name = "Inventory Management"
    verbose_name_plural = "Inventory Management"
    extra = 0
    max_num = 1
    fields = ("stock_quantity", "low_stock_threshold", "reserved_quantity", "sold_quantity", "last_updated")
    readonly_fields = ("reserved_quantity", "sold_quantity", "last_updated")

    def has_delete_permission(self, request, obj=None):
        return False


class MeasurementAdminForm(ModelForm):
    class Meta:
        fields = (
            "dimension_unit", "length_mm", "width_mm", "height_mm",
            "weight_unit", "product_weight_g", "packaging_weight_g",
            "shipping_weight_g", "custom_size", "custom_weight_g",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("length_mm", "width_mm", "height_mm"):
            self.fields[field_name].label = field_name.replace("_mm", "").title()
            if self.instance.pk:
                self.initial[field_name] = self.instance.dimension_in_display_unit(
                    getattr(self.instance, field_name)
                )
        for field_name in ("product_weight_g", "packaging_weight_g", "shipping_weight_g", "custom_weight_g"):
            self.fields[field_name].label = field_name.replace("_g", "").replace("_", " ").title()
            if self.instance.pk:
                self.initial[field_name] = self.instance.weight_in_display_unit(
                    getattr(self.instance, field_name)
                )

    def clean(self):
        cleaned_data = super().clean()
        dimension_unit = cleaned_data.get("dimension_unit", "cm")
        weight_unit = cleaned_data.get("weight_unit", "g")
        for field_name in ("length_mm", "width_mm", "height_mm"):
            value = cleaned_data.get(field_name)
            if value is not None:
                cleaned_data[field_name] = MeasurementFields.convert_dimension_to_mm(value, dimension_unit)
        for field_name in ("product_weight_g", "packaging_weight_g", "shipping_weight_g", "custom_weight_g"):
            value = cleaned_data.get(field_name)
            if value is not None:
                cleaned_data[field_name] = MeasurementFields.convert_weight_to_grams(value, weight_unit)
        return cleaned_data


class ProductMeasurementAdminForm(MeasurementAdminForm):
    class Meta(MeasurementAdminForm.Meta):
        model = ProductMeasurement


class VariantMeasurementAdminForm(MeasurementAdminForm):
    class Meta(MeasurementAdminForm.Meta):
        model = VariantMeasurement


class ProductMeasurementInlineFormset(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        product = self.instance
        required = MeasurementRequirement.objects.filter(
            category=product.category,
            is_required=True,
        )
        if product.subcategory_id:
            category_fields = set(
                required.filter(subcategory__isnull=True).values_list("field_name", flat=True)
            )
            overrides = {
                row.field_name: row.is_required
                for row in MeasurementRequirement.objects.filter(
                    category=product.category,
                    subcategory=product.subcategory,
                )
            }
            required_fields = {
                field for field in category_fields if overrides.get(field, True)
            } | {
                field for field, is_required in overrides.items() if is_required
            }
        else:
            required_fields = set(required.filter(subcategory__isnull=True).values_list("field_name", flat=True))
        if not required_fields:
            return
        values = {}
        for form in self.forms:
            if form.cleaned_data and not form.cleaned_data.get("DELETE", False):
                values.update(form.cleaned_data)
        missing = [
            dict(MeasurementRequirement.MEASUREMENT_FIELDS).get(field, field)
            for field in required_fields
            if values.get(field) in (None, "")
        ]
        if missing:
            raise ValidationError(
                "Required for this category: " + ", ".join(missing)
            )


class ProductMeasurementInline(admin.StackedInline):
    model = ProductMeasurement
    verbose_name = "Size & Weight"
    verbose_name_plural = "Size & Weight"
    form = ProductMeasurementAdminForm
    formset = ProductMeasurementInlineFormset
    extra = 1
    max_num = 1
    fields = (
        "dimension_unit", "length_mm", "width_mm", "height_mm",
        "weight_unit", "product_weight_g", "packaging_weight_g",
        "shipping_weight_g", "custom_size", "custom_weight_g",
    )


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    verbose_name = "Product Variants"
    verbose_name_plural = "Product Variants"
    extra = 0
    readonly_fields = ("profit_margin",)
    fields = (
        "attributes", "sku", "price", "compare_price", "cost_price",
        "tax_rate", "tax_inclusive", "scheduled_sale_price",
        "scheduled_sale_start", "scheduled_sale_end", "profit_margin", "image", "is_active",
    )
    show_change_link = True


class ProductAttributeValueInlineFormSet(BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        product = self.instance
        definitions = ProductAttributeDefinition.objects.none()
        if product.category_id:
            definitions = ProductAttributeDefinition.objects.filter(
                category_id=product.category_id,
                is_active=True,
            ).filter(
                Q(subcategory__isnull=True)
                | Q(subcategory_id=product.subcategory_id)
            )
        for form in self.forms:
            if "definition" in form.fields:
                form.fields["definition"].queryset = definitions


class ProductAttributeValueInline(admin.TabularInline):
    model = ProductAttributeValue
    extra = 0
    fields = ("definition", "value")
    formset = ProductAttributeValueInlineFormSet


class VariantMeasurementInline(admin.StackedInline):
    model = VariantMeasurement
    form = VariantMeasurementAdminForm
    extra = 1
    max_num = 1
    fields = (
        "dimension_unit", "length_mm", "width_mm", "height_mm",
        "weight_unit", "product_weight_g", "packaging_weight_g",
        "shipping_weight_g", "custom_size", "custom_weight_g",
    )


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "default_tax_rate", "updated_at")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    fieldsets = (
        ("Category", {"fields": ("name", "slug", "description", "image")}),
        ("Tax defaults", {"fields": ("default_tax_rate",)}),
        ("Metadata", {"fields": ("created_at", "updated_at"), "classes": ("collapse",)}),
    )
    readonly_fields = ("created_at", "updated_at")


@admin.register(SubCategory)
class SubCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "slug", "updated_at")
    list_filter = ("category",)
    search_fields = ("name", "slug", "category__name")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(MeasurementRequirement)
class MeasurementRequirementAdmin(admin.ModelAdmin):
    list_display = ("category", "subcategory", "field_name", "is_required", "sort_order")
    list_filter = ("category", "subcategory", "is_required")
    ordering = ("category__name", "sort_order", "field_name")


@admin.register(VariantAttributeDefinition)
class VariantAttributeDefinitionAdmin(admin.ModelAdmin):
    list_display = ("label", "key", "category", "subcategory", "is_required", "sort_order")
    list_filter = ("category", "subcategory", "is_required")
    search_fields = ("key", "label", "category__name", "subcategory__name")
    ordering = ("category__name", "sort_order", "key")


@admin.register(ProductAttributeDefinition)
class ProductAttributeDefinitionAdmin(admin.ModelAdmin):
    list_display = (
        "label", "key", "category", "subcategory", "data_type",
        "is_required", "unit", "is_active", "sort_order",
    )
    list_filter = ("category", "subcategory", "data_type", "is_required", "is_active")
    search_fields = ("key", "label", "category__name", "subcategory__name")
    ordering = ("category__name", "subcategory__name", "sort_order", "key")


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = (
        "product", "stock_quantity", "reserved_quantity", "sold_quantity",
        "low_stock_threshold", "low_stock", "last_updated",
    )
    list_filter = (LowStockFilter, "last_updated")
    search_fields = ("product__name", "product__sku", "product__seller__email")
    readonly_fields = ("reserved_quantity", "sold_quantity", "last_updated")
    fields = ("product", "stock_quantity", "low_stock_threshold", "reserved_quantity", "sold_quantity", "last_updated")

    @admin.display(boolean=True, description="Low stock")
    def low_stock(self, obj):
        return obj.is_low_stock

    def save_model(self, request, obj, form, change):
        requested_quantity = obj.stock_quantity
        old_quantity = None
        if change:
            old_quantity = Inventory.objects.select_for_update().get(pk=obj.pk).stock_quantity
            if requested_quantity != old_quantity:
                obj.stock_quantity = old_quantity
        else:
            obj.stock_quantity = 0
        super().save_model(request, obj, form, change)
        if requested_quantity != (old_quantity or 0):
            adjust_available_stock(
                obj, requested_quantity, actor=request.user,
                reason="admin_adjustment", note="Admin stock adjustment",
            )


@admin.register(VariantInventory)
class VariantInventoryAdmin(admin.ModelAdmin):
    list_display = (
        "variant", "stock_quantity", "reserved_quantity", "sold_quantity",
        "low_stock_threshold", "low_stock", "last_updated",
    )
    list_filter = (LowStockFilter, "last_updated")
    search_fields = ("variant__sku", "variant__product__name", "variant__product__seller__email")
    readonly_fields = ("reserved_quantity", "sold_quantity", "last_updated")
    fields = ("variant", "stock_quantity", "low_stock_threshold", "reserved_quantity", "sold_quantity", "last_updated")

    @admin.display(boolean=True, description="Low stock")
    def low_stock(self, obj):
        return obj.is_low_stock

    def save_model(self, request, obj, form, change):
        requested_quantity = obj.stock_quantity
        old_quantity = None
        if change:
            old_quantity = VariantInventory.objects.select_for_update().get(pk=obj.pk).stock_quantity
            if requested_quantity != old_quantity:
                obj.stock_quantity = old_quantity
        else:
            obj.stock_quantity = 0
        super().save_model(request, obj, form, change)
        if requested_quantity != (old_quantity or 0):
            adjust_available_stock(
                obj, requested_quantity, actor=request.user,
                reason="admin_adjustment", note="Admin variant stock adjustment",
            )


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "created_at", "reason", "inventory", "variant_inventory",
        "available_delta", "reserved_delta", "sold_delta", "actor", "order_id",
    )
    list_filter = ("reason", "created_at")
    search_fields = ("note", "inventory__product__name", "variant_inventory__variant__sku")
    readonly_fields = (
        "inventory", "variant_inventory", "order_id", "actor",
        "available_delta", "reserved_delta", "sold_delta", "reason", "note", "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProductPriceHistory)
class ProductPriceHistoryAdmin(admin.ModelAdmin):
    list_display = ("product", "variant", "old_price", "new_price", "actor", "created_at")
    list_filter = ("created_at",)
    search_fields = ("product__name", "product__sku", "variant__sku", "actor__email")
    readonly_fields = (
        "product", "variant", "old_price", "new_price",
        "old_regular_price", "new_regular_price",
        "old_scheduled_sale_price", "new_scheduled_sale_price",
        "old_scheduled_sale_start", "new_scheduled_sale_start",
        "old_scheduled_sale_end", "new_scheduled_sale_end",
        "actor", "created_at", "note",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ("sku", "product", "attribute_summary", "price", "is_active")
    list_filter = ("is_active", "product__category")
    search_fields = ("sku", "product__name")
    readonly_fields = ("combination_key", "profit_margin")
    inlines = [VariantMeasurementInline]
    fields = (
        "product", "attributes", "combination_key", "sku", "price",
        "compare_price", "cost_price", "tax_rate", "tax_inclusive",
        "scheduled_sale_price", "scheduled_sale_start", "scheduled_sale_end",
        "profit_margin", "image", "is_active",
    )

    @admin.display(description="Attributes")
    def attribute_summary(self, obj):
        return ", ".join(f"{key}: {value}" for key, value in sorted(obj.attributes.items()))

    def save_model(self, request, obj, form, change):
        obj._price_history_actor = request.user
        obj.full_clean(exclude=["combination_key"])
        super().save_model(request, obj, form, change)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    form = ProductForm
    action_form = ProductActionForm
    list_display = (
        "id", "name", "sku", "category", "seller", "price",
        "review_status", "is_active", "is_flash_sale",
    )
    list_filter = (
        "review_status", "is_active", "is_featured", "is_bestseller",
        "is_flash_sale", "category", "subcategory",
    )
    search_fields = ("name", "slug", "sku", "tags", "brand", "seller__email")
    list_editable = ("is_active", "is_flash_sale")
    autocomplete_fields = ("category", "subcategory", "seller", "store")
    inlines = [
        ProductMeasurementInline,
        ProductAttributeValueInline,
        InventoryInline,
        ProductVariantInline,
        ProductImageInline,
    ]
    actions = ("approve_products", "reject_products")
    fieldsets = (
        ("Basic Information", {
            "fields": ("name", "slug", "sku", "category", "subcategory", "brand", "seller", "store"),
        }),
        ("Description", {"fields": ("short_description", "description", "tags")}),
        ("Pricing", {
            "fields": (
                "price", "compare_price", "cost_price", "tax_rate", "tax_inclusive",
                "scheduled_sale_price", "scheduled_sale_start", "scheduled_sale_end",
                "profit_margin",
            ),
        }),
        ("Images", {"fields": ("image",)}),
        ("Publishing and Approval", {
            "fields": ("review_status", "rejection_reason", "is_active", "is_featured", "is_bestseller"),
        }),
        ("Flash Sale", {"fields": ("is_flash_sale", "flash_sale_start", "flash_sale_end")}),
        ("Metadata", {"fields": ("rating", "created_at", "updated_at"), "classes": ("collapse",)}),
    )
    readonly_fields = ("created_at", "updated_at", "rating", "profit_margin")

    @admin.action(description="Approve selected products")
    def approve_products(self, request, queryset):
        count = queryset.update(review_status="approved", rejection_reason="", is_active=True)
        self.message_user(request, f"{count} product(s) approved and published.", messages.SUCCESS)

    @admin.action(description="Reject selected products (enter reason above)")
    def reject_products(self, request, queryset):
        reason = request.POST.get("rejection_reason", "").strip()
        if not reason:
            self.message_user(request, "Enter a rejection reason before applying this action.", messages.ERROR)
            return
        count = queryset.update(review_status="rejected", rejection_reason=reason, is_active=False)
        self.message_user(request, f"{count} product(s) rejected.", messages.SUCCESS)

    def save_model(self, request, obj, form, change):
        obj._price_history_actor = request.user
        obj.full_clean()
        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        if formset.model is not Inventory:
            super().save_formset(request, form, formset, change)
            return
        old_quantities = {
            form.instance.pk: Inventory.objects.select_for_update().get(pk=form.instance.pk).stock_quantity
            for form in formset.forms
            if form.instance.pk and form.has_changed() and not form.cleaned_data.get("DELETE", False)
        }
        new_quantities = {
            form.instance: form.cleaned_data.get("stock_quantity", 0)
            for form in formset.forms
            if form.cleaned_data
            and not form.cleaned_data.get("DELETE", False)
            and (form.has_changed() or not form.instance.pk)
        }
        super().save_formset(request, form, formset, change)
        for inventory, requested_quantity in new_quantities.items():
            old_quantity = old_quantities.get(inventory.pk)
            if old_quantity is None:
                old_quantity = 0
            if requested_quantity == old_quantity:
                continue
            Inventory.objects.filter(pk=inventory.pk).update(stock_quantity=old_quantity)
            inventory.stock_quantity = old_quantity
            adjust_available_stock(
                inventory,
                requested_quantity,
                actor=request.user,
                reason="admin_adjustment",
                note="Admin product form stock adjustment",
            )
