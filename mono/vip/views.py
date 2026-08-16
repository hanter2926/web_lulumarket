from decimal import Decimal, InvalidOperation
from datetime import timedelta
from django.core.mail import send_mail
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

# Local imports
from .models import Product, Category, SubCategory, Color, Brand, Size, CartItem, Order, Wishlist, Address, Coupon, Wallet, Slider
from .forms import UserRegistrationForm, UserLoginForm, UserProfileForm, AddressForm, ContactSubmissionForm
from .utlis import send_order_confirmation, calculate_and_add_coins, spend_coins_for_order

try:
    import razorpay
except ImportError:
    razorpay = None


def _get_valid_coupon(code):
    code = (code or '').strip()
    if not code:
        return None
    return Coupon.objects.filter(
        code__iexact=code,
        active=True,
        valid_to__gte=timezone.now()
    ).first()


def _calculate_discount(total, coupon):
    if not coupon:
        return Decimal('0.00')
    if coupon.discount_percentage:
        return (total * coupon.discount_percentage / Decimal('100')).quantize(Decimal('0.01'))
    return min(coupon.discount_amount or Decimal('0.00'), total)


def _requested_quantity(value, default=1):
    try:
        quantity = int(value)
    except (TypeError, ValueError, InvalidOperation):
        return default
    return max(quantity, 1)


def _requested_coins(value, default=0):
    try:
        coins = int(value)
    except (TypeError, ValueError):
        return default
    return max(coins, 0)


def _wallet_coins(user):
    return Wallet.objects.filter(user=user).values_list('coins', flat=True).first() or 0


def index(request):
    """Home page view"""
    products = Product.objects.all().order_by('-id')[:8]
    slides = Slider.objects.filter(is_active=True).order_by('display_order')
    context = {'products': products, 'slides': slides}
    return render(request, 'lulumarket/index.html', context)

def about(request):
    """About Us page"""
    return render(request, 'lulumarket/about.html')

def contact(request):
    """Contact Us page"""
    form = ContactSubmissionForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            messages.success(request, "Aapka message bhej diya gaya hai!")
            return redirect('contact')
        messages.error(request, "Please correct the errors below.")
    return render(request, 'lulumarket/contact.html', {'form': form})

def faq(request):
    """Frequently Asked Questions"""
    return render(request, 'lulumarket/faq.html')

def search(request):
    """Search functionality for products"""
    query = request.GET.get('q', '')
    products = Product.objects.filter(
        Q(name__icontains=query) | Q(description__icontains=query)
    )
    context = {'query': query, 'products': products}
    return render(request, 'lulumarket/search.html', context)

def products(request):
    """All products listing page"""
    query = request.GET.get('q', '').strip()
    product_list = Product.objects.all().order_by('-id')
    if query:
        product_list = product_list.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
    paginator = Paginator(product_list, 9)

    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'lulumarket/products.html', {'page_obj': page_obj})

def product_detail(request, pk):
    """Single product view page"""
    product = get_object_or_404(Product, pk=pk)
    return render(request, 'lulumarket/product_detail.html', {'product': product})

def category_products(request, slug):
    """Products filtered by category"""
    category = get_object_or_404(Category, slug=slug)
    products = Product.objects.filter(category=category)
    context = {'products': products, 'category': category}
    return render(request, 'lulumarket/products.html', context)

def subcategory_products(request, slug):
    """Products filtered by subcategory"""
    subcategory = get_object_or_404(SubCategory, slug=slug)
    products = Product.objects.filter(subcategory=subcategory)
    context = {'products': products, 'subcategory': subcategory}
    return render(request, 'lulumarket/products.html', context)

def brand_products(request, slug):
    """Products filtered by brand"""
    brand = get_object_or_404(Brand, slug=slug)
    products = Product.objects.filter(brand=brand)
    context = {'products': products, 'brand': brand}
    return render(request, 'lulumarket/products.html', context)

def color_products(request, slug):
    """Products filtered by color"""
    color = get_object_or_404(Color, slug=slug)
    products = Product.objects.filter(color=color)
    context = {'products': products, 'color': color}
    return render(request, 'lulumarket/products.html', context)

def size_products(request, slug):
    """Products filtered by size"""
    size = get_object_or_404(Size, slug=slug)
    products = Product.objects.filter(size=size)
    context = {'products': products, 'size': size}
    return render(request, 'lulumarket/products.html', context)

