from decimal import Decimal
import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from products.inventory import apply_stock_delta
from products.models import Inventory, VariantInventory

from .models import Order, OrderItem, OrderRefund

logger = logging.getLogger(__name__)


def effective_line_price(product, variant=None, at=None):
    return variant.get_current_price(at) if variant else product.get_current_price(at)


def regular_line_price(product, variant=None, at=None):
    return variant.get_regular_price(at) if variant else product.get_regular_price(at)


def effective_tax_rate(product, variant=None):
    return (
        variant.tax_rate
        if variant and variant.tax_rate is not None
        else product.effective_tax_rate
    )


def create_order_item(order, product, quantity, variant=None):
    unit_price = effective_line_price(product, variant)
    regular_price = regular_line_price(product, variant)
    tax_rate = effective_tax_rate(product, variant)
    attributes = variant.attributes if variant else {}
    sku = variant.sku if variant else product.sku
    return OrderItem.objects.create(
        order=order,
        product=product,
        variant=variant,
        quantity=quantity,
        price=unit_price,
        regular_price=regular_price,
        sku_snapshot=sku or "",
        variant_attributes_snapshot=attributes,
        tax_rate_snapshot=tax_rate,
        tax_amount_snapshot=Decimal("0.00"),
    )


def _lock_stock_records(order_items):
    simple_product_ids = sorted({
        item.product_id for item in order_items if item.variant_id is None
    })
    variant_ids = sorted({
        item.variant_id for item in order_items if item.variant_id is not None
    })
    simple_records = {
        record.product_id: record
        for record in Inventory.objects.select_for_update()
        .filter(product_id__in=simple_product_ids)
        .order_by("product_id")
    }
    variant_records = {
        record.variant_id: record
        for record in VariantInventory.objects.select_for_update()
        .filter(variant_id__in=variant_ids)
        .order_by("variant_id")
    }
    records = {}
    for item in order_items:
        key = ("variant", item.variant_id) if item.variant_id else ("product", item.product_id)
        records[key] = variant_records.get(item.variant_id) if item.variant_id else simple_records.get(item.product_id)
    return records


def _get_locked_record(records, item):
    key = _stock_record_key(item)
    record = records.get(key)
    if record is None:
        raise ValidationError(f"Inventory is not configured for {item.product.name}.")
    return record


def _stock_record_key(item):
    return ("variant", item.variant_id) if item.variant_id else ("product", item.product_id)


def _reserved_delta(record, item):
    if record.reserved_quantity < item.quantity:
        logger.warning(
            "Order %s has legacy reservation counters for product %s: %s of %s units are recorded.",
            item.order_id,
            item.product_id,
            record.reserved_quantity,
            item.quantity,
        )
    return -min(record.reserved_quantity, item.quantity)


@transaction.atomic
def reserve_order_stock(order, *, actor=None):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.inventory_reserved:
        return
    items = list(
        order.items.select_related("product", "variant")
        .order_by("product_id", "variant_id", "id")
    )
    records = _lock_stock_records(items)
    requested = {}
    for item in items:
        _get_locked_record(records, item)
        key = _stock_record_key(item)
        requested[key] = requested.get(key, 0) + item.quantity
    for key, quantity in requested.items():
        record = records[key]
        if record.stock_quantity < quantity:
            item = next(item for item in items if _stock_record_key(item) == key)
            raise ValidationError(f"Insufficient stock for {item.product.name}.")
    for item in items:
        key = _stock_record_key(item)
        records[key] = apply_stock_delta(
            _get_locked_record(records, item),
            available_delta=-item.quantity,
            reserved_delta=item.quantity,
            reason="order_reserved",
            actor=actor,
            order_id=order.pk,
        )
    order.inventory_reserved = True
    order.save(update_fields=["inventory_reserved", "updated_at"])


@transaction.atomic
def complete_order_stock(order, *, actor=None):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not order.inventory_reserved:
        return
    items = list(
        order.items.select_related("product", "variant")
        .order_by("product_id", "variant_id", "id")
    )
    records = _lock_stock_records(items)
    for item in items:
        record = _get_locked_record(records, item)
        key = _stock_record_key(item)
        records[key] = apply_stock_delta(
            record,
            reserved_delta=_reserved_delta(record, item),
            sold_delta=item.quantity,
            reason="order_paid",
            actor=actor,
            order_id=order.pk,
        )
    order.inventory_reserved = False
    order.save(update_fields=["inventory_reserved", "updated_at"])


@transaction.atomic
def release_order_stock(order, *, reason="order_cancelled", actor=None):
    order = Order.objects.select_for_update().get(pk=order.pk)
    if not order.inventory_reserved:
        return
    items = list(
        order.items.select_related("product", "variant")
        .order_by("product_id", "variant_id", "id")
    )
    records = _lock_stock_records(items)
    for item in items:
        record = _get_locked_record(records, item)
        key = _stock_record_key(item)
        records[key] = apply_stock_delta(
            record,
            available_delta=item.quantity,
            reserved_delta=_reserved_delta(record, item),
            reason=reason,
            actor=actor,
            order_id=order.pk,
        )
    order.inventory_reserved = False
    order.save(update_fields=["inventory_reserved", "updated_at"])


@transaction.atomic
def complete_refund_and_restock(refund_id, *, actor=None, provider_refund_id=""):
    refund = OrderRefund.objects.select_for_update().select_related("order").get(pk=refund_id)
    if refund.status != "approved":
        raise ValidationError("Only an approved refund can be completed.")
    if refund.order.payment_method != "cod" and not provider_refund_id.strip():
        raise ValidationError("Record the payment provider refund ID before completing this refund.")
    if refund.stock_restocked_at:
        raise ValidationError("Stock has already been restored for this refund.")

    refund_items = list(
        refund.items.filter(restockable=True)
        .select_related("order_item__product", "order_item__variant")
        .order_by("order_item__product_id", "order_item__variant_id", "id")
    )
    records = _lock_stock_records([item.order_item for item in refund_items])
    for refund_item in refund_items:
        order_item = refund_item.order_item
        record = _get_locked_record(records, order_item)
        sold_delta = -refund_item.quantity if record.sold_quantity >= refund_item.quantity else 0
        key = _stock_record_key(order_item)
        records[key] = apply_stock_delta(
            record,
            available_delta=refund_item.quantity,
            sold_delta=sold_delta,
            reason="refund_restock",
            actor=actor,
            order_id=refund.order_id,
            note=f"Refund {refund.pk}",
        )

    refund.status = "completed"
    refund.provider_refund_id = provider_refund_id.strip()
    refund.reviewed_by = actor
    refund.reviewed_at = timezone.now()
    refund.stock_restocked_at = timezone.now()
    refund.save(update_fields=[
        "status", "provider_refund_id", "reviewed_by", "reviewed_at",
        "stock_restocked_at", "updated_at",
    ])
    return refund
