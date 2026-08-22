from rest_framework import serializers

from products.serializers import ProductSerializer

from .models import Wishlist


class WishlistSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    product_id = serializers.PrimaryKeyRelatedField(
        source="product",
        queryset=Wishlist._meta.get_field("product").remote_field.model.objects.all(),
        write_only=True,
    )

    class Meta:
        model = Wishlist
        fields = ["id", "user", "product", "product_id", "created_at"]
        read_only_fields = ["user", "created_at"]