def price_range(request):
    """Products filtered by price range"""
    try:
        min_price = Decimal(request.GET.get('min', '0'))
    except (TypeError, ValueError, InvalidOperation):
        min_price = Decimal('0')
    try:
        max_price = Decimal(request.GET.get('max', '100000'))
    except (TypeError, ValueError, InvalidOperation):
        max_price = Decimal('100000')
    if min_price > max_price:
        min_price, max_price = max_price, min_price
    products = Product.objects.filter(price__gte=min_price, price__lte=max_price)
    context = {'products': products, 'min_price': min_price, 'max_price': max_price}
    return render(request, 'lulumarket/products.html', context)

@login_required
def wishlist(request):
    """User wishlist page"""
    wishlist, created = Wishlist.objects.get_or_create(user=request.user)
    return render(request, 'lulumarket/wishlist.html', {'wishlist': wishlist})

@login_required
@require_POST
def add_to_wishlist(request, pk):
    """Add product to user's wishlist"""
    product = get_object_or_404(Product, pk=pk)
    wishlist, created = Wishlist.objects.get_or_create(user=request.user)
    wishlist.products.add(product)
    messages.success(request, "Product wishlist me add kar diya gaya hai.")
    return redirect('wishlist')

@login_required
@require_POST
def remove_from_wishlist(request, pk):
    """Remove product from user's wishlist"""
    product = get_object_or_404(Product, pk=pk)
    wishlist = get_object_or_404(Wishlist, user=request.user)
    wishlist.products.remove(product)
    messages.success(request, "Product wishlist se hata diya gaya hai.")
    return redirect('wishlist')

def cart(request):
    """View shopping cart"""
    cart_items = []
    total_price = 0
    coupon_code = request.session.get('checkout_coupon_code', '')
    if request.user.is_authenticated:
        cart_items = CartItem.objects.filter(user=request.user)
        total_price = sum(item.get_total() for item in cart_items)
    return render(request, 'lulumarket/cart.html', {
        'cart_items': cart_items,
        'total_price': total_price,
        'coupon_code': coupon_code,
    })

@login_required
def add_to_cart(request, pk):
    """Add product to cart"""
    product = get_object_or_404(Product, pk=pk)
    quantity = _requested_quantity(request.POST.get('quantity', 1))
    if product.stock_quantity < quantity:
        messages.error(request, 'Requested quantity is not available.')
        return redirect('product_detail', pk=product.pk)
    
    cart_item, created = CartItem.objects.get_or_create(
        user=request.user, 
        product=product
    )
    
    if not created:
        cart_item.quantity += quantity
    else:
        cart_item.quantity = quantity
    
    if cart_item.quantity > product.stock_quantity:
        cart_item.quantity = product.stock_quantity
    if cart_item.quantity < 1:
        messages.error(request, 'This product is out of stock.')
        return redirect('product_detail', pk=product.pk)
    cart_item.save()
    messages.success(request, "Product cart me add ho gaya!")
    return redirect('cart')

@login_required
def buy_now(request, pk):
    """Add one product to the cart and go directly to checkout."""
    product = get_object_or_404(Product, pk=pk)
    quantity = _requested_quantity(request.POST.get('quantity', 1))
    if product.stock_quantity < quantity:
        messages.error(request, 'Requested quantity is not available.')
        return redirect('product_detail', pk=product.pk)

    # Treat Buy Now as a single-product checkout path.
    CartItem.objects.filter(user=request.user).exclude(product=product).delete()
    cart_item, created = CartItem.objects.get_or_create(
        user=request.user,
        product=product
    )
    cart_item.quantity = quantity
    cart_item.save()
    request.session.pop('checkout_order_id', None)
    return redirect('checkout')

@login_required
@require_POST
def remove_from_cart(request, pk):
    """Remove product from cart"""
    cart_item = get_object_or_404(CartItem, pk=pk, user=request.user)
    cart_item.delete()
    messages.info(request, "Product cart se hata diya gaya hai.")
    return redirect('cart')

@login_required
@require_POST
def update_cart(request, pk):
    """Update item quantity in cart"""
    cart_item = get_object_or_404(CartItem, pk=pk, user=request.user)
    quantity = _requested_quantity(request.POST.get('quantity', 1), default=0)
    quantity = min(quantity, cart_item.product.stock_quantity)
    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
        messages.success(request, "Cart updated successfully.")
    else:
        cart_item.delete()
        messages.info(request, "Product cart se hata diya gaya hai.")
    return redirect('cart')

