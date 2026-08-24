import json

from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from rest_framework import permissions, status, viewsets
from rest_framework.response import Response

from products.models import Product

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
@require_POST
def toggle_wishlist(request):
    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except (TypeError, ValueError):
        payload = {}

    product_id = payload.get("product_id") or payload.get("product")
    if not product_id:
        return JsonResponse({"error": "Product ID is required."}, status=400)

    try:
        product = Product.objects.get(id=product_id, is_active=True)
    except Product.DoesNotExist:
        return JsonResponse({"error": "Product not found."}, status=404)

    wishlist_item, created = Wishlist.objects.get_or_create(user=request.user, product=product)
    if not created:
        wishlist_item.delete()
        return JsonResponse({"success": True, "added": False, "count": Wishlist.objects.filter(user=request.user).count()})

    return JsonResponse({"success": True, "added": True, "count": Wishlist.objects.filter(user=request.user).count()})


@login_required(login_url='login_page')
def wishlist_count_view(request):
    return JsonResponse({"count": Wishlist.objects.filter(user=request.user).count()})


@login_required(login_url='login_page')
def wishlist_list_view(request):
    """Display user's wishlist"""
    wishlist_items = Wishlist.objects.filter(user=request.user).select_related('product')

    context = {
        'wishlist_items': wishlist_items,
    }
    return render(request, 'wishlist/wishlist.html', context)
