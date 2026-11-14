import json
from decimal import Decimal, InvalidOperation
from datetime import date

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q

from .models import (
    DIMENSION_UNIT_CHOICES,
    WEIGHT_UNIT_CHOICES,
    MeasurementRequirement,
    Product,
    ProductAttributeDefinition,
    ProductAttributeValue,
    ProductMeasurement,
    ProductVariant,
    VariantAttributeDefinition,
)


MEASUREMENT_INPUTS = {
    "length": "length_mm",
    "width": "width_mm",
    "height": "height_mm",
    "product_weight": "product_weight_g",
    "packaging_weight": "packaging_weight_g",
    "shipping_weight": "shipping_weight_g",
    "custom_weight": "custom_weight_g",
}


class MeasurementFormMixin:
    measurement_field_specs = {
        "dimension_unit": lambda: forms.ChoiceField(choices=DIMENSION_UNIT_CHOICES, initial="cm", required=False),
        "weight_unit": lambda: forms.ChoiceField(choices=WEIGHT_UNIT_CHOICES, initial="g", required=False),
        "length": lambda: forms.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"), required=False),
        "width": lambda: forms.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"), required=False),
        "height": lambda: forms.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"), required=False),
        "product_weight": lambda: forms.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"), required=False),
        "packaging_weight": lambda: forms.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"), required=False),
        "shipping_weight": lambda: forms.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"), required=False),
        "custom_size": lambda: forms.CharField(max_length=255, required=False),
        "custom_weight": lambda: forms.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"), required=False),
    }

    def initialize_measurements(self, product):
        for field_name, factory in self.measurement_field_specs.items():
            self.fields[field_name] = factory()
        self.product_for_measurements = product
        measurement = getattr(product, "measurement", None) if product and product.pk else None
        if measurement is None:
            return
        self.initial.setdefault("dimension_unit", measurement.dimension_unit)
        self.initial.setdefault("weight_unit", measurement.weight_unit)
        for field_name in ("length", "width", "height"):
            self.initial.setdefault(
                field_name,
                measurement.dimension_in_display_unit(getattr(measurement, MEASUREMENT_INPUTS[field_name])),
            )
        for field_name in ("product_weight", "packaging_weight", "shipping_weight", "custom_weight"):
            self.initial.setdefault(
                field_name,
                measurement.weight_in_display_unit(getattr(measurement, MEASUREMENT_INPUTS[field_name])),
            )
        self.initial.setdefault("custom_size", measurement.custom_size)

    def clean_measurement_requirements(self, cleaned_data, category, subcategory):
        if category is None:
            return
        requirements = {
            item.field_name: item
            for item in MeasurementRequirement.objects.filter(category=category, subcategory__isnull=True)
        }
        if subcategory:
            requirements.update({
                item.field_name: item
                for item in MeasurementRequirement.objects.filter(category=category, subcategory=subcategory)
            })
        input_by_model_field = {model_field: input_name for input_name, model_field in MEASUREMENT_INPUTS.items()}
        for field_name, requirement in requirements.items():
            if not requirement.is_required:
                continue
            input_name = input_by_model_field.get(field_name, field_name)
            if not cleaned_data.get(input_name):
                self.add_error(input_name, "This measurement is required for the selected category.")

    def save_measurements(self, product):
        data = self.cleaned_data
        measurement, _ = ProductMeasurement.objects.get_or_create(product=product)
        measurement.dimension_unit = data.get("dimension_unit") or "cm"
        measurement.weight_unit = data.get("weight_unit") or "g"
        for input_name in ("length", "width", "height"):
            value = data.get(input_name)
            setattr(
                measurement,
                MEASUREMENT_INPUTS[input_name],
                measurement.convert_dimension_to_mm(value, measurement.dimension_unit) if value is not None else None,
            )
        for input_name in ("product_weight", "packaging_weight", "shipping_weight", "custom_weight"):
            value = data.get(input_name)
            setattr(
                measurement,
                MEASUREMENT_INPUTS[input_name],
                measurement.convert_weight_to_grams(value, measurement.weight_unit) if value is not None else None,
            )
        measurement.custom_size = data.get("custom_size", "")
        measurement.full_clean()
        measurement.save()
        return measurement


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name", "slug", "sku", "category", "subcategory", "seller", "store", "brand",
            "short_description", "description", "price", "compare_price",
            "cost_price", "tax_rate", "tax_inclusive", "scheduled_sale_price",
            "scheduled_sale_start", "scheduled_sale_end", "image",
            "is_featured", "is_bestseller", "is_active", "review_status",
            "rejection_reason",
        ]


class VariantAttributesField(forms.JSONField):
    default_error_messages = {
        "invalid": "Enter a JSON object mapping variant attribute keys to values."
    }

    def to_python(self, value):
        result = super().to_python(value)
        if result is None:
            return {}
        if not isinstance(result, dict):
            raise ValidationError(self.error_messages["invalid"])
        return result


