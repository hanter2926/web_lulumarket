from django import forms
from django.core.validators import URLValidator

from .models import Listing


class ListingForm(forms.ModelForm):
    MAX_IMAGE_SIZE = 5 * 1024 * 1024
    ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
    PUBLIC_URL_VALIDATOR = URLValidator(schemes=("http", "https"))

    class Meta:
        model = Listing
        fields = (
            "image", "category", "title", "game_name", "game_id", "game_level", "game_rank",
            "website_name", "website_url", "app_name", "app_url", "platform", "features",
            "public_details", "description", "price",
        )
        widgets = {
            "image": forms.ClearableFileInput(attrs={
                "accept": ".jpg,.jpeg,.png,.webp",
                "data-image-input": "true",
            }),
            "category": forms.Select(attrs={"data-category-input": "true"}),
            "title": forms.TextInput(attrs={"placeholder": "Enter account title"}),
            "game_name": forms.TextInput(attrs={"placeholder": "Enter game name"}),
            "game_id": forms.TextInput(attrs={"placeholder": "Public game or player ID"}),
            "game_level": forms.TextInput(attrs={"placeholder": "Optional level"}),
            "game_rank": forms.TextInput(attrs={"placeholder": "Optional rank"}),
            "website_name": forms.TextInput(attrs={"placeholder": "Enter website name"}),
            "website_url": forms.URLInput(attrs={"placeholder": "https://example.com"}),
            "app_name": forms.TextInput(attrs={"placeholder": "Enter app name"}),
            "app_url": forms.URLInput(attrs={"placeholder": "https://demo.example.com"}),
            "platform": forms.TextInput(attrs={"placeholder": "Optional platform"}),
            "features": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional public features"}),
            "public_details": forms.Textarea(attrs={"rows": 3, "placeholder": "Optional public identifier or details"}),
            "description": forms.Textarea(attrs={
                "rows": 5,
                "placeholder": "Describe what is included with this account...",
            }),
            "price": forms.NumberInput(attrs={
                "min": "0",
                "step": "0.01",
                "placeholder": "Enter price",
            }),
        }
        labels = {
            "image": "Account Image",
            "category": "Category",
            "title": "Title",
            "game_name": "Game Name",
            "game_id": "Game ID / Player ID",
            "game_level": "Level",
            "game_rank": "Rank",
            "website_name": "Website Name",
            "website_url": "Live Website URL",
            "app_name": "App Name",
            "app_url": "App / Demo URL",
            "platform": "Platform",
            "features": "Technology / Features",
            "public_details": "Public Identifier / Details",
            "description": "Description",
            "price": "Price",
        }
        help_texts = {"image": "Upload an image of the account/listing (optional)"}

    CATEGORY_FIELDS = {
        "game": {"game_name", "game_id", "game_level", "game_rank"},
        "gaming": {"game_name", "game_id", "game_level", "game_rank"},
        "website": {"website_name", "website_url"},
        "app": {"app_name", "app_url", "platform", "features"},
        "other": {"public_details"},
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            for category, category_fields in self.CATEGORY_FIELDS.items():
                if field_name in category_fields:
                    field.category_group = category
                    field.widget.attrs.setdefault("data-category-field", category)
                    break
            else:
                field.category_group = ""
        self.fields["website_url"].validators.append(self.PUBLIC_URL_VALIDATOR)
        self.fields["app_url"].validators.append(self.PUBLIC_URL_VALIDATOR)

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("category")
        required_fields = {
            "game": ("game_name", "game_id"),
            "gaming": ("game_name", "game_id"),
            "website": ("website_name", "website_url"),
            "app": ("app_name",),
        }.get(category, ())
        for field_name in required_fields:
            if not cleaned_data.get(field_name):
                self.add_error(field_name, "This field is required for this category.")
        return cleaned_data

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image:
            return image
        if image.size > self.MAX_IMAGE_SIZE:
            raise forms.ValidationError("Please choose an image smaller than 5 MB.")
        if image.content_type not in self.ALLOWED_IMAGE_TYPES:
            raise forms.ValidationError("Use a JPG, JPEG, PNG, or WebP image.")
        return image
