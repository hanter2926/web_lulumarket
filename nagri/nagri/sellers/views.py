import logging
import os
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Case, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.http import HttpResponseForbidden

from .models import SellerApplication
from .forms import OTPVerifyForm, SellerDocumentsForm, CategorySelectionForm, SellerProductForm
from accounts.models import CustomUser
from products.models import Category, Product
from orders.models import Order, OrderItem


@login_required
def apply_start(request):
    # Create or get a draft application for user
    app, _ = SellerApplication.objects.get_or_create(user=request.user, defaults={"email": request.user.email})
    return render(request, "sellers/apply_start.html", {"application": app})


def _seller_otp_wait_seconds(app):
    if not app or not app.otp_last_sent_at:
        return 0
    remaining = 60 - int((timezone.now() - app.otp_last_sent_at).total_seconds())
    return max(0, remaining)


logger = logging.getLogger(__name__)


@login_required
def send_email_otp(request):
    app, _ = SellerApplication.objects.get_or_create(user=request.user, defaults={"email": request.user.email})

    if request.method != "POST":
        if app.email_verified:
            return redirect("sellers:documents")
        return redirect("sellers:verify_email")

    logger.info("Seller OTP send attempt for recipient=%s", app.email)

    def send_callable(to_email, otp):
        subject = "Your NAGRI Seller Verification OTP"
        message = f"Your verification OTP is: {otp}\nIt will expire soon."
        # Use DEFAULT_FROM_EMAIL from settings for consistency with other sends
        try:
            logger.info("Attempting to send seller OTP email to %s", to_email)
            # use positional args to match expected call-site in requirements
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [to_email],
                fail_silently=False,
            )
            logger.info("Seller OTP email sent successfully to %s", to_email)
        except Exception:
            # Log full exception (stack trace) to development / Render logs
            logger.exception("Failed to send seller OTP email for user_id=%s", request.user.id if getattr(request, 'user', None) else None)
            # Re-raise so outer handler can decide flow (and to avoid double-success messages)
            raise

    try:
        app.generate_and_send_otp(send_callable)
    except ValidationError as exc:
        message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
        logger.warning("Seller OTP cooldown/validation error for recipient=%s: %s", app.email, message)
        messages.error(request, message)
        return redirect("sellers:verify_email")
    except Exception:
        # The inner send_callable already logged the exception; ensure it's captured here too
        logger.exception("Failed to send seller OTP email for user_id=%s", request.user.id if getattr(request, 'user', None) else None)
        messages.error(request, "Unable to send OTP right now. Please try again later.")
        return redirect("sellers:verify_email")

    messages.success(request, "OTP has been sent to your email address.")
    return redirect("sellers:verify_email")


@login_required
def verify_email_otp(request):
    app = get_object_or_404(SellerApplication, user=request.user)
    if app.email_verified:
        return redirect("sellers:documents")

    resend_wait_seconds = _seller_otp_wait_seconds(app)

    if request.method == "POST":
        form = OTPVerifyForm(request.POST)
        if form.is_valid():
            otp = form.cleaned_data["otp"]
            ok, reason = app.verify_otp(otp)
            if ok:
                messages.success(request, "Email verified successfully.")
                return redirect("sellers:documents")

            if reason == "expired":
                messages.error(request, "OTP has expired. Please request a new one.")
            elif reason == "attempts_exceeded":
                messages.error(request, "Too many invalid attempts. Please request a new OTP.")
            elif reason == "invalid":
                messages.error(request, "Invalid OTP.")
            else:
                messages.error(request, "Please request a new OTP.")

            return render(request, "sellers/verify_email.html", {"form": form, "application": app, "resend_wait_seconds": resend_wait_seconds})

    else:
        form = OTPVerifyForm()

    return render(request, "sellers/verify_email.html", {"form": form, "application": app, "resend_wait_seconds": resend_wait_seconds})


@login_required
def documents(request):
    app, _ = SellerApplication.objects.get_or_create(user=request.user, defaults={"email": request.user.email})
    if not app.email_verified:
        return redirect("sellers:apply_start")

    if request.method == "POST":
        form = SellerDocumentsForm(request.POST, request.FILES, instance=app)
        if form.is_valid():
            form.save()
            app.status = "documents_submitted"
            app.save(update_fields=["status"])
            return redirect("sellers:categories")
    else:
        form = SellerDocumentsForm(instance=app)
    return render(request, "sellers/documents.html", {"form": form, "application": app})


