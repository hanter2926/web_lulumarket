from django import forms
from .models import UserProfile, Address


class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['full_name', 'avatar']


class NotificationForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['notif_order_updates', 'notif_promotions', 'notif_important']


class AppearanceForm(forms.ModelForm):
    APPEARANCE_CHOICES = [
        ('light', 'Light'),
        ('dark', 'Dark'),
        ('system', 'System Default'),
    ]

    appearance = forms.ChoiceField(choices=APPEARANCE_CHOICES)

    class Meta:
        model = UserProfile
        fields = ['appearance']


class LanguageForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['language']


class AddressForm(forms.ModelForm):
    label = forms.ChoiceField(choices=Address.LABEL_CHOICES)

    class Meta:
        model = Address
        fields = [
            'label', 'full_name', 'phone', 'address_line_1', 'address_line_2',
            'city', 'state', 'country', 'pincode', 'landmark',
            'latitude', 'longitude', 'is_default',
        ]
        widgets = {
            'latitude': forms.NumberInput(attrs={
                'step': 'any',
                'inputmode': 'decimal',
                'min': '-90',
                'max': '90',
            }),
            'longitude': forms.NumberInput(attrs={
                'step': 'any',
                'inputmode': 'decimal',
                'min': '-180',
                'max': '180',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.label not in dict(Address.LABEL_CHOICES):
            self.fields['label'].choices = (
                *Address.LABEL_CHOICES,
                (self.instance.label, self.instance.label),
            )

    def clean(self):
        cleaned_data = super().clean()
        latitude = cleaned_data.get('latitude')
        longitude = cleaned_data.get('longitude')
        if (latitude is None) != (longitude is None):
            message = 'Enter both coordinates, or leave both blank.'
            self.add_error('latitude', message)
            self.add_error('longitude', message)
        return cleaned_data
