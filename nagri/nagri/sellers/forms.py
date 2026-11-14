import re
from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from .models import SellerApplication, Store
from products.forms import (
    MeasurementFormMixin,
    SellerVariantField,
    serialize_product_attributes,
    serialize_product_variants,
    validate_product_attribute_payload,
    validate_variant_payload,
)
from products.inventory import adjust_available_stock
from products.models import (
    Category,
    Inventory,
    Product,
    ProductAttributeDefinition,
    ProductAttributeValue,
    ProductImage,
    ProductVariant,
    SubCategory,
    VariantInventory,
    VariantMeasurement,
)

import json
from decimal import Decimal
from PIL import Image, UnidentifiedImageError


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        return [super().clean(upload, initial) for upload in files]


class ShopkeeperStoreForm(forms.ModelForm):
    class Meta:
        model = Store
        fields = (
            "name",
            "phone",
            "address",
            "city",
            "state",
            "pincode",
            "latitude",
            "longitude",
            "is_active",
        )
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "address": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "state": forms.TextInput(attrs={"class": "form-control"}),
            "pincode": forms.TextInput(attrs={"class": "form-control"}),
            "latitude": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "any",
                "inputmode": "decimal",
                "min": "-90",
                "max": "90",
            }),
            "longitude": forms.NumberInput(attrs={
                "class": "form-control",
                "step": "any",
                "inputmode": "decimal",
                "min": "-180",
                "max": "180",
            }),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, include_is_active=True, **kwargs):
        super().__init__(*args, **kwargs)
        if not include_is_active:
            self.fields.pop("is_active")


class OTPRequestForm(forms.Form):
    # no fields; uses logged-in user's email
    pass


class OTPVerifyForm(forms.Form):
    otp = forms.CharField(max_length=6)


class SellerDocumentsForm(forms.ModelForm):
    class Meta:
        model = SellerApplication
        fields = ("aadhaar_number", "pan_number", "pan_card_image", "passport_photo")

    def clean_aadhaar_number(self):
        value = self.cleaned_data.get("aadhaar_number") or ""
        digits = re.sub(r"\D", "", value)
        if digits and len(digits) != 12:
            raise forms.ValidationError("Aadhaar must be 12 digits.")
        return digits

    def clean_pan_number(self):
        value = (self.cleaned_data.get("pan_number") or "").strip().upper()
        if value and not re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', value):
            raise forms.ValidationError("PAN must match format (e.g. ABCDE1234F).")
        return value

    def _validate_image_field(self, f):
        if not f:
            return
        # validate size
        if f.size > 5 * 1024 * 1024:
            raise forms.ValidationError("File size must be <= 5MB.")
        # validate actual content using Pillow
        try:
            f.seek(0)
            img = Image.open(f)
            img.verify()
            format = img.format.upper() if getattr(img, 'format', None) else None
            if format not in ("JPEG", "PNG", "GIF"):
                raise forms.ValidationError("Unsupported image type. Use JPEG/PNG/GIF.")
        except UnidentifiedImageError:
            raise forms.ValidationError("Invalid image file.")
        finally:
            try:
                f.seek(0)
            except Exception:
                pass

    def clean_pan_card_image(self):
        f = self.cleaned_data.get("pan_card_image")
        self._validate_image_field(f)
        return f

    def clean_passport_photo(self):
        f = self.cleaned_data.get("passport_photo")
        self._validate_image_field(f)
        return f


class CategorySelectionForm(forms.Form):
    categories = forms.ModelMultipleChoiceField(queryset=Category.objects.all(), required=True)


