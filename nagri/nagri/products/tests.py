from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from orders.models import Order, OrderItem
from .models import Category, Product, SubCategory


class ProductTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.customer = User.objects.create_user(
            username="catalog-customer",
            email="catalog-customer@example.com",
            password="test-password",
        )
        self.staff = User.objects.create_user(
            username="catalog-staff",
            email="catalog-staff@example.com",
            password="test-password",
            is_staff=True,
        )
        self.category = Category.objects.create(
            name="Catalog Test Category",
            slug="catalog-test-category",
        )
        self.product = Product.objects.create(
            name="Rice",
            slug="rice",
            category=self.category,
            price=Decimal("5.00"),
        )

    def test_catalog_api_keeps_public_reads_available(self):
        self.assertEqual(
            self.client.get(reverse("categories-list")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("subcategories-list")).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("products-api-list")).status_code,
            200,
        )

    def test_catalog_api_rejects_anonymous_and_customer_writes(self):
        category_url = reverse("categories-detail", args=[self.category.pk])
        product_url = reverse("products-api-detail", args=[self.product.pk])

        self.assertEqual(
            self.client.post(
                reverse("categories-list"),
                {"name": "Unauthorized", "slug": "unauthorized"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("products-api-list"),
                {
                    "name": "Unauthorized",
                    "slug": "unauthorized-product",
                    "category": self.category.pk,
                    "price": "1.00",
                },
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("subcategories-list"),
                {
                    "category": self.category.pk,
                    "name": "Unauthorized Subcategory",
                    "slug": "unauthorized-subcategory",
                },
            ).status_code,
            403,
        )

        self.client.force_login(self.customer)
        self.assertEqual(
            self.client.patch(
                product_url,
                {"price": "0.01", "is_active": False},
                content_type="application/json",
            ).status_code,
            403,
        )
        self.assertEqual(self.client.delete(category_url).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("categories-list"),
                {"name": "Customer Category", "slug": "customer-category"},
            ).status_code,
            403,
        )

        self.product.refresh_from_db()
        self.assertEqual(self.product.price, Decimal("5.00"))
        self.assertTrue(self.product.is_active)

    def test_staff_can_manage_catalog_through_api(self):
        self.client.force_login(self.staff)
        category_response = self.client.post(
            reverse("categories-list"),
            {"name": "New Category", "slug": "new-category"},
        )
        self.assertEqual(category_response.status_code, 201)

        subcategory_response = self.client.post(
            reverse("subcategories-list"),
            {
                "category": self.category.pk,
                "name": "New Subcategory",
                "slug": "new-subcategory",
            },
        )
        self.assertEqual(subcategory_response.status_code, 201)

        product_response = self.client.post(
            reverse("products-api-list"),
            {
                "name": "New Product",
                "slug": "new-product",
                "category": self.category.pk,
                "price": "9.00",
            },
        )
        self.assertEqual(product_response.status_code, 201)
        product_url = reverse(
            "products-api-detail",
            args=[product_response.data["id"]],
        )
        update_response = self.client.patch(
            product_url,
            {"price": "10.00"},
            content_type="application/json",
        )
        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_response.data["price"], "10.00")
        self.assertEqual(self.client.delete(product_url).status_code, 204)

    def test_staff_cannot_delete_products_or_categories_in_order_history(self):
        order = Order.objects.create(
            user=self.customer,
            order_number="CATALOG-ORDER-1",
            total_amount=Decimal("5.00"),
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            quantity=1,
            price=Decimal("5.00"),
        )
        self.client.force_login(self.staff)

        product_response = self.client.delete(
            reverse("products-api-detail", args=[self.product.pk])
        )
        category_response = self.client.delete(
            reverse("categories-detail", args=[self.category.pk])
        )

        self.assertEqual(product_response.status_code, 403)
        self.assertEqual(category_response.status_code, 403)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
        self.assertTrue(Category.objects.filter(pk=self.category.pk).exists())
        self.assertTrue(OrderItem.objects.filter(order=order).exists())

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
