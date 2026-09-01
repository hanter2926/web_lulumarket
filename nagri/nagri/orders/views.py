import hashlib
import hmac
import uuid
from decimal import Decimal

import razorpay
from django.conf import settings
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q, Count
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
import logging
from django.db import DatabaseError

from cart.models import Cart
from products.models import Product
from accounts.models import Address

from .models import Order, OrderItem, UpiPaymentSubmission
from .serializers import OrderItemSerializer, OrderSerializer
from django.urls import reverse


@login_required(login_url='login_page')
def order_list_view(request):
    """Display user's orders with statistics"""
    orders = Order.objects.filter(user=request.user).prefetch_related('items__product').order_by('-created_at')
    
    # Calculate statistics
    total_orders = orders.count()
    completed_count = orders.filter(status='delivered').count()
    pending_count = orders.filter(status__in=['pending', 'processing']).count()
    cancelled_count = orders.filter(status='cancelled').count()
    
    context = {
        'orders': orders,
        'completed_count': completed_count,
        'pending_count': pending_count,
        'cancelled_count': cancelled_count,
    }
    return render(request, 'orders/order_list.html', context)


@login_required(login_url='login_page')
def order_detail_view(request, order_id):
    """Display detailed information about a specific order"""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    items = order.items.all().select_related('product')
    
    context = {
        'order': order,
        'items': items,
    }
    return render(request, 'orders/order_detail.html', context)


@login_required(login_url='login_page')
def checkout_view(request):
    """First step of checkout - review cart items"""
    cart, _ = Cart.objects.get_or_create(user=request.user)
    items = cart.items.all().select_related('product')
    
    if not items.exists():
        messages.warning(request, 'Your cart is empty. Please add items before checkout.')
        return redirect('cart_detail')
    
    subtotal = sum(item.product.price * item.quantity for item in items)
    
    # Store checkout session data
    request.session['checkout_subtotal'] = str(subtotal)
    request.session['checkout_step'] = 'checkout'
    
    context = {
        'items': items,
        'subtotal': subtotal,
        'cart_count': items.count(),
    }
    return render(request, 'checkout/checkout.html', context)


@login_required(login_url='login_page')
def checkout_address_view(request):
    """Second step - select/enter shipping address"""
    from .forms import CheckoutAddressForm
    
    user = request.user
    try:
        saved_addresses = Address.objects.filter(user=user)
        default_address = saved_addresses.filter(is_default=True).first()
    except DatabaseError:
        logging.exception("Database error while fetching addresses for user %s", getattr(user, 'id', None))
        # Show a friendly message instead of raising 500
        messages.error(request, 'There was a problem retrieving your saved addresses. Please try again later.')
        saved_addresses = Address.objects.none()
        default_address = None
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'select_saved':
            address_id = request.POST.get('address_id')
            # If no address_id submitted, show friendly validation message
            if not address_id:
                messages.error(request, 'Please select an address before continuing.')
                form = CheckoutAddressForm()
                context = {
                    'saved_addresses': saved_addresses,
                    'default_address': default_address,
                    'form': form,
                }
                return render(request, 'checkout/address.html', context)

            # Ensure the address exists and belongs to the current user
            try:
                address = get_object_or_404(Address, id=address_id, user=user)
            except Http404:
                messages.error(request, 'Selected address was not found. Please choose a different address.')
                return redirect('checkout_address')

            request.session['checkout_address_id'] = address.id
            request.session['checkout_step'] = 'delivery'
            messages.success(request, 'Address selected successfully.')
            return redirect('checkout_delivery')
        
        elif action == 'new_address':
            form = CheckoutAddressForm(request.POST)
            if form.is_valid():
                try:
                    address = form.save(commit=False)
                    address.user = user
                    address.save()
                except DatabaseError:
                    logging.exception("Database error while saving address for user %s", getattr(user, 'id', None))
                    messages.error(request, 'Unable to save address right now. Please try again later.')
                    return redirect('checkout_address')

                request.session['checkout_address_id'] = address.id
                request.session['checkout_step'] = 'delivery'
                messages.success(request, 'Address saved successfully.')
                return redirect('checkout_delivery')
    else:
        form = CheckoutAddressForm()
    
    context = {
        'saved_addresses': saved_addresses,
        'default_address': default_address,
        'form': form,
    }
    return render(request, 'checkout/address.html', context)


