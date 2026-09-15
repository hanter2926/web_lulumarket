from rest_framework import serializers

from .models import DeliveryAssignment, DeliveryWorker, Shopkeeper, Store


class ShopkeeperSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    owner_email = serializers.EmailField(source="owner.email", read_only=True, allow_null=True)

    class Meta:
        model = Shopkeeper
        fields = [
            "id",
            "user",
            "user_email",
            "owner",
            "owner_email",
            "status",
            "shop_name",
            "phone",
            "address",
            "city",
            "state",
            "pincode",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "owner", "created_at", "updated_at"]


class StoreSerializer(serializers.ModelSerializer):
    shopkeeper_email = serializers.EmailField(source="shopkeeper.user.email", read_only=True)

    class Meta:
        model = Store
        fields = [
            "id",
            "shopkeeper",
            "shopkeeper_email",
            "name",
            "slug",
            "address",
            "city",
            "state",
            "pincode",
            "phone",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "shopkeeper", "created_at", "updated_at"]


class DeliveryWorkerSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    shopkeeper_name = serializers.CharField(source="shopkeeper.shop_name", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)

    class Meta:
        model = DeliveryWorker
        fields = [
            "id",
            "user",
            "user_email",
            "shopkeeper",
            "shopkeeper_name",
            "store",
            "store_name",
            "phone",
            "status",
            "is_available",
            "current_latitude",
            "current_longitude",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "user", "shopkeeper", "store", "created_at", "updated_at"]


class DeliveryAssignmentSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    shopkeeper_name = serializers.CharField(source="shopkeeper.shop_name", read_only=True)
    worker_name = serializers.CharField(source="worker.user.get_full_name", read_only=True)

    class Meta:
        model = DeliveryAssignment
        fields = [
            "id",
            "order",
            "order_number",
            "store",
            "store_name",
            "shopkeeper",
            "shopkeeper_name",
            "worker",
            "worker_name",
            "status",
            "assigned_at",
            "picked_up_at",
            "delivered_at",
            "notes",
        ]
        read_only_fields = ["id", "order", "store", "shopkeeper", "worker", "assigned_at", "picked_up_at", "delivered_at"]