@login_required
def order_history(request):
    """List of all orders placed by the logged-in user"""
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'lulumarket/orders.html', {'orders': orders})

@login_required
def order_detail(request, pk):
    """Single order detail page"""
    order = get_object_or_404(Order, pk=pk, user=request.user)
    return render(request, 'lulumarket/order_detail.html', {'order': order})

@login_required
@require_POST
def cancel_order(request, pk):
    """Allow a user to cancel an order before it is delivered."""
    order = get_object_or_404(Order, pk=pk, user=request.user)
    if order.status in ['Delivered', 'Cancelled']:
        messages.warning(request, 'Yeh order ab cancel nahi ho sakta.')
    else:
        order.status = 'Cancelled'
        order.payment_status = 'Pending' if order.payment_method == 'COD' else order.payment_status
        order.cancelled_at = timezone.now()
        order.save(update_fields=['status', 'payment_status', 'cancelled_at'])
        messages.success(request, 'Aapka order cancel kar diya gaya hai.')
    return redirect('order_history')

def payment_success(request):
    """Payment success landing page"""
    return render(request, 'lulumarket/payment_success.html')

def payment_error(request):
    """Payment failed / canceled landing page"""
    return render(request, 'lulumarket/payment_error.html')


def terms(request):
    return render(request, 'lulumarket/terms.html')


def privacy(request):
    return render(request, 'lulumarket/privacy.html')


@login_required
def payment(request):
    return redirect('checkout')


@csrf_exempt
def payment_callback(request):
    return payment_success_view(request)


@login_required
def razorpay_payment(request):
    return redirect('checkout')


def login_view(request):
    """User login view"""
    if request.user.is_authenticated:
        return redirect('profile')
    if request.method == 'POST':
        form = UserLoginForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, f"Welcome back, {username}!")
                next_url = request.POST.get('next', '')
                if next_url and url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
                    return redirect(next_url)
                return redirect('profile')
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = UserLoginForm()
    return render(request, 'lulumarket/login.html', {'form': form, 'next': request.GET.get('next', '')})

def register(request):
    """User registration view"""
    if request.user.is_authenticated:
        return redirect('profile')
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            # Flag the session to show the account-created popup on the next page load
            request.session['show_account_popup'] = True
            messages.success(request, "Registration successful. Welcome!")
            return redirect('home')
    else:
        form = UserRegistrationForm()
    return render(request, 'lulumarket/register.html', {'form': form})

@require_POST
def logout_user(request):
    """Logout current user"""
    logout(request)
    messages.info(request, "Aap successful logout ho chuke hain.")
    return redirect('home')

@login_required
def profile(request):
    """User account profile page"""
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Aapka profile update ho gaya hai.')
            return redirect('profile')
    else:
        form = UserProfileForm(instance=request.user)
    
    return render(request, 'lulumarket/profile.html', {'form': form})

@login_required
def add_address(request):
    """Save a new shipping address for the current user."""
    if request.method == 'POST':
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()
            messages.success(request, 'Address added successfully.')
            return redirect('checkout')
    else:
        form = AddressForm()
    return render(request, 'lulumarket/add_address.html', {'form': form})


# Initialize Razorpay Client
razorpay_client = None
if razorpay and settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET:
    razorpay_client = razorpay.Client(
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    )

