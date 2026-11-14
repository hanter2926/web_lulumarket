from rest_framework import serializers

from .models import (
    Category,
    Inventory,
    Product,
    ProductMeasurement,
    ProductVariant,
    SubCategory,
    VariantInventory,
)


class SubCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = SubCategory
        fields = ["id", "category", "name", "slug", "description", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]


class CategorySerializer(serializers.ModelSerializer):
    subcategories = SubCategorySerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "description", "subcategories", "created_at", "updated_at"]
        read_only_fields = ["created_at", "updated_at"]


class InventorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Inventory
        fields = [
            "id", "product", "stock_quantity", "reserved_quantity",
            "sold_quantity", "low_stock_threshold", "last_updated",
        ]
        read_only_fields = ["product", "last_updated"]


class ProductMeasurementSerializer(serializers.ModelSerializer):
    length = serializers.SerializerMethodField()
    width = serializers.SerializerMethodField()
    height = serializers.SerializerMethodField()
    product_weight = serializers.SerializerMethodField()
    packaging_weight = serializers.SerializerMethodField()
    shipping_weight = serializers.SerializerMethodField()
    custom_weight = serializers.SerializerMethodField()

    class Meta:
        model = ProductMeasurement
        fields = [
            "dimension_unit", "length", "width", "height", "weight_unit",
            "product_weight", "packaging_weight", "shipping_weight",
            "custom_size", "custom_weight",
        ]

    def get_length(self, obj):
        return obj.dimension_in_display_unit(obj.length_mm)

    def get_width(self, obj):
        return obj.dimension_in_display_unit(obj.width_mm)

    def get_height(self, obj):
        return obj.dimension_in_display_unit(obj.height_mm)

    def get_product_weight(self, obj):
        return obj.weight_in_display_unit(obj.product_weight_g)

    def get_packaging_weight(self, obj):
        return obj.weight_in_display_unit(obj.packaging_weight_g)

    def get_shipping_weight(self, obj):
        return obj.weight_in_display_unit(obj.shipping_weight_g)

    def get_custom_weight(self, obj):
        return obj.weight_in_display_unit(obj.custom_weight_g)


class VariantInventorySerializer(serializers.ModelSerializer):
    class Meta:
        model = VariantInventory
        fields = ["stock_quantity", "reserved_quantity", "sold_quantity", "low_stock_threshold"]


class ProductVariantSerializer(serializers.ModelSerializer):
    inventory = VariantInventorySerializer(read_only=True)
    current_price = serializers.SerializerMethodField()
    regular_price = serializers.SerializerMethodField()
    measurement = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            "id", "sku", "attributes", "price", "compare_price",
            "current_price", "regular_price", "image", "is_active",
            "inventory", "measurement",
        ]

    def get_current_price(self, obj):
        return obj.get_current_price()

    def get_regular_price(self, obj):
        return obj.get_regular_price()

    def get_measurement(self, obj):
        if not hasattr(obj, "measurement"):
            return None
        return _serialize_measurement(obj.measurement)


def _serialize_measurement(measurement):
    return {
        "dimension_unit": measurement.dimension_unit,
        "length": measurement.dimension_in_display_unit(measurement.length_mm),
        "width": measurement.dimension_in_display_unit(measurement.width_mm),
        "height": measurement.dimension_in_display_unit(measurement.height_mm),
        "weight_unit": measurement.weight_unit,
        "product_weight": measurement.weight_in_display_unit(measurement.product_weight_g),
        "packaging_weight": measurement.weight_in_display_unit(measurement.packaging_weight_g),
        "shipping_weight": measurement.weight_in_display_unit(measurement.shipping_weight_g),
        "custom_size": measurement.custom_size,
        "custom_weight": measurement.weight_in_display_unit(measurement.custom_weight_g),
    }


class ProductSerializer(serializers.ModelSerializer):
    inventory = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    subcategory_name = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)
    measurement = serializers.SerializerMethodField()
    variants = serializers.SerializerMethodField()
    current_price = serializers.SerializerMethodField()
    regular_price = serializers.SerializerMethodField()
    discount_amount = serializers.SerializerMethodField()
    discount_percentage = serializers.SerializerMethodField()
    effective_tax_rate = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True)
    attributes = serializers.SerializerMethodField()
    has_variants = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
            "sku",
            "category",
            "category_name",
            "subcategory",
            "subcategory_name",
            "brand",
            "tags",
            "short_description",
            "description",
            "price",
            "compare_price",
            "current_price",
            "regular_price",
            "discount_amount",
            "discount_percentage",
            "effective_tax_rate",
            "tax_inclusive",
            "measurement",
            "attributes",
            "variants",
            "rating",
            "image",
            "is_featured",
            "is_bestseller",
            "is_active",
            "in_stock",
            "has_variants",
            "inventory",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at", "inventory", "in_stock"]

    def get_category_name(self, obj):
        return obj.category.name

    def get_inventory(self, obj):
        if obj.has_variants or not hasattr(obj, "inventory"):
            return None
        return InventorySerializer(obj.inventory, context=self.context).data

    def get_subcategory_name(self, obj):
        return obj.subcategory.name if obj.subcategory else None

    def get_measurement(self, obj):
        if not hasattr(obj, "measurement"):
            return None
        return _serialize_measurement(obj.measurement)

    def get_variants(self, obj):
        variants = obj.variants.filter(is_active=True).select_related("inventory", "measurement")
        return ProductVariantSerializer(variants, many=True, context=self.context).data

    def get_current_price(self, obj):
        return obj.get_current_price()

    def get_regular_price(self, obj):
        return obj.get_regular_price()

    def get_discount_amount(self, obj):
        return obj.get_discount_amount()

    def get_discount_percentage(self, obj):
        return obj.get_discount_percentage()

    def get_attributes(self, obj):
        return [
            {
                "key": row.definition.key,
                "label": row.definition.label,
                "value": row.value,
                "unit": row.definition.unit,
                "data_type": row.definition.data_type,
            }
            for row in obj.attribute_values.select_related("definition").filter(
                definition__is_active=True
            )
        ]