@login_required
def categories(request):
    app, _ = SellerApplication.objects.get_or_create(user=request.user, defaults={"email": request.user.email})
    if app.status not in ("email_verified", "documents_submitted"):
        return redirect("sellers:apply_start")

    if request.method == "POST":
        form = CategorySelectionForm(request.POST)
        if form.is_valid():
            cats = form.cleaned_data["categories"]
            app.selected_categories.set(cats)
            # mark as pending review
            app.status = "pending_review"
            app.submitted_at = timezone.now()
            app.save(update_fields=["status", "submitted_at"])

            # send notification emails
            send_mail(
                "Seller application submitted",
                f"Seller {request.user.get_full_name() or request.user.email} submitted an application.",
                settings.DEFAULT_FROM_EMAIL,
                [request.user.email],
                fail_silently=True,
            )
            # notify site owner (DEFAULT_FROM_EMAIL)
            owner_email = settings.DEFAULT_FROM_EMAIL
            if owner_email:
                send_mail(
                    "New seller application",
                    f"New seller application by {request.user.get_full_name() or request.user.email}.",
                    settings.DEFAULT_FROM_EMAIL,
                    [owner_email],
                    fail_silently=True,
                )

            return render(request, "sellers/submitted.html")
    else:
        form = CategorySelectionForm()
    return render(request, "sellers/categories.html", {"form": form, "application": app})


@login_required
def status_view(request):
    app, _ = SellerApplication.objects.get_or_create(user=request.user, defaults={"email": request.user.email})
    return render(request, "sellers/status.html", {"application": app})


def protected_document_view(request, pk, field):
    # serves document files only to owner or staff
    app = get_object_or_404(SellerApplication, pk=pk)
    if not (
        request.user.is_authenticated
        and (
            request.user == app.user
            or request.user.is_staff
            or request.user.is_superuser
            or getattr(request.user, "is_owner", False)
        )
    ):
        return HttpResponseForbidden()
    f = getattr(app, field, None)
    if not f:
        return HttpResponseForbidden()
    try:
        file_obj = f.open('rb')
    except (FileNotFoundError, OSError, ValueError):
        return HttpResponseForbidden()
    from django.http import FileResponse
    return FileResponse(file_obj, as_attachment=False, filename=os.path.basename(f.name))


def _get_approved_seller_application(request):
    if not request.user.is_authenticated:
        return None, redirect("accounts:login")

    app = SellerApplication.objects.filter(user=request.user).first()
    if app and app.status == "suspended":
        return None, HttpResponseForbidden()

    if not request.user.is_vendor:
        return None, redirect("sellers:apply_start")

    if app is None:
        app = SellerApplication.objects.create(user=request.user, email=request.user.email, status="approved")

    if app.status == "approved":
        return app, None

    return None, redirect("sellers:status")


def _is_marketplace_owner(user):
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return bool(user.is_superuser or getattr(user, "is_owner", False))


def _require_marketplace_owner(request):
    if not _is_marketplace_owner(request.user):
        return HttpResponseForbidden()
    return None


def _category_allowed_for_seller(app, category_id):
    if category_id is None:
        return False
    return app.selected_categories.filter(id=category_id).exists()


def _get_owned_product_or_403(request, pk):
    product = Product.objects.select_related("category", "subcategory", "inventory").filter(pk=pk).first()
    if not product or product.seller_id != request.user.id:
        return None, HttpResponseForbidden()
    return product, None


def _seller_order_items_queryset(request):
    return (
        OrderItem.objects.filter(product__seller=request.user)
        .select_related("order", "product", "product__category", "product__inventory")
        .prefetch_related("product__images")
        .order_by("-order__created_at", "-id")
    )


def _get_seller_order_item_or_403(request, item_id):
    item = OrderItem.objects.select_related("order", "product", "product__seller").get(pk=item_id)
    if item.product.seller_id != request.user.id:
        return None, HttpResponseForbidden()
    return item, None


def _seller_item_total_expression():
    return (F("price") * F("quantity"))


