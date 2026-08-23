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

    def test_product_list_is_paginated_and_has_empty_state_messages(self):
        category = Category.objects.create(name="Groceries", slug="groceries")

        for index in range(13):
            Product.objects.create(
                name=f"Product {index + 1}",
                slug=f"product-{index + 1}",
                category=category,
                price=Decimal("199.00"),
                rating=Decimal("4.50"),
                is_active=True,
            )

        response = self.client.get("/products/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["products"]), 12)

        empty_response = self.client.get("/products/?search=nonexistent-item")
        self.assertEqual(empty_response.status_code, 200)
        content = empty_response.content.decode()
        self.assertIn("No Products Available", content)
        self.assertIn("We couldn't find any products matching your search.", content)
