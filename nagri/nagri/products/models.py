from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.core.validators import MaxValueValidator, MinValueValidator
from decimal import Decimal
from datetime import date
from decimal import InvalidOperation
import json
from django.utils import timezone


DIMENSION_UNIT_CHOICES = (
    ("mm", "Millimetres (mm)"),
    ("cm", "Centimetres (cm)"),
    ("inch", "Inches"),
    ("feet", "Feet"),
)
WEIGHT_UNIT_CHOICES = (
    ("g", "Grams (g)"),
    ("kg", "Kilograms (kg)"),
)
PRICE_MIN = Decimal("0.01")
PRICE_MAX = Decimal("999999999.99")


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to="categories/", blank=True, null=True)
    default_tax_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class SubCategory(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="subcategories")
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("category", "slug")

    def __str__(self):
        return f"{self.category.name} / {self.name}"


class Product(models.Model):
    REVIEW_STATUS_CHOICES = (
        ("draft", "Draft"),
        ("pending_review", "Pending Review"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    )

    seller = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="seller_products")
    store = models.ForeignKey("sellers.Store", on_delete=models.SET_NULL, null=True, blank=True, related_name="products")
    sku = models.CharField(max_length=64, unique=True, blank=True, null=True)
    name = models.CharField(max_length=200, db_index=True)
    slug = models.SlugField(unique=True, db_index=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="products", db_index=True)
    subcategory = models.ForeignKey(SubCategory, on_delete=models.SET_NULL, related_name="products", null=True, blank=True, db_index=True)
    short_description = models.TextField(blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    brand = models.CharField(max_length=100, blank=True, null=True, db_index=True)
    tags = models.CharField(max_length=255, blank=True, null=True)
    price = models.DecimalField(
        max_digits=11, decimal_places=2, db_index=True,
        validators=[MinValueValidator(PRICE_MIN), MaxValueValidator(PRICE_MAX)],
    )
    compare_price = models.DecimalField(
        max_digits=11, decimal_places=2, default=0.00,
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(PRICE_MAX)],
    )
    cost_price = models.DecimalField(
        max_digits=11, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(PRICE_MAX)],
    )
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
    )
    tax_inclusive = models.BooleanField(default=True)
    scheduled_sale_price = models.DecimalField(
        max_digits=11, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(PRICE_MIN), MaxValueValidator(PRICE_MAX)],
    )
    scheduled_sale_start = models.DateTimeField(blank=True, null=True)
    scheduled_sale_end = models.DateTimeField(blank=True, null=True)
    is_flash_sale = models.BooleanField(default=False, db_index=True)
    flash_sale_start = models.DateTimeField(blank=True, null=True, db_index=True)
    flash_sale_end = models.DateTimeField(blank=True, null=True, db_index=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0.00, db_index=True)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    is_bestseller = models.BooleanField(default=False, db_index=True)
    is_active = models.BooleanField(default=True, db_index=True)
    review_status = models.CharField(
        max_length=20, choices=REVIEW_STATUS_CHOICES, default="approved", db_index=True
    )
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["is_active", "is_featured", "is_bestseller", "created_at"]),
            models.Index(fields=["category", "is_active", "created_at"]),
            models.Index(fields=["price", "is_active"]),
            models.Index(fields=["is_active", "is_flash_sale", "flash_sale_end"]),
        ]

    @property
    def in_stock(self):
        if self.variants.exists():
            return self.variants.filter(is_active=True, inventory__stock_quantity__gt=0).exists()
        return self.inventory.stock_quantity > 0 if hasattr(self, "inventory") else False

    @property
    def has_variants(self):
        return self.variants.exists()

    @property
    def effective_tax_rate(self):
        return self.tax_rate if self.tax_rate is not None else self.category.default_tax_rate

    @property
    def flash_sale_is_active(self):
        now = timezone.now()
        return bool(
            self.is_active
            and self.is_flash_sale
            and self.flash_sale_start
            and self.flash_sale_end
            and self.flash_sale_start <= now <= self.flash_sale_end
        )

    @property
    def flash_sale_discount_percent(self):
        if self.compare_price and self.compare_price > self.price:
            try:
                discount = ((float(self.compare_price) - float(self.price)) / float(self.compare_price)) * 100.0
                return int(round(discount))
            except (TypeError, ValueError, ZeroDivisionError):
                return 0
        return 0

    @property
    def flash_sale_remaining_stock(self):
        if self.variants.exists():
            total = self.variants.filter(is_active=True).aggregate(
                total=Sum("inventory__stock_quantity")
            )["total"]
            return total or 0
        inventory = getattr(self, "inventory", None)
        if inventory is None:
            return None
        return inventory.stock_quantity

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        create_sku = not self.sku
        super().save(*args, **kwargs)
        if create_sku:
            self.sku = f"NG-{self.pk:08d}"
            type(self).objects.filter(pk=self.pk).update(sku=self.sku)

    def clean(self):
        super().clean()
        if self.subcategory_id and self.subcategory.category_id != self.category_id:
            raise ValidationError({"subcategory": "Subcategory must belong to the selected category."})
        if self.compare_price and self.compare_price < self.price:
            raise ValidationError({"compare_price": "Regular price cannot be below the current price."})
        if self.review_status == "rejected" and not self.rejection_reason.strip():
            raise ValidationError({"rejection_reason": "A reason is required when rejecting a product."})
        if self.scheduled_sale_price is not None:
            if not self.scheduled_sale_start or not self.scheduled_sale_end:
                raise ValidationError("A scheduled sale price requires both start and end times.")
            if self.scheduled_sale_end <= self.scheduled_sale_start:
                raise ValidationError({"scheduled_sale_end": "Sale end must be after its start."})
            regular_price = self.compare_price if self.compare_price else self.price
            if self.scheduled_sale_price >= regular_price:
                raise ValidationError({"scheduled_sale_price": "Scheduled sale price must be below the regular price."})

    def get_current_price(self, at=None):
        at = at or timezone.now()
        if (
            self.scheduled_sale_price is not None
            and self.scheduled_sale_start
            and self.scheduled_sale_end
            and self.scheduled_sale_start <= at <= self.scheduled_sale_end
        ):
            return self.scheduled_sale_price
        return self.price

    def get_regular_price(self, at=None):
        current = self.get_current_price(at)
        return self.compare_price if self.compare_price > current else current

    def get_discount_amount(self, at=None):
        return max(self.get_regular_price(at) - self.get_current_price(at), Decimal("0.00"))

    def get_discount_percentage(self, at=None):
        regular = self.get_regular_price(at)
        if regular <= 0:
            return Decimal("0.00")
        return (self.get_discount_amount(at) * Decimal("100") / regular).quantize(Decimal("0.01"))

    @property
    def profit_margin(self):
        price = self.get_current_price()
        if self.cost_price is None or price <= 0:
            return None
        return ((price - self.cost_price) * Decimal("100") / price).quantize(Decimal("0.01"))


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    alt_text = models.CharField(max_length=255, blank=True, null=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["display_order", "-created_at"]

    def clean(self):
        from django.core.exceptions import ValidationError

        # Enforce maximum 12 images per product.
        # If the parent Product hasn't been saved yet (no PK), skip DB relationship checks
        # because accessing product.images will raise ValueError when product.pk is None.
        if not self.product or not getattr(self.product, 'pk', None):
            return

        if self.product.images.exclude(pk=self.pk).count() >= 12:
            raise ValidationError("A product cannot have more than 12 images.")

    def __str__(self):
        return f"Image for {self.product.name} ({self.pk})"


class MeasurementFields(models.Model):
    dimension_unit = models.CharField(max_length=8, choices=DIMENSION_UNIT_CHOICES, default="cm")
    weight_unit = models.CharField(max_length=4, choices=WEIGHT_UNIT_CHOICES, default="g")
    length_mm = models.DecimalField(max_digits=12, decimal_places=3, blank=True, null=True)
    width_mm = models.DecimalField(max_digits=12, decimal_places=3, blank=True, null=True)
    height_mm = models.DecimalField(max_digits=12, decimal_places=3, blank=True, null=True)
    product_weight_g = models.DecimalField(max_digits=12, decimal_places=3, blank=True, null=True)
    packaging_weight_g = models.DecimalField(max_digits=12, decimal_places=3, blank=True, null=True)
    shipping_weight_g = models.DecimalField(max_digits=12, decimal_places=3, blank=True, null=True)
    custom_size = models.CharField(max_length=255, blank=True)
    custom_weight_g = models.DecimalField(max_digits=12, decimal_places=3, blank=True, null=True)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        positive_fields = (
            "length_mm", "width_mm", "height_mm", "product_weight_g",
            "packaging_weight_g", "shipping_weight_g", "custom_weight_g",
        )
        errors = {}
        for field_name in positive_fields:
            value = getattr(self, field_name)
            if value is not None and value <= 0:
                errors[field_name] = "Enter a value greater than zero."
        if (
            self.shipping_weight_g is not None
            and self.product_weight_g is not None
            and self.shipping_weight_g < self.product_weight_g + (self.packaging_weight_g or Decimal("0"))
        ):
            errors["shipping_weight_g"] = "Shipping weight cannot be less than product plus packaging weight."
        if errors:
            raise ValidationError(errors)

    @staticmethod
    def convert_dimension_to_mm(value, unit):
        factors = {"mm": Decimal("1"), "cm": Decimal("10"), "inch": Decimal("25.4"), "feet": Decimal("304.8")}
        if unit not in factors:
            raise ValidationError({"dimension_unit": "Choose a supported dimension unit."})
        return (Decimal(value) * factors[unit]).quantize(Decimal("0.001"))

    @staticmethod
    def convert_weight_to_grams(value, unit):
        factors = {"g": Decimal("1"), "kg": Decimal("1000")}
        if unit not in factors:
            raise ValidationError({"weight_unit": "Choose a supported weight unit."})
        return (Decimal(value) * factors[unit]).quantize(Decimal("0.001"))

    def dimension_in_display_unit(self, value_mm):
        if value_mm is None:
            return None
        divisors = {"mm": Decimal("1"), "cm": Decimal("10"), "inch": Decimal("25.4"), "feet": Decimal("304.8")}
        return (value_mm / divisors[self.dimension_unit]).quantize(Decimal("0.001"))

    def weight_in_display_unit(self, value_g):
        if value_g is None:
            return None
        divisor = Decimal("1000") if self.weight_unit == "kg" else Decimal("1")
        return (value_g / divisor).quantize(Decimal("0.001"))


class ProductMeasurement(MeasurementFields):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="measurement")

    def clean(self):
        super().clean()
        if not self.product_id:
            return
        requirements = _measurement_requirements(
            self.product.category_id,
            self.product.subcategory_id,
        )
        errors = {
            field_name: "This measurement is required for the selected category."
            for field_name in requirements
            if requirements[field_name].is_required and getattr(self, field_name) in (None, "")
        }
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Measurements for {self.product.name}"


