from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CartItemViewSet, CartViewSet, add_to_cart, cart_count_view, cart_detail_view

router = DefaultRouter()
router.register(r"carts", CartViewSet, basename="carts")
router.register(r"items", CartItemViewSet, basename="cart-items")

urlpatterns = [
    path("", cart_detail_view, name="cart_detail"),
    path("add/", add_to_cart, name="cart_add"),
    path("count/", cart_count_view, name="cart_count"),
    *router.urls,
]
