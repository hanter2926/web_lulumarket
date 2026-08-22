from rest_framework import serializers

from .models import Category, Inventory, Product, SubCategory


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
        fields = ["id", "product", "stock_quantity", "low_stock_threshold", "last_updated"]
        read_only_fields = ["product", "last_updated"]


class ProductSerializer(serializers.ModelSerializer):
    inventory = InventorySerializer(read_only=True)
    category_name = serializers.SerializerMethodField()
    subcategory_name = serializers.SerializerMethodField()
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "slug",
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
            "rating",
            "image",
            "is_featured",
            "is_bestseller",
            "is_active",
            "in_stock",
            "inventory",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["created_at", "updated_at", "inventory", "in_stock"]

    def get_category_name(self, obj):
        return obj.category.name

    def get_subcategory_name(self, obj):
        return obj.subcategory.name if obj.subcategory else None