def _order_item_metric_summary(items_qs):
    return items_qs.aggregate(
        total_units=Coalesce(Sum("quantity"), 0),
        gross_sales=Coalesce(Sum(F("price") * F("quantity"), output_field=None), Decimal("0.00")),
        online_paid=Coalesce(Sum(
            Case(
                When(order__is_paid=True, order__payment_method__in=["razorpay", "netbanking", "upi", "wallet"], then=F("price") * F("quantity")),
                default=Value(Decimal("0.00")),
                output_field=None,
            )
        ), Decimal("0.00")),
        upi_manual=Coalesce(Sum(
            Case(
                When(order__payment_method__in=["upi", "netbanking", "wallet"], then=F("price") * F("quantity")),
                default=Value(Decimal("0.00")),
                output_field=None,
            )
        ), Decimal("0.00")),
        cod_amount=Coalesce(Sum(
            Case(
                When(order__payment_method="cod", then=F("price") * F("quantity")),
                default=Value(Decimal("0.00")),
                output_field=None,
            )
        ), Decimal("0.00")),
        pending_amount=Coalesce(Sum(
            Case(
                When(order__is_paid=False, order__payment_method__in=["razorpay", "netbanking", "upi", "wallet"], then=F("price") * F("quantity")),
                default=Value(Decimal("0.00")),
                output_field=None,
            )
        ), Decimal("0.00")),
        pending_items=Coalesce(Sum(Case(When(fulfillment_status="pending", then=1), default=0, output_field=None)), 0),
        processing_items=Coalesce(Sum(Case(When(fulfillment_status="processing", then=1), default=0, output_field=None)), 0),
        shipped_items=Coalesce(Sum(Case(When(fulfillment_status="shipped", then=1), default=0, output_field=None)), 0),
        delivered_items=Coalesce(Sum(Case(When(fulfillment_status="delivered", then=1), default=0, output_field=None)), 0),
        cancelled_items=Coalesce(Sum(Case(When(fulfillment_status="cancelled", then=1), default=0, output_field=None)), 0),
    )


def _seller_payment_summary_for_items(items_qs):
    return _order_item_metric_summary(items_qs)


def _seller_summary_for_user(user):
    qs = OrderItem.objects.filter(product__seller=user).select_related("order", "product")
    metrics = _order_item_metric_summary(qs)
    products = Product.objects.filter(seller=user).select_related("category", "inventory")
    return {
        "seller": user,
        "products": products,
        "total_products": products.count(),
        "active_products": products.filter(is_active=True).count(),
        "inactive_products": products.filter(is_active=False).count(),
        "units_sold": metrics["total_units"],
        "gross_sales": metrics["gross_sales"],
        "online_paid": metrics["online_paid"],
        "upi_manual": metrics["upi_manual"],
        "cod_amount": metrics["cod_amount"],
        "pending_amount": metrics["pending_amount"],
        "pending_items": metrics["pending_items"],
        "processing_items": metrics["processing_items"],
        "shipped_items": metrics["shipped_items"],
        "delivered_items": metrics["delivered_items"],
        "cancelled_items": metrics["cancelled_items"],
    }





@login_required
def owner_dashboard(request):
    forbidden = _require_marketplace_owner(request)
    if forbidden is not None:
        return forbidden

    total_apps = SellerApplication.objects.count()
    pending_apps = SellerApplication.objects.filter(status="pending_review").count()
    approved_apps = SellerApplication.objects.filter(status="approved").count()
    activated_sellers = CustomUser.objects.filter(is_vendor=True).count()
    rejected_apps = SellerApplication.objects.filter(status="rejected").count()
    suspended_apps = SellerApplication.objects.filter(status="suspended").count()

    total_products = Product.objects.count()
    active_products = Product.objects.filter(is_active=True).count()
    inactive_products = Product.objects.filter(is_active=False).count()
    all_items = OrderItem.objects.select_related("order", "product", "product__seller")
    market_metrics = _order_item_metric_summary(all_items)

    summary = {
        "total_seller_applications": total_apps,
        "pending_seller_applications": pending_apps,
        "approved_sellers": approved_apps,
        "activated_sellers": activated_sellers,
        "rejected_sellers": rejected_apps,
        "suspended_sellers": suspended_apps,
        "total_seller_products": total_products,
        "active_seller_products": active_products,
        "inactive_seller_products": inactive_products,
        "total_marketplace_orders": Order.objects.count(),
        "total_units_sold": market_metrics["total_units"],
        "total_marketplace_gross_sales": market_metrics["gross_sales"],
        "total_online_paid": market_metrics["online_paid"],
        "total_upi_manual": market_metrics["upi_manual"],
        "total_cod_amount": market_metrics["cod_amount"],
        "total_pending_unpaid_amount": market_metrics["pending_amount"],
    }
    return render(request, "sellers/owner_dashboard.html", {"application": None, "summary": summary})


