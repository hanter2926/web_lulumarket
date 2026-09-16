from rest_framework import serializers

from .models import Area, DeliveryAssignment, DeliveryIncident, DeliveryWorker, RouteIssue, Shopkeeper, Store


class AreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Area
        fields = [
            "id", "name", "code", "city", "state", "postal_code", "description",
            "latitude", "longitude", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


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
    area_name = serializers.CharField(source="area.name", read_only=True, allow_null=True)

    class Meta:
        model = Store
        fields = [
            "id",
            "shopkeeper",
            "shopkeeper_email",
            "area",
            "area_name",
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
    area_name = serializers.CharField(source="area.name", read_only=True, allow_null=True)

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
            "area",
            "area_name",
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


class DeliveryIncidentSerializer(serializers.ModelSerializer):
    client_id = serializers.UUIDField(required=False)
    area_name = serializers.CharField(source="area.name", read_only=True)
    reporter_email = serializers.EmailField(source="reported_by.user.email", read_only=True)
    assignment_number = serializers.CharField(source="delivery_assignment.order.order_number", read_only=True, allow_null=True)

    class Meta:
        model = DeliveryIncident
        fields = [
            "id", "client_id", "area", "area_name", "delivery_assignment", "assignment_number",
            "reported_by", "reporter_email", "incident_type", "title", "description", "severity",
            "latitude", "longitude", "status", "occurred_at", "resolved_at", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "reported_by", "reporter_email", "created_at", "updated_at"]
        extra_kwargs = {"area": {"required": False}, "client_id": {"required": False}}

    def validate(self, attrs):
        request = self.context.get("request")
        worker = getattr(getattr(request, "user", None), "delivery_worker_profile", None)
        assignment = attrs.get("delivery_assignment", self.instance.delivery_assignment if self.instance else None)
        area = attrs.get("area", self.instance.area if self.instance else None)
        if worker and assignment and assignment.worker_id != worker.id:
            raise serializers.ValidationError({"delivery_assignment": "You can only report incidents for your own assignment."})
        effective_area = area or (assignment.store.area if assignment else None) or (worker.area if worker else None) or (worker.store.area if worker else None)
        if effective_area is None:
            raise serializers.ValidationError({"area": "An operational area is required."})
        if assignment and assignment.store.area_id and assignment.store.area_id != effective_area.id:
            raise serializers.ValidationError({"area": "The incident area must match the assignment store area."})
        if worker and worker.area_id and worker.area_id != effective_area.id:
            raise serializers.ValidationError({"area": "The incident area must match your worker area."})
        return attrs


class RouteIssueSerializer(serializers.ModelSerializer):
    area_name = serializers.CharField(source="area.name", read_only=True)
    reporter_email = serializers.EmailField(source="reported_by.user.email", read_only=True, allow_null=True)
    assignment_number = serializers.CharField(source="delivery_assignment.order.order_number", read_only=True, allow_null=True)

    class Meta:
        model = RouteIssue
        fields = [
            "id", "area", "area_name", "title", "description", "issue_type", "severity", "status",
            "latitude", "longitude", "reported_by", "reporter_email", "delivery_assignment", "assignment_number",
            "starts_at", "expected_end_at", "resolved_at", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "reported_by", "reporter_email", "resolved_at", "created_at", "updated_at"]
        extra_kwargs = {"area": {"required": False}}

    def validate(self, attrs):
        request = self.context.get("request")
        worker = getattr(getattr(request, "user", None), "delivery_worker_profile", None)
        area = attrs.get("area", self.instance.area if self.instance else None)
        assignment = attrs.get("delivery_assignment", self.instance.delivery_assignment if self.instance else None)
        effective_area = area or (assignment.store.area if assignment else None) or (worker.area if worker else None) or (worker.store.area if worker else None)
        if effective_area is None:
            raise serializers.ValidationError({"area": "An operational area is required."})
        if assignment and assignment.store.area_id and assignment.store.area_id != effective_area.id:
            raise serializers.ValidationError({"area": "The route issue area must match the assignment store area."})
        if worker and worker.area_id and worker.area_id != effective_area.id:
            raise serializers.ValidationError({"area": "The route issue area must match your worker area."})
        if worker and assignment and assignment.worker_id != worker.id:
            raise serializers.ValidationError({"delivery_assignment": "You can only link your own assignment."})
        if self.instance and self.instance.status == "resolved" and attrs.get("status", "resolved") != "resolved":
            raise serializers.ValidationError({"status": "Resolved route issues cannot be reopened."})
        return attrs