class VariantMeasurement(MeasurementFields):
    variant = models.OneToOneField("ProductVariant", on_delete=models.CASCADE, related_name="measurement")

    def clean(self):
        super().clean()
        if not self.variant_id:
            return
        product_measurement = getattr(self.variant.product, "measurement", None)
        requirements = _measurement_requirements(
            self.variant.product.category_id,
            self.variant.product.subcategory_id,
        )
        errors = {}
        for field_name, requirement in requirements.items():
            if not requirement.is_required:
                continue
            if getattr(self, field_name) in (None, "") and (
                product_measurement is None or getattr(product_measurement, field_name) in (None, "")
            ):
                errors[field_name] = "This measurement is required for the selected category."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Measurements for {self.variant}"


class MeasurementRequirement(models.Model):
    MEASUREMENT_FIELDS = (
        ("length_mm", "Length"),
        ("width_mm", "Width"),
        ("height_mm", "Height"),
        ("product_weight_g", "Product weight"),
        ("packaging_weight_g", "Packaging weight"),
        ("shipping_weight_g", "Shipping weight"),
        ("custom_size", "Custom size"),
        ("custom_weight_g", "Custom weight"),
    )

    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="measurement_requirements")
    subcategory = models.ForeignKey(
        SubCategory, on_delete=models.CASCADE, blank=True, null=True,
        related_name="measurement_requirements",
    )
    field_name = models.CharField(max_length=32, choices=MEASUREMENT_FIELDS)
    is_required = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "field_name"],
                condition=Q(subcategory__isnull=True),
                name="unique_category_measurement_requirement",
            ),
            models.UniqueConstraint(
                fields=["category", "subcategory", "field_name"],
                condition=Q(subcategory__isnull=False),
                name="unique_subcategory_measurement_requirement",
            ),
        ]

    def clean(self):
        if self.subcategory_id and self.subcategory.category_id != self.category_id:
            raise ValidationError({"subcategory": "Subcategory must belong to the selected category."})

    def __str__(self):
        return f"{self.category}: {self.get_field_name_display()}"


