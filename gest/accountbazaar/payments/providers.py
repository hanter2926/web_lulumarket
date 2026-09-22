import hashlib
import hmac
import json
from decimal import Decimal

from django.conf import settings

from .models import Payment


def _razorpay_client():
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise RuntimeError("Razorpay credentials are not configured.")
    try:
        import razorpay
    except ImportError as error:
        raise RuntimeError("Install the razorpay package before using Razorpay payments.") from error
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_razorpay_order(*, payment):
    amount_paise = int(Decimal(str(payment.amount)) * 100)
    provider_order = _razorpay_client().order.create(
        {
            "amount": amount_paise,
            "currency": payment.order.currency,
            "receipt": f"accountbazaar-order-{payment.order_id}",
            "notes": {"order_id": str(payment.order_id)},
        }
    )
    payment.provider = "razorpay"
    payment.provider_order_id = provider_order["id"]
    payment.provider_payload = provider_order
    payment.save(update_fields=("provider", "provider_order_id", "provider_payload", "updated_at"))
    return provider_order


def verify_checkout_signature(*, order_id, payment_id, signature):
    message = f"{order_id}|{payment_id}".encode()
    expected = hmac.new(
        settings.RAZORPAY_KEY_SECRET.encode(),
        message,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(*, body, signature):
    expected = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def webhook_payment_details(body):
    payload = json.loads(body)
    event = payload.get("event")
    entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    if event != "payment.captured" or not entity.get("order_id") or not entity.get("id"):
        return None
    return entity["order_id"], entity["id"], payload
