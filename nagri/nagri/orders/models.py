from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Sum

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

    CANCELLATION_REASON_CHOICES = [
        ("ORDERED_BY_MISTAKE", "I ordered by mistake"),
        ("NOT_NEEDED", "I don't need the product anymore"),
        ("BETTER_PRICE", "I found a better price elsewhere"),
        ("DELIVERY_DELAY", "Delivery is taking too long"),
        ("CHANGE_ADDRESS", "I want to change my delivery address"),
        ("CHANGE_MOBILE", "I want to change my mobile number"),
        ("WRONG_PRODUCT_QUANTITY", "I ordered the wrong product or quantity"),
        ("PAYMENT_ISSUE", "Payment issue"),
        ("NO_LONGER_REQUIRED", "Product is no longer required"),
        ("OTHER", "Other reason"),
    ]
    CANCELLABLE_STATUSES = {"pending", "processing"}

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
    shipping_address_latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    shipping_address_longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        blank=True,
        null=True,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    
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
    inventory_reserved = models.BooleanField(default=False)
    razorpay_order_id = models.CharField(max_length=255, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=255, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)

    # Cancellation details are retained on the order for customer support and auditability.
    cancellation_reason = models.CharField(max_length=30, choices=CANCELLATION_REASON_CHOICES, blank=True)
    cancellation_comment = models.TextField(max_length=500, blank=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    cancelled_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="cancelled_orders")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(shipping_address_latitude__isnull=True)
                | models.Q(
                    shipping_address_latitude__gte=-90,
                    shipping_address_latitude__lte=90,
                ),
                name="order_shipping_latitude_range",
            ),
            models.CheckConstraint(
                condition=models.Q(shipping_address_longitude__isnull=True)
                | models.Q(
                    shipping_address_longitude__gte=-180,
                    shipping_address_longitude__lte=180,
                ),
                name="order_shipping_longitude_range",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        shipping_address_latitude__isnull=True,
                        shipping_address_longitude__isnull=True,
                    )
                    | models.Q(
                        shipping_address_latitude__isnull=False,
                        shipping_address_longitude__isnull=False,
                    )
                ),
                name="order_shipping_coordinates_paired",
            ),
        ]
        
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
    FULFILLMENT_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("shipped", "Shipped"),
        ("delivered", "Delivered"),
        ("cancelled", "Cancelled"),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    variant = models.ForeignKey(
        "products.ProductVariant",
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="order_items",
    )
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    regular_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    sku_snapshot = models.CharField(max_length=64, blank=True)
    variant_attributes_snapshot = models.JSONField(default=dict, blank=True)
    tax_rate_snapshot = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount_snapshot = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fulfillment_status = models.CharField(max_length=20, choices=FULFILLMENT_STATUS_CHOICES, default="pending")

    def clean(self):
        super().clean()
        if self.variant_id and self.variant.product_id != self.product_id:
            from django.core.exceptions import ValidationError

            raise ValidationError({"variant": "The selected variant does not belong to this product."})

    def __str__(self):
        return f"{self.product.name} x {self.quantity}"
    
    def get_subtotal(self):
        return self.price * self.quantity


class OrderRefund(models.Model):
    STATUS_CHOICES = (
        ("requested", "Requested"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("completed", "Completed"),
    )

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="refunds")
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default="requested")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    provider_refund_id = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="reviewed_order_refunds",
    )
    reviewed_at = models.DateTimeField(blank=True, null=True)
    stock_restocked_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def clean(self):
        super().clean()
        if self.amount <= 0 or self.amount > self.order.total_amount:
            from django.core.exceptions import ValidationError

            raise ValidationError({"amount": "Refund amount must be positive and cannot exceed the order total."})
        if self.status in {"approved", "completed"}:
            previous_refunds = self.order.refunds.exclude(pk=self.pk).filter(
                status__in=("approved", "completed")
            ).aggregate(total=Sum("amount"))["total"] or 0
            if previous_refunds + self.amount > self.order.total_amount:
                from django.core.exceptions import ValidationError

                raise ValidationError({"amount": "Approved refunds cannot exceed the order total."})

    def __str__(self):
        return f"Refund for {self.order.order_number} ({self.get_status_display()})"


class OrderRefundItem(models.Model):
    refund = models.ForeignKey(OrderRefund, on_delete=models.CASCADE, related_name="items")
    order_item = models.ForeignKey(OrderItem, on_delete=models.PROTECT, related_name="refund_items")
    quantity = models.PositiveIntegerField(default=1)
    restockable = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=("refund", "order_item"), name="unique_refund_order_item"),
        ]

    def clean(self):
        super().clean()
        if self.quantity <= 0:
            from django.core.exceptions import ValidationError

            raise ValidationError({"quantity": "Refund quantity must be greater than zero."})
        if self.refund_id and self.order_item_id and self.refund.order_id != self.order_item.order_id:
            from django.core.exceptions import ValidationError

            raise ValidationError({"order_item": "Refund item must belong to the refund's order."})
        if self.order_item_id and self.quantity > self.order_item.quantity:
            from django.core.exceptions import ValidationError

            raise ValidationError({"quantity": "Refund quantity cannot exceed the ordered quantity."})
        if self.refund_id and self.order_item_id:
            already_refunded = self.order_item.refund_items.exclude(refund=self.refund).filter(
                refund__status__in=("approved", "completed")
            ).aggregate(total=Sum("quantity"))["total"] or 0
            if self.refund.status in {"approved", "completed"} and already_refunded + self.quantity > self.order_item.quantity:
                from django.core.exceptions import ValidationError

                raise ValidationError({"quantity": "Approved refunds cannot exceed the ordered quantity."})


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
