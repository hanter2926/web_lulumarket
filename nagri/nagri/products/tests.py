from datetime import timedelta
from decimal import Decimal
import json

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from orders.models import Order, OrderItem
from .forms import serialize_product_variants
from .inventory import adjust_available_stock, release_stock_reservation, reserve_stock
from .models import (
    Category,
    MeasurementRequirement,
    Product,
    ProductAttributeDefinition,
    ProductAttributeValue,
    ProductMeasurement,
    ProductVariant,
    StockMovement,
    SubCategory,
    VariantAttributeDefinition,
    VariantMeasurement,
)


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


class ProductManagementModelTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Management Test Category",
            slug="management-test-category",
        )
        self.product = Product.objects.create(
            name="Management Test Product",
            slug="management-test-product",
            category=self.category,
            price=Decimal("100.00"),
            compare_price=Decimal("120.00"),
        )

    def test_scheduled_product_and_variant_prices_are_calculated(self):
        now = timezone.now()
        self.product.scheduled_sale_price = Decimal("80.00")
        self.product.scheduled_sale_start = now - timedelta(minutes=1)
        self.product.scheduled_sale_end = now + timedelta(minutes=1)
        self.assertEqual(self.product.get_current_price(now), Decimal("80.00"))
        self.assertEqual(self.product.get_regular_price(now), Decimal("120.00"))
        self.assertEqual(self.product.get_discount_amount(now), Decimal("40.00"))

        variant = ProductVariant.objects.create(
            product=self.product,
            attributes={"size": "M"},
            price=Decimal("90.00"),
            compare_price=Decimal("110.00"),
            scheduled_sale_price=Decimal("70.00"),
            scheduled_sale_start=now - timedelta(minutes=1),
            scheduled_sale_end=now + timedelta(minutes=1),
        )
        self.assertEqual(variant.get_current_price(now), Decimal("70.00"))
        self.assertEqual(variant.get_regular_price(now), Decimal("110.00"))

    def test_measurement_conversion_and_positive_validation(self):
        self.assertEqual(
            ProductMeasurement.convert_dimension_to_mm(Decimal("2"), "inch"),
            Decimal("50.800"),
        )
        self.assertEqual(
            ProductMeasurement.convert_weight_to_grams(Decimal("1.25"), "kg"),
            Decimal("1250.000"),
        )
        with self.assertRaises(ValidationError):
            ProductMeasurement(
                product=self.product,
                length_mm=Decimal("0"),
            ).full_clean()

    def test_required_measurement_and_typed_attribute_validation(self):
        MeasurementRequirement.objects.create(
            category=self.category,
            field_name="length_mm",
            is_required=True,
        )
        with self.assertRaises(ValidationError):
            ProductMeasurement(product=self.product).full_clean()

        definition = ProductAttributeDefinition.objects.create(
            category=self.category,
            key="material",
            label="Material",
            data_type="dropdown",
            is_required=True,
            options=["Cotton", "Wool"],
        )
        value = ProductAttributeValue(
            product=self.product,
            definition=definition,
            value="Wool",
        )
        value.full_clean()
        value.value = "Nylon"
        with self.assertRaises(ValidationError):
            value.full_clean()

    def test_variant_attribute_requirements_and_duplicate_combinations(self):
        VariantAttributeDefinition.objects.create(
            category=self.category,
            key="size",
            label="Size",
            options=["S", "M"],
        )
        with self.assertRaises(ValidationError):
            ProductVariant(product=self.product, attributes={}).full_clean()

        ProductVariant.objects.create(
            product=self.product,
            attributes={"size": "M"},
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProductVariant.objects.create(
                product=self.product,
                attributes={"size": "M"},
            )

    def test_variant_stock_adjustment_and_reservation_history(self):
        variant = ProductVariant.objects.create(
            product=self.product,
            attributes={"size": "L"},
        )
        inventory = variant.inventory
        adjust_available_stock(inventory, 8)
        inventory.refresh_from_db()
        reserve_stock(inventory, 3, order_id=42)
        inventory.refresh_from_db()
        self.assertEqual(inventory.stock_quantity, 5)
        self.assertEqual(inventory.reserved_quantity, 3)

        release_stock_reservation(inventory, 3, order_id=42)
        inventory.refresh_from_db()
        self.assertEqual(inventory.stock_quantity, 8)
        self.assertEqual(inventory.reserved_quantity, 0)
        self.assertEqual(
            StockMovement.objects.filter(variant_inventory=inventory).count(),
            3,
        )
        with self.assertRaises(ValidationError):
            adjust_available_stock(inventory, -1)

    def test_seller_variant_serialization_includes_disabled_state_and_measurements(self):
        variant = ProductVariant.objects.create(
            product=self.product,
            attributes={"size": "XL"},
            is_active=False,
        )
        VariantMeasurement.objects.create(
            variant=variant,
            dimension_unit="cm",
            length_mm=Decimal("100"),
            product_weight_g=Decimal("1500"),
        )

        payload = json.loads(serialize_product_variants(self.product))

        self.assertEqual(len(payload), 1)
        self.assertFalse(payload[0]["enabled"])
        self.assertEqual(payload[0]["measurement"]["length"], "10.000")
        self.assertEqual(payload[0]["measurement"]["product_weight"], "1500.000")

    def test_product_admin_add_form_renders_management_fieldsets(self):
        admin_user = get_user_model().objects.create_superuser(
            username="product-management-admin",
            email="product-management-admin@example.com",
            password="test-password",
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("admin:products_product_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Size &amp; Weight")
        self.assertContains(response, "Product Variants")
        self.assertContains(response, "Inventory Management")
