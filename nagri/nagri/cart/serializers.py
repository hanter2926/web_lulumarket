from rest_framework import serializers

from products.serializers import ProductSerializer

from .models import Cart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        source="product",
        queryset=CartItem._meta.get_field("product").remote_field.model.objects.all(),
        write_only=True,
    )

    class Meta:
        model = CartItem
        fields = ["id", "product", "product_id", "quantity", "added_at"]
        read_only_fields = ["added_at"]


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Cart
        fields = ["id", "user", "items", "created_at", "updated_at"]
        read_only_fields = ["user", "created_at", "updated_at"]
