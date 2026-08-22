from django import forms
from .models import Product


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            "name",
            "slug",
            "category",
            "short_description",
            "description",
            "price",
            "stock",
            "image",
            "is_featured",
            "is_active",
        ]
