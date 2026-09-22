from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from disputes.models import Dispute

from .models import ComplianceCheck, Escrow, FeeConfiguration, Order, Payment, Refund, Settlement


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
    if listing.seller_id == buyer.id:
        raise ValueError("A seller cannot buy their own listing.")
    if not listing.is_verified:
        raise ValueError("Only verified listings can be ordered.")

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
    order.settlement.status = Settlement.Status.HELD
    order.settlement.save(update_fields=("status",))
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
