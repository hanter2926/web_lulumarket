import json
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from marketplace.models import Listing

from .models import Order, Payment
from .providers import create_razorpay_order, verify_checkout_signature, verify_webhook_signature, webhook_payment_details
from .services import confirm_transfer, create_order, create_review, mark_transfer_sent, open_dispute, record_payment_failure, record_payment_success, request_refund, start_transfer


def payment_page(request):
	return render(request, "payments/payment.html")


@login_required
@require_POST
def checkout_start(request, listing_id):
	listing = get_object_or_404(Listing, pk=listing_id)
	try:
		order = create_order(buyer=request.user, listing=listing, provider="demo")
	except ValueError as error:
		return HttpResponse(str(error), status=400)
	return redirect("payments:order-summary", order_id=order.id)


@login_required
def order_summary(request, order_id):
	order = get_object_or_404(Order.objects.select_related("listing", "seller"), pk=order_id, buyer=request.user)
	return render(request, "payments/order_summary.html", {"order": order})


@login_required
@require_POST
def proceed_to_payment(request, order_id):
	order = get_object_or_404(Order, pk=order_id, buyer=request.user)
	if order.status != Order.Status.PENDING_PAYMENT:
		return redirect("payments:order-detail", order_id=order.id)
	return redirect("payments:payment", order_id=order.id)


@login_required
def payment_checkout(request, order_id):
	order = get_object_or_404(Order.objects.select_related("listing", "payment"), pk=order_id, buyer=request.user)
	return render(request, "payments/payment.html", {"order": order, "demo_payments_enabled": settings.DEMO_PAYMENTS_ENABLED})


@login_required
@require_POST
def demo_payment(request, order_id):
	if not settings.DEMO_PAYMENTS_ENABLED:
		return HttpResponse("Demo payments are disabled.", status=404)
	order = get_object_or_404(Order, pk=order_id, buyer=request.user)
	try:
		order = record_payment_success(order=order, provider_payment_id=f"demo_{order.order_id}", payload={"mode": "demo"})
	except ValueError as error:
		return HttpResponse(str(error), status=400)
	return redirect("payments:payment-success-page", order_id=order.id)


@login_required
@require_POST
def demo_payment_failed(request, order_id):
	if not settings.DEMO_PAYMENTS_ENABLED:
		return HttpResponse("Demo payments are disabled.", status=404)
	order = get_object_or_404(Order, pk=order_id, buyer=request.user)
	record_payment_failure(order=order, reason="Demo payment declined")
	return redirect("payments:order-detail", order_id=order.id)


@login_required
def payment_success_page(request, order_id):
	order = get_object_or_404(Order.objects.select_related("listing", "payment"), pk=order_id, buyer=request.user)
	if order.payment_status != "PAID":
		return redirect("payments:payment", order_id=order.id)
	return render(request, "payments/payment_success.html", {"order": order})


@login_required
def order_detail(request, order_id):
	order = get_object_or_404(Order.objects.select_related("listing", "buyer", "seller", "payment", "transfer"), pk=order_id)
	if request.user.id not in (order.buyer_id, order.seller_id):
		return HttpResponse("You do not have access to this order.", status=403)
	return render(request, "payments/order_detail.html", {"order": order, "is_buyer": request.user.id == order.buyer_id})


@login_required
def my_orders(request):
	orders = Order.objects.filter(buyer=request.user).select_related("listing", "seller").order_by("-created_at")
	return render(request, "payments/my_orders.html", {"orders": orders, "page_title": "My Orders"})


@login_required
def seller_orders(request):
	orders = Order.objects.filter(seller=request.user).select_related("listing", "buyer", "settlement").order_by("-created_at")
	return render(request, "payments/seller_orders.html", {"orders": orders, "page_title": "Seller Orders"})


@login_required
@require_POST
def transfer_start(request, order_id):
	order = get_object_or_404(Order, pk=order_id)
	try:
		start_transfer(order=order, seller=request.user)
	except ValueError as error:
		return HttpResponse(str(error), status=400)
	return redirect("payments:order-detail", order_id=order.id)


@login_required
@require_POST
def transfer_sent(request, order_id):
	order = get_object_or_404(Order, pk=order_id)
	try:
		mark_transfer_sent(order=order, seller=request.user, note=request.POST.get("note", ""))
	except ValueError as error:
		return HttpResponse(str(error), status=400)
	return redirect("payments:order-detail", order_id=order.id)


@login_required
@require_POST
def transfer_received(request, order_id):
	order = get_object_or_404(Order, pk=order_id)
	try:
		confirm_transfer(order=order, buyer=request.user)
	except ValueError as error:
		return HttpResponse(str(error), status=400)
	return redirect("payments:order-detail", order_id=order.id)


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
	provider_order_id = data.get("provider_order_id")
	signature = data.get("signature")
	if not provider_payment_id or not provider_order_id or not signature:
		return JsonResponse({"error": "Verified provider payment details are required"}, status=400)
	if not order.payment.provider_order_id or order.payment.provider_order_id != provider_order_id:
		return JsonResponse({"error": "The provider order does not match this order"}, status=400)
	if not settings.RAZORPAY_KEY_SECRET or not verify_checkout_signature(
		order_id=provider_order_id,
		payment_id=provider_payment_id,
		signature=signature,
	):
		return JsonResponse({"error": "Invalid payment signature"}, status=400)
	try:
		order = record_payment_success(
			order=order,
			provider_payment_id=provider_payment_id,
			payload=data,
			provider_order_id=provider_order_id,
			amount=data.get("amount"),
			currency=data.get("currency"),
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


@login_required
@require_POST
def review_request(request, order_id):
	data = _json_body(request)
	try:
		review = create_review(
			order=get_object_or_404(Order, pk=order_id),
			buyer=request.user,
			rating=data.get("rating"),
			body=data.get("body", ""),
		)
	except (ValueError, TypeError):
		return JsonResponse({"error": "A valid completed order and rating from 1 to 5 are required."}, status=400)
	return JsonResponse({"review_id": review.id, "rating": review.rating}, status=201)


@csrf_exempt
@require_POST
def razorpay_webhook(request):
	signature = request.headers.get("X-Razorpay-Signature", "")
	if not signature or not settings.RAZORPAY_WEBHOOK_SECRET or not verify_webhook_signature(
		body=request.body,
		signature=signature,
	):
		return JsonResponse({"error": "Invalid webhook signature"}, status=400)

	try:
		details = webhook_payment_details(request.body)
	except (TypeError, ValueError, json.JSONDecodeError):
		return JsonResponse({"error": "Invalid webhook payload"}, status=400)
	if not details:
		return HttpResponse(status=200)
	provider_order_id, provider_payment_id, payload = details
	payment = Payment.objects.filter(provider_order_id=provider_order_id).select_related("order").first()
	if not payment:
		return HttpResponse(status=200)
	entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
	record_payment_success(
		order=payment.order,
		provider_payment_id=provider_payment_id,
		payload=payload,
		provider_order_id=provider_order_id,
		amount=Decimal(str(entity["amount"])) / 100 if "amount" in entity else None,
		currency=entity.get("currency"),
	)
	return HttpResponse(status=200)
