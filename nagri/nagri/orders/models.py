from django.conf import settings
from django.db import models

from products.models import Product
from accounts.models import Address


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("pending_verification", "Pending Verification"),
        ("paid", "Paid"),
        ("shipped", "Shipped"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]

    TRACKING_CHOICES = [
        ("processing", "Processing"),
        ("packed", "Packed"),
        ("shipped", "Shipped"),
        ("out_for_delivery", "Out for Delivery"),
        ("delivered", "Delivered"),
    ]

    DELIVERY_CHOICES = [
        ("standard", "Standard Delivery (5-7 days) - FREE"),
        ("express", "Express Delivery (2-3 days) - ₹50"),
        ("overnight", "Overnight Delivery - ₹100"),
    ]

    PAYMENT_METHOD_CHOICES = [
        ("razorpay", "Credit/Debit Card"),
        ("netbanking", "Net Banking"),
        ("upi", "UPI"),
        ("wallet", "Wallet"),
        ("cod", "Cash on Delivery"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders")
    order_number = models.CharField(max_length=50, unique=True)
    
    # Pricing
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    delivery_charge = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Coupon/Discount
    coupon_code = models.CharField(max_length=50, blank=True, null=True)
    
    # Address
    shipping_address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    shipping_address_name = models.CharField(max_length=150, blank=True)
    shipping_address_phone = models.CharField(max_length=20, blank=True)
    shipping_address_line1 = models.CharField(max_length=255, blank=True)
    shipping_address_line2 = models.CharField(max_length=255, blank=True, null=True)
    shipping_address_city = models.CharField(max_length=100, blank=True)
    shipping_address_state = models.CharField(max_length=100, blank=True)
    shipping_address_postal_code = models.CharField(max_length=20, blank=True)
    shipping_address_country = models.CharField(max_length=100, blank=True, default="India")
    
    # Delivery & Payment
    delivery_method = models.CharField(max_length=20, choices=DELIVERY_CHOICES, default="standard")
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default="razorpay")
    
    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    tracking_status = models.CharField(max_length=30, choices=TRACKING_CHOICES, default="processing")
    tracking_code = models.CharField(max_length=100, blank=True, null=True)
    tracking_number = models.CharField(max_length=100, blank=True, null=True)
    is_paid = models.BooleanField(default=False)
    
    # Payment Provider
    payment_provider = models.CharField(max_length=50, blank=True, default="razorpay")
    razorpay_order_id = models.CharField(max_length=255, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=255, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        
    def __str__(self):
        return self.order_number
    
    def get_delivery_charge(self):
        """Get delivery charge based on method"""
        if self.delivery_method == "standard":
            return 0
        elif self.delivery_method == "express":
            return 50
        elif self.delivery_method == "overnight":
            return 100
        return 0


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="order_items")
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"
    
    def get_subtotal(self):
        return self.price * self.quantity


class UpiPaymentSubmission(models.Model):
    STATUS = [
        ("pending", "Pending Verification"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="upi_submissions")
    upi_id = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    utr = models.CharField(max_length=255, blank=True, null=True)
    receipt = models.FileField(upload_to="upi_receipts/", blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS, default="pending")
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="upi_reviews")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    admin_notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"UPI submission for {self.order.order_number} ({self.status})"
