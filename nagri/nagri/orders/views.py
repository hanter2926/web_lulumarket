import hashlib
import hmac
import uuid
from decimal import Decimal

import razorpay
from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from cart.models import Cart
from products.models import Product

from .models import Order, OrderItem
from .serializers import OrderItemSerializer, OrderSerializer


def verify_razorpay_signature(order_id, payment_id, razorpay_signature, secret):
    generated = hmac.new(
        secret.encode(),
        f"{order_id}|{payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(generated, razorpay_signature)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def verify_payment(request):
    razorpay_order_id = request.data.get("razorpay_order_id")
    razorpay_payment_id = request.data.get("razorpay_payment_id")
    razorpay_signature = request.data.get("razorpay_signature")

    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return Response({"detail": "Missing payment verification data."}, status=status.HTTP_400_BAD_REQUEST)

    order = get_object_or_404(Order, razorpay_order_id=razorpay_order_id, user=request.user)

    if not verify_razorpay_signature(
        razorpay_order_id,
        razorpay_payment_id,
        razorpay_signature,
        settings.RAZORPAY_KEY_SECRET,
    ):
        order.status = "cancelled"
        order.save(update_fields=["status", "updated_at"])
        return Response({"detail": "Payment verification failed."}, status=status.HTTP_400_BAD_REQUEST)

    order.razorpay_payment_id = razorpay_payment_id
    order.razorpay_signature = razorpay_signature
    order.is_paid = True
    order.status = "paid"
    order.save(update_fields=["razorpay_payment_id", "razorpay_signature", "is_paid", "status", "updated_at"])
    return Response({"detail": "Payment verified and order marked as paid.", "order_id": order.id})


@api_view(["POST"])
def payment_webhook(request):
    payload = request.data
    event = payload.get("event")
    if event != "payment.captured":
        return Response({"detail": "Ignored event."}, status=status.HTTP_200_OK)

    payment_entity = payload.get("payload", {}).get("payment", {}).get("entity", {})
    order_id = payment_entity.get("order_id")
    payment_id = payment_entity.get("id")
    signature = payment_entity.get("signature")
    if not all([order_id, payment_id]):
        return Response({"detail": "Missing webhook payment payload."}, status=status.HTTP_400_BAD_REQUEST)

    order = get_object_or_404(Order, razorpay_order_id=order_id)
    order.razorpay_payment_id = payment_id
    order.razorpay_signature = signature or order.razorpay_signature
    order.is_paid = True
    order.status = "paid"
    order.save(update_fields=["razorpay_payment_id", "razorpay_signature", "is_paid", "status", "updated_at"])
    return Response({"status": "ok"}, status=status.HTTP_200_OK)


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return Order.objects.prefetch_related("items__product").all().order_by("-created_at")
        return Order.objects.filter(user=self.request.user).prefetch_related("items__product").order_by("-created_at")

    @action(detail=True, methods=["get"], url_path="invoice")
    def invoice(self, request, pk=None):
        order = self.get_object()
        invoice_lines = [
            "Nagri Invoice",
            f"Order Number: {order.order_number}",
            f"Status: {order.status}",
            f"Tracking: {order.tracking_status}",
            f"Total Amount: ₹{order.total_amount}",
            "",
            "Items:",
        ]

        for item in order.items.all():
            invoice_lines.append(f"- {item.product.name} x {item.quantity} @ ₹{item.price}")

        content = "\n".join(invoice_lines)
        response = HttpResponse(content, content_type="text/plain")
        response["Content-Disposition"] = f'attachment; filename="invoice-{order.order_number}.txt"'
        return response

    @action(detail=False, methods=["post"], url_path="create")
    def create_order(self, request):
        user = request.user
        product_id = request.data.get("product_id")
        quantity = int(request.data.get("quantity", 1) or 1)
        cart_id = request.data.get("cart_id")

        if cart_id:
            cart = get_object_or_404(Cart, id=cart_id, user=user)
            cart_items = cart.items.select_related("product")
            if not cart_items.exists():
                return Response({"detail": "Cart is empty."}, status=status.HTTP_400_BAD_REQUEST)
            order_items = []
            total_amount = Decimal("0.00")
            for item in cart_items:
                order_items.append({
                    "product": item.product,
                    "quantity": item.quantity,
                    "price": item.product.price,
                })
                total_amount += Decimal(str(item.product.price)) * item.quantity
        else:
            if not product_id:
                return Response({"detail": "product_id is required."}, status=status.HTTP_400_BAD_REQUEST)
            product = get_object_or_404(Product, id=product_id)
            total_amount = Decimal(str(product.price)) * quantity
            order_items = [{"product": product, "quantity": quantity, "price": product.price}]

        order_number = f"ORD-{uuid.uuid4().hex[:10].upper()}"
        order = Order.objects.create(
            user=user,
            order_number=order_number,
            total_amount=total_amount,
            status="pending",
            payment_provider="razorpay",
            is_paid=False,
        )

        for item in order_items:
            OrderItem.objects.create(
                order=order,
                product=item["product"],
                quantity=item["quantity"],
                price=item["price"],
            )

        try:
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            razorpay_order = client.order.create({
                "amount": int(total_amount * 100),
                "currency": "INR",
                "receipt": order_number,
                "notes": {"order_id": str(order.id), "user_id": str(user.id)},
            })
        except Exception as exc:
            order.delete()
            return Response({"detail": f"Razorpay order creation failed: {exc}"}, status=status.HTTP_400_BAD_REQUEST)

        order.razorpay_order_id = razorpay_order.get("id")
        order.save(update_fields=["razorpay_order_id", "updated_at"])

        return Response({
            "order_id": order.id,
            "order_number": order.order_number,
            "amount": int(total_amount * 100),
            "currency": "INR",
            "razorpay_order_id": order.razorpay_order_id,
            "key": settings.RAZORPAY_KEY_ID,
            "name": "Nagri",
            "description": "Order Payment",
            "image": "https://example.com/logo.png",
        }, status=status.HTTP_201_CREATED)


class OrderItemViewSet(viewsets.ModelViewSet):
    serializer_class = OrderItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if self.request.user.is_staff:
            return OrderItem.objects.select_related("order", "product").all().order_by("id")
        return OrderItem.objects.filter(order__user=self.request.user).select_related("order", "product").order_by("id")