@login_required
def owner_seller_list(request):
    forbidden = _require_marketplace_owner(request)
    if forbidden is not None:
        return forbidden

    queryset = SellerApplication.objects.select_related("user").all()
    status_filter = request.GET.get("status")
    search = request.GET.get("q", "").strip()
    if status_filter:
        queryset = queryset.filter(status=status_filter)
    if search:
        queryset = queryset.filter(Q(user__email__icontains=search) | Q(user__username__icontains=search) | Q(seller_id__icontains=search))

    entries = []
    for app in queryset:
        metrics = _seller_summary_for_user(app.user)
        entries.append({
            "application": app,
            "metrics": metrics,
        })

    return render(request, "sellers/owner_seller_list.html", {"entries": entries, "status_filter": status_filter, "search": search})


@login_required
def owner_seller_detail(request, user_id):
    forbidden = _require_marketplace_owner(request)
    if forbidden is not None:
        return forbidden

    user = get_object_or_404(CustomUser, pk=user_id)
    app = SellerApplication.objects.filter(user=user).first()
    if app is None:
        app = SellerApplication.objects.create(user=user, email=user.email, status="approved" if user.is_vendor else "draft")

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    item_qs = OrderItem.objects.filter(product__seller=user).select_related("order", "product", "product__category")
    if start_date:
        item_qs = item_qs.filter(order__created_at__date__gte=start_date)
    if end_date:
        item_qs = item_qs.filter(order__created_at__date__lte=end_date)

    metrics = _order_item_metric_summary(item_qs)
    products = Product.objects.filter(seller=user).select_related("category", "inventory")
    return render(request, "sellers/owner_seller_detail.html", {
        "seller": user,
        "application": app,
        "products": products,
        "metrics": metrics,
        "start_date": start_date,
        "end_date": end_date,
    })


@login_required
def owner_seller_action(request, user_id):
    forbidden = _require_marketplace_owner(request)
    if forbidden is not None:
        return forbidden

    if request.method != "POST":
        return redirect("sellers:owner_seller_list")

    user = get_object_or_404(CustomUser, pk=user_id)
    app = SellerApplication.objects.filter(user=user).first()
    action = request.POST.get("action")
    review_notes = request.POST.get("review_notes", "")

    if action == "approve":
        if app is None:
            app = SellerApplication.objects.create(user=user, email=user.email)
        app.approve_application(request.user, review_notes)
    elif action == "reject":
        if app is None:
            app = SellerApplication.objects.create(user=user, email=user.email)
        app.reject_application(request.user, review_notes)
    elif action == "suspend":
        if app is None:
            app = SellerApplication.objects.create(user=user, email=user.email)
        app.suspend_application(request.user, review_notes)
    elif action == "reactivate":
        if app is None:
            app = SellerApplication.objects.create(user=user, email=user.email)
        app.reactivate_application(request.user, review_notes)
        user.is_vendor = True
        user.save(update_fields=["is_vendor", "updated_at"])
    elif action == "resend_activation":
        if app is None:
            app = SellerApplication.objects.create(user=user, email=user.email)
        token = app.generate_activation_token()
        app.activation_email_sent_at = timezone.now()
        app.save(update_fields=["activation_email_sent_at", "updated_at"])
        send_mail(
            "Seller activation reminder",
            f"Your seller activation link is ready:\n\n{settings.SITE_URL}/sellers/activate/{token}/",
            settings.DEFAULT_FROM_EMAIL,
            [app.email],
            fail_silently=True,
        )

    return redirect("sellers:owner_seller_detail", user_id=user.pk)


