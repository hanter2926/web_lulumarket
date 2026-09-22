from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from disputes.models import Dispute
from notifications.models import Notification
from notifications.services import record_audit

from .models import AccountTransfer, ComplianceCheck, Escrow, FeeConfiguration, Order, Payment, Refund, Settlement


def _compliance_status(*, buyer, seller):
    buyer_email_verified = buyer.is_email_verified
    seller_kyc_approved = getattr(getattr(seller, "kyc", None), "status", "") == "APPROVED"
    seller_verification_approved = getattr(getattr(seller, "seller_profile", None), "status", "") == "APPROVED"
    passed = buyer_email_verified and seller_kyc_approved and seller_verification_approved
    return passed, buyer_email_verified, seller_kyc_approved, seller_verification_approved


def _fee_for(amount):
    amount = Decimal(str(amount))
    fee = FeeConfiguration.objects.filter(is_active=True).order_by("-updated_at").first()
    if not fee:
        return Decimal("0.00")
    return (amount * fee.percentage / Decimal("100") + fee.fixed_amount).quantize(Decimal("0.01"))


@transaction.atomic
def create_order(*, buyer, listing, provider=""):
    listing = listing.__class__.objects.select_for_update().select_related("seller").get(pk=listing.pk)
    if listing.seller_id == buyer.id:
        raise ValueError("A seller cannot buy their own listing.")
    if not listing.is_verified:
        raise ValueError("Only verified listings can be ordered.")
    if listing.status.lower() in {"sold", "inactive", "cancelled"}:
        raise ValueError("This listing is no longer available.")

    existing_order = Order.objects.filter(
        listing=listing,
        status__in=(Order.Status.PENDING_PAYMENT, Order.Status.PAID, Order.Status.IN_ESCROW, Order.Status.COMPLETED, Order.Status.DISPUTED),
    ).first()
    if existing_order:
        if existing_order.buyer_id != buyer.id:
            raise ValueError("This listing already has a purchase in progress.")
        return existing_order

    compliance_passed, email_verified, kyc_approved, seller_approved = _compliance_status(
        buyer=buyer,
        seller=listing.seller,
    )
    if getattr(settings, "PAYMENT_COMPLIANCE_REQUIRED", False) and not compliance_passed:
        raise ValueError("Payment requires verified email, approved KYC, and approved seller verification.")

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
    AccountTransfer.objects.create(order=order)
    ComplianceCheck.objects.create(
        order=order,
        status=ComplianceCheck.Status.PASSED if compliance_passed else ComplianceCheck.Status.BLOCKED,
        buyer_email_verified=email_verified,
        seller_kyc_approved=kyc_approved,
        seller_verification_approved=seller_approved,
        reason="" if compliance_passed else "One or more verification checks are incomplete.",
    )
    order_amount = Decimal(str(order.amount))
    platform_fee = _fee_for(order_amount)
    Settlement.objects.create(
        order=order,
        seller=order.seller,
        gross_amount=order_amount,
        platform_fee=platform_fee,
        net_amount=order_amount - platform_fee,
    )
    record_audit(actor=buyer, action="ORDER_CREATED", obj=order, metadata={"listing_id": listing.id, "amount": str(order.amount)})
    return order


@transaction.atomic
def record_payment_success(*, order, provider_payment_id, payload=None, provider_order_id=None, amount=None, currency=None):
    original_order = order
    order = Order.objects.select_for_update().select_related("listing").get(pk=order.pk)
    payment = Payment.objects.select_for_update().get(order=order)
    if payment.status == Payment.Status.CAPTURED:
        if provider_payment_id and payment.provider_payment_id != provider_payment_id:
            raise ValueError("This order is already captured with a different payment.")
        original_order.status = order.status
        original_order.payment_status = order.payment_status
        return order
    if payment.status != Payment.Status.CREATED:
        raise ValueError("Only created payments can be captured.")
    if not provider_payment_id:
        raise ValueError("A verified provider payment is required.")
    if provider_order_id and payment.provider_order_id != provider_order_id:
        raise ValueError("The provider order does not match this order.")
    if amount is not None and Decimal(str(amount)) != payment.amount:
        raise ValueError("The provider amount does not match the order amount.")
    if currency and currency != order.currency:
        raise ValueError("The provider currency does not match the order currency.")
    if Payment.objects.filter(provider_payment_id=provider_payment_id).exclude(order=order).exists():
        raise ValueError("This provider payment is already linked to another order.")

    payment.status = Payment.Status.CAPTURED
    payment.provider_payment_id = provider_payment_id
    payment.provider_payload = payload or {}
    payment.save(update_fields=("status", "provider_payment_id", "provider_payload", "updated_at"))
    order.mark_paid()
    listing = order.listing.__class__.objects.select_for_update().get(pk=order.listing_id)
    if listing.status.lower() in {"sold", "inactive", "cancelled"}:
        raise ValueError("This listing is no longer available.")
    listing.status = "sold"
    listing.save(update_fields=("status",))
    order.settlement.status = Settlement.Status.HELD
    order.settlement.save(update_fields=("status",))
    Notification.objects.create(
        recipient=order.seller,
        title="Payment confirmed",
        body=f"Payment for {order.listing.title} is confirmed. Transfer the account securely.",
        link=f"/payments/orders/{order.id}/",
    )
    record_audit(actor=order.buyer, action="PAYMENT_VERIFIED", obj=order, metadata={"payment_id": provider_payment_id})
    original_order.status = order.status
    original_order.payment_status = order.payment_status
    return order


