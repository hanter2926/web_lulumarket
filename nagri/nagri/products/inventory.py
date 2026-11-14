from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Inventory, StockMovement, VariantInventory


@transaction.atomic
def apply_stock_delta(
    stock_record,
    *,
    available_delta=0,
    reserved_delta=0,
    sold_delta=0,
    reason,
    actor=None,
    order_id=None,
    note="",
):
    if not isinstance(stock_record, (Inventory, VariantInventory)) or not stock_record.pk:
        raise ValidationError("A saved product or variant inventory record is required.")

    record = type(stock_record).objects.select_for_update().get(pk=stock_record.pk)
    next_available = record.stock_quantity + available_delta
    next_reserved = record.reserved_quantity + reserved_delta
    next_sold = record.sold_quantity + sold_delta
    if min(next_available, next_reserved, next_sold) < 0:
        raise ValidationError("The stock adjustment would make an inventory balance negative.")

    record.stock_quantity = next_available
    record.reserved_quantity = next_reserved
    record.sold_quantity = next_sold
    record.save(update_fields=[
        "stock_quantity",
        "reserved_quantity",
        "sold_quantity",
        "last_updated",
    ])
    movement_fields = {
        "available_delta": available_delta,
        "reserved_delta": reserved_delta,
        "sold_delta": sold_delta,
        "reason": reason,
        "actor": actor,
        "order_id": order_id,
        "note": note,
    }
    if isinstance(record, Inventory):
        movement_fields["inventory"] = record
    else:
        movement_fields["variant_inventory"] = record
    StockMovement.objects.create(**movement_fields)
    return record


@transaction.atomic
def adjust_available_stock(stock_record, new_quantity, *, actor=None, reason="admin_adjustment", note=""):
    if isinstance(new_quantity, bool) or not isinstance(new_quantity, int) or new_quantity < 0:
        raise ValidationError("Available stock must be a non-negative whole number.")
    if not isinstance(stock_record, (Inventory, VariantInventory)) or not stock_record.pk:
        raise ValidationError("A saved product or variant inventory record is required.")
    locked_record = type(stock_record).objects.select_for_update().get(pk=stock_record.pk)
    delta = new_quantity - locked_record.stock_quantity
    if not delta:
        return stock_record
    return apply_stock_delta(
        locked_record,
        available_delta=delta,
        reason=reason,
        actor=actor,
        note=note,
    )


def reserve_stock(stock_record, quantity, *, order_id):
    if quantity <= 0:
        raise ValidationError("Reservation quantity must be greater than zero.")
    if stock_record.stock_quantity < quantity:
        raise ValidationError("Insufficient available stock.")
    return apply_stock_delta(
        stock_record,
        available_delta=-quantity,
        reserved_delta=quantity,
        reason="order_reserved",
        order_id=order_id,
    )


def complete_stock_reservation(stock_record, quantity, *, order_id):
    if quantity <= 0:
        raise ValidationError("Completed quantity must be greater than zero.")
    return apply_stock_delta(
        stock_record,
        reserved_delta=-quantity,
        sold_delta=quantity,
        reason="order_paid",
        order_id=order_id,
    )


def release_stock_reservation(stock_record, quantity, *, order_id, reason="order_cancelled"):
    if quantity <= 0:
        raise ValidationError("Released quantity must be greater than zero.")
    return apply_stock_delta(
        stock_record,
        available_delta=quantity,
        reserved_delta=-quantity,
        reason=reason,
        order_id=order_id,
    )


def stock_for_product(product, variant=None):
    if variant is not None:
        if variant.product_id != product.pk:
            raise ValidationError("The selected variant does not belong to this product.")
        return variant.inventory
    if product.variants.exists():
        raise ValidationError("A variant must be selected for this product.")
    return product.inventory
