from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CartItemViewSet, CartViewSet, cart_detail_view

router = DefaultRouter()
router.register(r"carts", CartViewSet, basename="carts")
router.register(r"items", CartItemViewSet, basename="cart-items")

urlpatterns = [
    path("", cart_detail_view, name="cart_detail"),
    *router.urls,
]
