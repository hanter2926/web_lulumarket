from rest_framework import serializers

from products.serializers import ProductSerializer

from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product", "quantity", "price"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "user",
            "order_number",
            "total_amount",
            "status",
            "tracking_status",
            "tracking_code",
            "is_paid",
            "payment_provider",
            "razorpay_order_id",
            "razorpay_payment_id",
            "razorpay_signature",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["user", "created_at", "updated_at"]