def _measurement_requirements(category_id, subcategory_id):
    category_requirements = {
        requirement.field_name: requirement
        for requirement in MeasurementRequirement.objects.filter(
            category_id=category_id,
            subcategory__isnull=True,
        )
    }
    if not subcategory_id:
        return category_requirements
    category_requirements.update({
        requirement.field_name: requirement
        for requirement in MeasurementRequirement.objects.filter(
            category_id=category_id,
            subcategory_id=subcategory_id,
        )
    })
    return category_requirements


class VariantAttributeDefinition(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="variant_attribute_definitions")
    subcategory = models.ForeignKey(
        SubCategory, on_delete=models.CASCADE, blank=True, null=True,
        related_name="variant_attribute_definitions",
    )
    key = models.SlugField(max_length=64)
    label = models.CharField(max_length=100)
    options = models.JSONField(default=list, blank=True)
    is_required = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["category", "key"], condition=Q(subcategory__isnull=True), name="unique_category_variant_attribute"),
            models.UniqueConstraint(fields=["category", "subcategory", "key"], condition=Q(subcategory__isnull=False), name="unique_subcategory_variant_attribute"),
        ]

    def clean(self):
        if self.subcategory_id and self.subcategory.category_id != self.category_id:
            raise ValidationError({"subcategory": "Subcategory must belong to the selected category."})
        if not isinstance(self.options, list) or any(not isinstance(option, str) or not option.strip() for option in self.options):
            raise ValidationError({"options": "Options must be a list of non-empty strings."})

    def __str__(self):
        return f"{self.category}: {self.label}"