@login_required(login_url='login_page')
def checkout_delivery_view(request):
    """Third step - select delivery method"""
    from .forms import DeliveryMethodForm
    
    address_id = request.session.get('checkout_address_id')
    if not address_id:
        messages.warning(request, 'Please select an address first.')
        return redirect('checkout_address')
    
    address = get_object_or_404(Address, id=address_id, user=request.user)
    
    if request.method == 'POST':
        form = DeliveryMethodForm(request.POST)
        if form.is_valid():
            request.session['checkout_delivery_method'] = form.cleaned_data['delivery_method']
            request.session['checkout_step'] = 'payment'
            return redirect('checkout_payment')
    else:
        form = DeliveryMethodForm()
    
    context = {
        'address': address,
        'form': form,
    }
    return render(request, 'checkout/delivery.html', context)


@login_required(login_url='login_page')
def checkout_payment_view(request):
    """Fourth step - select payment method"""
    from .forms import PaymentMethodForm, CouponForm
    
    address_id = request.session.get('checkout_address_id')
    delivery_method = request.session.get('checkout_delivery_method', 'standard')
    
    if not address_id:
        messages.warning(request, 'Please complete previous steps.')
        return redirect('checkout_address')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'apply_coupon':
            coupon_form = CouponForm(request.POST)
            payment_form = PaymentMethodForm()
            if coupon_form.is_valid():
                coupon_code = coupon_form.cleaned_data.get('coupon_code')
                if coupon_code:
                    request.session['checkout_coupon'] = coupon_code
                    messages.success(request, 'Coupon applied successfully.')
            else:
                messages.error(request, 'Invalid coupon.')
        
        else:
            payment_form = PaymentMethodForm(request.POST)
            coupon_form = CouponForm()
            if payment_form.is_valid():
                request.session['checkout_payment_method'] = payment_form.cleaned_data['payment_method']
                request.session['checkout_step'] = 'review'
                return redirect('checkout_review')
    else:
        payment_form = PaymentMethodForm()
        coupon_form = CouponForm()
    
    # Recompute subtotals from the cart as the authoritative source.
    try:
        cart, _ = Cart.objects.get_or_create(user=request.user)
        items = cart.items.select_related('product').all()
        # discounted subtotal uses product.price
        discounted_subtotal = sum((item.product.price or Decimal(0)) * item.quantity for item in items)
        # original subtotal uses compare_price when it's greater than price
        original_subtotal = Decimal(0)
        for item in items:
            p = item.product
            try:
                orig_price = p.compare_price if (p.compare_price and p.compare_price > p.price) else p.price
            except Exception:
                orig_price = p.price
            original_subtotal += (orig_price or Decimal(0)) * item.quantity
    except Exception:
        discounted_subtotal = Decimal(0)
        original_subtotal = Decimal(0)

    delivery_charge = Decimal(get_delivery_charge(delivery_method))

    # Compute discount amount/percent from the two subtotals
    discount_amount = (original_subtotal - discounted_subtotal) if original_subtotal > discounted_subtotal else Decimal(0)
    if original_subtotal and original_subtotal > 0:
        try:
            discount_percent = (discount_amount / original_subtotal) * Decimal(100)
        except Exception:
            discount_percent = Decimal(0)
    else:
        discount_percent = Decimal(0)

    # Final payable is discounted subtotal plus delivery
    total = discounted_subtotal + delivery_charge
    
    context = {
        'payment_form': payment_form,
        'coupon_form': coupon_form,
        'original_subtotal': original_subtotal,
        'discounted_subtotal': discounted_subtotal,
        'delivery_charge': delivery_charge,
        'discount_amount': discount_amount,
        'discount_percent': discount_percent,
        'total': total,
        'delivery_method': delivery_method,
    }
    return render(request, 'checkout/payment.html', context)