@login_required
def checkout_view(request):
    cart_items = CartItem.objects.filter(user=request.user)
    if not cart_items.exists():
        messages.error(request, "Aapka cart khaali hai.")
        return redirect('cart')

    subtotal = sum(item.get_total() for item in cart_items)
    coupon_code = request.session.get('checkout_coupon_code', '')
    coupon = _get_valid_coupon(coupon_code)
    discount_amount = _calculate_discount(subtotal, coupon)
    discounted_total = max(subtotal - discount_amount, Decimal('0.00'))
    coins_to_use = _requested_coins(request.session.get('checkout_coins', 0))
    if coins_to_use > _wallet_coins(request.user) or coins_to_use > discounted_total:
        coins_to_use = 0
        request.session.pop('checkout_coins', None)
    total_price = discounted_total - coins_to_use
    default_payment_method = 'RAZORPAY' if razorpay_client else 'COD'
    payment_method = request.POST.get(
        'payment_method',
        request.session.get('checkout_payment_method', default_payment_method),
    )
    payment_method = payment_method.strip().upper() if payment_method else 'RAZORPAY'

    if request.method == 'POST':
        if request.POST.get('apply_coupon'):
            coupon_code = request.POST.get('coupon_code', '').strip()
            coupon = _get_valid_coupon(coupon_code)
            if coupon:
                request.session['checkout_coupon_code'] = coupon_code
                messages.success(request, "Coupon code applied successfully.")
            else:
                request.session.pop('checkout_coupon_code', None)
                messages.error(request, "Invalid or expired coupon code.")
            return redirect('checkout')

        payment_method = request.POST.get('payment_method', payment_method)
        payment_method = payment_method.strip().upper() if payment_method else 'RAZORPAY'
        if payment_method == 'RAZORPAY' and razorpay_client is None:
            messages.error(request, 'Online payment is not configured. Please use Cash on Delivery.')
            payment_method = 'COD'
        request.session['checkout_payment_method'] = payment_method
        coupon_code = request.POST.get('coupon_code', coupon_code).strip()
        coupon = _get_valid_coupon(coupon_code)
        discount_amount = _calculate_discount(subtotal, coupon)
        discounted_total = max(subtotal - discount_amount, Decimal('0.00'))
        coins_to_use = _requested_coins(request.POST.get('coins_to_use', 0))
        if coins_to_use > _wallet_coins(request.user) or coins_to_use > discounted_total:
            messages.error(request, 'Invalid or insufficient wallet coins.')
            return redirect('checkout')
        request.session['checkout_coins'] = coins_to_use
        total_price = discounted_total - coins_to_use

        place_order_value = request.POST.get('place_order', '').strip().upper()
        if place_order_value == 'COD' or payment_method == 'COD':
            address = None
            address_id = request.POST.get('customer_address')
            if address_id:
                address = Address.objects.filter(id=address_id, user=request.user).first()

            try:
                with transaction.atomic():
                    order = Order.objects.create(
                        user=request.user,
                        address=address,
                        coupon=coupon,
                        payment_method='COD',
                        payment_status='Pending',
                        status='Placed',
                        total=total_price,
                        discount_amount=discount_amount,
                        coins_used=coins_to_use,
                        estimated_delivery=timezone.now() + timedelta(days=5),
                    )
                    for item in cart_items:
                        order.items.create(
                            product=item.product,
                            quantity=item.quantity,
                            price=item.product.price
                        )
                    spend_coins_for_order(order)
            except (Wallet.DoesNotExist, ValueError):
                messages.error(request, 'Your wallet balance changed. Please try again.')
                return redirect('checkout')

            CartItem.objects.filter(user=request.user).delete()
            request.session.pop('checkout_order_id', None)
            request.session.pop('checkout_coupon_code', None)
            request.session.pop('checkout_payment_method', None)
            request.session.pop('checkout_coins', None)
            calculate_and_add_coins(order.user, order.total)
            send_order_confirmation(order.user.email, order.id, order.total)
            return render(request, 'lulumarket/payment_success.html', {'order': order})

    if coupon is None and coupon_code:
        request.session.pop('checkout_coupon_code', None)
        coupon_code = ''
        coupon = None
        discount_amount = Decimal('0.00')
        total_price = subtotal
        coins_to_use = 0

    checkout_order_id = request.session.get('checkout_order_id')
    order = None
    if checkout_order_id:
        try:
            order = Order.objects.get(id=checkout_order_id, user=request.user, payment_status='Pending')
        except Order.DoesNotExist:
            order = None

    if payment_method == 'RAZORPAY' and not order:
        order = Order.objects.create(
            user=request.user,
            total=total_price,
            discount_amount=discount_amount,
            coupon=coupon,
            payment_method='RAZORPAY',
            status='Placed',
            payment_status='Pending',
            coins_used=coins_to_use,
            estimated_delivery=timezone.now() + timedelta(days=5),
        )
        for item in cart_items:
            order.items.create(
                product=item.product,
                quantity=item.quantity,
                price=item.product.price
            )
        request.session['checkout_order_id'] = order.id
    elif payment_method == 'RAZORPAY' and order:
        coins_changed = order.coins_used != coins_to_use
        order.total = total_price
        order.discount_amount = discount_amount
        order.coupon = coupon
        order.coins_used = coins_to_use
        order.payment_method = 'RAZORPAY'
        order.status = 'Placed'
        if not order.estimated_delivery:
            order.estimated_delivery = timezone.now() + timedelta(days=5)
        if coins_changed:
            order.razorpay_order_id = None
        order.save(update_fields=['total', 'discount_amount', 'coupon', 'coins_used', 'payment_method', 'status', 'estimated_delivery', 'razorpay_order_id'])
        order.items.all().delete()
        for item in cart_items:
            order.items.create(
                product=item.product,
                quantity=item.quantity,
                price=item.product.price
            )

    amount_in_paise = int(total_price * 100) 
    if payment_method == 'RAZORPAY' and razorpay_client:
        if not order.razorpay_order_id or order.total != total_price:
            try:
                razorpay_order = razorpay_client.order.create({
                    'amount': amount_in_paise,
                    'currency': 'INR',
                    'payment_capture': '1'
                })
            except (
                razorpay.errors.BadRequestError,
                razorpay.errors.GatewayError,
                razorpay.errors.ServerError,
            ):
                messages.error(request, 'Online payment is temporarily unavailable. Please try Cash on Delivery.')
                return render(request, 'lulumarket/payment_error.html')
            order.razorpay_order_id = razorpay_order['id']
            order.save(update_fields=['razorpay_order_id'])
    elif order:
        order.razorpay_order_id = None
        order.save(update_fields=['razorpay_order_id'])

    addresses = Address.objects.filter(user=request.user)
    context = {
        'razorpay_order_id': order.razorpay_order_id if order else None,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
        'amount': total_price,
        'amount_in_paise': amount_in_paise,
        'subtotal': subtotal,
        'discount_amount': discount_amount,
        'coins_to_use': coins_to_use,
        'wallet_coins': _wallet_coins(request.user),
        'coupon_code': coupon_code,
        'payment_method': payment_method,
        'order': order,
        'addresses': addresses,
        'cart_items': cart_items,
    }
    return render(request, 'lulumarket/checkout.html', context)


