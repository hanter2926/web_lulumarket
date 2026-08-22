from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, ProductViewSet, SubCategoryViewSet, product_list_view

router = DefaultRouter()
router.register(r"categories", CategoryViewSet, basename="categories")
router.register(r"subcategories", SubCategoryViewSet, basename="subcategories")
router.register(r"products-api", ProductViewSet, basename="products-api")

urlpatterns = [
    path("", product_list_view, name="product_list"),
    *router.urls,
]
