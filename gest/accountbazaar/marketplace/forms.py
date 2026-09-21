from django import forms

from .models import Listing


class ListingForm(forms.ModelForm):
    class Meta:
        model = Listing
        fields = ("category", "title", "description", "price")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
        }
