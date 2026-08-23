from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required

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


@login_required(login_url='login')
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
