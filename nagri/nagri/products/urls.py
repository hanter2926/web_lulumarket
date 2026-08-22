from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, ProductViewSet, SubCategoryViewSet

router = DefaultRouter()
router.register(r"categories", CategoryViewSet, basename="categories")
router.register(r"subcategories", SubCategoryViewSet, basename="subcategories")
router.register(r"products", ProductViewSet, basename="products")

urlpatterns = router.urls