class SellerProductForm(MeasurementFormMixin, forms.ModelForm):
    stock = forms.IntegerField(
        min_value=0,
        initial=0,
        required=False,
        label="Available stock (simple products)",
        help_text="Products with variants use the stock quantity on each variant instead.",
    )
    gallery_images = MultipleImageField(
        required=False,
        label="Additional product images",
        help_text="Select up to 12 images total, including previously uploaded images.",
    )
    variant_images = MultipleImageField(
        required=False,
        label="Variant images",
        help_text="Each filename must match its variant SKU, for example TEE-M-RED.jpg.",
    )
    attributes_json = forms.JSONField(
        required=False,
        initial=dict,
        widget=forms.HiddenInput,
        help_text="Enter category-specific values as a JSON object; Admin-defined fields and choices are validated.",
    )

    class Meta:
        model = Product
        fields = [
            "name",
            "slug",
            "category",
            "subcategory",
            "brand",
            "short_description",
            "description",
            "tags",
            "price",
            "compare_price",
            "image",
            "is_featured",
            "is_bestseller",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["variants_json"] = SellerVariantField(
            required=False,
            help_text=(
                'Optional JSON list, e.g. [{"attributes":{"size":"M","color":"Red"},'
                '"sku":"TEE-M-RED","price":"25.00","stock_quantity":5}].'
            ),
        )
        self.fields["attributes_json"].initial = serialize_product_attributes(self.instance)
        self.initialize_measurements(self.instance)
        self.fields["category"].queryset = Category.objects.order_by("name")
        self.fields["subcategory"].queryset = SubCategory.objects.none()

        if self.instance and self.instance.pk:
            self.fields["subcategory"].queryset = SubCategory.objects.filter(category=self.instance.category).order_by("name")
            inventory = getattr(self.instance, "inventory", None)
            if inventory is not None:
                self.initial.setdefault("stock", inventory.stock_quantity)
            self.initial.setdefault("variants_json", serialize_product_variants(self.instance))

        if self.data.get("category"):
            category_id = self.data.get("category")
            if category_id:
                self.fields["subcategory"].queryset = SubCategory.objects.filter(category_id=category_id).order_by("name")

    def clean(self):
        cleaned_data = super().clean()
        self.clean_measurement_requirements(
            cleaned_data,
            cleaned_data.get("category"),
            cleaned_data.get("subcategory"),
        )
        category = cleaned_data.get("category")
        if category and "variants_json" in cleaned_data:
            candidate = self.instance if self.instance and self.instance.pk else Product(category=category)
            candidate.category = category
            candidate.subcategory = cleaned_data.get("subcategory")
            try:
                validate_variant_payload(candidate, cleaned_data["variants_json"])
            except ValidationError as exc:
                self.add_error("variants_json", exc)
            for item in cleaned_data["variants_json"]:
                variant_id = item.get("id")
                if variant_id and not (
                    self.instance.pk
                    and self.instance.variants.filter(pk=variant_id).exists()
                ):
                    self.add_error("variants_json", "A submitted variant does not belong to this product.")
                    break
        if category and "attributes_json" in cleaned_data:
            candidate = self.instance if self.instance and self.instance.pk else Product(category=category)
            candidate.category = category
            candidate.subcategory = cleaned_data.get("subcategory")
            try:
                validate_product_attribute_payload(candidate, cleaned_data["attributes_json"] or {})
            except ValidationError as exc:
                self.add_error("attributes_json", exc)
        existing_gallery_count = self.instance.images.count() if self.instance.pk else 0
        if existing_gallery_count + len(cleaned_data.get("gallery_images", [])) > 12:
            self.add_error("gallery_images", "A product cannot have more than 12 gallery images.")
        variant_skus = {
            item.get("sku")
            for item in cleaned_data.get("variants_json", [])
            if item.get("sku")
        }
        if self.instance.pk:
            variant_skus.update(self.instance.variants.values_list("sku", flat=True))
        invalid_variant_images = [
            upload.name.rsplit(".", 1)[0]
            for upload in cleaned_data.get("variant_images", [])
            if upload.name.rsplit(".", 1)[0] not in variant_skus
        ]
        if invalid_variant_images:
            self.add_error(
                "variant_images",
                "Variant image filenames must match an existing or submitted variant SKU.",
            )
        return cleaned_data

    def clean_stock(self):
        value = self.cleaned_data.get("stock")
        return value if value is not None else 0

    def save(self, commit=True, seller=None, submit_for_review=False):
        product = super().save(commit=False)
        is_new = product.pk is None
        if seller is not None:
            product.seller = seller
            product._price_history_actor = seller
        if is_new:
            product.review_status = "pending_review" if submit_for_review else "draft"
            product.is_active = False
        elif submit_for_review and product.review_status in {"draft", "rejected"}:
            product.review_status = "pending_review"
            product.rejection_reason = ""
            product.is_active = False
        if commit:
            with transaction.atomic():
                product.save()
                self.save_measurements(product)
                variants_data = self.cleaned_data.get("variants_json", [])
                if not product.variants.exists() and not variants_data:
                    inventory, _ = Inventory.objects.get_or_create(
                        product=product,
                        defaults={"stock_quantity": 0, "low_stock_threshold": 5},
                    )
                    adjust_available_stock(
                        inventory,
                        self.cleaned_data.get("stock", 0),
                        actor=seller,
                        reason="seller_adjustment",
                        note="Seller product form update",
                    )
                if "variants_json" in self.cleaned_data:
                    self._save_variants(product, variants_data, seller)
                self._save_attributes(product, self.cleaned_data.get("attributes_json") or {})
                for image in self.cleaned_data.get("gallery_images", []):
                    product_image = ProductImage(
                        product=product,
                        image=image,
                        display_order=product.images.count(),
                    )
                    product_image.full_clean()
                    product_image.save()
                for image in self.cleaned_data.get("variant_images", []):
                    sku = image.name.rsplit(".", 1)[0]
                    variant = product.variants.get(sku=sku)
                    variant.image = image
                    variant.save(update_fields=["image", "updated_at"])
        return product

    def _save_attributes(self, product, values):
        definitions = ProductAttributeDefinition.objects.filter(
            category=product.category,
            is_active=True,
        ).filter(
            Q(subcategory__isnull=True)
            | Q(subcategory=product.subcategory)
        )
        definition_by_key = {definition.key: definition for definition in definitions}
        for key, value in values.items():
            definition = definition_by_key.get(key)
            if definition is None:
                continue
            attribute_value, _ = ProductAttributeValue.objects.get_or_create(
                product=product,
                definition=definition,
                defaults={"value": value},
            )
            attribute_value.value = value
            attribute_value.full_clean()
            attribute_value.save(update_fields=["value"])

    def _save_variants(self, product, variants_data, actor):
        from products.models import MeasurementFields

        for data in variants_data:
            variant_id = data.get("id")
            variant = None
            if variant_id:
                variant = product.variants.filter(pk=variant_id).first()
                if variant is None:
                    self.add_error("variants_json", "A submitted variant does not belong to this product.")
                    raise ValidationError("A submitted variant does not belong to this product.")
            if variant is None:
                variant = product.variants.filter(
                    combination_key=json.dumps(data["attributes"], sort_keys=True, separators=(",", ":"))
                ).first()
            if variant is None:
                variant = ProductVariant(product=product)
            variant.attributes = data["attributes"]
            variant.sku = data.get("sku") or variant.sku
            variant.price = Decimal(str(data["price"])) if data.get("price") not in (None, "") else None
            variant.compare_price = Decimal(str(data["compare_price"])) if data.get("compare_price") not in (None, "") else None
            variant.is_active = data.get("enabled", True)
            variant._price_history_actor = actor
            variant.full_clean(exclude=["combination_key"])
            variant.save()

            variant_inventory, _ = VariantInventory.objects.get_or_create(variant=variant)
            stock_quantity = data.get("stock_quantity", variant_inventory.stock_quantity)
            adjust_available_stock(
                variant_inventory,
                stock_quantity,
                actor=actor,
                reason="seller_adjustment",
                note="Seller variant form update",
            )

            measurement_data = data.get("measurement")
            if measurement_data:
                measurement, _ = VariantMeasurement.objects.get_or_create(variant=variant)
                dimension_unit = measurement_data.get("dimension_unit", measurement.dimension_unit)
                weight_unit = measurement_data.get("weight_unit", measurement.weight_unit)
                measurement.dimension_unit = dimension_unit
                measurement.weight_unit = weight_unit
                for field_name in ("length", "width", "height"):
                    value = measurement_data.get(field_name)
                    setattr(
                        measurement,
                        f"{field_name}_mm",
                        MeasurementFields.convert_dimension_to_mm(value, dimension_unit) if value not in (None, "") else None,
                    )
                for input_name, model_field in (
                    ("product_weight", "product_weight_g"),
                    ("packaging_weight", "packaging_weight_g"),
                    ("shipping_weight", "shipping_weight_g"),
                    ("custom_weight", "custom_weight_g"),
                ):
                    value = measurement_data.get(input_name)
                    setattr(
                        measurement,
                        model_field,
                        MeasurementFields.convert_weight_to_grams(value, weight_unit) if value not in (None, "") else None,
                    )
                measurement.custom_size = measurement_data.get("custom_size", "")
                measurement.full_clean()
                measurement.save()


class TestEmailForm(forms.Form):
    recipient = forms.EmailField(label="Recipient email", max_length=254)
