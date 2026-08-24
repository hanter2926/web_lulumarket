from rest_framework import permissions, status, viewsets
from rest_framework.response import Response
from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from .models import Wishlist
from .serializers import WishlistSerializer


class WishlistViewSet(viewsets.ModelViewSet):
    serializer_class = WishlistSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Wishlist.objects.filter(user=self.request.user).select_related("user", "product")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


@login_required(login_url='login_page')
def wishlist_list_view(request):
    """Display user's wishlist"""
    wishlist_items = Wishlist.objects.filter(user=request.user).select_related('product')
    
    context = {
        'wishlist_items': wishlist_items,
    }
    return render(request, 'wishlist/wishlist.html', context)
