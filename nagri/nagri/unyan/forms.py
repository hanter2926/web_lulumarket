from django import forms
from .models import HomeSlider


class ContactSupportForm(forms.Form):
    name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Your full name"}),
    )
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "you@example.com"}),
    )
    subject = forms.CharField(
        max_length=200,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "How can we help?"}),
    )
    message = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 6, "placeholder": "Tell us about your issue or question..."}),
    )


class HomeSliderForm(forms.ModelForm):
    """Form for creating and editing homepage sliders."""
    
    class Meta:
        model = HomeSlider
        fields = ['title', 'subtitle', 'image', 'mobile_image', 'button_text', 'button_link', 'display_order', 'is_active']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Summer Sale 2024',
                'maxlength': '200'
            }),
            'subtitle': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Up to 50% Off',
                'maxlength': '300'
            }),
            'image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
            'mobile_image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
            'button_text': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Shop Now, Learn More',
                'maxlength': '100'
            }),
            'button_link': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Internal: /products/ | External: https://example.com',
                'maxlength': '500'
            }),
            'display_order': forms.NumberInput(attrs={
                'class': 'form-control',
                'type': 'number',
                'min': '0',
                'placeholder': 'Lower numbers display first'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
            }),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        is_active = cleaned_data.get('is_active')
        
        # Check active slider limit for new sliders
        if is_active and not self.instance.pk:
            active_count = HomeSlider.objects.filter(is_active=True).count()
            if active_count >= 8:
                raise forms.ValidationError(
                    'Cannot create more than 8 active sliders. Deactivate an existing slider first.',
                    code='max_active_sliders'
                )
        # Check limit when reactivating
        elif is_active and self.instance.pk and not self.instance.is_active:
            active_count = HomeSlider.objects.filter(is_active=True).count()
            if active_count >= 8:
                raise forms.ValidationError(
                    'Cannot activate more than 8 sliders. Deactivate an existing slider first.',
                    code='max_active_sliders'
                )
        
        return cleaned_data
