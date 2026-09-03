from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class AccountRegistrationForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")


from .models import HomeSlider


class HomeSliderForm(forms.ModelForm):
    class Meta:
        model = HomeSlider
        fields = [
            'title', 'subtitle', 'image', 'mobile_image', 'button_text', 'button_link', 'display_order', 'is_active'
        ]
        widgets = {
            'button_link': forms.TextInput(attrs={'placeholder': 'https://example.com/path or /products/?id=1'}),
        }

    def clean_button_link(self):
        link = self.cleaned_data.get('button_link', '').strip()
        # Basic safety: disallow javascript: urls
        if link.lower().startswith('javascript:'):
            raise forms.ValidationError('Invalid URL')
        return link