@login_required
def owner_top_sellers(request):
    forbidden = _require_marketplace_owner(request)
    if forbidden is not None:
        return forbidden

    sort = request.GET.get("sort", "highest_revenue")
    sellers = []
    for user in CustomUser.objects.filter(is_vendor=True).select_related("seller_application"):
        metrics = _seller_summary_for_user(user)
        sellers.append({
            "seller": user,
            "seller_display_name": (user.get_full_name() or user.username.replace("-", " ").title()),
            "metrics": metrics,
        })

    if sort == "most_units_sold":
        sellers.sort(key=lambda entry: (-entry["metrics"]["units_sold"], -entry["metrics"]["gross_sales"], entry["seller"].email.lower()))
    elif sort == "most_orders":
        sellers.sort(key=lambda entry: (-OrderItem.objects.filter(product__seller=entry["seller"]).values_list("order_id", flat=True).distinct().count(), -entry["metrics"]["gross_sales"], entry["seller"].email.lower()))
    elif sort == "most_active_products":
        sellers.sort(key=lambda entry: (-entry["metrics"]["active_products"], -entry["metrics"]["gross_sales"], entry["seller"].email.lower()))
    else:
        sellers.sort(key=lambda entry: (-entry["metrics"]["gross_sales"], -entry["metrics"]["units_sold"], entry["seller"].email.lower()))

    return render(request, "sellers/owner_top_sellers.html", {"sellers": sellers[:10], "sort": sort})


@login_required
def product_list(request):
    app, redirect_response = _get_approved_seller_application(request)
    if redirect_response is not None:
        return redirect_response

    products = (
        Product.objects.filter(seller=request.user)
        .select_related("category", "subcategory", "inventory")
        .prefetch_related("images")
        .order_by("-updated_at", "-id")
    )
    return render(request, "sellers/product_list.html", {"products": products, "application": app})


@login_required
def product_create(request):
    app, redirect_response = _get_approved_seller_application(request)
    if redirect_response is not None:
        return redirect_response

    if request.method == "POST":
        form = SellerProductForm(request.POST, request.FILES)
        category_id = request.POST.get("category")
        if not _category_allowed_for_seller(app, category_id):
            form.add_error("category", "This category is not approved for your seller account.")
        if form.is_valid():
            product = form.save(seller=request.user)
            messages.success(request, "Product created successfully.")
            return redirect("sellers:product_edit", product.pk)
    else:
        form = SellerProductForm()

    return render(request, "sellers/product_form.html", {"form": form, "application": app, "is_edit": False})


@login_required
def product_edit(request, pk):
    app, redirect_response = _get_approved_seller_application(request)
    if redirect_response is not None:
        return redirect_response

    product, forbidden = _get_owned_product_or_403(request, pk)
    if forbidden is not None:
        return forbidden

    if request.method == "POST":
        form = SellerProductForm(request.POST, request.FILES, instance=product)
        category_id = request.POST.get("category")
        if not _category_allowed_for_seller(app, category_id):
            form.add_error("category", "This category is not approved for your seller account.")
        if form.is_valid():
            form.save(seller=request.user)
            messages.success(request, "Product updated successfully.")
            return redirect("sellers:product_edit", product.pk)
    else:
        form = SellerProductForm(instance=product)

    return render(request, "sellers/product_form.html", {"form": form, "product": product, "application": app, "is_edit": True})


@login_required
def product_delete(request, pk):
    app, redirect_response = _get_approved_seller_application(request)
    if redirect_response is not None:
        return redirect_response

    product, forbidden = _get_owned_product_or_403(request, pk)
    if forbidden is not None:
        return forbidden
    if request.method == "POST":
        product.delete()
        messages.success(request, "Product deleted.")
        return redirect("sellers:product_list")
    return render(request, "sellers/product_delete.html", {"product": product, "application": app})


@login_required
def product_toggle_active(request, pk):
    app, redirect_response = _get_approved_seller_application(request)
    if redirect_response is not None:
        return redirect_response

    product, forbidden = _get_owned_product_or_403(request, pk)
    if forbidden is not None:
        return forbidden
    product.is_active = not product.is_active
    product.save(update_fields=["is_active", "updated_at"])
    messages.success(request, "Product visibility updated.")
    return redirect("sellers:product_edit", product.pk)