class SellerVariantField(forms.JSONField):
    widget = forms.Textarea(attrs={"rows": 8, "class": "form-control"})

    def to_python(self, value):
        result = super().to_python(value)
        if result in (None, ""):
            return []
        if not isinstance(result, list) or any(not isinstance(item, dict) for item in result):
            raise ValidationError("Enter a JSON list of variant objects.")
        return result


def serialize_product_variants(product):
    if not product.pk:
        return "[]"
    values = []
    for variant in product.variants.select_related("inventory", "measurement").order_by("id"):
        inventory = getattr(variant, "inventory", None)
        measurement = getattr(variant, "measurement", None)
        measurement_data = None
        if measurement is not None:
            measurement_data = {
                "dimension_unit": measurement.dimension_unit,
                "length": str(measurement.dimension_in_display_unit(measurement.length_mm)) if measurement.length_mm is not None else None,
                "width": str(measurement.dimension_in_display_unit(measurement.width_mm)) if measurement.width_mm is not None else None,
                "height": str(measurement.dimension_in_display_unit(measurement.height_mm)) if measurement.height_mm is not None else None,
                "weight_unit": measurement.weight_unit,
                "product_weight": str(measurement.weight_in_display_unit(measurement.product_weight_g)) if measurement.product_weight_g is not None else None,
                "packaging_weight": str(measurement.weight_in_display_unit(measurement.packaging_weight_g)) if measurement.packaging_weight_g is not None else None,
                "shipping_weight": str(measurement.weight_in_display_unit(measurement.shipping_weight_g)) if measurement.shipping_weight_g is not None else None,
                "custom_size": measurement.custom_size,
                "custom_weight": str(measurement.weight_in_display_unit(measurement.custom_weight_g)) if measurement.custom_weight_g is not None else None,
            }
        values.append({
            "id": variant.pk,
            "attributes": variant.attributes,
            "sku": variant.sku,
            "price": str(variant.price) if variant.price is not None else None,
            "compare_price": str(variant.compare_price) if variant.compare_price is not None else None,
            "stock_quantity": inventory.stock_quantity if inventory else 0,
            "enabled": variant.is_active,
            "measurement": measurement_data,
        })
    return json.dumps(values, indent=2)


def serialize_product_attributes(product):
    if not product.pk:
        return "{}"
    values = {
        row.definition.key: row.value
        for row in product.attribute_values.select_related("definition").all()
    }
    return json.dumps(values, indent=2)


def validate_product_attribute_payload(product, values):
    category_definitions = ProductAttributeDefinition.objects.filter(
        category=product.category,
        subcategory__isnull=True,
        is_active=True,
    )
    definition_map = {definition.key: definition for definition in category_definitions}
    if product.subcategory_id:
        definition_map.update({
            definition.key: definition
            for definition in ProductAttributeDefinition.objects.filter(
                category=product.category,
                subcategory=product.subcategory,
                is_active=True,
            )
        })
    unknown = set(values) - set(definition_map)
    if unknown:
        raise ValidationError(
            "Unknown product attributes: " + ", ".join(sorted(unknown))
        )
    for definition in definition_map.values():
        value = values.get(definition.key)
        empty = value is None or value == "" or value == []
        if definition.is_required and empty:
            raise ValidationError(f"{definition.label} is required.")
        if empty:
            continue
        if definition.data_type == "text" and not isinstance(value, str):
            raise ValidationError(f"{definition.label} must be text.")
        if definition.data_type == "integer" and (
            isinstance(value, bool) or not isinstance(value, int)
        ):
            raise ValidationError(f"{definition.label} must be a whole number.")
        if definition.data_type == "decimal":
            try:
                number = Decimal(str(value))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValidationError(f"{definition.label} must be a decimal number.") from exc
            if not number.is_finite():
                raise ValidationError(f"{definition.label} must be a finite decimal number.")
        if definition.data_type == "boolean" and not isinstance(value, bool):
            raise ValidationError(f"{definition.label} must be true or false.")
        if definition.data_type == "date":
            try:
                date.fromisoformat(value)
            except (TypeError, ValueError) as exc:
                raise ValidationError(f"{definition.label} must use YYYY-MM-DD format.") from exc
        if definition.data_type == "dropdown" and value not in definition.options:
            raise ValidationError(f"{definition.label} must use a configured option.")
        if definition.data_type == "multi_select" and (
            not isinstance(value, list)
            or any(item not in definition.options for item in value)
        ):
            raise ValidationError(f"{definition.label} must contain configured options.")