@login_required(login_url='login_page')
def checkout_review_view(request):
    """Fifth step - review order before placing"""
    user = request.user
    
    # Get session data
    address_id = request.session.get('checkout_address_id')
    delivery_method = request.session.get('checkout_delivery_method', 'standard')
    payment_method = request.session.get('checkout_payment_method', 'razorpay')
    coupon_code = request.session.get('checkout_coupon', '')
    
    if not address_id:
        messages.warning(request, 'Please complete checkout steps.')
        return redirect('checkout_address')
    
    # Get cart and address
    cart = get_object_or_404(Cart, user=user)
    cart_items = cart.items.all().select_related('product')
    address = get_object_or_404(Address, id=address_id, user=user)
    
    if not cart_items.exists():
        messages.warning(request, 'Your cart is empty.')
        return redirect('cart_detail')
    
    # Calculate totals: use product.compare_price as original where applicable
    discounted_subtotal = sum(item.product.price * item.quantity for item in cart_items)
    original_subtotal = Decimal(0)
    for item in cart_items:
        p = item.product
        try:
            orig_price = p.compare_price if (p.compare_price and p.compare_price > p.price) else p.price
        except Exception:
            orig_price = p.price
        original_subtotal += (orig_price or Decimal(0)) * item.quantity

    delivery_charge = get_delivery_charge(delivery_method)
    discount_amount = (original_subtotal - discounted_subtotal) if original_subtotal > discounted_subtotal else Decimal(0)
    total = discounted_subtotal + delivery_charge
    
    if request.method == 'POST':
        # Create order
        order_number = f"ORD-{uuid.uuid4().hex[:10].upper()}"
        order = Order.objects.create(
            user=user,
            order_number=order_number,
            subtotal=original_subtotal,
            discount_amount=discount_amount,
            delivery_charge=delivery_charge,
            total_amount=total,
            shipping_address=address,
            shipping_address_name=address.full_name,
            shipping_address_phone=address.phone,
            shipping_address_line1=address.address_line_1,
            shipping_address_line2=address.address_line_2,
            shipping_address_city=address.city,
            shipping_address_state=address.state,
            shipping_address_postal_code=address.pincode,
            shipping_address_country=address.country,
            delivery_method=delivery_method,
            payment_method=payment_method,
            coupon_code=coupon_code,
            status='pending',
            is_paid=False,
        )
        
        # Create order items
        for cart_item in cart_items:
            OrderItem.objects.create(
                order=order,
                product=cart_item.product,
                quantity=cart_item.quantity,
                price=cart_item.product.price,
            )
        
        # Clear cart
        cart.items.all().delete()

        # Clear session
        for key in list(request.session.keys()):
            if key.startswith('checkout_'):
                del request.session[key]

        # Redirect based on payment method
        # For COD, show order success (order placed) page immediately.
        if order.payment_method == 'cod':
            return redirect('payment_success', order_id=order.id)

        # For online methods redirect to payment page where gateway flows happen.
        return redirect('payment_page', order_id=order.id)
    
    context = {
        'cart_items': cart_items,
        'address': address,
        'delivery_method': delivery_method,
        'payment_method': payment_method,
        'original_subtotal': original_subtotal,
        'discounted_subtotal': discounted_subtotal,
        'delivery_charge': delivery_charge,
        'discount_amount': discount_amount,
        'total': total,
    }
    return render(request, 'checkout/order_review.html', context)


@login_required(login_url='login')
def order_confirmation_view(request, order_id):
    """Order confirmation page after successful order placement"""
    order = get_object_or_404(Order, id=order_id, user=request.user)
    items = order.items.all().select_related('product')
    
    context = {
        'order': order,
        'items': items,
    }
    return render(request, 'checkout/order_confirmation.html', context)


