from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import WishlistViewSet, wishlist_list_view

router = DefaultRouter()
router.register(r"wishlist", WishlistViewSet, basename="wishlist")

urlpatterns = [
    path("", wishlist_list_view, name="wishlist_list"),
    *router.urls,
]