def validate_variant_payload(product, variants):
    seen = set()
    definitions = VariantAttributeDefinition.objects.filter(category=product.category).filter(
        Q(subcategory__isnull=True) | Q(subcategory=product.subcategory)
    )
    definition_map = {definition.key: definition for definition in definitions}
    for index, variant in enumerate(variants, start=1):
        attributes = variant.get("attributes")
        if not isinstance(attributes, dict) or not attributes:
            raise ValidationError(f"Variant {index} must include an attributes object.")
        normalized = json.dumps(attributes, sort_keys=True, separators=(",", ":"))
        if normalized in seen:
            raise ValidationError(f"Variant {index} duplicates an existing attribute combination.")
        if len(normalized) > 512:
            raise ValidationError(f"Variant {index} attribute combination is too long.")
        seen.add(normalized)
        variant_id = variant.get("id")
        if variant_id is not None and (
            not isinstance(variant_id, int) or isinstance(variant_id, bool)
        ):
            raise ValidationError(f"Variant {index} has an invalid ID.")
        if product.pk:
            existing_combinations = ProductVariant.objects.filter(
                product=product,
                combination_key=normalized,
            )
            if variant_id:
                existing_combinations = existing_combinations.exclude(pk=variant_id)
            if existing_combinations.exists():
                raise ValidationError(f"Variant {index} duplicates an existing attribute combination.")
        if "enabled" in variant and not isinstance(variant["enabled"], bool):
            raise ValidationError(f"Variant {index} enabled must be true or false.")
        for definition in definitions:
            if definition.is_required and not attributes.get(definition.key):
                raise ValidationError(f"Variant {index} is missing {definition.label}.")
        for key, value in attributes.items():
            definition = definition_map.get(key)
            if not isinstance(key, str) or not isinstance(value, str) or not value.strip():
                raise ValidationError(f"Variant {index} attributes must have non-empty text keys and values.")
            if definition and definition.options and value not in definition.options:
                raise ValidationError(f"{value!r} is not a valid value for {definition.label}.")
        price = variant.get("price")
        if price not in (None, ""):
            try:
                numeric_price = Decimal(str(price))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValidationError(f"Variant {index} has an invalid price.") from exc
            if not numeric_price.is_finite() or not Decimal("0.01") <= numeric_price <= Decimal("999999999.99"):
                raise ValidationError(f"Variant {index} price must be between 0.01 and 999999999.99.")
        compare_price = variant.get("compare_price")
        if compare_price not in (None, ""):
            try:
                numeric_compare_price = Decimal(str(compare_price))
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise ValidationError(f"Variant {index} has an invalid regular price.") from exc
            if not numeric_compare_price.is_finite() or not Decimal("0.00") <= numeric_compare_price <= Decimal("999999999.99"):
                raise ValidationError(f"Variant {index} regular price is outside the supported range.")
            if price not in (None, "") and numeric_compare_price < Decimal(str(price)):
                raise ValidationError(f"Variant {index} regular price cannot be below its price.")
        sku = variant.get("sku")
        if sku not in (None, ""):
            if not isinstance(sku, str) or len(sku) > 64:
                raise ValidationError(f"Variant {index} SKU must be at most 64 characters.")
            duplicates = ProductVariant.objects.filter(sku=sku)
            if variant_id:
                duplicates = duplicates.exclude(pk=variant_id)
            if duplicates.exists():
                raise ValidationError(f"Variant {index} SKU is already in use.")
        measurement = variant.get("measurement")
        if measurement is not None:
            if not isinstance(measurement, dict):
                raise ValidationError(f"Variant {index} measurement must be an object.")
            dimension_unit = measurement.get("dimension_unit", "cm")
            weight_unit = measurement.get("weight_unit", "g")
            if dimension_unit not in {"mm", "cm", "inch", "feet"}:
                raise ValidationError(f"Variant {index} has an invalid dimension unit.")
            if weight_unit not in {"g", "kg"}:
                raise ValidationError(f"Variant {index} has an invalid weight unit.")
            custom_size = measurement.get("custom_size", "")
            if not isinstance(custom_size, str) or len(custom_size) > 255:
                raise ValidationError(f"Variant {index} custom size must be at most 255 characters.")
            for name in ("length", "width", "height", "product_weight", "packaging_weight", "shipping_weight", "custom_weight"):
                value = measurement.get(name)
                if value not in (None, ""):
                    try:
                        numeric_value = Decimal(str(value))
                    except (InvalidOperation, TypeError, ValueError) as exc:
                        raise ValidationError(f"Variant {index} has an invalid {name.replace('_', ' ')}.") from exc
                    if not numeric_value.is_finite() or numeric_value <= 0:
                        raise ValidationError(f"Variant {index} {name.replace('_', ' ')} must be greater than zero.")
        stock = variant.get("stock_quantity", 0)
        if isinstance(stock, bool) or not isinstance(stock, int) or stock < 0:
            raise ValidationError(f"Variant {index} stock must be a non-negative integer.")
