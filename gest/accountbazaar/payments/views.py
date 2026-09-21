import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from marketplace.models import Listing

from .models import Order
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
	return JsonResponse({"order_id": order.id, "status": order.status}, status=201)


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
