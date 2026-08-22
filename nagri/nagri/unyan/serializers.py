from rest_framework import serializers


class BaseSerializer(serializers.Serializer):
    message = serializers.CharField(default="Nagri API")