@transaction.atomic
def record_payment_failure(*, order, reason="Payment failed"):
    order = Order.objects.select_for_update().get(pk=order.pk)
    payment = Payment.objects.select_for_update().get(order=order)
    if payment.status == Payment.Status.CAPTURED:
        raise ValueError("A captured payment cannot be marked as failed.")
    payment.status = Payment.Status.FAILED
    payment.provider_payload = {"reason": reason}
    payment.save(update_fields=("status", "provider_payload", "updated_at"))
    order.status = Order.Status.CANCELLED
    order.payment_status = "FAILED"
    order.save(update_fields=("status", "payment_status", "updated_at"))
    return order


@transaction.atomic
def start_transfer(*, order, seller):
    order = Order.objects.select_for_update().get(pk=order.pk, seller=seller)
    if order.status != Order.Status.IN_ESCROW:
        raise ValueError("Payment must be confirmed before handoff.")
    transfer = AccountTransfer.objects.select_for_update().get(order=order)
    if transfer.status != AccountTransfer.Status.AWAITING_SELLER:
        raise ValueError("Handoff has already started.")
    transfer.status = AccountTransfer.Status.STARTED
    transfer.handoff_started_at = timezone.now()
    transfer.save(update_fields=("status", "handoff_started_at"))
    Notification.objects.create(
        recipient=order.buyer,
        title="Seller started handoff",
        body=f"The seller has started the secure handoff for order {order.order_id}.",
        link=f"/payments/orders/{order.id}/",
    )
    record_audit(actor=seller, action="HANDOFF_STARTED", obj=order)
    return transfer


@transaction.atomic
def mark_transfer_sent(*, order, seller, note=""):
    order = Order.objects.select_for_update().get(pk=order.pk, seller=seller)
    if order.status != Order.Status.IN_ESCROW:
        raise ValueError("Payment must be confirmed before transfer.")
    transfer = AccountTransfer.objects.select_for_update().get(order=order)
    if transfer.status not in (AccountTransfer.Status.AWAITING_SELLER, AccountTransfer.Status.STARTED):
        raise ValueError("This transfer has already been submitted.")
    transfer.status = AccountTransfer.Status.TRANSFERRED
    transfer.seller_transferred_at = timezone.now()
    transfer.transfer_note = note
    transfer.save(update_fields=("status", "seller_transferred_at", "transfer_note"))
    Notification.objects.create(
        recipient=order.buyer,
        title="Account transfer submitted",
        body=f"The seller has submitted the account for order {order.order_id}. Confirm receipt when ready.",
        link=f"/payments/orders/{order.id}/",
    )
    record_audit(actor=seller, action="HANDOFF_SENT", obj=order)
    return transfer


@transaction.atomic
def confirm_transfer(*, order, buyer):
    order = Order.objects.select_for_update().get(pk=order.pk, buyer=buyer)
    transfer = AccountTransfer.objects.select_for_update().get(order=order)
    if transfer.status != AccountTransfer.Status.TRANSFERRED:
        raise ValueError("The seller has not submitted the transfer yet.")
    transfer.status = AccountTransfer.Status.RECEIVED
    transfer.buyer_confirmed_at = timezone.now()
    transfer.save(update_fields=("status", "buyer_confirmed_at"))
    order.status = Order.Status.COMPLETED
    order.save(update_fields=("status", "updated_at"))
    order.escrow.status = Escrow.Status.RELEASED
    order.escrow.released_at = timezone.now()
    order.escrow.save(update_fields=("status", "released_at"))
    mark_settlement_eligible(order=order)
    Notification.objects.create(
        recipient=order.seller,
        title="Buyer confirmed receipt",
        body=f"Order {order.order_id} is complete. Your payout is eligible and remains pending provider transfer.",
        link=f"/payments/orders/{order.id}/",
    )
    record_audit(actor=buyer, action="HANDOFF_CONFIRMED", obj=order)
    return order


@transaction.atomic
def mark_settlement_eligible(*, order):
    if order.status != Order.Status.COMPLETED or order.escrow.status != Escrow.Status.RELEASED:
        raise ValueError("Settlement requires a completed order and released escrow.")
    settlement = Settlement.objects.select_for_update().get(order=order)
    settlement.status = Settlement.Status.ELIGIBLE
    settlement.save(update_fields=("status",))
    return settlement


@transaction.atomic
def complete_settlement(*, settlement, provider_transfer_id):
    settlement = Settlement.objects.select_for_update().get(pk=settlement.pk)
    if settlement.status != Settlement.Status.ELIGIBLE:
        raise ValueError("Only eligible settlements can be paid.")
    settlement.status = Settlement.Status.PAID
    settlement.provider_transfer_id = provider_transfer_id
    settlement.paid_at = timezone.now()
    settlement.save(update_fields=("status", "provider_transfer_id", "paid_at"))
    return settlement


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
def open_dispute(*, order, opened_by, reason, description="", evidence=None):
    if opened_by.id not in (order.buyer_id, order.seller_id):
        raise ValueError("Only the buyer or seller can open a dispute.")
    if order.status not in (Order.Status.PENDING_PAYMENT, Order.Status.IN_ESCROW, Order.Status.PAID):
        raise ValueError("This order cannot be disputed in its current state.")

    dispute, _ = Dispute.objects.get_or_create(
        order=order,
        defaults={"opened_by": opened_by, "reason": reason, "description": description, "evidence": evidence},
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
