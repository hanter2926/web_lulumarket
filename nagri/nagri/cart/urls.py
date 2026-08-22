from rest_framework.routers import DefaultRouter

from .views import CartItemViewSet, CartViewSet

router = DefaultRouter()
router.register(r"carts", CartViewSet, basename="carts")
router.register(r"items", CartItemViewSet, basename="cart-items")

urlpatterns = router.urls
