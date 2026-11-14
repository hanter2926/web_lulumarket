from django.conf import settings
from django.db import models
from django.db.models import Q

from products.models import Product


class Cart(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="carts")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Cart for {self.user.email}"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="cart_items")
    variant = models.ForeignKey(
        "products.ProductVariant",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="cart_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("cart", "product"),
                condition=Q(variant__isnull=True),
                name="unique_simple_product_per_cart",
            ),
            models.UniqueConstraint(
                fields=("cart", "product", "variant"),
                condition=Q(variant__isnull=False),
                name="unique_variant_per_cart",
            ),
        ]

    def clean(self):
        super().clean()
        if self.variant_id and self.variant.product_id != self.product_id:
            from django.core.exceptions import ValidationError

            raise ValidationError({"variant": "The selected variant does not belong to this product."})

    @property
    def current_price(self):
        return self.variant.get_current_price() if self.variant_id else self.product.get_current_price()

    def __str__(self):
        item_name = f"{self.product.name} ({self.variant})" if self.variant_id else self.product.name
        return f"{item_name} x {self.quantity}"
