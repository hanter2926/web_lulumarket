from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Product, Inventory


@receiver(post_save, sender=Product)
def create_inventory_for_product(sender, instance, created, **kwargs):
    """Create a related Inventory object whenever a new Product is created.

    Uses get_or_create to avoid creating duplicate Inventory records.
    """
    if created:
        Inventory.objects.get_or_create(product=instance, defaults={"stock_quantity": 0})
