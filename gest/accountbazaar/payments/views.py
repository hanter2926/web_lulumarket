import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from marketplace.models import Listing

from .models import Order, Payment
from .providers import create_razorpay_order, verify_webhook_signature, webhook_payment_details
from .services import create_order, open_dispute, record_payment_success, request_refund


def _json_body(request):
	try:
		return json.loads(request.body or "{}")
	except json.JSONDecodeError:
		return {}


@login_required
@require_POST
def create_order_view(request, listing_id):
	listing = get_object_or_404(Listing, pk=listing_id)
	try:
		order = create_order(
			buyer=request.user,
			listing=listing,
			provider=request.headers.get("X-Payment-Provider", "configured-provider"),
		)
	except ValueError as error:
		return JsonResponse({"error": str(error)}, status=400)
	try:
		provider_order = create_razorpay_order(payment=order.payment)
	except RuntimeError as error:
		order.status = Order.Status.CANCELLED
		order.save(update_fields=("status", "updated_at"))
		return JsonResponse({"error": str(error)}, status=503)
	return JsonResponse({
		"order_id": order.id,
		"status": order.status,
		"provider": "razorpay",
		"provider_order_id": provider_order["id"],
		"key_id": settings.RAZORPAY_KEY_ID,
		"amount": provider_order["amount"],
		"currency": provider_order["currency"],
	}, status=201)


@login_required
@require_POST
def payment_success(request, order_id):
	order = get_object_or_404(Order, pk=order_id, buyer=request.user)
	data = _json_body(request)
	provider_payment_id = data.get("provider_payment_id")
	if not provider_payment_id:
		return JsonResponse({"error": "provider_payment_id is required"}, status=400)
	try:
		order = record_payment_success(
			order=order,
			provider_payment_id=provider_payment_id,
			payload=data,
		)
	except ValueError as error:
		return JsonResponse({"error": str(error)}, status=400)
	return JsonResponse({"order_id": order.id, "status": order.status})


@login_required
@require_POST
def refund_request(request, order_id):
	order = get_object_or_404(Order, pk=order_id, buyer=request.user)
	reason = _json_body(request).get("reason", "Buyer requested a refund.")
	try:
		refund = request_refund(order=order, reason=reason)
	except ValueError as error:
		return JsonResponse({"error": str(error)}, status=400)
	return JsonResponse({"refund_id": refund.id, "status": refund.status}, status=201)


@login_required
@require_POST
def dispute_request(request, order_id):
	order = get_object_or_404(Order, pk=order_id)
	reason = _json_body(request).get("reason", "Transaction issue reported.")
	try:
		dispute = open_dispute(order=order, opened_by=request.user, reason=reason)
	except ValueError as error:
		return JsonResponse({"error": str(error)}, status=400)
	return JsonResponse({"dispute_id": dispute.id, "status": dispute.status}, status=201)


@csrf_exempt
@require_POST
def razorpay_webhook(request):
	signature = request.headers.get("X-Razorpay-Signature", "")
	if not signature or not settings.RAZORPAY_WEBHOOK_SECRET or not verify_webhook_signature(
		body=request.body,
		signature=signature,
	):
		return JsonResponse({"error": "Invalid webhook signature"}, status=400)

	details = webhook_payment_details(request.body)
	if details:
		provider_order_id, provider_payment_id, payload = details
		payment = get_object_or_404(Payment, provider_order_id=provider_order_id)
		record_payment_success(
			order=payment.order,
			provider_payment_id=provider_payment_id,
			payload=payload,
		)
	return HttpResponse(status=200)