@login_required
def dashboard(request):
    app, redirect_response = _get_approved_seller_application(request)
    if redirect_response is not None:
        return redirect_response

    seller_products = Product.objects.filter(seller=request.user).select_related("category", "inventory")
    seller_items = _seller_order_items_queryset(request)
    order_ids = seller_items.values_list("order_id", flat=True).distinct()
    seller_orders = Order.objects.filter(id__in=order_ids)

    total_products = seller_products.count()
    active_products = seller_products.filter(is_active=True).count()
    inactive_products = seller_products.filter(is_active=False).count()
    total_units_sold = seller_items.aggregate(total_units=Coalesce(Sum("quantity"), 0))["total_units"]
    online_paid_amount = seller_items.filter(order__is_paid=True, order__payment_method__in=["razorpay", "netbanking", "upi", "wallet"]).aggregate(amount=Coalesce(Sum(F("price") * F("quantity"), output_field=None), Decimal("0.00")))["amount"]
    total_sales = online_paid_amount
    cod_amount = seller_items.filter(order__payment_method="cod").aggregate(amount=Coalesce(Sum(F("price") * F("quantity"), output_field=None), Decimal("0.00")))["amount"]
    pending_amount = seller_items.filter(order__is_paid=False).exclude(order__payment_method="cod").aggregate(amount=Coalesce(Sum(F("price") * F("quantity"), output_field=None), Decimal("0.00")))["amount"]

    metrics = {
        "total_products": total_products,
        "active_products": active_products,
        "inactive_products": inactive_products,
        "total_units_sold": total_units_sold,
        "total_seller_sales": total_sales,
        "online_paid_amount": online_paid_amount,
        "cod_amount": cod_amount,
        "pending_unpaid_amount": pending_amount,
        "pending_orders": seller_orders.filter(status="pending").count(),
        "processing_orders": seller_orders.filter(status__in=["pending_verification", "paid"]).count(),
        "shipped_orders": seller_orders.filter(status="shipped").count(),
        "delivered_orders": seller_orders.filter(status="completed").count(),
        "cancelled_orders": seller_orders.filter(status="cancelled").count(),
    }

    return render(request, "sellers/dashboard.html", {"application": app, "metrics": metrics})


@login_required
def orders_list(request):
    app, redirect_response = _get_approved_seller_application(request)
    if redirect_response is not None:
        return redirect_response

    items = _seller_order_items_queryset(request)

    start_date = request.GET.get("start_date")
    end_date = request.GET.get("end_date")
    payment_method = request.GET.get("payment_method")
    order_status = request.GET.get("order_status")
    payment_status = request.GET.get("payment_status")
    fulfillment_status = request.GET.get("fulfillment_status")

    if start_date:
        items = items.filter(order__created_at__date__gte=start_date)
    if end_date:
        items = items.filter(order__created_at__date__lte=end_date)
    if payment_method:
        items = items.filter(order__payment_method=payment_method)
    if order_status:
        items = items.filter(order__status=order_status)
    if fulfillment_status:
        items = items.filter(fulfillment_status=fulfillment_status)
    if payment_status == "paid":
        items = items.filter(order__is_paid=True).exclude(order__payment_method="cod")
    elif payment_status == "cod":
        items = items.filter(order__payment_method="cod")
    elif payment_status == "pending":
        items = items.filter(order__is_paid=False).exclude(order__payment_method="cod")

    items = items.order_by("-order__created_at", "-id")
    return render(request, "sellers/orders_list.html", {"application": app, "items": items, "filters": {"payment_method": payment_method, "order_status": order_status, "payment_status": payment_status, "fulfillment_status": fulfillment_status, "start_date": start_date, "end_date": end_date}})


@login_required
def order_item_detail(request, item_id):
    app, redirect_response = _get_approved_seller_application(request)
    if redirect_response is not None:
        return redirect_response

    item, forbidden = _get_seller_order_item_or_403(request, item_id)
    if forbidden is not None:
        return forbidden
    return render(request, "sellers/order_detail.html", {"application": app, "item": item})


@login_required
def order_item_status(request, item_id):
    app, redirect_response = _get_approved_seller_application(request)
    if redirect_response is not None:
        return redirect_response

    item, forbidden = _get_seller_order_item_or_403(request, item_id)
    if forbidden is not None:
        return forbidden
    if request.method == "POST":
        new_status = request.POST.get("fulfillment_status")
        if new_status in dict(item.FULFILLMENT_STATUS_CHOICES):
            item.fulfillment_status = new_status
            item.save(update_fields=["fulfillment_status"])
            messages.success(request, "Order status updated.")
        else:
            messages.error(request, "Invalid fulfillment status.")
        return redirect("sellers:order_item_detail", item_id=item.pk)
    return redirect("sellers:order_item_detail", item_id=item.pk)


