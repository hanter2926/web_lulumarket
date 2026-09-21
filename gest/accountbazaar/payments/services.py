from django.db import transaction
from django.utils import timezone

from disputes.models import Dispute

from .models import Escrow, Order, Payment, Refund


@transaction.atomic
def create_order(*, buyer, listing, provider=""):
    if listing.seller_id == buyer.id:
        raise ValueError("A seller cannot buy their own listing.")
    if not listing.is_verified:
        raise ValueError("Only verified listings can be ordered.")

    order = Order.objects.create(
        buyer=buyer,
        seller=listing.seller,
        listing=listing,
        amount=listing.price,
    )
    Payment.objects.create(
        order=order,
        provider=provider,
        amount=order.amount,
    )
    Escrow.objects.create(order=order)
    return order


@transaction.atomic
def record_payment_success(*, order, provider_payment_id, payload=None):
    payment = Payment.objects.select_for_update().get(order=order)
    if payment.status == Payment.Status.CAPTURED:
        return order
    if payment.status != Payment.Status.CREATED:
        raise ValueError("Only created payments can be captured.")

    payment.status = Payment.Status.CAPTURED
    payment.provider_payment_id = provider_payment_id
    payment.provider_payload = payload or {}
    payment.save(update_fields=("status", "provider_payment_id", "provider_payload", "updated_at"))
    order.mark_paid()
    return order


@transaction.atomic
def request_refund(*, order, reason):
    if order.status not in (Order.Status.IN_ESCROW, Order.Status.PAID):
        raise ValueError("This order cannot be refunded in its current state.")
    refund, _ = Refund.objects.get_or_create(
        order=order,
        defaults={"amount": order.amount, "reason": reason},
    )
    return refund


@transaction.atomic
def open_dispute(*, order, opened_by, reason):
    if opened_by.id not in (order.buyer_id, order.seller_id):
        raise ValueError("Only the buyer or seller can open a dispute.")
    if order.status not in (Order.Status.IN_ESCROW, Order.Status.PAID):
        raise ValueError("This order cannot be disputed in its current state.")

    dispute, _ = Dispute.objects.get_or_create(
        order=order,
        defaults={"opened_by": opened_by, "reason": reason},
    )
    order.status = Order.Status.DISPUTED
    order.save(update_fields=("status", "updated_at"))
    order.escrow.status = Escrow.Status.DISPUTED
    order.escrow.save(update_fields=("status",))
    return dispute


def complete_refund(*, refund, provider_refund_id):
    with transaction.atomic():
        refund = Refund.objects.select_for_update().select_related("order").get(pk=refund.pk)
        refund.status = Refund.Status.COMPLETED
        refund.provider_refund_id = provider_refund_id
        refund.save(update_fields=("status", "provider_refund_id"))
        refund.order.status = Order.Status.REFUNDED
        refund.order.save(update_fields=("status", "updated_at"))
        refund.order.escrow.status = Escrow.Status.REFUNDED
        refund.order.escrow.save(update_fields=("status",))
        refund.order.payment.status = Payment.Status.REFUNDED
        refund.order.payment.save(update_fields=("status", "updated_at"))
        return refund