def get_delivery_charge(delivery_method):
    """Helper function to get delivery charge"""
    charges = {
        'standard': Decimal(0),
        'express': Decimal(50),
        'overnight': Decimal(100),
    }
    return charges.get(delivery_method, Decimal(0))


@login_required(login_url='login_page')
def payment_page_view(request, order_id):
    """Render payment page for an order. For online payments create a Razorpay order id if missing."""
    order = get_object_or_404(Order, id=order_id, user=request.user)

    # If COD, render page (template handles display)
    if order.payment_method == 'cod':
        context = {'order': order}
        return render(request, 'payment/payment.html', context)

    # For other payment methods, ensure we have a razorpay_order_id (if Razorpay is configured)
    try:
        # Create razorpay order if missing
        if not order.razorpay_order_id:
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            razorpay_order = client.order.create({
                'amount': int(order.total_amount * 100),
                'currency': 'INR',
                'receipt': order.order_number,
                'notes': {'order_id': str(order.id), 'user_id': str(order.user.id)},
            })
            order.razorpay_order_id = razorpay_order.get('id')
            order.save(update_fields=['razorpay_order_id', 'updated_at'])
    except Exception:
        # If gateway not configured or creation failed, log the exception and show a friendly message
        logging.exception("Razorpay order creation failed for order %s", getattr(order, 'id', None))
        context = {'order': order, 'gateway_error': True}
        return render(request, 'payment/payment.html', context)

    context = {
        'order': order,
        'razorpay_key': settings.RAZORPAY_KEY_ID,
        'amount_paise': int(order.total_amount * 100),
        'manual_upi_id': settings.MANUAL_UPI_ID,
    }
    return render(request, 'payment/payment.html', context)


