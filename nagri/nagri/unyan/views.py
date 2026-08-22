from rest_framework.decorators import api_view
from rest_framework.response import Response

from .serializers import BaseSerializer


@api_view(["GET"])
def home(request):
    serializer = BaseSerializer()
    return Response(serializer.data)