@login_required
def reports(request):
    app, redirect_response = _get_approved_seller_application(request)
    if redirect_response is not None:
        return redirect_response

    items = _seller_order_items_queryset(request)
    now = timezone.now()
    start = now.date()
    periods = {}

    periods["today"] = items.filter(order__created_at__date=start)
    periods["this_week"] = items.filter(order__created_at__date__gte=(start - timedelta(days=7)))
    periods["this_month"] = items.filter(order__created_at__date__gte=(start.replace(day=1)))
    periods["all_time"] = items

    summary = {}
    for key, queryset in periods.items():
        summary[key] = {
            "total_orders": queryset.values_list("order_id", flat=True).distinct().count(),
            "total_units_sold": queryset.aggregate(total_units=Coalesce(Sum("quantity"), 0))["total_units"],
            "gross_sales": queryset.aggregate(total=Coalesce(Sum(F("price") * F("quantity"), output_field=None), Decimal("0.00")))["total"],
            "online_paid": queryset.filter(order__is_paid=True, order__payment_method__in=["razorpay", "netbanking", "upi", "wallet"]).aggregate(total=Coalesce(Sum(F("price") * F("quantity"), output_field=None), Decimal("0.00")))["total"],
            "cod": queryset.filter(order__payment_method="cod").aggregate(total=Coalesce(Sum(F("price") * F("quantity"), output_field=None), Decimal("0.00")))["total"],
            "pending_amount": queryset.filter(order__is_paid=False).exclude(order__payment_method="cod").aggregate(total=Coalesce(Sum(F("price") * F("quantity"), output_field=None), Decimal("0.00")))["total"],
        }

    return render(request, "sellers/reports.html", {"application": app, "summary": summary})


@login_required
def product_performance(request):
    app, redirect_response = _get_approved_seller_application(request)
    if redirect_response is not None:
        return redirect_response

    products = Product.objects.filter(seller=request.user).select_related("category", "inventory")
    sort = request.GET.get("sort", "most_sold")

    performance = []
    for product in products:
        product_items = OrderItem.objects.filter(product=product)
        units_sold = product_items.aggregate(total_units=Coalesce(Sum("quantity"), 0))["total_units"]
        total_sales = product_items.aggregate(total=Coalesce(Sum(F("price") * F("quantity"), output_field=None), Decimal("0.00")))["total"]
        online_paid_amount = product_items.filter(order__is_paid=True, order__payment_method__in=["razorpay", "netbanking", "upi", "wallet"]).aggregate(total=Coalesce(Sum(F("price") * F("quantity"), output_field=None), Decimal("0.00")))["total"]
        cod_amount = product_items.filter(order__payment_method="cod").aggregate(total=Coalesce(Sum(F("price") * F("quantity"), output_field=None), Decimal("0.00")))["total"]
        pending_amount = product_items.filter(order__is_paid=False).exclude(order__payment_method="cod").aggregate(total=Coalesce(Sum(F("price") * F("quantity"), output_field=None), Decimal("0.00")))["total"]
        stock = getattr(product, "inventory", None)
        current_stock = stock.stock_quantity if stock else 0
        performance.append({
            "product": product,
            "units_sold": units_sold,
            "total_sales": total_sales,
            "online_paid_amount": online_paid_amount,
            "cod_amount": cod_amount,
            "pending_amount": pending_amount,
            "current_stock": current_stock,
        })

    sort_options = {
        "most_sold": lambda item: (-item["units_sold"], -item["total_sales"], item["product"].name.lower()),
        "highest_revenue": lambda item: (-item["total_sales"], -item["units_sold"], item["product"].name.lower()),
        "lowest_stock": lambda item: (item["current_stock"], item["product"].name.lower()),
        "newest": lambda item: (-item["product"].id, item["product"].name.lower()),
    }
    performance.sort(key=sort_options.get(sort, sort_options["most_sold"]))

    return render(request, "sellers/product_performance.html", {"application": app, "performance": performance, "sort": sort})