class ProductAttributeDefinition(models.Model):
    DATA_TYPE_CHOICES = (
        ("text", "Text"),
        ("integer", "Whole number"),
        ("decimal", "Decimal number"),
        ("boolean", "Yes / No"),
        ("date", "Date"),
        ("dropdown", "Dropdown"),
        ("multi_select", "Multiple selections"),
    )

    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="attribute_definitions")
    subcategory = models.ForeignKey(
        SubCategory,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="attribute_definitions",
    )
    key = models.SlugField(max_length=64)
    label = models.CharField(max_length=100)
    data_type = models.CharField(max_length=16, choices=DATA_TYPE_CHOICES, default="text")
    is_required = models.BooleanField(default=False)
    options = models.JSONField(default=list, blank=True)
    unit = models.CharField(max_length=24, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=("category", "key"),
                condition=Q(subcategory__isnull=True),
                name="unique_category_product_attribute",
            ),
            models.UniqueConstraint(
                fields=("category", "subcategory", "key"),
                condition=Q(subcategory__isnull=False),
                name="unique_subcategory_product_attribute",
            ),
        ]

    def clean(self):
        if self.subcategory_id and self.subcategory.category_id != self.category_id:
            raise ValidationError({"subcategory": "Subcategory must belong to the selected category."})
        if not isinstance(self.options, list) or any(
            not isinstance(option, str) or not option.strip() for option in self.options
        ):
            raise ValidationError({"options": "Options must be a list of non-empty strings."})
        if self.data_type in {"dropdown", "multi_select"} and not self.options:
            raise ValidationError({"options": "Dropdown attributes require at least one option."})

    def __str__(self):
        return f"{self.category}: {self.label}"


