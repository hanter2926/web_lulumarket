from rest_framework import serializers

from products.models import ProductVariant
from products.serializers import ProductSerializer

from .models import Cart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        source="product",
        queryset=CartItem._meta.get_field("product").remote_field.model.objects.all(),
        write_only=True,
    )
    variant_id = serializers.PrimaryKeyRelatedField(
        source="variant",
        queryset=ProductVariant.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = CartItem
        fields = ["id", "product", "product_id", "variant_id", "quantity", "added_at"]
        read_only_fields = ["added_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        product = attrs.get("product", getattr(self.instance, "product", None))
        variant = attrs.get("variant", getattr(self.instance, "variant", None))
        if variant and (product is None or variant.product_id != product.pk):
            raise serializers.ValidationError({"variant_id": "The selected variant does not belong to this product."})
        if product and (not product.is_active or product.review_status != "approved"):
            raise serializers.ValidationError({"product_id": "The selected product is unavailable."})
        if variant and not variant.is_active:
            raise serializers.ValidationError({"variant_id": "The selected product variant is unavailable."})
        if not variant and product and product.variants.exists():
            raise serializers.ValidationError({"variant_id": "Select an available variant for this product."})
        return attrs


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Cart
        fields = ["id", "user", "items", "created_at", "updated_at"]
        read_only_fields = ["user", "created_at", "updated_at"]
