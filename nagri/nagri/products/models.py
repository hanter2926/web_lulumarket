from django.conf import settings
from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class SubCategory(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="subcategories")
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("category", "slug")

    def __str__(self):
        return f"{self.category.name} / {self.name}"


class Product(models.Model):
    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="seller_products")
    name = models.CharField(max_length=200, db_index=True)
    slug = models.SlugField(unique=True, db_index=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="products", db_index=True)
    subcategory = models.ForeignKey(SubCategory, on_delete=models.SET_NULL, related_name="products", null=True, blank=True, db_index=True)
    short_description = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    brand = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    tags = models.CharField(max_length=255, blank=True, null=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, db_index=True)
    compare_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00, db_index=True)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    is_bestseller = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "is_featured", "is_bestseller", "created_at"]),
            models.Index(fields=["category", "is_active", "created_at"]),
            models.Index(fields=["price", "is_active"]),
        ]

    @property
    def in_stock(self):
        return self.inventory.stock_quantity > 0 if hasattr(self, "inventory") else False

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    alt_text = models.CharField(max_length=255, blank=True, null=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "-created_at"]

    def clean(self):
        from django.core.exceptions import ValidationError

        # Enforce maximum 12 images per product.
        # If the parent Product hasn't been saved yet (no PK), skip DB relationship checks
        # because accessing product.images will raise ValueError when product.pk is None.
        if not self.product or not getattr(self.product, 'pk', None):
            return

        if self.product.images.exclude(pk=self.pk).count() >= 12:
            raise ValidationError("A product cannot have more than 12 images.")

    def __str__(self):
        return f"Image for {self.product.name} ({self.pk})"


class Inventory(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="inventory")
    stock_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    last_updated = models.DateTimeField(auto_now=True)

 

    stock_quantity = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.product.name} inventory"
