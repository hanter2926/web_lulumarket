from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import WishlistViewSet, toggle_wishlist, wishlist_count_view, wishlist_list_view

router = DefaultRouter()
router.register(r"wishlist", WishlistViewSet, basename="wishlist")

urlpatterns = [
    path("", wishlist_list_view, name="wishlist_list"),
    path("toggle/", toggle_wishlist, name="wishlist_toggle"),
    path("count/", wishlist_count_view, name="wishlist_count"),
    *router.urls,
]