@login_required(login_url='login_page')
def upi_submit_view(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if request.method != 'POST':
        return redirect('payment_page', order_id=order.id)

    utr = request.POST.get('utr', '').strip()
    upi_id = settings.MANUAL_UPI_ID or request.POST.get('upi_id', '').strip()
    receipt = request.FILES.get('receipt')

    if not upi_id:
        messages.error(request, 'UPI ID not configured. Contact the site administrator.')
        return redirect('payment_page', order_id=order.id)

    # Use server-side amount to avoid manipulation
    amount = order.total_amount

    submission = UpiPaymentSubmission.objects.create(
        order=order,
        upi_id=upi_id,
        amount=amount,
        utr=utr or None,
        receipt=receipt or None,
        status='pending',
    )

    # Mark order status to pending_verification and set provider
    order.status = 'pending_verification'
    order.payment_provider = 'manual_upi'
    order.save(update_fields=['status', 'payment_provider', 'updated_at'])

    messages.success(request, 'UPI payment submitted. It will be verified by admin shortly.')
    return redirect('order_detail', order_id=order.id)


@login_required(login_url='login_page')
def payment_success_view(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    # Allow viewing success/order page for one of:
    # - actually paid orders
    # - Cash on Delivery orders (order placed but unpaid)
    # - orders pending manual verification (e.g., manual UPI submissions)
    if not (order.is_paid or order.payment_method == 'cod' or order.status == 'pending_verification'):
        messages.error(request, 'Payment not completed for this order. Please complete payment first.')
        return redirect('payment_page', order_id=order.id)

    items = order.items.all().select_related('product')
    return render(request, 'payment/payment_success.html', {'order': order, 'items': items})


@login_required(login_url='login_page')
def payment_failed_view(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'payment/payment_failed.html', {'order': order})


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

    # Idempotent: if already marked paid, return success
    if order.is_paid and order.razorpay_payment_id == razorpay_payment_id:
        return Response({"detail": "Payment already verified.", "order_id": order.id}, status=status.HTTP_200_OK)

    try:
        valid = verify_razorpay_signature(
            razorpay_order_id,
            razorpay_payment_id,
            razorpay_signature,
            settings.RAZORPAY_KEY_SECRET,
        )
    except Exception as exc:
        logging.exception("Error while verifying razorpay signature")
        return Response({"detail": "Internal error verifying payment."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if not valid:
        # Do not mark as paid; keep order pending so customer can retry.
        order.status = "pending"
        order.save(update_fields=["status", "updated_at"]) 
        return Response({"detail": "Payment verification failed."}, status=status.HTTP_400_BAD_REQUEST)

    # Mark order as paid in a single safe write
    order.razorpay_payment_id = razorpay_payment_id
    order.razorpay_signature = razorpay_signature
    order.is_paid = True
    order.status = "paid"
    order.save(update_fields=["razorpay_payment_id", "razorpay_signature", "is_paid", "status", "updated_at"])

    return Response({"detail": "Payment verified and order marked as paid.", "order_id": order.id}, status=status.HTTP_200_OK)


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

    # Verify webhook authenticity using configured webhook secret
    webhook_secret = getattr(settings, 'RAZORPAY_WEBHOOK_SECRET', None)
    signature_header = request.META.get('HTTP_X_RAZORPAY_SIGNATURE') or request.headers.get('X-Razorpay-Signature', '')
    if not webhook_secret:
        logging.warning('Razorpay webhook secret not configured; rejecting webhook.')
        return Response({"detail": "Webhook not configured."}, status=status.HTTP_403_FORBIDDEN)

    try:
        # request.body is the raw payload bytes
        import hmac as _hmac
        generated = _hmac.new(webhook_secret.encode(), request.body, hashlib.sha256).hexdigest()
        if not _hmac.compare_digest(generated, signature_header or ''):
            logging.warning('Invalid razorpay webhook signature for order %s', order_id)
            return Response({"detail": "Invalid webhook signature."}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logging.exception('Error while verifying razorpay webhook signature')
        return Response({"detail": "Webhook verification error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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

    @action(detail=True, methods=["patch"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Cancel an order if it is in a cancellable state (pending/processing)."""
        order = self.get_object()
        # Allow cancellation only for pending or processing orders
        if order.status not in ["pending", "processing"]:
            return Response({"detail": "Only pending or processing orders can be cancelled."}, status=status.HTTP_400_BAD_REQUEST)

        order.status = "cancelled"
        order.save(update_fields=["status", "updated_at"])

        serializer = self.get_serializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)

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
            discounted_subtotal = Decimal("0.00")
            original_subtotal = Decimal("0.00")
            for item in cart_items:
                order_items.append({
                    "product": item.product,
                    "quantity": item.quantity,
                    "price": item.product.price,
                })
                discounted_subtotal += (item.product.price or Decimal(0)) * item.quantity
                try:
                    orig_price = item.product.compare_price if (item.product.compare_price and item.product.compare_price > item.product.price) else item.product.price
                except Exception:
                    orig_price = item.product.price
                original_subtotal += (orig_price or Decimal(0)) * item.quantity
            # final payable for cart path
            total_amount = discounted_subtotal
        else:
            if not product_id:
                return Response({"detail": "product_id is required."}, status=status.HTTP_400_BAD_REQUEST)
            product = get_object_or_404(Product, id=product_id)
            discounted_subtotal = Decimal(str(product.price)) * quantity
            try:
                orig_price = product.compare_price if (product.compare_price and product.compare_price > product.price) else product.price
            except Exception:
                orig_price = product.price
            original_subtotal = (orig_price or Decimal(0)) * quantity
            total_amount = discounted_subtotal
            order_items = [{"product": product, "quantity": quantity, "price": product.price}]

        order_number = f"ORD-{uuid.uuid4().hex[:10].upper()}"
        # Use computed original_subtotal and discounted total_amount
        try:
            _orig = original_subtotal
        except NameError:
            _orig = discounted_subtotal if 'discounted_subtotal' in locals() else Decimal(0)
        discount_amount = (_orig - total_amount) if _orig and _orig > total_amount else Decimal(0)

        order = Order.objects.create(
            user=user,
            order_number=order_number,
            subtotal=_orig,
            discount_amount=discount_amount,
            delivery_charge=Decimal(0),
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