@csrf_exempt
def payment_success_view(request):
    if not razorpay_client:
        messages.error(request, 'Online payment is not configured.')
        return render(request, 'lulumarket/payment_error.html')
    if request.method == "POST":
        payment_id = request.POST.get('razorpay_payment_id')
        order_id = request.POST.get('razorpay_order_id')
        signature = request.POST.get('razorpay_signature')

        params_dict = {
            'razorpay_order_id': order_id,
            'razorpay_payment_id': payment_id,
            'razorpay_signature': signature
        }

        try:
            razorpay_client.utility.verify_payment_signature(params_dict)

            try:
                with transaction.atomic():
                    order = Order.objects.select_for_update().get(razorpay_order_id=order_id)
                    if order.payment_status == 'Paid':
                        return render(request, 'lulumarket/payment_success.html', {'order': order})
                    if order.payment_status != 'Pending':
                        messages.error(request, 'This order is not payable.')
                        return render(request, 'lulumarket/payment_error.html')
                    spend_coins_for_order(order)
                    order.razorpay_payment_id = payment_id
                    order.razorpay_signature = signature
                    order.payment_status = 'Paid'
                    order.status = 'Processing'
                    order.save(update_fields=[
                        'razorpay_payment_id', 'razorpay_signature',
                        'payment_status', 'status',
                    ])
            except Order.DoesNotExist:
                messages.error(request, "Order not found.")
                return render(request, 'lulumarket/payment_error.html')
            except (Wallet.DoesNotExist, ValueError):
                messages.error(request, 'Your wallet balance is insufficient for this payment.')
                return render(request, 'lulumarket/payment_error.html')

            # Clear the cart
            CartItem.objects.filter(user=order.user).delete()

            # Clear the checkout session
            for key in ['checkout_order_id', 'checkout_coupon_code', 'checkout_payment_method']:
                if key in request.session:
                    del request.session[key]

            request.session.pop('checkout_coins', None)
            calculate_and_add_coins(order.user, order.total)

            # Send confirmation email
            send_order_confirmation(order.user.email, order.id, order.total)

            return render(request, 'lulumarket/payment_success.html', {'order': order})
        except razorpay.errors.SignatureVerificationError:
            messages.error(request, "Payment signature verification failed.")
            return render(request, 'lulumarket/payment_error.html')

    return redirect('home')
