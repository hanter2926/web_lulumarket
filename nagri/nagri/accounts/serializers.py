from rest_framework import serializers

from .models import Address, CustomUser, PaymentMethod, UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProfile
        fields = [
            "id",
            "user",
            "full_name",
            "phone",
            "avatar",
            "delivery_location",
            "address",
            "city",
            "state",
            "country",
            "pincode",
            "otp",
            "otp_expires_at",
            "is_phone_verified",
            "last_otp_sent_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["user", "otp", "otp_expires_at", "is_phone_verified", "last_otp_sent_at", "created_at", "updated_at"]


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = [
            "id",
            "user",
            "profile",
            "label",
            "full_name",
            "phone",
            "address_line_1",
            "address_line_2",
            "city",
            "state",
            "country",
            "pincode",
            "landmark",
            "is_default",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["user", "profile", "created_at", "updated_at"]


class PaymentMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentMethod
        fields = [
            "id",
            "user",
            "card_holder_name",
            "card_last4",
            "card_brand",
            "expiry_month",
            "expiry_year",
            "is_default",
            "created_at",
        ]
        read_only_fields = ["user", "created_at"]


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    addresses = AddressSerializer(many=True, read_only=True)
    payment_methods = PaymentMethodSerializer(many=True, read_only=True)
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "phone",
            "avatar",
            "is_vendor",
            "is_customer",
            "profile",
            "addresses",
            "payment_methods",
            "password",
        ]
        read_only_fields = ["is_vendor", "is_customer"]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = CustomUser(**validated_data)
        if password:
            user.set_password(password)
        user.save()
        UserProfile.objects.get_or_create(user=user, defaults={"full_name": user.get_full_name() or user.email})
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance
