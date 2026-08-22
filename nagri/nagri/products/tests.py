from decimal import Decimal

from django.test import TestCase

from .models import Category, Product, SubCategory


class ProductTests(TestCase):
    def test_product_filter_supports_search_and_price_range(self):
        category = Category.objects.create(name="Electronics", slug="electronics")
        subcategory = SubCategory.objects.create(name="Mobiles", slug="mobiles", category=category)
        Product.objects.create(
            name="Pixel Pro",
            slug="pixel-pro",
            category=category,
            subcategory=subcategory,
            brand="Google",
            price=Decimal("49999.00"),
            rating=Decimal("4.80"),
            description="Android flagship phone with premium features",
            tags="android, flagship, premium",
            is_featured=True,
            is_bestseller=True,
            is_active=True,
        )

        queryset = Product.objects.filter(category=category, price__gte=30000, price__lte=60000)
        self.assertEqual(queryset.count(), 1)
        self.assertTrue(Product.objects.filter(is_featured=True).exists())
        self.assertTrue(Product.objects.filter(is_bestseller=True).exists())
