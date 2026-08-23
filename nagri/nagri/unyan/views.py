from django.shortcuts import render
from products.models import Product, Category
from orders.models import Order


def home(request):
    """Home page view with featured products, bestsellers, and new arrivals."""
    # Get featured products
    featured_products = Product.objects.filter(is_featured=True, is_active=True).order_by('-created_at')[:6]
    
    # Get bestselling products
    bestseller_products = Product.objects.filter(is_bestseller=True, is_active=True).order_by('-rating')[:6]
    
    # Get new arrivals
    new_arrivals = Product.objects.filter(is_active=True).order_by('-created_at')[:6]
    
    # Get top rated products
    top_rated_products = Product.objects.filter(is_active=True).order_by('-rating')[:6]
    
    # Get all categories
    categories = Category.objects.all().order_by('name')
    
    # Get user's orders count if authenticated
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
