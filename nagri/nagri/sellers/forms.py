import re
from django import forms
from .models import SellerApplication
from products.models import Category, Product, SubCategory

from PIL import Image, UnidentifiedImageError


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


class SellerProductForm(forms.ModelForm):
    stock = forms.IntegerField(min_value=0, initial=0, required=False)

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
        self.fields["category"].queryset = Category.objects.order_by("name")
        self.fields["subcategory"].queryset = SubCategory.objects.none()

        if self.instance and self.instance.pk:
            self.fields["subcategory"].queryset = SubCategory.objects.filter(category=self.instance.category).order_by("name")

        if self.data.get("category"):
            category_id = self.data.get("category")
            if category_id:
                self.fields["subcategory"].queryset = SubCategory.objects.filter(category_id=category_id).order_by("name")

    def clean_stock(self):
        value = self.cleaned_data.get("stock")
        return value if value is not None else 0

    def save(self, commit=True, seller=None):
        product = super().save(commit=False)
        if seller is not None:
            product.seller = seller
        if commit:
            product.save()
            from products.models import Inventory
            inventory_data = {"stock_quantity": self.cleaned_data.get("stock", 0), "low_stock_threshold": 5}
            Inventory.objects.update_or_create(product=product, defaults=inventory_data)
        return product


class TestEmailForm(forms.Form):
    recipient = forms.EmailField(label="Recipient email", max_length=254)
