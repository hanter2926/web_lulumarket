from django.contrib import messages
from django.db.models import Count
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from products.models import Product, Category
from orders.models import Order
from .forms import ContactSupportForm


def home(request):
    """Home page view with featured products, bestsellers, and new arrivals."""
    featured_products = (
        Product.objects.filter(is_featured=True, is_active=True)
        .select_related("category")
        .only(
            "id",
            "name",
            "image",
            "price",
            "compare_price",
            "rating",
            "is_featured",
            "is_bestseller",
            "category__id",
            "category__name",
        )
        .order_by("-created_at")[:6]
    )
    bestseller_products = (
        Product.objects.filter(is_bestseller=True, is_active=True)
        .select_related("category")
        .only(
            "id",
            "name",
            "image",
            "price",
            "compare_price",
            "rating",
            "is_featured",
            "is_bestseller",
            "category__id",
            "category__name",
        )
        .order_by("-rating")[:6]
    )
    new_arrivals = (
        Product.objects.filter(is_active=True)
        .select_related("category")
        .only(
            "id",
            "name",
            "image",
            "price",
            "compare_price",
            "rating",
            "is_featured",
            "is_bestseller",
            "category__id",
            "category__name",
        )
        .order_by("-created_at")[:6]
    )
    top_rated_products = (
        Product.objects.filter(is_active=True)
        .select_related("category")
        .only(
            "id",
            "name",
            "image",
            "price",
            "compare_price",
            "rating",
            "is_featured",
            "is_bestseller",
            "category__id",
            "category__name",
        )
        .order_by("-rating")[:6]
    )
    categories = Category.objects.annotate(product_count=Count("products", distinct=True)).order_by("name")
    orders_count = 0
    if request.user.is_authenticated:
        orders_count = Order.objects.filter(user=request.user).count()

    context = {
        'featured_products': featured_products,
        'bestseller_products': bestseller_products,
        'new_arrivals': new_arrivals,
        'top_rated_products': top_rated_products,
        'categories': categories,
        'orders_count': orders_count,
    }
    return render(request, 'home/home.html', context)


def about_view(request):
    return render(request, 'home/about.html', {'title': 'About Nagri'})


@require_http_methods(["GET", "POST"])
def contact_view(request):
    form = ContactSupportForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Your message has been sent successfully. Our support team will respond shortly.')
        return redirect('contact')
    return render(request, 'support/contact_support.html', {'form': form, 'title': 'Contact Us'})


def privacy_policy(request):
    return render(request, 'policies/privacy_policy.html')


def terms_conditions(request):
    return render(request, 'policies/terms_conditions.html')


def refund_policy(request):
    return render(request, 'policies/refund_policy.html')


def shipping_policy(request):
    return render(request, 'policies/shipping_policy.html')


def return_policy(request):
    return render(request, 'policies/return_policy.html')


def cancellation_policy(request):
    return render(request, 'policies/cancellation_policy.html')


def help_center(request):
    return render(request, 'support/help_center.html')


def contact_support(request):
    form = ContactSupportForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Thank you! Your support request has been received.')
        return redirect('contact_support')
    return render(request, 'support/contact_support.html', {'form': form})
