from django.contrib import messages
from django.db.models import Count
from django.shortcuts import redirect, render, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.http import require_POST

from products.models import Product, Category
from orders.models import Order
from accounts.decorators import owner_required
from .forms import ContactSupportForm, HomeSliderForm
from .models import HomeSlider
import logging

logger = logging.getLogger(__name__)


def home(request):
    """Home page view with featured products, bestsellers, new arrivals, and promotional sliders."""
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
    
    # Get active promotional sliders
    active_sliders = HomeSlider.get_active_sliders()

    # Temporary debug logging: report slider count and image URLs to help diagnose
    try:
        slider_count = active_sliders.count()
        logger.info('Home view: active sliders count=%s', slider_count)
        for s in active_sliders:
            img = getattr(s, 'image', None)
            mobile_img = getattr(s, 'mobile_image', None)
            logger.info('Slider id=%s title=%s image=%s mobile_image=%s', s.pk, s.title, getattr(img, 'url', None), getattr(mobile_img, 'url', None))
    except Exception:
        logger.exception('Error while logging slider info')
    
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
        'sliders': active_sliders,
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


# ============================================================================
# SLIDER MANAGEMENT VIEWS (OWNER-ONLY)
# ============================================================================

@owner_required
def slider_list(request):
    """List all sliders for owner management."""
    sliders = HomeSlider.objects.all().order_by('display_order', 'created_at')
    active_count = HomeSlider.objects.filter(is_active=True).count()
    can_add_active = active_count < 8
    
    context = {
        'sliders': sliders,
        'active_count': active_count,
        'can_add_active': can_add_active,
        'max_sliders': 8,
        'min_recommended': 3,
    }
    return render(request, 'sliders/slider_list.html', context)


@owner_required
def slider_add(request):
    """Add new slider."""
    if request.method == 'POST':
        form = HomeSliderForm(request.POST, request.FILES)
        if form.is_valid():
            slider = form.save()
            messages.success(request, f'Slider "{slider.title}" created successfully.')
            return redirect('slider_list')
    else:
        form = HomeSliderForm()
    
    active_count = HomeSlider.objects.filter(is_active=True).count()
    can_add_active = active_count < 8
    
    context = {
        'form': form,
        'page_title': 'Add New Slider',
        'can_add_active': can_add_active,
        'max_sliders': 8,
    }
    return render(request, 'sliders/slider_form.html', context)


@owner_required
def slider_edit(request, slider_id):
    """Edit existing slider."""
    slider = get_object_or_404(HomeSlider, pk=slider_id)
    
    if request.method == 'POST':
        form = HomeSliderForm(request.POST, request.FILES, instance=slider)
        if form.is_valid():
            form.save()
            messages.success(request, f'Slider "{slider.title}" updated successfully.')
            return redirect('slider_list')
    else:
        form = HomeSliderForm(instance=slider)
    
    active_count = HomeSlider.objects.filter(is_active=True).exclude(pk=slider_id).count()
    can_activate = active_count < 8
    
    context = {
        'form': form,
        'slider': slider,
        'page_title': f'Edit Slider: {slider.title}',
        'can_activate': can_activate or slider.is_active,  # Can always save if already active
        'max_sliders': 8,
    }
    return render(request, 'sliders/slider_form.html', context)


@owner_required
@require_POST
def slider_delete(request, slider_id):
    """Delete slider."""
    slider = get_object_or_404(HomeSlider, pk=slider_id)
    title = slider.title
    slider.delete()
    messages.success(request, f'Slider "{title}" deleted successfully.')
    return redirect('slider_list')


@owner_required
@require_POST
def slider_toggle(request, slider_id):
    """Toggle slider active/inactive status."""
    slider = get_object_or_404(HomeSlider, pk=slider_id)
    
    # Check if activating would exceed limit
    if not slider.is_active and HomeSlider.objects.filter(is_active=True).count() >= 8:
        messages.error(request, 'Cannot activate slider. Maximum 8 active sliders allowed.')
        return redirect('slider_list')
    
    slider.is_active = not slider.is_active
    slider.save(update_fields=['is_active', 'updated_at'])
    
    status = 'activated' if slider.is_active else 'deactivated'
    messages.success(request, f'Slider "{slider.title}" {status} successfully.')
    return redirect('slider_list')