class ProductAttributeValue(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="attribute_values")
    definition = models.ForeignKey(
        ProductAttributeDefinition,
        on_delete=models.CASCADE,
        related_name="values",
    )
    value = models.JSONField()

    class Meta:
        ordering = ["definition__sort_order", "definition_id"]
        constraints = [
            models.UniqueConstraint(
                fields=("product", "definition"),
                name="unique_product_attribute_value",
            ),
        ]

    def clean(self):
        super().clean()
        if self.product_id and self.definition_id:
            definition = self.definition
            if definition.category_id != self.product.category_id:
                raise ValidationError({"definition": "Attribute definition does not belong to this product category."})
            if definition.subcategory_id and definition.subcategory_id != self.product.subcategory_id:
                raise ValidationError({"definition": "Attribute definition does not belong to this product subcategory."})
        else:
            return

        value = self.value
        data_type = definition.data_type
        if (value is None or value == "" or value == []) and definition.is_required:
            raise ValidationError({"value": "This attribute is required."})
        if value is None or value == "" or value == []:
            return
        if data_type == "text" and not isinstance(value, str):
            raise ValidationError({"value": "Enter text for this attribute."})
        if data_type == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValidationError({"value": "Enter a whole number for this attribute."})
        if data_type == "decimal":
            try:
                number = Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValidationError({"value": "Enter a decimal number for this attribute."}) from exc
            if not number.is_finite():
                raise ValidationError({"value": "Enter a finite decimal number for this attribute."})
        if data_type == "boolean" and not isinstance(value, bool):
            raise ValidationError({"value": "Enter Yes or No for this attribute."})
        if data_type == "date":
            try:
                date.fromisoformat(value)
            except (TypeError, ValueError) as exc:
                raise ValidationError({"value": "Enter a date in YYYY-MM-DD format."}) from exc
        if data_type == "dropdown" and value not in definition.options:
            raise ValidationError({"value": "Choose one of the configured options."})
        if data_type == "multi_select" and (
            not isinstance(value, list)
            or any(item not in definition.options for item in value)
        ):
            raise ValidationError({"value": "Choose one or more configured options."})

    def __str__(self):
        return f"{self.product.name}: {self.definition.label}"


class StockFields(models.Model):
    stock_quantity = models.PositiveIntegerField(default=0, verbose_name="Available stock")
    reserved_quantity = models.PositiveIntegerField(default=0)
    sold_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)

    class Meta:
        abstract = True

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.low_stock_threshold

    @property
    def is_out_of_stock(self):
        return self.stock_quantity == 0


class Inventory(models.Model):
    product = models.OneToOneField(Product, on_delete=models.CASCADE, related_name="inventory")
    stock_quantity = models.PositiveIntegerField(default=0, verbose_name="Available stock")
    reserved_quantity = models.PositiveIntegerField(default=0)
    sold_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.product.name} inventory"

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.low_stock_threshold

    @property
    def is_out_of_stock(self):
        return self.stock_quantity == 0


class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(max_length=64, unique=True, blank=True, null=True)
    attributes = models.JSONField(default=dict)
    combination_key = models.CharField(max_length=512, editable=False)
    price = models.DecimalField(
        max_digits=11, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(PRICE_MIN), MaxValueValidator(PRICE_MAX)],
    )
    compare_price = models.DecimalField(
        max_digits=11, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(PRICE_MAX)],
    )
    cost_price = models.DecimalField(
        max_digits=11, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(PRICE_MAX)],
    )
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(Decimal("100.00"))],
    )
    tax_inclusive = models.BooleanField(default=True)
    scheduled_sale_price = models.DecimalField(
        max_digits=11, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(PRICE_MIN), MaxValueValidator(PRICE_MAX)],
    )
    scheduled_sale_start = models.DateTimeField(blank=True, null=True)
    scheduled_sale_end = models.DateTimeField(blank=True, null=True)
    image = models.ImageField(upload_to="products/variants/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["product", "combination_key"], name="unique_product_variant_combination"),
        ]
        ordering = ["id"]

    def clean(self):
        super().clean()
        if not isinstance(self.attributes, dict) or not self.attributes:
            raise ValidationError({"attributes": "A variant must have at least one attribute."})
        if self.price is not None and self.compare_price is not None and self.compare_price < self.price:
            raise ValidationError({"compare_price": "Regular price cannot be below the variant price."})
        definitions = list(
            VariantAttributeDefinition.objects.filter(category=self.product.category)
            .filter(Q(subcategory__isnull=True) | Q(subcategory=self.product.subcategory))
        )
        definition_map = {definition.key: definition for definition in definitions}
        missing = [definition.label for definition in definitions if definition.is_required and not self.attributes.get(definition.key)]
        if missing:
            raise ValidationError({"attributes": f"Missing required variant attributes: {', '.join(missing)}."})
        errors = []
        for key, value in self.attributes.items():
            definition = definition_map.get(key)
            if not isinstance(key, str) or not isinstance(value, str) or not value.strip():
                errors.append("Variant attribute keys and values must be non-empty text.")
                continue
            if definition and definition.options and value not in definition.options:
                errors.append(f"{value!r} is not a valid option for {definition.label}.")
        if errors:
            raise ValidationError({"attributes": errors})
        if self.scheduled_sale_price is not None:
            if not self.scheduled_sale_start or not self.scheduled_sale_end:
                raise ValidationError("A scheduled sale price requires both start and end times.")
            if self.scheduled_sale_end <= self.scheduled_sale_start:
                raise ValidationError({"scheduled_sale_end": "Sale end must be after its start."})
            regular_price = self.compare_price or self.price or self.product.compare_price or self.product.price
            if self.scheduled_sale_price >= regular_price:
                raise ValidationError({"scheduled_sale_price": "Scheduled sale price must be below the regular price."})

    def save(self, *args, **kwargs):
        self.combination_key = json.dumps(self.attributes, sort_keys=True, separators=(",", ":"))
        create_sku = not self.sku
        super().save(*args, **kwargs)
        if create_sku:
            self.sku = f"{self.product.sku or 'NG'}-V{self.pk:06d}"
            type(self).objects.filter(pk=self.pk).update(sku=self.sku)

    def get_current_price(self, at=None):
        at = at or timezone.now()
        base_price = self.price if self.price is not None else self.product.get_current_price(at)
        if (
            self.scheduled_sale_price is not None
            and self.scheduled_sale_start
            and self.scheduled_sale_end
            and self.scheduled_sale_start <= at <= self.scheduled_sale_end
        ):
            return self.scheduled_sale_price
        return base_price

    def get_regular_price(self, at=None):
        current = self.get_current_price(at)
        base = self.compare_price if self.compare_price is not None else self.product.get_regular_price(at)
        return base if base > current else current

    @property
    def profit_margin(self):
        price = self.get_current_price()
        cost = self.cost_price if self.cost_price is not None else self.product.cost_price
        if cost is None or price <= 0:
            return None
        return ((price - cost) * Decimal("100") / price).quantize(Decimal("0.01"))

    @property
    def inventory_record(self):
        return self.inventory

    def __str__(self):
        values = ", ".join(f"{key}: {value}" for key, value in sorted(self.attributes.items()))
        return f"{self.product.name} ({values})"


