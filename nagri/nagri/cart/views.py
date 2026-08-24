import json

from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from products.models import Product

from .models import Cart, CartItem
from .serializers import CartItemSerializer, CartSerializer


class CartViewSet(viewsets.ModelViewSet):
    serializer_class = CartSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Cart.objects.filter(user=self.request.user).prefetch_related("items__product")

    def create(self, request, *args, **kwargs):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        serializer = self.get_serializer(cart)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def add_item(self, request, pk=None):
        cart = self.get_object()
        product_id = request.data.get("product")
        quantity = int(request.data.get("quantity", 1))

        if not product_id:
            return Response({"detail": "Product ID is required."}, status=status.HTTP_400_BAD_REQUEST)

        product = Product.objects.get(id=product_id)
        item, created = CartItem.objects.get_or_create(cart=cart, product=product)
        if not created:
            item.quantity += quantity
        else:
            item.quantity = quantity
        item.save()
        return Response(CartItemSerializer(item).data, status=status.HTTP_201_CREATED)


class CartItemViewSet(viewsets.ModelViewSet):
    serializer_class = CartItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return CartItem.objects.filter(cart__user=self.request.user).select_related("cart", "product")

    def perform_create(self, serializer):
        cart, _ = Cart.objects.get_or_create(user=self.request.user)
        serializer.save(cart=cart)


@login_required(login_url='login_page')
@require_POST
def add_to_cart(request):
    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except (TypeError, ValueError):
        payload = {}

    product_id = payload.get("product_id") or payload.get("product")
    quantity = int(payload.get("quantity", 1) or 1)

    if not product_id:
        return JsonResponse({"error": "Product ID is required."}, status=400)
    if quantity <= 0:
        return JsonResponse({"error": "Quantity must be greater than zero."}, status=400)

    try:
        product = Product.objects.get(id=product_id, is_active=True)
    except Product.DoesNotExist:
        return JsonResponse({"error": "Product not found."}, status=404)

    cart, _ = Cart.objects.get_or_create(user=request.user)
    item, created = CartItem.objects.get_or_create(cart=cart, product=product)
    if created:
        item.quantity = quantity
    else:
        item.quantity += quantity
    item.save()

    return JsonResponse({
        "success": True,
        "added": True,
        "quantity": item.quantity,
        "count": cart.items.aggregate(total=Sum("quantity"))["total"] or 0,
        "item_id": item.id,
    })


@login_required(login_url='login_page')
def cart_count_view(request):
    cart, _ = Cart.objects.get_or_create(user=request.user)
    total = cart.items.aggregate(total=Sum("quantity"))["total"] or 0
    return JsonResponse({"count": total})


@login_required(login_url='login_page')
@require_POST
def remove_from_cart(request, item_id):
    cart = Cart.objects.filter(user=request.user).first()
    if not cart:
        return JsonResponse({"error": "Cart not found."}, status=404)

    deleted, _ = CartItem.objects.filter(cart=cart, id=item_id).delete()
    if not deleted:
        return JsonResponse({"error": "Item not found."}, status=404)

    return JsonResponse({"success": True, "count": cart.items.aggregate(total=Sum("quantity"))["total"] or 0})


@login_required(login_url='login_page')
@require_POST
def update_cart_item(request, item_id):
    try:
        payload = json.loads(request.body.decode("utf-8")) if request.body else {}
    except (TypeError, ValueError):
        payload = {}

    quantity = int(payload.get("quantity", 1) or 1)
    if quantity <= 0:
        return JsonResponse({"error": "Quantity must be greater than zero."}, status=400)

    cart = Cart.objects.filter(user=request.user).first()
    if not cart:
        return JsonResponse({"error": "Cart not found."}, status=404)

    try:
        item = CartItem.objects.get(cart=cart, id=item_id)
    except CartItem.DoesNotExist:
        return JsonResponse({"error": "Item not found."}, status=404)

    item.quantity = quantity
    item.save(update_fields=["quantity"])
    return JsonResponse({"success": True, "quantity": item.quantity, "count": cart.items.aggregate(total=Sum("quantity"))["total"] or 0})


@login_required(login_url='login_page')
def cart_detail_view(request):
    """Display shopping cart for the user"""
    cart, _ = Cart.objects.get_or_create(user=request.user)
    items = cart.items.all().select_related('product')

    total = sum(item.product.price * item.quantity for item in items)

    context = {
        'items': items,
        'total': total,
        'cart': cart,
    }
    return render(request, 'cart/cart_detail.html', context)
