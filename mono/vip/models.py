from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator


class SiteSettings(models.Model):
    site_name = models.CharField(max_length=120, default='Lulumarket')
    logo = models.ImageField(upload_to='site/logo/', blank=True, null=True)
    favicon = models.ImageField(upload_to='site/favicon/', blank=True, null=True)
    default_image = models.ImageField(upload_to='site/default/', blank=True, null=True)
    hero_banner = models.ImageField(upload_to='site/hero/', blank=True, null=True)
    hero_background = models.ImageField(upload_to='site/backgrounds/', blank=True, null=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Site settings'
        verbose_name_plural = 'Site settings'
        ordering = ['-id']

    def __str__(self):
        return self.site_name or 'Lulumarket'

    @classmethod
    def get_active(cls):
        return cls.objects.filter(active=True).first() or cls(site_name='Lulumarket')


class Slider(models.Model):
    """Homepage slider/banner managed from admin."""
    SIZE_VALIDATOR = RegexValidator(r'^(auto|\d+(px|%))$', 'Enter a valid size like "100%", "450px" or "auto"')

    title = models.CharField(max_length=200, blank=True)
    subtitle = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='sliders/', blank=True, null=True)
    button_text = models.CharField(max_length=80, blank=True)
    button_url = models.URLField(blank=True)
    width = models.CharField(max_length=10, default='100%', validators=[SIZE_VALIDATOR])
    height = models.CharField(max_length=10, default='450px', validators=[SIZE_VALIDATOR])
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    auto_slide_seconds = models.PositiveIntegerField(default=5, help_text='Seconds before auto-advancing to next slide')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', '-created_at']
        verbose_name = 'Slider'
        verbose_name_plural = 'Sliders'

    def __str__(self):
        return self.title or f"Slide {self.pk}"


class Product(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.ForeignKey('Category', on_delete=models.CASCADE)
    subcategory = models.ForeignKey('SubCategory', on_delete=models.CASCADE, null=True, blank=True)
    brand = models.ForeignKey('Brand', on_delete=models.CASCADE, null=True, blank=True)
    color = models.ForeignKey('Color', on_delete=models.CASCADE, null=True, blank=True)
    size = models.ForeignKey('Size', on_delete=models.CASCADE, null=True, blank=True)
    image = models.ImageField(upload_to='products/')
    stock_quantity = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, null=True, blank=True)
    icon = models.ImageField(upload_to='categories/icons/', blank=True, null=True)
    image = models.ImageField(upload_to='categories/images/', blank=True, null=True)
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class SubCategory(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='subcategories')
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, null=True, blank=True)

    def __str__(self):
        return f"{self.category.name} > {self.name}"


class Brand(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, null=True, blank=True)

    def __str__(self):
        return self.name


class Color(models.Model):
    name = models.CharField(max_length=50)
    hex_code = models.CharField(max_length=7, null=True, blank=True)
    slug = models.SlugField(unique=True, null=True, blank=True)

    def __str__(self):
        return self.name


class Size(models.Model):
    name = models.CharField(max_length=50)
    slug = models.SlugField(unique=True, null=True, blank=True)

    def __str__(self):
        return self.name


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='products/images/')

    def __str__(self):
        return f"Image for {self.product.name}"


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=30, null=True, blank=True)

    def __str__(self):
        return self.user.username


class Address(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=100, null=True, blank=True)
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.user.username} - {self.label or self.line1}"


class Coupon(models.Model):
    code = models.CharField(max_length=50, unique=True)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    active = models.BooleanField(default=True)
    valid_to = models.DateTimeField()

    def __str__(self):
        return self.code

    def get_discount(self, total):
        if self.discount_percentage:
            return (total * self.discount_percentage / Decimal('100')).quantize(Decimal('0.01'))
        return min(self.discount_amount or Decimal('0.00'), total)


class ContactSubmission(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)

    class Meta:
        ordering = ('-created_at',)

    def __str__(self):
        return f"{self.name} - {self.email}"


class Cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='carts', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Cart {self.id} ({self.user.username if self.user else 'anonymous'})"


class CartItem(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cart_items', null=True, blank=True)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items', null=True, blank=True)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    def get_total(self):
        return self.product.price * self.quantity


class Order(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ('RAZORPAY', 'Online Payment'),
        ('COD', 'Cash on Delivery'),
    ]

    STATUS_CHOICES = [
        ('Placed', 'Placed'),
        ('Processing', 'Processing'),
        ('Out for Delivery', 'Out for Delivery'),
        ('Delivered', 'Delivered'),
        ('Cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True)
    coupon = models.ForeignKey('Coupon', on_delete=models.SET_NULL, null=True, blank=True)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='RAZORPAY')
    payment_status = models.CharField(max_length=50, default='Pending')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Placed')
    created_at = models.DateTimeField(auto_now_add=True)
    estimated_delivery = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coins_used = models.PositiveIntegerField(default=0)
    razorpay_order_id = models.CharField(max_length=255, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=255, null=True, blank=True)
    razorpay_signature = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"Order {self.id} - {self.user.username}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.product.name if self.product else 'deleted product'}"


class Wishlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wishlists')
    products = models.ManyToManyField(Product, related_name='wishlisted_by')

    def __str__(self):
        return f"Wishlist for {self.user.username}"


# User ka Wallet
class Wallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='wallet')
    coins = models.PositiveIntegerField(default=0) # Total Coins

    def __str__(self):
        return f"{self.user.username}'s Wallet - {self.coins} Coins"

# Coins Aane aur Kharch Hone ka Record
class CoinTransaction(models.Model):
    TRANSACTION_TYPES = (
        ('EARNED', 'Earned'),
        ('SPENT', 'Spent'),
    )
    
    wallet = models.ForeignKey(Wallet, on_delete=models.CASCADE, related_name='transactions')
    coins = models.PositiveIntegerField()
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    description = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type}: {self.coins} Coins"


class AccountPopup(models.Model):
    title = models.CharField(max_length=200)
    message = models.TextField(blank=True)
    image = models.ImageField(upload_to='popups/', blank=True, null=True)
    button_text = models.CharField(max_length=80, blank=True)
    button_url = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Account Popup'
        verbose_name_plural = 'Account Popups'

    def __str__(self):
        return self.title or f"Popup {self.pk}"
