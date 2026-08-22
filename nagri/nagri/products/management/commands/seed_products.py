from decimal import Decimal

from django.core.management.base import BaseCommand

from products.models import Category, Inventory, Product, SubCategory


class Command(BaseCommand):
    help = "Create dummy product data for the ecommerce frontend and filters."

    def handle(self, *args, **options):
        category_data = [
            ("Men", [
                ("Shirts", "men-shirts"),
                ("Jeans", "men-jeans"),
            ]),
            ("Women", [
                ("Kurtas", "women-kurtas"),
                ("Dresses", "women-dresses"),
            ]),
            ("Home", [
                ("Decor", "home-decor"),
                ("Kitchen", "home-kitchen"),
            ]),
        ]

        products = [
            {
                "name": "Classic Cotton Shirt",
                "slug": "classic-cotton-shirt",
                "category": "Men",
                "subcategory": "Shirts",
                "short_description": "Lightweight cotton shirt for everyday wear.",
                "description": "Premium cotton shirt with a comfortable fit and casual style.",
                "brand": "Nagri",
                "tags": "shirt, cotton, menswear",
                "price": Decimal("899.00"),
                "compare_price": Decimal("1299.00"),
                "rating": Decimal("4.50"),
                "is_featured": True,
                "is_bestseller": True,
                "stock": 45,
            },
            {
                "name": "Slim Fit Denim",
                "slug": "slim-fit-denim",
                "category": "Men",
                "subcategory": "Jeans",
                "short_description": "Modern lean-fit jeans for daily looks.",
                "description": "Made from stretch denim with a clean finish and easy movement.",
                "brand": "Nagri",
                "tags": "jeans, denim, menswear",
                "price": Decimal("1499.00"),
                "compare_price": Decimal("1999.00"),
                "rating": Decimal("4.30"),
                "is_featured": True,
                "is_bestseller": False,
                "stock": 32,
            },
            {
                "name": "Printed Cotton Kurta",
                "slug": "printed-cotton-kurta",
                "category": "Women",
                "subcategory": "Kurtas",
                "short_description": "Elegant printed kurta for festive and casual wear.",
                "description": "Soft-touch cotton kurta with breathable fabric and graceful design.",
                "brand": "Nagri",
                "tags": "kurta, women, cotton",
                "price": Decimal("1299.00"),
                "compare_price": Decimal("1699.00"),
                "rating": Decimal("4.70"),
                "is_featured": True,
                "is_bestseller": True,
                "stock": 28,
            },
            {
                "name": "Floral Summer Dress",
                "slug": "floral-summer-dress",
                "category": "Women",
                "subcategory": "Dresses",
                "short_description": "Comfortable floral dress with a chic silhouette.",
                "description": "A lightweight summer dress designed for comfort and style.",
                "brand": "Nagri",
                "tags": "dress, summer, women",
                "price": Decimal("1799.00"),
                "compare_price": Decimal("2299.00"),
                "rating": Decimal("4.40"),
                "is_featured": False,
                "is_bestseller": True,
                "stock": 19,
            },
            {
                "name": "Decorative Wall Art",
                "slug": "decorative-wall-art",
                "category": "Home",
                "subcategory": "Decor",
                "short_description": "Modern wall artwork to elevate living spaces.",
                "description": "A balanced home decor piece for stylized walls and cozy interiors.",
                "brand": "Nagri",
                "tags": "decor, home, wallart",
                "price": Decimal("2499.00"),
                "compare_price": Decimal("2999.00"),
                "rating": Decimal("4.20"),
                "is_featured": False,
                "is_bestseller": False,
                "stock": 14,
            },
            {
                "name": "Premium Kitchen Set",
                "slug": "premium-kitchen-set",
                "category": "Home",
                "subcategory": "Kitchen",
                "short_description": "Elegant kitchen essentials for daily cooking.",
                "description": "A versatile kitchen set combining utility and premium style.",
                "brand": "Nagri",
                "tags": "kitchen, home, essentials",
                "price": Decimal("2999.00"),
                "compare_price": Decimal("3999.00"),
                "rating": Decimal("4.60"),
                "is_featured": True,
                "is_bestseller": False,
                "stock": 11,
            },
        ]

        created_count = 0
        for category_name, subcategory_list in category_data:
            category, _ = Category.objects.get_or_create(
                name=category_name,
                defaults={"slug": category_name.lower().replace(" ", "-")},
            )
            for sub_name, sub_slug in subcategory_list:
                SubCategory.objects.get_or_create(
                    category=category,
                    name=sub_name,
                    defaults={"slug": sub_slug},
                )

        for item in products:
            category = Category.objects.get(name=item["category"])
            subcategory = SubCategory.objects.get(category=category, name=item["subcategory"])

            product, created = Product.objects.get_or_create(
                slug=item["slug"],
                defaults={
                    "name": item["name"],
                    "category": category,
                    "subcategory": subcategory,
                    "short_description": item["short_description"],
                    "description": item["description"],
                    "brand": item["brand"],
                    "tags": item["tags"],
                    "price": item["price"],
                    "compare_price": item["compare_price"],
                    "rating": item["rating"],
                    "is_featured": item["is_featured"],
                    "is_bestseller": item["is_bestseller"],
                    "is_active": True,
                },
            )

            if created:
                Inventory.objects.update_or_create(
                    product=product,
                    defaults={"stock_quantity": item["stock"], "low_stock_threshold": 5},
                )
                created_count += 1

        self.stdout.write(self.style.SUCCESS(f"Created {created_count} sample products."))