class VariantInventory(StockFields):
    variant = models.OneToOneField(ProductVariant, on_delete=models.CASCADE, related_name="inventory")
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.variant} inventory"


class StockMovement(models.Model):
    REASON_CHOICES = (
        ("admin_adjustment", "Admin adjustment"),
        ("seller_adjustment", "Seller adjustment"),
        ("order_reserved", "Order reserved"),
        ("order_paid", "Order paid"),
        ("order_cancelled", "Order cancelled"),
        ("payment_rejected", "Payment rejected"),
        ("refund_restock", "Refund restock"),
    )

    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, blank=True, null=True, related_name="movements")
    variant_inventory = models.ForeignKey(VariantInventory, on_delete=models.CASCADE, blank=True, null=True, related_name="movements")
    order_id = models.PositiveBigIntegerField(blank=True, null=True, db_index=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    available_delta = models.IntegerField(default=0)
    reserved_delta = models.IntegerField(default=0)
    sold_delta = models.IntegerField(default=0)
    reason = models.CharField(max_length=32, choices=REASON_CHOICES)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(inventory__isnull=False, variant_inventory__isnull=True) | Q(inventory__isnull=True, variant_inventory__isnull=False)),
                name="stock_movement_one_inventory_target",
            ),
        ]

    def __str__(self):
        return f"{self.get_reason_display()} ({self.created_at:%Y-%m-%d %H:%M})"


class ProductPriceHistory(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="price_history")
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, blank=True, null=True, related_name="price_history")
    old_price = models.DecimalField(max_digits=11, decimal_places=2, blank=True, null=True)
    new_price = models.DecimalField(max_digits=11, decimal_places=2)
    old_regular_price = models.DecimalField(max_digits=11, decimal_places=2, blank=True, null=True)
    new_regular_price = models.DecimalField(max_digits=11, decimal_places=2, blank=True, null=True)
    old_scheduled_sale_price = models.DecimalField(max_digits=11, decimal_places=2, blank=True, null=True)
    new_scheduled_sale_price = models.DecimalField(max_digits=11, decimal_places=2, blank=True, null=True)
    old_scheduled_sale_start = models.DateTimeField(blank=True, null=True)
    new_scheduled_sale_start = models.DateTimeField(blank=True, null=True)
    old_scheduled_sale_end = models.DateTimeField(blank=True, null=True)
    new_scheduled_sale_end = models.DateTimeField(blank=True, null=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.product.name}: {self.old_price} → {self.new_price}"
