from django import forms

from .models import Listing


class ListingForm(forms.ModelForm):
    MAX_IMAGE_SIZE = 5 * 1024 * 1024
    ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

    class Meta:
        model = Listing
        fields = ("image", "category", "title", "description", "price")
        widgets = {
            "image": forms.ClearableFileInput(attrs={
                "accept": ".jpg,.jpeg,.png,.webp",
                "data-image-input": "true",
            }),
            "title": forms.TextInput(attrs={"placeholder": "Enter account title"}),
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
            "description": "Description",
            "price": "Price",
        }
        help_texts = {"image": "Upload an image of the account/listing (optional)"}

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image:
            return image
        if image.size > self.MAX_IMAGE_SIZE:
            raise forms.ValidationError("Please choose an image smaller than 5 MB.")
        if image.content_type not in self.ALLOWED_IMAGE_TYPES:
            raise forms.ValidationError("Use a JPG, JPEG, PNG, or WebP image.")
        return image
