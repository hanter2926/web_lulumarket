from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import (
    Inventory,
    Product,
    ProductPriceHistory,
    ProductVariant,
    VariantInventory,
)


@receiver(pre_save, sender=Product)
def capture_product_prices(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_prices = None
        return
    instance._old_prices = sender.objects.filter(pk=instance.pk).values(
        "price", "compare_price", "scheduled_sale_price",
        "scheduled_sale_start", "scheduled_sale_end",
    ).first()


@receiver(post_save, sender=Product)
def record_product_price_change(sender, instance, created, **kwargs):
    old_prices = getattr(instance, "_old_prices", None)
    if not created and old_prices and (
        old_prices["price"] != instance.price
        or old_prices["compare_price"] != instance.compare_price
        or old_prices["scheduled_sale_price"] != instance.scheduled_sale_price
        or old_prices["scheduled_sale_start"] != instance.scheduled_sale_start
        or old_prices["scheduled_sale_end"] != instance.scheduled_sale_end
    ):
        ProductPriceHistory.objects.create(
            product=instance,
            old_price=old_prices["price"],
            new_price=instance.price,
            old_regular_price=old_prices["compare_price"],
            new_regular_price=instance.compare_price,
            old_scheduled_sale_price=old_prices["scheduled_sale_price"],
            new_scheduled_sale_price=instance.scheduled_sale_price,
            old_scheduled_sale_start=old_prices["scheduled_sale_start"],
            new_scheduled_sale_start=instance.scheduled_sale_start,
            old_scheduled_sale_end=old_prices["scheduled_sale_end"],
            new_scheduled_sale_end=instance.scheduled_sale_end,
            actor=getattr(instance, "_price_history_actor", None),
        )


@receiver(post_save, sender=Product)
def create_inventory_for_product(sender, instance, created, **kwargs):
    """Create a related Inventory object whenever a new Product is created.

    Uses get_or_create to avoid creating duplicate Inventory records.
    """
    if created:
        Inventory.objects.get_or_create(product=instance, defaults={"stock_quantity": 0})


@receiver(pre_save, sender=ProductVariant)
def capture_variant_prices(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_prices = None
        return
    instance._old_prices = sender.objects.filter(pk=instance.pk).values(
        "price", "compare_price", "scheduled_sale_price",
        "scheduled_sale_start", "scheduled_sale_end",
    ).first()


@receiver(post_save, sender=ProductVariant)
def create_variant_inventory_and_record_prices(sender, instance, created, **kwargs):
    if created:
        VariantInventory.objects.get_or_create(variant=instance)
        return
    old_prices = getattr(instance, "_old_prices", None)
    if old_prices and (
        old_prices["price"] != instance.price
        or old_prices["compare_price"] != instance.compare_price
        or old_prices["scheduled_sale_price"] != instance.scheduled_sale_price
        or old_prices["scheduled_sale_start"] != instance.scheduled_sale_start
        or old_prices["scheduled_sale_end"] != instance.scheduled_sale_end
    ):
        ProductPriceHistory.objects.create(
            product=instance.product,
            variant=instance,
            old_price=old_prices["price"],
            new_price=instance.price or instance.product.price,
            old_regular_price=old_prices["compare_price"],
            new_regular_price=instance.compare_price,
            old_scheduled_sale_price=old_prices["scheduled_sale_price"],
            new_scheduled_sale_price=instance.scheduled_sale_price,
            old_scheduled_sale_start=old_prices["scheduled_sale_start"],
            new_scheduled_sale_start=instance.scheduled_sale_start,
            old_scheduled_sale_end=old_prices["scheduled_sale_end"],
            new_scheduled_sale_end=instance.scheduled_sale_end,
            actor=getattr(instance, "_price_history_actor", None),
        )
